@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BENGX KI

set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo   Python fehlt. Bitte zuerst einrichten.bat doppelklicken.
  goto :ende
)

%PY% -c "import torch" >nul 2>nul
if errorlevel 1 (
  echo   Die KI braucht PyTorch. Wird jetzt einmalig installiert, das dauert ein paar Minuten ...
  %PY% -m pip install torch
  if errorlevel 1 goto :ende
)

:menue
echo.
echo   BENGX KI
echo   1  Lernprobe   - beweist auf erfundenen Kursen, dass die KI lernt
echo   2  Trainieren  - aus deiner Kursdatei lernen
echo   3  Vorhersage  - Einschaetzung fuer die letzte Kerze
echo   4  Testen      - gespeichertes Modell auf neueren Kerzen pruefen
echo   5  Oberflaeche - alles im Browser: Analyse, Indikatoren, Strategie, Verlauf, Tokens
echo   0  Ende
set /p WAHL=  Auswahl:
if "%WAHL%"=="1" %PY% -m bengx_ki lernprobe --gegenprobe
if "%WAHL%"=="2" call :mitdatei trainieren
if "%WAHL%"=="3" call :mitdatei vorhersage
if "%WAHL%"=="4" call :mitdatei testen
if "%WAHL%"=="5" call :mitdatei oberflaeche
if "%WAHL%"=="0" goto :eof
goto :menue

:mitdatei
set CSV=data\xauusd_h1.csv
set /p CSV=  Kursdatei [%CSV%]:
%PY% -m bengx_ki %1 --csv "%CSV%"
goto :eof

:ende
echo.
pause
