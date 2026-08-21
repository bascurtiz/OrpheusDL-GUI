@echo off
setlocal EnableExtensions

:: Set the installation directory
set "INSTALL_DIR=C:\orpheusdl"
:: Optional: raw URL to patched librespot core.py
:: Example:
:: set "LIBRESPOT_CORE_PATCH_URL=https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py"
set "LIBRESPOT_CORE_PATCH_URL=https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py"

echo [1/9] Creating installation directory at %INSTALL_DIR%...
mkdir "%INSTALL_DIR%" 2>nul
cd /d "%INSTALL_DIR%"

echo [2/9] Cloning main OrpheusDL repository...
:: We clone a temporary folder, move contents to root, and delete the temp folder 
:: to prevent nested folders and allow the GUI to merge cleanly later.
git clone https://github.com/bascurtiz/OrpheusDL temp_core
xcopy /E /Y temp_core\* . >nul
rmdir /S /Q temp_core

echo [3/9] Installing core Python requirements...
pip install --upgrade --ignore-installed -r requirements.txt
pip install --no-deps --upgrade --target vendor/librespot git+https://github.com/kokarare1212/librespot-python
if defined LIBRESPOT_CORE_PATCH_URL (
    echo       Applying patched librespot core.py...
    curl -fL "%LIBRESPOT_CORE_PATCH_URL%" -o "vendor\librespot\librespot\core.py"
    if errorlevel 1 (
        echo [WARN] Failed to download patched core.py. Continuing with upstream librespot.
    ) else (
        echo [OK] Patched core.py installed.
    )
)

echo [4/10] Preparing initial config directory...
if not exist "config" mkdir "config"

echo [5/10] Cloning modules...
REM Remove deprecated modules from previous installs
for %%d in (beatsource jiosaavn) do (
    if exist "modules\%%d" (
        echo       Removing deprecated module: %%d
        rmdir /s /q "modules\%%d"
    )
)
git clone https://github.com/bascurtiz/orpheusdl-amazonmusic modules/amazonmusic
git clone https://github.com/bascurtiz/orpheusdl-applemusic modules/applemusic
git clone https://github.com/bascurtiz/orpheusdl-beatport modules/beatport
git clone https://github.com/bascurtiz/orpheusdl-deezer modules/deezer
git clone https://github.com/bascurtiz/orpheusdl-qobuz modules/qobuz
git clone https://github.com/bascurtiz/orpheusdl-soundcloud modules/soundcloud
git clone https://github.com/bascurtiz/orpheusdl-spotify modules/spotify
git clone --recurse-submodules https://github.com/bascurtiz/orpheusdl-tidal modules/tidal
git clone https://github.com/bascurtiz/orpheusdl-youtube modules/youtube
git clone https://github.com/bascurtiz/orpheusdl-lrclib modules/lrclib
git clone https://github.com/OrfiDev/orpheusdl-musixmatch modules/musixmatch

echo [6/10] Installing OrpheusDL GUI...
git clone https://github.com/bascurtiz/OrpheusDL-GUI temp_gui
xcopy /E /Y temp_gui\* . >nul
rmdir /S /Q temp_gui
pip install -r requirements-gui.txt

echo [7/10] Downloading and extracting Deno...
curl -L -o deno.zip https://github.com/denoland/deno/releases/download/v2.8.0/deno-x86_64-pc-windows-msvc.zip
tar -xf deno.zip
del deno.zip

echo       Cleaning stale unplayplay metadata...
python -c "import shutil,site; from pathlib import Path; roots=[Path(p) for p in site.getsitepackages()]; roots+=[Path(site.getusersitepackages())] if site.ENABLE_USER_SITE else []; [shutil.rmtree(e, ignore_errors=True) or print('[cleanup] Removed', e) for r in roots if r.is_dir() for e in r.iterdir() if e.name.startswith('unplayplay-0.0.8')]"
echo       Forcing unplayplay==0.0.9...
pip uninstall -y unplayplay >nul 2>&1
pip install --no-cache-dir --upgrade --force-reinstall unplayplay==0.0.9
if errorlevel 1 goto :error
set "UNPLAYPLAY_VERSION="
for /f "tokens=2 delims=:" %%A in ('pip show unplayplay ^| findstr /B /C:"Version:"') do set "UNPLAYPLAY_VERSION=%%A"
set "UNPLAYPLAY_VERSION=%UNPLAYPLAY_VERSION: =%"
if not "%UNPLAYPLAY_VERSION%"=="0.0.9" (
    echo [ERROR] Expected unplayplay 0.0.9 but found %UNPLAYPLAY_VERSION%.
    goto :error
)
echo [8/10] Copying FFmpeg and downloading Spotify.dll...
:: Assuming ffmpeg.exe is located directly in C:\ as per your instructions.
:: If it's a folder, change this to xcopy /E /Y C:\ffmpeg\* .
copy C:\ffmpeg.exe .
curl -fL -o Spotify.dll http://orpheusdl-gui.x10.mx/Spotify.dll
if errorlevel 1 (
    echo [WARN] Failed to download Spotify.dll from server.
    echo [WARN] Trying local fallback C:\Spotify.dll...
    copy C:\Spotify.dll .
    if errorlevel 1 (
        echo [WARN] Could not obtain Spotify.dll automatically.
    ) else (
        echo [OK] Spotify.dll copied from local fallback.
    )
) else (
    echo [OK] Spotify.dll downloaded.
)

echo [8b/10] Downloading Shaka Packager + mp4decrypt fallback (Amazon Music)...
python installer\bootstrap_extras.py --shaka --mp4decrypt
if errorlevel 1 (
    echo [WARN] Shaka Packager download failed. Amazon Music may not work until it is installed manually.
)

echo [9/10] Launching GUI for first-run settings generation...
echo       Please close the GUI window after it fully opens.
python gui.py
if errorlevel 1 (
    echo [WARN] GUI exited with a non-zero code. Continuing anyway.
)

echo [10/10] Building installer package...
python installer/build_installer.py --platform windows
if errorlevel 1 goto :error

echo.
echo ======================================
echo WINDOWS INSTALLER BUILD COMPLETE
echo ======================================
echo.
echo Installer artifacts are in:
echo dist/

pause
goto :eof

:error
echo [FATAL] Dependency installation failed.
pause
exit /b 1