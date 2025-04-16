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
        'customtkinter',
        'tkinter',
        'PIL',
        'json',
        'os',
        'subprocess',
        'sys',
        'threading',
        'platform',
        'time',
        'CTkToolTip',
        'wave',
        'Cryptodome.Cipher',
	    'Cryptodome.Cipher.AES',
	    'Cryptodome.Cipher.ARC4',
        'Cryptodome.Cipher.Blowfish',
        'Cryptodome.Hash',
        'Cryptodome.Hash.MD5',
        'ffmpeg-python',
	    'uuid',
		'requests',
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
