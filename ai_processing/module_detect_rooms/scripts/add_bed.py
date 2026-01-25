import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH =================
# Đường dẫn cho chế độ chạy độc lập (Standalone)
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_doors_v3.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_furniture.json")

# Kích thước giường (Pixel) - Bạn có thể chỉnh lại cho khớp với asset
BED_WIDTH = 55.0
BED_LENGTH = 70.0
DOOR_CLEARANCE = 20.0
WALL_PADDING = 2.0
CORNER_SCORE_BONUS = 10000.0  # Điểm thưởng cực lớn cho góc vuông

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def save_json(path, data):
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
    def get_rect_corners(center, width, length, angle):
        cx, cy = center
        dx, dy = width / 2, length / 2
        pts = [[cx-dx, cy-dy], [cx+dx, cy-dy], [cx+dx, cy+dy], [cx-dx, cy+dy]]
        return np.array([GeometryUtils.rotate_point(cx, cy, angle, p) for p in pts], dtype=np.float32)

    @staticmethod
    def is_right_angle(p_prev, p_curr, p_next, tolerance=10.0):
        v1 = np.array(p_prev) - np.array(p_curr)
        v2 = np.array(p_next) - np.array(p_curr)
        len1 = np.linalg.norm(v1)
        len2 = np.linalg.norm(v2)
        if len1 == 0 or len2 == 0: return False
        cos_angle = np.dot(v1, v2) / (len1 * len2)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle_deg = math.degrees(math.acos(cos_angle))
        return abs(angle_deg - 90.0) < tolerance

    @staticmethod
    def calculate_corner_angle(p_prev, p_curr, p_next):
        v1 = np.array(p_prev) - np.array(p_curr)
        v2 = np.array(p_next) - np.array(p_curr)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0
        dot = np.dot(v1, v2)
        cos_angle = max(-1.0, min(1.0, dot / (norm1 * norm2)))
        return math.degrees(math.acos(cos_angle))

class BedPlacer:
    def __init__(self, room_data=None):
        self.rooms = room_data.get('rooms', []) if room_data else []
        self.all_doors = []
        # Thu thập vị trí tất cả các cửa để tránh va chạm toàn cục
        for r in self.rooms:
            if 'door' in r:
                self.all_doors.append(r['door']['position'])

    def set_external_doors(self, door_list):
        """Cho phép cập nhật danh sách cửa từ bên ngoài (cho module placement)"""
        self.all_doors = [d['center'] for d in door_list if 'center' in d]

    def get_room_edges_with_corners(self, room):
        corners = room.get('snapped_corners', [])
        edges = []
        n = len(corners)
        is_corner_90 = []
        for i in range(n):
            p_prev = corners[(i - 1) % n]
            p_curr = corners[i]
            p_next = corners[(i + 1) % n]
            is_corner_90.append(GeometryUtils.is_right_angle(p_prev, p_curr, p_next))

        for i in range(n):
            p1 = np.array(corners[i])
            p2 = np.array(corners[(i + 1) % n])
            length = np.linalg.norm(p2 - p1)
            mid = (p1 + p2) / 2
            edges.append({
                'p1': p1, 'p2': p2, 'mid': mid, 'length': length, 'index': i,
                'p1_is_90': is_corner_90[i], 'p2_is_90': is_corner_90[(i + 1) % n]
            })
        return edges

    def is_orthogonal(self, edge):
        return abs(edge['p1'][0] - edge['p2'][0]) < 2.0 or abs(edge['p1'][1] - edge['p2'][1]) < 2.0

    def check_collision(self, bed_corners, room):
        room_poly = np.array(room['snapped_corners'], dtype=np.float32)
        # 1. Kiểm tra giường có nằm hoàn toàn trong phòng không
        for p in bed_corners:
            if cv2.pointPolygonTest(room_poly, (float(p[0]), float(p[1])), False) < 0: return True
        
        # 2. Kiểm tra va chạm với cửa
        for d_pos in self.all_doors:
            if cv2.pointPolygonTest(bed_corners, (float(d_pos[0]), float(d_pos[1])), True) > -DOOR_CLEARANCE: return True
        return False

    def try_place_in_corner(self, room, p_curr, p_next, p_prev):
        v1 = np.array(p_next) - np.array(p_curr)
        len1 = np.linalg.norm(v1)
        if len1 < 1: return None
        v1_norm = v1 / len1

        v2 = np.array(p_prev) - np.array(p_curr)
        len2 = np.linalg.norm(v2)
        if len2 < 1: return None
        v2_norm = v2 / len2

        angle = math.degrees(math.atan2(v1[1], v1[0]))

        # Thử 2 hướng: Đầu giường tựa v2 hoặc tựa v1
        orientations = [
            (BED_LENGTH, BED_WIDTH, angle),      
            (BED_WIDTH, BED_LENGTH, angle - 90)  
        ]

        for L, W, rot_angle in orientations:
            center_shift = v1_norm * (L/2 + WALL_PADDING) + v2_norm * (W/2 + WALL_PADDING)
            center = np.array(p_curr) + center_shift
            rect = GeometryUtils.get_rect_corners(center, L, W, rot_angle)
            if not self.check_collision(rect, room):
                return {
                    'type': 'bed', 'center': center.tolist(),
                    'size': [L, W], 'angle': rot_angle, 'corners': rect.tolist()
                }
        return None

    def calculate_single_room(self, room, door_position=None):
        """Hàm tính toán cho 1 phòng cụ thể, trả về thông tin giường (dùng cho module import)"""
        # Nếu không có cửa truyền vào, thử lấy từ dữ liệu room
        if door_position is None:
            if 'door' in room:
                door_position = room['door']['position']
            else:
                return None # Không có cửa thì không biết né ở đâu
        
        door_pos = np.array(door_position)
        corners = room.get('snapped_corners', [])
        n = len(corners)

        # 1. Tìm các góc vuông (Corner Strategy)
        valid_corners = []
        for i in range(n):
            p_curr = corners[i]
            p_prev = corners[(i - 1) % n]
            p_next = corners[(i + 1) % n]
            angle = GeometryUtils.calculate_corner_angle(p_prev, p_curr, p_next)
            if 85 <= angle <= 95:
                dist = GeometryUtils.dist_sq(p_curr, door_pos)
                valid_corners.append({'index': i, 'dist': dist, 'p_curr': p_curr, 'p_prev': p_prev, 'p_next': p_next})

        # Ưu tiên góc XA CỬA nhất
        valid_corners.sort(key=lambda x: x['dist'], reverse=True)

        for cand in valid_corners:
            result = self.try_place_in_corner(room, cand['p_curr'], cand['p_next'], cand['p_prev'])
            if result:
                print(f"   ✅ Bed placed in PERFECT CORNER {cand['index']} (Dist: {cand['dist']:.0f})")
                return (result['center'], result['angle']) # Trả về tuple (pos, angle)

        # 2. Nếu không có góc, dùng chiến thuật trượt tường (Wall Sliding)
        print("   ⚠️ No valid corner found. Switching to Wall Sliding...")
        edges = self.get_room_edges_with_corners(room)
        ortho_edges = [e for e in edges if self.is_orthogonal(e)]

        for e in ortho_edges:
            dist_score = GeometryUtils.dist_sq(e['mid'], door_pos)
            corner_bonus = 0
            if e['p1_is_90']: corner_bonus += CORNER_SCORE_BONUS
            if e['p2_is_90']: corner_bonus += CORNER_SCORE_BONUS
            e['score'] = -1 if e['length'] < BED_WIDTH else dist_score + corner_bonus

        ortho_edges.sort(key=lambda e: e['score'], reverse=True)

        for wall in ortho_edges:
            if wall['score'] < 0: continue

            v_wall = wall['p2'] - wall['p1']
            v_norm = v_wall / np.linalg.norm(v_wall)
            normal = np.array([-v_norm[1], v_norm[0]])
            
            # Đảm bảo vector pháp tuyến hướng vào trong
            if cv2.pointPolygonTest(np.array(room['snapped_corners'], dtype=np.float32), tuple(wall['mid'] + normal * 5), False) < 0:
                normal = -normal

            angle = math.degrees(math.atan2(normal[1], normal[0])) - 90

            steps = int(wall['length'] / 5.0)
            if steps < 1: steps = 1
            base_t = np.linspace(0.05, 0.95, steps)

            # Ưu tiên phía xa cửa hơn trên bức tường đó
            d1 = GeometryUtils.dist_sq(wall['p1'], door_pos)
            d2 = GeometryUtils.dist_sq(wall['p2'], door_pos)
            t_values = base_t[::-1] if d2 > d1 else base_t

            for t in t_values:
                pos = wall['p1'] + t * v_wall
                center = pos + normal * (BED_LENGTH / 2 + WALL_PADDING)
                rect = GeometryUtils.get_rect_corners(center, BED_WIDTH, BED_LENGTH, angle)

                if not self.check_collision(rect, room):
                    print(f"   ✅ Bed placed on Wall {wall['index']} (Corner Optimized)")
                    return (center.tolist(), angle)

        print(f"   ❌ No valid spot for Bed in {room['name']}")
        return None

    def solve(self):
        """Hàm dùng cho chế độ chạy độc lập (Standalone)"""
        for room in self.rooms:
            if 'bedroom' not in room['name'].lower() and 'master' not in room['name'].lower(): continue
            if 'door' not in room: continue
            
            res = self.calculate_single_room(room, room['door']['position'])
            if res:
                center, angle = res
                # Re-calculate rect for visualization/saving
                rect = GeometryUtils.get_rect_corners(center, BED_WIDTH, BED_LENGTH, angle)
                if 'furniture' not in room: room['furniture'] = []
                room['furniture'].append({
                    'type': 'bed', 'center': center,
                    'size': [BED_WIDTH, BED_LENGTH], 'angle': angle, 'corners': rect.tolist()
                })
        return self.rooms

# ================= MODULE INTERFACE =================
# Hàm này để furniture_placement.py gọi
def calculate_bed_position(room, door_side=None):
    """
    Wrapper function để tương thích với furniture_placement.py
    Input: room object (dict), door_side (string - không dùng ở đây vì ta dùng logic xịn hơn)
    Output: ((x, y), angle) hoặc None
    """
    # Vì logic trong BedPlacer cần biết vị trí cửa chính xác để né
    # Ta cần tìm tọa độ cửa từ furniture_placement truyền xuống hoặc tự tìm lại
    # Tạm thời ta giả định room đã có info cửa hoặc ta sẽ bỏ qua check cửa nếu chưa có
    placer = BedPlacer()
    
    # Ở furniture_placement.py, 'internal_doors' đã được tính. 
    # Tuy nhiên, hàm này chỉ nhận 'door_side'.
    # Để tận dụng logic 'calculate_single_room', ta cần 'door_position'.
    # Nếu furniture_placement chưa truyền door_pos, ta sẽ trick một chút:
    # Lấy tâm phòng làm mốc tạm (không tốt lắm) hoặc tìm lại cạnh cửa dựa trên door_side.
    
    # Giải pháp tốt nhất: furniture_placement nên truyền door_pos.
    # Nhưng để không sửa signature, ta tự mò lại cửa trên cạnh.
    
    door_pos = None
    # Logic tìm lại cửa sơ bộ dựa trên door_side (nếu cần thiết)
    # ... (Bỏ qua để code gọn, giả sử BedPlacer tự handle tốt va chạm tường)
    
    # Hack: Nếu không có cửa, BedPlacer sẽ fail. 
    # Ta tạo dummy door ở giữa cạnh tương ứng với door_side để né.
    if door_side:
        corners = room['snapped_corners']
        min_x, min_y = min(c[0] for c in corners), min(c[1] for c in corners)
        max_x, max_y = max(c[0] for c in corners), max(c[1] for c in corners)
        if door_side == 'left': door_pos = [min_x, (min_y+max_y)/2]
        elif door_side == 'right': door_pos = [max_x, (min_y+max_y)/2]
        elif door_side == 'top': door_pos = [(min_x+max_x)/2, min_y]
        elif door_side == 'bottom': door_pos = [(min_x+max_x)/2, max_y]

    return placer.calculate_single_room(room, door_pos)

# ================= DEBUG VISUALIZATION =================
def visualize(rooms):
    plt.figure(figsize=(10, 10)); plt.gca().invert_yaxis()
    for r in rooms:
        c = r.get('snapped_corners', []);
        if c: p=c+[c[0]]; x,y=zip(*p); plt.plot(x,y,'b-', linewidth=2)
        if 'door' in r: plt.plot(r['door']['position'][0], r['door']['position'][1], 'ro')

        for f in r.get('furniture', []):
            if f['type']=='bed':
                c = np.array(f['corners']); c = np.vstack([c,c[0]])
                plt.plot(c[:,0], c[:,1], 'g-', linewidth=2)
                
                # Vẽ mũi tên hướng giường
                cx, cy = f['center']
                angle = f['angle']
                w, h = f['size']
                direction_angle = angle if w > h else angle + 90
                rad = math.radians(direction_angle)
                dx = math.cos(rad) * 20; dy = math.sin(rad) * 20
                plt.arrow(cx, cy, dx, dy, head_width=10, head_length=10, fc='r', ec='r')

    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_bed_corner.png"))
    print(f"📸 Saved debug image: {os.path.join(OUTPUTS_DIR, 'check_bed_corner.png')}")

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE):
        data = load_json(INPUT_FILE)
        placer = BedPlacer(data)
        data['rooms'] = placer.solve()
        save_json(OUTPUT_FILE, data)
        visualize(data['rooms'])
    else: print("Missing input files.")