@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Charge .env local s'il existe (ne jamais committer .env)
if exist "%~dp0.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Build-Release.ps1" %*
exit /b %ERRORLEVEL%
