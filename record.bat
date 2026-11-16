@echo off
rem Records a bench session to data\<name>.csv. Ctrl+C to stop.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 analysis\record.py) else (python analysis\record.py)
pause
