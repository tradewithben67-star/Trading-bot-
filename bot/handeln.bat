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
  if exist "config.example.toml" (
    copy "config.example.toml" "config.toml" >nul
    echo   Es gab noch keine config.toml — ich habe sie aus der Vorlage
    echo   angelegt. Bitte jetzt eintragen:
    echo     [bot] name            = welcher Bot laufen soll
    echo     [mt5] symbol          = wie dein Broker Gold nennt
    echo     [live] enabled        = true
    echo     [live] broker         = "mt5"
    echo.
    echo   Danach diese Datei noch einmal doppelklicken.
    echo.
    notepad "config.toml"
    pause
    exit /b 1
  )
  echo   Es fehlt config.example.toml. Ist der Ordner vollstaendig?
  echo.
  pause
  exit /b 1
)

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
