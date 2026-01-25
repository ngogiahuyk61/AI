import json
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "input" / "best_black_region.json"
OUTPUT_PATH = BASE_DIR / "input" / "best_black_region_smoothed.json"
MODEL_SOURCE_DIR = BASE_DIR.parent / "model" / "source"
TEXT_INPUT_DIR = MODEL_SOURCE_DIR / "text_input"

NEIGHBOR_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
NEIGHBOR_8 = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

SHARP_TRIPLETS = [
    ((-1, 0), (0, -1), (-1, -1)),  # lên, trái, chéo lên-trái
    ((-1, 0), (0, 1), (-1, 1)),    # lên, phải, chéo lên-phải
    ((1, 0), (0, -1), (1, -1)),    # xuống, trái, chéo xuống-trái
    ((1, 0), (0, 1), (1, 1)),      # xuống, phải, chéo xuống-phải
]


def in_bounds(y: int, x: int, height: int, width: int) -> bool:
    return 0 <= y < height and 0 <= x < width


def detect_sharp_zeros(grid: np.ndarray) -> np.ndarray:
    height, width = grid.shape
    sharp = np.zeros_like(grid, dtype=bool)

    for y in range(height):
        for x in range(width):
            if grid[y, x] != 0:
                continue

            for trio in SHARP_TRIPLETS:
                ok = True
                for dy, dx in trio:
                    ny, nx = y + dy, x + dx
                    if not in_bounds(ny, nx, height, width) or grid[ny, nx] != 1:
                        ok = False
                        break
                if ok:
                    sharp[y, x] = True
                    break

    return sharp


def group_sharp_zeros(sharp_mask: np.ndarray) -> List[List[Tuple[int, int]]]:
    height, width = sharp_mask.shape
    visited = np.zeros_like(sharp_mask, dtype=bool)
    groups: List[List[Tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            if not sharp_mask[y, x] or visited[y, x]:
                continue

            queue = deque([(y, x)])
            visited[y, x] = True
            coords: List[Tuple[int, int]] = []

            while queue:
                cy, cx = queue.popleft()
                coords.append((cy, cx))

                for dy, dx in NEIGHBOR_8:
                    ny, nx = cy + dy, cx + dx
                    if in_bounds(ny, nx, height, width) and sharp_mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))

            groups.append(coords)

    return groups


def determine_endpoints(coords: List[Tuple[int, int]]):
    if not coords:
        return None, None

    if len(coords) == 1:
        return coords[0], coords[0]

    coord_set = set(coords)
    adjacency = {}
    for y, x in coords:
        neighbors = 0
        for dy, dx in NEIGHBOR_8:
            ny, nx = y + dy, x + dx
            if (ny, nx) in coord_set:
                neighbors += 1
        adjacency[(y, x)] = neighbors

    endpoints = [pt for pt, deg in adjacency.items() if deg <= 1]

    if len(endpoints) >= 2:
        # chọn 2 endpoint xa nhau nhất để ổn định
        max_pair = endpoints[0], endpoints[1]
        max_dist = -1
        for i in range(len(endpoints)):
            for j in range(i + 1, len(endpoints)):
                (y1, x1), (y2, x2) = endpoints[i], endpoints[j]
                dist = abs(y1 - y2) + abs(x1 - x2)
                if dist > max_dist:
                    max_dist = dist
                    max_pair = endpoints[i], endpoints[j]
        return max_pair

    # Nếu không có endpoint (chu kỳ), chọn 2 điểm xa nhất toàn nhóm
    max_pair = coords[0], coords[0]
    max_dist = -1
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            (y1, x1), (y2, x2) = coords[i], coords[j]
            dist = abs(y1 - y2) + abs(x1 - x2)
            if dist > max_dist:
                max_dist = dist
                max_pair = coords[i], coords[j]

    return max_pair


def fill_bbox_between(grid: np.ndarray, p1: Tuple[int, int], p2: Tuple[int, int]):
    (y1, x1), (y2, x2) = p1, p2
    ymin, ymax = sorted((y1, y2))
    xmin, xmax = sorted((x1, x2))
    grid[ymin : ymax + 1, xmin : xmax + 1] = 0
    return {
        "y_min": int(ymin),
        "y_max": int(ymax),
        "x_min": int(xmin),
        "x_max": int(xmax),
    }


def count_site_pixels(grid: np.ndarray) -> int:
    return int(np.count_nonzero(grid == 1))


def latest_floorplan_request(text_input_dir: Path) -> Optional[Path]:
    if not text_input_dir.exists():
        return None
    candidates = sorted(
        text_input_dir.glob("floorplan-request-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def sync_total_area_to_request(area_m2: float) -> None:
    request_path = latest_floorplan_request(TEXT_INPUT_DIR)
    if request_path is None:
        return

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    payload["total_area_m2"] = float(area_m2)
    request_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    length = int(data.get("length", 0))
    width = int(data.get("width", 0))
    grid_raw = data.get("grid", [])

    grid = np.asarray(grid_raw, dtype=np.uint8)
    if grid.shape != (length, width):
        raise ValueError("Grid dimensions do not match length and width")

    sharp_mask = detect_sharp_zeros(grid)
    groups = group_sharp_zeros(sharp_mask)

    result = grid.copy()
    applied = []

    for group_id, coords in enumerate(groups, start=1):
        p1, p2 = determine_endpoints(coords)
        if p1 is None or p2 is None:
            continue
        bbox = fill_bbox_between(result, p1, p2)
        applied.append({
            "group_id": group_id,
            "size": len(coords),
            "start": {"y": int(p1[0]), "x": int(p1[1])},
            "end": {"y": int(p2[0]), "x": int(p2[1])},
            "bbox": bbox,
        })

    site_pixel_count = count_site_pixels(result)
    site_area_m2 = float(site_pixel_count)

    OUTPUT_PATH.write_text(
        json.dumps({
            "length": length,
            "width": width,
            "grid": result.astype(int).tolist(),
            "sharp_zero_count": int(np.count_nonzero(sharp_mask)),
            "sharp_group_count": len(groups),
            "applied_groups": applied,
            "site_pixel_count": site_pixel_count,
            "site_area_m2": site_area_m2,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sync_total_area_to_request(site_area_m2)
