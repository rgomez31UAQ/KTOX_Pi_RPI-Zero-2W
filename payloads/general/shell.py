#!/usr/bin/env python3
"""
KTOx Micro Shell – Crash-Proof Minimal Version
"""

import os, sys, time, fcntl, pty, select, re, signal
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont
try:
    from evdev import InputDevice, categorize, ecodes, list_devices
    HAS_EVDEV = True
except:
    HAS_EVDEV = False

WIDTH, HEIGHT = 128, 128
LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

FONT_SIZE = 8
try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", FONT_SIZE)
except:
    FONT = ImageFont.load_default()
CHAR_W, CHAR_H = 8, 10
COLS, ROWS = WIDTH//CHAR_W, HEIGHT//CHAR_H

PINS = {"KEY1":21,"KEY2":20,"KEY3":16}
GPIO.setmode(GPIO.BCM)
for p in PINS.values():
    GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
_prev_state = {p:1 for p in PINS.values()}

scrollback = []
current_line = ""
running = True
shift = False
ansi_escape = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")

# --- Safe keyboard detection ---
keyboard = None
if HAS_EVDEV:
    try:
        for path in list_devices():
            dev = InputDevice(path)
            if ecodes.EV_KEY in dev.capabilities():
                keyboard = dev
                fcntl.fcntl(keyboard.fd, fcntl.F_SETFL,
                            fcntl.fcntl(keyboard.fd, fcntl.F_GETFL)|os.O_NONBLOCK)
                break
    except Exception:
        keyboard = None

# --- PTY shell ---
pid, master_fd = pty.fork()
if pid==0:
    os.execv("/bin/bash", ["bash","--login"])
fcntl.fcntl(master_fd, fcntl.F_SETFL, fcntl.fcntl(master_fd, fcntl.F_GETFL)|os.O_NONBLOCK)

poller = select.poll()
poller.register(master_fd, select.POLLIN)
if keyboard: poller.register(keyboard.fd, select.POLLIN)

# --- Drawing ---
def draw():
    img = Image.new("RGB",(WIDTH,HEIGHT),"black")
    d = ImageDraw.Draw(img)
    visible = scrollback[-(ROWS-1):]+[current_line]
    y=0
    for line in visible:
        d.text((0,y), line.ljust(COLS)[:COLS], font=FONT, fill="#00FF00")
        y+=CHAR_H
    LCD.LCD_ShowImage(img,0,0)

def process_output():
    global current_line, scrollback
    try:
        data = os.read(master_fd,1024).decode(errors="ignore")
    except BlockingIOError:
        return
    except OSError:
        return
    if not data: return
    clean = ansi_escape.sub("", data)
    for ch in clean:
        if ch=="\n":
            scrollback.append(current_line)
            current_line=""
        elif ch in ("\x08","\x7f"):
            current_line=current_line[:-1]
        elif ch=="\r":
            continue
        else:
            current_line+=ch
            while len(current_line)>COLS:
                scrollback.append(current_line[:COLS])
                current_line=current_line[COLS:]
    if len(scrollback)>256:
        scrollback = scrollback[-256:]
    draw()

def cleanup(*_):
    global running
    running=False

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def handle_buttons():
    for pin, delta in ((PINS["KEY1"],+1),(PINS["KEY2"],-1)):
        state = GPIO.input(pin)
        if _prev_state[pin]==1 and state==0:
            pass # zoom or other features can go here
        _prev_state[pin]=state
    if GPIO.input(PINS["KEY3"])==0:
        cleanup()

# --- Main Loop ---
def main():
    global running
    draw()
    while running:
        for fd,_ in poller.poll(50):
            if fd==master_fd:
                process_output()
            elif keyboard and fd==keyboard.fd:
                try:
                    for ev in keyboard.read():
                        if ev.type==ecodes.EV_KEY:
                            key_name = ev.keycode if isinstance(ev.keycode,str) else ev.keycode[0]
                            if key_name=="KEY_ESC": cleanup()
                            elif ev.keystate==1: os.write(master_fd,(key_name+'\n').encode())
                except:
                    pass
        handle_buttons()
        time.sleep(0.02)
    LCD.LCD_Clear()
    GPIO.cleanup()
    try: os.close(master_fd)
    except: pass

if __name__=="__main__":
    main()
