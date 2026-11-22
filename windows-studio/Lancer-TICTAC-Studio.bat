@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TICTAC Studio Regie
if exist "%~dp0TICTAC-Studio-Regie.exe" (
  start "" "%~dp0TICTAC-Studio-Regie.exe"
  exit /b 0
)
if exist "%~dp0dist\TICTAC-Studio-Regie.exe" (
  start "" "%~dp0dist\TICTAC-Studio-Regie.exe"
  exit /b 0
)
echo Construction de TICTAC Studio Regie...
python -m pip install -r requirements.txt -q
python -m PyInstaller --noconfirm TICTAC-Studio-Regie.spec
copy /Y "dist\TICTAC-Studio-Regie.exe" "TICTAC-Studio-Regie.exe" >nul
start "" "%~dp0TICTAC-Studio-Regie.exe"
