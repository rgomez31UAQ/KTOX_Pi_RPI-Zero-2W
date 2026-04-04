#!/usr/bin/env python3
"""
KTOx Payload – Reliable Tiny Web Browser (Lightweight Fixed Version)
===================================================================
- Uses only system-friendly dependencies (beautifulsoup4 + lxml via apt)
- Strong URL normalization to fix "no host given" error
- Better error handling and fallbacks
- Clean text extraction with title support
"""

import os
import sys
import re
import time
import threading
import textwrap
import urllib.request
import urllib.parse
import urllib.error
from urllib.request import Request

KTOX_ROOT = "/root/KTOx"
if os.path.isdir(KTOX_ROOT) and KTOX_ROOT not in sys.path:
    sys.path.insert(0, KTOX_ROOT)

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("No hardware support detected.")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("Warning: BeautifulSoup4 not available — very basic parsing only.")

# ── Constants ────────────────────────────────────────────────────────────────
W, H = 128, 128
WEBUI_URL_FILE = "/dev/shm/ktox_browser_url.txt"
MAX_HISTORY = 15
CHAR_SET = "abcdefghijklmnopqrstuvwxyz0123456789./:_-?=&#@%+"
MAX_CONTENT_SIZE = 512 * 1024

PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26, "OK": 13,
    "KEY1": 21, "KEY2": 20, "KEY3": 16,
}

# ── Globals ──────────────────────────────────────────────────────────────────
LCD = None
_image = None
_draw = None
_font_sm = None
_font_md = None
_font_hd = None

RUNNING = True
_ui_lock = threading.Lock()

_page_lines   = ["Welcome to KTOx Browser", "", "Press KEY1 for URL"]
_page_links   = []
_link_idx     = 0
_scroll       = 0
_current_url  = ""
_history      = []
_status_msg   = "ready"
_fetching     = False
_page_title   = ""

_LINES_PER_PAGE = 9


# ── Hardware Init ────────────────────────────────────────────────────────────
def _init_hw():
    global LCD, _image, _draw, _font_sm, _font_md, _font_hd
    if not HAS_HW:
        return
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD.LCD_Clear()

    _image = Image.new("RGB", (W, H), "black")
    _draw = ImageDraw.Draw(_image)

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ]
    def _load(size):
        for p in font_paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    _font_sm = _load(9)
    _font_md = _load(11)
    _font_hd = _load(12)


# ── Robust Fetch with Strong URL Fix ─────────────────────────────────────────
def _robust_fetch(url, retries=3):
    url = (url or "").strip()
    if not url:
        url = "https://example.com"

    # Fix "no host given" — force proper scheme
    if not re.match(r'^https?://', url, re.IGNORECASE):
        if url.startswith('www.'):
            url = "https://" + url
        else:
            url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KTOxBrowser/1.4; RaspberryPi)",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }

    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read(MAX_CONTENT_SIZE)
                content_type = resp.headers.get("Content-Type", "").lower()
                charset = "utf-8"
                m = re.search(r'charset=([^\s;"]+)', content_type)
                if m:
                    charset = m.group(1).strip('"\'')
                return raw.decode(charset, errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.2 * (attempt + 1))


# ── Content Extraction (Lightweight + BS4) ───────────────────────────────────
def _extract_content(raw_html, base_url):
    global _page_title
    if not raw_html or not HAS_BS4:
        return _simple_wrap(raw_html or "No content"), []

    try:
        soup = BeautifulSoup(raw_html, 'lxml')

        # Title
        title_tag = soup.find('title')
        _page_title = (title_tag.get_text(strip=True) if title_tag else "")[:32]

        # Remove junk
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = _simple_wrap(text)

        # Links
        links = []
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True)
            if txt and len(txt) > 2:
                href = urllib.parse.urljoin(base_url, a['href'])
                links.append((txt[:22], href))

        return lines, links
    except Exception:
        return _simple_wrap(raw_html), []


def _simple_wrap(text, width=20):
    lines = []
    for line in text.splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            lines.extend(textwrap.wrap(line, width=width) or [line])
        else:
            lines.append("")
    out = "\n".join(lines)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.splitlines()


# ── Fetch Worker ─────────────────────────────────────────────────────────────
def _fetch(url):
    global _page_lines, _page_links, _scroll, _link_idx, _status_msg, _fetching, _page_title, _current_url

    with _ui_lock:
        _fetching = True
        _status_msg = "loading..."
        _page_lines = ["Connecting...", (url or "")[:25]]
        _page_links = []
        _scroll = 0
        _link_idx = 0
        _page_title = ""

    try:
        raw_html = _robust_fetch(url)
        lines, links = _extract_content(raw_html, url)

        if not lines:
            lines = ["(no readable content)"]

        if links:
            lines += ["", "── Links ──"]
            for i, (txt, _) in enumerate(links):
                lines.append(f"[{i+1}] {txt}")

        with _ui_lock:
            _page_lines = lines
            _page_links = links
            _scroll = 0
            _link_idx = 0
            _status_msg = f"OK {len(lines)}L {len(links)}lk"
            _current_url = url

    except Exception as e:
        err = str(e)[:30]
        if "no host" in err.lower() or "empty" in err.lower():
            err = "Invalid URL"
        with _ui_lock:
            _page_lines = ["Load failed", err]
            _status_msg = "Error"
    finally:
        with _ui_lock:
            _fetching = False


def navigate(url):
    global _history, _current_url
    url = (url or "").strip()
    if not url:
        return
    if _current_url and _current_url != url:
        _history.append(_current_url)
        if len(_history) > MAX_HISTORY:
            _history.pop(0)
    _current_url = url
    threading.Thread(target=_fetch, args=(url,), daemon=True).start()


def go_back():
    if _history:
        url = _history.pop()
        navigate(url)


# ── Drawing Functions (unchanged core) ───────────────────────────────────────
def _draw_browser():
    _draw.rectangle([(0, 0), (W, H)], fill="black")
    _draw.rectangle([(0, 0), (W, 17)], fill=(0, 40, 90))

    title = (_page_title or _current_url or "KTOx Browser")[-20:]
    _draw.text((2, 2), title, font=_font_sm, fill="cyan")

    st = _status_msg[:12]
    _draw.text((W - len(st)*6 - 3, 2), st, font=_font_sm, fill=(180, 180, 180))

    y = 20
    with _ui_lock:
        lines = _page_lines[:]
        scroll = _scroll
        fetching = _fetching

    if fetching:
        _draw.text((10, 45), "Fetching...", font=_font_md, fill="yellow")
    else:
        for i in range(_LINES_PER_PAGE):
            idx = scroll + i
            if idx >= len(lines):
                break
            txt = lines[idx][:20]
            color = (100, 220, 255) if txt.startswith("[") and "]" in txt else "white"
            _draw.text((2, y), txt, font=_font_sm, fill=color)
            y += 11

    # Scrollbar
    total = max(1, len(lines))
    if total > _LINES_PER_PAGE:
        sb_h = H - 20
        bar_h = max(3, int(sb_h * _LINES_PER_PAGE / total))
        bar_y = 18 + int(sb_h * scroll / total)
        _draw.rectangle([(125, 18), (127, H-1)], fill=(40, 40, 40))
        _draw.rectangle([(125, bar_y), (127, min(bar_y + bar_h, H-1))], fill=(0, 160, 255))

    _draw.rectangle([(0, H-11), (W, H)], fill=(25, 25, 25))
    _draw.text((2, H-10), "K1=URL K2=Link K3=Exit", font=_font_sm, fill=(140, 140, 140))


def _draw_url_input(input_text, char_idx):
    _draw.rectangle([(0, 0), (W, H)], fill="black")
    _draw.rectangle([(0, 0), (W, 15)], fill=(0, 70, 0))
    _draw.text((3, 2), "Enter URL", font=_font_sm, fill="lime")

    shown = (input_text or "")[-19:]
    _draw.rectangle([(0, 17), (W, 32)], fill=(30, 30, 30))
    _draw.text((2, 19), "> " + shown, font=_font_sm, fill="white")

    cs = CHAR_SET
    ci = char_idx
    prev_c = cs[(ci - 1) % len(cs)]
    curr_c = cs[ci]
    next_c = cs[(ci + 1) % len(cs)]

    _draw.text((8, 42), f"< {prev_c} ", font=_font_md, fill=(110, 110, 110))
    _draw.rectangle([(50, 38), (78, 56)], fill=(0, 90, 160))
    _draw.text((56, 40), curr_c, font=_font_hd, fill="yellow")
    _draw.text((82, 42), f" {next_c} >", font=_font_md, fill=(110, 110, 110))

    hints = ["U/D=char  OK=add", "L=del  R=.  K1=/", "K2=GO  K3=Cancel"]
    y = 65
    for h in hints:
        _draw.text((2, y), h, font=_font_sm, fill=(170, 170, 170))
        y += 11


def _push():
    if LCD and _image:
        LCD.LCD_ShowImage(_image, 0, 0)


# ── URL Input Screen ─────────────────────────────────────────────────────────
def _url_input_screen(initial=""):
    input_text = initial
    char_idx = 0
    while RUNNING:
        _draw_url_input(input_text, char_idx)
        _push()

        btn = None
        t0 = time.time()
        while not btn and RUNNING:
            for name, pin in PINS.items():
                if GPIO.input(pin) == 0:
                    btn = name
                    break
            if time.time() - t0 > 90:
                return ""
            time.sleep(0.05)

        if btn == "KEY3":
            return ""
        if btn == "KEY2":
            cleaned = input_text.strip()
            return cleaned if cleaned else ""
        if btn == "OK":
            input_text += CHAR_SET[char_idx]
        elif btn == "LEFT":
            input_text = input_text[:-1] if input_text else ""
        elif btn == "RIGHT":
            input_text += "."
        elif btn == "KEY1":
            input_text += "/"
        elif btn == "UP":
            char_idx = (char_idx - 1 + len(CHAR_SET)) % len(CHAR_SET)
        elif btn == "DOWN":
            char_idx = (char_idx + 1) % len(CHAR_SET)

        time.sleep(0.1)
    return ""


# ── WebUI Watcher ────────────────────────────────────────────────────────────
def _webui_watcher():
    last_url = ""
    while RUNNING:
        try:
            if os.path.exists(WEBUI_URL_FILE):
                with open(WEBUI_URL_FILE) as f:
                    url = f.read().strip()
                if url and url != last_url:
                    last_url = url
                    navigate(url)
        except Exception:
            pass
        time.sleep(0.7)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    global RUNNING, _scroll, _link_idx

    _init_hw()
    if not HAS_HW:
        print("No hardware — exiting.")
        return

    try:
        os.remove(WEBUI_URL_FILE)
    except OSError:
        pass

    watcher = threading.Thread(target=_webui_watcher, daemon=True)
    watcher.start()

    # Safe default start
    if not _current_url:
        navigate("https://example.com")

    _draw_browser()
    _push()

    held = {}

    try:
        while RUNNING:
            _draw_browser()
            _push()

            pressed = {name: GPIO.input(pin) == 0 for name, pin in PINS.items()}
            now = time.time()

            for name, is_down in pressed.items():
                if is_down and name not in held:
                    held[name] = now
                elif not is_down:
                    held.pop(name, None)

            def just_pressed(name):
                return pressed.get(name) and held.get(name, now) >= now - 0.1

            if just_pressed("KEY3"):
                break

            if just_pressed("KEY1"):
                url = _url_input_screen(_current_url)
                if url:
                    navigate(url)
                time.sleep(0.2)
                continue

            if just_pressed("LEFT"):
                go_back()
                time.sleep(0.25)
                continue

            if just_pressed("UP"):
                with _ui_lock:
                    _scroll = max(0, _scroll - 1)
                time.sleep(0.07)
                continue

            if just_pressed("DOWN"):
                with _ui_lock:
                    max_s = max(0, len(_page_lines) - _LINES_PER_PAGE)
                    _scroll = min(max_s, _scroll + 1)
                time.sleep(0.07)
                continue

            if just_pressed("KEY2"):
                with _ui_lock:
                    if _page_links:
                        _link_idx = (_link_idx + 1) % len(_page_links)
                        base = len(_page_lines) - len(_page_links) - 2
                        target = base + _link_idx + 2
                        _scroll = max(0, target - _LINES_PER_PAGE // 2)
                time.sleep(0.15)
                continue

            if just_pressed("OK"):
                with _ui_lock:
                    if _page_links and _link_idx < len(_page_links):
                        _, href = _page_links[_link_idx]
                        navigate(href)
                time.sleep(0.25)
                continue

            time.sleep(0.04)

    except KeyboardInterrupt:
        pass
    finally:
        RUNNING = False
        try:
            os.remove(WEBUI_URL_FILE)
        except OSError:
            pass
        if LCD:
            LCD.LCD_Clear()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
