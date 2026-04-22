#!/usr/bin/env python3
# NAME: Loki Autonomous Engine

"""
Loki Autonomous Engine — KTOx_Pi payload
Vendors pineapple_pager_loki and runs it headlessly from the Pi:
  - Clones repo to /root/KTOx/vendor/loki/ on first run
  - Patches SharedData paths (/mmc/ → loot/loki/) and WiFi check
  - Starts Loki's webapp (port 8000) + orchestrator as background process
  - LCD shows install progress, running status, and web UI URL
  - KEY3 → exit payload (Loki keeps running)
  - KEY1 → stop Loki + exit payload
  - KEY2 → re-install Loki
"""

import os, sys, time, subprocess, socket, signal, shutil, threading
from pathlib import Path
from datetime import datetime

# ── Env / Paths ───────────────────────────────────────────────────────────────
LOOT_DIR   = os.environ.get("KTOX_LOOT_DIR", "/root/KTOx/loot")
KTOX_ROOT  = str(Path(LOOT_DIR).parent)          # /root/KTOx

VENDOR_DIR = Path(KTOX_ROOT) / "vendor" / "loki"
LOKI_DIR   = VENDOR_DIR / "payloads" / "user" / "reconnaissance" / "loki"
LOKI_DATA  = Path(LOOT_DIR) / "loki"
LOKI_PID   = Path(LOOT_DIR) / "loki.pid"
LAUNCHER   = LOKI_DIR / "ktox_headless_loki.py"
LOKI_REPO  = "https://github.com/pineapple-pager-projects/pineapple_pager_loki"
LOKI_PORT  = 8000

# ── GPIO pin map (Waveshare 1.44" HAT) ────────────────────────────────────────
PINS = {
    "KEY_UP_PIN":    6,
    "KEY_DOWN_PIN":  19,
    "KEY_LEFT_PIN":  5,
    "KEY_RIGHT_PIN": 26,
    "KEY_PRESS_PIN": 13,
    "KEY1_PIN":      21,   # Back / Stop-Loki
    "KEY2_PIN":      20,   # Home / Re-install
    "KEY3_PIN":      16,   # Stop / Exit-payload
}

# ── Display palette (matches KTOx theme) ─────────────────────────────────────
BG     = "#0a0a0a"
FG     = "#c8c8c8"
RED    = "#8B0000"
GREEN  = "#2ecc40"
ORANGE = "#ff8800"
BLUE   = "#3399ff"
DIM    = "#444444"

FONT_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_MONO  = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# ── Hardware bootstrap ────────────────────────────────────────────────────────
_HW = False
LCD = image = draw = font = small = None

def _init_hw():
    global _HW, LCD, image, draw, font, small
    try:
        import RPi.GPIO as GPIO
        from PIL import Image, ImageDraw, ImageFont
        import LCD_1in44
        import LCD_Config

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in PINS.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        LCD = LCD_1in44.LCD()
        LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
        LCD_Config.Driver_Delay_ms(50)
        image = Image.new("RGB", (LCD.width, LCD.height), BG)
        draw  = ImageDraw.Draw(image)
        font  = ImageFont.truetype(FONT_BOLD, 9)
        small = ImageFont.truetype(FONT_MONO, 8)
        _HW = True
    except Exception:
        pass

def _flush():
    if _HW:
        LCD.LCD_ShowImage(image, 0, 0)

def _key(pin_name):
    if not _HW:
        return False
    try:
        import RPi.GPIO as GPIO
        return GPIO.input(PINS[pin_name]) == 0
    except Exception:
        return False

def _wait_key_release(pin_name, timeout=0.5):
    """Debounce: wait for key to be released."""
    t = time.time()
    while time.time() - t < timeout:
        if not _key(pin_name):
            break
        time.sleep(0.02)

# ── Network helpers ───────────────────────────────────────────────────────────
def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def _port_open(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False

# ── Loki process state ────────────────────────────────────────────────────────
_loki_proc: subprocess.Popen | None = None

def _loki_installed() -> bool:
    return LAUNCHER.exists()

def _loki_running() -> bool:
    global _loki_proc
    if _loki_proc is not None and _loki_proc.poll() is None:
        return True
    if LOKI_PID.exists():
        try:
            pid = int(LOKI_PID.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError, PermissionError):
            LOKI_PID.unlink(missing_ok=True)
    return False

def _start_loki() -> tuple[bool, str]:
    global _loki_proc
    if _loki_running():
        return True, "already running"
    if _port_open(LOKI_PORT):
        return False, f"port {LOKI_PORT} in use"
    ip  = _local_ip()
    env = os.environ.copy()
    env["LOKI_DATA_DIR"] = str(LOKI_DATA)
    env["BJORN_IP"]      = ip
    env["LOKI_PID_FILE"] = str(LOKI_PID)
    log = LOKI_DATA / "logs" / "ktox_loki.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    _loki_proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER)],
        env=env,
        stdout=open(log, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(LOKI_DIR),
    )
    time.sleep(3)
    if not _loki_running():
        return False, "check loot/loki/logs"
    return True, f"http://{ip}:{LOKI_PORT}"

def _stop_loki():
    global _loki_proc
    if _loki_proc is not None:
        try:
            _loki_proc.terminate()
            _loki_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _loki_proc.kill()
        _loki_proc = None
    if LOKI_PID.exists():
        try:
            pid = int(LOKI_PID.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except (ValueError, ProcessLookupError):
            pass
        LOKI_PID.unlink(missing_ok=True)
    subprocess.run(["killall", "-q", "nmap"], capture_output=True)

# ── Headless launcher writer ──────────────────────────────────────────────────
def _write_launcher():
    """
    Write ktox_headless_loki.py into vendored Loki payload directory.
    - Monkey-patches SharedData to redirect /mmc/ paths to loot/loki/
    - Replaces Pager wlan0cli WiFi check with standard ip route check
    - Starts webapp (port 8000) + Loki orchestrator, skips LCD display
    """
    code = f'''\
#!/usr/bin/env python3
# ktox_headless_loki.py
# Headless Loki launcher for KTOx_Pi — webapp + orchestrator, no LCD.
# Auto-generated by loki_engine.py — do not edit manually.

import sys, os, threading, signal, logging, time, subprocess

_dir = os.path.dirname(os.path.abspath(__file__))
_lib = os.path.join(_dir, 'lib')
if os.path.exists(_lib) and _lib not in sys.path:
    sys.path.insert(0, _lib)
if _dir not in sys.path:
    sys.path.insert(0, _dir)

os.environ['CRYPTOGRAPHY_OPENSSL_NO_LEGACY'] = '1'

# Redirect /mmc/ Pager paths to KTOx loot directory
_DATA = os.environ.get('LOKI_DATA_DIR', '{LOKI_DATA}')

from shared import SharedData as _SD
_orig = _SD.__init__

def _patch(self, *a, **kw):
    _orig(self, *a, **kw)
    self.datadir             = _DATA
    self.logsdir             = os.path.join(_DATA, 'logs')
    self.output_dir          = os.path.join(_DATA, 'output')
    self.input_dir           = os.path.join(_DATA, 'input')
    self.crackedpwddir       = os.path.join(_DATA, 'output', 'crackedpwd')
    self.datastolendir       = os.path.join(_DATA, 'output', 'datastolen')
    self.zombiesdir          = os.path.join(_DATA, 'output', 'zombies')
    self.vulnerabilities_dir = os.path.join(_DATA, 'output', 'vulnerabilities')
    self.scan_results_dir    = os.path.join(_DATA, 'output', 'vulnerabilities')
    self.netkbfile           = os.path.join(_DATA, 'netkb.csv')
    for d in [self.datadir, self.logsdir, self.output_dir, self.input_dir,
              self.crackedpwddir, self.datastolendir, self.zombiesdir,
              self.vulnerabilities_dir]:
        os.makedirs(d, exist_ok=True)

_SD.__init__ = _patch

# Replace Pager-specific wlan0cli WiFi check with standard Linux check
import Loki as _lm

def _wifi(self):
    try:
        r = subprocess.run(['ip', 'route', 'show', 'default'],
                           capture_output=True, text=True, timeout=5)
        self.wifi_connected = bool(r.stdout.strip())
    except Exception:
        self.wifi_connected = True
    return self.wifi_connected

_lm.Loki.is_wifi_connected = _wifi

from init_shared import shared_data
from Loki import Loki, handle_exit
from webapp import web_thread, handle_exit_web
from logger import Logger

logger = Logger(name='ktox_headless_loki', level=logging.INFO)

if __name__ == '__main__':
    shared_data.load_config()
    bjorn_ip = os.environ.get('BJORN_IP', '')
    if bjorn_ip:
        os.environ['BJORN_IP'] = bjorn_ip
    pid_file = os.environ.get('LOKI_PID_FILE', '')
    if pid_file:
        with open(pid_file, 'w') as _f:
            _f.write(str(os.getpid()))

    shared_data.webapp_should_exit  = False
    shared_data.display_should_exit = True   # no Pager LCD
    web_thread.start()
    logger.info('Loki web interface started on port 8000')

    loki = Loki(shared_data)
    shared_data.loki_instance = loki
    lt = threading.Thread(target=loki.run, daemon=True)
    lt.start()

    signal.signal(signal.SIGINT,  lambda s, f: handle_exit(s, f, lt, lt, web_thread))
    signal.signal(signal.SIGTERM, lambda s, f: handle_exit(s, f, lt, lt, web_thread))
    logger.info('Loki running — open http://0.0.0.0:8000 in your browser')

    while not shared_data.should_exit:
        time.sleep(2)
'''
    LAUNCHER.write_text(code)
    LAUNCHER.chmod(0o755)

# ── LCD drawing helpers ───────────────────────────────────────────────────────
def _border():
    draw.line([(127, 12), (127, 127)], fill=RED, width=5)
    draw.line([(127, 127), (0, 127)],  fill=RED, width=5)
    draw.line([(0, 127), (0, 12)],     fill=RED, width=5)
    draw.line([(0, 12), (128, 12)],    fill=RED, width=5)

def _center(y, text, fnt, color=FG):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    draw.text(((128 - w) // 2, y), text, font=fnt, fill=color)

def _hbar(y, pct, clr=(100, 180, 255)):
    W = 116
    draw.rectangle([6, y, 6 + W, y + 4], fill=(18, 24, 60))
    draw.rectangle([6, y, 6 + max(1, int(W * pct / 100)), y + 4], fill=clr)

# ── LCD screens ───────────────────────────────────────────────────────────────
def _screen_clear():
    draw.rectangle((0, 0, 128, 128), fill=BG)
    _border()

def screen_not_installed():
    _screen_clear()
    _center(15, "LOKI", font, RED)
    draw.line([(4, 27), (124, 27)], fill=DIM)
    _center(33, "Not installed", small, ORANGE)
    draw.line([(4, 58), (124, 58)], fill=DIM)
    _center(64,  "KEY3: install",     small, GREEN)
    _center(76,  "KEY1: exit",        small, DIM)

def screen_installing(step, total, msg):
    _screen_clear()
    _center(15, "LOKI", font, RED)
    _center(27, "INSTALLING", small, ORANGE)
    draw.line([(4, 38), (124, 38)], fill=DIM)
    _hbar(43, int(step / max(total, 1) * 100))
    draw.text((6, 51), msg[:20],           font=small, fill=FG)
    draw.text((6, 62), f"step {step}/{total}", font=small, fill=DIM)
    _center(112, "KEY3: cancel", small, DIM)
    _flush()

def screen_error(msg1, msg2=""):
    _screen_clear()
    _center(15, "LOKI", font, RED)
    draw.line([(4, 27), (124, 27)], fill=DIM)
    _center(38, "ERROR", small, RED)
    draw.text((4, 52), msg1[:20], font=small, fill=ORANGE)
    if msg2:
        draw.text((4, 63), msg2[:20], font=small, fill=DIM)
    _center(112, "KEY3/KEY1: exit", small, DIM)
    _flush()

def screen_starting():
    _screen_clear()
    _center(15, "LOKI", font, RED)
    draw.line([(4, 27), (124, 27)], fill=DIM)
    _center(50, "Starting...", small, ORANGE)
    _center(112, "please wait", small, DIM)
    _flush()

def screen_running(url: str, web_ready: bool, since: str):
    _screen_clear()
    _center(15, "LOKI", font, RED)
    draw.line([(4, 26), (124, 26)], fill=DIM)

    dot_color = GREEN if web_ready else ORANGE
    draw.ellipse([5, 29, 12, 36], fill=dot_color)
    status_label = "WEB READY" if web_ready else "STARTING"
    draw.text((15, 29), status_label, font=small, fill=dot_color)

    draw.line([(4, 40), (124, 40)], fill=DIM)

    # URL split across two lines
    host_port = url.replace("http://", "")
    parts = host_port.split(":")
    draw.text((4, 44), "http://", font=small, fill=DIM)
    draw.text((4, 54), parts[0],  font=small, fill=BLUE)
    draw.text((4, 64), f":{parts[1]}" if len(parts) > 1 else "", font=small, fill=BLUE)

    draw.line([(4, 76), (124, 76)], fill=DIM)
    draw.text((4, 80), since[:20],  font=small, fill=DIM)

    _center(100, "KEY1: stop loki",   small, DIM)
    _center(112, "KEY3: exit (keep)", small, DIM)
    _flush()

def screen_stopped(msg=""):
    _screen_clear()
    _center(15, "LOKI", font, RED)
    draw.line([(4, 26), (124, 26)], fill=DIM)
    draw.ellipse([5, 29, 12, 36], fill=DIM)
    draw.text((15, 29), "STOPPED", font=small, fill=DIM)
    draw.line([(4, 40), (124, 40)], fill=DIM)
    if msg:
        draw.text((4, 44), msg[:20], font=small, fill=ORANGE)
    _center(88,  "KEY3: start",     small, GREEN)
    _center(100, "KEY1: exit",      small, DIM)
    _center(112, "KEY2: reinstall", small, DIM)
    _flush()

# ── Install ───────────────────────────────────────────────────────────────────
class _Cancelled(Exception):
    pass

def _install_step(step, total, msg):
    print(f"[{step}/{total}] {msg}")
    if not _HW:
        return
    screen_installing(step, total, msg)
    time.sleep(0.05)
    if _key("KEY3_PIN"):
        raise _Cancelled

def install_loki():
    try:
        _install_step(1, 6, "Checking nmap...")
        if not shutil.which("nmap"):
            subprocess.run(["apt-get", "install", "-y", "nmap"], capture_output=True)

        _install_step(2, 6, "Cloning repo...")
        VENDOR_DIR.parent.mkdir(parents=True, exist_ok=True)
        if VENDOR_DIR.exists() and (VENDOR_DIR / ".git").exists():
            r = subprocess.run(
                ["git", "-C", str(VENDOR_DIR), "pull"],
                capture_output=True, timeout=120
            )
        else:
            if VENDOR_DIR.exists():
                shutil.rmtree(VENDOR_DIR)
            r = subprocess.run(
                ["git", "clone", "--depth=1", LOKI_REPO, str(VENDOR_DIR)],
                capture_output=True, timeout=300
            )
        if r.returncode != 0:
            return False, "git clone failed"

        _install_step(3, 6, "Creating dirs...")
        for sub in ["logs", "output/crackedpwd", "output/datastolen",
                    "output/zombies", "output/vulnerabilities", "input"]:
            (LOKI_DATA / sub).mkdir(parents=True, exist_ok=True)

        _install_step(4, 6, "Writing launcher...")
        _write_launcher()

        _install_step(5, 6, "Verifying...")
        if not LAUNCHER.exists():
            return False, "launcher missing"

        _install_step(6, 6, "Done!")
        time.sleep(1)
        return True, "ok"

    except _Cancelled:
        return False, "cancelled"
    except Exception as e:
        return False, str(e)[:20]

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    _init_hw()
    ip  = _local_ip()
    url = f"http://{ip}:{LOKI_PORT}"

    # ── First-run: prompt to install ──────────────────────────────────────
    if not _loki_installed():
        print("[loki_engine] Loki not installed.")
        if _HW:
            screen_not_installed()
            # Wait up to 15 s for user input
            deadline = time.time() + 15
            chosen = None
            while time.time() < deadline and chosen is None:
                if _key("KEY3_PIN"):
                    _wait_key_release("KEY3_PIN")
                    chosen = "install"
                elif _key("KEY1_PIN"):
                    _wait_key_release("KEY1_PIN")
                    chosen = "exit"
                time.sleep(0.05)
            if chosen == "exit" or chosen is None:
                return
        else:
            chosen = "install"

        print("[loki_engine] Installing Loki...")
        ok, msg = install_loki()
        if not ok:
            print(f"[loki_engine] Install failed: {msg}")
            if _HW:
                screen_error("Install failed", msg)
                time.sleep(4)
            return

    # ── Auto-start Loki ───────────────────────────────────────────────────
    if not _loki_running():
        print(f"[loki_engine] Starting Loki → {url}")
        if _HW:
            screen_starting()
        ok, result = _start_loki()
        if not ok:
            print(f"[loki_engine] Start failed: {result}")
            if _HW:
                screen_error("Start failed", result)
                time.sleep(4)
            return
        print(f"[loki_engine] Loki running at {result}")
    else:
        print(f"[loki_engine] Loki already running at {url}")

    # ── Main display loop ─────────────────────────────────────────────────
    start_ts = datetime.now().strftime("%H:%M:%S")
    since_label = f"since {start_ts}"

    while True:
        running = _loki_running()

        if running:
            web_up = _port_open(LOKI_PORT)
            if _HW:
                screen_running(url, web_up, since_label)
            else:
                print(f"\r[loki_engine] {'WEB READY' if web_up else 'STARTING':10s}  {url}", end="", flush=True)
        else:
            if _HW:
                screen_stopped()
            else:
                print("\r[loki_engine] STOPPED                                    ", end="", flush=True)

        # Button / input polling at ~10 Hz
        for _ in range(10):
            time.sleep(0.1)

            if running:
                if _key("KEY1_PIN"):           # Stop Loki + exit payload
                    _wait_key_release("KEY1_PIN")
                    print("\n[loki_engine] Stopping Loki...")
                    _stop_loki()
                    return
                if _key("KEY3_PIN"):           # Exit payload, Loki keeps running
                    _wait_key_release("KEY3_PIN")
                    print(f"\n[loki_engine] Exiting — Loki continues at {url}")
                    return
            else:
                if _key("KEY3_PIN"):           # Start Loki
                    _wait_key_release("KEY3_PIN")
                    if _HW:
                        screen_starting()
                    ok, result = _start_loki()
                    if ok:
                        start_ts    = datetime.now().strftime("%H:%M:%S")
                        since_label = f"since {start_ts}"
                    else:
                        if _HW:
                            screen_error("Start failed", result)
                            time.sleep(3)
                    break
                if _key("KEY1_PIN"):           # Exit payload
                    _wait_key_release("KEY1_PIN")
                    return
                if _key("KEY2_PIN"):           # Re-install Loki
                    _wait_key_release("KEY2_PIN")
                    ok, msg = install_loki()
                    if not ok and _HW:
                        screen_error("Install failed", msg)
                        time.sleep(3)
                    break


if __name__ == "__main__":
    main()
