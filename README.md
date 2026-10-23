# Amethyst: Autonomous Local AI Assistant

Amethyst is a fully offline, privacy-first artificial intelligence assistant platform designed for high-performance local execution. Powered by **Ollama**, **FastAPI**, **Angular**, and **ComfyUI**, Amethyst combines intelligent dual-model routing, persistent memory profiling, vector retrieval (RAG), structured knowledge graphs (Google OKF), agentic live web search, local image generation and multi-stage inpainting, vision analysis, system telemetry, and voice I/O into a unified desktop and web environment running entirely on local consumer hardware.

---

## Architecture Overview

Amethyst utilizes a decoupled client-server architecture optimized for low-latency streaming and strict VRAM budget management on single-GPU systems.

```
+-----------------------------------------------------------------------------+
|                           User Interface Layer                              |
|  - Angular 19 SPA (localhost:4200): SSE streaming, responsive UI, LaTeX     |
|  - Legacy Desktop UI (CustomTkinter): Voice I/O, IDE Bridge (Ctrl+Shift+A)  |
+-----------------------------------------------------------------------------+
                                       |
                                HTTP / SSE
                                       v
+-----------------------------------------------------------------------------+
|                     FastAPI Backend (api_server.py:8001)                   |
|  - Global GPU concurrency lock (prevents Ollama & ComfyUI VRAM collisions)  |
|  - SSE streaming event pipeline                                             |
|  - Endpoints for Chat, Sessions, RAG, OKF, Image Tasks, System Telemetry     |
+-----------------------------------------------------------------------------+
         |                     |                      |                 |
         v                     v                      v                 v
+-----------------+   +------------------+   +----------------+   +------------+
|  AI Router &    |   | Retrieval &      |   | Image Router & |   | System &   |
|  Ollama Engine  |   | Knowledge Store  |   | ComfyUI Engine |   | Telemetry  |
| (ai_engine.py)  |   |                  |   |                |   |            |
|                 |   | - ChromaDB RAG   |   | - Natural Lang |   | - psutil   |
| - amethyst-coder|   | - Google OKF     |   |   Task Router  |   |   monitor  |
|   (Qwen 2.5)    |   |   Knowledge Graph|   | - SDXL/FLUX    |   | - DuckDuck |
| - amethyst-chat |   | - MemoryManager  |   |   txt2img      |   |   Go live  |
|   (Dolphin/Gemma|   |   (Profile/JSON) |   | - Inpaint/Swap |   |   search   |
+-----------------+   +------------------+   +----------------+   +------------+
```

---

## Core Capabilities

### 1. Dual-Model Dynamic Routing
- **Intelligent Classification**: Incoming prompts are classified in a single pass via heuristic and keyword pattern matching (`ModelRouter`).
- **Code Specialization**: Programming, shell scripting, debugging, and system administration queries automatically route to `amethyst-coder` (based on `qwen2.5-coder:7b`).
- **Conversational Intelligence**: General queries, natural conversations, and creative writing route to `amethyst-chat` (based on `dolphin-llama3` or `gemma3:4b`).
- **Manual Override**: Users can lock prompt execution to coder, chat, or image modes directly in the interface.

### 2. ComfyUI Image Generation and Inpainting Pipeline
- **Natural Language Image Router (`image_task_router.py`)**: Accepts plain-English commands (e.g., *"change her outfit to a black leather jacket and put her in a cyberpunk street"*) without requiring fixed command-line flags.
- **Text-to-Image Generation**: Directly orchestrates SDXL or FLUX checkpoints to generate high-resolution images from textual descriptions.
- **Identity-Preserving Outfits & Scenario Editing**: Multi-stage image editing pipeline utilizing crop-and-stitch masking to preserve facial features and anatomical integrity while altering garments or replacing background environments.
- **Fail-Safe Stage Execution**: In multi-stage edits (such as simultaneous outfit swap and background replacement), intermediate outputs are preserved if a subsequent stage encounters an issue.

### 3. Google Open Knowledge Format (OKF) Engine (`okf_engine.py`)
- **Structured Knowledge Graph**: Maintains cross-linked Markdown nodes with YAML frontmatter, categorized by projects, concepts, references, profiles, and guides.
- **Bidirectional Graph Traversal**: Automatically resolves wikilinks and tags across indexed documents.
- **Memory Auto-Compilation**: Compiles long-term user memories and historical chat sessions into an accessible knowledge wiki with zero GPU VRAM overhead.

### 4. Retrieval-Augmented Generation (RAG) (`rag_engine.py`)
- **Document Ingestion**: Supports PDF, TXT, MD, PY, JS, TS, CSV, JSON, LOG, HTML, and CSS files.
- **Persistent Vector Store**: Built on `langchain-chroma` with embeddings computed locally via `langchain-ollama` (`nomic-embed-text`).
- **Noise Suppression**: Implements L2 distance thresholding to discard irrelevant context and employs casual greeting detection to avoid context flooding on short messages.
- **Thread Offloading & Deduplication**: Ingestion runs asynchronously via worker threads with temporary file isolation and automatic source deduplication.

### 5. Agentic Live Web Search (`search_engine.py`)
- **Privacy-Preserving Retrieval**: Scrapes live information via DuckDuckGo without requiring external API keys.
- **Offline Safety**: Performs lightweight connection checks before issuing queries, seamlessly falling back to local model weights when disconnected.
- **Rate-Limiting & Session Reuse**: Enforces query throttling and persistent connection pooling to prevent IP blocking.

### 6. Long-Term Memory and User Profiling (`memory_manager.py`)
- **Continuous Profiling**: Extracts user facts, development preferences, and active project contexts across sessions into persistent JSON storage.
- **Context Boundary Isolation**: Strictly separates historical summaries from active conversational prompts to eliminate hallucinated context leakage in new threads.
- **Session Lifecycle Management**: Full support for listing, loading, summarizing, and purging session histories.

### 7. Modern Web Interface & Legacy Desktop Shell
- **Angular 19 SPA (`amethyst-ui`)**: Features real-time Server-Sent Events (SSE) token streaming, markdown and syntax highlighting via Highlight.js, LaTeX-to-Unicode mathematical formatting, hardware telemetry widgets, and upload zones for documents and images.
- **Abortable Generation**: Supports immediate stream cancellation via `AbortController` without losing partial token output.
- **Desktop Integration (`ui_main.py` & `ide_bridge.py`)**: Includes global hotkey integration (`Ctrl+Shift+A`) to extract code snippets directly from external IDEs into the assistant, alongside offline speech-to-text (STT) and text-to-speech (TTS) engines.

### 8. VRAM Optimization & Hardware Protection
- **Single-Model Residency**: Constrains Ollama through `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=0` to ensure seamless model swaps on 8GB VRAM graphics cards.
- **Global GPU Concurrency Lock**: Enforces mutually exclusive GPU access between Ollama language inference and ComfyUI diffusion runs.
- **CUDA Enforcement**: Scripts force CUDA v13 execution to prevent unstable Vulkan driver fallbacks.

---

## Hardware Specifications

### Minimum Requirements
- **GPU**: NVIDIA GeForce RTX 3060 (12GB) or RTX 4060 (8GB)
- **VRAM**: 8GB dedicated VRAM (strict requirement for local dual-model and diffusion workflows)
- **System Memory (RAM)**: 16GB DDR4/DDR5
- **Storage**: 30GB free SSD space (model weights, vector indexes, and temporary scratch buffers)
- **Operating System**: Windows 10/11 (required for Windows audio APIs and global hotkey hooks)

### Recommended Requirements
- **GPU**: NVIDIA RTX 4070 / 4080 (12GB - 16GB VRAM)
- **System Memory (RAM)**: 32GB
- **Storage**: NVMe PCIe 4.0 SSD

---

## Project Structure

```text
AI_Assistant/
├── api_server.py             # FastAPI backend providing REST and SSE endpoints
├── ai_engine.py              # Dual-model routing, prompt management, and Ollama integration
├── memory_manager.py         # Session persistence, user profile extraction, and summarization
├── rag_engine.py             # ChromaDB vector store and document chunk ingestion
├── okf_engine.py             # Google Open Knowledge Format graph compilation and retrieval
├── comfy_bridge.py           # ComfyUI API integration, workflow compilation, inpainting
├── image_task_router.py      # Natural language image task intent parser and multi-stage planner
├── search_engine.py          # Offline-safe DuckDuckGo web search scraper
├── system_monitor.py         # psutil hardware telemetry (CPU, RAM, Disk, Battery)
├── code_executor.py          # Sandboxed script persistence and execution interface
├── document_reader.py        # File readers for PDF, Markdown, code, and text formats
├── vision_engine.py          # Multimodal screenshot analysis via local vision models
├── voice_engine.py           # Offline speech-to-text and text-to-speech engine
├── ide_bridge.py             # System hotkey hook (Ctrl+Shift+A) for external editors
├── ui_main.py                # Legacy CustomTkinter desktop interface
├── Modelfile.chat            # Ollama parameters for conversational model
├── Modelfile.coder           # Ollama parameters and system prompt for code model
├── requirements.txt          # Python package dependencies
├── start.bat                 # Primary application launcher (Ollama + Backend + Frontend)
├── start_portable.bat        # Portable environment launcher for external media
│
├── amethyst-ui/              # Angular 19 SPA frontend
│   ├── src/app/
│   │   ├── components/       # Chat window, input bar, sidebar, topbar, system stats
│   │   └── services/         # API HTTP client, SSE chat streaming service
│   ├── angular.json
│   └── package.json
│
└── docs/                     # Architectural documentation, issue trackers, and audit logs
```

---

## Installation and Setup

### Step 1: Install Ollama & Pull Base Models
Download and install [Ollama](https://ollama.com). Open a terminal and download the required weights:

```bash
ollama serve
ollama pull qwen2.5-coder:7b
ollama pull gemma3:4b
ollama pull nomic-embed-text
ollama pull llava              # Optional: For visual screenshot analysis
```

To build the customized Amethyst personas with predefined system prompts and parameters:

```bash
ollama create amethyst-coder -f Modelfile.coder
ollama create amethyst-chat -f Modelfile.chat
```

### Step 2: Install Python Dependencies
Ensure Python 3.10 or higher is installed. Set up dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Install Frontend Dependencies
Navigate to the Angular application directory and install node modules:

```bash
cd amethyst-ui
npm install
cd ..
```

### Step 4: Configure ComfyUI (Optional for Image Tasks)
For image generation and garment/scenario inpainting:
1. Install [ComfyUI](https://github.com/comfyanonymous/ComfyUI) (or use portable standalone distributions).
2. Ensure ComfyUI runs on default port `8188` (`http://localhost:8188`).
3. Place your preferred SDXL checkpoint (e.g., `sd_xl_base_1.0.safetensors` or realistic fine-tunes) in `ComfyUI/models/checkpoints/`.

---

## Running the Application

### Standard Startup
Launch the complete environment using the automated batch script:

```bash
start.bat
```

This script automatically:
1. Configures CUDA library flags (`OLLAMA_LLM_LIBRARY=cuda_v13`).
2. Configures single-model VRAM management (`OLLAMA_MAX_LOADED_MODELS=1`).
3. Starts the Ollama service bound to the primary NVIDIA GPU.
4. Starts the FastAPI backend at `http://localhost:8001`.
5. Starts the Angular web frontend at `http://localhost:4200`.
6. Launches your default web browser to the application dashboard.

### Portable Execution (USB / External Storage)
To run Amethyst from external media without leaving registry or temporary file residue on the host system:

```bash
start_portable.bat
```

This redirects temporary working files and profile databases to isolated scratch folders.

---

## Primary API Endpoints

The FastAPI server (`api_server.py`) provides the following programmatic endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Reports Ollama connectivity, resolved model names, and ComfyUI status. |
| `GET` | `/api/models` | Lists all local models registered in Ollama. |
| `POST` | `/api/chat/stream` | Server-Sent Events (SSE) streaming chat endpoint with automatic routing. |
| `GET` | `/api/sessions` | Retrieves saved conversation sessions. |
| `GET` | `/api/sessions/{id}` | Retrieves full message history and metadata for a specific session. |
| `DELETE` | `/api/sessions/{id}` | Deletes a conversation session from persistent storage. |
| `POST` | `/api/sessions/clear` | Purges all session histories and resets conversation memory. |
| `GET` | `/api/memory/profile` | Fetches extracted user facts, preferences, and project records. |
| `POST` | `/api/rag/ingest/upload` | Multipart file upload endpoint for ingesting documents into ChromaDB. |
| `GET` | `/api/rag/stats` | Returns total vector chunk counts and active collections. |
| `POST` | `/api/rag/clear` | Clears vector embeddings and resets the vector database. |
| `POST` | `/api/image/generate` | Generates a new image via ComfyUI text-to-image workflow. |
| `POST` | `/api/image/edit/outfit` | Swaps garment on an uploaded image using crop-and-stitch inpainting. |
| `POST` | `/api/image/edit/scenario`| Replaces image background environment while maintaining identity. |
| `GET` | `/api/image/checkpoints` | Lists installed checkpoints reported by ComfyUI. |
| `GET` | `/api/knowledge/topics` | Returns indexed Google OKF topics and node relationships. |
| `POST` | `/api/knowledge/compile` | Compiles memory and conversation histories into the OKF knowledge graph. |
| `GET` | `/api/system` | Telemetry snapshot containing CPU, RAM, disk, and battery usage. |
| `POST` | `/api/vision/analyze` | Evaluates screenshots or images via local multimodal vision models. |

---

## Shortcuts and Interactions

- **Enter**: Send message in active chat window.
- **Shift + Enter**: Insert newline in the prompt textarea.
- **Ctrl + Shift + A**: IDE Bridge hotkey (captures selected text from any open editor and routes to `amethyst-coder`).
- **Stop Generation**: Halts the active HTTP streaming connection via `AbortController` while keeping already rendered output intact.

---

## Security and Privacy Notice

Amethyst operates strictly on your local machine:
- Model weights, embeddings, vector indexes, and chat histories never leave your device.
- Web search is read-only and uses an anonymized HTTP scraper without third-party account tracking.
- Code execution is isolated and disabled by default in portable mode to ensure host security.
