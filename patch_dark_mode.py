import re

# We will inject the dark mode toggle script directly inside the <head> to avoid white flashes
DARK_INIT_SCRIPT = """    <script>
        // Init Dark Mode before body loads to prevent flash
        if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
        }
    </script>
"""

# The Tailwind configuration must be updated to support dark mode class
TAILWIND_CONFIG_NEW = """    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: { 
                        primary: '#218084', 
                        'primary-light': '#32b8c6', 
                        'primary-dark': '#1a6470', 
                        accent: '#e67e22', 
                        success: '#27ae60', 
                        warning: '#f39c12', 
                        danger: '#e74c3c', 
                        background: '#f8f9fa', 
                        card: '#ffffff', 
                        text: '#2c3e50', 
                        'text-light': '#7f8c8d', 
                        border: '#ecf0f1',
                        // Dark mode specific colors
                        dark: {
                            bg: '#0f172a',
                            card: '#1e293b',
                            text: '#f8fafc',
                            'text-light': '#94a3b8',
                            border: '#334155'
                        }
                    }
                }
            }
        }
    </script>"""

# HTML for the Dark Mode Toggle button
TOGGLE_BUTTON_HTML = """
            <-c Theme Toggle -->
            <button onclick="toggleTheme()" class="bg-gray-100 hover:bg-gray-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-text dark:text-dark-text p-2 rounded-full transition-colors ml-2" title="Alternar Tema Escuro">
                <i data-lucide="moon" class="w-4 h-4 dark:hidden"></i>
                <i data-lucide="sun" class="w-4 h-4 hidden dark:block"></i>
            </button>"""

# Add toggle script at the bottom of the body
TOGGLE_LOGIC_SCRIPT = """        // Theme Toggling Logic
        function toggleTheme() {
            if (document.documentElement.classList.contains('dark')) {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }
        }
"""

def patch_file(filepath, is_index=False):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # 1. Inject Init Script and Update Tailwind Config
    # Check if patched already
    if "darkMode: 'class'" not in content:
        # Update config
        content = re.sub(r'<script>\s*tailwind\.config = {.*?</script>', TAILWIND_CONFIG_NEW, content, flags=re.DOTALL)
        # Inject fast-init script before tailwind config
        content = content.replace(TAILWIND_CONFIG_NEW, DARK_INIT_SCRIPT + TAILWIND_CONFIG_NEW)
    
    # Update CSS classes of the body to support dark background natively
    if "dark:bg-dark-bg" not in content:
        content = content.replace('bg-white', 'bg-white dark:bg-dark-card')
        content = content.replace('bg-gray-50', 'bg-gray-50 dark:bg-slate-800')
        content = content.replace('bg-gray-100', 'bg-gray-100 dark:bg-slate-700')
        content = content.replace('text-text', 'text-text dark:text-dark-text')
        content = content.replace('text-text-light', 'text-text-light dark:text-dark-text-light')
        content = content.replace('border-border', 'border-border dark:border-dark-border')
        content = content.replace('text-gray-800', 'text-gray-800 dark:text-white')
        content = content.replace('text-gray-500', 'text-gray-500 dark:text-gray-400')
        content = content.replace('text-gray-400', 'text-gray-400 dark:text-gray-500')
        
    # We need to manually add the root body tag dark classes
    body_tag_pattern = r'<body\s+class="([^"]+)">'
    match = re.search(body_tag_pattern, content)
    if match and "dark:bg-dark-bg" not in match.group(1):
        og_classes = match.group(1)
        # remove hardcoded bg and text colors if they exist on the root to let css vars handle it, or just use tailwind
        new_classes = og_classes + " bg-background dark:bg-dark-bg text-text dark:text-dark-text transition-colors duration-200"
        content = content.replace(f'class="{og_classes}"', f'class="{new_classes}"')

    # Add global style CSS fix (Tailwind handles most, but specific text color overwrites need .dark overrides)
    style_fix = """
        .dark body { background-color: #0f172a; color: #f8fafc; }
        .dark .glass-panel { background: #1e293b; border-color: #334155; }
        .dark .card-custom { background: #1e293b; border-color: #334155; }
    </style>"""
    if ".dark body {" not in content:
        content = content.replace("</style>", style_fix)

    # Inject the button toggle
    if "toggleTheme()" not in content:
        if is_index:
            # Inject next to the settings button in index
            button_target = '<button class="bg-white/80'
            content = content.replace(button_target, TOGGLE_BUTTON_HTML.replace('ml-2', '') + '\n        ' + button_target)
        else:
            # Inject in the header flex container for other pages
            header_target = '<div class="flex items-center gap-2 cursor-pointer ml-2"'
            content = content.replace(header_target, TOGGLE_BUTTON_HTML + '\n            ' + header_target)
            
    # Inject toggle script
    if "function toggleTheme()" not in content:
        content = content.replace("lucide.createIcons();", TOGGLE_LOGIC_SCRIPT + "\n        lucide.createIcons();", 1)

    with open(filepath, 'w') as f:
        f.write(content)

patch_file('app/static/index.html', is_index=True)
patch_file('app/static/notifications.html', is_index=False)
patch_file('app/static/rag.html', is_index=False)
