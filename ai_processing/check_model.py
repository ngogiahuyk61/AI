import torch
import os
import sys

# Đường dẫn tới file model của bạn (dựa trên log bạn gửi)
MODEL_PATH = r"F:\ai-key-plan-develop_final_project\ai_processing\model\predict_model\model-98.pt"

def check_model_structure():
    print(f"--- Đang kiểm tra file: {MODEL_PATH} ---")
    
    if not os.path.exists(MODEL_PATH):
        print("LỖI: Không tìm thấy file model!")
        return

    try:
        # Load lên CPU
        checkpoint = torch.load(MODEL_PATH, map_location='cpu')
    except Exception as e:
        print(f"LỖI: Không thể đọc file .pt. File có thể bị hỏng. Chi tiết: {e}")
        return

    # 1. Kiểm tra Keys
    if isinstance(checkpoint, dict):
        keys = list(checkpoint.keys())
        print(f"\n[1] File là Dictionary. Các key chính: {keys}")
        
        # Tìm state_dict thực sự
        if 'ema' in checkpoint:
            state_dict = checkpoint['ema']
            print("-> Phát hiện key 'ema' (Model chất lượng cao).")
        elif 'model' in checkpoint:
            state_dict = checkpoint['model']
            print("-> Phát hiện key 'model'.")
        elif 'state_dict' in checkpoint:
            state_dict = checkpoint['state_dict']
            print("-> Phát hiện key 'state_dict'.")
        else:
            state_dict = checkpoint
            print("-> Không thấy key bao bọc, coi toàn bộ dict là state_dict.")
    else:
        print("\n[1] File là Object Model trực tiếp (không khuyến khích).")
        state_dict = checkpoint.state_dict()

    # 2. Soi kích thước các lớp quan trọng
    print("\n[2] Phân tích kích thước các lớp (Tensor Shapes):")
    
    # Kiểm tra lớp đầu vào (init_conv) để biết số channels và dim
    for key in ['init_conv.weight', 'conv_in.weight', 'downs.0.0.weight', 'input_blocks.0.0.weight']:
        if key in state_dict:
            shape = state_dict[key].shape
            print(f"   - Lớp đầu vào ('{key}'): {shape}")
            print(f"     => Số kênh đầu vào (Channels): {shape[1]}")
            print(f"     => Kích thước cơ sở (Base Dim): {shape[0]}")
            break
    else:
        print("   - Cảnh báo: Không tìm thấy lớp đầu vào tiêu chuẩn (init_conv/conv_in).")
        # In thử 5 key đầu tiên để đoán
        print("   - 5 key đầu tiên trong model:", list(state_dict.keys())[:5])

    # Kiểm tra lớp Time Embedding để đoán kích thước time_dim
    for key in ['time_mlp.1.weight', 'temb.1.weight']:
        if key in state_dict:
            print(f"   - Time Embedding ('{key}'): {state_dict[key].shape}")
            break

    # Kiểm tra lớp ra (final_conv)
    for key in ['final_conv.weight', 'out.2.weight', 'output_blocks.11.2.conv.weight']:
        if key in state_dict:
            print(f"   - Lớp đầu ra ('{key}'): {state_dict[key].shape}")
            break

if __name__ == "__main__":
    check_model_structure()