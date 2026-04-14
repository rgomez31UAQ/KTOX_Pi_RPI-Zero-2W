#!/usr/bin/env python3
"""
KTOx Payload – Virtual Pet Rock
================================
Author: wickednull

The ultimate low‑maintenance pet. It's a rock.
- No feeding, no cleaning, no dying.
- It ignores you most of the time.
- Press OK 100 times and it might roll over.

Controls:
  OK      – pet the rock (does nothing, counts toward rollover)
  KEY1    – talk to rock (rock ignores you)
  KEY2    – check rock's status (shows "It's a rock")
  KEY3    – exit
"""

import time
import random
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# Hardware setup
# ----------------------------------------------------------------------
PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13,
        "KEY1":21, "KEY2":20, "KEY3":16}
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
W, H = 128, 128

def font(size=9):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()
f9 = font(9)

def draw_screen(lines, title="PET ROCK", title_color="#8B0000"):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0,0,W,17), fill=title_color)
    d.text((4,3), title[:20], font=f9, fill="#FF3333")
    y = 20
    for line in lines[:7]:
        d.text((4,y), line[:23], font=f9, fill="#FFBBBB")
        y += 12
    d.rectangle((0,H-12,W,H), fill="#220000")
    d.text((4,H-10), "OK=pet  K1=talk  K2=status  K3=exit", font=f9, fill="#FF7777")
    LCD.LCD_ShowImage(img,0,0)

def wait_btn(timeout=0.1):
    start = time.time()
    while time.time() - start < timeout:
        for name,pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

# ----------------------------------------------------------------------
# Rock logic
# ----------------------------------------------------------------------
pet_count = 0
rolled_over = False
indifference_messages = [
    "The rock stares blankly.",
    "It's a rock.",
    "No reaction.",
    "The rock is indifferent.",
    "You pet a rock. Congrats.",
    "Nothing happens.",
    "The rock doesn't care.",
    "It's still a rock.",
    "You feel silly.",
    "The rock remains motionless."
]

def pet_rock():
    global pet_count, rolled_over
    pet_count += 1
    if pet_count >= 100 and not rolled_over:
        rolled_over = True
        return "The rock slowly rolls over. Then stops. It's still a rock."
    else:
        return random.choice(indifference_messages)

def talk_to_rock():
    responses = [
        "...", "The rock ignores you.", "It makes no sound.", 
        "Your words echo off the rock.", "The rock doesn't speak.",
        "You hear only silence."
    ]
    return random.choice(responses)

def rock_status():
    global pet_count, rolled_over
    if rolled_over:
        return f"Rock has rolled over once. You petted it {pet_count} times. It's still a rock."
    else:
        return f"Pet count: {pet_count}/100 to roll. It's a rock."

# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def main():
    draw_screen(["Welcome to Virtual Pet Rock", "Your pet requires nothing.", "Press any button."])
    time.sleep(2)
    draw_screen(["The rock is here.", "It judges you silently."])

    while True:
        btn = wait_btn(0.5)
        if btn == "KEY3":
            break
        elif btn == "OK":
            msg = pet_rock()
            draw_screen([msg, "", f"Pet count: {pet_count}"])
            time.sleep(1.5)
        elif btn == "KEY1":
            msg = talk_to_rock()
            draw_screen([msg])
            time.sleep(1.5)
        elif btn == "KEY2":
            msg = rock_status()
            draw_screen([msg])
            time.sleep(2)
        else:
            draw_screen(["The rock sits there.", "Watching."])
        time.sleep(0.05)

    GPIO.cleanup()
    draw_screen(["Goodbye.", "The rock will remember."])
    time.sleep(1)

if __name__ == "__main__":
    main()
