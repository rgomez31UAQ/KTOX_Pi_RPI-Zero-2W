#!/usr/bin/env python3

# NAME: Media Player

# DESC: Browse and play MP3/MP4 files. Video rendered via ffmpeg→PIL→LCD.

# “””
KTOx Payload — Media Player

Browse and play audio/video files. Video is decoded by ffmpeg and pushed
frame-by-frame through PIL directly to the SPI LCD. Audio plays via mplayer
or mpv with a live Now Playing screen.

Controls:
UP / DOWN   Navigate file list
LEFT        Go to parent directory
OK          Open folder / play file
KEY1        Stop playback
KEY2        Toggle repeat
KEY3        Exit payload
“””

import os, sys, time, subprocess, shutil, threading, struct
from pathlib import Path

KTOX_ROOT = “/root/KTOx”
if os.path.isdir(KTOX_ROOT) and KTOX_ROOT not in sys.path:
sys.path.insert(0, KTOX_ROOT)

try:
import RPi.GPIO as GPIO
import LCD_1in44
import LCD_Config
from PIL import Image, ImageDraw, ImageFont
from payloads._display_helper import ScaledDraw, scaled_font
from payloads._input_helper import get_button
HAS_HW = True
except ImportError as e:
print(f”[media_player] Missing hardware libs: {e}”)
HAS_HW = False

# ── Pins ──────────────────────────────────────────────────────────────────────

PINS = {
“UP”:   6,  “DOWN”: 19, “LEFT”: 5,  “RIGHT”: 26,
“OK”:  13,  “KEY1”: 21, “KEY2”: 20, “KEY3”:  16,
}
DEBOUNCE = 0.20

# ── Media types ───────────────────────────────────────────────────────────────

AUDIO_EXT = {’.mp3’, ‘.flac’, ‘.wav’, ‘.ogg’, ‘.aac’, ‘.m4a’, ‘.opus’}
VIDEO_EXT = {’.mp4’, ‘.avi’, ‘.mkv’, ‘.mov’, ‘.webm’, ‘.m4v’, ‘.flv’}
MEDIA_EXT = AUDIO_EXT | VIDEO_EXT

START_DIRS = [”/media”, “/root/Music”, “/root”, “/tmp”]

# ── LCD globals ───────────────────────────────────────────────────────────────

_lcd  = None
_W    = 128
_H    = 128

def _init_lcd():
global _lcd, _W, _H
_lcd = LCD_1in44.LCD()
_lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
_W, _H = _lcd.width, _lcd.height
_blank()

def _blank():
if _lcd:
_lcd.LCD_ShowImage(Image.new(“RGB”, (_W, _H), “black”), 0, 0)

def _show(img):
if _lcd:
_lcd.LCD_ShowImage(img.convert(“RGB”).resize((_W, _H)), 0, 0)

def _load_font(size):
for p in [
“/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf”,
“/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf”,
“/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf”,
]:
try:
return ImageFont.truetype(p, size)
except Exception:
pass
return ImageFont.load_default()

_font_sm = None
_font_md = None

def _fonts():
global _font_sm, _font_md
if _font_sm is None:
_font_sm = _load_font(9)
_font_md = _load_font(11)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_start():
for d in START_DIRS:
if os.path.isdir(d):
return d
return “/”

def _list_dir(path):
try:
out = []
for e in sorted(os.scandir(path),
key=lambda x: (not x.is_dir(), x.name.lower())):
if e.is_dir() or os.path.splitext(e.name)[1].lower() in MEDIA_EXT:
out.append(e)
return out
except PermissionError:
return []

def _best_player():
for cmd in (“mplayer”, “mpv”, “ffplay”):
if shutil.which(cmd):
return cmd
return None

def _has_ffmpeg():
return shutil.which(“ffmpeg”) is not None

def _media_duration(path):
“”“Return duration in seconds via ffprobe, or 0 on failure.”””
try:
r = subprocess.run(
[“ffprobe”, “-v”, “error”, “-show_entries”, “format=duration”,
“-of”, “default=noprint_wrappers=1:nokey=1”, path],
capture_output=True, text=True, timeout=5
)
return float(r.stdout.strip())
except Exception:
return 0.0

# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_browser(path, entries, sel, repeat):
_fonts()
img = Image.new(“RGB”, (_W, _H), (8, 8, 20))
d   = ImageDraw.Draw(img)

```
# Header
d.rectangle([(0, 0), (_W, 16)], fill=(0, 80, 160))
title = "MEDIA" + (" [R]" if repeat else "")
d.text((4, 3), title, font=_font_sm, fill="white")

# Current dir
short = os.path.basename(path) or "/"
d.text((4, 19), short[:21], font=_font_sm, fill=(90, 150, 255))

max_vis = 6
start   = max(0, sel - max_vis + 1) if sel >= max_vis else 0
y       = 31

for i in range(max_vis):
    idx = start + i
    if idx >= len(entries):
        break
    e      = entries[idx]
    is_sel = (idx == sel)
    ext    = os.path.splitext(e.name)[1].lower()

    if is_sel:
        d.rectangle([(0, y - 1), (_W, y + 12)], fill=(0, 55, 120))

    if e.is_dir():
        icon = "\u25b6"
        col  = (220, 170, 50)
        lbl  = e.name[:17] + "/"
    elif ext in VIDEO_EXT:
        icon = "\u25a0"
        col  = (80, 200, 255)
        lbl  = e.name[:17]
    else:
        icon = "\u266a"
        col  = (80, 255, 140)
        lbl  = e.name[:17]

    if not is_sel:
        col = tuple(max(0, c - 60) for c in col)

    d.text((4,  y), icon, font=_font_sm, fill=col)
    d.text((17, y), lbl,  font=_font_sm, fill=col)
    y += 13

if not entries:
    d.text((4, 60), "(empty)", font=_font_sm, fill=(80, 80, 80))

# Footer
d.rectangle([(0, _H - 14), (_W, _H)], fill=(20, 20, 20))
d.text((4, _H - 12), "OK=play  K2=rpt  K3=exit", font=_font_sm,
       fill=(100, 100, 100))

_show(img)
```

def _draw_now_playing(fname, elapsed=0.0, total=0.0, repeat=False):
_fonts()
img = Image.new(“RGB”, (_W, _H), (5, 5, 15))
d   = ImageDraw.Draw(img)

```
d.rectangle([(0, 0), (_W, 16)], fill=(0, 100, 60))
d.text((4, 3), "\u266b NOW PLAYING", font=_font_sm, fill="white")

title = os.path.splitext(fname)[0]
y = 22
for chunk in [title[i:i+19] for i in range(0, min(len(title), 57), 19)]:
    d.text((4, y), chunk, font=_font_sm, fill=(190, 215, 255))
    y += 12

# Progress bar
bar_y = 78
d.rectangle([(4, bar_y), (_W - 4, bar_y + 6)],
            fill=(25, 25, 35), outline=(50, 50, 70))
if total > 0:
    w = int((_W - 8) * min(elapsed, total) / total)
    if w > 0:
        d.rectangle([(4, bar_y), (4 + w, bar_y + 6)], fill=(0, 180, 80))
    ts = (f"{int(elapsed//60)}:{int(elapsed%60):02d} / "
          f"{int(total//60)}:{int(total%60):02d}")
else:
    tick = int(elapsed * 4) % (_W - 20)
    d.rectangle([(4 + tick, bar_y), (14 + tick, bar_y + 6)],
                fill=(0, 150, 220))
    ts = f"{int(elapsed//60)}:{int(elapsed%60):02d}"

d.text((4, bar_y + 9), ts, font=_font_sm, fill=(120, 120, 120))
if repeat:
    d.text((_W - 14, bar_y + 9), "\u21bb", font=_font_sm, fill=(80, 200, 80))

d.rectangle([(0, _H - 14), (_W, _H)], fill=(20, 20, 20))
d.text((4, _H - 12), "KEY1=stop  KEY3=exit", font=_font_sm,
       fill=(100, 100, 100))

_show(img)
```

def _draw_message(lines, header=“INFO”, header_col=(0, 80, 160)):
_fonts()
img = Image.new(“RGB”, (_W, _H), (8, 8, 20))
d   = ImageDraw.Draw(img)
d.rectangle([(0, 0), (_W, 16)], fill=header_col)
d.text((4, 3), header, font=_font_sm, fill=“white”)
y = 24
for line in lines:
d.text((4, y), str(line)[:21], font=_font_sm, fill=(200, 200, 200))
y += 13
_show(img)

# ── Audio playback ────────────────────────────────────────────────────────────

def play_audio(path, repeat=False):
player = _best_player()
if not player:
_draw_message([“No player found.”, “Install mplayer:”, “apt install mplayer”],
“ERROR”, (160, 0, 0))
time.sleep(3)
return

```
fname   = os.path.basename(path)
total   = _media_duration(path)
stop    = False

while not stop:
    if player == "mplayer":
        cmd = ["mplayer", "-quiet", "-vo", "null", "-ao", "alsa", path]
    elif player == "mpv":
        cmd = ["mpv", "--no-video", "--really-quiet",
               "--audio-device=alsa", path]
    else:
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]

    try:
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception as e:
        _draw_message([f"Launch error:", str(e)[:20]], "ERROR", (160, 0, 0))
        time.sleep(3)
        return

    start_t    = time.time()
    last_btn_t = 0.0

    while proc.poll() is None:
        now     = time.time()
        elapsed = now - start_t
        _draw_now_playing(fname, elapsed=elapsed, total=total, repeat=repeat)

        btn = get_button(PINS, GPIO)
        if btn and (now - last_btn_t) > DEBOUNCE:
            last_btn_t = now
            if btn in ("KEY1", "KEY3"):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stop = True
                break

        time.sleep(0.15)

    proc.wait()

    if stop or not repeat:
        break
    time.sleep(0.3)
```

# ── Video playback — ffmpeg → PIL → LCD_ShowImage ────────────────────────────

# 

# The Waveshare 1.44” LCD uses an SPI ST7735S controller. There is no kernel

# framebuffer for it (/dev/fb1 does NOT exist for SPI-only panels). The only

# way to display video is:

# ffmpeg -i <file> -f rawvideo -pix_fmt rgb24 -vf scale=W:H -r FPS pipe:1

# then read W*H*3 bytes per frame, wrap in PIL Image, call LCD_ShowImage().

TARGET_FPS = 10   # Pi Zero 2W can push ~10-15 fps at 128x128 over SPI

def play_video(path):
if not _has_ffmpeg():
_draw_message([“ffmpeg not found.”, “Install:”, “apt install ffmpeg”],
“ERROR”, (160, 0, 0))
time.sleep(3)
return

```
fname      = os.path.basename(path)
frame_size = _W * _H * 3        # RGB24
stop       = False
last_btn_t = 0.0

_draw_message([fname[:20], "Loading..."], "VIDEO", (0, 80, 160))

cmd = [
    "ffmpeg",
    "-re",                          # read at native frame rate
    "-i", path,
    "-f", "rawvideo",
    "-pix_fmt", "rgb24",
    "-vf", f"scale={_W}:{_H}",
    "-r", str(TARGET_FPS),
    "-an",                          # drop audio (going to alsa separately)
    "pipe:1",
]

# Separate audio process
audio_proc = None
player = _best_player()
if player:
    if player == "mplayer":
        acmd = ["mplayer", "-quiet", "-vo", "null", "-ao", "alsa", path]
    elif player == "mpv":
        acmd = ["mpv", "--no-video", "--really-quiet",
                "--audio-device=alsa", path]
    else:
        acmd = ["ffplay", "-nodisp", "-autoexit",
                "-loglevel", "quiet", "-vn", path]
    try:
        audio_proc = subprocess.Popen(acmd,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
    except Exception:
        audio_proc = None

try:
    proc = subprocess.Popen(cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
except Exception as e:
    _draw_message(["ffmpeg error:", str(e)[:20]], "ERROR", (160, 0, 0))
    if audio_proc:
        audio_proc.terminate()
    time.sleep(3)
    return

try:
    while not stop:
        raw = b""
        # Read exactly one frame
        while len(raw) < frame_size:
            chunk = proc.stdout.read(frame_size - len(raw))
            if not chunk:
                stop = True
                break
            raw += chunk

        if stop or len(raw) < frame_size:
            break

        # Push frame to LCD
        frame = Image.frombytes("RGB", (_W, _H), raw)
        if _lcd:
            _lcd.LCD_ShowImage(frame, 0, 0)

        # Check buttons (non-blocking)
        now = time.time()
        btn = get_button(PINS, GPIO)
        if btn and (now - last_btn_t) > DEBOUNCE:
            last_btn_t = now
            if btn in ("KEY1", "KEY3"):
                stop = True
                break

finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    if audio_proc and audio_proc.poll() is None:
        audio_proc.terminate()
        try:
            audio_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            audio_proc.kill()

# Reinit LCD SPI after heavy ffmpeg I/O
try:
    _lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD_Config.Driver_Delay_ms(50)
except Exception:
    pass
_blank()
```

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
if not HAS_HW:
print(”[media_player] No hardware libs — cannot run.”)
return

```
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

_init_lcd()
_fonts()

cur_path   = _find_start()
entries    = _list_dir(cur_path)
sel        = 0
repeat     = False
last_btn_t = 0.0

try:
    while True:
        _draw_browser(cur_path, entries, sel, repeat)

        btn = get_button(PINS, GPIO)
        now = time.time()

        if btn and (now - last_btn_t) > DEBOUNCE:
            last_btn_t = now

            if btn == "KEY3":
                break
            elif btn == "UP":
                sel = max(0, sel - 1)
            elif btn == "DOWN":
                sel = min(len(entries) - 1, sel + 1) if entries else 0
            elif btn == "LEFT":
                parent = os.path.dirname(cur_path)
                if parent != cur_path:
                    cur_path = parent
                    entries  = _list_dir(cur_path)
                    sel      = 0
            elif btn == "KEY2":
                repeat = not repeat
            elif btn in ("OK", "RIGHT") and entries:
                e = entries[sel]
                if e.is_dir():
                    cur_path = e.path
                    entries  = _list_dir(cur_path)
                    sel      = 0
                else:
                    ext = os.path.splitext(e.name)[1].lower()
                    if ext in VIDEO_EXT:
                        play_video(e.path)
                    else:
                        play_audio(e.path, repeat=repeat)
                    entries = _list_dir(cur_path)

        time.sleep(0.05)

except KeyboardInterrupt:
    pass
finally:
    _blank()
    GPIO.cleanup()
```

if **name** == “**main**”:
main()
