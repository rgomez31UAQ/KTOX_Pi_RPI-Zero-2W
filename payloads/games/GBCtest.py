#!/usr/bin/env python3
import os
import sys
import time
import threading
from flask import Flask, render_template_string, request, redirect
from pyboy import PyBoy, WindowEvent

# KTOx Driver Imports
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))
import RPi.GPIO as GPIO
import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageFont
from payloads._input_helper import get_button

# --- CONFIG ---
ROM_DIR = "/root/KTOx/roms"
os.makedirs(ROM_DIR, exist_ok=True)

PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}

# --- WEB SERVER (BAKED IN) ---
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        f = request.files['file']
        if f:
            f.save(os.path.join(ROM_DIR, f.name if hasattr(f, 'name') else f.filename))
            return redirect('/')
    
    roms = os.listdir(ROM_DIR)
    return render_template_string('''
        <body style="background:#000; color:#0f0; font-family:monospace; text-align:center;">
            <h1 style="color:red;">KTOx // GBC_INJECTOR</h1>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="file" style="background:#111; color:#0f0; border:1px solid #0f0;">
                <button type="submit" style="background:red; color:white; border:none; padding:10px;">INJECT ROM</button>
            </form>
            <hr><h3>VAULT:</h3>
            <ul style="list-style:none; padding:0;">{% for r in roms %}<li>{{r}}</li>{% endfor %}</ul>
        </body>
    ''', roms=roms)

def start_web():
    # Run silently in the background
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- EMULATOR CORE ---
def lcd_init():
    LCD_Config.GPIO_Init()
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    return lcd

def rom_selector(lcd):
    cursor = 0
    while True:
        roms = sorted([f for f in os.listdir(ROM_DIR) if f.lower().endswith(('.gb', '.gbc'))])
        
        img = Image.new("RGB", (128, 128), "black")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 128, 14), fill="red")
        draw.text((5, 2), "DARKSEC GBC CORE", fill="white")

        if not roms:
            draw.text((10, 50), "WAITING FOR ROM...", fill="#00FF41")
            draw.text((10, 70), "URL: PI_IP:5000", fill="white")
        else:
            for i, rom in enumerate(roms[:8]):
                prefix = "> " if i == cursor else "  "
                color = "#00FF41" if i == cursor else "#888888"
                draw.text((5, 20 + (i*12)), f"{prefix}{rom[:15]}", fill=color)

        lcd.LCD_ShowImage(img, 0, 0)
        
        btn = get_button(PINS, GPIO)
        if btn == "DOWN" and roms: cursor = (cursor + 1) % len(roms)
        elif btn == "UP" and roms: cursor = (cursor - 1) % len(roms)
        elif btn == "OK" and roms: return os.path.join(ROM_DIR, roms[cursor])
        elif btn == "KEY3": return None
        time.sleep(0.1)

def play_game(lcd, path):
    try:
        pyboy = PyBoy(path, window_type="dummy")
        while not pyboy.tick():
            # Raw GPIO reads for zero-latency gameplay
            if GPIO.input(PINS["UP"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_UP)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_UP)
            if GPIO.input(PINS["DOWN"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_DOWN)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_DOWN)
            if GPIO.input(PINS["LEFT"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_LEFT)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_LEFT)
            if GPIO.input(PINS["RIGHT"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_RIGHT)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_RIGHT)
            
            if GPIO.input(PINS["OK"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_A)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_A)
            if GPIO.input(PINS["KEY1"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_B)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_B)
            if GPIO.input(PINS["KEY2"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_START)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_START)

            # Render to SPI LCD
            frame = pyboy.screen_image().resize((128, 128), resample=Image.NEAREST)
            lcd.LCD_ShowImage(frame, 0, 0)

            if GPIO.input(PINS["KEY3"]) == 0: break # Exit back to ROM menu
        pyboy.stop()
    except Exception as e:
        print(f"ERROR: {e}")

def main():
    # 1. Setup
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values(): GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    lcd = lcd_init()

    # 2. Fire up the Baked Web Server
    web_thread = threading.Thread(target=start_web, daemon=True)
    web_thread.start()

    # 3. Main Loop
    while True:
        rom = rom_selector(lcd)
        if not rom: break
        play_game(lcd, rom)

    GPIO.cleanup()
    lcd.LCD_Clear()

if __name__ == "__main__":
    main()
