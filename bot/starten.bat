@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX Telegram-Bot

echo.
echo   BENGX - Telegram-Bot laeuft
echo   ===========================
echo   Dieses Fenster offen lassen. Zum Beenden: Strg+C
echo.

if not exist ".env" (
  echo   Es gibt noch keine .env.
  echo   Bitte zuerst einrichten.bat doppelklicken.
  echo.
  pause
  exit /b 1
)

py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
goto :keinpython

:mitpy
py -3 -m bengx_bot telegram
goto :ende

:mitpython
python -m bengx_bot telegram
goto :ende

:keinpython
echo   Python wurde nicht gefunden. Bitte zuerst einrichten.bat ausfuehren.
goto :ende

:ende
echo.
echo   Der Bot ist beendet.
pause
