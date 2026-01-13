"""
furniture_placement.py
======================
Chức năng chính:
1. Đọc dữ liệu phòng & tính diện tích.
2. Vẽ ảnh PNG tĩnh (đầy đủ nội thất + kích thước) để làm preview.
3. [V18] Export dữ liệu JSON chi tiết (bao gồm tọa độ nội thất) để Web dựng lại chế độ Interactive.

[PHIÊN BẢN V18 - HYBRID READY]
- Export furniture_list vào JSON.
- Đảm bảo đồng bộ hệ tọa độ giữa Python (OpenCV) và Web (Fabric.js).
- Tự động Sync kết quả sang Web App Static folder.
"""
import cv2
import numpy as np
import json
import os
import math
import shutil  # Quan trọng: Thư viện để copy file
from collections import defaultdict 

# ==========================================
# CONFIGURATION
# ==========================================
FURNITURE_SIZES = {
    "bed": (90, 120), 
    "table": (60, 45), 
    "toilet": (36, 54), 
    "bath": (75, 90),
    "wash": (48, 36),
    "door": (30, 30), 
    "entrance": (40, 40), 
    "window": (40, 3)
}

furniture_positions = {}
export_furniture_list = [] # List chứa nội thất để xuất JSON

# ==========================================
# UTILS: LOAD DATA & IMAGES
# ==========================================

def _load_request_info():
    request_path = os.getenv("REQUEST_JSON")
    if not request_path: return {}
    try: 
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError: 
        script_dir = os.getcwd()
    base_dir = script_dir
    if "scripts" in script_dir.lower(): base_dir = os.path.dirname(script_dir)
    elif not os.path.exists(os.path.join(base_dir, "outputs")):
        base_dir = os.path.dirname(script_dir) 
        if not os.path.exists(os.path.join(base_dir, "outputs")): base_dir = os.path.dirname(base_dir) 

    if not os.path.isabs(request_path):
        script_relative_path = os.path.join(script_dir, request_path)
        if os.path.exists(script_relative_path): request_path = script_relative_path
        else:
            base_relative_path = os.path.join(base_dir, request_path)
            if os.path.exists(base_relative_path): request_path = base_relative_path
            else:
                inputs_relative_path = os.path.join(os.path.join(base_dir, "inputs"), os.path.basename(request_path))
                if os.path.exists(inputs_relative_path): request_path = inputs_relative_path
                else: return {}
    try:
        with open(request_path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def _build_common_queue(metadata):
    queue = []
    study_info = metadata.get("StudyRoom", {})
    if study_info.get("num", 0) > 0:
        for i in range(study_info.get("num", 0)): queue.append("StudyRoom")
    guest_info = metadata.get("GuestRoom", {})
    if guest_info.get("num", 0) > 0:
        for i in range(guest_info.get("num", 0)): queue.append("Japan_Style_Room")
    second_info = metadata.get("SecondRoom", {})
    if second_info.get("num", 0) > 0:
        for i in range(second_info.get("num", 0)): queue.append(f"Bedroom_Second_{i+1}")
    child_info = metadata.get("ChildRoom", {})
    if child_info.get("num", 0) > 0:
        for i in range(child_info.get("num", 0)): queue.append(f"Bedroom_Child_{i+1}")
    return queue

def load_icons(icons_path):
    print("\n🎨 Loading furniture icons...")
    if not os.path.exists(icons_path): return {}
    icons = {}
    icon_files = {
        "bath": "bath.png", "bed": "bed.png", "table": "table.png", "door": "door.png",
        "toilet": "toilet.png", "wash": "wash.png", "entrance": "entrance.png", "window": "window.png"
    }
    for name, filename in icon_files.items():
        path = os.path.join(icons_path, filename)
        if not os.path.exists(path):
            icons[name] = None; continue
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            icons[name] = None; continue
        if len(img.shape) < 3 or img.shape[2] == 3:
            bgr = img[:,:,:3] if len(img.shape) > 2 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            alpha = np.ones(bgr.shape[:2], dtype=bgr.dtype) * 255
            img = cv2.merge((bgr[:,:,0], bgr[:,:,1], bgr[:,:,2], alpha))
        icons[name] = img
    return icons

# ==========================================
# AREA CALCULATION LOGIC
# ==========================================

def calculate_shoelace_area(corners):
    n = len(corners)
    if n < 3: return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += corners[i][0] * corners[j][1]
        area -= corners[j][0] * corners[i][1]
    return abs(area) / 2.0

def calculate_pixel_ratio(img_path, total_area_m2_input):
    if not os.path.exists(img_path): return 0.0
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if img is None: return 0.0
    _, thresh = cv2.threshold(img, 240, 255, cv2.THRESH_BINARY_INV)
    total_pixels = cv2.countNonZero(thresh)
    if total_pixels == 0: return 0.0
    ratio = total_area_m2_input / total_pixels
    print(f"   [Area Calc] Total Input: {total_area_m2_input}m2 | Total Pixels: {total_pixels} | Ratio: {ratio:.6f}")
    return ratio

def update_room_real_areas(rooms, ratio):
    print("\n📐 Calculating Real Room Areas...")
    for room in rooms:
        if not room.get('snapped_corners'): 
            room['area_m2'] = 0
            continue
        pixel_area = calculate_shoelace_area(room['snapped_corners'])
        real_area_m2 = pixel_area * ratio
        room['area_m2'] = round(real_area_m2, 2)
    return rooms

# ==========================================
# UTILS: IMAGE MANIPULATION & EXPORT
# ==========================================

def resize_icon(icon_img, icon_type):
    if icon_img is None: return None
    target_size = FURNITURE_SIZES.get(icon_type, (30, 30))
    return cv2.resize(icon_img, target_size)

def resize_icon_to_fit_zone(icon_img, zone_bbox, fill_ratio=0.7):
    if icon_img is None or not all(zone_bbox): return None
    zone_w, zone_h = int(zone_bbox[2]), int(zone_bbox[3])
    if zone_w <= 0 or zone_h <= 0: return None
    icon_h, icon_w = icon_img.shape[:2]
    if icon_w == 0 or icon_h == 0: return None
    scale = min(zone_w / icon_w, zone_h / icon_h) * fill_ratio
    new_w, new_h = int(icon_w * scale), int(icon_h * scale)
    if new_w < 1 or new_h < 1: return None
    return cv2.resize(icon_img, (new_w, new_h), interpolation=cv2.INTER_AREA)

def rotate_image(image, angle):
    if image is None: return None
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    rad = math.radians(angle)
    sin, cos = abs(math.sin(rad)), abs(math.cos(rad))
    new_w = int(height * sin + width * cos)
    new_h = int(height * cos + width * sin)
    rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
    rot_mat[0, 2] += (new_w / 2) - center[0]
    rot_mat[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(image, rot_mat, (new_w, new_h))

def place_icon(background, icon, position, icon_name="misc", rotation=0):
    """
    [V18] Hàm vẽ icon lên ảnh VÀ lưu thông tin vào danh sách export JSON.
    """
    if icon is None: return background
    h, w = icon.shape[:2]
    x, y = int(position[0]), int(position[1])
    
    # 1. Vẽ lên ảnh (để tạo ảnh tĩnh PNG)
    y_start, y_end = max(0, y), min(background.shape[0], y + h)
    x_start, x_end = max(0, x), min(background.shape[1], x + w)
    icon_y_start, icon_y_end = max(0, -y), h - max(0, y + h - background.shape[0])
    icon_x_start, icon_x_end = max(0, -x), w - max(0, x + w - background.shape[1])
    
    if y_end > y_start and x_end > x_start:
        icon_cropped = icon[icon_y_start:icon_y_end, icon_x_start:icon_x_end]
        if icon_cropped.shape[2] >= 4:
            alpha = icon_cropped[:, :, 3] / 255.0
            alpha = np.expand_dims(alpha, axis=2)
            bg_roi = background[y_start:y_end, x_start:x_end]
            blended = (1.0 - alpha) * bg_roi.astype(float) + alpha * icon_cropped[:, :, :3].astype(float)
            background[y_start:y_end, x_start:x_end] = blended.astype(np.uint8)

    # 2. [V18 NEW] Lưu thông tin để Web vẽ lại
    if icon_name not in ["dimension_text", "misc"]:
        global export_furniture_list
        export_furniture_list.append({
            "type": icon_name,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": rotation 
        })
    
    return background

def check_overlap(rect1, rect2, padding=5):
    x1, y1, w1, h1 = rect1
    x2, y2, w2, h2 = rect2
    return not (x1 + w1 + padding <= x2 or 
                x2 + w2 + padding <= x1 or 
                y1 + h1 + padding <= y2 or 
                y2 + h2 + padding <= y1)

# ==========================================
# TECHNICAL DIMENSIONS (V15 - FIX OVERLAP)
# ==========================================
def get_house_bounds(rooms):
    if not rooms: return 0, 0, 0, 0
    all_x, all_y = [], []
    for r in rooms:
        if not r.get('snapped_corners'): continue
        corners = r['snapped_corners']
        all_x.extend([c[0] for c in corners])
        all_y.extend([c[1] for c in corners])
    if not all_x: return 0,0,0,0
    return min(all_x), min(all_y), max(all_x), max(all_y)

def put_rotated_text(img, text, center, angle, font_scale=0.5, color=(0,0,0), thickness=1):
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    text_w, text_h = text_size
    dim = max(text_w, text_h) + 40 
    txt_img = np.zeros((dim * 2, dim * 2, 4), dtype=np.uint8)
    cx, cy = dim, dim 
    cv2.putText(txt_img, text, (int(cx - text_w/2), int(cy + text_h/2)), font, font_scale, (*color, 255), thickness, cv2.LINE_AA)
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    rotated_txt = cv2.warpAffine(txt_img, M, (dim * 2, dim * 2))
    x_offset = int(center[0] - dim)
    y_offset = int(center[1] - dim)
    return place_icon(img, rotated_txt, (x_offset, y_offset), icon_name="dimension_text", rotation=0)

def draw_dimension_line(canvas, p1, p2, offset_dist, text_val, is_vertical=False):
    p1 = np.array(p1, dtype=float)
    p2 = np.array(p2, dtype=float)
    if np.linalg.norm(p1 - p2) < 5: return canvas

    normal = np.array([1, 0]) if is_vertical else np.array([0, 1])
    p1_ext = p1 + normal * offset_dist
    p2_ext = p2 + normal * offset_dist
    color = (0, 0, 0)
    gray = (160, 160, 160) 
    
    gap = 10
    over = 10
    ext_dir = normal * (1 if offset_dist > 0 else -1)
    
    p1_start_ext = p1 + ext_dir * gap
    p2_start_ext = p2 + ext_dir * gap
    p1_end_ext = p1_ext + ext_dir * over
    p2_end_ext = p2_ext + ext_dir * over

    cv2.line(canvas, tuple(p1_start_ext.astype(int)), tuple(p1_end_ext.astype(int)), gray, 1)
    cv2.line(canvas, tuple(p2_start_ext.astype(int)), tuple(p2_end_ext.astype(int)), gray, 1)
    cv2.line(canvas, tuple(p1_ext.astype(int)), tuple(p2_ext.astype(int)), color, 1)
    
    tick_len = 5
    tick_vec = np.array([1, 1]) if not is_vertical else np.array([-1, 1])
    tick_vec = tick_vec / np.linalg.norm(tick_vec) * tick_len
    
    for p in [p1_ext, p2_ext]:
        t_a = (p - tick_vec).astype(int)
        t_b = (p + tick_vec).astype(int)
        cv2.line(canvas, tuple(t_a), tuple(t_b), color, 2)
    
    mid = (p1_ext + p2_ext) / 2
    text_offset = ext_dir * 15 
    text_pos = mid + text_offset
    angle = 90 if is_vertical else 0
    canvas = put_rotated_text(canvas, text_val, text_pos, angle, font_scale=0.45, color=(0,0,0), thickness=1)
    return canvas

def add_technical_dimensions(canvas, rooms):
    print("\n📏 Adding Room-Based Dimensions (V15 - Fixed Overlap)...")
    min_x, min_y, max_x, max_y = get_house_bounds(rooms)
    if max_x == 0: return canvas

    # Tăng Tolerance lên xíu để bắt dính tốt hơn
    TOLERANCE = 20 
    PX_TO_M = 0.01

    def get_rooms_on_side(side):
        found_segments = []
        for r in rooms:
            if not r.get('snapped_corners'): continue
            r_x = [c[0] for c in r['snapped_corners']]
            r_y = [c[1] for c in r['snapped_corners']]
            r_min_x, r_max_x = min(r_x), max(r_x)
            r_min_y, r_max_y = min(r_y), max(r_y)
            
            seg = None
            if side == 'top':
                if abs(r_min_y - min_y) < TOLERANCE: 
                    seg = {'start': r_min_x, 'end': r_max_x, 'val': r_max_x - r_min_x}
            elif side == 'bottom':
                if abs(r_max_y - max_y) < TOLERANCE: 
                    seg = {'start': r_min_x, 'end': r_max_x, 'val': r_max_x - r_min_x}
            elif side == 'left':
                if abs(r_min_x - min_x) < TOLERANCE: 
                    seg = {'start': r_min_y, 'end': r_max_y, 'val': r_max_y - r_min_y}
            elif side == 'right':
                if abs(r_max_x - max_x) < TOLERANCE: 
                    seg = {'start': r_min_y, 'end': r_max_y, 'val': r_max_y - r_min_y}
            
            if seg:
                found_segments.append(seg)

        # --- FIX 1: Deduplicate Segments (Lọc trùng) ---
        found_segments.sort(key=lambda x: x['start'])
        
        unique_segments = []
        if found_segments:
            prev = found_segments[0]
            unique_segments.append(prev)
            for curr in found_segments[1:]:
                # Nếu điểm đầu và điểm cuối gần trùng với đoạn trước đó -> Bỏ qua (Duplicate)
                if abs(curr['start'] - prev['start']) < 5 and abs(curr['end'] - prev['end']) < 5:
                    continue
                unique_segments.append(curr)
                prev = curr
                
        return unique_segments

    def draw_side(side_name, base_offset_1, base_offset_2):
        segments = get_rooms_on_side(side_name)
        is_vert = side_name in ['left', 'right']
        
        # Tính tổng chiều dài cạnh nhà
        total_len = (max_y - min_y if is_vert else max_x - min_x)
        
        # Vẽ các đoạn chi tiết (Layer 1)
        for seg in segments:
            # --- FIX 2: Skip if segment equals total length ---
            # Nếu đoạn con dài gần bằng đoạn tổng (chênh lệch < 20px), thì KHÔNG vẽ đoạn con nữa
            if abs(seg['val'] - total_len) < TOLERANCE:
                continue

            val_m = f"{seg['val'] * PX_TO_M:.2f}m"
            if side_name == 'top': p1, p2 = (seg['start'], min_y), (seg['end'], min_y)
            elif side_name == 'bottom': p1, p2 = (seg['start'], max_y), (seg['end'], max_y)
            elif side_name == 'left': p1, p2 = (min_x, seg['start']), (min_x, seg['end'])
            else: p1, p2 = (max_x, seg['start']), (max_x, seg['end'])
            
            draw_dimension_line(canvas, p1, p2, base_offset_1, val_m, is_vertical=is_vert)

        # Vẽ đường tổng thể (Layer 2 - Luôn vẽ)
        total_val_m = f"{total_len * PX_TO_M:.2f}m"
        if side_name == 'top': draw_dimension_line(canvas, (min_x, min_y), (max_x, min_y), base_offset_2, total_val_m, False)
        elif side_name == 'bottom': draw_dimension_line(canvas, (min_x, max_y), (max_x, max_y), base_offset_2, total_val_m, False)
        elif side_name == 'left': draw_dimension_line(canvas, (min_x, min_y), (min_x, max_y), base_offset_2, total_val_m, True)
        elif side_name == 'right': draw_dimension_line(canvas, (max_x, min_y), (max_x, max_y), base_offset_2, total_val_m, True)

    # Offset điều chỉnh khoảng cách các đường dim
    draw_side('top', -30, -70)
    draw_side('bottom', 30, 70)
    draw_side('left', -30, -70)
    draw_side('right', 30, 70)
    return canvas

# ==========================================
# LOGIC CORE FUNCTIONS
# ==========================================

def get_valid_entrance_segment(ext_edge, ldk_contour, other_room_contours, proximity_thresh=15, min_length=40):
    p1, p2 = np.array([ext_edge[0], ext_edge[1]]), np.array([ext_edge[2], ext_edge[3]])
    if np.linalg.norm(p1 - p2) < min_length: return None
    num_steps = max(8, int(np.linalg.norm(p1 - p2) / 5))
    valid_points = []
    for i in range(num_steps + 1):
        t = i / num_steps
        p = p1 * (1 - t) + p2 * t
        p_tuple = (float(p[0]), float(p[1]))
        dist_ldk = cv2.pointPolygonTest(ldk_contour, p_tuple, True)
        if abs(dist_ldk) < proximity_thresh:
            is_colliding = False
            for name, contour in other_room_contours.items():
                if abs(cv2.pointPolygonTest(contour, p_tuple, True)) < proximity_thresh:
                    is_colliding = True; break
            if not is_colliding: valid_points.append(p)
    if len(valid_points) < 8: return None
    return (valid_points[0], valid_points[-1])

def find_entrance_location(living_room, all_rooms, exterior_edges, tolerance=10):
    print("\n🚪 Finding entrance location...")
    if not living_room or not living_room.get('snapped_corners'): return None
    ldk_contour = np.array(living_room['snapped_corners']).reshape((-1, 1, 2)).astype(int)
    other_room_contours = {r['name']: np.array(r['snapped_corners']).reshape((-1, 1, 2)).astype(int) 
                           for r in all_rooms if r['name'] != living_room['name'] and r.get('snapped_corners')}
    valid_segments_bottom, valid_segments_other = [], []
    max_y = max((max(c[1] for c in r['snapped_corners']) for r in all_rooms if r.get('snapped_corners')), default=0)

    for ext_edge in exterior_edges:
        if not ext_edge or len(ext_edge) != 4: continue
        segment_coords = get_valid_entrance_segment(ext_edge, ldk_contour, other_room_contours, 15, 40)
        if segment_coords:
            p1, p2 = segment_coords
            center = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            is_bottom = abs(ext_edge[1] - ext_edge[3]) < tolerance and abs(ext_edge[1] - max_y) < tolerance
            item = {'original_edge': ext_edge, 'center': center, 'length': np.linalg.norm(p1 - p2)}
            (valid_segments_bottom if is_bottom else valid_segments_other).append(item)
    target = valid_segments_bottom if valid_segments_bottom else valid_segments_other
    if not target: return None
    best = max(target, key=lambda x: x['length'])
    return {'on_edge': best['original_edge'], 'center': best['center']}

def get_door_side_and_pos(room, doors_list):
    door = next((d for d in doors_list if d['room_name'] == room['name']), None)
    if not door: return None, None
    edge, center = door['on_edge'], door['center']
    is_horizontal = abs(edge[1] - edge[3]) < 5
    if is_horizontal: return ('top' if edge[1] < room['center'][1] else 'bottom'), center
    else: return ('left' if edge[0] < room['center'][0] else 'right'), center

def is_edge_exterior_for_room(room, edge, tolerance=10):
    if not room or not room.get('snapped_corners'): return False
    room_name_lower = room.get('original_name', room['name']).lower() 
    if 'master' in room_name_lower:
        x1, y1, x2, y2 = edge
        if abs(y1 - y2) < tolerance and abs(y1 - max(c[1] for c in room['snapped_corners'])) < tolerance:
            if (x1 + x2)/2 <= (min(c[0] for c in room['snapped_corners']) + max(c[0] for c in room['snapped_corners']))/2: return False 
    directions = set(room.get('exterior_facing', []) or [])
    if not directions: return False
    x1, y1, x2, y2 = edge
    min_x, max_x = min(c[0] for c in room['snapped_corners']), max(c[0] for c in room['snapped_corners'])
    min_y, max_y = min(c[1] for c in room['snapped_corners']), max(c[1] for c in room['snapped_corners'])
    if abs(y1 - y2) < tolerance:
        if abs(y1 - min_y) < tolerance and 'top' in directions: return True
        if abs(y1 - max_y) < tolerance and 'bottom' in directions:
             if 'master' not in room_name_lower: return True
             return (x1 + x2)/2 < (min_x + max_x)/2
    else:
        if abs(x1 - min_x) < tolerance and 'left' in directions: return True
        if abs(x1 - max_x) < tolerance and 'right' in directions: return True
    return False

def find_best_door_position_on_edge(edge, room_name, furniture_positions, neighbor_room_name=None, min_distance=40, door_padding=25, step=1):
    if not edge or len(edge) < 2: return (0, 0)
    if len(edge) == 4: (x1, y1), (x2, y2) = (edge[0], edge[1]), (edge[2], edge[3])
    else: (x1, y1), (x2, y2) = edge[0], edge[1]
    (x1, y1, x2, y2) = (int(x1), int(y1), int(x2), int(y2))
    is_horizontal = abs(y1 - y2) < 5
    if is_horizontal:
        if abs(x2 - x1) < 60: return ((x1 + x2) // 2, y1)
        return (min(x1, x2) + door_padding, y1)
    else:
        if abs(y2 - y1) < 60: return (x1, (y1 + y2) // 2)
        return (x1, min(y1, y2) + door_padding)

def get_valid_door_segment(r_edge, lr_contour, other_room_contours, proximity_thresh=15, min_length=20):
    p1, p2 = np.array([r_edge[0], r_edge[1]]), np.array([r_edge[2], r_edge[3]])
    if np.linalg.norm(p1 - p2) < min_length: return None
    num_steps = max(4, int(np.linalg.norm(p1 - p2) / 5))
    valid_points = []
    for i in range(num_steps + 1):
        t = i / num_steps
        p = p1 * (1 - t) + p2 * t
        p_tuple = (float(p[0]), float(p[1]))
        dist_ldk = cv2.pointPolygonTest(lr_contour, p_tuple, True)
        if dist_ldk > -2 or abs(dist_ldk) < proximity_thresh:
             is_colliding = False
             for name, contour in other_room_contours.items():
                 if abs(cv2.pointPolygonTest(contour, p_tuple, True)) < proximity_thresh: is_colliding = True; break
             if not is_colliding: valid_points.append(p)
    if len(valid_points) < 4: return None 
    segment_start, segment_end = valid_points[0], valid_points[-1]
    if np.linalg.norm(segment_start - segment_end) >= min_length: return (segment_start, segment_end)
    return None

def find_internal_doors(all_rooms, furniture_positions=None, bathroom_connections=None):
    print("\n🚪 Finding internal doors (V11)...")
    doors = []
    living_room = next((r for r in all_rooms if 'living' in r['name'].lower()), None)
    if not living_room or not living_room.get('snapped_corners'): return doors
    lr_contour = np.array(living_room['snapped_corners']).reshape((-1, 2)).astype(int)
    other_room_contours = {r['name']: np.array(r['snapped_corners']).reshape((-1, 2)).astype(int) 
                           for r in all_rooms if r['name'] != living_room['name'] and r.get('snapped_corners')}
    if furniture_positions is None: furniture_positions = {}
    
    for room in all_rooms:
        if room['name'] == living_room['name']: continue
        candidate_edges = []
        curr_others = {k: v for k, v in other_room_contours.items() if k != room['name']}
        for r_edge in room.get('edges', []):
            if not r_edge or len(r_edge) != 4: continue
            if is_edge_exterior_for_room(room, r_edge): continue
            valid_segment = get_valid_door_segment(r_edge, lr_contour, curr_others, 15, 20)
            if valid_segment:
                p1, p2 = valid_segment
                candidate_edges.append({
                    'edge': r_edge, 'shared_segment': [p1.tolist(), p2.tolist()],
                    'center': ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2),
                    'length': np.linalg.norm(p1 - p2)
                })
        if candidate_edges:
            best = max(candidate_edges, key=lambda x: x['length'])
            door_x, door_y = find_best_door_position_on_edge(best['shared_segment'], room['name'], furniture_positions, None)
            doors.append({
                'room_name': room['name'], 'connecting': [room['name'], living_room['name']],
                'center': (door_x, door_y), 'on_edge': best['edge'], 'door_size': [3, 15]
            })
    return doors

def find_bathroom_connections(bathrooms):
    connections = []
    if not bathrooms: return connections
    bathrooms.sort(key=lambda r: r['area'], reverse=True)
    largest_bathroom = bathrooms[0]
    for bathroom in bathrooms:
        if bathroom['name'] != largest_bathroom['name']: continue
        edges = bathroom.get('edges', [])
        h_edges = [e for e in edges if abs(e[1]-e[3])<5]
        v_edges = [e for e in edges if abs(e[0]-e[2])<5]
        if not h_edges or not v_edges: continue
        min_x, max_x = bathroom['bounding_box'][0], bathroom['bounding_box'][0] + bathroom['bounding_box'][2]
        min_y, max_y = bathroom['bounding_box'][1], bathroom['bounding_box'][1] + bathroom['bounding_box'][3]
        w, h = max_x - min_x, max_y - min_y
        ext_facing = bathroom.get('exterior_facing', [])
        ext_wall = next((d for d in ['left', 'right', 'top', 'bottom'] if d in ext_facing), 'right')
        
        if w > h: 
            p1_x = min_x + w * (0.6 if ext_wall == 'right' else 0.4)
            z40 = [int(p1_x), min_y, max_x - int(p1_x), h] if ext_wall == 'right' else [min_x, min_y, int(p1_x) - min_x, h]
            z60 = [min_x, min_y, int(p1_x) - min_x, h] if ext_wall == 'right' else [int(p1_x), min_y, max_x - int(p1_x), h]
            pt_wall = {'type': 'vertical', 'position': int(p1_x), 'start_point': [int(p1_x), min_y], 'end_point': [int(p1_x), max_y]}
        else: 
            p1_y = min_y + h * (0.6 if ext_wall == 'bottom' else 0.4)
            z40 = [min_x, int(p1_y), w, max_y - int(p1_y)] if ext_wall == 'bottom' else [min_x, min_y, w, int(p1_y) - min_y]
            z60 = [min_x, min_y, w, int(p1_y) - min_y] if ext_wall == 'bottom' else [min_x, int(p1_y), w, max_y - int(p1_y)]
            pt_wall = {'type': 'horizontal', 'position': int(p1_y), 'start_point': [min_x, int(p1_y)], 'end_point': [max_x, int(p1_y)]}
        pt_wall.update({'zone_40_bbox': z40, 'zone_60_bbox': z60, 'exterior_wall_side': ext_wall})
        connections.append({'bathroom_name': bathroom['name'], 'partition_walls': [pt_wall]})
    return connections

def draw_precise_partition_walls(canvas, bathroom_connections):
    if not bathroom_connections: return canvas
    for conn in bathroom_connections:
        for wall in conn.get('partition_walls', []):
            cv2.line(canvas, tuple(map(int, wall['start_point'])), tuple(map(int, wall['end_point'])), (0, 0, 0), 3)
    return canvas

def find_smart_wash_position(wash_zone, bath_zone):
    wx, wy, ww, wh = wash_zone
    bx, by, bw, bh = bath_zone
    ICON_W, ICON_D = 48, 36 
    is_vertical_room = wh > ww
    if is_vertical_room:
        bath_is_below = by > wy
        target_y = wy + 5 if bath_is_below else (wy + wh - ICON_D - 5)
        target_x = wx + (ww // 2) - (ICON_W // 2)
        target_x = max(wx, min(target_x, wx + ww - ICON_W))
        return (int(target_x), int(target_y)), 0
    else:
        bath_is_right = bx > wx
        target_x = wx + 5 if bath_is_right else (wx + ww - ICON_D - 5)
        target_y = wy + (wh // 2) - (ICON_W // 2)
        target_y = max(wy, min(target_y, wy + wh - ICON_W))
        return (int(target_x), int(target_y)), 90

def place_advanced_bathroom_furniture(canvas, rooms, internal_doors, icons, bathroom_connections, is_final_draw=False):
    if is_final_draw: print("\n🛁 Placing bathroom furniture (V12 - Smart Placement)...")
    global furniture_positions
    if furniture_positions is None: furniture_positions = {}
    
    all_bathrooms = sorted([r for r in rooms if 'bathroom' in r['name'].lower()], key=lambda r: r['area'], reverse=True)
    if not all_bathrooms: return canvas
    master_bath = all_bathrooms[0]
    
    for bathroom in all_bathrooms:
        if bathroom['name'] not in furniture_positions: furniture_positions[bathroom['name']] = {}
        
        door_info = next((d for d in internal_doors if d['room_name'] == bathroom['name']), None)
        door_rect, door_side = (0,0,0,0), None
        if door_info:
            dc = door_info['center']
            door_rect = (int(dc[0]-15), int(dc[1]-15), 30, 30)
            door_side, _ = get_door_side_and_pos(bathroom, internal_doors)

        conn = next((c for c in bathroom_connections if c['bathroom_name'] == bathroom['name']), None)
        
        if conn and conn.get('partition_walls') and bathroom['name'] == master_bath['name']:
            wall = conn['partition_walls'][0]
            z40, z60 = wall['zone_40_bbox'], wall['zone_60_bbox']
            
            if check_overlap(z40, door_rect, padding=-5):
                 if is_final_draw: print(f"   ⚠️ Door detected in Bath Zone. Swapping!")
                 z40, z60 = z60, z40 
                 
            bath_icon = icons.get('bath')
            if bath_icon is not None:
                zw, zh = int(z40[2]), int(z40[3])
                rot = (zh > zw)
                icon = resize_icon_to_fit_zone(bath_icon, z40, 0.85)
                if icon is not None:
                    angle = 90 if rot else 0
                    if rot: icon = rotate_image(icon, 90)
                    h_i, w_i = icon.shape[:2]
                    px, py = z40[0] + (zw - w_i)//2, z40[1] + (zh - h_i)//2
                    if not check_overlap((px, py, w_i, h_i), door_rect):
                        if is_final_draw: canvas = place_icon(canvas, icon, (px, py), icon_name="bath", rotation=angle)
                        furniture_positions[bathroom['name']]['bath'] = (px, py)

            wash_icon = icons.get('wash')
            if wash_icon is not None:
                icon = resize_icon(wash_icon, 'wash')
                pos, angle = find_smart_wash_position(z60, z40)
                icon = rotate_image(icon, angle)
                if icon is not None:
                    if is_final_draw: canvas = place_icon(canvas, icon, pos, icon_name="wash", rotation=angle)
                    furniture_positions[bathroom['name']]['wash'] = pos
        else:
            toilet_icon = icons.get('toilet')
            if toilet_icon is not None:
                icon = resize_icon(toilet_icon, 'toilet')
                angle = 180 if door_side == 'top' else 0
                icon = rotate_image(icon, angle)
                if icon is not None:
                    x, y, w, h = bathroom['bounding_box']
                    pos = (int(x + w/2 - 18), int(y + h/2 - 27))
                    if is_final_draw: canvas = place_icon(canvas, icon, pos, icon_name="toilet", rotation=angle)
                    furniture_positions[bathroom['name']]['toilet'] = pos
    return canvas

def place_door_icons(canvas, rooms, entrance_coords, internal_doors, icons):
    living_room = next((r for r in rooms if 'living' in r['name'].lower()), None)
    entrance_icon = icons.get('entrance')
    if entrance_icon is not None and entrance_coords and living_room:
        edge, dc = entrance_coords['on_edge'], entrance_coords['center']
        lc = living_room['center']
        is_hor = abs(edge[1]-edge[3]) < 5
        orient = ('top' if edge[1] < lc[1] else 'bottom') if is_hor else ('left' if edge[0] < lc[0] else 'right')
        angle = {'right': -90, 'bottom': 180, 'left': 90, 'top': 0}.get(orient, 0)
        icon = rotate_image(resize_icon(entrance_icon, 'entrance'), angle)
        if icon is not None:
            h, w = icon.shape[:2]
            px, py = int(dc[0]), int(dc[1])
            if orient == 'bottom': px -= w//2
            elif orient == 'top': px -= w//2; py -= h
            elif orient == 'left': px -= w; py -= h//2
            elif orient == 'right': py -= h//2
            canvas = place_icon(canvas, icon, (px, py), icon_name="entrance", rotation=angle)

    door_icon = icons.get('door')
    if internal_doors and door_icon is not None:
        for door in internal_doors:
            room = next((r for r in rooms if r['name'] == door['room_name']), None)
            if not room: continue
            edge, dc = door['on_edge'], door['center']
            rc = room['center']
            is_hor = abs(edge[1]-edge[3]) < 5
            side = ('top' if edge[1] < rc[1] else 'bottom') if is_hor else ('left' if edge[0] < rc[0] else 'right')
            angle = {'left': 270, 'right': 90, 'top': 180, 'bottom': 0}.get(side, 0)
            icon = rotate_image(resize_icon(door_icon, 'door'), angle)
            if icon is not None:
                h, w = icon.shape[:2]
                px, py = dc
                if side == 'left': py -= h//2
                elif side == 'right': px -= w; py -= h//2
                elif side == 'top': px -= w//2
                else: px -= w//2; py -= h
                canvas = place_icon(canvas, icon, (int(px), int(py)), icon_name="door", rotation=angle)
    return canvas

def place_bedroom_furniture(background_img, rooms, icons, internal_doors, is_final_draw=False):
    if is_final_draw: print("\n🛏️ 📚 Placing bedroom furniture (V11 - Collision Aware)...")
    global furniture_positions
    bed_icon, table_icon = icons.get('bed'), icons.get('table')
    target_rooms = [r for r in rooms if "bedroom" in r['name'].lower() or "study" in r['name'].lower()]
    for room in target_rooms:
        if room['name'] not in furniture_positions: furniture_positions[room['name']] = {}
        if not room.get('snapped_corners'): continue
        
        door_info = next((d for d in internal_doors if d['room_name'] == room['name']), None)
        door_rect, door_side = (0,0,0,0), None
        if door_info:
            dc = door_info['center']
            door_rect = (int(dc[0]-20), int(dc[1]-20), 40, 40)
            door_side, _ = get_door_side_and_pos(room, internal_doors)
            
        x_min, y_min = min(c[0] for c in room['snapped_corners']), min(c[1] for c in room['snapped_corners'])
        x_max, y_max = max(c[0] for c in room['snapped_corners']), max(c[1] for c in room['snapped_corners'])
        w_room, h_room = x_max - x_min, y_max - y_min
        angle = 90 if w_room > h_room else 0
        
        place_bed = "bedroom" in room['name'].lower() and bed_icon is not None
        place_table = ("bedroom" in room['name'].lower() or "study" in room['name'].lower()) and table_icon is not None
        on_right = (door_side == 'right') is False 
        
        if place_bed:
            icon = resize_icon(bed_icon, "bed")
            icon = rotate_image(icon, angle)
            if icon is not None:
                h, w = icon.shape[:2]
                px = int(x_max - w - 3) if on_right else int(x_min + 3)
                py = int(y_min + 3)
                if check_overlap((px, py, w, h), door_rect):
                    px = int(x_min + 3) if on_right else int(x_max - w - 3)
                if is_final_draw: background_img = place_icon(background_img, icon, (px, py), icon_name="bed", rotation=angle)
                furniture_positions[room['name']]['bed'] = (px, py)

        if place_table:
            icon = resize_icon(table_icon, "table")
            rot_angle = -90 if 'right' in room.get('exterior_facing', []) else 90
            icon = rotate_image(icon, rot_angle)
            if icon is not None:
                h, w = icon.shape[:2]
                px = int(x_max - w - 3) if on_right else int(x_min + 3)
                py = int(y_max - h - 3)
                if check_overlap((px, py, w, h), door_rect):
                      px = int(x_min + 3) if on_right else int(x_max - w - 3)
                if is_final_draw: background_img = place_icon(background_img, icon, (px, py), icon_name="table", rotation=rot_angle)
                furniture_positions[room['name']]['table'] = (px, py)
    return background_img

def classify_common_rooms(rooms):
    print("\n📖 CLASSIFYING ROOMS...")
    req = _load_request_info()
    queue = _build_common_queue(req)
    master, commons = None, []
    for r in rooms:
        if 'original_name' not in r: r['original_name'] = r['name']
        if 'master' in r['original_name'].lower(): master = r
        elif 'common' in r['original_name'].lower(): commons.append(r)
    commons.sort(key=lambda r: r.get('area', 0))
    idx = 2
    if master: master['name'] = "Bedroom_1"
    elif commons: commons.pop(-1)['name'] = "Bedroom_1"
    for r in commons:
        if queue:
            tag = queue.pop(0)
            if tag == "StudyRoom": r['name'] = "Study_Room"
            elif tag == "Japan_Style_Room": r['name'] = "Japan_Style_Room"
            else: r['name'] = f"Bedroom_{idx}"; idx+=1
        else: r['name'] = f"Bedroom_{idx}"; idx+=1
    return rooms

def place_window_icons(background_img, rooms, icons):
    print("\n🪟 Placing windows...")
    win_icon = icons.get('window')
    if win_icon is None: return background_img
    living = next((r for r in rooms if 'living' in r['name'].lower()), None)
    lr_contour = np.array(living['snapped_corners']).reshape((-1,1,2)).astype(int) if living else None
    base_icon = cv2.resize(win_icon, (60, 5), interpolation=cv2.INTER_AREA)
    for room in rooms:
        if 'living' in room['name'].lower() or not room.get('exterior_facing'): continue
        dirs = set(room.get('exterior_facing', []))
        for edge in room.get('edges', []):
            x1, y1, x2, y2 = edge
            l = math.hypot(x2-x1, y2-y1)
            if l < 60: continue
            mx, my = (x1+x2)//2, (y1+y2)//2
            if lr_contour is not None and abs(cv2.pointPolygonTest(lr_contour, (float(mx), float(my)), True)) < 10: continue
            is_hor = abs(y1-y2) < 5
            valid = False
            if is_hor and (('top' in dirs and abs(y1 - min(c[1] for c in room['snapped_corners']))<5) or 
                           ('bottom' in dirs and abs(y1 - max(c[1] for c in room['snapped_corners']))<5)): valid = True
            if not is_hor and (('left' in dirs and abs(x1 - min(c[0] for c in room['snapped_corners']))<5) or 
                               ('right' in dirs and abs(x1 - max(c[0] for c in room['snapped_corners']))<5)): valid = True
            if valid:
                angle = 0 if is_hor else 90
                icon = base_icon if is_hor else rotate_image(base_icon, 90)
                h, w = icon.shape[:2]
                background_img = place_icon(background_img, icon, (mx - w//2, my - h//2), icon_name="window", rotation=angle)
    return background_img

# ==========================================
# MAIN EXECUTION
# ==========================================

def process_furniture_placement(output_dir="outputs", icons_dir="inputs"):
    # CHUYỂN ĐỔI SANG ĐƯỜNG DẪN TUYỆT ĐỐI NẾU CHƯA CÓ
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)
    if not os.path.isabs(icons_dir):
        icons_dir = os.path.abspath(icons_dir)

    global furniture_positions, export_furniture_list
    furniture_positions = {}
    export_furniture_list = []

    print("="*60)
    print("🏠 FURNITURE PLACEMENT (V18 - HYBRID EXPORT)")
    print("="*60)
    
    room_path = os.path.join(output_dir, "room_data.json")
    ext_path = os.path.join(output_dir, "exterior_wall.json")
    img_path = os.path.join(output_dir, "colored_floorplan.png")

    if not all(os.path.exists(p) for p in [room_path, ext_path, img_path]):
        return False

    with open(room_path, 'r', encoding='utf-8') as f:
        r_data = json.load(f)
    with open(ext_path, 'r', encoding='utf-8') as f:
        e_data = json.load(f)
    canvas = cv2.imread(img_path)
    icons = load_icons(icons_dir)

    req_data = _load_request_info()
    total_area_m2 = req_data.get('total_area_m2', 100.0)
    ratio = calculate_pixel_ratio(img_path, total_area_m2)
    rooms = classify_common_rooms(r_data['rooms'])
    rooms = update_room_real_areas(rooms, ratio)
    r_data['rooms'] = rooms

    bathrooms = [r for r in rooms if 'bath' in r['name'].lower()]
    bath_conns = find_bathroom_connections(bathrooms)
    internal_doors = find_internal_doors(rooms, {}, bath_conns)

    place_advanced_bathroom_furniture(canvas.copy(), rooms, internal_doors, icons, bath_conns, False)
    place_bedroom_furniture(canvas.copy(), rooms, icons, internal_doors, False)

    canvas = cv2.imread(img_path)
    japan_room = next((r for r in rooms if r['name'] == 'Japan_Style_Room'), None)
    if japan_room:
        cv2.fillPoly(canvas, [np.array(japan_room['snapped_corners'], dtype=np.int32)], (144, 238, 144))

    canvas = draw_precise_partition_walls(canvas, bath_conns)
    canvas = place_window_icons(canvas, rooms, icons)

    lr = next((r for r in rooms if 'living' in r['name'].lower()), None)
    ent_coords = find_entrance_location(lr, rooms, e_data.get('exterior_edges', []))
    canvas = place_door_icons(canvas, rooms, ent_coords, internal_doors, icons)

    canvas = place_advanced_bathroom_furniture(canvas, rooms, internal_doors, icons, bath_conns, True)
    canvas = place_bedroom_furniture(canvas, rooms, icons, internal_doors, True)

    canvas = add_technical_dimensions(canvas, r_data['rooms'])

    # 3. [V18] Export Furniture Coordinates to JSON
    r_data['furniture'] = export_furniture_list

    # Lưu lại file JSON tại thư mục outputs
    with open(room_path, 'w', encoding='utf-8') as f:
        json.dump(r_data, f, indent=4)

    # 4. Lưu file ảnh tại thư mục outputs
    out_file = os.path.join(output_dir, "colored_floorplan_with_furniture.png")
    cv2.imwrite(out_file, canvas)
    print(f"✅ Saved Image Locally: {out_file}")

    # ==========================================================
    # 🚀 KHU VỰC UPDATE: ĐỒNG BỘ SANG WEBSITE (DỮ LIỆU & ẢNH)
    # ==========================================================
    # Điều chỉnh đường dẫn này cho khớp với cấu trúc thư mục của bạn
    # Dùng os.path.join hoặc r"..." để tránh lỗi trên Windows
    
    # Chúng ta sẽ tính toán đường dẫn tương đối từ vị trí script hiện tại
    # Script đang ở: ...\ai_processing\module_detect_rooms\scripts\
    # Web App ở:     ...\web_app\floorplan_app\static\floorplan_app\
    
    # Cách an toàn nhất là dùng đường dẫn tuyệt đối mà bạn đã cung cấp
    web_data_path = r"F:\ai-key-plan-develop_final_project\web_app\floorplan_app\static\floorplan_app\data\room_data.json"
    web_img_path = r"F:\ai-key-plan-develop_final_project\web_app\floorplan_app\static\floorplan_app\img\floorplan1.png"

    print(f"\n📡 Syncing results to Website...")
    try:
        # 1. Đồng bộ file JSON (chứa tọa độ edit mới nhất)
        os.makedirs(os.path.dirname(web_data_path), exist_ok=True)
        shutil.copy2(room_path, web_data_path)
        print(f"   ✅ Web Data Updated: {web_data_path}")

        # 2. Đồng bộ file ảnh (ảnh tĩnh có nội thất mới)
        os.makedirs(os.path.dirname(web_img_path), exist_ok=True)
        shutil.copy2(out_file, web_img_path)
        print(f"   ✅ Web Image Updated: {web_img_path}")
        
    except Exception as e:
        print(f"   ❌ Sync Failed: {str(e)}")
    # ==========================================================

    return True

def main():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except:
        script_dir = os.getcwd()
    base = script_dir
    if "scripts" in base.lower():
        base = os.path.dirname(base)
    elif not os.path.exists(os.path.join(base, "outputs")):
        base = os.path.dirname(script_dir)
    out_dir, in_dir = os.path.join(base, "outputs"), os.path.join(base, "inputs")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    process_furniture_placement(out_dir, in_dir)

if __name__ == "__main__":
    main()