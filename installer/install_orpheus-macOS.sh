#!/bin/bash
set -e

INSTALL_DIR="$HOME/downloads/orpheusdl"
# Optional: raw URL to patched librespot core.py
# Example:
# LIBRESPOT_CORE_PATCH_URL="https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py"
LIBRESPOT_CORE_PATCH_URL="${LIBRESPOT_CORE_PATCH_URL:-https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py}"

echo "[1/9] Creating installation directory at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR" || exit

echo "[2/9] Cloning main OrpheusDL repository..."
git clone https://github.com/bascurtiz/OrpheusDL temp_core
mv temp_core/* temp_core/.[!.]* . 2>/dev/null
rm -rf temp_core

echo "[3/9] Installing core Python requirements..."
pip3 install --upgrade --ignore-installed -r requirements.txt
echo "      Cleaning stale unplayplay metadata..."
python3 -c "import shutil,site; from pathlib import Path; roots=[Path(p) for p in site.getsitepackages()]; roots+=[Path(site.getusersitepackages())] if site.ENABLE_USER_SITE else []; [shutil.rmtree(e, ignore_errors=True) or print('[cleanup] Removed', e) for r in roots if r.is_dir() for e in r.iterdir() if e.name.startswith('unplayplay-0.0.8')]"
echo "      Forcing unplayplay==0.0.9..."
pip3 uninstall -y unplayplay >/dev/null 2>&1 || true
pip3 install --no-cache-dir --upgrade --force-reinstall "unplayplay==0.0.9"
UNPLAYPLAY_VERSION="$(pip3 show unplayplay 2>/dev/null | awk -F': ' '/^Version:/{print $2}')"
if [ "$UNPLAYPLAY_VERSION" != "0.0.9" ]; then
    echo "[FATAL] Expected unplayplay 0.0.9 but found '${UNPLAYPLAY_VERSION:-not installed}'."
    exit 1
fi
pip3 install --no-deps --target vendor/librespot git+https://github.com/kokarare1212/librespot-python
if [ -n "$LIBRESPOT_CORE_PATCH_URL" ]; then
    echo "      Applying patched librespot core.py..."
    if curl -fsSL "$LIBRESPOT_CORE_PATCH_URL" -o vendor/librespot/librespot/core.py; then
        echo "[OK] Patched core.py installed."
    else
        echo "[WARN] Failed to download patched core.py. Continuing with upstream librespot."
    fi
fi

echo "[4/10] Preparing initial config directory..."
mkdir -p config

echo "[5/10] Cloning modules..."
mkdir -p modules

# Remove deprecated modules from previous installs
for _stale in beatsource jiosaavn; do
    if [ -d "modules/$_stale" ]; then
        echo "      Removing deprecated module: $_stale"
        rm -rf "modules/$_stale"
    fi
done

# macOS specific fix for Apple Music (skip broken uninstall when RECORD metadata is missing)
pip3 install --upgrade --ignore-installed certifi || pip3 install --force-reinstall --no-deps certifi
git clone https://github.com/bascurtiz/orpheusdl-amazonmusic modules/amazonmusic
git clone https://github.com/bascurtiz/orpheusdl-applemusic modules/applemusic
git clone https://github.com/bascurtiz/orpheusdl-beatport modules/beatport
git clone https://github.com/bascurtiz/orpheusdl-deezer modules/deezer
git clone https://github.com/bascurtiz/orpheusdl-qobuz modules/qobuz
git clone https://github.com/bascurtiz/orpheusdl-soundcloud modules/soundcloud
git clone https://github.com/bascurtiz/orpheusdl-spotify modules/spotify
git clone --recurse-submodules https://github.com/bascurtiz/orpheusdl-tidal modules/tidal
git clone https://github.com/bascurtiz/orpheusdl-youtube modules/youtube

echo "[6/10] Installing OrpheusDL GUI..."
git clone https://github.com/bascurtiz/OrpheusDL-GUI temp_gui
# Robust merge of cloned GUI repo into current directory.
# `cp -a` avoids `mv` glob edge-cases that can abort script under `set -e`.
cp -a temp_gui/. .
rm -rf temp_gui
pip3 install -r requirements-gui.txt

echo "[7/10] Downloading and extracting Deno (macOS version)..."
curl -L -o deno.zip https://github.com/denoland/deno/releases/download/v2.7.9/deno-x86_64-apple-darwin.zip
unzip -o deno.zip
rm deno.zip

echo "[8/10] Downloading Spotify.dll (required for lossless/FLAC)..."
if [ ! -f "Spotify.dll" ]; then
    if curl -fsSL "http://orpheusdl-gui.x10.mx/Spotify.dll" -o Spotify.dll; then
        echo "[OK] Spotify.dll downloaded."
    else
        echo "[WARN] Failed to download Spotify.dll."
    fi
else
    echo "Spotify.dll already present, skipping download"
fi

echo "      Note: Make sure FFmpeg is installed (e.g., via Homebrew: brew install ffmpeg)"

echo "[8b/10] Downloading Shaka Packager + mp4decrypt fallback (Amazon Music)..."
python3 installer/bootstrap_extras.py --shaka --mp4decrypt || echo "[WARN] Shaka Packager download failed."

echo "[9/10] Launching GUI for first-run settings generation..."
echo "      Please close the GUI window after it fully opens."
python3 gui.py || echo "[WARN] GUI exited with a non-zero code. Continuing anyway."

echo "[10/10] Building installer package..."
python3 installer/build_installer.py --platform macos

echo ""
echo "======================================"
echo "MACOS INSTALLER BUILD COMPLETE"
echo "======================================"
echo ""
echo "Installer artifacts are in:"
echo "dist/"