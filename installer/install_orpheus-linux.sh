#!/bin/bash
set -e

INSTALL_DIR="$HOME/Downloads/OrpheusDL"
# Optional: raw URL to patched librespot core.py
# Example:
# LIBRESPOT_CORE_PATCH_URL="https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py"
LIBRESPOT_CORE_PATCH_URL="${LIBRESPOT_CORE_PATCH_URL:-https://raw.githubusercontent.com/bascurtiz/orpheusdl-spotify/main/librespot/core.py}"

echo "[1/18] Installing system dependencies..."
sudo apt update
sudo apt install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-tk \
    binutils \
    wget \
    ffmpeg \
    upx-ucl \
    patchelf

echo "[2/18] Preparing installation directory..."
cd "$HOME/Downloads"
if [ ! -d "OrpheusDL" ]; then
    git clone https://github.com/bascurtiz/OrpheusDL
fi
cd OrpheusDL

echo "[3/18] Creating Python virtual environment..."
python3 -m venv venv

echo "[4/18] Activating virtual environment..."
source venv/bin/activate

echo "[5/18] Upgrading pip..."
pip install --upgrade pip wheel setuptools

echo "[6/18] Installing core requirements..."
pip install -r requirements.txt
echo "[6/18] Cleaning stale unplayplay metadata..."
python3 -c "import shutil,site; from pathlib import Path; roots=[Path(p) for p in site.getsitepackages()]; roots+=[Path(site.getusersitepackages())] if site.ENABLE_USER_SITE else []; [shutil.rmtree(e, ignore_errors=True) or print('[cleanup] Removed', e) for r in roots if r.is_dir() for e in r.iterdir() if e.name.startswith('unplayplay-0.0.8')]"
echo "[6/18] Forcing unplayplay==0.0.9..."
pip uninstall -y unplayplay >/dev/null 2>&1 || true
pip install --no-cache-dir --upgrade --force-reinstall "unplayplay==0.0.9"
UNPLAYPLAY_VERSION="$(pip show unplayplay 2>/dev/null | awk -F': ' '/^Version:/{print $2}')"
if [ "$UNPLAYPLAY_VERSION" != "0.0.9" ]; then
    echo "[FATAL] Expected unplayplay 0.0.9 but found '${UNPLAYPLAY_VERSION:-not installed}'."
    exit 1
fi
pip install --no-deps --upgrade --target vendor/librespot git+https://github.com/kokarare1212/librespot-python
if [ -n "$LIBRESPOT_CORE_PATCH_URL" ]; then
    echo "[6/18] Applying patched librespot core.py..."
    if wget -qO vendor/librespot/librespot/core.py "$LIBRESPOT_CORE_PATCH_URL"; then
        echo "[OK] Patched core.py installed."
    else
        echo "[WARN] Failed to download patched core.py. Continuing with upstream librespot."
    fi
fi

echo "[7/18] Installing service modules..."
mkdir -p modules

# Remove deprecated modules from previous installs
for _stale in beatsource jiosaavn; do
    if [ -d "modules/$_stale" ]; then
        echo "      Removing deprecated module: $_stale"
        rm -rf "modules/$_stale"
    fi
done

clone_module () {
    if [ ! -d "$2" ]; then
        git clone "$1" "$2"
    else
        cd "$2" && git pull && cd - >/dev/null
    fi
}

clone_module https://github.com/bascurtiz/orpheusdl-amazonmusic modules/amazonmusic
clone_module https://github.com/bascurtiz/orpheusdl-applemusic modules/applemusic
clone_module https://github.com/bascurtiz/orpheusdl-beatport modules/beatport
clone_module https://github.com/bascurtiz/orpheusdl-deezer modules/deezer
clone_module https://github.com/bascurtiz/orpheusdl-qobuz modules/qobuz
clone_module https://github.com/bascurtiz/orpheusdl-soundcloud modules/soundcloud
clone_module https://github.com/bascurtiz/orpheusdl-spotify modules/spotify
clone_module https://github.com/bascurtiz/orpheusdl-youtube modules/youtube

if [ ! -d "modules/tidal" ]; then
    git clone --recurse-submodules https://github.com/bascurtiz/orpheusdl-tidal modules/tidal
fi

# Veilig settings refresh
if [ "$(ls -A modules 2>/dev/null)" ]; then
    echo "[8/18] Initializing OrpheusDL settings..."
    python3 orpheus.py settings refresh || true
else
    echo "[8/18] Skipping settings refresh: no modules installed yet"
fi

echo "[9/18] Installing GUI..."
if [ ! -d "temp_gui" ]; then
    git clone https://github.com/bascurtiz/OrpheusDL-GUI temp_gui
fi

cp -a temp_gui/. .
rm -rf temp_gui
pip install -r requirements-gui.txt

echo "[10/18] Downloading Spotify.dll (required for lossless/FLAC)..."
if [ ! -f "Spotify.dll" ]; then
    wget http://orpheusdl-gui.x10.mx/Spotify.dll -O Spotify.dll
    echo "Downloaded Spotify.dll ($(du -h Spotify.dll | cut -f1))"
else
    echo "Spotify.dll already present, skipping download"
fi

echo "[10b/18] Downloading Shaka Packager + mp4decrypt fallback (Amazon Music)..."
python3 installer/bootstrap_extras.py --shaka --mp4decrypt || echo "[WARN] Shaka Packager download failed."

echo "[11/18] Installing build dependencies..."
pip install pyinstaller

echo "[12/18] Fixing PyInstaller GUI dependency detection..."
pip install --upgrade customtkinter darkdetect

echo "[13/18] Downloading AppImage tool..."
mkdir -p installer/linux
if [ ! -f "installer/linux/appimagetool-x86_64.AppImage" ]; then
    wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O installer/linux/appimagetool-x86_64.AppImage
fi
chmod +x installer/linux/appimagetool-x86_64.AppImage

echo "[14/18] Bundling FFmpeg for portability..."
mkdir -p portable_bin
cp "$(which ffmpeg)" portable_bin/
cp "$(which ffprobe)" portable_bin/

echo "[15/18] Creating GUI launcher..."
cat << 'EOF' > run_gui.sh
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export PATH="$PWD/portable_bin:$PATH"
python3 gui.py
EOF
chmod +x run_gui.sh

echo "[16/18] Preparing PyInstaller hooks..."
mkdir -p build_hooks
cat << 'EOF' > build_hooks/hook-modules.py
from PyInstaller.utils.hooks import collect_submodules
hiddenimports = collect_submodules('modules')
EOF

echo "[17/18] Setting portable build environment..."
export PYINSTALLER_STRIP=1
export UPX_DIR=$(dirname $(which upx))
export PYTHONHASHSEED=0
export PYTHONUTF8=1
export PATH="$PWD/portable_bin:$PATH"
echo "UPX path: $UPX_DIR"

# The metadata (desktop file, icons, and AppData) is handled automatically 
# by build_installer.py using the files in installer/linux/

echo "[18/18] Building installer package..."
python3 installer/build_installer.py --platform linux --format all

echo ""
echo "======================================"
echo "LINUX INSTALLER BUILD COMPLETE"
echo "======================================"
echo ""
echo "Run GUI locally:"
echo "./run_gui.sh"
echo ""
echo "Installer artifacts are in:"
echo "dist/"
echo ""
