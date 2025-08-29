@echo off
echo Building BunkrDownloader executable...

REM Check if virtual environment exists
if not exist venv (
    echo Virtual environment not found. Running setup_launcher.bat...
    call setup_launcher.bat
    if %ERRORLEVEL% NEQ 0 (
        echo Setup failed. Please run setup_launcher.bat manually to see the error.
        pause
        exit /b 1
    )
    echo Setup completed successfully. Continuing with build...
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Installing PyInstaller...
pip install pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo Building executable...
pyinstaller BunkrDownloaderGUI.spec

if %ERRORLEVEL% NEQ 0 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build successful!
echo The executable can be found in the 'dist' folder: dist\BunkrDownloaderGUI.exe
echo You can run it by double-clicking the file.
echo.

REM Deactivate virtual environment
call deactivate

pause
pause
