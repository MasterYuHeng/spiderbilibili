@echo off
setlocal

cd /d "%~dp0"
wscript //nologo "%~dp0scripts\launch-dev.vbs"

exit /b 0
