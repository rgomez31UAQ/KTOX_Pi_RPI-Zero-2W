#!/usr/bin/env python3

# NAME: OTA Update

# DESC: Pull latest KTOx_Pi from GitHub and restart services.

import os
import sys
import time
import signal
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

KTOX_DIR   = “/root/KTOx”
LOOT_DIR   = KTOX_DIR + “/loot”
BACKUP_DIR = “/root/ktox_backups”
REPO_URL   = “https://github.com/wickednull/KTOx_Pi.git”
BRANCH     = “main”
WEBUI_SERVICES = [“ktox-device.service”, “ktox-webui.service”]

PINS = {“KEY1”: 21, “KEY2”: 20, “KEY3”: 16}
W, H = 128, 128

# ── Hardware ──────────────────────────────────────────────────────────────────

LCD     = None
FONT_SM = None
FONT_MD = None
HAS_HW  = False

def _init_hw():
global LCD, FONT_SM, FONT_MD, HAS_HW
try:
import RPi.GPIO as GPIO
import LCD_1in44
import LCD_Config
from PIL import ImageFont
GPIO.setmode(GPIO.BCM)
for p in PINS.values():
GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
HAS_HW = True
try:
FONT_SM = ImageFont.truetype(
“/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf”, 8)
FONT_MD = ImageFont.truetype(
“/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf”, 9)
except Exception:
FONT_SM = FONT_MD = ImageFont.load_default()
except Exception as e:
print(f”[OTA] No hardware: {e}”)
HAS_HW = False

# ── Colours ───────────────────────────────────────────────────────────────────

RED       = “#8B0000”
RED_BRITE = “#cc1a1a”
BG        = “#060101”
TEXT      = “#c8c8c8”
DIM       = “#4a2020”
GREEN     = “#2ecc71”
YELLOW    = “#f39c12”

# ── Drawing ───────────────────────────────────────────────────────────────────

def _show(title, lines, status_col=None):
if status_col is None:
status_col = TEXT
if not HAS_HW:
print(f”[OTA] {title}: {[l if isinstance(l, str) else l[0] for l in lines]}”)
return
try:
from PIL import Image, ImageDraw
img  = Image.new(“RGB”, (W, H), BG)
draw = ImageDraw.Draw(img)

```
    draw.rectangle([0, 0, W, 11], fill="#0d0000")
    draw.line([0, 11, W, 11], fill=RED, width=1)
    tw = draw.textbbox((0, 0), "KTOx_Pi UPDATE", font=FONT_SM)[2]
    draw.text(((W - tw) // 2, 1), "KTOx_Pi UPDATE", font=FONT_SM, fill=RED_BRITE)

    draw.rectangle([0, 12, W, 25], fill="#1a0000")
    draw.line([0, 25, W, 25], fill=RED, width=1)
    tw2 = draw.textbbox((0, 0), title, font=FONT_MD)[2]
    draw.text(((W - tw2) // 2, 14), title, font=FONT_MD, fill=status_col)

    y = 29
    for item in lines:
        if isinstance(item, tuple):
            txt, col = item
        else:
            txt, col = str(item), TEXT
        draw.text((4, y), str(txt)[:22], font=FONT_SM, fill=col)
        y += 12
        if y > 110:
            break

    draw.rectangle([0, 117, W, H], fill="#0d0000")
    draw.line([0, 117, W, 117], fill=RED, width=1)

    LCD.LCD_ShowImage(img, 0, 0)
except Exception as e:
    print(f"[OTA] draw error: {e}")
```

def _btn():
if not HAS_HW:
return None
try:
import RPi.GPIO as GPIO
for name, pin in PINS.items():
if GPIO.input(pin) == 0:
return name
except Exception:
pass
return None

def _wait_release():
if not HAS_HW:
return
try:
import RPi.GPIO as GPIO
while any(GPIO.input(p) == 0 for p in PINS.values()):
time.sleep(0.05)
except Exception:
pass

def _run(cmd, timeout=120):
try:
r = subprocess.run(
cmd, capture_output=True, text=True,
timeout=timeout,
shell=isinstance(cmd, str)
)
return r.returncode, (r.stdout + r.stderr).strip()
except subprocess.TimeoutExpired:
return -1, “Timeout”
except Exception as e:
return -1, str(e)

# ── Update steps ─────────────────────────────────────────────────────────────

def check_internet():
rc, _ = _run(
[“curl”, “-s”, “–connect-timeout”, “5”, “–max-time”, “8”,
“-o”, “/dev/null”, “https://github.com”],
timeout=15
)
return rc == 0

def backup_loot():
if not Path(LOOT_DIR).exists():
return True, “No loot to back up”
ts   = datetime.now().strftime(”%Y%m%d_%H%M%S”)
dest = f”{BACKUP_DIR}/loot_backup_{ts}”
try:
Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
shutil.copytree(LOOT_DIR, dest)
return True, f”Saved to {dest}”
except Exception as e:
return False, str(e)

def do_git_pull():
import tempfile

```
tmp = f"/tmp/ktox_update_{int(time.time())}"
try:
    rc, out = _run(
        ["git", "clone", "--depth=1", "-b", BRANCH, REPO_URL, tmp],
        timeout=150,
    )
    if rc != 0:
        return False, f"Clone failed: {out[:60]}"

    s = Path(tmp)
    d = Path(KTOX_DIR)

    # Core files from ktox_pi/ -> flat into KTOX_DIR
    for fname in [
        "ktox_device.py", "LCD_1in44.py", "LCD_Config.py",
        "ktox_input.py", "ktox_lcd.py", "ktox_payload_runner.py",
    ]:
        src_f = s / "ktox_pi" / fname
        if src_f.exists():
            shutil.copy2(src_f, d / fname)

    # Always create rj_input.py as a copy of ktox_input.py
    # so any code still importing rj_input works without modification
    ki = d / "ktox_input.py"
    rj = d / "rj_input.py"
    if ki.exists():
        shutil.copy2(ki, rj)

    # Root-level files
    for fname in [
        "device_server.py", "web_server.py", "nmap_parser.py",
        "scan.py", "spoof.py", "requirements.txt",
        "ktox.py", "ktox_mitm.py", "ktox_advanced.py",
        "ktox_extended.py", "ktox_defense.py", "ktox_stealth.py",
        "ktox_netattack.py", "ktox_wifi.py", "ktox_dashboard.py",
        "ktox_repl.py", "ktox_config.py",
        "ktox_device_pi.py", "payload_compat.py",
    ]:
        src_f = s / fname
        if src_f.exists():
            shutil.copy2(src_f, d / fname)

    # Directories
    for dname in ["web", "payloads", "wifi", "Responder", "DNSSpoof", "assets"]:
        src_d = s / dname
        dst_d = d / dname
        if src_d.exists():
            if dst_d.exists():
                shutil.rmtree(dst_d)
            shutil.copytree(src_d, dst_d)

    # Logo
    logo = s / "img" / "logo.bmp"
    if logo.exists():
        (d / "img").mkdir(exist_ok=True)
        shutil.copy2(logo, d / "img" / "logo.bmp")

    # Record commit hash
    _, commit = _run(["git", "-C", tmp, "rev-parse", "--short", "HEAD"])
    commit = commit.strip()
    try:
        (d / ".ktox_version").write_text(commit + "\n")
    except Exception:
        pass

    return True, f"HEAD: {commit}"

except Exception as e:
    return False, str(e)[:60]
finally:
    shutil.rmtree(tmp, ignore_errors=True)
```

def install_deps():
req = Path(KTOX_DIR + “/requirements.txt”)
if not req.exists():
return True, “No requirements.txt”
rc, out = _run(
[“pip3”, “install”, “–break-system-packages”, “-q”, “-r”, str(req)],
timeout=180
)
return rc == 0, out[:60] if rc != 0 else “deps OK”

def restart_services():
failed = []
for svc in WEBUI_SERVICES:
rc, _ = _run([“systemctl”, “restart”, svc], timeout=20)
if rc != 0:
failed.append(svc.split(”.”)[0])
try:
subprocess.Popen(
[“bash”, “-c”, “sleep 6 && systemctl restart ktox.service”],
stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
close_fds=True,
)
except Exception:
pass
if failed:
return False, “Failed: “ + “,”.join(failed)
return True, “Services restarting”

def get_current_version():
try:
v = Path(KTOX_DIR + “/.ktox_version”).read_text().strip()
if v:
return v
except Exception:
pass
return “unknown”

def get_remote_version():
rc, out = _run(
[“git”, “ls-remote”, REPO_URL, f”refs/heads/{BRANCH}”],
timeout=15
)
if rc == 0 and out:
return out.split()[0][:7]
return “unknown”

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
_init_hw()

```
signal.signal(signal.SIGINT,  lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

_show("READY", [
    ("KEY1 = Update now", TEXT),
    ("KEY3 = Exit", DIM),
    "",
    (f"Installed: {get_current_version()}", DIM),
    ("github.com/wickednull", DIM),
    ("/KTOx_Pi", DIM),
])

try:
    while True:
        btn = _btn()
        if btn == "KEY3":
            _show("Cancelled", [("No changes made.", DIM)], status_col=DIM)
            time.sleep(1.5)
            sys.exit(0)
        if btn == "KEY1":
            _wait_release()
            break
        time.sleep(0.1)

    # Step 1: internet check
    _show("Checking...", [("Connecting to GitHub...", DIM)])
    if not check_internet():
        _show("NO INTERNET", [
            ("Cannot reach GitHub.", YELLOW),
            ("Check your network", TEXT),
            ("and try again.", TEXT),
        ], status_col=YELLOW)
        time.sleep(4)
        sys.exit(1)

    # Step 2: version check
    current = get_current_version()
    _show("Checking...", [
        (f"Current: {current}", TEXT),
        ("Checking remote...", DIM),
    ])
    remote = get_remote_version()
    if current != "unknown" and remote != "unknown" and current == remote[:7]:
        _show("UP TO DATE", [
            (f"Version: {current}", GREEN),
            ("Nothing to update.", TEXT),
        ], status_col=GREEN)
        time.sleep(3)
        sys.exit(0)

    _show("UPDATE FOUND", [
        (f"Current: {current}", TEXT),
        (f"Remote:  {remote[:7]}", GREEN),
        "",
        ("KEY1 = Install", TEXT),
        ("KEY3 = Cancel", DIM),
    ], status_col=GREEN)

    deadline   = time.time() + 30
    confirmed  = False
    while time.time() < deadline:
        btn = _btn()
        if btn == "KEY1":
            _wait_release()
            confirmed = True
            break
        if btn == "KEY3":
            _wait_release()
            break
        time.sleep(0.1)

    if not confirmed:
        _show("Cancelled", [("No changes made.", DIM)], status_col=DIM)
        time.sleep(1.5)
        sys.exit(0)

    # Step 3: backup loot
    _show("BACKING UP", [("Saving loot...", DIM)])
    ok, msg = backup_loot()
    _show("BACKING UP", [
        (("+ " if ok else "! ") + msg[:20], GREEN if ok else YELLOW)
    ])
    time.sleep(0.8)

    # Step 4: git pull
    _show("DOWNLOADING", [
        ("Pulling from GitHub...", DIM),
        ("This may take a", DIM),
        ("minute...", DIM),
    ])
    ok, msg = do_git_pull()
    if not ok:
        _show("UPDATE FAILED", [
            ("Git pull failed:", YELLOW),
            (msg[:22], TEXT),
            "",
            ("Loot is safe.", DIM),
        ], status_col=YELLOW)
        time.sleep(5)
        sys.exit(1)
    _show("DOWNLOADING", [("+ " + msg, GREEN)])
    time.sleep(0.8)

    # Step 5: install deps
    _show("INSTALLING", [("Updating packages...", DIM)])
    ok, msg = install_deps()
    _show("INSTALLING", [
        (("+ " if ok else "~ ") + msg[:22], GREEN if ok else YELLOW)
    ])
    time.sleep(0.8)

    # Step 6: restart
    _show("RESTARTING", [("Restarting services...", DIM)])
    ok, msg = restart_services()

    if ok:
        _show("UPDATE DONE", [
            ("+ KTOx_Pi updated!", GREEN),
            (f"  {msg}", DIM),
            "",
            ("Restarting now...", TEXT),
        ], status_col=GREEN)
        time.sleep(3)
    else:
        _show("PARTIAL", [
            (msg[:22], YELLOW),
            ("Manual restart may", TEXT),
            ("be needed.", TEXT),
        ], status_col=YELLOW)
        time.sleep(4)

finally:
    if HAS_HW:
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        except Exception:
            pass
```

if **name** == “**main**”:
main()
