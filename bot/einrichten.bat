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
goto :keinpython

:mitpy
py -3 einrichten.py
goto :ende

:mitpython
python einrichten.py
goto :ende

:keinpython
echo   Python wurde auf diesem Rechner nicht gefunden.
echo.
echo   So holst du es:
echo     1. Microsoft Store oeffnen
echo     2. nach "Python 3.13" suchen
echo     3. installieren
echo     4. diese Datei noch einmal doppelklicken
echo.
echo   Alternativ von python.org - dort beim Installieren
echo   den Haken bei "Add Python to PATH" setzen.
goto :ende

:ende
echo.
pause
