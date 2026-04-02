#!/usr/bin/env python3
"""
KTOx MicroShell – Fixed v1.6b
==============================
Hand‑held Linux terminal: interactive /bin/bash in a PTY,
driven by a USB keyboard, rendered on 128×128 Waveshare LCD.

Requirements:
-------------
sudo apt install python3-evdev python3-pil

Quit: Esc on keyboard OR KEY3 on HAT
"""

# ---------------------------------------------------------
# 0) Imports & path tweaks
# ---------------------------------------------------------
import os, sys, time, signal, select, fcntl, pty, re
sys.path.append(os.path.abspath(os.path.join(__file__, '..', '..')))

import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageFont
from evdev import InputDevice, categorize, ecodes, list_devices
import RPi.GPIO as GPIO

# ---------------------------------------------------------
# 1) LCD init
# ---------------------------------------------------------
LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
WIDTH, HEIGHT = 128, 128

# ---------------------------------------------------------
# 2) Font management
# ---------------------------------------------------------
FONT_MIN, FONT_MAX = 6, 10
FONT_SIZE = 8

def load_font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
    except Exception:
        return ImageFont.load_default()

font = None
CHAR_W = CHAR_H = COLS = ROWS = 0

def set_font(size: int):
    global FONT_SIZE, font, CHAR_W, CHAR_H, COLS, ROWS
    FONT_SIZE = max(FONT_MIN, min(FONT_MAX, size))
    font = load_font(FONT_SIZE)
    _img = Image.new("RGB", (10, 10))
    _d = ImageDraw.Draw(_img)
    _bbox = _d.textbbox((0, 0), "M", font=font)
    CHAR_W, CHAR_H = _bbox[2] - _bbox[0], _bbox[3] - _bbox[1]
    COLS, ROWS = WIDTH // CHAR_W, HEIGHT // CHAR_H

set_font(FONT_SIZE)

# ---------------------------------------------------------
# 3) GPIO pins – KEY1/KEY2 zoom, KEY3 quit
# ---------------------------------------------------------
KEY1_PIN, KEY2_PIN, KEY3_PIN = 21, 20, 16
GPIO.setmode(GPIO.BCM)
for p in (KEY1_PIN, KEY2_PIN, KEY3_PIN):
    GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

_prev_state = {p: 1 for p in (KEY1_PIN, KEY2_PIN)}

# ---------------------------------------------------------
# 4) Locate USB keyboard
# ---------------------------------------------------------
def find_keyboard() -> InputDevice:
    for path in list_devices():
        dev = InputDevice(path)
        name = dev.name.lower()
        if "keyboard" in name or "kbd" in name:
            return dev
    raise RuntimeError("No USB keyboard detected")

keyboard = find_keyboard()
if hasattr(keyboard, "set_blocking"):
    keyboard.set_blocking(False)
elif hasattr(keyboard, "setblocking"):
    keyboard.setblocking(False)
else:
    fcntl.fcntl(keyboard.fd, fcntl.F_SETFL, os.O_NONBLOCK)

# ---------------------------------------------------------
# 5) Screen drawing helpers
# ---------------------------------------------------------
scrollback: list[str] = []
current_line: str = ""

def draw_buffer(lines: list[str], partial: str = "") -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ImageDraw.Draw(img)
    visible = lines[-(ROWS - 1):] + [partial]
    y = 0
    for line in visible:
        d.text((0, y), line.ljust(COLS)[:COLS], font=font, fill="#00FF00")
        y += CHAR_H
    LCD.LCD_ShowImage(img, 0, 0)

# ---------------------------------------------------------
# 6) Spawn Bash in PTY
# ---------------------------------------------------------
pid, master_fd = pty.fork()
if pid == 0:
    os.execv("/bin/bash", ["bash", "--login"])
fcntl.fcntl(master_fd, fcntl.F_SETFL, fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)
time.sleep(0.1)
os.write(master_fd, b"\n")  # force prompt

# ---------------------------------------------------------
# 7) Poller
# ---------------------------------------------------------
poller = select.poll()
poller.register(master_fd, select.POLLIN)
poller.register(keyboard.fd, select.POLLIN)

# ---------------------------------------------------------
# 8) Key maps
# ---------------------------------------------------------
SHIFT_KEYS = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}
KEYMAP = {**{f"KEY_{c}": c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
          "KEY_SPACE": " ", "KEY_ENTER": "\n", "KEY_KPENTER": "\n",
          "KEY_BACKSPACE": "\x7f", "KEY_TAB": "\t",
          "KEY_MINUS": "-", "KEY_EQUAL": "=", "KEY_LEFTBRACE": "[",
          "KEY_RIGHTBRACE": "]", "KEY_BACKSLASH": "\\",
          "KEY_SEMICOLON": ";", "KEY_APOSTROPHE": "'", "KEY_GRAVE": "`",
          "KEY_COMMA": ",", "KEY_DOT": ".", "KEY_SLASH": "/",
          **{f"KEY_{i}": str(i) for i in range(10)}}
SHIFT_MAP = {"KEY_1": "!", "KEY_2": "@", "KEY_3": "#", "KEY_4": "$",
             "KEY_5": "%", "KEY_6": "^", "KEY_7": "&", "KEY_8": "*",
             "KEY_9": "(", "KEY_0": ")", "KEY_MINUS": "_", "KEY_EQUAL": "+",
             "KEY_LEFTBRACE": "{", "KEY_RIGHTBRACE": "}", "KEY_BACKSLASH": "|",
             "KEY_SEMICOLON": ":", "KEY_APOSTROPHE": "\"", "KEY_GRAVE": "~",
             "KEY_COMMA": "<", "KEY_DOT": ">", "KEY_SLASH": "?",
             **{f"KEY_{c}": c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}}

ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

# ---------------------------------------------------------
# 9) Shell output
# ---------------------------------------------------------
def write_byte(s: str):
    os.write(master_fd, s.encode())

def process_shell_output():
    global current_line, scrollback
    try:
        data = os.read(master_fd, 1024).decode(errors="ignore")
    except BlockingIOError:
        return
    if not data:
        return
    clean = ansi_escape.sub("", data)
    for ch in clean:
        if ch == "\n":
            scrollback.append(current_line)
            current_line = ""
        elif ch in ("\r"):
            continue
        elif ch in ("\x08", "\x7f"):
            current_line = current_line[:-1]
        else:
            current_line += ch
            while len(current_line) > COLS:
                scrollback.append(current_line[:COLS])
                current_line = current_line[COLS:]
    if len(scrollback) > 256:
        scrollback = scrollback[-256:]
    draw_buffer(scrollback, current_line)

# ---------------------------------------------------------
# 10) Key handling
# ---------------------------------------------------------
shift = False
running = True

def handle_key(event):
    global shift, running
    key_name = event.keycode if isinstance(event.keycode, str) else event.keycode[0]
    if key_name in SHIFT_KEYS:
        shift = event.keystate == event.key_down
        return
    if event.keystate != event.key_down:
        return
    if key_name == "KEY_ESC" or GPIO.input(KEY3_PIN) == 0:
        running = False
        return
    char = SHIFT_MAP.get(key_name) if shift else KEYMAP.get(key_name)
    if char is not None:
        write_byte(char)

# ---------------------------------------------------------
# 11) Main loop
# ---------------------------------------------------------
draw_buffer([], "Micro Shell ready – KEY1/KEY2 = zoom ±")
try:
    while running:
        for fd, _ in poller.poll(50):
            if fd == master_fd:
                process_shell_output()
            elif fd == keyboard.fd:
                try:
                    events = keyboard.read()
                except BlockingIOError:
                    events = []
                for ev in events:
                    if ev.type == ecodes.EV_KEY:
                        handle_key(categorize(ev))
        # Zoom buttons
        for pin, delta in ((KEY1_PIN, +1), (KEY2_PIN, -1)):
            state = GPIO.input(pin)
            if _prev_state[pin] == 1 and state == 0:
                set_font(FONT_SIZE + delta)
                draw_buffer(scrollback, current_line)
                time.sleep(0.15)
            _prev_state[pin] = state
        # Quit via KEY3 held
        if GPIO.input(KEY3_PIN) == 0:
            running = False
except Exception as exc:
    print(f"[ERROR] {exc}", file=sys.stderr)
finally:
    LCD.LCD_Clear()
    GPIO.cleanup()
    try:
        os.close(master_fd)
    except Exception:
        pass
