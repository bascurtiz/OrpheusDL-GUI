import platform

block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('icon.icns', '.'),
        ('icon.png', '.'),
        ('update_checker.py', '.'),
    ],
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
        'ffmpeg',
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
        'six',
        'subprocess',
        'sys',
        'threading',
        'time',
        'tkinter',
        'tqdm',
        'urllib3',
        'uuid',
        'wave',
        'webbrowser',
        'xmltodict',
        'pbkdf2',
        'srp',
        'pytz'
    ],
    excludes=['torch', 'cuda', 'pytorch', 'matplotlib', 'pandas', 'numpy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    entitlements_file=None,
    icon='icon.icns',
)

# --- macOS App Bundle Definition ---
if platform.system() == 'Darwin':
    app = BUNDLE(
        exe,
        name='OrpheusDL_GUI.app',
        icon='icon.icns',
        bundle_identifier=None,
        info_plist={
            'NSHighResolutionCapable': 'True',
            'NSRequiresAquaSystemAppearance': 'False'
        }
    )

