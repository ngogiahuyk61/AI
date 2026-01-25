import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CONFIG =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_table.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_final.json")

# Tỷ lệ chia
MASTER_WASH_RATIO = 0.6 
TOILET_SPLIT_RATIO = 0.5 

WALL_PADDING = 2.0
DIAGONAL_CORNER_PADDING = 20.0 

# Kích thước nội thất
BATHTUB_WIDTH = 30.0
BATHTUB_LENGTH = 65.0

# --- CẤU HÌNH CỬA ---
DOOR_WIDTH = 30.0 
DOOR_CORNER_PADDING = 10.0 # Khoảng cách tối thiểu từ góc tường đến mép cửa

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

class GeometryUtils:
    @staticmethod
    def get_bbox(corners):
        pts = np.array(corners)
        return cv2.boundingRect(np.array(pts, dtype=np.float32))

    @staticmethod
    def poly_area(corners):
        pts = np.array(corners)
        return cv2.contourArea(np.array(pts, dtype=np.float32))

    @staticmethod
    def point_in_poly(pt, corners):
        return cv2.pointPolygonTest(np.array(corners, dtype=np.float32), pt, False) >= 0

    @staticmethod
    def get_rect_corners(center, w, h, angle):
        cx, cy = center; dx, dy = w/2, h/2
        pts = [[cx-dx, cy-dy], [cx+dx, cy-dy], [cx+dx, cy+dy], [cx-dx, cy+dy]]
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        res = []
        for x, y in pts:
            nx = cx + (x-cx)*cos_a - (y-cy)*sin_a
            ny = cy + (x-cx)*sin_a + (y-cy)*cos_a
            res.append([nx, ny])
        return np.array(res, dtype=np.float32)

    @staticmethod
    def dist_sq(p1, p2):
        return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

    @staticmethod
    def is_right_angle(p_prev, p_curr, p_next, tolerance=10.0):
        v1 = np.array(p_prev) - np.array(p_curr)
        v2 = np.array(p_next) - np.array(p_curr)
        len1 = np.linalg.norm(v1); len2 = np.linalg.norm(v2)
        if len1 == 0 or len2 == 0: return False
        cos_angle = np.dot(v1, v2) / (len1 * len2)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle_deg = math.degrees(math.acos(cos_angle))
        return abs(angle_deg - 90.0) < tolerance

class MiniDoorPlacer:
    def __init__(self, all_rooms):
        self.all_rooms = all_rooms
        self.living_room = next((r for r in all_rooms if 'living' in r['name'].lower()), None)
        
        self.other_room_polys = {}
        for r in all_rooms:
            if 'living' in r['name'].lower(): continue
            if 'snapped_corners' in r:
                self.other_room_polys[r['id']] = np.array(r['snapped_corners'], dtype=np.float32)

    def get_inward_render_angle(self, room_poly, pos_on_wall, wall_vector):
        v = wall_vector
        if np.linalg.norm(v) == 0: return 0
        normal = np.array([-v[1], v[0]]) 
        normal = normal / np.linalg.norm(normal)
        test_pt = (pos_on_wall[0] + normal[0] * 5, pos_on_wall[1] + normal[1] * 5)
        dist = cv2.pointPolygonTest(room_poly, test_pt, False)
        if dist < 0: normal = -normal 
        atan2_angle = math.degrees(math.atan2(normal[1], normal[0]))
        return atan2_angle - 90

    def is_blocked_by_neighbor(self, edge_midpoint, my_id):
        pt = tuple(edge_midpoint)
        parent_id = my_id - 200
        for r_id, poly in self.other_room_polys.items():
            if r_id == my_id: continue 
            if r_id == parent_id: continue 
            dist = cv2.pointPolygonTest(poly, pt, True)
            if dist > -2.0: return True 
        return False

    def place_door(self, room):
        print(f"      🚪 Placing NEW door for {room['name']} (ID: {room['id']})...")
        corners = room['snapped_corners']
        room_poly = np.array(corners, dtype=np.float32)
        target_center = self.living_room['center'] if self.living_room else [0,0]

        edges = []
        n = len(corners)
        for i in range(n):
            p1 = np.array(corners[i]); p2 = np.array(corners[(i + 1) % n])
            length = np.linalg.norm(p2 - p1)
            mid = (p1 + p2) / 2
            
            if length < DOOR_WIDTH + 5: continue
            if self.is_blocked_by_neighbor(mid, room['id']): continue 

            dist_to_center = GeometryUtils.dist_sq(mid, target_center)
            edges.append({
                'p1': p1, 'p2': p2, 
                'mid': mid, 
                'dist': dist_to_center, 
                'idx': i,
                'length': length
            })

        if not edges:
            print("      ⚠️ No valid wall found.")
            return False

        edges.sort(key=lambda x: x['dist'])
        best_edge = edges[0] 
        
        p1 = best_edge['p1']; p2 = best_edge['p2']
        v_wall = p2 - p1
        length = best_edge['length']

        # --- LOGIC MỚI: XÁC ĐỊNH VỊ TRÍ TRÊN TƯỜNG (OFFSET) ---
        # Kiểm tra nếu tường quá ngắn thì buộc phải đặt giữa
        if length < DOOR_WIDTH + 2 * DOOR_CORNER_PADDING:
            pos = p1 + 0.5 * v_wall
            print(f"      🔹 Wall too short, placing CENTER.")
        else:
            # Tính toán 2 vị trí ứng viên:
            # Tỷ lệ đệm (Padding Ratio)
            t_pad = DOOR_CORNER_PADDING / length
            # Tỷ lệ cửa (Door Ratio)
            t_door = DOOR_WIDTH / length # Vì tâm cửa nằm giữa DOOR_WIDTH, ta cần tính offset cho tâm

            # Vị trí 1: Gần đầu P1 (Cách P1 một đoạn Padding + Nửa cửa)
            t1 = t_pad + (0.5 * DOOR_WIDTH) / length
            pos1 = p1 + t1 * v_wall
            
            # Vị trí 2: Gần đầu P2 (Cách P2 một đoạn Padding + Nửa cửa)
            t2 = 1.0 - (t_pad + (0.5 * DOOR_WIDTH) / length)
            pos2 = p1 + t2 * v_wall

            # So sánh khoảng cách tới Living Room
            d1 = GeometryUtils.dist_sq(pos1, target_center)
            d2 = GeometryUtils.dist_sq(pos2, target_center)

            if d1 < d2:
                pos = pos1
                print(f"      🔹 Offset to side closer to Living Room (Near P1).")
            else:
                pos = pos2
                print(f"      🔹 Offset to side closer to Living Room (Near P2).")
        
        render_angle = self.get_inward_render_angle(room_poly, pos, v_wall)
        
        room['door'] = {
            'position': pos.tolist(),
            'angle': render_angle,
            'type': 'main',
            'generated': True,
            'connect_to': 'Living/Void'
        }
        print(f"      ✅ Door created on edge {best_edge['idx']}")
        return True

class BathroomProcessor:
    def __init__(self, room_data):
        self.rooms = room_data.get('rooms', [])
        bathrooms = [r for r in self.rooms if 'bathroom' in r['name'].lower()]
        bathrooms.sort(key=lambda x: x.get('area', 0), reverse=True)
        self.master_id = bathrooms[0]['id'] if bathrooms else -1
        self.door_placer = MiniDoorPlacer(self.rooms)

    def create_mask_from_room(self, room, canvas_size=(2000, 2000)):
        mask = np.zeros(canvas_size, dtype=np.uint8)
        corners = np.array(room['snapped_corners'], dtype=np.int32)
        cv2.fillPoly(mask, [corners], 255)
        return mask

    def contour_to_corners(self, contour):
        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        return [pt[0].tolist() for pt in approx]

    def split_logic(self, room, ratio, keep_both=True):
        print(f"🛁 Processing: {room['name']} (Master={keep_both})")
        max_coord = 2000
        mask_original = self.create_mask_from_room(room, (max_coord, max_coord))
        total_area = np.sum(mask_original > 0)
        target_wash_area = total_area * ratio
        
        x, y, w, h = GeometryUtils.get_bbox(room['snapped_corners'])
        door_pos = room['door']['position'] if 'door' in room else [0,0]
        split_axis = 'x' if w > h else 'y'

        best_cut_pos = -1
        min_diff = float('inf')
        start = x if split_axis == 'x' else y
        end = x + w if split_axis == 'x' else y + h
        
        final_mask_door_side = None
        final_mask_wall_side = None
        
        for pos in range(int(start), int(end), 5):
            mask_A = np.zeros_like(mask_original)
            if split_axis == 'x': mask_A[:, 0:pos] = 255
            else: mask_A[0:pos, :] = 255
            
            temp_cand = cv2.bitwise_and(mask_original, mask_A)
            area_A = np.sum(temp_cand > 0)
            
            dx, dy = int(door_pos[0]), int(door_pos[1])
            is_door_in_A = False
            if 0 <= dx < max_coord and 0 <= dy < max_coord:
                is_door_in_A = (mask_A[dy, dx] > 0)
            
            current_wash_area = area_A if is_door_in_A else (total_area - area_A)
            diff = abs(current_wash_area - target_wash_area)
            
            if diff < min_diff:
                min_diff = diff
                best_cut_pos = pos
                if is_door_in_A:
                    final_mask_door_side = temp_cand
                    final_mask_wall_side = cv2.bitwise_and(mask_original, cv2.bitwise_not(mask_A))
                else:
                    final_mask_door_side = cv2.bitwise_and(mask_original, cv2.bitwise_not(mask_A))
                    final_mask_wall_side = temp_cand

        result_rooms = []
        
        if keep_both:
            cnts, _ = cv2.findContours(final_mask_door_side, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                poly = self.contour_to_corners(cnts[0])
                wash_room = {
                    'id': room['id'] + 100, 'name': "Bathroom_Wash", 
                    'snapped_corners': poly, 'center': GeometryUtils.get_bbox(poly)[:2], 
                    'area': GeometryUtils.poly_area(poly),
                    'door': room['door'], 'furniture': []
                }
                result_rooms.append(wash_room)

        cnts, _ = cv2.findContours(final_mask_wall_side, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            poly = self.contour_to_corners(cnts[0])
            inner_name = "Bathroom_Bath" if keep_both else "Toilet"
            inner_room = {
                'id': room['id'] + 200, 'name': inner_name, 
                'snapped_corners': poly, 'center': GeometryUtils.get_bbox(poly)[:2], 
                'area': GeometryUtils.poly_area(poly),
                'furniture': []
            }
            
            if keep_both:
                p1, p2 = self.find_connection(mask_original, best_cut_pos, split_axis, max_coord)
                if p1 and p2:
                    p1_arr = np.array(p1); p2_arr = np.array(p2)
                    v_wall = p2_arr - p1_arr
                    d_pos = p1_arr + 0.5 * v_wall
                    angle = math.degrees(math.atan2(v_wall[1], v_wall[0]))
                    inner_room['door'] = {'position': d_pos.tolist(), 'angle': angle, 'type': 'sliding', 'connect_to': 'Bathroom_Wash'}
                    print(f"      ✅ Created Sliding Door at {d_pos}")
            else:
                self.door_placer.place_door(inner_room)

            result_rooms.append(inner_room)
            
        return result_rooms

    def find_connection(self, mask_original, cut_pos, axis, max_coord):
        p1, p2 = None, None
        if axis == 'x':
            if 0 <= cut_pos < max_coord:
                col = mask_original[:, cut_pos]; idxs = np.where(col > 0)[0]
                if len(idxs) > 0: p1 = [cut_pos, np.min(idxs)]; p2 = [cut_pos, np.max(idxs)]
        else:
            if 0 <= cut_pos < max_coord:
                row = mask_original[cut_pos, :]; idxs = np.where(row > 0)[0]
                if len(idxs) > 0: p1 = [np.min(idxs), cut_pos]; p2 = [np.max(idxs), cut_pos]
        return p1, p2

    def place_bathtub_fixed(self, room):
        print(f"   🛁 Placing Fixed Bathtub in {room['name']}...")
        if 'door' not in room: return

        door_pos = np.array(room['door']['position'])
        door_angle_raw = room['door']['angle']
        bathtub_angle = 0.0
        if abs(door_angle_raw) % 180 > 45 and abs(door_angle_raw) % 180 < 135:
            bathtub_angle = 90.0

        corners = room['snapped_corners']
        n = len(corners)
        is_corner_90 = []
        for i in range(n):
            p_prev = corners[(i - 1) % n]; p_curr = corners[i]; p_next = corners[(i + 1) % n]
            is_corner_90.append(GeometryUtils.is_right_angle(p_prev, p_curr, p_next))

        edges = []
        for i in range(n):
            p1 = np.array(corners[i]); p2 = np.array(corners[(i + 1) % n])
            length = np.linalg.norm(p2 - p1)
            edges.append({'p1': p1, 'p2': p2, 'length': length, 'idx': i})

        best_center = None
        best_rect = None
        max_dist_from_door = -1

        for i, edge in enumerate(edges):
            if edge['length'] < BATHTUB_LENGTH: continue
            pad_start = 2.0 if is_corner_90[i] else DIAGONAL_CORNER_PADDING
            pad_end = 2.0 if is_corner_90[(i + 1) % n] else DIAGONAL_CORNER_PADDING

            if edge['length'] < (pad_start + BATHTUB_LENGTH + pad_end): continue

            v_edge = edge['p2'] - edge['p1']
            v_norm = v_edge / edge['length']
            normal = np.array([-v_norm[1], v_norm[0]])
            if not GeometryUtils.point_in_poly(edge['p1'] + v_edge/2 + normal * 5, corners):
                normal = -normal

            t_start = (pad_start + BATHTUB_LENGTH/2) / edge['length']
            t_end = 1.0 - ((pad_end + BATHTUB_LENGTH/2) / edge['length'])

            steps = 10
            for k in range(steps + 1):
                t = t_start + (t_end - t_start) * (k / steps)
                pos_on_wall = edge['p1'] + v_edge * t
                center = pos_on_wall + normal * (BATHTUB_WIDTH/2 + WALL_PADDING)
                rect = GeometryUtils.get_rect_corners(center, BATHTUB_LENGTH, BATHTUB_WIDTH, bathtub_angle)

                valid = True
                for p in rect:
                    if not GeometryUtils.point_in_poly(p, corners): valid = False; break

                if valid:
                    dist = np.linalg.norm(center - door_pos)
                    if dist > max_dist_from_door:
                        max_dist_from_door = dist
                        best_center = center
                        best_rect = rect

        if best_center is not None:
            room['furniture'].append({
                'type': 'bathtub',
                'center': best_center.tolist(),
                'size': [BATHTUB_LENGTH, BATHTUB_WIDTH],
                'angle': bathtub_angle,
                'corners': best_rect.tolist()
            })
            print(f"      ✅ Bathtub placed successfully")

    def solve(self):
        final_rooms = []
        for room in self.rooms:
            if 'bathroom' not in room['name'].lower() and 'toilet' not in room['name'].lower():
                final_rooms.append(room)
                continue

            is_master = (room['id'] == self.master_id)
            ratio = MASTER_WASH_RATIO if is_master else TOILET_SPLIT_RATIO
            
            new_rooms = self.split_logic(room, ratio, keep_both=is_master)
            
            for nr in new_rooms:
                if is_master and nr['name'].endswith('_Bath'):
                    self.place_bathtub_fixed(nr)
            
            final_rooms.extend(new_rooms)
        return final_rooms

def visualize_final(rooms):
    plt.figure(figsize=(10, 10)); ax = plt.gca(); ax.invert_yaxis()
    for room in rooms:
        corners = room.get('snapped_corners', [])
        if not corners: continue
        poly = corners + [corners[0]]; xs, ys = zip(*poly)
        
        color = 'k'
        if 'Wash' in room['name']: color = 'c'
        elif 'Bath' in room['name']: color = 'm'
        elif 'Toilet' in room['name']: color = 'orange'
        
        plt.plot(xs, ys, color=color, linewidth=2)
        
        for item in room.get('furniture', []):
            c = np.array(item['corners']); c = np.vstack([c, c[0]])
            plt.plot(c[:,0], c[:,1], 'b-', linewidth=2)
            
        if 'door' in room:
            d = room['door']
            plt.plot(d['position'][0], d['position'][1], 'ro')
            if d.get('generated'):
                 plt.text(d['position'][0], d['position'][1], "NEW", fontsize=6, color='red')

    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_bathroom_split_v2.png"))

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE):
        data = load_json(INPUT_FILE)
        processor = BathroomProcessor(data)
        data['rooms'] = processor.solve()
        save_json(OUTPUT_FILE, data)
        visualize_final(data['rooms'])