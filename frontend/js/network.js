async function loadNetwork() {
    const tbody = document.getElementById('networkTableBody');
    
    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="p-10 text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary mx-auto mb-4"></div>
                <span class="text-white/60 font-semibold">Loading...</span>
            </td>
        </tr>
    `;
    
    try {
        const result = await Api.getNetworkList();
        
        console.log('getNetworkList returned result:', result);
        
        if (result.code === 0) {
            const data = result.data || [];
            
            console.log('Network connections list data:', data);
            
            if (data.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="p-10 text-center text-white/60 font-semibold">
                            No network connections
                        </td>
                    </tr>
                `;
                return;
            }
            
            let html = '';
            data.forEach(network => {
                console.log('Network connection data:', network);
                
                html += `
                    <tr class="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <td class="p-4 text-white">${network.identifier || network.id || '-'}</td>
                        <td class="p-4 text-white">${network.typeid || '-'}</td>
                        <td class="p-4 text-white">${network.type || '-'}</td>
                        <td class="p-4 text-white">${network.local_ip || '-'}</td>
                        <td class="p-4 text-white">${network.local_port || '-'}</td>
                        <td class="p-4 text-white">${network.peer_ip || '-'}</td>
                        <td class="p-4 text-white">${network.peer_port || '-'}</td>
                        <td class="p-4">
                            <button class="bg-red-500 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:shadow-neon transition-colors" onclick="closeNetwork('${network.identifier || network.id}')">Close</button>
                        </td>
                    </tr>
                `;
            });
            
            tbody.innerHTML = html;
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="p-10 text-center text-white/60 font-semibold">
                        Load failed: ${result.msg || 'Unknown error'}
                    </td>
                </tr>
            `;
        }
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="p-10 text-center text-white/60 font-semibold">
                    Network error: ${error.message}
                </td>
            </tr>
        `;
    }
}

async function closeNetwork(identifier) {
    // Show confirmation dialog
    showConfirmModal(
        'Confirm close connection',
        `Are you sure you want to close the connection with identifier ${identifier}?`,
        async function() {
            try {
                console.log('Close network connection:', identifier);
                
                // API call to close the network connection
                const result = await Api.request('/index/api/kick_session', { body: { id: identifier } });
                
                if (result.code === 0) {
                    showToast('Network connection closed', 'success');
                    // Reload network connections list
                    loadNetwork();
                } else {
                    showToast('Failed to close network connection: ' + (result.msg || 'Unknown error'), 'error');
                }
            } catch (error) {
                console.error('Failed to close network connection:', error);
                showToast('Failed to close network connection: ' + error.message, 'error');
            }
        }
    );
}

// Initialize network connections page
function initNetwork() {
    // Initial data load
    loadNetwork();
    
    // Bind refresh button event
    const refreshBtn = document.getElementById('refreshNetwork');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadNetwork);
    }
}

// Clean up network connections page resources
function cleanupNetwork() {
    // Remove event listeners and other resources
    const refreshBtn = document.getElementById('refreshNetwork');
    if (refreshBtn) {
        // Remove event listener
        const newRefreshBtn = refreshBtn.cloneNode(true);
        refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);
        newRefreshBtn.addEventListener('click', loadNetwork);
    }
}