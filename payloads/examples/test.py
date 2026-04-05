#!/usr/bin/env python3
"""
KTOX Shadow – Cyberpunk Animated Core
======================================
Animated red-team payload with live credential capture
- Cyberpunk floating core with face
- Pulsing + rotating rings + bobbing animation
- Idle / attack / alert states
- Live scrolling credentials
"""

import os, time, threading, random, math

# ── Hardware detection ───────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not detected")

# ── Constants ────────────────────────────────────────────────────────────────
W, H = 128, 128
PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}
ORB_RADIUS = 10
RING_COUNT = 3

# ── Globals ──────────────────────────────────────────────────────────────────
LCD = None
_draw = None
_image = None
_font_sm = None

RUNNING = True
shadow_running = False
ghost_frame = 0
ghost_state = "idle"
captured_creds = []  # last credentials captured

# ── Hardware init ───────────────────────────────────────────────────────────
def init_hw():
    global LCD, _image, _draw, _font_sm
    if not HAS_HW:
        return False
    try:
        GPIO.setmode(GPIO.BCM)
        for p in PINS.values():
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        LCD = LCD_1in44.LCD()
        LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        LCD.LCD_Clear()
        _image = Image.new("RGB", (W,H), "black")
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

# ── Cyberpunk Orb + Face ────────────────────────────────────────────────────
FACE = {"eyes": [(5,6),(12,6)], "mouth": (8,12)}

CORE_COLORS = {"idle":"#00AAFF","attack":"#FF3333","alert":"#FFFF00"}

def draw_cyberpunk_core(x, y):
    global ghost_frame
    state_color = CORE_COLORS.get(ghost_state,"#00AAFF")
    bob = int(math.sin(ghost_frame/5)*3)
    pulse = 1 + abs(math.sin(ghost_frame/3)*3)

    # Main orb
    _draw.ellipse(
        (x-ORB_RADIUS-pulse, y-ORB_RADIUS+bob-pulse,
         x+ORB_RADIUS+pulse, y+ORB_RADIUS+bob+pulse),
        fill=state_color
    )

    # Rotating rings
    for i in range(1,RING_COUNT+1):
        ring_radius = ORB_RADIUS*0.3*i + (ghost_frame%3)
        angle_offset = ghost_frame*(i*5)
        for angle in range(0,360,45):
            rad = math.radians(angle+angle_offset)
            sx = x + int(ring_radius*math.cos(rad))
            sy = y + int(ring_radius*math.sin(rad)) + bob
            _draw.rectangle((sx,sy,sx+1,sy+1), fill="#00FFAA")

    # Flicker overlay for attack/alert
    if ghost_state in ["attack","alert"] and ghost_frame%3==0:
        for _ in range(4):
            fx = x + random.randint(-ORB_RADIUS, ORB_RADIUS)
            fy = y + random.randint(-ORB_RADIUS, ORB_RADIUS) + bob
            _draw.rectangle((fx,fy,fx+1,fy+1), fill="#FFFFFF")

    draw_face(x, y+bob)
    ghost_frame += 1

def draw_face(x, y):
    # Eyes
    if ghost_state=="attack":
        eye_style="angry"
        color="#FF3333"
    elif ghost_state=="alert":
        eye_style="wide"
        color="#FFFF00"
    else:
        eye_style="blink" if ghost_frame%20>15 else "normal"
        color="#00AAFF"

    for ex, ey in FACE["eyes"]:
        if eye_style=="blink":
            _draw.line((x+ex,y+ey,x+ex+2,y+ey), fill=color)
        elif eye_style=="angry":
            _draw.line((x+ex,y+ey,x+ex+2,y+ey-1), fill=color)
        elif eye_style=="wide":
            _draw.rectangle((x+ex,y+ey,x+ex+2,y+ey+2), fill=color)
        else:
            _draw.rectangle((x+ex,y+ey,x+ex+1,y+ey+1), fill=color)

    # Mouth
    mx,my = FACE["mouth"]
    if ghost_state=="attack":
        _draw.rectangle((x+mx,y+my,x+mx+3,y+my+1), fill="#FF3333")
    elif ghost_state=="alert":
        _draw.line((x+mx,y+my,x+mx+3,y+my), fill="#FFFF00")
    else:
        _draw.line((x+mx,y+my,x+mx+2,y+my), fill="#00AAFF")

# ── Shadow Screen ──────────────────────────────────────────────────────────
def draw_shadow_screen():
    global _draw
    _draw.rectangle((0,0,W,H), fill="#0A0000")
    _draw.rectangle((0,0,W,18), fill="#8B0000")
    _draw.text((4,3),"KTOX SHADOW", font=_font_sm, fill="#FF3333")

    status = "CAPTURING" if shadow_running else "IDLE"
    color = "#00FF88" if shadow_running else "#FF6666"
    _draw.text((5,22),status,font=_font_sm,fill=color)

    # Credentials
    y=36
    for cred in captured_creds[-5:]:
        _draw.text((5,y),cred[:20],font=_font_sm,fill="#FF5555")
        y+=11

    # Orb mascot
    draw_cyberpunk_core(64,100)

    _draw.rectangle((0,117,W,128), fill="#220000")
    _draw.text((4,118),"K1=Toggle  K3=Exit", font=_font_sm, fill="#FF7777")
    push()

# ── Background Credential Capture ──────────────────────────────────────────
def capture_thread():
    global captured_creds
    fake_creds = ["admin:password123","user@gmail.com:letmein","banklogin:Secret2026","root:toor","victim:123456"]
    while shadow_running and RUNNING:
        if random.random()<0.4:
            cred=random.choice(fake_creds)
            if cred not in captured_creds:
                captured_creds.append(cred)
                if len(captured_creds)>15:
                    captured_creds.pop(0)
        time.sleep(1.5)

# ── Control ────────────────────────────────────────────────────────────────
def start_shadow():
    global shadow_running, ghost_state
    shadow_running=True
    ghost_state="idle"
    threading.Thread(target=capture_thread,daemon=True).start()
    draw_shadow_screen()

def stop_shadow():
    global shadow_running, ghost_state
    shadow_running=False
    ghost_state="idle"
    draw_shadow_screen()

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    global RUNNING
    hw_ok=init_hw()
    draw_shadow_screen()

    held = {}
    while RUNNING:
        pressed = {name: GPIO.input(pin)==0 for name,pin in PINS.items()} if HAS_HW else {}
        now = time.time()
        for n, down in pressed.items():
            if down and n not in held:
                held[n]=now
            elif not down:
                held.pop(n,None)

        def just_pressed(n):
            return pressed.get(n) and (now-held.get(n,0))<0.2

        if just_pressed("KEY3"):
            break

        if just_pressed("KEY1"):
            if shadow_running:
                stop_shadow()
            else:
                start_shadow()
            time.sleep(0.4)

        # Optional state simulation (random attack/alert)
        if shadow_running:
            ghost_state = random.choices(["idle","attack","alert"], [0.7,0.2,0.1])[0]
            draw_shadow_screen()
        time.sleep(0.2)

    RUNNING=False
    stop_shadow()
    if HAS_HW:
        try:
            LCD.LCD_Clear()
            GPIO.cleanup()
        except:
            pass
    print("KTOX Shadow payload exited.")

if __name__=="__main__":
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
