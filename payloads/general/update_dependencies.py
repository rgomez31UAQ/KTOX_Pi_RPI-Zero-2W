#!/usr/bin/env python3
"""
KTOx *payload* – **Dependency Checker & Installer**
====================================================
This payload checks for missing dependencies and installs them.

Features:
- Scans for missing APT and PIP packages
- Displays missing dependencies on LCD
- Installs only what's needed
- Shows real-time installation progress on LCD
- Graceful exit via KEY3 or Ctrl-C

Controls:
- SCAN SCREEN:
    - OK: Start installation of missing packages
    - KEY3: Cancel and exit
- INSTALLATION SCREEN:
    - KEY3: Abort and exit
"""

import sys
import os
import time
import signal
import subprocess
import threading

# Add KTOx root to path for imports
KTOX_ROOT = '/root/KTOx'
if os.path.isdir(KTOX_ROOT) and KTOX_ROOT not in sys.path:
    sys.path.insert(0, KTOX_ROOT)

# Try to import hardware libraries, fallback to headless mode
HEADLESS_MODE = False
LCD = None
try:
    import RPi.GPIO as GPIO
    import LCD_Config
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HEADLESS_MODE = False
except ImportError:
    HEADLESS_MODE = True
    class FakeImage:
        def __init__(self, *args, **kwargs): pass
    class FakeDraw:
        def text(self, *args, **kwargs): pass
        def line(self, *args, **kwargs): pass
        def rectangle(self, *args, **kwargs): pass
    Image = FakeImage
    ImageDraw = type('ImageDraw', (), {'Draw': lambda x: FakeDraw()})()
    ImageFont = type('ImageFont', (), {'load_default': lambda: None, 'truetype': lambda *a: None})()
    GPIO = None

# --- Global State ---
PINS = {"OK": 13, "KEY3": 16}
RUNNING = True
INSTALL_THREAD = None
UI_LOCK = threading.Lock()
STATUS_LINES = []
MISSING_APT = []
MISSING_PIP = []

# --- Complete Dependency List ---
# APT packages required by all payloads
APT_PACKAGES = [
    # Core system tools
    "git", "curl", "wget", "nano", "vim",
    # Bluetooth & Hardware
    "bluez", "bluez-tools",
    # WiFi & Network Core
    "aircrack-ng", "hcxtools", "hcxdumptool", "mdk4",
    "wireless-tools", "wpasupplicant", "iw", "arp-scan",
    "nmap", "tcpdump", "net-tools",
    # MITM & Interception
    "mitmproxy", "responder", "dnsmasq", "hostapd",
    # Credential & Exploitation
    "hashcat", "john", "hydra", "sshpass",
    "enum4linux", "impacket-scripts", "smbclient",
    # Reconnaissance
    "snmp", "snmpd",
    # Utilities
    "wifite", "w3m",
    # SSH & Network
    "openssh-server", "openssh-client", "autossh",
    # Python development
    "python3-dev", "python3-pip",
]

# Python packages required by payloads
PIP_PACKAGES = [
    "rich",              # Terminal UI
    "scapy>=2.5.0",      # Packet crafting
    "python-nmap>=0.7.1", # Network scanning
    "netifaces>=0.11.0", # Network interface enumeration
    "customtkinter>=5.2.0", # Desktop GUI
    "flask>=3.0.0",      # Web dashboard
    "evdev>=1.6.0",      # USB/Bluetooth input
    "Pillow>=9.0.0",     # Image processing
    "impacket",          # SMB/network protocol tools
    "requests",          # HTTP requests
    "pynmea2",           # GPS parsing
    "paramiko",          # SSH client library
    "cryptography",      # Encryption utilities
]

# --- Dependency Checker ---
def check_apt_packages():
    """Check which APT packages are missing."""
    missing = []
    try:
        result = subprocess.run(["dpkg", "-l"], capture_output=True, text=True, timeout=10)
        installed = set()
        for line in result.stdout.split('\n'):
            if line.startswith('ii'):
                parts = line.split()
                if len(parts) >= 2:
                    installed.add(parts[1].split(':')[0])

        for pkg in APT_PACKAGES:
            if pkg not in installed:
                missing.append(pkg)
    except Exception as e:
        log_status(f"Error checking APT: {e}")

    return missing

def check_pip_packages():
    """Check which PIP packages are missing."""
    missing = []
    try:
        result = subprocess.run(["pip3", "list"], capture_output=True, text=True, timeout=10)
        installed_lower = {line.split()[0].lower() for line in result.stdout.split('\n')[2:] if line.strip()}

        for pkg in PIP_PACKAGES:
            pkg_name = pkg.split('>')[0].split('=')[0].split('<')[0].lower()
            if pkg_name not in installed_lower:
                missing.append(pkg)
    except Exception as e:
        log_status(f"Error checking PIP: {e}")

    return missing

# --- LCD Drawing ---
def log_status(msg):
    """Add status message and update LCD."""
    with UI_LOCK:
        STATUS_LINES.append(msg)
        if not HEADLESS_MODE:
            draw_ui()

def draw_ui():
    """Draw current status on LCD."""
    if HEADLESS_MODE:
        return

    with UI_LOCK:
        image = Image.new("RGB", (128, 128), (10, 0, 0))
        draw = ImageDraw.Draw(image)
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
        except IOError:
            font_title = ImageFont.load_default()
            font_small = ImageFont.load_default()

        draw.text((5, 5), "Dependency Check", font=font_title, fill=(171, 178, 185))
        draw.line([(0, 18), (128, 18)], fill=(171, 178, 185), width=1)

        y = 22
        for line in STATUS_LINES[-7:]:
            display_line = line[:20] if len(line) > 20 else line
            draw.text((5, y), display_line, font=font_small, fill=(242, 243, 244))
            y += 12

        if LCD:
            LCD.LCD_ShowImage(image, 0, 0)

# --- Installation ---
def install_packages():
    """Install missing packages."""
    global MISSING_APT, MISSING_PIP

    log_status("Scanning dependencies...")
    time.sleep(0.5)

    log_status("Checking APT...")
    MISSING_APT = check_apt_packages()

    log_status("Checking PIP...")
    MISSING_PIP = check_pip_packages()

    if not MISSING_APT and not MISSING_PIP:
        log_status("All dependencies OK!")
        return True

    if MISSING_APT:
        log_status(f"Missing: {len(MISSING_APT)} APT")
    if MISSING_PIP:
        log_status(f"Missing: {len(MISSING_PIP)} PIP")

    time.sleep(1)

    # Install APT packages
    if MISSING_APT:
        log_status("Updating apt...")
        try:
            subprocess.run(["sudo", "apt-get", "update", "-qq"], timeout=60, check=True)
        except:
            log_status("APT update failed")
            return False

        for pkg in MISSING_APT:
            if not RUNNING:
                return False
            log_status(f"Installing {pkg}...")
            try:
                subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "--no-install-recommends", pkg],
                    timeout=120,
                    check=False,
                    capture_output=True
                )
            except Exception as e:
                log_status(f"Failed: {pkg}")

    # Install PIP packages
    if MISSING_PIP:
        for pkg in MISSING_PIP:
            if not RUNNING:
                return False
            log_status(f"Installing {pkg}...")
            try:
                subprocess.run(
                    ["pip3", "install", "-q", pkg],
                    timeout=120,
                    check=False,
                    capture_output=True
                )
            except Exception as e:
                log_status(f"Failed: {pkg}")

    log_status("Installation complete!")
    return True

# --- Cleanup ---
def cleanup(*_):
    global RUNNING
    if not RUNNING:
        return
    RUNNING = False
    if not HEADLESS_MODE and GPIO:
        try:
            GPIO.cleanup()
        except:
            pass

# --- Main Execution ---
if __name__ == "__main__":
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        if not HEADLESS_MODE:
            GPIO.setmode(GPIO.BCM)
            for pin in PINS.values():
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            LCD = LCD_1in44.LCD()
            LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
            LCD.LCD_Clear()
        else:
            print("Running in headless mode")

        log_status("Checking deps...")
        MISSING_APT = check_apt_packages()
        MISSING_PIP = check_pip_packages()

        if not MISSING_APT and not MISSING_PIP:
            log_status("All OK!")
            time.sleep(2)
        else:
            if MISSING_APT:
                log_status(f"Missing APT: {len(MISSING_APT)}")
            if MISSING_PIP:
                log_status(f"Missing PIP: {len(MISSING_PIP)}")

            if HEADLESS_MODE:
                log_status("Starting install...")
                install_packages()
            else:
                log_status("Press OK to install")
                log_status("KEY3 to cancel")

                # Wait for button press
                start_time = time.time()
                while RUNNING and time.time() - start_time < 30:
                    if GPIO.input(PINS["OK"]) == 0:
                        install_packages()
                        break
                    if GPIO.input(PINS["KEY3"]) == 0:
                        log_status("Cancelled")
                        break
                    time.sleep(0.1)

    except (KeyboardInterrupt, SystemExit):
        log_status("Interrupted")
    except Exception as e:
        log_status(f"Error: {str(e)[:20]}")
        import traceback
        traceback.print_exc()
    finally:
        if not HEADLESS_MODE and LCD:
            try:
                LCD.LCD_Clear()
            except:
                pass
        cleanup()
