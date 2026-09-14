@echo off
title Downloading Lightweight AI Models...
echo ===================================================
echo     Amethyst - Downloading Small Brains
echo ===================================================
echo.
echo Redirecting Ollama downloads to the USB Drive...
set "OLLAMA_MODELS=%~dp0ollama_models"
echo Path set to: %OLLAMA_MODELS%
echo.

echo [1/2] Downloading 'tinyllama' (600 MB)...
"%~dp0ollama\ollama.exe" pull tinyllama
echo.

echo [2/2] Downloading 'qwen2.5-coder:1.5b' (1.5 GB)...
"%~dp0ollama\ollama.exe" pull qwen2.5-coder:1.5b
echo.

echo ===================================================
echo Downloads Complete! 
echo You can now close this window and launch Amethyst.
echo ===================================================
pause
