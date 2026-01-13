import os
import base64
import json
from datetime import datetime
from math import hypot
from pathlib import Path
import subprocess
import sys

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


# --- CẤU HÌNH ĐƯỜNG DẪN (PATH CONFIGURATION) ---
MODEL_DIR = Path(settings.BASE_DIR).parent / "ai_processing" / "model"
SOURCE_DIR = MODEL_DIR / "source"
TEXT_INPUT_DIR = SOURCE_DIR / "text_input"
QUEUE_DIR = SOURCE_DIR / "queue"
NEW_TEXT_DIR = SOURCE_DIR / "new_text"
RESULT_DIR = SOURCE_DIR / "result"
QUEUE_PROCESSED_DIR = QUEUE_DIR / "processed"
QUEUE_FAILED_DIR = QUEUE_DIR / "failed"
STATIC_DIR = Path(settings.BASE_DIR) / "floorplan_app" / "static" / "floorplan_app" / "img"
STATICFILES_DIR = Path(settings.BASE_DIR) / "staticfiles" / "floorplan_app" / "img"
HERO_IMAGE_REL = "floorplan_app/img/proposal1.png"
GALLERY_IMAGE_REL = "floorplan_app/img/floorplan1.png"
COLLECT_MASK_INPUT_DIR = Path(settings.BASE_DIR).parent / "ai_processing" / "module_collect_mask" / "input"
SITE_DATA_PATH = COLLECT_MASK_INPUT_DIR / "site_data.json"
SKETCH_DIR = SOURCE_DIR / "sketch"

LOGICAL_SIZE_MM = 2000
DRAW_SIZE_PX = 600
CANVAS_SIZE_PX = 720
CANVAS_MARGIN_PX = (CANVAS_SIZE_PX - DRAW_SIZE_PX) / 2
SCALE_PX_PER_MM = DRAW_SIZE_PX / LOGICAL_SIZE_MM

# Tạo thư mục nếu chưa tồn tại
for directory in (TEXT_INPUT_DIR, QUEUE_DIR, NEW_TEXT_DIR, RESULT_DIR, QUEUE_PROCESSED_DIR, QUEUE_FAILED_DIR, COLLECT_MASK_INPUT_DIR, SKETCH_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# --- HELPER FUNCTIONS ---
def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _load_total_area_from_text_file(relative_path: str | None) -> float | None:
    if not relative_path:
        return None
    text_path = MODEL_DIR / Path(relative_path)
    if not text_path.exists():
        return None
    try:
        payload = json.loads(text_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _coerce_float(payload.get("total_area_m2"))

def _latest_text_request_file() -> Path | None:
    candidates = sorted(
        TEXT_INPUT_DIR.glob("floorplan-request-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None

def _load_latest_request_summary() -> dict:
    latest_file = _latest_text_request_file()
    if not latest_file:
        return {"text": None, "total_area_m2": None}
    try:
        payload = json.loads(latest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"text": None, "total_area_m2": None}
    return {
        "text": payload.get("text"),
        "total_area_m2": _coerce_float(payload.get("total_area_m2")),
    }

def _px_to_mm(x_px: int, y_px: int) -> tuple[float, float]:
    clamped_x = max(CANVAS_MARGIN_PX, min(CANVAS_MARGIN_PX + DRAW_SIZE_PX, float(x_px)))
    clamped_y = max(CANVAS_MARGIN_PX, min(CANVAS_MARGIN_PX + DRAW_SIZE_PX, float(y_px)))
    logical_x = (clamped_x - CANVAS_MARGIN_PX) / SCALE_PX_PER_MM
    logical_y = (CANVAS_MARGIN_PX + DRAW_SIZE_PX - clamped_y) / SCALE_PX_PER_MM
    return logical_x, logical_y

def _ensure_closed_points(points: list[dict[str, float]]) -> list[dict[str, float]]:
    if not points:
        return points
    first = points[0]
    last = points[-1]
    if (
        first.get("x") == last.get("x")
        and first.get("y") == last.get("y")
        and first.get("x_mm") == last.get("x_mm")
        and first.get("y_mm") == last.get("y_mm")
    ):
        return points
    copy_first = {
        "x": first.get("x"),
        "y": first.get("y"),
        "x_mm": first.get("x_mm"),
        "y_mm": first.get("y_mm"),
    }
    return points + [copy_first]

def _compute_edge_lengths_mm(points: list[dict[str, float]]) -> list[float]:
    lengths: list[float] = []
    if len(points) < 2:
        return lengths
    for idx in range(len(points) - 1):
        x1 = float(points[idx]["x_mm"])
        y1 = float(points[idx]["y_mm"])
        x2 = float(points[idx + 1]["x_mm"])
        y2 = float(points[idx + 1]["y_mm"])
        lengths.append(hypot(x2 - x1, y2 - y1))
    return lengths

def _compute_polygon_area_mm(points: list[dict[str, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area_acc = 0.0
    for idx in range(len(points) - 1):
        x1 = float(points[idx]["x_mm"])
        y1 = float(points[idx]["y_mm"])
        x2 = float(points[idx + 1]["x_mm"])
        y2 = float(points[idx + 1]["y_mm"])
        area_acc += x1 * y2 - x2 * y1
    return abs(area_acc) / 2.0

def _load_latest_land_info() -> dict | None:
    candidates = sorted(
        SKETCH_DIR.glob("sketch-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for json_path in candidates:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        raw_points = payload.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 3:
            continue

        cleaned_points: list[dict[str, float]] = []
        invalid = False
        for point in raw_points:
            if not isinstance(point, dict):
                invalid = True
                break
            try:
                x_px = int(point["x"])
                y_px = int(point["y"])
            except (KeyError, TypeError, ValueError):
                invalid = True
                break

            x_mm_val = point.get("x_mm")
            y_mm_val = point.get("y_mm")
            try:
                if x_mm_val is None or y_mm_val is None:
                    x_mm_float, y_mm_float = _px_to_mm(x_px, y_px)
                else:
                    x_mm_float = float(x_mm_val)
                    y_mm_float = float(y_mm_val)
            except (TypeError, ValueError):
                x_mm_float, y_mm_float = _px_to_mm(x_px, y_px)

            cleaned_points.append(
                {
                    "x": x_px,
                    "y": y_px,
                    "x_mm": x_mm_float,
                    "y_mm": y_mm_float,
                }
            )

        if invalid:
            continue

        closed = _ensure_closed_points(cleaned_points)
        if len(closed) < 4:
            continue

        try:
            lengths_mm = _compute_edge_lengths_mm(closed)
            area_mm2 = _compute_polygon_area_mm(closed)
        except (KeyError, TypeError, ValueError):
            continue

        if not lengths_mm:
            continue

        preview_path = json_path.with_name(f"{json_path.stem}_64.png")
        preview_data_url = None
        if preview_path.exists():
            try:
                preview_bytes = preview_path.read_bytes()
                encoded = base64.b64encode(preview_bytes).decode("ascii")
                preview_data_url = f"data:image/png;base64,{encoded}"
            except OSError:
                preview_data_url = None

        return {
            "success": True,
            "preview_data_url": preview_data_url,
            "points_px": [{"x": pt["x"], "y": pt["y"]} for pt in closed],
            "points_mm": [{"x_mm": pt["x_mm"], "y_mm": pt["y_mm"]} for pt in closed],
            "lengths_mm": lengths_mm,
            "area_mm2": area_mm2,
        }

    return None


# --- VIEWS ---

def homepage(request):
    return render(request, "floorplan_app/homepage.html")

def index(request):
    summary = _load_latest_request_summary()
    context = {
        "latest_description": summary.get("text"),
        "latest_area_plan": summary.get("total_area_m2"),
    }
    return render(request, "floorplan_app/index.html", context)

def survey_view(request):
    return render(request, 'floorplan_app/dashboard_parts_html/survey.html')


@csrf_exempt
def save_text_request(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return JsonResponse({"error": "`text` must be a non-empty string"}, status=400)
    
    total_area_m2 = payload.get("total_area_m2", 100.0)
    try:
        total_area_m2 = float(total_area_m2)
        if total_area_m2 <= 0:
            total_area_m2 = 100.0
    except (ValueError, TypeError):
        total_area_m2 = 100.0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"floorplan-request-{timestamp}.json"
    filepath = TEXT_INPUT_DIR / filename
    filepath.write_text(json.dumps({"text": text, "total_area_m2": total_area_m2}, ensure_ascii=False, indent=2), encoding="utf-8")

    job_id = timestamp
    new_text_rel = f"source/new_text/{job_id}.json"
    result_rel = f"source/result/{job_id}.png"

    enqueue_payload = {
        "job_id": job_id,
        "text_file": str(filepath.relative_to(MODEL_DIR)),
        "description": text.strip(),
        "total_area_m2": total_area_m2,
        "queued_at": timestamp,
        "new_text_file": new_text_rel,
        "result_image": result_rel,
    }
    queue_filename = f"queue-{job_id}.json"
    queue_path = QUEUE_DIR / queue_filename
    queue_path.write_text(json.dumps(enqueue_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return JsonResponse({
        "success": True,
        "filename": filename,
        "queue_file": queue_filename,
        "job_id": job_id,
        "new_text_json": new_text_rel,
        "result_image": result_rel,
        "hero_image": f"/{HERO_IMAGE_REL}",
        "gallery_image": f"/{GALLERY_IMAGE_REL}",
    })


@csrf_exempt
def save_land_settings(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    try:
        length = int(payload.get("length"))
        width = int(payload.get("width"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "`length` and `width` must be integers"}, status=400)

    if length <= 0 or width <= 0:
        return JsonResponse({"error": "`length` and `width` must be positive"}, status=400)

    grid = payload.get("grid")
    if not isinstance(grid, list) or not all(isinstance(row, list) for row in grid):
        return JsonResponse({"error": "`grid` must be a 2D array"}, status=400)

    if any(len(row) != width for row in grid) or len(grid) != length:
        return JsonResponse({"error": "`grid` dimensions must match `length` and `width`"}, status=400)

    try:
        SITE_DATA_PATH.write_text(
            json.dumps({"length": length, "width": width, "grid": grid}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse({"success": True, "path": str(SITE_DATA_PATH)})


@csrf_exempt
def upload_sketch(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    mask_file = request.FILES.get("mask")
    preview_file = request.FILES.get("mask_preview")
    points_raw = request.POST.get("points")

    if not mask_file or not preview_file or not points_raw:
        return JsonResponse({"error": "`mask`, `mask_preview`, and `points` fields are required"}, status=400)

    try:
        points_payload = json.loads(points_raw)
    except json.JSONDecodeError:
        return JsonResponse({"error": "`points` must be valid JSON"}, status=400)

    points_list = points_payload.get("points")
    if not isinstance(points_list, list) or len(points_list) < 3:
        return JsonResponse({"error": "`points` must contain at least three points"}, status=400)

    normalised_points: list[dict[str, float]] = []
    for point in points_list:
        if not isinstance(point, dict):
            return JsonResponse({"error": "Each point must be an object with x and y"}, status=400)
        try:
            x_val = int(point["x"])
            y_val = int(point["y"])
        except (KeyError, TypeError, ValueError):
            return JsonResponse({"error": "Points must include integer x and y values"}, status=400)
        x_mm_val = point.get("x_mm")
        y_mm_val = point.get("y_mm")
        try:
            if x_mm_val is None or y_mm_val is None:
                x_mm_float, y_mm_float = _px_to_mm(x_val, y_val)
            else:
                x_mm_float = float(x_mm_val)
                y_mm_float = float(y_mm_val)
        except (TypeError, ValueError):
            x_mm_float, y_mm_float = _px_to_mm(x_val, y_val)

        normalised_points.append(
            {
                "x": x_val,
                "y": y_val,
                "x_mm": x_mm_float,
                "y_mm": y_mm_float,
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"sketch-{timestamp}"
    mask_path = SKETCH_DIR / f"{base_name}.png"
    preview_path = SKETCH_DIR / f"{base_name}_64.png"
    points_path = SKETCH_DIR / f"{base_name}.json"

    def _save_uploaded(file_obj, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)

    try:
        _save_uploaded(mask_file, mask_path)
        _save_uploaded(preview_file, preview_path)
        points_content = json.dumps({"points": normalised_points}, ensure_ascii=False, indent=2)
        points_path.write_text(points_content, encoding="utf-8")
    except OSError as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse(
        {
            "success": True,
            "mask_path": str(mask_path),
            "preview_path": str(preview_path),
            "points_path": str(points_path),
        }
    )


def latest_land_info(request):
    if request.method != "GET":
        return JsonResponse({"error": "Only GET allowed"}, status=405)

    payload = _load_latest_land_info()
    if not payload:
        return JsonResponse({"success": False, "message": "No saved land mask found"})

    return JsonResponse(payload)


def job_status(request, job_id: str):
    job_id = (job_id or "").strip()
    if not job_id:
        return JsonResponse({"error": "Invalid job_id"}, status=400)

    queue_filename = f"queue-{job_id}.json"
    queue_path = QUEUE_DIR / queue_filename
    processed_path = QUEUE_PROCESSED_DIR / queue_filename
    failed_path = QUEUE_FAILED_DIR / queue_filename

    if processed_path.exists():
        payload = json.loads(processed_path.read_text(encoding="utf-8"))

        hero_image_path = STATIC_DIR / Path(HERO_IMAGE_REL).name
        gallery_image_path = STATIC_DIR / Path(GALLERY_IMAGE_REL).name
        
        hero_version = None
        gallery_version = None
        
        if hero_image_path.exists():
            hero_version = int(hero_image_path.stat().st_mtime)
        
        if gallery_image_path.exists():
            gallery_version = int(gallery_image_path.stat().st_mtime)
        
        version = max(hero_version or 0, gallery_version or 0)
        
        hero_url = f"{settings.STATIC_URL}{HERO_IMAGE_REL}"
        gallery_url = f"{settings.STATIC_URL}{GALLERY_IMAGE_REL}"

        total_area = _load_total_area_from_text_file(payload.get("text_file"))
        if total_area is None:
            total_area = _coerce_float(payload.get("total_area_m2"))

        return JsonResponse(
            {
                "status": "completed",
                "job_id": job_id,
                "queue_file": queue_filename,
                "new_text_json": payload.get("new_text_file"),
                "result_image": payload.get("result_image"),
                "hero_image_url": hero_url,
                "gallery_image_url": gallery_url,
                "version": version,
                "hero_version": hero_version,
                "gallery_version": gallery_version,
                "total_area_m2": total_area,
            }
        )

    if failed_path.exists():
        log_path = failed_path.with_suffix(".log")
        error_message = log_path.read_text(encoding="utf-8") if log_path.exists() else "Unknown error"
        payload = json.loads(failed_path.read_text(encoding="utf-8")) if failed_path.exists() else {}
        total_area = _load_total_area_from_text_file(payload.get("text_file")) if isinstance(payload, dict) else None
        if total_area is None and isinstance(payload, dict):
            total_area = _coerce_float(payload.get("total_area_m2"))
        return JsonResponse({"status": "failed", "job_id": job_id, "error": error_message, "total_area_m2": total_area})

    if queue_path.exists():
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        total_area = _load_total_area_from_text_file(payload.get("text_file"))
        if total_area is None:
            total_area = _coerce_float(payload.get("total_area_m2"))
        progress_percent = payload.get("progress_percent")
        progress_message = payload.get("progress_message")
        response = {"status": "pending", "job_id": job_id, "total_area_m2": total_area}
        if isinstance(progress_percent, (int, float)):
            response["progress_percent"] = float(progress_percent)
        if isinstance(progress_message, str):
            response["progress_message"] = progress_message
        return JsonResponse(response)

    return JsonResponse({"error": "Job not found", "job_id": job_id}, status=404)


# --- SAVE INTERACTIVE LAYOUT (API) ---
@csrf_exempt
def save_interactive_layout(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body)
        
        # 1. Lấy tham số
        image_data = data.get('image_base64')
        json_payload = data.get('json_data')

        # 2. Xử lý Lưu Ảnh
        if image_data:
            if "," in image_data:
                header, encoded = image_data.split(",", 1)
            else:
                encoded = image_data
            
            img_bytes = base64.b64decode(encoded)

            # --- CẤU HÌNH ĐƯỜNG DẪN ---
            base_img_dir = Path(settings.BASE_DIR) / "floorplan_app" / "static" / "floorplan_app" / "img"
            
            # File 1: proposal1.png (File gốc)
            path_proposal = base_img_dir / "proposal1.png"
            
            # File 2: floorplan1.png (File bạn yêu cầu thêm)
            path_floorplan = base_img_dir / "floorplan1.png"

            # Tạo thư mục nếu chưa có
            base_img_dir.mkdir(parents=True, exist_ok=True)
            
            # --- THỰC HIỆN LƯU FILE ---
            
            # Lưu proposal1.png
            with open(path_proposal, "wb") as fh:
                fh.write(img_bytes)
            print(f"✅ Image Saved to: {path_proposal}")

            # Lưu floorplan1.png (Copy logic lưu)
            with open(path_floorplan, "wb") as fh:
                fh.write(img_bytes)
            print(f"✅ Image Also Saved to: {path_floorplan}")

        # 3. Xử lý JSON (Vẫn giữ nguyên trạng thái comment như bạn yêu cầu)
        if json_payload:
            # print("⚠️ Notice: JSON Data received but writing to file is DISABLED temporarily.")
            # json_path = Path(settings.BASE_DIR) / "floorplan_app" / "static" / "floorplan_app" / "data" / "room_data.json"
            # with open(json_path, 'w', encoding='utf-8') as f:
            #     json.dump(json_payload, f, indent=4, ensure_ascii=False)
            pass 

        return JsonResponse({'success': True, 'message': 'Images (proposal1 & floorplan1) saved successfully.'})

    except Exception as e:
        print(f"❌ Error in save_interactive_layout: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)}, status=500)