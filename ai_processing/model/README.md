# Quick start
1. Install Python 3.11.9, link: https://www.python.org/downloads/release/python-3119/
2. Install relative packages.

    ```shell
    pip install -r requirements.txt
    ```

3. Download the predict model and unzip it in `predict_model`.
the model and parameters can be downloaded in <https://drive.google.com/drive/folders/16Xd96-AVt61Mr4RmksFbPhrayNiplHDy?usp=sharing>

4. **Run queue worker (CPU environment)**

    Web app sẽ ghi yêu cầu vào `source/queue/queue-<timestamp>.json`. Để xử lý và sinh ảnh cần chạy worker trong môi trường CPU (ngoài virtualenv của Django nếu cần):

    ```shell
    # Ví dụ: chạy một lần xử lý các job đang chờ
    python scripts/queue_worker.py --once --verbose

    # Hoặc chạy liên tục dưới dạng daemon
    python scripts/queue_worker.py --verbose
    ```

    Tùy chọn:

    - `--python`: chỉ định interpreter khác nếu worker cần chạy trong môi trường riêng (ví dụ `python scripts/queue_worker.py --python C:\\PythonEnv\\python.exe`).
    - `--mask`: thay đổi đường dẫn mask (mặc định `source/mask/4.png`).
    - `--no-invert-mask`: tắt `--invert-mask` khi gọi `quick_predict.py`.
    - Worker sau khi xử lý thành công sẽ tự động copy ảnh kết quả sang `floorplan_app/static/floorplan_app/img/floorplan1.png` (và nếu tồn tại, cả `staticfiles/floorplan_app/img/floorplan1.png`). Sau đó chỉ cần refresh trình duyệt để thấy ảnh mới.
    - Worker cũng tự động chạy pipeline `furnitures_doors/` (phát hiện cửa, dán nội thất) trước khi copy ảnh. Ảnh gốc và JSON layout sẽ được sync vào `furnitures_doors/data/input/`. Hãy đảm bảo đã cài các phụ thuộc bằng `pip install -r furnitures_doors/requirements.txt` trong môi trường CPU.

5. **Batch test (tùy chọn)**
    ```shell
    python scripts/batch_test.py --input "1 living room, 1 master room, 2 second room, 2 bathroom, 1 balcony" --direct-json
    ``` 
