from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


BASE_DIR = Path(__file__).resolve().parents[1]
MODULE_OUTPUT_DIR = BASE_DIR / "output"
MODEL_DIR = BASE_DIR.parent / "model"
MASK_DIR = MODEL_DIR / "source" / "mask"


def main() -> None:
    input_path = MODULE_OUTPUT_DIR / "object_centered_64.png"
    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    img = Image.open(input_path).convert("L")

    gray_border = img.filter(ImageFilter.MaxFilter(3))
    border = ImageChops.subtract(gray_border, img)
    final = Image.composite(Image.new("L", img.size, 14), img, border)

    MASK_DIR.mkdir(parents=True, exist_ok=True)
    output_path = MASK_DIR / "1.png"
    final.save(output_path)
    print(f"Saved gray border mask to: {output_path}")


if __name__ == "__main__":
    main()