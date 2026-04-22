#!/usr/bin/env python3
"""
KTOx Payload – Media Player with Full Controls
=================================================
- Plays video (MP4, AVI, MKV, MOV, WebM) and audio (MP3, WAV, FLAC, OGG)
- USB audio via plughw:1,0 (your Onn headset)
- Auto‑installs ffmpeg, alsa-utils, python3-pil if missing
- Playback controls: pause, next, previous, volume
- Non‑blocking buttons, smooth 15 fps video, A/V sync

Controls in file browser: UP/DOWN, OK, LEFT, KEY1=stop, KEY3=exit
Controls during playback:
  KEY1 – stop
  KEY2 – pause/resume
  LEFT – previous file
  RIGHT – next file
  UP   – volume up (+10%)
  DOWN – volume down (-10%)
  KEY3 – stop (same as KEY1)
"""

import os
import sys
import time
import json
import subprocess
import signal

# ----------------------------------------------------------------------
# Auto‑install dependencies
# ----------------------------------------------------------------------
def auto_install():
    missing = []
    if os.system("which ffmpeg >/dev/null 2>&1") != 0:
        missing.append("ffmpeg")
    if os.system("which aplay >/dev/null 2>&1") != 0:
        missing.append("alsa-utils")
    if os.system("which amixer >/dev/null 2>&1") != 0:
        missing.append("alsa-utils")  # amixer is part of alsa-utils
    try:
        from PIL import Image
    except ImportError:
        missing.append("python3-pil")

    if not missing:
        return True

    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    W, H = 128, 128
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    except:
        font = ImageFont.load_default()
    img = Image.new("RGB", (W, H), (10, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((64, 30), "Installing dependencies...", font=font, fill=(30, 132, 73), anchor="mm")
    d.text((64, 50), f"Missing: {', '.join(missing)}", font=font, fill=(171, 178, 185), anchor="mm")
    d.text((64, 70), "Please wait", font=font, fill=(113, 125, 126), anchor="mm")
    LCD.LCD_ShowImage(img, 0, 0)

    try:
        subprocess.run(["apt", "update"], check=True, capture_output=True)
        subprocess.run(["apt", "install", "-y"] + missing, check=True, capture_output=True)
        return True
    except:
        return False

# ----------------------------------------------------------------------
# Hardware
# ----------------------------------------------------------------------
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

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

def wait_btn_nonblock():
    for name, pin in PINS.items():
        if GPIO.input(pin) == 0:
            time.sleep(0.05)
            return name
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
# Audio device and volume control
# ----------------------------------------------------------------------
AUDIO_DEV = "plughw:1,0"

def set_volume(delta):
    """Change volume by delta percent (e.g., +10 or -10)."""
    try:
        # Get current volume
        result = subprocess.run(["amixer", "-D", "hw:1", "sget", "Master"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "Front Left:" in line or "Playback" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "[" and i+1 < len(parts):
                        vol_str = parts[i+1].replace("%", "")
                        vol = int(vol_str)
                        new_vol = max(0, min(100, vol + delta))
                        subprocess.run(["amixer", "-D", "hw:1", "sset", "Master", f"{new_vol}%"], capture_output=True)
                        return new_vol
    except:
        pass
    return 50

# ----------------------------------------------------------------------
# Config persistence
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/MediaPlayer"
os.makedirs(LOOT_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(LOOT_DIR, "config.json")
START_DIR = "/root/Videos"
os.makedirs(START_DIR, exist_ok=True)

VIDEO_EXTS = ('.mp4', '.avi', '.mkv', '.mov', '.webm')
AUDIO_EXTS = ('.mp3', '.wav', '.flac', '.ogg')
ALL_MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS

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
# File browser
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
    d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
    d.text((4, 2), "MEDIA PLAYER", font=FONT_BOLD, fill=(231, 76, 60))
    count_text = f"{len(entries)}"
    tw = d.textlength(count_text, font=FONT)
    d.text((W - 4 - int(tw), 2), count_text, font=FONT, fill=(30, 132, 73))
    path_display = os.path.basename(path) if path != "/" else path
    d.text((4, 14), f"📂 {path_display[:20]}", font=FONT, fill=(171, 178, 185))
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
    if len(entries) > 5:
        bar_h = max(4, int(5 / len(entries) * 70))
        bar_y = 26 + int((scroll / max(1, len(entries)-5)) * (70 - bar_h))
        d.rectangle((W-4, bar_y, W-2, bar_y+bar_h), fill=(192, 57, 43))
    d.rectangle((0, H-12, W, H), fill=(34, 0, 0))
    d.text((4, H-10), "UP/DN OK LEFT K1=Stop K3=Exit", font=FONT, fill=(192, 57, 43))
    LCD.LCD_ShowImage(img, 0, 0)

# ----------------------------------------------------------------------
# Playback with controls (pause, next, prev, volume)
# ----------------------------------------------------------------------
current_proc = None
paused = False
current_volume = 50

def stop_playback():
    global current_proc, paused
    if current_proc:
        try:
            current_proc.terminate()
            current_proc.wait(timeout=2)
        except:
            current_proc.kill()
        current_proc = None
    paused = False

def pause_playback():
    global paused, current_proc
    if not current_proc:
        return
    if paused:
        # Resume: send SIGCONT
        current_proc.send_signal(signal.SIGCONT)
        paused = False
    else:
        # Pause: send SIGSTOP
        current_proc.send_signal(signal.SIGSTOP)
        paused = True

def play_audio(filepath):
    """Play audio with controls using ffmpeg + aplay pipeline."""
    global current_proc, paused, current_volume
    stop_playback()
    # Use a shell pipeline so we can control the whole process group
    cmd = f"ffmpeg -i '{filepath}' -f s16le -ac 2 -ar 48000 - | aplay -D {AUDIO_DEV} -f S16_LE -c 2 -r 48000"
    current_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

def play_video(filepath):
    """Play video with controls."""
    global current_proc, paused, current_volume
    stop_playback()
    cmd = [
        "ffmpeg", "-re", "-i", filepath,
        "-vf", "fps=15,scale=128:128", "-pix_fmt", "rgb24",
        "-f", "rawvideo", "-vsync", "cfr", "-",
        "-map", "0:a", "-f", "alsa", AUDIO_DEV, "-ac", "2", "-ar", "48000", "-async", "1"
    ]
    current_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return current_proc

def playback_control_loop(playlist, start_idx):
    """
    playlist: list of file paths
    start_idx: index to start playing
    Handles next/prev/pause/stop/volume.
    Returns when user stops (KEY1/KEY3) or list exhausted.
    """
    global current_proc, paused, current_volume
    idx = start_idx
    is_video = False
    paused = False
    # Set initial volume
    set_volume(current_volume - 50)  # just to sync? We'll read later

    while 0 <= idx < len(playlist):
        filepath = playlist[idx]
        is_video = filepath.lower().endswith(VIDEO_EXTS)
        if is_video:
            proc = play_video(filepath)
            frame_size = 128 * 128 * 3
            # Show now‑playing screen for video
            img = Image.new("RGB", (W, H), (10, 0, 0))
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
            d.text((4, 2), "NOW PLAYING", font=FONT_BOLD, fill=(231, 76, 60))
            d.text((4, 20), f"🎬 {os.path.basename(filepath)[:18]}", font=FONT, fill=(171, 178, 185))
            d.text((4, 35), "K2=Pause  K1=Stop", font=FONT, fill=(113, 125, 126))
            d.text((4, 45), "LEFT/RIGHT=Prev/Next", font=FONT, fill=(113, 125, 126))
            d.text((4, 55), "UP/DOWN=Volume", font=FONT, fill=(113, 125, 126))
            LCD.LCD_ShowImage(img, 0, 0)
            time.sleep(1)
            # Video rendering loop
            while True:
                btn = wait_btn_nonblock()
                if btn == "KEY1" or btn == "KEY3":
                    stop_playback()
                    return idx  # return current index so we can resume browser
                elif btn == "KEY2":
                    pause_playback()
                elif btn == "LEFT":
                    stop_playback()
                    idx = (idx - 1) % len(playlist)
                    break
                elif btn == "RIGHT":
                    stop_playback()
                    idx = (idx + 1) % len(playlist)
                    break
                elif btn == "UP":
                    current_volume = set_volume(+10)
                elif btn == "DOWN":
                    current_volume = set_volume(-10)

                # Read video frame
                if current_proc and not paused:
                    raw = current_proc.stdout.read(frame_size)
                    if len(raw) < frame_size:
                        # EOF – end of video
                        stop_playback()
                        idx = (idx + 1) % len(playlist)
                        break
                    try:
                        frame = Image.frombytes("RGB", (128, 128), raw)
                        LCD.LCD_ShowImage(frame, 0, 0)
                    except:
                        pass
                else:
                    # If paused, just update the control screen (no frame read)
                    time.sleep(0.05)
        else:
            # Audio playback
            play_audio(filepath)
            # Show now‑playing screen for audio
            img = Image.new("RGB", (W, H), (10, 0, 0))
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, W, 13), fill=(139, 0, 0))
            d.text((4, 2), "NOW PLAYING", font=FONT_BOLD, fill=(231, 76, 60))
            d.text((4, 20), f"🎵 {os.path.basename(filepath)[:18]}", font=FONT, fill=(171, 178, 185))
            d.text((4, 35), "K2=Pause  K1=Stop", font=FONT, fill=(113, 125, 126))
            d.text((4, 45), "LEFT/RIGHT=Prev/Next", font=FONT, fill=(113, 125, 126))
            d.text((4, 55), "UP/DOWN=Volume", font=FONT, fill=(113, 125, 126))
            LCD.LCD_ShowImage(img, 0, 0)
            # Audio control loop – check buttons and process end
            while True:
                btn = wait_btn_nonblock()
                if btn == "KEY1" or btn == "KEY3":
                    stop_playback()
                    return idx
                elif btn == "KEY2":
                    pause_playback()
                elif btn == "LEFT":
                    stop_playback()
                    idx = (idx - 1) % len(playlist)
                    break
                elif btn == "RIGHT":
                    stop_playback()
                    idx = (idx + 1) % len(playlist)
                    break
                elif btn == "UP":
                    current_volume = set_volume(+10)
                elif btn == "DOWN":
                    current_volume = set_volume(-10)

                # Check if process ended (audio finished)
                if current_proc and current_proc.poll() is not None:
                    stop_playback()
                    idx = (idx + 1) % len(playlist)
                    break
                time.sleep(0.05)

    return idx

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not auto_install():
        GPIO.cleanup()
        sys.exit(1)

    cfg = load_config()
    path = cfg.get("last_dir", START_DIR)
    if not os.path.exists(path):
        path = START_DIR
    entries = list_media(path)
    cursor = 0
    scroll = 0
    show_message("Media Player Ready", f"Audio: {AUDIO_DEV}")

    while True:
        draw_browser(path, entries, cursor, scroll)
        btn = wait_btn_nonblock()
        if btn == "KEY3":
            break
        elif btn == "UP" and cursor > 0:
            cursor -= 1
            if cursor < scroll:
                scroll = cursor
        elif btn == "DOWN" and entries and cursor < len(entries)-1:
            cursor += 1
            if cursor >= scroll + 5:
                scroll = cursor - 4
        elif btn == "LEFT":
            parent = os.path.dirname(path)
            if parent != path:
                path = parent
                entries = list_media(path)
                cursor = 0
                scroll = 0
                cfg["last_dir"] = path
                save_config(cfg)
        elif btn == "OK" and entries:
            e = entries[cursor]
            if e.is_dir():
                path = e.path
                entries = list_media(path)
                cursor = 0
                scroll = 0
                cfg["last_dir"] = path
                save_config(cfg)
            else:
                # Build playlist from current directory (all media files in this folder)
                playlist = [f.path for f in entries if not f.is_dir()]
                # Start playback from the selected file
                start_idx = [i for i, f in enumerate(playlist) if f == e.path][0]
                playback_control_loop(playlist, start_idx)
                # After playback, refresh file list in case new files added
                entries = list_media(path)
        elif btn == "KEY1":
            # stop playback if any (not in file browser, but handle anyway)
            pass
        time.sleep(0.05)

    LCD.LCD_Clear()
    GPIO.cleanup()

if __name__ == "__main__":
    main()
