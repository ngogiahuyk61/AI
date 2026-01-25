import json
import cv2
import numpy as np
import math
import os
import shutil
from pathlib import Path

# ================= CẤU HÌNH =================
OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'outputs'))
# Đảm bảo thư mục tồn tại để tránh lỗi
os.makedirs(OUTPUTS_DIR, exist_ok=True)

INPUT_JSON = os.path.join(OUTPUTS_DIR, "room_data_with_windows.json")
INPUT_BOUNDARY = os.path.join(OUTPUTS_DIR, "boundary_aligned.json")
ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inputs'))
OUTPUT_IMAGE = os.path.join(OUTPUTS_DIR, "final_floorplan_fixed_v3.png")

# --- [NEW] CẤU HÌNH GÓC XOAY TOÀN BỘ ẢNH ---
DEFAULT_ROTATION_ANGLE = 0
# -------------------------------------------

GLOBAL_SCALE = 3.0
PADDING = 200 # Tăng padding để có chỗ vẽ kích thước
DEFAULT_TOTAL_M2_REFERENCE = 100.0

AI_PROCESSING_DIR = Path(__file__).resolve().parents[2]
ROTATION_INFO_PATH = AI_PROCESSING_DIR / "module_draw_mask" / "input" / "rotation_info.json"
TEXT_INPUT_DIR = AI_PROCESSING_DIR / "model" / "source" / "text_input"

SIZES = {
    "bed": (55, 70),
    "table": (80, 35),
    "toilet": (28, 48),
    "bathtub": (65, 32),
    "window": (40, 8),
    "door_sliding": (60, 1.5),
    "door_main": (30, 30),
    "door_rescue": (30, 30),
    "entrance": (60, 60)
}

ASSET_MAP = {
    "bed": "bed.png",
    "table": "table.png",
    "toilet": "toilet.png",
    "bathtub": "bathtub.png",
    "window": "window.png",
    "door_sliding": "door_sliding.png",
    "entrance": "entrance.png",
    "door_main_0": "door_0.png",
    "door_main_90": "door_90.png",
    "door_main_180": "door_180.png",
    "door_main_270": "door_270.png",
    "door_rescue_0": "door_0.png",
    "door_rescue_90": "door_90.png",
    "door_rescue_180": "door_180.png",
    "door_rescue_270": "door_270.png",
}

# ================= ĐỌC CẤU HÌNH NGOẠI VI =================

def load_rotation_angle(rotation_path: Path = ROTATION_INFO_PATH, default: float = DEFAULT_ROTATION_ANGLE) -> float:
    if not rotation_path.exists():
        return default
    try:
        payload = json.loads(rotation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

    angle = payload.get("rotated_by_degrees")
    try:
        return float(angle)
    except (TypeError, ValueError):
        return default


def latest_text_request_file(directory: Path = TEXT_INPUT_DIR) -> Path | None:
    if not directory.exists():
        return None
    candidates = sorted(
        directory.glob("floorplan-request-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_total_area_reference(default: float = DEFAULT_TOTAL_M2_REFERENCE) -> float:
    latest_request = latest_text_request_file()
    if latest_request is None:
        return default
    try:
        payload = json.loads(latest_request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

    value = payload.get("total_area_m2")
    try:
        area = float(value)
    except (TypeError, ValueError):
        return default

    return area if area > 0 else default

# ================= CÁC HÀM HỖ TRỢ =================

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def transform_point(pt, M):
    """Biến đổi tọa độ điểm (x, y) dựa trên ma trận xoay M"""
    px = (M[0, 0] * pt[0]) + (M[0, 1] * pt[1]) + M[0, 2]
    py = (M[1, 0] * pt[0]) + (M[1, 1] * pt[1]) + M[1, 2]
    return int(px), int(py)

def load_assets():
    assets = {}
    if not os.path.exists(ASSETS_DIR):
        print(f"⚠️ Assets dir missing. Using rectangles.")
        return assets

    main_assets = [
        "bed", "table", "toilet", "bathtub", "window",
        "door_sliding", "entrance", "door_main_0", "door_main_90",
        "door_main_180", "door_main_270"
    ]

    for key in main_assets:
        if key not in ASSET_MAP: continue
        path = os.path.join(ASSETS_DIR, ASSET_MAP[key])
        if os.path.exists(path):
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is not None:
                assets[key] = img
        else:
            # print(f"⚠️ Missing required asset file: {ASSET_MAP[key]}") 
            pass

    rescue_assets = [
        "door_rescue_0", "door_rescue_90",
        "door_rescue_180", "door_rescue_270"
    ]

    for key in rescue_assets:
        if key not in ASSET_MAP: continue
        path = os.path.join(ASSETS_DIR, ASSET_MAP[key])
        if os.path.exists(path) and ASSET_MAP[key] != ASSET_MAP[key.replace("rescue", "main")]:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is not None:
                assets[key] = img
                continue
        angle_key = key.split('_')[-1]
        fallback_key = f"door_main_{angle_key}"
        if fallback_key in assets:
            assets[key] = assets[fallback_key]

    return assets

def rotate_image(image, angle):
    (h, w) = image.shape[:2]
    if h == 0 or w == 0: return image
    (cX, cY) = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D((cX, cY), angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    nW = int((h * sin) + (w * cos))
    nH = int((h * cos) + (w * sin))
    M[0, 2] += (nW / 2) - cX
    M[1, 2] += (nH / 2) - cY
    return cv2.warpAffine(image, M, (nW, nH))

def overlay_image(bg, img, center):
    h, w = img.shape[:2]
    x_c, y_c = center
    x1, y1 = int(x_c - w/2), int(y_c - h/2)
    x2, y2 = x1 + w, y1 + h
    if x1 < 0 or y1 < 0 or x2 > bg.shape[1] or y2 > bg.shape[0]: return bg
    if img.shape[2] == 4:
        alpha = img[:, :, 3] / 255.0
        for c in range(0, 3):
            bg[y1:y2, x1:x2, c] = (alpha * img[:, :, c] + (1.0 - alpha) * bg[y1:y2, x1:x2, c])
    else:
        bg[y1:y2, x1:x2] = img
    return bg

def draw_rect_fallback(canvas, center, size, angle, color=(200,200,200), border=True):
    w, h = size
    rect = ((center[0], center[1]), (w, h), angle)
    box = cv2.boxPoints(rect)
    box = np.int32(box)
    cv2.fillPoly(canvas, [box], color)
    if border:
        cv2.polylines(canvas, [box], True, (0,0,0), 2)

def draw_sliding_door(canvas, center, length, thickness, angle_deg):
    center = np.array(center, dtype=np.float32)
    length = float(length)
    thickness = float(thickness)
    rad = math.radians(angle_deg)
    tangent = np.array([math.cos(rad), math.sin(rad)], dtype=np.float32)
    normal = np.array([-math.sin(rad), math.cos(rad)], dtype=np.float32)
    
    if np.linalg.norm(tangent) == 0: return
    tangent /= np.linalg.norm(tangent)
    normal /= np.linalg.norm(normal)

    half_len = length / 2.0
    main_thickness = max(1, int(round(max(thickness, GLOBAL_SCALE * 1.5))))

    line_start = center - tangent * half_len
    line_end = center + tangent * half_len
    
    # Cut wall
    removal_thickness = max(int(round(GLOBAL_SCALE * 4.0)), main_thickness + 2)
    cv2.line(canvas, tuple(np.int32(line_start)), tuple(np.int32(line_end)), (255, 255, 255), removal_thickness, cv2.LINE_AA)
    cv2.line(canvas, tuple(np.int32(line_start)), tuple(np.int32(line_end)), (0, 0, 0), main_thickness, cv2.LINE_AA)

    cross_span = max(length * 0.3, thickness * 5.0) * 0.4
    cross_half = cross_span / 2.0
    cross_thickness = max(1, int(round(max(thickness * 0.8, GLOBAL_SCALE * 1.5))))

    cross_start = center - normal * cross_half
    cross_end = center + normal * cross_half
    cv2.line(canvas, tuple(np.int32(cross_start)), tuple(np.int32(cross_end)), (0, 0, 0), cross_thickness, cv2.LINE_AA)

# ================= HÀM VẼ KÍCH THƯỚC (DIMENSION LINES) =================

def draw_dimension_line(canvas, start_pt, end_pt, scale_mm_per_pixel, offset=40, type='horizontal'):
    """
    Vẽ đường kích thước kiến trúc (dạng tick chéo hoặc chấm tròn).
    start_pt, end_pt: Tuple (x, y) trên canvas
    scale_mm_per_pixel: Tỉ lệ quy đổi từ pixel sang mm
    offset: Khoảng cách từ điểm đo đến đường kích thước
    type: 'horizontal' (đo ngang) hoặc 'vertical' (đo dọc)
    """
    x1, y1 = start_pt
    x2, y2 = end_pt
    
    # Màu sắc và độ dày
    dim_color = (80, 80, 80) # Xám đậm
    line_thick = 1
    tick_len = 8 # Độ dài gạch chéo
    
    # Tính toán tọa độ đường gióng (Extension lines) và đường kích thước (Dimension line)
    if type == 'horizontal':
        # Đo chiều ngang (vẽ ở trên hoặc dưới)
        # Offset âm thì vẽ lên trên, dương vẽ xuống dưới. Ở đây ta vẽ lên trên (y giảm)
        y_dim = y1 - offset
        
        # 1. Vẽ đường gióng (từ điểm đo đến quá đường kích thước một chút)
        cv2.line(canvas, (x1, y1), (x1, y_dim - 5), dim_color, line_thick, cv2.LINE_AA)
        cv2.line(canvas, (x2, y2), (x2, y_dim - 5), dim_color, line_thick, cv2.LINE_AA)
        
        # 2. Vẽ đường ngang chính
        cv2.line(canvas, (x1, y_dim), (x2, y_dim), dim_color, line_thick, cv2.LINE_AA)
        
        # 3. Vẽ Tick (Gạch chéo tại giao điểm) - Kiểu kiến trúc
        # Tick 1
        cv2.line(canvas, (x1 - 4, y_dim + 4), (x1 + 4, y_dim - 4), dim_color, line_thick + 1, cv2.LINE_AA)
        # Tick 2
        cv2.line(canvas, (x2 - 4, y_dim + 4), (x2 + 4, y_dim - 4), dim_color, line_thick + 1, cv2.LINE_AA)
        
        # 4. Tính và vẽ số đo (mm)
        dist_px = abs(x2 - x1)
        dist_mm = dist_px * scale_mm_per_pixel
        # Làm tròn đến hàng chục (cho giống 1820, 910...)
        val_display = int(round(dist_mm / 10.0)) * 10 
        text = str(val_display)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        f_scale = 0.5
        f_thick = 1
        (tw, th), _ = cv2.getTextSize(text, font, f_scale, f_thick)
        
        # Vẽ chữ nằm trên đường kẻ
        tx = int((x1 + x2) / 2 - tw / 2)
        ty = int(y_dim - 5)
        cv2.putText(canvas, text, (tx, ty), font, f_scale, (0,0,0), f_thick, cv2.LINE_AA)

    elif type == 'vertical':
        # Đo chiều dọc (vẽ bên trái hoặc phải). Ta vẽ bên trái (x giảm)
        x_dim = x1 - offset
        
        # 1. Đường gióng
        cv2.line(canvas, (x1, y1), (x_dim - 5, y1), dim_color, line_thick, cv2.LINE_AA)
        cv2.line(canvas, (x2, y2), (x_dim - 5, y2), dim_color, line_thick, cv2.LINE_AA)
        
        # 2. Đường dọc chính
        cv2.line(canvas, (x_dim, y1), (x_dim, y2), dim_color, line_thick, cv2.LINE_AA)
        
        # 3. Tick chéo
        cv2.line(canvas, (x_dim - 4, y1 + 4), (x_dim + 4, y1 - 4), dim_color, line_thick + 1, cv2.LINE_AA)
        cv2.line(canvas, (x_dim - 4, y2 + 4), (x_dim + 4, y2 - 4), dim_color, line_thick + 1, cv2.LINE_AA)
        
        # 4. Số đo
        dist_px = abs(y2 - y1)
        dist_mm = dist_px * scale_mm_per_pixel
        val_display = int(round(dist_mm / 10.0)) * 10
        text = str(val_display)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        f_scale = 0.5
        f_thick = 1
        (tw, th), _ = cv2.getTextSize(text, font, f_scale, f_thick)
        
        # Vẽ chữ xoay 90 độ (hoặc giữ thẳng nhưng nằm bên cạnh). 
        # Để dễ đọc trên code đơn giản, ta giữ chữ nằm ngang nhưng dời sang trái đường kẻ
        tx = int(x_dim - tw - 8)
        ty = int((y1 + y2) / 2 + th / 2)
        cv2.putText(canvas, text, (tx, ty), font, f_scale, (0,0,0), f_thick, cv2.LINE_AA)

# ================= MAIN =================

def main():
    rotation_angle = load_rotation_angle()
    total_m2_reference = load_total_area_reference()
    print(
        f"🚀 STARTING RENDER V24 - WITH DIMENSIONS (Rotation: {rotation_angle} deg, "
        f"Total area: {total_m2_reference} m2)..."
    )
    data = load_json(INPUT_JSON)
    boundary_data = load_json(INPUT_BOUNDARY)
    if not data or not boundary_data:
        print("❌ Missing input JSON files.")
        return

    assets = load_assets()
    rooms = data['rooms']
    b_pts = boundary_data.get('points', [])
    if not b_pts: return

    # Tính scale diện tích
    b_coords = np.array([[(p['x'], p['y'])] for p in b_pts], dtype=np.float32)
    total_pixel_area = cv2.contourArea(b_coords)
    m2_per_pixel = total_m2_reference / total_pixel_area if total_pixel_area > 0 else 0.0
    
    # [NEW] Tính scale linear (mm/pixel) để dùng cho kích thước
    # Diện tích = L^2 => L = sqrt(Diện tích). mm = m * 1000
    linear_m_per_pixel = math.sqrt(m2_per_pixel) if m2_per_pixel > 0 else 0
    mm_per_pixel = linear_m_per_pixel * 1000

    if m2_per_pixel > 0:
        print(f"   📐 Area scale: 1 m² = {1/m2_per_pixel:.1f} pixels")
        print(f"   📏 Linear scale: 1 pixel ≈ {mm_per_pixel:.2f} mm")

    # Tính kích thước canvas
    all_pts = []
    for r in rooms: all_pts.extend(r.get('snapped_corners', []))
    all_pts.extend([(p['x'], p['y']) for p in b_pts])
    
    pts = np.array(all_pts)
    min_x, min_y = np.min(pts, axis=0)
    max_x, max_y = np.max(pts, axis=0)
    
    w_real = (max_x - min_x) * GLOBAL_SCALE
    h_real = (max_y - min_y) * GLOBAL_SCALE
    w_canvas = int(w_real + 2 * PADDING)
    h_canvas = int(h_real + 2 * PADDING)

    def transform(pt):
        return int((pt[0] - min_x) * GLOBAL_SCALE + PADDING), \
               int((pt[1] - min_y) * GLOBAL_SCALE + PADDING)

    canvas = np.ones((h_canvas, w_canvas, 3), dtype=np.uint8) * 255

    # -----------------------------------------------------------
    # BƯỚC 1: VẼ CƠ BẢN (Tường, Sàn, Nội thất, Cửa)
    # -----------------------------------------------------------

    # 1. Vẽ Boundary và Tô màu nền
    scaled_boundary = [transform((p['x'], p['y'])) for p in b_pts]
    b_np = np.array(scaled_boundary, dtype=np.int32)
    
    # Tô nền living
    cv2.fillPoly(canvas, [b_np], (208, 253, 255))
    # Vẽ viền boundary
    cv2.polylines(canvas, [b_np], True, (0, 0, 0), int(4 * GLOBAL_SCALE))

    # 2. Vẽ Nền phòng & Chuẩn bị Text
    room_polys = {}
    total_other_room_area = 0.0
    scaled_living_poly = None
    
    text_data_queue = [] 
    window_queue = []

    FONT = cv2.FONT_HERSHEY_SIMPLEX
    font_scale_name = max(1.2, 0.5 * GLOBAL_SCALE)
    font_scale_area = max(1.0, 0.4 * GLOBAL_SCALE)
    font_thickness = int(2 * GLOBAL_SCALE)

    for r in rooms:
        corners = r.get('snapped_corners', [])
        if not corners: continue
        scaled_corners = [transform(p) for p in corners]
        pts_np = np.array(scaled_corners, dtype=np.int32)
        room_polys[r['name']] = pts_np
        name_lower = r['name'].lower()

        if 'living' in name_lower:
            scaled_living_poly = pts_np
            continue

        # Tô màu nền
        col = (245, 245, 245)
        if 'toilet' in name_lower or 'bath' in name_lower or 'wash' in name_lower: col = (210, 216, 173)
        elif 'bedroom' in name_lower or 'master' in name_lower: col = (0, 215, 255)
        elif 'balcony' in name_lower: col = (204, 230, 204)
        elif 'japan' in name_lower: col = (204, 248, 223)
        elif 'study' in name_lower: col = (255, 255, 255)

        cv2.fillPoly(canvas, [pts_np], col)
        cv2.polylines(canvas, [pts_np], True, (0, 0, 0), int(2 * GLOBAL_SCALE))

        # Tính diện tích & Tâm
        room_coords_unscaled = np.array([[(p[0], p[1])] for p in corners], dtype=np.float32)
        room_m2 = cv2.contourArea(room_coords_unscaled) * m2_per_pixel
        total_other_room_area += room_m2

        if 'living' not in name_lower:
            r['area'] = float(f"{room_m2:.2f}")
        
        M_moments = cv2.moments(pts_np)
        cX = int(M_moments["m10"] / M_moments["m00"]) if M_moments["m00"] != 0 else int(np.mean(pts_np, axis=0)[0])
        cY = int(M_moments["m01"] / M_moments["m00"]) if M_moments["m00"] != 0 else int(np.mean(pts_np, axis=0)[1])

        # Chuẩn hóa tên
        room_name = r['name']
        if name_lower == 'bathroom_wash': room_name = "Washroom"
        elif name_lower == 'bathroom_bath': room_name = "Bathroom"
        elif 'bedroom' in name_lower:
             parts = room_name.split('_')
             room_id = parts[-1] if parts[-1].isdigit() else '1'
             room_name = f"Bedroom {room_id}"
        elif 'japan' in name_lower: room_name = "Japan Room"
        elif 'study' in name_lower: room_name = "Study Room"
        elif 'storage' in name_lower: room_name = "Storage"
        elif 'balcony' in name_lower: room_name = "Balcony"
        elif 'bathroom' in name_lower: room_name = "Toilet"
        else: room_name = room_name.replace("_", " ")
        
        area_text = f"{room_m2:.1f} m2"

        text_data_queue.append({
            "name": room_name,
            "area": area_text,
            "center": (cX, cY)
        })

    # Xử lý LDK Text
    if scaled_living_poly is not None and m2_per_pixel > 0:
        M_moments = cv2.moments(scaled_living_poly)
        cX = int(M_moments["m10"] / M_moments["m00"]) if M_moments["m00"] != 0 else int(np.mean(scaled_living_poly, axis=0)[0])
        cY = int(M_moments["m01"] / M_moments["m00"]) if M_moments["m00"] != 0 else int(np.mean(scaled_living_poly, axis=0)[1])
        
        ldk_m2 = total_m2_reference - total_other_room_area

        for room_obj in rooms:
            if 'living' in room_obj['name'].lower():
                room_obj['area'] = float(f"{ldk_m2:.2f}")
                break
            
        text_data_queue.append({
            "name": "LDK",
            "area": f"{ldk_m2:.1f} m2",
            "center": (cX, cY)
        })

    # 3. Vẽ Nội thất & Cửa
    for r in rooms:
        room_poly = room_polys.get(r['name'])
        if room_poly is None: continue

        for item in r.get('furniture', []):
            itype = item['type']
            std_w, std_h = SIZES.get(itype, (40, 40))
            scale_w, scale_h = std_w * GLOBAL_SCALE, std_h * GLOBAL_SCALE
            json_w, json_h = item.get('size', (std_w, std_h))
            fallback_w, fallback_h = json_w * GLOBAL_SCALE, json_h * GLOBAL_SCALE
            cx, cy = transform(item['center'])
            angle = item['angle']

            if itype == 'window':
                window_queue.append({
                    'center': (cx, cy),
                    'size': (fallback_w, fallback_h),
                    'angle': angle
                })
                continue

            asset_key = itype
            if itype in ['bathtub', 'toilet']: asset_key = itype
            
            if asset_key in assets:
                img = assets[asset_key]
                img_res = cv2.resize(img, (int(scale_w), int(scale_h)))
                final_angle = angle
                
                if itype == 'toilet':
                    norm_angle = angle % 360
                    if not ((315 <= norm_angle <= 360) or (0 <= norm_angle <= 45) or (135 <= norm_angle <= 225)):
                        final_angle += 180
                else:
                    diff_direct = abs(json_w - std_w) + abs(json_h - std_h)
                    diff_swapped = abs(json_w - std_h) + abs(json_h - std_w)
                    if diff_swapped < diff_direct: final_angle += 90
                
                overlay_image(canvas, rotate_image(img_res, final_angle), (cx, cy))
            else:
                col = (200, 230, 200) if itype == 'bed' else (200, 200, 200)
                draw_rect_fallback(canvas, (cx, cy), (fallback_w, fallback_h), angle, col, True)

        if 'door' in r:
            d = r['door']
            dtype = "door_sliding" if d.get('type') == 'sliding' else "door_rescue" if d.get('type') == 'rescue' else "door_main"
            raw_w, raw_h = SIZES[dtype]
            w, h = raw_w * GLOBAL_SCALE, raw_h * GLOBAL_SCALE
            pos_wall = transform(d['position'])
            angle = d['angle']

            if dtype == "door_sliding":
                draw_sliding_door(canvas, pos_wall, w, h, angle)
            else:
                rounded_angle = int(round(angle / 90) * 90) % 360
                asset_key = f"{dtype}_{rounded_angle}"
                rad = math.radians(angle)
                shift_x = -(h / 2) * math.sin(rad)
                shift_y = (h / 2) * math.cos(rad)
                target_x, target_y = int(pos_wall[0] + shift_x), int(pos_wall[1] + shift_y)

                if asset_key in assets:
                    overlay_image(canvas, cv2.resize(assets[asset_key], (int(w), int(h))), (target_x, target_y))
                else:
                    draw_rect_fallback(canvas, (target_x, target_y), (w, h), angle, (150, 100, 50), True)

        if 'entrance' in r:
            e = r['entrance']
            raw_w, raw_h = SIZES["entrance"]
            w, h = raw_w * GLOBAL_SCALE, raw_h * GLOBAL_SCALE
            pos = transform(e['position'])
            angle = e['angle']
            
            rad = math.radians(angle)
            normal_vec = np.array([-math.sin(rad), math.cos(rad)], dtype=np.float32)
            tangent_vec = np.array([math.cos(rad), math.sin(rad)], dtype=np.float32)
            
            test_pt = (pos[0] + normal_vec[0]*20, pos[1] + normal_vec[1]*20)
            if cv2.pointPolygonTest(b_np, test_pt, False) >= 0:
                facing_vec = normal_vec
            else:
                facing_vec = -normal_vec

            vector_angle = math.degrees(math.atan2(facing_vec[1], facing_vec[0]))
            base_rot = vector_angle + 90
            norm_rot = base_rot % 360
            final_rot = base_rot + 180 if (315 <= norm_rot <= 360) or (0 <= norm_rot <= 45) or (135 <= norm_rot <= 225) else base_rot
            
            offset_door = h / 2
            tx, ty = int(pos[0] + facing_vec[0]*offset_door), int(pos[1] + facing_vec[1]*offset_door)

            h_gray = h
            offset_gray = h_gray / 2
            tx_gray_base = pos[0] + facing_vec[0] * offset_gray
            ty_gray_base = pos[1] + facing_vec[1] * offset_gray

            scan_margin = 20.0
            scan_origin = np.array([tx + facing_vec[0]*scan_margin, ty + facing_vec[1]*scan_margin], dtype=np.float32)

            def get_dist_high_precision(start_pt, direction):
                max_step = 2000
                step_size = 1.0 
                for d in np.arange(0, max_step, step_size):
                    chk_pt = start_pt + direction * d
                    chk_tuple = (float(chk_pt[0]), float(chk_pt[1]))
                    if cv2.pointPolygonTest(b_np, chk_tuple, False) < -2:
                        return d
                    for r_name, r_poly in room_polys.items():
                        name_lower = r_name.lower()
                        if 'living' in name_lower or 'ldk' in name_lower: continue
                        if cv2.pointPolygonTest(r_poly, chk_tuple, False) > 0:
                            return d
                return 0.0

            dist_pos = get_dist_high_precision(scan_origin, tangent_vec)
            dist_neg = get_dist_high_precision(scan_origin, -tangent_vec)
            
            total_gray_w = dist_pos + dist_neg
            if total_gray_w < w:
                total_gray_w = w
                shift = 0 
            else:
                shift = (dist_pos - dist_neg) / 2
            
            gray_cx = tx_gray_base + tangent_vec[0] * shift
            gray_cy = ty_gray_base + tangent_vec[1] * shift
            
            rect_bg = ((gray_cx, gray_cy), (total_gray_w, h_gray), angle)
            box_bg = np.int32(cv2.boxPoints(rect_bg))
            cv2.fillPoly(canvas, [box_bg], (192, 192, 192))
            
            rack_depth_cm = 20.0
            rack_w_px = rack_depth_cm * GLOBAL_SCALE 
            rack_l_px = h_gray * 0.5 
            
            side_dist = dist_neg 
            side_vec = -tangent_vec
            
            if side_dist > rack_w_px:
                rack_offset_tangent = side_dist - (rack_w_px / 2)
                rack_cx = tx_gray_base + side_vec[0] * rack_offset_tangent
                rack_cy = ty_gray_base + side_vec[1] * rack_offset_tangent
                
                rect_rack = ((rack_cx, rack_cy), (rack_w_px, rack_l_px), angle)
                box_rack = np.int32(cv2.boxPoints(rect_rack))
                
                cv2.fillPoly(canvas, [box_rack], (255, 255, 255))
                cv2.polylines(canvas, [box_rack], True, (100, 100, 100), 1)

            cv2.polylines(canvas, [b_np], True, (0, 0, 0), int(4 * GLOBAL_SCALE))
            for r_name, r_poly in room_polys.items():
                name_lower = r_name.lower()
                if 'living' not in name_lower and 'ldk' not in name_lower:
                     cv2.polylines(canvas, [r_poly], True, (0, 0, 0), int(2 * GLOBAL_SCALE))

            if "entrance" in assets:
                overlay_image(canvas, rotate_image(cv2.resize(assets["entrance"], (int(w), int(h))), final_rot), (tx, ty))
            else:
                draw_rect_fallback(canvas, (tx, ty), (w, h), final_rot, (100, 255, 100), True)

    for w_data in window_queue:
        draw_rect_fallback(
            canvas, 
            w_data['center'], 
            w_data['size'], 
            w_data['angle'], 
            (255, 255, 255), 
            True
        )
        
    # -----------------------------------------------------------
    # [NEW] BƯỚC 1.5: VẼ HỆ THỐNG DIMENSION LINES
    # -----------------------------------------------------------
    # Tìm bounding box của toàn bộ ngôi nhà trên canvas
    bx, by, bw, bh = cv2.boundingRect(b_np)
    
    # Vẽ kích thước tổng (Outer Dimensions)
    if mm_per_pixel > 0:
        # Kích thước Ngang (Trên cùng) - Cách mép trên bounding box 60px
        draw_dimension_line(canvas, (bx, by), (bx + bw, by), mm_per_pixel, offset=60, type='horizontal')
        
        # Kích thước Dọc (Bên trái) - Cách mép trái bounding box 60px
        draw_dimension_line(canvas, (bx, by), (bx, by + bh), mm_per_pixel, offset=60, type='vertical')

    # -----------------------------------------------------------
    # BƯỚC 2: XOAY TOÀN BỘ ẢNH
    # -----------------------------------------------------------
    
    if rotation_angle != 0:
        (h, w) = canvas.shape[:2]
        center = (w // 2, h // 2)
        
        M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
        
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]
        
        canvas = cv2.warpAffine(canvas, M, (new_w, new_h), borderValue=(255, 255, 255))
        
        for item in text_data_queue:
            item["center"] = transform_point(item["center"], M)

    # -----------------------------------------------------------
    # BƯỚC 3: VẼ CHỮ
    # -----------------------------------------------------------
    
    for item in text_data_queue:
        name_txt = item["name"]
        raw_area_txt = item["area"] 
        (cX, cY) = item["center"]
        
        if raw_area_txt.endswith("2"):
            base_txt = raw_area_txt[:-1]
            sup_txt = "2"
        else:
            base_txt = raw_area_txt
            sup_txt = ""

        (w_name, h_name), _ = cv2.getTextSize(name_txt, FONT, font_scale_name, font_thickness)
        (w_base, h_base), _ = cv2.getTextSize(base_txt, FONT, font_scale_area, font_thickness)
        
        font_scale_sup = font_scale_area * 0.6
        (w_sup, h_sup), _ = cv2.getTextSize(sup_txt, FONT, font_scale_sup, font_thickness)
        
        w_area_total = w_base + w_sup

        line_gap = int(10 * GLOBAL_SCALE) 
        
        y_name = cY - int(line_gap / 2)
        x_name = cX - w_name // 2
        
        y_area_base = cY + int(line_gap / 2) + h_base
        x_area_start = cX - w_area_total // 2
        
        h_canv, w_canv = canvas.shape[:2]
        x_name = max(10, min(w_canv - w_name - 10, x_name))
        y_name = max(h_name + 10, min(h_canv - 10, y_name))
        
        x_area_start = max(10, min(w_canv - w_area_total - 10, x_area_start))
        y_area_base = max(h_base + 10, min(h_canv - 10, y_area_base))

        cv2.putText(canvas, name_txt, (x_name, y_name), FONT, font_scale_name, (0, 0, 0), font_thickness, cv2.LINE_AA)
        
        area_color = (120, 120, 120)
        cv2.putText(canvas, base_txt, (x_area_start, y_area_base), FONT, font_scale_area, area_color, font_thickness, cv2.LINE_AA)
        
        if sup_txt:
            x_sup = x_area_start + w_base + 2 
            y_sup = y_area_base - int(h_base * 0.35)
            cv2.putText(canvas, sup_txt, (x_sup, y_sup), FONT, font_scale_sup, area_color, max(1, font_thickness - 1), cv2.LINE_AA)

    # -----------------------------------------------------------
    # BƯỚC 4: LƯU & COPY
    # -----------------------------------------------------------

    if cv2.imwrite(OUTPUT_IMAGE, canvas):
        print(f"✅ Render Complete! Output: {OUTPUT_IMAGE}")
        
        try:
            data['total_area_m2'] = total_m2_reference
            with open(INPUT_JSON, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"✅ Updated areas saved to: {INPUT_JSON}")
        except Exception as e:
            print(f"❌ Failed to update JSON area: {e}")
            
    else:
        print(f"❌ FAILED to save image to {OUTPUT_IMAGE}. Check folder permissions.")

    try:
        web_app_dir = Path(__file__).resolve().parents[3] / "web_app"
        source_static_dir = web_app_dir / "floorplan_app" / "static" / "floorplan_app" / "img"
        iis_static_dir = web_app_dir / "static" / "floorplan_app" / "img"

        os.makedirs(source_static_dir, exist_ok=True)
        os.makedirs(iis_static_dir, exist_ok=True)

        files_to_copy = ["floorplan1.png", "proposal1.png"]

        for file_name in files_to_copy:
            target_source = source_static_dir / file_name
            shutil.copy2(OUTPUT_IMAGE, target_source)
            print(f"   ✅ Copied to Source: {target_source}")

            target_iis = iis_static_dir / file_name
            shutil.copy2(OUTPUT_IMAGE, target_iis)
            print(f"   ✅ Copied to IIS:    {target_iis}")

    except Exception as e:
        print(f"   ⚠️ Error in web app copy block: {e}")

if __name__ == "__main__":
    main()

    import json
import cv2
import numpy as np
import math
import os
import shutil
from pathlib import Path

# ================= CẤU HÌNH =================
# Đường dẫn thư mục (Tự động điều chỉnh theo vị trí file script)
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
INPUTS_DIR = BASE_DIR / "inputs"
ASSETS_DIR = BASE_DIR.parent.parent / "furnitures_doors" / "assets" # Giả định đường dẫn assets

# Đảm bảo thư mục tồn tại
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

INPUT_JSON = OUTPUTS_DIR / "room_data.json" # File json bạn vừa cung cấp
OUTPUT_IMAGE = OUTPUTS_DIR / "floorplan_with_dimensions.png"

# Tỉ lệ ảnh đầu ra (Tăng lên để ảnh nét hơn)
GLOBAL_SCALE = 4.0 
PADDING = 300  # Khoảng trống lề để vẽ đường kích thước bao quanh

# Giả định diện tích tổng thể để tính tỉ lệ pixel -> mm
# Nếu trong JSON không có field này, script sẽ dùng giá trị mặc định
DEFAULT_TOTAL_M2 = 100.0 

# ================= HÀM HỖ TRỢ =================

def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def calculate_mm_per_pixel(rooms_data, default_m2):
    """Tính tỉ lệ quy đổi từ Pixel sang Millimeter dựa trên tổng diện tích"""
    total_pixel_area = 0
    for r in rooms_data.get('rooms', []):
        corners = r.get('snapped_corners', [])
        if len(corners) > 2:
            pts = np.array(corners, dtype=np.float32)
            total_pixel_area += cv2.contourArea(pts)
    
    # Nếu JSON không có total_area thực tế, dùng default
    # Công thức: sqrt(m2 / pixel_area) * 1000 = mm/pixel
    if total_pixel_area <= 0: return 10.0 # Fallback
    
    # Giả sử chúng ta dùng diện tích tham chiếu để scale
    # Nếu bạn muốn chính xác tuyệt đối, cần diện tích thực từ input
    real_m2 = rooms_data.get('total_area_m2', default_m2)
    
    scale_factor = math.sqrt(real_m2 / total_pixel_area) * 1000
    return scale_factor

def draw_architectural_tick(canvas, center, size, color, thickness):
    """Vẽ gạch chéo (Tick) tại đầu đường kích thước"""
    x, y = int(center[0]), int(center[1])
    d = int(size / 2)
    # Vẽ gạch chéo góc 45 độ
    cv2.line(canvas, (x - d, y + d), (x + d, y - d), color, thickness, cv2.LINE_AA)

def draw_dimension_line(canvas, p1, p2, mm_val, scale, offset=40):
    """
    Vẽ đường kích thước kiến trúc từ p1 đến p2
    offset: Khoảng cách đẩy đường đo ra khỏi tường (pixel)
    """
    p1 = np.array(p1, dtype=np.float32)
    p2 = np.array(p2, dtype=np.float32)
    
    # 1. Tính vector hướng của tường
    edge_vec = p2 - p1
    length_px = np.linalg.norm(edge_vec)
    if length_px == 0: return
    
    unit_vec = edge_vec / length_px
    # Vector pháp tuyến (vuông góc 90 độ)
    normal_vec = np.array([-unit_vec[1], unit_vec[0]], dtype=np.float32)
    
    # 2. Tính toán các điểm vẽ
    # Điểm bắt đầu và kết thúc của đường ngang (Dimension Line)
    dim_p1 = p1 + normal_vec * offset
    dim_p2 = p2 + normal_vec * offset
    
    # Điểm chân đường gióng (Extension Line) - hở tường 1 chút
    ext_p1_start = p1 + normal_vec * 5 
    ext_p1_end = dim_p1 + normal_vec * 10 # Nhô ra khỏi đường ngang 1 chút
    
    ext_p2_start = p2 + normal_vec * 5
    ext_p2_end = dim_p2 + normal_vec * 10
    
    # 3. Vẽ hình
    color = (60, 60, 60) # Màu xám đen
    thick = max(1, int(1.5 * scale)) # Độ dày nét
    
    # Đường gióng 1
    cv2.line(canvas, tuple(np.int32(ext_p1_start)), tuple(np.int32(ext_p1_end)), color, max(1, int(1*scale)), cv2.LINE_AA)
    # Đường gióng 2
    cv2.line(canvas, tuple(np.int32(ext_p2_start)), tuple(np.int32(ext_p2_end)), color, max(1, int(1*scale)), cv2.LINE_AA)
    # Đường ngang chính
    cv2.line(canvas, tuple(np.int32(dim_p1)), tuple(np.int32(dim_p2)), color, thick, cv2.LINE_AA)
    
    # Vẽ Tick (Gạch chéo)
    tick_size = 8 * scale
    draw_architectural_tick(canvas, dim_p1, tick_size, color, thick+1)
    draw_architectural_tick(canvas, dim_p2, tick_size, color, thick+1)
    
    # 4. Vẽ số đo (Text)
    text = str(int(round(mm_val)))
    
    # Cấu hình font
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.4 * scale
    font_thick = max(1, int(1 * scale))
    
    (t_w, t_h), _ = cv2.getTextSize(text, font, font_scale, font_thick)
    
    # Vị trí text: Giữa đoạn thẳng và nhích lên trên pháp tuyến
    mid_pt = (dim_p1 + dim_p2) / 2
    text_pos = mid_pt + normal_vec * (t_h + 5 * scale)
    
    # Xoay text (Đơn giản hóa: Luôn vẽ ngang để dễ đọc, có nền trắng)
    t_x = int(mid_pt[0] - t_w / 2)
    t_y = int(mid_pt[1] + t_h / 2)
    
    # Vẽ nền trắng nhỏ dưới chữ để không bị chìm
    pad = int(2 * scale)
    cv2.rectangle(canvas, (t_x - pad, t_y - t_h - pad), (t_x + t_w + pad, t_y + pad), (255,255,255), -1)
    cv2.putText(canvas, text, (t_x, t_y), font, font_scale, (0,0,0), font_thick, cv2.LINE_AA)


# ================= MAIN PROCESS =================

def main():
    print("🚀 Bắt đầu render ảnh với đường kích thước...")
    
    # 1. Load Data
    data = load_json(INPUT_JSON)
    if not data:
        print(f"❌ Không tìm thấy file: {INPUT_JSON}")
        return

    rooms = data.get('rooms', [])
    if not rooms:
        print("❌ JSON không có dữ liệu rooms")
        return

    # 2. Tính toán khung hình (Canvas)
    all_points = []
    for r in rooms:
        all_points.extend(r.get('snapped_corners', []))
    
    if not all_points: return

    pts = np.array(all_points)
    min_x, min_y = np.min(pts, axis=0)
    max_x, max_y = np.max(pts, axis=0)
    
    # Kích thước thực tế sau khi scale
    w_content = (max_x - min_x) * GLOBAL_SCALE
    h_content = (max_y - min_y) * GLOBAL_SCALE
    
    w_canvas = int(w_content + 2 * PADDING)
    h_canvas = int(h_content + 2 * PADDING)
    
    # Tạo canvas trắng
    canvas = np.ones((h_canvas, w_canvas, 3), dtype=np.uint8) * 255
    
    # Hàm convert toạ độ gốc -> toạ độ canvas
    def transform(pt):
        px = int((pt[0] - min_x) * GLOBAL_SCALE + PADDING)
        py = int((pt[1] - min_y) * GLOBAL_SCALE + PADDING)
        return (px, py)

    # 3. Tính tỉ lệ mm
    mm_per_pixel = calculate_mm_per_pixel(data, DEFAULT_TOTAL_M2)
    print(f"📏 Tỉ lệ tính toán: 1 pixel ~ {mm_per_pixel:.2f} mm")

    # 4. Vẽ nền phòng (Layer dưới)
    for r in rooms:
        corners = r.get('snapped_corners', [])
        if not corners: continue
        
        poly_pts = [transform(p) for p in corners]
        pts_np = np.array(poly_pts, dtype=np.int32)
        
        # Chọn màu
        name = r.get('name', '').lower()
        col = (240, 240, 240) # Màu mặc định
        if 'bed' in name: col = (204, 229, 255) # Cam nhạt (đổi thành xanh nhạt cho dịu)
        elif 'bath' in name or 'toilet' in name: col = (210, 216, 173)
        elif 'living' in name: col = (208, 253, 255) # Vàng nhạt (LDK)
        elif 'study' in name: col = (255, 215, 0)
        
        cv2.fillPoly(canvas, [pts_np], col)
        cv2.polylines(canvas, [pts_np], True, (0,0,0), int(2*GLOBAL_SCALE))
        
        # Vẽ tên phòng
        center = r.get('center', corners[0])
        cx, cy = transform(center)
        
        label = r.get('name', '').replace('_', ' ').title()
        if "Living" in label: label = "LDK"
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(canvas, label, (cx - 40, cy), font, 0.5*GLOBAL_SCALE, (0,0,0), int(1.5*GLOBAL_SCALE), cv2.LINE_AA)


    # 5. VẼ ĐƯỜNG KÍCH THƯỚC (QUAN TRỌNG)
    # Duyệt qua từng phòng và vẽ kích thước các cạnh
    
    for r in rooms:
        corners = r.get('snapped_corners', [])
        num_pts = len(corners)
        if num_pts < 3: continue
        
        # Tính tâm phòng (để xác định hướng đẩy đường đo ra ngoài)
        poly_pts_unscaled = np.array(corners)
        center_x = np.mean(poly_pts_unscaled[:, 0])
        center_y = np.mean(poly_pts_unscaled[:, 1])
        
        for i in range(num_pts):
            p1_raw = corners[i]
            p2_raw = corners[(i + 1) % num_pts]
            
            # Tính độ dài thực tế (mm)
            dist_px = np.linalg.norm(np.array(p1_raw) - np.array(p2_raw))
            mm_val = dist_px * mm_per_pixel
            
            # Chỉ vẽ kích thước cho cạnh dài (> 500mm) để đỡ rối
            if mm_val < 500: continue
            
            # Chuyển toạ độ sang canvas
            p1 = transform(p1_raw)
            p2 = transform(p2_raw)
            
            # Xác định hướng đẩy (Normal Vector)
            edge_vec = np.array(p2) - np.array(p1)
            # Pháp tuyến mặc định
            normal = np.array([-edge_vec[1], edge_vec[0]])
            
            # Kiểm tra hướng: Vector từ trung điểm cạnh về tâm phòng
            mid_pt = (np.array(p1) + np.array(p2)) / 2
            vec_to_center = np.array([transform((center_x, center_y))]) - mid_pt
            
            # Nếu pháp tuyến cùng chiều với hướng về tâm -> Đảo ngược để hướng ra ngoài
            # Dùng tích vô hướng (Dot Product)
            # Chú ý: vec_to_center shape là (1,2), normal là (2,)
            if np.dot(normal, vec_to_center[0]) > 0:
                # Đổi chiều pháp tuyến bằng cách đổi thứ tự p1, p2 truyền vào hàm vẽ
                draw_p1, draw_p2 = p2, p1
            else:
                draw_p1, draw_p2 = p1, p2
            
            # Offset (khoảng cách đẩy ra) = 30px * Scale
            draw_dimension_line(canvas, draw_p1, draw_p2, mm_val, GLOBAL_SCALE, offset=30*GLOBAL_SCALE)

    # 6. Save Image
    cv2.imwrite(str(OUTPUT_IMAGE), canvas)
    print(f"✅ Đã lưu ảnh tại: {OUTPUT_IMAGE}")

if __name__ == "__main__":
    main()