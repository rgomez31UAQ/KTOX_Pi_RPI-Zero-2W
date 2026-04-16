#!/usr/bin/env python3
"""
KTOx Payload – USB File Explorer
=========================================================
- Uses pyudev for reliable USB device detection
- Finds or creates the mount point
- Auto-mounts the drive if necessary
- Full cyberpunk web UI to copy files to KTOx
"""

import os
import sys
import time
import socket
import threading
import shutil
import subprocess
from flask import Flask, render_template_string, request, jsonify

# ----------------------------------------------------------------------
# Hardware & LCD
# ----------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not found – LCD disabled")

# Try to import pyudev - this is the key to reliable detection
try:
    import pyudev
    HAS_UDEV = True
except ImportError:
    HAS_UDEV = False
    print("pyudev not found. Install with: pip install pyudev")

PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}

if HAS_HW:
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    W, H = 128, 128
    try:
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    except:
        font_sm = font_bold = ImageFont.load_default()

# ----------------------------------------------------------------------
# Flask app
# ----------------------------------------------------------------------
PORT = 8889
app = Flask(__name__)

# ----------------------------------------------------------------------
# USB detection using pyudev
# ----------------------------------------------------------------------
def get_usb_mounts():
    """Get list of currently mounted USB drives."""
    mounts = []
    if not HAS_UDEV:
        # Fallback to checking common mount points
        base_dirs = ["/media/pi", "/media", "/mnt", "/run/media"]
        for base in base_dirs:
            if os.path.isdir(base):
                for entry in os.listdir(base):
                    full = os.path.join(base, entry)
                    if os.path.ismount(full):
                        mounts.append(full)
        return mounts

    context = pyudev.Context()
    for device in context.list_devices(subsystem='block', DEVTYPE='partition'):
        # Check if it's a USB device
        if device.get('ID_BUS') == 'usb':
            # Get the device node (e.g., /dev/sda1)
            dev_node = device.device_node
            if dev_node:
                # Use findmnt to get the mount point
                try:
                    result = subprocess.run(
                        ['findmnt', '-no', 'TARGET', dev_node],
                        capture_output=True, text=True, check=False
                    )
                    mount_point = result.stdout.strip()
                    if mount_point and os.path.exists(mount_point):
                        mounts.append(mount_point)
                except:
                    pass
    return sorted(set(mounts))

def mount_usb(dev_node):
    """Attempt to mount a USB device to a standard location."""
    mount_base = "/media/usb"
    # Create a unique mount point based on device node
    mount_point = os.path.join(mount_base, os.path.basename(dev_node))
    os.makedirs(mount_point, exist_ok=True)
    try:
        subprocess.run(['sudo', 'mount', dev_node, mount_point], check=True, capture_output=True)
        return mount_point
    except subprocess.CalledProcessError:
        return None

def find_usb_drives():
    """Return list of USB drives with device node and mount point."""
    drives = []
    if not HAS_UDEV:
        # Fallback: return mount points from common locations
        for mp in get_usb_mounts():
            drives.append({'mount': mp, 'device': 'unknown'})
        return drives

    context = pyudev.Context()
    for device in context.list_devices(subsystem='block', DEVTYPE='partition'):
        if device.get('ID_BUS') == 'usb':
            dev_node = device.device_node
            if not dev_node:
                continue

            # Try to find existing mount point
            mount_point = None
            try:
                result = subprocess.run(
                    ['findmnt', '-no', 'TARGET', dev_node],
                    capture_output=True, text=True, check=False
                )
                mount_point = result.stdout.strip()
            except:
                pass

            # If not mounted, try to mount it
            if not mount_point or not os.path.exists(mount_point):
                mount_point = mount_usb(dev_node)

            if mount_point and os.path.exists(mount_point):
                drives.append({'mount': mount_point, 'device': dev_node})

    return drives

# ----------------------------------------------------------------------
# File listing helpers
# ----------------------------------------------------------------------
def list_directory(path):
    items = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
            items.append({
                'name': entry.name,
                'type': 'dir' if entry.is_dir() else 'file',
                'size': entry.stat().st_size if entry.is_file() else 0,
                'path': entry.path
            })
    except PermissionError:
        pass
    return items

def size_fmt(size):
    for unit in ['B','KB','MB','GB']:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TB"

# ----------------------------------------------------------------------
# HTML template (cyberpunk)
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx USB Explorer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0a0f0f;
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            color: #0ff;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            font-size: 2rem;
            text-shadow: 0 0 5px #0ff;
            border-left: 4px solid #0ff;
            padding-left: 20px;
            margin-bottom: 20px;
        }
        .panel-row { display: flex; gap: 20px; flex-wrap: wrap; }
        .panel {
            flex: 1;
            background: #0f1212;
            border: 1px solid #0ff;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 0 10px rgba(0,255,255,0.2);
        }
        .panel h2 {
            color: #f0f;
            text-shadow: 0 0 3px #f0f;
            border-bottom: 1px solid #0ff;
            padding-bottom: 5px;
            margin-bottom: 15px;
        }
        .usb-selector select {
            background: #111;
            color: #0ff;
            border: 1px solid #0ff;
            padding: 8px;
            width: 100%;
            font-family: monospace;
            margin-bottom: 15px;
        }
        .file-list {
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.85rem;
        }
        .file-item {
            padding: 5px 8px;
            cursor: pointer;
            border-bottom: 1px solid #1a2a2a;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .file-item:hover { background: #1a2a2a; text-shadow: 0 0 2px #0ff; }
        .file-item.selected { background: #2a4a4a; border-left: 3px solid #0ff; }
        .file-icon { width: 20px; text-align: center; }
        .file-name { flex: 1; word-break: break-word; }
        .file-size { color: #8a8; font-size: 0.75rem; }
        .dir-icon { color: #0ff; }
        .file-icon-file { color: #f0f; }
        .dest-path {
            background: #111;
            padding: 8px;
            border: 1px solid #0ff;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 15px;
        }
        .dest-path span { flex: 1; word-break: break-all; }
        .dest-path button {
            background: #0a2a2a;
            border: 1px solid #0ff;
            color: #0ff;
            padding: 4px 10px;
            cursor: pointer;
        }
        .dest-path button:hover { background: #0ff; color: #000; }
        .copy-btn {
            background: #0ff;
            color: #000;
            border: none;
            padding: 12px 24px;
            font-size: 1.2rem;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            transition: 0.2s;
            box-shadow: 0 0 10px #0ff;
            display: block;
            width: 100%;
            margin-top: 20px;
        }
        .copy-btn:hover { background: #f0f; box-shadow: 0 0 15px #f0f; }
        .status {
            margin-top: 15px;
            padding: 8px;
            background: #0a1a1a;
            border-left: 4px solid #0ff;
            font-family: monospace;
        }
        footer { margin-top: 30px; text-align: center; color: #4a6; font-size: 0.7rem; }
        ::-webkit-scrollbar { width: 6px; background: #0a0f0f; }
        ::-webkit-scrollbar-thumb { background: #0ff; border-radius: 3px; }
    </style>
</head>
<body>
<div class="container">
    <h1>⎯ KTOx USB EXPLORER ⎯</h1>
    <div class="panel-row">
        <div class="panel">
            <h2>⚡ USB DRIVE</h2>
            <div class="usb-selector">
                <select id="usbSelect" onchange="loadUsbRoot()">
                    <option value="">-- Select USB --</option>
                    {% for drive in drives %}
                    <option value="{{ drive.mount }}">{{ drive.mount }}</option>
                    {% endfor %}
                </select>
            </div>
            <div id="usbFileList" class="file-list">Select a USB drive</div>
        </div>
        <div class="panel">
            <h2>💾 LOCAL DESTINATION</h2>
            <div class="dest-path">
                <span id="destPath">/root</span>
                <button onclick="browseLocal('/root')">Home</button>
                <button onclick="browseLocal('..')">Up</button>
            </div>
            <div id="localFileList" class="file-list">Loading...</div>
        </div>
    </div>
    <button class="copy-btn" onclick="copySelected()">▶ COPY SELECTED TO DESTINATION ◀</button>
    <div id="status" class="status">Ready.</div>
    <footer>KTOx Cyberdeck – USB File Transfer</footer>
</div>

<script>
    let currentUsbPath = "";
    let currentLocalPath = "/root";
    let selectedUsbFiles = [];

    function loadUsbRoot() {
        const usb = document.getElementById('usbSelect').value;
        if (!usb) {
            document.getElementById('usbFileList').innerHTML = '<div class="file-item">Select a USB drive</div>';
            return;
        }
        fetch('/api/usb/list?path=' + encodeURIComponent(usb))
            .then(r => r.json())
            .then(data => renderFileList(data, 'usbFileList', true));
        currentUsbPath = usb;
    }

    function browseLocal(path) {
        if (path === '..') {
            let parent = currentLocalPath.split('/').slice(0, -1).join('/');
            if (!parent) parent = '/';
            path = parent;
        }
        fetch('/api/local/list?path=' + encodeURIComponent(path))
            .then(r => r.json())
            .then(data => {
                renderFileList(data, 'localFileList', false);
                currentLocalPath = path;
                document.getElementById('destPath').innerText = path;
            });
    }

    function renderFileList(items, containerId, isUsb) {
        const container = document.getElementById(containerId);
        if (!items || items.length === 0) {
            container.innerHTML = '<div class="file-item">(empty)</div>';
            return;
        }
        let html = '';
        for (let item of items) {
            const icon = item.type === 'dir' ? '📁' : '📄';
            const colorClass = item.type === 'dir' ? 'dir-icon' : 'file-icon-file';
            const sizeText = item.type === 'file' ? ` (${item.size_fmt})` : '';
            const selectable = isUsb ? `onclick="toggleSelect('${item.path}', this)"` : '';
            html += `
                <div class="file-item" data-path="${item.path}" ${selectable}>
                    <div class="file-icon ${colorClass}">${icon}</div>
                    <div class="file-name">${escapeHtml(item.name)}</div>
                    <div class="file-size">${sizeText}</div>
                </div>
            `;
        }
        container.innerHTML = html;
        if (isUsb) selectedUsbFiles = [];
    }

    function toggleSelect(path, element) {
        if (element.classList.contains('selected')) {
            element.classList.remove('selected');
            selectedUsbFiles = selectedUsbFiles.filter(p => p !== path);
        } else {
            element.classList.add('selected');
            selectedUsbFiles.push(path);
        }
    }

    function copySelected() {
        if (selectedUsbFiles.length === 0) {
            document.getElementById('status').innerText = '❌ No files selected.';
            return;
        }
        document.getElementById('status').innerHTML = '⏳ Copying... please wait.';
        fetch('/api/copy', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ sources: selectedUsbFiles, destination: currentLocalPath })
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('status').innerHTML = `✅ ${data.message}`;
            browseLocal(currentLocalPath);
            selectedUsbFiles = [];
            document.querySelectorAll('#usbFileList .file-item').forEach(el => el.classList.remove('selected'));
        })
        .catch(err => {
            document.getElementById('status').innerHTML = `❌ Error: ${err}`;
        });
    }

    function escapeHtml(str) {
        return str.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    }

    browseLocal('/root');
</script>
</body>
</html>
"""

# ----------------------------------------------------------------------
# Flask routes
# ----------------------------------------------------------------------
@app.route('/')
def index():
    drives = find_usb_drives()
    return render_template_string(HTML_TEMPLATE, drives=drives)

@app.route('/api/usb/list')
def api_usb_list():
    path = request.args.get('path', '')
    if not os.path.exists(path):
        return jsonify([])
    items = list_directory(path)
    for i in items:
        i['size_fmt'] = size_fmt(i['size']) if i['type'] == 'file' else ''
    return jsonify(items)

@app.route('/api/local/list')
def api_local_list():
    path = request.args.get('path', '/root')
    if not os.path.exists(path):
        path = '/root'
    items = list_directory(path)
    for i in items:
        i['size_fmt'] = size_fmt(i['size']) if i['type'] == 'file' else ''
    return jsonify(items)

@app.route('/api/copy', methods=['POST'])
def api_copy():
    data = request.get_json()
    sources = data.get('sources', [])
    dest = data.get('destination', '')
    if not sources or not dest:
        return jsonify({'message': 'Invalid request'}), 400
    if not os.path.isdir(dest):
        return jsonify({'message': 'Destination is not a directory'}), 400
    copied = 0
    errors = []
    for src in sources:
        try:
            if os.path.isdir(src):
                dest_path = os.path.join(dest, os.path.basename(src))
                shutil.copytree(src, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
            copied += 1
        except Exception as e:
            errors.append(f"{src}: {str(e)}")
    msg = f"Copied {copied} item(s)."
    if errors:
        msg += f" Errors: {', '.join(errors[:3])}"
    return jsonify({'message': msg})

# ----------------------------------------------------------------------
# LCD display
# ----------------------------------------------------------------------
def lcd_loop():
    if not HAS_HW:
        return
    ip = socket.gethostbyname(socket.gethostname())
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        s.close()
    except:
        pass
    while True:
        drives = find_usb_drives()
        usb_status = drives[0]['mount'] if drives else "none"
        img = Image.new("RGB", (W, H), "#0A0000")
        d = ImageDraw.Draw(img)
        d.rectangle((0,0,W,17), fill="#8B0000")
        d.text((4,3), "USB EXPLORER", font=font_bold, fill="#FF3333")
        y = 20
        d.text((4,y), f"IP: {ip}:{PORT}", font=font_sm, fill="#FFBBBB"); y+=12
        d.text((4,y), f"USB: {usb_status[:15]}", font=font_sm, fill="#FFBBBB"); y+=12
        d.text((4,y), "Status: RUNNING", font=font_sm, fill="#00FF00"); y+=12
        d.text((4,y), "KEY3=Exit", font=font_sm, fill="#FF7777")
        d.rectangle((0,H-12,W,H), fill="#220000")
        LCD.LCD_ShowImage(img, 0, 0)
        time.sleep(2)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not HAS_UDEV:
        print("\n⚠️  pyudev is not installed.")
        print("   Please install it with: pip install pyudev\n")
        print("   The script will continue with fallback detection, but may be less reliable.\n")

    if HAS_HW:
        threading.Thread(target=lcd_loop, daemon=True).start()
        def run_flask():
            app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
        server_thread = threading.Thread(target=run_flask, daemon=True)
        server_thread.start()
        time.sleep(2)
        while True:
            for name, pin in PINS.items():
                if GPIO.input(pin) == 0:
                    time.sleep(0.05)
                    if name == "KEY3":
                        GPIO.cleanup()
                        LCD.LCD_Clear()
                        os._exit(0)
            time.sleep(0.1)
    else:
        app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == "__main__":
    main()
