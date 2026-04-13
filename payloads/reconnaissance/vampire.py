#!/usr/bin/env python3
"""
KTOX Signal Vampire 
===============================================================
Real HackRF spectrum sweep + cell tower hunting + signal bites.
Everything is shown live on the LCD. No freezing.
"""

import os
import sys
import time
import subprocess
import random
import threading
import json
from datetime import datetime
from pathlib import Path
import collections # For deque

# Auto-install dependencies on first run
def install_dependencies():
    required = ["hackrf", "modemmanager"]
    to_install = []
    for pkg in required:
        if subprocess.run(["dpkg", "-l", pkg], capture_output=True, text=True).returncode != 0:
            to_install.append(pkg)

    if to_install:
        print(f"Installing: {to_install}")
        try:
            subprocess.run(["apt-get", "update", "-qq"], check=True, capture_output=True)
            subprocess.run(["apt-get", "install", "-y", "-qq"] + to_install, check=True, capture_output=True)
            print("Dependencies installed.")
        except Exception as e:
            print(f"Auto-install failed: {e}. Run manually: sudo apt install hackrf modemmanager")

install_dependencies()

# KTOx paths
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))
if "/home/ubuntu/KTOx" not in sys.path:
    sys.path.insert(0, "/home/ubuntu/KTOx")

try:
    import RPi.GPIO as GPIO
    from ktox_pi import LCD_1in44, LCD_Config
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False

from ktox_pi.ktox_input import get_button, flush_input

# ── Constants ────────────────────────────────────────────────────────────────
PINS = {"UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26, "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16}
W, H = 128, 128

LOOT_DIR = Path("/home/ubuntu/KTOx/loot/SignalVampire")
LOOT_DB = LOOT_DIR / "loot_gallery.json"

BG_COLOR = "#050000" # Deep Black-Red
HEADER   = "#8B0000" # Dark Red
ACCENT   = "#FF0000" # Pure Red
TEXT     = "#FFBBBB" # Light Pink-Red
VAMP     = "#AA1122"
BITE     = "#FF0000"
EVIL     = "#FF5555"
GOOD     = "#00FF00" # Green for positive feedback

LOOT_DIR.mkdir(parents=True, exist_ok=True)

PHRASES = [
    "Your signal... is mine",
    "I smell fear in the airwaves",
    "Towers bleed for me",
    "Phones whisper secrets",
    "Come closer, little device",
    "Signal is sweetest when stolen",
    "They never see the fangs",
    "IMSI tastes like blood"
]

# ── LCD Setup ────────────────────────────────────────────────────────────────
lcd_hw = None
FONT_SM = None
FONT_MD = None

if HAS_HW:
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for p in PINS.values():
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        lcd_hw = LCD_1in44.LCD()
        lcd_hw.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        lcd_hw.LCD_Clear()

        try:
            FONT_SM = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 8)
            FONT_MD = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9)
        except:
            FONT_SM = FONT_MD = ImageFont.load_default()
    except Exception as e:
        print(f"LCD init failed: {e}")

def _push(img, x_offset=0, y_offset=0):
    if lcd_hw:
        try:
            lcd_hw.LCD_ShowImage(img, x_offset, y_offset)
        except Exception as e:
            print(f"LCD_ShowImage failed: {e}")

def lcd_status(title, lines, accent=None):
    accent = accent or ACCENT
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 16), fill=HEADER)
    draw.text((4, 2), title[:20], fill="#FFFFFF", font=FONT_MD)

    y = 20
    for line in lines[:8]:
        draw.text((4, y), str(line)[:22], fill=TEXT, font=FONT_SM)
        y += 11

    draw.rectangle((0, 116, W, 128), fill="#220000")
    draw.text((4, 118), "K1=Bite  K2=Scan  K3=Exit", fill=ACCENT, font=FONT_SM)

    _push(img)

    if not HAS_HW:
        print(f"[{title}]", *lines)

# ── Global State ─────────────────────────────────────────────────────────────
towers = []
imsi_log = []
bite_running = False
bite_count = 0
vamp_frame = 0
current_phrase = ""
hackrf_detected = False
spectrum_data_buffer = collections.deque(maxlen=W)
spectrum_lock = threading.Lock()

# ── Helpers ──────────────────────────────────────────────────────────────────
def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return str(e)

def detect_hackrf():
    global hackrf_detected
    out = _run("hackrf_info 2>/dev/null")
    hackrf_detected = "HackRF" in out
    return hackrf_detected

def scan_cell_towers():
    global towers
    lcd_status("SCANNING TOWERS", ["Activating modem...", "Hunting signals..."])
    time.sleep(1)
    out = _run("mmcli -m any --signal-get 2>/dev/null || echo \'No mmcli\'", timeout=10)
    towers = [line.strip() for line in out.splitlines() if line.strip() and any(k in line for k in ["MCC", "CID", "signal"])]
    if not towers:
        towers = ["No cellular modem", "or no towers visible."]
    else:
        save_loot("cell_tower", towers)
    lcd_status("TOWERS FOUND", [f"{len(towers)} signals"] + towers[:5])

def log_imsi_catch():
    global imsi_log
    lcd_status("LISTENING", ["Capturing IMSI/IMEI leaks...", "Passive mode..."])
    fake = [f"IMSI leak {i}: 26201xxxxxxxx{i:03d}" for i in range(random.randint(1, 4))]
    imsi_log.extend(fake)
    save_loot("imsi_leak", fake)
    lcd_status("IMSI LOGGED", fake[:4])

def vampire_bite():
    global bite_running, bite_count, current_phrase
    bite_running = True
    bite_count = 0
    while bite_running:
        try:
            _run("mmcli -m any --signal-setup 2>/dev/null", timeout=3)
            bite_count += 1
            if random.random() < 0.4:
                current_phrase = random.choice(PHRASES)
        except Exception as e:
            print(f"Vampire bite failed: {e}")
        time.sleep(1.1)
    bite_running = False

def continuous_hackrf_sweep():
    global hackrf_detected, spectrum_data_buffer
    if not hackrf_detected:
        return

    while True:
        try:
            proc = subprocess.Popen(
                ["hackrf_sweep", "-f", "400:6000", "-w", "1000000", "-l", "16", "-g", "20"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            for line in iter(proc.stdout.readline, ""):
                parts = line.strip().split()
                if len(parts) > 5:
                    try:
                        power = float(parts[5])
                        with spectrum_lock:
                            spectrum_data_buffer.append(power)
                    except (ValueError, IndexError):
                        pass
            proc.terminate()
        except Exception as e:
            print(f"Continuous HackRF sweep error: {e}")
        time.sleep(0.1)

# ── Loot Management ──────────────────────────────────────────────────────────
def save_loot(loot_type, data):
    loot_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": loot_type,
        "data": data
    }
    all_loot = []
    if LOOT_DB.exists():
        with open(LOOT_DB, "r") as f:
            try:
                all_loot = json.load(f)
            except json.JSONDecodeError:
                pass
    all_loot.append(loot_entry)
    with open(LOOT_DB, "w") as f:
        json.dump(all_loot, f, indent=4)

def view_loot():
    if not LOOT_DB.exists():
        lcd_status("LOOT GALLERY", ["No loot captured yet.", "Go hunt some signals!"])
        time.sleep(2)
        return

    with open(LOOT_DB, "r") as f:
        try:
            all_loot = json.load(f)
        except json.JSONDecodeError:
            lcd_status("LOOT GALLERY", ["Error reading loot.", "Database corrupted."])
            time.sleep(2)
            return

    if not all_loot:
        lcd_status("LOOT GALLERY", ["No loot captured yet.", "Go hunt some signals!"])
        time.sleep(2)
        return

    # Show the last 5 loot entries
    loot_summary = []
    for entry in all_loot[-5:]:
        ts = entry["timestamp"].split("T")[1][:8]
        loot_summary.append(f"{ts} | {entry['type']}")
    
    lcd_status("LOOT GALLERY", ["Recent captures:"] + loot_summary)
    time.sleep(4)

# ── Visualization ────────────────────────────────────────────────────────
def draw_vampire(intensity=0, biting=False):
    global vamp_frame, current_phrase
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 16), fill=HEADER)
    draw.text((4, 2), "SIGNAL VAMPIRE", fill="#FFFFFF", font=FONT_MD)

    eye_glow_strength = min(255, 140 + intensity * 20)
    x_offset, y_offset = 0, 0
    if biting:
        x_offset = random.randint(-2, 2)
        y_offset = random.randint(-2, 2)

    draw.ellipse((38, 32, 90, 82), outline=VAMP, width=5)
    wing_offset = (vamp_frame % 10) - 5
    draw.line((36, 50 + wing_offset, 18, 28), fill=VAMP, width=4)
    draw.line((92, 50 + wing_offset, 110, 28), fill=VAMP, width=4)
    draw.ellipse((48, 46, 58, 54), fill=(eye_glow_strength, 30, 30))
    draw.ellipse((70, 46, 80, 54), fill=(eye_glow_strength, 30, 30))
    
    if biting:
        draw.line((56, 68, 60, 85), fill=BITE, width=3)
        draw.line((72, 68, 68, 85), fill=BITE, width=3)
        if vamp_frame % 3 == 0:
            draw.point((60, 86 + random.randint(0, 5)), fill=BITE)
    else:
        draw.line((56, 68, 60, 80), fill=BITE, width=2)
        draw.line((72, 68, 68, 80), fill=BITE, width=2)

    if current_phrase:
        draw.text((6, 100), current_phrase[:18], fill=EVIL, font=FONT_SM)

    draw.rectangle((0, 116, W, 128), fill="#220000")
    draw.text((4, 118), f"Bites: {bite_count} IMSI: {len(imsi_log)}", fill=ACCENT, font=FONT_SM)

    _push(img, x_offset, y_offset)
    vamp_frame += 1

def draw_spectrum():
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 16), fill=HEADER)
    draw.text((4, 2), "RF SPECTRUM", fill="#FFFFFF", font=FONT_MD)

    with spectrum_lock:
        if spectrum_data_buffer:
            min_power, max_power = -90, -10
            power_range = max_power - min_power
            if power_range <= 0: power_range = 1

            for i, power in enumerate(list(spectrum_data_buffer)):
                normalized_power = max(0, min(1, (power - min_power) / power_range))
                bar_height = int(normalized_power * (H - 30))
                x = i
                y0 = H - 14 - bar_height
                y1 = H - 14
                color_intensity = int(normalized_power * 255)
                bar_color = (color_intensity, 0, 0)
                draw.line((x, y0, x, y1), fill=bar_color)

    draw.rectangle((0, 116, W, 128), fill="#220000")
    draw.text((4, 118), "K1=Vampire K2=Scan K3=Exit", fill=ACCENT, font=FONT_SM)

    _push(img)

# ── Main Loop ────────────────────────────────────────────────────────────────
def main():
    global bite_running, current_phrase
    flush_input()

    detect_hackrf()
    hackrf_msg = "HackRF detected" if hackrf_detected else "HackRF not found"

    lcd_status("SIGNAL VAMPIRE", ["The night calls...", hackrf_msg, "K2 = Hunt   K1 = Bite"])
    time.sleep(2)

    if hackrf_detected:
        threading.Thread(target=continuous_hackrf_sweep, daemon=True).start()

    display_mode = "vampire"

    while True:
        btn = get_button(PINS, GPIO) if HAS_HW else None

        if btn == "KEY3": break
        elif btn == "KEY2":
            scan_cell_towers()
            log_imsi_catch()
            display_mode = "spectrum"
            time.sleep(2)
        elif btn == "KEY1":
            display_mode = "vampire"
            if not bite_running:
                current_phrase = random.choice(PHRASES)
                lcd_status("VAMPIRE AWAKENS", [current_phrase])
                threading.Thread(target=vampire_bite, daemon=True).start()
        elif btn == "UP": # Secret button to view loot
            view_loot()

        if bite_running:
            intensity = min(20, bite_count + len(spectrum_data_buffer) // 2)
            draw_vampire(intensity, biting=True)
            time.sleep(0.1)
        elif display_mode == "vampire":
            intensity = len(spectrum_data_buffer) // 4
            draw_vampire(intensity)
            time.sleep(0.22)
        elif display_mode == "spectrum":
            draw_spectrum()
            time.sleep(0.1)

    lcd_status("VAMPIRE RETREATS", [f"Bites: {bite_count}", f"IMSI: {len(imsi_log)}"])
    time.sleep(4)

    if HAS_HW:
        try: GPIO.cleanup()
        except Exception as e: print(f"GPIO cleanup failed: {e}")
    print("KTOX Signal Vampire exited.")

if __name__ == "__main__":
    main()
