import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH (CONFIG) =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_final.json") 
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_complete.json")

TOILET_WIDTH = 28.0
TOILET_LENGTH = 48.0 
WALL_PADDING = 2.0      
DOOR_CLEARANCE = 15.0   

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

class GeometryUtils:
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
    def point_in_poly(pt, corners):
        return cv2.pointPolygonTest(np.array(corners, dtype=np.float32), pt, False) >= 0

    @staticmethod
    def check_collision(rect1, rect2):
        r1 = cv2.boundingRect(np.array(rect1, dtype=np.float32))
        r2 = cv2.boundingRect(np.array(rect2, dtype=np.float32))
        x_overlap = max(0, min(r1[0]+r1[2], r2[0]+r2[2]) - max(r1[0], r2[0]))
        y_overlap = max(0, min(r1[1]+r1[3], r2[1]+r2[3]) - max(r1[1], r2[1]))
        if x_overlap * y_overlap > 0: return True
        return False

class ToiletPlacer:
    def __init__(self, room_data):
        self.rooms = room_data.get('rooms', [])

    def get_room_edges(self, room):
        corners = room.get('snapped_corners', [])
        edges = []
        n = len(corners)
        for i in range(n):
            p1 = np.array(corners[i]); p2 = np.array(corners[(i + 1) % n])
            length = np.linalg.norm(p2 - p1)
            mid = (p1 + p2) / 2
            edges.append({'p1': p1, 'p2': p2, 'mid': mid, 'length': length, 'index': i})
        return edges

    def is_orthogonal(self, edge):
        p1, p2 = edge['p1'], edge['p2']
        return abs(p1[0] - p2[0]) < 2.0 or abs(p1[1] - p2[1]) < 2.0

    def check_furniture_collision(self, new_item_rect, existing_items):
        for item in existing_items:
            existing_corners = item.get('corners', [])
            if not existing_corners: continue
            if GeometryUtils.check_collision(new_item_rect, existing_corners):
                return True
        return False

    def place_toilet_small_room(self, room):
        """Đặt toilet cho phòng vệ sinh nhỏ (chỉ có toilet)"""
        if 'door' not in room: return None

        door_pos = np.array(room['door']['position'])
        corners = room['snapped_corners']
        edges = self.get_room_edges(room)
        avg_len = sum([e['length'] for e in edges]) / len(edges) if edges else 0

        candidates = []
        for edge in edges:
            if edge['length'] < TOILET_WIDTH: continue
            if not self.is_orthogonal(edge): continue

            v_wall = edge['p2'] - edge['p1']
            v_norm = v_wall / np.linalg.norm(v_wall)
            normal = np.array([-v_norm[1], v_norm[0]]) 
            if not GeometryUtils.point_in_poly(edge['mid'] + normal * 5, corners): normal = -normal

            v_to_door = door_pos - edge['mid']
            dist_to_door = np.linalg.norm(v_to_door)
            v_to_door_n = v_to_door / dist_to_door if dist_to_door > 0 else np.array([0,0])

            score_face = np.dot(normal, v_to_door_n)
            score_shape = 1.0 if edge['length'] < avg_len * 1.5 else 0.0 
            score_dist = dist_to_door

            if score_face < -0.3: continue 

            final_score = (score_face * 200) + (score_shape * 100) + score_dist
            candidates.append({'edge': edge, 'normal': normal, 'score': final_score})

        candidates.sort(key=lambda x: x['score'], reverse=True)

        for cand in candidates:
            edge = cand['edge']; normal = cand['normal']
            angle_deg = math.degrees(math.atan2(normal[1], normal[0])) - 90
            v_wall = edge['p2'] - edge['p1']
            
            t_values = [0.5, 0.2, 0.8, 0.35, 0.65, 0.1, 0.9]

            for t in t_values:
                pos_on_wall = edge['p1'] + t * v_wall
                center = pos_on_wall + normal * (TOILET_LENGTH/2 + WALL_PADDING)
                rect = GeometryUtils.get_rect_corners(center, TOILET_WIDTH, TOILET_LENGTH, angle_deg)

                valid = True
                for p in rect:
                    if not GeometryUtils.point_in_poly(p, corners): valid = False; break
                
                d_dist = cv2.pointPolygonTest(rect, (float(door_pos[0]), float(door_pos[1])), True)
                if d_dist > -DOOR_CLEARANCE: valid = False

                if valid and self.check_furniture_collision(rect, room.get('furniture', [])):
                    valid = False
                
                if valid:
                    # Return kết quả thay vì append trực tiếp
                    return {
                        'type': 'toilet', 'center': center.tolist(),
                        'size': [TOILET_WIDTH, TOILET_LENGTH], 'angle': angle_deg,
                        'corners': rect.tolist()
                    }
        return None

    def solve(self):
        """Hàm chạy độc lập"""
        for room in self.rooms:
            name_lower = room['name'].lower()
            if 'bathroom' in name_lower or 'toilet' in name_lower:
                res = self.place_toilet_small_room(room)
                if res:
                    if 'furniture' not in room: room['furniture'] = []
                    room['furniture'].append(res)
        return self.rooms

# ================= MODULE INTERFACE =================
def find_bathroom_connections(bathrooms):
    """
    Tìm vách ngăn cho phòng tắm lớn (Master Bath).
    Chia phòng thành 2 vùng: Wash (60%) và Bath (40%).
    """
    connections = []
    if not bathrooms: return connections
    
    # Sắp xếp theo diện tích giảm dần -> Lấy phòng lớn nhất làm Master Bath
    bathrooms.sort(key=lambda r: r.get('area', 0), reverse=True)
    largest_bathroom = bathrooms[0]
    
    # Logic chia vùng (giống furniture_placement cũ)
    # Lấy bounding box
    corners = largest_bathroom.get('snapped_corners', [])
    if not corners: return connections
    
    min_x = min(c[0] for c in corners); max_x = max(c[0] for c in corners)
    min_y = min(c[1] for c in corners); max_y = max(c[1] for c in corners)
    
    w = max_x - min_x
    h = max_y - min_y
    
    # Xác định hướng chia: Cắt ngang cạnh dài hơn
    partition_wall = {}
    
    # Giả định tường ngoài (exterior) là bên phải hoặc dưới
    # Logic cũ ưu tiên exterior_wall_side, ở đây ta đơn giản hóa:
    # Nếu W > H -> Chia dọc. Zone Bath (40%) ở xa cửa (thường là sâu bên trong)
    # Nếu H > W -> Chia ngang.
    
    if w > h: # Phòng ngang
        # Chia dọc tại x = 60% (Wash trái, Bath phải) hoặc ngược lại
        split_x = min_x + w * 0.6
        zone_wash = [min_x, min_y, w*0.6, h] # x, y, w, h
        zone_bath = [split_x, min_y, w*0.4, h]
        
        partition_wall = {
            'type': 'vertical',
            'start_point': [split_x, min_y],
            'end_point': [split_x, max_y],
            'zone_60_bbox': zone_wash,
            'zone_40_bbox': zone_bath,
            'exterior_wall_side': 'right' # Giả định
        }
    else: # Phòng dọc
        # Chia ngang tại y = 60%
        split_y = min_y + h * 0.6
        zone_wash = [min_x, min_y, w, h*0.6]
        zone_bath = [min_x, split_y, w, h*0.4]
        
        partition_wall = {
            'type': 'horizontal',
            'start_point': [min_x, split_y],
            'end_point': [max_x, split_y],
            'zone_60_bbox': zone_wash,
            'zone_40_bbox': zone_bath,
            'exterior_wall_side': 'bottom' # Giả định
        }
        
    connections.append({
        'bathroom_name': largest_bathroom['name'],
        'partition_walls': [partition_wall]
    })
    
    return connections

def calculate_toilet_position(room, door_side=None, icons=None):
    """
    Wrapper function trả về vị trí các thiết bị vệ sinh.
    - Master Bath: Trả về Bath + Wash (đã chia vùng).
    - Toilet nhỏ: Trả về Toilet.
    """
    placer = ToiletPlacer({'rooms': [room]})
    
    # Check nếu là Master Bath (đã có partition logic xử lý ở find_bathroom_connections)
    # Nhưng hàm này được gọi khi render từng phòng.
    # Nếu là phòng nhỏ -> Dùng logic place_toilet_small_room
    # Nếu là phòng lớn -> Dùng logic chia vùng (cần dữ liệu partition từ trước hoặc tính lại)
    
    # Ở đây ta đơn giản hóa: 
    # Nếu diện tích nhỏ (< 4m2 ~ pixel?) hoặc tên là Toilet -> Small Room Logic
    # Nếu diện tích lớn -> Master Logic
    
    is_master = 'master' in room['name'].lower() or room.get('area', 0) > 4.0 # Giả định
    
    results = {}
    
    if not is_master:
        # Phòng nhỏ: Chỉ đặt Toilet
        res = placer.place_toilet_small_room(room)
        if res:
            results['toilet'] = (res['center'], res['angle'])
    else:
        # Phòng lớn: Tính lại vùng chia (hoặc lấy từ cache nếu có)
        # Giả sử ta tính lại nhanh ở đây
        conns = find_bathroom_connections([room])
        if conns:
            wall = conns[0]['partition_walls'][0]
            # Bath Zone (40%)
            z40 = wall['zone_40_bbox'] # x,y,w,h
            bath_center = (z40[0] + z40[2]/2, z40[1] + z40[3]/2)
            bath_angle = 90 if z40[3] > z40[2] else 0
            results['bath'] = (bath_center, bath_angle)
            
            # Wash Zone (60%)
            z60 = wall['zone_60_bbox']
            wash_center = (z60[0] + z60[2]/2, z60[1] + z60[3]/2) # Cần logic bám tường cho wash
            # Wash thường bám tường đối diện cửa hoặc tường bên
            results['wash'] = (wash_center, 0)

    return results

# ================= DEBUG VISUALIZATION =================
def visualize_final(rooms):
    plt.figure(figsize=(10, 10)); ax = plt.gca(); ax.invert_yaxis()
    for room in rooms:
        corners = room.get('snapped_corners', [])
        if not corners: continue
        poly = corners + [corners[0]]; xs, ys = zip(*poly)
        plt.plot(xs, ys, 'k-', linewidth=1)

        for item in room.get('furniture', []):
            c = np.array(item['corners']); c = np.vstack([c, c[0]])
            color = 'r' if item['type'] == 'toilet' else 'm'
            plt.plot(c[:,0], c[:,1], color=color, linewidth=2)
            
            if item['type'] == 'toilet':
                cx, cy = item['center']; angle = item['angle']
                rad = math.radians(angle)
                dir_x = -math.sin(rad); dir_y = math.cos(rad)
                plt.arrow(cx - dir_x*10, cy - dir_y*10, dir_x*20, dir_y*20, head_width=5, fc='orange', ec='orange')

        if 'door' in room:
            d = room['door']
            plt.plot(d['position'][0], d['position'][1], 'yo', markersize=5)
            
    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_toilet_placement_final.png"))

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE):
        data = load_json(INPUT_FILE)
        placer = ToiletPlacer(data)
        data['rooms'] = placer.solve()
        save_json(OUTPUT_FILE, data)
        visualize_final(data['rooms'])