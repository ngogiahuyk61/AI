"""
Module phân tích mask để xác định các đặc trưng của từng vị trí.
Sử dụng các phép toán vectorized để tối ưu hiệu năng.
"""
import numpy as np
from PIL import Image
from typing import Dict, List, Tuple, Any
import logging
from scipy import ndimage
from .config import LOCATIONS

logger = logging.getLogger('layout_optimizer.mask_analysis')

class LocationFeatures:
    """Lớp chứa các đặc trưng của một vị trí."""
    def __init__(self, area_ratio=0.0, edge_ratio=0.0, connectivity=0.0, complexity=1.0):
        self.area_ratio = area_ratio
        self.edge_ratio = edge_ratio
        self.connectivity = connectivity
        self.complexity = complexity
        self.room_suitability = {}
    
    def __repr__(self):
        return f"LocationFeatures(area={self.area_ratio:.2f}, edge={self.edge_ratio:.2f}, conn={self.connectivity:.2f})"

def load_and_process_mask(mask_path: str) -> Tuple[np.ndarray, int, int, float, float]:
    """
    Load mask và tính toán centroid sử dụng numpy vectorized operations.
    
    Args:
        mask_path: Đường dẫn đến file mask
        
    Returns:
        binary_mask: Mask nhị phân
        height: Chiều cao của mask
        width: Chiều rộng của mask
        centroid_y: Tọa độ y của centroid
        centroid_x: Tọa độ x của centroid
    """
    try:
        mask = Image.open(mask_path).convert('L')
        mask_array = np.array(mask)
        height, width = mask_array.shape
        
        # Chuyển đổi sang mask nhị phân
        binary_mask = (mask_array < 128).astype(np.uint8)
        
        # Tính centroid
        y_indices, x_indices = np.where(binary_mask > 0)
        if len(y_indices) == 0 or len(x_indices) == 0:
            logger.warning(f"Mask rỗng hoặc toàn đen: {mask_path}")
            return binary_mask, height, width, height/2, width/2
        
        centroid_y = np.mean(y_indices)
        centroid_x = np.mean(x_indices)
        
        return binary_mask, height, width, centroid_y, centroid_x
    
    except Exception as e:
        logger.error(f"Lỗi khi load mask {mask_path}: {e}")
        # Trả về mask rỗng và centroid ở giữa
        return np.zeros((64, 64), dtype=np.uint8), 64, 64, 32, 32

def calculate_region_bounds(height: int, width: int, centroid_y: float, centroid_x: float) -> Tuple[int, int, int, int]:
    """
    Tính toán bounds cho 9 vùng với bounds checking.
    
    Args:
        height: Chiều cao của mask
        width: Chiều rộng của mask
        centroid_y: Tọa độ y của centroid
        centroid_x: Tọa độ x của centroid
        
    Returns:
        h_top: Ranh giới trên
        h_bottom: Ranh giới dưới
        w_left: Ranh giới trái
        w_right: Ranh giới phải
    """
    h_top = max(1, min(height-2, int(centroid_y * 0.7)))
    h_bottom = max(h_top+1, min(height-1, int(height - (height - centroid_y) * 0.7)))
    w_left = max(1, min(width-2, int(centroid_x * 0.7)))
    w_right = max(w_left+1, min(width-1, int(width - (width - centroid_x) * 0.7)))
    
    return h_top, h_bottom, w_left, w_right

def create_location_masks(binary_mask: np.ndarray, h_top: int, h_bottom: int, w_left: int, w_right: int) -> Dict[str, np.ndarray]:
    """
    Tạo mask cho từng vị trí.
    
    Args:
        binary_mask: Mask nhị phân
        h_top, h_bottom, w_left, w_right: Ranh giới các vùng
        
    Returns:
        Dict chứa mask cho từng vị trí
    """
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

def calculate_area_ratios(location_masks: Dict[str, np.ndarray]) -> Dict[str, float]:
    """
    Tính tỷ lệ diện tích cho từng vị trí sử dụng numpy.sum.
    
    Args:
        location_masks: Dict chứa mask cho từng vị trí
        
    Returns:
        Dict chứa tỷ lệ diện tích cho từng vị trí
    """
    location_areas = {loc: np.sum(loc_mask) for loc, loc_mask in location_masks.items()}
    total_area = sum(location_areas.values())
    
    if total_area == 0:
        logger.warning("Tổng diện tích bằng 0, sử dụng phân phối đều")
        return {loc: 1/9 for loc in LOCATIONS}
    
    return {loc: area / total_area for loc, area in location_areas.items()}

def calculate_edge_ratios(location_masks: Dict[str, np.ndarray]) -> Dict[str, float]:
    """
    Tính tỷ lệ cạnh ngoài cho từng vị trí sử dụng convolution.
    
    Args:
        location_masks: Dict chứa mask cho từng vị trí
        
    Returns:
        Dict chứa tỷ lệ cạnh ngoài cho từng vị trí
    """
    edge_ratios = {}
    
    for loc, loc_mask in location_masks.items():
        if loc_mask.size == 0 or np.sum(loc_mask) == 0:
            edge_ratios[loc] = 0
            continue
            
        # Sử dụng convolution để tìm cạnh
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        edges = ndimage.convolve(loc_mask, kernel, mode='constant', cval=0)
        edge_pixels = np.logical_and(loc_mask == 1, edges < 8).sum()
        edge_ratios[loc] = edge_pixels / max(1, np.sum(loc_mask))
    
    # Chuẩn hóa
    max_edge_ratio = max(edge_ratios.values()) if edge_ratios else 1
    if max_edge_ratio > 0:
        edge_ratios = {loc: ratio / max_edge_ratio for loc, ratio in edge_ratios.items()}
    
    return edge_ratios

def calculate_complexity(binary_mask: np.ndarray) -> float:
    """
    Tính chỉ số phức tạp của hình dạng sử dụng tỷ lệ chu vi / diện tích.
    
    Args:
        binary_mask: Mask nhị phân
        
    Returns:
        Chỉ số phức tạp
    """
    # Sử dụng convolution để tìm cạnh
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
    edges = ndimage.convolve(binary_mask, kernel, mode='constant', cval=0)
    perimeter = np.logical_and(binary_mask == 1, edges < 8).sum()
    
    area = np.sum(binary_mask)
    if area > 0:
        # Tỷ lệ chu vi / căn bậc hai của diện tích (chuẩn hóa)
        return perimeter / (2 * np.sqrt(np.pi * area))
    return 1.0

def get_base_room_suitability() -> Dict[str, Dict[str, float]]:
    """
    Định nghĩa độ phù hợp cơ bản của từng loại phòng với từng vị trí.
    
    Returns:
        Dict chứa độ phù hợp cơ bản cho từng loại phòng và vị trí
    """
    suitability = {}
    
    for loc in LOCATIONS:
        suitability[loc] = {}

        # LivingRoom và DiningRoom
        suitability[loc]["LivingRoom"] = 1.0 if loc == "center" else 0.4
        suitability[loc]["DiningRoom"] = 0.8 if loc == "center" else 0.5

        # Các phòng ngủ
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
        
        # Kitchen và DiningRoom
        if loc in ["north", "south", "east", "west"]:
            suitability[loc]["Kitchen"] = 0.9
            suitability[loc]["DiningRoom"] = max(suitability[loc]["DiningRoom"], 0.8)
        else:
            suitability[loc]["Kitchen"] = 0.5

        # Bathroom
        suitability[loc]["Bathroom"] = 0.9 if loc in ["northwest", "northeast", "southwest", "southeast"] else 0.6

        # Balcony
        suitability[loc]["Balcony"] = 0.9 if loc in ["north", "south", "east", "west"] else 0.3

        # Entrance
        suitability[loc]["Entrance"] = 0.9 if loc in ["north", "south", "east", "west"] else 0.4

        # Storage
        suitability[loc]["Storage"] = 0.8 if loc in ["northwest", "northeast", "southwest", "southeast"] else 0.5

        # StudyRoom
        suitability[loc]["StudyRoom"] = 0.7
        
        # CommonRoom
        suitability[loc]["CommonRoom"] = 0.7
    
    return suitability

def adjust_suitability_by_factors(room_suitability: Dict[str, Dict[str, float]], 
                                edge_ratios: Dict[str, float], 
                                area_ratios: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """
    Điều chỉnh độ phù hợp dựa trên edge và area factors.
    
    Args:
        room_suitability: Dict chứa độ phù hợp cơ bản
        edge_ratios: Dict chứa tỷ lệ cạnh ngoài
        area_ratios: Dict chứa tỷ lệ diện tích
        
    Returns:
        Dict chứa độ phù hợp đã điều chỉnh
    """
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

def analyze_mask(mask_path: str) -> Dict[str, LocationFeatures]:
    """
    Phân tích mask để xác định thông tin các vị trí.
    
    Args:
        mask_path: Đường dẫn đến file mask
        
    Returns:
        Dict chứa thông tin các vị trí
    """
    try:
        # Load và xử lý mask
        binary_mask, height, width, centroid_y, centroid_x = load_and_process_mask(mask_path)
        
        if height <= 2 or width <= 2:
            logger.warning(f"Mask quá nhỏ: {height}x{width}")
            return {loc: LocationFeatures(1/9, 0.5, 0.5, 1.0) for loc in LOCATIONS}
        
        # Tính toán ranh giới các vùng
        h_top, h_bottom, w_left, w_right = calculate_region_bounds(height, width, centroid_y, centroid_x)
        
        # Tạo mask cho từng vị trí
        location_masks = create_location_masks(binary_mask, h_top, h_bottom, w_left, w_right)
        
        # Tính toán các đặc trưng
        area_ratios = calculate_area_ratios(location_masks)
        edge_ratios = calculate_edge_ratios(location_masks)
        complexity = calculate_complexity(binary_mask)
        
        # Điều chỉnh area_ratios dựa trên complexity
        if complexity > 1.2:
            max_ratio = max(area_ratios.values())
            for loc in area_ratios:
                if area_ratios[loc] > 0.7 * max_ratio:
                    area_ratios[loc] *= 1.2
            
            total_ratio = sum(area_ratios.values())
            area_ratios = {loc: ratio / total_ratio for loc, ratio in area_ratios.items()}
        
        # Định nghĩa connectivity
        connectivity = {
            "center": 1.0,
            "north": 0.8, "south": 0.8, "east": 0.8, "west": 0.8,
            "northwest": 0.6, "northeast": 0.6, "southwest": 0.6, "southeast": 0.6
        }
        
        # Tính toán room_suitability
        room_suitability = get_base_room_suitability()
        room_suitability = adjust_suitability_by_factors(room_suitability, edge_ratios, area_ratios)
        
        # Tổng hợp kết quả
        result = {}
        for loc in LOCATIONS:
            features = LocationFeatures(
                area_ratio=area_ratios.get(loc, 0),
                edge_ratio=edge_ratios.get(loc, 0),
                connectivity=connectivity.get(loc, 0.5),
                complexity=complexity
            )
            features.room_suitability = room_suitability.get(loc, {})
            result[loc] = features
        
        return result
    
    except Exception as e:
        logger.error(f"Lỗi khi phân tích mask: {e}")
        return {loc: LocationFeatures(1/9, 0.5, 0.5, 1.0) for loc in LOCATIONS}