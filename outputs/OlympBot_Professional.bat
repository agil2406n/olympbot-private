@echo off
setlocal
chcp 65001 >nul
title OlympBot Demo Terminal v6.3 - Server 24-7
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
echo [1/4] Python yoxlanilir...
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 tapilmadi.
  echo Python 3.12 qurasdirin ve yeniden cehd edin.
  pause
  exit /b 1
)
echo [2/4] Lazimi paketler yoxlanilir...
py -3.12 -c "import flask, playwright" >nul 2>&1
if errorlevel 1 (
  py -3.12 -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo Paketlerin qurasdirilmasi alinmadi.
    pause
    exit /b 1
  )
)
echo [3/4] Chromium muherriki yoxlanilir...
py -3.12 -m playwright install chromium
if errorlevel 1 (
  echo Chromium muherriki hazirlana bilmedi.
  pause
  exit /b 1
)
echo [4/4] OlympBot Demo Terminal v6.3 - Server 24-7 basladilir...
py -3.12 "%~dp0OlympBot_Professional.py"
if errorlevel 1 (
  echo.
  echo OlympBot Professional xəta ilə dayandı.
  echo Yuxaridaki xeta metninin sekilini cekin.
  pause
)
endlocal
