#!/usr/bin/env python3
"""
Enhanced generation pipeline for HouseDiffusion (model-98.pt)
- Retry generation up to MAX_ATTEMPTS until image passes quality checks
- Post-processing: seal mask, enforce room fill, clean wall speckles, mild sharpen
- Quality checks: edge sharpness (Laplacian var), per-room color variance, speckle count
- Only export final files when "quality passed" (or best-effort after attempts)
"""
import os
import sys
import time
sys.path.append('.')

from PIL import Image
import numpy as np
import cv2
import pickle

# -----------------------------
# TUNABLE PARAMETERS
# -----------------------------
MAX_ATTEMPTS = 5
SAMPLING_STEPS = 100
INJECT_STEP = 40
MODEL_CHECKPOINT = 98

# Quality thresholds (tweak as needed)
EDGE_SHARPNESS_THRESHOLD = 80.0      # Laplacian variance threshold (higher = sharper)
ROOM_COLOR_VARIANCE_THRESHOLD = 400.0  # average region color variance (lower = uniform)
SPECKLE_COUNT_THRESHOLD = 500        # max allowed yellow-speckle pixels on walls

# Postprocess params
MASK_KERNEL_SIZE = 5
SPECKLE_SIZE_THRESHOLD_PX = 30
UNSHARP_AMOUNT = 0.8

# Paths
MASK_PATH = "source/mask/1.png"
JSON_PATH = "source/new_text/1.json"
ORIG_RESULT_PATH = "source/result/14_result.png"
OUTPUT_DIR = "source/result"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------
# Utilities
# -----------------------------
def pil_to_bgr(img_pil: Image.Image):
    arr = np.array(img_pil.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def bgr_to_pil(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)

def ensure_uint8(img):
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    return img

# -----------------------------
# Mask sealing & morphological ops
# -----------------------------
def seal_mask(mask_bgr, kernel_size=MASK_KERNEL_SIZE):
    """
    Close small holes in binary mask (preserve colors by zeroing background where closed==0).
    """
    mask_gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)
    _, thr = cv2.threshold(mask_gray, 1, 255, cv2.THRESH_BINARY)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    closed = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=2)
    sealed = mask_bgr.copy()
    sealed[closed == 0] = (0, 0, 0)
    return ensure_uint8(sealed)

# -----------------------------
# Enforce fill: set each mask region to majority color from prediction (keeps texture consistent)
# -----------------------------
def enforce_room_fill_by_mask(pred_bgr, mask_bgr, method='majority'):
    h, w = mask_bgr.shape[:2]
    pred = pred_bgr.copy()
    resh = mask_bgr.reshape(-1, 3)
    colors, idx = np.unique(resh, axis=0, return_inverse=True)
    # iterate colors except background
    for i, col in enumerate(colors):
        if (col == np.array([0,0,0])).all():
            continue
        region_mask = (idx.reshape(h, w) == i)
        if region_mask.sum() == 0:
            continue
        region_pixels = pred[region_mask]
        if region_pixels.size == 0:
            continue
        if method == 'majority':
            vals, counts = np.unique(region_pixels.reshape(-1,3), axis=0, return_counts=True)
            majority_color = vals[counts.argmax()]
            fill_color = majority_color
        else:
            avg = region_pixels.mean(axis=0)
            fill_color = np.round(avg).astype(np.uint8)
        pred[region_mask] = fill_color
    return ensure_uint8(pred)

# -----------------------------
# Remove small speckles on near-white walls that look yellow
# -----------------------------
def clean_wall_speckles(pred_bgr, mask_bgr=None,
                        wall_color_rgb=(255,255,255),
                        speckle_color_rgb=(240,200,60),
                        color_tol=45, speckle_tol=80,
                        size_threshold=SPECKLE_SIZE_THRESHOLD_PX):
    img = pred_bgr.copy()
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.int16)
    wall_col = np.array(wall_color_rgb, dtype=np.int16)
    speck_col = np.array(speckle_color_rgb, dtype=np.int16)
    dist_to_wall = np.linalg.norm(img_rgb - wall_col, axis=2)
    wall_mask = dist_to_wall < color_tol
    if mask_bgr is not None:
        mask_gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)
        mask_bin = mask_gray > 0
        kernel = np.ones((3,3), np.uint8)
        mask_bin = cv2.dilate(mask_bin.astype(np.uint8), kernel, iterations=1).astype(bool)
        wall_mask = wall_mask & mask_bin
    dist_to_speck = np.linalg.norm(img_rgb - speck_col, axis=2)
    speckle_mask = dist_to_speck < speckle_tol
    target_mask = wall_mask & speckle_mask
    if target_mask.sum() == 0:
        return img, 0
    target_uint8 = (target_mask.astype(np.uint8) * 255)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(target_uint8, connectivity=8)
    cleaned = img.copy()
    removed = 0
    for label in range(1, num_labels):
        area = stats[label, cv2.CC_STAT_AREA]
        component_mask = (labels == label)
        if area <= size_threshold:
            removed += int(area)
            kernel = np.ones((5,5), np.uint8)
            neigh = cv2.dilate(component_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
            neighbor_mask = neigh & (~component_mask)
            if neighbor_mask.sum() == 0:
                continue
            median_color = np.median(img[neighbor_mask], axis=0).astype(np.uint8)
            cleaned[component_mask] = median_color
    cleaned = cv2.medianBlur(cleaned, 3)
    return ensure_uint8(cleaned), removed

# -----------------------------
# Unsharp mask
# -----------------------------
def unsharp_mask(img_bgr, kernel_size=(5,5), sigma=1.0, amount=UNSHARP_AMOUNT):
    blurred = cv2.GaussianBlur(img_bgr, kernel_size, sigma)
    sharpened = cv2.addWeighted(img_bgr, 1.0 + amount, blurred, -amount, 0)
    return ensure_uint8(sharpened)

# -----------------------------
# Quality metrics
# -----------------------------
def edge_sharpness_score(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    var = lap.var()
    return float(var)

def average_room_color_variance(pred_bgr, mask_bgr):
    h, w = mask_bgr.shape[:2]
    resh = mask_bgr.reshape(-1,3)
    colors, idx = np.unique(resh, axis=0, return_inverse=True)
    pred = pred_bgr.reshape(-1,3)
    variances = []
    for i, col in enumerate(colors):
        if (col == np.array([0,0,0])).all():
            continue
        region_idx = (idx == i)
        if region_idx.sum() == 0:
            continue
        region_pixels = pred[region_idx]
        if region_pixels.shape[0] < 10:
            continue
        # variance across channels sum
        var = np.sum(np.var(region_pixels.astype(np.float32), axis=0))
        variances.append(var)
    if len(variances) == 0:
        return float('inf')
    return float(np.mean(variances))

def count_speckles(pred_bgr, mask_bgr):
    _, removed = clean_wall_speckles(pred_bgr, mask_bgr=mask_bgr)
    return removed

# -----------------------------
# Main enhanced test function
# -----------------------------
def test_14_corrected_with_quality_gate():
    print("🔄 Start enhanced generation with quality gate...")

    if not os.path.exists(MASK_PATH):
        print(f"❌ Mask file not found: {MASK_PATH}")
        return
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON file not found: {JSON_PATH}")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        json_data = f.read()

    # Preprocess mask (using existing helper from your codebase if available)
    from scripts.quick_predict import preprocess_mask
    print("🎭 Preprocessing mask (invert=True) ...")
    mask_img_pil = preprocess_mask(MASK_PATH, invert=True, debug_save_path="14_mask_debug.png")
    mask_bgr = pil_to_bgr(mask_img_pil)
    mask_bgr = seal_mask(mask_bgr, kernel_size=MASK_KERNEL_SIZE)

    # Load model & trainer (monkey patch predict_prepare logic like your original)
    import scripts.quick_predict as qp
    original_predict_prepare = qp.predict_prepare

    def corrected_predict_prepare():
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_folder = os.path.join(script_dir, "predict_model")
        train_num_workers = 0
        with open(os.path.join(results_folder, "params.pkl"), "rb") as f:
            params = pickle.load(f)

        # Filter out unsupported parameters from unet_dict
        unsupported_unet_params = [
            'cond_dim', 'cond_images_channels', 'num_resnet_blocks', 
            'layer_attns', 'omit_graphormer', 'graphormer_layers'
        ]
        unet_dict = params["unet_dict"].copy()
        for param in unsupported_unet_params:
            if param in unet_dict:
                print(f"[System] Đang xóa tham số thừa '{param}' khỏi cấu hình unet để tránh lỗi.")
                del unet_dict[param]
        
        model = qp.Unet(**unet_dict)
        model = model.to('cpu')

        # Filter out unsupported parameters from diffusion_dict
        unsupported_params = [
            'cond_dim', 'cond_images_channels', 'num_resnet_blocks', 
            'layer_attns', 'omit_graphormer', 'graphormer_layers', 'cond_drop_prob'
        ]
        diffusion_dict = params["diffusion_dict"].copy()
        for param in unsupported_params:
            if param in diffusion_dict:
                print(f"[System] Đang xóa tham số thừa '{param}' khỏi cấu hình để tránh lỗi.")
                del diffusion_dict[param]
        
        diffusion_dict["sampling_timesteps"] = SAMPLING_STEPS
        diffusion = qp.GaussianDiffusion(model, **diffusion_dict)

        trainer = qp.Trainer(
            diffusion,
            "",
            "",
            "",
            **params["trainer_dict"],
            results_folder=results_folder,
            train_num_workers=train_num_workers,
            mode="predict",
            inject_step=INJECT_STEP
        )

        trainer.ema.to('cpu')
        trainer.predict_load(MODEL_CHECKPOINT)
        return trainer

    qp.predict_prepare = corrected_predict_prepare
    trainer = corrected_predict_prepare()

    best_score = -1.0
    best_img = None
    best_metrics = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n🎨 Attempt {attempt}/{MAX_ATTEMPTS} - sampling_steps={SAMPLING_STEPS}")
        start = time.time()
        try:
            pred_pil = trainer.predict(mask_img_pil, json_data, repredict=True)
            if pred_pil.mode != "RGB":
                pred_pil = pred_pil.convert("RGB")
        except Exception as e:
            print(f"❌ Generation failed on attempt {attempt}: {e}")
            import traceback
            traceback.print_exc()
            continue

        pred_bgr = pil_to_bgr(pred_pil)

        # Postprocess pipeline
        # 1) Enforce fill per mask region
        pred_bgr = enforce_room_fill_by_mask(pred_bgr, mask_bgr, method='majority')

        # 2) Clean speckles and count removed
        pred_bgr, removed_speckles = clean_wall_speckles(pred_bgr, mask_bgr=mask_bgr)

        # 3) Mild unsharp to enhance edges
        pred_bgr = unsharp_mask(pred_bgr)

        # Evaluate metrics
        sharpness = edge_sharpness_score(pred_bgr)
        room_variance = average_room_color_variance(pred_bgr, mask_bgr)
        speckle_count = removed_speckles

        # Compose a simple quality score (higher is better)
        # We reward sharpness, penalize room_variance and speckle count
        score = (sharpness / (EDGE_SHARPNESS_THRESHOLD + 1e-9)) \
                - (room_variance / (ROOM_COLOR_VARIANCE_THRESHOLD + 1e-9)) \
                - (speckle_count / (SPECKLE_COUNT_THRESHOLD + 1e-9))

        print(f"   metrics -> sharpness: {sharpness:.1f}, room_var: {room_variance:.1f}, speckles_removed: {speckle_count}, score: {score:.3f}")

        # Keep best
        if score > best_score:
            best_score = score
            best_img = pred_bgr.copy()
            best_metrics = (sharpness, room_variance, speckle_count)

        # Decide pass/fail based on thresholds
        sharp_ok = sharpness >= EDGE_SHARPNESS_THRESHOLD
        room_ok = room_variance <= ROOM_COLOR_VARIANCE_THRESHOLD
        speckle_ok = speckle_count <= SPECKLE_COUNT_THRESHOLD

        if sharp_ok and room_ok and speckle_ok:
            print("✅ Quality gates passed — saving outputs.")
            final_img_pil = bgr_to_pil(pred_bgr)
            save_outputs(final_img_pil, attempt, best=False)
            qp.predict_prepare = original_predict_prepare
            return
        else:
            print("⚠️ Quality gates NOT passed — will retry (if attempts remain).")
            # Save debug failed attempt for inspection
            debug_name = os.path.join(OUTPUT_DIR, f"14_attempt_{attempt}_debug.png")
            bgr_to_pil(pred_bgr).save(debug_name)
            print(f"   Saved debug image: {debug_name}")
        elapsed = time.time() - start
        print(f"   Attempt time: {elapsed:.1f}s")

    # After attempts exhausted — save best effort
    print("\nℹ️ Max attempts reached. Saving best-effort result.")
    if best_img is not None:
        final_img_pil = bgr_to_pil(best_img)
        save_outputs(final_img_pil, attempt='best_effort', best=True, metrics=best_metrics)
    else:
        print("❌ No successful generation to save.")
    qp.predict_prepare = original_predict_prepare

# -----------------------------
# Save outputs helper
# -----------------------------
def save_outputs(img_pil, attempt, best=False, metrics=None):
    timestamp = int(time.time())
    base_name = f"14_corrected"
    if best:
        base_name += f"_best_{attempt}"
    else:
        base_name += f"_attempt_{attempt}"
    out_path = os.path.join(OUTPUT_DIR, f"{base_name}.png")
    img_pil.save(out_path)
    print(f"✅ Saved: {out_path}")
    # also save large upsample
    large = img_pil.resize((1024, 1024), Image.Resampling.BICUBIC)
    large_path = os.path.join(OUTPUT_DIR, f"{base_name}_large.png")
    large.save(large_path)
    print(f"✅ Saved large: {large_path}")
    # if original exists, create comparison
    if os.path.exists(ORIG_RESULT_PATH):
        try:
            orig = Image.open(ORIG_RESULT_PATH).convert("RGB")
            comp = Image.new("RGB", (1024, 512))
            comp.paste(orig.resize((512,512)), (0,0))
            comp.paste(large.resize((512,512)), (512,0))
            comp_path = os.path.join(OUTPUT_DIR, f"{base_name}_comparison.png")
            comp.save(comp_path)
            print(f"✅ Saved comparison: {comp_path}")
        except Exception:
            pass
    # metrics log
    if metrics is not None:
        (sharpness, room_var, speckle_count) = metrics
        meta_path = os.path.join(OUTPUT_DIR, f"{base_name}_metrics.txt")
        with open(meta_path, "w") as mf:
            mf.write(f"sharpness: {sharpness}\nroom_var: {room_var}\nspeckle_count: {speckle_count}\n")
        print(f"✅ Saved metrics: {meta_path}")

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    test_14_corrected_with_quality_gate()
