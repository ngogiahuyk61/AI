from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from PIL import Image

MODEL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODEL_DIR / "scripts"
SOURCE_DIR = MODEL_DIR / "source"
QUEUE_DIR = SOURCE_DIR / "queue"
PROCESSED_DIR = QUEUE_DIR / "processed"
FAILED_DIR = QUEUE_DIR / "failed"
PROJECT_ROOT = MODEL_DIR.parent.parent
MASK_DIR = SOURCE_DIR / "mask"
NEW_TEXT_DIR = SOURCE_DIR / "new_text"
RESULT_DIR = SOURCE_DIR / "result"

STATIC_IMG_DIR = PROJECT_ROOT / "web_app" / "floorplan_app" / "static" / "floorplan_app" / "img"
STATICFILES_IMG_DIR = PROJECT_ROOT / "web_app" / "staticfiles" / "floorplan_app" / "img"
STATIC_FLOORPLAN_PREFIX = "floorplan"
STATIC_PROPOSAL_PREFIX = "proposal"

MODULE_FLOORPLAN_VALID_DIR = PROJECT_ROOT / "ai_processing" / "module_floorplan_valid"
MODULE_FLOORPLAN_VALID_OUTPUT_IMG_DIR = MODULE_FLOORPLAN_VALID_DIR / "output" / "images"
MODULE_FLOORPLAN_VALID_OUTPUT_JSON_DIR = MODULE_FLOORPLAN_VALID_DIR / "output" / "json"
MODULE_COORD_ROOMS_DIR = PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms"
MODULE_DETECT_ROOMS_DIR = PROJECT_ROOT / "ai_processing" / "module_detect_rooms"
MODULE_COLLECT_MASK_DIR = PROJECT_ROOT / "ai_processing" / "module_collect_mask"

# --- CẤU HÌNH CÁC FILE SCRIPT CHO MODULE DETECT ROOMS (13 FILES) ---
DETECT_SCRIPTS_DIR = MODULE_DETECT_ROOMS_DIR / "scripts"
DETECT_OUTPUT_DIR = MODULE_DETECT_ROOMS_DIR / "outputs"

# Thứ tự chạy 13 file theo yêu cầu
DETECT_ROOMS_PIPELINE = [
    "grafting_rooms.py",       # 1. Tạo dữ liệu phòng cơ bản
    "add_room_areas.py",       # 2. Thêm thông tin diện tích
    "create_boundary.py",      # 3. Tạo ranh giới các phòng
    "canny.py",                # 4. Xử lý biên ảnh
    "furniture_placement.py",  # 5. Điều phối chính (setup placement)
    "add_entrance.py",         # 6. Thêm cửa chính
    "add_door.py",             # 7. Thêm cửa phòng
    "add_window.py",           # 8. Thêm cửa sổ
    "sliding_bathroom.py",     # 9. Xử lý phòng tắm
    "add_bed.py",              # 10. Thêm giường
    "add_table.py",            # 11. Thêm bàn
    "add_toilet.py",           # 12. Thêm bồn cầu
    "render_image.py",         # 13. Render hình ảnh cuối cùng
]

# Ảnh đầu ra cuối cùng từ file render_image.py
FINAL_RENDER_IMAGE = DETECT_OUTPUT_DIR / "final_floorplan.png"

DEFAULT_INTERVAL = 5.0
DEFAULT_UPSIZE_SIZE = 1024
DEFAULT_ENTRANCE_OVERRIDE = {"num": 1, "rooms": []}

VALIDATION_TIMEOUT = 30.0
MAX_PUBLISHED_IMAGES = 3

ROOM_NAME_MAPPING = {
    "LivingRoom": "Living Room",
    "MasterRoom": "Master Room",
    "Kitchen": "Kitchen",
    "Bathroom": "Bathroom",
    "DiningRoom": "Dining Room",
    "Balcony": "Balcony",
    "Entrance": "Entrance",
    "Storage": "Storage",
}

# Các loại phòng được phát hiện là "Common Room" (màu vàng)
COMMON_ROOM_TYPES = {"ChildRoom", "SecondRoom", "GuestRoom", "StudyRoom"}

IGNORED_DETECTED_ROOMS = {"ExteriorWall", "InteriorWall"}


def run_command(cmd: list[str], *, cwd: Path, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")
    merged_env.setdefault("PYTHONUTF8", "1")
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
        check=False,
    )


def ensure_directories() -> None:
    for path in (SOURCE_DIR, QUEUE_DIR, PROCESSED_DIR, FAILED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_text(text_file: Path) -> str:
    payload = json.loads(text_file.read_text(encoding="utf-8"))
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError(f"Invalid text payload in {text_file}")
    return text


def load_text_with_metadata(text_file: Path) -> tuple[str, dict]:
    """Load text and return both text and full payload for metadata extraction"""
    payload = json.loads(text_file.read_text(encoding="utf-8"))
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError(f"Invalid text payload in {text_file}")
    return text, payload


def overwrite_entrance(json_path: Path) -> None:
    if not json_path.exists():
        raise FileNotFoundError(f"Generated layout JSON not found: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    entrance = data.setdefault("Entrance", {})
    entrance.update(DEFAULT_ENTRANCE_OVERRIDE)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_python_script(
    python_exec: str,
    script_path: Path,
    extra_args: list[str],
    cwd: Path,
    verbose: bool,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [python_exec, str(script_path), *extra_args]
    if verbose:
        print(f"[multi-mask-worker] Running {script_path.relative_to(PROJECT_ROOT)}...")
    completed = run_command(cmd, cwd=cwd, env=env)
    if verbose:
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{script_path.name} failed: {completed.stderr or completed.stdout}"
        )
    return completed


def run_upsize_step(
    python_exec: str,
    result_rel: str,
    mask_rel: str,
    mask_output_rel: str,
    size: int,
    verbose: bool,
) -> None:
    args = [
        "--result",
        result_rel,
        "--mask",
        mask_rel,
        "--mask-output",
        mask_output_rel,
        "--size",
        str(size),
    ]
    run_python_script(
        python_exec,
        SCRIPTS_DIR / "upsize_images.py",
        args,
        MODEL_DIR,
        verbose,
    )


def copy_if_needed(src: Path, dest: Path) -> None:
    if src.resolve() == dest.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def prepare_downstream_inputs(
    base_name: str,
    mask_path: Path,
    mask_upscaled_path: Path,
    new_text_path: Path,
    result_path: Path,
    upsize_size: int,
) -> None:
    mask_target = SOURCE_DIR / "mask" / f"{base_name}.png"
    mask_upscaled_target = SOURCE_DIR / "mask" / f"{base_name}_{upsize_size}.png"
    json_target = SOURCE_DIR / "new_text" / f"{base_name}.json"
    result_target = SOURCE_DIR / "result" / f"{base_name}.png"
    copy_if_needed(mask_path, mask_target)
    copy_if_needed(mask_upscaled_path, mask_upscaled_target)
    copy_if_needed(new_text_path, json_target)
    copy_if_needed(result_path, result_target)


def run_validation(
    python_exec: str,
    base_env: dict[str, str],
    verbose: bool,
) -> None:
    run_python_script(
        python_exec,
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "validate_entrance_rooms.py",
        [],
        PROJECT_ROOT,
        verbose,
        base_env,
    )


def run_post_validation_scripts(
    python_exec: str,
    base_env: dict[str, str],
    verbose: bool,
) -> None:
    # 1. Các bước chuẩn bị dữ liệu (Valid, Coordinates)
    prep_scripts = [
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "detect_exterior_wall.py",
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "shrink_exterior_wall.py",
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "remove_background.py",
        PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms" / "scripts" / "coordinates_room_001.py",
        PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms" / "scripts" / "coordinates_room_v2.py",
    ]
    
    if verbose:
        print("[multi-mask-worker] Running preparation scripts...")
    for script in prep_scripts:
        run_python_script(python_exec, script, [], PROJECT_ROOT, verbose, base_env)

    # 2. Chạy chuỗi 13 file của MODULE_DETECT_ROOMS
    if verbose:
        print("[multi-mask-worker] Running module_detect_rooms 13-file pipeline...")
    
    for script_name in DETECT_ROOMS_PIPELINE:
        script_path = DETECT_SCRIPTS_DIR / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"Detect room script not found: {script_path}")
        
        run_python_script(python_exec, script_path, [], PROJECT_ROOT, verbose, base_env)


def run_collect_mask_preprocessing(
    python_exec: str,
    verbose: bool,
) -> None:
    site_data_path = MODULE_COLLECT_MASK_DIR / "input" / "site_data.json"
    if not site_data_path.exists():
        raise FileNotFoundError(f"Expected site data at {site_data_path} before preprocessing")

    scripts = [
        MODULE_COLLECT_MASK_DIR / "scripts" / "fill_zero_regions.py",
        MODULE_COLLECT_MASK_DIR / "scripts" / "generate_best_black_region.py",
        MODULE_COLLECT_MASK_DIR / "scripts" / "smooth_sharp_white_regions.py",
        MODULE_COLLECT_MASK_DIR / "scripts" / "add_border_to_best_region.py",
    ]
    for script in scripts:
        run_python_script(python_exec, script, [], PROJECT_ROOT, verbose)


def list_valid_masks(mask_dir: Path, verbose: bool) -> list[Path]:
    masks = sorted(mask_dir.glob("*.png"))
    valid: list[Path] = []
    for mask_path in masks:
        try:
            with Image.open(mask_path) as img:
                if img.size == (64, 64):
                    valid.append(mask_path)
                elif verbose:
                    rel = mask_path.relative_to(MODEL_DIR)
                    print(f"[multi-mask-worker] Skipping mask {rel} with size {img.size}.")
        except Exception as err:  # pylint: disable=broad-except
            if verbose:
                rel = mask_path.relative_to(MODEL_DIR)
                print(f"[multi-mask-worker] Could not inspect mask {rel}: {err}")
    return valid


def _load_expected_room_counts(new_text_path: Path) -> dict[str, int]:
    if not new_text_path.exists():
        return {}
    payload = json.loads(new_text_path.read_text(encoding="utf-8"))
    expected: dict[str, int] = {}
    common_room_total = 0
    
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        num = value.get("num")
        if not isinstance(num, int):
            continue
        
        # Các loại phòng common (SecondRoom, ChildRoom, etc.) được gộp thành "Common Room"
        if key in COMMON_ROOM_TYPES:
            common_room_total += num
        else:
            mapped = ROOM_NAME_MAPPING.get(key, key)
            expected[mapped] = expected.get(mapped, 0) + num
    
    if common_room_total > 0:
        expected["Common Room"] = common_room_total
    
    return expected


def validation_succeeded(base_name: str, new_text_path: Path, verbose: bool) -> bool:
    json_path = MODULE_FLOORPLAN_VALID_OUTPUT_JSON_DIR / f"room_coordinates_{base_name}.json"
    if not json_path.exists():
        return False
    data = json.loads(json_path.read_text(encoding="utf-8"))
    detected_counts: dict[str, int] = {}
    for room_name, room_info in data.items():
        if room_name in IGNORED_DETECTED_ROOMS:
            continue
        if not isinstance(room_info, dict):
            continue
        detected = room_info.get("num")
        if isinstance(detected, int):
            detected_counts[room_name] = detected
        else:
            coordinates = room_info.get("coordinates")
            if isinstance(coordinates, list):
                detected_counts[room_name] = len(coordinates)

    expected_counts = _load_expected_room_counts(new_text_path)

    # Check for mismatches against expected counts
    for room_name, expected in expected_counts.items():
        detected = detected_counts.get(room_name, 0)
        if room_name == "Common Room":
            if detected < expected:
                if verbose:
                    print(
                        f"[multi-mask-worker] Validation mismatch for '{room_name}': expected >= {expected}, detected {detected}."
                    )
                return False
            continue
        if expected != detected:
            if verbose:
                print(
                    f"[multi-mask-worker] Validation mismatch for '{room_name}': expected {expected}, detected {detected}."
                )
            return False

    # If unexpected rooms (not in expected_counts) appear with count > 0, flag mismatch
    for room_name, detected in detected_counts.items():
        if room_name in expected_counts or room_name in IGNORED_DETECTED_ROOMS:
            continue
        if room_name == "Common Room":
            # Cho phép Common Room phát hiện nhiều hơn yêu cầu
            continue
        if detected > 0:
            if verbose:
                print(
                    f"[multi-mask-worker] Validation mismatch for unexpected room '{room_name}': detected {detected} but not requested."
                )
            return False

    return True


def run_grafting_and_publish(
    python_exec: str,
    base_env: dict[str, str],
    verbose: bool,
    success_index: int,
    job_result_path: Optional[Path],
) -> None:
    # Lưu ý: Grafting (grafting_rooms.py) đã được chạy trong run_post_validation_scripts (bước 1 của 13 bước).
    # Hàm này bây giờ chỉ chịu trách nhiệm publish kết quả (FINAL_RENDER_IMAGE)

    source = FINAL_RENDER_IMAGE
    if not source.exists():
        raise FileNotFoundError(f"Final visualization not found at: {source}")

    publish_targets: list[Path] = []

    try:
        STATIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
        publish_targets.extend(
            [
                STATIC_IMG_DIR / f"{STATIC_FLOORPLAN_PREFIX}{success_index}.png",
                STATIC_IMG_DIR / f"{STATIC_PROPOSAL_PREFIX}{success_index}.png",
            ]
        )
    except Exception as static_err:  # pylint: disable=broad-except
        print(f"[multi-mask-worker] Warning: could not ensure static dir {STATIC_IMG_DIR}: {static_err}")

    try:
        STATICFILES_IMG_DIR.mkdir(parents=True, exist_ok=True)
        publish_targets.extend(
            [
                STATICFILES_IMG_DIR / f"{STATIC_FLOORPLAN_PREFIX}{success_index}.png",
                STATICFILES_IMG_DIR / f"{STATIC_PROPOSAL_PREFIX}{success_index}.png",
            ]
        )
    except Exception as staticfiles_err:  # pylint: disable=broad-except
        print(f"[multi-mask-worker] Warning: could not ensure staticfiles dir {STATICFILES_IMG_DIR}: {staticfiles_err}")

    for target in publish_targets:
        try:
            shutil.copyfile(source, target)
            if verbose:
                rel = target.relative_to(PROJECT_ROOT)
                print(f"[multi-mask-worker] Published visualization to {rel}")
        except Exception as publish_err:  # pylint: disable=broad-except
            print(f"[multi-mask-worker] Warning: could not publish to {target}: {publish_err}")

    if job_result_path is not None:
        try:
            job_result_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, job_result_path)
            if verbose:
                rel = job_result_path.relative_to(PROJECT_ROOT)
                print(f"[multi-mask-worker] Saved job result to {rel}")
        except Exception as result_err:  # pylint: disable=broad-except
            print(f"[multi-mask-worker] Warning: could not save job result {job_result_path}: {result_err}")


def process_for_mask(
    mask_path: Path,
    args: argparse.Namespace,
    queue_job: dict,
    success_index: int,
) -> bool:
    mask_rel = mask_path.relative_to(MODEL_DIR).as_posix()
    mask_base = mask_path.stem
    job_id = queue_job.get("job_id", mask_base)
    python_exec = args.python or sys.executable
    text_rel = queue_job.get("text_file")
    new_text_rel = queue_job.get("new_text_file")
    result_rel = queue_job.get("result_image")

    if not text_rel or not new_text_rel or not result_rel:
        raise ValueError("Queue job missing required fields")

    text_path = MODEL_DIR / text_rel
    new_text_path = MODEL_DIR / new_text_rel
    result_path = MODEL_DIR / result_rel

    text, text_payload = load_text_with_metadata(text_path)
    total_area_m2 = text_payload.get("total_area_m2", 100.0)

    simple_args = [
        "--input",
        text,
        "--mask",
        mask_rel,
        "--output",
        new_text_rel,
    ]
    run_python_script(
        python_exec,
        SCRIPTS_DIR / "simple_to_json.py",
        simple_args,
        MODEL_DIR,
        args.verbose,
    )

    new_text_abs = MODEL_DIR / new_text_rel
    overwrite_entrance(new_text_abs)

    predict_args = [
        "--mask",
        mask_rel,
        "--json",
        new_text_rel,
        "--output",
        result_rel,
    ]
    if args.invert_mask:
        predict_args.append("--invert-mask")
    run_python_script(
        python_exec,
        SCRIPTS_DIR / "quick_predict.py",
        predict_args,
        MODEL_DIR,
        args.verbose,
    )

    base_name = mask_base
    mask_output_rel = f"source/mask/{base_name}_{args.upsize_size}.png"
    run_upsize_step(
        python_exec,
        result_rel,
        mask_rel,
        mask_output_rel,
        args.upsize_size,
        args.verbose,
    )

    mask_upscaled_path = MODEL_DIR / mask_output_rel
    prepare_downstream_inputs(
        base_name,
        mask_path,
        mask_upscaled_path,
        new_text_path,
        result_path,
        args.upsize_size,
    )

    env = {
        "TARGET_BASE_NAME": base_name,
        "UPSCALED_SIZE": str(args.upsize_size),
        "JOB_ID": job_id,
        "TOTAL_AREA_M2": str(total_area_m2),
        "REQUEST_JSON": str(new_text_path),
    }

    run_validation(python_exec, env, args.verbose)

    if not validation_succeeded(base_name, new_text_path, args.verbose):
        if args.verbose:
            print(f"[multi-mask-worker] Validation failed for mask {mask_base}, skipping remaining steps.")
        queue_job.setdefault("failed_masks", []).append(mask_base)
        return False

    # Chạy validation scripts + 13 file detect rooms
    run_post_validation_scripts(python_exec, env, args.verbose)

    result_output = queue_job.get("result_image")
    job_result_path = MODEL_DIR / result_output if result_output else None

    # Publish kết quả
    run_grafting_and_publish(
        python_exec,
        env,
        args.verbose,
        success_index,
        job_result_path,
    )

    return True


def process_queue_file(queue_file: Path, args: argparse.Namespace) -> bool:
    """
    Process a single queue file.
    Returns True if at least one valid mask was successfully published.
    """
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    python_exec = args.python or sys.executable
    run_collect_mask_preprocessing(python_exec, args.verbose)
    masks = list_valid_masks(MASK_DIR, args.verbose)
    if not masks:
        raise FileNotFoundError(f"No 64x64 masks found in {MASK_DIR}")

    processed_any = False
    success_count = 0
    for idx, mask_path in enumerate(masks, start=1):
        if args.limit_masks and idx > args.limit_masks:
            break
        if success_count >= MAX_PUBLISHED_IMAGES:
            break
        try:
            success = process_for_mask(mask_path, args, data, success_count + 1)
            if success:
                success_count += 1
                processed_any = True
                data["published_slot"] = success_count
                if args.verbose:
                    print(f"[multi-mask-worker] Successfully processed mask {mask_path.name} (slot {success_count}).")
                break
        except Exception as mask_error:  # pylint: disable=broad-except
            print(f"[multi-mask-worker] Mask {mask_path.name} failed: {mask_error}")
            data.setdefault("failed_masks", []).append(mask_path.stem)


    dest_dir = PROCESSED_DIR if processed_any else FAILED_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / queue_file.name
    shutil.move(str(queue_file), dest)
    if not processed_any:
        log_path = dest.with_suffix(".log")
        log_path.write_text("No masks succeeded", encoding="utf-8")
        print(f"[multi-mask-worker] Job {queue_file.name} failed for all masks.")
    elif args.verbose:
        print(f"[multi-mask-worker] Job {queue_file.name} processed for {sum(1 for _ in masks)} mask(s).")
    
    return processed_any


def process_pending(args: argparse.Namespace) -> bool:
    queue_files = sorted(QUEUE_DIR.glob("queue-*.json"))
    if args.once and args.verbose:
        print(f"[multi-mask-worker] Found {len(queue_files)} pending queue file(s). Processing first one only (--once mode).")
    elif args.verbose and len(queue_files) > 0:
        print(f"[multi-mask-worker] Found {len(queue_files)} pending queue file(s). Processing each until valid result.")
    
    processed_any = False
    for queue_file in queue_files:
        try:
            success = process_queue_file(queue_file, args)
            if success:
                processed_any = True
                if args.verbose:
                    print(f"[multi-mask-worker] Queue {queue_file.name} completed with valid result. Moving to next queue.")
        except Exception as exc:  # pylint: disable=broad-except
            dest = FAILED_DIR / queue_file.name
            shutil.move(str(queue_file), dest)
            log_path = dest.with_suffix(".log")
            log_path.write_text(str(exc), encoding="utf-8")
            print(f"[multi-mask-worker] Job {queue_file.name} failed: {exc}")
        finally:
            if args.once:
                if args.verbose:
                    print(f"[multi-mask-worker] --once mode: stopping after processing {queue_file.name}.")
                break
    return processed_any


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Multi-mask worker for floorplan pipeline")
    parser.add_argument("--once", action="store_true", help="Process pending jobs once and exit")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Polling interval when watching")
    parser.add_argument("--python", help="Python executable to use when running scripts (default: current)")
    parser.add_argument("--invert-mask", action="store_true", default=True, help="Pass --invert-mask to quick_predict (default: on)")
    parser.add_argument("--no-invert-mask", dest="invert_mask", action="store_false", help="Disable --invert-mask")
    parser.add_argument("--verbose", action="store_true", help="Print command output")
    parser.add_argument("--upsize-size", type=int, default=DEFAULT_UPSIZE_SIZE, help="Target size for upsize_images")
    parser.add_argument("--limit-masks", type=int, help="Optional limit on number of masks to process per job")
    args = parser.parse_args(argv)

    if args.upsize_size <= 0:
        raise ValueError("--upsize-size must be positive")

    ensure_directories()

    if args.once:
        processed = process_pending(args)
        if not processed and args.verbose:
            print("[multi-mask-worker] No pending jobs.")
        return

    if args.verbose:
        print(f"[multi-mask-worker] Watching {QUEUE_DIR} every {args.interval}s")

    try:
        while True:
            processed = process_pending(args)
            if not processed:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("[multi-mask-worker] Stopped by user")


if __name__ == "__main__":
    main()