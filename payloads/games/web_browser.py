#!/usr/bin/env python3
"""
KTOx Payload – Tiny Web Browser
=============================================================
- Stable base (no crashes)
- URL input working
- Search (KEY1 hold)
- Reader mode (KEY2 hold)
- Bookmark system (KEY3)
- Safe link parsing
"""

import os, sys, re, time, threading, textwrap
import urllib.request, urllib.parse
from urllib.request import Request

KTOX_ROOT = "/root/KTOx"
if os.path.isdir(KTOX_ROOT) and KTOX_ROOT not in sys.path:
    sys.path.insert(0, KTOX_ROOT)

try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except:
    HAS_HW = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except:
    HAS_BS4 = False

W, H = 128, 128
CHAR_SET = "abcdefghijklmnopqrstuvwxyz0123456789./:_-?=&#@%+"
BOOKMARK_FILE = "/root/KTOx/bookmarks.txt"
MAX_CONTENT_SIZE = 512 * 1024

PINS = {
    "UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,
    "KEY1":21,"KEY2":20,"KEY3":16
}

LCD=_image=_draw=_font=None
RUNNING=True

_page_lines=["Welcome","KEY1=URL"]
_page_links=[]
_link_idx=0
_scroll=0
_current_url=""
_fetching=False
_status="ready"

_reader_mode=False
_last_key_time={"KEY1":0,"KEY2":0}

# ─────────────────────────────────────
def _init_hw():
    global LCD,_image,_draw,_font
    if not HAS_HW: return

    GPIO.setmode(GPIO.BCM)
    for p in PINS.values():
        GPIO.setup(p,GPIO.IN,pull_up_down=GPIO.PUD_UP)

    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

    _image = Image.new("RGB",(W,H),"black")
    _draw = ImageDraw.Draw(_image)
    _font = ImageFont.load_default()

# ─────────────────────────────────────
def _wrap(txt,w=20):
    out=[]
    for l in txt.splitlines():
        l=re.sub(r'\s+',' ',l).strip()
        if l:
            out+=textwrap.wrap(l,width=w)
        else:
            out.append("")
    return out

# ─────────────────────────────────────
def _fetch(url):
    global _page_lines,_page_links,_fetching,_status,_current_url,_link_idx,_scroll

    _fetching=True
    _status="loading"
    _page_lines=["Connecting...",url[:20]]
    _page_links=[]

    try:
        if not url.startswith("http"):
            url="https://"+url

        req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
        raw=urllib.request.urlopen(req,timeout=10).read(MAX_CONTENT_SIZE)
        html=raw.decode("utf-8","replace")

        links=[]
        if HAS_BS4:
            soup=BeautifulSoup(html,"lxml")
            for t in soup(["script","style"]):
                t.decompose()

            text=soup.get_text("\n")

            for a in soup.find_all("a",href=True):
                txt=a.get_text(strip=True)
                href=urllib.parse.urljoin(url,a["href"])
                if txt and href.startswith("http"):
                    links.append((txt[:20],href))
        else:
            text=html
            for m in re.finditer(r'href=["\'](.*?)["\']',html):
                links.append((m.group(1)[:20],m.group(1)))

        lines=_wrap(text)

        if links and not _reader_mode:
            lines+=["","-- Links --"]
            for i,(t,_) in enumerate(links):
                lines.append(f"[{i+1}] {t}")

        _page_lines=lines
        _page_links=links
        _current_url=url
        _link_idx=0
        _scroll=0
        _status=f"{len(lines)}L {len(links)}lk"

    except Exception as e:
        _page_lines=["Load failed",str(e)[:25]]
        _status="ERR"

    _fetching=False

# ─────────────────────────────────────
def navigate(url):
    threading.Thread(target=_fetch,args=(url,),daemon=True).start()

# ─────────────────────────────────────
def _draw_browser():
    _draw.rectangle((0,0,W,H),fill="black")

    y=2
    for i in range(10):
        idx=_scroll+i
        if idx>=len(_page_lines): break
        txt=_page_lines[idx][:20]

        color="white"

        if txt.startswith("["):
            try:
                n=int(txt.split("]")[0][1:])-1
                if n==_link_idx:
                    txt=">"+txt
                    color="yellow"
                else:
                    color="cyan"
            except:
                pass

        _draw.text((2,y),txt,font=_font,fill=color)
        y+=11

    _draw.text((2,118),_status[:18],font=_font,fill="gray")

# ─────────────────────────────────────
def _push():
    LCD.LCD_ShowImage(_image,0,0)

# ─────────────────────────────────────
def _url_input_screen(start=""):
    text=start
    idx=0

    while True:
        _draw.rectangle((0,0,W,H),fill="black")

        _draw.text((2,10),"Enter URL:",font=_font,fill="white")
        _draw.text((2,30),text[-18:],font=_font,fill="cyan")

        char=CHAR_SET[idx]
        _draw.text((2,60),f"[{char}]",font=_font,fill="yellow")

        _push()

        pressed={k:GPIO.input(v)==0 for k,v in PINS.items()}

        if pressed["UP"]:
            idx=(idx-1)%len(CHAR_SET)
            time.sleep(0.15)

        if pressed["DOWN"]:
            idx=(idx+1)%len(CHAR_SET)
            time.sleep(0.15)

        if pressed["RIGHT"]:
            text+=CHAR_SET[idx]
            time.sleep(0.2)

        if pressed["LEFT"]:
            text=text[:-1]
            time.sleep(0.2)

        if pressed["OK"]:
            return text

        if pressed["KEY3"]:
            return None

# ─────────────────────────────────────
def _search_page():
    query=_url_input_screen("")
    if not query: return
    query=query.lower()

    global _scroll
    for i,line in enumerate(_page_lines):
        if query in line.lower():
            _scroll=max(0,i-2)
            return

# ─────────────────────────────────────
def _save_bookmark():
    if not _current_url: return
    try:
        with open(BOOKMARK_FILE,"a") as f:
            f.write(_current_url+"\n")
        global _status
        _status="Saved"
    except:
        pass

# ─────────────────────────────────────
def _load_bookmark():
    if not os.path.exists(BOOKMARK_FILE):
        return None

    with open(BOOKMARK_FILE) as f:
        urls=f.read().splitlines()

    if not urls:
        return None

    idx=0
    while True:
        _draw.rectangle((0,0,W,H),fill="black")
        _draw.text((2,5),"Bookmarks",font=_font,fill="white")
        _draw.text((2,30),urls[idx][:20],font=_font,fill="cyan")
        _push()

        pressed={k:GPIO.input(v)==0 for k,v in PINS.items()}

        if pressed["UP"]:
            idx=(idx-1)%len(urls)
            time.sleep(0.2)

        if pressed["DOWN"]:
            idx=(idx+1)%len(urls)
            time.sleep(0.2)

        if pressed["OK"]:
            return urls[idx]

        if pressed["KEY3"]:
            return None

# ─────────────────────────────────────
def main():
    global RUNNING,_scroll,_link_idx,_reader_mode

    _init_hw()
    if not HAS_HW:
        print("No hardware")
        return

    navigate("example.com")

    held={}

    while RUNNING:
        _draw_browser()
        _push()

        pressed={k:GPIO.input(v)==0 for k,v in PINS.items()}
        now=time.time()

        def jp(k):
            return pressed[k] and not held.get(k)

        for k,v in pressed.items():
            if v: held[k]=1
            else: held.pop(k,None)

        # KEY3 → bookmarks
        if jp("KEY3"):
            url=_load_bookmark()
            if url: navigate(url)

        # KEY1 → URL or search (hold)
        if pressed["KEY1"]:
            if now-_last_key_time["KEY1"]>0.6:
                _search_page()
                _last_key_time["KEY1"]=now
        else:
            if jp("KEY1"):
                url=_url_input_screen(_current_url)
                if url: navigate(url)
                _last_key_time["KEY1"]=now

        # KEY2 → next link or reader mode
        if pressed["KEY2"]:
            if now-_last_key_time["KEY2"]>0.6:
                _reader_mode=not _reader_mode
                navigate(_current_url)
                _last_key_time["KEY2"]=now
        else:
            if jp("KEY2") and _page_links:
                _link_idx=(_link_idx+1)%len(_page_links)
                _last_key_time["KEY2"]=now

        if jp("UP"): _scroll=max(0,_scroll-1)
        if jp("DOWN"): _scroll+=1

        if jp("OK") and _page_links:
            navigate(_page_links[_link_idx][1])

        time.sleep(0.05)

    GPIO.cleanup()

if __name__=="__main__":
    main()
