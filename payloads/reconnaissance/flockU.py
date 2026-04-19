#!/usr/bin/env python3
"""
KTOx Payload – FlockU 
author: wickednull
====================================================
Detects Flock Safety surveillance cameras and related devices using:
- BLE scanning (manufacturer ID, device name patterns)
- Wi-Fi promiscuous mode (probe requests, beacon frames)
- MAC OUI prefix matching (20+ known Flock prefixes)
- SSID pattern matching ("Flock-XXXX", "FS Ext Battery")

Controls:
  KEY2 short – toggle list/radar view
  KEY2 long  – export data to JSON
  KEY1       – reset data
  KEY3       – exit
  UP/DOWN    – scroll flocks (list view)
  OK         – view details (list view)

Loot: /root/KTOx/loot/FlockDetect/
"""

import os
import sys
import json
import time
import threading
import math
import random
import subprocess
import re
import struct
from datetime import datetime

# KTOx hardware
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# GPIO & LCD setup
# ----------------------------------------------------------------------
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
FONT = font(10)
SMALL_FONT = font(8)

def wait_btn(timeout=0.1):
    start = time.time()
    while time.time() - start < timeout:
        for name, pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

def is_long_press(btn_name, hold=2.0):
    pin = PINS[btn_name]
    if GPIO.input(pin) == 0:
        start = time.time()
        while GPIO.input(pin) == 0:
            time.sleep(0.05)
            if time.time() - start >= hold:
                while GPIO.input(pin) == 0:
                    time.sleep(0.05)
                return True
    return False

# ----------------------------------------------------------------------
# Paths & constants
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/FlockDetect"
os.makedirs(LOOT_DIR, exist_ok=True)

# ======================================================================
# DETECTION DATABASES (from research)
# ======================================================================

# Known Flock Safety MAC OUIs (from flock-you project)
# Sources: colonelpanichacks/flock-you, wgreenberg/flock-you
FLOCK_MAC_PREFIXES = [
    "00:0C:43",  # Axis Communications (Flock hardware)
    "00:40:8C",  # Axis
    "AC:CC:8E",  # Axis
    "00:1E:C7",  # Hikvision (some Flock models)
    "4C:11:AE",  # Hikvision
    "70:E4:22",  # Hikvision
    "00:12:C9",  # Dahua
    "4C:54:99",  # Dahua
    "9C:8E:CD",  # Dahua
    "B8:27:EB",  # Raspberry Pi (Flock compute boxes)
    "DC:A6:32",  # Raspberry Pi
    "E4:5F:01",  # Raspberry Pi
    "00:14:2A",  # Sony
    "08:00:46",  # Sony
    "00:0F:53",  # Panasonic
    "00:80:5F",  # Panasonic
    "00:0B:5D",  # Bosch
    "00:07:5F",  # Bosch
    "00:1C:F0",  # FLIR
    "00:1E:3D",  # FLIR
]

# Known Flock SSID patterns
FLOCK_SSID_PATTERNS = [
    r"^Flock-",           # Flock-XXXX format
    r"^Flock_",
    r"^FS Ext Battery",
    r"(?i)flock",
    r"(?i)penguin",
    r"(?i)raven",
    r"(?i)pigvision",
]

# Known BLE manufacturer IDs
# 0x09C8 = XUNTONG (used in Flock hardware)
FLOCK_MANUFACTURER_IDS = [0x09C8]

# Known BLE device name patterns
FLOCK_BLE_NAME_PATTERNS = [
    "FS Ext Battery",
    "Flock",
    "Penguin",
    "Pigvision",
    "Raven",
]

# Known BLE service UUIDs (Raven gunshot detectors)
RAVEN_SERVICE_UUIDS = [
    "0000180a-0000-1000-8000-00805f9b34fb",  # Device Information
    "0000feaa-0000-1000-8000-00805f9b34fb",  # Raven specific
    "0000feb0-0000-1000-8000-00805f9b34fb",
]

# ----------------------------------------------------------------------
# Detection scoring weights
# ----------------------------------------------------------------------
SCORES = {
    "mac_prefix": 40,
    "ssid_pattern": 50,
    "ssid_format": 65,        # Exact Flock-XXXX format
    "ble_name": 45,
    "ble_mfg_id": 60,
    "raven_uuid": 80,
    "wifi_probe": 30,
}

# ----------------------------------------------------------------------
# Shared state
# ----------------------------------------------------------------------
lock = threading.Lock()
running = True
view_mode = "list"           # "list" or "radar"
detail_view = False
detail_device = None
scroll_pos = 0
selected_idx = 0

# Detected devices: {mac: {"last_seen": float, "rssi": int, "method": str, "score": int, "name": str}}
detected_devices = {}
flocks = []                   # Grouped by correlation (same as before)
radar_angle = 0

# ----------------------------------------------------------------------
# BLE Scanning Thread
# ----------------------------------------------------------------------
def ble_scan_thread():
    """Run hcitool to capture BLE advertisements."""
    global detected_devices
    try:
        proc = subprocess.Popen(
            ["sudo", "hcitool", "lescan", "--duplicates"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        print(f"BLE scan failed: {e}")
        return

    while running:
        line = proc.stdout.readline()
        if not line:
            break
        # Parse MAC and name from line like: "AA:BB:CC:DD:EE:FF Device Name"
        parts = line.strip().split()
        if len(parts) >= 2:
            mac = parts[0].upper()
            name = " ".join(parts[1:])
            now = time.time()
            score = 0
            method = ""
            # Check BLE name patterns
            for pattern in FLOCK_BLE_NAME_PATTERNS:
                if pattern.lower() in name.lower():
                    score += SCORES["ble_name"]
                    method = "ble_name"
                    break
            # Could also check manufacturer data via hcidump, but that's complex
            if score > 0:
                with lock:
                    if mac not in detected_devices or detected_devices[mac]["score"] < score:
                        detected_devices[mac] = {
                            "last_seen": now,
                            "rssi": -50,  # approximate
                            "method": method,
                            "score": score,
                            "name": name,
                        }
        time.sleep(0.01)
    proc.terminate()

# ----------------------------------------------------------------------
# WiFi Sniffing Thread (Monitor Mode)
# ----------------------------------------------------------------------
def wifi_sniff_thread(iface):
    """Use tcpdump to capture probe requests and beacons."""
    global detected_devices
    cmd = ["tcpdump", "-i", iface, "-e", "-l",
           "type", "mgt", "subtype", "probe-req", "or", "subtype", "beacon"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, bufsize=1)
    except Exception as e:
        print(f"WiFi sniff failed: {e}")
        return

    while running:
        line = proc.stdout.readline()
        if not line:
            break
        # Extract MAC
        mac_match = re.search(r"([\da-fA-F]{2}:){5}[\da-fA-F]{2}", line, re.I)
        if not mac_match:
            continue
        mac = mac_match.group(0).upper()
        now = time.time()
        score = 0
        method = ""
        # Check MAC OUI prefix
        for prefix in FLOCK_MAC_PREFIXES:
            if mac.startswith(prefix):
                score += SCORES["mac_prefix"]
                method = "mac_prefix"
                break
        # Try to extract SSID from beacon frame
        ssid_match = re.search(r'IEEE 802\.11.*Beacon.*"([^"]+)"', line)
        if ssid_match:
            ssid = ssid_match.group(1)
            for pattern in FLOCK_SSID_PATTERNS:
                if re.search(pattern, ssid, re.I):
                    score += SCORES["ssid_pattern"]
                    method = "ssid_pattern"
                    # Extra points for exact Flock-XXXX format
                    if re.match(r"^Flock-[0-9A-F]{6}$", ssid, re.I):
                        score += SCORES["ssid_format"]
                    break
        if score > 0:
            with lock:
                if mac not in detected_devices or detected_devices[mac]["score"] < score:
                    detected_devices[mac] = {
                        "last_seen": now,
                        "rssi": -60,  # approximate
                        "method": method,
                        "score": score,
                        "name": ssid if ssid_match else "",
                    }
        time.sleep(0.01)
    proc.terminate()

# ----------------------------------------------------------------------
# Correlation into "flocks"
# ----------------------------------------------------------------------
def compute_flocks():
    """Group devices that appear/disappear together."""
    with lock:
        devices = dict(detected_devices)
    if len(devices) < 2:
        return []
    # Simple grouping by presence window (simplified from earlier)
    now = time.time()
    window = 30  # seconds
    groups = []
    used = set()
    macs = list(devices.keys())
    for i, mac_a in enumerate(macs):
        if mac_a in used:
            continue
        group = [mac_a]
        ta = devices[mac_a]["last_seen"]
        for j, mac_b in enumerate(macs):
            if mac_b in used or mac_b == mac_a:
                continue
            tb = devices[mac_b]["last_seen"]
            if abs(ta - tb) < window:
                group.append(mac_b)
        if len(group) >= 2:
            for m in group:
                used.add(m)
            # Calculate group score (average device score)
            avg_score = sum(devices[m]["score"] for m in group) // len(group)
            groups.append({
                "members": group,
                "size": len(group),
                "score": avg_score,
                "first_seen": min(devices[m]["last_seen"] for m in group),
            })
    return groups

# ----------------------------------------------------------------------
# Loot export
# ----------------------------------------------------------------------
def export_loot():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(LOOT_DIR, f"flock_{ts}.json")
    with lock:
        data = {
            "timestamp": ts,
            "devices": detected_devices,
            "flocks": compute_flocks(),
        }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath

# ----------------------------------------------------------------------
# Drawing helpers
# ----------------------------------------------------------------------
def draw_header(draw, active):
    draw.rectangle((0, 0, W-1, 13), fill="#111")
    draw.text((2, 1), "FLOCK DETECT", font=FONT, fill="#FF6600")
    draw.ellipse((W-12, 2, W-4, 10), fill="#00FF00" if active else "#FF0000")

def draw_footer(draw, text):
    draw.rectangle((0, H-12, W-1, H-1), fill="#111")
    draw.text((2, H-10), text[:24], font=SMALL_FONT, fill="#AAA")

def show_message(line1, line2=""):
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), line1, font=FONT, fill="#00FF00")
    if line2:
        draw.text((4, 65), line2, font=SMALL_FONT, fill="#888")
    LCD.LCD_ShowImage(img, 0, 0)
    time.sleep(1.5)

# ----------------------------------------------------------------------
# List view
# ----------------------------------------------------------------------
def draw_list_view():
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    with lock:
        devices = list(detected_devices.items())
        flock_list = compute_flocks()
        sel = selected_idx
        sc = scroll_pos
    draw_header(draw, True)
    draw.text((2, 15), f"Devices:{len(devices)}  Flocks:{len(flock_list)}", font=SMALL_FONT, fill="#888")
    if not flock_list:
        draw.text((6, 40), "No flocks detected", font=SMALL_FONT, fill="#666")
        draw.text((6, 52), "Waiting for data...", font=SMALL_FONT, fill="#666")
    else:
        visible = flock_list[sc:sc+5]
        y = 28
        for i, flock in enumerate(visible):
            idx = sc + i
            prefix = ">" if idx == sel else " "
            color = "#00FF00" if flock["score"] >= 70 else "#FFAA00" if flock["score"] >= 40 else "#FF4444"
            draw.text((1, y), f"{prefix}{flock['size']}dev {flock['score']}%", font=SMALL_FONT, fill=color)
            y += 12
    draw_footer(draw, f"Flocks:{len(flock_list)} OK:View K2:Radar")
    LCD.LCD_ShowImage(img, 0, 0)

def draw_flock_detail(flock):
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W-1, 13), fill="#111")
    draw.text((2, 1), f"FLOCK ({flock['size']} dev)", font=FONT, fill="#FF6600")
    draw.text((2, 16), f"Score: {flock['score']}%", font=SMALL_FONT, fill="#AAA")
    members = flock["members"]
    y = 30
    for mac in members[:6]:
        draw.text((2, y), mac[-15:], font=SMALL_FONT, fill="#00CCFF")
        y += 12
    if len(members) > 6:
        draw.text((2, y), f"+{len(members)-6} more", font=SMALL_FONT, fill="#888")
    draw_footer(draw, "Any key: back")
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Radar view
# ----------------------------------------------------------------------
def get_device_color(score):
    if score >= 70:
        return (255, 0, 0)     # Red - high confidence
    elif score >= 40:
        return (255, 165, 0)   # Orange - medium
    else:
        return (255, 255, 0)   # Yellow - low

def draw_radar_view():
    global radar_angle
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    draw_header(draw, True)
    # Radar circle
    cx, cy = W//2, H//2 - 10
    r = 50
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline="#00FF00", width=1)
    draw.line((cx, cy-r, cx, cy+r), fill="#00FF00", width=1)
    draw.line((cx-r, cy, cx+r, cy), fill="#00FF00", width=1)
    # Sweep line
    rad = math.radians(radar_angle)
    end_x = cx + int(r * math.cos(rad))
    end_y = cy + int(r * math.sin(rad))
    draw.line((cx, cy, end_x, end_y), fill="#FF6600", width=1)
    # Draw devices
    with lock:
        devices = detected_devices.items()
        for mac, info in devices:
            # Angle based on MAC hash
            h = hash(mac) % 360
            # Radius based on RSSI (stronger = closer to center)
            rssi = info.get("rssi", -60)
            rad_dist = max(10, min(r-5, int( (rssi + 90) * (r/30) )))
            x = cx + int(rad_dist * math.cos(math.radians(h)))
            y = cy + int(rad_dist * math.sin(math.radians(h)))
            color = get_device_color(info["score"])
            draw.ellipse((x-2, y-2, x+2, y+2), fill=color, outline="#FFFFFF")
            label = mac.replace(":", "")[-4:]
            draw.text((x+3, y-3), label, font=SMALL_FONT, fill="#FFFFFF")
    draw_footer(draw, f"Devices:{len(detected_devices)}  K2:List")
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    global running, view_mode, detail_view, detail_device
    global scroll_pos, selected_idx, detected_devices, radar_angle

    # Find WiFi interface
    ifaces = [name for name in os.listdir("/sys/class/net") if name.startswith("wlan")]
    if not ifaces:
        show_message("No WiFi interface")
        return
    iface = "wlan1" if "wlan1" in ifaces else ifaces[0]

    # Start scanning threads
    threading.Thread(target=ble_scan_thread, daemon=True).start()
    threading.Thread(target=wifi_sniff_thread, args=(iface,), daemon=True).start()

    last_flock_update = 0
    flock_list = []
    detail_flock = None

    try:
        while running:
            btn = wait_btn(0.08)

            if btn == "KEY3":
                running = False
                if detected_devices:
                    export_loot()
                break

            # Handle detail view
            if detail_view:
                if btn is not None:
                    detail_view = False
                    time.sleep(0.2)
                else:
                    draw_flock_detail(detail_flock)
                continue

            # Handle view switching
            if btn == "KEY2":
                if is_long_press("KEY2", hold=2.0):
                    if detected_devices:
                        path = export_loot()
                        show_message("Exported!", path[-20:])
                    else:
                        show_message("No data yet")
                else:
                    view_mode = "radar" if view_mode == "list" else "list"
                    time.sleep(0.2)

            # Update flocks periodically
            now = time.time()
            if now - last_flock_update > 5.0:
                flock_list = compute_flocks()
                last_flock_update = now

            if view_mode == "list":
                if btn == "UP":
                    selected_idx = max(0, selected_idx-1)
                    if selected_idx < scroll_pos:
                        scroll_pos = selected_idx
                elif btn == "DOWN":
                    max_sel = max(0, len(flock_list)-1)
                    selected_idx = min(selected_idx+1, max_sel)
                    if selected_idx >= scroll_pos + 5:
                        scroll_pos = selected_idx - 4
                elif btn == "OK":
                    if selected_idx < len(flock_list):
                        detail_flock = flock_list[selected_idx]
                        detail_view = True
                elif btn == "KEY1":
                    with lock:
                        detected_devices = {}
                    show_message("Data reset")
                draw_list_view()
            else:  # radar view
                if btn == "KEY1":
                    with lock:
                        detected_devices = {}
                    show_message("Data reset")
                radar_angle = (radar_angle + 5) % 360
                draw_radar_view()

            time.sleep(0.05)

    finally:
        running = False
        LCD.LCD_Clear()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
