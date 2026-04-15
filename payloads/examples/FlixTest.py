#!/usr/bin/env python3
import os, sys, time, threading, subprocess, socket, re, urllib.parse
import requests
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

# --- CONFIGURATION ---
VIDEO_DIR = "/root/Videos"
THUMB_DIR = "/root/Videos/thumbnails"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}

os.makedirs(THUMB_DIR, exist_ok=True)
app = Flask(__name__)

# --- CYBERPUNK WEB UI (RED/BLACK/CYAN) ---
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

        /* Scanline Overlay */
        body::before {
            content: " "; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.2) 50%);
            background-size: 100% 4px; z-index: 1000; pointer-events: none;
        }

        nav { 
            padding: 20px 5%; background: rgba(0,0,0,0.9); border-bottom: 2px solid var(--red);
            display: flex; justify-content: space-between; align-items: center; box-shadow: 0 0 20px var(--dark-red);
        }
        .logo { color: var(--red); font-size: 22px; letter-spacing: 4px; text-shadow: 2px 0 var(--cyan); }

        .container { padding: 40px 5%; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 20px; }

        .card { 
            background: #000; border: 1px solid var(--dark-red); text-decoration: none; 
            color: inherit; transition: 0.3s; position: relative; overflow: hidden;
        }
        .card:hover { transform: scale(1.05); border-color: var(--red); box-shadow: 0 0 15px var(--red); z-index: 5; }

        .card img { 
            width: 100%; aspect-ratio: 2/3; object-fit: cover; 
            filter: grayscale(100%) sepia(100%) hue-rotate(-50deg) brightness(0.7); 
            transition: 0.4s;
        }
        .card:hover img { filter: grayscale(0%) brightness(1); }

        .card-meta { padding: 10px; font-size: 11px; background: rgba(20,0,0,0.9); }
        .data-id { color: var(--cyan); display: block; margin-bottom: 4px; }
        
        video { width: 90%; max-width: 900px; border: 2px solid var(--red); box-shadow: 0 0 30px var(--dark-red); margin-top: 50px; }
    </style>
</head>
<body>
    <nav><div class="logo">KTOx//CYBER_VOID</div><div style="color:var(--cyan); font-size:10px;">UPLINK_STABLE</div></nav>
    <div class="container">
        <h3 style="color:var(--red); text-transform:uppercase;">> DECODING_LOCAL_DATASTREAMS...</h3>
        <div class="grid">
            {% for v in videos %}
            <a href="/play/{{ v }}" class="card">
                <img src="/thumb/{{ v }}.jpg">
                <div class="card-meta">
                    <span class="data-id">STREAM//{{ v.rsplit('.', 1)[0] | upper }}</span>
                    <span style="color:#666;">STATUS: READY</span>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>playing//{{ video }}</title>
    <style>
        body { background: #000; color: #ff0000; font-family: monospace; text-align: center; }
        video { width: 80%; border: 2px solid #ff0000; margin-top: 50px; }
        .back { color: #00f3ff; text-decoration: none; display: block; margin-top: 20px; }
    </style>
</head>
<body>
    <h2>DECRYPTING: {{ video }}</h2>
    <video controls autoplay><source src="/stream/{{ video }}" type="video/mp4"></video>
    <a href="/" class="back"><< RETURN_TO_VOID</a>
</body>
</html>
"""

# --- UTILS ---
def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        return s.getsockname()[0]
    except: return "127.0.0.1"

def scrape_poster(name):
    query = f"{name} movie poster"
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find_all("img")[1] # Skip logo
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
            # FFmpeg fallback
            subprocess.run(["ffmpeg", "-ss", "00:00:10", "-i", os.path.join(VIDEO_DIR, f), 
                            "-vf", "scale=300:-1", "-vframes", "1", t_path], stderr=subprocess.DEVNULL)

# --- FLASK ROUTES ---
@app.route('/')
def index():
    vids = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTS)]
    return render_template_string(INDEX_HTML, videos=vids)

@app.route('/play/<f>')
def play(f): return render_template_string(PLAYER_HTML, video=f)

@app.route('/stream/<f>')
def stream(f): return send_from_directory(VIDEO_DIR, f)

@app.route('/thumb/<f>')
def thumb(f): return send_from_directory(THUMB_DIR, f)

# --- LCD LOGIC ---
def lcd_loop():
    if not HAS_HW: return
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    ip = get_ip()
    
    while True:
        img = Image.new("RGB", (128,128), "black")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,128,18), fill="#3d0000")
        draw.text((5,3), "CYBER_VOID", fill="red")
        draw.text((5,30), f"IP: {ip}", fill="#00f3ff")
        draw.text((5,50), f"SCANNING...", fill="red")
        
        # KEY1 shows QR
        if GPIO.input(PINS["KEY1"]) == 0:
            qr = qrcode.make(f"http://{ip}").resize((128,128)).convert("RGB")
            lcd.LCD_ShowImage(qr, 0,0)
            time.sleep(3)
        else:
            lcd.LCD_ShowImage(img, 0,0)
        time.sleep(1)

# --- MAIN ---
if __name__ == "__main__":
    # 1. Background Poster Scraper
    threading.Thread(target=generate_thumbnails, daemon=True).start()
    
    # 2. LCD Status Monitor
    if HAS_HW:
        GPIO.setmode(GPIO.BCM)
        for p in PINS.values(): GPIO.setup(p, GPIO.IN, GPIO.PUD_UP)
        threading.Thread(target=lcd_loop, daemon=True).start()

    # 3. Web Server
    print(f"CYBER_VOID Uplink established at http://{get_ip()}")
    app.run(host='0.0.0.0', port=80, debug=False, use_reloader=False)
