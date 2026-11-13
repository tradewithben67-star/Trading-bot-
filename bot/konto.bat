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
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo   Es gab noch keine .env — ich habe sie aus der Vorlage angelegt.
    echo.
    echo   Bitte jetzt bot\.env im Editor oeffnen und ganz unten eintragen:
    echo     MT5_LOGIN     = deine Kontonummer
    echo     MT5_PASSWORD  = dein HANDELSpasswort
    echo     MT5_SERVER    = der Servername, genau wie im Terminal
    echo.
    echo   Danach diese Datei noch einmal doppelklicken.
    echo.
    notepad ".env"
    pause
    exit /b 1
  )
  echo   Es fehlen .env und .env.example. Ist der Ordner vollstaendig?
  echo.
  pause
  exit /b 1
)

if not exist "config.toml" (
  copy "config.example.toml" "config.toml" >nul
  echo   config.toml aus der Vorlage angelegt. Falls dein Broker Gold
  echo   anders nennt als XAUUSD, sagt der Test das gleich.
  echo.
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
