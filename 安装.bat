@echo off
chcp 65001 >nul
cd /d "%~dp0"
python install.py
echo.
pause
