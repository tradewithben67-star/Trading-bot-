@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX pruefen

py -3 --version >nul 2>nul && goto :mitpy
python --version >nul 2>nul && goto :mitpython
echo   Python fehlt. Bitte zuerst einrichten.bat doppelklicken.
goto :ende

:mitpy
py -3 -m bengx_bot pruefen
goto :ende

:mitpython
python -m bengx_bot pruefen
goto :ende

:ende
echo.
pause
