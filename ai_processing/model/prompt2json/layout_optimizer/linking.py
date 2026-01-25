"""
Module tạo liên kết giữa các phòng sau khi đã gán vị trí.
"""
import numpy as np
from typing import Dict, List, Any, Set
import logging
from .config import ADJACENT_LOCATIONS, MAX_CONNECTIONS, CONNECTION_PRIORITY
from .utils import extract_room_type, is_preferred_pair

logger = logging.getLogger('layout_optimizer.linking')

def create_location_map(rooms: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Tạo map từ vị trí đến danh sách phòng ở vị trí đó.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Dict ánh xạ vị trí -> danh sách phòng
    """
    location_map = {}
    
    for room in rooms:
        location = room.get("location", "Unknown")
        if location not in location_map:
            location_map[location] = []
        location_map[location].append(room)
    
    return location_map

def get_max_connections(room: Dict[str, Any]) -> int:
    """
    Lấy số lượng kết nối tối đa cho một phòng.
    
    Args:
        room: Thông tin phòng
        
    Returns:
        Số lượng kết nối tối đa
    """
    room_size = room.get("size", "M")
    room_type = extract_room_type(room["name"])
    
    # Phòng khách luôn có nhiều kết nối nhất
    if room_type == "LivingRoom":
        return MAX_CONNECTIONS["XL"]
    return MAX_CONNECTIONS.get(room_size, 3)

def sort_rooms_by_priority(rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sắp xếp phòng theo độ ưu tiên.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Danh sách các phòng đã sắp xếp
    """
    def room_priority(room):
        room_type = extract_room_type(room["name"])
        connection_priority = CONNECTION_PRIORITY.get(room_type, 5)
        size_priority = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}.get(room.get("size", "M"), 2)
        return connection_priority * 10 + size_priority
    
    return sorted(rooms, key=room_priority, reverse=True)

def create_links(rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tạo liên kết giữa các phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Danh sách các phòng đã cập nhật với liên kết
    """
    # Tạo map từ tên phòng đến phòng
    room_map = {room["name"]: room for room in rooms}
    
    # Tạo map từ vị trí đến danh sách phòng
    location_map = create_location_map(rooms)
    
    # Khởi tạo danh sách liên kết cho mỗi phòng
    for room in rooms:
        room["links"] = []
    
    # Sắp xếp phòng theo độ ưu tiên
    sorted_rooms = sort_rooms_by_priority(rooms)
    
    # Tạo liên kết
    for room in sorted_rooms:
        max_links = get_max_connections(room)
        location = room.get("location", "Unknown")
        
        if location == "Unknown":
            logger.warning(f"Phòng {room['name']} không có vị trí, bỏ qua tạo liên kết")
            continue
        
        # Lấy danh sách vị trí liền kề
        adjacent_locations = ADJACENT_LOCATIONS.get(location, [])
        
        # Tạo danh sách phòng liền kề
        adjacent_rooms = []
        for adj_loc in adjacent_locations:
            adjacent_rooms.extend(location_map.get(adj_loc, []))
        
        # Lọc bỏ phòng hiện tại
        adjacent_rooms = [r for r in adjacent_rooms if r["name"] != room["name"]]
        
        # Sắp xếp phòng liền kề theo độ ưu tiên
        adjacent_rooms = sort_rooms_by_priority(adjacent_rooms)
        
        # Ưu tiên các cặp phòng nên đặt liền kề
        room_type = extract_room_type(room["name"])
        preferred_rooms = [r for r in adjacent_rooms if is_preferred_pair(room["name"], r["name"])]
        other_rooms = [r for r in adjacent_rooms if r not in preferred_rooms]
        
        # Kết hợp lại
        prioritized_rooms = preferred_rooms + other_rooms
        
        # Tạo liên kết
        for adj_room in prioritized_rooms:
            # Kiểm tra số lượng liên kết
            if len(room["links"]) >= max_links:
                break
            
            # Kiểm tra số lượng liên kết của phòng liền kề
            adj_max_links = get_max_connections(adj_room)
            if len(adj_room["links"]) >= adj_max_links:
                continue
            
            # Kiểm tra liên kết đã tồn tại
            if adj_room["name"] in room["links"] or room["name"] in adj_room["links"]:
                continue
            
            # Tạo liên kết hai chiều
            room["links"].append(adj_room["name"])
            adj_room["links"].append(room["name"])
    
    # Đảm bảo mọi phòng có ít nhất 1 liên kết
    ensure_minimum_connections(rooms, room_map)
    
    return rooms

def ensure_minimum_connections(rooms: List[Dict[str, Any]], room_map: Dict[str, Dict[str, Any]]) -> None:
    """
    Đảm bảo mọi phòng có ít nhất 1 liên kết.
    
    Args:
        rooms: Danh sách các phòng
        room_map: Map từ tên phòng đến phòng
    """
    # Tìm phòng LivingRoom
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    
    if not living_room:
        logger.warning("Không tìm thấy phòng LivingRoom, không thể đảm bảo liên kết tối thiểu")
        return
    
    # Kiểm tra từng phòng
    for room in rooms:
        if len(room["links"]) == 0:
            # Tìm phòng liền kề có thể kết nối
            location = room.get("location", "Unknown")
            if location == "Unknown":
                continue
            
            adjacent_locations = ADJACENT_LOCATIONS.get(location, [])
            living_room_location = living_room.get("location", "Unknown")
            
            # Ưu tiên kết nối với phòng liền kề
            if living_room_location in adjacent_locations and len(living_room["links"]) < get_max_connections(living_room):
                room["links"].append(living_room["name"])
                living_room["links"].append(room["name"])
                logger.info(f"Tạo liên kết giữa {room['name']} và {living_room['name']} (fallback)")
            else:
                # Tìm phòng liền kề khác
                for adj_loc in adjacent_locations:
                    for r in rooms:
                        if r["location"] == adj_loc and len(r["links"]) < get_max_connections(r):
                            room["links"].append(r["name"])
                            r["links"].append(room["name"])
                            logger.info(f"Tạo liên kết giữa {room['name']} và {r['name']} (fallback)")
                            break
                    if len(room["links"]) > 0:
                        break