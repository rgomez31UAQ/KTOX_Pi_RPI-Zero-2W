#!/usr/bin/env python3
"""
KTOX SDR Ghost - Live HackRF Waterfall
======================================
Follows exact Captive Portal Escape architecture.
"""

import os
import sys
import time
import subprocess
import random
from datetime import datetime
from pathlib import Path

# Auto-install dependencies (Kali)
def install_dependencies():
    required = ["hackrf", "modemmanager"]
    to_install = [pkg for pkg in required if subprocess.run(["dpkg", "-l", pkg], capture_output=True, text=True).returncode != 0]
    if to_install:
        print(f"Installing: {to_install}")
        try:
            subprocess.run(["apt-get", "update", "-qq"], check=True, capture_output=True)
            subprocess.run(["apt-get", "install", "-y", "-qq"] + to_install, check=True, capture_output=True)
            print("Dependencies installed.")
        except Exception as e:
            print(f"Auto-install failed: {e}")

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

LOOT_DIR = Path("/root/KTOx/loot/SDRGhost")
LOOT_DIR.mkdir(parents=True, exist_ok=True)

# Dark Red KTOx Palette
BG_COLOR = "#0A0000"
HEADER   = "#8B0000"
ACCENT   = "#FF3333"
TEXT     = "#FFBBBB"
WATER    = "#00FFAA"
WEAK     = "#FF5555"

# ── LCD helpers (exact same as your Captive Portal Escape) ───────────────────
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

def lcd_status(title, lines, tc=None, lc=None):
    tc = tc or HEADER
    lc = lc or TEXT
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 14), fill=tc)
    draw.text((3, 2), title[:20], fill="#FFFFFF", font=FONT_MD)

    y = 18
    for ln in (lines or []):
        draw.text((3, y), str(ln)[:21], fill=lc, font=FONT_SM)
        y += 11
        if y > H - 12:
            break
    _push(img)

    if not HAS_HW:
        print(f"[{title}]", *lines)

# ── Global State ─────────────────────────────────────────────────────────────
hackrf_detected = False
spectrum_buffer = []   # power values for waterfall

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

def hackrf_sweep():
    global spectrum_buffer
    if not hackrf_detected:
        lcd_status("NO HACKRF", ["Plug in HackRF One", "then press K2"])
        time.sleep(3)
        return

    lcd_status("SDR GHOST", ["Starting HackRF sweep...", "400-6000 MHz..."])
    spectrum_buffer = []

    try:
        proc = subprocess.Popen(
            ["hackrf_sweep", "-f", "400:6000", "-w", "1000000", "-N", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        start = time.time()
        while time.time() - start < 2.5:
            line = proc.stdout.readline()
            if not line:
                break
            parts = line.strip().split()
            if len(parts) > 5:
                try:
                    power = float(parts[5])
                    spectrum_buffer.append(power)
                    if len(spectrum_buffer) > W:
                        spectrum_buffer.pop(0)
                except:
                    pass
        proc.terminate()
    except Exception as e:
        print(f"HackRF error: {e}")

    lcd_status("SWEEP COMPLETE", [f"Peaks captured: {len(spectrum_buffer)}"])

def draw_waterfall():
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, W, 14), fill=HEADER)
    draw.text((3, 2), "SDR WATERFALL", fill="#FFFFFF", font=FONT_MD)

    if spectrum_buffer:
        min_p = min(spectrum_buffer) if spectrum_buffer else -100
        max_p = max(spectrum_buffer) if spectrum_buffer else -30
        range_p = max(1, max_p - min_p)

        for x in range(min(W, len(spectrum_buffer))):
            power = spectrum_buffer[x]
            normalized = max(0, min(1, (power - min_p) / range_p))
            height = int(normalized * (H - 30))
            color_val = int(normalized * 255)
            color = (color_val, int(color_val * 0.6), 0)
            draw.line((x, H - 14 - height, x, H - 14), fill=color)

    draw.rectangle((0, 116, W, 128), fill="#220000")
    draw.text((3, 118), "K2=Scan  K1=Waterfall  K3=Exit", fill=ACCENT, font=FONT_SM)

    _push(img)

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    flush_input()

    detect_hackrf()
    hackrf_msg = "HackRF detected" if hackrf_detected else "HackRF not found"

    lcd_status("SDR GHOST", ["KTOx Spectrum Viewer", hackrf_msg, "K2 = Scan   K1 = Waterfall"])
    time.sleep(2)

    waterfall_active = False

    while True:
        btn = get_button(PINS, GPIO)

        if btn == "KEY3":
            break

        elif btn == "KEY2":
            hackrf_sweep()

        elif btn == "KEY1":
            waterfall_active = not waterfall_active
            if waterfall_active:
                lcd_status("WATERFALL LIVE", ["Real-time spectrum...", "K1 to stop"])
            else:
                lcd_status("WATERFALL PAUSED", ["K1 to resume"])

        if waterfall_active:
            draw_waterfall()
        else:
            lcd_status("SDR GHOST", ["Ready", hackrf_msg, "K2=Scan  K1=Waterfall"])

        time.sleep(0.12)

    lcd_status("SDR GHOST", ["Shutting down...", "Goodbye"])
    time.sleep(2)

    if HAS_HW:
        try:
            GPIO.cleanup()
        except:
            pass
    print("KTOX SDR Ghost exited.")

if __name__ == "__main__":
    main()
