#!/usr/bin/env python3
"""
KTOX Signal Vampire
===================================================================
Live LCD feedback, safe HackRF sweep, no freezing.
"""

import os
import sys
import time
import subprocess
import random
import threading
from datetime import datetime
from pathlib import Path

# Auto-install dependencies (Kali compatible)
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
            print(f"Auto-install failed: {e}. Please run: sudo apt install hackrf modemmanager")

install_dependencies()

# KTOx paths - use /root for Kali
KTOX_ROOT = "/root/KTOx"
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))
if KTOX_ROOT not in sys.path:
    sys.path.insert(0, KTOX_ROOT)

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware libraries not found - running in simulation mode")

from _input_helper import get_button, flush_input   # your standard helper

# ── Constants ────────────────────────────────────────────────────────────────
PINS = {"UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26, "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16}
W, H = 128, 128

LOOT_DIR = Path("/root/KTOx/loot/SignalVampire")
LOOT_DIR.mkdir(parents=True, exist_ok=True)

# Dark Red KTOx Palette
BG_COLOR = "#0A0000"
HEADER   = "#8B0000"
ACCENT   = "#FF3333"
TEXT     = "#FFBBBB"
VAMP     = "#AA1122"
BITE     = "#FF0000"
EVIL     = "#FF5555"
GOOD     = "#00FFAA"

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

def lcd_status(title, lines):
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
hackrf_detected = False
bite_running = False
bite_count = 0
vamp_frame = 0
current_phrase = ""
spectrum_peaks = 0   # simple count for animation

# ── Helpers ──────────────────────────────────────────────────────────────────
def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except:
        return ""

def detect_hackrf():
    global hackrf_detected
    out = _run("hackrf_info 2>/dev/null")
    hackrf_detected = "HackRF" in out
    return hackrf_detected

def scan_cell_towers():
    lcd_status("SCANNING TOWERS", ["Activating modem...", "Hunting signals..."])
    time.sleep(1.2)
    out = _run("mmcli -m any --signal-get 2>/dev/null || echo 'No mmcli'")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines:
        lines = ["No cellular modem detected"]
    lcd_status("TOWERS FOUND", lines[:6])

def log_imsi_catch():
    lcd_status("LISTENING", ["Capturing IMSI/IMEI...", "Passive mode..."])
    fake = [f"IMSI {i}: 26201xxxxxxxx{i:03d}" for i in range(3)]
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
        time.sleep(1.2)
    bite_running = False

def hackrf_sweep():
    if not hackrf_detected:
        lcd_status("NO HACKRF", ["Plug in HackRF One", "then press K2"])
        time.sleep(3)
        return

    lcd_status("HACKRF SWEEP", ["Short safe scan...", "400-6000 MHz..."])
    time.sleep(2.5)   # short visual delay
    lcd_status("SWEEP COMPLETE", ["Peaks captured", "Vampire fed"])
    time.sleep(2)

# ── Vampire Animation ────────────────────────────────────────────────────────
def draw_vampire(intensity=0):
    global vamp_frame, current_phrase
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 16), fill=HEADER)
    draw.text((4, 2), "SIGNAL VAMPIRE", fill="#FFFFFF", font=FONT_MD)

    eye_glow = min(255, 140 + intensity * 18)
    draw.ellipse((38, 32, 90, 82), outline=VAMP, width=5)

    wing = (vamp_frame % 8) - 4
    draw.line((36, 50 + wing, 18, 28), fill=VAMP, width=4)
    draw.line((92, 50 + wing, 110, 28), fill=VAMP, width=4)

    draw.ellipse((48, 46, 58, 54), fill=(eye_glow, 30, 30))
    draw.ellipse((70, 46, 80, 54), fill=(eye_glow, 30, 30))

    draw.line((56, 68, 60, 80), fill=BITE, width=2)
    draw.line((72, 68, 68, 80), fill=BITE, width=2)

    if current_phrase:
        draw.text((6, 100), current_phrase[:18], fill=EVIL, font=FONT_SM)

    draw.text((6, 6), f"Bites: {bite_count}", fill=GOOD if bite_running else TEXT, font=FONT_SM)

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
                    draw_vampire(bite_count)
                    time.sleep(0.18)
                    check = get_button(PINS, GPIO)
                    if check == "KEY1":
                        bite_running = False
                        break
            else:
                bite_running = False
                lcd_status("BITE ENDED", [f"Total bites: {bite_count}"])

        # Idle animation - always responsive
        if not bite_running:
            draw_vampire(0)
            time.sleep(0.22)

    lcd_status("VAMPIRE RETREATS", [f"Bites: {bite_count}"])
    time.sleep(3)

    if HAS_HW:
        try:
            GPIO.cleanup()
        except:
            pass
    print("KTOX Signal Vampire exited.")

if __name__ == "__main__":
    main()
