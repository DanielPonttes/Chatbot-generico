import re

POLL_SCRIPT = """
        // Real-time API Status Updater
        async function pollHealthStatus() {
            const dots = document.querySelectorAll('.api-status-dot');
            try {
                const res = await fetch('/health');
                const data = await res.json();
                const isOk = data.status === 'ok';
                const color = isOk ? 'bg-success' : 'bg-danger';
                const pulse = isOk ? 'animate-pulse' : '';
                const title = isOk ? `API Online (${data.provider})` : 'Erro na API';
                
                dots.forEach(dot => {
                    // Update classes preserving base layout
                    dot.className = `api-status-dot w-3 h-3 rounded-full ${color} ${isOk ? '' : 'animate-pulse'} shadow-sm cursor-help`;
                    dot.title = title;
                });
                
                // Also update the modal if it's open
                const statusEl = document.getElementById('healthStatusText');
                if(statusEl) {
                    if(isOk) {
                        statusEl.textContent = `Online (${data.provider})`;
                        statusEl.className = "text-xs text-success font-medium";
                    } else {
                        statusEl.textContent = "Problemas detectados";
                        statusEl.className = "text-xs text-danger font-medium";
                    }
                }
            } catch(e) {
                dots.forEach(dot => {
                    dot.className = `api-status-dot w-3 h-3 rounded-full bg-danger shadow-sm cursor-help`;
                    dot.title = 'Offline / Sem Conexão';
                });
                const statusEl = document.getElementById('healthStatusText');
                if(statusEl) {
                    statusEl.textContent = "Falha ao conectar";
                    statusEl.className = "text-xs text-danger font-medium";
                }
            }
        }
        
        // Poll every 15 seconds, and once on load
        pollHealthStatus();
        setInterval(pollHealthStatus, 15000);
"""

def patch_file(filepath, is_index=False):
    with open(filepath, 'r') as f:
        content = f.read()
        
    if "pollHealthStatus" in content:
        return # already patched

    # Inject script before setTimeout lucide
    content = content.replace("setTimeout(() => { if(window.lucide)", POLL_SCRIPT + "\n        setTimeout(() => { if(window.lucide)")
    
    # 1. Index.html patch
    if is_index:
        old_button = """    <!-- Global Settings Button (Fixed Top Right) -->
    <button onclick="toggleGlobalModal(true)" class="fixed top-4 right-4 z-40 bg-white/80 backdrop-blur border border-border text-text p-2 rounded-full shadow-md hover:bg-gray-50 transition-colors">
        <i data-lucide="settings" class="w-5 h-5"></i>
    </button>"""
        
        new_button = """    <!-- Global Settings Button and Real-Time Status -->
    <div class="fixed top-4 right-4 z-40 flex items-center gap-3">
        <div class="api-status-dot w-3 h-3 rounded-full bg-gray-400 shadow-sm cursor-help" title="Verificando API..."></div>
        <button onclick="toggleGlobalModal(true)" class="bg-white/80 backdrop-blur border border-border text-text p-2 rounded-full shadow-md hover:bg-gray-50 transition-colors">
            <i data-lucide="settings" class="w-5 h-5"></i>
        </button>
    </div>"""
        content = content.replace(old_button, new_button)
        
    # 2. Others patch
    else:
        old_header = """        <div class="flex items-center gap-4">
            <button onclick="toggleGlobalModal(true)" class="bg-gray-100 hover:bg-gray-200 text-text p-2 rounded-full transition-colors order-last">
                <i data-lucide="settings" class="w-4 h-4"></i>
            </button>"""
            
        new_header = """        <div class="flex items-center gap-4">
            <-c Indicator API -->
            <div class="api-status-dot w-3 h-3 rounded-full bg-gray-400 shadow-sm cursor-help" title="Verificando API..."></div>
            <button onclick="toggleGlobalModal(true)" class="bg-gray-100 hover:bg-gray-200 text-text p-2 rounded-full transition-colors order-last">
                <i data-lucide="settings" class="w-4 h-4"></i>
            </button>"""
        content = content.replace(old_header, new_header)
        
    with open(filepath, 'w') as f:
        f.write(content)

patch_file('app/static/index.html', is_index=True)
patch_file('app/static/notifications.html', is_index=False)
patch_file('app/static/rag.html', is_index=False)
