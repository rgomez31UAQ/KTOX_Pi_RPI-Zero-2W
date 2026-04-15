#!/usr/bin/env python3
"""
KTOx Payload – Video Player (Stable)
=====================================
Plays videos on the Waveshare LCD using ffmpeg.
Exits cleanly – no freezing.

Controls:
  UP/DOWN   – navigate
  LEFT      – parent directory
  OK        – play video
  KEY1/KEY3 – stop playback / exit
"""

import os
import sys
import time
import subprocess
import threading
import signal

# ----------------------------------------------------------------------
# Hardware
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

PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26,
        "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}
VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.webm'}
START_DIRS = ["/media", "/home", "/root", "/tmp"]

# ----------------------------------------------------------------------
# LCD
# ----------------------------------------------------------------------
LCD = None
image = None
draw = None
font_sm = None

def init_lcd():
    global LCD, image, draw, font_sm
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD.LCD_Clear()
    image = Image.new("RGB", (128, 128), "black")
    draw = ImageDraw.Draw(image)
    try:
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    except:
        font_sm = ImageFont.load_default()

def draw_screen(lines, title="VIDEO PLAYER", title_color="#8B0000"):
    draw.rectangle((0,0,128,128), fill="#0A0000")
    draw.rectangle((0,0,128,17), fill=title_color)
    draw.text((4,3), title[:20], font=font_sm, fill="#FF3333")
    y = 20
    for line in lines[:7]:
        draw.text((4,y), line[:23], font=font_sm, fill="#FFBBBB")
        y += 12
    draw.rectangle((0,128-12,128,128), fill="#220000")
    draw.text((4,128-10), "UP/DN OK LEFT K3", font=font_sm, fill="#FF7777")
    LCD.LCD_ShowImage(image, 0, 0)

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
# File browser
# ----------------------------------------------------------------------
def list_media(path):
    try:
        items = []
        for f in sorted(os.scandir(path), key=lambda x: (not x.is_dir(), x.name.lower())):
            if f.is_dir():
                items.append(f)
            elif f.name.lower().endswith(tuple(VIDEO_EXTS)):
                items.append(f)
        return items
    except:
        return []

def draw_browser(path, entries, sel):
    lines = []
    short = os.path.basename(path) or "/"
    lines.append(f"Dir: {short[:18]}")
    lines.append("")
    start = max(0, sel - 5)
    for i in range(start, min(start+6, len(entries))):
        e = entries[i]
        marker = ">" if i == sel else " "
        name = e.name[:18] + ("/" if e.is_dir() else "")
        lines.append(f"{marker} {name}")
    if not entries:
        lines.append("(empty)")
    draw_screen(lines)

# ----------------------------------------------------------------------
# Video player (clean exit)
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
    # Reinit LCD after playback (in case framebuffer was messed)
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD.LCD_Clear()
    # Redraw browser (will happen in main loop)

def play_video(video_path):
    global ffmpeg_proc, playback_active
    playback_active = True
    # Show loading message
    draw.rectangle((0,0,128,128), fill="black")
    draw.text((4,60), "Loading...", font=font_sm, fill="#00FF00")
    LCD.LCD_ShowImage(image, 0, 0)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "scale=128:128,fps=10",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-"
    ]
    try:
        ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception as e:
        draw_screen([f"FFmpeg error", str(e)[:20]], title="ERROR")
        time.sleep(2)
        playback_active = False
        return

    frame_size = 128 * 128 * 3
    # Clear screen
    draw.rectangle((0,0,128,128), fill="black")
    LCD.LCD_ShowImage(image, 0, 0)

    while playback_active:
        # Check for stop button (non-blocking)
        btn = wait_btn(0.01)
        if btn in ("KEY1", "KEY3"):
            stop_playback()
            break

        raw = ffmpeg_proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break  # end of video

        try:
            img = Image.frombytes("RGB", (128, 128), raw)
            LCD.LCD_ShowImage(img, 0, 0)
        except:
            pass

    stop_playback()  # ensure cleanup

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not HAS_HW:
        return
    init_lcd()

    # Check ffmpeg
    if os.system("which ffmpeg > /dev/null 2>&1") != 0:
        draw_screen(["ffmpeg not installed", "sudo apt install ffmpeg", "KEY3 to exit"], title="ERROR")
        while wait_btn(0.5) != "KEY3":
            pass
        GPIO.cleanup()
        return

    # Start directory
    path = "/"
    for d in START_DIRS:
        if os.path.isdir(d):
            path = d
            break
    entries = list_media(path)
    sel = 0

    running = True
    while running:
        draw_browser(path, entries, sel)
        btn = wait_btn(0.5)
        if btn == "KEY3":
            running = False
        elif btn == "UP":
            sel = max(0, sel-1)
        elif btn == "DOWN":
            sel = min(len(entries)-1, sel+1) if entries else 0
        elif btn == "LEFT":
            parent = os.path.dirname(path)
            if parent and parent != path:
                path = parent
                entries = list_media(path)
                sel = 0
        elif btn == "OK" and entries:
            selected = entries[sel]
            if selected.is_dir():
                path = selected.path
                entries = list_media(path)
                sel = 0
            else:
                play_video(selected.path)
                # After playback, refresh entries (in case directory changed)
                entries = list_media(path)
        time.sleep(0.05)

    # Clean exit
    if ffmpeg_proc:
        stop_playback()
    LCD.LCD_Clear()
    GPIO.cleanup()
    sys.exit(0)

if __name__ == "__main__":
    main()
