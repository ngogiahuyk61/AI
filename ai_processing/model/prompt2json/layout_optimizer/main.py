"""
Module chính cho việc tối ưu hóa bố cục.
"""
import logging
from typing import Dict, List, Any
import sys
import os

# Thêm thư mục cha vào sys.path để import room_completer
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from room_completer import ensure_complete_room_structure

from .mask_analysis import analyze_mask
from .scoring import build_score_matrix, add_random_noise, get_room_priority_vector
from .assignment import assign_locations, update_rooms_with_locations
from .linking import create_links
from .utils import validate_room_structure, validate_location_assignment, validate_links

logger = logging.getLogger('layout_optimizer.main')

def ensure_complete_room_structure(rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Đảm bảo cấu trúc phòng đầy đủ.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Danh sách các phòng đã cập nhật
    """
    # Đơn giản hóa cho demo, chỉ đảm bảo các trường cần thiết
    for room in rooms:
        if "links" not in room:
            room["links"] = []
    
    return rooms

def assign_room_sizes(rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Gán kích thước cho các phòng dựa trên loại phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Danh sách các phòng đã cập nhật với kích thước
    """
    from .config import ROOM_SIZE_MAPPING
    
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

def optimize_layout(rooms: List[Dict[str, Any]], mask_path: str = None) -> List[Dict[str, Any]]:
    """
    Tối ưu hóa bố cục cho các phòng.
    
    Args:
        rooms: Danh sách các phòng
        mask_path: Đường dẫn đến file mask (nếu None, sẽ sử dụng mask mặc định)
        
    Returns:
        Danh sách các phòng đã tối ưu hóa
    """
    logger.info(f"Bắt đầu tối ưu hóa bố cục cho {len(rooms)} phòng")
    
    # Đảm bảo cấu trúc phòng đầy đủ
    rooms = ensure_complete_room_structure(rooms)
    
    # Gán kích thước cho các phòng
    rooms = assign_room_sizes(rooms)
    
    # Phân tích mask
    if mask_path:
        logger.info(f"Phân tích mask: {mask_path}")
        location_features = analyze_mask(mask_path)
    else:
        logger.info("Không có mask, sử dụng phân bố đều")
        from .mask_analysis import LocationFeatures
        from .config import LOCATIONS
        location_features = {loc: LocationFeatures(1/9, 0.5, 0.5, 1.0) for loc in LOCATIONS}
    
    # Xây dựng ma trận điểm
    score_matrix = build_score_matrix(rooms, location_features)
    
    # Thêm nhiễu ngẫu nhiên
    score_matrix = add_random_noise(score_matrix)
    
    # Tính vector ưu tiên
    priority_vector = get_room_priority_vector(rooms)
    
    # Gán vị trí cho các phòng
    assignment = assign_locations(score_matrix, rooms, priority_vector)
    
    # Cập nhật vị trí cho các phòng
    rooms = update_rooms_with_locations(rooms, assignment)
    
    # Tạo liên kết giữa các phòng
    rooms = create_links(rooms)
    
    # Kiểm tra tính hợp lệ
    if not validate_room_structure(rooms):
        logger.warning("Cấu trúc phòng không hợp lệ")
    
    if not validate_location_assignment(rooms):
        logger.warning("Gán vị trí không hợp lệ")
    
    if not validate_links(rooms):
        logger.warning("Liên kết không hợp lệ")
    
    logger.info(f"Hoàn thành tối ưu hóa bố cục cho {len(rooms)} phòng")
    
    return rooms