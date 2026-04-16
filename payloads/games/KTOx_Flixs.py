#!/usr/bin/env python3
"""
KTOx Payload – KTOxFliX
==============================================
- Movie & TV show library with metadata from IMDb (no API key)
- Groups TV shows by folder (series)
- Web UI on port 80, upload on port 8888
- LCD shows IP, QR for uplink
"""

import os, sys, time, socket, threading, json, requests, hashlib
from flask import Flask, render_template_string, send_from_directory, request, redirect, url_for
from werkzeug.utils import secure_filename

# Hardware
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
VIDEO_DIR = "/root/Videos"
CACHE_FILE = "/root/Videos/metadata_cache.json"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
PINS = {"UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,"KEY1":21,"KEY2":20,"KEY3":16}

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs("/root/KTOx/static", exist_ok=True)

# Flask apps
app_lib = Flask("Library")
app_up = Flask("Uplink")

# ----------------------------------------------------------------------
# Cinemagoer (no API key) – fetch metadata
# ----------------------------------------------------------------------
try:
    from imdb import Cinemagoer
    HAS_IMDB = True
except ImportError:
    HAS_IMDB = False
    print("⚠️  Cinemagoer not installed. Run: pip install cinemagoer")

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

def get_metadata(title, media_type='movie'):
    """Fetch metadata using Cinemagoer, caches results."""
    if not HAS_IMDB:
        return None
    cache = load_cache()
    key = f"{media_type}:{title.lower().strip()}"
    if key in cache:
        return cache[key]
    ia = Cinemagoer()
    try:
        if media_type == 'movie':
            results = ia.search_movie(title)
            for res in results:
                if res.get('kind') != 'tv series':
                    movie = ia.get_movie(res.movieID)
                    info = {
                        'title': movie.get('title'),
                        'year': movie.get('year'),
                        'plot': movie.get('plot')[0] if movie.get('plot') else 'No description',
                        'poster': movie.get('cover url'),
                        'rating': movie.get('rating'),
                        'type': 'movie'
                    }
                    cache[key] = info
                    save_cache(cache)
                    return info
        else:  # tv series
            results = ia.search_movie(title)
            for res in results:
                if res.get('kind') == 'tv series':
                    series = ia.get_movie(res.movieID)
                    info = {
                        'title': series.get('title'),
                        'year': series.get('year'),
                        'plot': series.get('plot')[0] if series.get('plot') else 'No description',
                        'poster': series.get('cover url'),
                        'rating': series.get('rating'),
                        'seasons': series.get('number of seasons'),
                        'type': 'series'
                    }
                    cache[key] = info
                    save_cache(cache)
                    return info
    except Exception as e:
        print(f"Metadata fetch error for {title}: {e}")
    return None

def get_poster_path(title, media_type):
    """Download poster locally if URL exists."""
    info = get_metadata(title, media_type)
    if not info or not info.get('poster'):
        return None
    poster_url = info['poster']
    # Create safe filename
    safe = hashlib.md5(f"{media_type}:{title}".encode()).hexdigest()
    local_path = f"/root/KTOx/static/posters/{safe}.jpg"
    os.makedirs("/root/KTOx/static/posters", exist_ok=True)
    if not os.path.exists(local_path):
        try:
            r = requests.get(poster_url, timeout=10)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
        except:
            pass
    return local_path if os.path.exists(local_path) else None

# ----------------------------------------------------------------------
# Scan library – group TV shows by folder
# ----------------------------------------------------------------------
def scan_library():
    items = []
    for entry in sorted(os.listdir(VIDEO_DIR)):
        full = os.path.join(VIDEO_DIR, entry)
        if os.path.isdir(full):
            # TV series folder
            episodes = []
            for f in os.listdir(full):
                if f.lower().endswith(VIDEO_EXTS):
                    episodes.append(f)
            if episodes:
                info = get_metadata(entry, 'series')
                poster_path = get_poster_path(entry, 'series') if info else None
                items.append({
                    'type': 'series',
                    'name': info['title'] if info else entry,
                    'plot': info['plot'] if info else 'No description.',
                    'poster': f"/static/posters/{hashlib.md5(f'series:{entry}'.encode()).hexdigest()}.jpg" if poster_path else None,
                    'path': entry,
                    'episodes': episodes
                })
        elif entry.lower().endswith(VIDEO_EXTS):
            # Movie
            name = os.path.splitext(entry)[0].replace('_', ' ').replace('.', ' ')
            info = get_metadata(name, 'movie')
            poster_path = get_poster_path(name, 'movie') if info else None
            items.append({
                'type': 'movie',
                'name': info['title'] if info else name,
                'plot': info['plot'] if info else 'No description.',
                'poster': f"/static/posters/{hashlib.md5(f'movie:{name}'.encode()).hexdigest()}.jpg" if poster_path else None,
                'year': info['year'] if info else '',
                'path': entry
            })
    return items

# ----------------------------------------------------------------------
# Web UI templates (cyberpunk)
# ----------------------------------------------------------------------
LIBRARY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOxFliX</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #0a0a0a; color: #ccc; font-family: monospace; margin:0; }
        nav { background: #000; padding: 15px; border-bottom: 2px solid #f00; display: flex; justify-content: space-between; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; padding: 20px; }
        .card { background: #111; border: 1px solid #300; text-decoration: none; color: inherit; transition: 0.2s; }
        .card:hover { transform: scale(1.02); border-color: #0ff; }
        .card img { width: 100%; aspect-ratio: 2/3; object-fit: cover; background: #222; }
        .card div { padding: 8px; font-size: 12px; text-align: center; }
        footer { text-align: center; padding: 20px; color: #555; }
        .placeholder { background: #1a1a2a; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <nav><div style="color:#f00">KTOxFLIX</div><div>PORT 80</div></nav>
    <div class="grid">
        {% for item in items %}
        <a href="/detail/{{ item.type }}/{{ item.path }}" class="card">
            {% if item.poster %}
            <img src="{{ item.poster }}">
            {% else %}
            <div class="placeholder" style="aspect-ratio:2/3; display:flex; align-items:center; justify-content:center;">🎬</div>
            {% endif %}
            <div>{{ item.name[:30] }}</div>
        </a>
        {% endfor %}
    </div>
    <footer>KTOx – Metadata from IMDb</footer>
</body>
</html>
"""

SERIES_DETAIL = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ series.name }} - KTOxFliX</title>
    <style>
        body { background: #0a0a0a; color: #ccc; font-family: monospace; margin:0; }
        .container { max-width: 800px; margin: 30px auto; background: #111; padding: 20px; border: 1px solid #300; }
        .poster { float: left; width: 150px; margin-right: 20px; border: 1px solid #0ff; }
        h2 { color: #f00; }
        .episode-list { clear: both; margin-top: 30px; }
        .episode { background: #1a1a1a; margin: 5px 0; padding: 8px; border-left: 3px solid #0ff; }
        .episode a { color: #0ff; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        {% if series.poster %}<img class="poster" src="{{ series.poster }}">{% endif %}
        <h2>{{ series.name }}</h2>
        <p>{{ series.plot }}</p>
        <div class="episode-list">
            <h3>Episodes</h3>
            {% for ep in episodes %}
            <div class="episode"><a href="/stream/{{ series.path }}/{{ ep }}">▶ {{ ep }}</a></div>
            {% endfor %}
        </div>
        <p><a href="/" style="color:#f00">← Back to Library</a></p>
    </div>
</body>
</html>
"""

MOVIE_DETAIL = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ movie.name }} - KTOxFliX</title>
    <style>
        body { background: #0a0a0a; color: #ccc; font-family: monospace; margin:0; }
        .container { max-width: 800px; margin: 30px auto; background: #111; padding: 20px; border: 1px solid #300; }
        .poster { float: left; width: 150px; margin-right: 20px; border: 1px solid #0ff; }
        h2 { color: #f00; }
        video { width: 100%; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="container">
        {% if movie.poster %}<img class="poster" src="{{ movie.poster }}">{% endif %}
        <h2>{{ movie.name }} ({{ movie.year }})</h2>
        <p>{{ movie.plot }}</p>
        <video controls>
            <source src="/stream/{{ movie.path }}" type="video/mp4">
        </video>
        <p><a href="/" style="color:#f00">← Back to Library</a></p>
    </div>
</body>
</html>
"""

@app_lib.route('/')
def library():
    items = scan_library()
    return render_template_string(LIBRARY_HTML, items=items)

@app_lib.route('/detail/series/<path:series_path>')
def series_detail(series_path):
    full_path = os.path.join(VIDEO_DIR, series_path)
    episodes = []
    if os.path.isdir(full_path):
        episodes = sorted([f for f in os.listdir(full_path) if f.lower().endswith(VIDEO_EXTS)])
    info = get_metadata(series_path, 'series')
    poster_path = get_poster_path(series_path, 'series') if info else None
    series = {
        'name': info['title'] if info else series_path,
        'plot': info['plot'] if info else 'No description.',
        'poster': f"/static/posters/{hashlib.md5(f'series:{series_path}'.encode()).hexdigest()}.jpg" if poster_path else None
    }
    return render_template_string(SERIES_DETAIL, series=series, episodes=episodes)

@app_lib.route('/detail/movie/<path:movie_path>')
def movie_detail(movie_path):
    name = os.path.splitext(movie_path)[0].replace('_', ' ').replace('.', ' ')
    info = get_metadata(name, 'movie')
    poster_path = get_poster_path(name, 'movie') if info else None
    movie = {
        'name': info['title'] if info else name,
        'plot': info['plot'] if info else 'No description.',
        'poster': f"/static/posters/{hashlib.md5(f'movie:{name}'.encode()).hexdigest()}.jpg" if poster_path else None,
        'year': info['year'] if info else '',
        'path': movie_path
    }
    return render_template_string(MOVIE_DETAIL, movie=movie)

@app_lib.route('/stream/<path:video_path>')
def stream(video_path):
    return send_from_directory(VIDEO_DIR, video_path)

@app_lib.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory("/root/KTOx/static", filename)

# ----------------------------------------------------------------------
# Uplink (file/folder upload)
# ----------------------------------------------------------------------
UPLINK_HTML = """
<!DOCTYPE html>
<html>
<head><title>KTOx Uplink</title><style>body{background:#000;color:#0f0;font-family:monospace;padding:20px}</style></head>
<body>
    <h1>KTOx DATA UPLINK</h1>
    <form method="POST" action="/upload" enctype="multipart/form-data">
        <label>Subdirectory (optional):</label><br>
        <input type="text" name="subdir" style="width:100%"><br><br>
        <label>Files:</label><br>
        <input type="file" name="files" multiple><br><br>
        <label>Folder:</label><br>
        <input type="file" name="files" multiple webkitdirectory><br><br>
        <button type="submit">UPLOAD</button>
    </form>
</body>
</html>
"""

@app_up.route('/')
def uplink():
    return UPLINK_HTML

@app_up.route('/upload', methods=['POST'])
def upload():
    sub = request.form.get('subdir', '').strip()
    target = os.path.join(VIDEO_DIR, sub)
    os.makedirs(target, exist_ok=True)
    for f in request.files.getlist('files'):
        if f.filename:
            path = os.path.join(target, secure_filename(f.filename))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            f.save(path)
    return redirect(url_for('uplink'))

# ----------------------------------------------------------------------
# LCD & main
# ----------------------------------------------------------------------
def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def main():
    if not HAS_HW:
        threading.Thread(target=lambda: app_lib.run(host='0.0.0.0', port=80), daemon=True).start()
        app_up.run(host='0.0.0.0', port=8888)
        return

    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    lcd.LCD_Clear()
    ip = get_ip()
    show_qr = False
    held = {}
    threading.Thread(target=lambda: app_lib.run(host='0.0.0.0', port=80), daemon=True).start()
    threading.Thread(target=lambda: app_up.run(host='0.0.0.0', port=8888), daemon=True).start()
    try:
        while True:
            now = time.time()
            img = Image.new("RGB", (128,128), "black")
            draw = ImageDraw.Draw(img)
            if show_qr:
                import qrcode
                qr = qrcode.QRCode(box_size=3, border=2)
                qr.add_data(f"http://{ip}:8888")
                qr_img = qr.make_image().convert("RGB").resize((128,128))
                img.paste(qr_img, (0,0))
            else:
                draw.rectangle([(0,0),(128,18)], fill=(120,0,0))
                try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",9)
                except: font = ImageFont.load_default()
                draw.text((4,3), "KTOxFLIX", fill="black", font=font)
                draw.text((4,30), f"IP: {ip}", fill="white", font=font)
                draw.text((4,50), "PORT 80: LIB", fill="cyan", font=font)
                draw.text((4,65), "PORT 8888: UP", fill="red", font=font)
                draw.text((4,113), "K1:QR  K3:EXIT", fill=(150,150,150), font=font)
            lcd.LCD_ShowImage(img,0,0)
            pressed = {n: GPIO.input(p)==0 for n,p in PINS.items()}
            for n, down in pressed.items():
                if down:
                    if n not in held: held[n] = now
                else: held.pop(n, None)
            if pressed.get("KEY3") and (now - held.get("KEY3", now)) <= 0.05:
                break
            if pressed.get("KEY1") and (now - held.get("KEY1", now)) <= 0.05:
                show_qr = not show_qr
                time.sleep(0.3)
            time.sleep(0.1)
    finally:
        lcd.LCD_Clear()
        GPIO.cleanup()

if __name__ == "__main__":
    # Check dependencies
    if not HAS_IMDB:
        print("\n⚠️  Cinemagoer not installed. Installing...")
        os.system("pip install cinemagoer")
        # Re-attempt import
        try:
            from imdb import Cinemagoer
            HAS_IMDB = True
            print("✓ Cinemagoer installed successfully.\n")
        except:
            print("✗ Failed to install Cinemagoer. Please run: pip install cinemagoer\n")
    # Create placeholder image
    placeholder = Image.new('RGB', (200,300), color=(30,30,50))
    placeholder.save("/root/KTOx/static/placeholder.jpg")
    print("Starting KTOxFliX (Cinemagoer Edition)...")
    main()
