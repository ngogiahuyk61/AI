"""
Các hàm tiện ích cho module tối ưu hóa bố cục.
"""
from typing import Dict, List, Any, Set, Tuple
import logging

from .config import (
    INCOMPATIBLE_PAIRS, 
    PREFERRED_PAIRS, 
    ROOM_SIZE_RANKING,
    LOCATIONS
)

logger = logging.getLogger('layout_optimizer.utils')

def extract_room_type(room_name: str) -> str:
    """
    Trích xuất loại phòng từ tên phòng.
    
    Args:
        room_name: Tên phòng (ví dụ: "LivingRoom", "Bathroom_1")
        
    Returns:
        Loại phòng (ví dụ: "LivingRoom", "Bathroom")
    """
    return room_name.split('_')[0]

def is_incompatible_pair(room1: str, room2: str) -> bool:
    """
    Kiểm tra xem hai phòng có không tương thích với nhau không.
    
    Args:
        room1: Tên phòng thứ nhất
        room2: Tên phòng thứ hai
        
    Returns:
        True nếu hai phòng không tương thích, False nếu ngược lại
    """
    room1_type = extract_room_type(room1)
    room2_type = extract_room_type(room2)
    
    return (room1_type, room2_type) in INCOMPATIBLE_PAIRS or (room2_type, room1_type) in INCOMPATIBLE_PAIRS

def is_preferred_pair(room1: str, room2: str) -> bool:
    """
    Kiểm tra xem hai phòng có được ưu tiên kết nối với nhau không.
    
    Args:
        room1: Tên phòng thứ nhất
        room2: Tên phòng thứ hai
        
    Returns:
        True nếu hai phòng được ưu tiên kết nối, False nếu ngược lại
    """
    room1_type = extract_room_type(room1)
    room2_type = extract_room_type(room2)
    
    return (room1_type, room2_type) in PREFERRED_PAIRS or (room2_type, room1_type) in PREFERRED_PAIRS

def get_size_rank(size: str) -> int:
    """
    Lấy thứ hạng của kích thước phòng.
    
    Args:
        size: Kích thước phòng (XS, S, M, L, XL)
        
    Returns:
        Thứ hạng của kích thước (số càng lớn thì kích thước càng lớn)
    """
    return ROOM_SIZE_RANKING.get(size, 0)

def validate_room_structure(rooms: List[Dict[str, Any]]) -> bool:
    """
    Kiểm tra tính hợp lệ của cấu trúc phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        True nếu cấu trúc hợp lệ, False nếu ngược lại
    """
    # Kiểm tra các trường bắt buộc
    for room in rooms:
        if "name" not in room:
            logger.error(f"Phòng thiếu trường 'name': {room}")
            return False
        if "size" not in room:
            logger.error(f"Phòng thiếu trường 'size': {room['name']}")
            return False
    
    # Kiểm tra tên phòng duy nhất
    room_names = [room["name"] for room in rooms]
    if len(room_names) != len(set(room_names)):
        logger.error("Có phòng trùng tên")
        return False
    
    return True

def validate_location_assignment(rooms: List[Dict[str, Any]]) -> bool:
    """
    Kiểm tra tính hợp lệ của việc gán vị trí cho các phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        True nếu việc gán vị trí hợp lệ, False nếu ngược lại
    """
    # Kiểm tra các trường bắt buộc
    for room in rooms:
        if "location" not in room:
            logger.error(f"Phòng thiếu trường 'location': {room['name']}")
            return False
    
    # Kiểm tra vị trí hợp lệ
    for room in rooms:
        if room["location"] not in LOCATIONS and room["location"] != "Unknown":
            logger.error(f"Vị trí không hợp lệ: {room['location']} cho phòng {room['name']}")
            return False
    
    # Kiểm tra vị trí duy nhất
    assigned_locations = [room["location"] for room in rooms if room["location"] != "Unknown"]
    if len(assigned_locations) != len(set(assigned_locations)):
        logger.error("Có vị trí được gán cho nhiều phòng")
        return False
    
    return True

def validate_links(rooms: List[Dict[str, Any]]) -> bool:
    """
    Kiểm tra tính hợp lệ của các liên kết giữa các phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        True nếu các liên kết hợp lệ, False nếu ngược lại
    """
    room_dict = {room["name"]: room for room in rooms}
    
    # Kiểm tra các liên kết
    for room in rooms:
        if "links" not in room:
            logger.error(f"Phòng thiếu trường 'links': {room['name']}")
            return False
        
        for link in room["links"]:
            # Kiểm tra liên kết tồn tại
            if link not in room_dict:
                logger.error(f"Liên kết không tồn tại: {link} từ phòng {room['name']}")
                return False
            
            # Kiểm tra liên kết hai chiều
            if room["name"] not in room_dict[link].get("links", []):
                logger.error(f"Liên kết không hai chiều: {room['name']} -> {link}")
                return False
    
    return True