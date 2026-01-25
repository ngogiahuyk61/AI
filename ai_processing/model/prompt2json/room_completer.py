"""
Module để bổ sung thông tin đầy đủ cho JSON output
Đảm bảo tất cả các loại phòng đều có mặt trong kết quả, kể cả những phòng không được đề cập
"""

from typing import Dict, List

# Danh sách đầy đủ tất cả các loại phòng có thể có (theo thứ tự cố định)
ALL_ROOM_TYPES = [
    "LivingRoom",
    "MasterRoom", 
    "Kitchen",
    "Bathroom",
    "DiningRoom",
    "ChildRoom",
    "StudyRoom",
    "SecondRoom",
    "GuestRoom",
    "Balcony",
    "Entrance",
    "Storage"
]

def normalize_link_format(json_data: Dict) -> Dict:
    for room_type, room_data in json_data.items():
        if "rooms" in room_data:
            for room in room_data["rooms"]:
                if "link" in room:
                    if isinstance(room["link"], list) and len(room["link"]) > 0:
                        if isinstance(room["link"][0], list):
                            room["link"] = room["link"][0]
                        elif not isinstance(room["link"], list):
                            room["link"] = []
    
    return json_data

def complete_room_data(json_data: Dict) -> Dict:
    """Bổ sung thông tin đầy đủ cho JSON data với thứ tự cố định"""
    from collections import OrderedDict
    completed_data = OrderedDict()

    for room_type in ALL_ROOM_TYPES:
        if room_type in json_data:
            completed_data[room_type] = json_data[room_type]
        else:
            completed_data[room_type] = {
                "num": 0,
                "rooms": []
            }
    
    return completed_data

def ensure_complete_room_structure(json_data: Dict) -> Dict:
    normalized_data = normalize_link_format(json_data)
    return complete_room_data(normalized_data)

def get_all_room_types() -> List[str]:
    return ALL_ROOM_TYPES.copy()

def validate_room_structure(json_data: Dict) -> bool:
    for room_type in ALL_ROOM_TYPES:
        if room_type not in json_data:
            return False

        room_data = json_data[room_type]
        if not isinstance(room_data, dict):
            return False
        if "num" not in room_data or "rooms" not in room_data:
            return False
        if not isinstance(room_data["num"], int):
            return False
        if not isinstance(room_data["rooms"], list):
            return False
    
    return True

def print_room_summary(json_data: Dict) -> None:
    print("\n📋 Room Summary:")
    print("=" * 50)
    
    total_rooms = 0
    rooms_with_data = 0
    empty_rooms = 0
    
    for room_type in ALL_ROOM_TYPES:
        if room_type in json_data:
            num_rooms = json_data[room_type]["num"]
            total_rooms += num_rooms
            
            if num_rooms > 0:
                rooms_with_data += 1
                print(f"✅ {room_type}: {num_rooms} phòng")
            else:
                empty_rooms += 1
                print(f"⭕ {room_type}: 0 phòng (trống)")
        else:
            empty_rooms += 1
            print(f"❌ {room_type}: Thiếu thông tin")
    
    print("=" * 50)
    print(f"📊 Tổng số phòng có dữ liệu: {total_rooms}")
    print(f"📊 Loại phòng có dữ liệu: {rooms_with_data}")
    print(f"📊 Loại phòng trống: {empty_rooms}")
    print(f"📊 Tổng loại phòng: {len(ALL_ROOM_TYPES)}")

# Ví dụ sử dụng
if __name__ == "__main__":
    # Test với dữ liệu mẫu
    sample_data = {
        "LivingRoom": {
            "num": 1,
            "rooms": [
                {
                    "name": "LivingRoom1",
                    "link": ["MasterRoom1", "Kitchen1"],
                    "location": "center",
                    "size": "XL"
                }
            ]
        },
        "MasterRoom": {
            "num": 1,
            "rooms": [
                {
                    "name": "MasterRoom1",
                    "link": ["LivingRoom1"],
                    "location": "southwest",
                    "size": "L"
                }
            ]
        },
        "Kitchen": {
            "num": 1,
            "rooms": [
                {
                    "name": "Kitchen1",
                    "link": ["LivingRoom1"],
                    "location": "north",
                    "size": "M"
                }
            ]
        }
    }
    
    print("Dữ liệu gốc:")
    print_room_summary(sample_data)
    
    print("\nSau khi bổ sung:")
    completed_data = complete_room_data(sample_data)
    print_room_summary(completed_data)
    
    print(f"\nKiểm tra cấu trúc: {validate_room_structure(completed_data)}")
