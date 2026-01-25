import sys
from pathlib import Path

import numpy as np
from PIL import Image


def describe_colors(image_path: Path) -> None:
    img = Image.open(image_path).convert("RGBA")
    arr = np.array(img)
    flat = arr.reshape(-1, arr.shape[-1])
    unique, counts = np.unique(flat, axis=0, return_counts=True)
    total = flat.shape[0]
    print(f"File: {image_path}")
    print(f"Image shape: {arr.shape}")
    print(f"Unique colors: {len(unique)}")
    for color, count in sorted(zip(unique, counts), key=lambda x: -x[1]):
        rgba = tuple(int(v) for v in color)
        pct = count / total * 100
        print(f"  {rgba} -> {count} pixels ({pct:.2f}% of image)")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tmp_color_stats.py <image_path> [<image_path> ...]")
        sys.exit(1)
    for arg in sys.argv[1:]:
        describe_colors(Path(arg))


if __name__ == "__main__":
    main()
