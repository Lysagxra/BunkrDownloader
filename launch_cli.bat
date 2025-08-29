@echo off
echo Launching BunkrDownloader...

REM Check if virtual environment exists
if not exist venv (
    echo Virtual environment not found. Running setup_launcher.bat...
    call setup_launcher.bat
    if %ERRORLEVEL% NEQ 0 (
        echo Setup failed. Please run setup_launcher.bat manually to see the error.
        pause
        exit /b 1
    )
    echo Setup completed successfully. Continuing with launch...
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

REM Launch the application
echo Starting BunkrDownloader...
echo.

REM Check if URL was provided as an argument
if "%~1" == "" (
    echo Please enter a Bunkr URL to download:
    set /p BUNKR_URL=URL: 
) else (
    set BUNKR_URL=%~1
)

REM Check if URL is provided
if "%BUNKR_URL%" == "" (
    echo No URL provided. Exiting...
    pause
    exit /b 1
)

echo Processing URL: %BUNKR_URL%
echo.

python downloader.py %BUNKR_URL%
if %ERRORLEVEL% NEQ 0 (
    echo Application exited with error.
    pause
)

REM Deactivate virtual environment
call deactivate