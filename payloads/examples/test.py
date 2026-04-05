#!/usr/bin/env python3
"""
KTOX Shadow Tier 5 – Final Form
================================
- Full cyberpunk skull with facial animation
- Real Wi-Fi scanning, packet capture, channel hopping
- PPS graph, heatmap, AP scrolling
- AI-driven target prioritization
- Persistent AP memory
- Manual / Auto modes
- Real-time adaptive red team training payload
"""
import os, time, math, subprocess, signal, threading, random, collections, pickle, re

# ── Hardware Detection ─────────────────────────
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not detected, running in simulation mode.")

# ── Constants ──────────────────────────────────
W,H = 128,128
PINS = {"K1":21,"K2":20,"K3":16}
AP_DB_FILE="ap_db.pkl"

# ── Globals ───────────────────────────────────
LCD = None; _draw = None; _image = None; _font = None
RUNNING = True; shadow_running = False; manual_mode = False
ghost_frame=0; ghost_state="idle"; eye_blink_state=True; eye_blink_timer=0
packets=0; last_packets=0; pps=0; total_packets=0
channel=1; log_lines=[]
capture_proc=None
ap_db={}; target_ap=None; pps_history=collections.deque(maxlen=60); channel_hits=[0]*12
ap_scroll=0; ai_mode=True; ai_state="idle"; ap_scores={}

# ── Hardware Init ────────────────────────────
def init_hw():
    global LCD,_draw,_image,_font
    if not HAS_HW: return
    GPIO.setmode(GPIO.BCM)
    for p in PINS.values(): GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD.LCD_Clear()
    _image = Image.new("RGB",(W,H),"black")
    _draw = ImageDraw.Draw(_image)
    _font = ImageFont.load_default()

def push(): 
    if LCD: LCD.LCD_ShowImage(_image,0,0)

# ── Cyberpunk Skull ──────────────────────────
def draw_skull(x, y):
    global ghost_state, eye_blink_state, eye_blink_timer, pps
    color={"idle":"#00AAFF","hunt":"#00FFAA","lock":"#FFFF00","overload":"#FF3333"}.get(ghost_state,"#00AAFF")
    if time.time()-eye_blink_timer > 0.5+random.random(): eye_blink_state, eye_blink_timer = not eye_blink_state, time.time()
    eye_fill=color if eye_blink_state else "#050505"
    _draw.rectangle((x-5,y-4,x-3,y-2),fill=eye_fill)
    _draw.rectangle((x+3,y-4,x+5,y-2),fill=eye_fill)
    _draw.polygon([(x,y-1),(x-1,y+2),(x+1,y+2)],fill=color)
    jaw_offset=min(6,pps//30)
    for i in range(-3,4,2): _draw.rectangle((x+i,y+4+jaw_offset,x+i+1,y+5+jaw_offset),fill=color)
    if target_ap and ghost_state in ["lock","overload"]:
        _draw.line((x-6,y,x+6,y),fill="#FFFFFF")
        _draw.line((x,y-6,x,y+6),fill="#FFFFFF")

def draw_orb(x,y):
    global ghost_frame
    bob=int(math.sin(ghost_frame/6)*3)
    pulse=abs(math.sin(ghost_frame/4)*4)
    _draw.ellipse((x-12-pulse,y-12+bob-pulse,x+12+pulse,y+12+bob+pulse),fill="#111144")
    _draw.ellipse((x-8,y-8+bob,x+8,y+8+bob),fill="#2222FF")
    draw_skull(x,y+bob)
    ghost_frame+=1

# ── Graphs & UI ─────────────────────────────
def draw_graph():
    x_offset=0
    for val in list(pps_history):
        h=min(20,val//10)
        _draw.line((x_offset,60,x_offset,60-h),fill="#00FFAA")
        x_offset+=2

def draw_heatmap():
    for ch in range(1,12):
        h=min(15,channel_hits[ch])
        x=ch*10
        _draw.rectangle((x,80,x+5,80-h),fill="#FF5500")

def draw_ap_list():
    global ap_scroll
    y=0
    sorted_aps=sorted(ap_db.items(),key=lambda x:x[1].get("score",0),reverse=True)
    for bssid,info in sorted_aps[ap_scroll:ap_scroll+4]:
        ssid=info.get("ssid",bssid[:6])
        rssi=info.get("rssi",-100)
        bar_len=min(20,max(0,rssi+100))
        _draw.text((0,y),ssid[:8],font=_font,fill="#FFAA00")
        _draw.rectangle((50,y,50+bar_len,y+5),fill="#00FFAA")
        y+=12

def draw_screen():
    _draw.rectangle((0,0,W,H),fill="#050505")
    _draw.text((2,2),f"KTOX {'MAN' if manual_mode else 'AUTO'}",font=_font,fill="#FF3333")
    _draw.text((70,2),f"CH:{channel}",font=_font,fill="#00FFAA")
    _draw.text((2,14),f"PPS:{pps}",font=_font,fill="#AAAAFF")
    _draw.text((2,24),f"APS:{len(ap_db)}",font=_font,fill="#00FFAA")
    _draw.text((2,36),f"AI:{ai_state.upper()}",font=_font,fill="#FF66FF")
    draw_graph(); draw_heatmap(); draw_ap_list(); draw_orb(64,105); push()

# ── Wi-Fi Monitor ───────────────────────────
def enable_monitor(iface="wlan0"):
    subprocess.call(["sudo","ip","link","set",iface,"down"])
    subprocess.call(["sudo","iw",iface,"set","monitor","control"])
    subprocess.call(["sudo","ip","link","set",iface,"up"])
    return iface

def hop_channels(iface):
    global channel
    while shadow_running:
        if ai_mode and ai_state in ["lock","overload"] and target_ap:
            time.sleep(1)
            continue
        if max(channel_hits)>20: channel=channel_hits.index(max(channel_hits))
        else: channel=(channel%11)+1
        subprocess.call(["sudo","iwconfig",iface,"channel",str(channel)])
        time.sleep(0.5)

def capture_packets(iface):
    global packets,total_packets,ap_db,target_ap,channel_hits
    cmd=["sudo","tcpdump","-i",iface,"-e","-I"]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    for line in proc.stdout:
        packets+=1; total_packets+=1; channel_hits[channel]+=1
        if "Beacon" in line:
            try:
                bssid=line.split()[1]
                rssi_match=re.search(r"(-\d+)dB",line)
                rssi=int(rssi_match.group(1)) if rssi_match else -100
                if bssid not in ap_db: ap_db[bssid]={"rssi":rssi,"seen":1,"activity":1,"ssid":bssid[:6]}
                else: 
                    ap_db[bssid]["rssi"]=rssi
                    ap_db[bssid]["seen"]+=1
                    ap_db[bssid]["activity"]+=1
            except: pass

# ── Stats Loop ──────────────────────────────
def stats_loop():
    global last_packets,pps,ghost_state
    while RUNNING:
        time.sleep(1)
        pps=packets-last_packets; last_packets=packets
        pps_history.append(pps)
        if ai_state=="overload": ghost_state="overload"
        elif ai_state=="lock": ghost_state="lock"
        elif ai_state=="hunt": ghost_state="hunt"
        else: ghost_state="idle"

# ── AI Brain ─────────────────────────────────
def ai_brain():
    global target_ap, ai_state, ap_scores
    while RUNNING:
        time.sleep(2)
        if not ap_db: ai_state="idle"; continue
        ap_scores={}
        for bssid,data in ap_db.items():
            score=(data.get("rssi",-100)+100)*2 + data.get("activity",0)*3 + data.get("seen",0)*2
            ap_scores[bssid]=score
            data["score"]=score
        target_ap=max(ap_scores,key=ap_scores.get)
        s=ap_scores[target_ap]
        if len(ap_db)>40: ai_state="overload"
        elif s>300: ai_state="lock"
        elif s>100: ai_state="hunt"
        else: ai_state="idle"

# ── Control ─────────────────────────────────
def start_shadow():
    global shadow_running
    shadow_running=True
    iface=enable_monitor("wlan0")
    threading.Thread(target=capture_packets,args=(iface,),daemon=True).start()
    threading.Thread(target=hop_channels,args=(iface,),daemon=True).start()

def stop_shadow(): global shadow_running; shadow_running=False
def toggle_manual(): global manual_mode; manual_mode=not manual_mode

# ── Persistent AP DB ────────────────────────
def load_ap_db():
    global ap_db
    if os.path.exists(AP_DB_FILE):
        try: ap_db=pickle.load(open(AP_DB_FILE,"rb"))
        except: ap_db={}

def save_ap_db():
    pickle.dump(ap_db,open(AP_DB_FILE,"wb"))

# ── Main ───────────────────────────────────
def main():
    global RUNNING, ap_scroll
    load_ap_db()
    init_hw()
    threading.Thread(target=stats_loop,daemon=True).start()
    threading.Thread(target=ai_brain,daemon=True).start()

    while RUNNING:
        if HAS_HW:
            k1=GPIO.input(PINS["K1"])==0
            k2=GPIO.input(PINS["K2"])==0
            k3=GPIO.input(PINS["K3"])==0
        else: k1=k2=k3=False

        if k1:
            if shadow_running: stop_shadow()
            else: start_shadow()
            time.sleep(0.4)
        if k2: toggle_manual(); time.sleep(0.4)
        if k3: break

        draw_screen()
        if shadow_running and manual_mode:
            ap_scroll=(ap_scroll+1)%max(1,len(ap_db))
        time.sleep(0.1)

    stop_shadow()
    save_ap_db()
    if HAS_HW: GPIO.cleanup()

if __name__=="__main__":
    main()
