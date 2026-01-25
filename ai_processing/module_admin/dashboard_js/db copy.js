// js/db.js

// 1. THAY THÔNG TIN CỦA BẠN VÀO ĐÂY (Lấy ở Bước 1.2 và 1.3)
const SUPABASE_URL = ''; 
const SUPABASE_ANON_KEY = ''; 

// 2. Client Supabase mặc định (dùng khi chưa login)
const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// 3. Hàm lấy Client Supabase ĐÃ ĐĂNG NHẬP (Authenticated)
// Hàm này sẽ tự động xin Clerk cái Token rồi gắn vào Supabase
async function getAuthenticatedSupabase() {
    if (!window.Clerk || !window.Clerk.session) {
        console.warn("Chưa đăng nhập Clerk!");
        return supabase;
    }

    // Xin Token từ Clerk (Template tên là 'supabase' đã tạo ở Phần 2)
    const clerkToken = await window.Clerk.session.getToken({ template: 'supabase' });

    // Tạo kết nối mới kèm Token
    return window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        global: {
            headers: { Authorization: `Bearer ${clerkToken}` },
        },
    });
}