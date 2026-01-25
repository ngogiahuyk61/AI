# Module Coordinates Rooms

Module này xử lý việc trích xuất tọa độ phòng từ floorplan và tạo ra các visualization.

## Scripts

### 1. coordinates_room_001.py
**Mục đích**: Pipeline hoàn chỉnh từ floorplan image đến room coordinates
```bash
python module_coordinates_rooms/scripts/coordinates_room_001.py
```

**Input cần có**:
- `module_coordinates_rooms/input/drawing_overwrite.png` - Ảnh floorplan đã xử lý
- `module_coordinates_rooms/input/exterior_wall_shrink.json` - JSON tọa độ tường ngoài thu nhỏ

**Output tạo ra**:
- `module_coordinates_rooms/output/images/` - Các ảnh kết quả
- `module_coordinates_rooms/output/json/room_coordinates.json` - Tọa độ phòng dạng COCO

### 2. coordinates_room_v2.py
**Mục đích**: Tạo visualization từ thông tin phòng đã có sẵn
```bash
python module_coordinates_rooms/scripts/coordinates_room_v2.py
```

**Input cần có**:
- `module_coordinates_rooms/output/images/layout_final_clean.png` - Ảnh từ coordinates_room_001.py
- `module_floorplan_valid/output/json/room_coordinates_278.json` - JSON thông tin phòng

**Output tạo ra**:
- `module_coordinates_rooms/output/images/room_visualization.png` - Visualization với tất cả phòng
- `module_coordinates_rooms/output/images/room_visualization_no_living.png` - Visualization không có Living room
- `module_coordinates_rooms/output/json/room_coordinates.json` - Tọa độ phòng dạng COCO

## Thứ tự chạy

1. **Chạy coordinates_room_001.py trước** để tạo file `layout_final_clean.png`
2. **Chạy coordinates_room_v2.py sau** để tạo visualization từ thông tin phòng

## Lưu ý

- Tất cả script đều chạy từ thư mục gốc của project
- coordinates_room_v2.py cần file từ coordinates_room_001.py và module_floorplan_valid
- Script sẽ tự động tạo các thư mục output nếu chưa tồn tại

## Dependencies

- OpenCV (cv2)
- NumPy
- SciPy
- scikit-image (optional)