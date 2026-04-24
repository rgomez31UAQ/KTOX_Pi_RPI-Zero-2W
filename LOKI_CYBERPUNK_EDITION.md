# LOKI - CYBERPUNK EDITION

## 🌐 Heavy Cyberpunk Web Interface

A dark, gritty cyberpunk-themed WebUI for Loki security engine, matching the aesthetic of yt-ripper and KTOx's signature look.

## 🎨 Visual Design

### Color Palette
Directly inspired by yt-ripper's cyberpunk aesthetic:

```
Background:     #0a0000  (Deep dark red - RGB 10,0,0)
Panel:          #220000  (Dark red - RGB 34,0,0)
Header:         #8b0000  (Medium red - RGB 139,0,0)
Foreground:     #abb2b9  (Light gray - RGB 171,178,185)
Accent:         #e74c3c  (Bright red-orange - RGB 231,76,60)
Warning:        #d4ac0d  (Yellow - RGB 212,172,13)
Dim:            #717d7e  (Dark gray - RGB 113,125,126)
```

### Visual Effects

- **Scanlines:** CRT monitor effect overlay
- **Glowing Borders:** Red accent borders with glow effects
- **Monospace Font:** Courier New for authentic terminal feel
- **Gradient Panels:** Dark red to medium red gradients
- **Shadow Effects:** Inset and outset shadows for depth
- **Glitch Animation:** Optional text glitch for dramatic effect

## 🚀 Features

### LCD Display Canvas
- 128×128 pixel-perfect display
- Real-time rendering of device screen
- Black background with red border glow
- Updates every 1 second

### Physical Controls

**D-Pad Navigation:**
```
       ▲ UP
    ◄  OK  ►
       ▼ DOWN
```

**Side Buttons:**
- KEY1 - Function/modifier
- KEY2 - Secondary function
- KEY3 - Exit/escape

All buttons styled with red accent borders and glow effects.

### Main Sections

#### 📡 RECONNAISSANCE
Network scanning and enumeration tools:
- Network Scan
- Enumerate Services
- Host Discovery
- Fingerprint OS/Version

#### ⚔️ EXPLOITATION
Attack and penetration testing:
- KICK ONE - Disconnect single target
- KICK ALL - Disconnect all network
- ARP MITM - Man-in-the-middle
- ARP FLOOD - Cache exhaustion
- ARP CAGE - Network isolation
- NTLM CAPTURE - Credential harvesting

#### 📋 ACTIVITY LOG
Real-time colored log output:
- Success (green)
- Error (red)
- Warning (yellow)
- Info (cyan)

#### ℹ️ STATUS PANEL
Current system state:
- STATE: ONLINE
- PORT: 8000
- UPTIME: HH:MM:SS
- MODE: ATTACK

## 💻 Architecture

```
┌─────────────────────────────────────────┐
│         CYBERPUNK WEBUI (Flask)         │
│  loki_cyberpunk_ui.py on port 8000     │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
[Canvas]   [Controls]   [API Routes]
[Display]  [D-Pad+Keys] [/api/status]
           [Buttons]    [/api/screen]
                        [/api/input]
                        [/api/action]
```

## 🌍 Responsive Layout

### Desktop (>900px)
- 2-column layout
- Left sidebar: LCD + Controls + Status
- Right content: Recon + Exploit + Logs
- Full-size canvas

### Tablet (768-900px)
- Single column with reordering
- Smaller canvas
- Touch-friendly buttons

### Mobile (<768px)
- Full-width layout
- Compact canvas
- Stacked sections

## 🎮 Usage

### Installation

The cyberpunk UI is the fallback when original Loki webapp is unavailable:

```bash
# Start Loki via menu or:
python3 /home/user/KTOX_Pi/payloads/offensive/loki_engine.py

# Or directly start cyberpunk UI:
python3 /home/user/KTOX_Pi/payloads/offensive/loki_cyberpunk_ui.py
```

### Web Access

```
http://localhost:8000       (local)
http://<device-ip>:8000    (remote)
```

### Button Control

**From Browser:**
- Click D-Pad buttons for navigation
- Click action buttons for attacks
- Click KEY buttons for control

**From Device (if connected):**
- Use physical GPIO buttons if device has LCD
- Same behavior as browser

## 🔧 API Endpoints

### GET /
Main cyberpunk WebUI interface

### GET /api/status
```json
{
  "status": "ONLINE",
  "uptime": "00:00:00"
}
```

### GET /api/screen
Returns LCD canvas as base64 PNG:
```json
{
  "image": "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADTAQEP..."
}
```

### POST /api/input
Button input from controls:
```json
{
  "button": "UP|DOWN|LEFT|RIGHT|OK|KEY1|KEY2|KEY3"
}
```

### POST /api/action
Execute reconnaissance action:
```json
{
  "type": "scan|enumerate|discover|fingerprint"
}
```

Result:
```json
{
  "status": "ok",
  "message": "ACTION INITIATED"
}
```

## 🎨 Customization

### Colors
Edit color definitions in `<style>`:
```css
:root {
    --bg: #0a0000;
    --accent: #e74c3c;
    /* ... etc ... */
}
```

### Fonts
Currently uses system Courier New. To change:
```css
body {
    font-family: 'YourFont', monospace;
}
```

### Layout
CSS Grid controls layout:
```css
.main-grid {
    grid-template-columns: 350px 1fr; /* Sidebar width */
    gap: 30px;
}
```

### Effects
Toggle scanlines or glow in CSS:
```css
.scanlines { /* Comment out to disable */ }
.panel { box-shadow: var(--glow); /* Remove for no glow */ }
```

## 📊 Performance

### Browser Requirements
- Modern browser with Canvas support
- JavaScript enabled
- CSS Grid support (all modern browsers)

### Server
- Flask lightweight server
- < 1% CPU idle
- ~50MB memory

### Canvas Updates
- 1 second refresh rate (adjustable)
- Smooth scaling to fit viewport
- Pixel-perfect rendering

## 🛠️ Troubleshooting

### WebUI Not Loading

Check if server is running:
```bash
curl http://localhost:8000
```

### Canvas Black/No Display

Canvas shows placeholder if PIL unavailable:
```bash
pip3 install pillow
```

### Colors Look Different

Browser color calibration may vary. Ensure:
- Browser in dark mode for best appearance
- No f.lux or similar color adjustment
- Fresh page load (Ctrl+Shift+R)

### Buttons Not Responding

Test button API:
```bash
curl -X POST http://localhost:8000/api/input \
  -H "Content-Type: application/json" \
  -d '{"button":"OK"}'
```

## 📝 Log Colors

Activity log uses semantic coloring:

```
[*] INFO     - Cyan    - Informational messages
[+] SUCCESS  - Green   - Operation succeeded
[!] WARNING  - Yellow  - Warning/caution
[-] ERROR    - Red     - Error/failure
```

## 🔐 Security Notes

- No authentication (for lab/isolated networks)
- All data in memory, not persisted
- Suitable for trusted networks only

For production, add:
- HTTP Basic Auth
- HTTPS/SSL certificates
- CORS restrictions
- Rate limiting

## 📦 Files

### Main Implementation
- `loki_cyberpunk_ui.py` - Cyberpunk Flask WebUI

### Dependencies
- Flask - Web framework
- PIL/Pillow - Image generation
- Python 3.7+ - Runtime

### Documentation
- `LOKI_CYBERPUNK_EDITION.md` - This file
- `LOKI_PROFESSIONAL_WEBUI_GUIDE.md` - Alternative UI
- `LOKI_INTEGRATION_GUIDE.md` - Installation & architecture

## 🌟 Design Philosophy

The cyberpunk UI embodies the aesthetic of modern penetration testing and security research:

- **Dark Theme:** Reduce eye strain during long sessions
- **Red Accents:** Signal danger, power, and offense
- **Monospace Font:** Traditional hacker/terminal look
- **Glow Effects:** Neon cyberpunk atmosphere
- **Minimal Distraction:** Focus on the task
- **Responsive:** Works on any device

It matches the style of **yt-ripper** and maintains visual consistency across KTOx tools.

## 🎯 Future Enhancements

Possible improvements:
1. WebSocket for real-time updates
2. Terminal emulator for command execution
3. Attack scheduling/automation
4. Network topology visualization
5. Custom payload designer
6. Integration with threat intelligence
7. Automated reporting
8. Dark web integration
9. Multi-language support
10. VR mode (extreme cyberpunk)

## 📚 References

- **yt-ripper** - Color scheme inspiration
- **KTOx_Pi** - Integration base
- **Loki** - https://github.com/pineapple-pager-projects/pineapple_pager_loki
- **Cyberpunk Aesthetic** - Neon, dark, high-tech, low-life

---

**LOKI - CYBERPUNK EDITION**
*Status: ✅ ONLINE*
*Theme: 🔴 HEAVY CYBERPUNK*
*Last Updated: 2026-04-24*
