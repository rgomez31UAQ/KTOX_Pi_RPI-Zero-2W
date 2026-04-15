#!/usr/bin/env python3
import os, sys, time, subprocess
import RPi.GPIO as GPIO
import LCD_1in44
from PIL import Image, ImageDraw, ImageFont

PINS = {"UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,"KEY3":16}
VIDEO_EXTS = ('.mp4','.avi','.mkv','.mov')
GPIO.setmode(GPIO.BCM)
for p in PINS.values(): GPIO.setup(p, GPIO.IN, GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
W,H=128,128
try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",9)
except: font=ImageFont.load_default()

def draw(lines):
    img=Image.new("RGB",(W,H),"black")
    d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,17),fill="#8B0000")
    d.text((4,3),"VIDEO",font=font,fill="#FF3333")
    y=20
    for l in lines[:6]:
        d.text((4,y),l[:23],font=font,fill="#FFBBBB")
        y+=12
    d.rectangle((0,H-12,W,H),fill="#220000")
    d.text((4,H-10),"UP/DN OK LEFT KEY3",font=font,fill="#FF7777")
    LCD.LCD_ShowImage(img,0,0)

def wait():
    for _ in range(50):
        for n,p in PINS.items():
            if GPIO.input(p)==0:
                time.sleep(0.05)
                return n
        time.sleep(0.01)
    return None

def list_dir(p):
    try:
        items=[]
        for f in sorted(os.scandir(p),key=lambda x:(not x.is_dir(),x.name)):
            if f.is_dir() or f.name.lower().endswith(VIDEO_EXTS):
                items.append(f)
        return items
    except: return []

def play_video(path):
    draw(["Loading..."])
    proc=subprocess.Popen(["ffmpeg","-i",path,"-vf","scale=128:128,fps=10",
                           "-pix_fmt","rgb24","-f","rawvideo","-",
                           "-f","pulse","-device","default"],
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    frame=128*128*3
    while True:
        raw=proc.stdout.read(frame)
        if len(raw)<frame: break
        img=Image.frombytes("RGB",(128,128),raw)
        LCD.LCD_ShowImage(img,0,0)
        if wait()=="KEY3":
            proc.terminate()
            break
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

path="/root"
entries=list_dir(path)
sel=0
while True:
    lines=[]
    short=os.path.basename(path) or "/"
    lines.append(f"Dir: {short[:18]}")
    lines.append("")
    start=max(0,sel-5)
    for i in range(start,min(start+6,len(entries))):
        e=entries[i]
        m=">" if i==sel else " "
        name=e.name[:18]+("/" if e.is_dir() else "")
        lines.append(f"{m} {name}")
    if not entries: lines.append("(empty)")
    draw(lines)
    btn=wait()
    if btn=="KEY3": break
    if btn=="UP": sel=max(0,sel-1)
    if btn=="DOWN": sel=min(len(entries)-1,sel+1) if entries else 0
    if btn=="LEFT":
        parent=os.path.dirname(path)
        if parent!=path:
            path=parent
            entries=list_dir(path)
            sel=0
    if btn=="OK" and entries:
        e=entries[sel]
        if e.is_dir():
            path=e.path
            entries=list_dir(path)
            sel=0
        else:
            play_video(e.path)
            entries=list_dir(path)

LCD.LCD_Clear()
GPIO.cleanup()
