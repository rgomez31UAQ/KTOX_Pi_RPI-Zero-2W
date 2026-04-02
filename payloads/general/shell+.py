#!/usr/bin/env python3
import os, sys, time, subprocess, threading
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

# KTOx / Waveshare Imports
sys.path.insert(0, "/root/KTOx")
import LCD_1in44
import LCD_Config

# --- Configuration ---
COLOR_BG = "#050505"
COLOR_TXT = "#00FF41" # Matrix Green (or change to #FF0000 for DarkSec Red)
COLOR_HDR = "#FF0000"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

class KTOxShell:
    def __init__(self):
        self.lcd = LCD_1in44.LCD()
        self.lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        self.image = Image.new("RGB", (self.lcd.width, self.lcd.height), COLOR_BG)
        self.draw = ImageDraw.Draw(self.image)
        try:
            self.font = ImageFont.truetype(FONT_PATH, 10)
        except:
            self.font = ImageFont.load_default()
        
        self.lines = ["> KTOX_SHEEL V1.0", "> READY_"]
        self.max_lines = 9

    def render(self):
        self.draw.rectangle((0, 0, 128, 128), fill=COLOR_BG)
        # Draw Header
        self.draw.rectangle((0, 0, 128, 12), fill=COLOR_HDR)
        self.draw.text((2, 1), " TERMINAL MODE ", fill="#FFFFFF", font=self.font)
        
        # Draw Output Lines
        y = 15
        for line in self.lines[-self.max_lines:]:
            self.draw.text((5, y), line, fill=COLOR_TXT, font=self.font)
            y += 12
        
        self.lcd.LCD_ShowImage(self.image, 0, 0)

    def add_line(self, text):
        # Wrap text for 1.44" screen (approx 20 chars)
        wrapped = [text[i:i+20] for i in range(0, len(text), 20)]
        self.lines.extend(wrapped)
        self.render()

    def run_cmd(self, cmd):
        self.add_line(f"# {cmd}")
        try:
            res = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            for l in res.splitlines():
                self.add_line(l)
        except Exception as e:
            self.add_line("ERR: CMD FAILED")

def main():
    # 1. Claim the Hardware
    shell = KTOxShell()
    shell.add_line("INIT DARKSEC...")
    shell.add_line(f"USER: {os.getlogin()}")
    
    # 2. Run initial Recon
    shell.run_cmd("hostname -I")
    
    # 3. Listen for Stop (KEY3)
    # Note: KTOx uses PIN 16 for KEY3
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    shell.add_line("HOLD KEY3 TO EXIT")
    
    try:
        while True:
            # If you have a BT keyboard, you could add an input() loop here
            # For now, this stays open so you can see loot/status
            if GPIO.input(16) == 0:
                shell.add_line("EXITING...")
                time.sleep(1)
                break
            time.sleep(0.1)
    finally:
        GPIO.cleanup() # CRITICAL: Release pins for the main menu!

if __name__ == "__main__":
    main()
