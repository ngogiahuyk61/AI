import json
import os
from pathlib import Path

import numpy as np
from PIL import Image


# --- Cấu hình đường dẫn ---
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = (BASE_DIR / ".." / "input").resolve()
OUTPUT_DIR = (BASE_DIR / ".." / "output").resolve()


def process_mask(json_filename: str, output_filename: str):
    json_path = INPUT_DIR / json_filename
    output_path = OUTPUT_DIR / output_filename

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    grid = np.array(data["grid"], dtype=np.uint8)

    # --- Tạo mask trắng–đen từ grid ---
    # 1 = vùng đất (site)  -> màu trắng (255)
    # 0 = ngoài site       -> màu đen (0)
    mask = np.where(grid == 1, 255, 0).astype(np.uint8)

    # --- Đảo ngược màu ---
    # 255 -> 0, 0 -> 255
    mask_inverted = 255 - mask

    # --- Resize lên 1024×1024 ---
    img_base = Image.fromarray(mask_inverted, mode="L")
    img_1024 = img_base.resize((1024, 1024), Image.NEAREST)

    # --- Lưu kết quả ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img_1024.save(output_path)
    # img.show(title=f"Mask from {json_filename}")

    print(f"✅ Mask inverted and resized saved to: {output_path}")

    if output_filename == "mask_best_region_with_border_1024.png":
        mask_dir = (BASE_DIR / ".." / ".." / "model" / "source" / "mask").resolve()
        mask_dir.mkdir(parents=True, exist_ok=True)
        img_64 = img_base.resize((64, 64), Image.NEAREST)
        mask_path = mask_dir / "mask.png"
        img_64.save(mask_path)
        print(f"✅ Additional 64x64 mask saved to: {mask_path}")


if __name__ == "__main__":
    files = [
        ("site_data.json", "mask_origin_1024.png"),
        ("stie_data_filled.json", "mask_filled_1024.png"),
        ("best_black_region.json", "mask_best_region_1024.png"),
        ("best_black_region_smoothed.json", "mask_best_region_smoothed_1024.png"),
        ("best_black_region_with_border.json", "mask_best_region_with_border_1024.png"),
    ]

    for json_name, output_name in files:
        process_mask(json_name, output_name)
