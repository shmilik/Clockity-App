@echo off
cd /d "%~dp0"
if not exist ".python_path" (
    echo.
    echo  ERROR: Python not configured.
    echo  Please run FIRST_TIME_SETUP.ps1 first (right-click -> Run with PowerShell).
    echo.
    pause
    exit /b 1
)
set /p PYTHON_EXE=<.python_path
echo.
echo  Starting ResearchTeam AutoGen Studio...
echo  Browser: http://127.0.0.1:8080
echo  Press Ctrl+C to stop the server.
echo.
"%PYTHON_EXE%" -m autogenstudio ui --host 127.0.0.1 --port 8080 --appdir "%~dp0autogenstudio"
pause
