#!/usr/bin/env python3
"""
KTOx Media Player – Professional Edition (USB Audio Fixed)
===========================================================
Unified video/audio player with USB audio output using plughw device.
Supports: MP4, AVI, MKV, MOV, WebM (video) and MP3, WAV, FLAC, OGG (audio)

Controls:
  UP/DOWN – navigate files/folders
  OK      – play selected file / enter folder
  LEFT    – go to parent directory
  KEY1    – stop playback
  KEY3    – exit

Loot: /root/KTOx/loot/MediaPlayer/
"""

import os
import sys
import time
import json
import subprocess
import re
import signal
import threading

import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# Paths & config
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/MediaPlayer"
os.makedirs(LOOT_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(LOOT_DIR, "config.json")
START_DIR = "/root/Videos"
if not os.path.exists(START_DIR):
    os.makedirs(START_DIR, exist_ok=True)

VIDEO_EXTS = ('.mp4', '.avi', '.mkv', '.mov', '.webm')
AUDIO_EXTS = ('.mp3', '.wav', '.flac', '.ogg')
ALL_MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS

# ----------------------------------------------------------------------
# Hardware
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
FONT = font(9)
FONT_BOLD = font(10)
FONT_ICON = font(11)

def wait_btn(timeout=0.1):
    start = time.time()
    while time.time() - start < timeout:
        for name, pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

def show_message(msg, sub=""):
    img = Image.new("RGB", (W, H), (10, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((64, 50), msg, font=FONT_BOLD, fill=(30, 132, 73), anchor="mm")
    if sub:
        d.text((64, 65), sub[:22], font=FONT, fill=(113, 125, 126), anchor="mm")
    LCD.LCD_ShowImage(img, 0, 0)
    time.sleep(1.5)

# ----------------------------------------------------------------------
# Audio device detection (now returns plughw device)
# ----------------------------------------------------------------------
def get_usb_audio_device():
    """Return ALSA device string (e.g., 'plughw:1,0') for USB headset."""
    try:
        result = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.splitlines()
        for line in lines:
            if "Headset" in line or "USB Audio" in line:
                match = re.search(r"card (\d+):", line)
                if match:
                    card = match.group(1)
                    return f"plughw:{card},0"  # Use plughw for automatic conversions
    except:
        pass
    return "plughw:1,0"  # fallback to card 1 (common for USB audio)

# ----------------------------------------------------------------------
# Config persistence
# ----------------------------------------------------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"last_dir": START_DIR}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except:
        pass

# ----------------------------------------------------------------------
# File browser helpers
# ----------------------------------------------------------------------
def list_media(path):
    try:
        items = []
        for f in sorted(os.scandir(path), key=lambda x: (not x.is_dir(), x.name.lower())):
            if f.is_dir() or f.name.lower().endswith(ALL_MEDIA_EXTS):
                items.append(f)
        return items
    except:
        return []

def get_icon(entry):
    if entry.is_dir():
        return "📁"
    name = entry.name.lower()
    if name.endswith(VIDEO_EXTS):
        return "🎬"
    elif name.endswith(AUDIO_EXTS):
        return "🎵"
    return "❓"

def draw_browser(path, entries, cursor, scroll):
    img = Image.new("RGB", (W, H), (10, 0, 0))
    d = ImageDraw.Draw(img)
    # Header
    d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
    d.text((4, 2), "MEDIA PLAYER", font=FONT_BOLD, fill=(231, 76, 60))
    d.text((W-4, 2), f"{len(entries)}", font=FONT, fill=(30, 132, 73), anchor="rt")
    # Path
    path_display = os.path.basename(path) if path != "/" else path
    d.text((4, 14), f"📂 {path_display[:20]}", font=FONT, fill=(171, 178, 185))
    # File list
    y = 26
    visible = entries[scroll:scroll+5]
    for i, e in enumerate(visible):
        idx = scroll + i
        name = e.name[:16] + ("/" if e.is_dir() else "")
        icon = get_icon(e)
        if idx == cursor:
            d.rectangle((0, y-1, W, y+9), fill=(60, 0, 0))
            d.text((4, y), f"{icon} {name}", font=FONT, fill=(255, 255, 255))
        else:
            d.text((4, y), f"{icon} {name}", font=FONT, fill=(171, 178, 185))
        y += 12
    # Scrollbar
    if len(entries) > 5:
        bar_h = max(4, int(5 / len(entries) * 70))
        bar_y = 26 + int((scroll / max(1, len(entries)-5)) * (70 - bar_h))
        d.rectangle((W-4, bar_y, W-2, bar_y+bar_h), fill=(192, 57, 43))
    # Footer
    d.rectangle((0, H-12, W, H), fill=(34, 0, 0))
    d.text((4, H-10), "UP/DN OK LEFT K1=Stop K3=Exit", font=FONT, fill=(192, 57, 43))
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Playback functions (using plughw device)
# ----------------------------------------------------------------------
current_process = None

def stop_playback():
    global current_process
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=2)
        except:
            current_process.kill()
        current_process = None

def play_audio(filepath, audio_dev):
    """Play audio file using ffplay with USB audio output."""
    global current_process
    stop_playback()
    cmd = [
        "ffplay", "-nodisp", "-autoexit",
        "-f", "alsa", "-i", audio_dev,  # Use the plughw device
        "-i", filepath
    ]
    current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def play_video(filepath, audio_dev):
    """Play video file using ffmpeg (video to LCD, audio to USB)."""
    global current_process
    stop_playback()
    cmd = [
        "ffmpeg", "-i", filepath,
        "-vf", "scale=128:128,fps=10",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo", "-",
        "-f", "alsa", "-i", audio_dev,  # Input audio device
        "-ac", "2", "-ar", "48000"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    current_process = proc
    frame_size = 128 * 128 * 3
    # Show now‑playing screen
    img = Image.new("RGB", (W, H), (10, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
    d.text((4, 2), "NOW PLAYING", font=FONT_BOLD, fill=(231, 76, 60))
    d.text((4, 20), f"🎬 {os.path.basename(filepath)[:18]}", font=FONT, fill=(171, 178, 185))
    d.text((4, 35), "Press KEY1 to stop", font=FONT, fill=(113, 125, 126))
    LCD.LCD_ShowImage(img, 0, 0)
    time.sleep(1)
    while True:
        btn = wait_btn(0.05)
        if btn == "KEY1" or btn == "KEY3":
            stop_playback()
            break
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        try:
            frame = Image.frombytes("RGB", (128, 128), raw)
            LCD.LCD_ShowImage(frame, 0, 0)
        except:
            pass
    # Reinit LCD after video
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

# ----------------------------------------------------------------------
# Now‑playing screen for audio (with progress bar)
# ----------------------------------------------------------------------
def play_audio_with_progress(filepath, audio_dev):
    """Play audio and show a simple progress bar (simulated)."""
    global current_process
    stop_playback()
    # Get duration using ffprobe
    duration = 0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout:
            duration = float(result.stdout.strip())
    except:
        pass
    # Start ffplay
    cmd = [
        "ffplay", "-nodisp", "-autoexit",
        "-f", "alsa", "-i", audio_dev,
        "-i", filepath
    ]
    current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Show progress screen
    start_time = time.time()
    while current_process.poll() is None:
        elapsed = time.time() - start_time
        percent = int((elapsed / duration) * 100) if duration > 0 else 0
        percent = min(100, percent)
        img = Image.new("RGB", (W, H), (10, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
        d.text((4, 2), "NOW PLAYING", font=FONT_BOLD, fill=(231, 76, 60))
        d.text((4, 20), f"🎵 {os.path.basename(filepath)[:18]}", font=FONT, fill=(171, 178, 185))
        # Progress bar
        bar_w = int(100 * percent / 100)
        d.rectangle((14, 40, 114, 48), fill=(34, 0, 0), outline=(192, 57, 43))
        d.rectangle((14, 40, 14+bar_w, 48), fill=(30, 132, 73))
        d.text((64, 44), f"{percent}%", font=FONT, fill=(255, 255, 255), anchor="mm")
        # Time
        d.text((64, 60), f"{int(elapsed//60):02d}:{int(elapsed%60):02d}", font=FONT, fill=(171, 178, 185), anchor="mm")
        d.text((4, H-12), "KEY1=stop  K3=exit", font=FONT, fill=(192, 57, 43))
        LCD.LCD_ShowImage(img, 0, 0)
        btn = wait_btn(0.2)
        if btn == "KEY1" or btn == "KEY3":
            stop_playback()
            break
    stop_playback()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    cfg = load_config()
    path = cfg.get("last_dir", START_DIR)
    if not os.path.exists(path):
        path = START_DIR
    entries = list_media(path)
    cursor = 0
    scroll = 0
    audio_dev = get_usb_audio_device()
    show_message("Media Player Ready", f"Audio: {audio_dev}")
    while True:
        draw_browser(path, entries, cursor, scroll)
        btn = wait_btn(0.2)
        if btn == "KEY3":
            break
        if btn == "UP" and cursor > 0:
            cursor -= 1
            if cursor < scroll:
                scroll = cursor
        if btn == "DOWN" and entries and cursor < len(entries)-1:
            cursor += 1
            if cursor >= scroll + 5:
                scroll = cursor - 4
        if btn == "LEFT":
            parent = os.path.dirname(path)
            if parent != path:
                path = parent
                entries = list_media(path)
                cursor = 0
                scroll = 0
                cfg["last_dir"] = path
                save_config(cfg)
        if btn == "OK" and entries:
            e = entries[cursor]
            if e.is_dir():
                path = e.path
                entries = list_media(path)
                cursor = 0
                scroll = 0
                cfg["last_dir"] = path
                save_config(cfg)
            else:
                filepath = e.path
                if filepath.lower().endswith(VIDEO_EXTS):
                    play_video(filepath, audio_dev)
                elif filepath.lower().endswith(AUDIO_EXTS):
                    play_audio_with_progress(filepath, audio_dev)
                # Refresh file list after playback
                entries = list_media(path)
        if btn == "KEY1":
            stop_playback()
    stop_playback()
    LCD.LCD_Clear()
    GPIO.cleanup()

if __name__ == "__main__":
    if os.system("which ffmpeg >/dev/null 2>&1") != 0 or os.system("which ffplay >/dev/null 2>&1") != 0:
        show_message("Missing ffmpeg/ffplay", "sudo apt install ffmpeg")
        sys.exit(1)
    main()
