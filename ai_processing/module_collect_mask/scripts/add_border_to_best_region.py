import json
from pathlib import Path

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "input" / "best_black_region_smoothed.json"
OUTPUT_PATH = BASE_DIR / "input" / "best_black_region_with_border.json"
UPSCALED_JSON_PATH = BASE_DIR / "input" / "best_black_region_with_border_upscaled.json"
UPSCALED_PREVIEW_PATH = BASE_DIR / "output" / "mask_best_region_with_border_upscaled_64.png"


def pad_to_square(grid: np.ndarray, length: int, width: int) -> tuple[np.ndarray, int, int]:
    """Pad the shorter dimension with zeros so grid becomes square."""
    if length == width:
        return grid, length, width

    if length > width:
        diff = length - width
        left_pad = diff // 2 + diff % 2  # ceil(diff / 2)
        right_pad = diff // 2           # floor(diff / 2)
        padded = np.pad(grid, ((0, 0), (left_pad, right_pad)), mode="constant", constant_values=0)
        return padded, length, width + diff

    # width > length
    diff = width - length
    top_pad = diff // 2 + diff % 2
    bottom_pad = diff // 2
    padded = np.pad(grid, ((top_pad, bottom_pad), (0, 0)), mode="constant", constant_values=0)
    return padded, length + diff, width


def add_zero_border(grid: np.ndarray) -> np.ndarray:
    height, width = grid.shape
    result = np.zeros((height + 8, width + 8), dtype=grid.dtype)
    result[4:-4, 4:-4] = grid
    return result


def upscale_nearest(grid: np.ndarray, factor: int = 3) -> np.ndarray:
    """Upscale the grid by nearest-neighbor repeat."""
    return np.repeat(np.repeat(grid, factor, axis=0), factor, axis=1)


def add_outer_boundary_value_two(grid: np.ndarray) -> np.ndarray:
    """Set value 2 on zero-cells that are 8-neighbors of any 1-cell (single-pixel ring)."""
    h, w = grid.shape
    result = grid.copy()

    ones = (grid == 1)
    # pad to simplify neighbor checks
    padded = np.pad(ones.astype(np.uint8), 1, mode="constant", constant_values=0)

    # accumulate 8-neighborhood counts
    neighbor_sum = (
        padded[0:h,     0:w] + padded[0:h,     1:w+1] + padded[0:h,     2:w+2] +
        padded[1:h+1,   0:w] +                         padded[1:h+1,   2:w+2] +
        padded[2:h+2,   0:w] + padded[2:h+2,   1:w+1] + padded[2:h+2,   2:w+2]
    )

    boundary_mask = (grid == 0) & (neighbor_sum > 0)
    result[boundary_mask] = 2
    return result


if __name__ == "__main__":
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    length = int(data.get("length", 0))
    width = int(data.get("width", 0))
    grid_raw = data.get("grid", [])

    grid = np.asarray(grid_raw, dtype=np.uint8)
    if grid.shape != (length, width):
        raise ValueError("Grid dimensions do not match length and width")

    grid, length, width = pad_to_square(grid, length, width)

    # Step 1: add the 4-pixel zero border around the best region grid
    bordered = add_zero_border(grid)

    # Save intermediate bordered JSON (original behavior)
    OUTPUT_PATH.write_text(
        json.dumps({
            "length": int(bordered.shape[0]),
            "width": int(bordered.shape[1]),
            "grid": bordered.astype(int).tolist(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Step 2: upscale by factor 3
    upscaled = upscale_nearest(bordered, factor=3)

    # Step 3: set boundary value 2 around the 1-region (single-pixel ring)
    upscaled_with_boundary = add_outer_boundary_value_two(upscaled)

    # Save new upscaled JSON
    UPSCALED_JSON_PATH.write_text(
        json.dumps({
            "length": int(upscaled_with_boundary.shape[0]),
            "width": int(upscaled_with_boundary.shape[1]),
            "grid": upscaled_with_boundary.astype(int).tolist(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Step 4: write a 64x64 preview image
    # Map values: 0 -> 0 (black), 2 -> 180 (gray), 1 -> 255 (white)
    vis = np.zeros_like(upscaled_with_boundary, dtype=np.uint8)
    vis[upscaled_with_boundary == 1] = 255
    vis[upscaled_with_boundary == 2] = 180

    img = Image.fromarray(vis, mode="L")
    img_64 = img.resize((64, 64), Image.NEAREST)
    UPSCALED_PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    img_64.save(UPSCALED_PREVIEW_PATH)

    # Step 5: create mask.png with custom color mapping
    # Map values: 0 (background) -> 255 (white), 1 (object) -> 0 (black), 2 (border) -> 14 (gray)
    mask_vis = np.zeros_like(upscaled_with_boundary, dtype=np.uint8)
    mask_vis[upscaled_with_boundary == 0] = 255  # background -> white
    mask_vis[upscaled_with_boundary == 1] = 0   # object -> black
    mask_vis[upscaled_with_boundary == 2] = 14  # border -> gray

    mask_img = Image.fromarray(mask_vis, mode="L")
    mask_64 = mask_img.resize((64, 64), Image.NEAREST)
    
    # Save to model/source/mask/mask.png
    mask_dir = (BASE_DIR  / ".." / "model" / "source" / "mask").resolve()
    mask_dir.mkdir(parents=True, exist_ok=True)
    mask_path = mask_dir / "1.png"
    mask_64.save(mask_path)
    print(f"✅ Mask saved to: {mask_path}")
