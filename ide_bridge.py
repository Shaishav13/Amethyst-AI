"""
Amethyst IDE Bridge
Global hotkey (Ctrl+Shift+A) → Capture highlighted code → Send to Amethyst
Clipboard-based workflow — no VS Code extension required
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Callable

import pyperclip

log = logging.getLogger("amethyst.ide_bridge")

HOTKEY_TRIGGER = "ctrl+3"


class IDEBridge:
    """
    Listens for a global hotkey. When triggered:
    1. Saves current clipboard content
    2. Sends Ctrl+C to copy highlighted text in the active editor
    3. Reads the new clipboard content (the selected code)
    4. Calls the registered callback with the captured code
    """

    def __init__(self, on_code_captured: Optional[Callable[[str], None]] = None):
        self._callback   = on_code_captured
        self._active     = False
        self._hotkey_registered = False

    def set_callback(self, callback: Callable[[str], None]):
        self._callback = callback

    def start(self):
        """Start listening for the global hotkey in a daemon thread."""
        if self._active:
            return
        self._active = True
        thread = threading.Thread(target=self._listen_loop, daemon=True, name="ide-bridge")
        thread.start()
        log.info(f"IDE bridge started — hotkey: {HOTKEY_TRIGGER}")

    def stop(self):
        self._active = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        log.info("IDE bridge stopped.")

    def _listen_loop(self):
        try:
            import keyboard
            keyboard.add_hotkey(HOTKEY_TRIGGER, self._on_hotkey_triggered)
            self._hotkey_registered = True
            log.info(f"Hotkey '{HOTKEY_TRIGGER}' registered.")
            while self._active:
                time.sleep(0.5)
        except ImportError:
            log.error("'keyboard' package not found. Run: pip install keyboard")
        except Exception as e:
            log.error(f"IDE bridge error: {e}")

    def _on_hotkey_triggered(self):
        """Called on hotkey press — runs in keyboard hook thread."""
        log.info("IDE bridge hotkey triggered!")
        threading.Thread(target=self._capture_clipboard, daemon=True).start()

    def _capture_clipboard(self):
        """
        Capture currently selected text from any app via clipboard.
        Sends Ctrl+C first to copy the selection.
        """
        try:
            # Save current clipboard
            old_clipboard = ""
            try:
                old_clipboard = pyperclip.paste() or ""
            except Exception:
                pass

            # Clear clipboard so we can detect if copy worked
            pyperclip.copy("")
            time.sleep(0.05)

            # Trigger copy in the active window
            import keyboard
            keyboard.send("ctrl+c")
            time.sleep(0.2)  # Give app time to copy

            # Read new clipboard
            captured = ""
            try:
                captured = pyperclip.paste() or ""
            except Exception:
                pass

            if captured and captured != old_clipboard:
                log.info(f"Captured {len(captured)} chars from clipboard.")
                if self._callback:
                    self._callback(captured)
            else:
                log.warning("No new text captured from clipboard.")
                # Restore old clipboard
                try:
                    pyperclip.copy(old_clipboard)
                except Exception:
                    pass

        except Exception as e:
            log.error(f"Clipboard capture failed: {e}")

    def paste_to_clipboard(self, text: str):
        """Helper to put text into clipboard."""
        try:
            pyperclip.copy(text)
        except Exception as e:
            log.error(f"Failed to write clipboard: {e}")

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def hotkey(self) -> str:
        return HOTKEY_TRIGGER


# Standalone test
if __name__ == "__main__":
    def on_capture(code: str):
        print(f"\n📋 Captured code:\n{code}\n")

    bridge = IDEBridge(on_code_captured=on_capture)
    bridge.start()
    print(f"🔗 IDE Bridge running. Press {HOTKEY_TRIGGER} with text selected.")
    print("   Press Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
        print("\nDone.")
