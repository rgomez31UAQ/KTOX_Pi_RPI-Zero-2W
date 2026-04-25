#!/usr/bin/env python3
# ktox_device.py — KTOx_Pi v1.0
# Raspberry Pi Zero 2W · Kali ARM64 · Waveshare 1.44" LCD HAT (ST7735S)
#
# Architecture: mirrors KTOx exactly
#   · Global image / draw / LCD objects
#   · _display_loop  — LCD_ShowImage() at ~10 fps continuously
#   · _stats_loop    — toolbar (temp + status) every 2 s
#   · draw_lock      — threading.Lock  on every draw call
#   · screen_lock    — threading.Event frozen during payload
#   · getButton()    — virtual (WebUI Unix socket) first, then GPIO
#   · exec_payload() — subprocess.run() BLOCKING + _setup_gpio() restore
#
# WebUI: device_server.py (WebSocket :8765) + web_server.py (HTTP :8080)
# Loot:  /root/KTOx/loot/  (symlinked from /root/KTOx/loot)
#
# Menu navigation
#   Joystick UP/DOWN     navigate
#   Joystick CTR/RIGHT   select / enter
#   KEY1  / LEFT         back
#   KEY2                 home
#   KEY3                 stop attack / exit payload

import os, sys, time, json, threading, subprocess, signal, socket, ipaddress, math
import base64, hashlib, hmac, secrets
from datetime import datetime
from functools import partial
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

KTOX_DIR      = "/root/KTOx"
INSTALL_PATH  = KTOX_DIR + "/"
LOOT_DIR      = KTOX_DIR + "/loot"
PAYLOAD_DIR   = KTOX_DIR + "/payloads"
WALLPAPER_DIR = LOOT_DIR + "/wallpapers"
PAYLOAD_LOG   = LOOT_DIR + "/payload.log"
VERSION      = "1.0"

sys.path.insert(0, KTOX_DIR)
sys.path.insert(0, KTOX_DIR + "/ktox_pi")

# ── WebUI input bridge (independent of physical hardware) ──────────────────────

try:
    import ktox_input as rj_input
    HAS_INPUT = True
except Exception as _ie:
    print(f"[WARN] WebUI input bridge unavailable ({_ie})")
    HAS_INPUT = False

# ── Hardware imports ───────────────────────────────────────────────────────────

try:
    import RPi.GPIO as GPIO
    from PIL import Image, ImageDraw, ImageFont
    import LCD_1in44
    import LCD_Config
    HAS_HW = True
except Exception as _ie:
    print(f"[WARN] Hardware unavailable ({_ie}) — headless mode")
    HAS_HW = False

# ── GPIO pin map ───────────────────────────────────────────────────────────────

PINS = {
    "KEY_UP_PIN":    6,
    "KEY_DOWN_PIN":  19,
    "KEY_LEFT_PIN":  5,
    "KEY_RIGHT_PIN": 26,
    "KEY_PRESS_PIN": 13,
    "KEY1_PIN":      21,
    "KEY2_PIN":      20,
    "KEY3_PIN":      16,
}

# ── Threading primitives ───────────────────────────────────────────────────────

draw_lock   = threading.Lock()      # protect every draw call
screen_lock = threading.Event()     # set = freeze display / stats threads
_stop_evt   = threading.Event()

# ── Button debounce state ──────────────────────────────────────────────────────

_last_button       = None
_last_button_time  = 0.0
_button_down_since = 0.0
_debounce_s        = 0.10
_repeat_delay      = 0.25
_repeat_interval   = 0.08

# ── Manual-lock: hold KEY3 for this many seconds to lock from anywhere ─────────
_LOCK_HOLD_BTN  = "KEY3_PIN"
_LOCK_HOLD_SECS = 2.0

# ── Live status text (updated by _stats_loop) ─────────────────────────────────

_status_text = ""
_temp_c      = 0.0

# ── Payload state paths ────────────────────────────────────────────────────────

PAYLOAD_STATE_PATH   = "/dev/shm/ktox_payload_state.json"
PAYLOAD_REQUEST_PATH = "/dev/shm/rj_payload_request.json"   # WebUI uses rj_ prefix

# ── Global LCD / image / draw (KTOx pattern — must be globals) ───────────

LCD   = None
image = None
draw  = None

# ── Fonts ──────────────────────────────────────────────────────────────────────

text_font  = None
small_font = None
icon_font  = None
medium_icon_font = None
large_icon_font = None

def _load_fonts():
    global text_font, small_font, icon_font, medium_icon_font, large_icon_font
    MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    MONO      = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    FA        = "/usr/share/fonts/truetype/fontawesome/fa-solid-900.ttf"
    def _f(p, sz):
        try:    return ImageFont.truetype(p, sz)
        except: return ImageFont.load_default()
    text_font  = _f(MONO_BOLD, 9)
    small_font = _f(MONO,      8)
    icon_font  = _f(FA,       12) if os.path.exists(FA) else None
    medium_icon_font = _f(FA,  20) if os.path.exists(FA) else None
    large_icon_font = _f(FA,   32) if os.path.exists(FA) else None

# ── Runtime state ──────────────────────────────────────────────────────────────

ktox_state = {
    "iface":       "eth0",
    "wifi_iface":  "wlan0",   # updated by _init_wifi_iface() after GPIO setup
    "gateway":     "",
    "hosts":       [],
    "running":     None,
    "mon_iface":   None,
    "stealth":     False,
    "stealth_image": None,
}

def _init_wifi_iface():
    """Called once after hardware init. Prefer wlan1 (external adapter) over wlan0."""
    import re as _re
    try:
        rc, out = _run(["iw", "dev"])
        ifaces = _re.findall(r"Interface\s+(\w+)", out) if rc == 0 else []
    except Exception:
        ifaces = []
    for candidate in ("wlan1", "wlan2", "wlan3"):
        if candidate in ifaces:
            ktox_state["wifi_iface"] = candidate
            return
    # Keep wlan0 if it's the only one available

# 
# ── Defaults / config class ────────────────────────────────────────────────────
# 

class Defaults:
    start_text      = [10, 20]
    text_gap        = 14
    install_path    = INSTALL_PATH
    payload_path    = PAYLOAD_DIR + "/"
    payload_log     = PAYLOAD_LOG
    imgstart_path   = "/root/"
    config_file     = KTOX_DIR + "/gui_conf.json"
    screensaver_gif = KTOX_DIR + "/img/screensaver/default.gif"

default = Defaults()

# 
# ── Colour scheme ──────────────────────────────────────────────────────────────
# 

class ColorScheme:
    border            = "#8B0000"
    background        = "#0a0a0a"
    text              = "#c8c8c8"
    selected_text     = "#FFFFFF"
    select            = "#640000"
    gamepad           = "#640000"
    gamepad_fill      = "#F0EDE8"
    title_bg          = "#1a0000"
    panel_bg          = "#0d0606"
    current_theme     = "ktox_red"

    def DrawBorder(self):
        draw.line([(127,12),(127,127)], fill=self.border, width=5)
        draw.line([(127,127),(0,127)],  fill=self.border, width=5)
        draw.line([(0,127),(0,12)],     fill=self.border, width=5)
        draw.line([(0,12),(128,12)],    fill=self.border, width=5)

    def DrawMenuBackground(self):
        if _wallpaper_image:
