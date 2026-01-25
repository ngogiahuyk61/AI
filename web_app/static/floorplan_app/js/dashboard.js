const dashboardController = {
    charts: {},
    
    init: function() {
        if (typeof Chart === 'undefined') {
            console.error('Chart.js not loaded');
            return;
        }
        this.renderRoomConfigChart();
        this.renderTotalAreaChart();
        this.renderConsistencyChart();
        this.renderRoomSizeChart();
    },

    renderRoomConfigChart: function() {
        const ctx = document.getElementById('roomConfigChart');
        if (!ctx) return;
        
        if (this.charts.roomConfig) this.charts.roomConfig.destroy();

        this.charts.roomConfig = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: ['LDK 1', 'LDK 2', 'LDK 3', 'LDK 4', 'Japan Style', 'Study', 'Balcony', 'Toilet 1', 'Toilet 2', 'Toilet 3'],
                datasets: [{
                    label: 'Count',
                    data: [120, 15, 8, 2, 85, 64, 142, 150, 95, 12],
                    backgroundColor: [
                        '#3b82f6', '#3b82f6', '#3b82f6', '#3b82f6',
                        '#8b5cf6', '#8b5cf6',
                        '#10b981', '#10b981', '#10b981', '#10b981'
                    ],
                    borderRadius: 4,
                    barPercentage: 0.6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, display: false },
                    x: { grid: { display: false }, ticks: { font: { size: 10 } } }
                }
            }
        });
    },

    renderTotalAreaChart: function() {
        const ctx = document.getElementById('totalAreaChart');
        if (!ctx) return;
        
        if (this.charts.totalArea) this.charts.totalArea.destroy();

        this.charts.totalArea = new Chart(ctx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Area 50', 'Area 100', 'Area 150', 'Area 200'],
                datasets: [{
                    data: [12, 45, 78, 15],
                    backgroundColor: ['#94a3b8', '#64748b', '#f97316', '#cbd5e1'],
                    borderWidth: 0,
                    cutout: '75%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { 
                    legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } 
                }
            }
        });
    },

    renderConsistencyChart: function() {
        const ctx = document.getElementById('consistencyChart');
        if (!ctx) return;
        
        if (this.charts.consistency) this.charts.consistency.destroy();

        this.charts.consistency = new Chart(ctx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Total False', 'Total True'],
                datasets: [{
                    data: [12, 138],
                    backgroundColor: ['#ef4444', '#10b981'],
                    borderWidth: 0,
                    cutout: '60%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } }
            }
        });
    },

    renderRoomSizeChart: function() {
        const ctx = document.getElementById('roomSizeChart');
        if (!ctx) return;
        
        if (this.charts.roomSize) this.charts.roomSize.destroy();

        this.charts.roomSize = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: ['LDK', 'Japan Style', 'Study', 'Storage', 'Balconies', 'Toilet'],
                datasets: [
                    {
                        label: 'Too Small',
                        data: [2, 0, 1, 5, 0, 4],
                        backgroundColor: '#ef4444',
                    },
                    {
                        label: 'Good',
                        data: [48, 15, 10, 20, 25, 30],
                        backgroundColor: '#10b981',
                    },
                    {
                        label: 'Too Big',
                        data: [0, 1, 0, 2, 0, 1],
                        backgroundColor: '#f97316',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { stacked: true, grid: { display: false } },
                    y: { stacked: true, beginAtZero: true }
                }
            }
        });
    }
};

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => dashboardController.init(), 100);
    });
} else {
    setTimeout(() => dashboardController.init(), 100);
}
