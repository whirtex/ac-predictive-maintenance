@echo off
rem Trains the model on the healthy recordings of data\.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 analysis\train.py) else (python analysis\train.py)
pause
