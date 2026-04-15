#!/usr/bin/env python3
import os, sys, time, threading, subprocess, socket, re, urllib.parse
import requests
import qrcode
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, send_from_directory

# Hardware imports
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("CRITICAL_ERROR: LCD hardware not detected.")

# --- CONFIGURATION ---
VIDEO_DIR = "/root/Videos"
THUMB_DIR = "/root/Videos/thumbnails"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}

os.makedirs(THUMB_DIR, exist_ok=True)
app = Flask(__name__)

# --- CYBER-VOID TERMINAL UI ---
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx//CYBER_VOID</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        :root { --red: #ff0000; --dark-red: #2b0000; --cyan: #00f3ff; --bg: #050505; }
        body { 
            background: var(--bg); color: #ccc; font-family: 'Share Tech Mono', monospace; 
            margin: 0; overflow-x: hidden;
            background-image: linear-gradient(rgba(255,0,0,0.05) 1px, transparent 1px), 
                              linear-gradient(90deg, rgba(255,0,0,0.05) 1px, transparent 1px);
            background-size: 30px 30px;
        }
        body::before {
            content: " "; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%);
            background-size: 100% 4px; z-index: 1000; pointer-events: none;
        }
        nav { 
            padding: 15px 5%; background: #000; border-bottom: 2px solid var(--red);
            display: flex; justify-content: space-between; align-items: center; 
            box-shadow: 0 0 20px var(--dark-red);
        }
        .logo { color: var(--red); font-size: 22px; letter-spacing: 4px; text-shadow: 2px 0 var(--cyan); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px; padding: 30px 5%; }
        .card { 
            background: #000; border: 1px solid var(--dark-red); text-decoration: none; 
            color: inherit; transition: 0.3s; position: relative;
        }
        .card:hover { transform: translateY(-5px); border-color: var(--red); box-shadow: 0 0 15px var(--red); z-index: 5; }
        .card img { 
            width: 100%; aspect-ratio: 2/3; object-fit: cover; 
            filter: grayscale(100%) sepia(100%) hue-rotate(-50deg) brightness(0.6); 
            transition: 0.4s;
        }
        .card:hover img { filter: grayscale(0%) brightness(1); }
        .card-meta { padding: 8px; font-size: 10px; background: #080000; }
        .data-id { color: var(--cyan); display: block; overflow: hidden; text-overflow: ellipsis; }
    </style>
</head>
<body>
    <nav><div class="logo">KTOx//CYBER_VOID</div><div style="color:var(--cyan); font-size:10px;">DATA_STREAM: ACTIVE</div></nav>
    <div class="grid">
        {% for v in videos %}
        <a href="/play/{{ v }}" class="card">
            <img src="/thumb/{{ v }}.jpg">
            <div class="card-meta">
                <span class="data-id">VOID//{{ v.rsplit('.', 1)[0] | upper }}</span>
                <span style="color:#555;">ENCRYPTED_STREAM</span>
            </div>
        </a>
        {% endfor %}
    </div>
</body>
</html>
"""

# --- HELPERS ---
def get_stats():
    # Get CPU Temp
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read().strip()) / 1000.0
    except: temp = 0.0
    # Get Net Stats (eth0 or wlan0)
    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "wlan0" in line or "eth0" in line:
                    parts = line.split()
                    rx = round(int(parts[1]) / 1048576, 1) # MB
                    tx = round(int(parts[9]) / 1048576, 1) # MB
                    return temp, rx, tx
    except: pass
    return temp, 0, 0

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        return s.getsockname()[0]
    except: return "127.0.0.1"

def scrape_poster(name):
    query = f"{name} official movie poster"
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find_all("img")[1]
        return img.get('src')
    except: return None

def generate_thumbnails():
    for f in os.listdir(VIDEO_DIR):
        if f.lower().endswith(VIDEO_EXTS):
            t_path = os.path.join(THUMB_DIR, f + ".jpg")
            if os.path.exists(t_path): continue
            clean = re.sub(r'1080p|720p|x264|h264|bluray', '', f.rsplit('.',1)[0], flags=re.I).replace('_',' ')
            p_url = scrape_poster(clean)
            if p_url:
                try:
                    data = requests.get(p_url).content
                    with open(t_path, 'wb') as h: h.write(data)
                    continue
                except: pass
            subprocess.run(["ffmpeg", "-ss", "00:00:05", "-i", os.path.join(VIDEO_DIR, f), 
                            "-vf", "scale=300:-1", "-vframes", "1", t_path], stderr=subprocess.DEVNULL)

# --- LCD MONITOR THREAD ---
def lcd_monitor():
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    ip = get_ip()
    show_qr = False
    
    while True:
        if GPIO.input(PINS["KEY1"]) == 0:
            show_qr = not show_qr
            time.sleep(0.3) # Debounce
            
        if show_qr:
            qr = qrcode.QRCode(box_size=3, border=2)
            qr.add_data(f"http://{ip}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((128,128))
            lcd.LCD_ShowImage(img, 0, 0)
        else:
            temp, rx, tx = get_stats()
            img = Image.new("RGB", (128,128), "black")
            d = ImageDraw.Draw(img)
            # Header
            d.rectangle((0,0,128,16), fill="#2b0000")
            d.text((4,2), "KTOx//CYBER_VOID", fill="red")
            # Stats
            d.text((4,25), f"IP: {ip}", fill="#00f3ff")
            d.text((4,45), f"CPU: {temp:.1f}C", fill="red" if temp > 65 else "green")
            d.text((4,65), f"RX: {rx}MB", fill="#ccc")
            d.text((4,78), f"TX: {tx}MB", fill="#ccc")
            d.text((4,100), "[KEY1] SCAN QR", fill="#555")
            lcd.LCD_ShowImage(img, 0, 0)
        time.sleep(0.5)

# --- ROUTES ---
@app.route('/')
def index():
    vids = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    return render_template_string(INDEX_HTML, videos=vids)

@app.route('/stream/<f>')
def stream(f): return send_from_directory(VIDEO_DIR, f)

@app.route('/thumb/<f>')
def thumb(f): return send_from_directory(THUMB_DIR, f)

@app.route('/play/<f>')
def play(f):
    tmpl = "<html><body style='background:#000;color:red;text-align:center;'><video controls autoplay style='width:90%;border:1px solid red;'><source src='/stream/{{f}}'></video><br><a href='/' style='color:#00f3ff;'><< BACK</a></body></html>"
    return render_template_string(tmpl, f=f)

if __name__ == "__main__":
    if HAS_HW:
        GPIO.setmode(GPIO.BCM)
        for p in PINS.values(): GPIO.setup(p, GPIO.IN, GPIO.PUD_UP)
        threading.Thread(target=lcd_monitor, daemon=True).start()
    
    threading.Thread(target=generate_thumbnails, daemon=True).start()
    app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False)
