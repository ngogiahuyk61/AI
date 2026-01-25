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

MODEL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODEL_DIR / "scripts"
SOURCE_DIR = MODEL_DIR / "source"
QUEUE_DIR = SOURCE_DIR / "queue"
PROCESSED_DIR = QUEUE_DIR / "processed"
FAILED_DIR = QUEUE_DIR / "failed"
PROJECT_ROOT = MODEL_DIR.parent.parent
STATIC_IMG_DIR = PROJECT_ROOT / "web_app" / "floorplan_app" / "static" / "floorplan_app" / "img"
STATICFILES_IMG_DIR = PROJECT_ROOT / "web_app" / "staticfiles" / "floorplan_app" / "img"
STATIC_TARGET_FILENAMES = ["floorplan1.png", "proposal1.png"]
MODULE_COORD_ROOMS_DIR = PROJECT_ROOT / "ai_processing" / "module_coordinates_rooms"
MODULE_COORD_ROOMS_OUTPUT_DIR = MODULE_COORD_ROOMS_DIR / "output" / "images"
FINAL_VISUALIZATION_NAME = "room_visualization_no_living.png"
MODULE_DETECT_ROOMS_DIR = PROJECT_ROOT / "ai_processing" / "module_detect_rooms"
GRAFTING_SCRIPT = MODULE_DETECT_ROOMS_DIR / "scripts" / "grafting_rooms.py"
GRAFTING_OUTPUT_IMAGE = MODULE_DETECT_ROOMS_DIR / "outputs" / "overlay_result.png"

DEFAULT_MASK = "source/mask/278.png"
DEFAULT_INTERVAL = 5.0
DEFAULT_BASE_NAME = "278"
DEFAULT_UPSIZE_SIZE = 1024


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


def copy_if_needed(src: Path, dest: Path) -> None:
    if src.resolve() == dest.resolve():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


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
        print(f"[extended-worker] Running {script_path.relative_to(PROJECT_ROOT)}...")
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


def prepare_downstream_inputs(
    base_name: str,
    mask_path: Path,
    mask_upscaled_path: Path,
    new_text_path: Path,
    result_path: Path,
    upsize_size: int,
) -> None:
    mask_target = MODEL_DIR / "source" / "mask" / f"{base_name}.png"
    mask_upscaled_target = MODEL_DIR / "source" / "mask" / f"{base_name}_{upsize_size}.png"
    json_target = MODEL_DIR / "source" / "new_text" / f"{base_name}.json"
    result_target = MODEL_DIR / "source" / "result" / f"{base_name}.png"
    copy_if_needed(mask_path, mask_target)
    copy_if_needed(mask_upscaled_path, mask_upscaled_target)
    copy_if_needed(new_text_path, json_target)
    copy_if_needed(result_path, result_target)


def run_downstream_scripts(
    python_exec: str,
    base_env: dict[str, str],
    verbose: bool,
) -> None:
    scripts = [
        PROJECT_ROOT / "module_floorplan_valid" / "scripts" / "validate_entrance_rooms.py",
        PROJECT_ROOT / "module_floorplan_valid" / "scripts" / "detect_exterior_wall.py",
        PROJECT_ROOT / "module_floorplan_valid" / "scripts" / "shrink_exterior_wall.py",
        PROJECT_ROOT / "module_floorplan_valid" / "scripts" / "remove_background.py",
        PROJECT_ROOT / "module_coordinates_rooms" / "scripts" / "coordinates_room_001.py",
        PROJECT_ROOT / "module_coordinates_rooms" / "scripts" / "coordinates_room_v2.py",
    ]
    for script in scripts:
        run_python_script(python_exec, script, [], PROJECT_ROOT, verbose, base_env)


def run_grafting_and_publish(
    python_exec: str,
    base_env: dict[str, str],
    verbose: bool,
) -> None:
    run_python_script(
        python_exec,
        GRAFTING_SCRIPT,
        [],
        PROJECT_ROOT,
        verbose,
        base_env,
    )

    source = GRAFTING_OUTPUT_IMAGE
    if not source.exists():
        raise FileNotFoundError(f"Final visualization not found: {source}")

    publish_targets: list[Path] = []

    try:
        STATIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATIC_IMG_DIR / name)
    except Exception as static_err:  # pylint: disable=broad-except
        print(f"[extended-worker] Warning: could not ensure static dir {STATIC_IMG_DIR}: {static_err}")

    try:
        STATICFILES_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATICFILES_IMG_DIR / name)
    except Exception as staticfiles_err:  # pylint: disable=broad-except
        print(f"[extended-worker] Warning: could not ensure staticfiles dir {STATICFILES_IMG_DIR}: {staticfiles_err}")

    for target in publish_targets:
        try:
            shutil.copyfile(source, target)
            if verbose:
                rel = target.relative_to(PROJECT_ROOT)
                print(f"[extended-worker] Published visualization to {rel}")
        except Exception as publish_err:  # pylint: disable=broad-except
            print(f"[extended-worker] Warning: could not publish to {target}: {publish_err}")


def process_queue_file(queue_file: Path, args: argparse.Namespace) -> None:
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    job_id = data.get("job_id", queue_file.stem.replace("queue-", ""))
    text_rel = data.get("text_file")
    new_text_rel = data.get("new_text_file")
    result_rel = data.get("result_image")
    if not text_rel or not new_text_rel or not result_rel:
        raise ValueError(f"Queue file {queue_file} is missing required fields")
    text_path = MODEL_DIR / text_rel
    new_text_path = MODEL_DIR / new_text_rel
    result_path = MODEL_DIR / result_rel
    text = load_text(text_path)
    python_exec = args.python or sys.executable
    mask_rel = args.mask
    mask_path = MODEL_DIR / mask_rel
    if not mask_path.exists():
        raise FileNotFoundError(f"Mask not found: {mask_path}")
    simple_args = [
        "--input",
        text,
        "--mask",
        args.mask,
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
    predict_args = [
        "--mask",
        args.mask,
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
    base_name = args.base_name or Path(mask_path.stem).stem
    mask_output_rel = f"source/mask/{base_name}_{args.upsize_size}.png"
    run_upsize_step(
        python_exec,
        result_rel,
        args.mask,
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
    }
    run_downstream_scripts(python_exec, env, args.verbose)
    run_grafting_and_publish(python_exec, env, args.verbose)
    dest = PROCESSED_DIR / queue_file.name
    shutil.move(str(queue_file), dest)
    if args.verbose:
        print(f"[extended-worker] Job {job_id} processed. Outputs ready for downstream modules.")


def mark_failed(queue_file: Path, err: Exception) -> None:
    dest = FAILED_DIR / queue_file.name
    shutil.move(str(queue_file), dest)
    log_path = dest.with_suffix(".log")
    log_path.write_text(str(err), encoding="utf-8")
    print(f"[extended-worker] Job {queue_file.name} failed: {err}")


def process_pending(args: argparse.Namespace) -> bool:
    queue_files = sorted(QUEUE_DIR.glob("queue-*.json"))
    processed_any = False
    for queue_file in queue_files:
        try:
            process_queue_file(queue_file, args)
            processed_any = True
        except Exception as exc:
            mark_failed(queue_file, exc)
    return processed_any


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Extended worker for floorplan pipeline")
    parser.add_argument("--once", action="store_true", help="Process pending jobs once and exit")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Polling interval when watching")
    parser.add_argument("--mask", default=DEFAULT_MASK, help="Relative path to mask image (from model dir)")
    parser.add_argument("--python", help="Python executable to use when running scripts (default: current)")
    parser.add_argument("--invert-mask", action="store_true", default=True, help="Pass --invert-mask to quick_predict (default: on)")
    parser.add_argument("--no-invert-mask", dest="invert_mask", action="store_false", help="Disable --invert-mask")
    parser.add_argument("--verbose", action="store_true", help="Print command output")
    parser.add_argument("--base-name", default=DEFAULT_BASE_NAME, help="Base name used by downstream validation scripts")
    parser.add_argument("--upsize-size", type=int, default=DEFAULT_UPSIZE_SIZE, help="Target size for upsize_images")
    args = parser.parse_args(argv)
    if args.upsize_size <= 0:
        raise ValueError("--upsize-size must be positive")
    ensure_directories()
    if args.once:
        processed = process_pending(args)
        if not processed and args.verbose:
            print("[extended-worker] No pending jobs.")
        return
    if args.verbose:
        print(f"[extended-worker] Watching {QUEUE_DIR} every {args.interval}s (mask={args.mask})")
    try:
        while True:
            processed = process_pending(args)
            if not processed:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("[extended-worker] Stopped by user")


if __name__ == "__main__":
    main()
