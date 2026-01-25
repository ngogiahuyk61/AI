/**
 * Biến toàn cục lưu instance của biểu đồ
 */
let validityChartInstance = null;

/**
 * Hàm chính được gọi từ dashboard.html
 */
async function renderValidityCharts() {
    const BASE_URL = '/static/floorplan_app/module_Survey/'; 

    console.log("Validity: Bắt đầu quét file JSON từ:", BASE_URL);

    // 1. Tải tất cả file JSON (1.json -> n.json)
    const allJsonFiles = await fetchAllJsonFiles(BASE_URL);

    // 2. Tính toán số liệu dựa trên key: request_status, Consistency, validation
    const calculatedStats = calculateStatsFromFiles(allJsonFiles);

    // 3. Cập nhật giao diện (List, Card, Legend) và vẽ biểu đồ tròn
    updateValidityUI(calculatedStats);
}

/**
 * Hàm tải tuần tự các file JSON cho đến khi gặp lỗi 404
 */
async function fetchAllJsonFiles(baseUrl) {
    let files = [];
    let index = 1;
    let keepFetching = true;

    // UI Feedback: Đang tải...
    const totalEl = document.getElementById('val-total-request');
    if(totalEl) totalEl.innerText = "...";

    while (keepFetching) {
        const fileName = `${index}.json`;
        const url = `${baseUrl}${fileName}`;

        try {
            const response = await fetch(url);
            
            if (response.ok) {
                const data = await response.json();
                files.push(data);
                index++; 
            } else {
                // Hết file -> Dừng
                keepFetching = false;
            }
        } catch (error) {
            console.error(`Lỗi đọc file ${fileName}:`, error);
            keepFetching = false;
        }

        // Safety break
        if (index > 5000) keepFetching = false;
    }

    console.log(`Validity: Đã tải xong ${files.length} file.`);
    return files;
}

/**
 * LOGIC TÍNH TOÁN (CORE LOGIC)
 */
function calculateStatsFromFiles(files) {
    let stats = {
        totalRequest: files.length,
        reqTrue: 0, reqFalse: 0,
        consTrue: 0, consFalse: 0,
        validTrue: 0, validFalse: 0,
        qualifiedCount: 0 
    };

    files.forEach(file => {
        // 1. Percentage Required (request_status)
        if (file.request_status === true) {
            stats.reqTrue++;
        } else {
            stats.reqFalse++;
        }

        // 2. Percentage Consistency (Consistency)
        if (file.Consistency === true) {
            stats.consTrue++;
        } else {
            stats.consFalse++;
        }

        // 3. Percentage Validation (validation)
        if (file.validation === true) {
            stats.validTrue++;
        } else {
            stats.validFalse++;
        }

        // 4. Logic Qualified: Cả 3 phải True
        if (file.request_status === true && file.Consistency === true && file.validation === true) {
            stats.qualifiedCount++;
        }
    });

    // Tính phần trăm
    const qualifiedPercent = stats.totalRequest > 0 
        ? ((stats.qualifiedCount / stats.totalRequest) * 100).toFixed(1)
        : 0;
    
    // Làm tròn số để hiển thị đẹp
    const qualifiedPercentInt = Math.round(qualifiedPercent); 
    const unqualifiedPercentInt = 100 - qualifiedPercentInt;

    return {
        ...stats,
        qualifiedPercent: qualifiedPercentInt,
        unqualifiedPercent: unqualifiedPercentInt
    };
}

/**
 * Cập nhật DOM và Vẽ Chart
 */
function updateValidityUI(data) {
    // --- 1. Cập nhật Text số liệu ---
    
    // A. Header Cards
    const elTotalReq = document.getElementById('val-total-request');
    if (elTotalReq) elTotalReq.innerText = data.totalRequest;

    const elQualifiedCard = document.getElementById('val-qualified-percent');
    if (elQualifiedCard) elQualifiedCard.innerText = `${data.qualifiedPercent}%`; 

    // B. Cột Legend (Bên phải biểu đồ) - PHẦN MỚI UPDATE
    const elLegendQualified = document.getElementById('val-legend-qualified-percent');
    if (elLegendQualified) {
        elLegendQualified.innerText = `${data.qualifiedPercent}%`;
    }

    const elLegendUnqualified = document.getElementById('val-legend-unqualified-percent');
    if (elLegendUnqualified) {
        elLegendUnqualified.innerText = `${data.unqualifiedPercent}%`;
    }

    // C. List Details (Cột trái)
    const calcPercent = (val) => data.totalRequest > 0 ? Math.round((val / data.totalRequest) * 100) : 0;

    // Required
    updateStatLine('val-req-true', calcPercent(data.reqTrue), data.reqTrue);
    updateStatLine('val-req-false', calcPercent(data.reqFalse), data.reqFalse);
    
    // Consistency
    updateStatLine('val-cons-true', calcPercent(data.consTrue), data.consTrue);
    updateStatLine('val-cons-false', calcPercent(data.consFalse), data.consFalse);

    // Validation
    updateStatLine('val-valid', calcPercent(data.validTrue), data.validTrue);
    updateStatLine('val-invalid', calcPercent(data.validFalse), data.validFalse);


    // --- 2. Vẽ Pie Chart ---
    const canvas = document.getElementById('validityPieChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    
    const purpleColor = '#31009C'; // Qualified
    const redColor = '#F53C56';    // Unqualified

    if (validityChartInstance) {
        validityChartInstance.destroy();
    }

    validityChartInstance = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['Qualified', 'Unqualified'],
            datasets: [{
                data: [data.qualifiedPercent, data.unqualifiedPercent],
                backgroundColor: [purpleColor, redColor],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Tắt legend mặc định
                },
                datalabels: {
                    color: '#fff',
                    font: {
                        weight: 'bold',
                        size: 16
                    },
                    formatter: (value) => {
                        return value > 0 ? value + '%' : '';
                    }
                },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label: function(context) {
                            return ` ${context.label}: ${context.raw}%`;
                        }
                    }
                }
            },
            layout: {
                padding: 10
            }
        },
        plugins: [ChartDataLabels]
    });
}

// Helper function
function updateStatLine(prefix, percent, count) {
    const elPercent = document.getElementById(`${prefix}-percent`);
    const elCount = document.getElementById(`${prefix}-count`);
    
    if (elPercent) elPercent.innerText = `${percent}%`;
    if (elCount) elCount.innerText = `(${count})`;
}