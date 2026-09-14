"""
Amethyst Vision Engine — Screenshot Analysis
==============================================
Captures screenshots and analyzes them using a vision-capable
Ollama model (e.g., llava, llama3.2-vision, gemma3).
Gives the AI the ability to literally "see" what the user sees.
"""

import asyncio
import base64
import io
import logging
import os
import time
from typing import Optional, Callable

log = logging.getLogger("amethyst.vision")


class VisionEngine:
    """
    Screenshot capture + vision model analysis.
    Uses Ollama's vision-capable models to interpret images.
    """

    # Vision-capable models in Ollama (in preference order)
    VISION_MODELS = [
        "gemma3:4b",           # Gemma 3 has native vision
        "llava:latest",
        "llama3.2-vision:latest",
        "llava:7b",
        "llava:13b",
        "bakllava:latest",
    ]

    def __init__(self):
        if "AMETHYST_HOME" in os.environ:
            amethyst_dir = os.environ["AMETHYST_HOME"]
        else:
            amethyst_dir = os.path.join(os.path.expanduser("~"), ".amethyst")
        self._screenshot_dir = os.path.join(amethyst_dir, "screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)
        self._vision_model: Optional[str] = None

    async def detect_vision_model(self, available_models: set) -> Optional[str]:
        """Find the best available vision-capable model."""
        for model in self.VISION_MODELS:
            if model in available_models:
                self._vision_model = model
                log.info(f"Vision model detected: {model}")
                return model
            # Also check without tag
            base = model.split(":")[0]
            for avail in available_models:
                if avail.startswith(base):
                    self._vision_model = avail
                    log.info(f"Vision model detected: {avail}")
                    return avail
        log.warning("No vision-capable model found. Pull one with: ollama pull llava")
        return None

    def capture_screenshot(self) -> Optional[str]:
        """
        Capture the current screen and save as PNG.
        Returns the file path, or None on failure.
        """
        try:
            from PIL import ImageGrab

            screenshot = ImageGrab.grab()

            # Resize to save memory (vision models don't need 4K)
            max_dim = 1280
            w, h = screenshot.size
            if max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                screenshot = screenshot.resize((int(w * ratio), int(h * ratio)))

            filename = f"screenshot_{int(time.time())}.png"
            filepath = os.path.join(self._screenshot_dir, filename)
            screenshot.save(filepath, "PNG", optimize=True)

            log.info(f"Screenshot captured: {filepath} ({screenshot.size[0]}x{screenshot.size[1]})")
            return filepath

        except ImportError:
            log.error("Pillow not installed or ImageGrab unavailable.")
            return None
        except Exception as e:
            log.error(f"Screenshot capture failed: {e}")
            return None

    def image_to_base64(self, filepath: str) -> Optional[str]:
        """Convert an image file to base64 for Ollama API."""
        try:
            with open(filepath, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            log.error(f"Failed to encode image: {e}")
            return None

    async def analyze_screenshot(self, user_prompt: str = "",
                                  on_token: Optional[Callable[[str], None]] = None,
                                  image_b64: Optional[str] = None) -> str:
        """
        Analyze an image with the vision model.
        If image_b64 is provided, analyzes that image. Otherwise captures the screen.
        Returns the full analysis text.
        """
        if not self._vision_model:
            return "⚠️ No vision model available. Pull one with: ollama pull llava"

        img_b64 = image_b64
        if not img_b64:
            # 1. Capture screenshot
            loop = asyncio.get_event_loop()
            filepath = await loop.run_in_executor(None, self.capture_screenshot)

            if not filepath:
                return "⚠️ Failed to capture screenshot."

            # 2. Encode to base64
            img_b64 = self.image_to_base64(filepath)
            if not img_b64:
                return "⚠️ Failed to encode screenshot."

        # 3. Build prompt
        prompt = user_prompt.strip() if user_prompt.strip() else "Describe what you see on this screen. If there are any errors, explain them."

        # 4. Send to vision model
        import ollama as ollama_lib
        from ai_engine import AmethystEngine
        client = ollama_lib.AsyncClient()

        full_response = ""
        try:
            async for chunk in await client.chat(
                model=self._vision_model,
                messages=[
                    {
                        "role": "system",
                        "content": AmethystEngine.BASE_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [img_b64],
                    }
                ],
                stream=True,
                options={"num_ctx": 4096, "num_predict": 1024, "temperature": 0.3},
            ):
                token = chunk.message.content
                if token:
                    full_response += token
                    if on_token:
                        on_token(token)

        except Exception as e:
            error_msg = f"⚠️ Vision analysis failed: {e}"
            log.error(error_msg)
            full_response = error_msg

        # 5. Cleanup old screenshots (keep last 5)
        self._cleanup_old_screenshots()

        return full_response

    def _cleanup_old_screenshots(self, keep: int = 5):
        """Remove old screenshots, keeping only the most recent ones."""
        try:
            files = sorted(
                [f for f in os.listdir(self._screenshot_dir) if f.startswith("screenshot_")],
                reverse=True
            )
            for old_file in files[keep:]:
                os.remove(os.path.join(self._screenshot_dir, old_file))
        except Exception:
            pass

    @property
    def has_vision(self) -> bool:
        return self._vision_model is not None

    @property
    def model_name(self) -> Optional[str]:
        return self._vision_model
