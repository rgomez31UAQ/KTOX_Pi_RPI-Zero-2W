#!/usr/bin/env python3
"""
KTOx GBC Emulator – Full Single-Script Build
================================================
- Works on Raspberry Pi Zero 2 W
- Manual ROM launch, no auto-boot, no HUD
- GPIO buttons for D-pad, A/B, Start/Select
- Save/load states via extra buttons
- ROM artwork preview
- Optimized for SPI / framebuffer LCD
"""

import os
import subprocess
import time
import RPi.GPIO as GPIO
import threading

# -----------------------------
# CONFIG
# -----------------------------
ROM_DIR = "/home/pi/ktox/roms"
ART_DIR = "/home/pi/ktox/art"
EMULATOR = "/home/pi/SameBoy/build/bin/sameboy"

# GPIO button mapping (BCM)
BUTTONS = {
    5: "Up",
    6: "Down",
    16: "Left",
    26: "Right",
    12: "z",       # A
    13: "x",       # B
    20: "Return",  # Start
    21: "Shift_L", # Select
    23: "F2",      # SAVE STATE
    24: "F3"       # LOAD STATE
}

# Framebuffer / SDL environment
ENV = os.environ.copy()
ENV["SDL_VIDEODRIVER"] = "fbcon"
ENV["SDL_FBDEV"] = "/dev/fb1"
ENV["SDL_RENDER_DRIVER"] = "software"
ENV["SDL_FBACCEL"] = "0"

# -----------------------------
# GPIO SETUP
# -----------------------------
GPIO.setmode(GPIO.BCM)
for pin in BUTTONS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

state = {pin: 1 for pin in BUTTONS}

def press(key):
    subprocess.run(["xdotool", "keydown", key])

def release(key):
    subprocess.run(["xdotool", "keyup", key])

def input_listener():
    while True:
        for pin, key in BUTTONS.items():
            val = GPIO.input(pin)
            if val == 0 and state[pin] == 1:
                press(key)
                state[pin] = 0
            elif val == 1 and state[pin] == 0:
                release(key)
                state[pin] = 1
        time.sleep(0.01)

# -----------------------------
# BANNER
# -----------------------------
def banner():
    print("\033[95m")
    print("╔══════════════════════════════╗")
    print("║      KTOX // GBC CORE        ║")
    print("║   [NO TRACE] [NO SIGNAL]     ║")
    print("║     READY TO EXECUTE         ║")
    print("╚══════════════════════════════╝")
    print("\033[0m")

# -----------------------------
# ROM / ART FUNCTIONS
# -----------------------------
def list_roms():
    roms = [f for f in os.listdir(ROM_DIR) if f.endswith((".gb", ".gbc"))]
    return roms

def show_art(rom):
    name = os.path.splitext(rom)[0]
    art_path = os.path.join(ART_DIR, f"{name}.png")
    if os.path.exists(art_path):
        subprocess.run(["fbi", "-T", "1", "-d", "/dev/fb1", "--noverbose", art_path])

def menu(roms):
    for i, r in enumerate(roms):
        print(f"\033[92m[{i}]\033[0m {r}")
    try:
        choice = int(input("\nSelect ROM: "))
        if 0 <= choice < len(roms):
            show_art(roms[choice])
            time.sleep(1)
            return roms[choice]
    except:
        pass
    return None

# -----------------------------
# LAUNCH ROM
# -----------------------------
def launch(rom):
    # Start GPIO listener thread
    listener_thread = threading.Thread(target=input_listener, daemon=True)
    listener_thread.start()

    # Launch emulator
    subprocess.run([EMULATOR, os.path.join(ROM_DIR, rom)], env=ENV)

# -----------------------------
# MAIN LOOP
# -----------------------------
def main():
    while True:
        os.system("clear")
        banner()
        roms = list_roms()
        if not roms:
            print("No ROMs found in ~/ktox/roms")
            return
        rom = menu(roms)
        if rom:
            launch(rom)

if __name__ == "__main__":
    main()
