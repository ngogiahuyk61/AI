from PIL import Image
import numpy as np
import matplotlib.pyplot as plt

def visualize_gray_levels(path):
    img = Image.open(path).convert("L")
    arr = np.array(img)

    # Hiển thị ảnh gốc
    plt.figure(figsize=(12,4))
    plt.subplot(1,3,1)
    plt.imshow(arr, cmap="gray", vmin=0, vmax=255)
    plt.title("Ảnh gốc (Grayscale)")
    plt.axis("off")

    # Tăng tương phản để thấy rõ vùng xám
    boosted = np.clip(arr * 10, 0, 255).astype(np.uint8)
    plt.subplot(1,3,2)
    plt.imshow(boosted, cmap="gray", vmin=0, vmax=255)
    plt.title("Tăng độ sáng ×10 (thấy vùng xám)")
    plt.axis("off")

    # Hiển thị mask phân loại vùng 0 / 14–15 / 255
    mask_dark = (arr >= 1) & (arr <= 20)
    mask_white = arr >= 200
    mask_black = arr == 0

    overlay = np.zeros((*arr.shape, 3), dtype=np.uint8)
    overlay[mask_black] = [0, 0, 0]       # Đen
    overlay[mask_dark] = [255, 0, 0]      # Đỏ = vùng xám
    overlay[mask_white] = [255, 255, 255] # Trắng

    plt.subplot(1,3,3)
    plt.imshow(overlay)
    plt.title("🔴 Vùng đỏ = pixel xám (14–15)")
    plt.axis("off")

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    path = "D:/10_10/ai-key-plan/ai_processing/model/source/mask/mask.png"  # thay đường dẫn bạn muốn
    visualize_gray_levels(path)
