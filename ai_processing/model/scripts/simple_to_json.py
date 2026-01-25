import argparse
import os
import json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompt2json.layoutOptimizer_combined import process_simple_input

def main():
    parser = argparse.ArgumentParser(
        description="Tạo file JSON từ input đơn giản và mask"
    )
    parser.add_argument("--input", required=True, help="Input đơn giản, ví dụ: '1 living room, 1 master room, 1 kitchen, 1 study room'")
    parser.add_argument("--mask", required=True, help="Đường dẫn đến file mask (tùy chọn)")
    parser.add_argument("--output", default="new_text.json", help="Đường dẫn để lưu file JSON")
    
    args = parser.parse_args()
    
    # Xử lý input đơn giản và tạo JSON hoàn chỉnh
    json_data = process_simple_input(args.input, args.mask)
    
    # Lưu JSON vào file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"Successfully created JSON file: {args.output}")
    print("You can use this file with quick_predict.py to generate the result drawing.")

if __name__ == "__main__":
    main()