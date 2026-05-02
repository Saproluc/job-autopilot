@echo off
REM ============================================================
REM  Job AutoPilot — Windows Task Scheduler Setup
REM  Runs the job search automation every night at 11:00 PM
REM ============================================================

SET TASK_NAME=JobAutoPilot
SET SCRIPT_DIR=%~dp0..
SET PYTHON_CMD=python

REM Find Python in common locations
WHERE python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    WHERE python3 >nul 2>nul
    IF %ERRORLEVEL% NEQ 0 (
        echo ERROR: Python not found. Install Python 3.10+ from python.org
        pause
        exit /b 1
    )
    SET PYTHON_CMD=python3
)

echo Creating scheduled task: %TASK_NAME%
echo Run time: 11:00 PM daily
echo Working directory: %SCRIPT_DIR%
echo.

REM Delete existing task if it exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>nul

REM Create the task
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON_CMD%\" \"%SCRIPT_DIR%\src\main.py\"" ^
    /sc DAILY ^
    /st 23:00 ^
    /sd %DATE% ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f ^
    /it

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Scheduled task created successfully!
    echo    Job AutoPilot will run every night at 11:00 PM.
    echo    Make sure your computer is on and Chrome is not blocking it.
    echo.
    echo To remove: schtasks /delete /tn "%TASK_NAME%" /f
    echo To run now: schtasks /run /tn "%TASK_NAME%"
) ELSE (
    echo.
    echo ❌ Failed to create scheduled task. Try running as Administrator.
)

pause
