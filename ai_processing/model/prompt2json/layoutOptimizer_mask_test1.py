import json
import random
from PIL import Image
import numpy as np
from typing import Dict, List, Tuple, Set
from .room_completer import ensure_complete_room_structure

# Định nghĩa các hằng số
ROOM_SIZE_MAPPING = {
    "LivingRoom": "XL",
    "MasterRoom": "L",
    "Kitchen": "M",
    "Bathroom": "M",
    "DiningRoom": "M",
    "CommonRoom": "M",
    "SecondRoom": "M",
    "ChildRoom": "S",
    "StudyRoom": "M",
    "GuestRoom": "M",
    "Balcony": "M",
    "Entrance": "XS",
    "Storage": "S"
}

# Định nghĩa các vị trí có thể có
LOCATIONS = ["north", "northwest", "west", "southwest", "south", "southeast", "east", "northeast", "center"]

# Định nghĩa các vị trí liền kề
ADJACENT_LOCATIONS = {
    "north": ["northwest", "northeast", "center"],
    "northwest": ["north", "west", "center"],
    "west": ["northwest", "southwest", "center"],
    "southwest": ["west", "south", "center"],
    "south": ["southwest", "southeast", "center"],
    "southeast": ["south", "east", "center"],
    "east": ["northeast", "southeast", "center"],
    "northeast": ["north", "east", "center"],
    "center": ["north", "northwest", "west", "southwest", "south", "southeast", "east", "northeast"]
}

def analyze_mask(mask_path: str) -> Dict[str, float]:
    """
    Phân tích mask để xác định các cạnh nhà và hướng có thể bố trí phòng.
    Phương pháp cải tiến để phát hiện các phần nhô ra, thụt vào của hình dạng phức tạp.
    
    Args:
        mask_path: Đường dẫn đến file mask
        
    Returns:
        Dict[str, float]: Từ điển chứa tỷ lệ diện tích của mỗi hướng
    """
    try:
        # Mở và chuyển đổi mask thành mảng numpy
        mask = Image.open(mask_path).convert('L')
        mask_array = np.array(mask)
        
        # Kích thước của mask
        height, width = mask_array.shape
        
        # Tạo mask nhị phân (0 và 1) từ ảnh xám
        binary_mask = (mask_array < 128).astype(np.uint8)
        
        # Tìm contour (đường viền) của mask
        # Sử dụng phương pháp phân tích hình dạng thay vì chỉ chia đều
        
        # Tính trọng tâm (centroid) của mask
        y_indices, x_indices = np.where(binary_mask > 0)
        if len(y_indices) == 0 or len(x_indices) == 0:
            # Nếu không có pixel đen nào, trả về giá trị mặc định
            return {loc: 1/9 for loc in LOCATIONS}
            
        centroid_y = np.mean(y_indices)
        centroid_x = np.mean(x_indices)
        
        # Chia mask thành 9 phần dựa trên trọng tâm thay vì chia đều
        # Điều này giúp xử lý tốt hơn các hình dạng không đều
        
        # Tính toán diện tích đen trong mỗi phần
        location_areas = {}
        
        # Tính khoảng cách từ trọng tâm đến các cạnh
        dist_to_top = centroid_y
        dist_to_bottom = height - centroid_y
        dist_to_left = centroid_x
        dist_to_right = width - centroid_x
        
        # Điều chỉnh kích thước các phần dựa trên hình dạng thực tế
        # Thay vì chia đều 1/3, chúng ta sẽ điều chỉnh dựa trên hình dạng
        h_top = int(centroid_y * 0.7)  # 70% khoảng cách từ trọng tâm đến cạnh trên
        h_bottom = int(height - (height - centroid_y) * 0.7)  # 70% khoảng cách từ trọng tâm đến cạnh dưới
        w_left = int(centroid_x * 0.7)  # 70% khoảng cách từ trọng tâm đến cạnh trái
        w_right = int(width - (width - centroid_x) * 0.7)  # 70% khoảng cách từ trọng tâm đến cạnh phải
        
        # Tính diện tích các phần
        # North
        north_area = np.sum(binary_mask[:h_top, w_left:w_right])
        location_areas["north"] = north_area
        
        # Northwest
        northwest_area = np.sum(binary_mask[:h_top, :w_left])
        location_areas["northwest"] = northwest_area
        
        # West
        west_area = np.sum(binary_mask[h_top:h_bottom, :w_left])
        location_areas["west"] = west_area
        
        # Southwest
        southwest_area = np.sum(binary_mask[h_bottom:, :w_left])
        location_areas["southwest"] = southwest_area
        
        # South
        south_area = np.sum(binary_mask[h_bottom:, w_left:w_right])
        location_areas["south"] = south_area
        
        # Southeast
        southeast_area = np.sum(binary_mask[h_bottom:, w_right:])
        location_areas["southeast"] = southeast_area
        
        # East
        east_area = np.sum(binary_mask[h_top:h_bottom, w_right:])
        location_areas["east"] = east_area
        
        # Northeast
        northeast_area = np.sum(binary_mask[:h_top, w_right:])
        location_areas["northeast"] = northeast_area
        
        # Center
        center_area = np.sum(binary_mask[h_top:h_bottom, w_left:w_right])
        location_areas["center"] = center_area
        
        # Phân tích thêm các phần nhô ra, thụt vào
        # Tính độ lệch chuẩn của khoảng cách từ trọng tâm đến các điểm biên
        # Điều này giúp phát hiện các phần nhô ra, thụt vào
        
        # Tính tổng diện tích
        total_area = sum(location_areas.values())
        if total_area == 0:
            return {loc: 1/9 for loc in LOCATIONS}
            
        # Chuẩn hóa diện tích thành tỷ lệ
        location_ratios = {loc: area / total_area for loc, area in location_areas.items()}
        
        # Phân tích hình dạng để điều chỉnh tỷ lệ
        # Tính toán độ phức tạp của hình dạng (complexity)
        perimeter = 0
        for y in range(1, height-1):
            for x in range(1, width-1):
                if binary_mask[y, x] == 1:
                    # Kiểm tra xem pixel này có phải là biên không
                    if (binary_mask[y-1, x] == 0 or binary_mask[y+1, x] == 0 or 
                        binary_mask[y, x-1] == 0 or binary_mask[y, x+1] == 0):
                        perimeter += 1
        
        # Tính chỉ số phức tạp (complexity index)
        area = np.sum(binary_mask)
        if area > 0:
            complexity = perimeter / (2 * np.sqrt(np.pi * area))
            
            # Điều chỉnh tỷ lệ dựa trên độ phức tạp
            # Nếu hình dạng phức tạp (nhiều phần nhô ra, thụt vào), tăng tỷ trọng cho các vị trí có diện tích lớn
            if complexity > 1.2:  # Ngưỡng phức tạp
                # Tăng tỷ trọng cho các vị trí có diện tích lớn
                max_ratio = max(location_ratios.values())
                for loc in location_ratios:
                    if location_ratios[loc] > 0.7 * max_ratio:
                        location_ratios[loc] *= 1.2
                
                # Chuẩn hóa lại tỷ lệ
                total_ratio = sum(location_ratios.values())
                location_ratios = {loc: ratio / total_ratio for loc, ratio in location_ratios.items()}
        
        return location_ratios
    except Exception as e:
        print(f"Lỗi khi phân tích mask: {e}")
        # Trả về giá trị mặc định nếu có lỗi
        return {loc: 1/9 for loc in LOCATIONS}

def assign_room_sizes(rooms: List[Dict]) -> List[Dict]:
    """
    Gán kích thước cho các phòng dựa trên loại phòng
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        List[Dict]: Danh sách các phòng đã được gán kích thước
    """
    for room in rooms:
        room_type = room["name"].split("_")[0]  # Lấy phần tên trước dấu "_" nếu có
        if room_type in ROOM_SIZE_MAPPING:
            room["size"] = ROOM_SIZE_MAPPING[room_type]
        else:
            # Nếu không có trong mapping, gán kích thước mặc định là M
            room["size"] = "M"
    
    return rooms

def assign_room_locations(rooms: List[Dict], location_ratios: Dict[str, float]) -> List[Dict]:
    """
    Gán vị trí cho các phòng dựa trên tỷ lệ diện tích của mỗi hướng
    
    Args:
        rooms: Danh sách các phòng
        location_ratios: Tỷ lệ diện tích của mỗi hướng
        
    Returns:
        List[Dict]: Danh sách các phòng đã được gán vị trí
    """
    # Sắp xếp các vị trí theo tỷ lệ diện tích giảm dần
    sorted_locations = sorted(location_ratios.items(), key=lambda x: x[1], reverse=True)
    
    # Sắp xếp các phòng theo kích thước giảm dần
    size_order = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
    sorted_rooms = sorted(rooms, key=lambda x: size_order.get(x.get("size", "M"), 2), reverse=True)
    
    # Gán vị trí cho các phòng
    assigned_locations = set()
    
    # Đảm bảo LivingRoom luôn ở center nếu có
    for room in sorted_rooms:
        if "LivingRoom" in room["name"]:
            room["location"] = "center"
            assigned_locations.add("center")
            break
    
    # Gán vị trí cho các phòng còn lại
    for room in sorted_rooms:
        if "location" in room and room["location"] != "Unknown":
            # Nếu phòng đã có vị trí, thêm vào danh sách đã gán
            assigned_locations.add(room["location"])
            continue
        
        # Tìm vị trí phù hợp cho phòng
        for location, _ in sorted_locations:
            if location not in assigned_locations:
                room["location"] = location
                assigned_locations.add(location)
                break
        
        # Nếu không tìm được vị trí phù hợp, gán vị trí ngẫu nhiên
        if "location" not in room or room["location"] == "Unknown":
            available_locations = [loc for loc in LOCATIONS if loc not in assigned_locations]
            if available_locations:
                room["location"] = random.choice(available_locations)
                assigned_locations.add(room["location"])
            else:
                # Nếu tất cả các vị trí đã được gán, chọn vị trí có tỷ lệ diện tích lớn nhất
                # Nhưng không trùng với phòng cùng loại
                room_type = room["name"].split("_")[0]
                similar_rooms = [r for r in rooms if r["name"].split("_")[0] == room_type and r != room and "location" in r]
                similar_locations = [r["location"] for r in similar_rooms]
                
                for location, _ in sorted_locations:
                    if location not in similar_locations:
                        room["location"] = location
                        break
                else:
                    # Nếu không tìm được vị trí khác, chọn vị trí ngẫu nhiên
                    room["location"] = random.choice(LOCATIONS)
    
    return sorted_rooms

def create_room_links(rooms: List[Dict]) -> List[Dict]:
    """
    Tạo liên kết giữa các phòng một cách thông minh dựa trên vị trí liền kề.
    """
    room_dict = {room["name"]: room for room in rooms}
    
    # Tìm LivingRoom làm trung tâm
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    if not living_room and rooms:
        living_room = rooms[0]

    # 1. Khởi tạo liên kết cơ bản: Mọi phòng đều trống và sẽ được xử lý
    for room in rooms:
        room["link"] = []

    # 2. Liên kết mọi thứ với LivingRoom (nếu có)
    if living_room:
        living_room_links = [r["name"] for r in rooms if r["name"] != living_room["name"]]
        living_room["link"] = [living_room_links]
        # Các phòng khác cũng liên kết ngược lại với LivingRoom
        for room in rooms:
            if room["name"] != living_room["name"]:
                room["link"] = [[living_room["name"]]]

    # 3. Tạo liên kết dựa trên vị trí liền kề một cách hợp lý
    for room in rooms:
        if room.get("location") not in ADJACENT_LOCATIONS:
            continue

        adjacent_locations = ADJACENT_LOCATIONS[room["location"]]
        potential_links = []
        for other_room in rooms:
            if room["name"] == other_room["name"]:
                continue
            if other_room.get("location") in adjacent_locations:
                potential_links.append(other_room)

        # Ưu tiên liên kết Balcony với phòng ngủ hoặc phòng khách
        # LOGIC MỚI: Balcony chỉ cần liên kết tối thiểu với 1 phòng trong số: LivingRoom, MasterRoom, SecondRoom
        if "Balcony" in room["name"]:
            # Tìm tất cả các phòng ưu tiên (không cần liền kề)
            all_priority_rooms = [r for r in rooms if any(pr in r["name"] for pr in ["MasterRoom", "SecondRoom", "LivingRoom"]) and r["name"] != room["name"]]
            
            # Ưu tiên các phòng liền kề trước
            priority_rooms_adjacent = [p for p in potential_links if any(pr in p["name"] for pr in ["MasterRoom", "SecondRoom", "LivingRoom"])]
            
            if priority_rooms_adjacent:
                # Liên kết với các phòng ưu tiên liền kề
                for pr in priority_rooms_adjacent:
                    if pr["name"] not in room["link"][0]:
                        room["link"][0].append(pr["name"])
                    if pr.get("link") and room["name"] not in pr["link"][0]:
                        pr["link"][0].append(room["name"])
            elif all_priority_rooms:
                # Nếu không có phòng ưu tiên nào liền kề, chọn 1 phòng ưu tiên bất kỳ
                selected_room = all_priority_rooms[0]  # Chọn phòng đầu tiên
                if selected_room["name"] not in room["link"][0]:
                    room["link"][0].append(selected_room["name"])
                if selected_room.get("link") and room["name"] not in selected_room["link"][0]:
                    selected_room["link"][0].append(room["name"])

        else:
            # Logic cho các phòng khác: liên kết với tất cả các phòng liền kề
            for other in potential_links:
                # Bỏ qua LivingRoom vì đã liên kết ở bước 2
                if living_room and other["name"] == living_room["name"]:
                    continue
                if other["name"] not in room["link"][0]:
                    room["link"][0].append(other["name"])

    # 4. Kiểm tra cuối cùng: Đảm bảo mọi Balcony đều có ít nhất một liên kết với phòng ưu tiên
    for room in rooms:
        if "Balcony" in room["name"]:
            # Kiểm tra xem balcony đã có liên kết với phòng ưu tiên chưa
            priority_links = [link for link in room["link"][0] if any(pr in link for pr in ["MasterRoom", "SecondRoom", "LivingRoom"])]
            
            # Nếu chưa có liên kết với phòng ưu tiên nào, tạo liên kết với phòng ưu tiên đầu tiên có sẵn
            if not priority_links:
                all_priority_rooms = [r for r in rooms if any(pr in r["name"] for pr in ["MasterRoom", "SecondRoom", "LivingRoom"]) and r["name"] != room["name"]]
                if all_priority_rooms:
                    selected_room = all_priority_rooms[0]
                    if selected_room["name"] not in room["link"][0]:
                        room["link"][0].append(selected_room["name"])
                    if selected_room.get("link") and room["name"] not in selected_room["link"][0]:
                        selected_room["link"][0].append(room["name"])
    
    return rooms

def optimize_layout(json_data: Dict, mask_path: str = None) -> Dict:
    """
    Tối ưu hóa bố cục bằng cách gán kích thước, vị trí và liên kết cho các phòng
    
    Args:
        json_data: Dữ liệu JSON chứa thông tin về các phòng
        mask_path: Đường dẫn đến file mask
        
    Returns:
        Dict: Dữ liệu JSON đã được tối ưu hóa
    """
    # Phân tích mask nếu có
    location_ratios = {}
    if mask_path:
        location_ratios = analyze_mask(mask_path)
    else:
        # Nếu không có mask, sử dụng tỷ lệ mặc định
        location_ratios = {loc: 1/9 for loc in LOCATIONS}
    
    # Tạo danh sách các phòng
    rooms = []
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            room = room_data["rooms"][i]
            rooms.append(room)
    
    # Gán kích thước cho các phòng
    rooms = assign_room_sizes(rooms)
    
    # Gán vị trí cho các phòng
    rooms = assign_room_locations(rooms, location_ratios)
    
    # Tạo liên kết giữa các phòng
    rooms = create_room_links(rooms)
    
    # Cập nhật lại json_data
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            for room in rooms:
                if room["name"] == room_data["rooms"][i]["name"]:
                    room_data["rooms"][i] = room
                    break
    
    # Bổ sung thông tin đầy đủ cho tất cả loại phòng
    complete_json = ensure_complete_room_structure(json_data)
    
    return complete_json

def process_simple_input(input_text: str, mask_path: str = None) -> Dict:
    """
    Xử lý input đơn giản và tạo JSON hoàn chỉnh
    
    Args:
        input_text: Văn bản đầu vào đơn giản, ví dụ: "1 living room, 1 master room, 1 kitchen, 1 study room"
        mask_path: Đường dẫn đến file mask
        
    Returns:
        Dict: Dữ liệu JSON hoàn chỉnh
    """
    # Phân tích input đơn giản
    rooms = []
    room_counts = {}  # Đếm số lượng phòng mỗi loại
    
    for item in input_text.split(','):
        item = item.strip().lower()
        
        # Bỏ qua các mục rỗng do dấu phẩy thừa
        if not item:
            continue
        
        # Tìm số lượng
        num = 1
        num_match = [c for c in item if c.isdigit()]
        if num_match:
            num = int(''.join(num_match))
        
        # Tìm loại phòng
        room_type = item.replace(str(num), '').strip()
        
        # Chuẩn hóa tên phòng
        if "living" in room_type:
            room_type = "LivingRoom"
        elif "master" in room_type:
            room_type = "MasterRoom"
        elif "kitchen" in room_type:
            room_type = "Kitchen"
        elif "bath" in room_type:
            room_type = "Bathroom"
        elif "dining" in room_type:
            room_type = "DiningRoom"
        elif "common" in room_type:
            room_type = "CommonRoom"
        elif "second" in room_type:
            room_type = "SecondRoom"
        elif "child" in room_type:
            room_type = "ChildRoom"
        elif "study" in room_type:
            room_type = "StudyRoom"
        elif "guest" in room_type:
            room_type = "GuestRoom"
        elif "balcony" in room_type:
            room_type = "Balcony"
        elif "entrance" in room_type:
            room_type = "Entrance"
        elif "storage" in room_type:
            room_type = "Storage"
        else:
            # Nếu không khớp với bất kỳ loại phòng nào, sử dụng tên gốc
            room_type = room_type.title().replace(' ', '')
        
        # Thêm phòng vào danh sách
        rooms.append({
            "name": room_type,
            "num": num
        })
        
        # Cập nhật số lượng phòng mỗi loại
        if room_type not in room_counts:
            room_counts[room_type] = 0
        room_counts[room_type] += num
    
    # Tạo JSON ban đầu
    json_data = {}
    for room in rooms:
        room_type = room["name"]
        room_list = []
        
        for i in range(room["num"]):
            # Nếu có nhiều hơn 1 phòng cùng loại, thêm số thứ tự vào tên
            if room_counts[room_type] > 1:
                room_name = f"{room_type}_{i+1}"
            else:
                room_name = room_type
                
            room_list.append({
                "name": room_name,
                "link": [],
                "location": "Unknown",
                "size": "Unknown"
            })
        
        json_data[room_type] = {
            "num": room["num"],
            "rooms": room_list
        }
    
    # Tối ưu hóa bố cục
    optimized_json = optimize_layout(json_data, mask_path)
    
    return optimized_json