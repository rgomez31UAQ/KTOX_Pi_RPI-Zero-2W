#!/usr/bin/env python3
# NAME: APT Store

import os, subprocess, time, re, threading
from pathlib import Path

# ---- LCD & GPIO ----
import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO

PINS = {"UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,"KEY1":21,"KEY2":20,"KEY3":16}
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

W, H = 128, 128
font = ImageFont.load_default()
try:
    bold_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 9)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 8)
except:
    bold_font = font
    small_font = font

def _key(pin): return GPIO.input(pin) == 0

def wait_button():
    while True:
        if _key(PINS["UP"]): return "UP"
        if _key(PINS["DOWN"]): return "DOWN"
        if _key(PINS["LEFT"]): return "LEFT"
        if _key(PINS["RIGHT"]): return "RIGHT"
        if _key(PINS["OK"]): return "OK"
        if _key(PINS["KEY1"]): return "KEY1"
        if _key(PINS["KEY2"]): return "KEY2"
        if _key(PINS["KEY3"]): return "KEY3"
        time.sleep(0.05)

def clear_screen():
    lcd = LCD_1in44.LCD()
    lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    LCD_Config.Driver_Delay_ms(50)
    return lcd

def draw_menu(lcd, lines, title, selected=0, page=0, total_pages=1):
    img = Image.new("RGB", (W, H), "#0a0a0a")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0,0,W,12), fill="#8B0000")
    draw.text((2,2), title[:16], font=bold_font, fill="#fff")
    if total_pages > 1:
        draw.text((W-30,2), f"{page+1}/{total_pages}", font=small_font, fill="#888")
    y = 16
    start = max(0, selected - 4)
    end = min(len(lines), start + 6)
    for i in range(start, end):
        prefix = "> " if i == selected else "  "
        text = lines[i][:18]
        draw.text((4, y), prefix + text, font=font, fill="#c8c8c8")
        y += 12
    lcd.LCD_ShowImage(img, 0, 0)

def show_message(text, delay=2):
    lcd = clear_screen()
    img = Image.new("RGB", (W, H), "#0a0a0a")
    draw = ImageDraw.Draw(img)
    draw.text((4,10), text[:20], font=font, fill="#c8c8c8")
    lcd.LCD_ShowImage(img, 0, 0)
    time.sleep(delay)

def show_text_scroll(lines, title="INFO"):
    """Show multiple lines with scroll up/down."""
    lcd = clear_screen()
    page = 0
    while True:
        img = Image.new("RGB", (W, H), "#0a0a0a")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,W,12), fill="#8B0000")
        draw.text((2,2), title[:16], font=bold_font, fill="#fff")
        y = 16
        start = page * 6
        end = min(start+6, len(lines))
        for i in range(start, end):
            draw.text((4, y), lines[i][:20], font=small_font, fill="#c8c8c8")
            y += 11
        if len(lines) > 6:
            draw.text((W-30,H-12), f"{page+1}/{(len(lines)-1)//6+1}", font=small_font, fill="#888")
        lcd.LCD_ShowImage(img, 0, 0)
        btn = wait_button()
        if btn == "UP" and page > 0: page -= 1
        elif btn == "DOWN" and (page+1)*6 < len(lines): page += 1
        elif btn == "OK" or btn == "KEY2" or btn == "KEY3": break

def run_apt(cmd, title="APT"):
    """Run apt command, show output on LCD."""
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lcd = clear_screen()
    lines = []
    for line in iter(proc.stdout.readline, ''):
        lines.append(line.strip())
        if len(lines) > 6: lines = lines[-6:]
        img = Image.new("RGB", (W, H), "#0a0a0a")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,W,12), fill="#8B0000")
        draw.text((2,2), title[:16], font=bold_font, fill="#fff")
        y = 16
        for l in lines:
            draw.text((4, y), l[:20], font=small_font, fill="#c8c8c8")
            y += 11
        lcd.LCD_ShowImage(img, 0, 0)
    proc.wait()
    return proc.returncode == 0

def confirm(msg):
    lcd = clear_screen()
    img = Image.new("RGB", (W, H), "#0a0a0a")
    draw = ImageDraw.Draw(img)
    draw.text((4,10), msg[:20], font=font, fill="#ff8800")
    draw.text((4,30), "KEY1 = YES", font=font, fill="#2ecc40")
    draw.text((4,42), "KEY2 = NO", font=font, fill="#c8c8c8")
    lcd.LCD_ShowImage(img, 0, 0)
    while True:
        btn = wait_button()
        if btn == "KEY1": return True
        if btn == "KEY2" or btn == "KEY3": return False

def get_installed_packages():
    result = subprocess.run(["apt", "list", "--installed"], capture_output=True, text=True)
    pkgs = []
    for line in result.stdout.splitlines():
        if "/" in line and "installed" in line:
            parts = line.split()
            name = parts[0].split("/")[0]
            version = parts[1] if len(parts) > 1 else "?"
            pkgs.append(f"{name} ({version})")
    return sorted(pkgs)

def get_package_details(pkg_name):
    result = subprocess.run(["apt", "show", pkg_name], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    details = []
    for line in lines[:30]:  # limit
        if line.startswith("Package:"):
            details.append(line)
        elif line.startswith("Version:"):
            details.append(line)
        elif line.startswith("Description:"):
            details.append(line)
        elif line.startswith("Homepage:"):
            details.append(line)
        elif line.startswith("Depends:"):
            details.append(line)
        elif line.startswith("Size:"):
            details.append(line)
    if not details:
        details = ["No details found"]
    return details

def search_packages(query):
    result = subprocess.run(f"apt-cache search --names-only '{query}'", shell=True, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    pkgs = []
    for line in lines[:50]:
        name = line.split(" - ")[0]
        pkgs.append(name)
    return pkgs

def install_package(pkg_name):
    if confirm(f"Install {pkg_name}?"):
        return run_apt(f"apt install --yes {pkg_name}", title="INSTALL")
    return False

def uninstall_package(pkg_name):
    if confirm(f"Remove {pkg_name}?"):
        return run_apt(f"apt remove --yes {pkg_name}", title="REMOVE")
    return False

def update_package_list():
    return run_apt("apt update", title="UPDATE")

def upgrade_all():
    if confirm("Upgrade all packages?"):
        return run_apt("apt upgrade --yes", title="UPGRADE")
    return False

# ---- On‑screen keyboard for search ----
KEYBOARD = [
    ['a','b','c','d','e','f','g','h','i','j'],
    ['k','l','m','n','o','p','q','r','s','t'],
    ['u','v','w','x','y','z','-','_','.',' '],
    ['←','⌫','🔍','OK','EXIT']
]

def keyboard_input(title="SEARCH"):
    """Return a string entered via on‑screen keyboard."""
    query = ""
    row, col = 0, 0
    lcd = clear_screen()
    while True:
        img = Image.new("RGB", (W, H), "#0a0a0a")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,W,12), fill="#8B0000")
        draw.text((2,2), title[:16], font=bold_font, fill="#fff")
        draw.text((2, H-12), f"> {query[:18]}", font=small_font, fill="#2ecc40")
        # Draw keyboard grid
        y = 16
        for r_idx, row_keys in enumerate(KEYBOARD):
            x = 2
            for c_idx, key in enumerate(row_keys):
                if r_idx == row and c_idx == col:
                    draw.rectangle((x-1, y-1, x+9, y+9), fill="#8B0000")
                    draw.text((x, y), key, font=font, fill="#fff")
                else:
                    draw.text((x, y), key, font=font, fill="#c8c8c8")
                x += 12
            y += 12
        lcd.LCD_ShowImage(img, 0, 0)
        btn = wait_button()
        if btn == "UP": row = max(0, row-1)
        elif btn == "DOWN": row = min(len(KEYBOARD)-1, row+1)
        elif btn == "LEFT": col = max(0, col-1)
        elif btn == "RIGHT": col = min(len(KEYBOARD[row])-1, col+1)
        elif btn == "OK":
            key = KEYBOARD[row][col]
            if key == '←':  # move cursor left
                query = query[:-1]
            elif key == '⌫': # clear all
                query = ""
            elif key == '🔍':
                return query
            elif key == 'OK':
                return query
            elif key == 'EXIT':
                return None
            else:
                query += key
        elif btn == "KEY2":
            return None
        elif btn == "KEY3":
            return None

def main():
    while True:
        options = ["Installed Packages", "Search & Install", "Update Package List", "Upgrade All", "Exit"]
        sel = 0
        while True:
            draw_menu(clear_screen(), options, "APT STORE", sel)
            btn = wait_button()
            if btn == "UP": sel = (sel-1) % len(options)
            elif btn == "DOWN": sel = (sel+1) % len(options)
            elif btn == "OK": break
            elif btn == "KEY3": return
        if sel == 0:  # Installed Packages
            pkgs = get_installed_packages()
            if not pkgs:
                show_message("No packages found", 1)
                continue
            p_idx = 0
            page = 0
            while True:
                draw_menu(clear_screen(), pkgs, "INSTALLED", p_idx)
                btn = wait_button()
                if btn == "UP": p_idx = (p_idx-1) % len(pkgs)
                elif btn == "DOWN": p_idx = (p_idx+1) % len(pkgs)
                elif btn == "OK":
                    pkg_line = pkgs[p_idx]
                    pkg_name = pkg_line.split(" (")[0]
                    # Show details
                    details = get_package_details(pkg_name)
                    show_text_scroll(details, f"DETAILS: {pkg_name[:10]}")
                    if confirm(f"Uninstall {pkg_name}?"):
                        if uninstall_package(pkg_name):
                            show_message(f"Removed {pkg_name}", 1)
                            pkgs = get_installed_packages()
                            if not pkgs: break
                            p_idx = min(p_idx, len(pkgs)-1)
                        else:
                            show_message("Remove failed", 1)
                elif btn == "KEY2": break
                elif btn == "KEY3": return
        elif sel == 1:  # Search & Install
            query = keyboard_input("SEARCH PACKAGE")
            if not query:
                continue
            show_message(f"Searching: {query}", 1)
            results = search_packages(query)
            if not results:
                show_message("No matches", 1)
                continue
            r_idx = 0
            while True:
                draw_menu(clear_screen(), results, f"RESULTS ({len(results)})", r_idx)
                btn = wait_button()
                if btn == "UP": r_idx = (r_idx-1) % len(results)
                elif btn == "DOWN": r_idx = (r_idx+1) % len(results)
                elif btn == "OK":
                    pkg = results[r_idx]
                    details = get_package_details(pkg)
                    show_text_scroll(details, f"DETAILS: {pkg[:10]}")
                    if confirm(f"Install {pkg}?"):
                        if install_package(pkg):
                            show_message(f"Installed {pkg}", 1)
                        else:
                            show_message("Install failed", 1)
                elif btn == "KEY2": break
                elif btn == "KEY3": return
        elif sel == 2:  # Update
            show_message("Updating...", 1)
            if update_package_list():
                show_message("Done", 1)
            else:
                show_message("Update failed", 1)
        elif sel == 3:  # Upgrade
            if upgrade_all():
                show_message("Upgrade done", 1)
            else:
                show_message("Upgrade failed", 1)
        elif sel == 4:
            return

if __name__ == "__main__":
    main()
