import json
import math
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os

# ================= CẤU HÌNH =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
INPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_doors_v3.json") # File đầu vào giả định
INPUT_BOUNDARY = os.path.join(OUTPUTS_DIR, "boundary_aligned.json")
INPUT_EXTERIOR = os.path.join(OUTPUTS_DIR, "exterior_wall.json")
OUTPUT_FILE = os.path.join(OUTPUTS_DIR, "room_data_with_entrance.json")

ENTRANCE_WIDTH = 40.0 # Kích thước icon entrance (pixel)
PROXIMITY_THRESH = 15.0 # Khoảng cách tối đa để coi là "gần tường"

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

class EntrancePlacer:
    def __init__(self, living_room, exterior_edges, other_room_contours):
        self.living_room = living_room
        self.exterior_edges = exterior_edges
        self.other_room_contours = other_room_contours
        
        # Tạo contour cho LDK để check va chạm
        if self.living_room and self.living_room.get('snapped_corners'):
            self.ldk_contour = np.array(self.living_room['snapped_corners']).reshape((-1, 1, 2)).astype(int)
        else:
            self.ldk_contour = None

    def get_valid_entrance_segment(self, ext_edge):
        """
        Quét một cạnh tường ngoài, trả về "đoạn thuần túy" chỉ hướng vào LDK.
        (Logic Pure Segment V10)
        """
        if self.ldk_contour is None: return None
        
        p1 = np.array([ext_edge[0], ext_edge[1]])
        p2 = np.array([ext_edge[2], ext_edge[3]])
        edge_length = np.linalg.norm(p1 - p2)
        
        if edge_length < ENTRANCE_WIDTH: return None
        
        num_steps = int(edge_length / 5) 
        if num_steps < 8: num_steps = 8 
        
        valid_points = []
        for i in range(num_steps + 1):
            t = i / num_steps
            p = p1 * (1 - t) + p2 * t
            p_tuple = (float(p[0]), float(p[1]))
            
            # Check 1: Điểm này phải gần LDK
            dist_ldk = cv2.pointPolygonTest(self.ldk_contour, p_tuple, True)
            if abs(dist_ldk) < PROXIMITY_THRESH:
                # Check 2: Điểm này KHÔNG được gần các phòng khác (Balcony, Bedroom...)
                is_colliding = False
                for name, contour in self.other_room_contours.items():
                    # Đảm bảo contour đúng định dạng
                    if len(contour.shape) == 2: contour = contour.reshape((-1, 1, 2))
                    
                    dist_other = cv2.pointPolygonTest(contour, p_tuple, True)
                    if abs(dist_other) < PROXIMITY_THRESH:
                        is_colliding = True 
                        break
                
                if not is_colliding:
                    valid_points.append(p)
                    
        if len(valid_points) < 8: return None # Quá ngắn
        
        segment_start = valid_points[0]
        segment_end = valid_points[-1]
        segment_len = np.linalg.norm(segment_start - segment_end)
        
        if segment_len >= ENTRANCE_WIDTH:
            return (segment_start, segment_end)
        return None

    def solve(self):
        """Tìm vị trí tốt nhất cho Entrance."""
        print("\n🚪 [EntrancePlacer] Analyzing exterior walls...")
        if not self.living_room or not self.exterior_edges:
            print("   ❌ Missing Living Room or Exterior Edges data.")
            return None

        # Tìm max Y của toàn nhà để xác định cạnh "bottom" (thường là hướng cửa chính)
        # (Để làm tốt cần bounds của toàn bộ các phòng, ở đây dùng tạm bounds của LDK và exterior)
        # Tuy nhiên logic Pure Segment quan trọng hơn hướng.
        
        valid_segments = []
        
        for ext_edge in self.exterior_edges:
            if not ext_edge or len(ext_edge) != 4: continue
            
            segment_coords = self.get_valid_entrance_segment(ext_edge)
            
            if segment_coords:
                p1, p2 = segment_coords
                length = np.linalg.norm(p1 - p2)
                center = ( (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 )
                
                # Xác định hướng (orientation) để xoay icon
                x1, y1, x2, y2 = ext_edge
                is_horizontal = abs(y1 - y2) < 5
                
                lc_x, lc_y = self.living_room['center']
                
                if is_horizontal:
                    orientation = 'top' if y1 < lc_y else 'bottom'
                else:
                    orientation = 'left' if x1 < lc_x else 'right'
                
                # Ưu tiên cạnh Bottom > Right > Left > Top (Logic chung cư)
                priority_score = length
                if orientation == 'bottom': priority_score += 1000
                elif orientation == 'right': priority_score += 500
                
                valid_segments.append({
                    'original_edge': ext_edge,
                    'center': center,
                    'length': length,
                    'orientation': orientation,
                    'score': priority_score
                })

        if not valid_segments:
            print("   ❌ No valid pure segment found for Entrance.")
            return None

        # Chọn đoạn có điểm cao nhất (ưu tiên Bottom + Dài nhất)
        best_segment = max(valid_segments, key=lambda x: x['score'])
        
        print(f"   ✅ Found Entrance at {best_segment['center']} (Orientation: {best_segment['orientation']})")
        
        return {
            'position': best_segment['center'], # Dạng tuple (x, y) hoặc np array
            'center': best_segment['center'],   # Alias
            'orientation': best_segment['orientation'],
            'on_edge': best_segment['original_edge'],
            'width': ENTRANCE_WIDTH
        }

# ================= MODULE INTERFACE =================
def find_entrance_location(living_room, exterior_edges, other_room_contours):
    """
    Wrapper function cho furniture_placement.py
    Input:
      - living_room: dict room object
      - exterior_edges: list of [x1, y1, x2, y2]
      - other_room_contours: dict {room_name: contour_array}
    Output:
      - dict {'center': (x, y), 'orientation': 'bottom'...} hoặc None
    """
    placer = EntrancePlacer(living_room, exterior_edges, other_room_contours)
    return placer.solve()

# ================= DEBUG & STANDALONE =================
def visualize(rooms, entrance_data, boundary_points=None):
    plt.figure(figsize=(10, 10)); ax = plt.gca(); ax.invert_yaxis()

    # Draw Boundary
    if boundary_points:
        bx = [p['x'] for p in boundary_points]; by = [p['y'] for p in boundary_points]
        bx.append(bx[0]); by.append(by[0])
        plt.plot(bx, by, 'k-', linewidth=3, alpha=0.5)

    # Draw Rooms
    for r in rooms:
        c = r.get('snapped_corners', []);
        if c:
            p = c+[c[0]]; x,y = zip(*p); plt.plot(x,y, 'b-', alpha=0.3)
            # Label
            cx, cy = np.mean(c, axis=0)
            plt.text(cx, cy, r['name'], fontsize=8, ha='center', color='blue')

    # Draw Entrance
    if entrance_data:
        x, y = entrance_data['center']
        ori = entrance_data['orientation']
        
        plt.plot(x, y, 'go', markersize=10, markeredgecolor='k', label='Entrance')
        
        # Vector
        angle_map = {'right': 0, 'bottom': 90, 'left': 180, 'top': 270} # Matplotlib angle (ngược Y)
        # Thực tế Matplotlib plot y downward nên:
        # Bottom (y lớn) -> vector hướng lên (y nhỏ) để chỉ vào nhà? 
        # Không, Entrance icon thường hướng MŨI NHỌN vào trong nhà.
        # Ở đây vẽ vector minh họa hướng VÀO TRONG.
        
        dx, dy = 0, 0
        if ori == 'bottom': dy = -30 # Hướng lên
        elif ori == 'top': dy = 30   # Hướng xuống
        elif ori == 'left': dx = 30  # Hướng phải
        elif ori == 'right': dx = -30 # Hướng trái
            
        plt.arrow(x, y, dx, dy, head_width=10, color='green', zorder=20, linewidth=2)
        plt.text(x, y-10, f"ENTRANCE\n({ori})", color='green', fontweight='bold', ha='center')

    plt.axis('equal'); plt.savefig(os.path.join(OUTPUTS_DIR, "check_entrance.png"))
    print(f"📸 Saved visualization: {os.path.join(OUTPUTS_DIR, 'check_entrance.png')}")

if __name__ == "__main__":
    # Load các file cần thiết để test độc lập
    if os.path.exists(INPUT_FILE) and os.path.exists(INPUT_EXTERIOR):
        r_data = load_json(INPUT_FILE)
        rooms = r_data.get('rooms', [])
        
        ext_data = load_json(INPUT_EXTERIOR)
        exterior_edges = ext_data.get('exterior_edges', [])
        
        boundary_data = load_json(INPUT_BOUNDARY)
        b_points = boundary_data.get('points', []) if boundary_data else []

        living_room = next((r for r in rooms if 'living' in r['name'].lower()), None)
        
        if living_room:
            # Tạo other_contours giả lập
            other_contours = {}
            for r in rooms:
                if r != living_room and r.get('snapped_corners'):
                    other_contours[r['name']] = np.array(r['snapped_corners']).reshape((-1, 1, 2)).astype(int)
            
            # Chạy logic
            result = find_entrance_location(living_room, exterior_edges, other_contours)
            
            # Visualize
            visualize(rooms, result, b_points)
            
            # (Optional) Lưu lại vào file json nếu cần test chuỗi
            if result:
                living_room['entrance'] = result
                save_json(OUTPUT_FILE, r_data)
        else:
            print("❌ No Living Room found in input.")
    else:
        print("❌ Missing input files (room_data or exterior_wall).")