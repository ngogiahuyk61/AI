"""Queue worker to process floorplan generation jobs.

Run this script in the CPU-only environment. It watches the
`model/source/queue/` directory for JSON job descriptors produced by the web
app and executes `simple_to_json.py` and `quick_predict.py` for each job.
"""
from __future__ import annotations

import argparse
import os
import json
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

FURN_DOORS_DIR = PROJECT_ROOT / "ai_processing" / "furnitures_doors"
FURN_INPUT_DIR = FURN_DOORS_DIR / "data" / "input"
FURN_OUTPUT_DIR = FURN_DOORS_DIR / "outputs"
FURN_OUTPUT_IMAGE = FURN_OUTPUT_DIR / "img" / "floorplan_with_furniture.png"
# Updated to use the new workflow in module_detect_rooms
FURN_SCRIPTS = [
    "scripts/grafting_rooms.py",
    "scripts/furniture_placement.py",
    "scripts/add_room_areas.py"
]

DEFAULT_MASK = "source/mask/278.png"
DEFAULT_INTERVAL = 5.0


def run_command(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Execute a command and capture output."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(  # nosec B603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
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


def prepare_furniture_inputs(result_image: Path, layout_json: Path) -> None:
    FURN_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result_image, FURN_INPUT_DIR / "drawing.png")
    shutil.copyfile(layout_json, FURN_INPUT_DIR / "layout_init.json")


def run_furniture_pipeline(
    python_exec: str,
    job_id: str,
    result_image: Path,
    layout_json: Path,
    verbose: bool,
) -> Path:
    # Define the output directory for module_detect_rooms
    output_dir = Path("E:/ai-key-plan-develop/ai_processing/module_detect_rooms/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy the input image to the module_detect_rooms/inputs directory
    input_dir = Path("E:/ai-key-plan-develop/ai_processing/module_detect_rooms/inputs")
    input_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy the input files to the module_detect_rooms directory
    input_img = input_dir / "img.png"
    shutil.copy2(result_image, input_img)
    
    # Copy the layout JSON if it exists
    if layout_json.exists():
        shutil.copy2(layout_json, input_dir / "layout.json")
    
    # Run each script in the correct order
    for script_rel in FURN_SCRIPTS:
        script_path = Path("E:/ai-key-plan-develop/ai_processing/module_detect_rooms") / script_rel
        if not script_path.exists():
            raise RuntimeError(f"Script not found: {script_path}")
        
        cmd = [python_exec, str(script_path)]
        if verbose:
            print(f"[queue-worker] Running {script_rel} for job {job_id}...")
        
        # Run the script in the module_detect_rooms directory
        completed = run_command(cmd, cwd=script_path.parent.parent)
        
        if verbose:
            print(completed.stdout)
            if completed.stderr:
                print(completed.stderr, file=sys.stderr)
        
        if completed.returncode != 0:
            raise RuntimeError(
                f"Script {script_rel} failed for job {job_id}: "
                f"{completed.stderr or completed.stdout}"
            )
    
    # The final output should be the one with furniture and areas
    final_image = output_dir / "colored_floorplan_with_furniture_and_areas.png"
    
    if not final_image.exists():
        # Fallback to the intermediate files if the final one is not found
        fallback_image = output_dir / "colored_floorplan_with_furniture.png"
        if fallback_image.exists():
            final_image = fallback_image
        else:
            raise RuntimeError("Final output file not found after running the pipeline")
    
    # Copy the final image to the result location
    shutil.copy2(final_image, result_image)
    
    if verbose:
        print(f"[queue-worker] Pipeline completed. Final output: {final_image}")
    
    return result_image


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

    simple_cmd = [
        python_exec,
        str(SCRIPTS_DIR / "simple_to_json.py"),
        "--input",
        text,
        "--mask",
        mask_rel,
        "--output",
        new_text_rel,
    ]

    if args.verbose:
        print(f"[queue-worker] Running simple_to_json for {job_id}...")

    new_text_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    completed_simple = run_command(simple_cmd, cwd=MODEL_DIR)
    if args.verbose:
        print(completed_simple.stdout)
        if completed_simple.stderr:
            print(completed_simple.stderr, file=sys.stderr)
    if completed_simple.returncode != 0:
        raise RuntimeError(
            f"simple_to_json failed for job {job_id}: {completed_simple.stderr or completed_simple.stdout}"
        )

    predict_cmd = [
        python_exec,
        str(SCRIPTS_DIR / "quick_predict.py"),
        "--mask",
        mask_rel,
        "--json",
        new_text_rel,
        "--output",
        result_rel,
    ]
    if args.invert_mask:
        predict_cmd.append("--invert-mask")

    if args.verbose:
        print(f"[queue-worker] Running quick_predict for {job_id}...")

    completed_predict = run_command(predict_cmd, cwd=MODEL_DIR)
    if args.verbose:
        print(completed_predict.stdout)
        if completed_predict.stderr:
            print(completed_predict.stderr, file=sys.stderr)
    if completed_predict.returncode != 0:
        raise RuntimeError(
            f"quick_predict failed for job {job_id}: {completed_predict.stderr or completed_predict.stdout}"
        )

    processed_image_path = result_path
    try:
        processed_image_path = run_furniture_pipeline(
            python_exec,
            job_id,
            result_path,
            new_text_path,
            args.verbose,
        )
    except Exception as furn_err:  # pylint: disable=broad-except
        raise RuntimeError(f"Furniture pipeline failed for job {job_id}: {furn_err}") from furn_err

    dest = PROCESSED_DIR / queue_file.name
    shutil.move(str(queue_file), dest)

    publish_targets: list[Path] = []

    try:
        STATIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATIC_IMG_DIR / name)
    except Exception as static_err:  # pylint: disable=broad-except
        print(f"[queue-worker] Warning: could not ensure static dir {STATIC_IMG_DIR}: {static_err}")

    try:
        STATICFILES_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATICFILES_IMG_DIR / name)
    except Exception as staticfiles_err:  # pylint: disable=broad-except
        print(f"[queue-worker] Warning: could not ensure staticfiles dir {STATICFILES_IMG_DIR}: {staticfiles_err}")

    for target in publish_targets:
        try:
            shutil.copyfile(processed_image_path, target)
            if args.verbose:
                print(f"[queue-worker] Published result to {target.relative_to(PROJECT_ROOT)}")
        except Exception as publish_err:  # pylint: disable=broad-except
            print(f"[queue-worker] Warning: could not publish to {target}: {publish_err}")

    if args.verbose:
        print(f"[queue-worker] Job {job_id} processed. Result saved to {result_rel}.")


def mark_failed(queue_file: Path, err: Exception) -> None:
    dest = FAILED_DIR / queue_file.name
    shutil.move(str(queue_file), dest)
    log_path = dest.with_suffix(".log")
    log_path.write_text(str(err), encoding="utf-8")
    print(f"[queue-worker] Job {queue_file.name} failed: {err}")


def process_pending(args: argparse.Namespace) -> bool:
    queue_files = sorted(QUEUE_DIR.glob("queue-*.json"))
    processed_any = False
    for queue_file in queue_files:
        try:
            process_queue_file(queue_file, args)
            processed_any = True
        except Exception as exc:  # pylint: disable=broad-except
            mark_failed(queue_file, exc)
    return processed_any


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Process floorplan generation queue")
    parser.add_argument("--once", action="store_true", help="Process pending jobs once and exit")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Polling interval when watching")
    parser.add_argument("--mask", default=DEFAULT_MASK, help="Relative path to mask image (from model dir)")
    parser.add_argument("--python", help="Python executable to use when running scripts (default: current)")
    parser.add_argument("--invert-mask", action="store_true", default=True, help="Pass --invert-mask to quick_predict (default: on)")
    parser.add_argument("--no-invert-mask", dest="invert_mask", action="store_false", help="Disable --invert-mask")
    parser.add_argument("--verbose", action="store_true", help="Print command output")
    args = parser.parse_args(argv)

    ensure_directories()

    if args.once:
        processed = process_pending(args)
        if not processed and args.verbose:
            print("[queue-worker] No pending jobs.")
        return

    if args.verbose:
        print(f"[queue-worker] Watching {QUEUE_DIR} every {args.interval}s (mask={args.mask})")

    try:
        while True:
            processed = process_pending(args)
            if not processed:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("[queue-worker] Stopped by user")


if __name__ == "__main__":
    main()
