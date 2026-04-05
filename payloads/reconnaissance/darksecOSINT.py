#!/usr/bin/env python3
"""
KTOx_Pi OSINT
==============================================================
Fully on-device with on-screen keyboard + Sherlock username hunting
"""

import os
import sys
import time
import subprocess
import requests
import urllib.parse
from urllib.request import urlopen, Request

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not detected - debug mode")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ── Constants ────────────────────────────────────────────────────────────────
W, H = 128, 128
CHAR_SET = "abcdefghijklmnopqrstuvwxyz0123456789.-_@/"
PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}

# ── Globals ──────────────────────────────────────────────────────────────────
LCD = None
_image = None
_draw = None
_font_sm = None
_font_md = None

RUNNING = True
_menu_idx = 0

MENU = [
    "1. My IP Info",
    "2. WHOIS Lookup",
    "3. DNS Lookup",
    "4. Web Page Title",
    "5. Username Check (basic)",
    "6. Email Breach Check",
    "7. Subdomain Enum",
    "8. Basic Port Scan",
    "9. Google Dork Ideas",
    "10. Reverse IP",
    "11. Geo from IP",
    "12. Sherlock Hunt",
    "13. Exit"
]

# ── Hardware Init ────────────────────────────────────────────────────────────
def init_hw():
    global LCD, _image, _draw, _font_sm, _font_md
    if not HAS_HW:
        return False
    try:
        GPIO.setmode(GPIO.BCM)
        for p in PINS.values():
            GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        LCD = LCD_1in44.LCD()
        LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        LCD.LCD_Clear()

        _image = Image.new("RGB", (W, H), "black")
        _draw = ImageDraw.Draw(_image)

        for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                     "/usr/share/fonts/truetype/freefont/FreeMono.ttf"]:
            try:
                _font_sm = ImageFont.truetype(path, 9)
                _font_md = ImageFont.truetype(path, 11)
                break
            except:
                pass
        if not _font_sm:
            _font_sm = ImageFont.load_default()
            _font_md = _font_sm
        return True
    except Exception as e:
        print(f"HW error: {e}")
        return False

def push():
    if LCD and _image:
        LCD.LCD_ShowImage(_image, 0, 0)

# ── Drawing ──────────────────────────────────────────────────────────────────
def draw_menu():
    _draw.rectangle((0,0,W,H), fill="black")
    _draw.rectangle((0,0,W,15), fill=(0,40,80))
    _draw.text((3,2), "KTOx OSINT", font=_font_sm, fill="cyan")

    y = 18
    for i, item in enumerate(MENU):
        color = (255,255,100) if i == _menu_idx else "white"
        _draw.text((3, y), item[:20], font=_font_sm, fill=color)
        y += 11

    _draw.rectangle((0,H-11,W,H), fill=(30,30,30))
    _draw.text((3,H-10), "UP/DN  K1=select", font=_font_sm, fill=(150,150,150))
    push()

def draw_result(lines, title="Result"):
    _draw.rectangle((0,0,W,H), fill="black")
    _draw.rectangle((0,0,W,15), fill=(0,40,80))
    _draw.text((3,2), title[:20], font=_font_sm, fill="cyan")

    y = 18
    for line in lines[:9]:
        _draw.text((3, y), line[:20], font=_font_sm, fill="white")
        y += 11

    _draw.rectangle((0,H-11,W,H), fill=(30,30,30))
    _draw.text((3,H-10), "K3=Back", font=_font_sm, fill=(150,150,150))
    push()

# ── On-Screen Keyboard ───────────────────────────────────────────────────────
def on_screen_keyboard(prompt="Enter:"):
    input_text = ""
    char_idx = 0
    while RUNNING:
        _draw.rectangle((0,0,W,H), fill="black")
        _draw.rectangle((0,0,W,16), fill=(0,60,0))
        _draw.text((3,2), prompt[:20], font=_font_sm, fill="lime")

        shown = input_text[-18:] if len(input_text) > 18 else input_text
        _draw.rectangle((0,18,W,34), fill=(25,25,25))
        _draw.text((3,20), "> " + shown, font=_font_sm, fill="white")

        cs = CHAR_SET
        prev = cs[(char_idx-1)%len(cs)]
        curr = cs[char_idx]
        nxt = cs[(char_idx+1)%len(cs)]
        _draw.text((10,45), f"< {prev} ", font=_font_md, fill=(100,100,100))
        _draw.rectangle((55,42,80,60), fill=(0,80,140))
        _draw.text((60,44), curr, font=_font_md, fill="yellow")
        _draw.text((85,45), f" {nxt} >", font=_font_md, fill=(100,100,100))

        hints = ["U/D=char OK=add", "L=del R=. K1=/", "K2=GO K3=Cancel"]
        y = 70
        for h in hints:
            _draw.text((3,y), h, font=_font_sm, fill=(170,170,170))
            y += 11
        push()

        btn = None
        t0 = time.time()
        while not btn and RUNNING and time.time()-t0 < 60:
            for name, pin in PINS.items():
                if GPIO.input(pin) == 0:
                    btn = name
                    break
            time.sleep(0.04)

        if not btn or not RUNNING: return ""
        if btn == "KEY3": return ""
        if btn == "KEY2": return input_text.strip()
        if btn == "OK": input_text += CHAR_SET[char_idx]
        elif btn == "LEFT": input_text = input_text[:-1]
        elif btn == "RIGHT": input_text += "."
        elif btn == "KEY1": input_text += "/"
        elif btn == "UP": char_idx = (char_idx - 1 + len(CHAR_SET)) % len(CHAR_SET)
        elif btn == "DOWN": char_idx = (char_idx + 1) % len(CHAR_SET)
        time.sleep(0.1)
    return ""

# ── OSINT Tools (Sherlock added) ─────────────────────────────────────────────
def my_ip_info():
    try:
        pub = requests.get("https://api.ipify.org", timeout=8).text.strip()
        loc = subprocess.getoutput("hostname -I").strip().split()[0] or "N/A"
        return [f"Pub: {pub}", f"Loc: {loc}"]
    except:
        return ["IP fetch failed"]

def whois_lookup():
    target = on_screen_keyboard("Domain/IP:")
    if not target: return ["Cancelled"]
    try:
        out = subprocess.getoutput(f"whois {target} | head -15")
        return [line.strip()[:20] for line in out.splitlines() if line.strip()]
    except:
        return ["WHOIS error"]

def dns_lookup():
    target = on_screen_keyboard("Domain:")
    if not target: return ["Cancelled"]
    try:
        out = subprocess.getoutput(f"dig +short {target} | head -8")
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines or ["No records"]
    except:
        return ["DNS error"]

def web_page_title():
    url = on_screen_keyboard("URL:")
    if not url: return ["Cancelled"]
    if not url.startswith("http"): url = "https://" + url
    try:
        req = Request(url, headers={"User-Agent": "KTOx-OSINT/1.0"})
        with urlopen(req, timeout=10) as r:
            data = r.read(100000)
        if HAS_BS4:
            soup = BeautifulSoup(data, 'lxml')
            title = soup.title.get_text(strip=True) if soup.title else "No title"
            return [title[:20], "OK"]
        return ["Title fetched"]
    except Exception as e:
        return [f"Err: {str(e)[:15]}"]

def username_check_basic():
    user = on_screen_keyboard("Username:")
    if not user: return ["Cancelled"]
    sites = ["github", "twitter", "reddit"]
    res = []
    for s in sites:
        try:
            r = requests.get(f"https://{s}.com/{user}", timeout=6, allow_redirects=True)
            status = "Found" if r.status_code in (200, 301, 302) else "Not found"
            res.append(f"{s}: {status}")
        except:
            res.append(f"{s}: ?")
    return res

def email_breach_check():
    email = on_screen_keyboard("Email:")
    if not email: return ["Cancelled"]
    try:
        r = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(email)}",
                         headers={"User-Agent": "KTOx-OSINT"}, timeout=10)
        if r.status_code == 200:
            return ["Breached!", "See terminal"]
        return ["No known breaches"]
    except:
        return ["Breach check failed"]

def subdomain_enum():
    domain = on_screen_keyboard("Domain:")
    if not domain: return ["Cancelled"]
    try:
        r = requests.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=12)
        data = r.json()[:12]
        subs = list(set([entry['name_value'].split('\n')[0] for entry in data]))
        return [s[:20] for s in subs[:8]] or ["None found"]
    except:
        return ["crt.sh failed"]

def basic_port_scan():
    target = on_screen_keyboard("IP/Domain:")
    if not target: return ["Cancelled"]
    try:
        out = subprocess.getoutput(f"nmap -F -T4 {target} 2>/dev/null | grep open | head -5")
        lines = [line.strip()[:20] for line in out.splitlines() if line.strip()]
        return lines or ["No open ports found"]
    except:
        return ["Port scan error"]

def google_dork_ideas():
    return [
        "site:target.com filetype:pdf",
        "inurl:admin login",
        "intitle:index.of",
        "intext:password filetype:txt",
        "Use legally only"
    ]

def reverse_ip_lookup():
    ip = on_screen_keyboard("IP:")
    if not ip: return ["Cancelled"]
    try:
        r = requests.get(f"http://api.hackertarget.com/reverseiplookup/?q={ip}", timeout=8)
        lines = r.text.strip().splitlines()[:8]
        return lines or ["No domains"]
    except:
        return ["Reverse IP failed"]

def geo_from_ip():
    ip = on_screen_keyboard("IP:")
    if not ip: return ["Cancelled"]
    try:
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=8)
        data = r.json()
        return [
            f"City: {data.get('city','?')}",
            f"Country: {data.get('country_name','?')}"
        ]
    except:
        return ["Geo failed"]

def sherlock_hunt():
    username = on_screen_keyboard("Username:")
    if not username:
        return ["Cancelled"]

    draw_result(["Running Sherlock...", "This can take 30-90s"], "Sherlock")

    try:
        # Run Sherlock with timeout and limit output for the small screen
        cmd = ["sherlock", username, "--timeout", "20", "--print-found"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        output = result.stdout.strip()
        if output:
            lines = [line.strip()[:20] for line in output.splitlines() if line.strip() and "http" in line]
            return lines[:8] or ["Found profiles (see terminal)"]
        else:
            return ["No profiles found", "or timeout"]
    except subprocess.TimeoutExpired:
        return ["Sherlock timed out"]
    except FileNotFoundError:
        return ["Sherlock not found", "Run: sudo apt install sherlock"]
    except Exception as e:
        return [f"Error: {str(e)[:15]}"]

# ── Main Loop ────────────────────────────────────────────────────────────────
def main():
    global RUNNING, _menu_idx
    hw_ok = init_hw()
    draw_menu()

    held = {}
    while RUNNING:
        pressed = {name: GPIO.input(pin) == 0 for name, pin in PINS.items()}
        now = time.time()
        for n, down in pressed.items():
            if down and n not in held:
                held[n] = now
            elif not down:
                held.pop(n, None)

        def just_pressed(n):
            return pressed.get(n) and (now - held.get(n, 0)) < 0.2

        if just_pressed("KEY3"):
            break

        if just_pressed("KEY1"):
            item = MENU[_menu_idx]
            draw_result(["Running..."], item)

            if "My IP" in item:           lines = my_ip_info()
            elif "WHOIS" in item:         lines = whois_lookup()
            elif "DNS" in item:           lines = dns_lookup()
            elif "Web Page" in item:      lines = web_page_title()
            elif "basic" in item:         lines = username_check_basic()
            elif "Email Breach" in item:  lines = email_breach_check()
            elif "Subdomain" in item:     lines = subdomain_enum()
            elif "Port Scan" in item:     lines = basic_port_scan()
            elif "Google Dork" in item:   lines = google_dork_ideas()
            elif "Reverse IP" in item:    lines = reverse_ip_lookup()
            elif "Geo from IP" in item:   lines = geo_from_ip()
            elif "Sherlock" in item:      lines = sherlock_hunt()
            else:                         lines = ["Done"]

            draw_result(lines, item)
            time.sleep(6)
            draw_menu()

        elif just_pressed("UP"):
            _menu_idx = (_menu_idx - 1) % len(MENU)
            draw_menu()
            time.sleep(0.15)

        elif just_pressed("DOWN"):
            _menu_idx = (_menu_idx + 1) % len(MENU)
            draw_menu()
            time.sleep(0.15)

        time.sleep(0.05)

    RUNNING = False
    if HAS_HW:
        try:
            LCD.LCD_Clear()
            GPIO.cleanup()
        except:
            pass
    print("KTOx OSINT exited.")

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