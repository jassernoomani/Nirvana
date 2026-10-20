@echo off
rem Same as start-demo.bat, but first rebuilds the demo data so it is dated around today.
rem Use it on the morning of the presentation. It deletes reviews and orders added since the last rebuild.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" -Action start -ResetData
pause
