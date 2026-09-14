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
import json
import logging
import uuid
from pathlib import Path
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from ai_engine import AmethystEngine, ModelType
from memory_manager import MemoryManager, StoredSession, StoredMessage
from rag_engine import RAGEngine
from code_executor import CodeExecutor, SCRIPTS_DIR
from system_monitor import SystemMonitor
from vision_engine import VisionEngine

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
executor = CodeExecutor()
sysmon  = SystemMonitor(interval=30.0)
vision  = VisionEngine()

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

        def on_model_selected(decision):
            if req.image_b64 and vision.has_vision:
                decision_info["model"] = vision.model_name
                decision_info["reason"] = "Multimodal request"
            else:
                resolved = engine.resolved_coder if decision.model == ModelType.CODER else engine.resolved_chat
                decision_info["model"] = resolved
                decision_info["reason"] = decision.reason

        try:
            # Check for RAG context
            rag.initialize()
            rag_context = rag.query(req.message)
            final_prompt = req.message
            
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

            # Start streaming — pass pre_routed so stream_response does NOT route again
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
                # Escape newlines for SSE
                safe = token.replace("\n", "\\n")
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            # Persist to session
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
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
