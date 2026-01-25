import argparse
from pathlib import Path
from PIL import Image

MODEL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESULT = MODEL_DIR / "source" / "result" / "278.png"
DEFAULT_MASK = MODEL_DIR / "source" / "mask" / "278.png"

def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (MODEL_DIR / path).resolve()

def upscale_and_overwrite(image_path: Path, size: int) -> Path:
    if not image_path.is_file():
        raise FileNotFoundError(f"Result image not found: {image_path}")
    image = Image.open(image_path)
    resized = image.resize((size, size), Image.Resampling.BICUBIC)
    temp_path = image_path.parent / f"{image_path.stem}_tmp{image_path.suffix}"
    resized.save(temp_path)
    temp_path.replace(image_path)
    return image_path

def upscale_mask(mask_path: Path, output_path: Path | None, size: int) -> Path:
    if not mask_path.is_file():
        raise FileNotFoundError(f"Mask image not found: {mask_path}")
    if output_path is None:
        output_path = mask_path.parent / f"{mask_path.stem}_{size}{mask_path.suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask = Image.open(mask_path)
    resized = mask.resize((size, size), Image.Resampling.NEAREST)
    resized.save(output_path)
    return output_path

def main() -> None:
    parser = argparse.ArgumentParser(description="Upscale result and mask images to a target size")
    parser.add_argument("--result", default=str(DEFAULT_RESULT), help="Path to the result image to overwrite")
    parser.add_argument("--mask", default=str(DEFAULT_MASK), help="Path to the mask image to upscale")
    parser.add_argument("--mask-output", help="Optional output path for the upscaled mask")
    parser.add_argument("--size", type=int, default=1024, help="Target square size in pixels")
    args = parser.parse_args()

    target_size = args.size
    if target_size <= 0:
        raise ValueError("--size must be a positive integer")

    result_path = resolve_path(args.result)
    mask_path = resolve_path(args.mask)
    mask_output_path = resolve_path(args.mask_output) if args.mask_output else None

    result_final = upscale_and_overwrite(result_path, target_size)
    mask_final = upscale_mask(mask_path, mask_output_path, target_size)

    print(f"Upscaled result saved to: {result_final}")
    print(f"Upscaled mask saved to: {mask_final}")

if __name__ == "__main__":
    main()
