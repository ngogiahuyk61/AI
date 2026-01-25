import json
from collections import deque
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "input" / "stie_data_filled.json"
OUTPUT_PATH = BASE_DIR / "input" / "best_black_region.json"


def mark_safe_cells(grid: np.ndarray) -> np.ndarray:
    """Đánh dấu các điểm 1 an toàn (giữ lại) theo tiêu chí xanh/đỏ."""
    arr = np.asarray(grid, dtype=np.uint8)
    safe = np.zeros_like(arr, dtype=bool)
    height, width = arr.shape

    for y in range(height):
        for x in range(width):
            if arr[y, x] != 1:
                continue

            up = arr[y - 1, x] if y > 0 else None
            down = arr[y + 1, x] if y < height - 1 else None
            left = arr[y, x - 1] if x > 0 else None
            right = arr[y, x + 1] if x < width - 1 else None

            touching_zero = any(nei == 0 for nei in (up, down, left, right) if nei is not None)

            if not touching_zero:
                safe[y, x] = True
                continue

            pairs = [
                (up, left),
                (up, right),
                (down, left),
                (down, right),
            ]

            for a, b in pairs:
                if a is not None and b is not None and a == 1 and b == 1:
                    safe[y, x] = True
                    break

    filtered = arr.copy()
    filtered[(arr == 1) & (~safe)] = 0
    return filtered


def find_clusters(arr: np.ndarray):
    height, width = arr.shape
    visited = np.zeros_like(arr, dtype=bool)
    clusters = []

    for y in range(height):
        for x in range(width):
            if arr[y, x] != 1 or visited[y, x]:
                continue

            queue = deque([(y, x)])
            visited[y, x] = True
            coords = []

            while queue:
                cy, cx = queue.popleft()
                coords.append((cy, cx))

                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width:
                        if arr[ny, nx] == 1 and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((ny, nx))

            clusters.append(coords)

    return clusters


def build_best_region_grid(arr: np.ndarray, clusters):
    if not clusters:
        return np.zeros_like(arr), []

    sizes = [len(cluster) for cluster in clusters]
    best_index = int(np.argmax(sizes))
    best_cluster = clusters[best_index]

    result = np.zeros_like(arr)
    for y, x in best_cluster:
        result[y, x] = 1

    return result, sizes


if __name__ == "__main__":
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    length = int(data.get("length", 0))
    width = int(data.get("width", 0))
    grid_raw = data.get("grid", [])

    grid = np.asarray(grid_raw, dtype=np.uint8)
    if grid.shape != (length, width):
        raise ValueError("Grid dimensions do not match length and width")

    filtered = mark_safe_cells(grid)
    clusters = find_clusters(filtered)
    best_region, sizes = build_best_region_grid(filtered, clusters)

    OUTPUT_PATH.write_text(
        json.dumps({
            "length": length,
            "width": width,
            "grid": best_region.astype(int).tolist(),
            "region_count": len(sizes),
            "region_sizes": sizes,
            "best_region_size": int(max(sizes) if sizes else 0),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
