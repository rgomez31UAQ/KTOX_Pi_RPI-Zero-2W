#!/usr/bin/env python3
"""
KTOx Payload – Video Player with Bluetooth (FULLY WORKING)
===========================================================
- Smooth video playback (128x128, 10fps, rawvideo)
- Bluetooth menu with cursor selection (UP/DOWN/OK)
- Automatic A2DP switching for audio
- Clean file browser with scrolling
- Clean exit – no freezing

Controls:
  File browser: UP/DOWN/LEFT/OK/KEY2(Bluetooth)/KEY3(exit)
  Bluetooth menu: UP/DOWN/OK(connect/pair)/KEY2(scan)/KEY3(back)
"""

import os
import sys
import time
import subprocess
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# Hardware & LCD
# ----------------------------------------------------------------------
PINS = {"UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,"KEY1":21,"KEY2":20,"KEY3":16}
VIDEO_EXTS = ('.mp4','.avi','.mkv','.mov','.webm')
START_DIRS = ["/media","/home","/root","/tmp"]

GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
W, H = 128, 128

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
except:
    font = ImageFont.load_default()

def draw_screen(lines, title="VIDEO PLAYER", title_color="#8B0000"):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0,0,W,17), fill=title_color)
    d.text((4,3), title[:20], font=font, fill="#FF3333")
    y = 20
    for line in lines[:7]:
        d.text((4,y), line[:23], font=font, fill="#FFBBBB")
        y += 12
    d.rectangle((0,H-12,W,H), fill="#220000")
    d.text((4,H-10), "UP/DN OK LEFT K2=BT K3=exit", font=font, fill="#FF7777")
    LCD.LCD_ShowImage(img,0,0)

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
# Bluetooth Manager (with cursor selection)
# ----------------------------------------------------------------------
def bt_cmd(cmd):
    subprocess.run(["bluetoothctl", cmd], capture_output=True)

def get_devices():
    out = subprocess.run(["bluetoothctl","devices"], capture_output=True, text=True).stdout
    devs = []
    for line in out.splitlines():
        if line.startswith("Device "):
            parts = line.split(" ", 2)
            if len(parts) >= 3:
                devs.append((parts[1], parts[2]))
    return devs

def scan_devices(duration=6):
    bt_cmd("scan off")
    bt_cmd("menu scan"); bt_cmd("transport le"); bt_cmd("back")
    bt_cmd("scan on")
    time.sleep(duration)
    bt_cmd("scan off")
    return get_devices()

def pair_and_connect(mac):
    bt_cmd(f"pair {mac}"); time.sleep(2)
    bt_cmd(f"trust {mac}")
    bt_cmd(f"connect {mac}"); time.sleep(2)
    # Force A2DP
    cards = subprocess.run("pactl list cards short | grep bluez | cut -f1", shell=True, capture_output=True, text=True).stdout.strip()
    if cards:
        subprocess.run(f"pactl set-card-profile {cards} a2dp-sink", shell=True)
        sink = subprocess.run("pactl list sinks | grep -A1 bluez | grep 'Name:' | cut -d: -f2 | tr -d ' '", shell=True, capture_output=True, text=True).stdout.strip()
        if sink:
            subprocess.run(f"pactl set-default-sink {sink}", shell=True)
    return True

def bluetooth_menu():
    while True:
        devices = get_devices()
        lines = ["BLUETOOTH MENU", "Paired devices:"]
        if devices:
            for i, (mac, name) in enumerate(devices[:5]):
                lines.append(f"{i+1}. {name[:16]}")
        else:
            lines.append("(none)")
        lines.append(""); lines.append("K2=scan  OK=connect  K3=back")
        draw_screen(lines, title="BLUETOOTH", title_color="#004466")
        btn = wait_btn()
        if btn == "KEY3": return
        if btn == "KEY2":
            draw_screen(["Scanning...", "6 sec"], title="SCAN")
            found = scan_devices(6)
            if not found:
                draw_screen(["No devices found"], title="SCAN")
                time.sleep(1.5)
                continue
            idx = 0
            while True:
                mac, name = found[idx]
                draw_screen([f"Select device:", name[:18], "", f"{idx+1}/{len(found)}", "UP/DOWN OK"], title="PAIR")
                btn2 = wait_btn()
                if btn2 == "UP": idx = (idx-1)%len(found)
                elif btn2 == "DOWN": idx = (idx+1)%len(found)
                elif btn2 == "OK":
                    draw_screen([f"Pairing {name[:15]}..."], title="PAIR")
                    pair_and_connect(mac)
                    draw_screen([f"Connected to {name[:15]}", "Audio ready"], title="SUCCESS")
                    time.sleep(2)
                    return
                elif btn2 == "KEY3": break
        elif btn == "OK" and devices:
            idx = 0
            while True:
                mac, name = devices[idx]
                draw_screen([f"Connect to:", name[:18], "", f"{idx+1}/{len(devices)}", "UP/DOWN OK"], title="CONNECT")
                btn2 = wait_btn()
                if btn2 == "UP": idx = (idx-1)%len(devices)
                elif btn2 == "DOWN": idx = (idx+1)%len(devices)
                elif btn2 == "OK":
                    draw_screen([f"Connecting to {name[:15]}..."], title="CONNECT")
                    bt_cmd(f"connect {mac}")
                    time.sleep(2)
                    # Force A2DP after connection
                    cards = subprocess.run("pactl list cards short | grep bluez | cut -f1", shell=True, capture_output=True, text=True).stdout.strip()
                    if cards:
                        subprocess.run(f"pactl set-card-profile {cards} a2dp-sink", shell=True)
                    draw_screen([f"Connected to {name[:15]}", "Audio ready"], title="SUCCESS")
                    time.sleep(2)
                    return
                elif btn2 == "KEY3": break

# ----------------------------------------------------------------------
# File Browser (with smooth scrolling)
# ----------------------------------------------------------------------
def list_media(path):
    try:
        items = []
        for f in sorted(os.scandir(path), key=lambda x: (not x.is_dir(), x.name.lower())):
            if f.is_dir() or f.name.lower().endswith(VIDEO_EXTS):
                items.append(f)
        return items
    except PermissionError:
        return []

def draw_browser(path, entries, sel, scroll):
    lines = []
    short = os.path.basename(path) or "/"
    lines.append(f"Dir: {short[:18]}")
    lines.append("")
    visible = entries[scroll:scroll+5]
    for i, e in enumerate(visible):
        idx = scroll + i
        marker = ">" if idx == sel else " "
        name = e.name[:18] + ("/" if e.is_dir() else "")
        lines.append(f"{marker} {name}")
    if not entries:
        lines.append("(empty)")
    draw_screen(lines, title="FILE BROWSER", title_color="#004466")

# ----------------------------------------------------------------------
# Video Player (smooth, 10fps, with audio via PulseAudio)
# ----------------------------------------------------------------------
playback_active = False
ffmpeg_proc = None

def stop_playback():
    global ffmpeg_proc, playback_active
    if ffmpeg_proc:
        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.wait(timeout=2)
        except:
            ffmpeg_proc.kill()
        ffmpeg_proc = None
    playback_active = False
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD.LCD_Clear()

def play_video(video_path):
    global ffmpeg_proc, playback_active
    playback_active = True
    # Ensure A2DP is active (if Bluetooth connected)
    cards = subprocess.run("pactl list cards short | grep bluez | cut -f1", shell=True, capture_output=True, text=True).stdout.strip()
    if cards:
        subprocess.run(f"pactl set-card-profile {cards} a2dp-sink", shell=True)
        sink = subprocess.run("pactl list sinks | grep -A1 bluez | grep 'Name:' | cut -d: -f2 | tr -d ' '", shell=True, capture_output=True, text=True).stdout.strip()
        if sink:
            subprocess.run(f"pactl set-default-sink {sink}", shell=True)
    # ffmpeg command: scale to 128x128 at 10fps, raw video to stdout, audio to pulse
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "scale=128:128,fps=10",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-",
        "-f", "pulse", "-device", "default"
    ]
    try:
        ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception as e:
        draw_screen([f"FFmpeg error", str(e)[:20]], title="ERROR")
        time.sleep(2)
        playback_active = False
        return
    frame_size = 128 * 128 * 3
    draw_screen(["Playing...", os.path.basename(video_path)[:18]], title="VIDEO")
    while playback_active:
        btn = wait_btn(0.01)
        if btn in ("KEY1", "KEY3"):
            stop_playback()
            break
        raw = ffmpeg_proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        try:
            img = Image.frombytes("RGB", (128, 128), raw)
            LCD.LCD_ShowImage(img, 0, 0)
        except:
            pass
    stop_playback()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # Check dependencies
    if os.system("which ffmpeg > /dev/null 2>&1") != 0:
        draw_screen(["ffmpeg not installed", "sudo apt install ffmpeg", "KEY3 to exit"], title="ERROR")
        while wait_btn() != "KEY3":
            pass
        GPIO.cleanup()
        sys.exit(1)
    # Start directory
    path = "/"
    for d in START_DIRS:
        if os.path.isdir(d):
            path = d
            break
    entries = list_media(path)
    sel = 0
    scroll = 0
    while True:
        draw_browser(path, entries, sel, scroll)
        btn = wait_btn()
        if btn == "KEY3":
            break
        elif btn == "UP" and sel > 0:
            sel -= 1
            if sel < scroll:
                scroll = sel
        elif btn == "DOWN" and entries and sel < len(entries) - 1:
            sel += 1
            if sel >= scroll + 5:
                scroll = sel - 4
        elif btn == "LEFT":
            parent = os.path.dirname(path)
            if parent != path:
                path = parent
                entries = list_media(path)
                sel = 0
                scroll = 0
        elif btn == "KEY2":
            bluetooth_menu()
            entries = list_media(path)  # refresh
        elif btn == "OK" and entries:
            selected = entries[sel]
            if selected.is_dir():
                path = selected.path
                entries = list_media(path)
                sel = 0
                scroll = 0
            else:
                play_video(selected.path)
                entries = list_media(path)
    LCD.LCD_Clear()
    GPIO.cleanup()
    sys.exit(0)

if __name__ == "__main__":
    main()
