#!/usr/bin/env python3
# NAME: Going Dark
"""
KTOx Payload -- Going Dark
---------------------------
Anonymity engine inspired by kali-whoami (owerdogan/whoami-project).

Activates privacy modules non-interactively:
  - Tor transparent proxy     route all traffic through Tor
  - MAC randomization         change MAC on every interface
  - Hostname randomization    replace hostname with a random string
  - DNS privacy               swap ISP DNS for Cloudflare / Quad9
  - Log cleaner               truncate system log files
  - IPv6 disable              prevent IPv6 leaks
  - Timezone UTC              strip timezone fingerprint
  - Browser stealth           clear browser caches / cookies

On stop, uses `kali-whoami --stop` if installed, then restores every
change from saved backups.

Controls:
  UP / DOWN  -- scroll module list
  OK         -- toggle Going Dark on / off
  KEY1       -- toggle highlighted module individually
  KEY2       -- status check
  KEY3       -- exit  (auto-stops if currently active)
"""

import os
import sys
import pwd
import time
import random
import string
import shutil
import subprocess
import threading
import json

sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..", "..")))

import RPi.GPIO as GPIO
import LCD_1in44
import LCD_Config
from PIL import Image, ImageDraw, ImageFont
from payloads._display_helper import ScaledDraw, scaled_font
from payloads._input_helper import get_button

# ---------------------------------------------------------------------------
# Hardware init
# ---------------------------------------------------------------------------
PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}
GPIO.setmode(GPIO.BCM)
for _pin in PINS.values():
    GPIO.setup(_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
WIDTH, HEIGHT = LCD.width, LCD.height
font = scaled_font()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOOT_DIR    = os.environ.get("KTOX_LOOT_DIR", "/root/KTOx/loot")
BACKUP_FILE = os.path.join(LOOT_DIR, "goingdark_backup.json")
LOG_FILE    = os.path.join(LOOT_DIR, "goingdark.log")

PRIVACY_DNS    = ["1.1.1.1", "9.9.9.9"]
TOR_DNS_PORT   = 5353
TOR_TRANS_PORT = 9040

ROWS_VISIBLE = 6
DEBOUNCE     = 0.25

# ---------------------------------------------------------------------------
# Module definitions
# ---------------------------------------------------------------------------
MODULES = [
    {"id": "tor",      "label": "Tor Proxy"},
    {"id": "mac",      "label": "MAC Randomize"},
    {"id": "hostname", "label": "Rand Hostname"},
    {"id": "dns",      "label": "DNS Privacy"},
    {"id": "logs",     "label": "Log Cleaner"},
    {"id": "ipv6",     "label": "IPv6 Disable"},
    {"id": "timezone", "label": "Timezone UTC"},
    {"id": "browser",  "label": "Browser Stealth"},
]

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_lock        = threading.Lock()
_draw_lock   = threading.Lock()   # serialises all LCD writes
_dark_active = False
_mod_enabled = {m["id"]: True for m in MODULES}
_scroll_pos  = 0
_status_msg  = "Ready"
_backups     = {}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _run(cmd, timeout=30):
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return res.returncode, (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as exc:
        return 1, str(exc)[:60]


def _log(msg):
    try:
        os.makedirs(LOOT_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _random_hostname():
    return "host-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _get_interfaces():
    try:
        return [e for e in os.listdir("/sys/class/net") if e != "lo"]
    except Exception:
        return ["eth0", "wlan0"]


def _get_mac(iface):
    try:
        with open(f"/sys/class/net/{iface}/address") as f:
            return f.read().strip()
    except Exception:
        return ""


def _random_mac():
    octets = [random.randint(0, 255) for _ in range(6)]
    octets[0] = (octets[0] & 0xFE) | 0x02   # locally administered, unicast
    return ":".join(f"{b:02x}" for b in octets)


def _tor_uid():
    """Return the uid of the tor daemon user as a string."""
    for name in ("debian-tor", "_tor", "tor"):
        try:
            return str(pwd.getpwnam(name).pw_uid)
        except KeyError:
            continue
    return "107"   # last-resort fallback


def _write_resolv(content):
    """Write content to the real resolv.conf, following symlinks."""
    real = os.path.realpath("/etc/resolv.conf")
    try:
        with open(real, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        _log(f"resolv write failed ({real}): {e}")
        return False


def _set_status(msg):
    """Update status string and redraw. Safe to call from any thread."""
    global _status_msg
    with _lock:
        _status_msg = msg
    _draw_screen()


# ---------------------------------------------------------------------------
# Module — ENABLE
# ---------------------------------------------------------------------------

def _enable_tor():
    global _backups
    torrc_extra = (
        "\n# Going Dark\n"
        f"VirtualAddrNetworkIPv4 10.192.0.0/10\n"
        f"AutomapHostsOnResolve 1\n"
        f"TransPort 0.0.0.0:{TOR_TRANS_PORT}\n"
        f"DNSPort 0.0.0.0:{TOR_DNS_PORT}\n"
    )
    try:
        with open("/etc/tor/torrc", "a") as f:
            f.write(torrc_extra)
    except Exception as e:
        _log(f"torrc write failed: {e}")

    _run(["systemctl", "restart", "tor"], timeout=20)
    time.sleep(3)

    uid = _tor_uid()
    rules = [
        ["-t", "nat", "-A", "OUTPUT", "-m", "owner", "--uid-owner", uid, "-j", "RETURN"],
        ["-t", "nat", "-A", "OUTPUT", "-p", "udp", "--dport", "53",
         "-j", "REDIRECT", "--to-ports", str(TOR_DNS_PORT)],
        ["-t", "nat", "-A", "OUTPUT", "-p", "tcp", "--syn",
         "-j", "REDIRECT", "--to-ports", str(TOR_TRANS_PORT)],
    ]
    _backups["tor_rules"] = rules
    for r in rules:
        rc, out = _run(["iptables"] + r)
        if rc != 0:
            _log(f"iptables add failed: {out}")
    _log(f"Tor proxy enabled (uid={uid})")
    return True


def _enable_mac():
    global _backups
    saved = {}
    for iface in _get_interfaces():
        saved[iface] = _get_mac(iface)
        new_mac = _random_mac()
        _run(["ip", "link", "set", iface, "down"])
        _run(["ip", "link", "set", iface, "address", new_mac])
        _run(["ip", "link", "set", iface, "up"])
    _backups["macs"] = saved
    _log(f"MAC randomized: {list(saved.keys())}")
    return True


def _enable_hostname():
    global _backups
    rc, orig = _run(["hostname"])
    _backups["hostname"] = orig.strip() if rc == 0 else "raspberrypi"
    new_name = _random_hostname()
    _run(["hostnamectl", "set-hostname", new_name])
    _log(f"Hostname → {new_name}")
    return True


def _enable_dns():
    global _backups
    real = os.path.realpath("/etc/resolv.conf")
    try:
        with open(real, "r") as f:
            _backups["resolv"] = f.read()
    except Exception:
        _backups["resolv"] = ""
    content = "\n".join(f"nameserver {ns}" for ns in PRIVACY_DNS) + "\n"
    ok = _write_resolv(content)
    if ok:
        _log("DNS → Cloudflare/Quad9")
    return ok


def _enable_logs():
    log_paths = [
        "/var/log/syslog", "/var/log/auth.log", "/var/log/messages",
        "/var/log/kern.log", "/var/log/daemon.log",
    ]
    _run(["journalctl", "--vacuum-size=1M"])
    for p in log_paths:
        if os.path.exists(p):
            try:
                open(p, "w").close()
            except Exception:
                _run(["truncate", "-s", "0", p])
    _log("Logs cleared")
    return True


def _enable_ipv6():
    global _backups
    _backups["ipv6_all"] = _run(["sysctl", "-n", "net.ipv6.conf.all.disable_ipv6"])[1]
    _backups["ipv6_def"] = _run(["sysctl", "-n", "net.ipv6.conf.default.disable_ipv6"])[1]
    _run(["sysctl", "-w", "net.ipv6.conf.all.disable_ipv6=1"])
    _run(["sysctl", "-w", "net.ipv6.conf.default.disable_ipv6=1"])
    _log("IPv6 disabled")
    return True


def _enable_timezone():
    global _backups
    rc, orig = _run(["timedatectl", "show", "--property=Timezone", "--value"])
    _backups["timezone"] = orig.strip() if rc == 0 else "UTC"
    _run(["timedatectl", "set-timezone", "UTC"])
    _log(f"Timezone UTC (was {_backups['timezone']})")
    return True


def _enable_browser():
    cache_dirs = [
        "/root/.cache/chromium",
        "/root/.cache/google-chrome",
        "/root/.mozilla/firefox",
        os.path.expanduser("~/.cache/chromium"),
        os.path.expanduser("~/.cache/google-chrome"),
        os.path.expanduser("~/.mozilla/firefox"),
    ]
    cleared = 0
    seen = set()
    for d in cache_dirs:
        real = os.path.realpath(d)
        if real in seen or not os.path.isdir(real):
            continue
        seen.add(real)
        shutil.rmtree(real, ignore_errors=True)
        cleared += 1
    _log(f"Browser caches cleared: {cleared} dirs")
    return True


_ENABLE = {m["id"]: globals()[f"_enable_{m['id']}"] for m in MODULES}


# ---------------------------------------------------------------------------
# Module — DISABLE / RESTORE
# ---------------------------------------------------------------------------

def _disable_tor():
    # Delete only the rules we added (by replaying -A as -D)
    for rule in _backups.get("tor_rules", []):
        delete = [r if r != "-A" else "-D" for r in rule]
        _run(["iptables"] + delete)
    # Strip Going Dark lines from torrc
    try:
        with open("/etc/tor/torrc", "r") as f:
            lines = f.readlines()
        with open("/etc/tor/torrc", "w") as f:
            skip = False
            for line in lines:
                if line.strip() == "# Going Dark":
                    skip = True
                if not skip:
                    f.write(line)
    except Exception:
        pass
    _run(["systemctl", "restart", "tor"], timeout=20)
    _log("Tor proxy removed")


def _disable_mac():
    for iface, orig_mac in _backups.get("macs", {}).items():
        if orig_mac:
            _run(["ip", "link", "set", iface, "down"])
            _run(["ip", "link", "set", iface, "address", orig_mac])
            _run(["ip", "link", "set", iface, "up"])
    _log("MACs restored")


def _disable_hostname():
    orig = _backups.get("hostname") or "raspberrypi"
    _run(["hostnamectl", "set-hostname", orig])
    _log(f"Hostname restored → {orig}")


def _disable_dns():
    orig = _backups.get("resolv", "")
    if orig:
        _write_resolv(orig)
        _log("DNS restored")


def _disable_ipv6():
    v_all = _backups.get("ipv6_all", "0")
    v_def = _backups.get("ipv6_def", "0")
    _run(["sysctl", "-w", f"net.ipv6.conf.all.disable_ipv6={v_all}"])
    _run(["sysctl", "-w", f"net.ipv6.conf.default.disable_ipv6={v_def}"])
    _log("IPv6 restored")


def _disable_timezone():
    orig = _backups.get("timezone") or "UTC"
    _run(["timedatectl", "set-timezone", orig])
    _log(f"Timezone restored → {orig}")


_DISABLE = {
    "tor":      _disable_tor,
    "mac":      _disable_mac,
    "hostname": _disable_hostname,
    "dns":      _disable_dns,
    "ipv6":     _disable_ipv6,
    "timezone": _disable_timezone,
    # logs + browser are one-way — no restore needed
}


# ---------------------------------------------------------------------------
# Core start / stop
# ---------------------------------------------------------------------------

def _start_dark():
    global _dark_active, _status_msg

    _set_status("Saving state...")
    os.makedirs(LOOT_DIR, exist_ok=True)

    with _lock:
        enabled = {m["id"]: _mod_enabled[m["id"]] for m in MODULES}

    results = {}
    for mod in MODULES:
        mid = mod["id"]
        if not enabled[mid]:
            continue
        _set_status(f"Starting {mod['label']}...")
        try:
            results[mid] = _ENABLE[mid]()
        except Exception as exc:
            _log(f"{mid} error: {exc}")
            results[mid] = False

    try:
        with open(BACKUP_FILE, "w") as f:
            json.dump(_backups, f)
    except Exception:
        pass

    failed = [m["label"] for m in MODULES
              if enabled.get(m["id"]) and results.get(m["id"]) is False]

    with _lock:
        _dark_active = True
        _status_msg = f"DARK ({len(failed)} fail)" if failed else "GOING DARK active"

    _log("Going Dark activated")
    _draw_screen()


def _stop_dark():
    global _dark_active, _status_msg

    _set_status("Restoring identity...")

    # Optional: let kali-whoami do its own cleanup if installed
    kw = shutil.which("kali-whoami")
    if kw:
        _set_status("whoami --stop ...")
        _run([kw, "--stop"], timeout=30)

    # Load persisted backups if needed (e.g. after process restart)
    if not _backups:
        try:
            with open(BACKUP_FILE, "r") as f:
                _backups.update(json.load(f))
        except Exception:
            pass

    with _lock:
        enabled = {m["id"]: _mod_enabled[m["id"]] for m in MODULES}

    for mod in MODULES:
        mid = mod["id"]
        if not enabled.get(mid):
            continue
        fn = _DISABLE.get(mid)
        if fn:
            try:
                fn()
            except Exception as exc:
                _log(f"restore {mid}: {exc}")

    try:
        os.remove(BACKUP_FILE)
    except Exception:
        pass

    with _lock:
        _dark_active = False
        _status_msg = "Identity restored"

    _log("Going Dark deactivated")
    _draw_screen()


def _check_status():
    global _dark_active, _status_msg

    kw = shutil.which("kali-whoami")
    if kw:
        rc, out = _run([kw, "--status"], timeout=15)
        _log(f"status check: {out}")
        lower = out.lower()
        with _lock:
            if "start" in lower or "active" in lower or "running" in lower:
                _dark_active = True
                _status_msg = "Active (whoami)"
            elif "stop" in lower or "not active" in lower or "inactive" in lower:
                _dark_active = False
                _status_msg = "Inactive (whoami)"
            else:
                _status_msg = out[:26] if out else "No status"
    else:
        with _lock:
            _status_msg = "DARK active" if _dark_active else "Not active"

    _draw_screen()


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _draw_splash():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ScaledDraw(img)
    d.rectangle((0, 0, 127, 18), fill="#001133")
    d.text((20, 3),  "GOING DARK",           font=font, fill="#0099ff")
    d.text((4,  24), "Tor+MAC+DNS+IPv6+more", font=font, fill="#555555")
    d.text((4,  38), "OK  = activate all",   font=font, fill="#666666")
    d.text((4,  50), "K1  = toggle module",  font=font, fill="#666666")
    d.text((4,  62), "K2  = status check",   font=font, fill="#666666")
    d.text((4,  74), "K3  = exit",           font=font, fill="#666666")
    with _draw_lock:
        LCD.LCD_ShowImage(img, 0, 0)


def _draw_screen():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ScaledDraw(img)

    with _lock:
        active = _dark_active
        states = dict(_mod_enabled)
        msg    = _status_msg
        sc     = _scroll_pos

    # Header banner
    if active:
        d.rectangle((0, 0, 127, 18), fill="#001133")
        d.text((8, 3), ">> GOING DARK <<", font=font, fill="#0099ff")
    else:
        d.rectangle((0, 0, 127, 18), fill="#220000")
        d.text((12, 3), "GOING DARK  off",  font=font, fill="#ff3333")

    # Module checklist
    y = 22
    for i, mod in enumerate(MODULES[sc: sc + ROWS_VISIBLE]):
        enabled   = states.get(mod["id"], True)
        is_cursor = (i == 0)
        check     = "[X]" if enabled else "[ ]"
        c_col     = "#00ccff" if enabled else "#444444"
        l_col     = "#ffffff" if is_cursor else "#aaaaaa"
        d.text((2,  y), check,              font=font, fill=c_col)
        d.text((24, y), mod["label"][:15],  font=font, fill=l_col)
        y += 12

    # Scroll indicators
    if sc > 0:
        d.text((118, 22), "^", font=font, fill="#555555")
    if sc + ROWS_VISIBLE < len(MODULES):
        d.text((118, 22 + (ROWS_VISIBLE - 1) * 12), "v", font=font, fill="#555555")

    # Status line
    d.line((0, 100, 127, 100), fill="#222222")
    d.text((2, 102), msg[:22], font=font, fill="#ffcc00")

    # Footer
    d.rectangle((0, 116, 127, 127), fill="#111111")
    d.text((2, 117), "OK:go K1:mod K2:stat K3:X", font=font, fill="#666666")

    with _draw_lock:
        LCD.LCD_ShowImage(img, 0, 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _scroll_pos, _status_msg

    _draw_splash()
    time.sleep(1.2)

    last_press = 0.0

    try:
        while True:
            btn = get_button(PINS, GPIO)
            now = time.time()

            if btn and (now - last_press) < DEBOUNCE:
                btn = None
            if btn:
                last_press = now

            if btn == "KEY3":
                break

            elif btn == "OK":
                with _lock:
                    active = _dark_active
                target = _stop_dark if active else _start_dark
                threading.Thread(target=target, daemon=True).start()

            elif btn == "KEY1":
                with _lock:
                    mid = MODULES[_scroll_pos]["id"]
                    _mod_enabled[mid] = not _mod_enabled[mid]
                    label = MODULES[_scroll_pos]["label"]
                    state = "ON" if _mod_enabled[mid] else "OFF"
                    _status_msg = f"{label}: {state}"

            elif btn == "KEY2":
                threading.Thread(target=_check_status, daemon=True).start()

            elif btn == "UP":
                with _lock:
                    _scroll_pos = max(0, _scroll_pos - 1)

            elif btn == "DOWN":
                with _lock:
                    _scroll_pos = min(len(MODULES) - 1, _scroll_pos + 1)

            _draw_screen()
            time.sleep(0.06)

    finally:
        with _lock:
            active = _dark_active
        if active:
            # Run stop in a thread with a hard cap so KEY3 doesn't hang forever
            t = threading.Thread(target=_stop_dark, daemon=True)
            t.start()
            t.join(timeout=45)
        try:
            LCD.LCD_Clear()
        except Exception:
            pass
        GPIO.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
