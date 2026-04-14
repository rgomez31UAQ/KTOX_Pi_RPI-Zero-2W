#!/usr/bin/env python3
"""
KTOx payload – Gemini Chat (Improved Keyboard)
================================================
Author: wickednull

Chat with Gemini using the official Google AI Python library.
- Full QWERTY on-screen keyboard with cursor highlight
- Scrollable conversation history
- Saves sessions to /root/KTOx/loot/GeminiChat/

Setup:
  1. Get Gemini API key: https://aistudio.google.com/app/apikey
  2. echo "export GEMINI_API_KEY='your-key'" >> ~/.bashrc && source ~/.bashrc
  3. pip install google-genai

Controls:
  In conversation view:
    UP/DOWN  – scroll history
    KEY1     – open keyboard
    KEY3     – exit (saves session)
  In keyboard:
    UP/DOWN  – change row
    LEFT/RIGHT – change column
    OK       – add selected character
    KEY1     – send message
    KEY2     – backspace
    KEY3     – cancel
"""

import os
import sys
import time
import textwrap
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
f11 = font(11)

# ----------------------------------------------------------------------
# Directories & API
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/GeminiChat"
os.makedirs(LOOT_DIR, exist_ok=True)

API_KEY = os.environ.get("GEMINI_API_KEY")
HAS_GEMINI = False
if API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=API_KEY)
        HAS_GEMINI = True
    except ImportError:
        print("google-genai not installed. Run: pip install google-genai")

# ----------------------------------------------------------------------
# LCD drawing helpers
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
# Improved On-Screen Keyboard (QWERTY layout)
# ----------------------------------------------------------------------
KEYBOARD_ROWS = [
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890",
    ".,!?@#$% "
]
ROW_Y = [28, 44, 60, 76, 92]  # Y positions for each row (pixels)
CELL_W = 11  # width per character (pixels)
START_X = 6  # left margin

def draw_keyboard(input_text, selected_row, selected_col):
    """Draw full keyboard with highlighted selection and input text."""
    img = Image.new("RGB", (W, H), "#0A0000")
    d = ImageDraw.Draw(img)
    # Title bar
    d.rectangle((0, 0, W, 17), fill="#004466")
    d.text((4, 3), "KEYBOARD", font=f9, fill="#FF3333")
    # Input text area
    d.rectangle((2, 19, W-2, 27), fill="#222222")
    display_text = input_text[-20:] if len(input_text) > 20 else input_text
    d.text((4, 20), display_text, font=f9, fill="#FFFF00")
    # Draw keyboard rows
    for r, row in enumerate(KEYBOARD_ROWS):
        y = ROW_Y[r]
        for c, ch in enumerate(row):
            x = START_X + c * CELL_W
            # Highlight selected cell
            if r == selected_row and c == selected_col:
                d.rectangle((x-1, y-1, x+CELL_W-1, y+7), fill="#FF8800")
                d.text((x, y), ch, font=f9, fill="#000000")
            else:
                d.text((x, y), ch, font=f9, fill="#FFFFFF")
    # Footer instructions
    d.rectangle((0, H-12, W, H), fill="#220000")
    d.text((4, H-10), "OK=add  K1=send  K2=del  K3=cancel", font=f9, fill="#FF7777")
    LCD.LCD_ShowImage(img, 0, 0)

def osk_input(prompt="Ask Gemini:", initial=""):
    """
    Improved keyboard: navigate with arrows, OK to add char,
    KEY1 to send, KEY2 to backspace, KEY3 to cancel.
    Returns the final string or None if cancelled.
    """
    input_text = initial
    selected_row = 0
    selected_col = 0
    # Ensure selected column is within current row length
    current_row = KEYBOARD_ROWS[selected_row]
    if selected_col >= len(current_row):
        selected_col = len(current_row) - 1
    # Show prompt briefly (optional)
    if prompt:
        draw_screen([prompt, "", "Press any key to start"], title="KEYBOARD", title_color="#004466")
        wait_btn(0.5)
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
            # Adjust column if new row is shorter
            new_row_len = len(KEYBOARD_ROWS[selected_row])
            if selected_col >= new_row_len:
                selected_col = new_row_len - 1
        elif btn == "DOWN":
            selected_row = (selected_row + 1) % len(KEYBOARD_ROWS)
            new_row_len = len(KEYBOARD_ROWS[selected_row])
            if selected_col >= new_row_len:
                selected_col = new_row_len - 1
        elif btn == "LEFT":
            selected_col = (selected_col - 1) % len(KEYBOARD_ROWS[selected_row])
        elif btn == "RIGHT":
            selected_col = (selected_col + 1) % len(KEYBOARD_ROWS[selected_row])
        elif btn == "OK":
            # Append selected character
            ch = KEYBOARD_ROWS[selected_row][selected_col]
            input_text += ch
        time.sleep(0.05)

# ----------------------------------------------------------------------
# Gemini Chat Engine
# ----------------------------------------------------------------------
class GeminiChat:
    def __init__(self):
        self.history = []
        self.system_prompt = "You are a helpful cybersecurity assistant running on a KTOx Raspberry Pi Zero 2 W with a 128x128 display. Keep responses concise and practical."

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})

    def ask(self, user_input):
        if not HAS_GEMINI:
            return "Gemini API not configured. Set GEMINI_API_KEY."
        try:
            self.add_message("user", user_input)
            # Build prompt with history
            full_prompt = self.system_prompt + "\n\n"
            for msg in self.history:
                full_prompt += f"{msg['role']}: {msg['content']}\n"
            full_prompt += "assistant: "
            # Non-streaming request (simpler for LCD)
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=full_prompt
            )
            answer = response.text
            self.add_message("assistant", answer)
            return answer
        except Exception as e:
            err = f"Error: {str(e)[:30]}"
            self.add_message("assistant", err)
            return err

    def save_session(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{ts}.txt"
        filepath = os.path.join(LOOT_DIR, filename)
        with open(filepath, "w") as f:
            f.write(f"KTOx Gemini Chat Session\nDate: {datetime.now().isoformat()}\n")
            f.write("-" * 40 + "\n")
            for msg in self.history:
                f.write(f"{msg['role'].upper()}: {msg['content']}\n\n")
        return filename

# ----------------------------------------------------------------------
# Conversation viewer
# ----------------------------------------------------------------------
class ConversationView:
    def __init__(self, chat):
        self.chat = chat
        self.scroll = 0
        self.lines = []
        self._rebuild_lines()

    def _rebuild_lines(self):
        self.lines = []
        for msg in self.chat.history:
            role = "You:" if msg["role"] == "user" else "AI:"
            prefix = f"{role} "
            content = msg["content"]
            wrapped = textwrap.wrap(content, width=20)
            for i, line in enumerate(wrapped):
                if i == 0:
                    self.lines.append(prefix + line)
                else:
                    self.lines.append("  " + line)
            self.lines.append("")

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

    def add_and_refresh(self, role, content):
        self._rebuild_lines()
        # Auto-scroll to bottom
        self.scroll = max(0, len(self.lines) - 6)
        self.draw()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not HAS_GEMINI:
        draw_screen(["Gemini API not ready", "", "Set GEMINI_API_KEY", "Install google-genai", "", "KEY3 to exit"], title_color="#FF4444")
        while wait_btn(0.5) != "KEY3":
            pass
        return

    chat = GeminiChat()
    viewer = ConversationView(chat)
    # Welcome message
    chat.add_message("assistant", "Gemini ready. Ask me anything.")
    viewer._rebuild_lines()
    viewer.draw()

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
            # Show thinking
            draw_screen(["Thinking...", "Please wait"], title="GEMINI", title_color="#444400")
            response = chat.ask(user_input)
            # Update viewer
            viewer.add_and_refresh("user", user_input)
            viewer.add_and_refresh("assistant", response)
            state = "conversation"
            viewer.draw()
        time.sleep(0.05)

    # Save session
    fname = chat.save_session()
    draw_screen([f"Saved: {fname}", "KEY3 to exit"], title_color="#00AA00")
    while wait_btn(0.5) != "KEY3":
        pass
    GPIO.cleanup()

if __name__ == "__main__":
    main()
