async function loadDashboard() {
    try {
        // Fetch data in parallel for better performance
        const [statisticResult, mediaResult, versionResult, threadsLoadResult, workThreadsLoadResult, hostStatsResult] = await Promise.all([
            Api.getStatistic(),
            Api.getMediaList(),
            Api.getVersion(),
            Api.getThreadsLoad(),
            Api.getWorkThreadsLoad(),
            Api.getHostStats()
        ]);
        
        // Process statistics data
        if (statisticResult.code === 0) {
            const statisticData = statisticResult.data || {};
            // Use MultiMediaSourceMuxer count as online stream count
            const streamCount = statisticData.MultiMediaSourceMuxer || 0;
            document.getElementById('streamCount').textContent = streamCount;
            
            // Draw statistics chart
            drawStatisticChart(statisticData);
        } else {
            document.getElementById('streamCount').textContent = '0';
        }
        
        // Process media list data
        if (mediaResult.code === 0) {
            const mediaData = mediaResult.data || [];
            let totalViewers = 0;
            mediaData.forEach(stream => {
                totalViewers += stream.readerCount || 0;
            });
            document.getElementById('viewerCount').textContent = totalViewers;
        } else {
            document.getElementById('viewerCount').textContent = '0';
        }
        
        // Process version info
        if (versionResult.code === 0) {
            const data = versionResult.data || {};
            const branchName = data.branchName || '-';
            const buildTime = data.buildTime || '-';
            const commitHash = data.commitHash || '-';
            document.getElementById('versionInfo').textContent = `Version: ${commitHash}`;
            document.getElementById('branchInfo').textContent = `Branch: ${branchName}`;
            document.getElementById('buildInfo').textContent = `Build time: ${buildTime}`;
        } else {
            document.getElementById('versionInfo').textContent = 'Version: -';
            document.getElementById('branchInfo').textContent = 'Branch: -';
            document.getElementById('buildInfo').textContent = 'Build time: -';
        }
        
        // Process thread load data
        if (threadsLoadResult.code === 0) {
            const data = threadsLoadResult.data || [];
            drawThreadsLoadChart(data);
        }
        
        // Process worker thread load data
        if (workThreadsLoadResult.code === 0) {
            const data = workThreadsLoadResult.data || [];
            drawWorkThreadsLoadChart(data);
        }
        
        // Process system resource data
        if (hostStatsResult.code === 0) {
            const data = hostStatsResult.data || {};
            
            // Update traffic stats
            const network = data.network || {};
            const sentTotal = network.sent_total || 0;
            const recvTotal = network.recv_total || 0;
            document.getElementById('trafficCount').innerHTML = `
                <p class="text-white/70 text-xs">Sent: ${formatBytes(sentTotal * 1024)}</p>
                <p class="text-white/70 text-xs mt-1">Received: ${formatBytes(recvTotal * 1024)}</p>
            `;
            
            // Update history data
            updateHistoryData(data);
            
            // Draw chart
            drawCpuMemoryChart(data.memory || {});
            drawDiskChart(data.disk || {});
            drawNetworkChart(data.network || {});
        } else {
            showToast('Failed to load system status: ' + hostStatsResult.msg, 'error');
        }
    } catch (error) {
        showToast('Failed to load data: ' + error.message, 'error');
        document.getElementById('streamCount').textContent = '0';
        document.getElementById('viewerCount').textContent = '0';
        document.getElementById('versionInfo').textContent = 'Version: -';
        document.getElementById('branchInfo').textContent = 'Branch: -';
        document.getElementById('buildInfo').textContent = 'Build time: -';
    }
}

// Store timerID
let dashboardTimer = null;

// Initialize dashboard, called after dashboard.html finishes loading
function initDashboard() {
    // Initial data load
    loadDashboard();
    
    // Clear previous timer
    if (dashboardTimer) {
        clearInterval(dashboardTimer);
    }
    
    // Refresh status every 3 seconds
    dashboardTimer = setInterval(loadDashboard, 3000);
}

// Clean up dashboard resources
function cleanupDashboard() {
    if (dashboardTimer) {
        clearInterval(dashboardTimer);
        dashboardTimer = null;
    }
}

function drawStatisticChart(data) {
    const ctx = document.getElementById('statisticChart').getContext('2d');
    
    const labels = Object.keys(data);
    const values = Object.values(data);
    
    if (window.statisticChart && typeof window.statisticChart.destroy === 'function') {
        window.statisticChart.destroy();
    }
    
    window.statisticChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Object count',
                data: values,
                backgroundColor: 'rgba(75, 192, 192, 0.7)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 20
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        rotation: 45
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

function drawThreadsLoadChart(data) {
    const ctx = document.getElementById('threadsLoadChart').getContext('2d');
    
    const labels = data.map(item => item.name || 'Unnamed');
    const loadData = data.map(item => (item.load || 0));
    const delayData = data.map(item => item.delay || 0);
    const fdCountData = data.map(item => item.fd_count || 0);
    
    const maxDelay = Math.max(...delayData, 100);
    const yMax = maxDelay > 100 ? maxDelay * 1.2 : 100;
    
    const maxFdCount = Math.max(...fdCountData, 1);
    const fdCountScaled = fdCountData.map(val => (val / maxFdCount) * 90);
    
    if (window.threadsLoadChart && typeof window.threadsLoadChart.destroy === 'function') {
        window.threadsLoadChart.destroy();
    }
    
    window.threadsLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Load',
                    data: loadData,
                    type: 'line',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointHoverRadius: 5
                },
                {
                    label: 'Latency',
                    data: delayData,
                    type: 'line',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    borderColor: 'rgba(255, 206, 86, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y',
                    pointRadius: 3,
                    pointHoverRadius: 5
                },
                {
                    label: 'FD count',
                    data: fdCountScaled,
                    type: 'line',
                    backgroundColor: 'rgba(153, 102, 255, 0.2)',
                    borderColor: 'rgba(153, 102, 255, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointHoverRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 30
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Latency',
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    beginAtZero: true,
                    max: yMax,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return value + ' ms';
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Load',
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    beginAtZero: true,
                    max: 110,
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return value + ' %';
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        rotation: 45
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            if (context.dataset.label === 'FD count') {
                                return 'FD count: ' + fdCountData[context.dataIndex];
                            }
                            return context.dataset.label + ': ' + context.parsed.y;
                        }
                    }
                }
            },
            animation: {
                onComplete: function() {
                    const chart = this;
                    const ctx = chart.ctx;
                    
                    chart.data.datasets.forEach(function(dataset, i) {
                        if (dataset.label === 'FD count') {
                            const meta = chart.getDatasetMeta(i);
                            meta.data.forEach(function(point, index) {
                                const data = fdCountData[index];
                                ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                                ctx.font = '10px Inter, system-ui, sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'bottom';
                                ctx.fillText(data, point.x, point.y - 5);
                            });
                        }
                    });
                }
            }
        }
    });
}

function drawWorkThreadsLoadChart(data) {
    const ctx = document.getElementById('workThreadsLoadChart').getContext('2d');
    
    const labels = data.map(item => item.name || 'Unnamed');
    const loadData = data.map(item => (item.load || 0));
    const delayData = data.map(item => item.delay || 0);
    const fdCountData = data.map(item => item.fd_count || 0);
    
    const maxDelay = Math.max(...delayData, 100);
    const yMax = maxDelay > 100 ? maxDelay * 1.2 : 100;
    
    const maxFdCount = Math.max(...fdCountData, 1);
    const fdCountScaled = fdCountData.map(val => (val / maxFdCount) * 90);
    
    if (window.workThreadsLoadChart && typeof window.workThreadsLoadChart.destroy === 'function') {
        window.workThreadsLoadChart.destroy();
    }
    
    window.workThreadsLoadChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Load',
                    data: loadData,
                    type: 'line',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointHoverRadius: 5
                },
                {
                    label: 'Latency',
                    data: delayData,
                    type: 'line',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    borderColor: 'rgba(255, 206, 86, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y',
                    pointRadius: 3,
                    pointHoverRadius: 5
                },
                {
                    label: 'FD count',
                    data: fdCountScaled,
                    type: 'line',
                    backgroundColor: 'rgba(153, 102, 255, 0.2)',
                    borderColor: 'rgba(153, 102, 255, 1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointHoverRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 30
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Latency',
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    beginAtZero: true,
                    max: yMax,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return value + ' ms';
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Load',
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    beginAtZero: true,
                    max: 110,
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return value + ' %';
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        rotation: 45
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            if (context.dataset.label === 'FD count') {
                                return 'FD count: ' + fdCountData[context.dataIndex];
                            }
                            return context.dataset.label + ': ' + context.parsed.y;
                        }
                    }
                }
            },
            animation: {
                onComplete: function() {
                    const chart = this;
                    const ctx = chart.ctx;
                    
                    chart.data.datasets.forEach(function(dataset, i) {
                        if (dataset.label === 'FD count') {
                            const meta = chart.getDatasetMeta(i);
                            meta.data.forEach(function(point, index) {
                                const data = fdCountData[index];
                                ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                                ctx.font = '10px Inter, system-ui, sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'bottom';
                                ctx.fillText(data, point.x, point.y - 5);
                            });
                        }
                    });
                }
            }
        }
    });
}

// Store history data
let cpuHistory = Array(30).fill(0);
let memoryHistory = Array(30).fill(0);
let diskHistory = Array(30).fill(0);
let networkSentHistory = Array(30).fill(0);
let networkRecvHistory = Array(30).fill(0);
let timeLabels = Array(30).fill('');

// Format byte units
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function updateHistoryData(data) {
    // Update time label
    const time = data.time || '';
    timeLabels.shift();
    timeLabels.push(time);
    
    // Update CPU data
    const cpu = data.cpu || 0;
    cpuHistory.shift();
    cpuHistory.push(cpu);
    
    // Update memory data
    const memoryUsed = data.memory?.used || 0;
    memoryHistory.shift();
    memoryHistory.push(memoryUsed);
    
    // Update disk data
    const diskUsed = data.disk?.used || 0;
    diskHistory.shift();
    diskHistory.push(diskUsed);
    
    // Update network data
    const networkSent = data.network?.sent || 0;
    networkSentHistory.shift();
    networkSentHistory.push(networkSent);
    
    const networkRecv = data.network?.recv || 0;
    networkRecvHistory.shift();
    networkRecvHistory.push(networkRecv);
}

// Format storage units
function formatStorage(value) {
    if (value >= 1024) {
        return {
            value: value / 1024,
            unit: 'TB'
        };
    }
    return {
        value: value,
        unit: 'GB'
    };
}

function drawCpuMemoryChart(memoryData = {}) {
    const ctx = document.getElementById('cpuMemoryChart').getContext('2d');
    
    const totalMemory = memoryData.total || 24;
    const formattedMemory = formatStorage(totalMemory);
    const maxMemory = Math.ceil(formattedMemory.value * 1.2);
    
    // Format memory history data
    const formattedMemoryHistory = memoryHistory.map(value => {
        if (formattedMemory.unit === 'TB') {
            return value / 1024;
        }
        return value;
    });
    
    if (window.cpuMemoryChart && typeof window.cpuMemoryChart.destroy === 'function') {
        window.cpuMemoryChart.destroy();
    }
    
    window.cpuMemoryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'CPU usage',
                data: cpuHistory,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.4,
                fill: true,
                yAxisID: 'y'
            }, {
                label: `Memory usage (${formattedMemory.unit})`,
                data: formattedMemoryHistory,
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                tension: 0.4,
                fill: true,
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: true,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return value + ' %';
                        }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    beginAtZero: true,
                    max: maxMemory,
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return Math.round(value) + ' ' + formattedMemory.unit;
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            }
        }
    });
}

function drawDiskChart(diskData = {}) {
    const ctx = document.getElementById('diskChart').getContext('2d');
    
    const totalDisk = diskData.total || 500;
    const formattedDisk = formatStorage(totalDisk);
    const maxDisk = Math.ceil(formattedDisk.value * 1.2);
    
    // Format disk history data
    const formattedDiskHistory = diskHistory.map(value => {
        if (formattedDisk.unit === 'TB') {
            return value / 1024;
        }
        return value;
    });
    
    if (window.diskChart && typeof window.diskChart.destroy === 'function') {
        window.diskChart.destroy();
    }
    
    window.diskChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: `Disk usage (${formattedDisk.unit})`,
                data: formattedDiskHistory,
                borderColor: 'rgba(255, 99, 132, 1)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: maxDisk,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return Math.round(value) + ' ' + formattedDisk.unit;
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            }
        }
    });
}

// Format network rate units
function formatNetworkSpeed(value) {
    if (value >= 1024 * 1024) {
        return {
            value: value / (1024 * 1024),
            unit: 'GB/s'
        };
    } else if (value >= 1024) {
        return {
            value: value / 1024,
            unit: 'MB/s'
        };
    }
    return {
        value: value,
        unit: 'KB/s'
    };
}

function drawNetworkChart(networkData = {}) {
    const ctx = document.getElementById('networkChart').getContext('2d');
    
    // Find the maximum network rate value
    const maxSent = Math.max(...networkSentHistory);
    const maxRecv = Math.max(...networkRecvHistory);
    const maxSpeed = Math.max(maxSent, maxRecv);
    
    // Format network rate units
    const formattedSpeed = formatNetworkSpeed(maxSpeed);
    
    // Compute Y-axis maximum
    const maxY = Math.ceil(formattedSpeed.value * 1.2);
    
    // Format history data
    const formattedSentHistory = networkSentHistory.map(value => {
        if (formattedSpeed.unit === 'GB/s') {
            return value / (1024 * 1024);
        } else if (formattedSpeed.unit === 'MB/s') {
            return value / 1024;
        }
        return value;
    });
    
    const formattedRecvHistory = networkRecvHistory.map(value => {
        if (formattedSpeed.unit === 'GB/s') {
            return value / (1024 * 1024);
        } else if (formattedSpeed.unit === 'MB/s') {
            return value / 1024;
        }
        return value;
    });
    
    if (window.networkChart && typeof window.networkChart.destroy === 'function') {
        window.networkChart.destroy();
    }
    
    window.networkChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: `Network sent (${formattedSpeed.unit})`,
                data: formattedSentHistory,
                borderColor: 'rgba(255, 159, 64, 1)',
                backgroundColor: 'rgba(255, 159, 64, 0.2)',
                tension: 0.4,
                fill: true
            }, {
                label: `Network received (${formattedSpeed.unit})`,
                data: formattedRecvHistory,
                borderColor: 'rgba(153, 102, 255, 1)',
                backgroundColor: 'rgba(153, 102, 255, 0.2)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: maxY,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)',
                        callback: function(value) {
                            return Math.round(value * 10) / 10 + ' ' + formattedSpeed.unit;
                        }
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    }
                }
            }
        }
    });
}
