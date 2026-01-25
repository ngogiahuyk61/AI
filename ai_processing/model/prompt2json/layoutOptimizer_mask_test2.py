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

# Định nghĩa độ ưu tiên kết nối (càng cao càng quan trọng)
CONNECTION_PRIORITY = {
    "LivingRoom": 10,  # Cao nhất - trung tâm của nhà
    "Kitchen": 5,     
    "Entrance": 7,     # Cao - lối vào chính
    "MasterRoom": 6,   # Trung bình cao
    "SecondRoom": 6,   # Trung bình cao
    "DiningRoom": 5,   # Trung bình
    "Bathroom": 4,     # Trung bình thấp - chỉ cần 1-2 kết nối
    "Balcony": 3,      # Thấp - chỉ cần kết nối với phòng chính
    "Storage": 4,      
    "StudyRoom": 4,    
    "GuestRoom": 4,    
    "ChildRoom": 4,    
    "CommonRoom": 5    
}

def analyze_mask(mask_path: str) -> Dict[str, Dict]:
    """
    Phân tích mask để xác định các cạnh nhà và hướng có thể bố trí phòng.
    Cải tiến: Phân tích chi tiết hơn về cấu trúc và hình dạng của căn nhà
    Trả về thông tin chi tiết về mỗi vị trí bao gồm:
    - area_ratio: Tỷ lệ diện tích
    - edge_ratio: Tỷ lệ cạnh ngoài (càng cao càng gần cạnh nhà)
    - connectivity: Khả năng kết nối với các vị trí khác
    - room_suitability: Độ phù hợp với các loại phòng
    """
    try:
        # Mở và chuyển đổi mask thành mảng numpy
        mask = Image.open(mask_path).convert('L')
        mask_array = np.array(mask)
        
        # Kích thước của mask
        height, width = mask_array.shape
        
        # Tạo mask nhị phân (0 và 1) từ ảnh xám
        binary_mask = (mask_array < 128).astype(np.uint8)
        
        # Tính trọng tâm (centroid) của mask
        y_indices, x_indices = np.where(binary_mask > 0)
        if len(y_indices) == 0 or len(x_indices) == 0:
            return {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                         "room_suitability": {}} for loc in LOCATIONS}
            
        centroid_y = np.mean(y_indices)
        centroid_x = np.mean(x_indices)
        
        # Chia mask thành 9 phần dựa trên trọng tâm
        h_top = int(centroid_y * 0.7)
        h_bottom = int(height - (height - centroid_y) * 0.7)
        w_left = int(centroid_x * 0.7)
        w_right = int(width - (width - centroid_x) * 0.7)
        
        # Tính diện tích các phần
        location_areas = {}
        location_masks = {}
        
        # Tạo mask cho từng vị trí
        location_masks["north"] = binary_mask[:h_top, w_left:w_right]
        location_masks["northwest"] = binary_mask[:h_top, :w_left]
        location_masks["west"] = binary_mask[h_top:h_bottom, :w_left]
        location_masks["southwest"] = binary_mask[h_bottom:, :w_left]
        location_masks["south"] = binary_mask[h_bottom:, w_left:w_right]
        location_masks["southeast"] = binary_mask[h_bottom:, w_right:]
        location_masks["east"] = binary_mask[h_top:h_bottom, w_right:]
        location_masks["northeast"] = binary_mask[:h_top, w_right:]
        location_masks["center"] = binary_mask[h_top:h_bottom, w_left:w_right]
        
        # Tính diện tích từng vị trí
        for loc, loc_mask in location_masks.items():
            location_areas[loc] = np.sum(loc_mask)
        
        # Tính tổng diện tích
        total_area = sum(location_areas.values())
        if total_area == 0:
            return {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                         "room_suitability": {}} for loc in LOCATIONS}
        
        # Chuẩn hóa diện tích thành tỷ lệ
        area_ratios = {loc: area / total_area for loc, area in location_areas.items()}
        
        # Tính tỷ lệ cạnh ngoài cho mỗi vị trí
        edge_ratios = {}
        for loc, loc_mask in location_masks.items():
            if loc_mask.size == 0 or np.sum(loc_mask) == 0:
                edge_ratios[loc] = 0
                continue
                
            # Tạo kernel để phát hiện cạnh
            from scipy import ndimage
            kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
            edges = ndimage.convolve(loc_mask, kernel, mode='constant', cval=0)
            # Đếm số pixel cạnh (pixel có giá trị 0 nhưng lân cận có pixel 1)
            edge_pixels = np.logical_and(loc_mask == 0, edges > 0).sum()
            
            # Tính tỷ lệ cạnh trên tổng số pixel
            if loc_mask.size > 0:
                edge_ratios[loc] = edge_pixels / loc_mask.size
            else:
                edge_ratios[loc] = 0
        
        # Chuẩn hóa edge_ratios
        max_edge_ratio = max(edge_ratios.values()) if edge_ratios else 1
        if max_edge_ratio > 0:
            edge_ratios = {loc: ratio / max_edge_ratio for loc, ratio in edge_ratios.items()}
        
        # Định nghĩa khả năng kết nối của mỗi vị trí
        connectivity = {
            "center": 1.0,      # Kết nối cao nhất
            "north": 0.8, "south": 0.8, "east": 0.8, "west": 0.8,  # Kết nối trung bình cao
            "northwest": 0.6, "northeast": 0.6, "southwest": 0.6, "southeast": 0.6  # Kết nối trung bình
        }
        
        # Định nghĩa độ phù hợp của từng loại phòng với từng vị trí
        room_suitability = {}
        for loc in LOCATIONS:
            room_suitability[loc] = {}
            
            # Phòng khách phù hợp với trung tâm
            if loc == "center":
                room_suitability[loc]["LivingRoom"] = 1.0
                room_suitability[loc]["DiningRoom"] = 0.8
            else:
                room_suitability[loc]["LivingRoom"] = 0.4
                
            # Phòng ngủ phù hợp với các góc và cạnh
            if loc in ["northwest", "northeast", "southwest", "southeast"]:
                room_suitability[loc]["MasterRoom"] = 0.9
                room_suitability[loc]["SecondRoom"] = 0.9
                room_suitability[loc]["ChildRoom"] = 0.8
                room_suitability[loc]["GuestRoom"] = 0.8
            elif loc in ["north", "south", "east", "west"]:
                room_suitability[loc]["MasterRoom"] = 0.7
                room_suitability[loc]["SecondRoom"] = 0.8
                room_suitability[loc]["ChildRoom"] = 0.7
                room_suitability[loc]["GuestRoom"] = 0.7
            else:
                room_suitability[loc]["MasterRoom"] = 0.3
                room_suitability[loc]["SecondRoom"] = 0.3
                room_suitability[loc]["ChildRoom"] = 0.3
                room_suitability[loc]["GuestRoom"] = 0.3
                
            # Nhà bếp phù hợp với các cạnh
            if loc in ["north", "south", "east", "west"]:
                room_suitability[loc]["Kitchen"] = 0.9
                room_suitability[loc]["DiningRoom"] = 0.8
            else:
                room_suitability[loc]["Kitchen"] = 0.5
                
            # Phòng tắm phù hợp với các góc
            if loc in ["northwest", "northeast", "southwest", "southeast"]:
                room_suitability[loc]["Bathroom"] = 0.9
            else:
                room_suitability[loc]["Bathroom"] = 0.6
                
            # Ban công phù hợp với các cạnh ngoài
            if loc in ["north", "south", "east", "west"]:
                room_suitability[loc]["Balcony"] = 0.9
            else:
                room_suitability[loc]["Balcony"] = 0.3
                
            # Lối vào phù hợp với các cạnh
            if loc in ["north", "south", "east", "west"]:
                room_suitability[loc]["Entrance"] = 0.9
            else:
                room_suitability[loc]["Entrance"] = 0.4
                
            # Kho phù hợp với các góc
            if loc in ["northwest", "northeast", "southwest", "southeast"]:
                room_suitability[loc]["Storage"] = 0.8
            else:
                room_suitability[loc]["Storage"] = 0.5
                
            # Phòng học/làm việc linh hoạt hơn
            room_suitability[loc]["StudyRoom"] = 0.7
        
        # Điều chỉnh độ phù hợp dựa trên tỷ lệ cạnh
        for loc in LOCATIONS:
            edge_factor = edge_ratios.get(loc, 0)
            # Phòng cần nhiều ánh sáng (ban công, phòng khách) phù hợp với vị trí có nhiều cạnh ngoài
            room_suitability[loc]["Balcony"] *= (0.5 + 0.5 * edge_factor)
            room_suitability[loc]["LivingRoom"] *= (0.7 + 0.3 * edge_factor)
            
            # Phòng riêng tư (phòng ngủ, phòng tắm) phù hợp với vị trí ít cạnh ngoài
            room_suitability[loc]["MasterRoom"] *= (1.0 - 0.3 * edge_factor)
            room_suitability[loc]["Bathroom"] *= (1.0 - 0.2 * edge_factor)
        
        # Tổng hợp kết quả
        result = {}
        for loc in LOCATIONS:
            result[loc] = {
                "area_ratio": area_ratios.get(loc, 0),
                "edge_ratio": edge_ratios.get(loc, 0),
                "connectivity": connectivity.get(loc, 0.5),
                "room_suitability": room_suitability.get(loc, {})
            }
        
        return result
    except Exception as e:
        print(f"Lỗi khi phân tích mask: {e}")
        return {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                     "room_suitability": {}} for loc in LOCATIONS}

def assign_room_sizes(rooms: List[Dict]) -> List[Dict]:
    """Gán kích thước cho các phòng dựa trên loại phòng"""
    for room in rooms:
        room_type = room["name"].split("_")[0]
        if room_type in ROOM_SIZE_MAPPING:
            room["size"] = ROOM_SIZE_MAPPING[room_type]
        else:
            room["size"] = "M"
    return rooms

def assign_room_locations(rooms: List[Dict], location_data: Dict[str, Dict]) -> List[Dict]:
    """
    Gán vị trí cho các phòng dựa trên phân tích chi tiết của mask và đặc điểm của từng loại phòng
    Sử dụng thông tin về độ phù hợp của từng loại phòng với từng vị trí
    """
    # Tạo bảng điểm cho mỗi cặp (phòng, vị trí)
    room_location_scores = {}
    
    # Sắp xếp các phòng theo độ ưu tiên kết nối và kích thước
    size_order = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
    
    def room_priority(room):
        room_type = room["name"].split("_")[0]
        connection_priority = CONNECTION_PRIORITY.get(room_type, 5)
        size_priority = size_order.get(room.get("size", "M"), 2)
        return connection_priority * 10 + size_priority  # Ưu tiên kết nối cao hơn kích thước
    
    sorted_rooms = sorted(rooms, key=room_priority, reverse=True)
    
    # Tính điểm cho mỗi cặp (phòng, vị trí)
    for room in sorted_rooms:
        room_type = room["name"].split("_")[0]
        room_location_scores[room["name"]] = {}
        
        for location, loc_data in location_data.items():
            # Điểm cơ bản dựa trên độ phù hợp của loại phòng với vị trí
            base_score = loc_data["room_suitability"].get(room_type, 0.5)
            
            # Điều chỉnh điểm dựa trên diện tích
            area_factor = loc_data["area_ratio"]
            
            # Điều chỉnh điểm dựa trên kích thước phòng và diện tích vị trí
            size_adjustment = 0
            if room.get("size") == "XL" and area_factor < 0.1:
                size_adjustment = -0.3  # Phòng lớn không phù hợp với vị trí nhỏ
            elif room.get("size") == "XS" and area_factor > 0.2:
                size_adjustment = -0.2  # Phòng nhỏ không cần vị trí lớn
                
            # Điều chỉnh điểm dựa trên khả năng kết nối
            connectivity_factor = loc_data["connectivity"]
            connectivity_importance = CONNECTION_PRIORITY.get(room_type, 5) / 10.0
            connectivity_adjustment = connectivity_factor * connectivity_importance
            
            # Tính điểm tổng hợp
            final_score = base_score + size_adjustment + connectivity_adjustment
            
            # Đảm bảo điểm nằm trong khoảng [0, 1]
            final_score = max(0, min(1, final_score))
            
            room_location_scores[room["name"]][location] = final_score
    
    # Gán vị trí cho các phòng
    assigned_locations = set()
    
    # Đảm bảo LivingRoom luôn ở center nếu có
    for room in sorted_rooms:
        if "LivingRoom" in room["name"]:
            room["location"] = "center"
            assigned_locations.add("center")
            break
    
    # Gán vị trí cho các phòng còn lại sử dụng thuật toán tham lam (greedy algorithm)
    for room in sorted_rooms:
        if "location" in room and room["location"] != "Unknown":
            assigned_locations.add(room["location"])
            continue
        
        # Sắp xếp các vị trí theo điểm giảm dần
        sorted_locations = sorted(
            [(loc, score) for loc, score in room_location_scores[room["name"]].items() if loc not in assigned_locations],
            key=lambda x: x[1],
            reverse=True
        )
        
        if sorted_locations:
            # Chọn vị trí có điểm cao nhất
            best_location, _ = sorted_locations[0]
            room["location"] = best_location
            assigned_locations.add(best_location)
        else:
            # Fallback: chọn vị trí ngẫu nhiên từ các vị trí còn lại
            available_locations = [loc for loc in LOCATIONS if loc not in assigned_locations]
            if available_locations:
                room["location"] = random.choice(available_locations)
                assigned_locations.add(room["location"])
            else:
                # Nếu tất cả vị trí đã được gán, chọn vị trí ngẫu nhiên
                room["location"] = random.choice(LOCATIONS)
    
    # Kiểm tra và điều chỉnh các vị trí không hợp lý
    for i, room1 in enumerate(sorted_rooms):
        room1_type = room1["name"].split("_")[0]
        
        # Kiểm tra các cặp phòng không nên ở cạnh nhau
        for j, room2 in enumerate(sorted_rooms):
            if i == j:
                continue
                
            room2_type = room2["name"].split("_")[0]
            
            # Kiểm tra các cặp phòng không nên ở cạnh nhau
            incompatible_pairs = [
                ("Bathroom", "Kitchen"),  # Phòng tắm không nên cạnh bếp
                ("Bathroom", "DiningRoom"),  # Phòng tắm không nên cạnh phòng ăn
            ]
            
            if (room1_type, room2_type) in incompatible_pairs or (room2_type, room1_type) in incompatible_pairs:
                # Nếu hai phòng không tương thích đang ở cạnh nhau
                if room1["location"] in ADJACENT_LOCATIONS[room2["location"]]:
                    # Tìm vị trí thay thế cho room1
                    for loc in LOCATIONS:
                        if loc not in assigned_locations and loc != room1["location"]:
                            assigned_locations.remove(room1["location"])
                            room1["location"] = loc
                            assigned_locations.add(loc)
                            break
    
    return sorted_rooms

def create_smart_room_links(rooms: List[Dict]) -> List[Dict]:
    """
    Tạo liên kết thông minh giữa các phòng dựa trên vị trí và quy tắc thiết kế
    Cải tiến: Sử dụng thuật toán đồ thị để tạo kết nối hợp lý
    """
    # Khởi tạo liên kết trống
    for room in rooms:
        room["link"] = [[]]
    
    # Tìm LivingRoom làm hub chính
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    
    # Định nghĩa số lượng kết nối tối đa cho mỗi loại phòng
    max_connections = {
        "LivingRoom": 5,    # Trung tâm kết nối
        "Kitchen": 3,       # Kết nối với phòng ăn và phòng khách
        "Entrance": 2,      # Lối vào chính
        "MasterRoom": 3,    # Phòng ngủ chính
        "SecondRoom": 2,    # Phòng ngủ phụ
        "Bathroom": 2,      # Phòng tắm
        "Balcony": 1,       # Ban công
        "Storage": 1,       # Kho
        "DiningRoom": 3,    # Phòng ăn
        "StudyRoom": 2,     # Phòng làm việc
        "GuestRoom": 2,     # Phòng khách
        "ChildRoom": 2,     # Phòng trẻ em
        "CommonRoom": 3     # Phòng sinh hoạt chung
    }
    
    # Định nghĩa các cặp phòng nên kết nối với nhau
    preferred_connections = {
        "LivingRoom": ["Kitchen", "DiningRoom", "Entrance", "MasterRoom", "Balcony"],
        "Kitchen": ["DiningRoom", "LivingRoom", "Storage"],
        "Entrance": ["LivingRoom", "CommonRoom"],
        "MasterRoom": ["Bathroom", "LivingRoom", "Balcony"],
        "SecondRoom": ["Bathroom", "LivingRoom"],
        "Bathroom": ["LivingRoom", "MasterRoom"],
        "Balcony": ["LivingRoom", "MasterRoom", "DiningRoom"],
        "Storage": ["LivingRoom"],
        "DiningRoom": ["Kitchen", "LivingRoom", "Balcony"],
        "StudyRoom": ["LivingRoom", "MasterRoom"],
        "GuestRoom": ["LivingRoom", "Bathroom"],
        "ChildRoom": ["LivingRoom", "Bathroom"],
        "CommonRoom": ["LivingRoom", "Kitchen", "Entrance"]
    }
    
    # Bước 1: Tạo kết nối dựa trên vị trí liền kề
    # Tạo từ điển ánh xạ từ vị trí đến phòng
    location_to_rooms = {}
    for room in rooms:
        location = room.get("location")
        if location not in location_to_rooms:
            location_to_rooms[location] = []
        location_to_rooms[location].append(room)
    
    # Kết nối các phòng ở vị trí liền kề
    for room in rooms:
        room_type = room["name"].split("_")[0]
        location = room.get("location")
        
        if not location or location not in ADJACENT_LOCATIONS:
            continue
            
        # Lấy danh sách vị trí liền kề
        adjacent_locations = ADJACENT_LOCATIONS[location]
        
        # Tìm các phòng ở vị trí liền kề
        for adj_location in adjacent_locations:
            if adj_location not in location_to_rooms:
                continue
                
            for adj_room in location_to_rooms[adj_location]:
                # Kiểm tra xem đã kết nối chưa
                if adj_room["name"] in room["link"][0] or room["name"] in adj_room["link"][0]:
                    continue
                    
                # Kiểm tra số lượng kết nối tối đa
                if len(room["link"][0]) >= max_connections.get(room_type, 2):
                    break
                    
                adj_room_type = adj_room["name"].split("_")[0]
                if len(adj_room["link"][0]) >= max_connections.get(adj_room_type, 2):
                    continue
                
                # Kiểm tra xem có phải là cặp phòng ưu tiên không
                is_preferred = False
                if room_type in preferred_connections and adj_room_type in preferred_connections[room_type]:
                    is_preferred = True
                elif adj_room_type in preferred_connections and room_type in preferred_connections[adj_room_type]:
                    is_preferred = True
                
                # Nếu là cặp phòng ưu tiên hoặc cả hai đều chưa có kết nối
                if is_preferred or (len(room["link"][0]) == 0 and len(adj_room["link"][0]) == 0):
                    room["link"][0].append(adj_room["name"])
                    adj_room["link"][0].append(room["name"])
    
    # Bước 2: Đảm bảo LivingRoom kết nối với các phòng quan trọng
    if living_room:
        for room_type in ["Kitchen", "Entrance", "DiningRoom"]:
            # Tìm phòng có loại tương ứng
            target_rooms = [r for r in rooms if room_type in r["name"] and r["name"] != living_room["name"]]
            
            for target_room in target_rooms:
                # Kiểm tra xem đã kết nối chưa
                if target_room["name"] in living_room["link"][0]:
                    continue
                    
                # Kiểm tra số lượng kết nối tối đa
                if len(living_room["link"][0]) >= max_connections.get("LivingRoom", 5):
                    break
                    
                if len(target_room["link"][0]) >= max_connections.get(room_type, 2):
                    continue
                    
                # Thêm kết nối
                living_room["link"][0].append(target_room["name"])
                target_room["link"][0].append(living_room["name"])
    
    # Bước 3: Xử lý đặc biệt cho các loại phòng cụ thể
    
    # Xử lý Bathroom: Kết nối với phòng ngủ gần nhất
    for room in rooms:
        if "Bathroom" in room["name"] and len(room["link"][0]) == 0:
            # Tìm phòng ngủ gần nhất
            bedroom_types = ["MasterRoom", "SecondRoom", "GuestRoom", "ChildRoom"]
            for bedroom_type in bedroom_types:
                bedrooms = [r for r in rooms if bedroom_type in r["name"]]
                for bedroom in bedrooms:
                    if len(bedroom["link"][0]) < max_connections.get(bedroom_type, 2):
                        room["link"][0].append(bedroom["name"])
                        bedroom["link"][0].append(room["name"])
                        break
                if room["link"][0]:
                    break
    
    # Xử lý Balcony: Kết nối với phòng khách hoặc phòng ngủ
    for room in rooms:
        if "Balcony" in room["name"] and len(room["link"][0]) == 0:
            # Ưu tiên kết nối với phòng khách hoặc phòng ngủ chính
            priority_rooms = [r for r in rooms if any(pr in r["name"] for pr in ["LivingRoom", "MasterRoom", "DiningRoom"])]
            
            for priority_room in priority_rooms:
                room_type = priority_room["name"].split("_")[0]
                if len(priority_room["link"][0]) < max_connections.get(room_type, 3):
                    room["link"][0].append(priority_room["name"])
                    priority_room["link"][0].append(room["name"])
                    break
    
    # Bước 4: Đảm bảo mọi phòng đều có ít nhất 1 kết nối
    for room in rooms:
        if len(room["link"][0]) == 0:
            # Tìm phòng phù hợp để kết nối
            best_candidate = None
            best_score = -1
            
            for other_room in rooms:
                if other_room["name"] == room["name"]:
                    continue
                    
                other_type = other_room["name"].split("_")[0]
                room_type = room["name"].split("_")[0]
                
                # Tính điểm phù hợp
                score = 0
                
                # Kiểm tra xem có phải là cặp phòng ưu tiên không
                if room_type in preferred_connections and other_type in preferred_connections[room_type]:
                    score += 3
                elif other_type in preferred_connections and room_type in preferred_connections[other_type]:
                    score += 3
                
                # Kiểm tra vị trí liền kề
                if room.get("location") in ADJACENT_LOCATIONS and other_room.get("location") in ADJACENT_LOCATIONS[room.get("location")]:
                    score += 2
                
                # Ưu tiên phòng có ít kết nối
                score -= len(other_room["link"][0]) * 0.5
                
                # Kiểm tra số lượng kết nối tối đa
                if len(other_room["link"][0]) >= max_connections.get(other_type, 2):
                    continue
                
                if score > best_score:
                    best_score = score
                    best_candidate = other_room
            
            # Thêm kết nối với ứng viên tốt nhất
            if best_candidate:
                room["link"][0].append(best_candidate["name"])
                best_candidate["link"][0].append(room["name"])
            elif living_room and len(living_room["link"][0]) < max_connections.get("LivingRoom", 5):
                # Kết nối với phòng khách nếu không tìm được ứng viên tốt
                room["link"][0].append(living_room["name"])
                living_room["link"][0].append(room["name"])
    
    # Bước 5: Kiểm tra và đảm bảo đồ thị kết nối là liên thông
    # Tạo đồ thị kết nối
    graph = {}
    for room in rooms:
        graph[room["name"]] = set(room["link"][0])
    
    # Kiểm tra tính liên thông bằng thuật toán DFS
    def dfs(node, visited):
        visited.add(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                dfs(neighbor, visited)
    
    # Bắt đầu DFS từ phòng đầu tiên
    visited = set()
    if rooms:
        dfs(rooms[0]["name"], visited)
    
    # Nếu đồ thị không liên thông, thêm các cạnh để làm cho nó liên thông
    if len(visited) < len(rooms):
        # Tìm các phòng chưa được thăm
        unvisited = [room["name"] for room in rooms if room["name"] not in visited]
        
        # Kết nối các phòng chưa thăm với phòng đã thăm
        for unvisited_name in unvisited:
            # Tìm phòng chưa thăm
            unvisited_room = next((r for r in rooms if r["name"] == unvisited_name), None)
            if not unvisited_room:
                continue
                
            # Tìm phòng đã thăm có ít kết nối nhất
            visited_rooms = [r for r in rooms if r["name"] in visited]
            visited_rooms.sort(key=lambda r: len(r["link"][0]))
            
            if visited_rooms:
                visited_room = visited_rooms[0]
                
                # Thêm kết nối
                unvisited_room["link"][0].append(visited_room["name"])
                visited_room["link"][0].append(unvisited_room["name"])
                
                # Cập nhật đồ thị và tập visited
                graph[unvisited_room["name"]].add(visited_room["name"])
                graph[visited_room["name"]].add(unvisited_room["name"])
                visited.add(unvisited_room["name"])
    
    return rooms


def apply_design_constraints(rooms: List[Dict]) -> List[Dict]:
    """
    Áp dụng các ràng buộc và quy tắc thiết kế để đảm bảo bố cục hợp lý
    """
    # Định nghĩa các cặp phòng không nên đặt cạnh nhau
    incompatible_rooms = {
        "Kitchen": ["Bathroom", "Storage"],
        "Bathroom": ["Kitchen", "DiningRoom"],
        "Storage": ["Balcony"],
        "MasterRoom": ["Kitchen", "DiningRoom"],
        "Entrance": ["Bathroom"]
    }
    
    # Định nghĩa các phòng nên đặt ở vị trí cạnh biên
    edge_preferred_rooms = ["Balcony", "Entrance", "Storage"]
    
    # Định nghĩa các phòng nên đặt ở vị trí trung tâm
    center_preferred_rooms = ["LivingRoom", "DiningRoom", "CommonRoom"]
    
    # Kiểm tra và điều chỉnh các kết nối không hợp lý
    for room in rooms:
        room_type = room["name"].split("_")[0]
        
        # Kiểm tra các kết nối không hợp lý
        if room_type in incompatible_rooms and "link" in room and room["link"]:
            incompatible_types = incompatible_rooms[room_type]
            
            # Lọc ra các kết nối không hợp lý
            for i, links in enumerate(room["link"]):
                filtered_links = []
                for linked_room in links:
                    linked_type = linked_room.split("_")[0]
                    if linked_type not in incompatible_types:
                        filtered_links.append(linked_room)
                room["link"][i] = filtered_links
    
    # Kiểm tra vị trí của các phòng và đánh dấu các vấn đề
    for room in rooms:
        room_type = room["name"].split("_")[0]
        location = room.get("location")
        
        # Đánh dấu các vấn đề về vị trí
        issues = []
        
        # Kiểm tra phòng ưu tiên đặt ở biên
        if room_type in edge_preferred_rooms and location in ["center"]:
            issues.append(f"{room_type} nên đặt ở vị trí cạnh biên")
        
        # Kiểm tra phòng ưu tiên đặt ở trung tâm
        if room_type in center_preferred_rooms and location in ["northwest", "northeast", "southwest", "southeast"]:
            issues.append(f"{room_type} nên đặt ở vị trí trung tâm")
        
        # Lưu các vấn đề vào phòng
        if issues:
            room["design_issues"] = issues
    
    return rooms

def validate_layout(rooms: List[Dict]) -> Dict:
    """
    Kiểm tra và đánh giá bố cục dựa trên các quy tắc thiết kế
    """
    validation_result = {
        "is_valid": True,
        "issues": [],
        "score": 10.0  # Điểm tối đa
    }
    
    # Kiểm tra các vấn đề thiết kế
    design_issues = []
    for room in rooms:
        if "design_issues" in room:
            for issue in room["design_issues"]:
                design_issues.append(f"{room['name']}: {issue}")
    
    # Kiểm tra tính liên thông của đồ thị kết nối
    graph = {}
    for room in rooms:
        graph[room["name"]] = set()
        if "link" in room and room["link"]:
            for links in room["link"]:
                for linked_room in links:
                    graph[room["name"]].add(linked_room)
    
    # Kiểm tra tính liên thông bằng DFS
    def dfs(node, visited):
        visited.add(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                dfs(neighbor, visited)
    
    visited = set()
    if rooms:
        dfs(rooms[0]["name"], visited)
    
    # Nếu không liên thông, thêm vấn đề
    if len(visited) < len(rooms):
        unvisited = [room["name"] for room in rooms if room["name"] not in visited]
        validation_result["issues"].append(f"Đồ thị kết nối không liên thông. Các phòng không kết nối: {', '.join(unvisited)}")
        validation_result["is_valid"] = False
        validation_result["score"] -= 3.0
    
    # Thêm các vấn đề thiết kế
    if design_issues:
        validation_result["issues"].extend(design_issues)
        validation_result["score"] -= len(design_issues) * 0.5
        if len(design_issues) > 5:
            validation_result["is_valid"] = False
    
    # Đảm bảo điểm không âm
    validation_result["score"] = max(0.0, validation_result["score"])
    
    return validation_result

def optimize_layout(json_data: Dict, mask_path: str = None) -> Dict:
    """Tối ưu hóa bố cục với logic cải tiến"""
    # Phân tích mask nếu có
    location_ratios = {}
    if mask_path:
        location_ratios = analyze_mask(mask_path)
    else:
        location_ratios = {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                         "room_suitability": {}} for loc in LOCATIONS}
    
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
    
    # Tạo liên kết thông minh giữa các phòng
    rooms = create_smart_room_links(rooms)
    
    # Áp dụng các ràng buộc và quy tắc thiết kế
    rooms = apply_design_constraints(rooms)
    
    # Kiểm tra và đánh giá bố cục
    validation = validate_layout(rooms)
    
    # Cập nhật lại json_data
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            for room in rooms:
                if room["name"] == room_data["rooms"][i]["name"]:
                    room_data["rooms"][i] = room
                    break
    
    # Bổ sung thông tin đầy đủ cho tất cả loại phòng
    complete_json = ensure_complete_room_structure(json_data)
    complete_json["validation"] = validation
    
    return complete_json

def process_simple_input(input_text: str, mask_path: str = None) -> Dict:
    """Xử lý input đơn giản và tạo JSON hoàn chỉnh"""
    # Phân tích input đơn giản
    rooms = []
    room_counts = {}
    
    for item in input_text.split(','):
        item = item.strip().lower()
        
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
            room_type = room_type.title().replace(' ', '')
        
        rooms.append({
            "name": room_type,
            "num": num
        })
        
        if room_type not in room_counts:
            room_counts[room_type] = 0
        room_counts[room_type] += num
    
    # Tạo JSON ban đầu
    json_data = {}
    for room in rooms:
        room_type = room["name"]
        room_list = []
        
        for i in range(room["num"]):
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
    
    # Bổ sung thông tin đầy đủ cho tất cả loại phòng
    complete_json = ensure_complete_room_structure(optimized_json)
    
    return complete_json
