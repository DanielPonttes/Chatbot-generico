import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    tailwind_script = """    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; background-color: #f8f9fa; color: #2c3e50; }
        .glass-panel { background: #ffffff; border: 1px solid #ecf0f1; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }
        .gradient-text { background: linear-gradient(to right, #218084, #32b8c6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    </style>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: { primary: '#218084', 'primary-light': '#32b8c6', 'primary-dark': '#1a6470', accent: '#e67e22', success: '#27ae60', warning: '#f39c12', danger: '#e74c3c', background: '#f8f9fa', card: '#ffffff', text: '#2c3e50', 'text-light': '#7f8c8d', border: '#ecf0f1' }
                }
            }
        }
    </script>"""

    content = re.sub(r'<style>.*?</style>', tailwind_script, content, flags=re.DOTALL)
    
    replacements = [
        ('bg-slate-900/50', 'bg-white'),
        ('bg-slate-900', 'bg-white'),
        ('bg-slate-800/80', 'bg-white border-border'),
        ('bg-slate-800', 'bg-gray-100'),
        ('bg-slate-950', 'bg-gray-50'),
        ('text-slate-200', 'text-text'),
        ('text-slate-300', 'text-text'),
        ('text-slate-400', 'text-text-light'),
        ('text-slate-500', 'text-gray-400'),
        ('text-white', 'text-text'),
        ('border-slate-700/50', 'border-border'),
        ('border-slate-700', 'border-border'),
        ('text-indigo-400', 'text-primary'),
        ('text-indigo-300', 'text-primary-light'),
        ('bg-indigo-600', 'bg-primary'),
        ('hover:bg-indigo-500', 'hover:bg-primary-light'),
        ('hover:bg-slate-700', 'hover:bg-gray-200'),
        ('bg-indigo-500/10', 'bg-primary/10'),
        ('bg-indigo-500/20', 'bg-primary/10'),
        ('bg-indigo-500/30', 'bg-[rgba(33,128,132,0.3)]'),
        ('border-indigo-500/50', 'border-primary/50'),
        ('border-t-indigo-500', 'border-t-primary'),
        ('ring-indigo-500', 'ring-primary'),
        ('shadow-indigo-500/20', 'shadow-primary/20'),
        ('text-sky-400', 'text-primary'),
        ('text-sky-200', 'text-primary'),
        ('bg-sky-600', 'bg-primary'),
        ('hover:bg-sky-500', 'hover:bg-primary-light'),
        ('border-sky-500/30', 'border-primary/30'),
        ('border-t-sky-500', 'border-t-primary'),
        ('shadow-sky-500/20', 'shadow-primary/20'),
        ('ring-sky-500', 'ring-primary'),
        ('bg-sky-500/20', 'bg-primary/20'),
        ('border-slate-600', 'border-gray-200'),
        ('text-purple-300', 'text-accent'),
        ('bg-slate-900/30', 'bg-gray-50'),
        ('Ir para Chat', 'Voltar ao Início'),
        ('Chat', 'Início'),
    ]

    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w') as f:
        f.write(content)

update_file('app/static/notifications.html')
update_file('app/static/rag.html')
