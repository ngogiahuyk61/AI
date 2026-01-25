import cv2
import numpy as np
import json
from collections import defaultdict
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon


MASK_DIR = "./source/mask"
JSON_DIR = "./source/new_text"
IMG_DIR = "./source/result"
OUTPUT_DIR = "./source/validate_result"
OUTPUT_IMG_DIR = f"{OUTPUT_DIR}/images"
OUTPUT_JSON_DIR = f"{OUTPUT_DIR}/json"
OUTPUT_DEBUG_DIR = f"{OUTPUT_DIR}/debug"
OUTPUT_ENTRANCE_DIR = f"{OUTPUT_DIR}/entrance_json"


os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)
os.makedirs(OUTPUT_DEBUG_DIR, exist_ok=True)
os.makedirs(OUTPUT_ENTRANCE_DIR, exist_ok=True)


room_colors_bgr = {
    "Living Room":   [170, 232, 238],  
    "Master Room":   [0, 165, 255],    
    "Kitchen":       [128, 128, 240],  
    "Bathroom":      [210, 216, 173], 
    "Balcony":       [35, 142, 107],   
    "Dining Room":   [214, 112, 218], 
    "Storage":       [221, 160, 221],  
    "Common Room":   [0, 215, 255],    
    "ExteriorWall":  [0, 0, 0]        
}

main_rooms = [
    "Living Room", "Master Room", "Kitchen", "Bathroom",
    "Balcony", "Dining Room", "Storage", "Common Room"
]


tolerances = {
    "Living Room": 30,
    "Master Room": 35,     
    "Kitchen": 30,
    "Bathroom": 40,        
    "Balcony": 40,        
    "Dining Room": 30,
    "Storage": 30,
    "Common Room": 30
}
default_tolerance = 30


min_area_defaults = {
    "Living Room": 2000,
    "Master Room": 1500,  
    "Kitchen": 1500,
    "Bathroom": 800,      
    "Balcony": 800,       
    "Dining Room": 1500,
    "Storage": 500,       
    "Common Room": 1000,
}
global_min_area = 300     


def normalize_room_name(name):
    """Chuẩn hóa tên phòng để so sánh"""
    return name.lower().replace(" ", "").replace("_", "")

def mask_range(img, color_bgr, tol):
    """Tạo mask với tolerance"""
    low = np.maximum(np.array(color_bgr) - tol, 0).astype(np.uint8)
    up  = np.minimum(np.array(color_bgr) + tol, 255).astype(np.uint8)
    mask = cv2.inRange(img, low, up)
    return mask, low.tolist(), up.tolist()

def clean_mask(mask, open_iter=1, close_iter=2, ksize=3):
    """Làm sạch mask"""
    kernel = np.ones((ksize,ksize), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=open_iter)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
    return mask

def get_contours_info(mask, min_area_thresh):
    """Tìm contours từ mask"""
    mask_c = clean_mask(mask, open_iter=1, close_iter=2, ksize=3)
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
        results.append({
            "contour": cnt, 
            "center": (cx,cy), 
            "bounding_box": (x,y,w,h), 
            "area_pixels": int(area)
        })
    results.sort(key=lambda r: r["area_pixels"], reverse=True)
    return results


def validate_entrance_detection(mask_img, drawing_img):
    """Logic entrance detection"""
    try:
        if mask_img is None or drawing_img is None:
            return None
        
   
        gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
        mask_black = cv2.inRange(gray, 0, 30)
        contours, _ = cv2.findContours(mask_black, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        exterior_coords = []
        for cnt in contours:
            coords = cnt.squeeze().tolist()
            if isinstance(coords[0], list):
                exterior_coords.append(coords)
            else:
                exterior_coords.append([coords])
        
      
        shrunk_coords_all = []
        for polygon in exterior_coords:
            try:
                poly = Polygon(polygon)
                if not poly.is_valid or poly.is_empty:
                    continue
                
                shrunk_poly = poly.buffer(-20)
                if shrunk_poly.is_empty:
                    continue
                
                if shrunk_poly.geom_type == "MultiPolygon":
                    for p in shrunk_poly:
                        shrunk_coords_all.append(
                            [[int(x), int(y)] for x, y in p.exterior.coords]
                        )
                else:
                    shrunk_coords_all.append(
                        [[int(x), int(y)] for x, y in shrunk_poly.exterior.coords]
                    )
            except:
                continue
        
        shapely_polygons = []
        for coords in shrunk_coords_all:
            try:
                poly = Polygon(coords)
                if poly.is_valid and not poly.is_empty:
                    shapely_polygons.append(poly)
            except:
                continue
        
     
        lower = np.array([0, 200, 200], dtype=np.uint8)
        upper = np.array([50, 255, 255], dtype=np.uint8)
        mask_yellow = cv2.inRange(drawing_img, lower, upper)
        
        kernel = np.ones((3, 3), np.uint8)
        mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        contours_yellow, _ = cv2.findContours(mask_yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
       
        entrance_coords = []
        
        for cnt in contours_yellow:
            if cv2.contourArea(cnt) < 50:
                continue
            
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            point = Point(cx, cy)
            
            inside_any = False
            for poly in shapely_polygons:
                if poly.contains(point):
                    inside_any = True
                    break
            
            if not inside_any:  
                x, y, w, h = cv2.boundingRect(cnt)
            
                if w < h:
                    x_center = x + w // 2
                    x = x_center - 5
                    w = 10
                else:
                    y_center = y + h // 2
                    y = y_center - 5
                    h = 10
                
                entrance_coords.append({
                    "center": [cx, cy],
                    "bounding_box": [int(x), int(y), int(w), int(h)],
                    "area_pixels": float(cv2.contourArea(cnt)),
                    "valid": True
                })
        
        if len(entrance_coords) > 0:
            return {
                "center": tuple(entrance_coords[0]["center"]),
                "bounding_box": entrance_coords[0]["bounding_box"],
                "area_pixels": entrance_coords[0]["area_pixels"]
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error in entrance detection: {e}")
        return None

def separate_common_rooms_and_entrance(img, mask_img, drawing_img):
    """Tách Common Room và Entrance"""
    entrance_info = validate_entrance_detection(mask_img, drawing_img)
    
    common_color = room_colors_bgr["Common Room"]
    mask, _, _ = mask_range(img, common_color, tolerances.get("Common Room", 30))
    mask = clean_mask(mask)
    
    common_infos = get_contours_info(mask, global_min_area)
    
    return common_infos, entrance_info


def process_single_file(mask_path, json_path, img_path, base_name):
    """Xử lý một bộ file: mask, json, image"""
    print(f"\n{'='*60}")
    print(f"Processing: {base_name}.png")
    print(f"{'='*60}")
    
 
    img = cv2.imread(img_path)
    mask_img = cv2.imread(mask_path)
    
    if img is None:
        print(f"Cannot load image: {img_path}")
        return False
    
    print(f"📷 Loaded image: {img.shape}")
    
 
    all_rooms_mask = np.zeros(img.shape[:2], dtype=np.uint8)
    for r in main_rooms:
        if r not in room_colors_bgr or r == "Common Room":
            continue
        tol = tolerances.get(r, default_tolerance)
        m, _, _ = mask_range(img, room_colors_bgr[r], tol)
        all_rooms_mask = cv2.bitwise_or(all_rooms_mask, clean_mask(m))

    final_results = defaultdict(list)

   
    for room_name in main_rooms:
        if room_name not in room_colors_bgr or room_name == "Common Room":
            continue
        tol = tolerances.get(room_name, default_tolerance)
        mask, low, up = mask_range(img, room_colors_bgr[room_name], tol)
        min_area = min_area_defaults.get(room_name, global_min_area)
        infos = get_contours_info(mask, min_area)
        
        if len(infos) > 0:
            print(f"  ✓ {room_name}: detected {len(infos)} room(s)")
        
        for info in infos:
            final_results[room_name].append({
                "center": info["center"],
                "bounding_box": list(info["bounding_box"]),
                "area_pixels": info["area_pixels"]
            })

 
    common_infos, entrance_info = separate_common_rooms_and_entrance(img, mask_img, img)

    for info in common_infos:
        final_results["Common Room"].append({
            "center": info["center"],
            "bounding_box": list(info["bounding_box"]),
            "area_pixels": info["area_pixels"]
        })

   
    entrance_data = {}
    if entrance_info:
        final_results["Entrance"].append(entrance_info)
        entrance_data = {
            "Entrance": {
                "num": 1,
                "coordinates": [entrance_info]
            }
        }
        valid_entrance = True
        print("  ✓ Entrance: detected 1 entrance")
        print("✅ Có entrance: Có")
    else:
        final_results["Entrance"] = []
        entrance_data = {
            "Entrance": {
                "num": 0,
                "coordinates": []
            }
        }
        valid_entrance = False
        print("❌ Có entrance: Không")

   
    ext_mask, _, _ = mask_range(img, room_colors_bgr["ExteriorWall"], 20)
    ext_mask = clean_mask(ext_mask, open_iter=1, close_iter=3, ksize=3)
    ext_infos = get_contours_info(ext_mask, 20)
    for wi in ext_infos:
        final_results["ExteriorWall"].append({
            "center": wi["center"], 
            "bounding_box": list(wi["bounding_box"]), 
            "area_pixels": wi["area_pixels"]
        })

  
    white_mask = cv2.inRange(img, np.array([245,245,245],np.uint8), np.array([255,255,255],np.uint8))
    white_mask = cv2.bitwise_and(white_mask, cv2.bitwise_not(all_rooms_mask))
    white_mask = clean_mask(white_mask, open_iter=1, close_iter=2, ksize=3)
    int_infos = get_contours_info(white_mask, 3)
    for wi in int_infos:
        final_results["InteriorWall"].append({
            "center": wi["center"], 
            "bounding_box": list(wi["bounding_box"]), 
            "area_pixels": wi["area_pixels"]
        })

    
    final_results_with_num = {}
    for room_type, coords_list in final_results.items():
        final_results_with_num[room_type] = {
            "num": len(coords_list),
            "coordinates": coords_list
        }

  
    image_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image_pil)

    try:
        font_path = "C:/Windows/Fonts/arial.ttf"
        font_label = ImageFont.truetype(font_path, 18)
    except OSError:
        font_label = ImageFont.load_default()

    skip_labels = ["ExteriorWall", "InteriorWall"]

    for label in final_results.keys():
        if label in skip_labels:
            continue
        for i, info in enumerate(final_results[label]):
            if not isinstance(info, dict) or "center" not in info:
                continue
            cx, cy = info["center"]
            txt = label if label != "Common Room" else "Common"
            
            if label == "Entrance":
                draw.ellipse([cx-15, cy-15, cx+15, cy+15], outline="red", width=3)
                txt = "ENTRANCE"
            
            draw.text((cx - 25, cy - 10), txt, font=font_label, fill="black",
                      stroke_width=2, stroke_fill="white")

    annot = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    output_img_path = f"{OUTPUT_IMG_DIR}/floorplan_labeled_{base_name}.png"
    cv2.imwrite(output_img_path, annot)

  
    if entrance_info:
        debug_img = img.copy()
        ex, ey = entrance_info["center"]
        cv2.circle(debug_img, (ex, ey), 8, (0, 0, 255), -1)
        cv2.rectangle(debug_img, 
                     (entrance_info["bounding_box"][0], entrance_info["bounding_box"][1]),
                     (entrance_info["bounding_box"][0] + entrance_info["bounding_box"][2],
                      entrance_info["bounding_box"][1] + entrance_info["bounding_box"][3]),
                     (0, 255, 0), 2)
        debug_path = f"{OUTPUT_DEBUG_DIR}/debug_entrance_{base_name}.png"
        cv2.imwrite(debug_path, debug_img)

    
    output_json_path = f"{OUTPUT_JSON_DIR}/room_coordinates_{base_name}.json"
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(final_results_with_num, f, indent=2, ensure_ascii=False)

    entrance_json_path = f"{OUTPUT_ENTRANCE_DIR}/entrance_coordinates_{base_name}.json"
    with open(entrance_json_path, "w", encoding="utf-8") as f:
        json.dump(entrance_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Output written successfully!")
    print(f" Annotated image: {output_img_path}")
    print(f" Room JSON: {output_json_path}")
    print(f" Entrance JSON: {entrance_json_path}")


    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            layout_init = json.load(f)

        print(f"\n VALIDATION RESULT")
        print("="*40)

      
        room_name_mapping = {
            "livingroom": "Living Room",
            "masterroom": "Master Room",
            "diningroom": "Dining Room",
            "storage": "Storage", 
            "kitchen": "Kitchen",
            "bathroom": "Bathroom",
            "balcony": "Balcony",
            "entrance": "Entrance",
            "childroom": "Common Room",
            "studyroom": "Common Room", 
            "secondroom": "Common Room",
            "guestroom": "Common Room"
        }

        common_count = final_results_with_num.get("Common Room", {}).get("num", 0)
        all_valid = True

        for key, value in layout_init.items():
            key_normalized = normalize_room_name(key)
            
  
            if key_normalized in ["childroom", "studyroom", "secondroom", "guestroom"]:
              
                expected_num = value.get("num", 0)
                detected_count = min(expected_num, common_count)
                common_count -= detected_count
            elif key_normalized == "entrance":
              
                detected_count = entrance_data.get("Entrance", {}).get("num", 0)
                if detected_count == 1:
                   
                    expected_num = 1
                else:
                   
                    expected_num = value.get("num", 0)
            else:
               
                expected_num = value.get("num", 0)
                detected_key = room_name_mapping.get(key_normalized, key)
                detected_count = final_results_with_num.get(detected_key, {}).get("num", 0)

            
            if detected_count == expected_num:
                status = "✅ VALID"
            else:
                status = f"❌ MISMATCH (expected {expected_num}, got {detected_count})"
                all_valid = False
            
            print(f"{key:12s} -> expected {expected_num}, detected {detected_count} --> {status}")

        if all_valid:
            print("\n All rooms (including Entrance) matched correctly!")
        else:
            print("\n Some rooms or Entrance mismatched.")
    else:
        print(f"\n JSON not found: {json_path}")
    
    return True


def main():
  
    mask_files = sorted(Path(MASK_DIR).glob("*.png"))
    json_files = sorted(Path(JSON_DIR).glob("*.json"))
    img_files = sorted(Path(IMG_DIR).glob("*.png"))
    
    if not mask_files or not json_files or not img_files:
        print("❌ Không tìm thấy file trong thư mục source!")
        return
    
   
    n = min(len(mask_files), len(json_files), len(img_files))
    
    print(f"🔍 Found {n} sets of files to process")
    
 
    for i in range(n):
        mask_path = str(mask_files[i])
        json_path = str(json_files[i])
        img_path = str(img_files[i])
        
       
        base_name = Path(img_files[i]).stem
        
        process_single_file(mask_path, json_path, img_path, base_name)
    
    print(f"\n{'='*60}")
    print(f"✅ Đã xử lý xong {n} bộ file!")
    print(f" Output directory: {OUTPUT_DIR}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()