#!/usr/bin/env python3

# NAME: Web File Explorer

# DESC: Browse, upload and download files over HTTP on port 8888.

# “””
KTOx Payload — Web File Explorer

Starts a Flask web server at http://<device-ip>:8888 for browsing,
uploading, and downloading files under /root.

Controls:
KEY1  — Start / stop the HTTP server
KEY3  — Exit payload

LCD shows the server URL and running status.
“””

import os
import sys
import time
import socket
import threading
import logging

sys.path.append(os.path.abspath(os.path.join(**file**, “..”, “..”, “..”)))

import RPi.GPIO as GPIO
import LCD_1in44
import LCD_Config
from PIL import Image, ImageDraw, ImageFont
from payloads._display_helper import ScaledDraw, scaled_font
from payloads._input_helper import get_button

# ── GPIO ──────────────────────────────────────────────────────────────────────

PINS = {
“UP”:   6,  “DOWN”: 19, “LEFT”: 5,  “RIGHT”: 26,
“OK”:  13,  “KEY1”: 21, “KEY2”: 20, “KEY3”:  16,
}
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ── LCD ───────────────────────────────────────────────────────────────────────

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
WIDTH, HEIGHT = LCD.width, LCD.height
font = scaled_font(9)

# ── Config ────────────────────────────────────────────────────────────────────

HTTP_PORT    = 8888
EXPLORE_ROOT = “/root”
DEBOUNCE     = 0.25

# ── Flask app (imported lazily so missing Flask doesn’t crash on import) ──────

def _build_flask_app():
try:
from flask import (Flask, render_template_string, request,
send_from_directory, abort, redirect, url_for)
from werkzeug.utils import secure_filename
except ImportError:
return None, None

```
_HTML = """<!DOCTYPE html>
```

<html>
<head>
  <title>KTOx File Explorer</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body{font-family:system-ui,sans-serif;background:#121212;color:#e0e0e0;margin:0;padding:20px}
    h1{color:#c0392b;font-size:1.4rem;margin-bottom:16px}
    .container{max-width:820px;margin:0 auto;background:#1e1e1e;padding:20px;border-radius:6px}
    .path{font-family:monospace;color:#888;margin-bottom:10px;word-break:break-all}
    ul{list-style:none;padding:0}
    li{padding:9px 4px;border-bottom:1px solid #2a2a2a;display:flex;justify-content:space-between;align-items:center}
    li:last-child{border-bottom:none}
    a{color:#4dabf7;text-decoration:none}
    a:hover{text-decoration:underline}
    .folder{font-weight:bold;color:#ffd43b}
    .upload-form{margin-top:24px;padding-top:18px;border-top:2px solid #333}
    input[type=file]{background:#2a2a2a;color:#e0e0e0;padding:8px;border-radius:4px;border:1px solid #444;width:100%;box-sizing:border-box}
    button{background:#c0392b;color:#fff;border:none;padding:10px 22px;border-radius:4px;font-weight:bold;cursor:pointer;margin-top:10px}
    button:hover{background:#a93226}
    .back{margin-bottom:18px;display:inline-block}
  </style>
</head>
<body>
<div class="container">
  <h1>KTOx File Explorer</h1>
  <div class="path">{{ current_path }}</div>
  {% if current_path != explore_root %}
    <a href="{{ url_for('browse', path=parent_path) }}" class="back">&larr; Back</a>
  {% endif %}
  <ul>
    {% for item in items %}
    <li>
      {% if item.is_dir %}
        <a href="{{ url_for('browse', path=item.rel_path) }}" class="folder">&#128193; {{ item.name }}</a>
      {% else %}
        <span>&#128196; {{ item.name }} <small style="color:#666">({{ item.size }})</small></span>
        <a href="{{ url_for('download', path=item.rel_path) }}">Download</a>
      {% endif %}
    </li>
    {% endfor %}
  </ul>
  <div class="upload-form">
    <h3 style="color:#c0392b">Upload to this directory</h3>
    <form method="POST" action="{{ url_for('upload', path=current_path_rel) }}" enctype="multipart/form-data">
      <input type="file" name="file" required>
      <button type="submit">Upload</button>
    </form>
  </div>
</div>
</body>
</html>"""

```
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

@app.route("/")
def index():
    return redirect(url_for("browse", path=""))

@app.route("/browse/")
@app.route("/browse/<path:path>")
def browse(path=""):
    full = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full.startswith(EXPLORE_ROOT):
        abort(403)
    if not os.path.isdir(full):
        abort(404)
    items = []
    try:
        for entry in sorted(os.listdir(full)):
            efull   = os.path.join(full, entry)
            is_dir  = os.path.isdir(efull)
            rel     = os.path.relpath(efull, EXPLORE_ROOT)
            size    = ""
            if not is_dir:
                s = os.path.getsize(efull)
                size = (f"{s}B" if s < 1024 else
                        f"{s/1024:.1f}KB" if s < 1048576 else
                        f"{s/1048576:.1f}MB")
            items.append({"name": entry, "is_dir": is_dir,
                          "rel_path": rel, "size": size})
    except Exception as e:
        return str(e), 500
    parent = os.path.relpath(os.path.dirname(full), EXPLORE_ROOT)
    if parent == ".":
        parent = ""
    return render_template_string(_HTML, items=items,
                                  current_path=full,
                                  current_path_rel=path,
                                  explore_root=EXPLORE_ROOT,
                                  parent_path=parent)

@app.route("/download/<path:path>")
def download(path):
    full = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full.startswith(EXPLORE_ROOT):
        abort(403)
    return send_from_directory(os.path.dirname(full),
                               os.path.basename(full))

@app.route("/upload/<path:path>", methods=["POST"])
def upload(path):
    full = os.path.normpath(os.path.join(EXPLORE_ROOT, path))
    if not full.startswith(EXPLORE_ROOT):
        abort(403)
    f = request.files.get("file")
    if not f or f.filename == "":
        return "No file", 400
    f.save(os.path.join(full, secure_filename(f.filename)))
    return redirect(url_for("browse", path=path))

return app, Flask
```

class _ServerThread(threading.Thread):
def **init**(self, app):
super().**init**(daemon=True)
self._app = app

```
def run(self):
    self._app.run(host="0.0.0.0", port=HTTP_PORT,
                  debug=False, use_reloader=False)
```

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ip():
try:
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
s.connect((“8.8.8.8”, 80))
ip = s.getsockname()[0]
s.close()
return ip
except Exception:
return “127.0.0.1”

def _draw(ip, running, error_msg=””):
img  = Image.new(“RGB”, (WIDTH, HEIGHT), “#0a0a0a”)
d    = ScaledDraw(img)

```
# ── Header bar ────────────────────────────────────────────────────────────
d.rectangle((0, 0, 128, 18), fill="#8B0000")
d.text((4, 3), "WEB EXPLORER", fill="#F0EDE8", font=font)

# ── Status badge ─────────────────────────────────────────────────────────
sc = "#2ecc71" if running else "#c0392b"
st = " RUNNING " if running else " STOPPED "
d.rectangle((0, 20, 128, 34), fill="#1a0000")
d.text((4, 22), "Status:", fill="#888888", font=font)
d.text((56, 22), st, fill=sc, font=font)

# ── URL block ─────────────────────────────────────────────────────────────
d.text((4, 40), "IP:", fill="#888888", font=font)
d.text((28, 40), ip, fill="#c8c8c8", font=font)

d.text((4, 54), "Port:", fill="#888888", font=font)
d.text((40, 54), str(HTTP_PORT), fill="#c8c8c8", font=font)

url = f"http://{ip}:{HTTP_PORT}"
d.text((4, 68), url, fill="#4dabf7", font=font)

# ── Error line ────────────────────────────────────────────────────────────
if error_msg:
    d.text((4, 84), error_msg[:20], fill="#e74c3c", font=font)

# ── Hint bar ──────────────────────────────────────────────────────────────
d.rectangle((0, 108, 128, 128), fill="#1a0000")
d.text((4, 110), "KEY1:start/stop", fill="#606060", font=font)
d.text((4, 119), "KEY3:exit", fill="#606060", font=font)

LCD.LCD_ShowImage(img, 0, 0)
```

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
ip        = _get_ip()
running   = False
srv_thread = None
error_msg  = “”
last_btn   = 0.0

```
flask_app, _Flask = _build_flask_app()
if flask_app is None:
    # Flask not installed — show error and wait for KEY3
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0a0a0a")
    d   = ScaledDraw(img)
    d.rectangle((0, 0, 128, 18), fill="#8B0000")
    d.text((4, 3), "WEB EXPLORER", fill="#F0EDE8", font=font)
    d.text((4, 30), "Flask not found.", fill="#e74c3c", font=font)
    d.text((4, 44), "Install with:", fill="#c8c8c8", font=font)
    d.text((4, 58), "pip3 install flask", fill="#4dabf7", font=font)
    d.text((4, 80), "KEY3: Exit", fill="#606060", font=font)
    LCD.LCD_ShowImage(img, 0, 0)
    while True:
        btn = get_button(PINS, GPIO)
        if btn == "KEY3":
            break
        time.sleep(0.1)
    return

_draw(ip, running)

while True:
    btn = get_button(PINS, GPIO)

    if btn and (time.time() - last_btn) > DEBOUNCE:
        last_btn = time.time()
        error_msg = ""

        if btn == "KEY3":
            break

        elif btn == "KEY1":
            if not running:
                # Start the server
                try:
                    srv_thread = _ServerThread(flask_app)
                    srv_thread.start()
                    running = True
                except Exception as e:
                    error_msg = str(e)[:20]
            else:
                # Flask's dev server has no clean stop — we kill our own
                # process group.  For a payload this is fine; exec_payload()
                # will restore GPIO + LCD after we exit.
                running = False
                srv_thread = None   # thread is daemon — dies with payload

        _draw(ip, running, error_msg)

    time.sleep(0.05)
```

if **name** == “**main**”:
try:
main()
except KeyboardInterrupt:
pass
finally:
GPIO.cleanup()
