const SystemModule = {
    clearCache: () => {
        const logs = document.getElementById('log-container');
        logs.innerHTML += `<div class="flex gap-4"><span class="text-slate-500 w-20">NOW</span><span class="text-green-400 w-20">SUCCESS</span><span>Cache cleared successfully.</span></div>`;
        logs.scrollTop = logs.scrollHeight;
    }
};