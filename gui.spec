block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include icon and other resources
        ('icon.ico', '.'),
        ('icon.icns', '.'),
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
    'webbrowser'
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
app = BUNDLE(
    exe, # Include the EXE definition
    name='OrpheusDL_GUI.app', # Standard macOS app naming
    icon='icon.icns', # Specify the icon for the .app bundle
    bundle_identifier=None, # Or set a specific identifier, e.g., 'com.yourdomain.orpheusdlgui'
    info_plist={
        'NSHighResolutionCapable': 'True', # Optional: Declare HiDPI support
        'NSRequiresAquaSystemAppearance': 'False' # Force dark mode
    }
)
