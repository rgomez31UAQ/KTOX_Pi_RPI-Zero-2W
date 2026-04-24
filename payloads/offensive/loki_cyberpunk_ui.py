#!/usr/bin/env python3
"""
LOKI - Cyberpunk WebUI
=====================
Heavy cyberpunk theme matching yt-ripper
Canvas LCD display + virtual keyboard
"""

import os
import sys
import json
import base64
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Configuration
KTOX_ROOT = "/root/KTOx"
LOOT_DIR = Path(KTOX_ROOT) / "loot"
LOKI_DATA = LOOT_DIR / "loki"
LOKI_PORT = 8000

# Cyberpunk Colors (matching yt-ripper)
BG = "#0a0000"           # (10, 0, 0)
PANEL = "#220000"        # (34, 0, 0)
HEADER = "#8b0000"       # (139, 0, 0)
FG = "#abb2b9"           # (171, 178, 185)
ACCENT = "#e74c3c"       # (231, 76, 60)
WHITE = "#ffffff"
WARN = "#d4ac0d"         # (212, 172, 13)
DIM = "#717d7e"          # (113, 125, 126)

# RGB Tuples for PIL
RGB_BG = (10, 0, 0)
RGB_PANEL = (34, 0, 0)
RGB_HEADER = (139, 0, 0)
RGB_FG = (171, 178, 185)
RGB_ACCENT = (231, 76, 60)
RGB_WHITE = (255, 255, 255)

# Virtual Keyboard Layout (from yt-ripper)
VKB = [
    ["q","w","e","r","t","y","u","i","o","p"],
    ["a","s","d","f","g","h","j","k","l","BS"],
    ["z","x","c","v","b","n","m",".","/","-"],
    ["http","https","www",".com","SPC"],
    ["CLR","ENT","ESC"],
]

app = Flask(__name__)

# Create data directories
for subdir in ["logs", "output/crackedpwd", "output/datastolen", "output/zombies", "output/vulnerabilities", "input"]:
    (LOKI_DATA / subdir).mkdir(parents=True, exist_ok=True)

# HTML Template with Cyberpunk Theme
CYBERPUNK_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOKI - CYBERPUNK EDITION</title>
    <style>
        :root {
            --bg: #0a0000;
            --panel: #220000;
            --header: #8b0000;
            --fg: #abb2b9;
            --accent: #e74c3c;
            --white: #ffffff;
            --warn: #d4ac0d;
            --dim: #717d7e;
            --glow: 0 0 20px rgba(231, 76, 60, 0.6);
            --glow-warn: 0 0 15px rgba(212, 172, 13, 0.5);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, var(--bg) 0%, var(--panel) 50%, var(--header) 100%);
            color: var(--fg);
            font-family: 'Courier New', monospace;
            line-height: 1.4;
            overflow-x: hidden;
        }

        .scanlines {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            background: repeating-linear-gradient(
                0deg,
                rgba(255, 255, 255, 0.03),
                rgba(255, 255, 255, 0.03) 1px,
                transparent 1px,
                transparent 2px
            );
            z-index: 9999;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            border-bottom: 2px solid var(--accent);
            padding-bottom: 20px;
            margin-bottom: 30px;
            text-align: center;
            box-shadow: var(--glow);
        }

        h1 {
            font-size: 36px;
            color: var(--accent);
            text-shadow: 0 0 10px var(--accent), 0 0 20px rgba(231, 76, 60, 0.5);
            margin-bottom: 5px;
            letter-spacing: 3px;
        }

        .subtitle {
            color: var(--dim);
            font-size: 12px;
            letter-spacing: 2px;
        }

        .main-grid {
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .panel {
            background: linear-gradient(135deg, var(--panel) 0%, var(--header) 100%);
            border: 2px solid var(--accent);
            padding: 20px;
            box-shadow: var(--glow);
            position: relative;
        }

        .panel::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--accent), transparent);
        }

        .panel-title {
            color: var(--accent);
            font-size: 14px;
            margin-bottom: 15px;
            letter-spacing: 2px;
            text-transform: uppercase;
            border-bottom: 1px dashed var(--accent);
            padding-bottom: 8px;
        }

        .canvas-wrapper {
            aspect-ratio: 1;
            background: #000;
            border: 3px solid var(--accent);
            padding: 10px;
            box-shadow: inset 0 0 20px rgba(231, 76, 60, 0.3), var(--glow);
            position: relative;
        }

        canvas {
            display: block;
            width: 100%;
            height: 100%;
            image-rendering: pixelated;
        }

        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
            margin-top: 15px;
        }

        .button {
            background: var(--panel);
            border: 2px solid var(--accent);
            color: var(--accent);
            padding: 12px;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 12px;
            transition: all 0.2s;
            box-shadow: 0 0 10px rgba(231, 76, 60, 0.2);
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .button:hover {
            background: var(--header);
            box-shadow: var(--glow);
            transform: scale(1.05);
        }

        .button:active {
            transform: scale(0.95);
            box-shadow: inset 0 0 10px rgba(231, 76, 60, 0.3);
        }

        .dpad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 5px;
            margin-bottom: 10px;
        }

        .dpad-btn {
            aspect-ratio: 1;
            padding: 0;
            font-size: 14px;
        }

        .dpad-spacer {
            background: transparent;
            border: none;
            box-shadow: none;
        }

        .key-buttons {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .key-button {
            background: var(--panel);
            border: 2px solid var(--warn);
            color: var(--warn);
            padding: 10px;
            font-size: 12px;
            box-shadow: 0 0 8px rgba(212, 172, 13, 0.3);
        }

        .key-button:hover {
            background: var(--header);
            box-shadow: var(--glow-warn);
        }

        .status-display {
            background: #000;
            border: 2px solid var(--accent);
            padding: 15px;
            margin-top: 15px;
            box-shadow: inset 0 0 10px rgba(231, 76, 60, 0.1);
        }

        .status-line {
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
            font-size: 12px;
            color: var(--fg);
        }

        .status-label {
            color: var(--dim);
        }

        .status-value {
            color: var(--accent);
            font-weight: bold;
        }

        .content {
            display: grid;
            gap: 20px;
        }

        .section {
            background: linear-gradient(135deg, var(--panel) 0%, var(--header) 100%);
            border: 2px solid var(--accent);
            padding: 20px;
            box-shadow: var(--glow);
        }

        .section-title {
            color: var(--accent);
            font-size: 16px;
            margin-bottom: 15px;
            letter-spacing: 2px;
            text-transform: uppercase;
            border-bottom: 1px dashed var(--accent);
            padding-bottom: 10px;
        }

        .action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }

        .action-btn {
            background: var(--panel);
            border: 2px solid var(--accent);
            color: var(--accent);
            padding: 15px;
            text-align: center;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.2s;
            text-transform: uppercase;
            letter-spacing: 1px;
            box-shadow: 0 0 10px rgba(231, 76, 60, 0.2);
        }

        .action-btn:hover {
            background: var(--header);
            box-shadow: var(--glow);
            transform: translateY(-2px);
        }

        .log-container {
            background: #000;
            border: 2px solid var(--accent);
            padding: 15px;
            height: 300px;
            overflow-y: auto;
            font-size: 11px;
            box-shadow: inset 0 0 10px rgba(231, 76, 60, 0.1);
            scrollbar-width: thin;
            scrollbar-color: var(--accent) var(--panel);
        }

        .log-entry {
            margin: 3px 0;
            padding: 2px 0;
        }

        .log-success { color: #00ff00; text-shadow: 0 0 5px #00ff00; }
        .log-error { color: #ff0000; text-shadow: 0 0 5px #ff0000; }
        .log-warning { color: var(--warn); text-shadow: 0 0 5px var(--warn); }
        .log-info { color: #00ffff; text-shadow: 0 0 5px #00ffff; }

        @media (max-width: 900px) {
            .main-grid {
                grid-template-columns: 1fr;
            }

            .sidebar {
                order: 2;
            }

            .content {
                order: 1;
            }
        }

        .glitch {
            animation: glitch 0.2s infinite;
        }

        @keyframes glitch {
            0%, 100% { text-shadow: 0 0 10px var(--accent); }
            50% { text-shadow: 0 0 20px var(--accent), 0 0 30px rgba(231, 76, 60, 0.5); }
        }
    </style>
</head>
<body>
    <div class="scanlines"></div>

    <div class="container">
        <header>
            <h1>⚡ LOKI ⚡</h1>
            <p class="subtitle">CYBERPUNK SECURITY ENGINE</p>
        </header>

        <div class="main-grid">
            <!-- Sidebar -->
            <div class="sidebar">
                <!-- LCD Display -->
                <div class="panel">
                    <div class="panel-title">LCD DISPLAY</div>
                    <div class="canvas-wrapper">
                        <canvas id="lcdCanvas" width="128" height="128"></canvas>
                    </div>
                </div>

                <!-- D-Pad Controls -->
                <div class="panel">
                    <div class="panel-title">CONTROLS</div>
                    <div class="dpad">
                        <button class="button dpad-btn dpad-spacer"></button>
                        <button class="button dpad-btn" onclick="sendBtn('UP')" title="UP">▲</button>
                        <button class="button dpad-btn dpad-spacer"></button>
                        <button class="button dpad-btn" onclick="sendBtn('LEFT')" title="LEFT">◄</button>
                        <button class="button dpad-btn" onclick="sendBtn('OK')" title="OK" style="color: var(--accent); background: var(--header);">OK</button>
                        <button class="button dpad-btn" onclick="sendBtn('RIGHT')" title="RIGHT">►</button>
                        <button class="button dpad-btn dpad-spacer"></button>
                        <button class="button dpad-btn" onclick="sendBtn('DOWN')" title="DOWN">▼</button>
                        <button class="button dpad-btn dpad-spacer"></button>
                    </div>

                    <div class="key-buttons">
                        <button class="button key-button" onclick="sendBtn('KEY1')">KEY1</button>
                        <button class="button key-button" onclick="sendBtn('KEY2')">KEY2</button>
                        <button class="button key-button" onclick="sendBtn('KEY3')">KEY3</button>
                    </div>
                </div>

                <!-- Status -->
                <div class="panel">
                    <div class="panel-title">STATUS</div>
                    <div class="status-display">
                        <div class="status-line">
                            <span class="status-label">STATE:</span>
                            <span class="status-value" id="status">ONLINE</span>
                        </div>
                        <div class="status-line">
                            <span class="status-label">PORT:</span>
                            <span class="status-value">8000</span>
                        </div>
                        <div class="status-line">
                            <span class="status-label">UPTIME:</span>
                            <span class="status-value" id="uptime">00:00:00</span>
                        </div>
                        <div class="status-line">
                            <span class="status-label">MODE:</span>
                            <span class="status-value">ATTACK</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Main Content -->
            <div class="content">
                <!-- Reconnaissance -->
                <div class="section">
                    <div class="section-title">📡 RECONNAISSANCE</div>
                    <div class="action-grid">
                        <button class="action-btn" onclick="exec('scan')">Network Scan</button>
                        <button class="action-btn" onclick="exec('enumerate')">Enumerate</button>
                        <button class="action-btn" onclick="exec('discover')">Host Discovery</button>
                        <button class="action-btn" onclick="exec('fingerprint')">Fingerprint</button>
                    </div>
                </div>

                <!-- Exploitation -->
                <div class="section">
                    <div class="section-title">⚔️  EXPLOITATION</div>
                    <div class="action-grid">
                        <button class="action-btn" onclick="exec('kick_one')">KICK ONE</button>
                        <button class="action-btn" onclick="exec('kick_all')">KICK ALL</button>
                        <button class="action-btn" onclick="exec('mitm')">ARP MITM</button>
                        <button class="action-btn" onclick="exec('flood')">ARP FLOOD</button>
                        <button class="action-btn" onclick="exec('cage')">ARP CAGE</button>
                        <button class="action-btn" onclick="exec('ntlm')">NTLM CAPTURE</button>
                    </div>
                </div>

                <!-- Activity Log -->
                <div class="section">
                    <div class="section-title">📋 ACTIVITY LOG</div>
                    <div class="log-container" id="logContainer">
                        <div class="log-entry log-info">[*] LOKI CYBERPUNK EDITION INITIALIZED</div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        const API = '/api';
        let startTime = Date.now();

        function sendBtn(btn) {
            console.log(`Button: ${btn}`);
            fetch(API + '/input', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({button: btn})
            }).catch(e => console.error(e));
        }

        function exec(type) {
            log(`EXECUTING: ${type}`, 'warning');
            fetch(API + '/action', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type})
            });
        }

        function log(msg, level = 'info') {
            const container = document.getElementById('logContainer');
            const entry = document.createElement('div');
            entry.className = `log-entry log-${level}`;
            const time = new Date().toLocaleTimeString();
            entry.textContent = `[${time}] ${msg}`;
            container.appendChild(entry);
            container.scrollTop = container.scrollHeight;
        }

        function updateUptime() {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const h = Math.floor(elapsed / 3600).toString().padStart(2, '0');
            const m = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0');
            const s = (elapsed % 60).toString().padStart(2, '0');
            document.getElementById('uptime').textContent = `${h}:${m}:${s}`;
        }

        function updateCanvas() {
            const canvas = document.getElementById('lcdCanvas');
            const ctx = canvas.getContext('2d');
            fetch(API + '/screen')
                .then(r => r.json())
                .then(data => {
                    if (data.image) {
                        const img = new Image();
                        img.onload = () => ctx.drawImage(img, 0, 0);
                        img.src = 'data:image/png;base64,' + data.image;
                    }
                })
                .catch(() => {
                    ctx.fillStyle = '#000';
                    ctx.fillRect(0, 0, 128, 128);
                    ctx.fillStyle = '#e74c3c';
                    ctx.font = '10px monospace';
                    ctx.fillText('LOKI READY', 25, 60);
                });
        }

        // Initialize
        updateCanvas();
        setInterval(updateUptime, 1000);
        setInterval(updateCanvas, 1000);
    </script>
</body>
</html>
'''

# API Routes
@app.route('/')
def index():
    return render_template_string(CYBERPUNK_HTML)

@app.route('/api/status')
def api_status():
    return jsonify({'status': 'ONLINE', 'uptime': '00:00:00'})

@app.route('/api/screen')
def api_screen():
    if HAS_PIL:
        img = Image.new('RGB', (128, 128), RGB_BG)
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 118, 118], outline=RGB_ACCENT, width=2)
        draw.text((20, 50), 'LOKI', fill=RGB_ACCENT)

        import io
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return jsonify({'image': base64.b64encode(buffer.getvalue()).decode()})
    return jsonify({'image': None})

@app.route('/api/input', methods=['POST'])
def api_input():
    btn = request.json.get('button', 'UNKNOWN')
    print(f"[LOKI] BUTTON: {btn}")
    return jsonify({'status': 'ok', 'button': btn})

@app.route('/api/action', methods=['POST'])
def api_action():
    action_type = request.json.get('type', 'unknown')
    print(f"[LOKI] ACTION: {action_type}")
    return jsonify({'status': 'ok', 'message': f'{action_type.upper()} INITIATED'})

if __name__ == '__main__':
    print("[LOKI] CYBERPUNK EDITION ONLINE")
    print("[LOKI] http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=LOKI_PORT, debug=False, threaded=True)
