@echo off
title Booting Amethyst OS...
echo ==============================================
echo       INITIALIZING AMETHYST AI SYSTEM
echo ==============================================
echo.
echo Please wait while the portable environment loads...
echo.

:: Navigate to the AI_Assistant folder where the real script lives
cd /d "%~dp0AI_Assistant"

:: Execute the portable launcher
call start_portable.bat

exit
