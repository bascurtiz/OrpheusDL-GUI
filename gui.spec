import platform
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules
# Do not import Tree from PyInstaller.building (path changed in 6.x). We build datas as 2-tuples below.

block_cipher = None

# Resolve paths relative to the spec file. PyInstaller injects SPECPATH (spec dir); __file__ is not set when spec runs.
try:
    SPEC_DIR = os.path.abspath(SPECPATH)
except NameError:
    SPEC_DIR = os.getcwd()
MODULES_SRC = os.path.join(SPEC_DIR, 'modules')

# Collect ffmpeg-python package properly to avoid circular import issues
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all('ffmpeg')
print(f"[PyInstaller] Collected ffmpeg submodules: {ffmpeg_hiddenimports}")

dc_datas, dc_binaries, dc_hiddenimports = collect_all('dataclass-click')
iq_datas, iq_binaries, iq_hiddenimports = collect_all('inquirerpy')
_tkdnd_datas, _tkdnd_binaries, _tkdnd_hiddenimports = collect_all('tkinterdnd2')
structlog_datas, structlog_binaries, structlog_hiddenimports = collect_all('structlog')
httpx_retries_datas, httpx_retries_binaries, httpx_retries_hiddenimports = collect_all('httpx_retries')
print(f"[PyInstaller] Collected structlog hiddenimports: {len(structlog_hiddenimports)}")
print(f"[PyInstaller] Collected httpx_retries hiddenimports: {len(httpx_retries_hiddenimports)}")

# Collect additional data files based on what exists in the source directory
additional_datas = [
    ('icon.ico', '.'),
    ('icon.icns', '.'),
    ('icon.png', '.'),
    ('update_checker.py', '.'),
]

# Vendored librespot-python (Spotify OAuth/stream path)
_librespot_vendor_root = os.path.join(SPEC_DIR, "vendor", "librespot")
_librespot_files = 0
if os.path.isdir(_librespot_vendor_root):
    def _skip_vendor_ls(dirname):
        if dirname in ("__pycache__", ".git"):
            return True
        return False
    for _root, _dirs, _filenames in os.walk(_librespot_vendor_root):
        _dirs[:] = [d for d in _dirs if not _skip_vendor_ls(d)]
        _rel = os.path.relpath(_root, _librespot_vendor_root)
        for _f in _filenames:
            if _f.endswith(".pyc"):
                continue
            _src = os.path.join(_root, _f)
            if _rel == ".":
                _dest_dir = os.path.join("vendor", "librespot")
            else:
                _dest_dir = os.path.join("vendor", "librespot", _rel.replace(os.sep, "/"))
            additional_datas.append((_src, _dest_dir))
            _librespot_files += 1
    print(f"[PyInstaller] vendor/librespot: bundled {_librespot_files} file(s)")
else:
    print("[PyInstaller] WARNING: vendor/librespot missing — Librespot Spotify mode may fail in frozen app")

_librespot_hiddenimports = []
_librespot_player_hi = []
if os.path.isdir(_librespot_vendor_root):
    _spath_saved = list(sys.path)
    try:
        sys.path.insert(0, _librespot_vendor_root)
        if os.path.isdir(os.path.join(_librespot_vendor_root, "librespot")):
            try:
                _librespot_hiddenimports = collect_submodules("librespot")
                print(f"[PyInstaller] Collected librespot-python submodules: {len(_librespot_hiddenimports)}")
            except Exception as _lib_exc:
                print(f"[PyInstaller] WARNING: collect_submodules(librespot) failed: {_lib_exc}")
                _librespot_hiddenimports = ["librespot"]
        if os.path.isdir(os.path.join(_librespot_vendor_root, "librespot_player")):
            try:
                _librespot_player_hi = collect_submodules("librespot_player")
                print(f"[PyInstaller] Collected librespot_player submodules: {len(_librespot_player_hi)}")
            except Exception as _lp_exc:
                print(f"[PyInstaller] WARNING: collect_submodules(librespot_player) failed: {_lp_exc}")
                _librespot_player_hi = ["librespot_player"]
    finally:
        sys.path[:] = _spath_saved

# Include platforms folder (platform icons)
PLATFORMS_DIR = os.path.join(SPEC_DIR, 'platforms')
if os.path.isdir(PLATFORMS_DIR):
    platform_files = [f for f in os.listdir(PLATFORMS_DIR) if os.path.isfile(os.path.join(PLATFORMS_DIR, f))]
    for f in platform_files:
        additional_datas.append((os.path.join(PLATFORMS_DIR, f), 'platforms'))
    print(f"[PyInstaller] Including platforms folder with {len(platform_files)} files")

# Include each module subfolder explicitly as (src, dest) 2-tuples so no module (e.g. youtube) is omitted.
# Tree() returns 3-tuple TOC entries; Analysis(datas=...) expects 2-tuples, so we build the list manually.
if os.path.isdir(MODULES_SRC):
    _exclude_dirs = {'__pycache__', '.git'}
    _exclude_suffixes = ('.pyc',)
    def _should_skip(path):
        if path in _exclude_dirs or path.endswith(_exclude_suffixes) or path == '.gitignore':
            return True
        return False
    modules_init = os.path.join(MODULES_SRC, '__init__.py')
    if os.path.isfile(modules_init):
        additional_datas.append((modules_init, 'modules'))
    module_subdirs = [d for d in os.listdir(MODULES_SRC) if os.path.isdir(os.path.join(MODULES_SRC, d))]
    for subdir in sorted(module_subdirs):
        if subdir == '__pycache__':
            continue
        src_root = os.path.join(MODULES_SRC, subdir)
        dest_prefix = os.path.join('modules', subdir)
        for root, dirs, filenames in os.walk(src_root, topdown=True):
            dirs[:] = [d for d in dirs if not _should_skip(d)]
            rel_root = os.path.relpath(root, src_root)
            for f in filenames:
                if _should_skip(f):
                    continue
                src_path = os.path.join(root, f)
                if rel_root == '.':
                    dest_path = os.path.join(dest_prefix, f)
                else:
                    dest_path = os.path.join(dest_prefix, rel_root, f)
                additional_datas.append((src_path, os.path.dirname(dest_path)))
    print(f"[PyInstaller] Including modules folder with: {module_subdirs}")

# Collect binaries (ffmpeg - Windows only)
# On macOS/Linux, we don't bundle ffmpeg - users should install via package manager
# macOS: brew install ffmpeg
# Linux: sudo apt install ffmpeg (or equivalent for your distro)
additional_binaries = []

# Include ffmpeg binary only on Windows
# Include ffmpeg binary only on Windows
if platform.system() == 'Windows':
    # We do NOT bundle binaries in the EXE anymore, as the installer handles them
    pass
    # if os.path.isfile('ffmpeg.exe'):
    #     additional_binaries.append(('ffmpeg.exe', '.'))
    #     print("[PyInstaller] Including Windows ffmpeg.exe binary")
    # if os.path.isfile('deno.exe'):
    #     additional_binaries.append(('deno.exe', '.'))
    #     print("[PyInstaller] Including Windows deno.exe binary")
elif platform.system() == 'Darwin':
    print("[PyInstaller] macOS: NOT bundling ffmpeg (use Homebrew: brew install ffmpeg)")
elif platform.system() == 'Linux':
    print("[PyInstaller] Linux: NOT bundling ffmpeg (use: sudo apt install ffmpeg)")

# Shaka Packager (Amazon Music decryption) — native binary (not datas) to avoid DLL load issues
_shaka_candidates = []
if platform.system() == 'Windows':
    _shaka_candidates = ['packager-win-x64.exe', 'packager-win.exe', 'shaka-packager.exe']
elif platform.system() == 'Darwin':
    _shaka_candidates = ['packager-osx-x64', 'packager-osx', 'shaka-packager']
else:
    _shaka_candidates = ['packager-linux-x64', 'packager-linux', 'shaka-packager']
for _shaka_name in _shaka_candidates:
    _shaka_path = os.path.join(SPEC_DIR, _shaka_name)
    if os.path.isfile(_shaka_path):
        additional_binaries.append((_shaka_path, '.'))
        additional_datas.append((_shaka_path, '.'))
        print(f"[PyInstaller] Bundling Shaka Packager: {_shaka_name}")
        break
else:
    print("[PyInstaller] WARNING: Shaka Packager not found — Amazon Music downloads may fail until it is placed next to the app")

# Bento4 mp4decrypt — DRM decryption fallback when Shaka Packager is unusable (e.g. the
# bundled macOS Shaka build is too new for an older host's libc++ and SIGABRTs on launch).
# Provide it at build time via installer/bootstrap_extras.py --mp4decrypt.
if platform.system() == 'Windows':
    _mp4decrypt_name = 'mp4decrypt.exe'
else:
    _mp4decrypt_name = 'mp4decrypt'
_mp4decrypt_path = os.path.join(SPEC_DIR, _mp4decrypt_name)
if os.path.isfile(_mp4decrypt_path):
    additional_binaries.append((_mp4decrypt_path, '.'))
    additional_datas.append((_mp4decrypt_path, '.'))
    print(f"[PyInstaller] Bundling mp4decrypt fallback: {_mp4decrypt_name}")
else:
    print("[PyInstaller] NOTE: mp4decrypt not found — Amazon Music has no decrypt fallback if Shaka Packager fails (run installer/bootstrap_extras.py --mp4decrypt to fetch it)")

a = Analysis(
    ['gui.py'],
    pathex=['.', os.path.join(SPEC_DIR, 'vendor', 'librespot'), os.path.join(SPEC_DIR, 'modules', 'applemusic', 'gamdl')],
    binaries=additional_binaries + ffmpeg_binaries + dc_binaries + iq_binaries + _tkdnd_binaries + structlog_binaries + httpx_retries_binaries,
    datas=additional_datas + ffmpeg_datas + dc_datas + iq_datas + _tkdnd_datas + structlog_datas + httpx_retries_datas,
    hiddenimports=[
        'certifi',
        'colorama',
        'Cryptodome',
        'Cryptodome.Cipher',
        'Cryptodome.Cipher.AES',
        'Cryptodome.Cipher.ARC4',
        'Cryptodome.Cipher.Blowfish',
        'Cryptodome.Hash',
        'Cryptodome.Hash.MD5',
        'CTkToolTip',
        'customtkinter',
        'defusedxml',
        'future',
        'idna',
        'json',
        'm3u8',
        'mutagen',
        'os',
        'PIL',
        'PIL._tkinter_finder',
        'platform',
        'requests',
        'subprocess',
        'sys',
        'threading',
        'time',
        'tkinter',
        'tqdm',
        'urllib3',
        'utils.utils',
        'uuid',
        'wave',
        'webbrowser',
        'pkce',
        'pywidevine',
        'yt_dlp',
        'aiohttp',
        'aiofiles',
        'httpx',
        'httpx_retries',
        'structlog',
        'async_lru',
        'pywinstyles',
        'tkinterdnd2',
        'packaging',
        'base62',                   # Spotify ID conversion (module name is 'base62')
        'google.protobuf',          # Required for Spotify proto files
        'Crypto',                   # Generic Crypto (pycryptodome)
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Util',
        'Crypto.Util.Counter',
        'dataclass-click',
        'inquirerpy',
        'click',
        'pfzy',                     # Dependency for inquirerpy
        'prompt_toolkit',            # Dependency for inquirerpy
        'websocket',                # Dependency for librespot
        'zeroconf',                 # Dependency for librespot
        'ifaddr',                   # Dependency for zeroconf
        'pyogg',                    # Dependency for librespot
        'modules.applemusic.interface',
    ] + ffmpeg_hiddenimports + dc_hiddenimports + iq_hiddenimports + _tkdnd_hiddenimports + structlog_hiddenimports + httpx_retries_hiddenimports + _librespot_hiddenimports + _librespot_player_hi,
    excludes=['torch', 'cuda', 'pytorch', 'matplotlib', 'pandas', 'numpy'],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=['hook-ffmpeg.py'],  # Pre-import ffmpeg to avoid circular import
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

# Use EXE normally unless on macOS (Darwin), where we avoid onefile
if platform.system() == 'Darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='OrpheusDL_GUI',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='icon.icns',
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='OrpheusDL_GUI',
    )

    app = BUNDLE(
        coll,
        name='OrpheusDL GUI.app',
        icon='icon.icns',
        bundle_identifier='com.orpheusdl.gui',
        info_plist={
            'CFBundleName': 'OrpheusDL GUI',
            'CFBundleDisplayName': 'OrpheusDL GUI',
            'NSHighResolutionCapable': 'True',
            'NSRequiresAquaSystemAppearance': 'False'
        }
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='OrpheusDL_GUI',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        icon='icon.ico',
        # this will default to onefile, or add `onefile=True` explicitly
    )

