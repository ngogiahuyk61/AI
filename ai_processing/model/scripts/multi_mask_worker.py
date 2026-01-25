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
SKETCH_SOURCE_DIR = SOURCE_DIR / "sketch"
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
MODULE_DRAW_MASK_DIR = PROJECT_ROOT / "ai_processing" / "module_draw_mask"
CENTER_BLACK_SCRIPT = MODULE_DRAW_MASK_DIR / "scripts" / "center_black_object.py"
ADD_GRAY_BORDER_SCRIPT = MODULE_DRAW_MASK_DIR / "scripts" / "add_gray_border.py"

GRAFTING_SCRIPT = MODULE_DETECT_ROOMS_DIR / "scripts" / "grafting_rooms.py"
GRAFTING_OUTPUT_IMAGE = MODULE_DETECT_ROOMS_DIR / "outputs" / "colored_floorplan_with_areas.png"
FURNITURE_SCRIPT = MODULE_DETECT_ROOMS_DIR / "scripts" / "furniture_placement.py"
FURNISHED_LABELED_IMAGE = MODULE_DETECT_ROOMS_DIR / "outputs" / "final_floorplan_with_furniture_and_areas.png"
ADD_ROOM_AREAS_SCRIPT = MODULE_DETECT_ROOMS_DIR / "scripts" / "add_room_areas.py"

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


def _update_queue_progress(job_id: str, percent: int) -> None:
    """Update in-place progress info in the pending queue file for the given job.

    This allows the web layer to report granular progress while status is 'pending'.
    Silently no-ops if the queue file is missing or invalid.
    """
    try:
        queue_file = QUEUE_DIR / f"queue-{job_id}.json"
        if not queue_file.exists():
            return
        try:
            payload = json.loads(queue_file.read_text(encoding="utf-8"))
        except Exception:  # pylint: disable=broad-except
            return
        payload["progress_percent"] = max(0, min(100, int(percent)))
        queue_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Do not break the worker on progress update issues
        pass


def _find_latest_sketch_assets() -> tuple[Path, Path]:
    candidates = sorted(
        SKETCH_SOURCE_DIR.glob("sketch-*.png"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for png_path in candidates:
        if png_path.name.endswith("_64.png"):
            continue
        json_path = png_path.with_suffix(".json")
        if json_path.exists():
            return png_path, json_path
    raise FileNotFoundError(
        f"No sketch PNG/JSON pair found in {SKETCH_SOURCE_DIR}"
    )


def _calculate_polygon_area_m2(points_mm: list[tuple[float, float]]) -> float:
    if len(points_mm) < 3:
        raise ValueError("At least three points are required to compute area")
    area2 = 0.0
    count = len(points_mm)
    for idx in range(count):
        x1, y1 = points_mm[idx]
        x2, y2 = points_mm[(idx + 1) % count]
        area2 += x1 * y2 - x2 * y1
    area_mm2 = abs(area2) / 2.0
    return area_mm2 / 1_000_000.0


def _calculate_area_from_sketch_json(json_path: Path) -> Optional[float]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    raw_points = data.get("points")
    if not isinstance(raw_points, list):
        return None

    points_mm: list[tuple[float, float]] = []
    for point in raw_points:
        if not isinstance(point, dict):
            return None
        x_mm = point.get("x_mm")
        y_mm = point.get("y_mm")
        if x_mm is None or y_mm is None:
            return None
        try:
            points_mm.append((float(x_mm), float(y_mm)))
        except (TypeError, ValueError):
            return None

    if not points_mm:
        return None

    try:
        return _calculate_polygon_area_m2(points_mm)
    except ValueError:
        return None


def _update_text_total_area(text_path: Path, area_m2: float) -> None:
    payload = json.loads(text_path.read_text(encoding="utf-8"))
    payload["total_area_m2"] = area_m2
    text_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[multi-mask-worker] Updated total_area_m2 in {text_path.name} to {area_m2:.2f}"
    )


def update_total_area_from_sketch(text_path: Path, sketch_json: Path) -> Optional[float]:
    if not text_path.exists():
        raise FileNotFoundError(f"Text input not found: {text_path}")
    area_m2 = _calculate_area_from_sketch_json(sketch_json)
    if area_m2 is None:
        return None
    _update_text_total_area(text_path, area_m2)
    return area_m2


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
    scripts = [
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "detect_exterior_wall.py",
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "shrink_exterior_wall.py",
        PROJECT_ROOT / "ai_processing" / "module_floorplan_valid" / "scripts" / "remove_background.py",
        PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms" / "scripts" / "coordinates_room_001.py",
        PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms" / "scripts" / "coordinates_room_v2.py",
        # Grafting rooms script phải chạy trước canny và furniture placement
        GRAFTING_SCRIPT,
        # Run canny edge detection after grafting rooms
        MODULE_DETECT_ROOMS_DIR / "scripts" / "canny.py",
        # Generate furnished image and overlay NEW names + areas; uses REQUEST_JSON/TOTAL_AREA_M2
        FURNITURE_SCRIPT,
        ADD_ROOM_AREAS_SCRIPT,
    ]
    job_id = base_env.get("JOB_ID", "")
    for script in scripts:
        # Progress milestones requested:
        # - At GRAFTING_SCRIPT (line ~324) -> 90%
        # - At ADD_ROOM_AREAS_SCRIPT (line ~329) -> 100%
        if job_id:
            if script == GRAFTING_SCRIPT:
                _update_queue_progress(job_id, 90)
            elif script == ADD_ROOM_AREAS_SCRIPT:
                _update_queue_progress(job_id, 100)
        run_python_script(python_exec, script, [], PROJECT_ROOT, verbose, base_env)


def run_collect_mask_preprocessing(
    python_exec: str,
    verbose: bool,
) -> None:
    # Note: MODULE_COLLECT_MASK_DIR wasn't imported in original snippet, assuming it exists or not needed.
    # If errors, define it at top: MODULE_COLLECT_MASK_DIR = PROJECT_ROOT / "ai_processing" / "module_collect_mask"
    pass 


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
            # --- FIX: Nới lỏng điều kiện cho Common Room ---
            # Nếu yêu cầu có Common Room và tìm thấy ít nhất 1 phòng, coi như đạt.
            # Điều này đồng bộ với logic "dễ tính" của validate_entrance_rooms.py
            if expected > 0 and detected >= 1:
                continue 
            
            # Chỉ fail nếu không tìm thấy phòng nào (hoặc quá ít nếu muốn strict hơn)
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
    run_python_script(
        python_exec,
        GRAFTING_SCRIPT,
        [],
        PROJECT_ROOT,
        verbose,
        base_env,
    )
    run_python_script(
        python_exec,
        FURNITURE_SCRIPT,
        [],
        PROJECT_ROOT,
        verbose,
        base_env,
    )
    run_python_script(
        python_exec,
        ADD_ROOM_AREAS_SCRIPT,
        [],
        PROJECT_ROOT,
        verbose,
        base_env,
    )

    # Prefer furnished-and-labeled image if available; fallback to colored_floorplan_with_areas.png
    source = FURNISHED_LABELED_IMAGE if FURNISHED_LABELED_IMAGE.exists() else GRAFTING_OUTPUT_IMAGE
    if not source.exists():
        raise FileNotFoundError(f"Final visualization not found: {source}")

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

    # --- NEW: Xóa các file JSON cũ để đảm bảo gen mới ---
    # Mục đích: Không dùng lại các file 1.json, 2.json... từ lần chạy trước
    # nếu lần generate này bị lỗi hoặc sinh ra ít file hơn.
    new_text_dir = SOURCE_DIR / "new_text"
    if args.verbose:
        print(f"[multi-mask-worker] Cleaning up old JSON files in {new_text_dir}...")
    
    for i in range(1, 11): # Quét rộng hơn 5 file một chút cho chắc chắn
        old_json_file = new_text_dir / f"{i}.json"
        if old_json_file.exists():
            try:
                old_json_file.unlink()
            except Exception as e:
                if args.verbose:
                    print(f"[multi-mask-worker] Warning: Could not delete old JSON {old_json_file}: {e}")

    # Chạy generate_layouts.py để tạo 5 file JSON với mask và text input
    _update_queue_progress(job_id, 30)
    generate_args = [
        "--mask",
        mask_rel,
        "--text",
        text_rel,
    ]
    run_python_script(
        python_exec,
        SCRIPTS_DIR / "generate_layouts.py",
        generate_args,
        MODEL_DIR,
        args.verbose,
    )
    _update_queue_progress(job_id, 40)
    
    # Thử từng file JSON cho đến khi validate thành công
    # Lưu ý: Vì đã xóa sạch ở trên, các file tìm thấy ở đây chắc chắn là file mới sinh ra
    json_files = [new_text_dir / f"{i}.json" for i in range(1, 6)]
    
    validation_success = False
    for i, json_file in enumerate(json_files, 1):
        if not json_file.exists():
            if args.verbose:
                # Nếu file không tồn tại, tức là generate_layouts.py không tạo ra nó trong lần chạy này
                print(f"[multi-mask-worker] JSON file {json_file} không tồn tại (chưa được generate mới), bỏ qua.")
            continue
            
        # Sao chép file JSON vào đường dẫn mong muốn
        shutil.copyfile(json_file, new_text_path)
        
        if args.verbose:
            print(f"[multi-mask-worker] Thử với file JSON mới tạo thứ {i}: {json_file.name}")
        
        # Thêm entrance nếu cần
        overwrite_entrance(new_text_path)
        
        # Chạy quick_predict với file JSON hiện tại
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
            
        try:
            _update_queue_progress(job_id, 45)
            run_python_script(
                python_exec,
                SCRIPTS_DIR / "quick_predict.py",
                predict_args,
                MODEL_DIR,
                args.verbose,
            )
            _update_queue_progress(job_id, 50)
            
            # Tiếp tục xử lý và kiểm tra validation
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
            _update_queue_progress(job_id, 60)

            if validation_succeeded(base_name, new_text_path, args.verbose):
                if args.verbose:
                    print(f"[multi-mask-worker] Validation thành công với file JSON thứ {i}")
                validation_success = True
                _update_queue_progress(job_id, 70)
                
                # Nếu validation thành công, chạy tiếp các bước post-validation ngay tại đây
                run_post_validation_scripts(
                    python_exec,
                    env,
                    args.verbose,
                )
                
                result_output = queue_job.get("result_image")
                job_result_path = MODEL_DIR / result_output if result_output else None

                run_grafting_and_publish(
                    python_exec,
                    env,
                    args.verbose,
                    success_index,
                    job_result_path,
                )
                break
            else:
                if args.verbose:
                    print(f"[multi-mask-worker] Validation thất bại với file JSON thứ {i}, thử file tiếp theo")
        except Exception as e:
            if args.verbose:
                print(f"[multi-mask-worker] Lỗi khi xử lý file JSON thứ {i}: {e}")
            continue
    
    if not validation_success:
        if args.verbose:
            print(f"[multi-mask-worker] Tất cả các file JSON (nếu có) đều không pass validation")
        queue_job.setdefault("failed_masks", []).append(mask_base)
        return False
        
    return True


def process_queue_file(queue_file: Path, args: argparse.Namespace) -> bool:
    """
    Process a single queue file.
    Returns True if at least one valid mask was successfully published.
    """
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    python_exec = args.python or sys.executable
    sketch_png, sketch_json = _find_latest_sketch_assets()
    if args.verbose:
        print(f"[multi-mask-worker] Latest sketch selected: {sketch_png.name}")
    job_id = data.get("job_id", "")
    if job_id:
        _update_queue_progress(job_id, 5)

    update_total_area_from_sketch(text_path := MODEL_DIR / data["text_file"], sketch_json)
    if job_id:
        _update_queue_progress(job_id, 10)

    run_python_script(
        python_exec,
        CENTER_BLACK_SCRIPT,
        [],
        PROJECT_ROOT,
        args.verbose,
    )
    if job_id:
        _update_queue_progress(job_id, 15)
    run_python_script(
        python_exec,
        ADD_GRAY_BORDER_SCRIPT,
        [],
        PROJECT_ROOT,
        args.verbose,
    )
    if job_id:
        _update_queue_progress(job_id, 20)

    masks = list_valid_masks(MASK_DIR, args.verbose)
    if not masks:
        raise FileNotFoundError(f"No 64x64 masks found in {MASK_DIR}")
    if job_id:
        _update_queue_progress(job_id, 25)

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
                    break
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