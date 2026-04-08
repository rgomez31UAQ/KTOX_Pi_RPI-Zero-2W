#!/usr/bin/env python3
# NAME: Web File Explorer
# DESC: Starts a web server for file browsing/upload/download.
"""
KTOx Payload — Web File Explorer
=================================
PURPOSE:
Starts a Flask-based web server that allows browsing, uploading,
and downloading files throughout the KTOx directory (or the entire /root).

CONTROLS:
- KEY1: Toggle server status (Start/Stop)
- KEY3: Exit payload

LCD:
- IP:Port of the server
- Status: Running / Stopped
"""

import os
import sys
import threading
import socket
import logging
from flask import Flask, render_template_string, request, send_from_directory, abort, redirect, url_for
from werkzeug.utils import secure_filename

# Add KTOx root to path for drivers
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..", "..")))

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    import LCD_Config
    from PIL import Image, ImageDraw, ImageFont
    from payloads._display_helper import ScaledDraw, scaled_font
    from payloads._input_helper import get_button
except ImportError:
    # Shim for local testing if not on hardware
    class GPIO:
        BCM = 11
        IN = 1
        PUD_UP = 2
        @staticmethod
        def setmode(a): pass
        @staticmethod
        def setup(a, b, pull_up_down=None): pass
        @staticmethod
        def input(a): return 1
    class LCD_1in44:
        SCAN_DIR_DFT = 0
        LCD_SCALE = 1.0
        class LCD:
            width = 128
            height = 128
            def LCD_Init(self, a): pass
            def LCD_ShowImage(self, a, b, c): pass
    def scaled_font(): return None
    class ScaledDraw:
        def __init__(self, img): self.d = ImageDraw.Draw(img)
        def rectangle(self, *args, **kwargs): self.d.rectangle(*args, **kwargs)
        def text(self, *args, **kwargs): self.d.text(*args, **kwargs)

# Configuration
PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}
HTTP_PORT = 8888
EXPLORE_ROOT = "/root" # Allow exploring throughout KTOx and beyond
KTOX_DIR = "/root/KTOx"

# HTML Template
HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx Web File Explorer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
        h1 { color: #00ff41; font-size: 1.5rem; margin-bottom: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: #1e1e1e; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .path { font-family: monospace; color: #888; margin-bottom: 10px; word-break: break-all; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        li:last-child { border-bottom: none; }
        a { color: #4dabf7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .folder { font-weight: bold; color: #ffd43b; }
        .upload-form { margin-top: 30px; padding-top: 20px; border-top: 2px solid #333; }
        input[type="file"] { background: #333; color: white; padding: 10px; border-radius: 4px; border: 1px solid #444; width: 100%; box-sizing: border-box; }
        button { background: #00ff41; color: #000; border: none; padding: 10px 20px; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top: 10px; }
        button:hover { background: #00cc33; }
        .back { margin-bottom: 20px; display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>KTOx File Explorer</h1>
        <div class="path">Current Path: {{ current_path }}</div>
        
        {% if current_path != explore_root %}
            <a href="{{ url_for('browse', path=parent_path) }}" class="back">&larr; Back</a>
        {% endif %}

        <ul>
            {% for item in items %}
            <li>
                {% if item.is_dir %}
                    <a href="{{ url_for('browse', path=item.rel_path) }}" class="folder">📁 {{ item.name }}</a>
                {% else %}
                    <span>📄 {{ item.name }} ({{ item.size }})</span>
                    <a href="{{ url_for('download', path=item.rel_path) }}">Download</a>
                {% endif %}
            </li>
            {% endfor %}
        </ul>

        <div class="upload-form">
            <h3>Upload File to this Directory</h3>
            <form method="POST" action="{{ url_for('upload', path=current_path_rel) }}" enctype="multipart/form-data">
                <input type="file" name="file" required>
                <button type="submit">Upload</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

app = Flask(__name__)
# Disable Flask logging to avoid LCD output clutter (if any)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route("/")
def index():
    return redirect(url_for('browse', path=''))

@app.route("/browse/")
@app.route("/browse/<path:path>")
def browse(path=""):
    full_path = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full_path.startswith(EXPLORE_ROOT):
        abort(403)
    
    if not os.path.isdir(full_path):
        abort(404)

    items = []
    try:
        for entry in sorted(os.listdir(full_path)):
            entry_full = os.path.join(full_path, entry)
            is_dir = os.path.isdir(entry_full)
            rel_path = os.path.relpath(entry_full, EXPLORE_ROOT)
            size = ""
            if not is_dir:
                s = os.path.getsize(entry_full)
                if s < 1024: size = f"{s}B"
                elif s < 1024*1024: size = f"{s/1024:.1f}KB"
                else: size = f"{s/1024/1024:.1f}MB"
            
            items.append({
                "name": entry,
                "is_dir": is_dir,
                "rel_path": rel_path,
                "size": size
            })
    except Exception as e:
        return str(e), 500

    parent_path = os.path.relpath(os.path.dirname(full_path), EXPLORE_ROOT)
    if parent_path == ".": parent_path = ""

    return render_template_string(
        HTML_TPL, 
        items=items, 
        current_path=full_path, 
        current_path_rel=path,
        explore_root=EXPLORE_ROOT,
        parent_path=parent_path
    )

@app.route("/download/<path:path>")
def download(path):
    full_path = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full_path.startswith(EXPLORE_ROOT):
        abort(403)
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

@app.route("/upload/<path:path>", methods=["POST"])
def upload(path):
    full_path = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full_path.startswith(EXPLORE_ROOT):
        abort(403)
    
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400
    
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(full_path, filename))
        return redirect(url_for('browse', path=path))

class ServerThread(threading.Thread):
    def __init__(self, app, port):
        threading.Thread.__init__(self)
        self.srv = None
        self.app = app
        self.port = port
        self.daemon = True

    def run(self):
        self.app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False)

# LCD State
class PayloadState:
    def __init__(self):
        self.running = False
        self.server_thread = None
        self.ip = self.get_ip()

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def toggle(self):
        if self.running:
            # Flask doesn't have a simple 'stop' in app.run(). 
            # For a payload, we can just let it run or use a more complex server.
            # But usually we just leave it or exit the payload.
            # To keep it simple, we'll just stop updating the LCD and exit if requested.
            pass
        else:
            self.server_thread = ServerThread(app, HTTP_PORT)
            self.server_thread.start()
            self.running = True

def main():
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    width, height = lcd.width, lcd.height
    
    state = PayloadState()
    
    # Pre-start the server for better UX
    state.toggle()

    while True:
        # Drawing
        img = Image.new('RGB', (width, height), 'black')
        draw = ScaledDraw(img)
        
        # Header
        draw.rectangle((0, 0, 128, 20), fill='#00ff41')
        draw.text((5, 2), "WEB EXPLORER", fill='black')
        
        # Body
        y = 30
        draw.text((5, y), f"IP: {state.ip}", fill='white')
        y += 15
        draw.text((5, y), f"Port: {HTTP_PORT}", fill='white')
        y += 20
        
        status_color = '#00ff41' if state.running else '#ff4100'
        status_text = "RUNNING" if state.running else "STOPPED"
        draw.text((5, y), "Status:", fill='white')
        draw.text((55, y), status_text, fill=status_color)
        
        y += 25
        draw.text((5, y), "URL:", fill='#888')
        y += 12
        draw.text((5, y), f"http://{state.ip}:{HTTP_PORT}", fill='#4dabf7')

        # Footer
        draw.text((5, 110), "KEY3: Exit", fill='#888')

        lcd.LCD_ShowImage(img, 0, 0)
        
        # Input
        btn = get_button(PINS, GPIO)
        if btn == "KEY3":
            break
        
        threading.Event().wait(0.2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()