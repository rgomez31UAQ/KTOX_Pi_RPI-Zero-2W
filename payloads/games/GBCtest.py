import evdev
from evdev import ecodes

# ... [Existing imports and LCD setup] ...

# ═══════════════════════════════════════════════════════════════
# CONTROLLER SUPPORT
# ═══════════════════════════════════════════════════════════════

class GamepadManager:
    def __init__(self):
        self.devices = []
        self.refresh_devices()
        
        # Standard Mapping (Xbox/8BitDo/General)
        # BTN_SOUTH = A, BTN_EAST = B, BTN_START = Start, BTN_SELECT = Select
        self.key_map = {
            ecodes.BTN_SOUTH: "a",
            ecodes.BTN_EAST: "b",
            ecodes.BTN_START: "start",
            ecodes.BTN_SELECT: "select",
            ecodes.KEY_UP: "up",
            ecodes.KEY_DOWN: "down",
            ecodes.KEY_LEFT: "left",
            ecodes.KEY_RIGHT: "right",
        }

    def refresh_devices(self):
        """Scan for USB/Bluetooth gamepads."""
        self.devices = []
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            # Filter for devices that look like joysticks/gamepads
            if "pad" in dev.name.lower() or "controller" in dev.name.lower() or "xbox" in dev.name.lower():
                self.devices.append(dev)

    def update_inputs(self, pyboy):
        """Poll events from all connected gamepads and send to PyBoy."""
        for dev in self.devices:
            try:
                # Use non-blocking reads
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        gb_btn = self.key_map.get(event.code)
                        if gb_btn:
                            if event.value == 1: # Pressed
                                pyboy.button_press(gb_btn)
                            elif event.value == 0: # Released
                                pyboy.button_release(gb_btn)
                                
                    # Handle D-Pad (Hat switches) often seen on 8BitDo/Xbox
                    elif event.type == ecodes.EV_ABS:
                        if event.code == ecodes.ABS_HAT0X: # Left/Right
                            if event.value == -1: pyboy.button_press("left")
                            elif event.value == 1: pyboy.button_press("right")
                            else: 
                                pyboy.button_release("left")
                                pyboy.button_release("right")
                        elif event.code == ecodes.ABS_HAT0Y: # Up/Down
                            if event.value == -1: pyboy.button_press("up")
                            elif event.value == 1: pyboy.button_press("down")
                            else:
                                pyboy.button_release("up")
                                pyboy.button_release("down")
            except (BlockingIOError, OSError):
                pass # No events or device disconnected

# ═══════════════════════════════════════════════════════════════
# MODIFIED EMULATOR LOOP
# ═══════════════════════════════════════════════════════════════

def _run_emulator(rom_path):
    global running
    _draw_loading(rom_path)
    
    # Initialize Controller Manager
    gp_manager = GamepadManager()

    try:
        pyboy = PyBoy(rom_path, window="null", sound_emulated=False)
        # ... [LCD Scaling logic from original script] ...

        while running:
            # 1. Physical Buttons (On-device)
            pressed = _read_buttons_noblock()
            if "KEY3" in pressed: break
            
            # Map on-device buttons
            for rj_btn, gb_btn in GB_MAP.items():
                if rj_btn in pressed: pyboy.button_press(gb_btn)
                else: pyboy.button_release(gb_btn)

            # 2. External Gamepad Buttons (USB/BT)
            gp_manager.update_inputs(pyboy)

            # 3. Tick and Render
            pyboy.tick(count=1, render=(frame_count % RENDER_EVERY == 0))
            
            if frame_count % RENDER_EVERY == 0:
                # ... [Existing LCD render logic] ...
            
            frame_count += 1
    finally:
        pyboy.stop(save=True)
