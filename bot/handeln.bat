@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX - Handelsbot am Konto

echo.
echo   BENGX - Handelsbot
echo   ==================
echo   Dieses Fenster offen lassen. Solange es laeuft, handelt der Bot.
echo   Zum Beenden: Strg+C oder Fenster schliessen.
echo.
echo   NOT-AUS: die Datei state\KILLSWITCH anlegen. Beim naechsten
echo   Durchlauf wird alles geschlossen und nichts Neues eroeffnet.
echo.

if not exist "config.toml" (
  echo   Es fehlt config.toml. Kopiere config.example.toml nach
  echo   config.toml und trage dein Symbol ein.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo   Es fehlt .env mit den MT5-Zugangsdaten.
  echo.
  pause
  exit /b 1
)

echo   Erst die Verbindung pruefen ...
echo.
py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
echo   Python fehlt. Bitte zuerst einrichten.bat doppelklicken.
goto :ende

:mitpy
py -3 -m pip install --quiet MetaTrader5
py -3 -m bengx_bot --config config.toml konto || goto :abbruch
echo.
echo   Verbindung steht. Der Bot laeuft jetzt.
echo.
py -3 -m bengx_bot --config config.toml live --loop
goto :ende

:mitpython
python -m pip install --quiet MetaTrader5
python -m bengx_bot --config config.toml konto || goto :abbruch
echo.
echo   Verbindung steht. Der Bot laeuft jetzt.
echo.
python -m bengx_bot --config config.toml live --loop
goto :ende

:abbruch
echo.
echo   Die Verbindung steht nicht. Es wurde nichts gehandelt.

:ende
echo.
pause
