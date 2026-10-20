@echo off
title Harmoni Agent Gateway
rem Alamat tidak ditulis tetap: %~dp0 adalah folder berkas ini sendiri.
cd /d "%~dp0"
echo ===================================================
echo     MENYALAKAN CORE GATEWAY HARMONI AGENT
echo ===================================================
echo.
if exist "runtime\python\python.exe" (
    "runtime\python\python.exe" -m uvicorn server_core:app --host 127.0.0.1 --port 8001
) else (
    py -m uvicorn server_core:app --host 127.0.0.1 --port 8001
)
pause
