@echo off
rem Checks a recording with the trained model.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 analysis\check.py) else (python analysis\check.py)
pause
