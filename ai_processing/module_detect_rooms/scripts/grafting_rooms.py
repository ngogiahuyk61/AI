import cv2
import numpy as np
import json
import os
from collections import Counter

TYPE_DISPLAY_MAP = {
    "masterroom": "Bedroom",
    "commonroom": "Bedroom",
    "bathroom": "Bathroom",
    "storage": "Storage",
    "balcony": "Balcony",
    "entrance": "Entrance",
    "livingroom": "livingroom_1",
    "unknownroom": "Unknown Room",
}

COMMON_ROOM_SEQUENCE = [
    "StudyRoom",
    "GuestRoom",
    "SecondRoom",
    "ChildRoom",
]


def _normalize_key(name: str) -> str:
    return (name or "").replace(" ", "").replace("_", "").lower()


def _parse_room_type(name: str):
    safe_name = (name or "").replace(" ", "_")
    parts = safe_name.split("_")
    if parts and parts[-1].isdigit():
        return "_".join(parts[:-1]), int(parts[-1])
    return safe_name, None


def _load_request_info():
    request_path = os.getenv("REQUEST_JSON")
    if not request_path:
        print("   ⚠️ REQUEST_JSON not set. Using fallback naming logic.")
        return {}

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    base_dir = script_dir
    if "scripts" in script_dir.lower():
        base_dir = os.path.dirname(script_dir)
    elif not os.path.exists(os.path.join(base_dir, "outputs")):
        base_dir = os.path.dirname(script_dir)
        if not os.path.exists(os.path.join(base_dir, "outputs")):
            base_dir = os.path.dirname(base_dir)

    if not os.path.isabs(request_path):
        script_relative = os.path.join(script_dir, request_path)
        base_relative = os.path.join(base_dir, request_path)
        inputs_relative = os.path.join(base_dir, "inputs", os.path.basename(request_path))
        if os.path.exists(script_relative):
            request_path = script_relative
        elif os.path.exists(base_relative):
            request_path = base_relative
        elif os.path.exists(inputs_relative):
            request_path = inputs_relative
        else:
            print(f"   ❌ Cannot find request JSON at '{request_path}'.")
            return {}

    try:
        with open(request_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"   ✅ Loaded request metadata from: {request_path}")
            return data
    except Exception as exc:  # pylint: disable=broad-except
        print(f"   ❌ Failed to read request JSON: {exc}")
        return {}


def _build_common_queue(metadata: dict) -> list[str]:
    queue: list[str] = []
    if not metadata:
        return queue

    study_count = metadata.get("StudyRoom", {}).get("num", 0)
    queue.extend(["StudyRoom"] * max(study_count, 0))

    guest_count = metadata.get("GuestRoom", {}).get("num", 0)
    queue.extend(["Japan_Style_Room"] * max(guest_count, 0))

    second_count = metadata.get("SecondRoom", {}).get("num", 0)
    queue.extend([f"Bedroom_Second_{i + 1}" for i in range(max(second_count, 0))])

    child_count = metadata.get("ChildRoom", {}).get("num", 0)
    queue.extend([f"Bedroom_Child_{i + 1}" for i in range(max(child_count, 0))])

    print(f"   → Common room queue: {queue}")
    return queue


def _resolve_display_base(original_name: str) -> str:
    base_type, _ = _parse_room_type(original_name)
    normalized = _normalize_key(base_type)
    mapped = TYPE_DISPLAY_MAP.get(normalized)
    if mapped:
        return mapped
    return base_type.replace("_", " ").title() if base_type else "Room"


def _format_requested_names(entries: list[dict]) -> list[str]:
    formatted = []
    for entry in entries or []:
        raw_name = entry.get("name")
        if raw_name:
            formatted.append(raw_name.replace("_", " "))
    return formatted


def _apply_request_names(rooms: list[dict], request_info: dict):
    print("\n🏷️ Applying metadata-based room names...")
    if not rooms:
        return rooms, {}

    common_queue = _build_common_queue(request_info)
    common_index = 0

    bathroom_requested = _format_requested_names(request_info.get("Bathroom", {}).get("rooms", []))
    storage_requested = _format_requested_names(request_info.get("Storage", {}).get("rooms", []))

    master_candidates, common_rooms, bathroom_rooms = [], [], []
    storage_rooms, balcony_rooms, living_rooms, other_rooms = [], [], [], []

    for room in rooms:
        original = room.get("original_name") or room.get("name", "")
        normalized = _normalize_key(original)

        if normalized.startswith("masterroom"):
            master_candidates.append(room)
        elif normalized.startswith("commonroom"):
            common_rooms.append(room)
        elif normalized.startswith("bathroom"):
            bathroom_rooms.append(room)
        elif normalized.startswith("livingroom"):
            living_rooms.append(room)
        elif normalized.startswith("storage"):
            storage_rooms.append(room)
        elif normalized.startswith("balcony"):
            balcony_rooms.append(room)
        else:
            other_rooms.append(room)

    processed_ids = set()

    def _mark_processed(room_obj, new_name: str):
        room_obj['name'] = new_name
        processed_ids.add(id(room_obj))

    # Master / Bedroom ordering
    master_room = None
    if master_candidates:
        master_room = max(master_candidates, key=lambda r: r.get('area', 0))
    elif common_rooms:
        master_room = max(common_rooms, key=lambda r: r.get('area', 0))
        common_rooms.remove(master_room)

    if master_room:
        if master_room in master_candidates:
            master_candidates.remove(master_room)
        _mark_processed(master_room, "Bedroom_1")
        bedroom_index = 2
    else:
        bedroom_index = 1

    # Treat additional master candidates as common stock
    if master_candidates:
        common_rooms.extend(master_candidates)

    common_rooms.sort(key=lambda r: r.get('area', 0))

    for room in common_rooms:
        if common_index < len(common_queue):
            token = common_queue[common_index]
            common_index += 1
        else:
            token = None

        if token == "StudyRoom":
            assigned_name = "Study_Room"
        elif token == "Japan_Style_Room":
            assigned_name = "Japan_Style_Room"
        else:
            assigned_name = f"Bedroom_{bedroom_index}"
            bedroom_index += 1
        _mark_processed(room, assigned_name)

    bathroom_rooms.sort(key=lambda r: (r.get('center', [0, 0])[0], r.get('center', [0, 0])[1]))
    for idx, room in enumerate(bathroom_rooms):
        if idx < len(bathroom_requested):
            assigned_name = bathroom_requested[idx]
        else:
            assigned_name = f"Bathroom {idx + 1}"
        _mark_processed(room, assigned_name)

    storage_rooms.sort(key=lambda r: r.get('area', 0), reverse=True)
    for idx, room in enumerate(storage_rooms):
        if idx < len(storage_requested):
            assigned_name = storage_requested[idx]
        else:
            assigned_name = "Storage" if len(storage_rooms) == 1 else f"Storage {idx + 1}"
        _mark_processed(room, assigned_name)

    for room in balcony_rooms:
        if id(room) in processed_ids:
            continue
        base_display = _resolve_display_base(room.get("original_name"))
        _mark_processed(room, base_display)

    display_counters = Counter()

    for room in rooms:
        if id(room) in processed_ids:
            continue
        original = room.get("original_name") or room.get("name", "")
        normalized = _normalize_key(original)
        if normalized.startswith("livingroom"):
            processed_ids.add(id(room))
            continue
        base_display = _resolve_display_base(original)
        display_counters[base_display] += 1
        count = display_counters[base_display]
        if count == 1:
            assigned_name = base_display
        else:
            separator = "_" if "_" in base_display else " "
            assigned_name = f"{base_display}{separator}{count}"
        _mark_processed(room, assigned_name)

    type_counter = Counter()
    for room in rooms:
        name_parts = room.get('name', '').replace('_', ' ').split()
        base = name_parts[0] if name_parts else 'Room'
        type_counter[base] += 1

    print(f"   ✅ Applied metadata naming. Final summary: {dict(type_counter)}")
    return rooms, dict(type_counter)

def get_mask_center(mask):
    M = cv2.moments(mask)
    if M["m00"] == 0: return None
    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
def create_edges_from_corners(corners):
    edges = []
    n = len(corners)
    for i in range(n):
        p1, p2 = corners[i], corners[(i + 1) % n]
        edges.append([int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])])
    return edges
def extract_exterior_walls_advanced(image_path, padding=20):
    print(f"\nAnalyzing complex exterior walls from: {os.path.basename(image_path)}...")
    image = cv2.imread(image_path)
    if image is None:
        print("   ❌ Error: Could not read exterior wall image."); return [], None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    kernel_size = padding * 2 + 1
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    dilated_mask = cv2.dilate(thresh, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("   → No exterior walls detected."); return [], None
    main_contour = max(contours, key=cv2.contourArea)
    epsilon = 0.005 * cv2.arcLength(main_contour, True)
    approx_contour = cv2.approxPolyDP(main_contour, epsilon, True)
    points = approx_contour.reshape(-1, 2)
    def cluster_coords(coords, threshold=15):
        coords = sorted(list(set(coords)))
        if not coords: return []
        clusters = [[coords[0]]]
        for coord in coords[1:]:
            if coord - clusters[-1][-1] < threshold:
                clusters[-1].append(coord)
            else:
                clusters.append([coord])
        return [int(np.mean(c)) for c in clusters]
    x_clusters = cluster_coords(points[:, 0])
    y_clusters = cluster_coords(points[:, 1])
    snapped_points = []
    for x, y in points:
        snapped_x = min(x_clusters, key=lambda c: abs(c - x))
        snapped_y = min(y_clusters, key=lambda c: abs(c - y))
        snapped_points.append([snapped_x, snapped_y])
    exterior_edges = []
    unique_points = []
    [unique_points.append(p) for p in snapped_points if p not in unique_points]
    for i in range(len(unique_points)):
        p1 = unique_points[i - 1]
        p2 = unique_points[i]
        exterior_edges.append([p1[0], p1[1], p2[0], p2[1]])
    print(f"   → Found, expanded, and snapped complex shape to 90-degree angles.")
    return exterior_edges, np.array(unique_points, dtype=np.int32)
def extract_exterior_walls_simple(image_path):
    """
    Trích xuất các cạnh tường ngoại thất một cách CHÍNH XÁC mà không
    cần đơn giản hóa, làm thẳng hay nắn góc.
    """
    print(f"\n✅ Extracting PRECISE exterior walls from: {os.path.basename(image_path)}...")
    image = cv2.imread(image_path)
    if image is None:
        print("   ❌ Error: Could not read exterior wall image.")
        return [], None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("   → No exterior walls detected."); return [], None
    main_contour = max(contours, key=cv2.contourArea)
    polygon_points = main_contour.reshape(-1, 2).astype(np.int32)
    exterior_edges = []
    n = len(polygon_points)
    for i in range(n):
        p1 = polygon_points[i]
        p2 = polygon_points[(i + 1) % n]
        exterior_edges.append([int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])])
    print(f"   ✅ Extracted {len(polygon_points)} precise points for the exterior wall.")
    return exterior_edges, polygon_points
def detect_corners_90(mask, min_angle=70, max_angle=110, epsilon_factor=0.015):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours: return []
    cnt = max(contours, key=cv2.contourArea)
    epsilon = epsilon_factor * cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, epsilon, True)
    corners = []
    n = len(approx)
    for i in range(n):
        p2, p1, p3 = approx[i][0], approx[i - 1][0], approx[(i + 1) % n][0]
        v1, v2 = p1 - p2, p3 - p2
        norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm_product == 0: continue
        cos_angle = np.clip(np.dot(v1, v2) / norm_product, -1.0, 1.0)
        angle_deg = np.degrees(np.arccos(cos_angle))
        if min_angle <= angle_deg <= max_angle:
            corners.append({'point': tuple(p2.astype(int)), 'angle': float(angle_deg)})
    return corners
def snap_to_rectangle(corners):
    if len(corners) < 2: return None
    pts = np.array([c['point'] for c in corners])
    x_left, y_top = np.min(pts, axis=0)
    x_right, y_bottom = np.max(pts, axis=0)
    return [(x_left, y_top), (x_right, y_top), (x_right, y_bottom), (x_left, y_bottom)]
def split_color_into_rooms(mask, min_area=100):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    room_masks = []
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            component_mask = np.zeros_like(mask); component_mask[labels == i] = 255
            room_masks.append(component_mask)
    return room_masks
def process_room(mask, color, room_id, room_name=None):
    corners = detect_corners_90(mask)
    if not corners: return None
    rect_corners = snap_to_rectangle(corners)
    if not rect_corners or len(rect_corners) != 4: return None
    x_left, y_top = np.min(rect_corners, axis=0)
    x_right, y_bottom = np.max(rect_corners, axis=0)
    bbox = [int(x_left), int(y_top), int(x_right - x_left), int(y_bottom - y_top)]
    area = int(cv2.countNonZero(mask))
    resolved_name = room_name or f'room_{room_id}'
    return {
        'id': room_id,
        'name': resolved_name,
        'original_name': resolved_name,
        'color': color,
        'center': get_mask_center(mask),
        'snapped_corners': rect_corners,
        'edges': create_edges_from_corners(rect_corners),
        'bounding_box': bbox,
        'area': area
    }
def merge_adjacent_edges_final(rooms, max_distance=30, angle_tolerance=5):
    print(f"\n🔄 Merging rooms ('Snap & Resize' Logic)...")
    shared_edges, merge_info, processed_pairs = [], [], set()
    def edge_length(e):
        """Calculate the length of an edge."""
        return np.sqrt((e[2] - e[0])**2 + (e[3] - e[1])**2)
    def edge_angle(e):
        """Calculate the angle of an edge in degrees (-180 to 180)."""
        return np.degrees(np.arctan2(e[3] - e[1], e[2] - e[0]))
    def is_vertical(angle, tolerance=angle_tolerance):
        """Check if an edge is vertical within the given tolerance."""
        return abs(abs(angle) - 90) < tolerance
    def is_horizontal(angle, tolerance=angle_tolerance):
        """Check if an edge is horizontal within the given tolerance."""
        return abs(angle) < tolerance or abs(abs(angle) - 180) < tolerance
    def edges_are_parallel(angle1, angle2, tolerance=angle_tolerance):
        """Check if two edges are parallel within the given tolerance."""
        diff = abs((angle1 - angle2 + 180) % 180)
        return diff < tolerance or abs(diff - 180) < tolerance
    def edges_overlap(edge1, edge2, is_vertical):
        """Check if two edges overlap along their length."""
        if is_vertical:
            y_min1, y_max1 = sorted((edge1[1], edge1[3]))
            y_min2, y_max2 = sorted((edge2[1], edge2[3]))
            overlap = max(y_min1, y_min2) < min(y_max1, y_max2)
        else:
            x_min1, x_max1 = sorted((edge1[0], edge1[2]))
            x_min2, x_max2 = sorted((edge2[0], edge2[2]))
            overlap = max(x_min1, x_min2) < min(x_max1, x_max2)
        return overlap
    def edge_distance(edge1, edge2, is_vertical):
        """Calculate the minimum distance between two edges."""
        if is_vertical:
            dist = abs(edge1[0] - edge2[0])
        else:
            dist = abs(edge1[1] - edge2[1])
        return dist
    def merge_edges(master_room, slave_room, master_edge, slave_edge, is_vertical):
        """Merge edges between two rooms by aligning the slave edge to the master edge."""
        if is_vertical:
            master_pos = master_edge[0]
            slave_pos = slave_edge[0]
            new_corners = [(master_pos if abs(x - slave_pos) < 1 else x, y) 
                           for x, y in slave_room['snapped_corners']]
            edge_type = 'vertical'
        else:
            master_pos = master_edge[1]
            slave_pos = slave_edge[1]
            new_corners = [(x, master_pos if abs(y - slave_pos) < 1 else y) 
                           for x, y in slave_room['snapped_corners']]
            edge_type = 'horizontal'
        old_corners = slave_room['snapped_corners']
        slave_room['snapped_corners'] = new_corners
        slave_room['edges'] = create_edges_from_corners(new_corners)
        print(f"   🔄 Merged {edge_type} edges: "
              f"{slave_room['name']} → {master_room['name']} "
              f"(distance: {edge_distance(master_edge, slave_edge, is_vertical):.1f}px)")
        return slave_room
    rooms_with_meta = [(i, room, room.get('area', 0), len(room.get('edges', []))) 
                       for i, room in enumerate(rooms)]
    rooms_with_meta.sort(key=lambda x: (-x[2], -x[3]))
    room_index = {room['name']: i for i, room in enumerate(rooms)}
    for i, (i_idx, room_a, area_a, _) in enumerate(rooms_with_meta):
        for j, (j_idx, room_b, area_b, _) in enumerate(rooms_with_meta[i+1:], i+1):
            pair_key = tuple(sorted((room_a['name'], room_b['name'])))
            if pair_key in processed_pairs:
                continue
            if area_a > area_b or (area_a == area_b and len(room_a.get('edges', [])) > len(room_b.get('edges', []))):
                master_room, slave_room = room_a, room_b
            else:
                master_room, slave_room = room_b, room_a
            for e1 in master_room['edges']:
                angle1 = edge_angle(e1)
                if not is_vertical(angle1):
                    continue
                for e2 in slave_room['edges']:
                    angle2 = edge_angle(e2)
                    if not is_vertical(angle2):
                        continue
                    if not edges_are_parallel(angle1, angle2):
                        continue
                    dist = edge_distance(e1, e2, is_vertical=True)
                    if dist > max_distance:
                        continue
                    if not edges_overlap(e1, e2, is_vertical=True):
                        continue
                    slave_room = merge_edges(master_room, slave_room, e1, e2, is_vertical=True)
                    processed_pairs.add(pair_key)
                    merge_info.append({
                        'master': master_room['name'],
                        'slave': slave_room['name'],
                        'type': 'vertical',
                        'distance': dist
                    })
                    break
                if pair_key in processed_pairs:
                    break
    for i, (i_idx, room_a, area_a, _) in enumerate(rooms_with_meta):
        for j, (j_idx, room_b, area_b, _) in enumerate(rooms_with_meta[i+1:], i+1):
            pair_key = tuple(sorted((room_a['name'], room_b['name'])))
            if pair_key in processed_pairs:
                continue
            if area_a > area_b or (area_a == area_b and len(room_a.get('edges', [])) > len(room_b.get('edges', []))):
                master_room, slave_room = room_a, room_b
            else:
                master_room, slave_room = room_b, room_a
            for e1 in master_room['edges']:
                angle1 = edge_angle(e1)
                if not is_horizontal(angle1):
                    continue
                for e2 in slave_room['edges']:
                    angle2 = edge_angle(e2)
                    if not is_horizontal(angle2):
                        continue
                    if not edges_are_parallel(angle1, angle2):
                        continue
                    dist = edge_distance(e1, e2, is_vertical=False)
                    if dist > max_distance:
                        continue
                    if not edges_overlap(e1, e2, is_vertical=False):
                        continue
                    slave_room = merge_edges(master_room, slave_room, e1, e2, is_vertical=False)
                    processed_pairs.add(pair_key)
                    merge_info.append({
                        'master': master_room['name'],
                        'slave': slave_room['name'],
                        'type': 'horizontal',
                        'distance': dist
                    })
                    break
                if pair_key in processed_pairs:
                    break
    return rooms, shared_edges, merge_info
def analyze_exterior_facing_edges(rooms, exterior_edges, threshold=60):
    print("\n🔎 Analyzing exterior-facing edges...")
    total_exterior_edges = 0
    def edge_angle(e): return np.degrees(np.arctan2(e[3] - e[1], e[2] - e[0]))
    def is_horizontal(angle): return abs(angle) < 45 or abs(angle) > 135
    for room in rooms:
        room['exterior_facing'] = []
        center_x, center_y = room['center']
        for r_edge in room['edges']:
            is_exterior = False
            for ext_edge in exterior_edges:
                if abs((edge_angle(r_edge) - edge_angle(ext_edge) + 180) % 180) < 5:
                    if is_horizontal(edge_angle(r_edge)):
                        dist = abs(r_edge[1] - ext_edge[1])
                        r_min, r_max = sorted((r_edge[0], r_edge[2]))
                        ext_min, ext_max = sorted((ext_edge[0], ext_edge[2]))
                        overlap = max(0, min(r_max, ext_max) - max(r_min, ext_min))
                    else:
                        dist = abs(r_edge[0] - ext_edge[0])
                        r_min, r_max = sorted((r_edge[1], r_edge[3]))
                        ext_min, ext_max = sorted((ext_edge[1], ext_edge[3]))
                        overlap = max(0, min(r_max, ext_max) - max(r_min, ext_min))
                    if dist < threshold and overlap > 10: is_exterior = True; break
            if is_exterior:
                direction = 'top' if is_horizontal(edge_angle(r_edge)) and r_edge[1] < center_y else 'bottom' if is_horizontal(edge_angle(r_edge)) else 'left' if r_edge[0] < center_x else 'right'
                room['exterior_facing'].append(direction)
        if room['exterior_facing']:
            print(f"   → {room['name']}: Found {len(room['exterior_facing'])} exterior edge(s) ({', '.join(sorted(room['exterior_facing']))})")
            total_exterior_edges += len(room['exterior_facing'])
    print(f"   ✅ Total exterior-facing room edges found: {total_exterior_edges}")
def stretch_rooms_to_exterior(rooms, exterior_edges, max_stretch=100):
    print("\n↔️ Stretching exterior-facing rooms to outer walls...")
    def is_horizontal(edge): 
        return edge[1] == edge[3]
    def get_room_bounds(corners):
        x_coords = [c[0] for c in corners]
        y_coords = [c[1] for c in corners]
        return min(x_coords), min(y_coords), max(x_coords), max(y_coords)
    room_polys = {}
    for room in rooms:
        if 'snapped_corners' in room and room['snapped_corners']:
            room_polys[room['name']] = np.array(room['snapped_corners'], dtype=np.int32)
    for room in rooms:
        if 'exterior_facing' not in room or not room['exterior_facing']:
            continue
        room_name = room.get('name', 'unknown')
        print(f"   → Stretching {room_name}...")
        if 'snapped_corners' not in room or not room['snapped_corners']:
            print(f"     ⚠️ No valid polygon for {room_name}")
            continue
        current_corners = np.array(room['snapped_corners'], dtype=np.int32)
        new_corners = current_corners.copy()
        for direction in room['exterior_facing']:
            if f"stretched_{direction}" in room:
                continue
            target_pos = None
            min_x, min_y, max_x, max_y = get_room_bounds(current_corners)
            if direction == 'top':
                candidates = [e for e in exterior_edges 
                              if is_horizontal(e) and e[1] < min_y]
                if candidates:
                    target_pos = max(e[1] for e in candidates)
            elif direction == 'bottom':
                candidates = [e for e in exterior_edges 
                              if is_horizontal(e) and e[1] > max_y]
                if candidates:
                    target_pos = min(e[1] for e in candidates)
            elif direction == 'left':
                candidates = [e for e in exterior_edges 
                              if not is_horizontal(e) and e[0] < min_x]
                if candidates:
                    target_pos = max(e[0] for e in candidates)
            elif direction == 'right':
                candidates = [e for e in exterior_edges 
                              if not is_horizontal(e) and e[0] > max_x]
                if candidates:
                    target_pos = min(e[0] for e in candidates)
            if target_pos is None:
                print(f"     ⚠️ No target position found for {direction} edge of {room_name}")
                continue
            if direction in ['top', 'bottom']:
                axis = 1  
                is_max = (direction == 'bottom')
                current_val = max(current_corners[:, axis]) if is_max else min(current_corners[:, axis])
                delta = target_pos - current_val
                if abs(delta) > max_stretch:
                    print(f"     ⚠️ Stretch too large ({abs(delta)}px) for {room_name} {direction} edge")
                    continue
                if is_max:
                    mask = (new_corners[:, axis] == current_val)
                    new_corners[mask, axis] = target_pos
                else:
                    mask = (new_corners[:, axis] == current_val)
                    new_corners[mask, axis] = target_pos
            else:  
                axis = 0  
                is_max = (direction == 'right')
                current_val = max(current_corners[:, axis]) if is_max else min(current_corners[:, axis])
                delta = target_pos - current_val
                if abs(delta) > max_stretch:
                    print(f"     ⚠️ Stretch too large ({abs(delta)}px) for {room_name} {direction} edge")
                    continue
                if is_max:
                    mask = (new_corners[:, axis] == current_val)
                    new_corners[mask, axis] = target_pos
                else:
                    mask = (new_corners[:, axis] == current_val)
                    new_corners[mask, axis] = target_pos
            room[f"stretched_{direction}"] = True
            print(f"     ✅ Stretched '{room_name}' to {direction} ({'x' if axis == 0 else 'y'}={target_pos})")
        room['snapped_corners'] = [tuple(p) for p in new_corners]
        room['edges'] = create_edges_from_corners(room['snapped_corners'])
        if room['snapped_corners']:
            pts = np.array(room['snapped_corners'])
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            room['bounding_box'] = [int(x_min), int(y_min), 
                                  int(x_max - x_min), int(y_max - y_min)]
    return rooms
def clip_rooms_to_exterior(layout_shape, rooms, exterior_polygon):
    print("\n✂️ Clipping rooms to exterior polygon (removing outside parts)...")
    if exterior_polygon is None:
        print("   ⚠️ No exterior polygon provided; skipping clip.")
        return rooms
    h, w = layout_shape[:2]
    exterior_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(exterior_mask, [exterior_polygon], 255)
    clipped_rooms = []
    for room in rooms:
        mask = np.zeros((h, w), dtype=np.uint8)
        corners = np.array(room['snapped_corners'], dtype=np.int32)
        cv2.fillPoly(mask, [corners], 255)
        clipped = cv2.bitwise_and(mask, exterior_mask)
        area = int(cv2.countNonZero(clipped))
        if area < 50:
            print(f"   → Dropping '{room['name']}' (outside or too small after clip)")
            continue
        contours, _ = cv2.findContours(clipped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        epsilon = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        poly = [tuple(pt[0]) for pt in approx]
        if len(poly) < 3:
            continue
        updated = dict(room)
        updated['snapped_corners'] = poly
        updated['edges'] = create_edges_from_corners(poly)
        updated['center'] = get_mask_center(clipped)
        pts_np = np.array(poly)
        x_left, y_top = np.min(pts_np, axis=0)
        x_right, y_bottom = np.max(pts_np, axis=0)
        updated['bounding_box'] = [int(x_left), int(y_top), int(x_right - x_left), int(y_bottom - y_top)]
        updated['area'] = area
        clipped_rooms.append(updated)
    print(f"   ✅ Clipped rooms count: {len(clipped_rooms)} (from {len(rooms)})")
    return clipped_rooms
def resolve_overlaps_by_area(layout_shape, rooms, min_keep_area=400):
    print("\n🧩 Resolving overlaps (Smart Preservation Logic)...")

    def get_room_rect(room):
        bbox = room.get('bounding_box')
        if not bbox or len(bbox) != 4: return None
        x, y, w, h = bbox
        return (x, y, x + w, y + h)

    def get_intersection_area(rect1, rect2):
        x_left = max(rect1[0], rect2[0])
        y_top = max(rect1[1], rect2[1])
        x_right = min(rect1[2], rect2[2])
        y_bottom = min(rect1[3], rect2[3])
        if x_right <= x_left or y_bottom <= y_top:
            return 0
        return (x_right - x_left) * (y_bottom - y_top)

    def update_room(room, new_rect):
        x_min, y_min, x_max, y_max = new_rect
        width = x_max - x_min
        height = y_max - y_min
        area = width * height
        
        # --- THAY ĐỔI QUAN TRỌNG ---
        # Nếu cắt xong mà phòng quá nhỏ -> HỦY BỎ VIỆC CẮT (Return False)
        # Thay vì xóa phòng như code cũ
        if area < min_keep_area:
            print(f"   ⚠️ Cannot resize '{room['name']}' (result too small), keeping overlap.")
            return False 
        # ---------------------------

        room['snapped_corners'] = [
            (int(x_min), int(y_min)), (int(x_max), int(y_min)),
            (int(x_max), int(y_max)), (int(x_min), int(y_max))
        ]
        room['edges'] = create_edges_from_corners(room['snapped_corners'])
        room['bounding_box'] = [int(x_min), int(y_min), int(width), int(height)]
        room['area'] = int(area)
        room['center'] = (int(x_min + width / 2), int(y_min + height / 2))
        return True

    # Sắp xếp: Ưu tiên giữ các phòng đã được định danh (có tên cụ thể)
    # Để tránh việc Living Room (thường là 'unknown' lúc đầu) đè lên Bedroom
    sorted_rooms = sorted(rooms, key=lambda r: (r.get('name', '').startswith('room') is False, -r.get('area', 0)))

    for i in range(len(sorted_rooms)):
        master = sorted_rooms[i]
        if master.get('area', 0) < 10: continue
        master_rect = get_room_rect(master)
        if not master_rect: continue
        
        for j in range(i + 1, len(sorted_rooms)):
            slave = sorted_rooms[j]
            if slave.get('area', 0) < 10: continue
            slave_rect = get_room_rect(slave)
            if not slave_rect: continue

            # Tính diện tích chồng lấn
            intersect_area = get_intersection_area(master_rect, slave_rect)
            if intersect_area == 0: continue

            # --- THAY ĐỔI QUAN TRỌNG ---
            # Chỉ xử lý nếu chồng lấn > 20% diện tích phòng nhỏ
            # Nếu chỉ chạm nhẹ biên (do sai số), BỎ QUA để giữ nguyên hình dáng
            slave_area = slave['area']
            overlap_ratio = intersect_area / slave_area
            
            if overlap_ratio < 0.2: 
                continue 
            # ---------------------------

            # Logic cắt gọt (Snap Bounding Box)
            s_x, s_y, s_x_max, s_y_max = slave_rect
            m_x, m_y, m_x_max, m_y_max = master_rect
            new_slave = list(slave_rect)
            
            inter_w = min(m_x_max, s_x_max) - max(m_x, s_x)
            inter_h = min(m_y_max, s_y_max) - max(m_y, s_y)

            if inter_w < inter_h: # Cắt theo trục X
                if (m_x + m_x_max) / 2 < (s_x + s_x_max) / 2: new_slave[0] = m_x_max
                else: new_slave[2] = m_x
            else: # Cắt theo trục Y
                if (m_y + m_y_max) / 2 < (s_y + s_y_max) / 2: new_slave[1] = m_y_max
                else: new_slave[3] = m_y

            # Thực hiện cập nhật (nếu an toàn)
            if update_room(slave, tuple(new_slave)):
                print(f"   ✂️ Trimmed '{slave['name']}' overlap with '{master['name']}'")

    # Lọc bỏ các phòng thực sự lỗi (area=0 từ trước đó, nếu có)
    final_rooms = [r for r in sorted_rooms if r.get('area', 0) > 0]
    return final_rooms
def rename_rooms_by_position(rooms, layout_shape):
    print("\n🏷️ Assigning final room names based on position...")
    def get_type(room):
        if 'name' not in room or not room['name']:
            return 'unknown'
        return room['name'].split('_')[0]
    rooms_by_type = {}
    for room in rooms:
        room_type = get_type(room)
        if room_type not in rooms_by_type:
            rooms_by_type[room_type] = []
        rooms_by_type[room_type].append(room)
    final_room_type_counter = {}
    for room_type, room_list in rooms_by_type.items():
        try:
            if room_type == 'master_room':
                room_list[0]['name'] = 'Bedroom 1'
            elif room_type == 'common_room':
                room_list.sort(key=lambda r: r['center'][0]) 
                if len(room_list) > 0:
                    room_list[0]['name'] = 'Bedroom 2'
                if len(room_list) > 1:
                    room_list[1]['name'] = 'Japan style room'
            elif room_type == 'bathroom':
                room_list.sort(key=lambda r: r['center'][0])
                if len(room_list) > 0:
                    room_list[0]['name'] = 'Bathroom 2'
                if len(room_list) > 1:
                    right_bathrooms = sorted(room_list[1:], key=lambda r: r['center'][1])
                    if len(right_bathrooms) > 0:
                        right_bathrooms[0]['name'] = 'Bathroom 1'
                    if len(right_bathrooms) > 1:
                        right_bathrooms[1]['name'] = 'Bathroom 3'
        except Exception as e:
            print(f"   ⚠️ Warning: Failed to rename room type '{room_type}': {e}")
    for room in rooms:
        base_name = room['name'].split(' ')[0].split('_')[0]
        final_room_type_counter[base_name] = final_room_type_counter.get(base_name, 0) + 1
    print(f"   ✅ Renamed rooms. Final types: {final_room_type_counter}")
    return rooms, final_room_type_counter
def detect_unassigned_space(layout_shape, all_rooms, exterior_polygon):
    print("\n🏡 Detecting unassigned space (e.g., Living Room)...")
    if exterior_polygon is None:
        print("   ❌ Cannot detect unassigned space without exterior walls.")
        return None, {}
    canvas = np.zeros(layout_shape[:2], dtype=np.uint8)
    cv2.fillPoly(canvas, [exterior_polygon], 255)
    for room in all_rooms:
        corners = np.array(room['snapped_corners'], dtype=np.int32)
        cv2.fillPoly(canvas, [corners], 0)
    contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("   → No significant unassigned space found.")
        return None, {}
    living_room_contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(living_room_contour) < 5000:
        print("   → Unassigned space is too small to be a living room.")
        return None, {}
    new_room_name = "livingroom_1"
    new_room_corners = [tuple(p[0]) for p in living_room_contour]
    pts = living_room_contour.reshape(-1, 2)
    x_left, y_top = np.min(pts, axis=0)
    x_right, y_bottom = np.max(pts, axis=0)
    bbox = [int(x_left), int(y_top), int(x_right - x_left), int(y_bottom - y_top)]
    area = int(cv2.contourArea(living_room_contour))
    new_room = {
        'id': len(all_rooms),
        'name': new_room_name,
        'color': [255, 253, 208], 
        'center': get_mask_center(canvas),
        'snapped_corners': new_room_corners,
        'edges': create_edges_from_corners(new_room_corners),
        'exterior_facing': [],
        'bounding_box': bbox,
        'area': area
    }
    print(f"   ✅ Detected and created '{new_room_name}'.")
    new_room_counter = {'livingroom': 1}
    return new_room, new_room_counter
def draw_final_image(layout_shape, rooms, exterior_edges, colored=False):
    canvas = np.ones((layout_shape[0], layout_shape[1], 3), dtype=np.uint8) * 255
    room_colors = {
        'master': (0, 165, 255),       
        'bathroom': (210, 216, 173),   
        'Bathroom': (210, 216, 173),   
        'common': (0, 215, 255),       
        'storage': (221, 160, 221),    
        'balcony': (35, 142, 107),     
        'livingroom': (208, 253, 255),   
        'living_room': (208, 253, 255),  
        'unknown': (200, 200, 200)       
    }
    filled_mask = np.zeros(layout_shape[:2], dtype=np.uint8)
    sorted_rooms = sorted(rooms, key=lambda x: x.get('area', 0))
    if colored:
        for room in sorted_rooms:
            if 'snapped_corners' not in room or not room['snapped_corners']:
                continue
            name_lower = room['name'].lower()
            if 'living' in name_lower:
                continue
            room_mask = np.zeros(layout_shape[:2], dtype=np.uint8)
            corners = np.array(room['snapped_corners'], dtype=np.int32)
            cv2.fillPoly(room_mask, [corners], 255)
            room_mask = cv2.bitwise_and(room_mask, cv2.bitwise_not(filled_mask))
            if 'bathroom' in name_lower:
                room_type = 'bathroom'
            elif 'master' in name_lower:
                room_type = 'master'
            elif 'common' in name_lower:
                room_type = 'common'
            elif 'storage' in name_lower:
                room_type = 'storage'
            elif 'balcony' in name_lower:
                room_type = 'balcony'
            else:
                room_type = room['name'].split('_')[0].split()[0]
            color = room_colors.get(room_type, 
                                    room.get('color', [200, 200, 200])[::-1] if 'color' in room 
                                    else room_colors.get('unknown', (200, 200, 200)))
            canvas[room_mask > 0] = color
            filled_mask = cv2.bitwise_or(filled_mask, room_mask)
        for room in rooms:
            name_lower = room['name'].lower()
            if 'living' not in name_lower or 'snapped_corners' not in room or not room['snapped_corners']:
                continue
            room_mask = np.zeros(layout_shape[:2], dtype=np.uint8)
            corners = np.array(room['snapped_corners'], dtype=np.int32)
            cv2.fillPoly(room_mask, [corners], 255)
            room_mask = cv2.bitwise_and(room_mask, cv2.bitwise_not(filled_mask))
            canvas[room_mask > 0] = room_colors['livingroom']
            filled_mask = cv2.bitwise_or(filled_mask, room_mask)
    if exterior_edges:
        for x1, y1, x2, y2 in exterior_edges:
            cv2.line(canvas, (x1, y1), (x2, y2), (0, 0, 0), 3)
    all_edges = set()
    for room in rooms:
        for edge in room.get('edges', []):
            p1, p2 = (edge[0], edge[1]), (edge[2], edge[3])
            all_edges.add(tuple(sorted((p1, p2))))
    for p1, p2 in all_edges:
        if np.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) > 1:
            cv2.line(canvas, p1, p2, (0, 0, 0), 2)
    if not colored:
        for room in rooms:
            if 'snapped_corners' in room and room['snapped_corners']:
                corners = np.array(room['snapped_corners'])
                if 'center' in room and room['center']:
                    center = tuple(int(c) for c in room['center'])
                else:
                    center = tuple(np.mean(corners, axis=0).astype(int))
                cv2.circle(canvas, center, 5, (0, 0, 255), -1)  
                text = room['name']
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                thickness = 1
                (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
                text_x = center[0] - text_w // 2
                text_y = center[1] + text_h // 2
                cv2.rectangle(canvas, 
                              (text_x - 2, text_y - text_h - 2),
                              (text_x + text_w + 2, text_y + 2),
                              (255, 255, 255), -1)
                cv2.putText(canvas, text, (text_x, text_y), 
                            font, font_scale, (0, 0, 0), thickness)
    return canvas
def apply_exterior_mask(image, exterior_polygon):
    if image is None or exterior_polygon is None:
        return image
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [exterior_polygon], 255)
    image[mask == 0] = 255
    return image
def process_floorplan(layout_path, exterior_wall_path, output_dir="outputs"):
    os.makedirs(output_dir, exist_ok=True)
    layout = cv2.imread(layout_path)
    if layout is None: print(f"❌ Error: Cannot read layout image at {layout_path}"); return None
    layout_rgb = cv2.cvtColor(layout, cv2.COLOR_BGR2RGB)
    print(f"📐 Layout size: {layout_rgb.shape[1]}x{layout_rgb.shape[0]}")
    unique_colors = [tuple(c.tolist()) for c in np.unique(layout_rgb.reshape(-1, 3), axis=0) if not (np.all(c > 250) or np.all(c < 5))]
    print(f"\n🎨 Detected {len(unique_colors)} unique room colors.")
    color_map = {
        (255, 255, 0): 'common_room', (255, 215, 0): 'common_room',
        (173, 216, 230): 'bathroom', (173, 216, 210): 'bathroom',
        (255, 165, 0): 'master_room',
        (221, 160, 221): 'storage',
        (255, 253, 208): 'living_room',
        (107, 142, 35): 'balcony'  
    }
    all_rooms, room_type_counter = [], {}
    for color in unique_colors:
        print(f"\nProcessing color: {color}...")
        mask = cv2.inRange(layout_rgb, np.array(color), np.array(color))
        room_masks = split_color_into_rooms(mask)
        for room_mask in room_masks:
            room_type = color_map.get(color, 'unknown_room')
            if room_type == 'living_room':
                print("   → Skipping 'living_room' color; will be detected from empty space.")
                continue
            room_type_counter[room_type] = room_type_counter.get(room_type, 0) + 1
            room_name = f"{room_type}_{room_type_counter[room_type]}"
            if (room_info := process_room(room_mask, color, len(all_rooms), room_name)):
                all_rooms.append(room_info); print(f"   → Found: {room_name}")
    if not all_rooms: print("\n❌ No valid rooms found."); return None
    exterior_edges, exterior_polygon = extract_exterior_walls_simple(exterior_wall_path)
    rooms, shared_edges, merge_info = merge_adjacent_edges_final(all_rooms, max_distance=50)
    analyze_exterior_facing_edges(rooms, exterior_edges)
    stretch_rooms_to_exterior(rooms, exterior_edges)
    rooms = clip_rooms_to_exterior(layout_rgb.shape, rooms, exterior_polygon)
    rooms = resolve_overlaps_by_area(layout_rgb.shape, rooms)
    living_room_obj, living_counter = detect_unassigned_space(layout_rgb.shape, rooms, exterior_polygon)
    if living_room_obj:
        rooms.append(living_room_obj)
        room_type_counter.update(living_counter)
    request_info = _load_request_info()
    rooms, room_type_counter = _apply_request_names(rooms, request_info)
    def np_converter(o):
        if isinstance(o, (np.integer, np.floating)): return o.item()
        if isinstance(o, np.ndarray): return o.tolist()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    for r in rooms: r['num_edges'] = len(r['edges'])
    room_data = {'total_rooms': len(rooms), 'room_types': room_type_counter, 'rooms': rooms}
    with open(os.path.join(output_dir, "room_data.json"), 'w', encoding='utf-8') as f: json.dump(room_data, f, indent=2, default=np_converter, ensure_ascii=False)
    print(f"\n✅ Saved room data to: room_data.json")
    shared_data = {'total_shared_edges': len(shared_edges), 'shared_edges': shared_edges, 'merge_info': merge_info}
    with open(os.path.join(output_dir, "shared_edges.json"), "w", encoding="utf-8") as f: json.dump(shared_data, f, indent=2, default=np_converter, ensure_ascii=False)
    print(f"✅ Saved shared edge data to: shared_edges.json")
    exterior_data = {'total_segments': len(exterior_edges), 'exterior_edges': exterior_edges}
    with open(os.path.join(output_dir, "exterior_wall.json"), "w", encoding="utf-8") as f: json.dump(exterior_data, f, indent=2, default=np_converter, ensure_ascii=False)
    print(f"✅ Saved exterior wall data to: exterior_wall.json")
    bw_image = draw_final_image(layout_rgb.shape, rooms, exterior_edges, colored=False)
    bw_image = apply_exterior_mask(bw_image, exterior_polygon)
    bw_path = os.path.join(output_dir, "overlay_result.png")
    cv2.imwrite(bw_path, bw_image)
    print(f"✅ Saved B&W line drawing to: overlay_result.png")
    colored_image = draw_final_image(layout_rgb.shape, rooms, exterior_edges, colored=True)
    colored_image = apply_exterior_mask(colored_image, exterior_polygon)
    colored_path = os.path.join(output_dir, "colored_floorplan.png")
    cv2.imwrite(colored_path, colored_image)
    print(f"✅ Saved colored floorplan (without furniture) to: colored_floorplan.png")
    return room_data
def main():
    print("=" * 60 + "\n🏠 STEP 1: GRAFTING ROOMS PROCESSOR\n" + "=" * 60)
    try: script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError: script_dir = os.getcwd()
    base_dir, input_dir = script_dir, os.path.join(script_dir, "inputs")
    if not os.path.exists(input_dir):
        base_dir = os.path.dirname(script_dir)
        input_dir = os.path.join(base_dir, "inputs")
    output_dir = os.path.join(base_dir, "outputs")
    print(f"📂 Base Directory: {base_dir}\n📥 Input Directory: {input_dir}\n📤 Output Directory: {output_dir}")
    layout_file = os.path.join(input_dir, "img.png")
    exterior_wall_file = os.path.join(input_dir, "exterior_wall.png")
    if not os.path.exists(layout_file): 
        print(f"\n❌ FATAL: Layout file 'img.png' not found in '{input_dir}'"); return
    if not os.path.exists(exterior_wall_file): 
        print(f"\n❌ FATAL: Exterior wall file 'exterior_wall.png' not found in '{input_dir}'"); return
    print(f"✅ Found layout: {os.path.basename(layout_file)}\n✅ Found exterior walls: {os.path.basename(exterior_wall_file)}")
    print("\n🚀 Starting processing...")
    result = process_floorplan(layout_file, exterior_wall_file, output_dir)
    if result: 
        print(f"\n{'='*60}\n🎉 STEP 1 COMPLETE! Output files:\n"
              f"   • room_data.json\n"
              f"   • shared_edges.json\n"
              f"   • exterior_wall.json\n"
              f"   • overlay_result.png\n"
              f"   • colored_floorplan.png\n"
              f"{'='*60}")
    else: 
        print(f"\n{'='*60}\n❌ STEP 1 FAILED.\n{'='*60}")
if __name__ == "__main__":
    main()