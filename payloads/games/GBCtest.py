#!/usr/bin/env python3
import os
import subprocess
import time
import RPi.GPIO as GPIO
import threading
from evdev import UInput, ecodes as e

# --- CONFIG ---
ROM_DIR = "/home/pi/ktox/roms"
EMULATOR = "/home/pi/SameBoy/build/bin/sameboy" # Ensure this path is correct

# GPIO button mapping (BCM) - Matches KTOx standard pins
BUTTONS = {
    5: e.KEY_UP,
    6: e.KEY_DOWN,
    16: e.KEY_LEFT,
    26: e.KEY_RIGHT,
    12: e.KEY_Z,          # A
    13: e.KEY_X,          # B
    20: e.KEY_ENTER,      # Start
    21: e.KEY_LEFTSHIFT,  # Select
    23: e.KEY_F2,         # Save
    24: e.KEY_F3          # Load
}

# Environment for the 1.44" SPI Screen
ENV = os.environ.copy()
ENV["SDL_VIDEODRIVER"] = "fbcon"
ENV["SDL_FBDEV"] = "/dev/fb1" 

# Initialize Virtual Keyboard
try:
    ui = UInput()
except:
    print("Error: Run with sudo or check uinput permissions.")
    exit()

# --- INPUT LOGIC ---
def input_listener():
    GPIO.setmode(GPIO.BCM)
    for pin in BUTTONS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    last_states = {pin: 1 for pin in BUTTONS}
    
    while True:
        for pin, key_code in BUTTONS.items():
            val = GPIO.input(pin)
            if val != last_states[pin]:
                # 1 = Press (GPIO 0), 0 = Release (GPIO 1)
                ui.write(e.EV_KEY, key_code, 1 if val == 0 else 0)
                ui.syn()
                last_states[pin] = val
        time.sleep(0.01)

# --- UI & LAUNCHER ---
def banner():
    print("\033[91m") # DarkSec Red
    print("┌──────────────────────────────┐")
    print("│      KTOX // GBC CORE        │")
    print("│      SYSTEM: DARKSEC         │")
    print("└──────────────────────────────┘")
    print("\033[0m")

def get_roms():
    if not os.path.exists(ROM_DIR):
        os.makedirs(ROM_DIR)
    return [f for f in os.listdir(ROM_DIR) if f.endswith((".gb", ".gbc"))]

def main():
    # Start input thread once
    threading.Thread(target=input_listener, daemon=True).start()

    while True:
        os.system("clear")
        banner()
        roms = get_roms()
        
        if not roms:
            print(f"No ROMS found in {ROM_DIR}")
            print("Add .gb or .gbc files and restart.")
            time.sleep(5)
            return

        for i, r in enumerate(roms):
            print(f"\033[92m[{i}]\033[0m {r}")
        
        try:
            choice = input("\nSelect ROM Index (or 'q' to quit): ")
            if choice.lower() == 'q': break
            
            rom_path = os.path.join(ROM_DIR, roms[int(choice)])
            
            print(f"\nLaunching {roms[int(choice)]}...")
            # Use --fullscreen to fit the 128x128 display
            subprocess.run([EMULATOR, "--fullscreen", rom_path], env=ENV)
            
        except (ValueError, IndexError):
            print("Invalid selection.")
            time.sleep(1)

if __name__ == "__main__":
    main()
