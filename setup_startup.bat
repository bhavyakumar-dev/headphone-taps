@echo off
echo ========================================================
echo   NuclearHeart - Headphone Like Translator Setup
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Installing/verifying Nuclear companion plugin...
python app\main.py --install-plugin
echo.

echo [2/3] Enabling Windows Startup autostart...
python -c "from app.autostart import StartupManager; StartupManager.set_enabled(True); print('Startup enabled:', StartupManager.is_enabled())"
echo.

echo [3/3] Launching NuclearHeart in background...
start "" wscript.exe "%~dp0launch_silent.vbs"

echo.
echo ========================================================
echo   Setup Complete!
echo   NuclearHeart is now active in your Windows system tray.
echo   Press your headphone button to like songs in Nuclear!
echo ========================================================
pause
