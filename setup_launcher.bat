@echo off
echo Setting up BunkrDownloader environment...

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH. Please install Python 3 and try again.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment. Please make sure you have venv module installed.
        pause
        exit /b 1
    )
)

REM Activate virtual environment and install dependencies
echo Activating virtual environment and installing dependencies...
call venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Setup completed successfully!
echo You can now run launch_cli.bat to start BunkrDownloader.
echo.
pause