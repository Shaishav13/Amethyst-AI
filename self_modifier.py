import os
import re
import logging
from datetime import datetime

log = logging.getLogger("amethyst.modifier")

class SelfModifier:
    """
    Allows Amethyst to safely upgrade its own source files.
    Requires strict logging of all changes before they are applied.
    """
    
    @staticmethod
    def get_log_dir() -> str:
        if "AMETHYST_HOME" in os.environ:
            base = os.environ["AMETHYST_HOME"]
        else:
            base = os.path.join(os.path.expanduser("~"), ".amethyst")
        log_dir = os.path.join(base, "update_logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    @classmethod
    def scan_and_apply(cls, full_text: str) -> str:
        """
        Scans AI output for [UPGRADE:filename] followed by a code block.
        If found, logs the intent and applies the change.
        Returns a status string to be injected into the UI.
        """
        pattern = re.compile(r"\[UPGRADE:([^\]]+)\]\s*```[a-zA-Z]*\n(.*?)```", re.DOTALL)
        match = pattern.search(full_text)
        
        if not match:
            return ""
            
        filename = match.group(1).strip()
        new_code = match.group(2).strip()
        
        # Security: Only allow editing .py, .bat, .md, .txt files in the current directory
        allowed_exts = (".py", ".bat", ".md", ".txt", ".css", ".html", ".js")
        if not filename.endswith(allowed_exts) or "/" in filename or "\\" in filename:
            return f"\n\n[SYS.ERR] Upgrade rejected. Invalid filename '{filename}'. Must be in root directory and allowed extension."
            
        # Get absolute path
        # Assuming the root directory is where ui_main.py is located
        root_dir = os.path.dirname(os.path.abspath(__import__("sys").argv[0]))
        filepath = os.path.join(root_dir, filename)
        
        # Log the change
        log_dir = cls.get_log_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(log_dir, f"{timestamp}_{filename}.log")
        
        try:
            old_code = ""
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    old_code = f.read()
                    
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"--- AMETHYST SELF-UPGRADE LOG ---\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Target File: {filename}\n")
                f.write(f"Absolute Path: {filepath}\n")
                f.write(f"\n--- PREVIOUS CONTENT ---\n{old_code}\n")
                f.write(f"\n--- NEW CONTENT ---\n{new_code}\n")
                
            log.info(f"Upgrade log written to {log_file}")
            
        except Exception as e:
            return f"\n\n[SYS.ERR] Upgrade failed during logging phase: {e}"
            
        # Apply the change
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_code)
            return f"\n\n[SYS.OK] UPGRADE APPLIED to '{filename}'. Log saved to update_logs. Restart required to take effect."
        except Exception as e:
            return f"\n\n[SYS.ERR] Upgrade failed while writing file '{filename}': {e}"
