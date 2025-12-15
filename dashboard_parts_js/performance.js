document.addEventListener('DOMContentLoaded', function () {
    // --- CẤU HÌNH ---
    const JSON_PATH_PREFIX = '/static/floorplan_app/module_Survey/';
    const itemsPerPage = 9; // STT 1-9 ở trang 1, STT 10 qua trang 2
    
    const ROOM_MAPPINGS = {
        "bedroom_1": "LDK_1", "bedroom_2": "LDK_2", "bedroom_3": "Bedroom",
        "japan": "Japan Style Room", "storage": "Storage",
        "toilet_1": "toilet 1", "2_toilet": "toilet 2", "3_toilet": "toilet 3"
    };
    const IGNORED_ROOMS = ["bathroom", "washroom", "entrance", "hall", "corridor", "living_dining_kitchen"];

    // --- STATE ---
    let allRequestsData = [];
    let currentPage = 1;
    let currentSort = "Ascending";
    let currentStatusFilter = "All"; 
    let myChart = null; 

    // --- 1. TẢI DỮ LIỆU ---
    async function fetchAllData() {
        let index = 1;
        let keepFetching = true;
        let tempResults = [];

        const tableBody = document.getElementById('perf-table-body');
        if (tableBody) tableBody.innerHTML = `<tr><td colspan="4" class="py-12 text-center text-gray-400 italic">Scanning data...</td></tr>`;

        while (keepFetching) {
            const fileName = `${index}.json`;
            const url = `${JSON_PATH_PREFIX}${fileName}`;
            try {
                const response = await fetch(url);
                if (response.ok) {
                    const json = await response.json();
                    const processedItem = processJsonItem(json, index);
                    processedItem.rawData = json; 
                    tempResults.push(processedItem);
                    index++; 
                } else {
                    keepFetching = false; 
                }
            } catch (err) {
                console.warn(`Lỗi khi đọc file ${fileName}:`, err);
                keepFetching = false;
            }
        }
        allRequestsData = tempResults;
        updateStatistics();
        renderTable();
    }

    function processJsonItem(json, index) {
        let reqIdRaw = json.req_id;
        if (json.processing_times && json.processing_times.length > 0 && json.processing_times[0].req_id) {
            reqIdRaw = json.processing_times[0].req_id;
        }
        const idNum = parseInt(reqIdRaw) || index;
        const reqId = `REQ_${String(idNum).padStart(3, '0')}`;
        const textInput = parseRoomsToText(json.rooms);

        let timeInSeconds = 0;
        if (json.processing_times && Array.isArray(json.processing_times) && json.processing_times.length > 0) {
            const timeObj = json.processing_times[0];
            if (timeObj.total_duration_seconds) timeInSeconds = parseInt(timeObj.total_duration_seconds);
        } 
        if (!timeInSeconds && json.total_duration_seconds) timeInSeconds = parseInt(json.total_duration_seconds);
        if (!timeInSeconds) timeInSeconds = 0; 

        let status = "Fails"; 
        if (json.request_status === true) status = "Success";
        else if (json.request_status === false) status = "Fails";

        const timeDisplay = formatTime(timeInSeconds);

        return {
            req_id: reqId,
            text_input: textInput,
            time_seconds: timeInSeconds,
            time_display: timeDisplay,
            status: status 
        };
    }

    function parseRoomsToText(rooms) {
        if (!rooms) return "";
        let parts = [];
        if (rooms["bedroom_4"] === 1) parts.push("4 LDK");
        else if (rooms["bedroom_3"] === 1) parts.push("3 LDK");
        else if (rooms["bedroom_2"] === 1) parts.push("2 LDK");
        else if (rooms["bedroom_1"] === 1) parts.push("1 LDK");
        
        if (rooms["japan"] === 1) parts.push("1 Japan Style Room");
        if (rooms["study_room"] === 1 || rooms["study"] === 1) parts.push("1 Study Room");
        if (rooms["storage"] === 1) parts.push("1 Storage Room");
        if (rooms["balcony"] === 1) parts.push("1 Balcony");
        if (rooms["3_toilet"] === 1) parts.push("3 Toilets");
        else if (rooms["2_toilet"] === 1) parts.push("2 Toilets");
        else if (rooms["toilet_1"] === 1 || rooms["toilet"] === 1) parts.push("1 Toilet");
        return parts.join("; "); 
    }

    function formatTime(seconds) {
        const m = Math.floor(seconds / 60).toString().padStart(2, '0');
        const s = (seconds % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    // --- 2. THỐNG KÊ ---
    function updateStatistics() {
        if (allRequestsData.length === 0) {
            document.getElementById('perf-total-request').textContent = "0";
            document.getElementById('perf-avg-time').textContent = "0s";
            return;
        }
        const total = allRequestsData.length;
        const validTimes = allRequestsData.map(d => d.time_seconds).filter(t => t > 0);
        let avg = 0, min = 0, max = 0;
        if (validTimes.length > 0) {
            const sum = validTimes.reduce((a, b) => a + b, 0);
            avg = Math.round(sum / validTimes.length);
            min = Math.min(...validTimes);
            max = Math.max(...validTimes);
        }
        document.getElementById('perf-total-request').textContent = total;
        document.getElementById('perf-avg-time').textContent = `${avg}s`;
        document.getElementById('stat-avg-count').textContent = `${avg}s`;
        document.getElementById('stat-fast-count').textContent = `${min}s`;
        document.getElementById('stat-slow-count').textContent = `${max}s`;
        initPerformanceChart(avg, min, max);
    }

    // --- 3. CHART ---
    function initPerformanceChart(avg, fastest, slowest) {
        const ctx = document.getElementById('performanceChart');
        if (!ctx) return;
        if (myChart) myChart.destroy();

        const chartLabels = ['Average', 'Fastest', 'Slowest'];
        const chartDataValues = [avg, fastest, slowest];
        const backgroundColors = ['#1e3a8a', '#3b82f6', '#93c5fd'];

        const arrowAxisPlugin = {
            id: 'arrowAxisPlugin',
            afterDraw: (chart) => {
                const ctx = chart.ctx;
                const xAxis = chart.scales.x;
                const yAxis = chart.scales.y;
                ctx.save();
                ctx.strokeStyle = '#6b7280'; ctx.fillStyle = '#6b7280'; ctx.lineWidth = 2; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'center';
                
                // Y Axis
                ctx.beginPath(); ctx.moveTo(xAxis.left, yAxis.bottom); ctx.lineTo(xAxis.left, yAxis.top - 20); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(xAxis.left - 5, yAxis.top - 20); ctx.lineTo(xAxis.left + 5, yAxis.top - 20); ctx.lineTo(xAxis.left, yAxis.top - 30); ctx.closePath(); ctx.fill();
                ctx.fillStyle = '#374151'; ctx.fillText("Time (s)", xAxis.left, yAxis.top - 40);
                
                // X Axis
                ctx.fillStyle = '#6b7280';
                ctx.beginPath(); ctx.moveTo(xAxis.left, yAxis.bottom); ctx.lineTo(xAxis.right + 20, yAxis.bottom); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(xAxis.right + 20, yAxis.bottom - 5); ctx.lineTo(xAxis.right + 20, yAxis.bottom + 5); ctx.lineTo(xAxis.right + 30, yAxis.bottom); ctx.closePath(); ctx.fill();
                ctx.fillStyle = '#374151'; ctx.fillText("Type", xAxis.right + 30, yAxis.bottom + 25);
                ctx.restore();
            }
        };

        myChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: 'Processing Time', data: chartDataValues, backgroundColor: backgroundColors, borderRadius: 4, barPercentage: 0.4, categoryPercentage: 0.6
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                layout: { padding: { top: 80, right: 50, bottom: 10, left: 20 } },
                plugins: { legend: { display: false }, tooltip: { enabled: true }, datalabels: { anchor: 'end', align: 'top', font: { weight: 'bold', size: 14 }, color: '#1f2937' } },
                scales: { y: { beginAtZero: true, border: { display: false }, grid: { display: false }, ticks: { display: false } }, x: { border: { display: false }, grid: { display: false }, ticks: { font: { weight: 'bold', size: 12 }, color: '#4b5563', padding: 10 } } }
            },
            plugins: [arrowAxisPlugin]
        });
    }

    // --- 4. BẢNG ---
    function processDataForTable() {
        let data = [...allRequestsData];
        if (currentStatusFilter !== "All") data = data.filter(item => item.status === currentStatusFilter);
        if (data.length === 0) return [];
        switch (currentSort) {
            case "Ascending": return data.sort((a, b) => a.time_seconds - b.time_seconds);
            case "Descending": return data.sort((a, b) => b.time_seconds - a.time_seconds);
            case "Fastest": return data.filter(item => item.time_seconds === Math.min(...data.map(i => i.time_seconds)));
            case "Slowest": return data.filter(item => item.time_seconds === Math.max(...data.map(i => i.time_seconds)));
            default: return data;
        }
    }

    function renderTable() {
        const tableBody = document.getElementById('perf-table-body');
        const pageInfo = document.getElementById('perf-page-info');
        const prevBtn = document.getElementById('perf-prev-btn');
        const nextBtn = document.getElementById('perf-next-btn');
        if (!tableBody) return;

        const processedData = processDataForTable();
        const totalPages = Math.ceil(processedData.length / itemsPerPage);
        if (currentPage > totalPages) currentPage = totalPages || 1;
        if (currentPage < 1) currentPage = 1;

        const startIndex = (currentPage - 1) * itemsPerPage;
        const currentPaginatedData = processedData.slice(startIndex, startIndex + itemsPerPage);

        tableBody.innerHTML = '';
        if (currentPaginatedData.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="4" class="py-8 text-center text-gray-500 italic">No data found</td></tr>`;
        } else {
            currentPaginatedData.forEach((row, index) => {
                const statusClass = row.status === "Success" ? "bg-blue-500 text-white shadow-sm shadow-blue-200" : "bg-red-500 text-white shadow-sm shadow-red-200";
                const realIndex = index + 1 + (currentPage - 1) * itemsPerPage;
                const tr = document.createElement('tr');
                tr.className = "hover:bg-gray-50 transition-colors duration-150 border-b border-gray-50 cursor-pointer group";
                tr.onclick = () => showRequestDetail(row);
                tr.innerHTML = `
                    <td class="py-4 px-6 text-gray-400 text-center font-bold text-xs group-hover:text-gray-600 transition-colors">${realIndex}</td>
                    <td class="py-4 px-6 text-left"><span class="inline-block px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wide w-20 text-center ${statusClass}">${row.req_id}</span></td>
                    <td class="py-4 px-6 text-gray-600 text-left font-medium text-xs truncate max-w-xs" title="${row.text_input}">${row.text_input}</td>
                    <td class="py-4 px-6 text-gray-900 font-bold text-right text-xs font-mono">${row.time_display}</td>
                `;
                tableBody.appendChild(tr);
            });
        }
        pageInfo.textContent = `Page ${currentPage} of ${totalPages || 1}`;
        prevBtn.disabled = currentPage === 1;
        nextBtn.disabled = currentPage === (totalPages || 1);
    }

    // --- 5. LOGIC HIỂN THỊ CHI TIẾT (COMPACT LAYOUT) ---
    function showRequestDetail(row) {
        const viewAnalysis = document.getElementById('view-analysis');
        const viewDetail = document.getElementById('view-detail');
        viewAnalysis.style.opacity = '0'; viewAnalysis.style.pointerEvents = 'none';
        setTimeout(() => {
            viewAnalysis.classList.add('hidden'); viewDetail.classList.remove('hidden');
            void viewDetail.offsetWidth; viewDetail.style.opacity = '1'; viewDetail.style.pointerEvents = 'auto';
        }, 300);

        document.getElementById('detail-req-id').textContent = row.req_id;
        document.getElementById('detail-total-time').textContent = row.time_seconds;

        // Đọc dữ liệu chi tiết
        const raw = row.rawData || {};
        let procData = {};
        if (raw.processing_times && Array.isArray(raw.processing_times) && raw.processing_times.length > 0) {
            procData = raw.processing_times[0];
        }

        const maskTime = parseInt(procData.mask_layout || procData.duration_layout_mask_generation) || 0;
        const drawTime = parseInt(procData.draw_plan || procData.duration_draw_plan) || 0;
        
        document.getElementById('detail-mask-time').textContent = maskTime;
        document.getElementById('detail-draw-time').textContent = drawTime;
        
        // Màu sắc cho Mask và Draw: Nếu Request Fail -> Đỏ, ngược lại Xanh
        const prepColor = row.status === "Fails" ? "bg-red-500" : "bg-blue-500";
        const total = Math.max(row.time_seconds, 1); 
        updateBar('bar-mask', maskTime, total, prepColor);
        updateBar('bar-draw', drawTime, total, prepColor);

        // --- XỬ LÝ GENERATION ---
        const genContainer = document.getElementById('detail-generation-container');
        genContainer.innerHTML = ''; 

        // Tìm lần Gen cuối cùng có thời gian > 0
        let lastGenIndex = 0;
        for (let i = 1; i <= 5; i++) {
            const t = parseInt(procData[`generation_${i}`] || procData[`duration_generate_floor_plan_${i}`]) || 0;
            if (t > 0) lastGenIndex = i;
        }

        for (let i = 1; i <= 5; i++) {
            const key = `generation_${i}`;
            const genTime = parseInt(procData[key] || procData[`duration_generate_floor_plan_${i}`]) || 0;
            const opacityClass = genTime > 0 ? '' : 'opacity-50';
            
            // Logic màu sắc thanh Gen
            let genBarColor = "bg-blue-500"; // Mặc định xanh
            
            if (row.status === "Fails") {
                // Nếu Request Fail -> Tất cả Đỏ
                genBarColor = "bg-red-500";
            } else {
                // Nếu Success
                if (i === lastGenIndex) {
                    genBarColor = "bg-blue-500"; // Gen cuối cùng: Xanh
                } else if (genTime > 0) {
                    genBarColor = "bg-red-500"; // Các Gen trước đó (failed attempts): Đỏ
                }
            }

            const genHtml = `
                <div class="pl-4 relative group ${opacityClass}">
                    <div class="flex justify-between items-end mb-1">
                        <span class="text-[9px] font-bold text-gray-400 uppercase tracking-wide">GENERATION ${i}</span>
                        <span class="text-xs font-bold text-gray-800">${genTime}s</span>
                    </div>
                    <div class="h-1 bg-gray-100 rounded-full w-full overflow-hidden">
                        <div class="h-full ${genBarColor} rounded-full transition-all duration-700 ease-out" style="width: ${Math.min((genTime/total)*100, 100)}%"></div>
                    </div>
                </div>
            `;
            genContainer.insertAdjacentHTML('beforeend', genHtml);
        }
    }

    function updateBar(elementId, value, max, colorClass) {
        const percentage = Math.min((value / max) * 100, 100);
        const el = document.getElementById(elementId);
        if (el) {
            el.className = `h-full ${colorClass} rounded-full transition-all duration-700 ease-out`;
            el.style.width = `${percentage}%`;
        }
    }

    document.getElementById('btn-close-detail')?.addEventListener('click', () => {
        const viewAnalysis = document.getElementById('view-analysis');
        const viewDetail = document.getElementById('view-detail');
        viewDetail.style.opacity = '0'; viewDetail.style.pointerEvents = 'none';
        setTimeout(() => {
            viewDetail.classList.add('hidden'); viewAnalysis.classList.remove('hidden');
            void viewAnalysis.offsetWidth; viewAnalysis.style.opacity = '1'; viewAnalysis.style.pointerEvents = 'auto';
        }, 300);
    });

    // --- 6. EVENT LISTENERS ---
    const statusBtn = document.getElementById('perf-status-btn');
    const statusMenu = document.getElementById('perf-status-menu');
    const statusLabel = document.getElementById('perf-current-status');
    if (statusBtn) {
        statusBtn.addEventListener('click', (e) => { e.stopPropagation(); statusMenu.classList.toggle('hidden'); document.getElementById('perf-filter-menu')?.classList.add('hidden'); });
        document.querySelectorAll('.perf-status-option').forEach(item => {
            item.addEventListener('click', (e) => {
                currentStatusFilter = e.target.getAttribute('data-value');
                currentPage = 1; statusLabel.textContent = currentStatusFilter;
                statusMenu.classList.add('hidden'); renderTable();
            });
        });
    }

    const filterBtn = document.getElementById('perf-filter-btn');
    const filterMenu = document.getElementById('perf-filter-menu');
    const filterLabel = document.getElementById('perf-current-filter');
    if (filterBtn) {
        filterBtn.addEventListener('click', (e) => { e.stopPropagation(); filterMenu.classList.toggle('hidden'); document.getElementById('perf-status-menu')?.classList.add('hidden'); });
        document.querySelectorAll('.perf-filter-option').forEach(item => {
            item.addEventListener('click', (e) => {
                currentSort = e.target.getAttribute('data-value');
                currentPage = 1; filterLabel.textContent = currentSort;
                filterMenu.classList.add('hidden'); renderTable();
            });
        });
    }

    document.addEventListener('click', (e) => {
        if (filterBtn && !filterBtn.contains(e.target) && !filterMenu.contains(e.target)) filterMenu.classList.add('hidden');
        if (statusBtn && !statusBtn.contains(e.target) && !statusMenu.contains(e.target)) statusMenu.classList.add('hidden');
    });

    document.getElementById('perf-prev-btn')?.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderTable(); } });
    document.getElementById('perf-next-btn')?.addEventListener('click', () => { 
        const processedData = processDataForTable(); 
        const totalPages = Math.ceil(processedData.length / itemsPerPage);
        if (currentPage < totalPages) { currentPage++; renderTable(); } 
    });

    // --- 7. CHẠY ---
    fetchAllData();
});