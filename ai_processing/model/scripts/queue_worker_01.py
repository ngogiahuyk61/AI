"""Single job worker to process floorplan generation for mask 14.png.

Run this script in the CPU-only environment. It processes a single job
for mask 14.png, runs simple_to_json.py, quick_predict.py, test.py,
and furniture pipeline, then outputs results to web interface.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

MODEL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODEL_DIR / "scripts"
SOURCE_DIR = MODEL_DIR / "source"
PROJECT_ROOT = MODEL_DIR.parent.parent
STATIC_IMG_DIR = PROJECT_ROOT / "web_app" / "floorplan_app" / "static" / "floorplan_app" / "img"
STATICFILES_IMG_DIR = PROJECT_ROOT / "web_app" / "staticfiles" / "floorplan_app" / "img"
STATIC_TARGET_FILENAMES = ["floorplan1.png", "proposal1.png"]

FURN_DOORS_DIR = PROJECT_ROOT / "ai_processing" / "furnitures_doors"
FURN_INPUT_DIR = FURN_DOORS_DIR / "data" / "input"
FURN_OUTPUT_DIR = FURN_DOORS_DIR / "outputs"
FURN_OUTPUT_IMAGE = FURN_OUTPUT_DIR / "img" / "floorplan_with_furniture.png"
FURN_SCRIPTS = [
    "scripts/floorplan_room_detection.py",
    "scripts/floorplan_edges.py",
    "scripts/door_edge.py",
    "scripts/furniture_placement.py",
]

# Fixed paths for job 14
FIXED_MASK = "source/mask/14.png"
FIXED_TEXT_OUTPUT = "source/new_text/14.json"
FIXED_RESULT_OUTPUT = "source/result/14_result.png"
FIXED_JOB_ID = "14"


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
    """Create necessary directories."""
    for path in (SOURCE_DIR,):
        path.mkdir(parents=True, exist_ok=True)


def load_text(text_file: Path) -> str:
    """Load text from JSON file."""
    payload = json.loads(text_file.read_text(encoding="utf-8"))
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError(f"Invalid text payload in {text_file}")
    return text


def prepare_furniture_inputs(result_image: Path, layout_json: Path) -> None:
    """Prepare inputs for furniture pipeline."""
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
    """Run furniture pipeline if available."""
    if not FURN_DOORS_DIR.exists():
        if verbose:
            print("[single-worker] furnitures_doors module not found, skipping post-processing.")
        return result_image

    prepare_furniture_inputs(result_image, layout_json)

    final_image = result_image
    for script_rel in FURN_SCRIPTS:
        script_path = FURN_DOORS_DIR / script_rel
        if not script_path.exists():
            if verbose:
                print(f"[single-worker] Missing furnitures_doors script: {script_rel}, skipping.")
            continue

        cmd = [python_exec, str(script_path)]
        if verbose:
            print(f"[single-worker] Running {script_rel} for job {job_id}...")

        completed = run_command(cmd, cwd=FURN_DOORS_DIR)
        if verbose:
            print(completed.stdout)
            if completed.stderr:
                print(completed.stderr, file=sys.stderr)
        if completed.returncode != 0:
            if verbose:
                print(f"[single-worker] Warning: furnitures_doors step {script_rel} failed: {completed.stderr or completed.stdout}")

    if FURN_OUTPUT_IMAGE.exists():
        final_image = FURN_OUTPUT_IMAGE
        if verbose:
            print(f"[single-worker] Furniture pipeline produced {final_image.relative_to(PROJECT_ROOT)}")
        shutil.copyfile(final_image, result_image)

    return final_image


def create_layout_text() -> str:
    """Create layout text description for the floorplan."""
    return "1 living room, 1 master room, 2 second rooms, 2 bathrooms, 1 toilet"


def run_simple_to_json(python_exec: str, mask_path: str, output_path: str, verbose: bool) -> None:
    """Run simple_to_json.py to create layout JSON."""
    text = create_layout_text()

    simple_cmd = [
        python_exec,
        str(SCRIPTS_DIR / "simple_to_json.py"),
        "--input",
        text,
        "--mask",
        mask_path,
        "--output",
        output_path,
    ]

    if verbose:
        print(f"[single-worker] Running simple_to_json for job {FIXED_JOB_ID}...")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    completed_simple = run_command(simple_cmd, cwd=MODEL_DIR)
    if verbose:
        print(completed_simple.stdout)
        if completed_simple.stderr:
            print(completed_simple.stderr, file=sys.stderr)
    if completed_simple.returncode != 0:
        raise RuntimeError(
            f"simple_to_json failed for job {FIXED_JOB_ID}: {completed_simple.stderr or completed_simple.stdout}"
        )


def run_quick_predict(python_exec: str, mask_path: str, json_path: str, output_path: str, invert_mask: bool, verbose: bool) -> None:
    """Run quick_predict.py to generate floorplan."""
    predict_cmd = [
        python_exec,
        str(SCRIPTS_DIR / "quick_predict.py"),
        "--mask",
        mask_path,
        "--json",
        json_path,
        "--output",
        output_path,
    ]
    if invert_mask:
        predict_cmd.append("--invert-mask")

    if verbose:
        print(f"[single-worker] Running quick_predict for job {FIXED_JOB_ID}...")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    completed_predict = run_command(predict_cmd, cwd=MODEL_DIR)
    if verbose:
        print(completed_predict.stdout)
        if completed_predict.stderr:
            print(completed_predict.stderr, file=sys.stderr)
    if completed_predict.returncode != 0:
        raise RuntimeError(
            f"quick_predict failed for job {FIXED_JOB_ID}: {completed_predict.stderr or completed_predict.stdout}"
        )


def run_test_script(python_exec: str, verbose: bool) -> None:
    """Run test.py script."""
    test_cmd = [
        python_exec,
        str(MODEL_DIR / "test.py"),
    ]

    if verbose:
        print(f"[single-worker] Running test.py for job {FIXED_JOB_ID}...")

    completed_test = run_command(test_cmd, cwd=MODEL_DIR)
    if verbose:
        print(completed_test.stdout)
        if completed_test.stderr:
            print(completed_test.stderr, file=sys.stderr)
    if completed_test.returncode != 0:
        if verbose:
            print(f"[single-worker] Warning: test.py failed: {completed_test.stderr or completed_test.stdout}")


def publish_results(processed_image_path: Path, verbose: bool) -> None:
    """Copy results to static directories for web interface."""
    publish_targets: list[Path] = []

    try:
        STATIC_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATIC_IMG_DIR / name)
    except Exception as static_err:  # pylint: disable=broad-except
        print(f"[single-worker] Warning: could not ensure static dir {STATIC_IMG_DIR}: {static_err}")

    try:
        STATICFILES_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for name in STATIC_TARGET_FILENAMES:
            publish_targets.append(STATICFILES_IMG_DIR / name)
    except Exception as staticfiles_err:  # pylint: disable=broad-except
        print(f"[single-worker] Warning: could not ensure staticfiles dir {STATICFILES_IMG_DIR}: {staticfiles_err}")

    for target in publish_targets:
        try:
            shutil.copyfile(processed_image_path, target)
            if verbose:
                print(f"[single-worker] Published result to {target.relative_to(PROJECT_ROOT)}")
        except Exception as publish_err:  # pylint: disable=broad-except
            print(f"[single-worker] Warning: could not publish to {target}: {publish_err}")


def process_single_job(args: argparse.Namespace) -> None:
    """Process single job for mask 14.png."""
    job_id = FIXED_JOB_ID
    python_exec = args.python or sys.executable

    if args.verbose:
        print(f"[single-worker] Processing job {job_id} with mask {FIXED_MASK}")

    # Check if mask exists
    mask_path = MODEL_DIR / FIXED_MASK
    if not mask_path.exists():
        raise FileNotFoundError(f"Mask file not found: {mask_path}")

    # Step 1: Run simple_to_json.py
    run_simple_to_json(python_exec, FIXED_MASK, FIXED_TEXT_OUTPUT, args.verbose)

    # Step 2: Run quick_predict.py
    run_quick_predict(python_exec, FIXED_MASK, FIXED_TEXT_OUTPUT, FIXED_RESULT_OUTPUT, args.invert_mask, args.verbose)

    # Step 3: Run test.py
    run_test_script(python_exec, args.verbose)

    # Replace 14_result.png with improved version for furniture pipeline
    result_path = MODEL_DIR / FIXED_RESULT_OUTPUT
    improved_path = MODEL_DIR / "source" / "result" / "14_improved.png"

    if improved_path.exists():
        if args.verbose:
            print(f"[single-worker] Replacing {FIXED_RESULT_OUTPUT} with improved version...")

        # Delete old result
        if result_path.exists():
            result_path.unlink()

        # Rename improved to result
        shutil.move(str(improved_path), str(result_path))

        if args.verbose:
            print(f"[single-worker] Successfully replaced with improved floorplan")
    else:
        if args.verbose:
            print(f"[single-worker] Warning: {improved_path} not found, using original result")

    # Step 4: Run furniture pipeline
    text_path = MODEL_DIR / FIXED_TEXT_OUTPUT

    try:
        processed_image_path = run_furniture_pipeline(
            python_exec,
            job_id,
            result_path,
            text_path,
            args.verbose,
        )
    except Exception as furn_err:  # pylint: disable=broad-except
        if args.verbose:
            print(f"[single-worker] Furniture pipeline failed: {furn_err}")
        processed_image_path = result_path

    # Step 5: Publish results to web interface (always use improved version)
    publish_results(result_path, args.verbose)

    if args.verbose:
        print(f"[single-worker] Job {job_id} completed. Results published to web interface.")


def main(argv: Optional[list[str]] = None) -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Process single floorplan generation job for mask 14.png")
    parser.add_argument("--python", help="Python executable to use when running scripts (default: current)")
    parser.add_argument("--invert-mask", action="store_true", default=True, help="Pass --invert-mask to quick_predict (default: on)")
    parser.add_argument("--no-invert-mask", dest="invert_mask", action="store_false", help="Disable --invert-mask")
    parser.add_argument("--verbose", action="store_true", help="Print command output")
    args = parser.parse_args(argv)

    ensure_directories()

    try:
        process_single_job(args)
        print(f"✅ Single job {FIXED_JOB_ID} completed successfully!")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ Single job {FIXED_JOB_ID} failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()