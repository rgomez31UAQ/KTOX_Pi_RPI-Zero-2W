# M5Stack Cardputer Remote Control for KTOX_Pi

Full-featured remote control application for KTOX_Pi running on M5Stack Cardputer with ESP32-S3.

## Features

- **Live Video Streaming**: View KTOX_Pi LCD display on M5Cardputer (240x135)
- **Full Control**: Complete menu system for all KTOX operations:
  - Reconnaissance (ARP scan, host discovery, port scan, fingerprinting)
  - Offensive attacks (packet injection, DoS, ARP poisoning)
  - Defensive/MITM operations (SSL stripping, DNS spoofing, ARP hardening)
  - WiFi attacks (deauth, handshake capture, evil twin)
  - System tools (status, logs, loot management)
- **Settings Persistence**: WiFi credentials and KTOX connection settings saved to SPIFFS
- **Real-time Input**: Keyboard input handling for navigation and command execution
- **Status Display**: Connection status, frame count, and FPS display

## Hardware Requirements

- M5Stack M5Cardputer with 240x135 display
- ESP32-S3 microcontroller (integrated)
- WiFi capability (WiFi 802.11 b/g/n)
- USB-C connection for programming

## Software Requirements

- PlatformIO (VS Code extension or CLI)
- ESP32 Arduino framework
- M5Cardputer library
- WebSocket client library
- ArduinoJson library
- TJpg_Decoder library

## Building and Deploying

### 1. Prerequisites

Install PlatformIO:
```bash
# Via Python
pip install platformio

# Or via VS Code: Install PlatformIO IDE extension
```

### 2. Build the Firmware

```bash
cd /home/user/KTOX_Pi/m5cardputer

# Compile for M5Stack Cardputer
platformio run -e m5stack-cardputer

# Or to build and upload directly
platformio run -e m5stack-cardputer --target upload
```

### 3. Upload to M5Cardputer

Connect M5Cardputer via USB-C cable and:

```bash
cd /home/user/KTOX_Pi/m5cardputer

# Upload firmware
platformio run -e m5stack-cardputer --target upload

# Monitor serial output for debugging
platformio run -e m5stack-cardputer --target upload --target monitor
```

### 4. First-Time Setup

1. Power on M5Cardputer after upload
2. Follow the on-screen setup wizard:
   - Enter WiFi SSID
   - Enter WiFi password
   - Enter KTOX_Pi IP address (e.g., 192.168.0.50)
   - Enter KTOX WebSocket port (default 8765)
   - (Optional) Enter authentication token
3. Device connects to WiFi and KTOX_Pi WebSocket
4. Frame streaming begins automatically

## Keyboard Controls

### Stream View
- `M` - Open main menu
- `H` - Open configuration/settings
- `T` - Set target IP address
- `?` - Show help screen
- Arrow keys/WASD - Navigation (when in menu)
- Space/Enter - Select menu item
- Q/Esc - Go back

### Menu Navigation
- Up/Down (or W/S, I/K) - Navigate menu items
- Enter (or Space) - Select operation
- Q/Esc (or Back button) - Return to previous menu or stream

## Configuration

Settings are stored in `/settings.json` on device's SPIFFS:

```json
{
  "wifi_ssid": "YourWiFiNetwork",
  "wifi_password": "YourPassword",
  "ktox_host": "192.168.0.50",
  "ktox_port": 8765,
  "auth_token": "optional_token"
}
```

Change settings via the in-device configuration menu (press 'H' on stream view).

## Connection Flow

1. **WiFi Connection** → M5Cardputer connects to configured WiFi network
2. **WebSocket Connection** → Establishes connection to KTOX_Pi device_server (port 8765)
3. **Authentication** → Sends optional auth token if configured
4. **Frame Streaming** → Receives base64-encoded JPEG frames
5. **Input Handling** → Sends keyboard and button events back to KTOX_Pi

## Frame Format

Frames are received as JSON messages:

```json
{
  "type": "frame",
  "data": "<base64-encoded JPEG>"
}
```

The application automatically:
- Decodes base64 data
- Decompresses JPEG
- Scales to fit 240x135 display
- Updates display at received frame rate

## Troubleshooting

### Can't Connect to WiFi
- Check SSID spelling (case-sensitive)
- Verify password is correct
- Ensure WiFi 2.4GHz is available (M5Cardputer doesn't support 5GHz)
- Check WiFi signal strength

### WebSocket Connection Fails
- Verify KTOX_Pi IP address is correct
- Ensure KTOX_Pi device_server is running (`ps aux | grep device_server`)
- Check firewall allows port 8765: `sudo ufw allow 8765`
- Test locally: `netstat -tlnp | grep 8765`

### Frames Not Displaying
- Check KTOX_Pi frame capture is enabled: `env | grep RJ_FRAME`
- Verify frames exist: `ls -lh /dev/shm/ktox_*.jpg`
- Monitor frame timestamps: `watch -n 0.5 ls -lh /dev/shm/ktox_*.jpg`
- Check M5Cardputer USB connection during upload

### Menu Hangs or Freezes
- Press reset button on M5Cardputer
- Check serial monitor for errors: `platformio run -e m5stack-cardputer --target monitor`
- Reduce frame rate in KTOX_Pi: `export RJ_FRAME_FPS=3`

### Compilation Errors
- Update PlatformIO: `platformio update`
- Clean build: `platformio run -e m5stack-cardputer --target clean`
- Delete `.pio` directory and rebuild

## Serial Debugging

Monitor M5Cardputer output during runtime:

```bash
cd /home/user/KTOX_Pi/m5cardputer
platformio device monitor -b 115200

# Or after upload
platformio run -e m5stack-cardputer --target monitor
```

Look for connection status, frame statistics, and error messages.

## Power Consumption

- Idle (WiFi connected, no frame streaming): ~100mA
- Active (streaming frames): ~300-400mA
- Max (streaming + menu interaction): ~500mA

Use a quality USB-C power supply (5V/2A minimum) for reliable operation.

## Known Limitations

- Display aspect ratio differs from KTOX LCD (4:3 vs square)
- Frame scaling may distort certain UI elements
- Latency depends on WiFi signal quality (typically 100-300ms)
- Menu operations limited to available button combinations on M5Cardputer

## Future Improvements

- Hardware button mappings for common attacks
- Recorded frame playback when offline
- Signal strength indicator
- Battery level monitoring
- Screen rotation options

## Integration with KTOX_Pi

This application is designed to work with KTOX_Pi frame streaming infrastructure:

- **device_server.py**: Handles WebSocket connections and frame broadcasting
- **web_server.py**: Provides authentication and configuration
- **.env.frame_capture**: Environment variables controlling frame capture

See `/home/user/KTOX_Pi/docs/M5_CARDPUTER_SETUP.md` for server-side configuration.

## Support

For issues, enable serial debugging and check:
1. KTOX_Pi server logs: `sudo journalctl -u ktox_pi -f` (if using systemd)
2. M5Cardputer serial output via `platformio device monitor`
3. Network connectivity: `ping KTOX_Pi_IP_ADDRESS`

