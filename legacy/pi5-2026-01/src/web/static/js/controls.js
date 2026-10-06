/**
 * Robot Control Interface - JavaScript Controller v2.0
 * Handles motor control (via RPi3), LIDAR visualization, dual cameras, and autonomous navigation
 */

document.addEventListener('DOMContentLoaded', function () {
    // ========== Socket.IO Setup ==========
    const socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: Infinity
    });

    // ========== State Variables ==========
    let isAutoMode = false;
    let activeCommand = null;
    let currentSpeed = 0.5;
    let currentNavMode = null;
    let currentCamera = 'front';
    let lidarData = [];
    let robotPosition = { x: 0, y: 0, theta: 0 };
    let motorConnected = false;
    let lastMotorConnectedState = null;  // Track previous state to detect changes

    // ========== DOM Elements ==========
    const elements = {
        connectionStatus: document.getElementById('connection-status'),
        motorStatus: document.getElementById('motor-status'),
        modeIndicator: document.getElementById('mode-indicator'),
        toggleMode: document.getElementById('toggle-mode'),
        lidarCanvas: document.getElementById('lidar-canvas'),
        objectsList: document.getElementById('objects-list'),
        consoleOutput: document.getElementById('console-output'),
        speedSlider: document.getElementById('speed-slider'),
        speedValue: document.getElementById('speed-value'),
        scanRate: document.getElementById('scan-rate'),
        navState: document.getElementById('nav-state'),
        obstacleCount: document.getElementById('obstacle-count'),
        traveledDistance: document.getElementById('traveled-distance'),
        posX: document.getElementById('pos-x'),
        posY: document.getElementById('pos-y'),
        posTheta: document.getElementById('pos-theta'),
        safeDistance: document.getElementById('safe-distance'),
        lidarOffset: document.getElementById('lidar-offset'),
        clearMap: document.getElementById('clear-map'),
        clearConsole: document.getElementById('clear-console'),
        videoFeed: document.getElementById('video-feed'),
        cameraLabel: document.getElementById('camera-label'),
        camFront: document.getElementById('cam-front'),
        camRear: document.getElementById('cam-rear')
    };

    // ========== LIDAR Canvas Setup ==========
    const ctx = elements.lidarCanvas?.getContext('2d');
    const canvasSize = 400;
    const maxRange = 6000;

    // ========== Button Command Mappings ==========
    const buttonCommands = {
        'move_forward': 'move_forward',
        'move_backward': 'move_backward',
        'strafe_left': 'strafe_left',
        'strafe_right': 'strafe_right',
        'rotate_counterclockwise': 'rotate_counterclockwise',
        'rotate_clockwise': 'rotate_clockwise',
        'stop': 'stop'
    };

    // ========== Keyboard Mappings ==========
    const keyMap = {
        'w': 'move_forward',
        'W': 'move_forward',
        's': 'move_backward',
        'S': 'move_backward',
        'a': 'strafe_left',
        'A': 'strafe_left',
        'd': 'strafe_right',
        'D': 'strafe_right',
        'ArrowLeft': 'rotate_counterclockwise',
        'ArrowRight': 'rotate_clockwise',
        ' ': 'stop'
    };

    // ========== Logging Function ==========
    function log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        entry.textContent = `[${timestamp}] ${message}`;
        
        if (elements.consoleOutput) {
            elements.consoleOutput.appendChild(entry);
            elements.consoleOutput.scrollTop = elements.consoleOutput.scrollHeight;
            
            while (elements.consoleOutput.children.length > 100) {
                elements.consoleOutput.removeChild(elements.consoleOutput.firstChild);
            }
        }
        console.log(`[${type.toUpperCase()}] ${message}`);
    }

    // ========== UI Update Functions ==========
    function updateConnectionStatus(connected) {
        if (elements.connectionStatus) {
            const dot = elements.connectionStatus.querySelector('.dot');
            const label = elements.connectionStatus.querySelector('.label');
            
            dot.classList.toggle('connected', connected);
            label.textContent = connected ? 'SERVER ✓' : 'SERVER ✗';
        }
    }

    function updateMotorStatus(connected) {
        motorConnected = connected;
        
        if (elements.motorStatus) {
            const dot = elements.motorStatus.querySelector('.dot');
            const label = elements.motorStatus.querySelector('.label');
            
            dot.classList.toggle('connected', connected);
            label.textContent = connected ? 'RPi3 ✓' : 'RPi3 ✗';
        }
        
        // Disable controls if motors not connected
        if (!connected && !isAutoMode) {
            Object.keys(buttonCommands).forEach(buttonId => {
                const button = document.getElementById(buttonId);
                if (button && buttonId !== 'stop') {
                    button.disabled = true;
                }
            });
        }
    }

    function updateModeUI() {
        if (elements.modeIndicator) {
            const dot = elements.modeIndicator.querySelector('.dot');
            const label = elements.modeIndicator.querySelector('.label');
            
            dot.classList.remove('manual', 'auto');
            dot.classList.add(isAutoMode ? 'auto' : 'manual');
            label.textContent = isAutoMode ? 'AUTO' : 'MANUAL';
        }

        if (elements.toggleMode) {
            elements.toggleMode.classList.toggle('active', isAutoMode);
            elements.toggleMode.querySelector('.mode-text').textContent = 
                isAutoMode ? 'MANUAL MODE' : 'AUTO MODE';
        }

        // Enable/disable control buttons
        Object.keys(buttonCommands).forEach(buttonId => {
            const button = document.getElementById(buttonId);
            if (button && buttonId !== 'stop') {
                button.disabled = isAutoMode || !motorConnected;
            }
        });
    }

    function setActiveButton(buttonId, active) {
        const button = document.getElementById(buttonId);
        if (button) {
            button.classList.toggle('active', active);
        }
    }

    function updateDetectedObjects(objects) {
        if (elements.objectsList) {
            elements.objectsList.innerHTML = objects.map(obj =>
                `<li>${obj}</li>`
            ).join('');
        }
    }

    function updatePosition(position) {
        robotPosition = position;
        
        if (elements.posX) elements.posX.textContent = position.x.toFixed(2);
        if (elements.posY) elements.posY.textContent = position.y.toFixed(2);
        if (elements.posTheta) {
            const degrees = ((position.theta * 180 / Math.PI) % 360).toFixed(1);
            elements.posTheta.textContent = degrees;
        }
    }

    function updateNavStatus(status) {
        if (elements.navState) elements.navState.textContent = status.state || 'IDLE';
        if (elements.obstacleCount) elements.obstacleCount.textContent = status.obstacles || '0';
        if (elements.traveledDistance) {
            elements.traveledDistance.textContent = (status.distance || 0).toFixed(1) + ' m';
        }
    }

    function switchCamera(camera) {
        currentCamera = camera;
        
        // Update video feed URL
        if (elements.videoFeed) {
            elements.videoFeed.src = `/video_feed/${camera}?t=${Date.now()}`;
        }
        
        // Update label
        if (elements.cameraLabel) {
            elements.cameraLabel.textContent = camera.toUpperCase() + ' CAM';
        }
        
        // Update button states
        if (elements.camFront) {
            elements.camFront.classList.toggle('active', camera === 'front');
        }
        if (elements.camRear) {
            elements.camRear.classList.toggle('active', camera === 'rear');
        }
        
        socket.emit('switch_camera', camera);
    }

    // ========== LIDAR Visualization ==========
    function drawLidarMap() {
        if (!ctx) return;

        const centerX = canvasSize / 2;
        const centerY = canvasSize / 2;

        // Clear canvas
        ctx.fillStyle = '#12121a';
        ctx.fillRect(0, 0, canvasSize, canvasSize);

        // Draw grid
        ctx.strokeStyle = '#2a2a3a';
        ctx.lineWidth = 1;
        
        for (let r = 50; r <= 200; r += 50) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
            ctx.stroke();
        }

        ctx.beginPath();
        ctx.moveTo(centerX, 0);
        ctx.lineTo(centerX, canvasSize);
        ctx.moveTo(0, centerY);
        ctx.lineTo(canvasSize, centerY);
        ctx.stroke();

        // Draw lidar points
        const safeDistance = parseInt(elements.safeDistance?.value || 500);
        const offset = parseInt(elements.lidarOffset?.value || -105);
        
        lidarData.forEach(point => {
            const adjustedAngle = ((point.angle + offset) % 360) * Math.PI / 180;
            const distance = point.distance;
            
            const scale = 200 / maxRange;
            const x = centerX + Math.cos(adjustedAngle) * distance * scale;
            const y = centerY - Math.sin(adjustedAngle) * distance * scale;
            
            if (distance < safeDistance) {
                ctx.fillStyle = '#ff3366';
            } else if (distance < safeDistance * 2) {
                ctx.fillStyle = '#ffaa00';
            } else {
                ctx.fillStyle = '#00ff88';
            }
            
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fill();
        });

        // Draw robot
        ctx.fillStyle = '#00ccff';
        ctx.beginPath();
        ctx.arc(centerX, centerY, 8, 0, Math.PI * 2);
        ctx.fill();

        // Draw direction
        const dirAngle = robotPosition.theta || 0;
        ctx.strokeStyle = '#00ccff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
            centerX + Math.cos(dirAngle) * 20,
            centerY - Math.sin(dirAngle) * 20
        );
        ctx.stroke();

        // Draw forward cone
        ctx.fillStyle = 'rgba(0, 255, 136, 0.1)';
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        const coneAngle = 30 * Math.PI / 180;
        const coneRadius = (safeDistance / maxRange) * 200;
        ctx.arc(centerX, centerY, coneRadius, -Math.PI/2 - coneAngle, -Math.PI/2 + coneAngle);
        ctx.closePath();
        ctx.fill();
    }

    // ========== Command Functions ==========
    function sendCommand(command) {
        if ((!isAutoMode || command === 'stop') && motorConnected) {
            socket.emit('command', { command, speed: currentSpeed });
        } else if (!motorConnected && command !== 'stop') {
            log('Cannot send command - RPi3 not connected', 'warning');
        }
    }

    function setNavMode(mode) {
        currentNavMode = mode;
        
        document.querySelectorAll('.nav-mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
        
        socket.emit('nav_mode', { 
            mode,
            safe_distance: parseInt(elements.safeDistance?.value || 500),
            lidar_offset: parseInt(elements.lidarOffset?.value || -105)
        });
        
        log(`Navigation mode: ${mode}`, 'success');
    }

    // ========== Event Listeners ==========

    // Camera switch buttons
    if (elements.camFront) {
        elements.camFront.addEventListener('click', () => switchCamera('front'));
    }
    if (elements.camRear) {
        elements.camRear.addEventListener('click', () => switchCamera('rear'));
    }

    // Control buttons (mouse)
    Object.entries(buttonCommands).forEach(([buttonId, command]) => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('mousedown', (e) => {
                e.preventDefault();
                if ((!isAutoMode || buttonId === 'stop') && motorConnected) {
                    activeCommand = command;
                    sendCommand(command);
                    setActiveButton(buttonId, true);
                }
            });

            button.addEventListener('mouseup', () => {
                if (activeCommand === command && buttonId !== 'stop') {
                    activeCommand = null;
                    sendCommand('stop');
                    setActiveButton(buttonId, false);
                }
            });

            button.addEventListener('mouseleave', () => {
                if (activeCommand === command && buttonId !== 'stop') {
                    activeCommand = null;
                    sendCommand('stop');
                    setActiveButton(buttonId, false);
                }
            });

            // Touch support
            button.addEventListener('touchstart', (e) => {
                e.preventDefault();
                if ((!isAutoMode || buttonId === 'stop') && motorConnected) {
                    activeCommand = command;
                    sendCommand(command);
                    setActiveButton(buttonId, true);
                }
            });

            button.addEventListener('touchend', () => {
                if (activeCommand === command && buttonId !== 'stop') {
                    activeCommand = null;
                    sendCommand('stop');
                    setActiveButton(buttonId, false);
                }
            });
        }
    });

    // Keyboard controls
    document.addEventListener('keydown', (e) => {
        if (keyMap[e.key] && activeCommand !== keyMap[e.key]) {
            const command = keyMap[e.key];
            if ((!isAutoMode || command === 'stop') && motorConnected) {
                e.preventDefault();
                activeCommand = command;
                sendCommand(buttonCommands[command] || command);
                setActiveButton(command, true);
            }
        }
    });

    document.addEventListener('keyup', (e) => {
        if (keyMap[e.key] && activeCommand === keyMap[e.key]) {
            e.preventDefault();
            const command = keyMap[e.key];
            if (command !== 'stop') {
                activeCommand = null;
                sendCommand('stop');
                setActiveButton(command, false);
            }
        }
    });

    // Mode toggle
    if (elements.toggleMode) {
        elements.toggleMode.addEventListener('click', () => {
            isAutoMode = !isAutoMode;
            socket.emit('mode', isAutoMode ? 'auto' : 'manual');
            updateModeUI();
            log(`Mode switched to: ${isAutoMode ? 'AUTO' : 'MANUAL'}`, 'success');
            
            if (!isAutoMode) {
                sendCommand('stop');
            }
        });
    }

    // Speed slider
    if (elements.speedSlider) {
        elements.speedSlider.addEventListener('input', (e) => {
            currentSpeed = e.target.value / 100;
            if (elements.speedValue) {
                elements.speedValue.textContent = `${e.target.value}%`;
            }
            socket.emit('set_speed', currentSpeed);
        });
    }

    // Navigation mode buttons
    document.querySelectorAll('.nav-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (isAutoMode) {
                setNavMode(btn.dataset.mode);
            } else {
                log('Switch to AUTO mode first', 'warning');
            }
        });
    });

    // Parameter inputs
    if (elements.safeDistance) {
        elements.safeDistance.addEventListener('change', () => {
            socket.emit('set_params', {
                safe_distance: parseInt(elements.safeDistance.value),
                lidar_offset: parseInt(elements.lidarOffset?.value || -105)
            });
            log(`Safe distance: ${elements.safeDistance.value}mm`, 'info');
        });
    }

    if (elements.lidarOffset) {
        elements.lidarOffset.addEventListener('change', () => {
            socket.emit('set_params', {
                safe_distance: parseInt(elements.safeDistance?.value || 500),
                lidar_offset: parseInt(elements.lidarOffset.value)
            });
            log(`LIDAR offset: ${elements.lidarOffset.value}°`, 'info');
        });
    }

    // Clear buttons
    if (elements.clearMap) {
        elements.clearMap.addEventListener('click', () => {
            lidarData = [];
            drawLidarMap();
            socket.emit('clear_map');
            log('Map cleared', 'info');
        });
    }

    if (elements.clearConsole) {
        elements.clearConsole.addEventListener('click', () => {
            if (elements.consoleOutput) {
                elements.consoleOutput.innerHTML = '';
            }
        });
    }

    // ========== Socket.IO Event Handlers ==========
    socket.on('connect', () => {
        updateConnectionStatus(true);
        log('Connected to RPi5 server', 'success');
        socket.emit('get_objects');
        socket.emit('get_state');
    });

    socket.on('disconnect', () => {
        updateConnectionStatus(false);
        updateMotorStatus(false);
        log('Disconnected from server', 'error');
    });

    socket.on('connect_error', (error) => {
        log(`Connection error: ${error.message}`, 'error');
    });

    socket.on('objects', (objects) => {
        updateDetectedObjects(objects);
    });

    socket.on('lidar_data', (data) => {
        lidarData = data.points || [];
        if (elements.scanRate) {
            elements.scanRate.textContent = `${data.scan_rate || 0} Hz`;
        }
        drawLidarMap();
    });

    socket.on('position', (position) => {
        updatePosition(position);
    });

    socket.on('nav_status', (status) => {
        updateNavStatus(status);
    });

    socket.on('motor_status', (status) => {
        updateMotorStatus(status.connected);
        
        // Only log when connection state CHANGES
        if (status.is_remote && status.connected !== lastMotorConnectedState) {
            lastMotorConnectedState = status.connected;
            log(`Motors: RPi3 ${status.connected ? 'connected' : 'disconnected'}`, 
                status.connected ? 'success' : 'warning');
        }
    });

    socket.on('mode', (mode) => {
        isAutoMode = mode === 'auto';
        updateModeUI();
    });

    socket.on('log', (data) => {
        log(data.message, data.type || 'info');
    });

    // ========== Initialization ==========
    updateModeUI();
    drawLidarMap();
    log('Robot Control Interface v2.0 ready', 'success');
    log('Waiting for RPi3 motor controller...', 'info');

    // Request initial state
    socket.emit('get_state');

    // Periodic LIDAR redraw
    setInterval(drawLidarMap, 100);
});
