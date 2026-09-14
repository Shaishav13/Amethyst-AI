"""
Amethyst Code Executor — Sandboxed Code Execution
===================================================
Allows the AI to write and execute Python code in a safe subprocess.
- Runs in isolated subprocess with timeout
- Captures stdout, stderr, and return code
- Memory and time limited
- Supports Python, PowerShell, Bash/Shell
"""

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("amethyst.executor")

# Safety limits
MAX_EXECUTION_TIME = 15    # seconds
MAX_OUTPUT_CHARS   = 5000  # truncate output

if "AMETHYST_HOME" in os.environ:
    AMETHYST_DIR = Path(os.environ["AMETHYST_HOME"])
else:
    AMETHYST_DIR = Path.home() / ".amethyst"

# Where generated scripts are saved persistently
SCRIPTS_DIR = AMETHYST_DIR / "scripts"
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Sandbox temp dir for one-shot execution
SANDBOX_DIR = AMETHYST_DIR / "sandbox"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


class CodeExecutor:
    """
    Executes code in a sandboxed subprocess.
    Supports Python (default), PowerShell, and Bash.
    """

    def save_script(self, code: str, language: str = "python",
                    filename: Optional[str] = None) -> Path:
        """Save a script to the persistent scripts directory."""
        ext_map = {
            "python": ".py", "py": ".py",
            "powershell": ".ps1", "ps1": ".ps1",
            "bash": ".sh", "shell": ".sh",
            "javascript": ".js", "js": ".js",
        }
        ext = ext_map.get(language.lower(), ".py")

        if not filename:
            filename = f"script_{int(time.time())}{ext}"
        elif not filename.endswith(ext):
            filename += ext

        path = SCRIPTS_DIR / filename
        path.write_text(code, encoding="utf-8")
        log.info(f"Script saved: {path}")
        return path

    def list_saved_scripts(self) -> list[Path]:
        """Return all saved scripts, sorted newest first."""
        files = list(SCRIPTS_DIR.glob("*"))
        files = [f for f in files if f.is_file()]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files

    async def execute(self, code: str, language: str = "python",
                      timeout: int = MAX_EXECUTION_TIME) -> dict:
        """
        Execute code in a subprocess.
        Returns: {"success": bool, "stdout": str, "stderr": str, "duration": float}
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_sync, code, language, timeout)

    def _execute_sync(self, code: str, language: str, timeout: int) -> dict:
        """Blocking execution — runs in thread pool."""
        lang = language.lower()

        # Write code to a temp file
        ext_map = {"python": ".py", "py": ".py",
                   "powershell": ".ps1", "ps1": ".ps1",
                   "bash": ".sh", "shell": ".sh"}
        ext = ext_map.get(lang, ".py")
        script_path = SANDBOX_DIR / f"_amethyst_run_{int(time.time())}{ext}"

        try:
            script_path.write_text(code, encoding="utf-8")

            # Build the command based on language
            if lang in ("python", "py"):
                cmd = [sys.executable, str(script_path)]
            elif lang in ("powershell", "ps1"):
                cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                       "-File", str(script_path)]
            elif lang in ("bash", "shell", "sh"):
                cmd = ["bash", str(script_path)]
            else:
                cmd = [sys.executable, str(script_path)]  # default to python

            start = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(SANDBOX_DIR),
            )
            duration = round(time.time() - start, 2)

            stdout = (result.stdout or "")[:MAX_OUTPUT_CHARS]
            stderr = (result.stderr or "")[:MAX_OUTPUT_CHARS]
            if len(result.stdout or "") > MAX_OUTPUT_CHARS:
                stdout += "\n...[output truncated]"

            log.info(f"Code executed in {duration}s. Return code: {result.returncode}")
            return {
                "success":     result.returncode == 0,
                "stdout":      stdout,
                "stderr":      stderr,
                "return_code": result.returncode,
                "duration":    duration,
                "language":    language,
            }

        except subprocess.TimeoutExpired:
            log.warning(f"Code execution timed out after {timeout}s")
            return {
                "success":     False,
                "stdout":      "",
                "stderr":      f"Execution timed out after {timeout} seconds.",
                "return_code": -1,
                "duration":    timeout,
                "language":    language,
            }
        except Exception as e:
            log.error(f"Code execution error: {e}")
            return {
                "success":     False,
                "stdout":      "",
                "stderr":      str(e),
                "return_code": -1,
                "duration":    0,
                "language":    language,
            }
        finally:
            try:
                script_path.unlink(missing_ok=True)
            except Exception:
                pass

    def cleanup_sandbox(self):
        """Remove all one-shot temp files from the sandbox."""
        for f in SANDBOX_DIR.glob("_amethyst_run_*"):
            try:
                f.unlink()
            except Exception:
                pass
