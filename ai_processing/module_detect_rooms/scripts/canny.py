import cv2
import numpy as np
import json
import os
from collections import defaultdict

def get_building_outline(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _thresh, img_binary = cv2.threshold(gray, 254, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(img_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    all_points = np.concatenate(contours)
    return cv2.boundingRect(all_points)

def analyze_room_contour(cnt, room_type, room_type_count, room_id, color_bgr, building_rect):
    room_data = {}
    area = int(cv2.contourArea(cnt))
    x, y, w, h = cv2.boundingRect(cnt)
    
    M = cv2.moments(cnt)
    center = [int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])] if M["m00"] != 0 else [0, 0]

    epsilon = 0.02 * cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, epsilon, True)
    corners = approx.reshape(-1, 2).tolist()
    num_edges = len(corners)

    edges = []
    for j in range(num_edges):
        p1 = corners[j]
        p2 = corners[(j + 1) % num_edges]
        edges.append([p1[0], p1[1], p2[0], p2[1]])

    exterior_facing = []
    bx, by, bw, bh = building_rect
    
    buffer = 2
    if abs(y - by) <= buffer:
        exterior_facing.append("top")
    if abs(x - bx) <= buffer:
        exterior_facing.append("left")
    if abs((y + h) - (by + bh)) <= buffer:
        exterior_facing.append("bottom")
    if abs((x + w) - (bx + bw)) <= buffer:
        exterior_facing.append("right")

    room_data = {
        "id": room_id,
        "name": f"{room_type}_{room_type_count}",
        "color": color_bgr[::-1],
        "center": center,
        "snapped_corners": corners,
        "edges": edges,
        "bounding_box": [x, y, w, h],
        "area": area,
        "exterior_facing": exterior_facing,
        "num_edges": num_edges
    }
    
    return room_data

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUTS_DIR = os.path.join(MODULE_DIR, 'outputs')

INPUT_IMAGE_FILENAME = os.path.join(OUTPUTS_DIR, 'colored_floorplan.png')
OUTPUT_MASK_IMAGE = os.path.join(OUTPUTS_DIR, 'output_mask_white_background.png')
OUTPUT_JSON = os.path.join(OUTPUTS_DIR, 'all_rooms_data.json')

COLOR_TO_ROOM_MAP = {
    (208, 253, 255): "livingroom",
    (0, 165, 255): "master_room",
    (0, 215, 255): "common_room",
    (221, 160, 221): "storage",
    (210, 216, 173): "bathroom",
    (35, 142, 107): "balcony"
}

CREAM_COLOR_BGR = [208, 253, 255]

img = cv2.imread(INPUT_IMAGE_FILENAME)
if img is None:
    print(f"LỖI: Không thể tải ảnh từ '{INPUT_IMAGE_FILENAME}'. Vui lòng kiểm tra lại tên file.")
    exit()
print(f"Đã tải ảnh '{INPUT_IMAGE_FILENAME}' thành công.")


print(f"\nĐang thực hiện Tác vụ 1: Tạo ảnh mask '{OUTPUT_MASK_IMAGE}'...")

lower_bound_cream = np.array(CREAM_COLOR_BGR)
upper_bound_cream = np.array(CREAM_COLOR_BGR)

mask_kem = cv2.inRange(img, lower_bound_cream, upper_bound_cream)
mask_khac = cv2.bitwise_not(mask_kem)
white_image = np.full(img.shape, 255, dtype=np.uint8)
result_khac = cv2.bitwise_and(white_image, white_image, mask=mask_khac)
result_kem = cv2.bitwise_and(img, img, mask=mask_kem)
final_result = cv2.add(result_kem, result_khac)
cv2.imwrite(OUTPUT_MASK_IMAGE, final_result)
print(f"Đã lưu ảnh mask tại: {OUTPUT_MASK_IMAGE}")


print(f"\nĐang thực hiện Tác vụ 2: Phân tích ảnh và tạo '{OUTPUT_JSON}'...")

building_rect = get_building_outline(img)
if building_rect is None:
    print("LỖI: Không tìm thấy viền tòa nhà trong ảnh!")
    exit()

output_data = {
    "total_rooms": 0,
    "room_types": {},
    "rooms": []
}
room_types_counter = defaultdict(int)
global_room_id = 0

for color_bgr, room_type in COLOR_TO_ROOM_MAP.items():
    lower_bound = np.array(color_bgr)
    upper_bound = np.array(color_bgr)
    mask = cv2.inRange(img, lower_bound, upper_bound)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        continue

    for cnt in contours:
        if cv2.contourArea(cnt) < 100:
            continue
            
        room_types_counter[room_type] += 1
        current_room_count = room_types_counter[room_type]
        
        room_data = analyze_room_contour(
            cnt, 
            room_type, 
            current_room_count, 
            global_room_id, 
            color_bgr, 
            building_rect
        )
        
        output_data["rooms"].append(room_data)
        global_room_id += 1

output_data["total_rooms"] = global_room_id
output_data["room_types"] = dict(room_types_counter)

with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=4)

ROOM_DATA_JSON = os.path.join(os.path.dirname(OUTPUT_JSON), 'room_data.json')

if os.path.exists(ROOM_DATA_JSON):
    try:
        with open(ROOM_DATA_JSON, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        
        new_living_room = None
        for room in output_data['rooms']:
            if room['name'].startswith('livingroom'):
                new_living_room = room
                break
        
        if new_living_room:
            updated = False
            for i, room in enumerate(existing_data['rooms']):
                if room['name'].startswith('livingroom'):
                    new_living_room['id'] = room['id']
                    existing_data['rooms'][i] = new_living_room
                    updated = True
                    break
            
            if updated:
                with open(ROOM_DATA_JSON, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=4)
                print(f"\n--- Đã cập nhật living room trong {ROOM_DATA_JSON} ---")
            else:
                print("\n--- Cảnh báo: Không tìm thấy living room cũ để cập nhật ---")
        else:
            print("\n--- Cảnh báo: Không tìm thấy living room mới trong dữ liệu vừa tạo ---")
            
    except Exception as e:
        print(f"\n--- Lỗi khi cập nhật room_data.json: {str(e)} ---")
else:
    print(f"\n--- Cảnh báo: Không tìm thấy file {ROOM_DATA_JSON} để cập nhật ---")

print(f"\n--- Phân tích hoàn tất! ---")
print(f"Đã tìm thấy tổng cộng {global_room_id} phòng.")
print(f"Dữ liệu đã được lưu vào: {OUTPUT_JSON}")