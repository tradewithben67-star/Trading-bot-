@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX Telegram-Bot

echo.
echo   BENGX - Telegram-Bot
echo   ====================
echo   Dieses Fenster offen lassen. Solange es laeuft, antwortet dein Bot.
echo   Zum Beenden: Strg+C oder Fenster schliessen.
echo.

if not exist ".env" (
  echo   Noch nicht eingerichtet.
  echo   Bitte zuerst einrichten.bat doppelklicken.
  echo.
  pause
  exit /b 1
)

py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
echo   Python fehlt. Bitte zuerst einrichten.bat doppelklicken.
goto :ende

:mitpy
py -3 -m bengx_bot telegram
goto :ende

:mitpython
python -m bengx_bot telegram
goto :ende

:ende
echo.
echo   Der Bot ist beendet.
pause
