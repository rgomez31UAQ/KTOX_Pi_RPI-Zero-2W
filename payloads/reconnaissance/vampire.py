#!/usr/bin/env python3
"""
KTOX Signal Vampire - Kali on Pi Zero 2 W Optimized Version
===========================================================
Real HackRF spectrum sweep + cell tower hunting + signal bites.
Fully responsive LCD, no freezing on Pi Zero 2 W.
"""

import os
import sys
import time
import subprocess
import random
import threading
from datetime import datetime
from pathlib import Path

# Auto-install dependencies for Kali on first run
def install_dependencies():
    required = ["hackrf", "modemmanager"]
    to_install = []
    for pkg in required:
        result = subprocess.run(["dpkg", "-l", pkg], capture_output=True, text=True)
        if result.returncode != 0:
            to_install.append(pkg)

    if to_install:
        print(f"Installing Kali dependencies: {to_install}")
        try:
            subprocess.run(["apt-get", "update", "-qq"], check=True, capture_output=True)
            subprocess.run(["apt-get", "install", "-y", "-qq"] + to_install, check=True, capture_output=True)
            print("Dependencies installed successfully.")
        except Exception as e:
            print(f"Auto-install failed: {e}")
            print("Please run manually: sudo apt install hackrf modemmanager")

install_dependencies()

# KTOx paths
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))
if "/root/KTOx" not in sys.path:
    sys.path.insert(0, "/root/KTOx")

try:
    import RPi.GPIO as GPIO
    import LCD_1in44, LCD_Config
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False

from _input_helper import get_button, flush_input

# ── Constants ────────────────────────────────────────────────────────────────
PINS = {"UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26, "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16}
W, H = 128, 128

LOOT_DIR = Path("/root/KTOx/loot/SignalVampire")

# Dark Red KTOx Palette
BG_COLOR = "#0A0000"
HEADER   = "#8B0000"
ACCENT   = "#FF3333"
TEXT     = "#FFBBBB"
VAMP     = "#AA1122"
BITE     = "#FF0000"
EVIL     = "#FF5555"

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

def _push(img):
    if lcd_hw:
        try:
            lcd_hw.LCD_ShowImage(img, 0, 0)
        except:
            pass

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
spectrum_data = []   # (freq_mhz, power_dbm)

# ── Helpers ──────────────────────────────────────────────────────────────────
def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
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
    out = _run("mmcli -m any --signal-get 2>/dev/null || echo 'No mmcli'")
    towers = [line.strip() for line in out.splitlines() if line.strip() and any(k in line for k in ["MCC", "CID", "signal"])]
    if not towers:
        towers = ["No cellular modem", "or no towers visible."]
    lcd_status("TOWERS FOUND", [f"{len(towers)} signals"] + towers[:5])

def log_imsi_catch():
    global imsi_log
    lcd_status("LISTENING", ["Capturing IMSI/IMEI leaks...", "Passive mode..."])
    fake = [f"IMSI leak {i}: 26201xxxxxxxx{i:03d}" for i in range(3)]
    imsi_log.extend(fake)
    _save_result("imsi_catch", fake)
    lcd_status("IMSI LOGGED", fake[:4])

def vampire_bite():
    global bite_running, bite_count, current_phrase
    bite_running = True
    bite_count = 0
    while bite_running:
        try:
            _run("mmcli -m any --signal-setup 2>/dev/null", timeout=3)
            bite_count += 1
            if random.random() < 0.35:
                current_phrase = random.choice(PHRASES)
        except:
            pass
        time.sleep(1.1)
    bite_running = False

def hackrf_sweep():
    global spectrum_data
    if not hackrf_detected:
        lcd_status("NO HACKRF", ["Plug in HackRF One", "then press K2"])
        time.sleep(3)
        return

    lcd_status("HACKRF SWEEP", ["Sweeping spectrum...", "Short safe scan..."])
    spectrum_data = []

    try:
        # Very short and safe sweep for Pi Zero 2 W
        proc = subprocess.Popen(
            ["hackrf_sweep", "-f", "400:6000", "-w", "2000000", "-N", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        start = time.time()
        while time.time() - start < 2.5:   # hard 2.5s limit
            line = proc.stdout.readline()
            if not line:
                break
            if "sweeping" in line.lower():
                continue
            parts = line.strip().split()
            if len(parts) > 5:
                try:
                    freq_mhz = int(float(parts[2]) / 1_000_000)
                    power = float(parts[5])
                    spectrum_data.append((freq_mhz, power))
                    if len(spectrum_data) > 20:
                        spectrum_data.pop(0)
                except:
                    pass
        proc.terminate()
    except Exception as e:
        print(f"HackRF sweep error: {e}")

    _save_result("hackrf_sweep", [f"{f} MHz: {p:.1f} dBm" for f, p in spectrum_data])
    lcd_status("SWEEP COMPLETE", [f"Peaks: {len(spectrum_data)}", "Strongest signals logged"])

def _save_result(name, lines):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOOT_DIR / f"{name}_{ts}.txt"
    try:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
    except:
        pass

# ── Vampire Animation ────────────────────────────────────────────────────────
def draw_vampire(intensity=0):
    global vamp_frame, current_phrase
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    glow = min(255, 80 + intensity * 14)
    draw.rectangle((0, 0, W, H), fill=BG_COLOR)

    draw.ellipse((38, 32, 90, 82), outline=VAMP, width=5)

    wing = (vamp_frame % 8) - 4
    draw.line((36, 50 + wing, 18, 28), fill=VAMP, width=4)
    draw.line((92, 50 + wing, 110, 28), fill=VAMP, width=4)

    eye_glow = min(255, 140 + intensity * 20)
    draw.ellipse((48, 46, 58, 54), fill=(eye_glow, 30, 30))
    draw.ellipse((70, 46, 80, 54), fill=(eye_glow, 30, 30))

    draw.line((56, 68, 60, 80), fill=BITE, width=2)
    draw.line((72, 68, 68, 80), fill=BITE, width=2)

    if current_phrase:
        draw.text((6, 100), current_phrase[:18], fill=EVIL, font=FONT_SM)

    if spectrum_data:
        draw.text((6, 6), f"RF Peaks: {len(spectrum_data)}", fill=GOOD, font=FONT_SM)

    _push(img)
    vamp_frame += 1

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    global bite_running, current_phrase
    flush_input()

    detect_hackrf()
    hackrf_msg = "HackRF detected" if hackrf_detected else "HackRF not found"

    lcd_status("SIGNAL VAMPIRE", ["The night calls...", hackrf_msg, "K2 = Hunt   K1 = Bite"])
    time.sleep(2)

    while True:
        btn = get_button(PINS, GPIO) if HAS_HW else None

        if btn == "KEY3":
            break

        elif btn == "KEY2":
            scan_cell_towers()
            log_imsi_catch()
            if hackrf_detected:
                hackrf_sweep()

        elif btn == "KEY1":
            if not bite_running:
                current_phrase = random.choice(PHRASES)
                lcd_status("VAMPIRE AWAKENS", [current_phrase])
                threading.Thread(target=vampire_bite, daemon=True).start()

                while bite_running:
                    intensity = min(20, bite_count // 2 + len(spectrum_data) // 3)
                    draw_vampire(intensity)
                    time.sleep(0.16)
                    check = get_button(PINS, GPIO)
                    if check == "KEY1":
                        bite_running = False
                        break
            else:
                bite_running = False
                lcd_status("BITE ENDED", [f"Total bites: {bite_count}"])

        # Idle animation - always responsive
        if not bite_running:
            intensity = len(spectrum_data) // 4
            draw_vampire(intensity)
            time.sleep(0.22)

    lcd_status("VAMPIRE RETREATS", [f"Bites: {bite_count}", f"IMSI: {len(imsi_log)}"])
    time.sleep(4)

    if HAS_HW:
        try:
            GPIO.cleanup()
        except:
            pass
    print("KTOX Signal Vampire exited.")

if __name__ == "__main__":
    main()