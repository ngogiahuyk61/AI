import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_final_complete.json")
INPUT_BOUNDARY = os.path.join(OUTPUTS_DIR, "boundary_aligned.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_windows.json")

WINDOW_LENGTH = 60.0 # Tăng lên 60px để dễ nhìn hơn
WINDOW_THICKNESS = 5.0
BOUNDARY_TOLERANCE = 15.0

# --- CẤU HÌNH MỚI ---
MAX_WINDOWS_PER_ROOM = 1       # Tối đa 1 cửa sổ/phòng
DOUBLE_WINDOW_THRESHOLD = 180.0 # Tường > 180px mới được đặt 2 cửa (logic cũ, giờ dùng max 1)
ENTRANCE_SAFETY_MARGIN = 60.0   # Khoảng cách tối thiểu tới cửa chính

EXCLUDED_ROOM_KEYWORDS = {
    "bathroom", "bath", "toilet", "wash", "restroom", "wc", "lavatory",
    "storage", "storeroom", "closet", "pantry"
}

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

class WindowPlacer:
    def __init__(self, room_data, boundary_data=None):
        self.rooms = room_data.get('rooms', [])
        # Nếu không có boundary data, tạo boundary segments từ exterior_facing (nếu có) hoặc rỗng
        if boundary_data:
            self.boundary_points = boundary_data.get('points', [])
            self.boundary_segments = []
            n = len(self.boundary_points)
            for i in range(n):
                p1 = self.boundary_points[i]
                p2 = self.boundary_points[(i + 1) % n]
                self.boundary_segments.append({'p1': [p1['x'], p1['y']], 'p2': [p2['x'], p2['y']]})
        else:
            self.boundary_segments = []

    def get_room_edges(self, room):
        corners = room.get('snapped_corners', [])
        edges = []
        n = len(corners)
        for i in range(n):
            p1 = np.array(corners[i]); p2 = np.array(corners[(i+1)%n])
            length = np.linalg.norm(p2 - p1)
            mid = (p1 + p2) / 2
            edges.append({'p1': p1, 'p2': p2, 'mid': mid, 'length': length})
        return edges

    def is_exterior(self, edge, room):
        # Cách 1: Check với boundary segments (chính xác nhất)
        if self.boundary_segments:
            mid = edge['mid']
            for b in self.boundary_segments:
                dist = GeometryUtils.point_line_segment_distance(mid[0], mid[1], b['p1'][0], b['p1'][1], b['p2'][0], b['p2'][1])
                if dist < BOUNDARY_TOLERANCE: return True
            return False
        
        # Cách 2: Check với thuộc tính 'exterior_facing' của phòng (nếu có)
        # Đây là fallback nếu không có boundary data
        ext_facing = room.get('exterior_facing', [])
        if not ext_facing: return False
        
        mid = edge['mid']
        corners = room.get('snapped_corners', [])
        min_x = min(c[0] for c in corners); max_x = max(c[0] for c in corners)
        min_y = min(c[1] for c in corners); max_y = max(c[1] for c in corners)
        
        tol = 5.0
        if 'top' in ext_facing and abs(mid[1] - min_y) < tol: return True
        if 'bottom' in ext_facing and abs(mid[1] - max_y) < tol: return True
        if 'left' in ext_facing and abs(mid[0] - min_x) < tol: return True
        if 'right' in ext_facing and abs(mid[0] - max_x) < tol: return True
        
        return False

    def check_conflict(self, window_center, window_rect, room):
        """
        Kiểm tra va chạm với Cửa đi (Door) và Cửa chính (Entrance).
        """
        # 1. Check Room Internal Door
        if 'door' in room:
            d_pos = room['door']['position']
            # Khoảng cách tâm > (Window_W/2 + Door_W/2 + Padding) ~ 60px
            if GeometryUtils.dist_sq(window_center, d_pos) < 60.0**2:
                return True

        # 2. Check Main Entrance (Living Room)
        if 'entrance' in room:
            e_pos = room['entrance']['position']
            if GeometryUtils.dist_sq(window_center, e_pos) < ENTRANCE_SAFETY_MARGIN**2:
                return True

        return False

    def solve(self):
        print("🪟 Placing Windows (Max 1/room, excluding bathroom/storage)...")

        for room in self.rooms:
            # Skip LDK vì thường có cửa ban công thay vì cửa sổ, hoặc xử lý riêng
            if 'living' in room['name'].lower(): continue
            
            raw_names = [room.get('name', ''), room.get('original_name', '')]
            normalized = ' '.join(filter(None, raw_names)).lower()
            
            if any(keyword in normalized for keyword in EXCLUDED_ROOM_KEYWORDS):
                continue

            # Lọc cạnh ngoài
            edges = self.get_room_edges(room)
            exterior_edges = [e for e in edges if self.is_exterior(e, room)]

            # Sắp xếp cạnh dài nhất xử lý trước
            exterior_edges.sort(key=lambda e: e['length'], reverse=True)

            windows_count = 0

            for edge in exterior_edges:
                if windows_count >= MAX_WINDOWS_PER_ROOM: break
                if edge['length'] < WINDOW_LENGTH + 20: continue # Đủ rộng

                v_wall = edge['p2'] - edge['p1']
                angle = math.degrees(math.atan2(v_wall[1], v_wall[0]))

                # Đặt 1 cửa sổ ở giữa cạnh
                t = 0.5
                pos = edge['p1'] + t * v_wall
                rect = GeometryUtils.get_rect_corners(pos, WINDOW_LENGTH, WINDOW_THICKNESS, angle)

                if not self.check_conflict(pos, rect, room):
                    if 'furniture' not in room: room['furniture'] = []
                    room['furniture'].append({
                        'type': 'window',
                        'center': pos.tolist(),
                        'size': [WINDOW_LENGTH, WINDOW_THICKNESS],
                        'angle': angle,
                        'corners': rect.tolist()
                    })
                    windows_count += 1
                    print(f"   ✅ Window placed in {room['name']}")

        return self.rooms

# ================= MODULE INTERFACE =================
def find_window_locations(rooms, boundary_points=None):
    """
    Wrapper function cho furniture_placement.py
    Output: List các dict window info [{'center':..., 'angle':..., 'type':...}]
    """
    # Tạo dummy data structure
    room_data = {'rooms': rooms}
    boundary_data = {'points': boundary_points} if boundary_points else None
    
    placer = WindowPlacer(room_data, boundary_data)
    placer.solve() # Sẽ update trực tiếp vào room['furniture']
    
    # Trích xuất thông tin để trả về cho renderer vẽ
    all_windows = []
    for r in rooms:
        for f in r.get('furniture', []):
            if f['type'] == 'window':
                # Determine orientation for icon rotation based on angle
                angle = f['angle'] % 360
                is_horizontal = (abs(angle) < 45 or abs(angle - 180) < 45 or abs(angle - 360) < 45)
                w_type = 'horizontal' if is_horizontal else 'vertical'
                
                all_windows.append({
                    'center': f['center'],
                    'angle': f['angle'],
                    'type': w_type
                })
    return all_windows

# ================= DEBUG VISUALIZATION =================
def visualize_final(rooms, boundary_points):
    plt.figure(figsize=(10, 10)); ax = plt.gca(); ax.invert_yaxis()

    if boundary_points:
        bx = [p['x'] for p in boundary_points]; by = [p['y'] for p in boundary_points]
        bx.append(bx[0]); by.append(by[0])
        plt.plot(bx, by, 'k-', linewidth=3)

    for r in rooms:
        c = r.get('snapped_corners', []);
        if c: p=c+[c[0]]; x,y=zip(*p); plt.plot(x,y,'b-', alpha=0.3)

        for f in r.get('furniture', []):
            c=np.array(f['corners']); c=np.vstack([c,c[0]])
            col = 'k'
            lw = 1
            if f['type'] == 'window':
                col = 'c'; lw = 3 
            elif f['type'] == 'bed': col = 'g'
            plt.plot(c[:,0],c[:,1], color=col, linewidth=lw)

        if 'door' in r: plt.plot(r['door']['position'][0], r['door']['position'][1], 'ro')
        if 'entrance' in r: plt.plot(r['entrance']['position'][0], r['entrance']['position'][1], 'go', markersize=8)

    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_windows_v2.png"))
    print(f"📸 Saved visualization: {os.path.join(OUTPUTS_DIR, 'check_windows_v2.png')}")

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE) and os.path.exists(INPUT_BOUNDARY):
        r_data = load_json(INPUT_FILE)
        b_data = load_json(INPUT_BOUNDARY)

        placer = WindowPlacer(r_data, b_data)
        r_data['rooms'] = placer.solve()

        save_json(OUTPUT_FILE, r_data)
        visualize_final(r_data['rooms'], b_data['points'])
    else:
        print("Missing input files.")