@echo off
rem Stops the Nirvana back-end and front-end and unloads the model from memory.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" -Action stop
pause
