#!/usr/bin/env python3
import os
import sys
import time
from pyboy import PyBoy, WindowEvent # Added WindowEvent import

# Standard KTOx Imports
sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))
import RPi.GPIO as GPIO
import LCD_1in44, LCD_Config
from PIL import Image

# Pins matching your working Game of Life setup
PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}

def main():
    # 1. Setup Hardware
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    LCD_Config.GPIO_Init()
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

    # 2. Load ROM (Ensure this path exists!)
    rom_path = "/home/pi/ktox/roms/game.gbc"
    if not os.path.exists(rom_path):
        print(f"Error: {rom_path} not found.")
        return

    # Start PyBoy in 'dummy' mode to save CPU/GPU cycles
    pyboy = PyBoy(rom_path, window_type="dummy") 
    pyboy.set_emulation_speed(1) # Keep it at 100% speed

    print("KTOX GBC CORE ACTIVE [KEY3 TO EXIT]")

    try:
        while not pyboy.tick():
            # 3. Handle Inputs (Mapped to GBC standard)
            # UP/DOWN/LEFT/RIGHT
            if GPIO.input(PINS["UP"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_UP)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_UP)
            
            if GPIO.input(PINS["DOWN"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_DOWN)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_DOWN)

            if GPIO.input(PINS["LEFT"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_LEFT)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_LEFT)

            if GPIO.input(PINS["RIGHT"]) == 0: pyboy.send_input(WindowEvent.PRESS_ARROW_RIGHT)
            else: pyboy.send_input(WindowEvent.RELEASE_ARROW_RIGHT)

            # A/B Buttons
            if GPIO.input(PINS["OK"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_A)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_A)

            if GPIO.input(PINS["KEY1"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_B)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_B)

            # Start/Select
            if GPIO.input(PINS["KEY2"]) == 0: pyboy.send_input(WindowEvent.PRESS_BUTTON_START)
            else: pyboy.send_input(WindowEvent.RELEASE_BUTTON_START)

            # 4. Refresh LCD (128x128)
            # Resizing is intensive; nearest neighbor is fastest for the Zero 2 W
            screen_image = pyboy.screen_image().resize((128, 128), resample=Image.NEAREST)
            lcd.LCD_ShowImage(screen_image, 0, 0)
            
            # Kill Switch
            if GPIO.input(PINS["KEY3"]) == 0:
                break

    except Exception as e:
        print(f"Core Error: {e}")
    finally:
        pyboy.stop()
        lcd.LCD_Clear()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
