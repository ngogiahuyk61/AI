let validityChartInstance = null;

async function renderValidityCharts() {
    const BASE_URL = '/static/floorplan_app/module_Survey/'; 

    console.log("Validity: Bắt đầu quét file JSON từ:", BASE_URL);

    const allJsonFiles = await fetchAllJsonFiles(BASE_URL);
    const calculatedStats = calculateStatsFromFiles(allJsonFiles);
    updateValidityUI(calculatedStats);
}

async function fetchAllJsonFiles(baseUrl) {
    let files = [];
    let index = 1;
    let keepFetching = true;

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
                keepFetching = false;
            }
        } catch (error) {
            console.error(`Lỗi đọc file ${fileName}:`, error);
            keepFetching = false;
        }

        if (index > 5000) keepFetching = false;
    }

    console.log(`Validity: Đã tải xong ${files.length} file.`);
    return files;
}

function calculateStatsFromFiles(files) {
    let stats = {
        totalRequest: files.length,
        reqTrue: 0, reqFalse: 0,
        consTrue: 0, consFalse: 0,
        validTrue: 0, validFalse: 0,
        qualifiedCount: 0 
    };

    files.forEach(file => {
        if (file.request_status === true) {
            stats.reqTrue++;
        } else {
            stats.reqFalse++;
        }

        if (file.Consistency === true) {
            stats.consTrue++;
        } else {
            stats.consFalse++;
        }

        if (file.validation === true) {
            stats.validTrue++;
        } else {
            stats.validFalse++;
        }

        if (file.request_status === true && file.Consistency === true && file.validation === true) {
            stats.qualifiedCount++;
        }
    });

    const qualifiedPercent = stats.totalRequest > 0 
        ? ((stats.qualifiedCount / stats.totalRequest) * 100).toFixed(1)
        : 0;
    
    const qualifiedPercentInt = Math.round(qualifiedPercent); 
    const unqualifiedPercentInt = 100 - qualifiedPercentInt;

    return {
        ...stats,
        qualifiedPercent: qualifiedPercentInt,
        unqualifiedPercent: unqualifiedPercentInt
    };
}

function updateValidityUI(data) {
    const elTotalReq = document.getElementById('val-total-request');
    if (elTotalReq) elTotalReq.innerText = data.totalRequest;

    const elQualifiedCard = document.getElementById('val-qualified-percent');
    if (elQualifiedCard) elQualifiedCard.innerText = `${data.qualifiedPercent}%`; 

    const elLegendQualified = document.getElementById('val-legend-qualified-percent');
    if (elLegendQualified) {
        elLegendQualified.innerText = `${data.qualifiedPercent}%`;
    }

    const elLegendUnqualified = document.getElementById('val-legend-unqualified-percent');
    if (elLegendUnqualified) {
        elLegendUnqualified.innerText = `${data.unqualifiedPercent}%`;
    }

    const calcPercent = (val) => data.totalRequest > 0 ? Math.round((val / data.totalRequest) * 100) : 0;

    updateStatLine('val-req-true', calcPercent(data.reqTrue), data.reqTrue);
    updateStatLine('val-req-false', calcPercent(data.reqFalse), data.reqFalse);
    updateStatLine('val-cons-true', calcPercent(data.consTrue), data.consTrue);
    updateStatLine('val-cons-false', calcPercent(data.consFalse), data.consFalse);
    updateStatLine('val-valid', calcPercent(data.validTrue), data.validTrue);
    updateStatLine('val-invalid', calcPercent(data.validFalse), data.validFalse);

    const canvas = document.getElementById('validityPieChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    
    const purpleColor = '#31009C';
    const redColor = '#F53C56';

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
                    display: false
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

function updateStatLine(prefix, percent, count) {
    const elPercent = document.getElementById(`${prefix}-percent`);
    const elCount = document.getElementById(`${prefix}-count`);
    
    if (elPercent) elPercent.innerText = `${percent}%`;
    if (elCount) elCount.innerText = `(${count})`;
}