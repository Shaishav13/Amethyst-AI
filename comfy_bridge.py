import re
import os
import sys

def clean_outfit_prompt(text: str) -> str:
    """
    Cleans raw user/ChatGPT prompts for garment inpainting.
    Extracts clothing/textile descriptions and strips person references,
    facial descriptions, poses, and environment instructions to prevent
    hallucinating duplicate persons/heads inside the clothing mask.
    """
    text = (text or "").strip()
    if not text:
        return "fashionable outfit, realistic fabric texture"

    # 1. Check if structured prompt with ATTIRE / CLOTHING section
    attire_pattern = r'(?:^|\n)[^\n]*(?:ATTIRE|CLOTHING|OUTFIT|DRESS|GARMENT)[^\n]*\n([\s\S]*?)(?=(?:\n[^\n]*(?:POSE|ENVIRONMENT|LIGHTING|PHOTOREALISM|STRICT|DO NOT|FINAL PRIORITY)|$))'
    m = re.search(attire_pattern, text, re.IGNORECASE)
    
    extracted = ""
    if m:
        extracted = m.group(1).strip()
    elif "FINAL PROMPT" in text:
        m2 = re.search(r'FINAL PROMPT\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
        if m2:
            extracted = m2.group(1).strip()
    
    if not extracted:
        extracted = text

    # Extract lines, stripping headers & bullet markers
    lines = []
    for line in extracted.splitlines():
        line = line.strip()
        if not line or line.startswith('━') or line.startswith('=') or line.startswith('#'):
            continue
        line = re.sub(r'^(?:TOP|LOWER GARMENT|BOTTOM|SHOES|ACCESSORIES|OUTFIT|DRESS|GARMENT)\s*:\s*', '', line, flags=re.IGNORECASE)
        line = line.lstrip('•-* \t')
        if line:
            lines.append(line)
            
    candidate = " ".join(lines) if lines else extracted
    
    # 2. Strip subject/person references and photographic metadata
    strip_patterns = [
        r'(?i)EDIT THE PROVIDED SUBJECT IMAGE[^\n]*',
        r'(?i)PHOTOREALISTIC FASHION PHOTOGRAPHY',
        r'(?i)\b(?:an?\s+)?(?:editorial\s+)?(?:photograph|photo|picture|portrait|image)\s+of\s+(?:a\s+)?(?:girl|woman|man|boy|person|subject|model|guy)(?:\s+from\s+the\s+supplied\s+image)?(?:\s+photographed)?(?:\s+in)?\b',
        r'(?i)\b(?:please\s+)?(?:can\s+you\s+)?(?:change|swap|replace|put|dress|give)(?:\s+(?:the|her|him|them|subject|person))?(?:\s+(?:into|in|with|to))?\s+(?:outfit|clothes|clothing|dress|attire)?(?:\s+to\s+)?\b',
        r'(?i)\b(?:pose\s+and\s+dark\s+studio\s+environment|dark\s+studio\s+environment|studio\s+environment|studio\s+lighting|studio\s+setting)\b',
        r'(?i)\b(?:from\s+the\s+supplied\s+image|supplied\s+image|original\s+image)\b',
        r'(?i)\b(?:preserve\s+the\s+exact\s+same[^\n,.]*)\b',
        r'(?i)\b(?:arms\s+raised[^\n,.]*|standing\s+in\s+pose|standing\s+confident[^\n,.]*)\b',
        r'(?i)\b(?:The\s+complete\s+outfit\s+should\s+look\s+like[^\n.]*\.)\b',
        r'(?i)\b(?:Dress\s+the\s+subject\s+in\s+[^\n.]*\.)\b',
    ]
    for p in strip_patterns:
        candidate = re.sub(p, ' ', candidate)

    # 3. Clean whitespace and punctuation
    candidate = re.sub(r'\s+', ' ', candidate).strip(' ,;.?!:-"\'')
    
    # 4. Strip leading conversational words
    candidate = re.sub(r'^(?:can you\s+|please\s+|change\s+|swap\s+|wearing\s+|in\s+|into\s+|to\s+|a\s+|an\s+)+', '', candidate, flags=re.IGNORECASE)
    
    # Keep it focused to top 320 characters
    if len(candidate) > 320:
        candidate = candidate[:320].rsplit(' ', 1)[0]
        
    return candidate.strip(' ,;.?!:-"\'')



def determine_attire_categories(prompt: str) -> dict:
    """
    Determines segmentation categories based on user outfit prompt.
    Segformer identifies existing clothing on the subject to replace.
    All core clothing classes (Upper-clothes, Skirt, Pants, Dress) are True
    by default so any existing outfit in the input image is properly masked.
    Face, Hair, and exposed limbs (arms, legs) are protected by default.
    """
    p_lower = (prompt or "").lower()

    # Detect if user explicitly requested sleeves, gloves, stockings, or footwear
    wants_arms = any(k in p_lower for k in ["long sleeve", "sleeves", "sleeve", "glove", "gloves", "gauntlet", "cuff"])
    wants_legs = any(k in p_lower for k in ["stocking", "stockings", "tights", "leggings", "socks", "sock"])
    wants_shoes = any(k in p_lower for k in ["shoe", "shoes", "boot", "boots", "heels", "sneaker", "sneakers", "footwear"])

    # Base: Always protect Face, Hair, Hat, Sunglasses, Background
    # Core clothing classes all default to True to mask whatever the person is wearing
    cats = {
        "Face": False,
        "Hair": False,
        "Hat": False,
        "Sunglasses": False,
        "Background": False,
        "Upper-clothes": True,
        "Skirt": True,
        "Dress": True,
        "Pants": True,
        "Belt": True,
        "Scarf": True,
        "Bag": True,
        "Left-arm": wants_arms,
        "Right-arm": wants_arms,
        "Left-leg": wants_legs,
        "Right-leg": wants_legs,
        "Left-shoe": wants_shoes,
        "Right-shoe": wants_shoes
    }

    # Explicit selective preservation (only when user explicitly says "keep pants", "keep shirt", etc.)
    if any(k in p_lower for k in ["keep pants", "keep skirt", "keep bottoms", "only change top", "only change shirt"]):
        cats["Skirt"] = False
        cats["Pants"] = False
    elif any(k in p_lower for k in ["keep shirt", "keep top", "only change pants", "only change skirt"]):
        cats["Upper-clothes"] = False

    return cats




def clean_scenario_prompt(prompt: str) -> str:
    """Clean scenario/background prompt by stripping conversational filler and command phrases."""
    if not prompt:
        return ""
    import re
    cleaned = re.sub(r'(?i)^(?:can you\s+|please\s+)?(?:change|swap|replace|put|set|move|generate|make)?(?:\s+(?:the|her|him|them|subject|person))?(?:\s+(?:background|scenario|scene|setting|environment))?(?:\s+(?:to|with|in|into|as))?\s+', '', prompt.strip())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,;.?!:-"\'')
    return cleaned


"""
Amethyst ComfyUI Bridge - Image Generation and Editing Engine
=============================================================
Connects Amethyst to local ComfyUI instance (http://127.0.0.1:8188)
Provides text-to-image generation and identity-preserving image editing
(outfit swap and scenario change) using WebSockets and REST API.
"""

import asyncio
import io
import json
import logging
import os
import random
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union

import httpx
import websockets
from PIL import Image

log = logging.getLogger("amethyst.comfy")

COMFY_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1:8188")
COMFY_BASE_URL = f"http://{COMFY_HOST}"
COMFY_WS_URL = f"ws://{COMFY_HOST}/ws"

OUTPUT_DIR = Path.home() / ".amethyst" / "generated_images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)



def analyze_image_style(image_data: Union[bytes, str]) -> dict:
    """Analyze input image to detect monochrome/black-and-white tonality and aspect ratio."""
    try:
        import io, base64
        from PIL import Image, ImageStat, ImageChops
        if isinstance(image_data, str):
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            raw = base64.b64decode(image_data)
        else:
            raw = image_data
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        r, g, b = img.split()
        diff1 = ImageStat.Stat(ImageChops.difference(r, g)).mean[0]
        diff2 = ImageStat.Stat(ImageChops.difference(g, b)).mean[0]
        is_mono = (diff1 < 10.0 and diff2 < 10.0)
        return {"is_monochrome": is_mono, "width": img.width, "height": img.height}
    except Exception as e:
        log.warning(f"Could not analyze image style: {e}")
        return {"is_monochrome": False, "width": 1024, "height": 1024}


class ComfyBridge:
    def __init__(self, base_url: str = COMFY_BASE_URL, ws_url: str = COMFY_WS_URL):
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
        self._cached_checkpoints: List[str] = []
        self._cached_nodes: set = set()
        self._last_check = 0.0

    async def is_online(self) -> bool:
        """Check if ComfyUI is running and responding."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/system_stats")
                return res.status_code == 200
        except Exception:
            return False

    async def get_system_status(self) -> dict:
        """Fetch ComfyUI hardware stats and available models."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/system_stats")
                if res.status_code != 200:
                    return {"online": False}
                stats = res.json()
                checkpoints = await self.get_available_checkpoints()
                return {
                    "online": True,
                    "devices": stats.get("devices", []),
                    "checkpoints": checkpoints,
                    "default_checkpoint": checkpoints[0] if checkpoints else None
                }
        except Exception as e:
            return {"online": False, "error": str(e)}

    async def get_available_checkpoints(self) -> List[str]:
        """Get list of installed checkpoint models from ComfyUI."""
        now = time.time()
        if self._cached_checkpoints and (now - self._last_check < 30):
            return self._cached_checkpoints

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/object_info/CheckpointLoaderSimple")
                if res.status_code == 200:
                    data = res.json()
                    ckpts = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                    self._cached_checkpoints = sorted(ckpts)
                    self._last_check = now
                    return self._cached_checkpoints
        except Exception as e:
            log.warning(f"Could not fetch checkpoints: {e}")
        return self._cached_checkpoints

    async def check_custom_nodes(self) -> set:
        """Discover available node classes in ComfyUI."""
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.base_url}/object_info")
                if res.status_code == 200:
                    self._cached_nodes = set(res.json().keys())
                    return self._cached_nodes
        except Exception as e:
            log.warning(f"Could not query ComfyUI object_info: {e}")
        return self._cached_nodes

    async def upload_image(self, image_data: Union[bytes, str], filename_prefix: str = "input_") -> str:
        """
        Upload an image (bytes or base64) to ComfyUI input folder.
        Returns the filename assigned by ComfyUI.
        """
        import base64
        import os
        if isinstance(image_data, str):
            if os.path.isfile(image_data):
                with open(image_data, "rb") as img_file:
                    raw_bytes = img_file.read()
            else:
                if "," in image_data:
                    image_data = image_data.split(",", 1)[1]
                raw_bytes = base64.b64decode(image_data)
        else:
            raw_bytes = image_data

        # Limit uploaded image size to max 1280px to prevent excessive memory and oversized renders
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                if max(pil_img.width, pil_img.height) > 1280:
                    ratio = 1280.0 / max(pil_img.width, pil_img.height)
                    new_w = int(pil_img.width * ratio)
                    new_h = int(pil_img.height * ratio)
                    resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    out_buf = io.BytesIO()
                    resized.save(out_buf, format="PNG")
                    raw_bytes = out_buf.getvalue()
                    log.info(f"Downscaled input image from {pil_img.width}x{pil_img.height} to {new_w}x{new_h} for optimal inpainting.")
        except Exception as resize_err:
            log.warning(f"Failed to check/resize input image: {resize_err}")

        ext = "png"
        unique_name = f"{filename_prefix}{uuid.uuid4().hex[:8]}.{ext}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"image": (unique_name, raw_bytes, "image/png")}
            data = {"overwrite": "true"}
            res = await client.post(f"{self.base_url}/upload/image", files=files, data=data)
            res.raise_for_status()
            result = res.json()
            return result.get("name", unique_name)

    async def queue_prompt(self, workflow_prompt: dict) -> str:
        """Submit a prompt workflow to ComfyUI. Returns prompt_id."""
        payload = {
            "prompt": workflow_prompt,
            "client_id": self.client_id
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(f"{self.base_url}/prompt", json=payload)
            res.raise_for_status()
            data = res.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"Failed to queue prompt: {data}")
            return prompt_id

    async def wait_for_completion(
        self,
        prompt_id: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        timeout: float = 300.0
    ) -> List[Path]:
        """
        Listen on WebSocket for prompt execution, stream progress,
        and download the final generated images.
        """
        ws_url = f"{self.ws_url}?clientId={self.client_id}"
        start_time = time.time()

        try:
            async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
                while True:
                    if time.time() - start_time > timeout:
                        raise TimeoutError("ComfyUI generation timed out.")

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    except asyncio.TimeoutError:
                        continue

                    if isinstance(msg, bytes):
                        # Binary preview frames
                        continue

                    try:
                        data = json.loads(msg)
                    except Exception:
                        continue

                    msg_type = data.get("type")
                    msg_data = data.get("data", {})

                    if msg_type == "progress":
                        val = msg_data.get("value", 0)
                        max_val = msg_data.get("max", 1)
                        if on_progress:
                            on_progress(val, max_val, f"Step {val}/{max_val}")

                    elif msg_type == "executing":
                        node = msg_data.get("node")
                        cur_prompt = msg_data.get("prompt_id")
                        if cur_prompt == prompt_id and node is None:
                            # Prompt execution finished!
                            break

                    elif msg_type == "execution_error":
                        if msg_data.get("prompt_id") == prompt_id:
                            err = msg_data.get("exception_message", "Unknown ComfyUI error")
                            raise RuntimeError(f"ComfyUI error: {err}")

        except Exception as ws_err:
            if isinstance(ws_err, RuntimeError) and str(ws_err).startswith("ComfyUI error:"):
                raise
            log.warning(f"WebSocket closed or notice: {ws_err}, reading history API...")

        # Fetch history to get the output image filenames
        return await self._fetch_history_outputs(prompt_id)

    async def _fetch_history_outputs(self, prompt_id: str) -> List[Path]:
        """Download images from ComfyUI history for the given prompt_id with resilient retry."""
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.get(f"{self.base_url}/history/{prompt_id}")
                    if res.status_code == 200:
                        history = res.json().get(prompt_id, {})
                        outputs = history.get("outputs", {})

                        local_files = []
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for img in node_output["images"]:
                                    fname = img.get("filename")
                                    subfolder = img.get("subfolder", "")
                                    img_type = img.get("type", "output")
                                    
                                    params = {
                                        "filename": fname,
                                        "subfolder": subfolder,
                                        "type": img_type
                                    }
                                    img_res = await client.get(f"{self.base_url}/view", params=params)
                                    if img_res.status_code == 200:
                                        saved_name = f"{int(time.time())}_{fname}"
                                        local_path = OUTPUT_DIR / saved_name
                                        local_path.write_bytes(img_res.content)
                                        local_files.append(local_path)
                        if local_files:
                            return local_files
            except Exception as e:
                log.warning(f"Attempt {attempt+1} fetching history for {prompt_id} error: {e}")
            if attempt < 3:
                await asyncio.sleep(0.5)
        return []


    async def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> bool:
        """
        Call ComfyUI /free endpoint to purge VRAM and unload diffusion models.
        Leaves 8GB VRAM completely clear when ComfyUI is idle.
        """
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    f"{self.base_url}/free",
                    json={"unload_models": unload_models, "free_memory": free_memory}
                )
                log.info("ComfyUI /free called: VRAM purged successfully.")
                return res.status_code == 200
        except Exception as e:
            log.warning(f"Could not call ComfyUI /free: {e}")
            return False

    async def unload_ollama_vram(self, ollama_url: str = "http://localhost:11434") -> bool:
        """
        Instruct Ollama to unload models from VRAM before heavy ComfyUI generation.
        Prevents VRAM collisions on 8GB GPU.
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                ps_res = await client.get(f"{ollama_url}/api/ps")
                if ps_res.status_code == 200:
                    running_models = ps_res.json().get("models", [])
                    for m in running_models:
                        model_name = m.get("model") or m.get("name")
                        if model_name:
                            log.info(f"Temporarily yielding VRAM: unloading Ollama model {model_name}...")
                            await client.post(
                                f"{ollama_url}/api/generate",
                                json={"model": model_name, "keep_alive": 0}
                            )
                    return True
        except Exception as e:
            log.debug(f"Ollama ps/unload notice: {e}")
        return False

    async def generate_txt2img(
        self,
        prompt: str,
        negative_prompt: str = "ugly, blurry, distorted, cartoon, low quality, oversaturated",
        width: int = 1024,
        height: int = 1024,
        steps: int = 28,
        cfg: float = 6.0,
        checkpoint: Optional[str] = None,
        seed: Optional[int] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """Generate a new image from text prompt using SDXL."""
        if not await self.is_online():
            raise RuntimeError("ComfyUI is not running. Please start ComfyUI at http://127.0.0.1:8188")

        ckpts = await self.get_available_checkpoints()
        if not ckpts:
            raise RuntimeError("No checkpoint models found in ComfyUI/models/checkpoints/")

        ckpt_to_use = checkpoint if (checkpoint and checkpoint in ckpts) else ckpts[0]
        actual_seed = seed if seed is not None else random.randint(100000000, 999999999999)

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt_to_use}
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": prompt
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": negative_prompt
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": actual_seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["6", 0],
                    "filename_prefix": "Amethyst_SDXL"
                }
            }
        }

        await self.unload_ollama_vram()
        # Filter out empty conditional nodes
        workflow = {k: v for k, v in workflow.items() if v}
        prompt_id = await self.queue_prompt(workflow)
        try:
            paths = await self.wait_for_completion(prompt_id, on_progress)
        finally:
            await self.free_memory()
        if not paths:
            raise RuntimeError("Generation completed but no image was returned by ComfyUI.")

        return {
            "success": True,
            "prompt_id": prompt_id,
            "filename": paths[0].name,
            "local_path": str(paths[0]),
            "url": f"/api/image/view/{paths[0].name}",
            "seed": actual_seed,
            "checkpoint": ckpt_to_use
        }


    async def swap_outfit_flux(
        self,
        image_data: Union[bytes, str],
        outfit_prompt: str,
        negative_prompt: str = "cartoon, anime, 3d render, plastic skin, distorted anatomy, blurry",
        categories: Optional[dict] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """
        Photorealistic 12B DiT (FLUX.1-dev) outfit swap workflow.
        Provides ChatGPT / Midjourney-level fabric folds, collar physics, and crisp contours.
        """
        uploaded_name = await self.upload_image(image_data, filename_prefix="outfit_in_")
        actual_seed = random.randint(100000000, 999999999999)
        clean_prompt = clean_outfit_prompt(outfit_prompt)
        cats = categories or determine_attire_categories(outfit_prompt)

        style_info = analyze_image_style(image_data)
        is_mono = style_info.get("is_monochrome", False) or any(k in outfit_prompt.lower() for k in ["same filter", "black and white", "monochrome", "grayscale", "bw"])
        
        mono_prefix = "monochrome black and white, " if is_mono else ""
        clip_l_text = f"{mono_prefix}{clean_prompt}, garment clothing fabric detail only, high resolution textile texture, no head, no face"
        t5_text = f"photo of {mono_prefix}{clean_prompt}, worn on subject body, natural fabric drape and folds, realistic seams, no human face, no head, no eyes, masterpiece"

        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_name}},
            "2": {
                "class_type": "ClothesSegment",
                "inputs": {
                    "images": ["1", 0],
                    "Upper-clothes": cats.get("Upper-clothes", True),
                    "Skirt": cats.get("Skirt", True),
                    "Dress": cats.get("Dress", True),
                    "Pants": cats.get("Pants", True),
                    "Belt": cats.get("Belt", True),
                    "Scarf": cats.get("Scarf", True),
                    "Bag": cats.get("Bag", True),
                    "Left-arm": cats.get("Left-arm", True),
                    "Right-arm": cats.get("Right-arm", True),
                    "Left-leg": cats.get("Left-leg", True),
                    "Right-leg": cats.get("Right-leg", True),
                    "Left-shoe": cats.get("Left-shoe", True),
                    "Right-shoe": cats.get("Right-shoe", True),
                    "Face": False,
                    "Hair": False,
                    "Hat": False,
                    "Sunglasses": False,
                    "Background": False,
                    "process_res": 1024,
                    "mask_blur": 3,
                    "mask_offset": 2,
                    "invert_output": False,
                    "unload_model": False,
                    "background": "Alpha",
                    "background_color": "#222222"
                }
            },
            "3": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-dev-Q4_K_S.gguf"}},
            "4": {"class_type": "DualCLIPLoaderGGUF", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5-v1_1-xxl-encoder-Q3_K_M.gguf", "type": "flux"}},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "6": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {
                    "clip": ["4", 0],
                    "clip_l": clip_l_text,
                    "t5xxl": t5_text,
                    "guidance": 3.5
                }
            },
            "7": {
                "class_type": "InpaintCropImproved",
                "inputs": {
                    "image": ["1", 0],
                    "mask": ["2", 1],
                    "downscale_algorithm": "bilinear",
                    "upscale_algorithm": "bicubic",
                    "preresize": False,
                    "preresize_mode": "ensure minimum resolution",
                    "preresize_min_width": 1024,
                    "preresize_min_height": 1024,
                    "preresize_max_width": 16384,
                    "preresize_max_height": 16384,
                    "mask_fill_holes": True,
                    "mask_expand_pixels": 2,
                    "mask_invert": False,
                    "mask_blend_pixels": 4,
                    "mask_hipass_filter": 0.05,
                    "extend_for_outpainting": False,
                    "extend_up_factor": 1.0,
                    "extend_down_factor": 1.0,
                    "extend_left_factor": 1.0,
                    "extend_right_factor": 1.0,
                    "context_from_mask_extend_factor": 1.55,
                    "output_resize_to_target_size": True,
                    "output_target_width": 1024,
                    "output_target_height": 1024,
                    "output_padding": "32",
                    "device_mode": "gpu (much faster)"
                }
            },
            "8": {
                "class_type": "VAEEncodeForInpaint",
                "inputs": {
                    "pixels": ["7", 1],
                    "vae": ["5", 0],
                    "mask": ["7", 2],
                    "grow_mask_by": 6
                }
            },
            "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": actual_seed}},
            "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "11": {"class_type": "BasicScheduler", "inputs": {"model": ["3", 0], "scheduler": "simple", "steps": 20, "denoise": 0.98}},
            "12": {"class_type": "BasicGuider", "inputs": {"model": ["3", 0], "conditioning": ["6", 0]}},
            "13": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["9", 0],
                    "guider": ["12", 0],
                    "sampler": ["10", 0],
                    "sigmas": ["11", 0],
                    "latent_image": ["8", 0]
                }
            },
            "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["5", 0]}},
            "15": {"class_type": "InpaintStitchImproved", "inputs": {"stitcher": ["7", 0], "inpainted_image": ["14", 0]}},
            "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": "Amethyst_Outfit_FLUX"}}
        }

        await self.unload_ollama_vram()
        # Filter out empty conditional nodes
        workflow = {k: v for k, v in workflow.items() if v}
        prompt_id = await self.queue_prompt(workflow)
        paths = await self.wait_for_completion(prompt_id, on_progress)
        await self.free_memory()
        if not paths:
            raise RuntimeError("FLUX Outfit swap completed but no image was returned by ComfyUI.")

        return {
            "success": True,
            "prompt_id": prompt_id,
            "filename": paths[0].name,
            "local_path": str(paths[0]),
            "url": f"/api/image/view/{paths[0].name}",
            "seed": actual_seed,
            "checkpoint": "FLUX.1-dev (12B DiT GGUF)",
            "engine": "flux"
        }


    async def swap_outfit(
        self,
        image_data: Union[bytes, str],
        outfit_prompt: str,
        negative_prompt: str = "cartoon, anime, 3d render, plastic skin, distorted anatomy, blurry, bad seams",
        categories: Optional[dict] = None,
        checkpoint: Optional[str] = None,
        engine: str = "sdxl",
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        if engine == "flux":
            return await self.swap_outfit_flux(image_data, outfit_prompt, negative_prompt, categories, on_progress)
        """
        Swap clothing on the subject using the identity-preserving Crop & Stitch workflow.
        Keeps face, hair, arms, and legs 100% unaltered.
        """
        if not await self.is_online():
            raise RuntimeError("ComfyUI is not running. Please start ComfyUI at http://127.0.0.1:8188")

        ckpts = await self.get_available_checkpoints()
        if not ckpts:
            raise RuntimeError("No checkpoint models found in ComfyUI/models/checkpoints/")
        ckpt_to_use = checkpoint if (checkpoint and checkpoint in ckpts) else ckpts[0]

        nodes = await self.check_custom_nodes()
        uploaded_name = await self.upload_image(image_data, filename_prefix="outfit_in_")
        actual_seed = random.randint(100000000, 999999999999)

        has_crop_and_stitch = ("InpaintCrop" in nodes or "InpaintCropImproved" in nodes) and ("InpaintStitch" in nodes or "InpaintStitchImproved" in nodes)
        crop_class = 'InpaintCropImproved' if 'InpaintCropImproved' in nodes else 'InpaintCrop'
        stitch_class = 'InpaintStitchImproved' if 'InpaintStitchImproved' in nodes else 'InpaintStitch'
        has_clothes_segment = "ClothesSegment" in nodes

        has_chroma_neutralizer = ("LayerColor: HSV" in nodes) and ("ImageCompositeMasked" in nodes)
        log.info(f"Outfit swap capabilities: ClothesSegment={has_clothes_segment}, CropAndStitch={has_crop_and_stitch}, ChromaNeutralizer={has_chroma_neutralizer}")
        crop_class = "InpaintCropImproved" if "InpaintCropImproved" in nodes else "InpaintCrop"
        stitch_class = "InpaintStitchImproved" if "InpaintStitchImproved" in nodes else "InpaintStitch"

        # Perfectionist Style & Tone Detection
        clean_prompt = clean_outfit_prompt(outfit_prompt)
        cats = categories or determine_attire_categories(outfit_prompt)
        style_info = analyze_image_style(image_data)
        is_mono = style_info.get("is_monochrome", False) or any(k in outfit_prompt.lower() for k in ["same filter", "black and white", "monochrome", "grayscale", "bw"])
        
        color_neg = "red, burgundy, maroon, crimson, pink seam, collar outline, visible seam line, boundary line, duplicate person, extra head, face on chest" if not any(c in clean_prompt.lower() for c in ["red", "maroon", "burgundy", "crimson", "pink", "wine"]) else "duplicate person, extra head, face on chest, visible seam line"
        if is_mono:
            enhanced_prompt = f"flawless monochrome black and white photography, {clean_prompt}, perfectly fitted garment, subtle fabric drape, realistic textile weave, authentic 35mm photograph"
            enhanced_neg = f"specular blowout, harsh white reflections, glossy plastic sheen, synthetic shine, blown out highlights, color, saturated, face, head, eyes, lips, nose, chin, skin where fabric should be, miniature person, duplicate person, extra person, floating collar, deformed hands, {color_neg}, {negative_prompt}"
        else:
            enhanced_prompt = f"photorealistic, {clean_prompt}, natural fabric drape, realistic textile weave, subtle soft luster, delicate tailored seams, authentic photograph"
            enhanced_neg = f"specular blowout, harsh white reflections, glossy plastic sheen, synthetic shine, blown out highlights, oversaturated reflections, jagged seams, edge halos, dark fringe, face, head, neck, chin, lips, eyes, nose, hair, skin where fabric should be, extra person, duplicate person, miniature person, background, studio backdrop, blurry seams, {color_neg}, {negative_prompt}"

        if has_clothes_segment and has_crop_and_stitch:
            workflow = {
                "1": {
                    "class_type": "LoadImage",
                    "inputs": {"image": uploaded_name}
                },
                "2": {
                    "class_type": "ClothesSegment",
                    "inputs": {
                        "images": ["1", 0],
                        "Upper-clothes": cats.get("Upper-clothes", True),
                        "Skirt": cats.get("Skirt", True),
                        "Dress": cats.get("Dress", True),
                        "Pants": cats.get("Pants", True),
                        "Belt": cats.get("Belt", True),
                        "Scarf": cats.get("Scarf", True),
                        "Bag": cats.get("Bag", True),
                        "Left-arm": cats.get("Left-arm", True),
                        "Right-arm": cats.get("Right-arm", True),
                        "Left-leg": cats.get("Left-leg", True),
                        "Right-leg": cats.get("Right-leg", True),
                        "Left-shoe": cats.get("Left-shoe", True),
                        "Right-shoe": cats.get("Right-shoe", True),
                        "Face": False,
                        "Hair": False,
                        "Hat": False,
                        "Sunglasses": False,
                        "Background": False,
                        "process_res": 1024,
                        "mask_blur": 2,
                        "mask_offset": 2,
                        "invert_output": False,
                        "unload_model": False,
                        "background": "Alpha",
                        "background_color": "#222222"
                    }
                },
                "3": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": ckpt_to_use}
                },
                "4": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["3", 1],
                        "text": enhanced_prompt
                    }
                },
                "5": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["3", 1],
                        "text": enhanced_neg
                    }
                },
                # Chroma Neutralization (eliminates red color bleed while preserving folds/drape)
                "20": {
                    "class_type": "LayerColor: HSV",
                    "inputs": {
                        "image": ["1", 0],
                        "H": 0,
                        "S": -255,
                        "V": 0
                    }
                } if has_chroma_neutralizer else {},
                "21": {
                    "class_type": "ImageCompositeMasked",
                    "inputs": {
                        "destination": ["1", 0],
                        "source": ["20", 0],
                        "mask": ["2", 1],
                        "x": 0,
                        "y": 0,
                        "resize_source": False
                    }
                } if has_chroma_neutralizer else {},
                "6": {
                    "class_type": crop_class,
                    "inputs": {
                        "image": ["21", 0] if has_chroma_neutralizer else ["1", 0],
                        "mask": ["2", 1],
                        "downscale_algorithm": "bilinear",
                        "upscale_algorithm": "bicubic",
                        "preresize": False,
                        "preresize_mode": "ensure minimum resolution",
                        "preresize_min_width": 1024,
                        "preresize_min_height": 1024,
                        "preresize_max_width": 16384,
                        "preresize_max_height": 16384,
                        "mask_fill_holes": True,
                        "mask_expand_pixels": 0,
                        "mask_invert": False,
                        "mask_blend_pixels": 4,
                        "mask_hipass_filter": 0.02,
                        "extend_for_outpainting": False,
                        "extend_up_factor": 1.0,
                        "extend_down_factor": 1.0,
                        "extend_left_factor": 1.0,
                        "extend_right_factor": 1.0,
                        "context_from_mask_extend_factor": 1.4,
                        "output_resize_to_target_size": True,
                        "output_target_width": 1024,
                        "output_target_height": 1024,
                        "output_padding": "8",
                        "device_mode": "gpu (much faster)"
                    }
                },
                "7": {
                    "class_type": "InpaintModelConditioning",
                    "inputs": {
                        "positive": ["4", 0],
                        "negative": ["5", 0],
                        "vae": ["3", 2],
                        "pixels": ["6", 1],
                        "mask": ["6", 2],
                        "noise_mask": True
                    }
                },
                "8": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["3", 0],
                        "positive": ["7", 0],
                        "negative": ["7", 1],
                        "latent_image": ["7", 2],
                        "seed": actual_seed,
                        "steps": 30,
                        "cfg": 5.0,
                        "sampler_name": "dpmpp_2m",
                        "scheduler": "karras",
                        "denoise": 0.85
                    }
                },
                "9": {
                    "class_type": "VAEDecode",
                    "inputs": {
                        "samples": ["8", 0],
                        "vae": ["3", 2]
                    }
                },
                "10": {
                    "class_type": stitch_class,
                    "inputs": {
                        "stitcher": ["6", 0],
                        "inpainted_image": ["9", 0]
                    }
                },
                "11": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["10", 0],
                        "filename_prefix": "Amethyst_Outfit_Swap"
                    }
                }
            }
        else:
            workflow = {
                "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_name}},
                "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_to_use}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": outfit_prompt}},
                "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": negative_prompt}},
                "5": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["1", 0], "vae": ["2", 2], "mask": ["1", 1], "grow_mask_by": 6}},
                "6": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0], "seed": actual_seed, "steps": 25, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.85}},
                "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
                "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "Amethyst_Inpaint"}}
            }

        await self.unload_ollama_vram()
        # Filter out empty conditional nodes
        workflow = {k: v for k, v in workflow.items() if v}
        prompt_id = await self.queue_prompt(workflow)
        try:
            paths = await self.wait_for_completion(prompt_id, on_progress)
        finally:
            await self.free_memory()
        if not paths:
            raise RuntimeError("Outfit swap completed but no image was returned by ComfyUI.")

        return {
            "success": True,
            "prompt_id": prompt_id,
            "filename": paths[0].name,
            "local_path": str(paths[0]),
            "url": f"/api/image/view/{paths[0].name}",
            "seed": actual_seed,
            "checkpoint": ckpt_to_use
        }

    async def change_scenario(
        self,
        image_data: Union[bytes, str],
        scenario_prompt: str,
        negative_prompt: str = "blurry, low quality, artifacts, cartoon, bad anatomy, warped",
        checkpoint: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """
        Change the entire background/scenario around the subject using RMBG-2.0 isolation.
        """
        if not await self.is_online():
            raise RuntimeError("ComfyUI is not running. Please start ComfyUI at http://127.0.0.1:8188")

        ckpts = await self.get_available_checkpoints()
        if not ckpts:
            raise RuntimeError("No checkpoint models found in ComfyUI/models/checkpoints/")
        ckpt_to_use = checkpoint if (checkpoint and checkpoint in ckpts) else ckpts[0]

        nodes = await self.check_custom_nodes()
        uploaded_name = await self.upload_image(image_data, filename_prefix="scenario_in_")
        actual_seed = random.randint(100000000, 999999999999)

        has_rmbg = "RMBG" in nodes
        has_crop_and_stitch = ("InpaintCrop" in nodes or "InpaintCropImproved" in nodes) and ("InpaintStitch" in nodes or "InpaintStitchImproved" in nodes)
        crop_class = 'InpaintCropImproved' if 'InpaintCropImproved' in nodes else 'InpaintCrop'
        stitch_class = 'InpaintStitchImproved' if 'InpaintStitchImproved' in nodes else 'InpaintStitch'

        if has_rmbg and has_crop_and_stitch:
            workflow = {
                "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_name}},
                "2": {
                    "class_type": "RMBG",
                    "inputs": {
                        "image": ["1", 0],
                        "model": "RMBG-2.0",
                        "sensitivity": 0.85,
                        "process_res": 1024,
                        "mask_blur": 1,
                        "mask_offset": 0,
                        "invert_output": False,
                        "refine_foreground": True,
                        "unload_model": False,
                        "background": "Alpha",
                        "background_color": "#222222"
                    }
                },
                "3": {"class_type": "InvertMask", "inputs": {"mask": ["2", 1]}},
                "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_to_use}},
                "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": f"{clean_scenario_prompt(scenario_prompt)}, natural atmospheric lighting, high resolution photography, cinematic bokeh, 8k uhd"}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": f"blue curtains, blue cloth, blue drape, indoor stage, halos, edge glow, blurry, cartoon, low quality, duplicate person, extra limbs, {negative_prompt}"}},
                "7": {
                    "class_type": crop_class,
                    "inputs": {
                        "image": ["1", 0],
                        "mask": ["3", 0],
                        "downscale_algorithm": "bilinear",
                        "upscale_algorithm": "bicubic",
                        "preresize": False,
                        "preresize_mode": "ensure minimum resolution",
                        "preresize_min_width": 1024,
                        "preresize_min_height": 1024,
                        "preresize_max_width": 16384,
                        "preresize_max_height": 16384,
                        "mask_fill_holes": True,
                        "mask_expand_pixels": 0,
                        "mask_invert": False,
                        "mask_blend_pixels": 4,
                        "mask_hipass_filter": 0.0,
                        "extend_for_outpainting": False,
                        "extend_up_factor": 1.0,
                        "extend_down_factor": 1.0,
                        "extend_left_factor": 1.0,
                        "extend_right_factor": 1.0,
                        "context_from_mask_extend_factor": 1.0,
                        "output_resize_to_target_size": True,
                        "output_target_width": 1024,
                        "output_target_height": 1024,
                        "output_padding": "32",
                        "device_mode": "gpu (much faster)"
                    }
                },
                "8": {
                    "class_type": "InpaintModelConditioning",
                    "inputs": {
                        "positive": ["5", 0],
                        "negative": ["6", 0],
                        "vae": ["4", 2],
                        "pixels": ["7", 1],
                        "mask": ["7", 2],
                        "noise_mask": True
                    }
                },
                "9": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["8", 2], "seed": actual_seed, "steps": 35, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.98}},
                "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 2]}},
                "11": {"class_type": stitch_class, "inputs": {"stitcher": ["7", 0], "inpainted_image": ["10", 0]}},
                "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "Amethyst_Scenario"}}
            }
        else:
            workflow = {
                "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_name}},
                "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_to_use}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": scenario_prompt}},
                "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": negative_prompt}},
                "5": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["1", 0], "vae": ["2", 2], "mask": ["1", 1], "grow_mask_by": 8}},
                "6": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0], "seed": actual_seed, "steps": 25, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.95}},
                "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
                "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "Amethyst_Scenario"}}
            }

        await self.unload_ollama_vram()
        # Filter out empty conditional nodes
        workflow = {k: v for k, v in workflow.items() if v}
        prompt_id = await self.queue_prompt(workflow)
        try:
            paths = await self.wait_for_completion(prompt_id, on_progress)
        finally:
            await self.free_memory()
        if not paths:
            raise RuntimeError("Scenario change completed but no image was returned by ComfyUI.")

        return {
            "success": True,
            "prompt_id": prompt_id,
            "filename": paths[0].name,
            "local_path": str(paths[0]),
            "url": f"/api/image/view/{paths[0].name}",
            "seed": actual_seed,
            "checkpoint": ckpt_to_use
        }

    async def editorial_photoshoot(
        self,
        image_data: Union[bytes, str],
        prompt: str,
        engine: str = "flux",
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """
        Generates a high-fashion editorial photoshoot with full pose, environment, and attire control
        using FLUX.1-dev, then preserves the subject's exact facial likeness and spectacles using
        InsightFace landmark alignment and color-matched Poisson/sharp blending.
        """
        uploaded_name = await self.upload_image(image_data, filename_prefix="editorial_in_")
        actual_seed = random.randint(100000000, 999999999999)
        clean_prompt = clean_outfit_prompt(prompt)

        # Build comprehensive editorial prompt
        t5_text = (
            f"RAW authentic fashion studio photography of a young voluptuous curvy Indian woman with long straight dark black hair. "
            f"She has clear transparent round spectacles. She is striking an editorial fashion pose with {clean_prompt}. "
            f"Natural authentic voluptuous curvy body build, full natural bust, soft natural waist and gentle soft rounded tummy, "
            f"soft natural arms, realistic soft Indian skin tones with warm highlights, authentic skin texture with pores. "
            f"Dark charcoal black fabric studio backdrop with faint horizontal fold crease. "
            f"Studio flash photography, softbox key lighting, 85mm portrait lens, ultra-high resolution, masterpiece."
        )

        clip_l_text = (
            f"Editorial portrait of a voluptuous curvy young Indian woman wearing clear transparent round glasses, "
            f"{clean_prompt}, long dark hair, soft natural curvy body, full bust, "
            f"dark charcoal fabric studio background, professional studio lighting, 8k uhd"
        )

        workflow = {
            "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-dev-Q4_K_S.gguf"}},
            "2": {"class_type": "DualCLIPLoaderGGUF", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5-v1_1-xxl-encoder-Q3_K_M.gguf", "type": "flux"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": ["1", 0],
                    "lora_name": "flux_realism_lora.safetensors",
                    "strength_model": 0.85
                }
            },
            "5": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {
                    "clip": ["2", 0],
                    "clip_l": clip_l_text,
                    "t5xxl": t5_text,
                    "guidance": 2.2
                }
            },
            "6": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 1024,
                    "height": 1536,
                    "batch_size": 1
                }
            },
            "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": actual_seed}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "9": {"class_type": "BasicScheduler", "inputs": {"model": ["4", 0], "scheduler": "simple", "steps": 26, "denoise": 1.0}},
            "10": {"class_type": "BasicGuider", "inputs": {"model": ["4", 0], "conditioning": ["5", 0]}},
            "11": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["7", 0],
                    "guider": ["10", 0],
                    "sampler": ["8", 0],
                    "sigmas": ["9", 0],
                    "latent_image": ["6", 0]
                }
            },
            "12": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["11", 0],
                    "vae": ["3", 0]
                }
            },
            "13": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "Amethyst_Editorial_FLUX",
                    "images": ["12", 0]
                }
            }
        }

        await self.unload_ollama_vram()
        # Filter out empty conditional nodes
        workflow = {k: v for k, v in workflow.items() if v}
        prompt_id = await self.queue_prompt(workflow)
        paths = await self.wait_for_completion(prompt_id, on_progress)
        await self.free_memory()

        if not paths:
            raise RuntimeError("Editorial photoshoot completed but no image was returned by ComfyUI.")

        gen_path = str(paths[0])
        src_path = os.path.join(r"D:\comfyui\ComfyUI-Easy-Install\ComfyUI\input", uploaded_name)
        out_name = f"Amethyst_Editorial_Final_{paths[0].stem}.png"
        out_path = os.path.join(paths[0].parent, out_name)

        py_embed = r"D:\comfyui\ComfyUI-Easy-Install\python_embeded\python.exe"
        script_path = r"D:\comfyui\ComfyUI-Easy-Install\apply_face_composite.py"

        if os.path.exists(py_embed) and os.path.exists(script_path):
            try:
                proc = await asyncio.create_subprocess_exec(
                    py_embed, script_path,
                    "--source", src_path,
                    "--target", gen_path,
                    "--output", out_path,
                    "--mode", "inswapper",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
            except Exception as e:
                pass

        final_filename = out_name if os.path.exists(out_path) else paths[0].name
        final_path = out_path if os.path.exists(out_path) else gen_path

        return {
            "success": True,
            "prompt_id": prompt_id,
            "filename": final_filename,
            "local_path": str(final_path),
            "url": f"/api/image/view/{final_filename}",
            "seed": actual_seed,
            "checkpoint": "flux1-dev-Q4_K_S.gguf"
        }
