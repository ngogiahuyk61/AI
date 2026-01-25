/**
 * USER INPUT DASHBOARD CONTROLLER - FULL UPDATE (16px Fonts, Logic Fixed, Arrow Layout Fixed)
 */

// --- 1. CONFIGURATION ---
const BASE_JSON_PATH = '/static/floorplan_app/module_Survey/';

// --- 2. CUSTOM PLUGIN: ARROW AXIS ---
const arrowAxisPlugin = {
    id: 'arrowAxis',
    afterDraw: (chart) => {
        const { ctx, chartArea: { left, right, top, bottom } } = chart;
        ctx.save();
        ctx.strokeStyle = '#6b7280'; ctx.lineWidth = 1.5; ctx.fillStyle = '#6b7280';
        
        // FONT: 16px Bold
        ctx.font = 'bold 16px "Segoe UI", sans-serif'; 
        ctx.textAlign = 'center';

        const yAxisX = left - 10;
        const arrowTop = top - 30;

        // Y Axis
        ctx.beginPath(); ctx.moveTo(yAxisX, bottom); ctx.lineTo(yAxisX, arrowTop); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(yAxisX - 4, arrowTop); ctx.lineTo(yAxisX + 4, arrowTop); ctx.lineTo(yAxisX, arrowTop - 8); ctx.fill();
        ctx.fillStyle = '#4b5563'; 
        // VẼ CHỮ "Request": Vẽ cao hơn mũi tên một chút, đảm bảo không bị cắt nhờ padding top chart
        ctx.fillText('Request', yAxisX, arrowTop - 15); 

        // X Axis
        ctx.beginPath(); ctx.moveTo(yAxisX, bottom); ctx.lineTo(right + 10, bottom); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(right + 10, bottom - 4); ctx.lineTo(right + 10, bottom + 4); ctx.lineTo(right + 18, bottom); ctx.fill();
        ctx.textAlign = 'left'; 
        // VẼ CHỮ "Room": Vẽ lệch phải, đảm bảo không bị cắt nhờ padding right chart
        ctx.fillText('Room', right + 25, bottom + 5);
        ctx.restore();
    }
};

// --- 3. DYNAMIC FETCH LOGIC ---
async function fetchAllSurveys() {
    let index = 1;
    let allData = [];
    let keepFetching = true;

    while (keepFetching) {
        try {
            const url = `${BASE_JSON_PATH}${index}.json`;
            const response = await fetch(url);
            
            if (response.ok) {
                const data = await response.json();
                allData.push(data);
                index++; 
            } else {
                keepFetching = false;
            }
        } catch (error) {
            keepFetching = false;
        }
    }
    return allData;
}

// --- 4. MAIN PROCESSING LOGIC ---
async function fetchAndRenderDashboard() {
    // 1. Fetch Dynamic Data
    const results = await fetchAllSurveys();
    const totalRequest = results.length; 

    // 2. Init Counts
    let counts = {
        // Bedroom types 
        bed_1: 0, bed_2: 0, bed_3: 0, bed_4: 0,
        // Specific rooms
        japan: 0, study: 0, balcony: 0, storage: 0,
        // Areas
        area_50: 0, area_100: 0, area_150: 0, area_200: 0
    };

    // 3. Count Data
    results.forEach(data => {
        if (data && data.rooms) {
            const r = data.rooms;
            const ta = data.total_area || {};

            // Check Bedroom specifics
            if (r.bedroom_1 === 1) counts.bed_1++;
            if (r.bedroom_2 === 1) counts.bed_2++;
            if (r.bedroom_3 === 1) counts.bed_3++;
            if (r.bedroom_4 === 1) counts.bed_4++;

            // Check List Room items
            if (r.Japan === 1) counts.japan++;
            if (r.study === 1) counts.study++;
            if (r.balcony === 1) counts.balcony++;
            if (r.storage === 1) counts.storage++;

            // Check Areas
            if (ta.total_area_50 === 1) counts.area_50++;
            if (ta.total_area_100 === 1) counts.area_100++;
            if (ta.total_area_150 === 1) counts.area_150++;
            if (ta.total_area_200 === 1) counts.area_200++;
        }
    });

    // 4. Update KPI: Total Request
    const totalEl = document.getElementById('kpi-total-request');
    if (totalEl) totalEl.innerText = totalRequest;

    // 5. Logic: Most Requested (ONLY LIST ROOM ITEMS: Japan, Study, Balcony, Storage)
    const rankingList = [
        { name: 'JAPAN STYLE', val: counts.japan },
        { name: 'STUDY ROOM', val: counts.study },
        { name: 'BALCONY', val: counts.balcony },
        { name: 'STORAGE', val: counts.storage }
    ];
    
    // Sort Descending
    rankingList.sort((a, b) => b.val - a.val);
    const topItem = rankingList[0];

    // Update UI Most Requested
    const labelCard2 = document.getElementById('label-card-2');
    const valCard2 = document.getElementById('val-card-2');
    if (labelCard2 && valCard2) {
        if (topItem.val > 0) {
            labelCard2.innerText = topItem.name;
            valCard2.innerText = topItem.val;
        } else {
            labelCard2.innerText = "NONE";
            valCard2.innerText = "0";
        }
    }

    // 6. Update List Room Table (Left Table)
    setSafeText('list-japan', counts.japan);
    setSafeText('list-study', counts.study);
    setSafeText('list-balcony', counts.balcony);
    setSafeText('list-storage', counts.storage);

    // 7. Update Room Default Table (Right Table - Equals Total Request)
    setSafeText('list-bathroom', totalRequest);
    setSafeText('list-bedroom', totalRequest);
    setSafeText('list-toilet', totalRequest);

    // 8. Update Charts Data (Top Tables)
    setSafeText('val-bed-1', counts.bed_1);
    setSafeText('val-bed-2', counts.bed_2);
    setSafeText('val-bed-3', counts.bed_3);
    setSafeText('val-bed-4', counts.bed_4);

    setSafeText('val-area-50', counts.area_50);
    setSafeText('val-area-100', counts.area_100);
    setSafeText('val-area-150', counts.area_150);
    setSafeText('val-area-200', counts.area_200);

    renderBedroomChart([counts.bed_1, counts.bed_2, counts.bed_3, counts.bed_4]);
    renderAreaChart([counts.area_50, counts.area_100, counts.area_150, counts.area_200]);
}

// Helper function
function setSafeText(id, val) {
    const el = document.getElementById(id);
    if (el) el.innerText = val;
}

// --- 5. RENDER CHART FUNCTIONS ---
function renderBedroomChart(dataValues) {
    const ctx = document.getElementById('bedroomChart');
    if (!ctx) return;

    const defaultColors = ['#1e3a8a', '#3b82f6', '#93c5fd', '#e5e7eb'];
    let chartData = [
        { label: '1 Bedroom', value: dataValues[0], color: defaultColors[0] },
        { label: '2 Bedroom', value: dataValues[1], color: defaultColors[1] },
        { label: '3 Bedroom', value: dataValues[2], color: defaultColors[2] },
        { label: '4 Bedroom', value: dataValues[3], color: defaultColors[3] }
    ];

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    window.bedroomChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartData.map(i => i.label),
            datasets: [{
                label: 'Request',
                data: chartData.map(i => i.value),
                backgroundColor: chartData.map(i => i.color),
                borderRadius: 4,
                barThickness: 50,
                hoverBackgroundColor: '#60a5fa'
            }]
        },
        plugins: [arrowAxisPlugin, typeof ChartDataLabels !== 'undefined' ? ChartDataLabels : {}],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            // LAYOUT PADDING INCREASED: Top 80 (cho chữ Request), Right 80 (cho chữ Room)
            layout: { padding: { top: 80, right: 80, left: 50, bottom: 20 } },
            plugins: {
                legend: { display: false },
                datalabels: {
                    anchor: 'end', align: 'top', color: '#374151',
                    font: { weight: 'bold', size: 16 }, offset: 4,
                    formatter: (val) => val > 0 ? val : '',
                    display: true
                }
            },
            scales: {
                y: { display: false, beginAtZero: true, grace: '10%' },
                x: { border: { display: false }, grid: { display: false }, ticks: { color: '#6b7280', font: { size: 16 }, padding: 10 } }
            }
        }
    });

    const filterEl = document.getElementById('bedroomFilter');
    if (filterEl) {
        const newFilterEl = filterEl.cloneNode(true);
        filterEl.parentNode.replaceChild(newFilterEl, filterEl);

        newFilterEl.addEventListener('change', function(e) {
            const type = e.target.value;
            let sorted = [...chartData];

            if (type === 'asc') sorted.sort((a, b) => a.label.localeCompare(b.label));
            else if (type === 'desc') sorted.sort((a, b) => b.label.localeCompare(a.label));
            else if (type === 'lar') { sorted.sort((a, b) => b.value - a.value); sorted = sorted.slice(0, 1); }
            else if (type === 'sml') { sorted.sort((a, b) => a.value - b.value); sorted = sorted.slice(0, 1); }

            window.bedroomChartInstance.data.labels = sorted.map(i => i.label);
            window.bedroomChartInstance.data.datasets[0].data = sorted.map(i => i.value);
            window.bedroomChartInstance.data.datasets[0].backgroundColor = sorted.map(i => i.color);
            window.bedroomChartInstance.update();
        });
    }
}

function renderAreaChart(dataValues) {
    const ctx = document.getElementById('areaDonutChart');
    if (!ctx) return;

    const existingChart = Chart.getChart(ctx);
    if (existingChart) existingChart.destroy();

    const total = dataValues.reduce((a, b) => a + b, 0);
    const updateLegend = (idx, idSuffix) => {
        const val = dataValues[idx];
        const pct = total > 0 ? Math.round((val / total) * 100) : 0;
        const el = document.getElementById(`legend-text-${idSuffix}`);
        if (el) {
            // Update Legend theo định dạng mới: "9% (2)"
            el.innerText = `${pct}% (${val})`;
        }
    };
    updateLegend(0, '50'); updateLegend(1, '100'); updateLegend(2, '150'); updateLegend(3, '200');

    window.areaChartInstance = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['Area 50-100', 'Area 100-150', 'Area 150-200', 'Area 200-250'],
            datasets: [{
                data: dataValues,
                // UPDATED COLORS TO MATCH HTML LEGEND
                // Yellow #facc15, Purple #7e22ce, Pink #d946ef, Gray #d1d5db
                backgroundColor: ['#facc15', '#7e22ce', '#d946ef', '#d1d5db'],
                borderWidth: 0, hoverOffset: 4
            }]
        },
        plugins: [typeof ChartDataLabels !== 'undefined' ? ChartDataLabels : {}],
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                datalabels: {
                    display: true, align: 'center', color: '#fff',
                    font: { weight: 'bold', size: 16 },
                    formatter: (val, ctx) => {
                        let sum = ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
                        return sum > 0 && val > 0 ? (val*100/sum).toFixed(0)+"%" : "";
                    }
                }
            },
            layout: { padding: 0 }
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    fetchAndRenderDashboard();
});