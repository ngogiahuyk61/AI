import json
from collections import deque
from pathlib import Path

import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "input" / "site_data.json"
OUTPUT_PATH = BASE_DIR / "input" / "stie_data_filled.json"

def bridge_single_pixel_gaps(grid: np.ndarray) -> np.ndarray:
    """Lấp các khoảng hở 1 pixel theo hàng/cột giữa các điểm 0."""
    arr = np.asarray(grid, dtype=np.uint8).copy()

    while True:
        changed = False

        horizontal = (arr[:, :-2] == 0) & (arr[:, 1:-1] == 1) & (arr[:, 2:] == 0)
        if np.any(horizontal):
            rows, cols = np.where(horizontal)
            arr[rows, cols + 1] = 0
            changed = True

        vertical = (arr[:-2, :] == 0) & (arr[1:-1, :] == 1) & (arr[2:, :] == 0)
        if np.any(vertical):
            rows, cols = np.where(vertical)
            arr[rows + 1, cols] = 0
            changed = True

        if not changed:
            break

    return arr


def fill_zero_regions_smart(grid, max_gap=2):
    """
    Tạo kết nối 4-neighbour cho các điểm 0 bằng cách lấp khe hở 1 pixel.
    Sau đó xác định các vùng 0 liên thông, tìm biên gần nhất và lấp vùng về phía biên đó.
    Tham số max_gap giữ lại để tương thích, hiện không dùng.
    """
    grid = np.asarray(grid, dtype=np.uint8)
    bridged = bridge_single_pixel_gaps(grid)

    clusters = find_zero_clusters(bridged)
    filled = bridged.copy()
    cluster_infos = []

    height, width = filled.shape

    for idx, cluster in enumerate(clusters, start=1):
        bbox = calculate_bounding_box(cluster)
        distances, nearest_border = determine_nearest_border(bbox, height, width)
        fill_rect = fill_towards_border(filled, bbox, nearest_border)

        cluster_infos.append({
            "cluster_id": idx,
            "size": len(cluster),
            "bounding_box": {
                "x_min": int(bbox["x_min"]),
                "x_max": int(bbox["x_max"]),
                "y_min": int(bbox["y_min"]),
                "y_max": int(bbox["y_max"]),
            },
            "nearest_border": nearest_border,
            "distances": {k: int(v) for k, v in distances.items()},
            "filled_region": fill_rect,
        })

    return filled, cluster_infos


def find_zero_clusters(arr: np.ndarray):
    height, width = arr.shape
    visited = np.zeros_like(arr, dtype=bool)
    clusters = []

    for y in range(height):
        for x in range(width):
            if arr[y, x] != 0 or visited[y, x]:
                continue

            queue = deque([(y, x)])
            visited[y, x] = True
            coords = []

            while queue:
                cy, cx = queue.popleft()
                coords.append((cy, cx))

                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width:
                        if arr[ny, nx] == 0 and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((ny, nx))

            clusters.append(coords)

    return clusters


def calculate_bounding_box(coords):
    ys, xs = zip(*coords)
    return {
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
    }


def determine_nearest_border(bbox, height, width):
    distances = {
        "left": bbox["x_min"],
        "right": width - 1 - bbox["x_max"],
        "top": bbox["y_min"],
        "bottom": height - 1 - bbox["y_max"],
    }
    order = ("left", "top", "right", "bottom")
    nearest = min(order, key=lambda k: distances[k])
    return distances, nearest


def fill_towards_border(arr: np.ndarray, bbox, border: str):
    y_min, y_max = bbox["y_min"], bbox["y_max"]
    x_min, x_max = bbox["x_min"], bbox["x_max"]

    if border == "left":
        arr[y_min : y_max + 1, : x_min + 1] = 0
        return {
            "x_min": 0,
            "x_max": int(x_min),
            "y_min": int(y_min),
            "y_max": int(y_max),
        }

    if border == "right":
        arr[y_min : y_max + 1, x_min :] = 0
        return {
            "x_min": int(x_min),
            "x_max": int(arr.shape[1] - 1),
            "y_min": int(y_min),
            "y_max": int(y_max),
        }

    if border == "top":
        arr[: y_min + 1, x_min : x_max + 1] = 0
        return {
            "x_min": int(x_min),
            "x_max": int(x_max),
            "y_min": 0,
            "y_max": int(y_min),
        }

    if border == "bottom":
        arr[y_min :, x_min : x_max + 1] = 0
        return {
            "x_min": int(x_min),
            "x_max": int(x_max),
            "y_min": int(y_min),
            "y_max": int(arr.shape[0] - 1),
        }

    return None


# --- Test trực tiếp ---
if __name__ == "__main__":
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    length = int(data.get("length", 0))
    width = int(data.get("width", 0))
    grid_raw = data.get("grid", [])

    grid = np.asarray(grid_raw, dtype=np.uint8)
    if grid.shape != (length, width):
        raise ValueError("Grid dimensions do not match length and width")

    filled, cluster_infos = fill_zero_regions_smart(grid, max_gap=2)

    OUTPUT_PATH.write_text(
        json.dumps({
            "length": length,
            "width": width,
            "grid": filled.astype(int).tolist(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
