#!/usr/bin/env python3
"""
KTOx payload – Gemini Chat (Debug)
====================================
Author: wickednull

Tests API key and shows detailed error if invalid.
"""

import os
import sys
import time
import textwrap
import subprocess
import json
from datetime import datetime

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
    print("KTOx hardware not found")
    sys.exit(1)

PINS = {
    "UP": 6, "DOWN": 19, "LEFT": 5, "RIGHT": 26,
    "OK": 13, "KEY1": 21, "KEY2": 20, "KEY3": 16,
}
GPIO.setmode(GPIO.BCM)
for pin in PINS.values():
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

LCD = LCD_1in44.LCD()
LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
W, H = 128, 128

def font(size=9):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

f9 = font(9)

# ----------------------------------------------------------------------
# Directories
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/GeminiChat"
os.makedirs(LOOT_DIR, exist_ok=True)
KEY_FILE = "/root/KTOx/gemini_key.txt"

# ----------------------------------------------------------------------
# LCD helpers
# ----------------------------------------------------------------------
def draw_screen(lines, title="GEMINI CHAT", title_color="#8B0000", text_color="#FFBBBB"):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 17), fill=title_color)
    d.text((4, 3), title[:20], font=f9, fill="#FF3333" if title_color == "#8B0000" else "white")
    y = 20
    for line in lines[:7]:
        d.text((4, y), line[:23], font=f9, fill=text_color)
        y += 12
    d.rectangle((0, H-12, W, H), fill="#220000")
    d.text((4, H-10), "UP/DN OK KEY1/2 K3", font=f9, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def wait_btn(timeout=0.1):
    start = time.time()
    while time.time() - start < timeout:
        for name, pin in PINS.items():
            if GPIO.input(pin) == 0:
                time.sleep(0.05)
                return name
        time.sleep(0.02)
    return None

# ----------------------------------------------------------------------
# API key reading and testing
# ----------------------------------------------------------------------
def get_api_key():
    # Try environment
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    # Try file
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "r") as f:
                key = f.read().strip()
                if key:
                    return key
        except:
            pass
    return None

def test_api_key(key):
    """Return (success, error_message) where error_message is empty on success."""
    # Basic format check
    if not key.startswith("AIza"):
        return False, "Key doesn't start with AIza (invalid format)"
    if len(key) < 30:
        return False, "Key too short (should be ~39 chars)"
    # Build curl command with proper escaping
    payload = '{"contents":[{"parts":[{"text":"Hello"}]}]}'
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={key}",
        "-H", "Content-Type: application/json",
        "-d", payload
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        if "error" in data:
            err_msg = data["error"].get("message", "Unknown error")
            return False, err_msg
        # Check if we got a valid response
        if "candidates" in data:
            return True, ""
        return False, "Unexpected response format (no candidates)"
    except json.JSONDecodeError:
        return False, "Invalid JSON response from API"
    except Exception as e:
        return False, str(e)

# ----------------------------------------------------------------------
# Keyboard (same as before)
# ----------------------------------------------------------------------
KEYBOARD_ROWS = [
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890",
    ".,!?@#$% "
]
ROW_Y = [28, 44, 60, 76, 92]
CELL_W = 11
START_X = 6

def draw_keyboard(input_text, selected_row, selected_col):
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 17), fill="#004466")
    d.text((4, 3), "KEYBOARD", font=f9, fill="#FF3333")
    d.rectangle((2, 19, W-2, 27), fill="#222222")
    display_text = input_text[-20:] if len(input_text) > 20 else input_text
    d.text((4, 20), display_text, font=f9, fill="#FFFF00")
    for r, row in enumerate(KEYBOARD_ROWS):
        y = ROW_Y[r]
        for c, ch in enumerate(row):
            x = START_X + c * CELL_W
            if r == selected_row and c == selected_col:
                d.rectangle((x-1, y-1, x+CELL_W-1, y+7), fill="#FF8800")
                d.text((x, y), ch, font=f9, fill="#000000")
            else:
                d.text((x, y), ch, font=f9, fill="#FFFFFF")
    d.rectangle((0, H-12, W, H), fill="#220000")
    d.text((4, H-10), "OK=add  K1=send  K2=del  K3=cancel", font=f9, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def osk_input(prompt="Ask Gemini:", initial=""):
    input_text = initial
    selected_row = 0
    selected_col = 0
    current_row = KEYBOARD_ROWS[selected_row]
    if selected_col >= len(current_row):
        selected_col = len(current_row) - 1
    while True:
        draw_keyboard(input_text, selected_row, selected_col)
        btn = wait_btn(0.5)
        if btn == "KEY3":
            return None
        elif btn == "KEY1":
            if input_text.strip():
                return input_text.strip()
        elif btn == "KEY2":
            input_text = input_text[:-1]
        elif btn == "UP":
            selected_row = (selected_row - 1) % len(KEYBOARD_ROWS)
            new_len = len(KEYBOARD_ROWS[selected_row])
            if selected_col >= new_len:
                selected_col = new_len - 1
        elif btn == "DOWN":
            selected_row = (selected_row + 1) % len(KEYBOARD_ROWS)
            new_len = len(KEYBOARD_ROWS[selected_row])
            if selected_col >= new_len:
                selected_col = new_len - 1
        elif btn == "LEFT":
            selected_col = (selected_col - 1) % len(KEYBOARD_ROWS[selected_row])
        elif btn == "RIGHT":
            selected_col = (selected_col + 1) % len(KEYBOARD_ROWS[selected_row])
        elif btn == "OK":
            ch = KEYBOARD_ROWS[selected_row][selected_col]
            input_text += ch
        time.sleep(0.05)

# ----------------------------------------------------------------------
# Gemini API caller (curl)
# ----------------------------------------------------------------------
def gemini_chat(api_key, user_input, history):
    """Send chat request, return assistant response."""
    contents = []
    for role, content in history:
        contents.append({"role": "user" if role == "user" else "model", "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": user_input}]})
    payload = {"contents": contents}
    payload_json = json.dumps(payload)
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}",
        "-H", "Content-Type: application/json",
        "-d", payload_json
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        data = json.loads(result.stdout)
        if "error" in data:
            return f"API error: {data['error'].get('message', 'Unknown')}"
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "No text")
        return "Unexpected API response"
    except Exception as e:
        return f"Request failed: {str(e)}"

# ----------------------------------------------------------------------
# Conversation viewer
# ----------------------------------------------------------------------
class ConversationView:
    def __init__(self):
        self.history = []  # (role, content)
        self.lines = []
        self.scroll = 0

    def rebuild(self):
        self.lines = []
        for role, content in self.history:
            prefix = "You: " if role == "user" else "AI: "
            wrapped = textwrap.wrap(content, width=20)
            for i, line in enumerate(wrapped):
                if i == 0:
                    self.lines.append(prefix + line)
                else:
                    self.lines.append("  " + line)
            self.lines.append("")
        self.scroll = max(0, len(self.lines) - 6)

    def draw(self):
        if not self.lines:
            draw_screen(["No messages yet", "Press KEY1 to chat"], title="CONVERSATION")
            return
        total = len(self.lines)
        visible = self.lines[self.scroll:self.scroll+6]
        display = visible + [f"Line {self.scroll+1}/{total}"] if total > 6 else visible
        draw_screen(display, title="CONVERSATION", title_color="#004466")

    def scroll_up(self):
        if self.scroll > 0:
            self.scroll -= 1
            self.draw()

    def scroll_down(self):
        if self.scroll + 6 < len(self.lines):
            self.scroll += 1
            self.draw()

    def add_message(self, role, content):
        self.history.append((role, content))
        self.rebuild()
        self.draw()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # Get API key
    api_key = get_api_key()
    if not api_key:
        draw_screen(["API key missing", "", "Set GEMINI_API_KEY", "or create file:", KEY_FILE, "KEY3 to exit"], title_color="#FF4444")
        while wait_btn(0.5) != "KEY3":
            pass
        return

    # Show masked key for verification
    masked = api_key[:8] + "..." + api_key[-4:]
    draw_screen([f"Key: {masked}", "Testing...", "Please wait"], title="GEMINI")
    ok, err = test_api_key(api_key)
    if not ok:
        draw_screen(["API key invalid!", err[:22], "", "Check key format", "KEY3 to exit"], title_color="#FF4444")
        while wait_btn(0.5) != "KEY3":
            pass
        return

    draw_screen(["API key valid!", "Starting chat..."], title="GEMINI", title_color="#00AA00")
    time.sleep(1)

    viewer = ConversationView()
    viewer.add_message("assistant", "Gemini ready. Ask me anything.")
    state = "conversation"

    while True:
        if state == "conversation":
            viewer.draw()
            btn = wait_btn(0.5)
            if btn == "UP":
                viewer.scroll_up()
            elif btn == "DOWN":
                viewer.scroll_down()
            elif btn == "KEY1":
                state = "typing"
            elif btn == "KEY3":
                break
        elif state == "typing":
            user_input = osk_input("Ask Gemini:", "")
            if user_input is None:
                state = "conversation"
                continue
            draw_screen(["Thinking...", "Please wait"], title="GEMINI", title_color="#444400")
            response = gemini_chat(api_key, user_input, viewer.history)
            viewer.add_message("user", user_input)
            viewer.add_message("assistant", response)
            state = "conversation"
            viewer.draw()
        time.sleep(0.05)

    # Save session
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{ts}.txt"
    filepath = os.path.join(LOOT_DIR, filename)
    with open(filepath, "w") as f:
        f.write(f"KTOx Gemini Chat Session\nDate: {datetime.now().isoformat()}\n")
        f.write("-" * 40 + "\n")
        for role, content in viewer.history:
            f.write(f"{role.upper()}: {content}\n\n")
    draw_screen([f"Saved: {filename}", "KEY3 to exit"], title_color="#00AA00")
    while wait_btn(0.5) != "KEY3":
        pass
    GPIO.cleanup()

if __name__ == "__main__":
    main()
