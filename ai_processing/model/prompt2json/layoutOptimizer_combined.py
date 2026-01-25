import json
import random
from PIL import Image
import numpy as np
from typing import Dict, List, Tuple, Set
from .room_completer import ensure_complete_room_structure

random.seed(42)

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
    "Storage": "XS"
}

LOCATIONS = ["north", "northwest", "west", "southwest", "south", "southeast", "east", "northeast", "center"]

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

# Cụm hướng để cân bằng tải diện tích theo dải
SEGMENTS = {
    "east_vertical": ["northeast", "east", "southeast"],
}

CONNECTION_PRIORITY = {
    "LivingRoom": 10,  
    "Kitchen": 7,      
    "Entrance": 8,     
    "MasterRoom": 6,   
    "SecondRoom": 5,   
    "DiningRoom": 7,   
    "Bathroom": 4,     
    "Balcony": 3,      
    "Storage": 2,      
    "StudyRoom": 4,    
    "GuestRoom": 4,    
    "ChildRoom": 5,    
    "CommonRoom": 6    
}

INCOMPATIBLE_PAIRS = [
    ("Bathroom", "Kitchen"),      
    ("Bathroom", "DiningRoom"),   
    #("Storage", "LivingRoom"),    
    ("Storage", "DiningRoom")     
]

PREFERRED_PAIRS = [
    ("Kitchen", "DiningRoom"),   
    ("LivingRoom", "Entrance"),   
    ("MasterRoom", "Bathroom"),   
    ("Balcony", "LivingRoom"),    
    ("Balcony", "MasterRoom")     
]

def _load_and_process_mask(mask_path: str) -> Tuple[np.ndarray, int, int, float, float]:
    """Load mask và tính toán centroid"""
    mask = Image.open(mask_path).convert('L')
    mask_array = np.array(mask)
    height, width = mask_array.shape
    binary_mask = (mask_array < 128).astype(np.uint8)
    
    y_indices, x_indices = np.where(binary_mask > 0)
    if len(y_indices) == 0 or len(x_indices) == 0:
        return binary_mask, height, width, height/2, width/2
    
    centroid_y = np.mean(y_indices)
    centroid_x = np.mean(x_indices)
    return binary_mask, height, width, centroid_y, centroid_x

def _calculate_region_bounds(height: int, width: int, centroid_y: float, centroid_x: float) -> Tuple[int, int, int, int]:
    """Tính toán bounds cho 9 vùng với bounds checking"""
    h_top = max(1, min(height-2, int(centroid_y * 0.7)))
    h_bottom = max(h_top+1, min(height-1, int(height - (height - centroid_y) * 0.7)))
    w_left = max(1, min(width-2, int(centroid_x * 0.7)))
    w_right = max(w_left+1, min(width-1, int(width - (width - centroid_x) * 0.7)))
    return h_top, h_bottom, w_left, w_right

def _create_location_masks(binary_mask: np.ndarray, h_top: int, h_bottom: int, w_left: int, w_right: int) -> Dict[str, np.ndarray]:
    """Tạo mask cho từng vị trí"""
    return {
        "north": binary_mask[:h_top, w_left:w_right],
        "northwest": binary_mask[:h_top, :w_left],
        "west": binary_mask[h_top:h_bottom, :w_left],
        "southwest": binary_mask[h_bottom:, :w_left],
        "south": binary_mask[h_bottom:, w_left:w_right],
        "southeast": binary_mask[h_bottom:, w_right:],
        "east": binary_mask[h_top:h_bottom, w_right:],
        "northeast": binary_mask[:h_top, w_right:],
        "center": binary_mask[h_top:h_bottom, w_left:w_right]
    }

def _calculate_area_ratios(location_masks: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Tính tỷ lệ diện tích cho từng vị trí"""
    location_areas = {loc: np.sum(loc_mask) for loc, loc_mask in location_masks.items()}
    total_area = sum(location_areas.values())
    
    if total_area == 0:
        return {loc: 1/9 for loc in LOCATIONS}
    
    return {loc: area / total_area for loc, area in location_areas.items()}

def _calculate_edge_ratios(location_masks: Dict[str, np.ndarray]) -> Dict[str, float]:
    """Tính tỷ lệ cạnh ngoài cho từng vị trí"""
    from scipy import ndimage
    edge_ratios = {}
    
    for loc, loc_mask in location_masks.items():
        if loc_mask.size == 0 or np.sum(loc_mask) == 0:
            edge_ratios[loc] = 0
            continue
            
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        edges = ndimage.convolve(loc_mask, kernel, mode='constant', cval=0)
        edge_pixels = np.logical_and(loc_mask == 0, edges > 0).sum()
        edge_ratios[loc] = edge_pixels / loc_mask.size if loc_mask.size > 0 else 0
    
    # Chuẩn hóa
    max_edge_ratio = max(edge_ratios.values()) if edge_ratios else 1
    if max_edge_ratio > 0:
        edge_ratios = {loc: ratio / max_edge_ratio for loc, ratio in edge_ratios.items()}
    
    return edge_ratios

def _calculate_complexity(binary_mask: np.ndarray) -> float:
    """Tính chỉ số phức tạp của hình dạng"""
    height, width = binary_mask.shape
    perimeter = 0
    
    for y in range(1, height-1):
        for x in range(1, width-1):
            if binary_mask[y, x] == 1:
                if (binary_mask[y-1, x] == 0 or binary_mask[y+1, x] == 0 or 
                    binary_mask[y, x-1] == 0 or binary_mask[y, x+1] == 0):
                    perimeter += 1
    
    area = np.sum(binary_mask)
    if area > 0:
        return perimeter / (2 * np.sqrt(np.pi * area))
    return 1.0

def _get_base_room_suitability() -> Dict[str, Dict[str, float]]:
    """Định nghĩa độ phù hợp cơ bản của từng loại phòng với từng vị trí"""
    suitability = {}
    
    for loc in LOCATIONS:
        suitability[loc] = {}

        suitability[loc]["LivingRoom"] = 1.0 if loc == "center" else 0.4
        suitability[loc]["DiningRoom"] = 0.8 if loc == "center" else 0.5

        if loc in ["northwest", "northeast", "southwest", "southeast"]:
            suitability[loc]["MasterRoom"] = 0.9
            suitability[loc]["SecondRoom"] = 0.9
            suitability[loc]["ChildRoom"] = 0.8
            suitability[loc]["GuestRoom"] = 0.8
        elif loc in ["north", "south", "east", "west"]:
            suitability[loc]["MasterRoom"] = 0.7
            suitability[loc]["SecondRoom"] = 0.8
            suitability[loc]["ChildRoom"] = 0.7
            suitability[loc]["GuestRoom"] = 0.7
        else:
            suitability[loc]["MasterRoom"] = 0.3
            suitability[loc]["SecondRoom"] = 0.3
            suitability[loc]["ChildRoom"] = 0.3
            suitability[loc]["GuestRoom"] = 0.3
        
        if loc in ["north", "south", "east", "west"]:
            suitability[loc]["Kitchen"] = 0.9
            suitability[loc]["DiningRoom"] = max(suitability[loc]["DiningRoom"], 0.8)
        else:
            suitability[loc]["Kitchen"] = 0.5

        suitability[loc]["Bathroom"] = 0.9 if loc in ["northwest", "northeast", "southwest", "southeast"] else 0.6

        suitability[loc]["Balcony"] = 0.9 if loc in ["north", "south", "east", "west"] else 0.3

        suitability[loc]["Entrance"] = 0.9 if loc in ["north", "south", "east", "west"] else 0.4

        suitability[loc]["Storage"] = 0.8 if loc in ["northwest", "northeast", "southwest", "southeast"] else 0.5

        suitability[loc]["StudyRoom"] = 0.7
    
    return suitability

def _adjust_suitability_by_factors(room_suitability: Dict[str, Dict[str, float]], 
                                 edge_ratios: Dict[str, float], 
                                 area_ratios: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """Điều chỉnh độ phù hợp dựa trên edge và area factors"""
    for loc in LOCATIONS:
        edge_factor = edge_ratios.get(loc, 0)
        area_factor = area_ratios.get(loc, 0)
        
        # Điều chỉnh dựa trên edge factor
        room_suitability[loc]["Balcony"] *= (0.5 + 0.5 * edge_factor)
        room_suitability[loc]["LivingRoom"] *= (0.7 + 0.3 * edge_factor)
        room_suitability[loc]["MasterRoom"] *= (1.0 - 0.3 * edge_factor)
        room_suitability[loc]["Bathroom"] *= (1.0 - 0.2 * edge_factor)
        
        # Điều chỉnh dựa trên area factor
        room_suitability[loc]["LivingRoom"] *= (0.5 + 0.5 * area_factor)
        room_suitability[loc]["MasterRoom"] *= (0.6 + 0.4 * area_factor)
        
        if area_factor > 0.15:
            room_suitability[loc]["Storage"] *= (1.0 - 0.3 * area_factor)
            room_suitability[loc]["Entrance"] *= (1.0 - 0.3 * area_factor)
    
    return room_suitability

def analyze_mask(mask_path: str) -> Dict[str, Dict]:
    """Phân tích mask để xác định thông tin các vị trí"""
    try:
        binary_mask, height, width, centroid_y, centroid_x = _load_and_process_mask(mask_path)
        
        if height <= 2 or width <= 2:
            return {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                         "room_suitability": {}} for loc in LOCATIONS}
        
        h_top, h_bottom, w_left, w_right = _calculate_region_bounds(height, width, centroid_y, centroid_x)
        location_masks = _create_location_masks(binary_mask, h_top, h_bottom, w_left, w_right)
        
        area_ratios = _calculate_area_ratios(location_masks)
        edge_ratios = _calculate_edge_ratios(location_masks)
        complexity = _calculate_complexity(binary_mask)
        
        # Điều chỉnh area_ratios dựa trên complexity
        if complexity > 1.2:
            max_ratio = max(area_ratios.values())
            for loc in area_ratios:
                if area_ratios[loc] > 0.7 * max_ratio:
                    area_ratios[loc] *= 1.2
            
            total_ratio = sum(area_ratios.values())
            area_ratios = {loc: ratio / total_ratio for loc, ratio in area_ratios.items()}
        
        connectivity = {
            "center": 1.0,
            "north": 0.8, "south": 0.8, "east": 0.8, "west": 0.8,
            "northwest": 0.6, "northeast": 0.6, "southwest": 0.6, "southeast": 0.6
        }
        
        room_suitability = _get_base_room_suitability()
        room_suitability = _adjust_suitability_by_factors(room_suitability, edge_ratios, area_ratios)
        
        # Tổng hợp kết quả
        result = {}
        for loc in LOCATIONS:
            result[loc] = {
                "area_ratio": area_ratios.get(loc, 0),
                "edge_ratio": edge_ratios.get(loc, 0),
                "connectivity": connectivity.get(loc, 0.5),
                "room_suitability": room_suitability.get(loc, {}),
                "complexity": complexity
            }
        
        return result
    except Exception as e:
        print(f"Lỗi khi phân tích mask: {e}")
        return {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                     "room_suitability": {}, "complexity": 1.0} for loc in LOCATIONS}

def assign_room_sizes(rooms: List[Dict]) -> List[Dict]:
    """Gán kích thước cho các phòng dựa trên loại phòng"""
    # Gán kích thước mặc định theo loại phòng
    for room in rooms:
        room_type = room["name"].split("_")[0]
        room["size"] = ROOM_SIZE_MAPPING.get(room_type, "M")

    # Xử lý đặc biệt cho Bathroom: nếu có n phòng tắm, 1 phòng size M, còn lại size XS
    bathrooms = [r for r in rooms if r["name"].split("_")[0] == "Bathroom"]
    if len(bathrooms) >= 2:
        # Đặt tất cả về XS trước, sau đó chọn 1 phòng làm M
        for b in bathrooms:
            b["size"] = "XS"
        # Chọn ổn định theo tên (Bathroom, Bathroom_1, Bathroom_2, ...)
        primary_bathroom = sorted(bathrooms, key=lambda r: r["name"])[0]
        primary_bathroom["size"] = "M"
    elif len(bathrooms) == 1:
        bathrooms[0]["size"] = "M"

    return rooms

def _ensure_living_room_at_center(rooms: List[Dict], assigned_locations: Set[str]) -> None:
    """Đảm bảo LivingRoom luôn ở vị trí center"""
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    if not living_room:
        return
    
    if living_room["location"] == "center":
        return
    
    # Tìm phòng đang ở center và hoán đổi
    room_at_center = next((r for r in rooms if r["location"] == "center"), None)
    if room_at_center:
        room_at_center["location"] = living_room["location"]
    
    living_room["location"] = "center"
    assigned_locations.add("center")

def _calculate_room_location_scores(rooms: List[Dict], location_data: Dict[str, Dict]) -> Dict[str, Dict[str, float]]:
    """Tính điểm cho mỗi cặp (phòng, vị trí)"""
    room_location_scores = {}
    
    for room in rooms:
        room_type = _get_room_type(room)
        room_location_scores[room["name"]] = {}
        
        for location, loc_data in location_data.items():
            base_score = loc_data["room_suitability"].get(room_type, 0.5)
            area_factor = loc_data["area_ratio"]
            
            # Điều chỉnh theo kích thước phòng
            size_adjustment = 0
            if room.get("size") == "XL" and area_factor < 0.1:
                size_adjustment = -0.3
            elif room.get("size") == "XS" and area_factor > 0.2:
                size_adjustment = -0.2
            
            # Điều chỉnh theo khả năng kết nối
            connectivity_factor = loc_data["connectivity"]
            connectivity_importance = CONNECTION_PRIORITY.get(room_type, 5) / 10.0
            connectivity_adjustment = connectivity_factor * connectivity_importance
            
            # Tính điểm final với random factor
            final_score = base_score + size_adjustment + connectivity_adjustment
            final_score += random.uniform(-0.05, 0.05)
            final_score = max(0, min(1, final_score))
            
            room_location_scores[room["name"]][location] = final_score
    
    return room_location_scores

def _sort_rooms_by_priority(rooms: List[Dict]) -> List[Dict]:
    """Sắp xếp phòng theo độ ưu tiên"""
    size_order = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
    
    def room_priority(room):
        room_type = _get_room_type(room)
        connection_priority = CONNECTION_PRIORITY.get(room_type, 5)
        size_priority = size_order.get(room.get("size", "M"), 2)
        return connection_priority * 10 + size_priority
    
    return sorted(rooms, key=room_priority, reverse=True)

def _assign_initial_locations(sorted_rooms: List[Dict], room_location_scores: Dict[str, Dict[str, float]]) -> Set[str]:
    """Gán vị trí ban đầu cho các phòng"""
    assigned_locations = set()
    
    # Đảm bảo LivingRoom ở center
    living_room = next((r for r in sorted_rooms if "LivingRoom" in r["name"]), None)
    if living_room:
        living_room["location"] = "center"
        assigned_locations.add("center")
    
    # Gán vị trí cho các phòng còn lại
    for room in sorted_rooms:
        if "location" in room and room["location"] != "Unknown":
            assigned_locations.add(room["location"])
            continue
        
        # Tìm vị trí tốt nhất chưa được gán
        available_locations = [(loc, score) for loc, score in room_location_scores[room["name"]].items() 
                             if loc not in assigned_locations]
        
        if available_locations:
            best_location, _ = max(available_locations, key=lambda x: x[1])
            room["location"] = best_location
            assigned_locations.add(best_location)
        else:
            # Fallback: chọn vị trí ngẫu nhiên
            available = [loc for loc in LOCATIONS if loc not in assigned_locations]
            room["location"] = random.choice(available) if available else random.choice(LOCATIONS)
            assigned_locations.add(room["location"])
    
    return assigned_locations

def _optimize_incompatible_pairs(sorted_rooms: List[Dict], room_location_scores: Dict[str, Dict[str, float]]) -> bool:
    """Tối ưu hóa các cặp phòng không tương thích"""
    improved = False
    
    for i, room1 in enumerate(sorted_rooms):
        room1_type = _get_room_type(room1)
        
        for j, room2 in enumerate(sorted_rooms):
            if i == j:
                continue
                
            room2_type = _get_room_type(room2)
            is_incompatible = _is_incompatible_pair(room1_type, room2_type)
            
            # Xử lý hai phòng không tương thích ở cạnh nhau
            if is_incompatible and room2["location"] in ADJACENT_LOCATIONS[room1["location"]]:
                # Tìm vị trí thay thế tốt nhất cho room1
                best_alternative = None
                best_score = -1
                
                for loc in LOCATIONS:
                    if loc == room1["location"]:
                        continue
                    
                    # Kiểm tra xung đột mới
                    would_create_conflict = any(
                        _is_incompatible_pair(room1_type, _get_room_type(other_room)) and 
                        loc in ADJACENT_LOCATIONS[other_room["location"]]
                        for other_room in sorted_rooms if other_room != room1
                    )
                    
                    if not would_create_conflict:
                        score = room_location_scores[room1["name"]].get(loc, 0)
                        if score > best_score:
                            best_score = score
                            best_alternative = loc
                
                # Thực hiện hoán đổi nếu tìm được vị trí tốt hơn
                if best_alternative:
                    room_to_swap = next((r for r in sorted_rooms if r["location"] == best_alternative), None)
                    if room_to_swap:
                        room_to_swap["location"], room1["location"] = room1["location"], best_alternative
                    else:
                        room1["location"] = best_alternative
                    improved = True
    
    return improved

def _optimize_preferred_pairs(sorted_rooms: List[Dict], max_iterations: int) -> None:
    """Tối ưu hóa các cặp phòng nên đặt liền kề"""
    for pair in PREFERRED_PAIRS:
        room1_type, room2_type = pair
        
        rooms1 = [r for r in sorted_rooms if _get_room_type(r) == room1_type]
        rooms2 = [r for r in sorted_rooms if _get_room_type(r) == room2_type]
        
        if not rooms1 or not rooms2:
            continue
        
        # Kiểm tra xem có cặp nào đã liền kề chưa
        already_adjacent = any(
            r2["location"] in ADJACENT_LOCATIONS[r1["location"]]
            for r1 in rooms1 for r2 in rooms2
        )
        
        # Nếu chưa liền kề, thử hoán đổi
        if not already_adjacent:
            r1, r2 = rooms1[0], rooms2[0]
            adjacent_to_r1 = ADJACENT_LOCATIONS[r1["location"]]
            
            for loc in adjacent_to_r1:
                room_at_loc = next((r for r in sorted_rooms if r["location"] == loc), None)
                if room_at_loc and room_at_loc != r2:
                    # Kiểm tra xung đột
                    room_at_loc_type = _get_room_type(room_at_loc)
                    if not _is_incompatible_pair(room_at_loc_type, room2_type):
                        room_at_loc["location"], r2["location"] = r2["location"], room_at_loc["location"]
                        break

def assign_room_locations(rooms: List[Dict], location_data: Dict[str, Dict]) -> List[Dict]:
    """Gán vị trí cho các phòng dựa trên phân tích mask"""
    room_location_scores = _calculate_room_location_scores(rooms, location_data)
    sorted_rooms = _sort_rooms_by_priority(rooms)
    assigned_locations = _assign_initial_locations(sorted_rooms, room_location_scores)
    
    # Tối ưu hóa cục bộ
    max_iterations = 5
    _ensure_living_room_at_center(sorted_rooms, assigned_locations)
    
    for iteration in range(max_iterations):
        if not _optimize_incompatible_pairs(sorted_rooms, room_location_scores):
            break
    
    _optimize_preferred_pairs(sorted_rooms, max_iterations)
    
    return sorted_rooms

def _size_rank(size: str) -> int:
    order = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
    return order.get(size or "M", 2)

def _would_create_conflict(room: Dict, new_location: str, rooms: List[Dict]) -> bool:
    room_type = _get_room_type(room)
    for other in rooms:
        if other is room:
            continue
        other_loc = other.get("location")
        if not other_loc or new_location not in ADJACENT_LOCATIONS:
            continue
        if other_loc in ADJACENT_LOCATIONS[new_location]:
            if _is_incompatible_pair(room_type, _get_room_type(other)):
                return True
    return False

def _rebalance_segment_load(rooms: List[Dict]) -> None:
    """Nếu dải northeast–east–southeast chứa đồng thời XL, L, M thì hoán đổi
    phòng lớn nhất trong dải với một phòng nhỏ (S/XS) ngoài dải để phân tán tải.
    Tránh tạo xung đột không tương thích sau hoán đổi.
    """
    segment = SEGMENTS["east_vertical"]
    rooms_by_loc: Dict[str, List[Dict]] = {}
    for r in rooms:
        loc = r.get("location")
        if not loc:
            continue
        rooms_by_loc.setdefault(loc, []).append(r)

    # Thu thập kích thước trong dải
    sizes_in_segment: List[str] = []
    segment_rooms: List[Dict] = []
    for loc in segment:
        for r in rooms_by_loc.get(loc, []):
            sizes_in_segment.append(r.get("size", "M"))
            segment_rooms.append(r)

    have_xl = any(s == "XL" for s in sizes_in_segment)
    have_l = any(s == "L" for s in sizes_in_segment)
    have_m = any(s == "M" for s in sizes_in_segment)
    if not (have_xl and have_l and have_m):
        return

    # Chọn phòng lớn nhất trong dải (ưu tiên XL, rồi L, rồi M có bậc lớn)
    segment_rooms_sorted = sorted(segment_rooms, key=lambda r: (-_size_rank(r.get("size")), r.get("name")))
    big_room = segment_rooms_sorted[0] if segment_rooms_sorted else None
    if not big_room:
        return

    # Tìm phòng nhỏ ngoài dải (S/XS), không phải center
    small_candidates = [r for r in rooms if r not in segment_rooms and r.get("location") not in (None, "center") and r.get("size") in ("S", "XS")]
    if not small_candidates:
        return

    # Thử hoán đổi với ứng viên đầu tiên thỏa điều kiện không tạo xung đột
    for small_room in sorted(small_candidates, key=lambda r: (r.get("size"), r.get("name"))):
        loc_big = big_room.get("location")
        loc_small = small_room.get("location")
        if not loc_big or not loc_small:
            continue
        if _would_create_conflict(big_room, loc_small, rooms):
            continue
        if _would_create_conflict(small_room, loc_big, rooms):
            continue
        # Hoán đổi vị trí
        big_room["location"], small_room["location"] = loc_small, loc_big
        break

def _get_max_connections() -> Dict[str, int]:
    """Định nghĩa số lượng kết nối tối đa cho mỗi loại phòng"""
    return {
        "LivingRoom": 8, "Kitchen": 3, "Entrance": 2, "MasterRoom": 3,
        "SecondRoom": 2, "Bathroom": 2, "Balcony": 2, "Storage": 1,
        "DiningRoom": 3, "StudyRoom": 2, "GuestRoom": 2, "ChildRoom": 2, "CommonRoom": 3
    }

def _get_preferred_connections() -> Dict[str, List[str]]:
    """Định nghĩa các cặp phòng nên kết nối với nhau"""
    return {
        "LivingRoom": ["Kitchen", "DiningRoom", "Entrance", "MasterRoom", "Balcony"],
        "Kitchen": ["DiningRoom", "LivingRoom", "Storage"],
        "Entrance": ["LivingRoom", "CommonRoom"],
        "MasterRoom": ["Bathroom", "LivingRoom", "Balcony"],
        "SecondRoom": ["Bathroom", "LivingRoom"],
        "Bathroom": ["LivingRoom", "MasterRoom", "SecondRoom"],
        "Balcony": ["LivingRoom", "MasterRoom", "DiningRoom"],
        "Storage": ["Kitchen", "LivingRoom"],
        "DiningRoom": ["Kitchen", "LivingRoom", "Balcony"],
        "StudyRoom": ["LivingRoom", "MasterRoom"],
        "GuestRoom": ["LivingRoom", "Bathroom"],
        "ChildRoom": ["LivingRoom", "Bathroom"],
        "CommonRoom": ["LivingRoom", "Kitchen", "Entrance"]
    }

def _create_location_mapping(rooms: List[Dict]) -> Dict[str, List[Dict]]:
    """Tạo từ điển ánh xạ từ vị trí đến phòng"""
    location_to_rooms = {}
    for room in rooms:
        location = room.get("location")
        if location not in location_to_rooms:
            location_to_rooms[location] = []
        location_to_rooms[location].append(room)
    return location_to_rooms

def _connect_adjacent_rooms(rooms: List[Dict], location_to_rooms: Dict[str, List[Dict]], 
                          max_connections: Dict[str, int], preferred_connections: Dict[str, List[str]]) -> None:
    """Kết nối các phòng ở vị trí liền kề"""
    for room in rooms:
        room_type = _get_room_type(room)
        location = room.get("location")
        # Áp dụng giới hạn kết nối cho phòng nhỏ (S/XS): tối đa 2 kết nối tổng
        room_size_cap = 2 if room.get("size") in ["S", "XS"] else max_connections.get(room_type, 2)
        
        if not location or location not in ADJACENT_LOCATIONS:
            continue
        
        for adj_location in ADJACENT_LOCATIONS[location]:
            if adj_location not in location_to_rooms:
                continue
            
            for adj_room in location_to_rooms[adj_location]:
                adj_room_type = _get_room_type(adj_room)
                adj_room_size_cap = 2 if adj_room.get("size") in ["S", "XS"] else max_connections.get(adj_room_type, 2)

                # Bỏ qua nếu đã kết nối hoặc vượt giới hạn cho một trong hai phòng
                if (adj_room["name"] in room["link"] or 
                    len(room["link"]) >= room_size_cap or
                    len(adj_room["link"]) >= adj_room_size_cap):
                    continue
                
                if (_is_incompatible_pair(room_type, adj_room_type)):
                    continue
                
                # Kiểm tra ưu tiên kết nối
                is_preferred = (
                    (room_type in preferred_connections and adj_room_type in preferred_connections[room_type]) or
                    (adj_room_type in preferred_connections and room_type in preferred_connections[adj_room_type])
                )
                
                # Ưu tiên hoặc nếu phòng chưa đạt một nửa giới hạn của nó
                if is_preferred or len(room["link"]) < max(1, room_size_cap // 2):
                    if len(room["link"]) < room_size_cap and len(adj_room["link"]) < adj_room_size_cap:
                        room["link"].append(adj_room["name"])
                        adj_room["link"].append(room["name"])

def create_smart_room_links(rooms: List[Dict]) -> List[Dict]:
    """Tạo liên kết thông minh giữa các phòng"""
    # Khởi tạo
    for room in rooms:
        room["link"] = []
    
    max_connections = _get_max_connections()
    preferred_connections = _get_preferred_connections()
    location_to_rooms = _create_location_mapping(rooms)
    
    _connect_adjacent_rooms(rooms, location_to_rooms, max_connections, preferred_connections)
    
    # Kết nối LivingRoom với các phòng quan trọng liền kề (tôn trọng giới hạn cho phòng nhỏ)
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    if living_room and living_room.get("location") in ADJACENT_LOCATIONS:
        for room in rooms:
            if (room != living_room and 
                room.get("location") in ADJACENT_LOCATIONS[living_room["location"]] and
                CONNECTION_PRIORITY.get(_get_room_type(room), 0) >= 7 and
                living_room["name"] not in room["link"]):
                # Áp dụng giới hạn 2 kết nối cho phòng size S/XS
                room_cap = 2 if room.get("size") in ["S", "XS"] else _get_max_connections().get(_get_room_type(room), 2)
                lr_cap = 2 if living_room.get("size") in ["S", "XS"] else _get_max_connections().get("LivingRoom", 8)
                if len(room["link"]) < room_cap and len(living_room["link"]) < lr_cap:
                    room["link"].append(living_room["name"])
                    if room["name"] not in living_room["link"] and len(living_room["link"]) < lr_cap:
                        living_room["link"].append(room["name"])
    
    # Đảm bảo tất cả phòng có ít nhất một kết nối (tôn trọng giới hạn cho phòng nhỏ)
    for room in rooms:
        if not room["link"] and living_room and room != living_room:
            room_cap = 2 if room.get("size") in ["S", "XS"] else _get_max_connections().get(_get_room_type(room), 2)
            lr_cap = 2 if living_room.get("size") in ["S", "XS"] else _get_max_connections().get("LivingRoom", 8)
            if len(room["link"]) < room_cap and len(living_room["link"]) < lr_cap:
                room["link"].append(living_room["name"])
                if room["name"] not in living_room["link"] and len(living_room["link"]) < lr_cap:
                    living_room["link"].append(room["name"])
    
    return rooms

def optimize_layout(json_data: Dict, mask_path: str = None) -> Dict:
    """
    Tối ưu hóa bố cục bằng cách gán kích thước, vị trí và liên kết cho các phòng.
    """
    # Phân tích mask
    location_data = {}
    if mask_path:
        location_data = analyze_mask(mask_path)
    else:
        location_data = {loc: {"area_ratio": 1/9, "edge_ratio": 0.5, "connectivity": 0.5, 
                              "room_suitability": {}, "complexity": 1.0} for loc in LOCATIONS}
    
    # Tạo danh sách các phòng
    rooms = []
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            room = room_data["rooms"][i]
            rooms.append(room)

    rooms = assign_room_sizes(rooms)

    for room in rooms:
        if "LivingRoom" in room["name"]:
            room["location"] = "center"
            break

    rooms = assign_room_locations(rooms, location_data)

    # Cân bằng tải diện tích theo dải hướng trước khi tạo liên kết
    _rebalance_segment_load(rooms)
    
    # Kiểm tra lại sau khi gán vị trí để đảm bảo LivingRoom vẫn ở center
    for room in rooms:
        if "LivingRoom" in room["name"] and room["location"] != "center":
            room_at_center = next((r for r in rooms if r["location"] == "center"), None)
            if room_at_center:
                room_at_center["location"] = room["location"]
                room["location"] = "center"
            else:
                room["location"] = "center"
    
    # Tạo liên kết giữa các phòng
    rooms = create_smart_room_links(rooms)
    
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
            if room_counts[room_type] > 1:
                room_name = f"{room_type}_{i+1}"
            else:
                room_name = room_type
                
            room_list.append({
                "name": room_name,
                "link": [],
                "location": "Unknown"
            })
        
        json_data[room_type] = {
            "num": room["num"],
            "rooms": room_list
        }
    
    # Tối ưu hóa bố cục
    optimized_json = optimize_layout(json_data, mask_path)
    
    return optimized_json


def _get_room_type(room: Dict) -> str:
    """Lấy loại phòng từ tên phòng"""
    return room["name"].split("_")[0]

def _is_incompatible_pair(room1_type: str, room2_type: str) -> bool:
    """Kiểm tra xem hai loại phòng có không tương thích không"""
    for pair in INCOMPATIBLE_PAIRS:
        if (room1_type == pair[0] and room2_type == pair[1]) or \
           (room1_type == pair[1] and room2_type == pair[0]):
            return True
    return False
