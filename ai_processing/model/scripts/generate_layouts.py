"""
Script để tạo 5 layout JSON khác nhau với định dạng đúng
Đảm bảo LivingRoom luôn ở vị trí "center" và các phòng khác được bố trí ngẫu nhiên
Sử dụng logic từ module layout_optimizer và phân tích mask
Có hỗ trợ cố định SEED để tái lập kết quả.
"""

import json
import random
import os
import numpy as np
import sys
import re
import argparse
from collections import OrderedDict
from pathlib import Path

# Thêm đường dẫn để import các module từ layout_optimizer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import các module từ layout_optimizer
# Lưu ý: Cần đảm bảo các module này tồn tại trong dự án của bạn
try:
    from prompt2json.layout_optimizer.config import LOCATIONS, ROOM_SIZE_MAPPING, ADJACENT_LOCATIONS
    from prompt2json.layout_optimizer.utils import extract_room_type
    from prompt2json.layout_optimizer.linking import create_links, get_max_connections, sort_rooms_by_priority
    from prompt2json.layout_optimizer.mask_analysis import analyze_mask
    from prompt2json.room_completer import ensure_complete_room_structure
except ImportError:
    # Fallback cơ bản nếu không import được (để script không crash ngay lập tức khi test độc lập)
    print("Warning: Không thể import đầy đủ các module từ prompt2json. Sử dụng cấu hình mặc định.")
    LOCATIONS = ["center", "top", "bottom", "left", "right", "top-left", "top-right", "bottom-left", "bottom-right"]
    ROOM_SIZE_MAPPING = {}
    ADJACENT_LOCATIONS = {k: [] for k in LOCATIONS}
    def extract_room_type(name): return name.split('_')[0]
    def sort_rooms_by_priority(rooms): return rooms
    def analyze_mask(path): return None
    def ensure_complete_room_structure(data): return data

# Định nghĩa đường dẫn
MODEL_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = MODEL_DIR / "source"
MASK_DIR = SOURCE_DIR / "mask"
TEXT_INPUT_DIR = SOURCE_DIR / "text_input"
NEW_TEXT_DIR = SOURCE_DIR / "new_text"

# Danh sách đầy đủ tất cả các loại phòng có thể có (theo thứ tự cố định)
ALL_ROOM_TYPES = [
    "LivingRoom",
    "MasterRoom", 
    "Kitchen",
    "Bathroom",
    "DiningRoom",
    "ChildRoom",
    "StudyRoom",
    "SecondRoom",
    "GuestRoom",
    "Balcony",
    "Entrance",
    "Storage"
]

def parse_room_requirements(text):
    """
    Phân tích yêu cầu phòng từ text đầu vào.
    Nâng cấp: Regex linh hoạt hơn và mapping từ khóa mở rộng.
    """
    if not text:
        return []

    text_lower = text.lower()
    
    # Mapping các từ khóa biến thể sang tên chuẩn
    # Threshold phát hiện: Dựa trên sự xuất hiện của từ khóa
    keyword_map = {
        'living': 'LivingRoom', 'lounge': 'LivingRoom', 'salon': 'LivingRoom',
        'master': 'MasterRoom', 'main bed': 'MasterRoom',
        'kitchen': 'Kitchen', 'cooking': 'Kitchen',
        'bath': 'Bathroom', 'restroom': 'Bathroom', 'wc': 'Bathroom', 'toilet': 'Bathroom',
        'dining': 'DiningRoom',
        'child': 'ChildRoom', 'kid': 'ChildRoom', 'baby': 'ChildRoom',
        'study': 'StudyRoom', 'office': 'StudyRoom', 'work': 'StudyRoom',
        'second': 'SecondRoom', 'bedroom': 'SecondRoom', 'bed room': 'SecondRoom', # Mặc định bedroom chung chung là SecondRoom
        'guest': 'GuestRoom',
        'balcony': 'Balcony', 'terrace': 'Balcony', 'loggia': 'Balcony',
        'entrance': 'Entrance', 'entry': 'Entrance', 'foyer': 'Entrance',
        'storage': 'Storage', 'store': 'Storage', 'pantry': 'Storage'
    }

    # Regex bắt định dạng: Số lượng + (khoảng trắng) + Tên phòng
    # Ví dụ: "1 living room", "2 bathrooms", "1 master"
    pattern = r'(\d+)\s+([a-zA-Z\s]+)'
    matches = re.findall(pattern, text_lower)
    
    rooms = []
    
    # Xử lý các match tìm được
    for count_str, raw_name in matches:
        try:
            count = int(count_str)
        except ValueError:
            continue
            
        clean_name = raw_name.strip()
        detected_type = None
        
        # Tìm loại phòng dựa trên keyword
        for key, standard_type in keyword_map.items():
            if key in clean_name:
                # Ưu tiên: Nếu đã là SecondRoom nhưng có từ 'master' thì đổi lại thành Master
                if standard_type == 'SecondRoom' and 'master' in clean_name:
                    detected_type = 'MasterRoom'
                elif detected_type is None: 
                     detected_type = standard_type
                # Nếu tìm thấy keyword cụ thể hơn (ví dụ 'master' trong 'master bedroom'), break để lấy nó
                if standard_type != 'SecondRoom':
                    detected_type = standard_type
                    break
        
        if detected_type:
            # Thêm phòng vào danh sách
            for i in range(count):
                # Tạo tên unique nếu có > 1 phòng cùng loại
                if count > 1:
                    room_name = f"{detected_type}_{i+1}"
                else:
                    room_name = detected_type
                
                # Xác định kích thước
                size = ROOM_SIZE_MAPPING.get(detected_type, "M")
                rooms.append({"name": room_name, "size": size})

    return rooms

def generate_layout(rooms, mask_path=None, seed=None):
    """
    Tạo một layout với LivingRoom ở center và các phòng khác ngẫu nhiên.
    Sử dụng seed để đảm bảo tính tất định (deterministic).
    """
    # --- THIẾT LẬP SEED ---
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
    
    # Phân tích mask nếu có
    location_features = None
    if mask_path and os.path.exists(mask_path):
        try:
            location_features = analyze_mask(mask_path)
        except Exception as e:
            # Chỉ in lỗi nhẹ, không dừng chương trình
            print(f"[Warn] Lỗi khi phân tích mask: {e}")
    
    # --- LOGIC BỐ TRÍ PHÒNG ---
    
    # 1. Chuẩn bị vị trí
    available_locations = list(LOCATIONS) # Copy list gốc
    if "center" in available_locations:
        available_locations.remove("center")  # Dành riêng center cho LivingRoom
    
    # Xáo trộn vị trí dựa trên seed hiện tại
    random.shuffle(available_locations)
    
    # 2. Gán vị trí
    room_locations = {}
    location_index = 0
    
    # Tách LivingRoom ra xử lý riêng để đảm bảo ưu tiên
    living_rooms = [r for r in rooms if extract_room_type(r["name"]) == "LivingRoom"]
    other_rooms = [r for r in rooms if extract_room_type(r["name"]) != "LivingRoom"]
    
    # Gán LivingRoom vào Center
    for room in living_rooms:
        room_locations[room["name"]] = "center"
        # Nếu có > 1 living room (hiếm), các living room phụ sẽ bị đẩy vào danh sách other
        # Logic hiện tại chỉ hỗ trợ 1 center, nên các living room thừa sẽ xử lý như phòng thường (nếu logic cho phép)
    
    # Gán các phòng còn lại
    for room in other_rooms:
        if location_index < len(available_locations):
            room_locations[room["name"]] = available_locations[location_index]
            location_index += 1
        else:
            # Hết vị trí đẹp -> Chọn ngẫu nhiên (trừ center)
            # Dùng random.choice cũng sẽ tuân theo seed
            room_locations[room["name"]] = random.choice(available_locations)
    
    # Cập nhật thông tin vị trí vào dict rooms gốc
    for room in rooms:
        # Fallback nếu phòng chưa có location (trường hợp living room thừa chẳng hạn)
        if room["name"] not in room_locations:
             room_locations[room["name"]] = random.choice(available_locations)
        room["location"] = room_locations[room["name"]]
    
    # 3. Sắp xếp và Tạo liên kết (Linking)
    sorted_rooms = sort_rooms_by_priority(rooms)
    
    room_links = {}
    for room in rooms:
        links = []
        for other_room in rooms:
            if room["name"] != other_room["name"]:
                # Logic liên kết: Chỉ nối nếu vị trí nằm trong danh sách kề (ADJACENT_LOCATIONS)
                # Cần đảm bảo ADJACENT_LOCATIONS được import đúng
                current_loc = room["location"]
                other_loc = other_room["location"]
                
                valid_adjacents = ADJACENT_LOCATIONS.get(current_loc, [])
                if other_loc in valid_adjacents:
                    links.append(other_room["name"])
        room_links[room["name"]] = links
    
    # 4. Đóng gói kết quả JSON
    result = OrderedDict()
    
    # Khởi tạo khung rỗng cho tất cả loại phòng
    for room_type in ALL_ROOM_TYPES:
        result[room_type] = {
            "num": 0,
            "rooms": []
        }
    
    # Điền dữ liệu
    for room in rooms:
        room_type = extract_room_type(room["name"])
        # Fallback nếu room_type không nằm trong ALL_ROOM_TYPES (hiếm)
        if room_type not in result:
             result[room_type] = {"num": 0, "rooms": []}
             
        result[room_type]["num"] += 1
        
        room_info = {
            "name": room["name"],
            "link": room_links[room["name"]],
            "location": room_locations[room["name"]],
            "size": room["size"]
        }
        result[room_type]["rooms"].append(room_info)
    
    # Đảm bảo cấu trúc hoàn chỉnh (thêm các trường thiếu nếu cần)
    result = ensure_complete_room_structure(result)
    
    return result

def parse_args():
    parser = argparse.ArgumentParser(description='Tạo 5 layout JSON khác nhau dựa trên mask và text input')
    parser.add_argument('--mask', type=str, help='Đường dẫn tương đối đến file mask')
    parser.add_argument('--text', type=str, help='Đường dẫn tương đối đến file text input')
    parser.add_argument('--seed', type=int, default=None, help='Seed cố định để tái tạo kết quả (Optional)')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # --- CẤU HÌNH ĐƯỜNG DẪN ---
    if args.mask:
        mask_path = MODEL_DIR / args.mask
    else:
        # Fallback thông minh hơn: Tìm file mask mới nhất trong thư mục mask
        mask_files = list(MASK_DIR.glob("*.png"))
        if mask_files:
            mask_path = sorted(mask_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
        else:
            mask_path = MASK_DIR / "1.png" # Default cứng
    
    if args.text:
        text_file_path = MODEL_DIR / args.text
    else:
        # Fallback: Tìm file text input mới nhất
        text_files = list(TEXT_INPUT_DIR.glob("*.json"))
        if text_files:
            text_file_path = sorted(text_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
        else:
            print("Lỗi: Không tìm thấy file text input nào.")
            return

    output_dir = NEW_TEXT_DIR
    
    print(f"--- Generate Layouts ---")
    print(f"Mask: {mask_path}")
    print(f"Input: {text_file_path}")
    if args.seed is not None:
        print(f"Base Seed: {args.seed}")
    
    # --- ĐỌC INPUT ---
    try:
        with open(text_file_path, 'r', encoding='utf-8') as f:
            text_data = json.load(f)
        text_request = text_data.get("text", "")
        print(f"Text Request: {text_request}")
    except Exception as e:
        print(f"Lỗi đọc file text input: {e}")
        return

    # --- PHÂN TÍCH PHÒNG ---
    rooms = parse_room_requirements(text_request)
    print(f"Phát hiện: {len(rooms)} phòng.")
    for r in rooms:
        print(f" - {r['name']} ({r['size']})")
    
    # Kiểm tra file mask
    if not mask_path.exists():
        print(f"Cảnh báo: Không tìm thấy file mask tại {mask_path}. Bỏ qua phân tích mask.")
        mask_path = None
    
    # --- GENERATE LOOP ---
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sử dụng seed người dùng nhập hoặc seed ngẫu nhiên
    base_seed = args.seed if args.seed is not None else random.randint(1, 10000)
    
    for i in range(1, 6):
        # Tính toán seed cho từng biến thể để đảm bảo khác nhau nhưng tái tạo được
        # Variation seed = base + i
        current_variation_seed = base_seed + i
        
        layout = generate_layout(rooms, mask_path, seed=current_variation_seed)
        
        # Lưu layout vào file JSON
        output_file = output_dir / f"{i}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)
        
        print(f"Đã tạo: {output_file.name} (Seed: {current_variation_seed})")

if __name__ == "__main__":
    main()