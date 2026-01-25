import os
import subprocess
import argparse
import time
from glob import glob
import json
from PIL import Image, ImageOps
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompt2json.layoutOptimizer_combined import process_simple_input
from denoising_diffusion_pytorch import Unet, GaussianDiffusion, Trainer
import pickle
from layout_validator import LayoutValidator

def predict_prepare():
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    # Use absolute path to avoid relative path issues
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_folder = os.path.join(script_dir, "../predict_model")
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
    
    model = Unet(**unet_dict)
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
    
    diffusion_dict["sampling_timesteps"] = 50
    diffusion = GaussianDiffusion(model, **diffusion_dict)

    trainer = Trainer(
        diffusion,
        "",
        "",
        "",
        **params["trainer_dict"],
        results_folder=results_folder,
        train_num_workers=train_num_workers,
        mode="predict",
        inject_step=40
    )

    # Force device and EMA to CPU
    trainer.ema.to('cpu')
    return trainer

def preprocess_mask(mask_path: str, invert: bool = False, debug_save_path: str = None) -> Image.Image:
    """Load and preprocess mask image - EXACT COPY from quick_predict.py"""
    img = Image.open(mask_path)
    gray = img.convert("L")
    binary = gray.point(lambda x: 0 if x > 128 else 255, "1")
    if invert:
        binary = ImageOps.invert(binary.convert("L")).point(lambda x: 255 if x > 0 else 0, "1")
    binary = binary.resize((64, 64), Image.Resampling.BOX)
    
    # Print simple mask stats - EXACT COPY from quick_predict.py
    mask_l = binary.convert("L")
    pixels = mask_l.getdata()
    white = sum(1 for p in pixels if p > 128)
    total = len(pixels)
    white_ratio = white / total if total else 0
    print(f"  📊 Mask {os.path.basename(mask_path)}: size={binary.size}, mode={binary.mode}, white_ratio={white_ratio:.3f}")
    
    return binary

def create_json_direct(input_text: str, mask_path: str, output_path: str):
    """Tạo JSON trực tiếp thay vì dùng subprocess"""
    try:
        result = process_simple_input(input_text, mask_path)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Lỗi tạo JSON: {e}")
        return False

def _setup_directories():
    """Thiết lập các thư mục cần thiết"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs = {
        'mask_dir': os.path.join(base_dir, 'source/mask'),
        'json_output_dir': os.path.join(base_dir, 'source/new_text'),
        'image_output_dir': os.path.join(base_dir, 'source/result'),
        'validate_output_dir': os.path.join(base_dir, 'source/validate_result')
    }
    
    # Tạo thư mục output
    for key in ['json_output_dir', 'image_output_dir', 'validate_output_dir']:
        os.makedirs(dirs[key], exist_ok=True)
    
    return dirs

def _find_mask_files(mask_dir):
    """Tìm tất cả file mask"""
    mask_files = (glob(os.path.join(mask_dir, '*.png')) + 
                  glob(os.path.join(mask_dir, '*.jpg')) + 
                  glob(os.path.join(mask_dir, '*.jpeg')))
    
    if not mask_files:
        print(f"❌ Không tìm thấy file ảnh nào trong thư mục: {mask_dir}")
        return None
    
    return mask_files

def _setup_model_strategy(args):
    """Thiết lập strategy cho model loading"""
    trainer = None
    model_load_time = 0
    
    if args.subprocess_predict:
        print("\n[SUBPROCESS MODE] Se dung subprocess cho prediction...")
    elif not args.reload_model_each:
        print("\n[SUPER OPTIMIZED] Dang load model AI mot lan...")
        model_load_start = time.time()
        trainer = predict_prepare()
        model_load_time = time.time() - model_load_start
        print(f"[SUCCESS] Model da load xong trong {model_load_time:.2f}s!")
    else:
        print("\n[QUALITY MODE] Se reload model cho moi anh...")
    
    return trainer, model_load_time

def _create_json_file(args, mask_path, json_output_path):
    """Tạo file JSON với strategy được chọn"""
    if args.direct_json:
        print(f"  [DIRECT] Tao JSON truc tiep...")
        return create_json_direct(args.input, mask_path, json_output_path)
    else:
        print(f"  [SUBPROCESS] Tao JSON qua subprocess...")
        # Use absolute path for subprocess to avoid path issues
        script_dir = os.path.dirname(os.path.abspath(__file__))
        simple_to_json_path = os.path.join(script_dir, 'simple_to_json.py')
        cmd_json = [
            sys.executable, simple_to_json_path,
            '--input', args.input,
            '--mask', mask_path,
            '--output', json_output_path
        ]
        result = subprocess.run(cmd_json, check=True, capture_output=True, text=True)
        return True

def _predict_with_subprocess(mask_path, json_output_path, image_output_path):
    """Prediction sử dụng subprocess"""
    print(f"  [SUBPROCESS MODE] Using subprocess for prediction...")
    # Use absolute path for subprocess to avoid path issues
    script_dir = os.path.dirname(os.path.abspath(__file__))
    quick_predict_path = os.path.join(script_dir, 'quick_predict.py')
    cmd_predict = [
        sys.executable, quick_predict_path,
        '--mask', mask_path,
        '--json', json_output_path,
        '--output', image_output_path,
        '--invert-mask'  # Added back - invert=True is correct
    ]
    subprocess.run(cmd_predict, check=True, capture_output=True, text=True)
    print(f"  [SUCCESS] Subprocess prediction completed")

def _predict_with_model(args, trainer, mask_path, json_output_path, image_output_path, base_filename):
    """Prediction sử dụng model đã load"""
    print("[QuickPredict] Preprocessing mask ...")
    mask_img = preprocess_mask(mask_path, invert=True, debug_save_path="_debug_mask_preprocessed.png")
    
    # Read JSON
    with open(json_output_path, "r", encoding="utf-8") as f:
        json_text = f.read()
    
    # Predict
    if args.reload_model_each:
        print(f"  [QUALITY MODE] Loading fresh model...")
        fresh_trainer = predict_prepare()
        prediction = fresh_trainer.predict(mask_img, json_text, repredict=False)
    else:
        prediction = trainer.predict(mask_img, json_text, repredict=True)
    
    # Save result
    if prediction.mode != "RGB":
        prediction = prediction.convert("RGB")
    
    resize_size = 400
    if resize_size and resize_size > 0:
        prediction = prediction.resize((resize_size, resize_size), Image.Resampling.BICUBIC)
    
    os.makedirs(os.path.dirname(image_output_path) or ".", exist_ok=True)
    prediction.save(image_output_path)

def _validate_result(validator, image_output_path, json_output_path, image_output_dir, validate_output_dir):
    """Validate kết quả nếu cần"""
    if not validator:
        return False
    
    print(f"  [VALIDATION] Validating layout...")
    try:
        is_valid, validation_message, detected_results = validator.validate_layout(
            image_output_path, json_output_path, image_output_dir, validate_output_dir
        )
        if is_valid:
            print(f"  [SUCCESS] Validation PASSED: {validation_message}")
            return True
        else:
            print(f"  [ERROR] Validation FAILED: {validation_message}")
            return False
    except Exception as e:
        print(f"  [ERROR] Validation error: {str(e)}")
        return False

def _process_single_file(args, trainer, validator, dirs, mask_path, i, total_files):
    """Xử lý một file mask"""
    file_start_time = time.time()
    mask_filename = os.path.basename(mask_path)
    base_filename = os.path.splitext(mask_filename)[0]
    
    progress = f"[{i+1:2d}/{total_files:2d}]"
    print(f"\n{progress} [FILE] {mask_filename}")

    json_output_path = os.path.join(dirs['json_output_dir'], f"{base_filename}.json")
    image_output_path = os.path.join(dirs['image_output_dir'], f"{base_filename}_result.png")

    try:
        # Bước 1: Tạo JSON
        json_success = _create_json_file(args, mask_path, json_output_path)
        if not json_success:
            return False, False

        # Bước 2: Predict
        print(f"  [GENERATING] Generating image...")
        
        if args.subprocess_predict:
            _predict_with_subprocess(mask_path, json_output_path, image_output_path)
        else:
            _predict_with_model(args, trainer, mask_path, json_output_path, image_output_path, base_filename)
        
        file_time = time.time() - file_start_time
        print(f"  [SUCCESS] Hoan thanh trong {file_time:.2f}s")
        
        # Bước 3: Validation
        is_validated = _validate_result(validator, image_output_path, json_output_path, 
                                      dirs['image_output_dir'], dirs['validate_output_dir'])
        
        return True, is_validated
        
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Loi subprocess: {e.stderr}")
        return False, False
    except Exception as e:
        print(f"  [ERROR] Loi: {str(e)}")
        return False, False

def _print_final_stats(success_count, error_count, validated_count, total_files, total_time, model_load_time, validate_enabled):
    """In thống kê cuối cùng"""
    avg_time_per_file = (total_time - model_load_time) / total_files if total_files > 0 else 0
    
    print(f"\n[SUCCESS] === KET QUA CUOI CUNG ===")
    print(f"[SUCCESS] Thanh cong: {success_count}/{total_files} file")
    print(f"[ERROR] Loi: {error_count}/{total_files} file")
    if validate_enabled:
        print(f"[VALIDATION] Validation passed: {validated_count}/{success_count} file")
        validation_rate = (validated_count / success_count * 100) if success_count > 0 else 0
        print(f"[STATS] Validation rate: {validation_rate:.1f}%")
    print(f"[TIME] Tong thoi gian: {total_time:.2f}s")
    print(f"[STATS] Thoi gian trung binh/file: {avg_time_per_file:.2f}s")

def main(args):
    start_time = time.time()
    
    # Setup
    dirs = _setup_directories()
    mask_files = _find_mask_files(dirs['mask_dir'])
    if not mask_files:
        return
    
    validator = LayoutValidator() if args.validate else None
    if args.validate:
        print("Validation mode enabled")
    
    total_files = len(mask_files)
    print(f"[INFO] Tim thay {total_files} file mask. Bat dau qua trinh xu ly...")
    
    trainer, model_load_time = _setup_model_strategy(args)

    # Xử lý từng file
    success_count = 0
    error_count = 0
    validated_count = 0
    
    for i, mask_path in enumerate(mask_files):
        success, is_validated = _process_single_file(args, trainer, validator, dirs, mask_path, i, total_files)
        
        if success:
            success_count += 1
            if is_validated:
                validated_count += 1
        else:
            error_count += 1
    
    # Thống kê cuối
    total_time = time.time() - start_time
    _print_final_stats(success_count, error_count, validated_count, total_files, total_time, model_load_time, args.validate)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='TOI UU: Batch test voi model load 1 lan duy nhat!'
    )
    parser.add_argument('--input', type=str, required=True, 
                        help='Chuỗi văn bản mô tả các phòng')
    parser.add_argument('--direct-json', action='store_true',
                        help='Tạo JSON trực tiếp thay vì qua subprocess (nhanh hơn)')
    parser.add_argument('--reload-model-each', action='store_true',
                        help='Reload model cho mỗi ảnh (chậm hơn nhưng chất lượng tốt hơn)')
    parser.add_argument('--subprocess-predict', action='store_true',
                        help='Sử dụng subprocess cho prediction (chậm nhất nhưng chất lượng cao nhất)')
    parser.add_argument('--validate', action='store_true',
                        help='Validate generated layouts against JSON specifications')
    
    args = parser.parse_args()
    main(args)
