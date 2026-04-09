#!/usr/bin/env python3
"""
KTOx Payload – BT Audio Pair
==============================
Scan for Bluetooth speakers/headphones, pair & connect, and set as
the default PulseAudio/PipeWire audio sink so media plays through them.

Controls:
  UP / DOWN   Browse discovered devices
  OK          Pair + connect (or disconnect if already connected)
  KEY1        Disconnect current device & rescan
  KEY2        Force-set selected device as default audio sink
  KEY3        Exit payload
"""

import os, sys, time, subprocess, re

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

PINS = {"UP":6, "DOWN":19, "LEFT":5, "RIGHT":26, "OK":13, "KEY1":21, "KEY2":20, "KEY3":16}
SCAN_SECONDS = 12


# ── LCD ────────────────────────────────────────────────────────────────────────

_lcd       = None
_image     = None
_draw      = None
_font_bold = None
_font_sm   = None


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _init_lcd():
    global _lcd, _image, _draw, _font_bold, _font_sm
    _lcd = LCD_1in44.LCD()
    _lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    _lcd.LCD_Clear()
    _image = Image.new("RGB", (128, 128), "black")
    _draw  = ImageDraw.Draw(_image)
    _font_bold = _load_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    _font_sm   = _load_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)


def _show():
    if _lcd:
        _lcd.LCD_ShowImage(_image, 0, 0)


def _draw_header(title, bg=(50, 0, 100)):
    _draw.rectangle([(0, 0), (128, 16)], fill=bg)
    _draw.text((4, 3), title[:21], font=_font_sm, fill=(200, 150, 255))


def _draw_footer(text):
    _draw.rectangle([(0, 112), (128, 128)], fill=(20, 20, 20))
    _draw.text((4, 114), text, font=_font_sm, fill=(110, 110, 110))


def _show_status(msg, color=(200, 200, 200)):
    _draw.rectangle([(0, 0), (128, 128)], fill=(5, 0, 15))
    _draw_header("BT AUDIO PAIR", (50, 0, 100))
    y = 26
    for line in msg.split("\n"):
        _draw.text((4, y), line[:21], font=_font_sm, fill=color)
        y += 14
    _show()


# ── Bluetooth helpers ──────────────────────────────────────────────────────────

def _bt_cmd(cmd_str, timeout=15):
    """Run one or more bluetoothctl commands non-interactively."""
    try:
        # Escape single quotes in MAC addresses etc.
        escaped = cmd_str.replace("'", "\\'")
        full = f"printf '{escaped}\\nexit\\n' | bluetoothctl"
        r = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception as e:
        return str(e)


def _scan_devices():
    """Power on BT, scan for SCAN_SECONDS, return list of {mac, name} dicts."""
    _show_status("Powering on\nBluetooth...", (150, 200, 255))
    _bt_cmd("power on")
    time.sleep(1)

    scan_proc = subprocess.Popen(
        ["bluetoothctl", "scan", "on"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    for i in range(SCAN_SECONDS, 0, -1):
        _show_status(
            f"Scanning...\n{i}s remaining\n\n\nKEY3 = Cancel",
            (150, 200, 255)
        )
        if HAS_HW and GPIO.input(PINS["KEY3"]) == 0:
            break
        time.sleep(1)

    scan_proc.terminate()
    try:
        scan_proc.wait(timeout=2)
    except Exception:
        scan_proc.kill()

    _bt_cmd("scan off", timeout=3)
    _show_status("Processing...", (200, 200, 100))

    raw = _bt_cmd("devices", timeout=5)
    devices = []
    seen    = set()
    pat     = re.compile(r"Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+(.+)")

    for line in raw.splitlines():
        m = pat.search(line)
        if m:
            mac  = m.group(1).upper()
            name = m.group(2).strip()
            if mac not in seen:
                seen.add(mac)
                devices.append({"mac": mac, "name": name})

    return devices


def _connect_device(dev):
    mac  = dev["mac"]
    name = dev["name"]

    _show_status(f"Pairing...\n{name[:18]}", (200, 200, 100))
    _bt_cmd(f"pair {mac}", timeout=20)
    time.sleep(0.5)

    _show_status(f"Trusting...\n{name[:18]}", (200, 200, 100))
    _bt_cmd(f"trust {mac}", timeout=5)
    time.sleep(0.5)

    _show_status(f"Connecting...\n{name[:18]}", (200, 200, 100))
    out = _bt_cmd(f"connect {mac}", timeout=20)
    time.sleep(1.0)

    if "Connection successful" in out or "Connected: yes" in out:
        return True

    # Double-check via info
    info = _bt_cmd(f"info {mac}", timeout=5)
    return "Connected: yes" in info


def _disconnect_device(mac):
    _bt_cmd(f"disconnect {mac}", timeout=10)


def _get_connected_mac():
    """Return the MAC of the currently connected BT device, or None."""
    try:
        out = subprocess.run(
            ["bluetoothctl", "info"],
            capture_output=True, text=True, timeout=5
        ).stdout
        m = re.search(r"Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})", out)
        if m and "Connected: yes" in out:
            return m.group(1).upper()
    except Exception:
        pass
    return None


def _set_default_sink(mac):
    """Try to set BT device as default PulseAudio/PipeWire audio output."""
    # PulseAudio / PipeWire (pactl)
    try:
        sinks_raw = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=5
        ).stdout
        mac_under = mac.replace(":", "_").lower()
        for line in sinks_raw.splitlines():
            line_low = line.lower()
            if mac_under in line_low or "bluez" in line_low or "a2dp" in line_low:
                sink_name = line.split()[1]
                subprocess.run(
                    ["pactl", "set-default-sink", sink_name],
                    timeout=5, capture_output=True
                )
                return True, sink_name
    except Exception:
        pass

    # Fallback: ALSA bluealsa
    try:
        subprocess.run(
            ["amixer", "-D", "bluealsa", "cset", "name='Master Playback Volume'", "80%"],
            capture_output=True, timeout=5
        )
        return True, "bluealsa"
    except Exception:
        pass

    return False, None


# ── Device list drawing ────────────────────────────────────────────────────────

def _draw_device_list(devices, sel, connected_mac):
    _draw.rectangle([(0, 0), (128, 128)], fill=(5, 0, 15))
    count = f"({len(devices)})" if devices else ""
    _draw_header(f"BT AUDIO PAIR {count}", (50, 0, 100))

    if not devices:
        _draw.text((8,  45), "No devices found.", font=_font_sm, fill=(150, 150, 150))
        _draw.text((8,  60), "KEY1 = Rescan",     font=_font_sm, fill=(100, 100, 200))
        _draw_footer("KEY3=Exit")
        _show()
        return

    max_items = 6
    start = max(0, sel - max_items + 1) if sel >= max_items else 0
    y = 20

    for i in range(max_items):
        idx = start + i
        if idx >= len(devices):
            break
        dev    = devices[idx]
        is_sel = (idx == sel)
        is_con = (dev["mac"] == connected_mac)

        if is_sel:
            _draw.rectangle([(0, y - 1), (128, y + 12)], fill=(40, 0, 80))

        icon     = "\u2714" if is_con else "\u25cf"
        icon_col = (0, 255, 100) if is_con else (90, 90, 180)
        name_col = (0, 255, 150) if is_con else ((220, 180, 255) if is_sel else (170, 170, 210))
        label    = dev["name"][:16]

        _draw.text((4,  y), icon,  font=_font_sm, fill=icon_col)
        _draw.text((16, y), label, font=_font_sm, fill=name_col)
        y += 13

    _draw_footer("OK=Conn K1=Scan K2=Snk")
    _show()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not HAS_HW:
        print("[bt_audio_pair] No hardware — cannot run.")
        return

    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    _init_lcd()

    devices       = _scan_devices()
    sel           = 0
    connected_mac = _get_connected_mac()
    _held         = {}

    try:
        while True:
            _draw_device_list(devices, sel, connected_mac)

            now     = time.time()
            pressed = {n: GPIO.input(p) == 0 for n, p in PINS.items()}
            for n, down in pressed.items():
                if down:
                    _held.setdefault(n, now)
                else:
                    _held.pop(n, None)

            def jp(name):
                return pressed.get(name) and (now - _held.get(name, now)) <= 0.06

            if jp("KEY3"):
                break

            elif jp("UP"):
                sel = max(0, sel - 1)
            elif jp("DOWN"):
                sel = min(len(devices) - 1, sel + 1) if devices else 0

            elif jp("KEY1"):
                # Disconnect current + rescan
                if connected_mac:
                    _show_status("Disconnecting...", (200, 100, 100))
                    _disconnect_device(connected_mac)
                    connected_mac = None
                    time.sleep(0.8)
                devices = _scan_devices()
                sel     = 0
                connected_mac = _get_connected_mac()

            elif jp("KEY2") and devices:
                # Force-set selected device as audio sink
                dev = devices[sel]
                ok, sink = _set_default_sink(dev["mac"])
                if ok:
                    _show_status(f"Sink set!\n{sink[:18]}", (0, 255, 100))
                else:
                    _show_status("Sink failed.\nCheck PulseAudio\nor PipeWire.", (255, 100, 100))
                time.sleep(2)

            elif jp("OK") and devices:
                dev = devices[sel]
                if dev["mac"] == connected_mac:
                    # Already connected — disconnect
                    _show_status(f"Disconnecting\n{dev['name'][:18]}...", (200, 100, 100))
                    _disconnect_device(dev["mac"])
                    connected_mac = None
                    time.sleep(1)
                else:
                    ok = _connect_device(dev)
                    if ok:
                        connected_mac = dev["mac"]
                        # Auto-route audio
                        _set_default_sink(dev["mac"])
                        _show_status(
                            f"Connected!\n{dev['name'][:18]}\n\nAudio routed.\nKEY2=Re-set sink",
                            (0, 255, 100)
                        )
                    else:
                        _show_status(
                            f"Failed to\nconnect to\n{dev['name'][:18]}",
                            (255, 80, 80)
                        )
                    time.sleep(2)
                    connected_mac = _get_connected_mac()

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        if _lcd:
            _lcd.LCD_Clear()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
