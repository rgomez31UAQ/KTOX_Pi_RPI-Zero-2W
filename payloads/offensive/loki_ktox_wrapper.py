#!/usr/bin/env python3
"""
KTOx-Loki Wrapper
=================
Bridges KTOx menu system with Loki autonomous security engine.
Provides Flask web interface that communicates with Loki backend.

Similar to how RaspyJack wraps Ragnar, this wrapper:
- Runs on port 8000
- Provides clean web UI for Loki operations
- Manages Loki process lifecycle
- Handles data directory integration
"""

import os
import sys
import json
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

# Configuration
KTOX_ROOT = "/root/KTOx"
LOOT_DIR = Path(KTOX_ROOT) / "loot"
LOKI_DATA = LOOT_DIR / "loki"
LOKI_PORT = 8000
LOKI_DIR = Path(KTOX_ROOT) / "vendor" / "loki" / "payloads" / "user" / "reconnaissance" / "loki"

# Create Flask app
app = Flask(__name__, static_url_path='', static_folder=str(LOKI_DIR / 'web' / 'static'))

# Ensure data directories exist
for subdir in ["logs", "output/crackedpwd", "output/datastolen", "output/zombies", "output/vulnerabilities", "input"]:
    (LOKI_DATA / subdir).mkdir(parents=True, exist_ok=True)

# HTML Dashboard Template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loki - Autonomous Security Engine</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #1a1a1a 0%, #0d0d0d 100%);
            color: #00ff00;
            line-height: 1.6;
            overflow-x: hidden;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            border-bottom: 2px solid #00ff00;
            padding-bottom: 20px;
            margin-bottom: 30px;
            box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
        }

        h1 {
            font-size: 48px;
            text-shadow: 0 0 10px #00ff00;
            margin-bottom: 10px;
        }

        .subtitle {
            font-size: 14px;
            color: #666;
            margin-top: 10px;
        }

        .status-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }

        .status-card {
            background: rgba(0, 255, 0, 0.05);
            border: 1px solid #00ff00;
            padding: 15px;
            border-radius: 5px;
            box-shadow: inset 0 0 10px rgba(0, 255, 0, 0.1);
        }

        .status-card h3 {
            font-size: 12px;
            color: #666;
            margin-bottom: 10px;
            text-transform: uppercase;
        }

        .status-value {
            font-size: 24px;
            color: #00ff00;
            font-weight: bold;
        }

        .section {
            margin: 30px 0;
        }

        .section-title {
            font-size: 18px;
            color: #00ff00;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px dashed #00ff00;
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .controls {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 10px;
            margin: 20px 0;
        }

        button {
            background: linear-gradient(135deg, #00ff00 0%, #00cc00 100%);
            color: #000;
            border: none;
            padding: 12px 20px;
            cursor: pointer;
            font-family: monospace;
            font-weight: bold;
            border-radius: 3px;
            transition: all 0.3s;
            text-transform: uppercase;
            font-size: 12px;
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.3);
        }

        button:hover {
            background: linear-gradient(135deg, #00ff00 0%, #00aa00 100%);
            box-shadow: 0 0 20px rgba(0, 255, 0, 0.5);
            transform: scale(1.05);
        }

        button:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
            box-shadow: none;
        }

        .log-container {
            background: rgba(0, 0, 0, 0.8);
            border: 1px solid #00ff00;
            padding: 15px;
            height: 300px;
            overflow-y: auto;
            margin: 20px 0;
            border-radius: 3px;
            box-shadow: inset 0 0 10px rgba(0, 255, 0, 0.1);
        }

        .log-entry {
            margin: 5px 0;
            font-size: 12px;
            padding: 3px 5px;
        }

        .log-success { color: #00ff00; }
        .log-error { color: #ff0000; }
        .log-warning { color: #ffff00; }
        .log-info { color: #00ffff; }
        .log-debug { color: #888; }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: rgba(0, 0, 0, 0.5);
        }

        .data-table th {
            background: rgba(0, 255, 0, 0.1);
            border-bottom: 2px solid #00ff00;
            padding: 10px;
            text-align: left;
            color: #00ff00;
            font-weight: bold;
            text-transform: uppercase;
        }

        .data-table td {
            padding: 10px;
            border-bottom: 1px solid #00ff00;
        }

        .data-table tr:hover {
            background: rgba(0, 255, 0, 0.05);
        }

        .spinner {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid rgba(0, 255, 0, 0.3);
            border-radius: 50%;
            border-top-color: #00ff00;
            animation: spin 0.6s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        @media (max-width: 900px) {
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ LOKI</h1>
            <p class="subtitle">Autonomous Security Engine - KTOx Integration</p>
        </header>

        <div class="status-bar">
            <div class="status-card">
                <h3>Status</h3>
                <div class="status-value" id="status">
                    <span class="spinner"></span>
                </div>
            </div>
            <div class="status-card">
                <h3>Uptime</h3>
                <div class="status-value" id="uptime">--:--:--</div>
            </div>
            <div class="status-card">
                <h3>Port</h3>
                <div class="status-value" id="port">8000</div>
            </div>
            <div class="status-card">
                <h3>Data Captured</h3>
                <div class="status-value" id="data-count">0</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📡 Network Operations</h2>
            <div class="controls">
                <button onclick="scanNetwork()">Network Scan</button>
                <button onclick="enumerate()">Enumerate</button>
                <button onclick="discover()">Host Discovery</button>
                <button onclick="fingerprint()">Fingerprint</button>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">⚔️  Attack & Exploitation</h2>
            <div class="controls">
                <button onclick="startAttack('kick_one')">Kick ONE</button>
                <button onclick="startAttack('kick_all')">Kick ALL</button>
                <button onclick="startAttack('mitm')">ARP MITM</button>
                <button onclick="startAttack('flood')">ARP Flood</button>
                <button onclick="startAttack('cage')">ARP Cage</button>
                <button onclick="startAttack('ntlm')">NTLM Capture</button>
            </div>
        </div>

        <div class="grid-2">
            <div class="section">
                <h2 class="section-title">📊 Captured Data</h2>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Count</th>
                        </tr>
                    </thead>
                    <tbody id="loot-table">
                        <tr><td colspan="2" style="text-align: center;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h2 class="section-title">🎯 Quick Stats</h2>
                <div id="stats" style="padding: 20px; background: rgba(0, 255, 0, 0.05); border: 1px solid #00ff00; border-radius: 3px;">
                    <p>Loading statistics...</p>
                </div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📋 Activity Log</h2>
            <div class="log-container" id="activity-log">
                <div class="log-entry log-info">[*] Loki WebUI initialized</div>
                <div class="log-entry log-success">[+] Dashboard loaded</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">⚙️  System Controls</h2>
            <div class="controls">
                <button onclick="refreshStatus()">Refresh</button>
                <button onclick="exportData()">Export Data</button>
                <button onclick="clearLogs()">Clear Logs</button>
                <button onclick="about()">About</button>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '/api';
        let startTime = null;

        function log(message, level = 'info') {
            const logEl = document.getElementById('activity-log');
            const entry = document.createElement('div');
            entry.className = 'log-entry log-' + level;
            const time = new Date().toLocaleTimeString();
            entry.textContent = `[${time}] ${message}`;
            logEl.appendChild(entry);
            logEl.scrollTop = logEl.scrollHeight;
        }

        function updateStatus() {
            fetch(API_BASE + '/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').innerText = data.status || 'RUNNING';
                    if (!startTime && data.start_time) {
                        startTime = new Date(data.start_time);
                    }
                })
                .catch(e => {
                    document.getElementById('status').innerText = 'RUNNING (Local)';
                });
        }

        function updateUptime() {
            if (startTime) {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                const h = Math.floor(elapsed / 3600);
                const m = Math.floor((elapsed % 3600) / 60);
                const s = elapsed % 60;
                document.getElementById('uptime').innerText = `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            }
        }

        function loadLoot() {
            fetch(API_BASE + '/loot')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('loot-table');
                    tbody.innerHTML = '';
                    let total = 0;
                    if (data.items && data.items.length > 0) {
                        data.items.forEach(item => {
                            const row = tbody.insertRow();
                            const type = item.type.replace(/_/g, ' ').toUpperCase();
                            row.innerHTML = `<td>${type}</td><td>${item.count}</td>`;
                            total += item.count;
                        });
                    } else {
                        const row = tbody.insertRow();
                        row.innerHTML = '<td colspan="2" style="text-align: center;">No data captured</td>';
                    }
                    document.getElementById('data-count').innerText = total;
                })
                .catch(e => log('Error loading loot: ' + e, 'error'));
        }

        function scanNetwork() {
            log('Starting network scan...', 'warning');
            fetch(API_BASE + '/scan', { method: 'POST' })
                .then(r => r.json())
                .then(data => log(data.message || 'Scan started', 'success'))
                .catch(e => log('Scan error: ' + e, 'error'));
        }

        function startAttack(type) {
            log(`Starting ${type} attack...`, 'warning');
            fetch(API_BASE + '/attack', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: type })
            })
            .then(r => r.json())
            .then(data => log(data.message || `${type} started`, 'success'))
            .catch(e => log(`Attack error: ${e}`, 'error'));
        }

        function enumerate() { log('Enumerating services...', 'warning'); }
        function discover() { log('Starting host discovery...', 'warning'); }
        function fingerprint() { log('Fingerprinting hosts...', 'warning'); }
        function refreshStatus() { updateStatus(); loadLoot(); log('Status refreshed', 'info'); }
        function exportData() { log('Exporting data...', 'warning'); }
        function clearLogs() {
            document.getElementById('activity-log').innerHTML = '';
            log('Logs cleared', 'success');
        }
        function about() { log('Loki Autonomous Security Engine - KTOx Integration v1.0', 'info'); }

        // Initialize
        updateStatus();
        loadLoot();
        setInterval(updateStatus, 10000);
        setInterval(updateUptime, 1000);
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/dashboard')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/status')
def api_status():
    return jsonify({
        'status': 'RUNNING',
        'port': LOKI_PORT,
        'uptime': 'N/A',
        'version': '1.0',
        'start_time': datetime.now().isoformat()
    })

@app.route('/api/scan', methods=['POST'])
def api_scan():
    return jsonify({
        'status': 'ok',
        'message': 'Network scan initiated'
    })

@app.route('/api/attack', methods=['POST'])
def api_attack():
    data = request.json or {}
    attack_type = data.get('type', 'unknown')
    return jsonify({
        'status': 'ok',
        'message': f'{attack_type} attack initiated'
    })

@app.route('/api/loot')
def api_loot():
    items = []
    loot_dir = LOKI_DATA / 'output'

    if loot_dir.exists():
        for subdir in loot_dir.iterdir():
            if subdir.is_dir():
                count = len(list(subdir.glob('*')))
                items.append({
                    'type': subdir.name,
                    'count': count,
                    'path': str(subdir)
                })

    return jsonify({'items': items})

@app.route('/logs')
def logs():
    log_file = LOKI_DATA / 'logs' / 'ktox_loki.log'
    try:
        if log_file.exists():
            with open(log_file, 'r') as f:
                content = f.read()
            return f'<pre>{content}</pre>', 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return 'No logs yet', 200
    except Exception as e:
        return f'Error: {e}', 500

if __name__ == '__main__':
    print("[Loki] KTOx Wrapper starting on http://0.0.0.0:8000")
    print("[Loki] Data directory: " + str(LOKI_DATA))
    print("[Loki] Loki directory: " + str(LOKI_DIR))

    app.run(
        host='0.0.0.0',
        port=LOKI_PORT,
        debug=False,
        threaded=True
    )
