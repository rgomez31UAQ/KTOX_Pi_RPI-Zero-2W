#!/usr/bin/env python3
"""
KTOx Payload – WPA/WPA2 Handshake Cracker (FIXED + UI UPGRADE)
"""

import sys
import os
import time
import signal
import subprocess
import threading

KTOX_ROOT = '/root/KTOx' if os.path.isdir('/root/KTOx') else os.path.abspath(os.path.join(__file__, '..', '..'))
if KTOX_ROOT not in sys.path:
    sys.path.insert(0, KTOX_ROOT)

import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

HANDSHAKE_FILE = ""
WORDLIST_FILE = ""
running = True

PINS = { "OK": 13, "KEY3": 16, "KEY1": 21, "KEY2": 20, "UP": 6, "DOWN": 19 }

GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
FONT = ImageFont.load_default()

# -------------------- CLEANUP --------------------
def cleanup(*_):
    global running
    running = False
    subprocess.run("killall hashcat", shell=True)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# -------------------- UI --------------------
def draw(lines):
    img = Image.new("RGB", (128, 128), "black")
    d = ImageDraw.Draw(img)

    # Title bar
    d.text((4, 2), "WPA CRACKER", font=FONT_TITLE, fill="#00FFAA")
    d.line((0, 16, 128, 16), fill="#00FFAA")

    y = 20
    for line in lines:
        d.text((4, y), line[:20], font=FONT, fill="white")
        y += 12

    LCD.LCD_ShowImage(img, 0, 0)

# -------------------- FILE SCANNER --------------------
def get_files(file_type):
    files = []

    if file_type == "Handshake":
        dirs = [os.path.join(KTOX_ROOT, "loot")]

        exts = (".pcap", ".cap", ".22000")

    else:
        dirs = [
            os.path.join(KTOX_ROOT, "wordlists"),
            "/usr/share/wordlists",
            "/usr/share/seclists"
        ]
        exts = (".txt", ".lst", ".wordlist")

    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, filenames in os.walk(d):
            for f in filenames:
                if f.endswith(exts):
                    files.append(os.path.join(root, f))

    return sorted(list(set(files)))

# -------------------- FILE SELECTOR --------------------
def select_file(file_type):
    files = get_files(file_type)

    if not files:
        draw([f"No {file_type}", "files found"])
        time.sleep(2)
        return None

    idx = 0
    offset = 0
    visible = 6

    while running:
        view = files[offset:offset+visible]

        lines = [f"{file_type}:"]
        for i, f in enumerate(view):
            name = os.path.basename(f)[:18]
            prefix = ">" if (offset + i) == idx else " "
            lines.append(f"{prefix} {name}")

        lines.append("OK=Select")
        draw(lines)

        btn = get_button()

        if btn == "KEY3":
            return None
        elif btn == "OK":
            return files[idx]
        elif btn == "UP":
            idx = (idx - 1) % len(files)
        elif btn == "DOWN":
            idx = (idx + 1) % len(files)

        if idx < offset:
            offset = idx
        elif idx >= offset + visible:
            offset = idx - visible + 1

        time.sleep(0.15)

# -------------------- BUTTON HANDLER --------------------
def get_button():
    for name, pin in PINS.items():
        if GPIO.input(pin) == 0:
            while GPIO.input(pin) == 0:
                time.sleep(0.05)
            return name
    return None

# -------------------- ATTACK --------------------
def run_attack():
    draw(["Starting...", "Hashcat"])

    cmd = [
        "hashcat",
        "-m", "22000",
        HANDSHAKE_FILE,
        WORDLIST_FILE,
        "--force"
    ]

    try:
        proc = subprocess.Popen(cmd)

        while proc.poll() is None:
            draw([
                "Cracking...",
                os.path.basename(HANDSHAKE_FILE)[:18],
                os.path.basename(WORDLIST_FILE)[:18],
                "KEY3=Stop"
            ])

            if get_button() == "KEY3":
                proc.terminate()
                draw(["Stopped"])
                time.sleep(2)
                return

            time.sleep(1)

        draw(["Done!", "Check potfile"])
        time.sleep(3)

    except Exception as e:
        draw(["Error:", str(e)[:18]])
        time.sleep(3)

# -------------------- MAIN LOOP --------------------
if __name__ == "__main__":
    try:
        while running:
            draw([
                f"H: {os.path.basename(HANDSHAKE_FILE)[:16]}",
                f"W: {os.path.basename(WORDLIST_FILE)[:16]}",
                "",
                "OK = Start",
                "K1 = Handshake",
                "K2 = Wordlist",
                "K3 = Exit"
            ])

            btn = get_button()

            if btn == "OK":
                if HANDSHAKE_FILE and WORDLIST_FILE:
                    run_attack()
                else:
                    draw(["Select files first"])
                    time.sleep(2)

            elif btn == "KEY1":
                f = select_file("Handshake")
                if f:
                    HANDSHAKE_FILE = f

            elif btn == "KEY2":
                f = select_file("Wordlist")
                if f:
                    WORDLIST_FILE = f

            elif btn == "KEY3":
                break

            time.sleep(0.1)

    finally:
        cleanup()
        LCD.LCD_Clear()
        GPIO.cleanup()
        print("Done.")
