#!/usr/bin/env python3
"""
KTOx payload – Gemini Chat (CLI)
=================================
Author: wickednull

Chat with Google Gemini using the `gemini` command-line tool.
- Full on-screen keyboard
- Scrollable conversation history
- Saves sessions to /root/KTOx/loot/GeminiChat/

Controls:
  UP/DOWN    – scroll conversation
  OK         – keyboard: add char / review: send
  KEY1       – switch to keyboard / send (review)
  KEY2       – backspace (keyboard) / view conversation (review)
  KEY3       – exit (saves session)
"""

import os
import sys
import time
import subprocess
import threading
import queue
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

# ----------------------------------------------------------------------
# Directories
# ----------------------------------------------------------------------
LOOT_DIR = "/root/KTOx/loot/GeminiChat"
os.makedirs(LOOT_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# LCD helpers
# ----------------------------------------------------------------------
def draw_screen(lines, title="GEMINI", title_color="#8B0000", text_color="#FFBBBB"):
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
# On-Screen Keyboard (same as before)
# ----------------------------------------------------------------------
CHAR_SETS = [
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "0123456789",
    " .,!?;:()[]{}<>/\\|`~@#$%^&*_-+=",
]
def get_char_set(idx):
    return CHAR_SETS[idx % len(CHAR_SETS)]

def osk_input(prompt="Ask Gemini:", initial=""):
    input_text = initial
    char_set_idx = 0
    char_idx = 0
    while True:
        cs = get_char_set(char_set_idx)
        curr_char = cs[char_idx % len(cs)]
        lines = [
            prompt[:20],
            "> " + input_text[-17:] if input_text else "> ",
            "",
            f"< {cs[(char_idx-1)%len(cs)]}  {curr_char}  {cs[(char_idx+1)%len(cs)]} >",
            "",
            "UP/DN=char  LEFT/RIGHT=set",
            "OK=add  KEY1=send  KEY2=del  K3=cancel"
        ]
        draw_screen(lines, title="KEYBOARD", title_color="#004466")
        btn = wait_btn(0.5)
        if btn == "KEY3":
            return None
        elif btn == "OK":
            input_text += curr_char
        elif btn == "KEY1":
            if input_text.strip():
                return input_text.strip()
        elif btn == "KEY2":
            input_text = input_text[:-1]
        elif btn == "UP":
            char_idx = (char_idx - 1) % len(cs)
        elif btn == "DOWN":
            char_idx = (char_idx + 1) % len(cs)
        elif btn == "LEFT":
            char_set_idx = (char_set_idx - 1) % len(CHAR_SETS)
            char_idx = 0
        elif btn == "RIGHT":
            char_set_idx = (char_set_idx + 1) % len(CHAR_SETS)
            char_idx = 0
        time.sleep(0.05)

# ----------------------------------------------------------------------
# Gemini CLI wrapper (using `gemini` command)
# ----------------------------------------------------------------------
def check_gemini():
    """Return True if `gemini` command exists."""
    try:
        subprocess.run(["which", "gemini"], capture_output=True, check=True)
        return True
    except:
        return False

class GeminiChat:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.running = False
        self.reader_thread = None
        self.history = []  # list of (role, content)

    def start(self):
        if not check_gemini():
            return False
        # Launch gemini in interactive mode (assumes it reads stdin)
        # Some gemini CLIs accept `gemini chat` or just `gemini`
        self.process = subprocess.Popen(
            ["gemini"],  # or ["gemini", "chat"] if needed
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.running = True
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()
        time.sleep(1)  # let it initialize
        return True

    def _read_output(self):
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.output_queue.put(line.strip())
            except:
                break

    def send(self, text):
        if not self.process:
            return
        try:
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
        except:
            pass

    def get_response(self, timeout=45):
        lines = []
        start = time.time()
        # Collect until we see a prompt indicator (like ">" or ">>>") or timeout
        while time.time() - start < timeout:
            try:
                line = self.output_queue.get(timeout=0.5)
                lines.append(line)
                # Stop if line looks like a prompt (common in interactive CLIs)
                if line.rstrip().endswith(">") or line.rstrip().endswith(">>>") or line.rstrip().endswith("$"):
                    break
            except queue.Empty:
                if lines:
                    break
        return "\n".join(lines)

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            time.sleep(0.5)
            self.process.kill()
            self.process = None

    def save_session(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gemini_session_{ts}.txt"
        filepath = os.path.join(LOOT_DIR, filename)
        with open(filepath, "w") as f:
            f.write(f"KTOx Gemini Chat Session\nDate: {datetime.now().isoformat()}\n")
            f.write("-" * 40 + "\n")
            for role, content in self.history:
                f.write(f"{role.upper()}: {content}\n\n")
        return filename

# ----------------------------------------------------------------------
# Conversation viewer
# ----------------------------------------------------------------------
class ConversationView:
    def __init__(self):
        self.lines = []
        self.scroll = 0

    def set_history(self, history):
        self.lines = []
        for role, content in history:
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

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not check_gemini():
        draw_screen(["`gemini` command", "not found in PATH", "Install it first", "", "KEY3 to exit"], title_color="#FF4444")
        while wait_btn(0.5) != "KEY3":
            pass
        return

    gemini = GeminiChat()
    if not gemini.start():
        draw_screen(["Failed to start", "gemini process", "Check installation", "KEY3 to exit"], title_color="#FF4444")
        while wait_btn(0.5) != "KEY3":
            pass
        return

    # Add a welcome message
    gemini.history.append(("assistant", "Gemini ready. Ask me anything."))
    viewer = ConversationView()
    viewer.set_history(gemini.history)
    viewer.draw()

    state = "conversation"

    try:
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
                gemini.send(user_input)
                response = gemini.get_response(timeout=45)
                if not response:
                    response = "[No response or timeout]"
                gemini.history.append(("user", user_input))
                gemini.history.append(("assistant", response))
                viewer.set_history(gemini.history)
                state = "conversation"
                viewer.draw()
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        gemini.stop()
        fname = gemini.save_session()
        draw_screen([f"Session saved", f"{fname}", "KEY3 to exit"], title_color="#00AA00")
        while wait_btn(0.5) != "KEY3":
            pass
        GPIO.cleanup()

if __name__ == "__main__":
    main()
