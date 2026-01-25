import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH =================
# Đường dẫn cho chế độ chạy độc lập (Standalone)
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_ROOM_FILE = os.path.join(OUTPUTS_DIR, "room_data_update.json")
INPUT_BOUNDARY_FILE = os.path.join(OUTPUTS_DIR, "boundary_aligned.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_doors_v3.json")

DOOR_WIDTH = 30.0
CORNER_PADDING = 15.0
BOUNDARY_TOLERANCE = 10.0

RESCUE_PRIORITY = ["study", "japan", "common", "bedroom", "living", "kitchen"]

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class GeometryUtils:
    @staticmethod
    def dist_sq(p1, p2):
        return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

    @staticmethod
    def point_line_segment_distance(px, py, x1, y1, x2, y2):
        A = px - x1; B = py - y1; C = x2 - x1; D = y2 - y1
        dot = A * C + B * D
        len_sq = C * C + D * D
        param = -1
        if len_sq != 0: param = dot / len_sq
        if param < 0: xx, yy = x1, y1
        elif param > 1: xx, yy = x2, y2
        else: xx, yy = x1 + param * C, y1 + param * D
        dx = px - xx; dy = py - yy
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def get_segment_overlap(p1, p2, p3, p4):
        v = np.array(p2) - np.array(p1)
        len_sq = np.dot(v, v)
        if len_sq == 0: return None
        dist3 = GeometryUtils.point_line_segment_distance(p3[0], p3[1], p1[0], p1[1], p2[0], p2[1])
        dist4 = GeometryUtils.point_line_segment_distance(p4[0], p4[1], p1[0], p1[1], p2[0], p2[1])
        if dist3 > 5.0 and dist4 > 5.0: return None

        t3 = np.dot(np.array(p3) - np.array(p1), v) / len_sq
        t4 = np.dot(np.array(p4) - np.array(p1), v) / len_sq
        start = max(0.0, min(t3, t4))
        end = min(1.0, max(t3, t4))
        if end > start + 0.05: return (start, end)
        return None

class DoorPlacerV3:
    def __init__(self, room_data, boundary_data=None):
        self.rooms = room_data.get('rooms', [])
        # Nếu không có boundary data, tạo dummy để tránh lỗi (cho trường hợp gọi từ module khác)
        if boundary_data:
            self.boundary_points = boundary_data.get('points', [])
        else:
            self.boundary_points = []
            
        self.living_room = next((r for r in self.rooms if 'living' in r['name'].lower()), None)
        self.boundary_segments = []
        
        n = len(self.boundary_points)
        for i in range(n):
            p1 = self.boundary_points[i]
            p2 = self.boundary_points[(i + 1) % n]
            self.boundary_segments.append({'p1': (p1['x'], p1['y']), 'p2': (p2['x'], p2['y'])})

        self.room_polys = {}
        for r in self.rooms:
            corners = r.get('snapped_corners', [])
            if corners and len(corners) > 2:
                self.room_polys[r['name']] = np.array(corners, dtype=np.float32)

    def get_room_edges(self, room):
        corners = room.get('snapped_corners', [])
        edges = []
        n = len(corners)
        for i in range(n):
            p1 = corners[i]; p2 = corners[(i + 1) % n]
            mid = [(p1[0] + p2[0])/2, (p1[1] + p2[1])/2]
            length = math.sqrt(GeometryUtils.dist_sq(p1, p2))
            v = np.array(p2) - np.array(p1)
            edges.append({'p1': p1, 'p2': p2, 'mid': mid, 'length': length, 'index': i, 'vector': v})
        return edges

    def is_edge_exterior(self, edge):
        # Nếu không có dữ liệu biên, giả sử không phải tường ngoài (để an toàn)
        if not self.boundary_segments: return False
        mid = edge['mid']
        for b_seg in self.boundary_segments:
            bx1, by1 = b_seg['p1']; bx2, by2 = b_seg['p2']
            dist = GeometryUtils.point_line_segment_distance(mid[0], mid[1], bx1, by1, bx2, by2)
            if dist < BOUNDARY_TOLERANCE: return True
        return False

    def get_occupied_segments(self, target_room, edge):
        occupied = []
        for other in self.rooms:
            if other['id'] == target_room['id'] or 'living' in other['name'].lower(): continue
            other_edges = self.get_room_edges(other)
            for oe in other_edges:
                overlap = GeometryUtils.get_segment_overlap(edge['p1'], edge['p2'], oe['p1'], oe['p2'])
                if overlap: occupied.append(overlap)
        occupied.sort()
        merged = []
        if occupied:
            curr_s, curr_e = occupied[0]
            for next_s, next_e in occupied[1:]:
                if next_s < curr_e: curr_e = max(curr_e, next_e)
                else: merged.append((curr_s, curr_e)); curr_s, curr_e = next_s, next_e
            merged.append((curr_s, curr_e))
        return merged

    def get_inward_render_angle(self, room_poly, pos_on_wall, wall_vector):
        v = wall_vector
        if np.linalg.norm(v) == 0: return 0
        normal = np.array([-v[1], v[0]])
        normal = normal / np.linalg.norm(normal)
        test_pt = (pos_on_wall[0] + normal[0] * 5, pos_on_wall[1] + normal[1] * 5)
        dist = cv2.pointPolygonTest(room_poly, test_pt, False)
        if dist < 0: normal = -normal
        atan2_angle = math.degrees(math.atan2(normal[1], normal[0]))
        # FIX: Cộng 90 độ để cửa quay vào trong
        render_angle = atan2_angle + 90
        return render_angle

    def attempt_rescue(self, room):
        print(f"   🚑 RESCUING {room['name']}...")
        candidates = []
        room_edges = self.get_room_edges(room)

        for other in self.rooms:
            if other['id'] == room['id']: continue
            p_score = 999
            other_name = other['name'].lower()
            for idx, key in enumerate(RESCUE_PRIORITY):
                if key in other_name: p_score = idx; break
            if p_score == 999 and ('bathroom' in other_name or 'toilet' in other_name): p_score = 1000

            other_edges = self.get_room_edges(other)
            for edge in room_edges:
                if self.is_edge_exterior(edge): continue
                for oe in other_edges:
                    overlap = GeometryUtils.get_segment_overlap(edge['p1'], edge['p2'], oe['p1'], oe['p2'])
                    if overlap:
                        overlap_len = (overlap[1] - overlap[0]) * edge['length']
                        if overlap_len >= DOOR_WIDTH:
                            candidates.append({'score': p_score, 'neighbor': other['name'], 'edge': edge, 'interval': overlap})

        if not candidates:
            print("      ❌ No neighbor found for rescue!")
            return False

        candidates.sort(key=lambda x: (x['score'], -x['edge']['length']))
        best = candidates[0]
        print(f"      ✅ Rescued by {best['neighbor']} (Score: {best['score']})")

        edge = best['edge']; t1, t2 = best['interval']
        margin_t = CORNER_PADDING / edge['length']
        safe_t1 = t1 + margin_t; safe_t2 = t2 - margin_t

        if safe_t2 <= safe_t1: final_t = (t1 + t2) / 2
        else:
            p1 = np.array(edge['p1']); v = np.array(edge['p2']) - p1
            lr_center = self.living_room['center']
            pos1 = p1 + safe_t1 * v
            dist1 = GeometryUtils.dist_sq(pos1, lr_center)
            t_width = DOOR_WIDTH / edge['length']
            t_end_check = safe_t2 - t_width
            if t_end_check < safe_t1: t_end_check = safe_t1
            pos2 = p1 + t_end_check * v
            dist2 = GeometryUtils.dist_sq(pos2, lr_center)
            final_t = safe_t1 if dist1 < dist2 else t_end_check

        p1 = np.array(edge['p1']); v = np.array(edge['p2']) - p1
        final_pos = p1 + final_t * v

        room_poly = self.room_polys[room['name']]
        render_angle = self.get_inward_render_angle(room_poly, final_pos, edge['vector'])

        room['door'] = {
            'position': final_pos.tolist(),
            'angle': render_angle,
            'edge_index': edge['index'],
            'type': 'rescue',
            'connect_to': best['neighbor']
        }
        return True

    def solve(self):
        if not self.living_room:
            print("⚠️ Living room not found.")
            return self.rooms

        lc = self.living_room['center']

        for room in self.rooms:
            if 'living' in room['name'].lower(): continue
            if room['name'] not in self.room_polys:
                print(f"⚠️ Skipping {room['name']} (no geometry found in cache)")
                continue

            print(f"\n🚪 Analyzing: {room['name']}")
            edges = self.get_room_edges(room)
            edges.sort(key=lambda e: GeometryUtils.dist_sq(e['mid'], lc))

            door_placed = False

            for edge in edges:
                if self.is_edge_exterior(edge): continue
                if edge['length'] < DOOR_WIDTH + 2 * CORNER_PADDING: continue

                occupied = self.get_occupied_segments(room, edge)

                free_intervals = []
                curr_t = 0.0
                t_pad = CORNER_PADDING / edge['length']
                for start, end in occupied:
                    if start > curr_t + t_pad: free_intervals.append((curr_t + t_pad, start - t_pad))
                    curr_t = max(curr_t, end)
                if curr_t < 1.0 - t_pad: free_intervals.append((curr_t + t_pad, 1.0 - t_pad))

                valid_intervals = [inter for inter in free_intervals if (inter[1]-inter[0])*edge['length'] >= DOOR_WIDTH]

                if valid_intervals:
                    best_t = -1
                    min_dist_to_center = float('inf')
                    p1 = np.array(edge['p1']); v = np.array(edge['p2']) - p1

                    for t_start, t_end in valid_intervals:
                        pos1 = p1 + t_start * v
                        dist1 = GeometryUtils.dist_sq(pos1, lc)
                        t_end_pos = t_end - (DOOR_WIDTH / edge['length'])
                        pos2 = p1 + t_end_pos * v
                        dist2 = GeometryUtils.dist_sq(pos2, lc)
                        if dist1 < min_dist_to_center: min_dist_to_center = dist1; best_t = t_start
                        if dist2 < min_dist_to_center: min_dist_to_center = dist2; best_t = t_end_pos

                    final_pos = p1 + best_t * v

                    room_poly = self.room_polys[room['name']]
                    render_angle = self.get_inward_render_angle(room_poly, final_pos, edge['vector'])

                    room['door'] = {
                        'position': final_pos.tolist(),
                        'angle': render_angle,
                        'edge_index': edge['index'],
                        'type': 'main'
                    }
                    door_placed = True
                    print(f"   ✅ Main Door placed on Edge {edge['index']} (Angle: {render_angle:.1f})")
                    break

            if not door_placed:
                self.attempt_rescue(room)
        return self.rooms

# ================= MODULE INTERFACE =================
def calculate_internal_doors(rooms, lr_contour=None, other_contours=None):
    """
    Wrapper function để tương thích với furniture_placement.py
    Logic: Tận dụng thuật toán DoorPlacerV3
    """
    # Tạo cấu trúc dữ liệu giả lập để khớp với input của class DoorPlacerV3
    room_data = {'rooms': rooms}
    # boundary_data có thể None, DoorPlacerV3 sẽ bỏ qua check tường ngoài nếu None
    placer = DoorPlacerV3(room_data, boundary_data=None)
    
    # Chạy thuật toán
    updated_rooms = placer.solve()
    
    # Trích xuất kết quả trả về định dạng list các doors
    doors = []
    for r in updated_rooms:
        if 'door' in r:
            d = r['door']
            # Convert angle sang side (top/bottom/left/right) nếu cần thiết cho renderer cũ
            # Nhưng tốt nhất nên dùng angle trực tiếp
            doors.append({
                'room_name': r['name'],
                'center': d['position'],
                'angle': d['angle'],
                'type': d.get('type', 'main'),
                'side': 'top' # Dummy side, nên dùng angle để render chính xác hơn
            })
    return doors

def get_door_side_and_pos(room, doors_list=None):
    """
    Helper function xác định vị trí cửa (trái/phải/trên/dưới) 
    dựa vào tọa độ so với tâm phòng.
    """
    if 'door' not in room: return None, None
    
    d_pos = room['door']['position']
    corners = room.get('snapped_corners', [])
    if not corners: return None, None
    
    min_x = min(c[0] for c in corners); max_x = max(c[0] for c in corners)
    min_y = min(c[1] for c in corners); max_y = max(c[1] for c in corners)
    
    # Simple bounding box check
    tol = 5.0
    if abs(d_pos[0] - min_x) < tol: return 'left', d_pos
    if abs(d_pos[0] - max_x) < tol: return 'right', d_pos
    if abs(d_pos[1] - min_y) < tol: return 'top', d_pos
    if abs(d_pos[1] - max_y) < tol: return 'bottom', d_pos
    
    return None, d_pos

# ================= DEBUG VISUALIZATION =================
def visualize(rooms, boundary_points):
    plt.figure(figsize=(10, 10))
    ax = plt.gca(); ax.invert_yaxis()

    if boundary_points:
        bx = [p['x'] for p in boundary_points]; by = [p['y'] for p in boundary_points]
        bx.append(bx[0]); by.append(by[0])
        plt.plot(bx, by, 'k-', linewidth=3)

    for room in rooms:
        corners = room.get('snapped_corners', [])
        if not corners: continue
        poly = corners + [corners[0]]; xs, ys = zip(*poly)
        plt.plot(xs, ys, 'b-', linewidth=1)

        if 'door' in room:
            d = room['door']
            x, y = d['position']
            plt.plot(x, y, 'ro', markersize=8, zorder=10)

            angle_rad = math.radians(d['angle'] + 90)
            dx = math.cos(angle_rad) * 25; dy = math.sin(angle_rad) * 25
            plt.arrow(x, y, dx, dy, head_width=8, color='r', zorder=10)

            label = "Rescue" if d.get('type') == 'rescue' else "Main"
            plt.text(x, y-10, label, fontsize=6, color='red', ha='center')

        if corners:
            try:
                M = cv2.moments(np.array(corners, dtype=np.int32))
                cx = int(M["m10"] / M["m00"]); cy = int(M["m01"] / M["m00"])
            except:
                cx, cy = np.mean(np.array(corners), axis=0)
            plt.text(cx, cy, room['name'], ha='center', fontsize=7, color='blue')

    plt.axis('equal')
    plt.savefig(os.path.join(OUTPUTS_DIR, "check_door_v3.png"))
    print(f"📸 Saved check image: {os.path.join(OUTPUTS_DIR, 'check_door_v3.png')}")

if __name__ == "__main__":
    if os.path.exists(INPUT_ROOM_FILE) and os.path.exists(INPUT_BOUNDARY_FILE):
        r_data = load_json(INPUT_ROOM_FILE)
        b_data = load_json(INPUT_BOUNDARY_FILE)

        placer = DoorPlacerV3(r_data, b_data)
        r_data['rooms'] = placer.solve()

        save_json(OUTPUT_FILE, r_data)
        visualize(r_data['rooms'], b_data['points'])
    else: print("Missing input files.")