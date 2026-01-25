import cv2
import numpy as np
import json
from collections import defaultdict
import math
import os
from PIL import Image, ImageDraw, ImageFont
import shutil

class LayoutValidator:
    """
    Layout validation module extracted from validate.py
    Validates generated layout images against JSON specifications
    """
    
    def __init__(self):
        # -------------------------------
        # Màu phòng (BGR) - dùng BGR vì OpenCV
        # -------------------------------
        self.room_colors_bgr = {
            "Living Room":   [170, 232, 238],
            "Master Room":   [0, 165, 255],
            "Kitchen":       [128, 128, 240],
            "Bathroom":      [210, 216, 173],
            "Balcony":       [35, 142, 107],
            "Dining Room":   [214, 112, 218],
            "Storage":       [221, 160, 221],
            "Common Room":   [0, 215, 255],
            # Cấu trúc
            "ExteriorWall":  [0, 0, 0],
            # InteriorWall ảnh này vẽ bằng màu trắng (line) nên ta detect bằng white mask
            "FrontDoor":     [25, 225, 255],   # BGR (tương ứng RGB [255,225,25])
        }

        # Các phòng chính
        self.main_rooms = [
            "Living Room", "Master Room", "Kitchen", "Bathroom",
            "Balcony", "Dining Room", "Storage", "Common Room"
        ]

        # Các tham số (có thể điều chỉnh)
        self.default_tolerance = 25
        self.tolerances = {
            "Balcony": 30,    # balcony nhỏ: cần tol rộng hơn để bắt chuẩn màu olive
            "FrontDoor": 18,  # door: dùng tol nhỏ hơn để tránh gom quá nhiều vùng
            "Dining Room": 25,
            "Storage": 25,
            "Master Room": 25,
            "Common Room": 25
        }

        self.min_area_defaults = {
            "Living Room": 200,
            "Balcony": 5,    # giảm ngưỡng để bắt balcony nhỏ
            "Storage": 10,
        }
        self.global_min_area = 50

        # Scale factor for area calculation
        self.scale_factor = 0.0004  # m² / pixel

    def mask_range(self, img, color_bgr, tol):
        """Create mask for color range detection"""
        low = np.maximum(np.array(color_bgr) - tol, 0).astype(np.uint8)
        up  = np.minimum(np.array(color_bgr) + tol, 255).astype(np.uint8)
        mask = cv2.inRange(img, low, up)
        return mask, low.tolist(), up.tolist()

    def clean_mask(self, mask, open_iter=1, close_iter=2, ksize=3):
        """Clean mask using morphological operations"""
        kernel = np.ones((ksize,ksize), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=open_iter)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
        return mask

    def get_contours_info(self, mask, min_area_thresh):
        """Extract contour information from mask"""
        mask_c = self.clean_mask(mask, open_iter=1, close_iter=2, ksize=3)
        contours, _ = cv2.findContours(mask_c, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area_thresh:
                continue
            x,y,w,h = cv2.boundingRect(cnt)
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"]/M["m00"]); cy = int(M["m01"]/M["m00"])
            else:
                cx,cy = x + w//2, y + h//2
            results.append({"contour": cnt, "center": (cx,cy), "bounding_box": (x,y,w,h), "area_pixels": int(area)})
        results.sort(key=lambda r: r["area_pixels"], reverse=True)
        return results

    def find_wall_in_direction(self, mask, start, dx, dy, maxd=60):
        """Find wall pixel in a specific direction"""
        h,w = mask.shape
        x0,y0 = start
        for d in range(1, maxd+1):
            x = int(round(x0 + dx*d)); y = int(round(y0 + dy*d))
            if x < 0 or x >= w or y < 0 or y >= h:
                break
            if mask[y,x] > 0:
                return (x,y,d)
        return None

    def is_between_two_same_walls(self, mask, center, maxd=60):
        """Check if point is between two walls of same type"""
        # horizontal:
        left = self.find_wall_in_direction(mask, center, -1, 0, maxd)
        right = self.find_wall_in_direction(mask, center, 1, 0, maxd)
        if left and right:
            return True, ('h', left, right)
        # vertical:
        up = self.find_wall_in_direction(mask, center, 0, -1, maxd)
        down = self.find_wall_in_direction(mask, center, 0, 1, maxd)
        if up and down:
            return True, ('v', up, down)
        return False, None

    def simplify_label(self, label: str) -> str:
        """Simplify room labels for display"""
        replacements = {
            "Living Room": "Living",
            "Master Room": "Master",
            "Dining Room": "Dining",
            "Common Room": "Common",
            "ChildRoom": "Child",
            "StudyRoom": "Study",
            "SecondRoom": "Second",
            "GuestRoom": "Guest",
        }
        return replacements.get(label, label)

    def detect_rooms(self, img):
        """Detect all rooms in the image"""
        final_results = defaultdict(list)
        
        # Build a "rooms combined mask" để loại bỏ khi detect interior wall
        all_rooms_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        for r in self.main_rooms:
            if r not in self.room_colors_bgr:
                continue
            tol = self.tolerances.get(r, self.default_tolerance)
            m,_,_ = self.mask_range(img, self.room_colors_bgr[r], tol)
            all_rooms_mask = cv2.bitwise_or(all_rooms_mask, self.clean_mask(m))

        # Detect main rooms
        print("🔍 Detecting main rooms...")
        for room_name in self.main_rooms:
            if room_name not in self.room_colors_bgr:
                print(f"  ❌ {room_name}: no color defined. Skipping.")
                continue
            tol = self.tolerances.get(room_name, self.default_tolerance)
            mask, low, up = self.mask_range(img, self.room_colors_bgr[room_name], tol)
            pixel_count = cv2.countNonZero(mask)
            print(f"  🎨 {room_name}: Target {self.room_colors_bgr[room_name]}, tol ±{tol} -> pixels {pixel_count}")
            if pixel_count == 0:
                continue
            # clean + contours
            min_area = self.min_area_defaults.get(room_name, self.global_min_area)
            infos = self.get_contours_info(mask, min_area)
            print(f"      ✅ Found {len(infos)} region(s) (min_area={min_area})")
            for info in infos:
                final_results[room_name].append({
                    "center": info["center"],
                    "bounding_box": list(info["bounding_box"]),
                    "area_pixels": info["area_pixels"]
                })
                print(f"         - Area {info['area_pixels']}px at {info['center']}")

        # Detect ExteriorWall (black)
        print("\n🧱 Detecting walls...")
        ext_mask, low_ext, up_ext = self.mask_range(img, self.room_colors_bgr["ExteriorWall"], 20)
        ext_mask = self.clean_mask(ext_mask, open_iter=1, close_iter=3, ksize=3)
        ext_infos = self.get_contours_info(ext_mask, 20)
        print(f"  ExteriorWall pixels range {low_ext}..{up_ext} -> found {len(ext_infos)} region(s)")
        for wi in ext_infos:
            final_results["ExteriorWall"].append({
                "center": wi["center"], "bounding_box": list(wi["bounding_box"]), "area_pixels": wi["area_pixels"]
            })

        # Detect InteriorWall via white mask
        white_mask = cv2.inRange(img, np.array([245,245,245],np.uint8), np.array([255,255,255],np.uint8))
        white_mask = cv2.bitwise_and(white_mask, cv2.bitwise_not(all_rooms_mask))
        white_mask = self.clean_mask(white_mask, open_iter=1, close_iter=2, ksize=3)
        int_infos = self.get_contours_info(white_mask, 3)
        print(f"  InteriorWall (white-line) -> found {len(int_infos)} region(s)")
        for wi in int_infos:
            final_results["InteriorWall"].append({
                "center": wi["center"], "bounding_box": list(wi["bounding_box"]), "area_pixels": wi["area_pixels"]
            })

        # Detect & Validate FrontDoor
        print("\n🚪 Detecting FrontDoor...")
        door_mask, low_d, up_d = self.mask_range(img, self.room_colors_bgr["FrontDoor"], self.tolerances.get("FrontDoor", self.default_tolerance))
        print(f"  FrontDoor mask range {low_d} .. {up_d} -> pixels {cv2.countNonZero(door_mask)}")
        door_mask = self.clean_mask(door_mask, open_iter=1, close_iter=2, ksize=3)
        door_candidates = self.get_contours_info(door_mask, min_area_thresh=3)
        print(f"  🔍 Found {len(door_candidates)} FrontDoor candidate(s) after small-area filter")

        # Prepare wall masks for directional tests
        ext_binary = (ext_mask > 0).astype(np.uint8) * 255
        int_binary = (white_mask > 0).astype(np.uint8) * 255

        for i, dc in enumerate(door_candidates, start=1):
            center = dc["center"]
            # check between TWO exterior walls (same-type)
            ext_between, ext_data = self.is_between_two_same_walls(ext_binary, center, maxd=50)
            int_between, int_data = self.is_between_two_same_walls(int_binary, center, maxd=50)
            valid = ext_between or int_between
            print(f"     Candidate {i} at {center}: area={dc['area_pixels']}, ext_between={ext_between}, int_between={int_between} -> {'VALID' if valid else 'INVALID'}")
            if valid:
                final_results["FrontDoor"].append({
                    "center": center,
                    "bounding_box": list(dc["bounding_box"]),
                    "area_pixels": dc["area_pixels"],
                    "ext_between": ext_between,
                    "int_between": int_between
                })

        return final_results

    def create_annotated_image(self, img, final_results, output_path):
        """Create annotated image with room labels and areas"""
        # Convert OpenCV -> PIL
        image_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image_pil)

        try:
            font_path = "C:/Windows/Fonts/arial.ttf"   # Windows font phổ biến
            font_label = ImageFont.truetype(font_path, 18)
            font_area  = ImageFont.truetype(font_path, 16)
        except OSError:
            # fallback nếu không tìm thấy font
            font_label = ImageFont.load_default()
            font_area  = ImageFont.load_default()

        skip_labels = ["ExteriorWall", "InteriorWall"]
        main_rooms_simplified = ["Living", "Master", "Dining", "Kitchen",
                                 "Bathroom", "Balcony", "Storage", "Common"]

        # Draw labels + area
        for label in final_results.keys():
            if label in skip_labels:
                continue

            for i, info in enumerate(final_results[label]):
                cx, cy = info["center"]
                area_m2 = info["area_pixels"] * self.scale_factor

                short_label = self.simplify_label(label)

                if len(final_results[label]) > 1 and short_label not in ["Child","Study","Second","Guest","Common"]:
                    txt = f"{short_label}{i+1}"
                else:
                    txt = short_label

                # Vẽ tên phòng (outline trắng, chữ đen)
                draw.text((cx - 25, cy - 10), txt, font=font_label, fill="black",
                          stroke_width=2, stroke_fill="white")

                # Nếu là phòng chính thì thêm diện tích
                if short_label in main_rooms_simplified:
                    area_text = f"{area_m2:.1f} m²"
                    draw.text((cx - 25, cy + 10), area_text, font=font_area, fill="black",
                              stroke_width=2, stroke_fill="white")

        # Convert PIL -> OpenCV and save
        annot = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
        cv2.imwrite(output_path, annot)

    def validate_against_json(self, detected_results, init_json_path):
        """Validate detected rooms against initial JSON specification"""
        if not os.path.exists(init_json_path):
            print("\n⚠️ layout_init.json not found, skipping validation.")
            return False, "JSON file not found"

        with open(init_json_path, "r", encoding="utf-8") as f:
            layout_init = json.load(f)

        print("\n🔎 VALIDATION RESULT")
        print("="*40)

        # Mapping tên giữa 2 file
        room_name_mapping = {
            "LivingRoom": "Living Room",
            "MasterRoom": "Master Room", 
            "DiningRoom": "Dining Room",
            "Storage": "Storage",
            "Kitchen": "Kitchen",
            "Entrance": "FrontDoor",  # Entrance trong init -> FrontDoor trong detected
            # Các phòng thuộc CommonRoom
            "ChildRoom": "Common Room",
            "StudyRoom": "Common Room",
            "SecondRoom": "Common Room",
            "GuestRoom": "Common Room"
        }

        # Đếm số common room detect được
        common_count = len(detected_results.get("Common Room", []))

        all_valid = True
        validation_details = []

        for key, value in layout_init.items():
            expected_num = value.get("num", 0)

            # Nếu phòng thuộc nhóm common
            if key in ["ChildRoom", "StudyRoom", "SecondRoom", "GuestRoom"]:
                detected_count = min(expected_num, common_count)  # phân bổ từ CommonRoom detect được
                common_count -= detected_count
            else:
                detected_key = room_name_mapping.get(key, key)
                detected_count = len(detected_results.get(detected_key, []))

            is_valid = detected_count == expected_num
            status = "✅ VALID" if is_valid else f"❌ MISMATCH (expected {expected_num}, got {detected_count})"
            print(f"{key:12s} -> expected {expected_num}, detected {detected_count} --> {status}")
            
            validation_details.append({
                "room": key,
                "expected": expected_num,
                "detected": detected_count,
                "valid": is_valid
            })

            if not is_valid:
                all_valid = False

        if all_valid:
            print("\n🎉 All rooms matched correctly!")
            return True, "All rooms validated successfully"
        else:
            print("\n⚠️ Some rooms mismatched. Check mapping or detection results.")
            return False, f"Validation failed: {validation_details}"

    def validate_layout(self, image_path, json_path, output_dir, validate_output_dir):
        """
        Main validation function
        
        Args:
            image_path: Path to generated layout image
            json_path: Path to JSON specification file
            output_dir: Directory for intermediate results
            validate_output_dir: Directory for validated results
            
        Returns:
            tuple: (is_valid, message, results_dict)
        """
        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                return False, f"Cannot load image: {image_path}", None

            # Detect rooms
            detected_results = self.detect_rooms(img)

            # Print summary
            print("\n" + "="*50)
            print("📊 SUMMARY")
            print("="*50)
            for room in self.main_rooms:
                cnt = len(detected_results.get(room, []))
                print(f"{room:12s}: {cnt:2d}")
            print(f"ExteriorWall : {len(detected_results.get('ExteriorWall',[]))}")
            print(f"InteriorWall : {len(detected_results.get('InteriorWall',[]))}")
            print(f"FrontDoor    : {len(detected_results.get('FrontDoor',[]))}")

            # Create output paths
            base_filename = os.path.splitext(os.path.basename(image_path))[0]
            annotated_image_path = os.path.join(output_dir, f"{base_filename}_annotated.png")
            detection_json_path = os.path.join(output_dir, f"{base_filename}_detected.json")

            # Create annotated image
            self.create_annotated_image(img, detected_results, annotated_image_path)

            # Save detection results
            with open(detection_json_path, "w", encoding="utf-8") as f:
                json.dump(detected_results, f, indent=2, ensure_ascii=False)

            # Validate against JSON
            is_valid, validation_message = self.validate_against_json(detected_results, json_path)

            # If validation passes, copy to validate_result directory
            if is_valid:
                os.makedirs(validate_output_dir, exist_ok=True)
                validated_image_path = os.path.join(validate_output_dir, f"{base_filename}_validated.png")
                validated_json_path = os.path.join(validate_output_dir, f"{base_filename}_validated.json")
                
                # Copy original image and JSON to validated directory
                shutil.copy2(image_path, validated_image_path)
                shutil.copy2(detection_json_path, validated_json_path)
                
                print(f"\n✅ Validation passed! Files copied to: {validate_output_dir}")

            print(f"\n✅ Output written:")
            print(f"   - Annotated image: {annotated_image_path}")
            print(f"   - Detection JSON : {detection_json_path}")

            return is_valid, validation_message, detected_results

        except Exception as e:
            return False, f"Validation error: {str(e)}", None
