import cv2
import numpy as np
import json
import os
import shutil
from collections import Counter
from pathlib import Path

# Đã xóa PIL vì không cần thiết trong logic mới, nhưng giữ lại import trong hàm main để resize
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

class FloorplanAreaLabeler:
    # COMMON_ROOM_SEQUENCE không còn cần thiết nữa
    
    # TYPE_DISPLAY_MAP được cập nhật để xử lý tên mới
    TYPE_DISPLAY_MAP = {
        "bathroom": "Bathroom",
        "storage": "Storage",
        "livingroom": "LDK",
        "masterroom": "Bedroom", # Xử lý các tên cũ
        "commonroom": "Common Room",
        "balcony": "Balcony",
        "kitchen": "Kitchen",
        "entrance": "Entrance",
        
        # Xử lý các tên mới (đã được classify)
        "bedroom": "Bedroom",
        "studyroom": "Study Room",
        "japanstyleroom": "Japan Style Room",
    }

    def __init__(self, total_area_m2: float = 100.0):
        self.total_area_m2 = total_area_m2
        self.pixel_to_m2_ratio = 0.0
        # *** LOGIC ĐỌC JSON REQUEST ĐÃ BỊ XÓA BỎ ***
        # self.request_info = self._load_request_info()
        print("✅ Labeler initialized. Will use names from room_data.json")

    # *** HÀM _load_request_info ĐÃ BỊ XÓA BỎ ***
    
    @staticmethod
    def _normalize_key(name: str) -> str:
        return (name or "").lower().replace(" ", "").replace("_", "")

    @staticmethod
    def _parse_room_type(name: str):
        parts = (name or "").split("_")
        if parts and parts[-1].isdigit():
            return "_".join(parts[:-1]), int(parts[-1])
        return name, None

    # *** HÀM _get_request_count ĐÃ BỊ XÓA BỎ ***
    # *** HÀM _build_common_queue ĐÃ BỊ XÓA BỎ ***
    # *** HÀM _build_unknown_queue ĐÃ BỊ XÓA BỎ ***

    def _resolve_display_base(self, raw_name: str) -> str:
        """
        Logic đơn giản hóa: Tin tưởng tên 'raw_name' đã được phân loại
        từ 'furniture_placement.py' và chỉ làm đẹp nó.
        """
        type_key, num = self._parse_room_type(raw_name)
        normalized = self._normalize_key(type_key)

        # Xử lý tên đã được phân loại (vd: "Bedroom_1", "Study_Room")
        if normalized.startswith("bedroom"):
             if num is not None:
                 return f"Bedroom {num}"
             return "Bedroom"
        if normalized == "studyroom":
             return "Study Room"
        if normalized == "japanstyleroom":
             return "Japan Style Room"
             
        # Xử lý các tên cũ (vd: "master_room", "bathroom")
        mapped = self.TYPE_DISPLAY_MAP.get(normalized)
        if mapped:
            return mapped
            
        return type_key.replace("_", " ").title()

    def calculate_pixel_ratio(self, image_path: str) -> float:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        interior_pixels = cv2.countNonZero(binary)
        if interior_pixels > 0:
            self.pixel_to_m2_ratio = self.total_area_m2 / interior_pixels
        print(f"   📏 Interior pixels: {interior_pixels}")
        print(f"   📏 Total area: {self.total_area_m2} m²")
        print(f"   📏 Pixel to m² ratio: {self.pixel_to_m2_ratio:.6f}")
        return self.pixel_to_m2_ratio

    def calculate_room_area(self, corners: list) -> float:
        if len(corners) < 3:
            return 0.0
        area = 0.0
        n = len(corners)
        for i in range(n):
            j = (i + 1) % n
            area += corners[i][0] * corners[j][1]
            area -= corners[j][0] * corners[i][1]
        return abs(area) / 2.0

    def add_area_labels(self, image_path: str, room_data_path: str, output_path: str) -> None:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        with open(room_data_path, 'r', encoding='utf-8') as f:
            room_data = json.load(f)
            
        print("\n📋 Loading classified room names from room_data.json...")
        
        total_calculated_area = 0.0
        room_entries = []

        # --- LOGIC MỚI: Tách phòng tắm lớn thành 2 entry ---
        temp_other_rooms = []
        bathrooms_to_sort = []

        for room in room_data.get('rooms', []):
            room_name = room.get('name', 'Unknown')
            
            # KIỂM TRA SPLIT_ZONES (TỪ add_toilet.py)
            if room.get('split_zones'):
                print(f"   → Found split zones in '{room_name}'. Creating 'Wash' and 'Bath' entries.")
                zones = room['split_zones']
                
                # Xử lý khu vực WASH (60%)
                wash_bbox = zones['wash'] # [x, y, w, h]
                wash_corners = [[wash_bbox[0], wash_bbox[1]], [wash_bbox[0] + wash_bbox[2], wash_bbox[1]], [wash_bbox[0] + wash_bbox[2], wash_bbox[1] + wash_bbox[3]], [wash_bbox[0], wash_bbox[1] + wash_bbox[3]]]
                wash_pixel_area = self.calculate_room_area(wash_corners)
                wash_area_m2 = wash_pixel_area * self.pixel_to_m2_ratio
                wash_center = (int(wash_bbox[0] + wash_bbox[2] / 2), int(wash_bbox[1] + wash_bbox[3] / 2))
                room_entries.append({
                    'raw_name': room_name + "_wash",
                    'display_base': "Wash", # Tên hiển thị mới
                    'center': wash_center,
                    'pixel_area': wash_pixel_area,
                    'area_m2': wash_area_m2,
                    'original_name': room.get('original_name', room_name)
                })
                total_calculated_area += wash_area_m2

                # Xử lý khu vực BATH (40%)
                bath_bbox = zones['bath'] # [x, y, w, h]
                bath_corners = [[bath_bbox[0], bath_bbox[1]], [bath_bbox[0] + bath_bbox[2], bath_bbox[1]], [bath_bbox[0] + bath_bbox[2], bath_bbox[1] + bath_bbox[3]], [bath_bbox[0], bath_bbox[1] + bath_bbox[3]]]
                bath_pixel_area = self.calculate_room_area(bath_corners)
                bath_area_m2 = bath_pixel_area * self.pixel_to_m2_ratio
                bath_center = (int(bath_bbox[0] + bath_bbox[2] / 2), int(bath_bbox[1] + bath_bbox[3] / 2))
                room_entries.append({
                    'raw_name': room_name + "_bath",
                    'display_base': "Bath", # Tên hiển thị mới
                    'center': bath_center,
                    'pixel_area': bath_pixel_area,
                    'area_m2': bath_area_m2,
                    'original_name': room.get('original_name', room_name)
                })
                total_calculated_area += bath_area_m2
            
            # Xử lý phòng bình thường (không phải master bath)
            else:
                center = room.get('center', [0, 0])
                corners = room.get('snapped_corners', [])
                pixel_area = self.calculate_room_area(corners)
                area_m2 = pixel_area * self.pixel_to_m2_ratio
                total_calculated_area += area_m2
                
                display_base = self._resolve_display_base(room_name)
                
                entry = {
                    'raw_name': room_name,
                    'display_base': display_base,
                    'center': (int(center[0]), int(center[1])),
                    'pixel_area': pixel_area,
                    'area_m2': area_m2,
                    'original_name': room.get('original_name', room_name)
                }
                
                # Kiểm tra xem đây có phải là phòng tắm nhỏ (cần sắp xếp) không
                if 'bathroom' in room.get('original_name', '').lower():
                    bathrooms_to_sort.append(entry)
                else:
                    temp_other_rooms.append(entry)
        
        # Sắp xếp các phòng tắm nhỏ (Toilet)
        print(f"\nProcessing {len(bathrooms_to_sort)} smaller bathrooms (renaming to 'Toilet')...")
        bathrooms_to_sort.sort(key=lambda x: x['area_m2'], reverse=True)
        
        for i, bath in enumerate(bathrooms_to_sort, 1):
            bath['display_base'] = f"Toilet {i}"
            
        # Kết hợp tất cả các entry lại
        room_entries.extend(bathrooms_to_sort)
        room_entries.extend(temp_other_rooms)
        # --- KẾT THÚC LOGIC MỚI ---

        display_totals = Counter(entry['display_base'] for entry in room_entries)
        display_seen = Counter()
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        print("\n🔢 Final room labels and areas:")
        for entry in room_entries:
            display_seen[entry['display_base']] += 1
            total_for_name = display_totals[entry['display_base']]
            
            # Chỉ thêm số nếu có nhiều phòng cùng tên (vd: "Bedroom 1", "Bedroom 2")
            if total_for_name > 1 and not any(char.isdigit() for char in entry['display_base']):
                 final_name = f"{entry['display_base']} {display_seen[entry['display_base']]}"
            else:
                 final_name = entry['display_base']
                 
            print(f"   • {final_name:20} : {entry['pixel_area']:8.0f} px → {entry['area_m2']:6.2f} m² (from {entry['raw_name']})")
            center_x, center_y = entry['center']
            area_text = f"{entry['area_m2']:.2f} m2"
            (name_w, name_h), name_baseline = cv2.getTextSize(final_name, font, font_scale, thickness)
            (area_w, area_h), area_baseline = cv2.getTextSize(area_text, font, font_scale, thickness)
            max_width = max(name_w, area_w)
            name_x = center_x - name_w // 2
            name_y = center_y - 2
            area_x = center_x - area_w // 2
            area_y = name_y + name_h + 5
            padding = 5
            bg_x1 = center_x - max_width // 2 - padding
            bg_y1 = name_y - name_h - padding
            bg_x2 = center_x + max_width // 2 + padding
            bg_y2 = area_y + area_baseline + padding
            cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), (255, 255, 255), -1)
            cv2.putText(img, final_name, (name_x, name_y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
            cv2.putText(img, area_text, (area_x, area_y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
            
        print(f"\n   📊 Summary:")
        print(f"   • Total calculated: {total_calculated_area:.2f} m²")
        print(f"   • Input total:      {self.total_area_m2:.2f} m²")
        print(f"   • Difference:       {abs(total_calculated_area - self.total_area_m2):.2f} m² ({abs(total_calculated_area - self.total_area_m2) / self.total_area_m2 * 100:.1f}%)")
        cv2.imwrite(output_path, img)
        print(f"\n   ✅ Saved image with area labels: {output_path}")

    def copy_to_website(self, source_path: str, target_paths: list) -> None:
        """
        Copy image to website static directories
        """
        if not os.path.exists(source_path):
            print(f"   ⚠️ Source file not found: {source_path}")
            return
        for target_path in target_paths:
            try:
                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)
                shutil.copy2(source_path, target_path)
                print(f"   ✅ Copied to: {target_path}")
            except Exception as e:
                print(f"   ⚠️ Error copying to {target_path}: {str(e)}")

def main():
    """Main entry point"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    output_dir = os.path.join(base_dir, "outputs")
    overlay_result = os.path.join(output_dir, "overlay_result.png")
    # Sử dụng file đầu ra của bước trước (furniture_placement)
    colored_floorplan = os.path.join(output_dir, "colored_floorplan_with_furniture.png") 
    room_data_json = os.path.join(output_dir, "room_data.json")
    overlay_with_areas = os.path.join(output_dir, "overlay_result_with_areas.png")
    colored_with_areas = os.path.join(output_dir, "colored_floorplan_with_areas.png") # Final output
    
    # Đường dẫn xuất bản web
    web_app_dir = Path(script_dir).parent.parent.parent / "web_app"
    website_targets = [
        str(web_app_dir / "floorplan_app" / "static" / "floorplan_app" / "img" / "floorplan1.png"),
        str(web_app_dir / "floorplan_app" / "static" / "floorplan_app" / "img" / "proposal1.png"),
    ]
    total_area = float(os.getenv("TOTAL_AREA_M2", "100.0"))
    
    print("\n" + "="*60)
    print("🏠 FLOORPLAN AREA LABELER (Simplified Logic)")
    print("="*60)
    print(f"📍 Total Area: {total_area} m²")
    
    labeler = FloorplanAreaLabeler(total_area_m2=total_area)
    
    # Bước 1: Tính tỷ lệ pixel trên ảnh (dùng ảnh furniture temp hoặc colored_floorplan)
    if os.path.exists(colored_floorplan):
        print("\n📍 Step 1: Calculating pixel ratio...")
        labeler.calculate_pixel_ratio(colored_floorplan)
    else:
        print("   ❌ Error: No base image found to calculate ratio.")
        return

    # Bước 2: Thêm nhãn diện tích vào Overlay (nếu có)
    print("\n📍 Step 2: Adding area labels to overlay_result.png...")
    if os.path.exists(overlay_result):
        labeler.add_area_labels(overlay_result, room_data_json, overlay_with_areas)
    else:
        print(f"   ⚠️ File not found: {overlay_result}")

    # Bước 3: Thêm nhãn diện tích vào ảnh nội thất cuối cùng
    print("\n📍 Step 3: Adding area labels to colored_floorplan_with_furniture.png...")
    if os.path.exists(colored_floorplan):
        labeler.add_area_labels(colored_floorplan, room_data_json, colored_with_areas)
        
        # Ghi đè file colored_floorplan_with_furniture.png bằng file có diện tích (để đồng nhất)
        shutil.copyfile(colored_with_areas, colored_floorplan)
        print(f"   ✅ Updated final output with areas: {os.path.basename(colored_floorplan)}")
    else:
        print(f"   ⚠️ File not found: {colored_floorplan}")
        print("   Please run furniture_placement.py first!")

    # Bước 4: Copy sang website
    print("\n📍 Step 4: Copying to website...")
    labeler.copy_to_website(colored_with_areas, website_targets)

    # --- BỔ SUNG: Copy output sang module_draw_mask/input/floorplan1.png ---
    # Đường dẫn đến module_draw_mask trong thư mục ai_processing
    mask_input_dir = Path(script_dir).parent.parent.parent / "ai_processing" / "module_draw_mask" / "input"
    mask_input_dir.mkdir(parents=True, exist_ok=True)
    mask_input_path = mask_input_dir / "floorplan1.png"
    
    try:
        if HAS_PIL:
            # Đảm bảo resize nếu cần thiết
            img_out = Image.open(colored_with_areas)
            
            # Nếu có ảnh cũ ở đích, lấy size của nó để resize theo (giữ consistency)
            # Nếu không, giữ nguyên size
            orig_path = mask_input_path if mask_input_path.exists() else None
            if orig_path:
                try:
                    with Image.open(orig_path) as img_orig:
                        target_size = img_orig.size
                    img_out = img_out.resize(target_size, Image.Resampling.LANCZOS)
                except Exception:
                    pass # Nếu ảnh gốc lỗi, bỏ qua resize
                    
            img_out.save(mask_input_path)
            print(f"   ✅ Copied (and resized if needed) to: {mask_input_path}")
        else:
            # Fallback nếu không có PIL: Copy trực tiếp
            shutil.copy2(colored_with_areas, mask_input_path)
            print(f"   ✅ Copied (direct) to: {mask_input_path}")
            
    except Exception as e:
        print(f"   ⚠️ Error copying to {mask_input_path}: {str(e)}")

    print("\n" + "="*60)
    print("✅ COMPLETED!")
    print("="*60)
    print(f"\n📁 Output files:")
    print(f"   • {overlay_with_areas}")
    print(f"   • {colored_with_areas}")
    print(f"   • {mask_input_path}")
    print(f"\n🌐 Website files updated:")
    for target in website_targets:
        print(f"   • {target}")

if __name__ == "__main__":
    main()