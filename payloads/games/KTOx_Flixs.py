cat > /root/KTOx/payloads/ktoxflix_server.py << 'EOF'
#!/usr/bin/env python3
"""
KTOx Payload – KTOxFliX Video Server
=====================================
- Serves videos from /root/Videos on port 80
- LCD shows IP, video count, CPU temp, status, QR code on KEY1
- Use any browser on your phone/laptop to watch videos
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

PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}
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

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

app = Flask(__name__)

# ----------------------------------------------------------------------
# Generate thumbnails using ffmpeg
# ----------------------------------------------------------------------
def generate_thumbnails():
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
# HTML templates (KTOxFliX style)
# ----------------------------------------------------------------------
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOxFliX</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #141414; color: white; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 20px; }
        h1 { color: #E50914; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
        .card { background: #222; border-radius: 4px; overflow: hidden; transition: transform 0.3s; cursor: pointer; text-decoration: none; color: white; }
        .card:hover { transform: scale(1.05); }
        .card img { width: 100%; height: 120px; object-fit: cover; }
        .card-title { padding: 10px; font-size: 14px; text-align: center; }
        footer { margin-top: 40px; text-align: center; color: #666; }
        .port-info { background: #333; padding: 8px; border-radius: 4px; text-align: center; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>KTOxFliX</h1>
    <div class="port-info">🌐 Server running on port 80 – http://<span id="ip"></span>:80</div>
    <div class="grid">
        {% for video in videos %}
        <a href="/play/{{ video }}" class="card">
            <img src="/thumb/{{ video }}.jpg" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'200\' height=\'120\' viewBox=\'0 0 200 120\'%3E%3Crect width=\'200\' height=\'120\' fill=\'%23333\'/%3E%3Ctext x=\'50%25\' y=\'50%25\' text-anchor=\'middle\' dy=\'.3em\' fill=\'%23999\'%3ENo thumbnail%3C/text%3E%3C/svg%3E'">
            <div class="card-title">{{ video }}</div>
        </a>
        {% endfor %}
    </div>
    <footer>KTOxFliX – Powered by KTOx on Raspberry Pi</footer>
    <script>
        fetch('/ip').then(r=>r.text()).then(ip=>document.getElementById('ip').innerText=ip);
    </script>
</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOxFliX – {{ video }}</title>
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
    <a href="/" class="back">← Back to KTOxFliX</a>
</body>
</html>
"""

@app.route('/')
def index():
    videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    return render_template_string(INDEX_HTML, videos=videos)

@app.route('/ip')
def get_ip():
    return get_local_ip()

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

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read().strip()) / 1000.0
            return temp
    except:
        return 0.0

def generate_qr(data):
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="white", back_color="black").get_image()

def draw_lcd(ip, video_count, server_running):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0,0,W,17), fill="#8B0000")
    d.text((4,3), "KTOxFLIX", font=font_bold, fill="#FF3333")
    y = 20
    d.text((4,y), f"IP: {ip}:80", font=font_sm, fill="#FFBBBB"); y+=12
    d.text((4,y), f"Videos: {video_count}", font=font_sm, fill="#FFBBBB"); y+=12
    temp = get_cpu_temp()
    if temp < 60:
        temp_color = "#00FF00"
    elif temp < 75:
        temp_color = "#FFFF00"
    else:
        temp_color = "#FF0000"
    d.text((4,y), f"Temp: {temp:.1f}C", font=font_sm, fill=temp_color); y+=12
    status = "RUNNING" if server_running else "STOPPED"
    d.text((4,y), f"Status: {status}", font=font_sm, fill="#00FF00" if server_running else "#FF6666"); y+=12
    d.text((4,y), "KEY1 = QR code", font=font_sm, fill="#FF7777")
    d.rectangle((0,H-12,W,H), fill="#220000")
    d.text((4,H-10), "KEY2=Rescan  KEY3=Exit", font=font_sm, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def draw_qr_fullscreen(ip):
    img = Image.new("RGB", (W, H), "white")
    url = f"http://{ip}:80"
    qr_img = generate_qr(url)
    qr_img = qr_img.resize((W, H))
    img.paste(qr_img, (0, 0))
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
# Main
# ----------------------------------------------------------------------
def main():
    if os.system("which ffmpeg >/dev/null 2>&1") != 0:
        img = Image.new("RGB", (W,H), "black")
        d = ImageDraw.Draw(img)
        d.text((4,50), "ffmpeg missing", font=font_sm, fill="red")
        d.text((4,65), "sudo apt install ffmpeg", font=font_sm, fill="white")
        LCD.LCD_ShowImage(img,0,0)
        time.sleep(5)
        GPIO.cleanup()
        return

    generate_thumbnails()
    videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    video_count = len(videos)

    # Start Flask server on port 80
    server_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False), daemon=True)
    server_thread.start()
    time.sleep(2)

    ip = get_local_ip()
    server_running = True
    qr_showing = False

    while True:
        if qr_showing:
            draw_qr_fullscreen(ip)
            btn = wait_btn()
            if btn is not None:
                qr_showing = False
            time.sleep(0.1)
        else:
            draw_lcd(ip, video_count, server_running)
            btn = wait_btn()
            if btn == "KEY3":
                break
            elif btn == "KEY1":
                qr_showing = True
            elif btn == "KEY2":
                generate_thumbnails()
                videos = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
                video_count = len(videos)
                draw_lcd(ip, video_count, server_running)
                time.sleep(1)

    os._exit(0)
    GPIO.cleanup()
    LCD.LCD_Clear()

if __name__ == "__main__":
    main()
EOF
