@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py atc_lms.py %*) else (python atc_lms.py %*)
pause
