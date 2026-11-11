@echo off
REM Double-click to start soft grind. studio (Windows)
REM Your keys, projects and the installed helper files live in %USERPROFILE%\soft-grind-data,
REM so you can overwrite this app folder with a new version at any time.
cd /d "%~dp0"
if not exist "%~dp0app.py" (
  echo.
  echo This start file is no longer inside the soft-grind folder, so it can't find the app.
  echo Put start-windows.bat back in the soft-grind folder, next to app.py.
  echo For a Desktop icon: right-click start-windows.bat, then Send to, then Desktop ^(create shortcut^).
  echo.
  pause
  exit /b 1
)
where python >nul 2>nul || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
set "DATA=%USERPROFILE%\soft-grind-data"
if not exist "%DATA%" mkdir "%DATA%"
if not exist "%DATA%\venv" python -m venv "%DATA%\venv"
call "%DATA%\venv\Scripts\activate.bat"
python update.py
pip install -q -r requirements.txt
streamlit run app.py
pause
