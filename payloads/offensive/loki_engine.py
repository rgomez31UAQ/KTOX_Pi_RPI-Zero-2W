#!/usr/bin/env python3
"""
KTOx Loki Engine - Simple Launcher
===================================
Manages Loki autonomous security engine installation and lifecycle.

Author: KTOx Development
"""

import os
import subprocess
import time
import socket
from pathlib import Path

KTOX_DIR = os.environ.get("KTOX_DIR", "/root/KTOx")
LOOT_DIR = os.path.join(KTOX_DIR, "loot")
VENDOR_DIR = Path(KTOX_DIR) / "vendor" / "loki"
LOKI_DATA = Path(LOOT_DIR) / "loki"
LOKI_PORT = 8000
LOKI_REPO = "https://github.com/pineapple-pager-projects/pineapple_pager_loki"


def run_cmd(cmd, timeout=120, show_output=False):
    """Run command safely"""
    try:
        if show_output:
            subprocess.run(cmd, timeout=timeout, check=True)
        else:
            subprocess.run(cmd, timeout=timeout, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        return False
    except subprocess.TimeoutExpired:
        print(f"Command timeout after {timeout}s")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"


def is_port_open(port=LOKI_PORT):
    """Check if Loki port is open"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        return result
    except:
        return False


def is_installed():
    """Check if Loki is installed"""
    return VENDOR_DIR.exists() and (VENDOR_DIR / "Loki.py").exists()


def is_running():
    """Check if Loki is running"""
    return is_port_open()


def install():
    """Install Loki from GitHub"""
    print("\n[Loki] Installing from GitHub...")

    try:
        print("  [1/6] Updating packages...")
        if not run_cmd(["apt-get", "update", "-qq"], timeout=120):
            return False

        if not run_cmd(["apt-get", "install", "-y", "-qq", "nmap", "python3-pil", "git", "python3-pip"], timeout=180):
            return False

        print("  [2/6] Cloning Loki repository...")
        VENDOR_DIR.parent.mkdir(parents=True, exist_ok=True)

        if VENDOR_DIR.exists():
            run_cmd(["rm", "-rf", str(VENDOR_DIR)])

        if not run_cmd(["git", "clone", "--depth=1", LOKI_REPO, str(VENDOR_DIR)], timeout=300):
            print("  [!] Git clone failed - check internet connection")
            return False

        print("  [3/6] Installing Python dependencies...")
        req_file = VENDOR_DIR / "requirements.txt"
        if req_file.exists():
            if not run_cmd(["pip3", "install", "-q", "-r", str(req_file)], timeout=300):
                print("  [!] Dependency installation failed")
                return False

        print("  [4/6] Creating data directories...")
        for sub in ["logs", "output/crackedpwd", "output/datastolen", "output/zombies", "output/vulnerabilities", "input"]:
            (LOKI_DATA / sub).mkdir(parents=True, exist_ok=True)

        print("  [5/6] Writing pagerctl shim...")
        lib_dir = VENDOR_DIR / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        pagerctl_shim = lib_dir / "pagerctl.py"
        pagerctl_shim.write_text('''class Pager:
    """LCD display shim for headless Loki operation"""
    def __init__(self, *args, **kwargs):
        self.enabled = False
    def display(self, *args, **kwargs):
        pass
    def clear(self, *args, **kwargs):
        pass
''')

        print("  [6/6] Writing headless launcher...")
        launcher = VENDOR_DIR / "ktox_headless_loki.py"
        launcher.write_text('''#!/usr/bin/env python3
import sys, os, threading, signal, logging, time
_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path: sys.path.insert(0, _dir)
os.environ['CRYPTOGRAPHY_OPENSSL_NO_LEGACY'] = '1'

logging.basicConfig(level=logging.INFO)

try:
    from init_shared import shared_data
    from Loki import Loki, handle_exit
    from webapp import web_thread, handle_exit_web

    shared_data.load_config()
    shared_data.webapp_should_exit = False
    shared_data.display_should_exit = True

    print("[*] Starting Loki WebUI service...")
    web_thread.start()

    loki = Loki(shared_data)
    lt = threading.Thread(target=loki.run, daemon=True)
    lt.start()

    signal.signal(signal.SIGINT, lambda s, f: handle_exit(s, f, lt, web_thread))
    signal.signal(signal.SIGTERM, lambda s, f: handle_exit(s, f, lt, web_thread))

    print("[+] Loki running - Ctrl+C to stop")
    while not shared_data.should_exit:
        time.sleep(2)
except Exception as e:
    print(f"[!] Loki Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
''')
        launcher.chmod(0o755)

        print("[✓] Loki installed successfully!")
        return True

    except Exception as e:
        print(f"[!] Installation failed: {e}")
        return False


def start():
    """Start Loki service"""
    if is_running():
        ip = get_local_ip()
        print(f"\n[✓] Loki already running at http://{ip}:{LOKI_PORT}")
        return True

    print("\n[Loki] Starting service...")
    ip = get_local_ip()

    env = os.environ.copy()
    env["LOKI_DATA_DIR"] = str(LOKI_DATA)
    env["BJORN_IP"] = ip
    env["PYTHONUNBUFFERED"] = "1"

    log_file = LOKI_DATA / "logs" / "loki.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_file, "a") as lf:
            subprocess.Popen(
                ["python3", str(VENDOR_DIR / "ktox_headless_loki.py")],
                env=env,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(VENDOR_DIR),
                preexec_fn=os.setsid
            )

        # Wait for port to open
        print("  Waiting for WebUI to start...")
        for i in range(30):
            if is_port_open():
                ip = get_local_ip()
                print(f"\n[✓] Loki running at http://{ip}:{LOKI_PORT}")
                print(f"  Dashboard: http://{ip}:{LOKI_PORT}/dashboard")
                print(f"  API: http://{ip}:{LOKI_PORT}/api")
                return True
            time.sleep(1)

        print("\n[!] Startup timeout - check logs:")
        print(f"  tail -f {log_file}")
        print(f"\nDebug: Check if port {LOKI_PORT} is in use:")
        print(f"  netstat -tlnp | grep {LOKI_PORT}")
        return False

    except Exception as e:
        print(f"[!] Start failed: {e}")
        return False


def stop():
    """Stop Loki service"""
    print("\n[Loki] Stopping...")
    subprocess.run(["pkill", "-f", "ktox_headless_loki"], capture_output=True)
    print("[✓] Loki stopped")


def main():
    """Interactive main menu"""
    while True:
        print("\n" + "="*50)
        print("  LOKI Autonomous Security Engine")
        print("="*50)

        if is_installed():
            print("[✓] Installed")
        else:
            print("[✗] Not installed")

        if is_running():
            ip = get_local_ip()
            print(f"[✓] Running: http://{ip}:{LOKI_PORT}")
        else:
            print("[✗] Not running")

        print("\nOptions:")
        print("  1) Install Loki")
        print("  2) Start Loki")
        print("  3) Stop Loki")
        print("  4) Exit")

        choice = input("\nChoice (1-4): ").strip()

        if choice == "1":
            if is_installed():
                print("Already installed")
                continue
            if install():
                if input("\nStart now? (y/n): ").lower() == 'y':
                    start()
        elif choice == "2":
            if not is_installed():
                print("Not installed - install first")
                continue
            start()
        elif choice == "3":
            stop()
        elif choice == "4":
            break
        else:
            print("Invalid choice")


if __name__ == "__main__":
    main()
