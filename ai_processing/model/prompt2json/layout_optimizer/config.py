"""
Cấu hình và hằng số cho module tối ưu hóa bố cục.
"""

# Mapping kích thước phòng
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

# Danh sách các vị trí
LOCATIONS = ["north", "northwest", "west", "southwest", "south", "southeast", "east", "northeast", "center"]

# Vị trí liền kề
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

# Phân đoạn theo hướng
SEGMENTS = {
    "east_vertical": ["northeast", "east", "southeast"],
    # Có thể thêm các phân đoạn khác nếu cần
}

# Độ ưu tiên kết nối
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

# Các cặp phòng không tương thích
INCOMPATIBLE_PAIRS = [
    ("Bathroom", "Kitchen"),      
    ("Bathroom", "DiningRoom"),   
    ("Storage", "DiningRoom")     
]

# Các cặp phòng nên đặt liền kề
PREFERRED_PAIRS = [
    ("Kitchen", "DiningRoom"),   
    ("LivingRoom", "Entrance"),   
    ("MasterRoom", "Bathroom"),   
    ("Balcony", "LivingRoom"),    
    ("Balcony", "MasterRoom")     
]

# Giới hạn số lượng kết nối cho mỗi loại phòng
MAX_CONNECTIONS = {
    "XL": 6,  # Phòng cực lớn (LivingRoom)
    "L": 4,   # Phòng lớn (MasterRoom)
    "M": 3,   # Phòng trung bình
    "S": 2,   # Phòng nhỏ
    "XS": 1   # Phòng cực nhỏ (Entrance, Storage)
}

# Trọng số mặc định cho các yếu tố trong tính toán điểm
DEFAULT_WEIGHTS = {
    "base_suitability": 0.5,
    "area_factor": 0.2,
    "edge_factor": 0.15,
    "connectivity_factor": 0.15
}

# Thứ hạng kích thước phòng
ROOM_SIZE_RANKING = {
    "XL": 4,
    "L": 3,
    "M": 2,
    "S": 1,
    "XS": 0
}