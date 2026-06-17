let allConfig = {};
let filteredConfig = {};
let currentCategory = 'all';

async function loadServerConfig() {
    const container = document.getElementById('configContainer');
    
    container.innerHTML = `
        <div class="flex justify-center items-center h-64">
            <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary mx-auto mb-4"></div>
            <span class="text-white/60 font-semibold">Loading...</span>
        </div>
    `;
    
    try {
        const result = await Api.getServerConfig();
        
        if (result.code === 0 && result.data && result.data.length > 0) {
            allConfig = result.data[0] || {};
            filteredConfig = { ...allConfig };
            updateCategoryFilter();
            renderConfig();
        } else {
            container.innerHTML = `
                <div class="text-center p-10 text-white/60 font-semibold">
                    Failed to load config: ${result.msg || 'Unknown error'}
                </div>
            `;
        }
    } catch (error) {
        container.innerHTML = `
            <div class="text-center p-10 text-white/60 font-semibold">
                Network error: ${error.message}
            </div>
        `;
    }
}

function updateCategoryFilter() {
    const categoryFilter = document.getElementById('categoryFilter');
    if (!categoryFilter) return;
    
    const categories = new Set();
    Object.keys(allConfig).forEach(key => {
        const parts = key.split('.');
        if (parts.length > 1) {
            categories.add(parts[0]);
        } else {
            categories.add('general');
        }
    });
    
    let html = '<option value="all">All Categories</option>';
    Array.from(categories).sort().forEach(category => {
        html += `<option value="${category}">${category}</option>`;
    });
    
    categoryFilter.innerHTML = html;
}

function renderConfig() {
    const container = document.getElementById('configContainer');
    const searchTerm = document.getElementById('searchInput')?.value.toLowerCase() || '';
    const selectedCategory = document.getElementById('categoryFilter')?.value || 'all';
    
    const filteredItems = {};
    Object.keys(allConfig).forEach(key => {
        const parts = key.split('.');
        const category = parts.length > 1 ? parts[0] : 'general';
        
        const matchesCategory = selectedCategory === 'all' || category === selectedCategory;
        const matchesSearch = searchTerm === '' || 
                             key.toLowerCase().includes(searchTerm) ||
                             String(allConfig[key]).toLowerCase().includes(searchTerm);
        
        if (matchesCategory && matchesSearch) {
            filteredItems[key] = allConfig[key];
        }
    });
    
    if (Object.keys(filteredItems).length === 0) {
        container.innerHTML = `
            <div class="text-center p-10 text-white/60 font-semibold">
                No matching config items found
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead>
                    <tr class="bg-white/10 border-b border-white/20">
                        <th class="px-4 py-3 text-left text-white font-semibold w-1/3">Config Item</th>
                        <th class="px-4 py-3 text-left text-white font-semibold w-1/2">Config Value</th>
                        <th class="px-4 py-3 text-center text-white font-semibold w-1/6">Actions</th>
                    </tr>
                </thead>
                <tbody id="configTableBody">
    `;
    
    Object.keys(filteredItems).sort().forEach(key => {
        html += renderConfigRow(key, filteredItems[key]);
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    container.innerHTML = html;
}

function renderConfigRow(key, value) {
    const isSecret = key.toLowerCase().includes('secret') || 
                     key.toLowerCase().includes('password') ||
                     key.toLowerCase().includes('pwd') ||
                     key.toLowerCase().includes('key');
    
    const inputType = isSecret ? 'password' : 'text';
    const displayValue = isSecret ? '******' : value;
    const comment = typeof CONFIG_COMMENTS !== 'undefined' ? (CONFIG_COMMENTS[key] || '') : '';
    
    return `
        <tr class="border-b border-white/5 hover:bg-white/5 transition-colors">
            <td class="px-4 py-3">
                <div class="text-white font-medium">${key}</div>
                ${comment ? `<div class="text-white/50 text-xs mt-1">${comment}</div>` : ''}
            </td>
            <td class="px-4 py-3">
                <input type="${inputType}" 
                       id="input-${key.replace(/\./g, '-')}" 
                       value="${escapeHtml(value)}" 
                       class="w-full bg-white/10 border border-white/20 rounded px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                       data-key="${key}"
                       data-original="${escapeHtml(value)}">
            </td>
            <td class="px-4 py-3">
                <div class="flex items-center justify-center space-x-2">
                    <button onclick="resetConfig('${key}')" 
                            class="text-white/60 hover:text-white transition-colors p-2"
                            title="Reset">
                        <i class="fa fa-undo"></i>
                    </button>
                    <button onclick="saveConfig('${key}')" 
                            class="bg-gradient-primary text-white px-3 py-1 rounded text-sm font-semibold hover:shadow-neon transition-all"
                            title="Save">
                        Save
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function saveConfig(key) {
    const inputId = `input-${key.replace(/\./g, '-')}`;
    const input = document.getElementById(inputId);
    if (!input) {
        showToast('Config item not found', 'error');
        return;
    }
    
    const value = input.value;
    
    try {
        const result = await Api.setServerConfig({ [key]: value });
        
        if (result.code === 0) {
            showToast('Config saved', 'success');
            allConfig[key] = value;
            input.setAttribute('data-original', value);
        } else {
            showToast('Failed to save config: ' + (result.msg || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Failed to save config: ' + error.message, 'error');
    }
}

function resetConfig(key) {
    const inputId = `input-${key.replace(/\./g, '-')}`;
    const input = document.getElementById(inputId);
    if (!input) return;
    
    const originalValue = input.getAttribute('data-original');
    input.value = originalValue;
    showToast('Reset to original value', 'info');
}

function searchConfig() {
    renderConfig();
}

function filterByCategory() {
    renderConfig();
}

function initSettingsPage() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', searchConfig);
    }
    
    const categoryFilter = document.getElementById('categoryFilter');
    if (categoryFilter) {
        categoryFilter.addEventListener('change', filterByCategory);
    }
    
    const refreshBtn = document.getElementById('refreshConfig');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadServerConfig);
    }
    
    loadServerConfig();
}
