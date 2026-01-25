"""
Module gán vị trí cho các phòng dựa trên ma trận điểm.
"""
import numpy as np
from typing import Dict, List, Any, Set, Tuple
import logging
from scipy.optimize import linear_sum_assignment
from .config import LOCATIONS, ADJACENT_LOCATIONS
from .utils import extract_room_type, is_incompatible_pair

logger = logging.getLogger('layout_optimizer.assignment')

def assign_locations_hungarian(score_matrix: np.ndarray, rooms: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Gán vị trí cho các phòng sử dụng thuật toán Hungarian.
    
    Args:
        score_matrix: Ma trận điểm (rooms x locations)
        rooms: Danh sách các phòng
        
    Returns:
        Dict ánh xạ tên phòng -> vị trí
    """
    # Đảm bảo ma trận vuông bằng cách thêm các hàng giả
    num_rooms, num_locations = score_matrix.shape
    
    if num_rooms > num_locations:
        logger.warning(f"Số phòng ({num_rooms}) > số vị trí ({num_locations}), một số phòng sẽ không được gán vị trí")
        # Cắt bớt số phòng
        score_matrix = score_matrix[:num_locations, :]
        rooms = rooms[:num_locations]
    elif num_rooms < num_locations:
        # Thêm các hàng giả với điểm thấp
        padding = np.zeros((num_locations - num_rooms, num_locations))
        score_matrix = np.vstack((score_matrix, padding))
    
    # Chuyển thành bài toán tối thiểu hóa
    cost_matrix = 1 - score_matrix
    
    # Giải bài toán gán
    row_indices, col_indices = linear_sum_assignment(cost_matrix)
    
    # Tạo kết quả
    assignment = {}
    for i, room in enumerate(rooms):
        if i in row_indices:
            col_idx = col_indices[np.where(row_indices == i)[0][0]]
            assignment[room["name"]] = LOCATIONS[col_idx]
    
    return assignment

def assign_locations_greedy(score_matrix: np.ndarray, rooms: List[Dict[str, Any]], 
                           priority_vector: np.ndarray) -> Dict[str, str]:
    """
    Gán vị trí cho các phòng sử dụng thuật toán tham lam.
    
    Args:
        score_matrix: Ma trận điểm (rooms x locations)
        rooms: Danh sách các phòng
        priority_vector: Vector ưu tiên cho các phòng
        
    Returns:
        Dict ánh xạ tên phòng -> vị trí
    """
    # Sắp xếp phòng theo độ ưu tiên
    room_indices = np.argsort(-priority_vector)
    
    # Khởi tạo kết quả
    assignment = {}
    assigned_locations = set()
    
    # Đảm bảo LivingRoom ở center
    living_room_idx = None
    for i, room in enumerate(rooms):
        if "LivingRoom" in room["name"]:
            living_room_idx = i
            break
    
    if living_room_idx is not None:
        center_idx = LOCATIONS.index("center")
        assignment[rooms[living_room_idx]["name"]] = "center"
        assigned_locations.add("center")
    
    # Gán vị trí cho các phòng còn lại
    for i in room_indices:
        room = rooms[i]
        
        # Bỏ qua phòng đã được gán
        if room["name"] in assignment:
            continue
        
        # Tìm vị trí tốt nhất chưa được gán
        available_indices = [j for j, loc in enumerate(LOCATIONS) if loc not in assigned_locations]
        
        if available_indices:
            scores = score_matrix[i, available_indices]
            best_idx = available_indices[np.argmax(scores)]
            assignment[room["name"]] = LOCATIONS[best_idx]
            assigned_locations.add(LOCATIONS[best_idx])
        else:
            logger.warning(f"Không còn vị trí trống cho phòng {room['name']}")
    
    return assignment

def optimize_incompatible_pairs(assignment: Dict[str, str], rooms: List[Dict[str, Any]], 
                              score_matrix: np.ndarray, max_iterations: int = 5) -> Dict[str, str]:
    """
    Tối ưu hóa các cặp phòng không tương thích.
    
    Args:
        assignment: Dict ánh xạ tên phòng -> vị trí
        rooms: Danh sách các phòng
        score_matrix: Ma trận điểm (rooms x locations)
        max_iterations: Số lần lặp tối đa
        
    Returns:
        Dict ánh xạ tên phòng -> vị trí đã tối ưu
    """
    room_map = {room["name"]: room for room in rooms}
    room_indices = {room["name"]: i for i, room in enumerate(rooms)}
    location_indices = {loc: i for i, loc in enumerate(LOCATIONS)}
    
    for _ in range(max_iterations):
        improved = False
        
        for room1_name, location1 in list(assignment.items()):
            room1 = room_map[room1_name]
            room1_type = extract_room_type(room1_name)
            
            # Kiểm tra xung đột
            for room2_name, location2 in assignment.items():
                if room1_name == room2_name:
                    continue
                
                room2 = room_map[room2_name]
                room2_type = extract_room_type(room2["name"])
                
                # Nếu hai phòng không tương thích và liền kề
                if is_incompatible_pair(room1_type, room2_type) and location2 in ADJACENT_LOCATIONS[location1]:
                    # Tìm vị trí thay thế tốt nhất cho room1
                    best_alternative = None
                    best_score = -1
                    
                    for loc in LOCATIONS:
                        if loc == location1 or loc in assignment.values():
                            continue
                        
                        # Kiểm tra xung đột mới
                        would_create_conflict = any(
                            is_incompatible_pair(room1_type, extract_room_type(room_map[r_name]["name"])) and 
                            loc in ADJACENT_LOCATIONS[assignment[r_name]]
                            for r_name in assignment if r_name != room1_name
                        )
                        
                        if not would_create_conflict:
                            score = score_matrix[room_indices[room1_name], location_indices[loc]]
                            if score > best_score:
                                best_score = score
                                best_alternative = loc
                    
                    # Thực hiện hoán đổi nếu tìm được vị trí tốt hơn
                    if best_alternative:
                        assignment[room1_name] = best_alternative
                        improved = True
                        break
            
            if improved:
                break
        
        if not improved:
            break
    
    return assignment

def assign_locations(score_matrix: np.ndarray, rooms: List[Dict[str, Any]], 
                    priority_vector: np.ndarray = None) -> Dict[str, str]:
    """
    Gán vị trí cho các phòng.
    
    Args:
        score_matrix: Ma trận điểm (rooms x locations)
        rooms: Danh sách các phòng
        priority_vector: Vector ưu tiên cho các phòng (nếu None, sẽ được tính toán)
        
    Returns:
        Dict ánh xạ tên phòng -> vị trí
    """
    num_rooms = len(rooms)
    
    if priority_vector is None:
        from .scoring import get_room_priority_vector
        priority_vector = get_room_priority_vector(rooms)
    
    # Chọn thuật toán phù hợp
    if num_rooms <= len(LOCATIONS):
        logger.info("Sử dụng thuật toán Hungarian")
        assignment = assign_locations_hungarian(score_matrix, rooms)
    else:
        logger.info("Sử dụng thuật toán tham lam")
        assignment = assign_locations_greedy(score_matrix, rooms, priority_vector)
    
    # Tối ưu hóa các cặp phòng không tương thích
    assignment = optimize_incompatible_pairs(assignment, rooms, score_matrix)
    
    return assignment

def update_rooms_with_locations(rooms: List[Dict[str, Any]], assignment: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Cập nhật vị trí cho các phòng.
    
    Args:
        rooms: Danh sách các phòng
        assignment: Dict ánh xạ tên phòng -> vị trí
        
    Returns:
        Danh sách các phòng đã cập nhật
    """
    for room in rooms:
        if room["name"] in assignment:
            room["location"] = assignment[room["name"]]
        else:
            logger.warning(f"Không tìm thấy vị trí cho phòng {room['name']}")
            room["location"] = "Unknown"
    
    return rooms