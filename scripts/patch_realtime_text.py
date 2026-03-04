import re

POLL_SCRIPT_NEW = """
        // Real-time API Status Updater
        async function pollHealthStatus() {
            const dots = document.querySelectorAll('.api-status-dot');
            const texts = document.querySelectorAll('.api-status-text');
            try {
                const res = await fetch('/health');
                const data = await res.json();
                const isOk = data.status === 'ok';
                const color = isOk ? 'bg-success' : 'bg-danger';
                const pulse = isOk ? 'animate-pulse' : '';
                const title = isOk ? `API Online (${data.provider})` : 'Erro na API';
                
                dots.forEach(dot => {
                    dot.className = `api-status-dot w-3 h-3 rounded-full ${color} ${isOk ? '' : 'animate-pulse'} shadow-sm cursor-help`;
                    dot.title = title;
                });

                texts.forEach(t => {
                    t.textContent = isOk ? data.model : 'Erro';
                    t.className = `api-status-text text-xs mr-2 font-medium ${isOk ? 'text-text-light' : 'text-danger'}`;
                });
                
                // Also update the modal if it's open
                const statusEl = document.getElementById('healthStatusText');
                if(statusEl) {
                    if(isOk) {
                        statusEl.textContent = `Online (${data.provider} - ${data.model})`;
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
                texts.forEach(t => {
                    t.textContent = 'Offline';
                    t.className = `api-status-text text-xs mr-2 font-medium text-danger`;
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
        
    # Replace the old JS script
    # To do so we'll just slice out everything between // Real-time API Status Updater and // Poll every 15 seconds... setInterval
    old_script_pattern = re.compile(r'// Real-time API Status Updater.*setInterval\(pollHealthStatus, 15000\);', re.DOTALL)
    
    if old_script_pattern.search(content):
        content = old_script_pattern.sub(POLL_SCRIPT_NEW.strip(), content)
    else:
        print("Couldn't find old polling script in", filepath)
        return

    # Replace the HTML dot
    old_html_dot = '<div class="api-status-dot w-3 h-3 rounded-full bg-gray-400 shadow-sm cursor-help" title="Verificando API..."></div>'
    new_html_dot = '<span class="api-status-text text-xs mr-2 font-medium text-text-light">Verificando...</span>\n        <div class="api-status-dot w-3 h-3 rounded-full bg-gray-400 shadow-sm cursor-help" title="Verificando API..."></div>'
    
    content = content.replace(old_html_dot, new_html_dot)
        
    with open(filepath, 'w') as f:
        f.write(content)

patch_file('app/static/index.html', is_index=True)
patch_file('app/static/notifications.html', is_index=False)
patch_file('app/static/rag.html', is_index=False)
