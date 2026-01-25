import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
# Đường dẫn cơ sở
SCRIPT_DIR = Path(__file__).resolve().parent
DETECT_ROOT = SCRIPT_DIR.parent
DETECT_OUTPUTS_DIR = DETECT_ROOT / "outputs"
DRAW_MASK_INPUT_DIR = DETECT_ROOT.parent / "module_draw_mask" / "input"

# Input Files
FILE_BOUNDARY = DETECT_OUTPUTS_DIR / "boundary_aligned.json"
FILE_ROOMS = DETECT_OUTPUTS_DIR / "room_data_update.json"
FILE_SKETCH = DRAW_MASK_INPUT_DIR / "sketch_coordinates_full.json"

# Output Files (Ghi đè)
TARGET_BOUNDARY = FILE_BOUNDARY
TARGET_ROOMS = FILE_ROOMS

# Tham số xử lý
CLIP_MARGIN = 10.0  # Khoảng cách thu nhỏ biên để cắt mép (px)
SHOW_PLOT = False

# ==========================================
# HÀM HỖ TRỢ (UTILS)
# ==========================================
def load_json(path: Path):
    if not path.exists():
        print(f"⚠️ Không tìm thấy file: {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"✅ Đã GHI ĐÈ file: {path}")

def get_poly(room):
    corners = room.get('snapped_corners', [])
    if len(corners) < 3: return None
    return Polygon(corners).buffer(0)

# ==========================================
# PHẦN 1: CHỈNH SỬA HÌNH DÁNG (SHAPE CORRECTION)
# ==========================================
def calculate_fixed_shape(sketch_data, boundary_data):
    print("🔄 Đang tính toán chuẩn hóa hình dáng (Procrustes Analysis)...")
    
    pts_sketch = np.array([[p['x'], p['y']] for p in sketch_data['points']])
    pts_bound = np.array([[p['x'], p['y']] for p in boundary_data['points']])

    # 1. Tính Tâm (Centroid)
    center_sketch = np.mean(pts_sketch, axis=0)
    center_bound = np.mean(pts_bound, axis=0)

    # 2. Tính Tỷ lệ Scale (Uniform Scale - Giữ nguyên hình dáng)
    dist_sketch = np.linalg.norm(pts_sketch - center_sketch, axis=1)
    dist_bound = np.linalg.norm(pts_bound - center_bound, axis=1)
    
    # Tránh chia cho 0
    mean_dist_sketch = np.mean(dist_sketch)
    if mean_dist_sketch == 0: mean_dist_sketch = 1
        
    scale_factor = np.mean(dist_bound) / mean_dist_sketch
    print(f"   ⚖️ Tỷ lệ Scale đồng dạng: {scale_factor:.4f}")

    # 3. Biến đổi (Transform)
    # Công thức: New = (Old - CenterOld) * Scale + CenterNew
    fixed_pts = (pts_sketch - center_sketch) * scale_factor + center_bound

    # 4. Đóng kín vòng lặp (Close Loop)
    if np.linalg.norm(fixed_pts[0] - fixed_pts[-1]) > 1.0:
        fixed_pts = np.vstack([fixed_pts, fixed_pts[0]])

    # Chuyển về List Dict
    fixed_boundary_list = [{"x": round(float(p[0]), 2), "y": round(float(p[1]), 2)} for p in fixed_pts]
    
    return fixed_boundary_list

# ==========================================
# PHẦN 2: SIẾT BIÊN VÀ CẮT GỌT (TIGHTEN & CLIP)
# ==========================================
def tighten_and_clip_rooms(fixed_boundary_pts, room_data):
    print(f"✂️ Đang thực hiện cắt gọt phòng (Margin={CLIP_MARGIN}px)...")
    
    rooms_list = room_data['rooms']
    room_polys = [get_poly(r) for r in rooms_list if get_poly(r)]
    
    if not room_polys:
        print("❌ Lỗi: Không có dữ liệu phòng hợp lệ.")
        return None, None

    # 1. Tính BBox của toàn bộ các phòng
    all_rooms_union = unary_union(room_polys)
    minx_r, miny_r, maxx_r, maxy_r = all_rooms_union.bounds
    
    # Kích thước mục tiêu (Room Size - Margin)
    target_width = (maxx_r - minx_r) - (CLIP_MARGIN * 2)
    target_height = (maxy_r - miny_r) - (CLIP_MARGIN * 2)
    room_center = np.array([(minx_r + maxx_r)/2, (miny_r + maxy_r)/2])

    # 2. Xử lý Boundary (từ kết quả Phần 1)
    b_pts = [(p['x'], p['y']) for p in fixed_boundary_pts]
    boundary_poly = Polygon(b_pts)
    minx_b, miny_b, maxx_b, maxy_b = boundary_poly.bounds
    bound_width = maxx_b - minx_b
    bound_height = maxy_b - miny_b
    bound_center = np.array([(minx_b + maxx_b)/2, (miny_b + maxy_b)/2])

    # Tính Scale Factor để thu nhỏ Boundary vào lọt lòng Rooms
    scale_x = target_width / bound_width
    scale_y = target_height / bound_height
    final_scale = min(scale_x, scale_y) # Chọn scale nhỏ nhất để lọt lòng
    
    print(f"   📉 Scale Factor thu nhỏ: {final_scale:.4f}")

    # 3. Tạo Boundary Mới (Tight)
    new_b_pts = []
    for p in b_pts:
        vec = np.array(p) - bound_center   # Về gốc
        vec = vec * final_scale            # Scale
        vec = vec + room_center            # Về tâm phòng
        new_b_pts.append(vec)
        
    new_boundary_poly = Polygon(new_b_pts).buffer(0)

    # 4. Cắt gọt (Clipping Intersection)
    new_rooms_list = []
    for r in rooms_list:
        old_poly = get_poly(r)
        if not old_poly: continue
        
        # Phép giao: Room giao với Boundary Mới
        clipped_poly = old_poly.intersection(new_boundary_poly)
        
        if clipped_poly.is_empty: continue
        if clipped_poly.geom_type == 'MultiPolygon':
             clipped_poly = max(clipped_poly.geoms, key=lambda a: a.area)
        
        # Cập nhật thông tin phòng
        coords = list(clipped_poly.exterior.coords)[:-1]
        corners = [[round(p[0], 2), round(p[1], 2)] for p in coords]
        
        r['snapped_corners'] = corners
        r['edges'] = [[corners[i][0], corners[i][1], corners[(i+1)%len(corners)][0], corners[(i+1)%len(corners)][1]] for i in range(len(corners))]
        r['area'] = round(clipped_poly.area, 2)
        r['center'] = [round(clipped_poly.centroid.x, 2), round(clipped_poly.centroid.y, 2)]
        b = clipped_poly.bounds
        r['bounding_box'] = [round(b[0],2), round(b[1],2), round(b[2]-b[0],2), round(b[3]-b[1],2)]
        
        new_rooms_list.append(r)

    # Chuyển Boundary mới sang format list dict
    final_boundary_list = [{"x": round(p[0], 2), "y": round(p[1], 2)} for p in new_b_pts]
    
    return final_boundary_list, new_rooms_list, new_boundary_poly

# ==========================================
# PHẦN 3: VISUALIZE & MAIN
# ==========================================
def visualize_final_result(boundary_poly, rooms_list):
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Vẽ Boundary
    bx, by = boundary_poly.exterior.xy
    ax.plot(bx, by, color='#00FF00', linewidth=3, label='Final Boundary (Fixed & Clipped)', zorder=10, marker='o')
    
    # Vẽ Rooms
    colors = plt.cm.tab10.colors
    for i, r in enumerate(rooms_list):
        pts = r['snapped_corners']
        poly = patches.Polygon(pts, closed=True, facecolor=colors[i%10], alpha=0.7, edgecolor='black')
        ax.add_patch(poly)
        # Vẽ ID
        ax.text(r['center'][0], r['center'][1], str(r['id']), fontweight='bold', color='white', fontsize=8)

    ax.set_aspect('equal')
    ax.invert_yaxis()
    ax.set_title(f"KẾT QUẢ GỘP: SHAPE FIX + TIGHTEN + CLIP\n(Margin={CLIP_MARGIN}px)")
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.3)
    
    if SHOW_PLOT:
        plt.show()
    plt.close(fig)

def main():
    # 1. Load Dữ liệu
    sketch_data = load_json(FILE_SKETCH)
    boundary_data = load_json(FILE_BOUNDARY)
    room_data = load_json(FILE_ROOMS)

    if not all([sketch_data, boundary_data, room_data]):
        print("❌ Thiếu file đầu vào. Dừng chương trình.")
        return

    # 2. Bước 1: Tính toán hình dáng chuẩn (Fixed Shape)
    # Input: Sketch gốc + Boundary méo -> Output: Boundary chuẩn hình dáng
    fixed_boundary_pts = calculate_fixed_shape(sketch_data, boundary_data)

    # 3. Bước 2: Siết biên và Cắt phòng (Tighten & Clip)
    # Input: Boundary chuẩn + Rooms -> Output: Boundary thu nhỏ + Rooms đã cắt
    final_bound, final_rooms, final_bound_poly = tighten_and_clip_rooms(fixed_boundary_pts, room_data)

    if final_bound and final_rooms:
        # 4. Bước 3: Ghi đè File
        
        # Ghi Boundary
        save_json({"points": final_bound}, TARGET_BOUNDARY)
        
        # Ghi Rooms
        room_data['rooms'] = final_rooms
        save_json(room_data, TARGET_ROOMS)

        # 5. Vẽ hình kiểm tra
        visualize_final_result(final_bound_poly, final_rooms)
    else:
        print("❌ Có lỗi trong quá trình xử lý.")

if __name__ == "__main__":
    main()