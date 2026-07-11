@echo off
REM Starts the Luna backend + your permanent ngrok tunnel in two windows.
REM
REM First time only (see docs/STABLE_URL_NGROK.md):
REM   1) winget install --id ngrok.ngrok
REM   2) ngrok config add-authtoken YOUR_AUTHTOKEN
REM   3) claim a free static domain in the ngrok dashboard
REM   4) put that domain in the line below:

set NGROK_DOMAIN=unexpired-composer-acquire.ngrok-free.dev

set PROJECT=%~dp0
set VENV=%PROJECT%..\venv\Scripts\activate.bat

start "Luna Backend" cmd /k "cd /d %PROJECT% && call \"%VENV%\" && python manage.py runserver"
start "Luna Tunnel"  cmd /k "ngrok http --domain=%NGROK_DOMAIN% 8000"

echo.
echo Backend + tunnel started.
echo Extension Server URL should be:  https://%NGROK_DOMAIN%
echo (set it once in Settings; it never changes)
echo.
pause
