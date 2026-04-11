@echo off
setlocal

cd /d "%~dp0"
wscript //nologo "%~dp0scripts\close-dev.vbs"

exit /b 0
