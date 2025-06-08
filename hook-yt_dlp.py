from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# yt-dlp hook - comprehensive collection
datas, binaries, hiddenimports = collect_all('yt_dlp')

# Also collect any additional submodules that might be missed
hiddenimports += collect_submodules('yt_dlp')

# Ensure the main yt_dlp module is included
if 'yt_dlp' not in hiddenimports:
    hiddenimports.append('yt_dlp') 