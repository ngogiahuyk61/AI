/**
 * 02_services.js
 * Pricing & Subscription Dashboard Management
 * Features: Auto Renew, Realtime Token, Advanced Filtering, Pagination (20 rows), Cancellation (Delete)
 */

window.ServicesModule = {
    // Configuration
    pricingData: {
        monthly: { pro: 29, vip: 99 },
        yearly: { pro: 24, vip: 79 }
    },
    planLimits: {
        free: { name: "Free Starter", tokens: 100 },
        pro: { name: "Pro Architect", tokens: 500 },
        vip: { name: "VIP Studio", tokens: 3000 }
    },

    // State Management
    state: {
        allData: [],       // Raw data from DB
        filteredData: [], // Data after applying filters
        currentPage: 1,
        itemsPerPage: 20, // Requirement 1: 20 rows limit
        currentCycle: 'monthly',
        filters: {
            status: 'all', // 'all', 'active', 'expired'
            plan: 'all'    // 'all', 'free', 'pro', 'vip'
        }
    },

    // --- 1. INITIALIZATION ---
    init: async function () {
        console.log("🛠️ ServicesModule: Initializing...");

        if (window.lucide) window.lucide.createIcons();

        // Initialize UI components
        this.updatePricingUI();
        this.injectFilterControls(); // Inject Filter/Pagination UI

        // Load Data (Small delay for Clerk/Auth to be ready)
        setTimeout(() => this.refreshData(), 1000);
    },

    // --- 2. DATA FETCHING & PROCESSING ---
    refreshData: async function () {
        console.log("🔄 refreshData: Fetching...");
        const tbody = document.getElementById('services-table-body');
        if (!tbody) return;

        try {
            this.renderLoading(tbody);

            // Check Auth (Clerk)
            if (!window.Clerk || !window.Clerk.user) {
                tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-8 text-center text-gray-500">Please sign in to view services.</td></tr>`;
                return;
            }

            const userId = window.Clerk.user.id;

            // Check Supabase Function
            if (typeof getAuthenticatedSupabase !== 'function') {
                console.error("❌ Missing getAuthenticatedSupabase function");
                tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-8 text-center text-red-500">System Error: Supabase client not found.</td></tr>`;
                return;
            }

            const client = await getAuthenticatedSupabase();

            // Query DB
            const { data: subs, error } = await client
                .from('subscriptions')
                .select('*')
                .eq('user_id', userId)
                .order('created_at', { ascending: false });

            if (error) throw error;

            // Pre-process data (Calculate status/days once)
            this.state.allData = (subs || []).map(sub => {
                const today = new Date();
                const endDate = new Date(sub.end_date);
                const diffTime = endDate - today;
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                // Determine Real Status based on logic
                const isRealActive = sub.status === 'active' && diffDays >= 0;

                return {
                    ...sub,
                    computedStatus: isRealActive ? 'active' : 'expired',
                    diffDays: diffDays
                };
            });

            // Initial Filter & Render
            this.applyFilters();

        } catch (err) {
            console.error("💥 Error refreshData:", err);
            tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-8 text-center text-red-500">System Error: ${err.message}</td></tr>`;
        }
    },

    // --- 3. FILTER & PAGINATION LOGIC ---

    // Inject Filter Toolbar into DOM
    injectFilterControls: function () {
        const tableBody = document.getElementById('services-table-body');
        if (!tableBody) return;

        const tableElement = tableBody.closest('table');
        if (!tableElement) return;

        const containerId = 'services-filter-toolbar';
        if (document.getElementById(containerId)) return; // Prevent duplicate

        const toolbar = document.createElement('div');
        toolbar.id = containerId;
        toolbar.className = "flex flex-col sm:flex-row justify-between items-center mb-4 gap-4 bg-white p-4 rounded-lg shadow-sm border border-gray-100";

        toolbar.innerHTML = `
            <div class="flex gap-3 w-full sm:w-auto">
                <div class="relative">
                    <select id="filter-status" onchange="window.ServicesModule.handleFilterChange('status', this.value)" 
                        class="appearance-none bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-8">
                        <option value="all">Status: All</option>
                        <option value="active">Active</option>
                        <option value="expired">Expired</option>
                    </select>
                    <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-700">
                        <i data-lucide="filter" class="w-4 h-4"></i>
                    </div>
                </div>

                <div class="relative">
                    <select id="filter-plan" onchange="window.ServicesModule.handleFilterChange('plan', this.value)" 
                        class="appearance-none bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 pr-8">
                        <option value="all">Plan: All</option>
                        <option value="free">Free Starter</option>
                        <option value="pro">Pro Architect</option>
                        <option value="vip">VIP Studio</option>
                    </select>
                    <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-700">
                        <i data-lucide="layers" class="w-4 h-4"></i>
                    </div>
                </div>
            </div>

            <div id="pagination-info" class="text-sm text-gray-500 font-medium">
                Showing 0 results
            </div>
        `;

        tableElement.parentNode.insertBefore(toolbar, tableElement);
        if (window.lucide) window.lucide.createIcons();
    },

    handleFilterChange: function (type, value) {
        this.state.filters[type] = value;
        this.state.currentPage = 1; // Reset to page 1 on filter
        this.applyFilters();
    },

    applyFilters: function () {
        let data = this.state.allData;

        // 1. Filter by Status
        if (this.state.filters.status !== 'all') {
            data = data.filter(item => item.computedStatus === this.state.filters.status);
        }

        // 2. Filter by Plan
        if (this.state.filters.plan !== 'all') {
            data = data.filter(item => {
                const code = (item.package_code || 'free').toLowerCase();
                return code === this.state.filters.plan;
            });
        }

        this.state.filteredData = data;
        this.renderPaginatedTable();
    },

    // --- 4. RENDER TABLE (PAGINATED) ---
    renderPaginatedTable: function () {
        const tbody = document.getElementById('services-table-body');
        const { filteredData, currentPage, itemsPerPage } = this.state;

        if (filteredData.length === 0) {
            this.renderEmptyState(tbody);
            this.updatePaginationControls();
            return;
        }

        // Calculate slice
        const startIndex = (currentPage - 1) * itemsPerPage;
        const endIndex = startIndex + itemsPerPage;
        const pageData = filteredData.slice(startIndex, endIndex);

        tbody.innerHTML = '';

        pageData.forEach(sub => {
            const code = sub.package_code || 'free';
            const planConfig = this.planLimits[code] || { name: code.toUpperCase(), tokens: 0 };
            const diffDays = sub.diffDays;

            let statusBadge, daysText, actionBtn;

            // Logic Status
            if (sub.computedStatus === 'active') {
                statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">Active</span>`;
                daysText = `<span class="text-green-600 font-medium">${diffDays} days left</span>`;
                actionBtn = `<button onclick="window.ServicesModule.goToPayment('${code}')" class="text-blue-600 hover:text-blue-800 text-sm font-bold transition-colors">Renew</button>`;
            } else {
                statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">Expired</span>`;
                daysText = `<span class="text-gray-400">Ended</span>`;
                actionBtn = `<button onclick="window.ServicesModule.goToPayment('${code}')" class="text-black hover:underline text-sm font-bold transition-colors">Subscribe</button>`;
            }

            // Logic Token
            const maxTokens = planConfig.tokens;
            const usedTokens = sub.tokens_used || 0;
            let percent = Math.round((usedTokens / maxTokens) * 100);
            if (percent > 100) percent = 100;
            const progressColor = percent > 90 ? 'bg-red-500' : (percent > 50 ? 'bg-yellow-500' : 'bg-blue-600');

            // Logic Discount
            let discountHtml = `<span class="text-gray-400 text-xs">-</span>`;
            if (sub.discount) {
                discountHtml = `
                    <span class="inline-flex items-center gap-1 text-xs font-bold text-orange-600 bg-orange-50 px-2 py-1 rounded border border-orange-100">
                        <i data-lucide="tag" class="w-3 h-3"></i> ${sub.discount}
                    </span>
                `;
            }

            // Logic Auto Renewal
            const isAuto = sub.is_auto_renewal === true;
            const toggleHtml = `
                <div class="flex justify-center">
                    <div class="relative inline-block w-10 align-middle select-none transition duration-200 ease-in">
                        <input type="checkbox" name="toggle" id="toggle-${sub.id}" class="toggle-checkbox absolute block w-6 h-6 rounded-full bg-white border-4 appearance-none cursor-pointer" 
                            ${isAuto ? 'checked' : ''} 
                            onclick="window.ServicesModule.openAutoRenewModal('${sub.id}', ${isAuto})"/>
                        <label for="toggle-${sub.id}" class="toggle-label block overflow-hidden h-6 rounded-full bg-gray-300 cursor-pointer"></label>
                    </div>
                </div>
            `;

            // Delete Button
            const deleteBtn = `
                <button onclick="window.ServicesModule.openDeleteModal('${sub.id}')" 
                    class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors" title="Cancel Subscription">
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            `;

            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-50 transition-colors border-b border-gray-100";
            tr.innerHTML = `
                <td class="px-6 py-4">
                    <div class="text-sm font-bold text-gray-900 uppercase">${planConfig.name}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">${statusBadge}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm">${daysText}</td>
                
                <td class="px-6 py-4 align-middle">
                    <div class="w-full max-w-[140px]">
                        <div class="flex justify-between text-xs mb-1 font-medium">
                            <span class="text-gray-600">${usedTokens} used</span>
                            <span class="text-gray-400">/ ${maxTokens}</span>
                        </div>
                        <div class="w-full bg-gray-200 rounded-full h-1.5">
                            <div class="h-1.5 rounded-full ${progressColor}" style="width: ${percent}%"></div>
                        </div>
                    </div>
                </td>

                <td class="px-6 py-4 align-middle">${toggleHtml}</td>

                <td class="px-6 py-4 whitespace-nowrap text-center">${discountHtml}</td>
                
                <td class="px-6 py-4 whitespace-nowrap text-right">
                    <div class="flex items-center justify-end gap-3">
                        ${actionBtn}
                        ${deleteBtn}
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

        if (window.lucide) window.lucide.createIcons();
        this.updatePaginationControls();
    },

    updatePaginationControls: function () {
        const { filteredData, currentPage, itemsPerPage } = this.state;
        const totalItems = filteredData.length;
        const totalPages = Math.ceil(totalItems / itemsPerPage);

        // Update Info Text
        const infoEl = document.getElementById('pagination-info');
        if (infoEl) {
            if (totalItems === 0) {
                infoEl.innerText = 'No results found';
            } else {
                const start = (currentPage - 1) * itemsPerPage + 1;
                const end = Math.min(currentPage * itemsPerPage, totalItems);
                infoEl.innerText = `Showing ${start}-${end} of ${totalItems}`;
            }
        }

        // Render Bottom Pagination Buttons
        let pagContainer = document.getElementById('services-pagination');
        if (!pagContainer) {
            const tableElement = document.getElementById('services-table-body').closest('table');
            pagContainer = document.createElement('div');
            pagContainer.id = 'services-pagination';
            pagContainer.className = "flex justify-end gap-2 mt-4 px-1";
            tableElement.parentNode.appendChild(pagContainer);
        }

        if (totalItems <= itemsPerPage) {
            pagContainer.innerHTML = ''; // Hide if 1 page
            return;
        }

        pagContainer.innerHTML = `
            <button onclick="window.ServicesModule.changePage(-1)" 
                ${currentPage === 1 ? 'disabled' : ''}
                class="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed">
                Previous
            </button>
            <span class="px-3 py-1 text-sm text-gray-700 font-bold bg-gray-50 border rounded">
                Page ${currentPage}
            </span>
            <button onclick="window.ServicesModule.changePage(1)" 
                ${currentPage >= totalPages ? 'disabled' : ''}
                class="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed">
                Next
            </button>
        `;
    },

    changePage: function (direction) {
        const { currentPage, filteredData, itemsPerPage } = this.state;
        const totalPages = Math.ceil(filteredData.length / itemsPerPage);
        const newPage = currentPage + direction;

        if (newPage > 0 && newPage <= totalPages) {
            this.state.currentPage = newPage;
            this.renderPaginatedTable();
        }
    },

    renderLoading: function (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-8 text-center text-gray-500 flex flex-col items-center gap-2">
            <svg class="animate-spin h-6 w-6 text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            <span>Loading data...</span>
        </td></tr>`;
    },

    renderEmptyState: function (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-12 text-center">
                    <div class="flex flex-col items-center justify-center">
                        <div class="p-3 bg-gray-100 rounded-full mb-3">
                            <i data-lucide="package-open" class="w-8 h-8 text-gray-400"></i>
                        </div>
                        <p class="text-gray-900 font-medium">No subscriptions found.</p>
                        <p class="text-gray-500 text-sm mb-4">Choose a plan below to get started.</p>
                        <button onclick="document.getElementById('pricing').scrollIntoView({behavior: 'smooth'})" class="text-blue-600 font-bold hover:underline">View Pricing</button>
                    </div>
                </td>
            </tr>
        `;
        if (window.lucide) window.lucide.createIcons();
    },

    // --- 5. AUTO RENEWAL MODAL ---
    openAutoRenewModal: function (subId, currentStatus) {
        const checkbox = document.getElementById(`toggle-${subId}`);
        if (checkbox) checkbox.checked = currentStatus;

        const title = currentStatus ? "Cancel Auto-Renewal?" : "Enable Auto-Renewal?";
        const desc = currentStatus
            ? "Are you sure you want to disable this? You will need to renew manually when the plan expires."
            : "The system will automatically renew this plan upon expiration to ensure uninterrupted service.";
        const confirmBtnText = currentStatus ? "Disable Renewal" : "Enable Renewal";
        const confirmBtnColor = currentStatus ? "bg-red-600 hover:bg-red-700" : "bg-black hover:bg-gray-800";

        const modalHtml = `
            <div id="confirm-modal" class="custom-modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                <div class="custom-modal-box bg-white rounded-xl shadow-2xl max-w-sm w-full p-6 transform transition-all scale-100">
                    <div class="text-center mb-6">
                        <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full ${currentStatus ? 'bg-red-100' : 'bg-green-100'} mb-4">
                            <i data-lucide="${currentStatus ? 'alert-triangle' : 'zap'}" class="h-6 w-6 ${currentStatus ? 'text-red-600' : 'text-green-600'}"></i>
                        </div>
                        <h3 class="text-lg leading-6 font-bold text-gray-900">${title}</h3>
                        <p class="text-sm text-gray-500 mt-2">${desc}</p>
                    </div>
                    <div class="flex gap-3 justify-center">
                        <button onclick="document.getElementById('confirm-modal').remove()" 
                            class="w-full inline-flex justify-center rounded-lg border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none sm:text-sm">
                            Cancel
                        </button>
                        <button onclick="window.ServicesModule.confirmAutoRenew('${subId}', ${!currentStatus})" 
                            class="w-full inline-flex justify-center rounded-lg border border-transparent shadow-sm px-4 py-2 ${confirmBtnColor} text-base font-medium text-white focus:outline-none sm:text-sm">
                            ${confirmBtnText}
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        if (window.lucide) window.lucide.createIcons();
    },

    confirmAutoRenew: async function (subId, newStatus) {
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.remove();

        try {
            const client = await getAuthenticatedSupabase();
            const { error } = await client
                .from('subscriptions')
                .update({ is_auto_renewal: newStatus })
                .eq('id', subId);

            if (error) throw error;

            await this.refreshData();
            console.log(`✅ Auto Renew updated: ${newStatus}`);

        } catch (err) {
            console.error("Update error:", err);
            alert("Could not update. Please try again.");
        }
    },

    // --- 6. DELETE (CANCEL) SUBSCRIPTION MODAL ---
    openDeleteModal: function (subId) {
        // Find subscription details to show in modal
        const sub = this.state.allData.find(s => s.id === subId);
        if (!sub) return;

        const code = sub.package_code || 'free';
        const planName = (this.planLimits[code] || { name: code.toUpperCase() }).name;

        // Format dates
        const createdDate = new Date(sub.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

        const modalHtml = `
            <div id="delete-modal" class="custom-modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                <div class="custom-modal-box bg-white rounded-xl shadow-2xl max-w-md w-full p-6 transform transition-all scale-100">
                    <div class="text-center mb-6">
                        <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 mb-4">
                            <i data-lucide="trash-2" class="h-6 w-6 text-red-600"></i>
                        </div>
                        <h3 class="text-lg leading-6 font-bold text-gray-900">Cancel Subscription?</h3>
                        
                        <div class="mt-4 bg-gray-50 p-4 rounded-lg text-left text-sm text-gray-600 border border-gray-100">
                            <p class="mb-2"><span class="font-bold text-gray-800">Plan:</span> ${planName}</p>
                            <p class="mb-2"><span class="font-bold text-gray-800">Created on:</span> ${createdDate}</p>
                            <p class="mb-2"><span class="font-bold text-gray-800">Cancellation Date:</span> ${today}</p>
                            <p class="mt-3 text-red-500 italic text-xs border-t border-gray-200 pt-2">
                                * Note: This action is non-refundable. Your access will be revoked immediately.
                            </p>
                        </div>
                    </div>
                    
                    <div class="flex gap-3 justify-center">
                        <button onclick="document.getElementById('delete-modal').remove()" 
                            class="w-full inline-flex justify-center rounded-lg border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none sm:text-sm">
                            Cancel
                        </button>
                        <button id="btn-confirm-delete" onclick="window.ServicesModule.confirmDelete('${subId}')" 
                            class="w-full inline-flex justify-center items-center rounded-lg border border-transparent shadow-sm px-4 py-2 bg-red-600 text-base font-medium text-white hover:bg-red-700 focus:outline-none sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed">
                            Confirm Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        if (window.lucide) window.lucide.createIcons();
    },

    confirmDelete: async function (subId) {
        const confirmBtn = document.getElementById('btn-confirm-delete');
        const modal = document.getElementById('delete-modal');

        try {
            // Set loading state
            if (confirmBtn) {
                confirmBtn.innerHTML = `Processing...`;
                confirmBtn.disabled = true;
            }

            if (typeof getAuthenticatedSupabase !== 'function') {
                throw new Error("Supabase authentication function not found.");
            }

            const client = await getAuthenticatedSupabase();

            // --- KHÚC QUAN TRỌNG ĐÃ SỬA ---
            // Thêm { count: 'exact' } để biết chính xác có bao nhiêu dòng bị xóa
            const { error, count } = await client
                .from('subscriptions')
                .delete({ count: 'exact' })
                .eq('id', subId);

            if (error) throw error;

            // Nếu không có dòng nào bị xóa (count === 0 hoặc null) -> Lỗi do RLS hoặc ID sai
            if (count === 0 || count === null) {
                throw new Error("Không thể xóa. Có thể do chặn quyền (RLS) hoặc dữ liệu không tồn tại.");
            }
            // -------------------------------

            console.log(`✅ Subscription deleted successfully. Count: ${count}`);

            // Đóng modal trước
            if (modal) modal.remove();

            // Refresh lại bảng dữ liệu
            await this.refreshData();

        } catch (err) {
            console.error("❌ Delete error:", err);
            alert("Lỗi xóa data: " + err.message); // Hiện popup lỗi cho user thấy

            // Reset button
            if (confirmBtn) {
                confirmBtn.innerHTML = 'Confirm Cancel';
                confirmBtn.disabled = false;
            }
        }
    },

    // --- 7. PRICING LOGIC ---
    setPricing: function (cycle) {
        this.state.currentCycle = cycle;
        this.updatePricingUI();
    },

    updatePricingUI: function () {
        const prices = this.pricingData[this.state.currentCycle];
        const btnMonthly = document.getElementById('btn-monthly');
        const btnYearly = document.getElementById('btn-yearly');

        const activeClass = "bg-white text-black shadow-sm ring-1 ring-black/5";
        const inactiveClass = "text-neutral-500 hover:text-black bg-transparent shadow-none ring-0";

        if (this.state.currentCycle === 'monthly') {
            if (btnMonthly) btnMonthly.className = `px-6 py-2 rounded-full text-sm font-bold transition-all ${activeClass}`;
            if (btnYearly) btnYearly.className = `px-6 py-2 rounded-full text-sm font-bold transition-all ${inactiveClass}`;
        } else {
            if (btnMonthly) btnMonthly.className = `px-6 py-2 rounded-full text-sm font-bold transition-all ${inactiveClass}`;
            if (btnYearly) btnYearly.className = `px-6 py-2 rounded-full text-sm font-bold transition-all ${activeClass}`;
        }

        const subText = this.state.currentCycle === 'monthly' ? '/month' : '/month (billed yearly)';

        const pricePro = document.getElementById('price-pro');
        const periodPro = document.getElementById('period-pro');
        const priceVip = document.getElementById('price-vip');
        const periodVip = document.getElementById('period-vip');

        if (pricePro) pricePro.innerText = `$${prices.pro}`;
        if (periodPro) periodPro.innerText = subText;
        if (priceVip) priceVip.innerText = `$${prices.vip}`;
        if (periodVip) periodVip.innerText = subText;
    },

    // --- 8. PAYMENT ---
    goToPayment: function (planId) {
        const cycle = this.state.currentCycle;
        localStorage.setItem('selected_plan', planId);
        window.location.href = `http://127.0.0.1:8000/payment/?plan=${planId}&cycle=${cycle}`;
    }
};

// Auto init
window.ServicesModule.init();