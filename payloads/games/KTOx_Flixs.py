#!/usr/bin/env python3
"""
KTOx Payload – Netflix‑Style Video Server
==========================================
- Serves videos from /root/Videos over HTTP (web interface)
- LCD shows server IP, video count, QR code, and status
- Use any browser on your phone/laptop to watch videos
- No Bluetooth/PulseAudio issues – client handles audio
"""

import os
import sys
import time
import threading
import subprocess
import socket
import qrcode
from flask import Flask, render_template_string, send_from_directory

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
    print("Hardware not found – exiting")
    sys.exit(1)

PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY3":16}
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
# Flask web server configuration
# ----------------------------------------------------------------------
VIDEO_DIR = "/root/Videos"
THUMB_DIR = "/root/Videos/thumbnails"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')

# Create directories if they don't exist
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

app = Flask(__name__)

# ----------------------------------------------------------------------
# Generate thumbnails using ffmpeg
# ----------------------------------------------------------------------
def generate_thumbnails():
    """Create a preview image for every video."""
    for f in os.listdir(VIDEO_DIR):
        if f.lower().endswith(VIDEO_EXTS):
            thumb_path = os.path.join(THUMB_DIR, f + ".jpg")
            if not os.path.exists(thumb_path):
                video_path = os.path.join(VIDEO_DIR, f)
                subprocess.run([
                    "ffmpeg", "-i", video_path, "-ss", "00:00:02",
                    "-vframes", "1", "-q:v", "2", thumb_path
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ----------------------------------------------------------------------
# HTML templates (Netflix style)
# ----------------------------------------------------------------------
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx Video Server</title>
    <style>
        body { background: #141414; color: white; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 20px; }
        h1 { color: #E50914; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
        .card { background: #222; border-radius: 4px; overflow: hidden; transition: transform 0.3s; cursor: pointer; text-decoration: none; color: white; }
        .card:hover { transform: scale(1.05); }
        .card img { width: 100%; height: 120px; object-fit: cover; }
        .card-title { padding: 10px; font-size: 14px; text-align: center; }
        footer { margin-top: 40px; text-align: center; color: #666; }
    </style>
</head>
<body>
    <h1>KTOx NETFLIX</h1>
    <div class="grid">
        {% for video in videos %}
        <a href="/play/{{ video }}" class="card">
            <img src="/thumb/{{ video }}.jpg" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'200\' height=\'120\' viewBox=\'0 0 200 120\'%3E%3Crect width=\'200\' height=\'120\' fill=\'%23333\'/%3E%3Ctext x=\'50%25\' y=\'50%25\' text-anchor=\'middle\' dy=\'.3em\' fill=\'%23999\'%3ENo thumbnail%3C/text%3E%3C/svg%3E'">
            <div class="card-title">{{ video }}</div>
        </a>
        {% endfor %}
    </div>
    <footer>KTOx Video Server – Powered by Raspberry Pi</footer>
</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Playing {{ video }}</title>
    <style>
        body { background: black; color: white; text-align: center; font-family: sans-serif; }
        video { width: 80%; max-width: 1000px; margin-top: 50px; outline: none; }
        .back { display: inline-block; margin-top: 20px; color: #E50914; text-decoration: none; font-size: 18px; }
    </style>
</head>
<body>
    <video controls autoplay>
        <source src="/stream/{{ video }}" type="video/mp4">
        Your browser does not support the video tag.
    </video>
    <br>
    <a href="/" class="back">← Back to Gallery</a>
</body>
</html>
"""

@app.route('/')
def index():
    videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    return render_template_string(INDEX_HTML, videos=videos)

@app.route('/play/<filename>')
def play(filename):
    return render_template_string(PLAYER_HTML, video=filename)

@app.route('/stream/<filename>')
def stream(filename):
    return send_from_directory(VIDEO_DIR, filename)

@app.route('/thumb/<filename>')
def thumb(filename):
    return send_from_directory(THUMB_DIR, filename)

# ----------------------------------------------------------------------
# LCD helpers
# ----------------------------------------------------------------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_qr(data):
    """Return PIL Image of QR code for the given data."""
    qr = qrcode.QRCode(box_size=2, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="white", back_color="black").get_image()

def draw_lcd(ip, video_count, server_running):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0,0,W,17), fill="#8B0000")
    d.text((4,3), "NETFLIX SERVER", font=font_bold, fill="#FF3333")
    y = 20
    d.text((4,y), f"IP: {ip}", font=font_sm, fill="#FFBBBB"); y+=12
    d.text((4,y), f"Videos: {video_count}", font=font_sm, fill="#FFBBBB"); y+=12
    status = "RUNNING" if server_running else "STOPPED"
    d.text((4,y), f"Status: {status}", font=font_sm, fill="#00FF00" if server_running else "#FF6666"); y+=12
    # QR code
    if server_running:
        qr_img = generate_qr(f"http://{ip}")
        # Resize to fit on LCD (max 80x80)
        qr_img = qr_img.resize((80,80))
        img.paste(qr_img, (24, y))
    d.rectangle((0,H-12,W,H), fill="#220000")
    d.text((4,H-10), "KEY3=Exit  KEY2=Rescan", font=font_sm, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def wait_btn():
    for _ in range(50):
        for n, p in PINS.items():
            if GPIO.input(p) == 0:
                time.sleep(0.05)
                return n
        time.sleep(0.01)
    return None

# ----------------------------------------------------------------------
# Main – start Flask server in a thread, LCD shows info
# ----------------------------------------------------------------------
def main():
    # Check dependencies
    if os.system("which ffmpeg >/dev/null 2>&1") != 0:
        draw_lcd("0.0.0.0", 0, False)
        # Show error on LCD
        img = Image.new("RGB", (W,H), "black")
        d = ImageDraw.Draw(img)
        d.text((4,50), "ffmpeg missing", font=font_sm, fill="red")
        d.text((4,65), "sudo apt install ffmpeg", font=font_sm, fill="white")
        LCD.LCD_ShowImage(img,0,0)
        time.sleep(5)
        GPIO.cleanup()
        return

    # Generate thumbnails initially
    generate_thumbnails()

    # Get video count
    videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    video_count = len(videos)

    # Start Flask server in a background thread
    server_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False), daemon=True)
    server_thread.start()
    time.sleep(2)  # let server start

    ip = get_local_ip()
    server_running = True

    # Main LCD loop
    while True:
        draw_lcd(ip, video_count, server_running)
        btn = wait_btn()
        if btn == "KEY3":
            break
        elif btn == "KEY2":
            # Rescan videos and regenerate missing thumbnails
            generate_thumbnails()
            videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
            video_count = len(videos)
            draw_lcd(ip, video_count, server_running)
            time.sleep(1)

    # Cleanup
    os._exit(0)  # force kill Flask threads
    GPIO.cleanup()
    LCD.LCD_Clear()

if __name__ == "__main__":
    main()
