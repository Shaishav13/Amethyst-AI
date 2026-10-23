"""
Amethyst API Server — FastAPI Backend
======================================
Exposes all Amethyst engines over HTTP so the Angular frontend can consume them.

Endpoints:
  GET  /api/status          — Ollama connection + model availability
  GET  /api/models          — List of installed Ollama models
  POST /api/chat/stream     — SSE streaming chat response
  GET  /api/sessions        — List all saved sessions
  GET  /api/sessions/{id}   — Get a single session
  DELETE /api/sessions/{id} — Delete a session
  POST /api/sessions/clear  — Wipe all sessions
  GET  /api/memory/profile  — User profile facts/prefs/projects
  POST /api/rag/ingest      — Ingest a document into ChromaDB
  GET  /api/rag/stats       — Vector DB stats
  POST /api/rag/clear       — Clear vector DB
  POST /api/code/save       — Save a script to disk
  POST /api/code/execute    — Execute a script (user-triggered only)
  GET  /api/system          — Current system snapshot (CPU/RAM/disk)
  POST /api/vision/analyze  — Capture + analyze screenshot

Run with:
  python api_server.py
  (default: http://localhost:8000)
"""

import asyncio
import re
import json
import logging
import uuid
from pathlib import Path
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from ai_engine import AmethystEngine, ModelType
from memory_manager import MemoryManager, StoredSession, StoredMessage
from rag_engine import RAGEngine
from okf_engine import OKFEngine
from code_executor import CodeExecutor, SCRIPTS_DIR
from system_monitor import SystemMonitor
from vision_engine import VisionEngine
from comfy_bridge import ComfyBridge
from image_task_router import ImageTaskRouter, TaskIntent, EditType, ImageTaskPlan

import time
import os
import tempfile

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("amethyst.api")

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Amethyst API", version="2.0.0")

# Allow Angular dev server (localhost:4200) and any local origin
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Engine Singletons ─────────────────────────────────────────────────────────
memory  = MemoryManager()
engine  = AmethystEngine(memory_manager=memory)
rag     = RAGEngine()
okf     = OKFEngine()
executor = CodeExecutor()
sysmon  = SystemMonitor(interval=30.0)
vision  = VisionEngine()
comfy   = ComfyBridge()
image_router = ImageTaskRouter()

# Global GPU Concurrency Lock: Prevents Ollama chat/coding and ComfyUI image generation
# from colliding in VRAM simultaneously on 8GB GPU.
gpu_system_lock = asyncio.Lock()

TRIGGER_PATTERN = re.compile(
    r'^\s*(?:gen(?:e)?rate[\s_-]*image|edit[\s_-]*image|swap[\s_-]*outfit|change[\s_-]*(?:outfit|clothes|scenario|background)|/(?:image|edit))\s*[:=-]?\s*(.*)',
    re.IGNORECASE | re.DOTALL
)

# Web search engine — single instance, reused across requests (has rate limiting)
try:
    from search_engine import WebSearchEngine
    _search_engine = WebSearchEngine()
except ImportError:
    _search_engine = None
    log.warning("WebSearchEngine not available — search feature disabled.")

sysmon.start()

# ── Request / Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    force_model: Optional[str] = None   # "coder" | "chat"
    options: Optional[dict] = None      # override temperature, top_p, etc.
    image_b64: Optional[str] = None

class SaveScriptRequest(BaseModel):
    code: str
    language: str = "python"
    filename: Optional[str] = None

class ExecuteScriptRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 30

class IngestRequest(BaseModel):
    filepath: str   # absolute path on the server machine


class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 28
    cfg: float = 6.0
    checkpoint: Optional[str] = None
    seed: Optional[int] = None

class ImageEditRequest(BaseModel):
    prompt: str
    image_b64: str
    negative_prompt: Optional[str] = None
    edit_type: str = "outfit"  # "outfit" or "scenario"
    checkpoint: Optional[str] = None

class VisionRequest(BaseModel):
    prompt: str = ""
    image_b64: Optional[str] = None


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    log.info("Amethyst API starting up...")
    status = await engine.check_models()
    log.info(f"Model status: {status}")
    # Detect vision model
    await vision.detect_vision_model(engine.available_models)


# ── Status & Models ───────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Check Ollama connection and which models are available."""
    try:
        status = await engine.check_models()
        return {
            "online": any(status.values()),
            "models": status,
            "coder_model": engine.resolved_coder,
            "chat_model":  engine.resolved_chat,
            "vision_model": vision.model_name,
            "comfy_online": await comfy.is_online(),
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"online": False, "error": str(e)})


@app.get("/api/models")
async def list_models():
    """Return all models installed in Ollama."""
    try:
        import ollama
        client = ollama.AsyncClient()
        response = await client.list()
        models = [{"name": m.model, "size": getattr(m, "size", 0)} for m in response.models]
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Chat Streaming ────────────────────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE endpoint — streams tokens as they arrive from Ollama.
    Client reads Server-Sent Events: data: <token>\n\n
    Final event:  data: [DONE]\n\n
    """
    # Resolve force_model string → ModelType
    force = None
    if req.force_model == "coder":
        force = ModelType.CODER
    elif req.force_model == "chat":
        force = ModelType.CHAT

    # Load or create session
    session_id = req.session_id or str(uuid.uuid4())
    stored: Optional[StoredSession] = None
    if req.session_id:
        stored = memory._store.load(req.session_id)

    if stored is None:
        # Use first 4 words for a cleaner title instead of an arbitrary 40-char slice
        words = req.message.split()
        short_title = " ".join(words[:4]) + ("..." if len(words) > 4 else "")
        
        stored = StoredSession(
            id=session_id,
            title=short_title,
            created=time.time(),
            updated=time.time(),
        )

    # Only clear and reload history if we are switching to a new session.
    # If we stay in the same session, keep the engine history so RAG context isn't lost.
    if getattr(engine, "current_session_id", None) != session_id:
        engine.clear_history()
        engine.current_session_id = session_id
        if stored and stored.messages:
            from ai_engine import Message
            for m in stored.messages:
                engine.history.add(Message(role=m.role, content=m.content))

    async def event_generator() -> AsyncGenerator[str, None]:
        decision_info = {}
        full_text = ""

        # ── Pure Natural Language Image Task Planning & Execution ──────────
        # Resolves active reference image from request or past session messages
        active_image = req.image_b64
        if not active_image and stored and stored.messages:
            for m in reversed(stored.messages):
                if getattr(m, 'image_b64', None):
                    active_image = m.image_b64
                    break

        has_reference_image = bool(active_image)
        plan: ImageTaskPlan = image_router.plan_task(
            prompt=req.message,
            has_reference_image=has_reference_image,
            force_model=req.force_model
        )

        # 1. Informational queries or general coding/chat questions route straight to Ollama ModelRouter
        if plan.intent == TaskIntent.CONVERSATION:
            pass  # Fall through to on_model_selected / engine.generate_stream below

        # 2. Ambiguous requests (e.g. descriptive scene caption with attached image) ask user for intent
        elif plan.intent == TaskIntent.DISAMBIGUATION:
            meta = json.dumps({"type": "meta", "session_id": session_id, "model": "Amethyst Router"})
            yield "data: " + meta + "\n\n"
            yield "data: " + json.dumps({"type": "token", "text": f"🤔 {plan.clarification_message}\n\n"}) + "\n\n"
            yield "data: [DONE]\n\n"
            return

        # 3. Executable Image Tasks (TXT2IMG or multi-stage IMAGE_EDIT)
        elif plan.intent in (TaskIntent.TXT2IMG, TaskIntent.IMAGE_EDIT):
            if plan.intent == TaskIntent.IMAGE_EDIT and not has_reference_image:
                meta = json.dumps({"type": "meta", "session_id": session_id, "model": "Amethyst Router"})
                yield "data: " + meta + "\n\n"
                yield "data: " + json.dumps({"type": "token", "text": f"⚠️ {plan.clarification_message}\n\n"}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            meta = json.dumps({"type": "meta", "session_id": session_id, "model": "ComfyUI"})
            yield "data: " + meta + "\n\n"

            if not await comfy.is_online():
                err_msg = (
                    "⚠️ **ComfyUI is currently offline.**\n\n"
                    "Image generation was triggered, but the ComfyUI engine is not running on port 8188.\n\n"
                    "**To start generation:**\n"
                    "1. Double-click `Start ComfyUI.bat` in `D:\\comfyui\\ComfyUI-Easy-Install\\`.\n"
                    f"2. Re-send your command: `{req.message}`\n"
                )
                yield "data: " + json.dumps({"type": "token", "text": err_msg}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            if gpu_system_lock.locked():
                yield "data: " + json.dumps({"type": "token", "text": "⏳ *System GPU is currently processing chat/code inference. Waiting for GPU to become free...*\n\n"}) + "\n\n"

            async with gpu_system_lock:
                yield "data: " + json.dumps({"type": "token", "text": "🎨 *GPU allocated to ComfyUI. Queuing image execution plan...*\n\n"}) + "\n\n"

                try:
                    engine_choice = (req.options or {}).get("image_engine", "sdxl")
                    intermediate_results = []
                    current_image = active_image

                    if plan.intent == TaskIntent.TXT2IMG:
                        stage = plan.stages[0] if plan.stages else None
                        prompt_text = stage.prompt_payload if stage else req.message
                        yield "data: " + json.dumps({"type": "token", "text": f"🎨 *Rendering from scratch: \"{prompt_text}\"...*\n\n"}) + "\n\n"
                        result = await comfy.generate_txt2img(prompt=prompt_text)
                        intermediate_results.append((None, result))
                    else:
                        # Multi-stage image editing
                        for idx, stage in enumerate(plan.stages):
                            stage_num = idx + 1
                            total_stages = len(plan.stages)
                            prefix = f"Stage {stage_num}/{total_stages}" if total_stages > 1 else "Edit"

                            if not stage.supported:
                                yield "data: " + json.dumps({"type": "token", "text": f"⚠️ *Skipping {prefix} ({stage.edit_type.value.capitalize()}): {stage.unavailable_reason}*\n\n"}) + "\n\n"
                                continue

                            if stage.edit_type == EditType.ATTIRE:
                                yield "data: " + json.dumps({"type": "token", "text": f"👔 *[{stage.preferred_engine.upper()} Inpaint] {prefix} (Attire): \"{stage.prompt_payload}\"...*\n\n"}) + "\n\n"
                                res = await comfy.swap_outfit(
                                    current_image,
                                    stage.prompt_payload,
                                    categories=stage.categories,
                                    engine=stage.preferred_engine or engine_choice
                                )
                                intermediate_results.append((stage, res))
                                current_image = res["local_path"]

                            elif stage.edit_type == EditType.BACKGROUND:
                                yield "data: " + json.dumps({"type": "token", "text": f"🌄 *[{stage.preferred_engine.upper()}/RMBG] {prefix} (Background): \"{stage.prompt_payload}\"...*\n\n"}) + "\n\n"
                                res = await comfy.change_scenario(
                                    current_image,
                                    stage.prompt_payload
                                )
                                intermediate_results.append((stage, res))
                                current_image = res["local_path"]

                    if not intermediate_results:
                        yield "data: " + json.dumps({"type": "token", "text": "⚠️ *No executable stages could be completed with currently installed workflows.*\n\n"}) + "\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    final_stage, final_result = intermediate_results[-1]
                    srv_port = os.environ.get("AMETHYST_PORT", "8001")
                    img_url = f"http://localhost:{srv_port}{final_result['url']}"
                    stage_summary = f" • Multi-stage: {len(intermediate_results)} completed" if len(intermediate_results) > 1 else ""
                    img_md = f"\n\n![Generated Image]({img_url})\n\n*(Rendered with {final_result['checkpoint']} • Seed: {final_result['seed']}{stage_summary})*"
                    yield "data: " + json.dumps({"type": "token", "text": img_md}) + "\n\n"

                    # Persist to session
                    stored.messages.append(StoredMessage(
                        role="user",
                        content=req.message,
                        image_b64=req.image_b64 or "",
                        model="",
                        timestamp=time.time(),
                    ))
                    stored.messages.append(StoredMessage(
                        role="assistant",
                        content=f"🎨 *Generated Image*\n{img_md}",
                        image_b64="",
                        model="ComfyUI",
                        timestamp=time.time(),
                    ))
                    stored.updated = time.time()
                    memory._store.save(stored)

                    yield "data: [DONE]\n\n"
                    return

                except Exception as comfy_err:
                    log.error(f"ComfyUI execution failed: {comfy_err}", exc_info=True)
                    if intermediate_results:
                        _, last_good = intermediate_results[-1]
                        srv_port = os.environ.get("AMETHYST_PORT", "8001")
                        salvaged_url = f"http://localhost:{srv_port}{last_good['url']}"
                        err_text = (
                            f"\n\n⚠️ **Notice:** A subsequent stage encountered an error: {str(comfy_err)}\n"
                            f"**Preserving intermediate output from earlier successful stage:**\n\n"
                            f"![Intermediate Image]({salvaged_url})\n\n"
                        )
                    else:
                        err_text = f"\n\n❌ **Generation error:** {str(comfy_err)}"
                    yield "data: " + json.dumps({"type": "token", "text": err_text}) + "\n\n"
                    yield "data: [DONE]\n\n"
                    return

        def on_model_selected(decision):
            if req.image_b64 and vision.has_vision:
                decision_info["model"] = vision.model_name
                decision_info["reason"] = "Multimodal request"
            else:
                resolved = engine.resolved_coder if decision.model == ModelType.CODER else engine.resolved_chat
                decision_info["model"] = resolved
                decision_info["reason"] = decision.reason

        try:
            # Check for Google OKF Knowledge Graph context
            okf_context = okf.query(req.message)
            final_prompt = req.message
            if okf_context:
                final_prompt = f"--- GOOGLE OKF KNOWLEDGE GRAPH ---\n{okf_context}\n--- END KNOWLEDGE ---\n\n{final_prompt}"
                log.info(f"Injected {len(okf_context)} chars of OKF graph context.")

            # Check for RAG context
            rag.initialize()
            rag_context = rag.query(req.message)
            
            if rag_context:
                final_prompt = f"--- ATTACHED DOCUMENT CONTEXT ---\n{rag_context}\n--- END DOCUMENT ---\n\n{final_prompt}"
                log.info(f"Injected {len(rag_context)} chars of RAG context.")

            # Route ONCE — this decision is reused for both search check and model selection
            route_decision = engine.router.route(req.message)

            # Check for Web Search Intent
            if _search_engine and getattr(route_decision, "requires_search", False):
                if _search_engine.is_connected():
                    log.info("Internet connection found, executing live search...")
                    search_results = await asyncio.to_thread(_search_engine.search, req.message)
                    final_prompt = f"--- LIVE WEB SEARCH RESULTS ---\n{search_results}\n--- END SEARCH ---\n\n{final_prompt}"
                    log.info("Injected live web search results.")
                else:
                    log.warning("Offline: skipped live web search.")

            # Start streaming under GPU lock so image generation cannot collide
            async with gpu_system_lock:
                async for token in engine.stream_response(
                    user_prompt=final_prompt,
                    force_model=force,
                    vision_model_override=vision.model_name if req.image_b64 and vision.has_vision else None,
                    image_b64=req.image_b64 if vision.has_vision else None,
                    on_model_selected=on_model_selected,
                    custom_options=req.options,
                    pre_routed=route_decision if not force else None,
                ):
                    # Send meta event once, after routing has decided the model
                    if not decision_info.get("_meta_sent"):
                        routed_model = decision_info.get("model", engine.resolved_coder)
                        meta = json.dumps({"type": "meta", "session_id": session_id,
                                           "model": routed_model})
                        yield f"data: {meta}\n\n"
                        decision_info["_meta_sent"] = True
                    full_text += token
                    yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
            stored.messages.append(StoredMessage(
                role="user", 
                content=req.message,
                image_b64=req.image_b64 or ""
            ))
            stored.messages.append(StoredMessage(
                role="assistant", content=full_text,
                model=decision_info.get("model", "")
            ))
            stored.updated = time.time()
            memory.save_session(stored)

            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

            # Background summarization (fire and forget)
            asyncio.create_task(memory.process_session_memory(stored))

        except Exception as e:
            log.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions():
    sessions = memory.load_all_sessions()
    return {
        "sessions": [
            {
                "id":            s.id,
                "title":         s.title,
                "created":       s.created,
                "updated":       s.updated,
                "message_count": s.message_count,
                "summarized":    s.summarized,
                "is_resumable":  s.is_resumable,
            }
            for s in sessions
        ]
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    s = memory._store.load(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id":       s.id,
        "title":    s.title,
        "created":  s.created,
        "updated":  s.updated,
        "summary":  s.summary,
        "messages": [
            {"role": m.role, "content": m.content,
             "model": m.model, "timestamp": m.timestamp}
            for m in s.messages
        ],
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    memory.delete_session(session_id)
    return {"ok": True}


@app.post("/api/sessions/clear")
async def clear_sessions():
    memory.clear_all_memory()
    engine.clear_history()
    return {"ok": True}


# ── Memory / Profile ──────────────────────────────────────────────────────────

@app.get("/api/memory/profile")
async def get_profile():
    p = memory.profile
    return {
        "facts":       p.facts,
        "preferences": p.preferences,
        "projects":    p.projects,
        "updated":     p.updated,
    }


# ── RAG ───────────────────────────────────────────────────────────────────────

@app.post("/api/rag/ingest")
async def rag_ingest(req: IngestRequest):
    if not os.path.exists(req.filepath):
        raise HTTPException(status_code=404, detail="File not found on server")
    rag.initialize()
    chunks = rag.ingest_document(req.filepath)
    return {"ok": True, "chunks_added": chunks}


from fastapi import Form

@app.post("/api/rag/ingest/upload")
async def rag_ingest_upload(file: UploadFile = File(...), session_id: str = Form(None)):
    """Upload a file directly from the browser and ingest it."""
    # Use a UUID-based temp path to prevent race conditions when two uploads
    # happen concurrently with the same filename
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    tmp_path = os.path.join(tempfile.gettempdir(), safe_name)
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)
    rag.initialize()
    total_chunks = len(rag_engine_chunks := [])  # placeholder for result
    try:
        chunks = await asyncio.to_thread(rag.ingest_document, tmp_path)
    finally:
        # Always clean up, even if ingestion fails
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    
    if session_id:
        stored = memory._store.load(session_id)
        if stored:
            stored.messages.append(StoredMessage(role="user", content=f"📎 [User attached document: {file.filename}]"))
            stored.updated = time.time()
            memory.save_session(stored)

    return {"ok": True, "chunks_added": chunks, "filename": file.filename}


@app.get("/api/rag/stats")
async def rag_stats():
    rag.initialize()
    return rag.get_stats()


@app.post("/api/rag/clear")
async def rag_clear():
    rag.initialize()
    rag.clear_database()
    return {"ok": True}


# ── Code Executor ─────────────────────────────────────────────────────────────

@app.post("/api/code/save")
async def save_script(req: SaveScriptRequest):
    raise HTTPException(status_code=403, detail="Code saving is disabled in portable mode for security.")


@app.post("/api/code/execute")
async def execute_script(req: ExecuteScriptRequest):
    """Execute code — DISABLED for security."""
    return {
        "success": False,
        "stdout": "",
        "stderr": "Security Error: Script execution is disabled in portable mode to protect the host PC.",
        "return_code": -1,
        "duration": 0,
        "language": req.language,
    }


@app.get("/api/code/scripts")
async def list_scripts():
    scripts = executor.list_saved_scripts()
    return {
        "scripts": [
            {"name": p.name, "path": str(p),
             "size": p.stat().st_size,
             "modified": p.stat().st_mtime}
            for p in scripts
        ]
    }


# ── System Monitor ────────────────────────────────────────────────────────────

@app.get("/api/system")
async def get_system():
    snap = sysmon.get_snapshot()
    if snap is None:
        return {"available": False}
    return {
        "available":      True,
        "cpu_percent":    snap.cpu_percent,
        "ram_percent":    snap.ram_percent,
        "ram_used_gb":    snap.ram_used_gb,
        "ram_total_gb":   snap.ram_total_gb,
        "disk_percent":   snap.disk_percent,
        "disk_free_gb":   snap.disk_free_gb,
        "battery_percent": snap.battery_percent,
        "battery_plugged": snap.battery_plugged,
        "os_name":        snap.os_name,
        "hostname":       snap.hostname,
    }


# ── Vision ────────────────────────────────────────────────────────────────────

@app.post("/api/vision/analyze")
async def analyze_vision(req: VisionRequest):
    """Analyze a provided image or capture a screenshot. Returns full text response."""
    if not vision.has_vision:
        raise HTTPException(status_code=503,
                            detail="No vision model available. Pull llava: ollama pull llava")

    tokens = []

    async def collect(token: str):
        tokens.append(token)

    result = await vision.analyze_screenshot(
        user_prompt=req.prompt,
        on_token=collect,
        image_b64=req.image_b64
    )
    return {"response": result}


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("AMETHYST_PORT", 8001))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False, log_level="info")


# ── Image Generation & Editing (ComfyUI) ────────────────────────────────────

@app.get("/api/image/status")
async def get_image_status():
    """Check ComfyUI server status, devices, and available checkpoints."""
    return await comfy.get_system_status()


@app.get("/api/image/checkpoints")
async def get_image_checkpoints():
    """List all installed checkpoint models in ComfyUI."""
    ckpts = await comfy.get_available_checkpoints()
    return {"checkpoints": ckpts}


@app.post("/api/image/generate")
async def generate_image(req: ImageGenerateRequest):
    """Generate a new image from a text prompt using SDXL."""
    try:
        async with gpu_system_lock:
            result = await comfy.generate_txt2img(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt or "ugly, blurry, distorted, cartoon, low quality",
                width=req.width,
                height=req.height,
                steps=req.steps,
                cfg=req.cfg,
                checkpoint=req.checkpoint,
                seed=req.seed
            )
            return result
    except Exception as e:
        log.error(f"Image generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/edit/outfit")
async def edit_outfit_upload(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    checkpoint: Optional[str] = Form(None),
):
    """
    Swap outfit on uploaded photo using identity-preserving Crop & Stitch.
    Face and body are 100% unaltered.
    """
    try:
        image_bytes = await file.read()
        async with gpu_system_lock:
            result = await comfy.swap_outfit(
                image_data=image_bytes,
                outfit_prompt=prompt,
                negative_prompt=negative_prompt or "cartoon, anime, 3d render, plastic skin, distorted anatomy, blurry",
                checkpoint=checkpoint
            )
            return result
    except Exception as e:
        log.error(f"Outfit swap failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/edit/scenario")
async def edit_scenario_upload(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    checkpoint: Optional[str] = Form(None),
):
    """
    Change the background/scenario around the subject while locking identity.
    """
    try:
        image_bytes = await file.read()
        async with gpu_system_lock:
            result = await comfy.change_scenario(
                image_data=image_bytes,
                scenario_prompt=prompt,
                negative_prompt=negative_prompt or "blurry, low quality, artifacts, cartoon, bad anatomy, warped",
                checkpoint=checkpoint
            )
            return result
    except Exception as e:
        log.error(f"Scenario edit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/edit")
async def edit_image_json(req: ImageEditRequest):
    """Edit an image via JSON with base64 image data and intelligent routing."""
    try:
        async with gpu_system_lock:
            if req.edit_type == "scenario":
                return await comfy.change_scenario(
                    image_data=req.image_b64,
                    scenario_prompt=req.prompt,
                    negative_prompt=req.negative_prompt or "",
                    checkpoint=req.checkpoint
                )
            elif req.edit_type == "outfit":
                return await comfy.swap_outfit(
                    image_data=req.image_b64,
                    outfit_prompt=req.prompt,
                    negative_prompt=req.negative_prompt or "",
                    checkpoint=req.checkpoint
                )
            else:
                plan = image_router.plan_task(req.prompt, has_reference_image=True)
                if plan.intent == TaskIntent.IMAGE_EDIT and plan.stages:
                    stage = plan.stages[0]
                    if stage.edit_type == EditType.BACKGROUND:
                        return await comfy.change_scenario(
                            image_data=req.image_b64,
                            scenario_prompt=stage.prompt_payload,
                            negative_prompt=req.negative_prompt or "",
                            checkpoint=req.checkpoint
                        )
                    elif stage.edit_type == EditType.ATTIRE:
                        return await comfy.swap_outfit(
                            image_data=req.image_b64,
                            outfit_prompt=stage.prompt_payload,
                            negative_prompt=req.negative_prompt or "",
                            categories=stage.categories,
                            checkpoint=req.checkpoint
                        )
                    elif stage.edit_type == EditType.POSE and not stage.supported:
                        raise HTTPException(status_code=400, detail=stage.unavailable_reason)
                return await comfy.swap_outfit(
                    image_data=req.image_b64,
                    outfit_prompt=req.prompt,
                    negative_prompt=req.negative_prompt or "",
                    checkpoint=req.checkpoint
                )
    except Exception as e:
        log.error(f"Image edit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/image/view/{filename}")
async def view_generated_image(filename: str):
    """Serve generated or edited images from local Amethyst storage."""
    from comfy_bridge import OUTPUT_DIR
    target = OUTPUT_DIR / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = "image/png"
    if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filename.lower().endswith(".webp"):
        media_type = "image/webp"
    return FileResponse(target, media_type=media_type)

# ── Google Open Knowledge Format (OKF) Endpoints ────────────────────────────

@app.get("/api/knowledge/topics")
async def get_knowledge_topics():
    """Return all indexed OKF knowledge topics and graph connections."""
    return {"topics": okf.get_topics_list(), "count": len(okf.nodes)}


@app.get("/api/knowledge/topic/{topic_id}")
async def get_knowledge_topic(topic_id: str):
    """Get full details and connected neighbors for an OKF node."""
    if topic_id not in okf.nodes:
        raise HTTPException(status_code=404, detail="Topic not found in OKF graph")
    node = okf.nodes[topic_id]
    neighbors = [okf.nodes[nid].to_dict() for nid in okf.graph.get(topic_id, set()) if nid in okf.nodes]
    result = node.to_dict()
    result["content"] = node.content
    result["connected_nodes"] = neighbors
    return result


@app.post("/api/knowledge/compile")
async def compile_knowledge():
    """Compile Amethyst long-term memory and sessions into OKF wiki."""
    count = okf.compile_profile_and_sessions(memory)
    return {"success": True, "compiled_count": count, "total_nodes": len(okf.nodes)}


@app.post("/api/knowledge/upload")
async def upload_knowledge_file(file: UploadFile = File(...)):
    """Upload an OKF markdown document or zip bundle to the knowledge base."""
    target_dir = okf.knowledge_dir / "imported"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    filename = file.filename or "uploaded.md"
    data = await file.read()
    
    if filename.lower().endswith(".zip"):
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(target_dir)
    else:
        (target_dir / filename).write_bytes(data)
        
    okf.load_all_bundles()
    return {"success": True, "filename": filename, "total_nodes": len(okf.nodes)}
