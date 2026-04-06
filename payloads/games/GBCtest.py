# #!/usr/bin/env python3
“””
KTOX GBC Injector — Fixed Single-File Payload

Drop into:  /root/KTOx/payloads/games/GBCtest.py

Fixes vs original:

- Correct import path for LCD_1in44 / LCD_Config (ktox_pi/ folder)
- PyBoy install check with on-screen error if missing
- GPIO fully set up before any pin is read
- All errors shown on LCD, not just printed to console
- Flask web uploader runs in background so you can push ROMs over WiFi
- KEY3 exits the game, KEY3 on empty menu exits the payload cleanly

Hardware: ST7735S 128x128 SPI LCD (LCD_1in44)
Buttons (BCM GPIO, active-LOW, pull-up):
UP=6  DOWN=19  LEFT=5  RIGHT=26
OK=13 KEY1=21  KEY2=20  KEY3=16

Install PyBoy once on the Pi (run as root):
pip3 install pyboy
“””

import os
import sys
import time
import threading

# ── 1. Fix import path so LCD_1in44 / LCD_Config are always found ─────────────

# The drivers live in /root/KTOx/ktox_pi/ — add that to sys.path first so

# imports work no matter where this payload is launched from.

_KTOX_PI_DIR = os.path.join(os.path.dirname(**file**), “..”, “..”, “ktox_pi”)
_KTOX_PI_DIR = os.path.realpath(_KTOX_PI_DIR)
if _KTOX_PI_DIR not in sys.path:
sys.path.insert(0, _KTOX_PI_DIR)

# Also add the standard KTOx root in case other helpers are needed

_KTOX_ROOT = os.path.realpath(os.path.join(os.path.dirname(**file**), “..”, “..”))
if _KTOX_ROOT not in sys.path:
sys.path.insert(0, _KTOX_ROOT)

# ── 2. Hardware imports ────────────────────────────────────────────────────────

HAS_HW = False
lcd_module = None

try:
import RPi.GPIO as GPIO
import LCD_1in44 as _lcd_mod
lcd_module = _lcd_mod
from PIL import Image, ImageDraw, ImageFont
HAS_HW = True
except ImportError as _e:
print(f”[GBC] Hardware import failed: {_e}”)
print(”[GBC] Running in headless/debug mode — no LCD output.”)
from PIL import Image, ImageDraw, ImageFont  # still needed for fallback

# ── 3. Config ─────────────────────────────────────────────────────────────────

ROM_DIR = “/root/KTOx/roms”
os.makedirs(ROM_DIR, exist_ok=True)

PINS = {
“UP”:    6,
“DOWN”:  19,
“LEFT”:  5,
“RIGHT”: 26,
“OK”:    13,
“KEY1”:  21,
“KEY2”:  20,
“KEY3”:  16,   # Universal exit / back
}

LCD_W, LCD_H = 128, 128

# ── 4. Helpers ────────────────────────────────────────────────────────────────

def _font(size=10):
“”“Return a PIL font — falls back to default if no TTF available.”””
try:
return ImageFont.truetype(”/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf”, size)
except Exception:
return ImageFont.load_default()

def _make_error_image(title, lines):
“”“Render a red-on-black error screen as a PIL Image.”””
img = Image.new(“RGB”, (LCD_W, LCD_H), “black”)
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, LCD_W, 14), fill=”#cc0000”)
draw.text((3, 2), title[:20], fill=“white”, font=_font(9))
y = 18
for line in lines:
draw.text((3, y), str(line)[:21], fill=”#ff4444”, font=_font(8))
y += 10
if y > LCD_H - 10:
break
return img

def lcd_show(lcd, img):
“”“Push a PIL Image to the LCD (silently no-ops if no hardware).”””
if lcd is None:
return
try:
lcd.LCD_ShowImage(img, 0, 0)
except Exception as e:
print(f”[GBC] LCD_ShowImage error: {e}”)

def lcd_show_error(lcd, title, lines):
lcd_show(lcd, _make_error_image(title, lines))
time.sleep(2)

def read_button():
“””
Poll all button GPIO pins.
Returns the name of the first pressed button (active-LOW), or None.
“””
if not HAS_HW:
return None
for name, pin in PINS.items():
try:
if GPIO.input(pin) == GPIO.LOW:
return name
except Exception:
pass
return None

# ── 5. LCD initialisation ─────────────────────────────────────────────────────

def lcd_init():
if not HAS_HW:
print(”[GBC] No hardware — skipping LCD init.”)
return None
try:
lcd = lcd_module.LCD()
lcd.LCD_Init(lcd_module.SCAN_DIR_DFT)
lcd.LCD_Clear()
return lcd
except Exception as e:
print(f”[GBC] LCD init failed: {e}”)
return None

# ── 6. PyBoy availability check ───────────────────────────────────────────────

def check_pyboy(lcd):
“””
Verify PyBoy is installed. If not, show an on-screen install message
and return False so the caller can bail gracefully.
“””
try:
import pyboy  # noqa: F401
return True
except ImportError:
msg = [
“PyBoy not installed!”,
“”,
“On the Pi run:”,
“  pip3 install pyboy”,
“”,
“Then relaunch.”
]
print(”[GBC] PyBoy not found. Install with:  pip3 install pyboy”)
if lcd:
lcd_show_error(lcd, “MISSING DEP”, msg)
# Keep the message visible for 6 seconds
time.sleep(4)
return False

# ── 7. Flask web uploader (background thread) ─────────────────────────────────

def _start_web_server():
try:
from flask import Flask, request, redirect, render_template_string
app = Flask(**name**)

```
    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST" and "file" in request.files:
            f = request.files["file"]
            if f and f.filename:
                try:
                    f.save(os.path.join(ROM_DIR, f.filename))
                except Exception as e:
                    return f"<h2 style='color:red'>Upload failed: {e}</h2><a href='/'>Back</a>"
            return redirect("/")

        try:
            roms = sorted(os.listdir(ROM_DIR))
        except Exception:
            roms = []

        return render_template_string("""
```

<!DOCTYPE html>

<html>
<body style="background:#000;color:#0f0;font-family:monospace;text-align:center;padding:20px">
  <h1 style="color:#f00">KTOx // GBC ROM VAULT</h1>
  <form method="post" enctype="multipart/form-data">
    <input type="file" name="file" accept=".gb,.gbc"
           style="background:#111;color:#0f0;border:1px solid #0f0;padding:8px">
    <button type="submit"
            style="background:#f00;color:white;border:none;padding:10px 20px;margin:8px">
      INJECT ROM
    </button>
  </form>
  <hr style="border-color:#333">
  <h3>ROMs ({{ roms|length }})</h3>
  <ul style="list-style:none;padding:0;text-align:left;max-width:400px;margin:0 auto">
    {% for r in roms %}<li style="margin:4px 0">{{ r }}</li>{% endfor %}
  </ul>
  <p style="color:#666;margin-top:30px">Upload .gb / .gbc — access at PI_IP:5000</p>
</body>
</html>""", roms=roms)

```
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
except Exception as e:
    print(f"[GBC] Web server error: {e}")
```

# ── 8. ROM selector UI ────────────────────────────────────────────────────────

def rom_selector(lcd):
“””
Show a scrollable ROM list on the LCD.
Returns the full path to the selected ROM, or None to exit.
“””
cursor = 0
font_title = _font(9)
font_item  = _font(8)

```
while True:
    roms = sorted([
        f for f in os.listdir(ROM_DIR)
        if f.lower().endswith((".gb", ".gbc"))
    ])

    img  = Image.new("RGB", (LCD_W, LCD_H), "black")
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle((0, 0, LCD_W, 14), fill="#cc0000")
    draw.text((4, 2), "GBC INJECTOR", fill="white", font=font_title)

    if not roms:
        draw.text((4, 30), "NO ROMS FOUND", fill="#00ff41", font=font_item)
        draw.text((4, 44), "Upload via web:", fill="#888888", font=font_item)
        draw.text((4, 56), "PI_IP:5000", fill="white",   font=font_item)
        draw.text((4, LCD_H - 12), "KEY3=exit", fill="#555", font=font_item)
    else:
        visible = 7          # rows that fit below the header
        # Keep cursor inside list
        cursor = max(0, min(cursor, len(roms) - 1))
        start  = max(0, min(cursor - visible // 2, len(roms) - visible))
        start  = max(0, start)

        for idx in range(visible):
            rom_idx = start + idx
            if rom_idx >= len(roms):
                break
            selected = rom_idx == cursor
            prefix = ">" if selected else " "
            colour = "#00ff41" if selected else "#888888"
            label  = f"{prefix} {roms[rom_idx]}"[:20]
            draw.text((4, 18 + idx * 14), label, fill=colour, font=font_item)

        draw.text((4, LCD_H - 12),
                  "OK=play  KEY3=exit",
                  fill="#444444", font=_font(7))

    lcd_show(lcd, img)

    # Button polling with debounce
    btn = read_button()
    if btn == "DOWN":
        cursor = min(cursor + 1, max(0, len(roms) - 1))
        time.sleep(0.18)
    elif btn == "UP":
        cursor = max(cursor - 1, 0)
        time.sleep(0.18)
    elif btn == "OK" and roms:
        return os.path.join(ROM_DIR, roms[cursor])
    elif btn == "KEY3":
        return None
    else:
        time.sleep(0.05)
```

# ── 9. Game loop ──────────────────────────────────────────────────────────────

def play_game(lcd, rom_path):
“”“Load and run a ROM with PyBoy, rendering each frame to the LCD.”””
try:
from pyboy import PyBoy, WindowEvent
except ImportError:
lcd_show_error(lcd, “PyBoy missing”, [“pip3 install pyboy”])
return

```
# Show loading screen
img  = Image.new("RGB", (LCD_W, LCD_H), "black")
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, LCD_W, 14), fill="#cc0000")
draw.text((4, 2), "LOADING...", fill="white", font=_font(9))
draw.text((4, 24), os.path.basename(rom_path)[:20], fill="#00ff41", font=_font(8))
draw.text((4, 40), "Please wait", fill="#888", font=_font(8))
lcd_show(lcd, img)

try:
    pyboy = PyBoy(rom_path, window_type="dummy", sound=False)
except Exception as e:
    lcd_show_error(lcd, "ROM LOAD FAIL", [str(e)[:60]])
    return

print(f"[GBC] Loaded: {rom_path}")

# Button → WindowEvent mapping
press_map = {
    "UP":    WindowEvent.PRESS_ARROW_UP,
    "DOWN":  WindowEvent.PRESS_ARROW_DOWN,
    "LEFT":  WindowEvent.PRESS_ARROW_LEFT,
    "RIGHT": WindowEvent.PRESS_ARROW_RIGHT,
    "OK":    WindowEvent.PRESS_BUTTON_A,
    "KEY1":  WindowEvent.PRESS_BUTTON_B,
    "KEY2":  WindowEvent.PRESS_BUTTON_START,
}
release_map = {
    "UP":    WindowEvent.RELEASE_ARROW_UP,
    "DOWN":  WindowEvent.RELEASE_ARROW_DOWN,
    "LEFT":  WindowEvent.RELEASE_ARROW_LEFT,
    "RIGHT": WindowEvent.RELEASE_ARROW_RIGHT,
    "OK":    WindowEvent.RELEASE_BUTTON_A,
    "KEY1":  WindowEvent.RELEASE_BUTTON_B,
    "KEY2":  WindowEvent.RELEASE_BUTTON_START,
}

prev_pressed = set()

try:
    while True:
        if pyboy.tick():
            # PyBoy signals game-over / stop
            break

        # Read currently held buttons
        now_pressed = set()
        if HAS_HW:
            for name, pin in PINS.items():
                if name == "KEY3":
                    continue
                try:
                    if GPIO.input(pin) == GPIO.LOW:
                        now_pressed.add(name)
                except Exception:
                    pass

        # KEY3 = exit game immediately
        if HAS_HW:
            try:
                if GPIO.input(PINS["KEY3"]) == GPIO.LOW:
                    break
            except Exception:
                pass

        # Send press/release events only on state change (avoids event spam)
        newly_pressed   = now_pressed - prev_pressed
        newly_released  = prev_pressed - now_pressed

        for btn in newly_pressed:
            if btn in press_map:
                pyboy.send_input(press_map[btn])
        for btn in newly_released:
            if btn in release_map:
                pyboy.send_input(release_map[btn])

        prev_pressed = now_pressed

        # Render frame to LCD
        # PyBoy screen is 160x144 — scale to 128x128 (slight crop is fine)
        frame = pyboy.screen_image()
        frame = frame.resize((LCD_W, LCD_H), resample=Image.NEAREST)
        lcd_show(lcd, frame)

except Exception as e:
    print(f"[GBC] Runtime error: {e}")
    lcd_show_error(lcd, "RUNTIME ERR", [str(e)[:60]])

finally:
    try:
        pyboy.stop()
    except Exception:
        pass
    print("[GBC] Game exited.")
```

# ── 10. Entry point ───────────────────────────────────────────────────────────

def main():
# GPIO setup — do this BEFORE lcd_init so pins are ready
if HAS_HW:
try:
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for pin in PINS.values():
GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
except Exception as e:
print(f”[GBC] GPIO setup failed: {e}”)

```
lcd = lcd_init()

# Check PyBoy before going any further
if not check_pyboy(lcd):
    return  # Error already shown on screen

# Start ROM uploader web server in the background
web_thread = threading.Thread(target=_start_web_server, daemon=True)
web_thread.start()
print("[GBC] Web ROM uploader running on port 5000")

# Main loop: pick a ROM, play it, repeat
while True:
    rom = rom_selector(lcd)
    if rom is None:
        break                 # KEY3 on selector = exit payload
    play_game(lcd, rom)

# Clean up
if lcd:
    try:
        lcd.LCD_Clear()
    except Exception:
        pass
if HAS_HW:
    try:
        GPIO.cleanup()
    except Exception:
        pass

print("[GBC] KTOx GBC Injector exited.")
```

if **name** == “**main**”:
try:
main()
except KeyboardInterrupt:
pass
finally:
if HAS_HW:
try:
GPIO.cleanup()
except Exception:
pass
