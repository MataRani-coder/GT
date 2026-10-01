@echo off
cd /d "%~dp0"
title Ghost Trail
if exist ".venv\Scripts\python.exe" (
  call ".venv\Scripts\activate.bat"
)
python sentinel_app.py
