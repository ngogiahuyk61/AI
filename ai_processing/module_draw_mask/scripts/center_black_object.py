from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
# Chúng ta không cần ImageFilter hay ImageEnhance
# vì chúng đang gây ra xung đột với mục tiêu chống răng cưa

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR.parent / "model"
SKETCH_DIR = MODEL_DIR / "source" / "sketch"
MODULE_INPUT_DIR = BASE_DIR / "input"
MODULE_OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_INPUT_NAME = "sketch-mask.png"
DEFAULT_OUTPUT_NAME = "object_centered_64.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Center the black object, square the canvas, and resize to 64x64."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional explicit input image path. If omitted, the latest sketch PNG will be used.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the processed 64x64 image.",
    )
    return parser.parse_args()


def _find_latest_sketch_png() -> Path:
    candidates = sorted(SKETCH_DIR.glob("sketch-*.png"))
    filtered = [path for path in candidates if not path.name.endswith("_64.png")]
    if not filtered:
        raise FileNotFoundError(f"No sketch PNG files found in {SKETCH_DIR}")
    return max(filtered, key=lambda path: path.stat().st_mtime)


def _copy_to_module_input(source_path: Path) -> Path:
    MODULE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    destination = MODULE_INPUT_DIR / DEFAULT_INPUT_NAME
    if source_path.resolve() != destination.resolve():
        shutil.copyfile(source_path, destination)
    return destination


def find_object_bounds(arr: np.ndarray) -> tuple[int, int, int, int]:
    # Sử dụng ảnh thang độ xám (không binarize) để tìm bounds
    mask = arr < 128
    if not np.any(mask):
        raise ValueError("No black object detected in the image.")

    ys, xs = np.where(mask)
    x_min = int(xs.min())
    x_max = int(xs.max())
    y_min = int(ys.min())
    y_max = int(ys.max())
    return x_min, x_max, y_min, y_max


def crop_to_equal_margin(arr: np.ndarray, bounds: tuple[int, int, int, int]) -> tuple[np.ndarray, dict]:
    height, width = arr.shape
    x_min, x_max, y_min, y_max = bounds

    distances = {
        "left": x_min,
        "right": width - 1 - x_max,
        "top": y_min,
        "bottom": height - 1 - y_max,
    }

    min_distance = min(distances.values())

    crop_left = max(0, distances["left"] - min_distance)
    crop_right = max(0, distances["right"] - min_distance)
    crop_top = max(0, distances["top"] - min_distance)
    crop_bottom = max(0, distances["bottom"] - min_distance)

    cropped = arr[crop_top : height - crop_bottom, crop_left : width - crop_right]

    report = {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "distances": distances,
        "min_distance": min_distance,
        "crop": {
            "left": crop_left,
            "right": crop_right,
            "top": crop_top,
            "bottom": crop_bottom,
        },
    }

    return cropped, report


def pad_to_square(arr: np.ndarray) -> np.ndarray:
    height, width = arr.shape
    if height == width:
        return arr

    if height > width:
        diff = height - width
        left_pad = diff // 2
        right_pad = diff - left_pad
        padding = ((0, 0), (left_pad, right_pad))
    else:
        diff = width - height
        top_pad = diff // 2
        bottom_pad = diff - top_pad
        padding = ((top_pad, bottom_pad), (0, 0))

    return np.pad(arr, padding, mode="constant", constant_values=255)


def process_image(input_path: Path, output_path: Optional[Path] = None) -> Path:
    # 1. Đọc ảnh, giữ lại thang độ xám (ảnh gốc của bạn rất mượt)
    image = Image.open(input_path).convert("L")
    arr = np.array(image)
    
    # 2. KHÔNG binarize ảnh gốc. Giữ nguyên các cạnh mượt.
    # arr = np.where(arr < 128, 0, 255).astype(np.uint8) 

    bounds = find_object_bounds(arr)
    cropped, report = crop_to_equal_margin(arr, bounds)
    squared = pad_to_square(cropped)

    img = Image.fromarray(squared, mode="L")
    
    # 3. RESIZE VỚI LANCZOS (phương pháp chống răng cưa tốt nhất)
    # Bước này sẽ TẠO RA các pixel xám ở cạnh để làm mượt.
    # Đây là kết quả "mờ" mà bạn thấy, nhưng nó là "mượt".
    resized_image = img.resize((64, 64), Image.LANCZOS)
    
    # 4. KHÔNG BINARIZE KẾT QUẢ CUỐI CÙNG
    # Dòng code này chính là nguyên nhân gây ra răng cưa ở các lần thử trước.
    # Bằng cách xóa nó, chúng ta giữ lại các pixel xám chống răng cưa.
    # -----------------------------------------------------------------
    # final_arr = np.array(resized_image)
    # binarized_final_arr = np.where(final_arr < 128, 0, 255).astype(np.uint8)
    # final_image = Image.fromarray(binarized_final_arr, mode="L")
    # -----------------------------------------------------------------

    if output_path is None:
        MODULE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = MODULE_OUTPUT_DIR / DEFAULT_OUTPUT_NAME
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # 5. Lưu trực tiếp ảnh đã resize (ảnh "mờ" nhưng mượt)
    resized_image.save(output_path) 

    print("Bounding box:", report["x_min"], report["x_max"], report["y_min"], report["y_max"])
    print("Distances to edges:", report["distances"])
    print("Minimum distance:", report["min_distance"])
    print("Applied crop (pixels):", report["crop"])
    print(f"Saved processed image to: {output_path}")

    return output_path


def main() -> None:
    args = parse_args()
    input_path = args.input
    source_origin: Optional[Path] = None

    if input_path is None:
        source_origin = _find_latest_sketch_png()
        input_path = _copy_to_module_input(source_origin)
        print(f"Using latest sketch: {source_origin.name} -> {input_path}")
    else:
        if not input_path.exists():
            raise FileNotFoundError(f"Input image not found: {input_path}")
        if input_path.parent.resolve() != MODULE_INPUT_DIR.resolve():
            source_origin = input_path
            input_path = _copy_to_module_input(input_path)
            print(f"Copied input image to module workspace: {source_origin} -> {input_path}")

    process_image(input_path, args.output)


if __name__ == "__main__":
    main()