@echo off
chcp 65001 >nul
title Amethyst Launcher

echo.
echo  [*] Starting Amethyst...
echo.

:: ── Memory management ─────────────────────────────────────────────────────────
:: Force Ollama to use CUDA v13 instead of falling back to Vulkan (which crashes)
set OLLAMA_LLM_LIBRARY=cuda_v13
:: Only keep 1 model in VRAM at a time — prevents OOM when swapping models
:: qwen2.5-coder=5.1GB + llama3.2=2.3GB = 7.4GB which crashes on 8GB VRAM
set OLLAMA_MAX_LOADED_MODELS=1
set OLLAMA_KEEP_ALIVE=0

:: Kill any existing Ollama to ensure it restarts with the right GPU
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul 2>&1
if not errorlevel 1 (
    echo  [*] Restarting Ollama to force RTX GPU...
    taskkill /IM ollama.exe /F >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo  [+] Starting Ollama on RTX 4060...
start /B ollama serve
timeout /t 4 /nobreak >nul

:: Verify GPU selection
ollama ps >nul 2>&1

:: Start FastAPI backend
echo  [+] Starting API server on http://localhost:8000
start "Amethyst API" cmd /k "cd /d %~dp0 && python api_server.py"

timeout /t 3 /nobreak >nul

:: Start Angular UI
echo  [+] Starting Angular UI on http://localhost:4200
start "Amethyst UI" cmd /k "cd /d %~dp0amethyst-ui && npm run start"

timeout /t 5 /nobreak >nul
echo  [+] Opening browser...
start http://localhost:4200

echo.
echo  ┌──────────────────────────────────────────┐
echo  │  Amethyst running on RTX 4060            │
echo  │  API : http://localhost:8000             │
echo  │  UI  : http://localhost:4200             │
echo  │  GPU : CUDA device 0 (NVIDIA RTX)        │
echo  └──────────────────────────────────────────┘
echo.
echo  Run "ollama ps" in a terminal to confirm GPU usage.
echo  Close the API and UI windows to stop.
echo.
pause
