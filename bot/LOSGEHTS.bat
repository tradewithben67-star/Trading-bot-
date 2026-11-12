@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX - einrichten, pruefen, starten

echo.
echo   BENGX
echo   =====
echo   Dieses Fenster macht alles der Reihe nach:
echo   einrichten, pruefen, und erst dann starten.
echo.

rem --- Python finden oder anbieten, es zu installieren ---
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if defined PY goto :einrichten

echo   Auf diesem Rechner fehlt noch Python.
echo.
winget --version >nul 2>nul || goto :von_hand
set /p antwort="  Soll ich es jetzt installieren? [j/n]: "
if /i not "%antwort%"=="j" goto :von_hand
echo.
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
echo.
echo   Fertig. Bitte diese Datei JETZT NOCH EINMAL doppelklicken -
echo   Windows muss Python erst neu einlesen.
goto :ende

:von_hand
echo.
echo   Dann von Hand, dauert zwei Minuten:
echo     1. www.python.org/downloads oeffnen
echo     2. auf den grossen gelben Knopf klicken
echo     3. die Datei starten
echo     4. GANZ WICHTIG: unten den Haken bei
echo        "Add python.exe to PATH" setzen
echo     5. "Install Now", danach diese Datei noch einmal doppelklicken
goto :ende

rem --- 1. Einrichten, falls noch nichts da ist ---
:einrichten
if exist ".env" goto :pruefen
echo   Noch nicht eingerichtet - ich fuehre dich jetzt durch.
echo.
%PY% einrichten.py
if errorlevel 1 goto :ende
echo.

rem --- 2. Pruefen, und nur bei gruen weiter ---
:pruefen
echo.
echo   ------------------------------------------------
echo   Pruefe, ob alles da ist ...
echo   ------------------------------------------------
echo.
%PY% -m bengx_bot pruefen
if errorlevel 1 goto :nicht_bereit

rem --- 3. Starten ---
echo.
echo   ------------------------------------------------
echo   Alles gut. Der Bot laeuft jetzt.
echo   Dieses Fenster offen lassen - schliesst du es, ist er aus.
echo   ------------------------------------------------
echo.
%PY% -m bengx_bot telegram
echo.
echo   Der Bot ist beendet.
goto :ende

:nicht_bereit
echo.
echo   ------------------------------------------------
echo   Ich starte den Bot NICHT, weil oben etwas fehlt.
echo   Was genau, steht ein Stueck weiter oben in diesem Fenster.
echo.
echo   Mach ein Foto davon und schick es Claude.
echo   Willst du es selbst nachtragen: einrichten.bat doppelklicken.
echo   ------------------------------------------------

:ende
echo.
pause
