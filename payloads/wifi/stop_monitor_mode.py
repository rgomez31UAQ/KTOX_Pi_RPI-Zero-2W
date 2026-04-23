#!/usr/bin/env python3
"""
KTOx payload — Stop Monitor Mode
================================
Safely restores monitor-mode Wi-Fi interfaces back to managed mode.

Designed for KTOx_Pi on Raspberry Pi Zero 2 W running Kali Linux.

Behavior:
- Finds active monitor-mode interfaces
- Uses the shared monitor_mode_helper
- Does NOT restart NetworkManager or wpa_supplicant blindly
- Shows clear LCD progress and result state

Controls:
  KEY3 — exit after result is shown
"""

import sys
import os
import time
import signal

# ── Path setup ────────────────────────────────────────────────────────────────
KTOX_ROOT = "/root/KTOx" if os.path.isdir("/root/KTOx") else \
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

for _p in (KTOX_ROOT, os.path.join(KTOX_ROOT, "wifi")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# ── Hardware ──────────────────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError as e:
    print(f"[WARN] Hardware not available: {e}")
    HAS_HW = False

# ── Monitor helper ────────────────────────────────────────────────────────────
MON_OK = False
helper_error = None

try:
    from wifi.monitor_mode_helper import (
        disable_monitor_mode,
        get_interfaces,
        get_type,
    )
    MON_OK = True
except Exception as e:
    helper_error = e
    try:
        from monitor_mode_helper import (
            disable_monitor_mode,
            get_interfaces,
            get_type,
        )
        MON_OK = True
        helper_error = None
    except Exception as e2:
        helper_error = e2

PINS = {"OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16}
WIDTH, HEIGHT = 128, 128

_running = True
_lcd = None
_font = None


def _cleanup(*_):
    global _running
    _running = False


signal.signal(signal.SIGINT, _cleanup)
signal.signal(signal.SIGTERM, _cleanup)


def _init_hw():
    global _lcd, _font
    if not HAS_HW:
        return

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in PINS.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        _lcd = LCD_1in44.LCD()
        _lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)

        try:
            _font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10
            )
        except Exception:
            _font = ImageFont.load_default()

    except Exception as e:
        print(f"[WARN] LCD init failed: {e}")


def _show(lines, title="STOP MON MODE", title_color=(0, 200, 255), body_color=(0, 220, 0)):
    for ln in lines:
        print(f"  {ln}")

    if not (_lcd and _font):
        return

    try:
        img = Image.new("RGB", (WIDTH, HEIGHT), (10, 0, 0))
        d = ImageDraw.Draw(img)

        d.rectangle((0, 0, WIDTH, 13), fill=(20, 20, 20))
        d.text((2, 1), title[:20], font=_font, fill=title_color)

        y = 16
        for i, ln in enumerate(lines[:7]):
            color = title_color if i == 0 else body_color
            d.text((2, y), str(ln)[:22], font=_font, fill=color)
            y += 15

        _lcd.LCD_ShowImage(img, 0, 0)
    except Exception as e:
        print(f"[WARN] LCD show failed: {e}")


def _wait_key3():
    if not HAS_HW:
        time.sleep(3)
        return

    while _running:
        if GPIO.input(PINS["KEY3"]) == 0:
            break
        time.sleep(0.05)


def _current_monitor_ifaces():
    out = []
    for iface in get_interfaces():
        try:
            if get_type(iface) == "monitor":
                out.append(iface)
        except Exception:
            pass
    return out


def main():
    _init_hw()

    if not MON_OK:
        _show(
            [
                "IMPORT ERROR",
                "monitor helper",
                "not available",
                str(helper_error)[:22],
            ],
            title_color=(255, 0, 0),
            body_color=(255, 160, 0),
        )
        _wait_key3()
        return 1

    _show(["Step 1/3", "Scanning WiFi...", "Looking for", "monitor mode"])
    time.sleep(0.4)

    mon_ifaces = _current_monitor_ifaces()

    if not mon_ifaces:
        _show(
            [
                "NOT ACTIVE",
                "No interface in",
                "monitor mode",
                "Nothing to stop",
            ],
            title_color=(255, 200, 0),
            body_color=(255, 180, 0),
        )
        print("[INFO] No monitor-mode interfaces found")
        _wait_key3()
        return 0

    _show(
        [
            "Step 2/3",
            f"Found: {','.join(mon_ifaces)}"[:22],
            "Restoring mode...",
            "Please wait...",
        ]
    )
    print(f"[INFO] Restoring interfaces: {mon_ifaces}")
    time.sleep(0.3)

    ok = disable_monitor_mode()

    _show(["Step 3/3", "Checking result..."])
    time.sleep(0.3)

    remaining = _current_monitor_ifaces()

    if ok and not remaining:
        _show(
            [
                "RESTORE OK",
                "Managed mode back",
                "Monitor stopped",
                "KEY3 to exit",
            ],
            title_color=(0, 255, 0),
            body_color=(180, 255, 180),
        )
        print("[OK] Monitor mode disabled successfully")
        _wait_key3()
        return 0

    if remaining:
        _show(
            [
                "PARTIAL FAILURE",
                "Still monitor:",
                ",".join(remaining)[:22],
                "Check helper/state",
            ],
            title_color=(255, 120, 0),
            body_color=(255, 180, 0),
        )
        print(f"[WARN] Remaining monitor interfaces: {remaining}")
        _wait_key3()
        return 1

    _show(
        [
            "STOP FAILED",
            "No active monitor",
            "restore confirmed",
            "Check helper logic",
        ],
        title_color=(255, 0, 0),
        body_color=(255, 180, 0),
    )
    print("[ERROR] disable_monitor_mode() did not confirm success")
    _wait_key3()
    return 1


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: requires root")
        sys.exit(1)

    rc = 1
    try:
        rc = main()
    finally:
        if _lcd:
            try:
                _lcd.LCD_Clear()
            except Exception:
                pass
        if HAS_HW:
            try:
                GPIO.cleanup()
            except Exception:
                pass

    raise SystemExit(rc)
