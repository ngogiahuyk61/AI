// dashboard_js/01_users.js
console.log("🚀 Module 01: User Management (Advanced Hybrid Sync V2) Loaded.");

window.UsersModule = {
    // --- 1. CONFIGURATION ---
    erpConfig: {
        url: "http://localhost:8080",
        apiKey: "744a146da7db682",       // ✅ Keep your API Key
        apiSecret: "5942607d474b5e0",    // ✅ Keep your Secret
        company: "Gia Huy Corp"          // ✅ Keep your Company Name
    },

    // --- 2. INITIALIZATION ---
    init: async function() {
        console.log("1. Init Users Module...");
        
        // Tự động kiểm tra: Nếu User đang login là Khách mới -> Đẩy sang ERPNext Customer ngay
        await this.autoSyncCurrentCustomer();
    },

    // --- 3. UI LOGIC: TAB SWITCHING (IFRAME MANAGER) ---
    switchTab: function(tabId) {
        // Ẩn tất cả tab
        document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
        
        // Hiện tab được chọn
        const target = document.getElementById(tabId);
        if(target) target.classList.remove('hidden');

        // Reset style buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active-tab', 'text-slate-900', 'bg-white', 'shadow-sm', 'border-gray-200');
            btn.classList.add('text-gray-500', 'border-transparent');
        });
        
        // Active style cho button được chọn
        const activeBtn = Array.from(document.querySelectorAll('.tab-btn'))
            .find(b => b.getAttribute('onclick').includes(tabId));
        
        if(activeBtn) {
            activeBtn.classList.remove('text-gray-500', 'border-transparent');
            activeBtn.classList.add('active-tab', 'text-slate-900', 'bg-white', 'shadow-sm', 'border-gray-200');
        }
    },

// --- 4. CORE FEATURE: SYNC STAFF FROM ERPNEXT (ERP -> SUPABASE) ---
    // Hàm này được gọi khi bấm nút "Sync Staff" trên giao diện
    syncStaffFromERP: async function() {
        if(typeof showToast === "function") showToast("⏳ Đang kết nối ERPNext để lấy danh sách nhân sự...", "info");
        
        try {
            // 1. NÂNG CẤP API QUERY: Lấy thêm trường 'user_id' và 'company_email'
            // 'user_id' trong ERPNext chính là Email đăng nhập (User ID) liên kết với hồ sơ Employee
            const response = await fetch(`${this.erpConfig.url}/api/resource/Employee?fields=["name","employee_name","personal_email","company_email","user_id","status","designation"]&limit_page_length=100`, {
                headers: { 'Authorization': `token ${this.erpConfig.apiKey}:${this.erpConfig.apiSecret}` }
            });

            if (!response.ok) throw new Error("Không thể kết nối ERPNext (Kiểm tra lại mạng hoặc API Key)");
            const data = await response.json();
            const employees = data.data || [];

            if(employees.length === 0) {
                alert("ERPNext chưa có dữ liệu nhân viên nào!");
                return;
            }

            // 2. XỬ LÝ DỮ LIỆU & LƯU VÀO SUPABASE
            const client = await getAuthenticatedSupabase();
            let count = 0;
            let skipped = 0;

            console.log(`🔍 Tìm thấy ${employees.length} hồ sơ nhân viên từ ERPNext.`);

            for (const emp of employees) {
                // --- LOGIC TÌM EMAIL THÔNG MINH (FALLBACK STRATEGY) ---
                // Ưu tiên 1: Email cá nhân (Personal Email)
                // Ưu tiên 2: Email công ty (Company Email)
                // Ưu tiên 3: User ID (Đây là trường quan trọng nhất, thường chứa email đăng nhập pka3008@gmail.com)
                const finalEmail = emp.personal_email || emp.company_email || emp.user_id;

                // Chỉ xử lý nếu tìm thấy một địa chỉ email hợp lệ (có chứa @)
                if(finalEmail && finalEmail.includes('@')) { 
                    const { error } = await client.from('users').upsert({
                        email: finalEmail,             // Lưu email tìm được làm khóa chính
                        full_name: emp.employee_name,
                        job_title: emp.designation || 'Staff',
                        role_id: 'd4167981-b0d1-4f41-9847-faa400033f97',                  // Mặc định gán Role ID = 1 (Staff)
                        status: emp.status === 'Active' ? 'active' : 'inactive',
                        // Lưu ý: Không ghi đè clerk_id để tránh mất liên kết nếu họ đã đăng ký Clerk
                    }, { onConflict: 'email' });
                    
                    if(!error) {
                        count++;
                        console.log(`✅ Synced: ${emp.employee_name} -> ${finalEmail}`);
                    } else {
                        console.error(`❌ Lỗi lưu DB cho ${finalEmail}:`, error.message);
                    }
                } else {
                    skipped++;
                    console.warn(`⚠️ Bỏ qua nhân viên: ${emp.employee_name} (Không tìm thấy Email trong hồ sơ)`);
                }
            }

            // 3. THÔNG BÁO KẾT QUẢ CHI TIẾT
            if(typeof showToast === "function") {
                if (count > 0) {
                    showToast(`✅ Đã đồng bộ thành công ${count} nhân viên! (Bỏ qua ${skipped} hồ sơ thiếu email)`, "success");
                } else {
                    showToast(`⚠️ Không đồng bộ được ai. Kiểm tra lại dữ liệu Email trong ERPNext!`, "error");
                }
            }
            
        } catch (err) {
            console.error("Critical Sync Error:", err);
            alert("Lỗi Sync Staff: " + err.message);
        }
    },

    // --- 5. CORE FEATURE: AUTO SYNC CUSTOMER (CLERK -> ERPNEXT) ---
    // Hàm này chạy ngầm khi User login
    autoSyncCurrentCustomer: async function() {
        if (!window.Clerk?.user) return;
        const user = window.Clerk.user;
        const email = user.primaryEmailAddress.emailAddress;
        
        // Logic: Gọi API tạo Customer bên ERPNext. 
        // Nếu đã có rồi, ERPNext sẽ trả về lỗi "Duplicate" -> Ta bỏ qua lỗi đó.
        try {
            await this.syncToERPCustomer(user.fullName || "New Customer", email, "");
        } catch(e) {
            // Chỉ log warning chứ không alert để tránh làm phiền user
            console.warn("Auto-sync Customer status:", e.message);
        }
    },

    // --- 6. MANUAL ACTION: DRAWER SAVE (HYBRID SYNC) ---
    // Dùng cho nút "Invite Customer" hoặc thêm Staff thủ công
    saveUser: async function() {
        // 6.1. Lấy dữ liệu Form
        const userType = document.getElementById('sel-user-type').value;
        const fullName = document.getElementById('inp-name').value;
        const email = document.getElementById('inp-email').value;
        const phone = document.getElementById('inp-phone').value;
        const jobTitle = document.getElementById('inp-title').value;

        if (!fullName || !email) { alert("Thiếu tên hoặc email!"); return; }

        const client = await getAuthenticatedSupabase();
        
        // 6.2. Lưu vào Supabase trước (Source of Authentication Data)
        const { error } = await client.from('users').upsert({
            email: email,
            full_name: fullName,
            phone: phone,
            job_title: jobTitle,
            status: 'pending', // Trạng thái chờ họ tự login Clerk để active
            clerk_id: 'invite_' + Date.now() // Placeholder ID
        }, { onConflict: 'email' });

        if (error) { alert("Lỗi Supabase: " + error.message); return; }

        // 6.3. Đẩy sang ERPNext (Source of Business Data)
        if(typeof showToast === "function") showToast("Supabase OK. Syncing ERPNext...", "info");
        
        try {
            if (userType === 'employee') {
                // Cảnh báo quy trình chuẩn
                const confirmERP = confirm("⚠️ QUY TRÌNH CHUẨN: Staff nên được tạo từ ERPNext trước rồi bấm 'Sync Staff'.\nBạn có chắc muốn tạo từ đây không?");
                if(confirmERP) {
                    await this.syncToERPEmployee(fullName, email, jobTitle, "2000-01-01");
                }
            } else {
                // Customer thì thoải mái
                await this.syncToERPCustomer(fullName, email, phone);
            }
            
            // Reload Iframe để thấy dữ liệu mới
            const iframe = document.getElementById('ifrm-users');
            if(iframe) iframe.src = iframe.src; 

        } catch (err) {
            alert("Lỗi ERPNext: " + err.message);
        }

        this.closeDrawer();
        this.resetForm();
    },

    // --- 7. API HELPERS (ERP CONNECTORS) ---
    
    // Tạo Nhân viên
    syncToERPEmployee: async function(fullName, email, jobTitle, dob) {
        const nameParts = fullName.trim().split(' ');
        const firstName = nameParts.pop();
        const lastName = nameParts.join(' ');

        const response = await fetch(`${this.erpConfig.url}/api/resource/Employee`, {
            method: 'POST',
            headers: {
                'Authorization': `token ${this.erpConfig.apiKey}:${this.erpConfig.apiSecret}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                "first_name": firstName || fullName,
                "last_name": lastName,
                "company": this.erpConfig.company,
                "status": "Active",
                "gender": "Male",
                "date_of_birth": dob,
                "date_of_joining": new Date().toISOString().split('T')[0],
                "personal_email": email,
                "designation": jobTitle
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.exception ? data.exception.split(':').pop() : "ERP Error");
        if (typeof showToast === "function") showToast("✅ Staff Created in ERPNext!", "success");
    },

    // Tạo Khách hàng
    syncToERPCustomer: async function(fullName, email, phone) {
        const response = await fetch(`${this.erpConfig.url}/api/resource/Customer`, {
            method: 'POST',
            headers: {
                'Authorization': `token ${this.erpConfig.apiKey}:${this.erpConfig.apiSecret}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                "customer_name": fullName,
                "customer_type": "Individual",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
                "email_id": email,
                "mobile_no": phone
            })
        });
        const data = await response.json();
        // Bỏ qua lỗi nếu Customer đã tồn tại (Duplicate Name/Email)
        if (!response.ok && !JSON.stringify(data).includes("exists") && !JSON.stringify(data).includes("Duplicate")) {
            throw new Error(data.exception ? data.exception.split(':').pop() : "ERP Error");
        }
        if (response.ok && typeof showToast === "function") showToast("✅ Customer Synced to ERPNext!", "success");
    },

    // --- 8. DRAWER UI UTILS ---
    openDrawer: function() {
        document.getElementById('user-drawer').classList.remove('hidden');
        setTimeout(() => document.getElementById('user-drawer-content').classList.remove('translate-x-full'), 10);
    },
    closeDrawer: function() {
        document.getElementById('user-drawer-content').classList.add('translate-x-full');
        setTimeout(() => document.getElementById('user-drawer').classList.add('hidden'), 300);
        this.resetForm();
    },
    resetForm: function() {
        document.querySelectorAll('#user-drawer input').forEach(i => i.value = '');
        const selType = document.getElementById('sel-user-type');
        if(selType) selType.value = 'customer';
        const divDob = document.getElementById('div-dob');
        if(divDob) divDob.classList.add('hidden');
    }
};

// Start the module
UsersModule.init();