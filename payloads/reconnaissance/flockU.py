#!/usr/bin/env python3
"""
KTOx Payload – Camera Flock Detector with Radar View
======================================================
Monitors WiFi probe requests, detects groups of devices (flocks)
that appear/disappear together (e.g., Flock cameras).

Controls:
  UP/DOWN      – scroll flocks (list view)
  OK           – view member MACs (list view)
  KEY1         – reset all data
  KEY2 short   – toggle list/radar view
  KEY2 long    – export data to JSON
  KEY3         – exit

Loot: /root/KTOx/loot/FlockDetect/
"""

import os
import sys
import json
import time
import re
import subprocess
import threading
import math
import random
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
                # wait for release
                while GPIO.input(pin) == 0:
                    time.sleep(0.05)
                return True
    return False

# ----------------------------------------------------------------------
# Paths & constants
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/FlockDetect"
os.makedirs(LOOT_DIR, exist_ok=True)
CORRELATION_WINDOW = 30   # seconds
ROWS_VISIBLE = 6

# ----------------------------------------------------------------------
# OUI vendor lookup (including camera brands)
# ----------------------------------------------------------------------
OUI_DB = {
    # Flock cameras (Flock Safety uses Axis hardware)
    "00:0C:43": "Axis",     "00:40:8C": "Axis",     "AC:CC:8E": "Axis",
    "00:1E:C7": "Hikvision","4C:11:AE": "Hikvision","70:E4:22": "Hikvision",
    "00:12:C9": "Dahua",    "4C:54:99": "Dahua",    "9C:8E:CD": "Dahua",
    "00:14:2A": "Sony",     "08:00:46": "Sony",     "00:0F:53": "Panasonic",
    "00:80:5F": "Panasonic","00:0B:5D": "Bosch",    "00:07:5F": "Bosch",
    "00:1E:C7": "Hikvision","00:24:5E": "Vivotek",  "00:40:8C": "Arecont",
    "00:0C:43": "Mobotix",  "00:1C:F0": "FLIR",     "00:1E:3D": "FLIR",
    # Generic devices
    "B8:27:EB": "Raspberry","DC:A6:32": "Raspberry","E4:5F:01": "Raspberry",
    "AC:DE:48": "Apple",    "00:1C:B3": "Apple",    "A4:83:E7": "Apple",
    "FC:F1:36": "Samsung",  "A0:CC:2B": "Samsung",  "8C:F5:A3": "Samsung",
    "78:02:F8": "Xiaomi",   "50:EC:50": "Xiaomi",   "3C:5A:B4": "Google",
    "00:1A:2B": "Cisco",    "00:1B:44": "Cisco",    "40:B0:76": "ASUSTek",
}
def oui_lookup(mac):
    prefix = mac.upper()[:8]
    return OUI_DB.get(prefix, "Unknown")

# ----------------------------------------------------------------------
# Shared state
# ----------------------------------------------------------------------
lock = threading.Lock()
running = True
capturing = False
status_msg = "Idle"
scroll_pos = 0
selected_idx = 0
mac_timestamps = {}      # mac -> list of timestamps
flocks = []              # list of dicts with members, first_seen, score
view_mode = "list"       # "list" or "radar"
detail_view = False      # showing member list of a flock
detail_flock = None

# For radar: assign a color per flock
flock_colors = []        # list of (r,g,b) per flock index

# ----------------------------------------------------------------------
# Probe capture thread
# ----------------------------------------------------------------------
def parse_mac(line):
    match = re.search(r"([\da-fA-F]{2}:){5}[\da-fA-F]{2}", line)
    return match.group(0).upper() if match else None

def capture_thread():
    global capturing, status_msg
    # Try to use monitor interface; we assume it's already in monitor mode.
    cmd = ["tcpdump", "-i", IFACE, "-e", "-l", "type", "mgt", "subtype", "probe-req"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, bufsize=1)
    except Exception as e:
        with lock:
            status_msg = f"tcpdump fail: {str(e)[:10]}"
            capturing = False
        return
    with lock:
        status_msg = "Capturing probes..."
        capturing = True
    try:
        while running:
            line = proc.stdout.readline()
            if not line:
                break
            mac = parse_mac(line)
            if mac and mac != "FF:FF:FF:FF:FF:FF":
                now = time.time()
                with lock:
                    ts_list = mac_timestamps.get(mac, [])
                    ts_list.append(now)
                    # keep only last 100 timestamps per MAC
                    if len(ts_list) > 100:
                        ts_list = ts_list[-100:]
                    mac_timestamps[mac] = ts_list
    except:
        pass
    finally:
        proc.terminate()
        with lock:
            capturing = False
            if "fail" not in status_msg:
                status_msg = "Capture stopped"

# ----------------------------------------------------------------------
# Flock correlation algorithm
# ----------------------------------------------------------------------
def compute_flocks():
    with lock:
        snapshot = {mac: list(ts) for mac, ts in mac_timestamps.items()}
    if len(snapshot) < 2:
        return []
    # Collect all timestamps to find time range
    all_ts = []
    for ts_list in snapshot.values():
        all_ts.extend(ts_list)
    if not all_ts:
        return []
    min_t = min(all_ts)
    max_t = max(all_ts)
    bucket_size = CORRELATION_WINDOW
    # Build bucket presence for each MAC
    mac_buckets = {}
    for mac, ts_list in snapshot.items():
        buckets = set()
        for t in ts_list:
            b = int((t - min_t) / bucket_size)
            buckets.add(b)
        mac_buckets[mac] = frozenset(buckets)
    # Group by Jaccard similarity >= 0.5
    used = set()
    computed = []
    macs = list(snapshot.keys())
    for i, mac_a in enumerate(macs):
        if mac_a in used:
            continue
        group = [mac_a]
        buckets_a = mac_buckets[mac_a]
        if not buckets_a:
            continue
        for j in range(i+1, len(macs)):
            mac_b = macs[j]
            if mac_b in used:
                continue
            buckets_b = mac_buckets[mac_b]
            if not buckets_b:
                continue
            inter = len(buckets_a & buckets_b)
            union = len(buckets_a | buckets_b)
            if union == 0:
                continue
            if inter / union >= 0.5:
                group.append(mac_b)
        if len(group) >= 2:
            for m in group:
                used.add(m)
            # First seen time
            first_ts = min(snapshot[m][0] for m in group)
            first_seen_str = datetime.fromtimestamp(first_ts).strftime("%H:%M:%S")
            # Consistency score
            scores = []
            for gi in range(len(group)):
                for gj in range(gi+1, len(group)):
                    ba = mac_buckets[group[gi]]
                    bb = mac_buckets[group[gj]]
                    u = len(ba | bb)
                    if u > 0:
                        scores.append(len(ba & bb) / u)
            avg_score = int((sum(scores)/len(scores))*100) if scores else 0
            computed.append({
                "members": group,
                "first_seen": first_seen_str,
                "score": avg_score,
                "last_update": time.time(),
            })
    return computed

# ----------------------------------------------------------------------
# Loot export
# ----------------------------------------------------------------------
def export_loot():
    os.makedirs(LOOT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(LOOT_DIR, f"flock_{ts}.json")
    with lock:
        flock_data = []
        for f in flocks:
            flock_data.append({
                "members": [{"mac": m, "vendor": oui_lookup(m)} for m in f["members"]],
                "device_count": len(f["members"]),
                "first_seen": f["first_seen"],
                "consistency_score": f["score"],
            })
        total_macs = len(mac_timestamps)
    data = {
        "timestamp": ts,
        "interface": IFACE,
        "total_macs_seen": total_macs,
        "flocks_detected": len(flock_data),
        "flocks": flock_data,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
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
        active = capturing
        st = status_msg
        total_macs = len(mac_timestamps)
        flock_list = list(flocks)
        sel = selected_idx
        sc = scroll_pos
    draw_header(draw, active)
    draw.text((2, 15), f"{st[:18]} MACs:{total_macs}", font=SMALL_FONT, fill="#888")
    if not flock_list:
        draw.text((6, 40), "Waiting for probes", font=SMALL_FONT, fill="#666")
        draw.text((6, 52), "Detecting correlated", font=SMALL_FONT, fill="#666")
        draw.text((6, 64), "device groups...", font=SMALL_FONT, fill="#666")
        draw.text((6, 80), f"Window: {CORRELATION_WINDOW}s", font=SMALL_FONT, fill="#555")
    else:
        visible = flock_list[sc:sc+ROWS_VISIBLE]
        y = 28
        for i, flock in enumerate(visible):
            idx = sc + i
            prefix = ">" if idx == sel else " "
            count = len(flock["members"])
            score = flock["score"]
            first = flock["first_seen"]
            color = "#00FF00" if score >= 70 else "#FFAA00" if score >= 40 else "#FF4444"
            line = f"{prefix}{count}dev {first} {score}%"
            draw.text((1, y), line[:22], font=SMALL_FONT, fill=color)
            y += 12
        total_items = len(flock_list)
        if total_items > ROWS_VISIBLE:
            bar_h = max(4, int(ROWS_VISIBLE / total_items * 80))
            bar_y = 28 + int(sc / total_items * 80)
            draw.rectangle((W-4, bar_y, W-2, bar_y+bar_h), fill="#444")
    draw_footer(draw, f"Flk:{len(flock_list)} OK:View K2:Radar K3:Exit")
    LCD.LCD_ShowImage(img, 0, 0)

def draw_flock_detail(flock):
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W-1, 13), fill="#111")
    draw.text((2, 1), f"FLOCK ({len(flock['members'])} dev)", font=FONT, fill="#FF6600")
    draw.text((2, 16), f"Score: {flock['score']}%  @{flock['first_seen']}", font=SMALL_FONT, fill="#AAA")
    members = flock["members"]
    y = 30
    for i, mac in enumerate(members[:7]):
        vendor = oui_lookup(mac)
        short_mac = mac[6:]
        vendor_str = vendor[:6] if vendor else "???"
        draw.text((2, y), f"{short_mac} {vendor_str}", font=SMALL_FONT, fill="#00CCFF")
        y += 12
    if len(members) > 7:
        draw.text((2, y), f"+{len(members)-7} more", font=SMALL_FONT, fill="#888")
    draw_footer(draw, "Any key: back")
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Radar view
# ----------------------------------------------------------------------
def get_flock_color(flock_idx):
    # Generate a distinct color based on index
    colors = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (255, 128, 0), (128, 0, 255),
        (0, 128, 255), (255, 64, 64)
    ]
    return colors[flock_idx % len(colors)]

def draw_radar_view(angle):
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    draw_header(draw, capturing)
    # Radar circle
    cx, cy = W//2, H//2 - 10
    r = 50
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline="#00FF00", width=1)
    draw.line((cx, cy-r, cx, cy+r), fill="#00FF00", width=1)
    draw.line((cx-r, cy, cx+r, cy), fill="#00FF00", width=1)
    # Sweep line
    rad = math.radians(angle)
    end_x = cx + int(r * math.cos(rad))
    end_y = cy + int(r * math.sin(rad))
    draw.line((cx, cy, end_x, end_y), fill="#FF6600", width=1)
    # Draw devices
    with lock:
        # Build a mapping from MAC to flock index
        mac_to_flock = {}
        for idx, flock in enumerate(flocks):
            for mac in flock["members"]:
                mac_to_flock[mac] = idx
        # Plot each MAC
        for mac, ts_list in mac_timestamps.items():
            if not ts_list:
                continue
            # Angle based on MAC hash
            h = hash(mac) % 360
            # Radius based on last seen recency (0-50)
            last_seen = ts_list[-1]
            age = time.time() - last_seen
            rad_dist = max(5, r - min(r-5, int(age * 2)))  # older = closer to center
            x = cx + int(rad_dist * math.cos(math.radians(h)))
            y = cy + int(rad_dist * math.sin(math.radians(h)))
            # Color by flock
            flock_idx = mac_to_flock.get(mac, -1)
            if flock_idx >= 0:
                color = get_flock_color(flock_idx)
            else:
                color = (100, 100, 100)  # ungrouped devices
            draw.ellipse((x-2, y-2, x+2, y+2), fill=color, outline="#FFFFFF")
            # Short label (last 4 hex digits)
            label = mac.replace(":", "")[-4:]
            draw.text((x+3, y-3), label, font=SMALL_FONT, fill="#FFFFFF")
    draw_footer(draw, "K2:List  K3:Exit  LongK2:Export")
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    global running, scroll_pos, selected_idx, flocks, mac_timestamps, IFACE
    global view_mode, detail_view, detail_flock
    # Select WiFi interface
    ifaces = [name for name in os.listdir("/sys/class/net") if name.startswith("wlan")]
    if not ifaces:
        show_message("No WiFi interface")
        return
    IFACE = "wlan1" if "wlan1" in ifaces else ifaces[0]
    # Start capture thread
    running = True
    threading.Thread(target=capture_thread, daemon=True).start()
    last_flock_update = 0
    radar_angle = 0
    try:
        while running:
            btn = wait_btn(0.08)
            if btn == "KEY3":
                running = False
                if flocks:
                    export_loot()
                break
            if detail_view:
                if btn is not None:
                    detail_view = False
                    time.sleep(0.2)
                else:
                    draw_flock_detail(detail_flock)
                continue
            # Handle view switching and export
            if btn == "KEY2":
                if is_long_press("KEY2", hold=2.0):
                    with lock:
                        has_data = len(flocks) > 0 or len(mac_timestamps) > 0
                    if has_data:
                        path = export_loot()
                        show_message("Exported!", path[-20:])
                    else:
                        show_message("No data yet")
                else:
                    # Short press: toggle view
                    view_mode = "radar" if view_mode == "list" else "list"
                    time.sleep(0.2)
            if view_mode == "list":
                if btn == "UP":
                    with lock:
                        selected_idx = max(0, selected_idx-1)
                        if selected_idx < scroll_pos:
                            scroll_pos = selected_idx
                elif btn == "DOWN":
                    with lock:
                        max_sel = max(0, len(flocks)-1)
                        selected_idx = min(selected_idx+1, max_sel)
                        if selected_idx >= scroll_pos + ROWS_VISIBLE:
                            scroll_pos = selected_idx - ROWS_VISIBLE + 1
                elif btn == "OK":
                    with lock:
                        if selected_idx < len(flocks):
                            detail_flock = flocks[selected_idx]
                            detail_view = True
                    time.sleep(0.2)
                elif btn == "KEY1":
                    with lock:
                        mac_timestamps = {}
                        flocks = []
                        scroll_pos = 0
                        selected_idx = 0
                    show_message("Data reset")
                draw_list_view()
            else:  # radar view
                if btn == "KEY1":
                    with lock:
                        mac_timestamps = {}
                        flocks = []
                    show_message("Data reset")
                # Update radar sweep angle
                radar_angle = (radar_angle + 5) % 360
                draw_radar_view(radar_angle)
            # Recompute flocks periodically
            now = time.time()
            if now - last_flock_update > 5.0:
                new_flocks = compute_flocks()
                with lock:
                    flocks = new_flocks
                last_flock_update = now
            time.sleep(0.05)
    finally:
        running = False
        time.sleep(0.3)
        LCD.LCD_Clear()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
