import re

html_path = 'app/static/notifications.html'

with open(html_path, 'r') as f:
    content = f.read()

# 1. Add the Saved Notifications global button to the header
SAVED_BTN = """            <button onclick="toggleSavedModal(true)" class="bg-primary/10 hover:bg-primary/20 text-primary dark:text-primary-light px-3 py-1.5 rounded-md text-sm transition-colors border border-primary/20 flex items-center gap-2 font-medium">
                <i data-lucide="bookmark" class="w-4 h-4"></i>
                <span class="hidden sm:inline">Salvas</span>
            </button>"""

if "toggleSavedModal(true)" not in content:
    # insert before configBtn
    content = content.replace('<button id="configBtn"', SAVED_BTN + '\n            <button id="configBtn"')

# 2. Add Like/Dislike click handlers to the notification evaluation buttons
if "onclick=\"saveNotification('like')\"" not in content:
    content = content.replace('title="Boa notificação">', 'title="Boa notificação" onclick="saveNotification(\'like\')">')
    content = content.replace('title="Notificação ruim">', 'title="Notificação ruim" onclick="saveNotification(\'dislike\')">')

# 3. Add the Saved Notifications Modal HTML at the end of the body
SAVED_MODAL_HTML = """
    <-c Saved Notifications Modal -->
    <div id="savedModal" class="fixed inset-0 z-50 hidden">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onclick="toggleSavedModal(false)"></div>
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl max-h-[85vh] flex flex-col p-6">
            <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-border dark:border-slate-700 h-full">
                
                <-c Header -->
                <div class="p-6 border-b border-border dark:border-slate-700 flex flex-col md:flex-row md:items-center justify-between gap-4 shrink-0 bg-gray-50 dark:bg-slate-800/50">
                    <div>
                        <h3 class="text-xl font-bold text-text dark:text-white flex items-center gap-2">
                            <i data-lucide="bookmark" class="w-5 h-5 text-primary"></i> 
                            Notificações Salvas
                        </h3>
                        <p class="text-sm text-text-light dark:text-gray-400 mt-1">Histórico de mensagens avaliadas durante os testes.</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="clearSaved()" class="text-xs text-danger hover:bg-danger/10 px-3 py-1.5 rounded transition-colors flex items-center gap-1">
                            <i data-lucide="trash-2" class="w-3 h-3"></i> Limpar Todas
                        </button>
                        <button onclick="toggleSavedModal(false)" class="text-text-light hover:text-text dark:hover:text-white p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-slate-700 transition-colors">
                            <i data-lucide="x" class="w-5 h-5"></i>
                        </button>
                    </div>
                </div>

                <-c Tabs -->
                <div class="flex border-b border-border dark:border-slate-700 shrink-0">
                    <button onclick="switchTab('like')" id="tab-like" class="flex-1 py-3 text-sm font-medium border-b-2 border-primary text-primary transition-colors flex items-center justify-center gap-2">
                        <i data-lucide="thumbs-up" class="w-4 h-4"></i> Aprovadas (<span id="count-like">0</span>)
                    </button>
                    <button onclick="switchTab('dislike')" id="tab-dislike" class="flex-1 py-3 text-sm font-medium border-b-2 border-transparent text-text-light hover:text-text dark:hover:text-gray-200 transition-colors flex items-center justify-center gap-2">
                        <i data-lucide="thumbs-down" class="w-4 h-4"></i> Reprovadas (<span id="count-dislike">0</span>)
                    </button>
                </div>

                <-c List Content -->
                <div class="p-6 overflow-y-auto flex-1 bg-gray-50/50 dark:bg-slate-900/20" id="savedListContainer">
                    <-c Populated via JS -->
                </div>
            </div>
        </div>
    </div>
"""
if "id=\"savedModal\"" not in content:
    content = content.replace('</body>', SAVED_MODAL_HTML + '\n</body>')


# 4. Add the JavaScript logic for handling saving and rendering
JS_LOGIC = """
        // ==========================================
        // Saved Notifications Manager
        // ==========================================
        let currentTab = 'like';
        
        function getSavedNotifications() {
            try {
                return JSON.parse(localStorage.getItem('savedNotifications')) || [];
            } catch(e) { return []; }
        }

        function saveNotification(type) {
            const contentText = document.getElementById('notifContent').textContent;
            const personaText = document.getElementById('notifPersonaName').textContent;
            const modelText = document.getElementById('modelUsedTag').textContent.replace('Modelo: ', '');
            
            if(!contentText) return;

            const savedList = getSavedNotifications();
            
            const newItem = {
                id: Date.now().toString(),
                type: type, // 'like' or 'dislike'
                content: contentText,
                persona: personaText,
                model: modelText,
                date: new Date().toLocaleString()
            };
            
            savedList.unshift(newItem); // Add to beginning
            localStorage.setItem('savedNotifications', JSON.stringify(savedList));
            
            // Visual feedback
            const btn = type === 'like' ? document.querySelector('[title="Boa notificação"]') : document.querySelector('[title="Notificação ruim"]');
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<i data-lucide="check" class="w-4 h-4 text-green-500"></i>`;
            lucide.createIcons();
            
            // Render to update counts if modal was opened before
            renderSavedList();
            
            setTimeout(() => {
                btn.innerHTML = originalHtml;
                lucide.createIcons();
            }, 1000);
        }

        function toggleSavedModal(show) {
            document.getElementById('savedModal').classList.toggle('hidden', !show);
            if(show) { 
                renderSavedList(); 
                switchTab(currentTab); // Ensure UI reflects state
            }
        }

        function switchTab(tab) {
            currentTab = tab;
            const tabLike = document.getElementById('tab-like');
            const tabDislike = document.getElementById('tab-dislike');
            
            if(tab === 'like') {
                tabLike.classList.add('border-primary', 'text-primary');
                tabLike.classList.remove('border-transparent', 'text-text-light');
                tabDislike.classList.remove('border-danger', 'text-danger');
                tabDislike.classList.add('border-transparent', 'text-text-light');
            } else {
                tabDislike.classList.add('border-danger', 'text-danger');
                tabDislike.classList.remove('border-transparent', 'text-text-light');
                tabLike.classList.remove('border-primary', 'text-primary');
                tabLike.classList.add('border-transparent', 'text-text-light');
            }
            renderSavedList();
        }

        function deleteSaved(id) {
            let list = getSavedNotifications();
            list = list.filter(item => item.id !== id);
            localStorage.setItem('savedNotifications', JSON.stringify(list));
            renderSavedList();
        }

        function clearSaved() {
            if(confirm("Tem certeza que deseja apagar TODAS as notificações salvas permanentemente?")) {
                localStorage.removeItem('savedNotifications');
                renderSavedList();
            }
        }

        function renderSavedList() {
            const container = document.getElementById('savedListContainer');
            if(!container) return;
            
            const allSaved = getSavedNotifications();
            const filtered = allSaved.filter(item => item.type === currentTab);
            
            // Update Counts
            document.getElementById('count-like').textContent = allSaved.filter(i => i.type === 'like').length;
            document.getElementById('count-dislike').textContent = allSaved.filter(i => i.type === 'dislike').length;
            
            if(filtered.length === 0) {
                container.innerHTML = `
                    <div class="flex flex-col items-center justify-center h-full text-gray-400 py-12">
                        <i data-lucide="inbox" class="w-12 h-12 mb-3 opacity-50"></i>
                        <p>Nenhuma notificação salva nesta categoria.</p>
                    </div>`;
                lucide.createIcons();
                return;
            }

            container.innerHTML = filtered.map(item => `
                <div class="bg-white dark:bg-slate-800 p-4 rounded-xl border border-border dark:border-slate-700 mb-4 shadow-sm relative group">
                    <button onclick="deleteSaved('${item.id}')" class="absolute top-3 right-3 text-gray-400 hover:text-danger opacity-0 group-hover:opacity-100 transition-opacity" title="Excluir">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                    
                    <div class="flex items-center gap-3 mb-2 pr-6">
                        <span class="text-xs font-semibold bg-primary/10 text-primary dark:text-primary-light px-2 py-1 rounded">
                            ${item.persona}
                        </span>
                        <span class="text-xs text-text-light dark:text-gray-400">
                            ${item.date}
                        </span>
                    </div>
                    
                    <p class="text-sm text-text dark:text-gray-200 mb-3 whitespace-pre-wrap leading-relaxed">${item.content}</p>
                    
                    <div class="flex border-t border-border dark:border-slate-700 pt-3">
                        <span class="text-[11px] text-text-light dark:text-gray-500 flex items-center gap-1">
                            <i data-lucide="cpu" class="w-3 h-3"></i> Modelo: ${item.model}
                        </span>
                    </div>
                </div>
            `).join('');
            
            lucide.createIcons();
        }
"""
if "getSavedNotifications()" not in content:
    content = content.replace('// Modal Logic', JS_LOGIC + '\n        // Modal Logic')

with open(html_path, 'w') as f:
    f.write(content)

