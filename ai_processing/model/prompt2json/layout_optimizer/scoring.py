"""
Module xây dựng ma trận điểm cho các phòng và vị trí.
"""
import numpy as np
from typing import Dict, List, Any
import logging
from .config import LOCATIONS, DEFAULT_WEIGHTS
from .utils import extract_room_type

logger = logging.getLogger('layout_optimizer.scoring')

def build_score_matrix(rooms: List[Dict[str, Any]], location_features: Dict[str, Any], 
                      weights: Dict[str, float] = None) -> np.ndarray:
    """
    Xây dựng ma trận điểm cho các phòng và vị trí.
    
    Args:
        rooms: Danh sách các phòng
        location_features: Đặc trưng của từng vị trí
        weights: Trọng số cho các yếu tố (mặc định: DEFAULT_WEIGHTS)
        
    Returns:
        Ma trận điểm (rooms x locations)
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    
    num_rooms = len(rooms)
    num_locations = len(LOCATIONS)
    
    # Khởi tạo ma trận điểm
    score_matrix = np.zeros((num_rooms, num_locations))
    
    for i, room in enumerate(rooms):
        room_type = extract_room_type(room["name"])
        
        for j, location in enumerate(LOCATIONS):
            features = location_features[location]
            
            # Lấy các yếu tố
            base_suitability = features.room_suitability.get(room_type, 0.5)
            area_factor = features.area_ratio
            edge_factor = features.edge_ratio
            connectivity_factor = features.connectivity
            
            # Điều chỉnh theo kích thước phòng
            size_adjustment = 0
            if room.get("size") == "XL" and area_factor < 0.1:
                size_adjustment = -0.3
            elif room.get("size") == "XS" and area_factor > 0.2:
                size_adjustment = -0.2
            
            # Tính điểm tổng hợp
            score = (
                weights["base_suitability"] * base_suitability +
                weights["area_factor"] * (area_factor * (1 + size_adjustment)) +
                weights["edge_factor"] * edge_factor +
                weights["connectivity_factor"] * connectivity_factor
            )
            
            # Chuẩn hóa điểm
            score = max(0, min(1, score))
            
            # Lưu vào ma trận
            score_matrix[i, j] = score
    
    return score_matrix

def add_random_noise(score_matrix: np.ndarray, noise_level: float = 0.05) -> np.ndarray:
    """
    Thêm nhiễu ngẫu nhiên vào ma trận điểm để tránh trùng lặp.
    
    Args:
        score_matrix: Ma trận điểm
        noise_level: Mức độ nhiễu (mặc định: 0.05)
        
    Returns:
        Ma trận điểm có nhiễu
    """
    np.random.seed(42)  # Đảm bảo kết quả ổn định
    noise = np.random.uniform(-noise_level, noise_level, score_matrix.shape)
    noisy_matrix = score_matrix + noise
    
    # Chuẩn hóa lại
    noisy_matrix = np.clip(noisy_matrix, 0, 1)
    
    return noisy_matrix

def get_room_priority_vector(rooms: List[Dict[str, Any]]) -> np.ndarray:
    """
    Tính vector ưu tiên cho các phòng.
    
    Args:
        rooms: Danh sách các phòng
        
    Returns:
        Vector ưu tiên cho các phòng
    """
    from .config import CONNECTION_PRIORITY
    
    priority_vector = np.zeros(len(rooms))
    
    for i, room in enumerate(rooms):
        room_type = extract_room_type(room["name"])
        size_priority = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}.get(room.get("size", "M"), 2)
        connection_priority = CONNECTION_PRIORITY.get(room_type, 5)
        
        # Tính ưu tiên tổng hợp
        priority = connection_priority * 10 + size_priority
        priority_vector[i] = priority
    
    return priority_vector