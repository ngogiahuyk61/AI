# 🏠 Gen Floorplan

## 🚀 Chạy dự án

### 1. Tải model từ link drive <[https://drive.google.com/drive/folders/16Xd96-AVt61Mr4RmksFbPhrayNiplHDy?usp=sharing](https://drive.google.com/drive/folders/1k_s7ioeVmZ6ObBAe45ljXiIpOhD0HLot?usp=drive_link)>, đem vào thư mục ai_processing/model/predict_model.
 - Foler predict_model phải có đủ model đuôi pt và pkl; folder model phải có file t5_feature.pkl.

### 2. Cài dependencies cho mỗi model, module trong ai_processing (cd vào folder, chạy lệnh bên dưới cho mỗi folder)
```bash
pip install -r requirements.txt
```
Lưu ý, nếu lỗi thư viện thì có thể do máy đang cài các thư viện như torch, pytorch cho phiên bản CPU, xóa và cài lại bản chạy bằng GPU.

**⚠️ Quan trọng:** Nếu bạn chỉ có CPU (không có GPU), model đã được fix để chạy trên CPU. Xem file `QUICK_START_CPU.md` để biết thêm chi tiết.

### 3. Chạy server Django
Cài môi trường ảo (khuyên dùng)

```bash
cd web_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

### 4. Chạy worker xử lý hàng đợi
Mở một terminal khác (giữ server đang chạy) và chạy:

```bash
cd ai_processing
python model/scripts/multi_mask_worker.py --verbose
```

Mặc định truy cập tại: http://127.0.0.1:8000

Thực hiện tạo hình dạng khu đất yêu cầu với Land setting -> Save.
Sau đó thực hiện nhập mô tả số phòng của floorplan -> Generate Plans



