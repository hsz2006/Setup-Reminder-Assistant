@echo off
set /p ASSISTANT_PYTHON=<"%~dp0config\python-path.txt"
"%ASSISTANT_PYTHON%" "%~dp0app.py" cli
pause
