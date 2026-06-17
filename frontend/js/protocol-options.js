function initProtocolOptionsEvents() {
    const addButton = document.getElementById('addProtocolOption');
    if (addButton) {
        addButton.removeEventListener('click', openAddModal);
        addButton.addEventListener('click', openAddModal);
    }
}

async function loadProtocolOptions() {
    initProtocolOptionsEvents();
    
    const tbody = document.getElementById('protocolOptionsTableBody');
    
    tbody.innerHTML = `
        <tr>
            <td colspan="4" class="p-10 text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary mx-auto mb-4"></div>
                <span class="text-white/60 font-semibold">Loading...</span>
            </td>
        </tr>
    `;
    
    try {
        const result = await Api.getProtocolOptionsList();
        
        if (result.code === 0) {
            const data = result.data || [];
            
            if (data.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" class="p-10 text-center text-white/60 font-semibold">
                            No protocol configs
                        </td>
                    </tr>
                `;
                return;
            }
            
            let html = '';
            data.forEach(option => {
                html += `
                    <tr class="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <td class="p-4 text-white">${option.id}</td>
                        <td class="p-4 text-white">${option.name}</td>
                        <td class="p-4 text-white">${option.created_at || '-'}</td>
                        <td class="p-4">
                            <button class="bg-blue-500 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:shadow-neon transition-colors mr-2" onclick="editProtocolOption(${option.id})">
                                <i class="fa fa-edit mr-1"></i>Edit
                            </button>
                            <button class="bg-red-500 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:shadow-neon transition-colors" onclick="deleteProtocolOption(${option.id}, '${option.name}')">
                                <i class="fa fa-trash mr-1"></i>Delete
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            tbody.innerHTML = html;
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" class="p-10 text-center text-white/60 font-semibold">
                        Load failed: ${result.msg || 'Unknown error'}
                    </td>
                </tr>
            `;
        }
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="p-10 text-center text-white/60 font-semibold">
                    Network error: ${error.message}
                </td>
            </tr>
        `;
    }
}

async function openAddModal() {
    showProtocolOptionsModal('Add protocol preset', null, {});
}

function editProtocolOption(id) {
    Api.getProtocolOptions(id).then(result => {
        if (result.code !== 0) {
            showToast('Failed to get config: ' + (result.msg || 'Unknown error'), 'error');
            return;
        }
        showProtocolOptionsModal('Edit protocol preset', result.data);
    }).catch(error => {
        showToast('Failed to get config: ' + error.message, 'error');
    });
}

function showProtocolOptionsModal(title, data, serverConfig = {}) {
    const modal = document.createElement('div');
    modal.className = 'absolute inset-0 bg-black/80 flex items-center justify-center pointer-events-auto';
    
    const getValue = (key, defaultValue = '') => {
        if (data && data[key] !== undefined) {
            return data[key];
        }
        if (serverConfig && serverConfig[key] !== undefined) {
            return serverConfig[key];
        }
        return defaultValue;
    };
    
    const iCls = 'w-full bg-white/10 border border-white/20 rounded-lg px-4 py-2 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-primary';
    const buildToggle = (label, id, val) => `
        <div>
            <label class="block text-white font-semibold mb-2">${label}</label>
            <select id="${id}" class="${iCls}" style="color:white;">
                <option value="" ${!val ? 'selected' : ''}>Default</option>
                <option value="1" ${val === '1' ? 'selected' : ''}>1 - On</option>
                <option value="0" ${val === '0' ? 'selected' : ''}>0 - Off</option>
            </select>
        </div>`;

    modal.innerHTML = `
        <div class="bg-gray-900 rounded-xl p-6 max-w-4xl w-full mx-4 border border-white/20 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold text-white">${title}</h3>
                <div class="flex items-center gap-2">
                    <button type="button" id="poLoadDefaultBtn"
                        class="bg-white/10 text-white px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-white/20 transition-colors">
                        <i class="fa fa-magic mr-1"></i>Load defaults
                    </button>
                    <button type="button" id="poClearBtn"
                        class="bg-red-500/20 text-red-400 px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-red-500/30 transition-colors">
                        <i class="fa fa-eraser mr-1"></i>Clear
                    </button>
                    <button class="text-white/60 hover:text-white ml-1" onclick="this.closest('.absolute').remove()">
                        <i class="fa fa-times text-2xl"></i>
                    </button>
                </div>
            </div>
            <form id="protocolOptionsForm" class="space-y-6">
                <input type="hidden" id="optionId" value="${data ? data.id : ''}">

                <!-- General config -->
                <div class="bg-white/5 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-4 border-b border-white/10 pb-2">General config</h4>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-white font-semibold mb-2">Preset name(name) *</label>
                            <input type="text" id="optionName" required value="${data ? data.name : ''}" class="${iCls}">
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-white font-semibold mb-2">Timestamp override(modify_stamp)</label>
                                <select id="modifyStamp" class="${iCls}" style="color:white;">
                                    <option value="" ${!getValue('modify_stamp') ? 'selected' : ''}>Default</option>
                                    <option value="0" ${getValue('modify_stamp') === '0' ? 'selected' : ''}>0 - Absolute timestamp</option>
                                    <option value="1" ${getValue('modify_stamp') === '1' ? 'selected' : ''}>1 - System timestamp</option>
                                    <option value="2" ${getValue('modify_stamp') === '2' ? 'selected' : ''}>2 - Relative timestamp</option>
                                </select>
                            </div>
                            ${buildToggle('Enable audio(enable_audio)', 'enableAudio', getValue('enable_audio'))}
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            ${buildToggle('Add silent audio(add_mute_audio)', 'addMuteAudio', getValue('add_mute_audio'))}
                            ${buildToggle('Auto close(auto_close)', 'autoClose', getValue('auto_close'))}
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-white font-semibold mb-2">Reconnect continue-push delay(continue_push_ms, ms)</label>
                                <input type="number" id="continuePushMs" value="${getValue('continue_push_ms')}" placeholder="15000" class="${iCls}">
                            </div>
                            <div>
                                <label class="block text-white font-semibold mb-2">Paced sender interval(paced_sender_ms, ms)</label>
                                <input type="number" id="pacedSenderMs" value="${getValue('paced_sender_ms')}" placeholder="0" class="${iCls}">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Remux toggles -->
                <div class="bg-white/5 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-4 border-b border-white/10 pb-2">Remux toggles</h4>
                    <div class="grid grid-cols-3 gap-4">
                        ${buildToggle('Enable HLS(enable_hls)', 'enableHls', getValue('enable_hls'))}
                        ${buildToggle('Enable HLS-FMP4(enable_hls_fmp4)', 'enableHlsFmp4', getValue('enable_hls_fmp4'))}
                        ${buildToggle('Enable MP4 recording(enable_mp4)', 'enableMp4', getValue('enable_mp4'))}
                        ${buildToggle('Enable RTSP(enable_rtsp)', 'enableRtsp', getValue('enable_rtsp'))}
                        ${buildToggle('Enable RTMP/FLV(enable_rtmp)', 'enableRtmp', getValue('enable_rtmp'))}
                        ${buildToggle('Enable HTTP-TS(enable_ts)', 'enableTs', getValue('enable_ts'))}
                        ${buildToggle('Enable FMP4(enable_fmp4)', 'enableFmp4', getValue('enable_fmp4'))}
                    </div>
                </div>

                <!-- On-demand remux toggles -->
                <div class="bg-white/5 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-4 border-b border-white/10 pb-2">On-demand remux toggles</h4>
                    <div class="grid grid-cols-3 gap-4">
                        ${buildToggle('HLS on-demand(hls_demand)', 'hlsDemand', getValue('hls_demand'))}
                        ${buildToggle('RTSP on-demand(rtsp_demand)', 'rtspDemand', getValue('rtsp_demand'))}
                        ${buildToggle('RTMP on-demand(rtmp_demand)', 'rtmpDemand', getValue('rtmp_demand'))}
                        ${buildToggle('TS on-demand(ts_demand)', 'tsDemand', getValue('ts_demand'))}
                        ${buildToggle('FMP4 on-demand(fmp4_demand)', 'fmp4Demand', getValue('fmp4_demand'))}
                    </div>
                </div>

                <!-- Recording config -->
                <div class="bg-white/5 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-white mb-4 border-b border-white/10 pb-2">Recording config</h4>
                    <div class="grid grid-cols-2 gap-4">
                        ${buildToggle('MP4 counts toward viewers(mp4_as_player)', 'mp4AsPlayer', getValue('mp4_as_player'))}
                        <div>
                            <label class="block text-white font-semibold mb-2">MP4 segment size(mp4_max_second, sec)</label>
                            <input type="number" id="mp4MaxSecond" value="${getValue('mp4_max_second')}" placeholder="3600" class="${iCls}">
                        </div>
                        <div>
                            <label class="block text-white font-semibold mb-2">MP4 save path(mp4_save_path)</label>
                            <input type="text" id="mp4SavePath" value="${getValue('mp4_save_path')}" placeholder="./www" class="${iCls}">
                        </div>
                        <div>
                            <label class="block text-white font-semibold mb-2">HLS save path(hls_save_path)</label>
                            <input type="text" id="hlsSavePath" value="${getValue('hls_save_path')}" placeholder="./www" class="${iCls}">
                        </div>
                    </div>
                </div>

                <div class="flex justify-end space-x-4 mt-6">
                    <button type="button" class="bg-white/10 text-white px-6 py-2 rounded-lg font-semibold hover:bg-white/20 transition-colors" onclick="this.closest('.absolute').remove()">
                        Cancel
                    </button>
                    <button type="submit" class="bg-gradient-primary text-white px-6 py-2 rounded-lg font-semibold hover:shadow-neon transition-all duration-300">
                        Save
                    </button>
                </div>
            </form>
        </div>
    `;
    const container = document.getElementById('protocol-options-modal-container');
    if (container) {
        container.appendChild(modal);
    } else {
        document.body.appendChild(modal);
    }
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.remove();
        }
    });

    // ---- Field id list (for load defaults / clear)----
    const _fieldMap = {
        modifyStamp:    'modify_stamp',
        enableAudio:    'enable_audio',
        addMuteAudio:   'add_mute_audio',
        autoClose:      'auto_close',
        continuePushMs: 'continue_push_ms',
        pacedSenderMs:  'paced_sender_ms',
        enableHls:      'enable_hls',
        enableHlsFmp4:  'enable_hls_fmp4',
        enableMp4:      'enable_mp4',
        enableRtsp:     'enable_rtsp',
        enableRtmp:     'enable_rtmp',
        enableTs:       'enable_ts',
        enableFmp4:     'enable_fmp4',
        hlsDemand:      'hls_demand',
        rtspDemand:     'rtsp_demand',
        rtmpDemand:     'rtmp_demand',
        tsDemand:       'ts_demand',
        fmp4Demand:     'fmp4_demand',
        mp4AsPlayer:    'mp4_as_player',
        mp4MaxSecond:   'mp4_max_second',
        mp4SavePath:    'mp4_save_path',
        hlsSavePath:    'hls_save_path',
    };

    // Load defaults: fetch server config in real time and fill each field
    document.getElementById('poLoadDefaultBtn').addEventListener('click', async function () {
        const btn = this;
        btn.disabled = true;
        btn.innerHTML = '<i class="fa fa-spinner fa-spin mr-1"></i>Loading...';
        try {
            const result = await Api.getServerConfig();
            if (result.code === 0 && result.data && result.data.length > 0) {
                const raw = result.data[0] || {};
                // Extract protocol.xxx key-values
                const cfg = {};
                for (const [key, value] of Object.entries(raw)) {
                    if (key.startsWith('protocol.')) {
                        cfg[key.substring('protocol.'.length)] = value;
                    }
                }
                let applied = 0;
                Object.entries(_fieldMap).forEach(([domId, cfgKey]) => {
                    const el = document.getElementById(domId);
                    if (el && cfg[cfgKey] !== undefined && cfg[cfgKey] !== null) {
                        el.value = String(cfg[cfgKey]);
                        applied++;
                    }
                });
                if (applied > 0) {
                    showToast(`Loaded ${applied} server default values`, 'success');
                } else {
                    showToast('Server did not return protocol.* config', 'warning');
                }
            } else {
                showToast('Failed to get server config: ' + (result.msg || 'Unknown error'), 'error');
            }
        } catch (e) {
            showToast('Failed to get server config: ' + e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa fa-magic mr-1"></i>Load defaults';
        }
    });

    // Clear: reset all fields (except name) to empty
    document.getElementById('poClearBtn').addEventListener('click', function () {
        Object.keys(_fieldMap).forEach(domId => {
            const el = document.getElementById(domId);
            if (el) el.value = '';
        });
        showToast('All protocol params cleared', 'info');
    });
    
    document.getElementById('protocolOptionsForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const id = document.getElementById('optionId').value;
        const name = document.getElementById('optionName').value;
        
        if (!name) {
            showToast('Preset name cannot be empty', 'error');
            return;
        }
        
        const formData = {
            name: name,
            modify_stamp: document.getElementById('modifyStamp').value,
            enable_audio: document.getElementById('enableAudio').value,
            add_mute_audio: document.getElementById('addMuteAudio').value,
            auto_close: document.getElementById('autoClose').value,
            continue_push_ms: document.getElementById('continuePushMs').value,
            paced_sender_ms: document.getElementById('pacedSenderMs').value,
            enable_hls: document.getElementById('enableHls').value,
            enable_hls_fmp4: document.getElementById('enableHlsFmp4').value,
            enable_mp4: document.getElementById('enableMp4').value,
            enable_rtsp: document.getElementById('enableRtsp').value,
            enable_rtmp: document.getElementById('enableRtmp').value,
            enable_ts: document.getElementById('enableTs').value,
            enable_fmp4: document.getElementById('enableFmp4').value,
            mp4_as_player: document.getElementById('mp4AsPlayer').value,
            mp4_max_second: document.getElementById('mp4MaxSecond').value,
            mp4_save_path: document.getElementById('mp4SavePath').value,
            hls_save_path: document.getElementById('hlsSavePath').value,
            hls_demand: document.getElementById('hlsDemand').value,
            rtsp_demand: document.getElementById('rtspDemand').value,
            rtmp_demand: document.getElementById('rtmpDemand').value,
            ts_demand: document.getElementById('tsDemand').value,
            fmp4_demand: document.getElementById('fmp4Demand').value
        };
        
        try {
            let result;
            if (id) {
                formData.id = id;
                result = await Api.updateProtocolOptions(formData);
            } else {
                result = await Api.addProtocolOptions(formData);
            }
            
            if (result.code === 0) {
                showToast(id ? 'Updated' : 'Added', 'success');
                modal.remove();
                loadProtocolOptions();
            } else {
                showToast((id ? 'Update failed' : 'Add failed') + ': ' + (result.msg || 'Unknown error'), 'error');
            }
        } catch (error) {
            showToast((id ? 'Update failed' : 'Add failed') + ': ' + error.message, 'error');
        }
    });
}

async function deleteProtocolOption(id, name) {
    showConfirmModal(
        'Confirm delete',
        `Are you sure you want to delete protocol preset "${name}"?`,
        async function() {
            try {
                const result = await Api.deleteProtocolOptions(id);
                
                if (result.code === 0) {
                    showToast('Deleted', 'success');
                    loadProtocolOptions();
                } else {
                    showToast('Delete failed: ' + (result.msg || 'Unknown error'), 'error');
                }
            } catch (error) {
                showToast('Delete failed: ' + error.message, 'error');
            }
        }
    );
}
