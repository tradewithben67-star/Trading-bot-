@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX - Verbindung zu MetaTrader 5 pruefen

echo.
echo   BENGX - Verbindung pruefen
echo   ==========================
echo   Zeigt, ob der Bot dein MT5-Konto erreicht, und was er dort
echo   handeln wuerde. Es wird NICHTS gehandelt.
echo.
echo   Vorher: MetaTrader 5 starten und anmelden.
echo.

if not exist ".env" (
  echo   Noch keine .env. Bitte zuerst einrichten.bat doppelklicken
  echo   und darin MT5_LOGIN, MT5_PASSWORD und MT5_SERVER eintragen.
  echo.
  pause
  exit /b 1
)

py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
echo   Python fehlt. Bitte zuerst einrichten.bat doppelklicken.
goto :ende

:mitpy
py -3 -m pip install --quiet MetaTrader5
py -3 -m bengx_bot --config config.toml konto
goto :ende

:mitpython
python -m pip install --quiet MetaTrader5
python -m bengx_bot --config config.toml konto
goto :ende

:ende
echo.
pause
