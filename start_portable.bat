@echo off
echo ==============================================
echo       Amethyst Portable Launcher
echo ==============================================

:: 1. Set the directory of this script as the root of the pen drive app
set "PORTABLE_ROOT=%~dp0"

:: 2. Set the AMETHYST_HOME environment variable to store data on the pen drive
:: We use %TEMP% instead of the USB drive to prevent SQLite file-locking hard crashes on FAT32 USBs!
set "AMETHYST_HOME=%TEMP%\.amethyst_portable"

:: 3. Set Ollama to use the models folder on the pen drive
:: This ensures Ollama doesn't try to download models to the host PC
set "OLLAMA_MODELS=%PORTABLE_ROOT%ollama_models"

:: 3.5 Redirect Temporary files to the pen drive for ZERO system residue
set "TMP=%PORTABLE_ROOT%.amethyst\temp"
set "TEMP=%PORTABLE_ROOT%.amethyst\temp"
if not exist "%TMP%" mkdir "%TMP%"

:: 4. Start Ollama in the background (Assuming you put ollama.exe in an 'ollama' folder)
if exist "%PORTABLE_ROOT%ollama\ollama.exe" (
    echo Starting portable Ollama...
    start /B "" "%PORTABLE_ROOT%ollama\ollama.exe" serve
) else (
    echo [WARNING] ollama.exe not found in \ollama\ directory.
    echo If Ollama is installed globally on this PC, it will use the global version.
)

:: 5. Start the Amethyst UI using the portable Python environment
set "PYTHON_CMD="
for /f "delims=" %%i in ('dir /s /b "%PORTABLE_ROOT%python\python.exe" 2^>nul') do (
    set "PYTHON_CMD=%%i"
    goto :found_python
)
:found_python

if defined PYTHON_CMD (
    echo [SYS] Verifying portable libraries...
    "%PYTHON_CMD%" -m pip install -r "%PORTABLE_ROOT%requirements.txt" --quiet
    
    echo Starting Amethyst UI using: %PYTHON_CMD%
    "%PYTHON_CMD%" "%PORTABLE_ROOT%ui_main.py"
    pause
) else (
    echo [WARNING] Portable Python not found anywhere inside the \python\ directory.
    echo Falling back to system Python...
    python "%PORTABLE_ROOT%ui_main.py"
)

echo Amethyst is running! Close this window to exit.
