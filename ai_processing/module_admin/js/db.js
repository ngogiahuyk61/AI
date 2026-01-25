// js/db.js

// 1. URL thật (Đã điền đúng cho bạn)
const SUPABASE_URL = 'https://fexyylqfnxiyvhkyrylc.supabase.co'; 
const SUPABASE_ANON_KEY = 'sb_publishable_4IREqPoTacRW-Va0w9X_Kg_um-da6BH'; 


// --- KHỞI TẠO CLIENT ---

// [QUAN TRỌNG] Đổi tên biến từ 'supabase' thành 'publicClient' để không lỗi trùng tên
const publicClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

async function getAuthenticatedSupabase() {
    if (!window.Clerk || !window.Clerk.session) {
        console.warn("⚠️ Chưa đăng nhập Clerk! Đang dùng kết nối ẩn danh.");
        return publicClient; // Trả về biến đã đổi tên
    }

    try {
        const clerkToken = await window.Clerk.session.getToken({ template: 'supabase' });

        if (!clerkToken) {
            console.error("❌ Không lấy được Token từ Clerk.");
            return publicClient;
        }

        // Tạo kết nối xác thực
        return window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
            global: {
                headers: { Authorization: `Bearer ${clerkToken}` },
            },
        });

    } catch (error) {
        console.error("❌ Lỗi Auth:", error);
        return publicClient;
    }
}