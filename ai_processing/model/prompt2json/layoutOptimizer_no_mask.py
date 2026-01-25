import json
import random
from typing import Dict, List

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


def assign_room_sizes(rooms: List[Dict]) -> List[Dict]:
    for room in rooms:
        room_type = room["name"].split("_")[0]
        if room_type in ROOM_SIZE_MAPPING:
            room["size"] = ROOM_SIZE_MAPPING[room_type]
        else:
            room["size"] = "M"
    return rooms

def assign_room_locations(rooms: List[Dict], location_ratios: Dict[str, float]) -> List[Dict]:
    sorted_locations = sorted(location_ratios.items(), key=lambda x: x[1], reverse=True)
    size_order = {"XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
    sorted_rooms = sorted(rooms, key=lambda x: size_order.get(x.get("size", "M"), 2), reverse=True)
    assigned_locations = set()

    for room in sorted_rooms:
        if "LivingRoom" in room["name"]:
            room["location"] = "center"
            assigned_locations.add("center")
            break

    for room in sorted_rooms:
        if "location" in room and room["location"] != "Unknown":
            assigned_locations.add(room["location"])
            continue

        for location, _ in sorted_locations:
            if location not in assigned_locations:
                room["location"] = location
                assigned_locations.add(location)
                break

        if "location" not in room or room["location"] == "Unknown":
            available_locations = [loc for loc in LOCATIONS if loc not in assigned_locations]
            if available_locations:
                room["location"] = random.choice(available_locations)
                assigned_locations.add(room["location"])
            else:
                room_type = room["name"].split("_")[0]
                similar_rooms = [r for r in rooms if r["name"].split("_")[0] == room_type and r != room and "location" in r]
                similar_locations = [r["location"] for r in similar_rooms]
                for location, _ in sorted_locations:
                    if location not in similar_locations:
                        room["location"] = location
                        break
                else:
                    room["location"] = random.choice(LOCATIONS)
    return sorted_rooms

def create_room_links(rooms: List[Dict]) -> List[Dict]:
    living_room = next((r for r in rooms if "LivingRoom" in r["name"]), None)
    if not living_room and rooms:
        living_room = rooms[0]

    for room in rooms:
        room["link"] = []

    if living_room:
        living_room_links = [r["name"] for r in rooms if r["name"] != living_room["name"]]
        living_room["link"] = [living_room_links]
        for room in rooms:
            if room["name"] != living_room["name"]:
                room["link"] = [[living_room["name"]]]

    for room in rooms:
        if room.get("location") not in ADJACENT_LOCATIONS:
            continue
        adjacent_locations = ADJACENT_LOCATIONS[room["location"]]
        potential_links = [other for other in rooms if room["name"] != other["name"] and other.get("location") in adjacent_locations]

        if "Balcony" in room["name"]:
            priority_rooms = [p for p in potential_links if any(pr in p["name"] for pr in ["MasterRoom", "SecondRoom", "LivingRoom"])]
            if priority_rooms:
                for pr in priority_rooms:
                    if pr["name"] not in room["link"][0]:
                        room["link"][0].append(pr["name"])
                    if pr.get("link") and room["name"] not in pr["link"][0]:
                        pr["link"][0].append(room["name"])
        else:
            for other in potential_links:
                if living_room and other["name"] == living_room["name"]:
                    continue
                if other["name"] not in room["link"][0]:
                    room["link"][0].append(other["name"])

    for room in rooms:
        if "Balcony" in room["name"]:
            if living_room and len(room["link"][0]) == 1 and room["link"][0][0] == living_room["name"]:
                balcony_location = room.get("location")
                adjacent_locations = ADJACENT_LOCATIONS.get(balcony_location, [])
                for other_room in rooms:
                    if other_room.get("location") in adjacent_locations and other_room["name"] != living_room["name"]:
                        room["link"][0].append(other_room["name"])
                        if other_room.get("link") and room["name"] not in other_room["link"][0]:
                            other_room["link"][0].append(room["name"])
                        break
    return rooms

def optimize_layout(json_data: Dict) -> Dict:
    """
    Tối ưu hóa bố cục mà KHÔNG cần phân tích mask.
    """
    # Luôn sử dụng tỷ lệ mặc định vì không phân tích mask
    location_ratios = {loc: 1/9 for loc in LOCATIONS}
    
    rooms = []
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            room = room_data["rooms"][i]
            rooms.append(room)
    
    rooms = assign_room_sizes(rooms)
    rooms = assign_room_locations(rooms, location_ratios)
    rooms = create_room_links(rooms)
    
    for room_type, room_data in json_data.items():
        for i in range(room_data["num"]):
            for room in rooms:
                if room["name"] == room_data["rooms"][i]["name"]:
                    room_data["rooms"][i] = room
                    break
    return json_data

def process_simple_input(input_text: str) -> Dict:
    """
    Xử lý input đơn giản và tạo JSON hoàn chỉnh (không cần mask).
    """
    rooms = []
    room_counts = {}
    
    for item in input_text.split(','):
        item = item.strip().lower()
        if not item:
            continue
        
        num = 1
        num_match = [c for c in item if c.isdigit()]
        if num_match:
            num = int(''.join(num_match))
        
        room_type = item.replace(str(num), '').strip()
        
        type_mapping = {
            "living": "LivingRoom", "master": "MasterRoom", "kitchen": "Kitchen",
            "bath": "Bathroom", "dining": "DiningRoom", "common": "CommonRoom",
            "second": "SecondRoom", "child": "ChildRoom", "study": "StudyRoom",
            "guest": "GuestRoom", "balcony": "Balcony", "entrance": "Entrance",
            "storage": "Storage"
        }
        
        final_room_type = room_type.title().replace(' ', '')
        for key, value in type_mapping.items():
            if key in room_type:
                final_room_type = value
                break
        
        rooms.append({"name": final_room_type, "num": num})
        if final_room_type not in room_counts:
            room_counts[final_room_type] = 0
        room_counts[final_room_type] += num
    
    json_data = {}
    for room in rooms:
        room_type = room["name"]
        room_list = []
        for i in range(room["num"]):
            room_name = f"{room_type}_{i+1}" if room_counts[room_type] > 1 else room_type
            room_list.append({
                "name": room_name, "link": [], "location": "Unknown", "size": "Unknown"
            })
        json_data[room_type] = {"num": room["num"], "rooms": room_list}
    
    optimized_json = optimize_layout(json_data)
    
    return optimized_json
