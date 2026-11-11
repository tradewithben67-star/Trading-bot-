@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX einrichten

echo.
echo   BENGX - Telegram-Assistent einrichten
echo   =====================================
echo.

py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
goto :kein_python

:mitpy
py -3 einrichten.py
goto :ende

:mitpython
python einrichten.py
goto :ende

:kein_python
echo   Auf diesem Rechner fehlt noch Python.
echo.
winget --version >nul 2>nul || goto :von_hand
echo   Ich kann es jetzt selbst installieren - dauert ein bis zwei Minuten.
echo   Es kann sein, dass Windows dabei einmal nachfragt.
echo.
set /p antwort="  Jetzt installieren? [j/n]: "
if /i not "%antwort%"=="j" goto :von_hand
echo.
echo   Wird installiert ...
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
echo.
echo   Das war es. Bitte diese Datei JETZT NOCH EINMAL doppelklicken -
echo   Windows muss Python erst neu einlesen.
goto :ende

:von_hand
echo.
echo   Dann von Hand, dauert auch nur zwei Minuten:
echo     1. www.python.org/downloads oeffnen
echo     2. auf den grossen gelben Knopf klicken
echo     3. die heruntergeladene Datei starten
echo     4. GANZ WICHTIG: unten den Haken bei
echo        "Add python.exe to PATH" setzen
echo     5. auf "Install Now" klicken
echo     6. diese Datei hier noch einmal doppelklicken
goto :ende

:ende
echo.
pause
