import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_furniture.json")
INPUT_BOUND = os.path.join(OUTPUTS_DIR, "boundary_aligned.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_table.json")

TABLE_DEPTH = 35.0
TABLE_WIDTH = 80.0
WALL_PADDING = 2.0
OBJECT_PADDING = 5.0
DOOR_CLEARANCE = 20.0

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def save_json(path, data):
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class GeometryUtils:
    @staticmethod
    def dist_sq(p1, p2):
        return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

    @staticmethod
    def rotate_point(cx, cy, angle_deg, p):
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        dx, dy = p[0] - cx, p[1] - cy
        return [cx + dx*cos_a - dy*sin_a, cy + dx*sin_a + dy*cos_a]

    @staticmethod
    def get_rect_corners(center, w, h, angle):
        cx, cy = center
        dx, dy = w/2, h/2
        pts = [[cx-dx, cy-dy], [cx+dx, cy-dy], [cx+dx, cy+dy], [cx-dx, cy+dy]]
        return np.array([GeometryUtils.rotate_point(cx, cy, angle, p) for p in pts], dtype=np.float32)

    @staticmethod
    def check_rect_overlap(rect1, rect2):
        for p in rect1:
            if cv2.pointPolygonTest(rect2, (float(p[0]), float(p[1])), False) >= 0: return True
        for p in rect2:
            if cv2.pointPolygonTest(rect1, (float(p[0]), float(p[1])), False) >= 0: return True
        return False

    @staticmethod
    def point_line_dist(px, py, x1, y1, x2, y2):
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
    def calculate_corner_angle(p_prev, p_curr, p_next):
        """Trả về góc (độ) tại đỉnh p_curr"""
        v1 = np.array(p_prev) - np.array(p_curr)
        v2 = np.array(p_next) - np.array(p_curr)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0

        dot = np.dot(v1, v2)
        cos_angle = max(-1.0, min(1.0, dot / (norm1 * norm2)))
        angle = math.degrees(math.acos(cos_angle))
        return angle

class TablePlacer:
    def __init__(self, room_data, bound_data):
        self.rooms = room_data.get('rooms', []) if room_data else []
        self.bound_pts = bound_data.get('points', []) if bound_data else []
        self.all_doors = []
        # Thu thập cửa từ room data
        for r in self.rooms:
            if 'door' in r: self.all_doors.append(r['door']['position'])

    def get_room_edges(self, room):
        corners = room.get('snapped_corners', [])
        edges = []
        n = len(corners)
        for i in range(n):
            p1 = np.array(corners[i]); p2 = np.array(corners[(i+1)%n])
            edges.append({'p1': p1, 'p2': p2, 'mid': (p1+p2)/2, 'length': np.linalg.norm(p2-p1), 'index': i})
        return edges

    def is_orthogonal(self, edge):
        dx = abs(edge['p1'][0] - edge['p2'][0])
        dy = abs(edge['p1'][1] - edge['p2'][1])
        return dx < 2.0 or dy < 2.0

    def is_exterior(self, edge):
        n = len(self.bound_pts)
        if n == 0: return False # Không có boundary data thì coi như không phải exterior
        mid = edge['mid']
        for i in range(n):
            p1 = self.bound_pts[i]; p2 = self.bound_pts[(i+1)%n]
            if GeometryUtils.point_line_dist(mid[0], mid[1], p1['x'], p1['y'], p2['x'], p2['y']) < 15.0:
                return True
        return False

    def check_validity(self, rect, room):
        # 1. Inside Room
        poly = np.array(room['snapped_corners'], dtype=np.float32)
        for p in rect:
            if cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), False) < 0: return False

        # 2. Global Door Check
        for d in self.all_doors:
            if cv2.pointPolygonTest(rect, (float(d[0]), float(d[1])), True) > -DOOR_CLEARANCE:
                return False

        # 3. Furniture Overlap (Bed)
        # Kiểm tra xem room này đã có furniture chưa (ví dụ từ bước add_bed)
        for f in room.get('furniture', []):
            if f['type'] == 'bed':
                bed_rect = np.array(f['corners'], dtype=np.float32)
                if GeometryUtils.check_rect_overlap(rect, bed_rect): return False
                # Padding
                center = np.mean(rect, axis=0)
                if cv2.pointPolygonTest(bed_rect, (float(center[0]), float(center[1])), True) > -OBJECT_PADDING:
                    return False
        return True

    def try_place_in_corner(self, room, p_curr, p_next, p_prev):
        """Thử đặt bàn lọt thỏm vào góc"""
        v1 = np.array(p_next) - np.array(p_curr)
        len1 = np.linalg.norm(v1)
        if len1 < 1: return None
        v1_norm = v1 / len1

        v2 = np.array(p_prev) - np.array(p_curr)
        len2 = np.linalg.norm(v2)
        if len2 < 1: return None
        v2_norm = v2 / len2

        angle = math.degrees(math.atan2(v1[1], v1[0]))

        # Thử 2 tư thế: Dọc theo v1 hoặc v2
        orientations = [
            (TABLE_WIDTH, TABLE_DEPTH, angle),      # Dài theo v1
            (TABLE_DEPTH, TABLE_WIDTH, angle - 90)  # Dài theo v2
        ]

        for W, D, rot_angle in orientations:
            # Tính toán vị trí tâm bàn
            center_shift = v1_norm * (W/2 + WALL_PADDING) + v2_norm * (D/2 + WALL_PADDING)
            center = np.array(p_curr) + center_shift

            rect = GeometryUtils.get_rect_corners(center, W, D, rot_angle)

            if self.check_validity(rect, room):
                return {
                    'type': 'table', 'center': center.tolist(),
                    'size': [TABLE_WIDTH, TABLE_DEPTH], 
                    'angle': rot_angle, 'corners': rect.tolist()
                }
        return None

    def calculate_single_room(self, room, strategy='exterior'):
        """Hàm tính toán cho 1 phòng cụ thể (cho module import)"""
        print(f"\n🪑 Analyzing Table for {room['name']} ({strategy})")

        corners = room.get('snapped_corners', [])
        n = len(corners)
        door_pos = np.array(room['door']['position']) if 'door' in room else None

        # --- CHIẾN THUẬT 1: CORNER HUNTING ---
        valid_corners = []

        for i in range(n):
            p_curr = corners[i]
            p_prev = corners[(i - 1) % n]
            p_next = corners[(i + 1) % n]

            angle = GeometryUtils.calculate_corner_angle(p_prev, p_curr, p_next)

            if 85 <= angle <= 95:
                score = 0
                if strategy == 'study' and door_pos is not None:
                    # Ưu tiên XA cửa
                    score = GeometryUtils.dist_sq(p_curr, door_pos)
                elif strategy == 'exterior':
                    # Ưu tiên góc có tường ngoài (nếu có boundary data)
                    # Nếu không có boundary data, score = 0
                    edge1 = {'mid': (np.array(p_curr) + np.array(p_next))/2}
                    edge2 = {'mid': (np.array(p_curr) + np.array(p_prev))/2}
                    is_ext = self.is_exterior(edge1) or self.is_exterior(edge2)
                    if is_ext: score = 1000000 
                    else: score = 0 

                valid_corners.append({
                    'index': i, 'score': score,
                    'p_curr': p_curr, 'p_prev': p_prev, 'p_next': p_next
                })

        valid_corners.sort(key=lambda x: x['score'], reverse=True)

        for cand in valid_corners:
            result = self.try_place_in_corner(room, cand['p_curr'], cand['p_next'], cand['p_prev'])
            if result:
                print(f"   ✅ Table placed in CORNER {cand['index']} (Score: {cand['score']:.0f})")
                return (result['center'], result['angle'])

        # --- CHIẾN THUẬT 2: WALL SLIDING (FALLBACK) ---
        print("   ⚠️ No valid corner found. Switching to Wall Sliding...")

        edges = self.get_room_edges(room)
        edges = [e for e in edges if self.is_orthogonal(e)]

        if strategy == 'study' and door_pos is not None:
            edges.sort(key=lambda e: GeometryUtils.dist_sq(e['mid'], door_pos), reverse=True)
        else: 
            edges.sort(key=lambda e: (self.is_exterior(e), e['length']), reverse=True)

        for edge in edges:
            if edge['length'] < TABLE_WIDTH: continue

            v = edge['p2'] - edge['p1']; v_norm = v / np.linalg.norm(v)
            normal = np.array([-v_norm[1], v_norm[0]])
            if cv2.pointPolygonTest(np.array(room['snapped_corners'], dtype=np.float32),
                                    tuple(edge['mid'] + normal*5), False) < 0: normal = -normal
            angle = math.degrees(math.atan2(normal[1], normal[0])) - 90

            steps = int(edge['length'] / 5.0)
            if steps < 1: steps = 1
            t_vals = np.linspace(0.1, 0.9, steps)

            for t in t_vals:
                pos = edge['p1'] + t * v
                center = pos + normal * (TABLE_DEPTH/2 + WALL_PADDING)
                rect = GeometryUtils.get_rect_corners(center, TABLE_WIDTH, TABLE_DEPTH, angle)

                if self.check_validity(rect, room):
                    print(f"   ✅ Table placed on Edge {edge['index']} (Sliding)")
                    return (center.tolist(), angle)

        print(f"   ❌ Could not place Table in {room['name']}")
        return None

    def solve(self):
        """Hàm chạy độc lập"""
        for r in self.rooms:
            name = r['name'].lower()
            strategy = 'study' if 'study' in name else 'exterior'
            if 'study' in name or 'master' in name or 'bedroom_1' in name:
                res = self.calculate_single_room(r, strategy)
                if res:
                    center, angle = res
                    rect = GeometryUtils.get_rect_corners(center, TABLE_WIDTH, TABLE_DEPTH, angle)
                    if 'furniture' not in r: r['furniture'] = []
                    r['furniture'].append({
                        'type': 'table', 'center': center, 'size': [TABLE_WIDTH, TABLE_DEPTH],
                        'angle': angle, 'corners': rect.tolist()
                    })
        return self.rooms

# ================= MODULE INTERFACE =================
def calculate_table_position(room, door_side=None):
    """
    Wrapper function để tương thích với furniture_placement.py
    """
    # Cần tạo TablePlacer instance. 
    # Vấn đề: TablePlacer cần boundary data để check tường ngoài (exterior strategy).
    # Tuy nhiên furniture_placement thường không truyền boundary vào hàm này.
    # Giải pháp: Nếu không có boundary, TablePlacer sẽ fallback sang logic không check exterior.
    
    placer = TablePlacer({'rooms': [room]}, bound_data=None) 
    
    # Xác định strategy dựa trên tên phòng
    name = room['name'].lower()
    strategy = 'study' if 'study' in name else 'exterior'
    
    # Nếu phòng đã có Bed (từ bước trước), nó nằm trong room['furniture'].
    # TablePlacer sẽ tự check va chạm với Bed đó.
    
    return placer.calculate_single_room(room, strategy)

# ================= DEBUG VISUALIZATION =================
def visualize(rooms):
    plt.figure(figsize=(10, 10)); plt.gca().invert_yaxis()
    for r in rooms:
        c = r.get('snapped_corners', []);
        if c: p=c+[c[0]]; x,y=zip(*p); plt.plot(x,y,'b-')
        for f in r.get('furniture', []):
            col = 'g' if f['type']=='bed' else 'c'
            c=np.array(f['corners']); c=np.vstack([c,c[0]])
            plt.plot(c[:,0],c[:,1],col)
        if 'door' in r: plt.plot(r['door']['position'][0], r['door']['position'][1], 'ro')
    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_table_adv.png"))

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE) and os.path.exists(INPUT_BOUND):
        r_data = load_json(INPUT_FILE)
        b_data = load_json(INPUT_BOUND)
        placer = TablePlacer(r_data, b_data)
        r_data['rooms'] = placer.solve()
        save_json(OUTPUT_FILE, r_data)
        visualize(r_data['rooms'])