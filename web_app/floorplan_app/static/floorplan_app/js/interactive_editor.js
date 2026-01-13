/*
 * INTERACTIVE EDITOR V27 (PYTHON COMPATIBLE JSON)
 * Compatible with furniture_placement.py V18 structure.
 */

// --- GLOBAL VARIABLES ---
let canvas;
let scaleRatio = 100; // Pixels per Meter

const THEME = {
    wallStroke: '#333333',
    strokeWidth: 2,
    wallFillDefault: '#fdfdf0',
    text: '#000000',
    font: 'Inter, sans-serif',
    selected: '#4A90E2',
    doorStroke: '#5d4037',
    dimColor: '#000000',
    dimGuideColor: '#a0a0a0',
    dimFont: 'Arial',
    dimFontSize: 12
};

document.addEventListener('DOMContentLoaded', () => {
    initCanvas();
    loadSceneData();
    setupEventHandlers();
});

function initCanvas() {
    const container = document.getElementById('techShiftContainer');
    if (!container) return;

    // --- FIX GIAO DIỆN: ÉP FULL SIZE ---
    container.style.width = "100%";
    container.style.display = "block";
    
    // 1. Tính toán Chiều Rộng
    let width = container.clientWidth;
    if (width === 0 && container.parentElement) {
        width = container.parentElement.clientWidth;
    }

    // 2. Tính toán Chiều Cao
    let height = container.clientHeight;
    if (height < 400) { 
        // Lấy chiều cao màn hình trừ đi phần header (khoảng 150-180px)
        const rect = container.getBoundingClientRect();
        if (rect.top > 0) {
             height = window.innerHeight - rect.top - 20;
        } else {
             height = window.innerHeight - 180;
        }
        
        // Gán chiều cao tối thiểu để không bị lỗi
        if (height < 500) height = 600;
        
        container.style.height = height + "px"; 
    }

    // Xóa canvas cũ nếu có (chỉ dispose object fabric, không xóa html)
    if (window.vectorCanvas) {
        try { window.vectorCanvas.dispose(); } catch(e) {}
    }

    // Tạo thẻ canvas nếu chưa có
    let el = document.getElementById('vectorCanvas');
    if (!el) {
        el = document.createElement('canvas');
        el.id = 'vectorCanvas';
        
        // --- [QUAN TRỌNG] ĐỪNG XÓA DÒNG NÀY ĐI ---
        // Dòng lỗi cũ: container.innerHTML = '';  <-- NGUYÊN NHÂN LỖI LÀ ĐÂY (Nó xóa mất thẻ imgProposal1)
        // ------------------------------------------
        
        container.appendChild(el);
    }

    // Khởi tạo Fabric
    window.vectorCanvas = new fabric.Canvas('vectorCanvas', {
        width: width,
        height: height,
        backgroundColor: '#ffffff',
        selection: true,
        preserveObjectStacking: true,
        uniScaleTransform: true
    });

    canvas = window.vectorCanvas;

    // --- AUTO RESIZE ---
    window.addEventListener('resize', () => {
        const newWidth = container.clientWidth;
        // Tính lại height khi resize
        const rect = container.getBoundingClientRect();
        const newHeight = window.innerHeight - rect.top - 20;
        
        canvas.setWidth(newWidth);
        canvas.setHeight(newHeight);
        container.style.height = newHeight + "px";
        canvas.requestRenderAll();
    });

    // ... (Giữ nguyên phần Zoom Logic và Pan Logic ở dưới không đổi) ...
    canvas.on('mouse:wheel', function (opt) {
        var delta = opt.e.deltaY;
        var zoom = canvas.getZoom();
        zoom *= 0.999 ** delta;
        if (zoom > 20) zoom = 20;
        if (zoom < 0.1) zoom = 0.1;
        canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
        opt.e.preventDefault();
        opt.e.stopPropagation();
    });

    let isDragging = false, lastX, lastY;
    canvas.on('mouse:down', function (opt) {
        if (opt.e.altKey === true) {
            isDragging = true;
            canvas.selection = false;
            lastX = opt.e.clientX;
            lastY = opt.e.clientY;
            canvas.defaultCursor = 'grab';
        }
    });
    canvas.on('mouse:move', function (opt) {
        if (isDragging) {
            var e = opt.e;
            var vpt = canvas.viewportTransform;
            vpt[4] += e.clientX - lastX;
            vpt[5] += e.clientY - lastY;
            canvas.requestRenderAll();
            lastX = e.clientX;
            lastY = e.clientY;
        }
    });
    canvas.on('mouse:up', function () {
        isDragging = false;
        canvas.selection = true;
        canvas.defaultCursor = 'default';
    });
}

function loadSceneData() {
    const url = `/static/floorplan_app/data/room_data.json?t=${Date.now()}`;

    fetch(url)
        .then(res => res.json())
        .then(data => {
            console.log("📥 Loaded Data:", data);
            canvas.clear();
            canvas.setBackgroundColor('#ffffff', canvas.renderAll.bind(canvas));

            // 1. Tính Scale
            if (data.rooms && data.rooms.length > 0) {
                const totalM2 = data.total_area_m2 || 100.0;
                calculateScale(data.rooms, totalM2);

                // Sắp xếp vẽ phòng to trước
                data.rooms.sort((a, b) => calculateRawArea(b.snapped_corners) - calculateRawArea(a.snapped_corners));

                data.rooms.forEach(room => createRoomObject(room));
            }

            // 2. Vẽ Furniture
            if (data.furniture) {
                const promises = data.furniture.map(item => createFurnitureObject(item));
                Promise.all(promises).then(() => finalizeRendering());
            } else {
                finalizeRendering();
            }
        })
        .catch(err => console.error("❌ Load Error:", err));
}

function finalizeRendering() {
    setTimeout(() => {
        // Tự động Zoom và Căn giữa
        zoomToContent();
        
        // Vẽ lại kích thước sau khi zoom
        const rooms = canvas.getObjects().filter(o => o.isRoom);
        if (rooms.length > 0) {
            const oldDims = canvas.getObjects().filter(o => o.isDimension);
            oldDims.forEach(d => canvas.remove(d));
            addTechnicalDimensions(rooms);
        }
        
        forceLayerOrder();
    }, 200);
}

// ============================================================
//  CORE SAVE LOGIC (PYTHON COMPATIBLE)
// ============================================================
// window.saveInteractiveData = function () {
//     const loader = document.getElementById('loadingOverlay');
//     if (loader) {
//         loader.hidden = false;
//         const msg = loader.querySelector('.loading-message');
//         if (msg) msg.innerText = "Processing 100% House View...";
//     }

//     // 1. Chuẩn bị Canvas (Bỏ chọn để không dính viền xanh)
//     canvas.discardActiveObject();
//     canvas.requestRenderAll();

//     const allObjects = canvas.getObjects();
//     if (allObjects.length === 0) {
//         if(loader) loader.hidden = true;
//         return;
//     }

//     // 2. Tính toán Bounding Box (Vùng bao quanh toàn bộ nhà)
//     // Lưu ý: getBoundingRect(true) trả về tọa độ tuyệt đối trên canvas, không phụ thuộc vào viewport hiện tại
//     let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

//     allObjects.forEach(obj => {
//         const b = obj.getBoundingRect(true); 
//         if (b.left < minX) minX = b.left;
//         if (b.top < minY) minY = b.top;
//         if (b.left + b.width > maxX) maxX = b.left + b.width;
//         if (b.top + b.height > maxY) maxY = b.top + b.height;
//     });

//     // Thêm padding 50px mỗi bên cho thoáng
//     const padding = 50;
//     // Tính toán vùng Crop (Làm tròn để tránh lỗi sub-pixel)
//     const cropX = Math.floor(minX - padding);
//     const cropY = Math.floor(minY - padding);
//     const cropWidth = Math.ceil((maxX - minX) + (padding * 2));
//     const cropHeight = Math.ceil((maxY - minY) + (padding * 2));

//     // 3. CHỤP ẢNH (CROP ĐÚNG VÙNG NHÀ)
//     // Dùng tham số left/top/width/height của toDataURL để cắt đúng phần nhà
//     const imageData = canvas.toDataURL({
//         format: 'png',
//         multiplier: 2, // Tăng chất lượng ảnh (High Res)
//         left: cropX,
//         top: cropY,
//         width: cropWidth,
//         height: cropHeight
//     });

//     // 4. TẠO JSON MỚI (SHIFT TỌA ĐỘ THEO VÙNG CROP)
//     // Quy tắc: Tọa độ Mới = Tọa độ Canvas Gốc - Tọa độ Crop (cropX, cropY)
    
//     const roomsData = [];
//     const furnitureData = [];
//     const roomTypesCount = {};
//     let roomIdCounter = 0;

//     allObjects.forEach((obj) => {
//         // --- XỬ LÝ ROOM ---
//         if (obj.isRoom || (obj.type === 'polygon' && obj.roomName)) {
//             // Lấy ma trận biến đổi hiện tại (kéo giãn, di chuyển...)
//             const matrix = obj.calcTransformMatrix();
//             const points = obj.points;

//             // Chuyển đổi điểm Local -> Global -> Shift theo Crop
//             const snapped_corners = points.map(p => {
//                 const t = fabric.util.transformPoint(p, matrix);
//                 return [Math.round(t.x - cropX), Math.round(t.y - cropY)];
//             });

//             // Tái tạo Edges từ corners mới
//             const edges = [];
//             for (let i = 0; i < snapped_corners.length; i++) {
//                 const p1 = snapped_corners[i];
//                 const p2 = snapped_corners[(i + 1) % snapped_corners.length];
//                 edges.push([p1[0], p1[1], p2[0], p2[1]]);
//             }

//             // Tính Bounding Box mới (Relative to Image)
//             const xs = snapped_corners.map(p => p[0]);
//             const ys = snapped_corners.map(p => p[1]);
//             const bMinX = Math.min(...xs);
//             const bMinY = Math.min(...ys);
//             const bW = Math.max(...xs) - bMinX;
//             const bH = Math.max(...ys) - bMinY;

//             // Tính Center mới
//             const centerX = Math.round(bMinX + bW / 2);
//             const centerY = Math.round(bMinY + bH / 2);

//             // Xử lý Color
//             let colorArr = [255, 255, 255];
//             if (obj.fill && typeof obj.fill === 'string') {
//                 const match = obj.fill.match(/\d+/g);
//                 if (match && match.length >= 3) colorArr = [parseInt(match[0]), parseInt(match[1]), parseInt(match[2])];
//             }

//             // Room Type
//             const rName = obj.roomName || "Room";
//             const rType = rName.split('_')[0].split(' ')[0];
//             roomTypesCount[rType] = (roomTypesCount[rType] || 0) + 1;

//             roomsData.push({
//                 "id": obj.id !== undefined ? obj.id : roomIdCounter++,
//                 "name": rName,
//                 "original_name": obj.originalName || rName,
//                 "color": colorArr,
//                 "center": [centerX, centerY],
//                 "snapped_corners": snapped_corners,
//                 "edges": edges, 
//                 "bounding_box": [Math.round(bMinX), Math.round(bMinY), Math.round(bW), Math.round(bH)],
//                 "area": Math.round(bW * bH),
//                 "exterior_facing": obj.exterior_facing || [],
//                 "num_edges": snapped_corners.length,
//                 "area_m2": obj.areaM2 || 0
//             });
//         }
//         // --- XỬ LÝ FURNITURE ---
//         else if (obj.isFurniture) {
//             // Tính toán kích thước hiển thị thực tế
//             const realW = obj.width * obj.scaleX;
//             const realH = obj.height * obj.scaleY;

//             // Tính Top-Left thực tế trên Canvas rồi trừ đi Crop Offset
//             // Lưu ý: Trong createFurnitureObject ta dùng originX='center', originY='center'
//             // Công thức: X_TopLeft = (obj.left - width/2)
            
//             const rawLeft = obj.left - (realW / 2);
//             const rawTop = obj.top - (realH / 2);

//             const finalX = Math.round(rawLeft - cropX);
//             const finalY = Math.round(rawTop - cropY);

//             // Góc xoay
//             let angle = Math.round(obj.angle) % 360;
//             if (angle === -0) angle = 0;

//             furnitureData.push({
//                 "type": obj.furnType || "unknown",
//                 "x": finalX,
//                 "y": finalY,
//                 "width": Math.round(realW),
//                 "height": Math.round(realH),
//                 "angle": angle
//             });
//         }
//     });

//     const exportPayload = {
//         "total_rooms": roomsData.length,
//         "room_types": roomTypesCount,
//         "rooms": roomsData,
//         "furniture": furnitureData
//     };

//     console.log("📤 Exporting Synced Data:", exportPayload);

//     // 5. GỬI LÊN SERVER
//     const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

//     fetch('/api/save-interactive-layout/', {
//         method: 'POST',
//         headers: {
//             'Content-Type': 'application/json',
//             'X-CSRFToken': csrftoken
//         },
//         body: JSON.stringify({
//             "json_data": exportPayload,
//             "image_base64": imageData
//         })
//     })
//     .then(res => res.json())
//     .then(data => {
//         if (data.success) {
//             alert("✅ Saved Successfully! (Image & JSON Synced)");
//             // Refresh ảnh preview
//             const staticImg = document.getElementById('imgProposal1');
//             if (staticImg) staticImg.src = staticImg.src.split('?')[0] + '?t=' + Date.now();
//         } else {
//             alert("❌ Server Error: " + data.message);
//         }
//     })
//     .catch(err => {
//         console.error(err);
//         alert("❌ Network Error");
//     })
//     .finally(() => {
//         if (loader) loader.hidden = true;
//     });
// };

function exportResult() {
    canvas.discardActiveObject();
    canvas.renderAll();
    const dataURL = canvas.toDataURL({ format: 'png', multiplier: 2 });
    const link = document.createElement('a');
    link.download = 'floorplan_export.png';
    link.href = dataURL;
    link.click();
};

function deleteSelected() {
    const activeObjects = canvas.getActiveObjects();
    if (activeObjects.length) {
        canvas.discardActiveObject();
        activeObjects.forEach(function (obj) {
            if (obj.relatedText) canvas.remove(obj.relatedText);
            canvas.remove(obj);
        });
        canvas.requestRenderAll();
    }
};

function changeColor(color) {
    const activeObj = canvas.getActiveObject();
    // Nếu chọn vào Group (Room + Text)
    if (activeObj) {
        let poly = activeObj.poly;
        if (!poly && activeObj.type === 'polygon') poly = activeObj; // Nếu chọn trực tiếp polygon

        if (poly) {
            poly.set('fill', color);
            // Cập nhật lại màu cho mảng gốc nếu cần
            canvas.requestRenderAll();
        }
    }
};

// --- HELPER FUNCTIONS ---
function calculateRawArea(corners) {
    if (!corners) return 0;
    let area = 0;
    for (let i = 0; i < corners.length; i++) {
        let j = (i + 1) % corners.length;
        area += corners[i][0] * corners[j][1];
        area -= corners[j][0] * corners[i][1];
    }
    return Math.abs(area) / 2;
}

function calculatePolygonAreaVal(points) {
    let area = 0;
    for (let i = 0; i < points.length; i++) {
        let j = (i + 1) % points.length;
        area += points[i].x * points[j].y;
        area -= points[j].x * points[i].y;
    }
    return parseFloat((Math.abs(area) / 2 / (scaleRatio * scaleRatio)).toFixed(2));
}

function calculateScale(rooms, totalExpectedM2) {
    let totalPx = 0;
    rooms.forEach(r => { totalPx += calculateRawArea(r.snapped_corners); });
    if (totalPx > 0 && totalExpectedM2 > 0) {
        scaleRatio = Math.sqrt(totalPx / totalExpectedM2);
    } else {
        scaleRatio = 100;
    }
}

function createRoomObject(roomData) {
    if (!roomData.snapped_corners) return;
    const points = roomData.snapped_corners.map(p => ({ x: p[0], y: p[1] }));

    const poly = new fabric.Polygon(points, {
        fill: roomData.color ? `rgb(${roomData.color[0]},${roomData.color[1]},${roomData.color[2]})` : THEME.wallFillDefault,
        stroke: THEME.wallStroke,
        strokeWidth: THEME.strokeWidth,
        objectCaching: false,
        cornerColor: THEME.selected,
        hasControls: true,
        selectable: true,
        roomName: roomData.name,
        originalName: roomData.original_name, // Lưu lại tên gốc
        isRoom: true,
        exterior_facing: roomData.exterior_facing || [] // Lưu lại thuộc tính này
    });

    const areaVal = roomData.area_m2 || calculatePolygonAreaVal(points);
    poly.areaM2 = areaVal;

    // Center point
    let cX = 0, cY = 0;
    if (roomData.center) { cX = roomData.center[0]; cY = roomData.center[1]; }
    else { const c = poly.getCenterPoint(); cX = c.x; cY = c.y; }

    const text = new fabric.Text(`${roomData.name}\n${areaVal}m²`, {
        fontSize: 11, fontFamily: THEME.font, fontWeight: 'bold', fill: THEME.text,
        left: cX, top: cY, originX: 'center', originY: 'center',
        textAlign: 'center', selectable: false, evented: false, isRoomLabel: true
    });

    poly.relatedText = text;
    canvas.add(poly);
    canvas.add(text);

    // Sync Text
    const syncText = () => {
        const c = poly.getCenterPoint();
        const m = poly.calcTransformMatrix();
        const pts = poly.points.map(p => fabric.util.transformPoint(p, m));
        const newArea = calculatePolygonAreaVal(pts);
        poly.areaM2 = newArea;
        text.set({ left: c.x, top: c.y, text: `${roomData.name}\n${newArea}m²` });
    };

    poly.on('moving', syncText);
    poly.on('scaling', syncText);
    poly.on('modified', syncText);
}

function createFurnitureObject(item) {
    return new Promise((resolve) => {
        let iconPath = item.src;
        // Fix đường dẫn nếu bị null hoặc lỗi
        if (!iconPath || iconPath.includes('None') || !iconPath.startsWith('http')) {
            iconPath = `/static/floorplan_app/icons/${item.type}.png`;
        }

        fabric.Image.fromURL(iconPath, (img) => {
            if (!img) { resolve(); return; }

            // Xử lý góc xoay (đảo ngược lại lúc lưu)
            const angle = item.angle ? -item.angle : 0;

            img.set({
                left: item.x + item.width / 2, // Chuyển từ Top-Left sang Center
                top: item.y + item.height / 2,
                angle: angle,
                scaleX: item.width / img.width,
                scaleY: item.height / img.height,
                originX: 'center', originY: 'center',
                selectable: true, hasControls: true,
                isFurniture: true, furnType: item.type
            });

            canvas.add(img);
            resolve(img);
        }, { crossOrigin: 'anonymous' });
    });
}

function forceLayerOrder() {
    canvas._objects.sort((a, b) => getZIndex(a) - getZIndex(b));
    canvas.renderAll();
}

function getZIndex(obj) {
    if (obj.isDimension) return 5;
    if (obj.isRoomLabel) return 4;
    if (obj.isFurniture) return 3;
    if (['door', 'entrance', 'window'].includes(obj.furnType)) return 2;
    if (obj.isRoom) return 1;
    return 0;
}

// ... (Giữ nguyên các hàm zoomToContent, addTechnicalDimensions, getHouseBounds, v.v. ở cuối file) ...
// Bạn hãy copy nốt các hàm đó vào đây (nếu chưa có thì bảo tôi gửi nốt)

// ... (Giữ các hàm Dimensions, Zoom, Utils còn lại ở cuối file) ...
// (Hãy đảm bảo copy nốt các hàm addTechnicalDimensions, getHouseBounds... từ bản trước vào đây)
function createRoomObject(roomData) {
    if (!roomData.snapped_corners) return;
    const points = roomData.snapped_corners.map(p => ({ x: p[0], y: p[1] }));

    const poly = new fabric.Polygon(points, {
        fill: roomData.color ? `rgb(${roomData.color[0]},${roomData.color[1]},${roomData.color[2]})` : THEME.wallFillDefault,
        stroke: THEME.wallStroke,
        strokeWidth: THEME.strokeWidth,
        objectCaching: false,
        transparentCorners: false,
        cornerColor: THEME.selected,
        hasControls: true,
        selectable: true,
        roomName: roomData.name,
        isRoom: true
    });

    const center = poly.getCenterPoint();
    const areaVal = calculatePolygonAreaVal(points);
    poly.areaM2 = areaVal;

    const text = new fabric.Text(`${roomData.name}\n${areaVal}m²`, {
        fontSize: 11,
        fontFamily: THEME.font,
        fontWeight: 'bold',
        fill: THEME.text,
        left: center.x,
        top: center.y,
        originX: 'center',
        originY: 'center',
        textAlign: 'center',
        selectable: false,
        evented: false,
        isRoomLabel: true
    });

    poly.relatedText = text;
    canvas.add(poly);
    canvas.add(text);

    function syncText() {
        const center = poly.getCenterPoint();
        const m = poly.calcTransformMatrix();
        const pts = poly.points.map(p => fabric.util.transformPoint(p, m));
        const newArea = calculatePolygonAreaVal(pts);
        poly.areaM2 = newArea;

        text.set({
            left: center.x,
            top: center.y,
            text: `${roomData.name}\n${newArea}m²`
        });
        text.setCoords();
    }

    poly.on('moving', syncText);
    poly.on('scaling', syncText);
    poly.on('modified', syncText);
}

function createFurnitureObject(item) {
    return new Promise((resolve) => {
        let iconPath = item.src;
        if (!iconPath || iconPath.includes('None')) {
            iconPath = `/static/floorplan_app/icons/${item.type}.png`;
        }

        fabric.Image.fromURL(iconPath, (img) => {
            if (!img) { resolve(); return; }

            const centerX = item.x + item.width / 2;
            const centerY = item.y + item.height / 2;
            let targetW = item.width;
            let targetH = item.height;
            const angle = item.angle || 0;

            const isRotated90 = (Math.abs(angle) % 180 !== 0);
            if (isRotated90) {
                [targetW, targetH] = [targetH, targetW];
            }

            const scaleX = targetW / img.width;
            const scaleY = targetH / img.height;
            const finalAngle = -angle;

            img.set({
                left: centerX,
                top: centerY,
                angle: finalAngle,
                scaleX: scaleX,
                scaleY: scaleY,
                originX: 'center',
                originY: 'center',
                selectable: true,
                hasControls: true,
                borderColor: THEME.selected,
                cornerColor: THEME.selected,
                isFurniture: true,
                furnType: item.type
            });

            if (['door', 'entrance', 'window'].includes(item.type)) {
                img.set({ lockScalingFlip: true });
            }

            canvas.add(img);
            resolve(img);
        }, { crossOrigin: 'anonymous' });
    });
}

// --- UTILS ---
function calculateRawArea(corners) {
    if (!corners) return 0;
    let area = 0;
    for (let i = 0; i < corners.length; i++) {
        let j = (i + 1) % corners.length;
        area += corners[i][0] * corners[j][1];
        area -= corners[j][0] * corners[i][1];
    }
    return Math.abs(area) / 2;
}

function calculatePolygonAreaVal(points) {
    let area = 0;
    for (let i = 0; i < points.length; i++) {
        let j = (i + 1) % points.length;
        area += points[i].x * points[j].y;
        area -= points[j].x * points[i].y;
    }
    return parseFloat((Math.abs(area) / 2 / (scaleRatio * scaleRatio)).toFixed(2));
}

function calculateScale(rooms, totalExpectedM2) {
    let totalPx = 0;
    rooms.forEach(r => {
        const areaRaw = calculateRawArea(r.snapped_corners);
        if (areaRaw < 500000) {
            totalPx += areaRaw;
        }
    });
    if (totalPx === 0) totalPx = calculateRawArea(rooms[0].snapped_corners);

    if (totalPx > 0 && totalExpectedM2 > 0) {
        scaleRatio = Math.sqrt(totalPx / totalExpectedM2);
    } else {
        scaleRatio = 100;
    }
}

// File: interactive_editor.js

window.saveInteractiveData = function () {
    // 1. Hiển thị Loading
    const loader = document.getElementById('loadingOverlay');
    if (loader) {
        loader.hidden = false;
        const msg = loader.querySelector('.loading-message');
        if (msg) msg.innerText = "Saving design...";
    }

    if (typeof vectorCanvas === 'undefined' || !vectorCanvas) {
        alert("Lỗi: Canvas chưa khởi tạo!");
        return;
    }

    // 2. Chuẩn bị dữ liệu
    vectorCanvas.discardActiveObject();
    vectorCanvas.requestRenderAll();
    const imageData = vectorCanvas.toDataURL({ format: 'png', multiplier: 2 });
    
    // Payload giả để server không lỗi
    const exportPayload = { "total_rooms": 0, "room_types": {}, "rooms": [], "furniture": [] };
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    // 3. Gửi lên Server
    fetch('/api/save-interactive-layout/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({
            "json_data": exportPayload,
            "image_base64": imageData,
            "save_mode": "image_only"
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert("✅ Đã lưu floorplan1.png thành công!");

            // --- LOGIC QUAN TRỌNG: ĐỔI ẢNH VÀ CHUYỂN TAB ---
            
            const staticImg = document.getElementById('imgProposal1');
            const fabricWrapper = document.querySelector('.canvas-container'); // Class do Fabric tạo
            const tabInteractive = document.getElementById('tabInteractive');
            const tabStatic = document.getElementById('tabStatic');

            // B1: Đổi đường dẫn ảnh sang floorplan1.png (Thêm time để xóa cache)
            if (staticImg) {
                staticImg.src = "/static/floorplan_app/img/floorplan1.png?t=" + new Date().getTime();
                staticImg.style.display = 'block'; // Bắt buộc hiện ảnh
                
                // Đánh dấu vào ảnh là đã chuyển sang floorplan1 để hàm switchViewMode biết
                staticImg.dataset.activeImage = "floorplan1"; 
            }

            // B2: Ẩn Canvas
            if (fabricWrapper) {
                fabricWrapper.style.display = 'none';
            }

            // B3: Cập nhật màu nút bấm (Highlight tab Floorplan 1)
            if (tabInteractive) {
                tabInteractive.className = "px-4 py-2 text-xs font-bold rounded-lg transition-all text-slate-500 hover:bg-white/50";
            }
            if (tabStatic) {
                tabStatic.className = "px-4 py-2 text-xs font-bold rounded-lg transition-all shadow-sm bg-white text-blue-600";
            }

        } else {
            alert("❌ Lỗi Server: " + data.message);
        }
    })
    .catch(err => {
        console.error(err);
        alert("❌ Lỗi kết nối mạng.");
    })
    .finally(() => {
        if (loader) loader.hidden = true;
    });
};

// window.saveInteractiveData = function () {
//     const loader = document.getElementById('loadingOverlay');
//     if (loader) {
//         loader.hidden = false;
//         const msg = loader.querySelector('.loading-message');
//         if (msg) msg.innerText = "Saving design...";
//     }

//     // --- 1. CHỤP ẢNH (WYSIWYG - Cái gì thấy là lưu) ---
//     // Quan trọng: Bỏ chọn vật thể để ảnh không bị dính khung xanh
//     // Dùng vectorCanvas (biến toàn cục bạn đã khai báo) thay vì canvas chung chung
//     if (typeof vectorCanvas === 'undefined') {
//         alert("Lỗi: Canvas chưa khởi tạo!");
//         return;
//     }

//     vectorCanvas.discardActiveObject();
//     vectorCanvas.requestRenderAll(); // Render lại để đảm bảo sạch sẽ

//     // Multiplier giúp ảnh nét hơn
//     const imageData = vectorCanvas.toDataURL({ format: 'png', multiplier: 2 });

//     // --- 2. THU THẬP DỮ LIỆU JSON (BẢO TOÀN DỮ LIỆU) ---
//     // const roomsData = [];
//     // const furnitureData = [];
//     // const objects = vectorCanvas.getObjects();
//     // const roomTypesCount = {};

//     // objects.forEach((obj, index) => {
//     //     // XỬ LÝ ROOM (Là Group hoặc Polygon)
//     //     if (obj.roomName) {
//     //         // Lấy Polygon gốc bên trong Group (nếu là Group) hoặc chính nó
//     //         const poly = obj.poly || (obj.type === 'polygon' ? obj : null) || (obj._objects ? obj._objects.find(o => o.type === 'polygon') : null);

//     //         if (poly && poly.points) {
//     //             // Tính toán tọa độ thực tế trên Canvas
//     //             const matrix = obj.calcTransformMatrix();
//     //             const pts = poly.points.map(p => {
//     //                 const t = fabric.util.transformPoint(p, matrix);
//     //                 return [Math.round(t.x), Math.round(t.y)];
//     //             });

//     //             // Tính bounding box thực tế
//     //             const bound = obj.getBoundingRect();

//     //             // Đếm loại phòng
//     //             const rType = obj.roomName.split('_')[0].split(' ')[0];
//     //             roomTypesCount[rType] = (roomTypesCount[rType] || 0) + 1;

//     //             roomsData.push({
//     //                 "id": index,
//     //                 "name": obj.roomName,
//     //                 "original_name": obj.roomName, // Giữ nguyên tên gốc
//     //                 // Lấy màu từ fill của Polygon, fallback về màu mặc định nếu lỗi
//     //                 "color": poly.fill && poly.fill.includes('rgb') ?
//     //                     poly.fill.replace(/[^\d,]/g, '').split(',').map(Number) : [253, 253, 240],
//     //                 "center": [Math.round(bound.left + bound.width / 2), Math.round(bound.top + bound.height / 2)],
//     //                 "snapped_corners": pts,
//     //                 "edges": pts.map((p, i) => { // Tái tạo edges
//     //                     const nextP = pts[(i + 1) % pts.length];
//     //                     return [p[0], p[1], nextP[0], nextP[1]];
//     //                 }),
//     //                 "bounding_box": [Math.round(bound.left), Math.round(bound.top), Math.round(bound.width), Math.round(bound.height)],
//     //                 "area": Math.round(bound.width * bound.height),
//     //                 "exterior_facing": obj.exterior_facing || [], // Bảo lưu thuộc tính này nếu có gán vào object
//     //                 "num_edges": pts.length,
//     //                 "area_m2": obj.areaM2 || 0 // Lấy diện tích M2 đã tính toán trên giao diện
//     //             });
//     //         }
//     //     }
//     //     // XỬ LÝ FURNITURE (Là Image)
//     //     else if (obj.isFurniture || obj.furnType) {
//     //         const bound = obj.getBoundingRect();
//     //         furnitureData.push({
//     //             "type": obj.furnType || "unknown",
//     //             "x": Math.round(bound.left),
//     //             "y": Math.round(bound.top),
//     //             "width": Math.round(bound.width),
//     //             "height": Math.round(bound.height),
//     //             "angle": Math.round(-obj.angle) // Đảo góc cho khớp hệ tọa độ
//     //         });
//     //     }
//     // });

//     // const exportPayload = {
//     //     "total_rooms": roomsData.length,
//     //     "room_types": roomTypesCount,
//     //     "rooms": roomsData,
//     //     "furniture": furnitureData // Đảm bảo mảng này không rỗng
//     // };

//     // // --- 3. GỬI LÊN SERVER ---
//     // const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

//     // fetch('/api/save-interactive-layout/', {
//     //     method: 'POST',
//     //     headers: {
//     //         'Content-Type': 'application/json',
//     //         'X-CSRFToken': csrftoken
//     //     },
//     //     body: JSON.stringify({
//     //         "json_data": exportPayload,
//     //         "image_base64": imageData
//     //     })
//     // })
//     //     .then(res => res.json())
//     //     .then(data => {
//     //         if (data.success) {
//     //             alert("✅ Đã lưu thành công! (Ảnh & Dữ liệu)");
//     //             // Cập nhật ngay lập tức ảnh preview
//     //             const staticImg = document.getElementById('imgProposal1');
//     //             if (staticImg) staticImg.src = staticImg.src.split('?')[0] + '?t=' + Date.now();
//     //         } else {
//     //             alert("❌ Lỗi Server: " + data.message);
//     //         }
//     //     })
//     //     .catch(err => {
//     //         console.error(err);
//     //         alert("❌ Lỗi mạng hoặc dữ liệu.");
//     //     })
//     //     .finally(() => {
//     //         if (loader) loader.hidden = true;
//     //     });
// };


window.exportResult = function () {
    canvas.discardActiveObject();
    canvas.renderAll();
    const dataURL = canvas.toDataURL({ format: 'png', multiplier: 2 });
    const link = document.createElement('a');
    link.download = 'floorplan_export.png';
    link.href = dataURL;
    link.click();
};

function setupEventHandlers() {
    // 1. Tự động tìm nút Save theo các ID phổ biến
    const saveBtnIds = ['saveBtn', 'btnSave', 'save-data-btn', 'saveButton'];
    let saveBtn = null;
    
    for (const id of saveBtnIds) {
        saveBtn = document.getElementById(id);
        if (saveBtn) break;
    }

    // Nếu tìm thấy nút, gắn sự kiện click
    if (saveBtn) {
        console.log("✅ Save Button Found:", saveBtn.id);
        // Xóa sự kiện cũ để tránh bị double click
        saveBtn.replaceWith(saveBtn.cloneNode(true));
        saveBtn = document.getElementById(saveBtn.id); // Lấy lại element mới
        saveBtn.addEventListener('click', window.saveInteractiveData);
    } else {
        console.warn("⚠️ Warning: Save button not found via ID. Make sure your HTML button has onclick='saveInteractiveData()' or id='saveBtn'.");
    }

    // 2. Phím tắt xóa
    window.addEventListener('keydown', e => {
        if (e.key === 'Delete' || e.key === 'Backspace') {
            const active = canvas.getActiveObjects();
            if (active.length) {
                canvas.discardActiveObject();
                active.forEach(o => {
                    if (o.relatedText) canvas.remove(o.relatedText);
                    canvas.remove(o);
                });
                canvas.requestRenderAll();
            }
        }
    });
}

// ============================================================
//  ADVANCED DIMENSION LOGIC (RAYCAST SCAN V2)
//  Feature: Detects ALL exterior edges (including short/recessed walls)
// ============================================================

function addTechnicalDimensions(rooms) {
    console.log("📏 Adding Advanced Dimensions...");

    // 1. Get House Bounds
    const bounds = getHouseBounds(rooms);
    if (!bounds) return;

    const { minX, minY, maxX, maxY } = bounds;

    // Offsets
    const OFFSET_L1 = 40;
    const OFFSET_L2 = 80;

    const processSide = (side) => {
        // Find ALL exterior segments
        const segments = getExteriorSegmentsByScan(side, rooms);

        const isVertical = (side === 'left' || side === 'right');

        // Determine draw position
        let drawPos, offsetDir;
        if (side === 'top') { drawPos = minY - OFFSET_L1; offsetDir = -1; }
        if (side === 'bottom') { drawPos = maxY + OFFSET_L1; offsetDir = 1; }
        if (side === 'left') { drawPos = minX - OFFSET_L1; offsetDir = -1; }
        if (side === 'right') { drawPos = maxX + OFFSET_L1; offsetDir = 1; }

        // --- LAYER 1: DETAILED SEGMENTS (ALL EDGES) ---
        segments.forEach(seg => {
            let p1, p2;
            if (!isVertical) {
                p1 = { x: seg.start, y: drawPos };
                p2 = { x: seg.end, y: drawPos };
                drawExtensionLine(seg.start, seg.realLevel, drawPos, false);
                drawExtensionLine(seg.end, seg.realLevel, drawPos, false);
            } else {
                p1 = { x: drawPos, y: seg.start };
                p2 = { x: drawPos, y: seg.end };
                drawExtensionLine(drawPos, seg.start, seg.realLevel, true);
                drawExtensionLine(drawPos, seg.end, seg.realLevel, true);
            }

            drawDimensionLine(p1, p2, isVertical, seg.val);
        });

        // --- LAYER 2: TOTAL LENGTH ---
        let tp1, tp2;
        const totalPos = drawPos + (offsetDir * (OFFSET_L2 - OFFSET_L1));
        const totalLen = isVertical ? (maxY - minY) : (maxX - minX);

        if (side === 'top') { tp1 = { x: minX, y: totalPos }; tp2 = { x: maxX, y: totalPos }; }
        if (side === 'bottom') { tp1 = { x: minX, y: totalPos }; tp2 = { x: maxX, y: totalPos }; }
        if (side === 'left') { tp1 = { x: totalPos, y: minY }; tp2 = { x: totalPos, y: maxY }; }
        if (side === 'right') { tp1 = { x: totalPos, y: minY }; tp2 = { x: totalPos, y: maxY }; }

        if (segments.length > 1 || Math.abs(segments[0].val - totalLen) > 10) {
            drawDimensionLine(tp1, tp2, isVertical, totalLen, true);
        }
    };

    processSide('top');
    processSide('bottom');
    processSide('left');
    processSide('right');
}

/**
 * Scan all edges to find which are exterior
 */
function getExteriorSegmentsByScan(side, rooms) {
    let segments = [];
    const checkDist = 5;

    rooms.forEach(room => {
        const pts = room.points.map(p => fabric.util.transformPoint(p, room.calcTransformMatrix()));

        for (let i = 0; i < pts.length; i++) {
            const p1 = pts[i];
            const p2 = pts[(i + 1) % pts.length];

            const isHor = Math.abs(p1.y - p2.y) < 5;
            const isVer = Math.abs(p1.x - p2.x) < 5;

            const midX = (p1.x + p2.x) / 2;
            const midY = (p1.y + p2.y) / 2;
            let checkPt = null;
            let isValidEdge = false;

            if (side === 'top' && isHor) {
                if (midY < room.getCenterPoint().y) {
                    checkPt = { x: midX, y: midY - checkDist };
                    isValidEdge = true;
                }
            }
            else if (side === 'bottom' && isHor) {
                if (midY > room.getCenterPoint().y) {
                    checkPt = { x: midX, y: midY + checkDist };
                    isValidEdge = true;
                }
            }
            else if (side === 'left' && isVer) {
                if (midX < room.getCenterPoint().x) {
                    checkPt = { x: midX - checkDist, y: midY };
                    isValidEdge = true;
                }
            }
            else if (side === 'right' && isVer) {
                if (midX > room.getCenterPoint().x) {
                    checkPt = { x: midX + checkDist, y: midY };
                    isValidEdge = true;
                }
            }

            if (isValidEdge && checkPt) {
                const isInternal = rooms.some(r => {
                    if (r === room) return false;
                    return isPointInPoly(checkPt, r);
                });

                if (!isInternal) {
                    let val = Math.hypot(p2.x - p1.x, p2.y - p1.y);
                    let start = isHor ? Math.min(p1.x, p2.x) : Math.min(p1.y, p2.y);
                    let end = isHor ? Math.max(p1.x, p2.x) : Math.max(p1.y, p2.y);

                    segments.push({
                        start: Math.round(start),
                        end: Math.round(end),
                        val: val,
                        realLevel: isHor ? midY : midX
                    });
                }
            }
        }
    });

    segments.sort((a, b) => a.start - b.start);

    // Merge Check
    const merged = [];
    if (segments.length > 0) {
        let curr = segments[0];
        for (let i = 1; i < segments.length; i++) {
            let next = segments[i];
            if (next.start < curr.end + 5) {
                curr.end = Math.max(curr.end, next.end);
                curr.val = curr.end - curr.start;
            } else {
                merged.push(curr);
                curr = next;
            }
        }
        merged.push(curr);
    }

    return merged;
}

function isPointInPoly(pt, polyObj) {
    if (polyObj.containsPoint) {
        return polyObj.containsPoint(new fabric.Point(pt.x, pt.y));
    }
    return false;
}

function getHouseBounds(rooms) {
    if (!rooms || rooms.length === 0) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    rooms.forEach(r => {
        const coords = r.aCoords;
        if (!coords) return;
        ['tl', 'tr', 'br', 'bl'].forEach(corner => {
            if (coords[corner].x < minX) minX = coords[corner].x;
            if (coords[corner].y < minY) minY = coords[corner].y;
            if (coords[corner].x > maxX) maxX = coords[corner].x;
            if (coords[corner].y > maxY) maxY = coords[corner].y;
        });
    });
    return (minX === Infinity) ? null : { minX, minY, maxX, maxY };
}

function drawExtensionLine(x1, y1, x2, isVertical) {
    let coords = isVertical ? [x1, y1, x2, y1] : [x1, y1, x1, x2];

    const line = new fabric.Line(coords, {
        stroke: THEME.dimGuideColor,
        strokeWidth: 1,
        strokeDashArray: [4, 4],
        selectable: false,
        evented: false,
        opacity: 0.6
    });
    line.isDimension = true;
    canvas.add(line);
    line.sendToBack();
}

function drawDimensionLine(p1, p2, isVertical, pixelLength, isTotal = false) {
    if (pixelLength < 10) return;

    // Main Line
    const mainLine = new fabric.Line([p1.x, p1.y, p2.x, p2.y], {
        stroke: THEME.dimColor,
        strokeWidth: 1,
        selectable: false,
        evented: false
    });

    // Ticks
    const tickLen = 4;
    const makeTick = (pt) => {
        return new fabric.Line([pt.x - tickLen, pt.y - tickLen, pt.x + tickLen, pt.y + tickLen], {
            stroke: THEME.dimColor,
            strokeWidth: 2,
            selectable: false,
            evented: false
        });
    };
    const tick1 = makeTick(p1);
    const tick2 = makeTick(p2);

    // Text
    const meterVal = (pixelLength / scaleRatio).toFixed(2) + "m";
    const midX = (p1.x + p2.x) / 2;
    const midY = (p1.y + p2.y) / 2;

    let textOffX = 0, textOffY = 0;
    if (isVertical) textOffX = isTotal ? -15 : -10;
    else textOffY = isTotal ? -15 : -10;

    const textObj = new fabric.Text(meterVal, {
        fontFamily: THEME.dimFont,
        fontSize: isTotal ? 13 : 11,
        fontWeight: isTotal ? 'bold' : 'normal',
        fill: THEME.dimColor,
        left: midX + textOffX,
        top: midY + textOffY,
        originX: 'center',
        originY: 'center',
        angle: isVertical ? -90 : 0,
        backgroundColor: '#ffffff',
        selectable: false,
        evented: false
    });

    [mainLine, tick1, tick2, textObj].forEach(o => {
        o.isDimension = true;
        canvas.add(o);
        o.sendToBack();
    });
}

// ============================================================
//  ZOOM TO CONTENT (CĂN GIỮA & PHÓNG TO)
// ============================================================
function zoomToContent() {
    if (!canvas) return;
    const objects = canvas.getObjects();
    if (!objects || objects.length === 0) return;

    // 1. Tìm biên (Bounding Box) của toàn bộ nội dung
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    objects.forEach(obj => {
        if (obj.isDimension) return; // Bỏ qua đường kích thước khi tính toán zoom
        const bound = obj.getBoundingRect();
        if (bound.left < minX) minX = bound.left;
        if (bound.top < minY) minY = bound.top;
        if (bound.left + bound.width > maxX) maxX = bound.left + bound.width;
        if (bound.top + bound.height > maxY) maxY = bound.top + bound.height;
    });

    if (minX === Infinity) return;

    // 2. Tính toán vùng hiển thị
    const padding = 50; // Khoảng cách đệm
    const contentWidth = maxX - minX;
    const contentHeight = maxY - minY;

    // Kích thước canvas hiện tại
    const availWidth = canvas.width - (padding * 2);
    const availHeight = canvas.height - (padding * 2);

    // Tính tỷ lệ zoom
    const scaleX = availWidth / contentWidth;
    const scaleY = availHeight / contentHeight;
    let zoomLevel = Math.min(scaleX, scaleY);

    // Giới hạn zoom
    if (zoomLevel > 5) zoomLevel = 5; 
    
    // 3. Tính toán vị trí Pan để đưa vào giữa
    const contentCenterX = minX + contentWidth / 2;
    const contentCenterY = minY + contentHeight / 2;
    
    const canvasCenterX = canvas.width / 2;
    const canvasCenterY = canvas.height / 2;

    const panX = canvasCenterX - (contentCenterX * zoomLevel);
    const panY = canvasCenterY - (contentCenterY * zoomLevel);

    // 4. Áp dụng
    canvas.setViewportTransform([zoomLevel, 0, 0, zoomLevel, panX, panY]);
    canvas.requestRenderAll();
}