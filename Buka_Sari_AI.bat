@echo off
title Harmoni Agent Launcher
rem Alamat tidak ditulis tetap: %~dp0 adalah folder berkas ini sendiri.
cd /d "%~dp0"
if exist "runtime\python\pythonw.exe" (
    start "" "runtime\python\pythonw.exe" "%~dp0app_desktop.py"
) else (
    start "" pyw "%~dp0app_desktop.py"
)
exit
