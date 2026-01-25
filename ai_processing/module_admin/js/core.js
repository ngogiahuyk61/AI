// js/core.js

// --- 1. CONFIGURATION ---
const MY_CLERK_KEY = 'pk_test_c2V0dGxpbmcta2l0dGVuLTEyLmNsZXJrLmFjY291bnRzLmRldiQ';

// CẤU HÌNH MENU
const MODULE_CONFIG = [
    {
        id: "01_users",
        title: "1/ Manager Users",
        roles: ['staff', 'admin'],
        icon: "users",
        path: "01_users",
        desc: "Quản trị nhân sự & Khách hàng",
        subs: [
            { id: "tab-manage", title: "Manager Users" },
            { id: "tab-roles", title: "Manager Roles" },
            { id: "tab-workspace", title: "Manager Workspaces" }
        ]
    },
    { id: "02_services", title: "Service management", icon: "package", path: "02_services", desc: "Service package management", roles: ['all'] },
    { id: "04_ai_core", title: "4/ Dự án AI (CORE)", icon: "zap", path: "04_ai_core", desc: "Quản lý AI Core", roles: ['all'] },
    { id: "07_notifications", title: "7/ Thông báo", icon: "bell", path: "07_notifications", desc: "Cấu hình thông báo", roles: ['all'] },
    { id: "08_statistics", title: "8/ Thống Kê", icon: "pie-chart", path: "08_statistics", desc: "Báo cáo tổng quan", roles: ['all'] },
    { id: "09_integration", title: "9/ Tích hợp", icon: "plug", path: "09_integration", desc: "Kết nối ERP", roles: ['staff', 'admin'] },
    { id: "10_system", title: "10/ Hệ Thống", icon: "settings", path: "10_system", desc: "Cấu hình hệ thống", roles: ['admin'] }
];

let state = {
    activeModuleId: null,
    sidebarOpen: true
};

// --- 2. AUTHENTICATION LOGIC ---
class MockClerk {
    constructor() { this.user = null; this.isMock = true; }
    async load() { return; }
    openSignIn() {
        const mockUser = {
            id: "user_admin_demo",
            fullName: "Demo Admin",
            primaryEmailAddress: { emailAddress: "admin@webai.com" },
            imageUrl: "https://www.svgrepo.com/show/382099/female-avatar-girl-face-woman-user-2.svg"
        };
        this.user = mockUser;
        handleLoginSuccess(mockUser, true);
    }
    signOut() { this.user = null; handleLogoutSuccess(); }
    mountUserButton(el) {
        if (!this.user) return;
        el.innerHTML = `<div class="w-8 h-8 rounded-full bg-cover bg-center border-2 border-white shadow-sm cursor-pointer hover:ring-2 hover:ring-blue-500" style="background-image: url('${this.user.imageUrl}');" onclick="if(confirm('Thoát chế độ Demo?')) window.Clerk.signOut()"></div>`;
    }
}

let isClerkRealLoaded = false;

const initApp = async () => {
    // 1. Kiểm tra môi trường (Không chạy file://)
    if (window.location.protocol === 'file:') {
        showEnvironmentWarning("Bạn đang chạy file trực tiếp. Clerk sẽ không hoạt động. Hãy dùng Live Server.");
        updateAuthStatus('error');
    }

    try {
        // 2. Tải thư viện Clerk
        await loadScript("https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js", MY_CLERK_KEY);

        if (typeof window.Clerk !== 'undefined') {
            const currentUrl = window.location.href;
            
            // 3. Khởi động Clerk
            await window.Clerk.load({ 
                signInForceRedirectUrl: currentUrl, 
                signUpForceRedirectUrl: currentUrl 
            });
            
            isClerkRealLoaded = true;

            // --- ĐOẠN CODE FIX LỖI USER UNDEFINED ---
            if (window.Clerk.user) {
                console.log("✅ Clerk đã tải xong User ID:", window.Clerk.user.id);
                
                // QUAN TRỌNG: Truyền trực tiếp object user vào hàm
                // để đảm bảo bên kia nhận được dữ liệu, không bị undefined
                handleLoginSuccess(window.Clerk.user, false); 
            } else {
                // Trường hợp chưa đăng nhập
                console.log("ℹ️ Người dùng chưa đăng nhập.");
                updateAuthStatus('ready');
                const landing = document.getElementById('auth-landing');
                if (landing) landing.classList.remove('hidden');
            }
            // ----------------------------------------
        }
    } catch (err) {
        console.error("❌ Lỗi tải Clerk:", err);
        isClerkRealLoaded = false;
        
        const landing = document.getElementById('auth-landing');
        if (landing) landing.classList.remove('hidden');
        
        showEnvironmentWarning(`Môi trường Sandbox/Local có thể chặn Clerk. Dùng nút "Vào Dashboard Demo".`);
        updateAuthStatus('error');
    } finally {
        // 4. Luôn tắt màn hình Loading dù thành công hay thất bại
        const loading = document.getElementById('app-loading');
        if (loading) loading.classList.add('hidden');
    }
};

// --- Helper Functions ---
function showEnvironmentWarning(msg) {
    document.getElementById('env-warning').classList.remove('hidden');
    document.getElementById('env-warning-text').innerHTML = msg;
}
function updateAuthStatus(status) {
    const el = document.getElementById('auth-status');
    if (status === 'ready') el.innerHTML = `<span class="text-green-600 font-medium">● Clerk Connected</span>`;
    else el.innerHTML = `<span class="text-red-500 font-medium">● Connection Issue</span>`;
}
function loadScript(src, key) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src; script.async = true; script.crossOrigin = "anonymous";
        if(key) script.setAttribute('data-clerk-publishable-key', key);
        script.onload = () => resolve();
        script.onerror = () => reject();
        document.body.appendChild(script);
    });
}
window.handleSignInClick = () => { if (isClerkRealLoaded && window.Clerk) window.Clerk.openSignIn(); else alert("Vui lòng dùng nút Demo."); };
window.handleDemoClick = () => { window.Clerk = new MockClerk(); window.Clerk.openSignIn(); };
window.handleSignOutClick = () => { if (window.Clerk) window.Clerk.signOut(); };

// --- LOGIN HANDLER (Copy đè vào core.js) ---

async function handleLoginSuccess(user, isDemo) {
    console.log("🚀 handleLoginSuccess được gọi với User:", user?.id); // Debug

    // 1. Ẩn màn hình loading, hiện dashboard
    document.getElementById('auth-landing').classList.add('hidden');
    document.getElementById('dashboard-container').classList.remove('hidden');
    
    // 2. Cập nhật UI
    const userName = user.fullName || user.firstName || "User";
    const nameEl = document.getElementById('clerk-user-name');
    if (nameEl) nameEl.innerText = userName;

    if (document.getElementById('user-button-mount') && window.Clerk) {
        window.Clerk.mountUserButton(document.getElementById('user-button-mount'));
    }

    // 3. Gọi đồng bộ (Chỉ khi không phải Demo)
    if (!isDemo) {
        if (user && user.id) {
            await syncUserSystem(user);
        } else {
            console.error("❌ LỖI: handleLoginSuccess nhận user bị rỗng!", user);
        }
    } else {
        const roleEl = document.getElementById('clerk-user-role');
        if (roleEl) roleEl.innerText = "Demo Admin";
        showToast("Đang dùng chế độ Demo.", "info");
    }

    // 4. Khởi tạo các module khác
    initDashboardModules();
}

let currentUserRole = 'customer';

async function syncUserSystem(clerkUser) {
    // Check kỹ lần cuối
    if (!clerkUser || !clerkUser.id) {
        console.error("❌ syncUserSystem dừng lại vì clerkUser bị undefined.");
        return;
    }

    console.log("🔄 Bắt đầu đồng bộ User:", clerkUser.id);
    
    if (typeof getAuthenticatedSupabase === 'undefined') {
        console.error("❌ Không tìm thấy hàm getAuthenticatedSupabase từ db.js");
        return;
    }

    const client = await getAuthenticatedSupabase();
    const email = clerkUser.primaryEmailAddress?.emailAddress;

    // A. Kiểm tra User đã tồn tại chưa
    // Lưu ý: Lỗi 400 thường do cột 'role' chưa có hoặc cache sai.
    // Ta chỉ select id trước cho an toàn.
    let { data: existingUser, error: fetchError } = await client
        .from('users')
        .select('id, role')
        .eq('email', email)
        .maybeSingle(); // Dùng maybeSingle để không báo lỗi nếu chưa có

    if (fetchError) {
        console.error("⚠️ Lỗi kiểm tra user (có thể bỏ qua nếu là lỗi 406/PGRST116):", fetchError);
    }

    let finalRole = 'customer';
    if (existingUser && existingUser.role) {
        finalRole = existingUser.role;
        console.log("ℹ️ User cũ, giữ nguyên role:", finalRole);
    } else if (email && email.endsWith('@webai.com')) {
        finalRole = 'admin';
    }

    // B. Ghi vào Database (Upsert)
    const { data: dbUser, error } = await client
        .from('users')
        .upsert({
            id: clerkUser.id,          // TEXT (user_...)
            clerk_id: clerkUser.id,    // TEXT
            email: email,
            full_name: clerkUser.fullName,
            avatar: clerkUser.imageUrl,
            role: finalRole,
            status: 'active',
            last_active_at: new Date()
        }, { onConflict: 'id' })
        .select()
        .single();

    if (error) {
        console.error("❌ LỖI ĐỒNG BỘ SUPABASE:", error);
        // Nếu lỗi 400 ở đây -> Do Database chưa hiểu ID là Text
        showToast("Lỗi đồng bộ dữ liệu: " + error.message, "error");
    } else {
        console.log("✅ Đồng bộ thành công! Role:", dbUser.role);
        currentUserRole = dbUser.role;
        
        const roleEl = document.getElementById('clerk-user-role');
        if (roleEl) {
            roleEl.innerText = currentUserRole === 'admin' ? 'Admin' : 
                               currentUserRole === 'employee' ? 'Employee' : 'Customer';
        }
        showToast(`Xin chào ${clerkUser.firstName}!`, "success");
    }
}

function handleLogoutSuccess() {
    document.getElementById('dashboard-container').classList.add('hidden');
    document.getElementById('auth-landing').classList.remove('hidden');
    location.reload();
}

// --- 3. MODULE & UI LOGIC ---

function toggleSubmenu(moduleId, element) {
    const subMenu = document.getElementById(`sub-${moduleId}`);
    const chevron = document.getElementById(`chevron-${moduleId}`);

    if (subMenu) {
        const isHidden = subMenu.classList.contains('hidden');
        document.querySelectorAll('[id^="sub-"]').forEach(menu => {
            if (menu.id !== `sub-${moduleId}`) {
                menu.classList.add('hidden');
                const otherModuleId = menu.id.replace('sub-', '');
                const otherChevron = document.getElementById(`chevron-${otherModuleId}`);
                if (otherChevron) {
                    otherChevron.setAttribute('data-lucide', 'chevron-right');
                    lucide.createIcons();
                }
            }
        });

        if (isHidden) {
            subMenu.classList.remove('hidden');
            if (chevron) {
                chevron.setAttribute('data-lucide', 'chevron-down');
                lucide.createIcons();
            }
            const firstSub = MODULE_CONFIG.find(m => m.id === moduleId)?.subs?.[0];
            if (firstSub) loadModule(moduleId, firstSub.id);
        } else {
            subMenu.classList.add('hidden');
            if (chevron) {
                chevron.setAttribute('data-lucide', 'chevron-right');
                lucide.createIcons();
            }
        }
    } else {
        loadModule(moduleId);
    }
}

function initDashboardModules() {
    const menu = document.getElementById('sidebar-menu');
    const visibleModules = MODULE_CONFIG.filter(mod => {
        if (mod.roles.includes('all')) return true;
        if (currentUserRole === 'admin') return true;
        if (currentUserRole === 'employee' && mod.roles.includes('staff')) return true;
        return mod.roles.includes(currentUserRole);
    });

    menu.innerHTML = visibleModules.map(mod => {
        let subMenuHtml = '';
        if (mod.subs && mod.subs.length > 0) {
            subMenuHtml = `
                <div id="sub-${mod.id}" class="hidden flex-col bg-slate-900 border-l border-slate-700 ml-6 my-1 space-y-1 transition-all">
                    ${mod.subs.map(sub => `
                        <div onclick="event.stopPropagation(); loadModule('${mod.id}', '${sub.id}')"
                             id="menu-${sub.id}"
                             class="text-xs text-slate-400 hover:text-white px-3 py-2 cursor-pointer rounded hover:bg-slate-800 transition-colors sidebar-text">
                            ${sub.title}
                        </div>
                    `).join('')}
                </div>
            `;
        }

        return `
            <div class="flex flex-col">
                <div onclick="toggleSubmenu('${mod.id}', this)" 
                    id="menu-${mod.id}"
                    class="flex items-center gap-3 px-4 py-3 cursor-pointer border-l-4 border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-all mb-1">
                    <i data-lucide="${mod.icon}" class="w-5 h-5 shrink-0"></i>
                    <span class="sidebar-text font-medium text-sm truncate flex-1">${mod.title}</span>
                    ${mod.subs ? '<i data-lucide="chevron-right" class="w-4 h-4 sidebar-text opacity-50 transition-transform" id="chevron-' + mod.id + '"></i>' : ''}
                </div>
                ${subMenuHtml}
            </div>
        `;
    }).join('');

    lucide.createIcons();
    safeOverlayScrollbars(document.getElementById('sidebar-scroll-area'), { scrollbars: { theme: 'os-theme-dark' } });
    safeOverlayScrollbars(document.getElementById('main-scroll-area'), { scrollbars: { theme: 'os-theme-dark' } });

    if (currentUserRole === 'admin' || currentUserRole === 'staff') {
        loadModule('01_users');
    } else {
        loadModule('04_ai_core');
    }
}

// --- 🔥 HÀM LOAD MODULE (ĐÃ SỬA: HỖ TRỢ REACT JSX CHO FEEDBACK) ---
async function loadModule(moduleId, subTabId = null) {
    const config = MODULE_CONFIG.find(m => m.id === moduleId);
    if (!config) return;

    // 1. Highlight UI
    document.querySelectorAll('[id^="menu-"]').forEach(el => {
        if (!el.id.includes(moduleId)) {
            el.className = "flex items-center gap-3 px-4 py-3 cursor-pointer border-l-4 border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-all mb-1";
        }
    });

    const menuItem = document.getElementById(`menu-${moduleId}`);
    if (menuItem) {
        menuItem.className = "flex items-center gap-3 px-4 py-3 cursor-pointer border-l-4 border-blue-500 bg-slate-800 text-white font-medium transition-all mb-1";
    }

    const subMenu = document.getElementById(`sub-${moduleId}`);
    if (subMenu) {
        subMenu.querySelectorAll('div').forEach(el => el.classList.remove('text-blue-400', 'font-bold'));
        if (subTabId) {
            const activeSub = document.getElementById(`menu-${subTabId}`);
            if (activeSub) activeSub.classList.add('text-blue-400', 'font-bold');
        }
    }

    // 2. Load Content
    if (state.activeModuleId !== moduleId) {
        document.getElementById('page-title').innerText = config.title;
        document.getElementById('page-desc').innerText = config.desc;

        const contentArea = document.getElementById('module-content-area');

        // Xử lý riêng cho Statistic (iframe)
        if (moduleId === '08_statistics') {
            contentArea.classList.add('p-0', 'h-full');
            contentArea.innerHTML = `
                <div class="h-full w-full">
                    <iframe src="http://127.0.0.1:8000/survey/" 
                            class="w-full h-full border-0 absolute inset-0" 
                            frameborder="0" 
                            style="width: calc(100% - 1rem); height: calc(100% - 1rem); margin: 0.5rem;"
                            allowfullscreen>
                    </iframe>
                </div>`;
            state.activeModuleId = moduleId;
            return;
        } else {
            contentArea.classList.remove('p-0');
        }

        contentArea.innerHTML = `<div class="flex justify-center p-10"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>`;

        try {
            // A. Load HTML
            const htmlResponse = await fetch(`dashboard_html/${config.path}.html?v=${Date.now()}`);
            if (!htmlResponse.ok) throw new Error(`HTTP error! status: ${htmlResponse.status}`);
            contentArea.innerHTML = await htmlResponse.text();

            // B. Load CSS
            const oldLink = document.getElementById('module-css');
            if (oldLink) oldLink.remove();
            const link = document.createElement('link');
            link.id = 'module-css';
            link.rel = 'stylesheet';
            link.href = `dashboard_css/${config.path}.css?v=${Date.now()}`;
            document.head.appendChild(link);

            // C. Load JS (Xử lý đặc biệt cho React JSX)
            const oldScript = document.getElementById('module-js');
            if (oldScript) oldScript.remove();

            // >>> LOGIC MỚI CHO FEEDBACK MODULE <<<
            if (moduleId === '06_feedback') {
                console.log("⚛️ Phát hiện Module React: Đang kích hoạt Babel...");

                // 1. Đảm bảo thư viện React/Babel đã có
                if (!window.React || !window.ReactDOM || !window.Babel) {
                    console.log("📥 Đang tải thư viện React & Babel...");
                    await loadScript("https://unpkg.com/react@18/umd/react.production.min.js");
                    await loadScript("https://unpkg.com/react-dom@18/umd/react-dom.production.min.js");
                    await loadScript("https://unpkg.com/@babel/standalone/babel.min.js");
                }

                // 2. Tải File JS dưới dạng TEXT (Không chạy ngay)
                const jsPath = `dashboard_js/${config.path}.js?v=${Date.now()}`;
                const jsResponse = await fetch(jsPath);
                if (!jsResponse.ok) throw new Error(`Không tìm thấy file JS: ${jsPath}`);
                
                const jsxCode = await jsResponse.text();

                // 3. Dùng Babel biên dịch JSX -> JS thường
                try {
                    const compiledCode = Babel.transform(jsxCode, { presets: ['react', 'es2015'] }).code;
                    console.log("✅ Biên dịch JSX thành công!");

                    // 4. Chạy code đã biên dịch
                    const script = document.createElement('script');
                    script.id = 'module-js';
                    script.textContent = compiledCode;
                    document.body.appendChild(script);
                } catch (babelErr) {
                    console.error("❌ Lỗi biên dịch Babel:", babelErr);
                    contentArea.innerHTML = `<div class="text-red-500 p-4">Lỗi Code React: ${babelErr.message}</div>`;
                }

            } else {
                // >>> LOGIC CŨ CHO CÁC MODULE KHÁC <<<
                const script = document.createElement('script');
                script.id = 'module-js';
                script.src = `dashboard_js/${config.path}.js?v=${Date.now()}`;
                script.onload = () => {
                    setTimeout(() => {
                        if (window.lucide) lucide.createIcons();
                        if (subTabId && moduleId === '01_users' && window.UsersModule) {
                            window.UsersModule.switchTab(subTabId);
                        }
                    }, 100);
                };
                document.body.appendChild(script);
            }

            state.activeModuleId = moduleId;

        } catch (error) {
            contentArea.innerHTML = `<div class="text-red-500 p-4 border border-red-200 bg-red-50 rounded">Lỗi tải module: ${error.message}.</div>`;
        }
    } else {
        if (subTabId && moduleId === '01_users' && window.UsersModule) {
            window.UsersModule.switchTab(subTabId);
        }
    }
}

// UI Helpers
window.toggleSidebar = () => {
    state.sidebarOpen = !state.sidebarOpen;
    const sb = document.getElementById('sidebar');
    sb.style.width = state.sidebarOpen ? '300px' : '70px';
    document.querySelectorAll('.sidebar-text').forEach(t => t.style.display = state.sidebarOpen ? 'block' : 'none');
    if (!state.sidebarOpen) document.querySelectorAll('[id^="sub-"]').forEach(el => el.classList.add('hidden'));
};

const safeOverlayScrollbars = (element, options) => {
    if (typeof window.OverlayScrollbarsGlobal !== 'undefined' && window.OverlayScrollbarsGlobal.OverlayScrollbars) return window.OverlayScrollbarsGlobal.OverlayScrollbars(element, options);
    element.classList.add('overflow-y-auto');
    return null;
};
function showToast(msg, type) {
    const container = document.getElementById('toast-container');
    const div = document.createElement('div');
    div.className = `toast ${type === 'success' ? 'bg-green-600' : 'bg-blue-600'} text-white px-4 py-3 rounded-lg shadow-xl flex items-center gap-3 min-w-[250px] toast-enter`;
    div.innerHTML = `<span class="text-sm font-medium">${msg}</span>`;
    container.appendChild(div);
    setTimeout(() => { div.classList.remove('toast-enter'); div.classList.add('toast-enter-active'); }, 10);
    setTimeout(() => div.remove(), 3000);
}

document.addEventListener('DOMContentLoaded', initApp);