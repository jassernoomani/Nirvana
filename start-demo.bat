@echo off
rem Starts the whole Nirvana demo: Ollama model, back-end, front-end and two browser windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" -Action start
pause
