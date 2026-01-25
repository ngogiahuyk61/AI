# Module Floorplan Valid

Module này xử lý validation và phát hiện các thành phần trong bản vẽ floorplan, bao gồm phát hiện tường ngoài, entrance, và các phòng.

## Thứ tự chạy các script

### 1. validate_entrance_rooms.py
**Mục đích**: Phát hiện và validate các phòng, entrance trong floorplan
```bash
python module_floorplan_valid/scripts/validate_entrance_rooms.py
```

**Input cần có**:
- `model/source/mask/278_1024.png` - Ảnh mask
- `model/source/new_text/278.json` - File JSON layout
- `model/source/result/278.png` - Ảnh floorplan gốc

**Output tạo ra**:
- `module_floorplan_valid/output/images/` - Các ảnh kết quả
- `module_floorplan_valid/output/json/` - Các file JSON tọa độ
- `module_floorplan_valid/output/debug/` - Ảnh debug
- `module_floorplan_valid/output/entrance_json/` - JSON entrance

### 2. detect_exterior_wall.py
**Mục đích**: Phát hiện tường ngoài từ mask image
```bash
python module_floorplan_valid/scripts/detect_exterior_wall.py
```

**Input cần có**:
- `model/source/mask/278_1024.png` - Ảnh mask
- `model/source/result/278.png` - Ảnh floorplan gốc

**Output tạo ra**:
- `module_floorplan_valid/output/images/exterior_wall_278.png` - Ảnh tường ngoài
- `module_floorplan_valid/output/images/drawing_with_exterior_278.png` - Ảnh overlay
- `module_floorplan_valid/output/json/exterior_wall_278.json` - Tọa độ tường ngoài
- `module_floorplan_valid/output/json/exterior_wall_shrink_278.json` - Tọa độ tường ngoài đã thu nhỏ

### 3. shrink_exterior_wall.py
**Mục đích**: Thu nhỏ polygon tường ngoài và tạo ảnh với vùng ngoài bị ẩn
```bash
python module_floorplan_valid/scripts/shrink_exterior_wall.py
```

**Input cần có**:
- `module_floorplan_valid/output/images/drawing_with_exterior_278.png` - Ảnh từ bước 2
- `module_floorplan_valid/output/json/exterior_wall_278.json` - JSON từ bước 2
- `module_floorplan_valid/output/json/exterior_wall_shrink_278.json` - JSON từ bước 2

**Output tạo ra**:
- `module_floorplan_valid/output/images/drawing_with_black_walls_278.png` - Ảnh với vùng ngoài bị ẩn trắng

### 4. remove_background.py
**Mục đích**: Loại bỏ background và copy file sang module_coordinates_rooms
```bash
python module_floorplan_valid/scripts/remove_background.py
```

**Input cần có**:
- `module_floorplan_valid/output/images/drawing_with_black_walls_278.png` - Ảnh từ bước 3
- `module_floorplan_valid/output/images/exterior_wall_278.png` - Ảnh từ bước 2
- `module_floorplan_valid/output/json/exterior_wall_shrink_278.json` - JSON từ bước 2

**Output tạo ra**:
- `module_coordinates_rooms/input/drawing_overwrite.png` - Ảnh đã loại bỏ background
- `module_coordinates_rooms/input/exterior_wall.png` - Ảnh tường ngoài
- `module_coordinates_rooms/input/exterior_wall_shrink.json` - JSON tường ngoài thu nhỏ

## Lưu ý

- Tất cả script đều được thiết kế để chạy từ thư mục gốc của project
- Các file input cần có sẵn trước khi chạy script
- Script sẽ tự động tạo các thư mục output nếu chưa tồn tại
- TARGET_BASE_NAME mặc định là "278" - có thể thay đổi trong code nếu cần

## Dependencies

- OpenCV (cv2)
- NumPy
- Shapely
- PIL (Pillow)
- rembg (cho remove_background.py)
