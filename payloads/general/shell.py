#!/usr/bin/env python3
"""
KTOx DarkSec Shell+ – Micro Shell on 1.44-inch LCD
--------------------------------------------------
Fully interactive PTY shell on Waveshare 128x128 LCD.
Supports USB/Bluetooth keyboard, DarkSec theme, scrollback,
and zoom buttons (KEY1/KEY2). Quit via KEY3 or ESC.
"""

import os, sys, time, fcntl, select, pty, signal, re
from PIL import Image, ImageDraw, ImageFont
from evdev import InputDevice, list_devices, categorize, ecodes
import RPi.GPIO as GPIO

# -------------------------------
# LCD Setup
# -------------------------------
import LCD_1in44
LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
WIDTH, HEIGHT = 128, 128

# -------------------------------
# GPIO Pins
# -------------------------------
KEY1_PIN, KEY2_PIN, KEY3_PIN = 21, 20, 16
GPIO.setmode(GPIO.BCM)
for p in (KEY1_PIN, KEY2_PIN, KEY3_PIN):
    GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
_prev_state = {p: 1 for p in (KEY1_PIN, KEY2_PIN)}

# -------------------------------
# Font & Zoom
# -------------------------------
FONT_MIN, FONT_MAX = 6, 10
FONT_SIZE = 8
def load_font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
    except:
        return ImageFont.load_default()
font = load_font(FONT_SIZE)
CHAR_W = CHAR_H = COLS = ROWS = 0

def set_font(size):
    global font, CHAR_W, CHAR_H, COLS, ROWS, FONT_SIZE
    FONT_SIZE = max(FONT_MIN, min(FONT_MAX, size))
    font = load_font(FONT_SIZE)
    img = Image.new("RGB",(10,10))
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0,0),"M",font=font)
    CHAR_W, CHAR_H = bbox[2]-bbox[0], bbox[3]-bbox[1]
    COLS, ROWS = WIDTH//CHAR_W, HEIGHT//CHAR_H
set_font(FONT_SIZE)

# -------------------------------
# Scrollback
# -------------------------------
scrollback = []
current_line = ""

# -------------------------------
# ANSI escape cleaner
# -------------------------------
ansi_escape = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")

# -------------------------------
# Spawn PTY Bash
# -------------------------------
pid, master_fd = pty.fork()
if pid == 0:
    os.execv("/bin/bash", ["bash","--login"])
fcntl.fcntl(master_fd, fcntl.F_SETFL, fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

# -------------------------------
# Keyboard Detection
# -------------------------------
def find_keyboard():
    for path in list_devices():
        dev = InputDevice(path)
        if ecodes.EV_KEY in dev.capabilities():
            return dev
    raise RuntimeError("No keyboard detected!")
keyboard = find_keyboard()
keyboard.grab()
if hasattr(keyboard, "set_blocking"):
    keyboard.set_blocking(False)
else:
    fcntl.fcntl(keyboard.fd, fcntl.F_SETFL, os.O_NONBLOCK)

# -------------------------------
# Poller
# -------------------------------
poller = select.poll()
poller.register(master_fd, select.POLLIN)
poller.register(keyboard.fd, select.POLLIN)

# -------------------------------
# Key maps
# -------------------------------
SHIFT_KEYS = {"KEY_LEFTSHIFT","KEY_RIGHTSHIFT"}
KEYMAP = {f"KEY_{c}":c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
KEYMAP.update({
    "KEY_SPACE":" ","KEY_ENTER":"\n","KEY_KPENTER":"\n","KEY_TAB":"\t",
    "KEY_MINUS":"-","KEY_EQUAL":"=","KEY_LEFTBRACE":"[","KEY_RIGHTBRACE":"]",
    "KEY_BACKSLASH":"\\","KEY_SEMICOLON":";","KEY_APOSTROPHE":"'","KEY_GRAVE":"`",
    "KEY_COMMA":",","KEY_DOT":".","KEY_SLASH":"/",
    "KEY_1":"1","KEY_2":"2","KEY_3":"3","KEY_4":"4","KEY_5":"5",
    "KEY_6":"6","KEY_7":"7","KEY_8":"8","KEY_9":"9","KEY_0":"0",
})
SHIFT_MAP = {
    "KEY_1":"!","KEY_2":"@","KEY_3":"#","KEY_4":"$","KEY_5":"%",
    "KEY_6":"^","KEY_7":"&","KEY_8":"*","KEY_9":"(","KEY_0":")",
    "KEY_MINUS":"_","KEY_EQUAL":"+","KEY_LEFTBRACE":"{","KEY_RIGHTBRACE":"}",
    "KEY_BACKSLASH":"|","KEY_SEMICOLON":":","KEY_APOSTROPHE":"\"","KEY_GRAVE":"~",
    "KEY_COMMA":"<","KEY_DOT":">","KEY_SLASH":"?",
    **{f"KEY_{c}":c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
}

# -------------------------------
# Draw buffer
# -------------------------------
def draw_buffer(lines, partial=""):
    img = Image.new("RGB",(WIDTH,HEIGHT),(0,0,0))
    d = ImageDraw.Draw(img)
    visible = lines[-(ROWS-1):] + [partial]
    y = 0
    for line in visible:
        d.text((0,y),line.ljust(COLS)[:COLS],font=font,fill=(0,255,65))
        y+=CHAR_H
    LCD.LCD_ShowImage(img,0,0)

# -------------------------------
# Write to PTY
# -------------------------------
def write_byte(s):
    os.write(master_fd,s.encode())

# -------------------------------
# Process PTY output
# -------------------------------
def process_shell_output():
    global current_line, scrollback
    try:
        data = os.read(master_fd,1024).decode(errors="ignore")
    except BlockingIOError:
        return
    if not data:
        return
    clean = ansi_escape.sub("",data)
    for ch in clean:
        if ch=="\n":
            scrollback.append(current_line)
            current_line=""
        elif ch in ("\x08","\x7f"):
            current_line=current_line[:-1]
        else:
            current_line+=ch
            while len(current_line)>COLS:
                scrollback.append(current_line[:COLS])
                current_line=current_line[COLS:]
    if len(scrollback)>256:
        scrollback=scrollback[-256:]
    draw_buffer(scrollback,current_line)

# -------------------------------
# Key handling
# -------------------------------
shift=False
running=True

def handle_key(event):
    global shift
    key_name = event.keycode if isinstance(event.keycode,str) else event.keycode[0]
    if key_name in SHIFT_KEYS:
        shift = event.keystate==event.key_down
        return
    if event.keystate!=event.key_down:
        return
    if key_name=="KEY_ESC" or GPIO.input(KEY3_PIN)==0:
        global running
        running=False
        return
    char = SHIFT_MAP.get(key_name) if shift else KEYMAP.get(key_name)
    if char: write_byte(char)

# -------------------------------
# Main loop
# -------------------------------
draw_buffer([], "KTOx DarkSec Shell+ ready")
try:
    while running:
        for fd,_ in poller.poll(50):
            if fd==master_fd:
                process_shell_output()
            elif fd==keyboard.fd:
                for ev in keyboard.read():
                    if ev.type==ecodes.EV_KEY:
                        handle_key(categorize(ev))
        # Zoom buttons
        for pin,delta in ((KEY1_PIN,+1),(KEY2_PIN,-1)):
            state = GPIO.input(pin)
            if _prev_state[pin]==1 and state==0:
                set_font(FONT_SIZE+delta)
                draw_buffer(scrollback,current_line)
                time.sleep(0.15)
            _prev_state[pin]=state
        if GPIO.input(KEY3_PIN)==0:
            running=False
except Exception as e:
    print(f"[ERROR] {e}",file=sys.stderr)
finally:
    LCD.LCD_Clear()
    GPIO.cleanup()
    try: os.close(master_fd)
    except: pass
