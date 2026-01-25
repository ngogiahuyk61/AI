import argparse
import os
import sys
from PIL import Image, ImageOps
import pickle
import inspect 

# ==============================================================================
# QUAN TRỌNG: ÉP PYTHON DÙNG THƯ VIỆN LOCAL THAY VÌ PIP
# ==============================================================================
# Lấy đường dẫn thư mục gốc của project
current_file_path = os.path.abspath(__file__) # .../model/scripts/quick_predict.py
model_dir = os.path.dirname(os.path.dirname(current_file_path)) # .../model
sys.path.insert(0, model_dir) # CHÈN VÀO VỊ TRÍ SỐ 0 ĐỂ ƯU TIÊN TUYỆT ĐỐI

try:
    # Thử import từ local folder
    from denoising_diffusion_pytorch import Unet, GaussianDiffusion, Trainer
    print(f"[Info] Đã load thư viện từ: {os.path.dirname(inspect.getfile(Trainer))}")
except ImportError as e:
    print("[Critical] Không tìm thấy thư viện 'denoising_diffusion_pytorch' trong thư mục model.")
    print("Hãy đảm bảo cấu trúc thư mục là: ai_processing/model/denoising_diffusion_pytorch")
    raise e

def debug_log(msg):
    print(f"[DEBUG] {msg}")

def predict_prepare():
    # Force CPU usage
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # model_dir đã lấy ở trên
    results_folder = os.path.join(model_dir, "predict_model")
    
    # Load file cấu hình cũ
    param_path = os.path.join(results_folder, "params.pkl")
    if not os.path.exists(param_path):
        raise FileNotFoundError(f"Missing config file: {param_path}")

    with open(param_path, "rb") as f:
        params = pickle.load(f)

    # 1. FIX UNET
    print("[QuickPredict] --- CHECK UNET ---")
    unet_params = params["unet_dict"]
    valid_unet = set(inspect.signature(Unet.__init__).parameters.keys())
    clean_unet = {k: v for k, v in unet_params.items() if k in valid_unet}
    
    # Logic riêng cho Graphormer (dựa trên code bạn gửi)
    if 'omit_graphormer' in unet_params and 'omit_graphormer' not in valid_unet:
        print("[WARNING] Unet local không có omit_graphormer, bỏ qua.")
        
    try:
        model = Unet(**clean_unet)
    except Exception as e:
        print(f"[CRITICAL] Lỗi Unet: {e}")
        raise e

    model = model.to('cpu')
    params["diffusion_dict"]["sampling_timesteps"] = 250
    
    # 2. FIX DIFFUSION
    print("[QuickPredict] --- CHECK DIFFUSION ---")
    diff_valid = set(inspect.signature(GaussianDiffusion.__init__).parameters.keys())
    clean_diff = {k: v for k, v in params["diffusion_dict"].items() if k in diff_valid}

    try:
        diffusion = GaussianDiffusion(model, **clean_diff)
    except Exception as e:
        print(f"[CRITICAL] Lỗi Diffusion: {e}")
        raise e

    # 3. FIX TRAINER (Dựa trên file trainer.py bạn gửi - Cần 3 folders)
    print("[QuickPredict] --- CHECK TRAINER ---")
    
    trainer_sig = inspect.signature(Trainer.__init__)
    trainer_params = trainer_sig.parameters.keys()
    
    # Lọc kwargs
    final_kwargs = {}
    for k, v in params["trainer_dict"].items():
        if k in trainer_params:
            final_kwargs[k] = v
            
    # Bổ sung/Ghi đè tham số bắt buộc
    if 'train_num_workers' in trainer_params:
        final_kwargs['train_num_workers'] = 0
    if 'results_folder' in trainer_params:
        final_kwargs['results_folder'] = results_folder
    if 'mode' in trainer_params:
        final_kwargs['mode'] = "predict"
    if 'inject_step' in trainer_params:
        final_kwargs['inject_step'] = 40

    try:
        # Code local của bạn yêu cầu 3 folder positional arguments
        # init(self, diffusion_model, folder_image, folder_mask, folder_text, ...)
        if 'folder_image' in trainer_params:
            debug_log("Khởi tạo Trainer Local (3 folders)...")
            trainer = Trainer(
                diffusion,
                "", "", "", # Dummy paths cho image, mask, text
                **final_kwargs 
            )
        else:
            # Fallback nếu lỡ vẫn load sai thư viện
            debug_log("Cảnh báo: Không thấy 3 folder, có thể đang load sai thư viện!")
            trainer = Trainer(diffusion, **final_kwargs)

        debug_log("Khởi tạo Trainer thành công!")
    except Exception as e:
        print(f"[CRITICAL] Lỗi Trainer: {e}")
        raise e

    trainer.ema.to('cpu')
    
    # Đây là dòng quan trọng nhất: Chỉ thư viện Local mới có hàm này
    if hasattr(trainer, 'predict_load'):
        trainer.predict_load(98)
    else:
        raise AttributeError("Trainer load được không có hàm 'predict_load'. BẠN CẦN UNINSTALL THƯ VIỆN PIP: 'pip uninstall denoising-diffusion-pytorch'")
        
    return trainer

def preprocess_mask(mask_path: str, invert: bool = False, debug_save_path: str | None = None) -> Image.Image:
    try:
        img = Image.open(mask_path)
    except Exception as e:
        raise ValueError(f"Cannot open mask: {mask_path} - {e}")

    gray = img.convert("L")
    binary = gray.point(lambda x: 0 if x > 128 else 255, "1")
    
    if invert:
        binary = ImageOps.invert(binary.convert("L")).point(lambda x: 255 if x > 0 else 0, "1")
    
    binary = binary.resize((64, 64), Image.Resampling.BOX)

    if debug_save_path:
        os.makedirs(os.path.dirname(debug_save_path) or ".", exist_ok=True)
        binary.convert("L").save(debug_save_path)

    return binary

def main():
    print("\n" + "="*50)
    print("QUICK PREDICT SCRIPT - FORCE LOCAL LIB")
    print("="*50)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", default="drawing.png")
    parser.add_argument("--repredict", action="store_true")
    parser.add_argument("--invert-mask", action="store_true")
    parser.add_argument("--resize", type=int, default=400)

    args = parser.parse_args()
    
    if not os.path.isfile(args.mask) or not os.path.isfile(args.json):
        print("[QuickPredict] Error: Input files not found.")
        return

    print("[QuickPredict] Step 1: Preprocessing mask...")
    mask_img = preprocess_mask(args.mask, invert=args.invert_mask, debug_save_path="_debug_mask_preprocessed.png")
    
    print("[QuickPredict] Step 2: Reading JSON...")
    with open(args.json, "r", encoding="utf-8") as f:
        json_text = f.read()

    print("[QuickPredict] Step 3: Preparing Model...")
    try:
        trainer = predict_prepare()
    except Exception as e:
        print(f"[QuickPredict] [FAIL] Load model thất bại. {e}")
        return 

    print("[QuickPredict] Step 4: Running diffusion sampling...")
    try:
        prediction = trainer.predict(mask_img, json_text, repredict=args.repredict)

        if prediction.mode != "RGB":
            prediction = prediction.convert("RGB")

        if args.resize > 0:
            prediction = prediction.resize((args.resize, args.resize), Image.Resampling.BICUBIC)

        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        prediction.save(args.output)
        print(f"[QuickPredict] SUCCESS! Saved to: {args.output}")
        
    except Exception as e:
        print(f"[QuickPredict] [ERROR] Lỗi sinh ảnh: {e}")
        raise e 

if __name__ == "__main__":
    main()