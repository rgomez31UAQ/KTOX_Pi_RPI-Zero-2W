#!/usr/bin/env python3
"""
KTOX Operator - Professional Social Engineering Assistant
========================================================
Live elicitation coach, timer, and profiling tool
"""

import os
import time
import random

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False

# ── Hardware ─────────────────────────────────────────────────────────────────
LCD = None
_image = None
_draw = None
_font_sm = None

RUNNING = True
interaction_timer = 0
rapport_meter = 0
victim_notes = []
current_tip_idx = 0

# Professional elicitation & influence techniques
TECHNIQUES = [
    "Use their first name naturally",
    "Ask 'how' or 'tell me about' questions",
    "Offer a small piece of information first",
    "Rationalize the request ('everyone does this')",
    "Build sympathy ('that must be tough')",
    "Create mild scarcity ('we need to move fast')",
    "Assume knowledge ('when you handled the last one...')",
    "Silence after asking — let them fill it"
]

def init_hw():
    global LCD, _image, _draw, _font_sm
    if not HAS_HW:
        return False
    try:
        GPIO.setmode(GPIO.BCM)
        for p in [6,19,5,26,13,21,20,16]:
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        LCD = LCD_1in44.LCD()
        LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        LCD.LCD_Clear()

        _image = Image.new("RGB", (128, 128), "black")
        _draw = ImageDraw.Draw(_image)
        try:
            _font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        except:
            _font_sm = ImageFont.load_default()
        return True
    except:
        return False

def push():
    if LCD and _image:
        LCD.LCD_ShowImage(_image, 0, 0)

# ── Dark Red Professional UI ─────────────────────────────────────────────────
def draw_operator():
    _draw.rectangle((0,0,128,128), fill="#0A0000")
    _draw.rectangle((0,0,128,17), fill="#8B0000")
    _draw.text((4,3), "KTOX OPERATOR", font=_font_sm, fill="#FF3333")

    # Timer
    _draw.text((5,22), f"Time: {interaction_timer}s", font=_font_sm, fill="#FFBBBB")

    # Rapport meter
    meter = min(118, int(rapport_meter * 1.18))
    _draw.rectangle((5, 35, 5 + meter, 42), fill="#FF5555")

    # Current tip
    tip = TECHNIQUES[current_tip_idx]
    _draw.text((5,50), tip[:20], font=_font_sm, fill="#FF6666")

    # Notes
    y = 65
    for note in victim_notes[-3:]:
        _draw.text((5, y), note[:20], font=_font_sm, fill="#FFAAAA")
        y += 11

    _draw.rectangle((0,117,128,128), fill="#220000")
    _draw.text((4,118), "K1=Next Tip  K2=Note  K3=Exit", font=_font_sm, fill="#FF7777")
    push()

# ── Main Loop ────────────────────────────────────────────────────────────────
def main():
    global RUNNING, interaction_timer, rapport_meter, current_tip_idx
    hw_ok = init_hw()
    draw_operator()

    start_time = time.time()
    held = {}

    while RUNNING:
        pressed = {name: GPIO.input(pin) == 0 for name, pin in {"KEY1":21, "KEY2":20, "KEY3":16}.items()}
        now = time.time()
        for n, down in pressed.items():
            if down and n not in held:
                held[n] = now
            elif not down:
                held.pop(n, None)

        interaction_timer = int(now - start_time)

        if pressed.get("KEY3") and (now - held.get("KEY3", 0)) < 0.3:
            break

        if pressed.get("KEY1") and (now - held.get("KEY1", 0)) < 0.3:
            current_tip_idx = (current_tip_idx + 1) % len(TECHNIQUES)
            rapport_meter = min(100, rapport_meter + 8)
            draw_operator()
            time.sleep(0.3)

        if pressed.get("KEY2") and (now - held.get("KEY2", 0)) < 0.3:
            # Add quick note (expand with full keyboard later if needed)
            note = f"Note {len(victim_notes)+1}"
            victim_notes.append(note)
            rapport_meter = min(100, rapport_meter + 5)
            draw_operator()
            time.sleep(0.3)

        draw_operator()
        time.sleep(0.8)

    RUNNING = False
    if HAS_HW:
        try:
            LCD.LCD_Clear()
            GPIO.cleanup()
        except:
            pass
    print("KTOX Operator closed.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        if HAS_HW:
            try:
                GPIO.cleanup()
            except:
                pass