// Logic xử lý toggle switch (nếu cần)
document.querySelectorAll('input[type="checkbox"]').forEach(i => {
    i.addEventListener('change', (e) => {
        console.log("Setting changed:", e.target.checked);
    });
});