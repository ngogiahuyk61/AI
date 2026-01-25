#!/usr/bin/env python3
"""
Simple validation script for single image and JSON pair
Usage: python simple_validate.py --image path/to/image.png --json path/to/spec.json
"""

import os
import argparse
import sys
from layout_validator import LayoutValidator

def main():
    parser = argparse.ArgumentParser(
        description='🔍 Simple validation for single image and JSON pair'
    )
    parser.add_argument('--image', type=str, required=True,
                        help='Path to generated layout image')
    parser.add_argument('--json', type=str, required=True,
                        help='Path to JSON specification file')
    parser.add_argument('--output-dir', type=str, default='../source/result',
                        help='Directory for intermediate results (default: ../source/result)')
    parser.add_argument('--validate-dir', type=str, default='../source/validate_result',
                        help='Directory for validated results (default: ../source/validate_result)')
    
    args = parser.parse_args()
    
    # Convert relative paths to absolute
    base_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.abspath(args.image)
    json_path = os.path.abspath(args.json)
    output_dir = os.path.abspath(os.path.join(base_dir, args.output_dir))
    validate_dir = os.path.abspath(os.path.join(base_dir, args.validate_dir))
    
    # Check if files exist
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)
        
    if not os.path.exists(json_path):
        print(f"❌ JSON file not found: {json_path}")
        sys.exit(1)
    
    # Create output directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(validate_dir, exist_ok=True)
    
    print("🔍 Starting simple validation...")
    print(f"📁 Image: {image_path}")
    print(f"📄 JSON: {json_path}")
    print(f"📂 Output dir: {output_dir}")
    print(f"✅ Validate dir: {validate_dir}")
    print("-" * 50)
    
    # Initialize validator
    validator = LayoutValidator()
    
    try:
        # Run validation
        is_valid, validation_message, detected_results = validator.validate_layout(
            image_path, 
            json_path, 
            output_dir, 
            validate_dir
        )
        
        print("-" * 50)
        if is_valid:
            print("🎉 VALIDATION PASSED!")
            print(f"✅ {validation_message}")
            print(f"📁 Validated files saved to: {validate_dir}")
        else:
            print("❌ VALIDATION FAILED!")
            print(f"⚠️ {validation_message}")
            print("📁 Check intermediate results for details")
        
        # Print summary of detected rooms
        if detected_results:
            print("\n📊 DETECTED ROOMS SUMMARY:")
            for room_type, rooms in detected_results.items():
                if rooms:  # Only show non-empty room types
                    print(f"  {room_type}: {len(rooms)} detected")
        
        return 0 if is_valid else 1
        
    except Exception as e:
        print(f"❌ Validation error: {str(e)}")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
