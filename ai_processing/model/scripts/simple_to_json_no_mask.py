import argparse
import os
import json
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompt2json.layoutOptimizer_no_mask import process_simple_input

def main():
    parser = argparse.ArgumentParser(
        description="Tạo file JSON từ input đơn giản (không cần mask)."
    )
    parser.add_argument("--input", required=True, help="Input đơn giản, ví dụ: '1 living room, 1 master room'")
    parser.add_argument("--output", default="new_text_no_mask.json", help="Đường dẫn để lưu file JSON")
    
    args = parser.parse_args()
    
    # Xử lý input và tạo JSON mà không cần mask
    json_data = process_simple_input(args.input)
    
    # Lưu JSON vào file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"Successfully created JSON file: {args.output}")

if __name__ == "__main__":
    main()
