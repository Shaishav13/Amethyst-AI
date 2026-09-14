# ✦ Amethyst — Local AI Assistant

A fully offline, privacy-first AI assistant powered by **Ollama**. Dual-model intelligence, persistent memory, voice I/O, vision, RAG, code execution, and a sleek dark UI — all running on your machine.

---

## Models Used

| Model | Purpose |
|-------|---------|
| `gemma3:4b` | General chat, explanations, summaries, vision |
| `qwen2.5-coder:7b` | Code writing, debugging, refactoring |
| `nomic-embed-text` | Semantic embeddings for RAG (optional) |
| `llava` / `llama3.2-vision` | Vision fallback (optional) |

---

## Quick Start

### 1. Install Ollama
Download from: https://ollama.com/download

### 2. Start Ollama & Pull Models
```bash
ollama serve
ollama pull gemma3:4b
ollama pull qwen2.5-coder:7b

# Optional — for RAG document search
ollama pull nomic-embed-text
```

### 3. Install Python Dependencies
```bash
python setup.py
```

### 4. Launch Amethyst
```bash
python ui_main.py
```

---

## Features

### Core
- **🤖 Dual-Model Routing** — Automatically routes prompts to the right model based on keywords and heuristics. Code/debug queries → `qwen2.5-coder:7b`. Everything else → `gemma3:4b`.
- **💬 Streaming Responses** — Tokens stream live to the UI. No waiting for a full response.
- **📋 Code Blocks** — Syntax-highlighted code blocks with a one-click Copy button.
- **⚙️ AI Parameter Control** — Adjust Temperature, Top P, Max Tokens, and Repeat Penalty from the settings dialog.

### Memory
- **🧠 Persistent Memory** — Sessions are saved to disk and survive restarts.
- **📝 Session Summaries** — Gemma automatically summarizes past conversations into bullet-point memories.
- **👤 User Profile** — Facts, preferences, and projects are extracted from conversations and injected into future sessions so Amethyst remembers you.
- **🔄 Session Resume** — If the app closes mid-response, the session is marked resumable and can be continued from where it left off.

### Voice
- **🎤 Voice Input (STT)** — Press the mic button and speak. Uses SpeechRecognition with Google Web Speech fallback.
- **🔊 Voice Output (TTS)** — Responses are read aloud via `edge-tts` (Microsoft Neural voices). Toggle the speaker button to mute.

### Documents & RAG
- **📂 Document Attachment** — Attach PDFs, `.txt`, `.md`, `.py`, `.json`, `.csv`, and more directly in chat.
- **🔍 RAG Engine** — Ingest documents into a persistent ChromaDB vector database (powered by LangChain + `nomic-embed-text`). Relevant chunks are retrieved and injected into the AI context automatically.

### Vision
- **👁️ Screenshot Analysis** — Amethyst can capture your screen and analyze it using a vision-capable model (`gemma3:4b`, `llava`, or `llama3.2-vision`). Useful for explaining UI errors or describing what's on screen.

### Code Execution
- **⚡ Sandboxed Python Runner** — The AI can write and execute Python code in an isolated subprocess with a 15-second timeout and output capture. Results are shown inline.

### System Awareness
- **📊 System Monitor** — Background thread monitors CPU, RAM, disk, and battery. Triggers alerts in chat when thresholds are critical (CPU >95%, RAM >92%, disk >95%, battery <10%).

### IDE Integration
- **🔗 IDE Bridge** — Press `Ctrl+Shift+A` in any editor to capture selected code and send it directly to Amethyst, automatically routed to the coder model.

---

## Troubleshooting

### "Connection error: All connection attempts failed"
Ollama is not running. Start it:
```bash
ollama serve
```

### "Model error: model 'qwen2.5-coder:7b' not found"
The model isn't pulled yet:
```bash
ollama pull qwen2.5-coder:7b
ollama pull gemma3:4b
```

Verify with:
```bash
ollama list
```

---

## Project Structure

```
AI_Assistant/
├── ai_engine.py        # Dual-model router + async Ollama client + streaming
├── memory_manager.py   # Persistent sessions, summarization, user profile
├── rag_engine.py       # ChromaDB vector store + LangChain document ingestion
├── vision_engine.py    # Screenshot capture + Ollama vision model analysis
├── code_executor.py    # Sandboxed Python subprocess runner
├── system_monitor.py   # CPU / RAM / disk / battery background monitor
├── document_reader.py  # PDF + text file reader for RAG ingestion
├── voice_engine.py     # STT (SpeechRecognition) + TTS (edge-tts)
├── ide_bridge.py       # Global hotkey + clipboard code capture
├── ui_main.py          # CustomTkinter dark UI (sidebar, chat, input bar)
├── setup.py            # Dependency installer + Ollama checker
├── requirements.txt    # All Python dependencies
└── README.md
```

---

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in input |
| `Ctrl+Shift+A` | Capture selected code from any editor (IDE Bridge) |

---

## Resource Optimizations

Tuned for 8GB VRAM / low-RAM systems:

- `num_ctx = 4096` for coder model, `2048` for chat model
- `num_predict = 1024` to cap output length and save memory
- Rolling 20-message conversation window (oldest messages drop off)
- Streaming prevents memory accumulation in the UI
- Models load on-demand — only one active at a time
- Screenshots are resized to max 1280px before being sent to the vision model
- Code executor runs in a separate subprocess with a 15s timeout

---

## Storage Layout

Amethyst stores all persistent data under `~/.amethyst/`:

```
~/.amethyst/
├── sessions/       ← Full session JSON files (chat history)
├── memories/       ← Per-session summaries + drafts
├── profile.json    ← Long-term user profile (facts, preferences, projects)
├── chroma_db/      ← ChromaDB vector database (RAG documents)
└── screenshots/    ← Temporary vision screenshots (last 5 kept)
```

---

## Requirements

- Python 3.10+
- Windows (IDE Bridge uses `pywin32`; voice uses Windows audio APIs)
- Ollama installed and running
- ~8GB VRAM recommended for running both models simultaneously
