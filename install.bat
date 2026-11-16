@echo off
rem Installs what the recorder and the model need. Run it once, with internet.
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m pip install pyserial matplotlib numpy pandas scikit-learn) else (python -m pip install pyserial matplotlib numpy pandas scikit-learn)
pause
