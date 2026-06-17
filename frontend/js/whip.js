let whipState = {
    localStream: null,
    peerConnection: null,
    sessionId: '',
    whipUrl: '',
    locationUrl: '',
    isStreaming: false,
    initialized: false
};

async function stopWhipStream() {
    try {
        if (whipState.locationUrl) {
            console.log('Send WHIP stop request to:', whipState.locationUrl);
            await fetch(whipState.locationUrl, {
                method: 'DELETE',
                credentials: 'include'
            });
            whipState.locationUrl = '';
            whipState.sessionId = '';
        }
        
        if (whipState.localStream) {
            whipState.localStream.getTracks().forEach(track => track.stop());
            whipState.localStream = null;
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = null;
            }
        }
        
        if (whipState.peerConnection) {
            whipState.peerConnection.close();
            whipState.peerConnection = null;
        }
        
        whipState.isStreaming = false;
        
        const startStreamBtn = document.getElementById('startStream');
        const stopStreamBtn = document.getElementById('stopStream');
        if (startStreamBtn) {
            startStreamBtn.disabled = false;
        }
        if (stopStreamBtn) {
            stopStreamBtn.disabled = true;
        }
        
        console.log('Push stopped');
        
    } catch (error) {
        console.error('Failed to stop push:', error);
    }
}

function restoreWhipState() {
    const localVideo = document.getElementById('localVideo');
    const startStreamBtn = document.getElementById('startStream');
    const stopStreamBtn = document.getElementById('stopStream');
    
    if (whipState.localStream && localVideo) {
        localVideo.srcObject = whipState.localStream;
        console.log('Local preview restored');
    }
    
    if (startStreamBtn && stopStreamBtn) {
        startStreamBtn.disabled = whipState.isStreaming;
        stopStreamBtn.disabled = !whipState.isStreaming;
        console.log('Button state restored, streaming state:', whipState.isStreaming);
    }
    
    const whipUrlInput = document.getElementById('whipUrl');
    if (whipUrlInput && whipState.whipUrl) {
        whipUrlInput.value = whipState.whipUrl;
    }
}

function initWhipStreaming() {
    console.log('Whip streaming initialized');
    
    const updateWhipUrl = async () => {
        const appName = document.getElementById('appName').value || 'live';
        const streamName = document.getElementById('streamName').value || 'test';
        const baseUrl = Api.getBaseUrl();
        const apiPath = '/index/api/whip';
        let url = `${baseUrl}${apiPath}?app=${encodeURIComponent(appName)}&stream=${encodeURIComponent(streamName)}`;
        try {
            const result = await Api.getPluginUrlParams('on_publish', appName, streamName);
            if (result.code === 0 && result.data && Object.keys(result.data).length > 0) {
                url += '&' + new URLSearchParams(result.data).toString();
            }
        } catch (e) {
            console.warn('Failed to get push URL extra params, using default address:', e);
        }
        whipState.whipUrl = url;
        document.getElementById('whipUrl').value = whipState.whipUrl;
        console.log('Update push URL:', whipState.whipUrl);
    };
    
    const initDeviceSelection = async () => {
        try {
            let devices = await navigator.mediaDevices.enumerateDevices();
            
            const hasPermission = devices.some(device => device.label);
            
            if (!hasPermission) {
                console.log('No device permission, showing hint');
                const videoSelect = document.getElementById('videoDevice');
                const audioSelect = document.getElementById('audioDevice');
                
                videoSelect.innerHTML = '<option value="">Authorize after starting push</option>';
                audioSelect.innerHTML = '<option value="">Authorize after starting push</option>';
                return;
            }
            
            const videoSelect = document.getElementById('videoDevice');
            videoSelect.innerHTML = '<option value="">Select camera</option>';
            
            let firstVideoDeviceId = '';
            devices.forEach(device => {
                if (device.kind === 'videoinput') {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.text = device.label || `Camera ${videoSelect.options.length}`;
                    videoSelect.appendChild(option);
                    
                    if (!firstVideoDeviceId) {
                        firstVideoDeviceId = device.deviceId;
                    }
                }
            });
            
            const audioSelect = document.getElementById('audioDevice');
            audioSelect.innerHTML = '<option value="">Select microphone</option>';
            
            let firstAudioDeviceId = '';
            devices.forEach(device => {
                if (device.kind === 'audioinput') {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.text = device.label || `Microphone ${audioSelect.options.length}`;
                    audioSelect.appendChild(option);
                    
                    if (!firstAudioDeviceId) {
                        firstAudioDeviceId = device.deviceId;
                    }
                }
            });
            
            if (firstVideoDeviceId) {
                videoSelect.value = firstVideoDeviceId;
                console.log('Auto-select video device:', firstVideoDeviceId);
            }
            
            if (firstAudioDeviceId) {
                audioSelect.value = firstAudioDeviceId;
                console.log('Auto-select audio device:', firstAudioDeviceId);
            }
            
        } catch (error) {
            console.error('Device enumeration failed:', error);
            showToast('Cannot enumerate devices', 'error');
        }
    };
    
    const startStream = async () => {
        try {
            console.log('Start push...');
            
            let videoDevice = document.getElementById('videoDevice').value;
            let audioDevice = document.getElementById('audioDevice').value;
            
            if (!videoDevice || videoDevice === 'Authorize after starting push') {
                console.log('Requesting media device permission...');
                try {
                    const tempStream = await navigator.mediaDevices.getUserMedia({ 
                        video: true, 
                        audio: true 
                    });
                    tempStream.getTracks().forEach(track => track.stop());
                    
                    await initDeviceSelection();
                    
                    videoDevice = document.getElementById('videoDevice').value;
                    audioDevice = document.getElementById('audioDevice').value;
                    
                    if (!videoDevice || videoDevice === 'Authorize after starting push') {
                        showToast('Please select a video device', 'error');
                        return;
                    }
                } catch (error) {
                    console.error('Failed to get device permission:', error);
                    showToast('Cannot access camera or microphone, please check permission settings', 'error');
                    return;
                }
            }
            
            console.log('Using video device:', videoDevice, 'Audio device:', audioDevice);
            
            console.log('Getting local media stream...');
            whipState.localStream = await navigator.mediaDevices.getUserMedia({
                video: { deviceId: videoDevice ? { exact: videoDevice } : true },
                audio: audioDevice ? { deviceId: { exact: audioDevice } } : true
            });
            console.log('Got local media stream, track count:', whipState.localStream.getTracks().length);
            
            const localVideo = document.getElementById('localVideo');
            localVideo.srcObject = whipState.localStream;
            console.log('Local preview shown');
            
            console.log('Creating PeerConnection...');
            whipState.peerConnection = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' }
                ]
            });
            
            whipState.peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    console.log('Generated ICE candidate:', event.candidate);
                }
            };
            
            whipState.peerConnection.onconnectionstatechange = () => {
                console.log('PeerConnection state:', whipState.peerConnection.connectionState);
            };
            
            whipState.localStream.getTracks().forEach(track => {
                console.log('Add track to PeerConnection:', track.kind);
                whipState.peerConnection.addTrack(track, whipState.localStream);
            });
            
            console.log('Generating SDP offer...');
            const offer = await whipState.peerConnection.createOffer();
            console.log('SDP offer generated');
            await whipState.peerConnection.setLocalDescription(offer);
            console.log('Local SDP set successfully');
            
            console.log('Send WHIP request to:', whipState.whipUrl);
            console.log('SDP content length:', offer.sdp.length);
            const response = await fetch(whipState.whipUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/sdp'
                },
                body: offer.sdp,
                credentials: 'include'
            });
            
            console.log('WHIP server response status:', response.status);
            console.log('WHIP server response headers:', Object.fromEntries(response.headers.entries()));
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('WHIP server returned error content:', errorText);
                throw new Error(`WHIP server returned error: ${response.status} - ${errorText}`);
            }
            
            const location = response.headers.get('Location');
            console.log('Location header:', location);
            if (!location) {
                throw new Error('WHIP server did not return Location header');
            }
            
            whipState.locationUrl = location;
            
            whipState.sessionId = location.split('/').pop();
            console.log('Got session ID:', whipState.sessionId);
            console.log('Saved Location URL:', whipState.locationUrl);
            
            const answerSDP = await response.text();
            console.log('SDP answer length:', answerSDP.length);
            await whipState.peerConnection.setRemoteDescription(new RTCSessionDescription({
                type: 'answer',
                sdp: answerSDP
            }));
            console.log('Remote SDP set successfully');
            
            whipState.isStreaming = true;
            
            document.getElementById('startStream').disabled = true;
            document.getElementById('stopStream').disabled = false;
            showToast('Push started', 'success');
            console.log('Push started successfully');
            
        } catch (error) {
            console.error('Failed to start push:', error);
            showToast('Failed to start push: ' + error.message, 'error');
            if (whipState.localStream) {
                whipState.localStream.getTracks().forEach(track => track.stop());
                whipState.localStream = null;
            }
            if (whipState.peerConnection) {
                whipState.peerConnection.close();
                whipState.peerConnection = null;
            }
            whipState.isStreaming = false;
        }
    };
    
    const stopStream = async () => {
        await stopWhipStream();
        showToast('Push stopped', 'success');
    };
    
    const initEventListeners = () => {
        console.log('Start initializing event listeners...');
        
        const appNameInput = document.getElementById('appName');
        const streamNameInput = document.getElementById('streamName');
        
        if (appNameInput) {
            appNameInput.addEventListener('input', updateWhipUrl);
            console.log('Bound appName input event listener');
        } else {
            console.error('appName element not found');
        }
        
        if (streamNameInput) {
            streamNameInput.addEventListener('input', updateWhipUrl);
            console.log('Bound streamName input event listener');
        } else {
            console.error('streamName element not found');
        }
        
        const startStreamBtn = document.getElementById('startStream');
        if (startStreamBtn) {
            startStreamBtn.addEventListener('click', startStream);
            console.log('Bound startStream button click event listener');
        } else {
            console.error('startStream button not found');
        }
        
        const stopStreamBtn = document.getElementById('stopStream');
        if (stopStreamBtn) {
            stopStreamBtn.addEventListener('click', stopStream);
            console.log('Bound stopStream button click event listener');
        } else {
            console.error('stopStream button not found');
        }
        
        console.log('Event listener initialization complete');
    };
    
    updateWhipUrl();
    initDeviceSelection();
    initEventListeners();
}
