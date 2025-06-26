import os
import sys
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    sys.path.insert(0, application_path)
    modules_path = os.path.join(application_path, 'modules')
    if os.path.isdir(modules_path):
        sys.path.insert(0, modules_path)
    gamdl_parent_path = os.path.join(application_path, 'modules', 'applemusic', 'gamdl')
    if os.path.isdir(gamdl_parent_path):
        sys.path.insert(0, gamdl_parent_path)
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import copy
import customtkinter
import datetime
import enum
import inspect
import io
import json
import multiprocessing
import os
import platform
import queue
import re
import requests
import subprocess
import sys
import threading
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import shutil
from CTkToolTip import CTkToolTip
from PIL import Image
from pathlib import Path
from tkinter import ttk
from tqdm import tqdm
from urllib.parse import urlparse
import traceback
import logging
import webbrowser
import time
import asyncio
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        print("[Patch] Applied asyncio.WindowsSelectorEventLoopPolicy() for Windows.")
    except Exception as e:
        print(f"[Patch] WARNING: Failed to set asyncio.WindowsSelectorEventLoopPolicy(): {e}")

_SCRIPT_DIR = None

SERVICE_COLORS = {
    "tidal": "#33ffe7",
    "jiosaavn": "#1eccb0",
    "apple music": "#FA586A",
    "beatport": "#00ff89",
    "beatsource": "#16a8f4",
    "deezer": "#a238ff",
    "qobuz": "#0070ef",
    "soundcloud": "#ff5502",
    "spotify": "#1cc659",
    "napster": "#295EFF",
    "kkbox": "#27B1D8",
    "idagio": "#5C34FE",
    "bugs": "#FF3B28",
    "nugs": "#C83B30"
}

SERVICE_DISPLAY_NAMES = {
    "tidal": "TIDAL",
    "jiosaavn": "JioSaavn",
    "apple music": "Apple Music",
    "beatport": "Beatport",
    "beatsource": "Beatsource",
    "deezer": "Deezer",
    "qobuz": "Qobuz",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
    "napster": "Napster",
    "kkbox": "KKBOX",
    "idagio": "IDAGIO",
    "bugs": "Bugs!",
    "nugs": "Nugs.net"
}

def _simple_slugify(text):
    if not text: return None
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'--+', '-', text)
    text = text.strip('-')
    return text if text else None

class DummyStderr:
    """A dummy file-like object that discards stderr output."""
    def write(self, msg): pass
    def flush(self): pass
    def isatty(self): return False
file_download_queue = []
output_queue = queue.Queue()
current_batch_output_path = None
_current_download_context = None

_queue_log_handler_instance = None

class QueueLogHandler(logging.Handler):
    """A handler class which sends records to a queue."""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        self.reset_ffmpeg_state_for_current_download()

    def reset_ffmpeg_state_for_current_download(self):
        self._specific_ffmpeg_hls_error_logged_this_download = False

    def emit(self, record):
        import re
        global current_settings
        is_debug_mode = current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False)

        if is_debug_mode:
            log_entry = f"[{record.levelname}] {self.format(record)}\n"
            self.log_queue.put(log_entry)
            return
        return

        msg_content = record.getMessage()
        hls_ffmpeg_warning_pattern = r"soundcloud --> HLS_UNEXPECTED_ERROR_IN_TRY_BLOCK: \[(WinError 2|Errno 2)\] (The system cannot find the file specified|No such file or directory)"
        is_primary_hls_ffmpeg_warning = (
            record.levelname == 'WARNING' and
            "Track download attempt" in msg_content and
            "failed for" in msg_content and
            re.search(hls_ffmpeg_warning_pattern, msg_content)
        )

        if is_primary_hls_ffmpeg_warning:
            if not self._specific_ffmpeg_hls_error_logged_this_download:
                self._specific_ffmpeg_hls_error_logged_this_download = True
                ffmpeg_path_setting = current_settings.get("globals", {}).get("advanced", {}).get("ffmpeg_path", "ffmpeg").strip()
                user_friendly_ffmpeg_msg = (
                    "\n[FFMPEG ERROR] FFmpeg was not found or is misconfigured. This is required for audio conversion (e.g., SoundCloud HLS streams).\n\n"
                    "Possible Solutions:\n"
                    "1. Install FFmpeg: If not installed, download from ffmpeg.org and install it.\n"
                    "2. Check PATH: Ensure the directory containing ffmpeg.exe (or ffmpeg) is in your system's PATH environment variable.\n"
                    "3. Configure in GUI: Go to Settings > Global > Advanced > FFmpeg Path, and set the full path to your ffmpeg executable.\n\n"
                    f"Current FFmpeg Path setting in GUI: '{ffmpeg_path_setting}'\n\n"
                    "Download process aborted due to FFmpeg issue."
                )
                self.log_queue.put(user_friendly_ffmpeg_msg + '\n')
            return
        if self._specific_ffmpeg_hls_error_logged_this_download:
            if record.levelname == 'ERROR' and "Failed after 3 attempts" in msg_content:
                return
        is_beatsource_404_warning = (
            record.name == 'root' and
            record.levelname == 'WARNING' and
            "Fetching as playlist failed (404)" in msg_content
        )
        if is_beatsource_404_warning:
            return
        
        if "Librespot:AudioKeyManager" in record.name and "Audio key error" in msg_content:
            return            
        if "modules.spotify" in record.name and "Rate limit suspected" in msg_content:
            return            
        if record.name == 'root' and record.levelname == 'ERROR' and "SpotifyAuthError" in msg_content:
            return
        if record.levelno == logging.INFO and ':' in record.name:
            return        
        if record.name == 'modules.spotify.spotify_api' and \
           record.levelname == 'ERROR' and \
           msg_content.startswith("GLOBAL_PATCH_DEBUG: Unexpected generic exception during Librespot session creation: [Errno 61] Connection refused"):
            return
        cleaned_msg = self.format(record) 
        cleaned_msg = re.sub(r' - \w+ - ', ' - ', cleaned_msg)
        if "Track download attempt" in cleaned_msg and "failed for" in cleaned_msg:            
            attempt_match = re.search(r'Track download attempt (\d+) failed for \w+\. Retrying in (\d+) seconds', cleaned_msg)
            if attempt_match:
                attempt_num = attempt_match.group(1)
                retry_seconds = attempt_match.group(2)
                cleaned_msg = re.sub(r'Track download attempt \d+ failed for \w+\. Retrying in \d+ seconds.*', 
                                   f'Download attempt {attempt_num} failed. Retrying in {retry_seconds} seconds...', cleaned_msg)
        
        if "Track download failed for" in cleaned_msg and "Module get_track_download returned None" in cleaned_msg:
            if "after 3 attempts" in cleaned_msg:
                cleaned_msg = re.sub(r'Track download failed for \w+: Module get_track_download returned None after \d+ attempts.*', 
                                   'Failed after 3 attempts (likely due to rate-limiting)', cleaned_msg)
            else:
                cleaned_msg = re.sub(r'Track download failed for \w+: Module get_track_download returned None.*', 
                                   'Download failed (likely due to rate-limiting)', cleaned_msg)
        
        log_entry = f"[{record.levelname}] {cleaned_msg}\n"
        self.log_queue.put(log_entry)

    def flush(self):
        pass
    def readable(self):
        return False
    def seekable(self):
        return False
    def writable(self):
        return True
    
def setup_logging(log_queue):
    global current_settings, _queue_log_handler_instance

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    _queue_log_handler_instance = QueueLogHandler(log_queue)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s', datefmt='%H:%M:%S')
    _queue_log_handler_instance.setFormatter(formatter)
    root_logger.addHandler(_queue_log_handler_instance)
    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
        root_logger.setLevel(logging.INFO)
        logging.info("Logging configured to use GUI queue (debug mode enabled).")
    else:
        root_logger.setLevel(logging.CRITICAL)
__version__ = "1.0.6"
from update_checker import run_check_in_thread
if platform.system() == "Windows":
    try:
        import winsound
    except ImportError:
        print("[Warning] 'winsound' module not found, sound notifications disabled on Windows.")
        winsound = None
else:
    winsound = None
if platform.system() == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2) 
        print("[DPI] Set Per Monitor V2 DPI Awareness (2)")
    except Exception as e1:
        try:
            windll.user32.SetProcessDpiAware()
            print("[DPI] Set System DPI Awareness (Legacy) - Fallback")
        except Exception as e2:
            print(f"[DPI] Warning: Could not set DPI awareness ({e1} / {e2})")

def get_script_directory():
    """Gets the directory containing the script/executable, handling bundled apps."""
    if getattr(sys, 'frozen', False):
        abs_executable_path = os.path.abspath(sys.executable)
        
        if platform.system() == "Darwin":
            if ".app/Contents/MacOS" in abs_executable_path:
                dir_of_executable = os.path.dirname(abs_executable_path)
                app_bundle_contents_dir = os.path.dirname(dir_of_executable)
                app_bundle_itself_path = os.path.dirname(app_bundle_contents_dir)
                return os.path.dirname(app_bundle_itself_path)
            else:
                return os.path.dirname(abs_executable_path)
        else:
            return os.path.dirname(abs_executable_path)
    else:
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            try:
                script_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
            except AttributeError:
                script_path = os.path.abspath(os.path.dirname(sys.argv[0]))
        return script_path
    
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        try:
             base_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
             base_path = os.path.abspath(".")
        if not os.path.isdir(base_path):
             base_path = get_script_directory()

    final_path = os.path.join(base_path, relative_path)
    return final_path
_app_dir = get_script_directory()
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
try:
    import orpheus.core
    _orpheus_core_available = True
except ImportError as e:
    print(f"ERROR: Failed to import orpheus.core: {e}. Patching and core functionality might fail.")
    _orpheus_core_available = False
    orpheus = type('obj', (object,), {'core': None})()
_original_resource_path = None
if _orpheus_core_available and hasattr(orpheus.core, 'resource_path'):
    _original_resource_path = orpheus.core.resource_path
    print("[Patch] Stored original orpheus.core.resource_path")

    def patched_resource_path(relative_path):
        """ Patched version to always return path relative to executable dir """
        executable_dir = get_script_directory()
        patched_path = os.path.join(executable_dir, relative_path)
        return patched_path

    orpheus.core.resource_path = patched_resource_path
    print("[Patch] Patched orpheus.core.resource_path")
elif _orpheus_core_available:
    print("[Patch] WARNING: orpheus.core.resource_path not found for patching.")
if _orpheus_core_available:
    try:
        from orpheus.core import Orpheus, MediaIdentification, ManualEnum, ModuleModes
        from orpheus.music_downloader import beauty_format_seconds, Downloader
        from utils.models import (ImageFileTypeEnum, CoverCompressionEnum, Oprinter, DownloadTypeEnum)
        ORPHEUS_AVAILABLE = True
    except (ImportError, AttributeError) as e:
        print(f"ERROR: Failed to import Orpheus library components after patching: {e}. Core functionality will be unavailable.")
        class Orpheus: pass
        class MediaIdentification: pass
        class ManualEnum: manual = 1
        class ModuleModes: lyrics=1; covers=2; credits=3
        def beauty_format_seconds(s): return str(s)
        class Downloader: pass
        class ImageFileTypeEnum(enum.Enum): pass
        class CoverCompressionEnum(enum.Enum): pass
        class Oprinter: pass
        class DownloadTypeEnum(enum.Enum): track="track"; artist="artist"; playlist="playlist"; album="album"
        ORPHEUS_AVAILABLE = False
else:
    print("Skipping import of Orpheus components as orpheus.core was not found.")
    class Orpheus: pass
    class MediaIdentification: pass
    class ManualEnum: manual = 1
    class ModuleModes: lyrics=1; covers=2; credits=3
    def beauty_format_seconds(s): return str(s)
    class Downloader: pass
    class ImageFileTypeEnum(enum.Enum): pass
    class CoverCompressionEnum(enum.Enum): pass
    class Oprinter: pass
    class DownloadTypeEnum(enum.Enum): track="track"; artist="artist"; playlist="playlist"; album="album"
    ORPHEUS_AVAILABLE = False
_original_get_terminal_size = os.get_terminal_size

def _patched_get_terminal_size(fd=None):
    """Patched os.get_terminal_size to prevent 'bad file descriptor' under pythonw.exe."""
    try:
        if fd is not None:
            return _original_get_terminal_size(fd)
        else:
            return _original_get_terminal_size()
    except (OSError, ValueError) as e:
        is_bad_fd_error = isinstance(e, ValueError) and 'bad file descriptor' in str(e)
        is_pythonw = sys.executable and sys.executable.lower().endswith("pythonw.exe")
        if is_bad_fd_error or is_pythonw:
            try: pass
            except Exception: pass
            return os.terminal_size((80, 24))
        else:
            raise e

os.get_terminal_size = _patched_get_terminal_size
try:
    print("[Patch] Applied os.get_terminal_size monkey-patch.", file=sys.stderr)
except Exception: pass
if platform.system() == "Windows":
    import subprocess
    _original_popen = subprocess.Popen
    
    class _PatchedPopen(_original_popen):
        """Patched subprocess.Popen class to suppress console windows on Windows."""
        def __init__(self, *args, **kwargs):
            try:
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = 0
                kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
                if 'startupinfo' not in kwargs:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                    
            except Exception as e:
                print(f"[Patch Warning] Could not set subprocess flags to hide console: {e}", file=sys.__stderr__)
            
            super().__init__(*args, **kwargs)
    
    subprocess.Popen = _PatchedPopen
    try:
        print("[Patch] Applied subprocess.Popen patch to suppress console windows on Windows.", file=sys.__stdout__)
    except Exception: pass

try:
    from customtkinter.windows.widgets import CTkEntry, CTkCheckBox, CTkComboBox
    import tkinter

    print("[Patch] Attempting to patch CTkEntry, CTkCheckBox, and CTkComboBox _draw methods...")
    _original_ctkentry_draw = CTkEntry._draw

    def _patched_ctkentry_draw(self, *args, **kwargs):
        try:
            return _original_ctkentry_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                pass
            else:
                raise e
        except Exception as e:
            print(f"[Patch Error] Unexpected error in CTkEntry._draw for {self}: {type(e).__name__}: {e}")
            raise e

    CTkEntry._draw = _patched_ctkentry_draw
    print("[Patch] Patched CTkEntry._draw method.")
    _original_ctkcheckbox_draw = CTkCheckBox._draw

    def _patched_ctkcheckbox_draw(self, *args, **kwargs):
        try:
            return _original_ctkcheckbox_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                pass
            else:
                raise e
        except Exception as e:
            print(f"[Patch Error] Unexpected error in CTkCheckBox._draw for {self}: {type(e).__name__}: {e}")
            raise e

    CTkCheckBox._draw = _patched_ctkcheckbox_draw
    print("[Patch] Patched CTkCheckBox._draw method.")
    _original_ctkcombobox_draw = CTkComboBox._draw
                                                                                  
    def _patched_ctkcombobox_draw(self, *args, **kwargs):
        try:
            return _original_ctkcombobox_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                pass
            else:
                raise e
        except Exception as e:
            print(f"[Patch Error] Unexpected error in CTkComboBox._draw for {self}: {type(e).__name__}: {e}")
            raise e
                                                                                  
    CTkComboBox._draw = _patched_ctkcombobox_draw
    print("[Patch] Patched CTkComboBox._draw method.")

except ImportError:
    print("[Patch Warning] Could not import CTkEntry, CTkCheckBox, or CTkComboBox for patching _draw methods.")
except Exception as e:
    print(f"[Patch Error] Failed to apply CustomTkinter _draw patches: {e}")

class OrpheusdlError(Exception): pass
class AuthenticationError(OrpheusdlError): pass
class DownloadError(OrpheusdlError): pass
class NetworkError(OrpheusdlError): pass

class DownloadCancelledError(Exception):
    """Locally defined placeholder for missing exception."""
    pass

class QualityEnum(enum.Enum):
    HIFI = 1
    HIGH = 2
    LOW = 3

def deep_merge(dict1, dict2, keys_to_overwrite_if_dicts=None):
    """Deep merge two dictionaries.
    
    Args:
        dict1: The dictionary to merge into.
        dict2: The dictionary to merge from.
        keys_to_overwrite_if_dicts: A list of keys for which, if both dict1[key]
                                     and dict2[key] are dictionaries, dict1[key]
                                     will be replaced by dict2[key] instead of
                                     their contents being recursively merged.
    """
    if keys_to_overwrite_if_dicts is None:
        keys_to_overwrite_if_dicts = []

    for key, value2 in dict2.items():
        if key in dict1:
            value1 = dict1[key]
            if isinstance(value1, dict) and isinstance(value2, dict):
                if key in keys_to_overwrite_if_dicts:
                    dict1[key] = value2
                else:
                    deep_merge(value1, value2, keys_to_overwrite_if_dicts) 
            else:
                dict1[key] = value2
        else:
            dict1[key] = value2
    return dict1

def load_settings():
    """Loads settings directly from ./config/settings.json."""
    global current_settings, CONFIG_FILE_PATH, DEFAULT_SETTINGS

    settings = {
        "globals": copy.deepcopy(DEFAULT_SETTINGS["globals"]),
        "credentials": {},
        "modules": {}
    }

    if not os.path.exists(CONFIG_FILE_PATH):
        error_message = f"CRITICAL ERROR: Configuration file not found at '{CONFIG_FILE_PATH}'. Cannot start without settings."
        print(error_message)
        raise FileNotFoundError(error_message)

    try:
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print(f"Directly reading settings from {CONFIG_FILE_PATH}...")
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            file_settings = json.load(f)
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print("File read successfully.")
        if "global" in file_settings:
            orpheus_global_from_file = file_settings["global"]
            if "general" in orpheus_global_from_file:
                orpheus_general = orpheus_global_from_file["general"]
                if "general" not in settings["globals"]: settings["globals"]["general"] = {}
                if "download_path" in orpheus_general: settings["globals"]["general"]["output_path"] = orpheus_general["download_path"]
                if "download_quality" in orpheus_general: settings["globals"]["general"]["quality"] = orpheus_general["download_quality"]
                if "search_limit" in orpheus_general: settings["globals"]["general"]["search_limit"] = orpheus_general["search_limit"]
                if "concurrent_downloads" in orpheus_general: settings["globals"]["general"]["concurrent_downloads"] = orpheus_general["concurrent_downloads"]
                if "play_sound_on_finish" in orpheus_general: settings["globals"]["general"]["play_sound_on_finish"] = orpheus_general["play_sound_on_finish"]
            for section_key, section_data in orpheus_global_from_file.items():
                 if section_key != "general" and section_key in settings["globals"]:
                     if isinstance(section_data, dict) and isinstance(settings["globals"].get(section_key), dict):
                         if section_key == "advanced" and "codec_conversions" in section_data:
                             for key, value in section_data.items():
                                 if key == "codec_conversions":
                                     settings["globals"][section_key][key] = copy.deepcopy(value)
                                 else:
                                     if key in settings["globals"][section_key] and isinstance(settings["globals"][section_key][key], dict) and isinstance(value, dict):
                                         deep_merge(settings["globals"][section_key][key], value)
                                     else:
                                         settings["globals"][section_key][key] = copy.deepcopy(value)
                         else:
                             deep_merge(settings["globals"][section_key], section_data)
        if "modules" in file_settings:
            settings["modules"] = copy.deepcopy(file_settings["modules"])
            platform_map_from_orpheus = { "bugs": "BugsMusic", "nugs": "Nugs", "soundcloud": "SoundCloud", "tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer", "idagio": "Idagio", "kkbox": "KKBOX", "napster": "Napster", "beatport": "Beatport", "beatsource": "Beatsource", "musixmatch": "Musixmatch", "spotify": "Spotify", "applemusic": "AppleMusic" }
            for orpheus_platform, creds_from_file in file_settings["modules"].items():
                gui_platform = platform_map_from_orpheus.get(orpheus_platform)
                if gui_platform and gui_platform in DEFAULT_SETTINGS["credentials"]:
                    platform_defaults = copy.deepcopy(DEFAULT_SETTINGS["credentials"][gui_platform])
                    deep_merge(platform_defaults, creds_from_file)
                    settings["credentials"][gui_platform] = platform_defaults
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print(f"Settings loaded and mapped from {CONFIG_FILE_PATH}")

    except (json.JSONDecodeError, IOError, TypeError, KeyError) as e:
        print(f"Error loading/mapping '{CONFIG_FILE_NAME}': {e}")
        print("Using default settings ONLY for globals. Credentials will be empty.")
        settings = {
            "globals": copy.deepcopy(DEFAULT_SETTINGS["globals"]),
            "credentials": {},
            "modules": {}
        }

    current_settings = settings
    return settings

def initialize_orpheus():
    """Attempts to initialize the global Orpheus instance."""
    global orpheus_instance, app, download_button, search_button, DATA_DIR, _SCRIPT_DIR

    if not ORPHEUS_AVAILABLE:
        print("Orpheus library not available. Skipping initialization.")
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(100, lambda: show_centered_messagebox("Initialization Error", "Orpheus library components are missing or failed to load. Core features will be disabled.", dialog_type="error"))
            if 'download_button' in globals() and download_button and download_button.winfo_exists(): download_button.configure(state="disabled")
            if 'search_button' in globals() and search_button and search_button.winfo_exists(): search_button.configure(state="disabled")
        except Exception as gui_e: print(f"Error showing Orpheus unavailable message in GUI: {gui_e}")
        return False

    if _SCRIPT_DIR is None:
        error_message = "FATAL ERROR: _SCRIPT_DIR (application base path) is not set. Cannot reliably initialize Orpheus. The application may be in an inconsistent state or not launched correctly."
        print(error_message)
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(100, lambda: show_centered_messagebox("Critical Application Error", error_message, dialog_type="error"))
        except Exception as gui_e: print(f"Error showing critical _SCRIPT_DIR error in GUI: {gui_e}")
        return False
    elif not os.path.isdir(_SCRIPT_DIR):
        error_message = f"FATAL ERROR: _SCRIPT_DIR '{_SCRIPT_DIR}' is not a valid directory. Cannot initialize Orpheus."
        print(error_message)
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(100, lambda: show_centered_messagebox("Critical Application Error", error_message, dialog_type="error"))
        except Exception as gui_e: print(f"Error showing critical _SCRIPT_DIR directory error in GUI: {gui_e}")
        return False
    original_cwd = os.getcwd()
    normalized_original_cwd = os.path.normpath(original_cwd)
    normalized_script_dir = os.path.normpath(_SCRIPT_DIR)

    if normalized_original_cwd != normalized_script_dir:
        print(f"[Initialize Orpheus] Current CWD is '{original_cwd}'. Target application directory (_SCRIPT_DIR) is '{_SCRIPT_DIR}'. Attempting to change CWD.")
        try:
            os.chdir(_SCRIPT_DIR)
            new_cwd = os.getcwd()
            print(f"[Initialize Orpheus] CWD successfully changed to '{new_cwd}'.")
            if os.path.normpath(new_cwd) != normalized_script_dir:
                print(f"[Initialize Orpheus] WARNING: CWD changed to '{new_cwd}', but it does not match the normalized _SCRIPT_DIR '{normalized_script_dir}'. This might indicate issues.")
        except Exception as e_chdir:
            error_detail = f"Type: {type(e_chdir).__name__}, Message: {e_chdir}"
            tb_str_chdir = traceback.format_exc()
            error_message_chdir = f"CRITICAL ERROR: Failed to change CWD to application directory '{_SCRIPT_DIR}' needed for Orpheus initialization.\nError: {error_detail}\nFull Traceback:\n{tb_str_chdir}\nOrpheus will likely fail to initialize or function correctly."
            print(error_message_chdir)
            try:
                if 'app' in globals() and app and app.winfo_exists():
                    user_error_msg = f"A critical error occurred while setting up the application's working directory: {e_chdir}. The application might not work correctly. Please check logs or try restarting."
                    app.after(100, lambda: show_centered_messagebox("Critical Setup Error", user_error_msg, dialog_type="error"))
            except Exception as gui_e: print(f"Error showing CWD change critical error in GUI: {gui_e}")
            return False
    global current_settings
    ffmpeg_path_setting = current_settings.get("globals", {}).get("advanced", {}).get("ffmpeg_path", "ffmpeg").strip()
    if ffmpeg_path_setting and ffmpeg_path_setting.lower() != "ffmpeg":
        if os.path.isfile(ffmpeg_path_setting):
            ffmpeg_dir = os.path.dirname(ffmpeg_path_setting)
            if ffmpeg_dir:
                current_path = os.environ.get("PATH", "")
                if ffmpeg_dir not in current_path.split(os.pathsep):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path

    if orpheus_instance is None:
        try:
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"Initializing global Orpheus instance (CWD: {os.getcwd()})...")
            orpheus_instance = Orpheus()
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print("Global Orpheus instance initialized successfully.")
            return True
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            error_message_init = f"FATAL: Failed to initialize Orpheus library (CWD: {os.getcwd()}).\nError Type: {type(e).__name__}\nError: {e}\nTraceback:\n{tb_str}"
            print(error_message_init)
            try:
                if 'app' in globals() and app and app.winfo_exists():
                    user_error_msg_init = f"Failed to start the Orpheus download engine: {e}. Please check your settings and ensure all components are correctly placed. If the problem persists, check the console output for more details."
                    app.after(100, lambda: show_centered_messagebox("Initialization Error", user_error_msg_init, dialog_type="error"))
                if 'download_button' in globals() and download_button and download_button.winfo_exists():
                    download_button.configure(state="disabled")
                if 'search_button' in globals() and search_button and search_button.winfo_exists():
                    search_button.configure(state="disabled")
            except NameError: pass
            except Exception as gui_e: print(f"Error showing Orpheus init error in GUI: {gui_e}")
            return False
    return True

def save_settings(show_confirmation: bool = True):
    """Loads existing settings, merges UI changes, validates, maps, and saves back to settings.json.

    Args:
        show_confirmation: If True, displays a success message box.

    Returns:
        True if save was successful, False otherwise.
    """
    global settings_vars, current_settings, DEFAULT_SETTINGS, CONFIG_FILE_PATH, orpheus_instance
    existing_settings = {}
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f: existing_settings = json.load(f)
        else:
            existing_settings = { "global": {"general": {},"formatting": {},"codecs": {},"covers": {},"playlist": {},"advanced": {},"module_defaults": {},"artist_downloading": {},"lyrics": {}}, "modules": {} }
    except (json.JSONDecodeError, IOError) as e:
        error_message = f"Error loading existing settings file '{CONFIG_FILE_PATH}':\\n{type(e).__name__}: {e}. Cannot proceed with save."
        show_centered_messagebox("Settings Error", error_message, dialog_type="error")
        return False
    updated_gui_settings = {"globals": {}, "credentials": {}}
    parse_errors = []
    collected_conversion_flags = {}
    aac_var_key = "advanced.conversion_flags.aac.audio_bitrate"
    aac_var = settings_vars.get("globals", {}).get(aac_var_key)
    if isinstance(aac_var, tkinter.StringVar):
        collected_conversion_flags["aac"] = {"audio_bitrate": aac_var.get()}
    else:
        parse_errors.append(f"AAC bitrate var not found or invalid type for key '{aac_var_key}'. Using default.")
        collected_conversion_flags["aac"] = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["aac"].copy()
    flac_var_key = "advanced.conversion_flags.flac.compression_level"
    flac_var = settings_vars.get("globals", {}).get(flac_var_key)
    if isinstance(flac_var, tkinter.StringVar):
        try:
            collected_conversion_flags["flac"] = {"compression_level": int(flac_var.get())}
        except ValueError:
            parse_errors.append(f"Invalid integer for FLAC compression from var '{flac_var_key}': '{flac_var.get()}'. Using default.")
            collected_conversion_flags["flac"] = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["flac"].copy()
    else:
        parse_errors.append(f"FLAC compression var not found or invalid type for key '{flac_var_key}'. Using default.")
        collected_conversion_flags["flac"] = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["flac"].copy()
    mp3_var_key = "advanced.conversion_flags.mp3.setting"
    mp3_var = settings_vars.get("globals", {}).get(mp3_var_key)
    if isinstance(mp3_var, tkinter.StringVar):
        raw_selected_mp3_option = mp3_var.get()
        selected_mp3_option = raw_selected_mp3_option.strip()
        
        if selected_mp3_option == "MP3 VBR (Max Quality)":
            selected_mp3_option = "VBR -V0"

        if selected_mp3_option == "VBR -V0":
            collected_conversion_flags["mp3"] = {"qscale:a": "0"}
        elif selected_mp3_option.endswith("k"):
            collected_conversion_flags["mp3"] = {"audio_bitrate": selected_mp3_option}
        else:
            parse_errors.append(f"Invalid MP3 setting selected from var '{mp3_var_key}': '{raw_selected_mp3_option}'. Using default.")
            collected_conversion_flags["mp3"] = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["mp3"].copy()
    else:
        parse_errors.append(f"MP3 setting var not found or invalid type for key '{mp3_var_key}'. Using default.")
        collected_conversion_flags["mp3"] = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["mp3"].copy()
    if "globals" not in updated_gui_settings: updated_gui_settings["globals"] = {}
    if "advanced" not in updated_gui_settings["globals"]: updated_gui_settings["globals"]["advanced"] = {}
    updated_gui_settings["globals"]["advanced"]["conversion_flags"] = collected_conversion_flags
    slider_handled_conversion_flag_keys = [
        "advanced.conversion_flags.aac.audio_bitrate",
        "advanced.conversion_flags.flac.compression_level",
        "advanced.conversion_flags.mp3.setting"
    ]

    for key_path_str, var in settings_vars.get("globals", {}).items():
        if key_path_str in slider_handled_conversion_flag_keys:
            continue

        if key_path_str == "advanced.codec_conversions":
            if isinstance(var, dict):
                keys = key_path_str.split('.')
                temp_dict = updated_gui_settings["globals"]
                for k_idx, k_part in enumerate(keys[:-1]):
                    if k_part not in temp_dict: temp_dict[k_part] = {}
                    temp_dict = temp_dict[k_part]
                
                final_dict_key = keys[-1]
                codec_conversions_to_save = {}
                grouped_vars = {}

                for inner_key, tkinter_var_instance in var.items():
                    if not isinstance(tkinter_var_instance, tkinter.Variable):
                        continue
                    actual_value = tkinter_var_instance.get()
                    base_key = inner_key.replace('_source', '').replace('_target', '')
                    if base_key not in grouped_vars: grouped_vars[base_key] = {}

                    if inner_key.endswith('_source'):
                        grouped_vars[base_key]['source'] = actual_value
                    elif inner_key.endswith('_target'):
                        grouped_vars[base_key]['target'] = actual_value

                for base_key, pair_values in grouped_vars.items():
                    source_val = pair_values.get('source')
                    target_val = pair_values.get('target')
                    if source_val and target_val:
                        codec_conversions_to_save[source_val] = target_val
                
                temp_dict[final_dict_key] = codec_conversions_to_save
            else:
                pass
            continue
        
        if not isinstance(var, tkinter.Variable):
            continue
        raw_value = var.get(); keys = key_path_str.split('.')
        try:
            current_data = updated_gui_settings["globals"]; original_value_scope = DEFAULT_SETTINGS["globals"]; valid_default_path = True
            for i, key in enumerate(keys[:-1]):
                if key not in current_data or not isinstance(current_data.get(key), dict): current_data[key] = {}
                current_data = current_data[key]
                if isinstance(original_value_scope, dict): original_value_scope = original_value_scope.get(key)
                else: valid_default_path = False; break
            setting_key = keys[-1]; original_value = None
            if valid_default_path and isinstance(original_value_scope, dict): original_value = original_value_scope.get(setting_key)
            elif valid_default_path and not isinstance(original_value_scope, dict) and keys[-1] == setting_key: original_value = original_value_scope
            if original_value is None and key_path_str in DEFAULT_SETTINGS["globals"]: original_value = DEFAULT_SETTINGS["globals"].get(key_path_str)
            final_value = None
            if isinstance(original_value, bool): final_value = bool(raw_value)
            elif isinstance(original_value, int):
                 try: final_value = int(raw_value)
                 except (ValueError, TypeError): parse_errors.append(f"Invalid integer for '{key_path_str}': '{raw_value}'"); final_value = original_value
            elif isinstance(original_value, float):
                 try: final_value = float(raw_value)
                 except (ValueError, TypeError): parse_errors.append(f"Invalid float for '{key_path_str}': '{raw_value}'"); final_value = original_value
            elif isinstance(original_value, list):
                 try:
                     str_val = str(raw_value).strip()
                     if not str_val: final_value = []
                     else: final_value = [s.strip() for s in str_val.split(',') if s.strip()]
                 except Exception as e: parse_errors.append(f"Invalid list format for '{key_path_str}': '{raw_value}' ({e})"); final_value = original_value
            elif isinstance(original_value, dict): final_value = original_value
            elif original_value is None: final_value = str(raw_value)
            else: final_value = str(raw_value)
            current_data[setting_key] = final_value
        except Exception as e: error_msg = f"Error processing global setting '{key_path_str}': {e}"; parse_errors.append(error_msg)
    for platform_name, fields in settings_vars.get("credentials", {}).items():
         if platform_name not in updated_gui_settings["credentials"]: updated_gui_settings["credentials"][platform_name] = {}
         for field_key, var in fields.items():
              if not isinstance(var, tkinter.Variable): continue
              updated_gui_settings["credentials"][platform_name][field_key] = str(var.get())
    if not validate_codec_conversions():
        return False

    if parse_errors:
         error_list = "\\n - ".join(parse_errors)
         show_centered_messagebox("Settings Error", f"Could not save due to invalid values:\\n - {error_list}", dialog_type="error")
         return False
    mapped_orpheus_updates = { "global": {"general": {},"formatting": {},"codecs": {},"covers": {},"playlist": {},"advanced": {},"module_defaults": {},"artist_downloading": {},"lyrics": {}}, "modules": {} }
    gui_globals = updated_gui_settings.get("globals", {})
    general_map_gui_to_orpheus = { "output_path": "download_path", "quality": "download_quality", "search_limit": "search_limit", "concurrent_downloads": "concurrent_downloads", "play_sound_on_finish": "play_sound_on_finish", "min_file_size_kb": "min_file_size_kb" }
    if "general" in gui_globals:
        gui_general_section = gui_globals["general"]
        if "general" not in mapped_orpheus_updates["global"]: mapped_orpheus_updates["global"]["general"] = {}
        for gui_key, orpheus_key in general_map_gui_to_orpheus.items():
            if gui_key in gui_general_section: mapped_orpheus_updates["global"]["general"][orpheus_key] = gui_general_section[gui_key]
    if "globals" in updated_gui_settings and "advanced" in updated_gui_settings["globals"] and "conversion_flags" in updated_gui_settings["globals"]["advanced"]:
        if "global" not in mapped_orpheus_updates: mapped_orpheus_updates["global"] = {}
        if "advanced" not in mapped_orpheus_updates["global"]: mapped_orpheus_updates["global"]["advanced"] = {}
        
        mapped_orpheus_updates["global"]["advanced"]["conversion_flags"] = copy.deepcopy(updated_gui_settings["globals"]["advanced"]["conversion_flags"])

    for section_key, section_data in gui_globals.items():
         if section_key != "general" and section_key in mapped_orpheus_updates["global"]:
             if isinstance(section_data, dict) and isinstance(mapped_orpheus_updates["global"].get(section_key), dict):
                  if section_key not in mapped_orpheus_updates["global"]: mapped_orpheus_updates["global"][section_key] = {}
                  for item_key, item_value in section_data.items():
                      if section_key == "advanced" and item_key == "conversion_flags":
                          continue
                      mapped_orpheus_updates["global"][section_key][item_key] = item_value
    platform_map_to_orpheus = { "BugsMusic": "bugs", "Nugs": "nugs", "SoundCloud": "soundcloud", "Tidal": "tidal", "Qobuz": "qobuz", "Deezer": "deezer", "Idagio": "idagio", "KKBOX": "kkbox", "Napster": "napster", "Beatport": "beatport", "Beatsource": "beatsource", "Musixmatch": "musixmatch", "Spotify": "spotify", "AppleMusic": "applemusic" }
    for gui_platform, creds in updated_gui_settings.get("credentials", {}).items():
        orpheus_platform = platform_map_to_orpheus.get(gui_platform)
        if orpheus_platform:
            if orpheus_platform not in mapped_orpheus_updates["modules"]: mapped_orpheus_updates["modules"][orpheus_platform] = {}
            mapped_orpheus_updates["modules"][orpheus_platform] = creds.copy()

    final_settings_to_save = deep_merge(existing_settings, mapped_orpheus_updates, keys_to_overwrite_if_dicts=["codec_conversions", "conversion_flags"])
    try:
        config_dir = os.path.dirname(CONFIG_FILE_PATH)
        if not os.path.exists(config_dir): os.makedirs(config_dir)
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f: json.dump(final_settings_to_save, f, indent=4, ensure_ascii=False, sort_keys=True)

        deep_merge(current_settings, updated_gui_settings, keys_to_overwrite_if_dicts=["codec_conversions", "conversion_flags"])
        if "globals" in updated_gui_settings and "advanced" in updated_gui_settings["globals"] and "conversion_flags" in updated_gui_settings["globals"]["advanced"]:
            clean_conversion_flags_from_ui = updated_gui_settings["globals"]["advanced"]["conversion_flags"]
            if "globals" not in current_settings: current_settings["globals"] = {}
            if "advanced" not in current_settings["globals"]: current_settings["globals"]["advanced"] = {}
            if "conversion_flags" not in current_settings["globals"]["advanced"]: current_settings["globals"]["advanced"]["conversion_flags"] = {}
            if "aac" in clean_conversion_flags_from_ui:
                current_settings["globals"]["advanced"]["conversion_flags"]["aac"] = clean_conversion_flags_from_ui["aac"].copy()
            if "flac" in clean_conversion_flags_from_ui:
                current_settings["globals"]["advanced"]["conversion_flags"]["flac"] = clean_conversion_flags_from_ui["flac"].copy()
            if "mp3" in clean_conversion_flags_from_ui:
                current_settings["globals"]["advanced"]["conversion_flags"]["mp3"] = clean_conversion_flags_from_ui["mp3"].copy()
        
        orpheus_instance = None
        initialize_orpheus()
        if show_confirmation:
            show_centered_messagebox("Settings Saved", "Settings have been saved successfully.", dialog_type="info")

        return True

    except IOError as e:
        log_file_path = os.path.join(os.getcwd(), 'error_log.txt')
        error_message = f"Error writing settings file '{CONFIG_FILE_PATH}':\\n{type(e).__name__}: {e}"
        full_traceback = traceback.format_exc()
        try:
            with open(log_file_path, 'a', encoding='utf-8') as log_f:
                log_f.write(f"--- Error during settings save (IOError) ---\\n")
                log_f.write(f"{error_message}\\n")
                log_f.write(f"Full Traceback:\\n{full_traceback}\\n")
                log_f.write("---------------------------------------------\\n")
            error_message_for_dialog = f"{error_message}\\n\\nSee 'error_log.txt' in the application folder for details."
        except Exception as log_e:
            error_message_for_dialog = f"{error_message}\\n\\n(Failed to write details to error_log.txt)"
        show_centered_messagebox("Settings Error", error_message_for_dialog, dialog_type="error")
        return False
    except Exception as e:
        log_file_path = os.path.join(os.getcwd(), 'error_log.txt')
        error_message = f"Unexpected error saving settings:\\n{type(e).__name__}: {e}"
        full_traceback = traceback.format_exc()
        try:
            with open(log_file_path, 'a', encoding='utf-8') as log_f:
                log_f.write(f"--- Error during settings save (Exception) ---\\n")
                log_f.write(f"{error_message}\\n")
                log_f.write(f"Full Traceback:\\n{full_traceback}\\n")
                log_f.write("----------------------------------------------\\n")
            error_message_for_dialog = f"{error_message}\\n\\nSee 'error_log.txt' in the application folder for details."
        except Exception as log_e:
            error_message_for_dialog = f"{error_message}\\n\\n(Failed to write details to error_log.txt)"
        show_centered_messagebox("Settings Error", error_message_for_dialog, dialog_type="error")
        return False

def handle_save_settings():
    """Handles the save settings button click."""
    global save_status_var, save_status_label, app

    try:
        save_attempt_successful = save_settings(show_confirmation=True)
        
        if 'app' in globals() and app and app.winfo_exists():
            app.after(50, _update_settings_tab_widgets)
        if save_attempt_successful:
            if 'save_status_var' in globals() and save_status_var:
                save_status_var.set("Settings saved.")
                if 'save_status_label' in globals() and save_status_label:
                    save_status_label.configure(text_color=("#00C851", "#00C851"))
            
            if 'update_search_platform_dropdown' in globals() and callable(update_search_platform_dropdown):
                app.after(100, update_search_platform_dropdown)
        else:
            if 'save_status_var' in globals() and save_status_var:
                save_status_var.set("Failed to save settings.")
                if 'save_status_label' in globals() and save_status_label:
                    save_status_label.configure(text_color=("#FF6B6B", "#FF6B6B"))

    except Exception as e:
        err_msg = f"Unexpected error during save handling:\\n{type(e).__name__}: {e}"
        if 'save_status_var' in globals() and save_status_var:
            save_status_var.set(f"Error handling save: {type(e).__name__}")
            if 'save_status_label' in globals() and save_status_label:
                save_status_label.configure(text_color=("#FF6B6B", "#FF6B6B"))
        show_centered_messagebox("Save Error", err_msg, dialog_type="error")
        import traceback
        traceback.print_exc(file=sys.__stderr__)
    finally:
        if 'app' in globals() and app and app.winfo_exists() and 'save_status_var' in globals() and save_status_var:
            app.after(4000, lambda: save_status_var.set("") if save_status_var else None)

def run_login_in_thread(orpheus, platform_name, gui_settings):
    """Target function for the login thread."""
    global output_queue, app
    is_frozen = getattr(sys, 'frozen', False)
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    queue_writer = QueueWriter(output_queue)
    dummy_stderr = DummyStderr()
    
    sys.stdout = queue_writer
    sys.stderr = dummy_stderr
    
    try:
        module_instance = orpheus.load_module(platform_name)
        if hasattr(module_instance, 'login'):
            if platform_name.lower() == 'beatport':
                string_io = io.StringIO()
                sys.stdout = string_io
                
                login_success = module_instance.login()
                sys.stdout = queue_writer
                
                captured_output = string_io.getvalue()
                if "Professional subscription detected" not in captured_output and captured_output:
                    output_queue.put(captured_output)
            else:
                 login_success = module_instance.login()

            if login_success:
                output_queue.put(f"{platform_name} login successful!\\n")
            else:
                output_queue.put(f"{platform_name} login failed. Check credentials or console for details.\\n")
        else:
            output_queue.put(f"The {platform_name} module does not have a login method.\\n")
            
    except Exception as e:
        output_queue.put(f"An error occurred during {platform_name} login: {e}\\n")
        if not is_frozen:
            traceback.print_exc(file=sys.__stderr__)
            
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        
        if 'app' in globals() and app.winfo_exists():
            app.after(0, lambda: _update_settings_tab_widgets())
            
def _update_settings_tab_widgets():
    global credential_tabs_config, current_settings, app
    
    for platform_name, tab_info in credential_tabs_config.items():
        if platform_name in loaded_credential_tabs:
            tab_frame = tab_info['frame']
            platform_creds = current_settings.get("credentials", {}).get(platform_name, {})
            
            for child in tab_frame.winfo_children():
                widget_name = getattr(child, '_w', str(child))
                
                for setting_key in tab_info['settings']:
                    entry_attr = f"{setting_key}_entry"
                    if hasattr(tab_frame, entry_attr):
                        entry = getattr(tab_frame, entry_attr)
                        if isinstance(entry, customtkinter.CTkEntry):
                            entry.unbind("<KeyRelease>")
                            
                            current_val = entry.get()
                            new_val = platform_creds.get(setting_key, '')
                            if current_val != new_val:
                                entry.delete(0, "end")
                                entry.insert(0, new_val)
                            
                            entry.bind("<KeyRelease>", lambda event, p=platform_name, k=setting_key, w=entry: _auto_save_credential_change(p, k, w))
                        break

def start_login_thread(platform_name):
    """Starts the login process in a separate thread."""
    global orpheus_instance, gui_settings, app
    
    if orpheus_instance:
        login_thread = threading.Thread(target=run_login_in_thread, args=(orpheus_instance, platform_name, gui_settings), daemon=True)
        login_thread.start()
    else:
        if not getattr(sys, 'frozen', False):
            print(f"Orpheus instance not ready, cannot start login for {platform_name}")
            
def _auto_save_path_change(*args):
    """Callback triggered when path_var_main changes. Updates in-memory setting AND saves to file."""
    global current_settings, path_var_main, settings_vars, save_status_var, app
    try:
        if 'path_var_main' not in globals() or not path_var_main: return

        new_path = path_var_main.get()
        if not new_path:
            return

        current_path_in_memory = current_settings.get("globals", {}).get("general", {}).get("output_path")
        settings_tab_var = settings_vars.get("globals", {}).get("general.output_path")
        current_path_in_settings_tab = settings_tab_var.get() if settings_tab_var else None
        should_save = False
        if new_path != current_path_in_memory:
            should_save = True
        elif settings_tab_var and new_path != current_path_in_settings_tab:
            should_save = True
        elif not settings_tab_var:
            should_save = True 

        if should_save:
            if "globals" not in current_settings: current_settings["globals"] = {}
            if "general" not in current_settings["globals"]: current_settings["globals"]["general"] = {}
            current_settings["globals"]["general"]["output_path"] = new_path
            if settings_tab_var:
                settings_tab_var.set(new_path)
            save_successful = save_settings(show_confirmation=False)
            if 'save_status_var' in globals() and save_status_var:
                status_msg = "Path saved." if save_successful else "Auto-save failed!"
                save_status_var.set(status_msg)
                if 'app' in globals() and app and app.winfo_exists():
                    app.after(3000, lambda var=save_status_var, msg=status_msg: var.set("") if var and var.get() == msg else None)
    except Exception as e:
        log_file_path = os.path.join(os.getcwd(), 'error_log.txt')
        err_msg = f"Error during automatic path save handling:\\n{type(e).__name__}: {e}"
        full_traceback = traceback.format_exc()

        try:
            with open(log_file_path, 'a', encoding='utf-8') as log_f:
                log_f.write(f"--- Error during _auto_save_path_change ---\\n")
                log_f.write(f"{err_msg}\\n")
                log_f.write(f"Full Traceback:\\n{full_traceback}\\n")
                log_f.write("---------------------------------------------\\n")
            error_message_for_dialog = f"{err_msg}\\n\\nSee 'error_log.txt' in the application folder for details."
        except Exception as log_e:
            error_message_for_dialog = f"{err_msg}\\n\\n(Failed to write details to error_log.txt)"
        if 'save_status_var' in globals() and save_status_var:
            save_status_var.set("Error during auto-save!")
            if 'app' in globals() and app and app.winfo_exists():
                 app.after(4000, lambda var=save_status_var: var.set("") if var else None)
        dialog_title = "Initialization Error" if "Initialization" in str(e) else "Auto-Save Error"
        show_centered_messagebox(dialog_title, error_message_for_dialog, dialog_type="error")

def handle_focus_in(widget):
    try:
        if not hasattr(widget, '_original_fg_color_stored'):
            original_color = widget.cget("fg_color")
            widget._original_fg_color_stored = original_color
        widget.configure(fg_color="#2B2B2B")
    except Exception as e:
        print(f"Error in handle_focus_in for {widget}: {e}")

def handle_focus_out(widget):
    try:
        if hasattr(widget, '_original_fg_color_stored'):
            original_color = widget._original_fg_color_stored
            widget.configure(fg_color=original_color)
    except Exception as e:
        print(f"Error in handle_focus_out for {widget}: {e}")

def show_centered_messagebox(title, message, dialog_type="info", parent=None):
    """Creates and displays a centered CTkToplevel message box."""
    global app
    if parent is None:
        parent = app if 'app' in globals() and app else None
        if parent is None:
             print("ERROR: Cannot show messagebox, main app window not available.")
             return

    dialog = customtkinter.CTkToplevel(parent); dialog.title(title); dialog.geometry("450x150"); dialog.resizable(False, False); dialog.attributes("-topmost", True); dialog.transient(parent)
    dialog.update_idletasks(); parent_width = parent.winfo_width(); parent_height = parent.winfo_height(); parent_x = parent.winfo_x(); parent_y = parent.winfo_y(); dialog_width = dialog.winfo_width(); dialog_height = dialog.winfo_height()
    center_x = parent_x + (parent_width // 2) - (dialog_width // 2); center_y = parent_y + (parent_height // 2) - (dialog_height // 2); dialog.geometry(f"+{center_x}+{center_y}")
    message_label = customtkinter.CTkLabel(dialog, text=message, wraplength=400, justify="left"); message_label.pack(pady=(20, 10), padx=20, expand=True, fill="both")
    ok_button = customtkinter.CTkButton(dialog, text="OK", command=dialog.destroy, width=100); ok_button.pack(pady=(0, 20)); ok_button.focus_set(); dialog.bind("<Return>", lambda event: ok_button.invoke())
    dialog.grab_set(); dialog.wait_window()
def _create_menu():
    global _context_menu, app, BUTTON_COLOR
    if _context_menu and _context_menu.winfo_exists(): return
    if 'app' not in globals() or not app: return
    _context_menu = customtkinter.CTkFrame(app, border_width=1, border_color="#565B5E")
    copy_button = customtkinter.CTkButton(_context_menu, text="Copy", command=copy_text, width=100, height=28, fg_color=BUTTON_COLOR, hover_color="#1F6AA5", text_color_disabled="gray", border_width=0); copy_button.pack(pady=(2, 1), padx=2, fill="x")
    paste_button = customtkinter.CTkButton(_context_menu, text="Paste", command=paste_text, width=100, height=28, fg_color=BUTTON_COLOR, hover_color="#1F6AA5", text_color_disabled="gray", border_width=0); paste_button.pack(pady=(1, 2), padx=2, fill="x")
    _context_menu.pack_forget()

def show_context_menu(event):
    global _context_menu, _target_widget, _hide_menu_binding_id, app
    _create_menu();
    if not _context_menu: print("Context menu: Failed to create menu frame."); return
    hide_context_menu()
    if 'app' not in globals() or not app: return
    try: target_at_coords = app.winfo_containing(event.x_root, event.y_root);
    except Exception as e: print(f"Context menu: Error finding widget at coords: {e}"); return
    if not target_at_coords: return
    intended_ctk_widget = None; temp_widget = target_at_coords; max_levels = 10; current_level = 0
    while temp_widget and temp_widget != app and current_level < max_levels:
        if isinstance(temp_widget, customtkinter.CTkEntry): intended_ctk_widget = temp_widget; break
        try: temp_widget = temp_widget.master
        except AttributeError: break
        current_level += 1
    if not intended_ctk_widget: return
    _target_widget = intended_ctk_widget
    can_copy = False; can_paste = False; has_selection = False; clipboard_has_text = False
    clipboard_content = ""
    try: clipboard_content = app.clipboard_get();
    except tkinter.TclError: pass
    except Exception as e: print(f"Context menu: Error checking clipboard - {e}")
    if isinstance(clipboard_content, str) and clipboard_content: clipboard_has_text = True
    try:
        try:
            if _target_widget._entry.selection_present(): has_selection = True
        except (tkinter.TclError, AttributeError): has_selection = False
        can_copy = has_selection or bool(_target_widget.get())
        state = _target_widget.cget("state") if hasattr(_target_widget, 'cget') else 'disabled'
        can_paste = state == "normal" and clipboard_has_text
    except Exception as e: print(f"Context menu: Error checking widget state/content: {e}")
    try:
        children = _context_menu.winfo_children()
        if len(children) >= 2 and isinstance(children[0], customtkinter.CTkButton) and isinstance(children[1], customtkinter.CTkButton):
            copy_btn = children[0]; paste_btn = children[1]
            copy_btn.configure(state="normal" if can_copy else "disabled"); paste_btn.configure(state="normal" if can_paste else "disabled")
        else: print("Context menu: Button widgets not found or invalid."); return
        menu_x = event.x_root - app.winfo_rootx() + 2; menu_y = event.y_root - app.winfo_rooty() + 2
        _context_menu.place(x=menu_x, y=menu_y); _context_menu.lift()
        if _hide_menu_binding_id is None: _hide_menu_binding_id = app.bind("<Button-1>", hide_context_menu, add=True)
    except tkinter.TclError as e: print(f"Context menu: TclError configuring/placing menu: {e}")
    except Exception as e: print(f"Context menu: Error configuring/placing menu: {e}")

def hide_context_menu(event=None):
    global _context_menu, _target_widget, _hide_menu_binding_id, app
    if 'app' not in globals() or not app: return
    if event and _context_menu and _context_menu.winfo_exists():
         try: click_widget = app.winfo_containing(event.x_root, event.y_root);
         except tkinter.TclError: pass
         except Exception as e: print(f"Error checking click location in hide_context_menu: {e}")
         else:
             if click_widget == _context_menu or click_widget in _context_menu.winfo_children(): return
    if _context_menu and _context_menu.winfo_exists(): _context_menu.place_forget()
    if _hide_menu_binding_id:
         try: app.unbind("<Button-1>", _hide_menu_binding_id)
         except tkinter.TclError: pass
         except Exception as e: print(f"Error unbinding hide_context_menu: {e}")
         finally: _hide_menu_binding_id = None
    _target_widget = None

def copy_text():
    global _target_widget, app
    if not isinstance(_target_widget, customtkinter.CTkEntry): hide_context_menu(); return
    if 'app' not in globals() or not app: return
    text_to_copy = ""
    try:
        try: text_to_copy = _target_widget._entry.selection_get()
        except tkinter.TclError: text_to_copy = _target_widget.get()
        if text_to_copy: app.clipboard_clear(); app.clipboard_append(text_to_copy); app.update()
    except tkinter.TclError as e: print(f"TclError during copy: {e}")
    except Exception as e: print(f"Error copying text: {e}")
    finally: hide_context_menu()

def paste_text():
    global _target_widget, app
    if not isinstance(_target_widget, customtkinter.CTkEntry): hide_context_menu(); return
    if 'app' not in globals() or not app: return
    try:
        state = 'disabled'
        try:
            if hasattr(_target_widget, 'cget') and callable(_target_widget.cget): state = _target_widget.cget("state")
        except Exception as e: print(f"Could not get widget state for paste check: {e}")
        if state != "normal": hide_context_menu(); return
        clipboard_text = app.clipboard_get(); tk_widget = _target_widget._entry
        try:
            if tk_widget.selection_present(): tk_widget.delete(tkinter.SEL_FIRST, tkinter.SEL_LAST)
        except tkinter.TclError: pass
        tk_widget.insert(tkinter.INSERT, clipboard_text)
    except tkinter.TclError as e:
        if "CLIPBOARD selection doesn't exist" not in str(e): print(f"TclError during paste: {e}")
    except Exception as e: print(f"Error pasting text: {e}", exc_info=True)
    finally: hide_context_menu()

def _clean_ansi_and_process_markers(text):
    """Clean ANSI color codes and process custom markers for GUI display"""
    import re
    platform_patterns = {
        r'Platform: \033\[96m(TIDAL)\033\[0m': 'tidal',
        r'Platform: \x1b\[96m(JioSaavn)\033\[0m': 'jiosaavn',
        r'Platform: \033\[96m(JioSaavn)\033\[0m': 'jiosaavn',
        r'Platform: \x1b\[96m(Jiosaavn)\033\[0m': 'jiosaavn',
        r'Platform: \033\[96m(Jiosaavn)\033\[0m': 'jiosaavn',
        r'Platform: \033\[91m(Apple Music)\033\[0m': 'apple music',
        r'Platform: \033\[92m(Beatport)\033\[0m': 'beatport',
        r'Platform: \033\[94m(Beatsource)\033\[0m': 'beatsource',
        r'Platform: \033\[94m(Napster)\033\[0m': 'napster',
        r'Platform: \033\[38;5;129m(Deezer)\033\[0m': 'deezer',
        r'Platform: \033\[34m(Qobuz)\033\[0m': 'qobuz',
        r'Platform: \033\[38;5;208m(SoundCloud)\033\[0m': 'soundcloud',
        r'Platform: \033\[32m(Spotify)\033\[0m': 'spotify',
        r'Platform: \033\[36m(KKBOX)\033\[0m': 'kkbox',
        r'Platform: \033\[35m(Idagio)\033\[0m': 'idagio',
        r'Platform: \033\[31m(Bugs)\033\[0m': 'bugs',
        r'Platform: \033\[31m(Nugs)\033\[0m': 'nugs',
    }
    for platform_pattern, platform_name in platform_patterns.items():
        display_name = SERVICE_DISPLAY_NAMES.get(platform_name, platform_name)
        text = re.sub(platform_pattern, rf'Platform: |PLATFORM_{platform_name.upper().replace(" ", "_")}|{display_name}|RESET|', text)
    gray_pattern = r'\033\[90m(.*?)\033\[0m'
    text = re.sub(gray_pattern, r'|GRAY|\1|RESET|', text)
    text = re.sub(r'(\d+/\d+\s+)(?:\033\[[0-9;]*m)?\+(?:\033\[[0-9;]*m)?(\s+)', r'\1✓\2', text)
    text = re.sub(r'(\d+/\d+\s+)(?:\033\[[0-9;]*m)?>(?:\033\[[0-9;]*m)?(\s+)', r'\1▶\2', text)
    text = re.sub(r'(\d+/\d+\s+)(\033\[91m)[xX](\033\[0m)(\s+)', r'\1\2❌\3\4', text)
    text = re.sub(r'(\d+/\d+\s+)(?:\033\[[0-9;]*m)?[xX](?:\033\[[0-9;]*m)?(\s+)', r'\1❌\2', text)
    text = re.sub(r'(\033\[91m)X(\033\[0m)', r'\1❌\2', text)
    yellow_pattern = r'\033\[33m(.*?)\033\[0m'
    def yellow_replacer(match):
        content = match.group(1)
        if "Track skipped" in content or "▶" in content or content.strip() == ">":
            return content
        return f'|YELLOW|{content}|RESET|'
    
    text = re.sub(yellow_pattern, yellow_replacer, text)
    red_pattern = r'\033\[91m(.*?)\033\[0m'
    text = re.sub(red_pattern, r'|RED|\1|RESET|', text)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    text = text.replace('|RESET|', '')
    
    return text

def _insert_text_with_links_and_platforms(text_content, error):
    """Helper function to insert text with URL and platform styling"""
    try:
        url_regex = r'https?://\S+|www\.\S+'
        service_names = '|'.join(re.escape(s) for s in SERVICE_COLORS.keys())
        service_regex = f'Platform: ({service_names})'
        url_matches = list(re.finditer(url_regex, text_content, re.IGNORECASE))
        platform_matches = list(re.finditer(service_regex, text_content, re.IGNORECASE))
        all_matches = []
        for match in url_matches:
            all_matches.append((match.start(), match.end(), 'url', match.group()))
        for match in platform_matches:
            all_matches.append((match.start(), match.end(), 'platform', match.group()))
        all_matches.sort(key=lambda x: x[0])
        
        if all_matches:
            last_end = 0
            for start, end, match_type, matched_text in all_matches:
                if start > last_end:
                    text_before = text_content[last_end:start]
                    tag = "error" if error else "normal"
                    log_textbox.insert("end", text_before, (tag,))
                if match_type == 'url':
                    log_textbox.insert("end", matched_text, ("hyperlink",))
                elif match_type == 'platform':
                    prefix = "Platform: "
                    service_name = matched_text.replace(prefix, "")
                    service_tag = f"service_{service_name.replace(' ', '_')}"
                    log_textbox.insert("end", prefix)
                    log_textbox.insert("end", service_name, (service_tag,))
                
                last_end = end
            if last_end < len(text_content):
                remaining_text = text_content[last_end:]
                tag = "error" if error else "normal"
                log_textbox.insert("end", remaining_text, (tag,))
        else:
            tag = "error" if error else "normal"
            log_textbox.insert("end", text_content, (tag,))
    except Exception as e:
        tag = "error" if error else "normal"
        log_textbox.insert("end", text_content, (tag,))

def log_to_textbox(msg, error=False):
    """
    Simplified log function that relies on clean CLI output.
    Only handles basic styling: colors, emojis, hyperlinks, and platform coloring.
    """
    global _last_message_was_empty, log_textbox, log_scrollbar, app
    
    try:
        if 'log_textbox' not in globals() or not log_textbox or not log_textbox.winfo_exists(): 
            return
        if any(filter_text in msg for filter_text in [
            "Librespot:Session - Failed reading packet!",
            "Librespot authentication failed during session creation: BadCredentials",
            "Failed to create Librespot session from existing OAuth credentials",
            "Attempting token refresh...",
            "Token refresh failed",
            "Attempting login via",
            "Login successful, obtained session ID",
            "Attempting authorization via",
            "Authorization successful, obtained code",
            "Exchanging code for token via",
            "Token exchange successful",
            "Initializing async downloads...",
            "Set Windows ProactorEventLoopPolicy",
            "Starting async event loop...",
            "Creating aiohttp session...",
            "aiohttp session created successfully"
        ]) or any(pattern in msg for pattern in [
            "Download speed: ",
            "Download time: "
        ]):
            return

        content_to_insert = _clean_ansi_and_process_markers(msg)
        is_current_empty = not content_to_insert.strip()
        if is_current_empty and _last_message_was_empty: 
            return
        _last_message_was_empty = is_current_empty
        
        if not content_to_insert:
            return
            
        log_textbox.configure(state="normal")
        try:
            log_textbox.tag_configure("error", foreground="#FF4444")
            log_textbox.tag_configure("detail_text", foreground="#A0A0A0")
            log_textbox.tag_configure("normal", foreground="")
            log_textbox.tag_configure("hyperlink", foreground="royal blue", underline=True)
            log_textbox.tag_configure("emoji_success", foreground="#00C851")
            log_textbox.tag_configure("emoji_error", foreground="#FF4444")
            log_textbox.tag_configure("emoji_warning", foreground="#CCA700")
            log_textbox.tag_configure("color_red", foreground="#FF4444")
            log_textbox.tag_configure("color_yellow", foreground="#FFA500")
            log_textbox.tag_configure("color_gray", foreground="#A0A0A0")
            for service, color in SERVICE_COLORS.items():
                log_textbox.tag_configure(f"service_{service.replace(' ', '_')}", foreground=color)
                log_textbox.tag_configure(f"platform_{service.replace(' ', '_')}", foreground=color)
                
            log_textbox.tag_bind("hyperlink", "<Enter>", lambda e: log_textbox.config(cursor="hand2"))
            log_textbox.tag_bind("hyperlink", "<Leave>", lambda e: log_textbox.config(cursor=""))
            log_textbox.tag_bind("hyperlink", "<Button-1>", _on_hyperlink_click)
        except: 
            pass
        emoji_processed = False
        for emoji, tag in [("✅", "emoji_success"), ("❌", "emoji_error"), ("▶", "emoji_warning"), ("✓", "emoji_success")]:
            if emoji in content_to_insert:
                parts = content_to_insert.split(emoji)
                for i, part in enumerate(parts):
                    if part:
                        if "|RED|" in part or "|YELLOW|" in part or "|GRAY|" in part or "|PLATFORM_" in part:
                            import re
                            try:
                                color_parts = []
                                current_pos = 0
                                color_markers = re.finditer(r'\|(RED|YELLOW|GRAY|PLATFORM_[A-Z_]+)\|([^|]*?)(?=\||$)', part)
                                
                                for marker in color_markers:
                                    if marker.start() > current_pos:
                                        text_before = part[current_pos:marker.start()]
                                        if text_before:
                                            _insert_text_with_links_and_platforms(text_before, error)
                                    
                                    color = marker.group(1).lower()
                                    text = marker.group(2)
                                    if color == 'red':
                                        log_textbox.insert("end", text, ("color_red",))
                                    elif color == 'yellow':
                                        log_textbox.insert("end", text, ("color_yellow",))
                                    elif color == 'gray':
                                        log_textbox.insert("end", text, ("color_gray",))
                                    elif color.startswith('platform_'):
                                        platform_tag = color
                                        log_textbox.insert("end", text, (platform_tag,))
                                    current_pos = marker.end()
                                
                                if current_pos < len(part):
                                    remaining_text = part[current_pos:]
                                    if remaining_text:
                                        _insert_text_with_links_and_platforms(remaining_text, error)
                            except:
                                _insert_text_with_links_and_platforms(part, error)
                        else:
                            _insert_text_with_links_and_platforms(part, error)
                    
                    if i < len(parts) - 1:
                        log_textbox.insert("end", emoji, (tag,))
                
                emoji_processed = True
                break
        
        if not emoji_processed:
            if "=== + " in content_to_insert:
                parts = content_to_insert.split("=== + ")
                log_textbox.insert("end", parts[0] + "=== ")
                log_textbox.insert("end", "✅", ("emoji_success",))
                if len(parts) > 1:
                    log_textbox.insert("end", " " + parts[1])
            elif "=== X " in content_to_insert:
                parts = content_to_insert.split("=== X ")
                log_textbox.insert("end", parts[0] + "=== ")
                log_textbox.insert("end", "❌", ("emoji_error",))
                if len(parts) > 1:
                    log_textbox.insert("end", " " + parts[1])
            elif "=== > " in content_to_insert:
                parts = content_to_insert.split("=== > ")
                log_textbox.insert("end", parts[0] + "=== ")
                log_textbox.insert("end", "▶", ("emoji_warning",))
                if len(parts) > 1:
                    log_textbox.insert("end", " " + parts[1])
            else:
                import re
                try:
                    if "|RED|" in content_to_insert or "|YELLOW|" in content_to_insert or "|GRAY|" in content_to_insert or "|PLATFORM_" in content_to_insert:
                        parts = []
                        current_pos = 0
                        color_markers = re.finditer(r'\|(RED|YELLOW|GRAY|PLATFORM_[A-Z_]+)\|([^|]*?)(?=\||$)', content_to_insert)
                        
                        for marker in color_markers:
                            if marker.start() > current_pos:
                                parts.append(('text', content_to_insert[current_pos:marker.start()]))
                            color = marker.group(1).lower()
                            text = marker.group(2)
                            parts.append(('color', color, text))
                            current_pos = marker.end()
                        if current_pos < len(content_to_insert):
                            parts.append(('text', content_to_insert[current_pos:]))
                        for part in parts:
                            if part[0] == 'text':
                                _insert_text_with_links_and_platforms(part[1], error)
                                    
                            elif part[0] == 'color':
                                color = part[1]
                                text = part[2]
                                if color == 'red':
                                    log_textbox.insert("end", text, ("color_red",))
                                elif color == 'yellow':
                                    log_textbox.insert("end", text, ("color_yellow",))
                                elif color == 'gray':
                                    log_textbox.insert("end", text, ("color_gray",))
                                elif color.startswith('platform_'):
                                    platform_tag = color
                                    log_textbox.insert("end", text, (platform_tag,))
                                else:
                                    tag = "error" if error else "normal"
                                    log_textbox.insert("end", text, (tag,))
                    
                    else:
                        _insert_text_with_links_and_platforms(content_to_insert, error)
                            
                except re.error as regex_err:
                    print(f"[Debug] Regex error in log_to_textbox: {regex_err}")
                    tag = "error" if error else "normal"
                    log_textbox.insert("end", content_to_insert, (tag,))
            try:
                yview_info = log_textbox.yview()
                is_at_bottom = yview_info[1] >= 0.95
                
                if is_at_bottom:
                    log_textbox.yview_moveto(1.0)
                    log_textbox.update()
            except:
                pass
                
            log_textbox.configure(state="disabled")
            def delayed_scroll():
                try:
                    if log_textbox and log_textbox.winfo_exists():
                        yview_info = log_textbox.yview()
                        is_at_bottom = yview_info[1] >= 0.95
                        
                        if is_at_bottom:
                            log_textbox.yview_moveto(1.0)
                            log_textbox.update_idletasks()
                except:
                    pass
            
            if 'app' in globals() and app and app.winfo_exists():
                app.after(10, delayed_scroll)
        try:
            if 'app' in globals() and app and app.winfo_exists() and 'log_scrollbar' in globals() and log_scrollbar:
                app.after(0, lambda: _check_and_toggle_text_scrollbar(log_textbox, log_scrollbar))
        except: 
            pass
            
    except NameError: 
        print("[Debug] log_to_textbox: NameError (likely widget not ready)")
    except tkinter.TclError as e: 
        print(f"TclError in log_to_textbox (widget destroyed?): {e}")
    except Exception as e:
        print(f"Error in log_to_textbox: {e}")
        try:
            if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists():
                log_textbox.configure(state="disabled")
        except: 
            pass

_has_shown_unavailable_warning = False

def update_log_area():
    global output_queue, app, _has_shown_unavailable_warning, _current_download_context
    try:
        messages_processed = 0
        max_messages_per_update = 5
        start_time = time.time()
        max_processing_time = 0.02
        
        while messages_processed < max_messages_per_update:
            try: 
                msg = output_queue.get_nowait()
                msg_strip = msg.strip()
                if msg_strip.startswith('[Apple Music]'):
                    continue
                if 'Professional subscription detected' in msg_strip or 'allowing high and lossless quality' in msg_strip:
                    continue
                if 'No tracks were deferred due to rate limiting' in msg_strip:
                    continue
                if 'Cover resized from' in msg_strip and 'MB to' in msg_strip and 'px)' in msg_strip:
                    continue
                if ('All ' in msg_strip and ' tracks available!' in msg_strip and
                    ('downloaded' in msg_strip or 'already existed' in msg_strip or 'failed' in msg_strip)):
                    continue
                if (' tracks processed!' in msg_strip and
                    ('downloaded' in msg_strip or 'already existed' in msg_strip or 'failed' in msg_strip)):
                    continue
                if msg_strip.startswith('=== Downloading track'):
                    _has_shown_unavailable_warning = False
                if 'This song is unavailable' in msg_strip:
                    if not _has_shown_unavailable_warning:
                        try:
                            recent_content = log_textbox.get("end-30l", "end")
                            if ("=== Downloading album" in recent_content and
                                "=== Downloading playlist" not in recent_content):
                                log_to_textbox("       This song is unavailable.\n")
                            else:
                                log_to_textbox("       This song is unavailable.\n")
                        except:
                            log_to_textbox("       This song is unavailable.\n")
                        _has_shown_unavailable_warning = True
                    continue
                if 'Failed after 3 attempts' in msg_strip and msg_strip.startswith('[ERROR]'):
                    log_to_textbox("[ERROR] Failed after 3 attempts.\n", error=True)
                    continue
                if 'Track is not from the correct artist, skipping' in msg_strip:
                    log_to_textbox("Track is not from the correct artist, skipping\n")
                    continue
                if 'Pausing for' in msg_strip and 'seconds before next download attempt' in msg_strip:
                    log_to_textbox(msg)
                    log_to_textbox("\n")
                    continue
                if '[CRITICAL]' in msg_strip and 'Librespot:Session' in msg_strip and 'Failed reading packet!' in msg_strip:
                    continue
                if 'Could not get track info for' in msg_strip:
                    continue
                if 'Download stop requested...' in msg_strip:
                    log_to_textbox("|GRAY|Download stop requested... Please wait.|RESET|\n")
                    continue
                if 'tracks in playlist... Please wait.' in msg_strip:
                    fixed_message = msg_strip.lstrip()
                    log_to_textbox(f"{fixed_message}\n")
                    continue
                if msg_strip.startswith('Fetching ') and 'Fetching data. Please wait...' in msg_strip:
                    parts = msg_strip.split('Fetching data. Please wait...')
                    if len(parts) >= 2:
                        log_to_textbox(f"Fetching data. Please wait...\n")
                        continue
                import re
                if re.search(r'Fetching \d+/\d+', msg_strip):
                    if '===' in msg_strip:
                        cleaned_msg = re.sub(r'Fetching \d+/\d+', '', msg_strip)
                        cleaned_msg = cleaned_msg.strip()
                        if cleaned_msg:
                            log_to_textbox(f"{cleaned_msg}\n")
                        continue
                    else:
                        continue
                if 'Processing' in msg_strip and 'standalone tracks...' in msg_strip and 'Artist Progress:' in msg_strip:
                    log_to_textbox(f"{msg}\n")
                    continue
                if 'Spotify authentication error during track download' in msg_strip or \
                   ('Download attempt' in msg_strip and 'failed. Retrying in' in msg_strip):
                    cleaned_message = msg_strip
                    if 'Spotify authentication error during track download' in msg_strip and 'Failed fetching audio key!' in msg_strip:
                        cleaned_message = msg_strip.split('Failed fetching audio key!')[0] + 'Failed fetching audio key!'
                    indented_message = f"       {cleaned_message}\n"
                    log_to_textbox(indented_message)
                    continue
                if '=== ✅ Track completed ===' in msg_strip:
                    log_to_textbox(msg)
                    continue
                if ('=== ✅ Album completed ===' in msg_strip or
                    '=== ✅ Track completed ===' in msg_strip or
                    '=== ✅ Playlist completed ===' in msg_strip or
                    '=== ✅ Artist completed ===' in msg_strip):
                    try:
                        next_msg = output_queue.get_nowait()
                        if next_msg.strip():
                            output_queue.put(next_msg)
                    except queue.Empty:
                        pass
                    continue
                is_error = msg_strip.startswith(('[WARNING]', '[ERROR]'))
                if is_error and (('Download attempt' in msg_strip and ('failed' in msg_strip or 'Retrying' in msg_strip)) or 
                                'Failed after 3 attempts' in msg_strip):
                    log_to_textbox(f"       {msg_strip}\n", error=is_error)
                else:
                    log_to_textbox(msg, error=is_error)

                messages_processed += 1
                if time.time() - start_time > max_processing_time:
                    break
            except queue.Empty: 
                break
            except Exception as e: 
                print(f"Error processing message from queue: {e}")
                break
        if 'app' in globals() and app and app.winfo_exists():
            app.update_idletasks()
            try:
                if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists():
                    yview_info = log_textbox.yview()
                    is_at_bottom = yview_info[1] >= 0.95
                    
                    if is_at_bottom:
                        log_textbox.yview_moveto(1.0)
            except:
                pass
            
    except Exception as e: 
        print(f"[ERROR] Exception in update_log_area loop: {type(e).__name__}: {e}")
    finally:
        try:
            if 'app' in globals() and app and app.winfo_exists():
                queue_size = output_queue.qsize() if output_queue else 0
                update_interval = min(100, max(25, queue_size * 2))
                app.after(update_interval, update_log_area)
            else:
                print("[Debug] update_log_area: 'app' not found or destroyed, stopping log polling.")
        except NameError: 
            print("[Debug] update_log_area: NameError accessing 'app'.")
        except Exception as e_sched: 
            print(f"[Error] Could not reschedule update_log_area: {e_sched}")

def clear_output_log():
    global log_textbox
    try:
        if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists():
            log_textbox.configure(state='normal'); log_textbox.delete('1.0', tkinter.END); log_textbox.configure(state='disabled')
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing log (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing log: {e}")

def browse_output_path(path_variable):
    directory = tkinter.filedialog.askdirectory(initialdir=path_variable.get())
    if directory: path_variable.set(directory)

def clear_url_entry():
    global url_entry
    try:
        if 'url_entry' in globals() and url_entry and url_entry.winfo_exists():
            url_entry.delete(0, tkinter.END)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing URL entry (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing URL entry: {e}")

def open_download_path():
    global path_var_main
    try:
        if 'path_var_main' not in globals() or not path_var_main: return

        path_to_open = path_var_main.get()
        if os.path.isdir(path_to_open):
            try:
                if platform.system() == "Windows": os.startfile(path_to_open)
                elif platform.system() == "Darwin": subprocess.Popen(["open", path_to_open])
                else: subprocess.Popen(["xdg-open", path_to_open])
            except Exception as e: show_centered_messagebox("Error", f"Could not open path: {e}", dialog_type="error")
        else: show_centered_messagebox("Warning", "Output path does not exist.", dialog_type="warning")
    except NameError: pass
    except Exception as e: print(f"Error opening download path: {e}")

def clear_search_entry():
    global search_entry
    try:
        if 'search_entry' in globals() and search_entry and search_entry.winfo_exists():
            search_entry.delete(0, tkinter.END)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing search entry (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing search entry: {e}")

def set_ui_state_downloading(is_downloading):
    global download_button, stop_button, progress_bar, app
    def _update_state():
        download_state = "disabled" if is_downloading else "normal"; stop_state = "normal" if is_downloading else "disabled"
        try:
            if 'download_button' in globals() and download_button and download_button.winfo_exists():
                 download_button.configure(state=download_state)
            if 'stop_button' in globals() and stop_button and stop_button.winfo_exists():
                 stop_button.configure(state=stop_state)
            if 'progress_bar' in globals() and progress_bar and progress_bar.winfo_exists():
                if is_downloading: progress_bar.configure(mode="indeterminate"); progress_bar.start()
                else: progress_bar.stop(); progress_bar.set(0); progress_bar.configure(mode="determinate")
        except NameError: print("[Debug] NameError setting download UI state.")
        except tkinter.TclError as e: print(f"TclError setting download UI state (widget destroyed?): {e}")
        except Exception as e: print(f"Error setting download UI state: {e}")
    try:
        if 'app' in globals() and app and app.winfo_exists():
            app.after(0, _update_state)
        else: print("[Debug] 'app' not found for download UI state update.")
    except NameError: print("[Debug] NameError accessing 'app' for download UI state update.")
    except Exception as e: print(f"Error scheduling download UI state update: {e}")

def set_ui_state_searching(is_searching):
    global search_button, clear_search_button, platform_combo, type_combo, search_entry, search_progress_bar, app
    def _update_state():
        state = "disabled" if is_searching else "normal"; combo_state = "disabled" if is_searching else "readonly"
        try:
            if 'search_button' in globals() and search_button and search_button.winfo_exists(): search_button.configure(state=state)
            if 'clear_search_button' in globals() and clear_search_button and clear_search_button.winfo_exists(): clear_search_button.configure(state=state)
            if 'platform_combo' in globals() and platform_combo and platform_combo.winfo_exists(): platform_combo.configure(state=combo_state)
            if 'type_combo' in globals() and type_combo and type_combo.winfo_exists(): type_combo.configure(state=combo_state)
            if 'search_entry' in globals() and search_entry and search_entry.winfo_exists(): search_entry.configure(state=state)
            if 'search_progress_bar' in globals() and search_progress_bar and search_progress_bar.winfo_exists():
                if is_searching: search_progress_bar.configure(mode="indeterminate"); search_progress_bar.start()
                else: search_progress_bar.stop(); search_progress_bar.set(0); search_progress_bar.configure(mode="determinate")
        except NameError: pass
        except tkinter.TclError as e: print(f"TclError setting search UI state (widget destroyed?): {e}")
        except Exception as e: print(f"Error setting search UI state: {e}")
    try:
        if 'app' in globals() and app and app.winfo_exists():
            app.after(0, _update_state)
        else: print("[Debug] 'app' not found for search UI state update.")
    except NameError: pass
    except Exception as e: print(f"Error scheduling search UI state update: {e}")

def _check_and_toggle_scrollbar(tree_widget, scrollbar_widget):
    if not tree_widget or not tree_widget.winfo_exists() or not scrollbar_widget or not scrollbar_widget.winfo_exists(): return
    try:
        tree_widget.update_idletasks(); yview_info = tree_widget.yview()
        if yview_info[1] < 1.0 and tree_widget.get_children():
            if not scrollbar_widget.winfo_ismapped(): scrollbar_widget.grid(row=0, column=1, sticky='ns', pady=3, padx=(0,5))
        else:
             if scrollbar_widget.winfo_ismapped(): scrollbar_widget.grid_remove()
    except Exception as e:
        if isinstance(e, tkinter.TclError): pass
        else: print(f"Error checking/toggling scrollbar: {e}")

def _check_and_toggle_text_scrollbar(text_widget, scrollbar_widget):
    """Check if text widget needs scrollbar and show/hide accordingly"""
    if not text_widget or not text_widget.winfo_exists() or not scrollbar_widget or not scrollbar_widget.winfo_exists():         
        return
    try:        
        text_widget.update_idletasks()
        first, last = text_widget.yview()
        is_content_fully_visible = (last - first) >= (1.0 - 1e-9)

        if not is_content_fully_visible:
            if not scrollbar_widget.winfo_ismapped():
                scrollbar_widget.grid(row=0, column=1, sticky='ns') 
                text_widget.update_idletasks()
        else:            
            if scrollbar_widget.winfo_ismapped():                 
                scrollbar_widget.grid_remove()
                text_widget.update_idletasks()
    except Exception as e:
        if isinstance(e, tkinter.TclError):             
            pass
        else: 
            print(f"Error checking/toggling text scrollbar: {e}")

class QueueWriter(io.TextIOBase):
    def __init__(self, queue_instance, media_type=None):
        self.queue = queue_instance
        self.buffer = ''
        self.media_type = media_type
        self.in_track_context = False
        self.completed_track_count = 0
        self.total_tracks = 0
        self.in_concurrent_download = False
        
        self.MESSAGES_TO_INDENT = [
            "Downloading encrypted stream...",
            "Getting decryption key...",
            "Processing with legacy remux...",
            "Applying Apple Music metadata...",
        ]

    def _is_progress_bar_line(self, line):
        """Check if a line is a tqdm progress bar that should be filtered out."""
        stripped = line.strip()
        if not stripped:
            return False
        import re
        if re.search(r'\d+%\|.*\|.*\[.*[KMGT]?B/s.*\]', stripped):
            return True
        if ('|' in stripped and
            re.search(r'\d+\.\d+[KMGT]?B/\d+\.\d+[KMGT]?B', stripped) and
            re.search(r'\[.*[KMGT]?B/s.*\]', stripped)):
            return True
        if re.match(r'^\s*\d+%\|[#\s\-\.]*\|', stripped):
            return True

        return False

    def write(self, msg):
        if '\r' in msg:
            parts = msg.split('\r')
            filtered_parts = []
            for part in parts:
                if not self._is_progress_bar_line(part):
                    filtered_parts.append(part)
            if filtered_parts:
                msg = filtered_parts[-1]
            else:
                return len(msg)


        self.buffer += msg
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                if self._is_progress_bar_line(line):
                    continue
                global current_settings
                is_debug_mode = current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False)
                if not is_debug_mode and "[gamdl AppleMusicApi DEBUG]" in line:
                    continue
                import re
                line = re.sub(r'(\d+/\d+\s+)\+(\s+)', r'\1✓\2', line)
                line = re.sub(r'(\d+/\d+\s+)>(\s+)', r'\1▶\2', line)
                line = re.sub(r'(\d+/\d+\s+)x(\s+)', r'\1✗\2', line)
                stripped_line = line.lstrip()
                if ("=== ✅" in line or "=== ❌" in line or
                    "Track completed" in line or "Track failed" in line or
                    "Album completed" in line or "Album failed" in line or "Album skipped" in line):
                    if "=== ✅" in line:
                        completion_msg = line[line.find("=== ✅"):]
                    elif "=== ❌" in line:
                        completion_msg = line[line.find("=== ❌"):]
                    elif "=== ▶" in line:
                        completion_msg = line[line.find("=== ▶"):]
                    else:
                        completion_msg = stripped_line
                    self.queue.put(completion_msg.strip() + '\n')
                    continue

                if ("=== ✅ Album completed ===" in stripped_line or 
                    "=== ✅ Playlist completed ===" in stripped_line or
                    "=== ✅ Artist completed ===" in stripped_line):
                    self.in_concurrent_download = False
                    self.completed_track_count = 0
                if (not self.media_type or self.media_type == DownloadTypeEnum.track) and (
                    stripped_line.startswith("Artists:") or
                    stripped_line.startswith("Release year:") or
                    stripped_line.startswith("Duration:") or
                    stripped_line.startswith("Platform:") or
                    stripped_line.startswith("Codec:") or
                    stripped_line.startswith("Downloading audio...") or
                    stripped_line.startswith("Downloading artwork...") or
                    stripped_line.startswith("Tagging file...") or
                    stripped_line.startswith("Spotify API error during track download:") or
                    stripped_line.startswith("[ERROR]") or
                    stripped_line.startswith("No download info available")):
                    self.queue.put("       " + stripped_line + '\n')
                    continue

                if self.media_type == DownloadTypeEnum.artist or self.media_type == DownloadTypeEnum.album or self.media_type == DownloadTypeEnum.playlist:
                    import re
                    if "=== ✅ Album completed ===" in line:
                        line = "=== ✅ Album completed ==="
                    elif re.match(r'^\s*\d+/\d+\s+[▶✓❌⚠]', line):
                        if self.media_type == DownloadTypeEnum.artist:
                            stripped_content = line.strip()
                            line = "       " + stripped_content
                        elif self.media_type == DownloadTypeEnum.album:
                            stripped_content = line.strip()
                            line = "       " + stripped_content
                        elif self.media_type == DownloadTypeEnum.playlist:
                            stripped_content = line.strip()
                            line = "       " + stripped_content
                        elif self.in_concurrent_download and self.total_tracks > 0:
                            self.completed_track_count += 1
                            match = re.match(r'^\s*\d+/\d+\s+([▶✓❌⚠])\s*(.*)', line)
                            if match:
                                status_symbol = match.group(1)
                                track_name = match.group(2)
                                total_digits = len(str(self.total_tracks))
                                formatted_line = f"{self.completed_track_count:0{total_digits}d}/{self.total_tracks} {status_symbol} {track_name}"
                                line = formatted_line
                            else:
                                line = stripped_line
                        else:
                            line = stripped_line
                    elif ("Processing album track" in stripped_line or
                        "-> Album Track" in stripped_line or
                        "Processing album" in stripped_line or
                        "Fetching SoundCloud album metadata" in stripped_line or
                        "Downloading album cover" in stripped_line or
                        ("=== Track" in stripped_line and ("downloaded ===" in stripped_line or "completed ===" in stripped_line)) or
                        ("=== Downloading album" in stripped_line) or
                        ("=== Downloading track" in stripped_line) or
                        ("=== ❌ Album" in stripped_line and "cancelled ===" in stripped_line)):
                        line = stripped_line
                    if self.media_type == DownloadTypeEnum.artist:
                        if "=== Downloading track" in stripped_line:
                            self.in_track_context = True
                        elif "=== Downloading album" in stripped_line:
                            self.in_track_context = False
                        elif "=== ✅ Track completed ===" in stripped_line:
                            self.in_track_context = False
                    if self.media_type == DownloadTypeEnum.artist and self.in_track_context and (
                        stripped_line.startswith("Artists:") or
                        stripped_line.startswith("Release year:") or
                        stripped_line.startswith("Duration:") or
                        stripped_line.startswith("Platform:") or
                        stripped_line.startswith("Codec:") or
                        stripped_line.startswith("Downloading audio...") or
                        stripped_line.startswith("Downloading artwork...") or
                        stripped_line.startswith("Tagging file...") or
                        stripped_line.startswith("Track file already exists") or
                        "This song is unavailable" in stripped_line or
                        stripped_line.startswith("Spotify API error during track download:") or
                        stripped_line.startswith("[ERROR]") or
                        stripped_line.startswith("No download info available") or
                        any(msg in stripped_line for msg in self.MESSAGES_TO_INDENT)):
                        line = "       " + stripped_line
                    elif self.media_type == DownloadTypeEnum.artist and not self.in_track_context and (
                        stripped_line.startswith("Artist:") or
                        stripped_line.startswith("Year:") or
                        stripped_line.startswith("Duration:") or
                        stripped_line.startswith("Number of tracks:") or
                        stripped_line.startswith("Platform:") or
                        stripped_line.startswith("Skipping unrecognized album item") or
                        (stripped_line.startswith("Using ") and "concurrent downloads" in stripped_line)):
                        line = "       " + stripped_line
                    elif self.media_type == DownloadTypeEnum.artist and not self.in_track_context and (
                        (stripped_line.startswith("Using ") and "sequential downloads" in stripped_line)):
                        line = "       " + stripped_line + "\n"
                    elif self.media_type == DownloadTypeEnum.artist and (
                        stripped_line.startswith("Track ") and ("Pass" in stripped_line)):
                        line = "       " + stripped_line
                    elif line.startswith('        ') and not line.startswith('         ') and not line.startswith('=== '):
                        if not (self.media_type == DownloadTypeEnum.artist and re.match(r'^\s*\d+/\d+\s+[▶✓❌⚠]', line)):
                            line = line[1:]
                elif self.media_type == DownloadTypeEnum.playlist:
                    stripped_line = line.lstrip()
                    if any(msg in stripped_line for msg in self.MESSAGES_TO_INDENT):
                        line = "        " + stripped_line
                    elif "=== Track" in stripped_line and ("downloaded ===" in stripped_line or "completed ===" in stripped_line):
                        line = stripped_line
                    elif (stripped_line.startswith("Using ") and ("sequential downloads" in stripped_line or "concurrent downloads" in stripped_line)):
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Track ") and ("Pass" in stripped_line)):
                        line = "       " + stripped_line
                    elif line.startswith('        ') and not line.startswith('         ') and not line.startswith('=== '):
                        contains_apple_music_msg = any(msg in line for msg in self.MESSAGES_TO_INDENT)
                        if not contains_apple_music_msg:
                            line = line[1:]
                elif self.media_type == DownloadTypeEnum.album:
                    stripped_line = line.lstrip()
                    import re
                    if re.match(r'^\d+/\d+\s+[▶✓❌⚠]', stripped_line):
                        line = "       " + stripped_line
                    elif "=== Downloading track" in stripped_line:
                        line = stripped_line
                    elif "=== Track" in stripped_line and ("downloaded ===" in stripped_line or "completed ===" in stripped_line):
                        line = stripped_line
                    elif "This song is unavailable" in stripped_line:
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Artists:") or
                          stripped_line.startswith("Release year:") or
                          stripped_line.startswith("Duration:") or
                          stripped_line.startswith("Platform:") or
                          stripped_line.startswith("Codec:") or
                          stripped_line.startswith("Downloading audio...") or
                          stripped_line.startswith("Downloading artwork...") or
                          stripped_line.startswith("Tagging file...") or
                          stripped_line.startswith("Spotify API error during track download:") or
                          stripped_line.startswith("[ERROR]") or
                          stripped_line.startswith("No download info available") or
                          (len(line) - len(line.lstrip()) >= 16 and any(detail in stripped_line for detail in [
                              "Artists:", "Release year:", "Duration:", "Platform:", "Codec:",
                              "Downloading audio...", "Downloading artwork...", "Tagging file..."
                          ]))):
                        if len(line) - len(line.lstrip()) >= 16:
                            line = line
                        else:
                            line = "       " + stripped_line
                    elif any(msg in stripped_line for msg in self.MESSAGES_TO_INDENT):
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Artist:") or
                          stripped_line.startswith("Year:") or
                          stripped_line.startswith("Number of tracks:")):
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Using ") and ("sequential downloads" in stripped_line or "concurrent downloads" in stripped_line)):
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Track ") and ("Pass" in stripped_line)):
                        line = "       " + stripped_line
                    elif line.startswith('        ') and not line.startswith('         ') and not line.startswith('=== '):
                        line = line[1:]
                elif self.media_type == DownloadTypeEnum.track:
                    stripped_line = line.lstrip()
                    if "=== Downloading track" in stripped_line:
                        line = stripped_line
                    elif "=== Track" in stripped_line and ("downloaded ===" in stripped_line or "completed ===" in stripped_line):
                        line = stripped_line
                    elif any(msg in stripped_line for msg in self.MESSAGES_TO_INDENT):
                        line = "       " + stripped_line
                    elif "This song is unavailable" in stripped_line:
                        line = "       " + stripped_line
                    elif (stripped_line.startswith("Artists:") or
                          stripped_line.startswith("Release year:") or
                          stripped_line.startswith("Duration:") or
                          stripped_line.startswith("Platform:") or
                          stripped_line.startswith("Codec:") or
                          stripped_line.startswith("Downloading audio...") or
                          stripped_line.startswith("Downloading artwork...") or
                          stripped_line.startswith("Tagging file...") or
                          stripped_line.startswith("Spotify API error during track download:") or
                          stripped_line.startswith("[ERROR]") or
                          stripped_line.startswith("No download info available")):
                        line = "       " + stripped_line
                    elif line.startswith('        ') and not line.startswith('         ') and not line.startswith('=== '):
                        line = line[1:]

                self.queue.put(line + '\n')
            self.buffer = lines[-1]
        return len(msg)

    def flush(self):
        if self.buffer:
            self.queue.put(self.buffer)
            self.buffer = ''

    def readable(self):
        return False

    def seekable(self):
        return False

    def writable(self):
        return True

def run_interruptible_download(download_func, stop_event, *args, **kwargs):
    """
    Runs a download function in a way that can be interrupted by checking stop_event.
    This approach uses a global cancellation flag and monkey-patching to make downloads more responsive to cancellation.
    """
    import threading
    import time
    global _download_cancelled
    _download_cancelled = False

    result = {'completed': False, 'exception': None, 'result': None}

    def download_worker():
        try:
            result['result'] = download_func(*args, **kwargs)
            result['completed'] = True
        except Exception as e:
            result['exception'] = e
            result['completed'] = True
    download_thread = threading.Thread(target=download_worker, daemon=True)
    download_thread.start()
    check_interval = 0.1
    cancellation_timeout = 3.0
    cancellation_start_time = None

    while download_thread.is_alive():
        if stop_event.is_set():
            _download_cancelled = True

            if cancellation_start_time is None:
                cancellation_start_time = time.time()
            download_thread.join(timeout=1.0)
            if time.time() - cancellation_start_time > cancellation_timeout:
                print("Download cancellation timeout reached. Forcing UI reset.")
                try:
                    if 'app' in globals() and app and app.winfo_exists():
                        app.after(0, lambda: set_ui_state_downloading(False))
                except:
                    pass
                raise DownloadCancelledError("Download cancelled by user (timeout)")

            if not download_thread.is_alive():
                raise DownloadCancelledError("Download cancelled by user")

        time.sleep(check_interval)
    _download_cancelled = False
    if result['exception']:
        raise result['exception']

    return result['result']

def patch_download_file_for_cancellation():
    """
    Monkey-patch the download_file function and concurrent download methods to check for cancellation during downloads.
    """
    try:
        import utils.utils as utils_module
        if not hasattr(utils_module, '_original_download_file'):
            utils_module._original_download_file = utils_module.download_file

        def cancellable_download_file(url, file_location, headers={}, enable_progress_bar=False, indent_level=0, artwork_settings=None):
            global _download_cancelled
            if _download_cancelled:
                raise DownloadCancelledError("Download cancelled before file download")
            import os
            from tqdm import tqdm

            if os.path.isfile(file_location):
                return None
            directory = os.path.dirname(file_location)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            r = utils_module.r_session.get(url, stream=True, headers=headers, verify=False)

            total = None
            if 'content-length' in r.headers:
                total = int(r.headers['content-length'])

            try:
                with open(file_location, 'wb') as f:
                    if enable_progress_bar and total:
                        import sys
                        from io import StringIO

                        class IndentedOutput:
                            def __init__(self, indent_level):
                                self.indent_level = indent_level

                            def write(self, text):
                                lines = text.split('\n')
                                indented_lines = []
                                for line in lines:
                                    if line.strip():
                                        indented_lines.append(' ' * self.indent_level + line)
                                    else:
                                        indented_lines.append(line)
                                sys.stdout.write('\n'.join(indented_lines))

                            def flush(self):
                                sys.stdout.flush()

                        bar = tqdm(
                            total=total,
                            unit='B',
                            unit_scale=True,
                            unit_divisor=1024,
                            initial=0,
                            miniters=1,
                            leave=False,
                            file=IndentedOutput(indent_level)
                        )
                        for chunk in r.iter_content(chunk_size=1024):
                            if _download_cancelled:
                                bar.close()
                                if os.path.isfile(file_location):
                                    os.remove(file_location)
                                raise DownloadCancelledError("Download cancelled during file transfer")

                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))
                        bar.close()
                    else:
                        for chunk in r.iter_content(chunk_size=1024):
                            if _download_cancelled:
                                if os.path.isfile(file_location):
                                    os.remove(file_location)
                                raise DownloadCancelledError("Download cancelled during file transfer")

                            if chunk:
                                f.write(chunk)
                if artwork_settings and artwork_settings.get('should_resize', False):
                    if _download_cancelled:
                        if os.path.isfile(file_location):
                            os.remove(file_location)
                        raise DownloadCancelledError("Download cancelled during artwork processing")
                    new_resolution = artwork_settings.get('resolution', 1400)
                    new_format = artwork_settings.get('format', 'jpeg')
                    if new_format == 'jpg': new_format = 'jpeg'
                    new_compression = artwork_settings.get('compression', 'low')
                    if new_compression == 'low':
                        new_compression = 90
                    elif new_compression == 'high':
                        new_compression = 70
                    if new_format == 'png': new_compression = None

                    from PIL import Image
                    with Image.open(file_location) as im:
                        im = im.resize((new_resolution, new_resolution), Image.Resampling.BICUBIC)
                        im.save(file_location, new_format, quality=new_compression)

            except KeyboardInterrupt:
                if os.path.isfile(file_location):
                    print(f'\tDeleting partially downloaded file "{str(file_location)}"')
                    utils_module.silentremove(file_location)
                raise KeyboardInterrupt
            except DownloadCancelledError:
                if os.path.isfile(file_location):
                    print(f'\tDeleting partially downloaded file due to cancellation: "{str(file_location)}"')
                    try:
                        os.remove(file_location)
                    except:
                        pass
                raise
            return file_location
        utils_module.download_file = cancellable_download_file
        print("[Patch] Applied cancellable download_file patch.")
        try:
            from orpheus.music_downloader import Downloader
            if not hasattr(Downloader, '_original_concurrent_download_tracks'):
                Downloader._original_concurrent_download_tracks = Downloader._concurrent_download_tracks

            def cancellable_concurrent_download_tracks(self, track_list, download_args_list, concurrent_downloads, performance_summary_indent=0):
                """Patched version of _concurrent_download_tracks that respects cancellation"""
                global _download_cancelled
                should_indent_tracks = True

                if concurrent_downloads <= 1:
                    self.print("Using sequential downloads (sync)")
                    results = []
                    for i, (track_info, args) in enumerate(zip(track_list, download_args_list)):
                        if _download_cancelled:
                            print(f"Download cancelled during sequential track {i+1}")
                            break
                        try:
                            result = self.download_track(**args)
                            results.append((i, result, None))
                        except Exception as e:
                            results.append((i, None, e))
                        if _download_cancelled:
                            print(f"Download cancelled after sequential track {i+1}")
                            break
                    return results
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import queue
                import threading
                total_tracks = len(track_list)
                self.print(f"Using {concurrent_downloads} concurrent downloads for {total_tracks} tracks", drop_level=performance_summary_indent)

                progress_queue = queue.Queue()

                def download_worker(index, args):
                    if _download_cancelled:
                        return (index, None, Exception("Download cancelled"))

                    try:
                        track_id = args.get('track_id', 'Unknown')
                        track_name = f"Track {track_id}"
                        track_info_failed = False
                        track_info_error = None
                        try:
                            if _download_cancelled:
                                return (index, None, Exception("Download cancelled"))
                                
                            from utils.models import QualityEnum, CodecOptions
                            quality_tier = QualityEnum[self.global_settings['general']['download_quality'].upper()]
                            codec_options = CodecOptions(
                                spatial_codecs=self.global_settings['codecs']['spatial_codecs'],
                                proprietary_codecs=self.global_settings['codecs']['proprietary_codecs'],
                            )
                            track_info = self.service.get_track_info(track_id, quality_tier, codec_options, **args.get('extra_kwargs', {}))
                            if track_info and hasattr(track_info, 'name') and track_info.name:
                                if hasattr(track_info, 'artists') and track_info.artists:
                                    artists_str = ', '.join(track_info.artists)
                                    track_name = f"{artists_str} - {track_info.name}"
                                else:
                                    track_name = track_info.name
                        except Exception as e:
                            track_info_failed = True
                            track_info_error = e
                        if track_info_failed:
                            progress_queue.put((index, track_name, track_info_error))
                            return (index, None, track_info_error)
                        if _download_cancelled:
                            return (index, None, Exception("Download cancelled"))
                        result = self.download_track(**args, verbose=False)
                        if _download_cancelled:
                            return (index, None, Exception("Download cancelled"))
                        if result is None:
                            progress_queue.put((index, track_name, "SKIPPED"))
                        elif result == "RATE_LIMITED":
                            progress_queue.put((index, track_name, "RATE_LIMITED"))
                        else:
                            progress_queue.put((index, track_name, None))

                        return (index, result, None)
                    except Exception as e:
                        error_track_name = track_name
                        if error_track_name.startswith("Track "):
                            try:
                                from utils.models import QualityEnum, CodecOptions
                                quality_tier = QualityEnum[self.global_settings['general']['download_quality'].upper()]
                                codec_options = CodecOptions(
                                    spatial_codecs=self.global_settings['codecs']['spatial_codecs'],
                                    proprietary_codecs=self.global_settings['codecs']['proprietary_codecs'],
                                )
                                track_info = self.service.get_track_info(track_id, quality_tier, codec_options, **args.get('extra_kwargs', {}))
                                if track_info and hasattr(track_info, 'name') and track_info.name:
                                    if hasattr(track_info, 'artists') and track_info.artists:
                                        artists_str = ', '.join(track_info.artists)
                                        error_track_name = f"{artists_str} - {track_info.name}"
                                    else:
                                        error_track_name = track_info.name
                            except Exception:
                                pass

                        progress_queue.put((index, error_track_name, e))
                        return (index, None, e)
                results = []
                completion_counter = 0
                with ThreadPoolExecutor(max_workers=concurrent_downloads) as executor:
                    future_to_index = {}
                    for i, args in enumerate(download_args_list):
                        if _download_cancelled:
                            print(f"Download cancelled before submitting task {i+1}")
                            break
                        future = executor.submit(download_worker, i, args)
                        future_to_index[future] = i
                    completed_count = 0
                    total_tasks = len(future_to_index)

                    for future in as_completed(future_to_index):
                        if _download_cancelled:
                            for remaining_future in future_to_index:
                                if not remaining_future.done():
                                    remaining_future.cancel()
                            executor.shutdown(wait=False)
                            break

                        try:
                            result = future.result()
                            results.append(result)
                            completed_count += 1
                            while not progress_queue.empty():
                                try:
                                    index, track_name, status = progress_queue.get_nowait()
                                    completion_counter += 1
                                    total_digits = len(str(total_tasks))
                                    indent_prefix = "       " if should_indent_tracks else ""
                                    
                                    if status == "SKIPPED":
                                        self.print(f'{indent_prefix}{completion_counter:0{total_digits}d}/{total_tasks} ▶ {track_name} |GRAY|(already exists)', drop_level=1)
                                    elif status == "RATE_LIMITED":
                                        self.print(f'{indent_prefix}{completion_counter:0{total_digits}d}/{total_tasks} ⚠ {track_name} (rate limited)', drop_level=1)
                                    elif status is not None:
                                        error_msg = str(status)
                                        if "Could not get track info for" in error_msg:
                                            if ":" in error_msg:
                                                error_reason = error_msg.split(":", 1)[1].strip()
                                            else:
                                                error_reason = error_msg
                                        else:
                                            error_reason = error_msg

                                        self.print(f'{indent_prefix}{completion_counter:0{total_digits}d}/{total_tasks} ❌ {track_name}: {error_reason} |GRAY|(failed)', drop_level=1)
                                    else:
                                        self.print(f'{indent_prefix}{completion_counter:0{total_digits}d}/{total_tasks} ✓ {track_name}', drop_level=1)
                                except queue.Empty:
                                    break
                        except Exception as e:
                            index = future_to_index[future]
                            results.append((index, None, e))
                actual_downloaded = sum(1 for r in results if r and r[2] is None and r[1] is not None and r[1] != "RATE_LIMITED")
                actual_already_existed = sum(1 for r in results if r and r[2] is None and r[1] is None)
                actual_failed = sum(1 for r in results if r and (r[2] is not None or (r[1] == "RATE_LIMITED")))
                from utils.models import Oprinter

                if actual_failed > 0:
                    if actual_downloaded > 0 and actual_already_existed > 0:
                        Oprinter._original_oprint(self.oprinter, f"All {len(results)} tracks available! ({actual_downloaded} downloaded, {actual_already_existed} already existed, {actual_failed} failed)", drop_level=performance_summary_indent)
                    elif actual_downloaded > 0:
                        Oprinter._original_oprint(self.oprinter, f"{actual_downloaded + actual_failed} tracks processed! ({actual_downloaded} downloaded, {actual_failed} failed)", drop_level=performance_summary_indent)
                    elif actual_already_existed > 0:
                        Oprinter._original_oprint(self.oprinter, f"{actual_already_existed + actual_failed} tracks processed! ({actual_already_existed} already existed, {actual_failed} failed)", drop_level=performance_summary_indent)
                    else:
                        Oprinter._original_oprint(self.oprinter, f"{actual_failed} tracks failed.", drop_level=performance_summary_indent)
                else:
                    pass

                return results
            Downloader._concurrent_download_tracks = cancellable_concurrent_download_tracks
            print("[Patch] Applied cancellable concurrent download patch.")
            try:
                original_concurrent_func = Downloader._original_concurrent_download_tracks
                
                def patched_original_concurrent_download_tracks(self, track_list, download_args_list, concurrent_downloads, performance_summary_indent=0):
                    original_print_method = self.print
                    def indentation_aware_print(message, drop_level=0):
                        message_str = str(message)
                        is_track_progress = ('/' in message_str and 
                                           any(symbol in message_str for symbol in ['▶', '✓', '❌', '⚠']) and
                                           ('already exists' in message_str or 'failed' in message_str or 'rate limited' in message_str or 
                                            not any(keyword in message_str for keyword in ['Using', 'Summary:', 'Download'])))
                        
                        if is_track_progress:
                            indented_message = "       " + message_str
                            original_print_method(indented_message, drop_level=1)
                        else:
                            original_print_method(message, drop_level=drop_level)
                    self.print = indentation_aware_print
                    
                    try:
                        return original_concurrent_func(self, track_list, download_args_list, concurrent_downloads, performance_summary_indent)
                    finally:
                        self.print = original_print_method
                Downloader._original_concurrent_download_tracks = patched_original_concurrent_download_tracks
                print("[Patch] Applied indentation patch to original concurrent download function.")
                
            except Exception as e:
                print(f"[Patch Warning] Could not patch original concurrent download indentation: {e}")
            if not hasattr(Downloader, '_original_download_track'):
                Downloader._original_download_track = Downloader.download_track

                def cancellable_download_track(self, track_id, **kwargs):
                    """Patched version of download_track that checks for cancellation"""
                    global _download_cancelled
                    if _download_cancelled:
                        raise DownloadCancelledError("Download cancelled before track download")
                    return Downloader._original_download_track(self, track_id, **kwargs)
                Downloader.download_track = cancellable_download_track
                print("[Patch] Applied cancellable download_track patch.")
            try:
                from utils.models import Oprinter

                if not hasattr(Oprinter, '_original_oprint'):
                    Oprinter._original_oprint = Oprinter.oprint

                    def patched_oprint(self, inp: str, drop_level: int = 0):
                        inp_str = str(inp)
                        
                        is_summary_message = (
                            ("available! (" in inp_str and "downloaded" in inp_str and "already existed" in inp_str) or
                            ("processed! (" in inp_str) or
                            ("downloaded successfully!" in inp_str) or
                            ("failed." in inp_str and "tracks" in inp_str)
                        ) and not inp_str.strip().startswith("===")
                        is_completion_message = ("=== " in inp_str and "completed ===" in inp_str)

                        if is_summary_message and not is_completion_message:
                            return
                        elif not is_completion_message and any(keyword in inp_str for keyword in [
                            "tracks processed!", "tracks available!", "tracks downloaded successfully!",
                            "tracks already existed", "tracks failed.", "Summary:"
                        ]):
                            original_indent = self.indent_number
                            self.indent_number = 0
                            try:
                                Oprinter._original_oprint(self, inp, drop_level=0)
                            finally:
                                self.indent_number = original_indent
                        else:
                            Oprinter._original_oprint(self, inp, drop_level)

                    Oprinter.oprint = patched_oprint
                    print("[Patch] Applied Oprinter patch to remove summary indentation.")

            except Exception as oprinter_e:
                print(f"[Patch Warning] Could not patch Oprinter: {oprinter_e}")
            try:
                if not hasattr(Downloader, '_original_download_artist'):
                    Downloader._original_download_artist = Downloader.download_artist

                    def patched_download_artist(self, artist_id, **kwargs):
                        global _download_cancelled

                        try:
                            result = Downloader._original_download_artist(self, artist_id, **kwargs)
                            return result
                        except Exception as e:
                            if _download_cancelled or "Download cancelled" in str(e):
                                raise e
                            else:
                                raise e
                    def patched_download_artist_with_status_check(self, artist_id, **kwargs):
                        global _download_cancelled
                        original_print = self.print

                        def status_aware_print(message, drop_level=0):
                            message_str = str(message)
                            if "completed ===" in message_str and _download_cancelled:
                                if "=== Artist" in message_str:
                                    artist_name = message_str.split("=== Artist ")[1].split(" completed ===")[0] if "=== Artist " in message_str else "Unknown"
                                    original_print(f"=== ❌ Artist {artist_name} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                                elif "=== Album" in message_str:
                                    album_name = message_str.split("=== Album ")[1].split(" completed ===")[0] if "=== Album " in message_str else "Unknown"
                                    original_print(f"=== ❌ Album {album_name} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                                elif "=== Playlist" in message_str:
                                    playlist_name = message_str.split("=== Playlist ")[1].split(" completed ===")[0] if "=== Playlist " in message_str else "Unknown"
                                    original_print(f"=== ❌ Playlist {playlist_name} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                                elif "=== Track" in message_str:
                                    track_info = message_str.split("=== Track ")[1].split(" completed ===")[0] if "=== Track " in message_str else "Unknown"
                                    original_print(f"=== ❌ Track {track_info} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                            else:
                                original_print(message, drop_level=drop_level)
                        self.print = status_aware_print

                        try:
                            result = Downloader._original_download_artist(self, artist_id, **kwargs)
                            return result
                        finally:
                            self.print = original_print

                    Downloader.download_artist = patched_download_artist_with_status_check
                    print("[Patch] Applied download_artist patch to show correct completion status.")

            except Exception as artist_e:
                print(f"[Patch Warning] Could not patch download_artist: {artist_e}")
            try:
                if not hasattr(Downloader, '_original_download_track'):
                    Downloader._original_download_track = Downloader.download_track

                    def patched_download_track_with_status_check(self, track_id, **kwargs):
                        global _download_cancelled
                        original_print = self.print

                        def track_status_aware_print(message, drop_level=0):
                            message_str = str(message)
                            if "completed ===" in message_str and _download_cancelled:
                                if "=== Track" in message_str:
                                    track_info = message_str.split("=== Track ")[1].split(" completed ===")[0] if "=== Track " in message_str else "Unknown"
                                    original_print(f"=== ❌ Track {track_info} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                            else:
                                original_print(message, drop_level=drop_level)

                        self.print = track_status_aware_print
                        try:
                            result = Downloader._original_download_track(self, track_id, **kwargs)
                            return result
                        finally:
                            self.print = original_print

                    Downloader.download_track = patched_download_track_with_status_check
                if not hasattr(Downloader, '_original_download_album'):
                    Downloader._original_download_album = Downloader.download_album

                    def patched_download_album_with_status_check(self, album_id, **kwargs):
                        global _download_cancelled

                        original_print = self.print

                        def album_status_aware_print(message, drop_level=0):
                            message_str = str(message)
                            if "completed ===" in message_str and _download_cancelled:
                                if "=== Album" in message_str:
                                    album_name = message_str.split("=== Album ")[1].split(" completed ===")[0] if "=== Album " in message_str else "Unknown"
                                    original_print(f"=== ❌ Album {album_name} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                            else:
                                original_print(message, drop_level=drop_level)

                        self.print = album_status_aware_print
                        try:
                            result = Downloader._original_download_album(self, album_id, **kwargs)
                            return result
                        finally:
                            self.print = original_print

                    Downloader.download_album = patched_download_album_with_status_check
                if not hasattr(Downloader, '_original_download_playlist'):
                    Downloader._original_download_playlist = Downloader.download_playlist

                    def patched_download_playlist_with_status_check(self, playlist_id, **kwargs):
                        global _download_cancelled

                        original_print = self.print
                        original_download_track = self.download_track

                        def playlist_status_aware_print(message, drop_level=0):
                            message_str = str(message)
                            if "completed ===" in message_str and _download_cancelled:
                                if "=== Playlist" in message_str:
                                    playlist_name = message_str.split("=== Playlist ")[1].split(" completed ===")[0] if "=== Playlist " in message_str else "Unknown"
                                    original_print(f"=== ❌ Playlist {playlist_name} cancelled ===", drop_level=drop_level)
                                    original_print("", drop_level=drop_level)
                            else:
                                original_print(message, drop_level=drop_level)

                        def cancellation_aware_download_track(track_id, **track_kwargs):
                            if _download_cancelled:
                                service_name = getattr(self, 'service_name', 'Unknown')
                                raise DownloadCancelledError(f"Download cancelled during {service_name} playlist track processing")
                            return original_download_track(track_id, **track_kwargs)

                        self.print = playlist_status_aware_print
                        self.download_track = cancellation_aware_download_track
                        try:
                            result = Downloader._original_download_playlist(self, playlist_id, **kwargs)
                            return result
                        finally:
                            self.print = original_print
                            self.download_track = original_download_track

                    Downloader.download_playlist = patched_download_playlist_with_status_check

                print("[Patch] Applied completion status patches for all download types.")
                try:
                    def create_universal_cancellable_method(original_method, method_name, media_type):
                        """Factory function to create cancellation-aware download methods for all services"""
                        def universal_cancellable_download(self, *args, **kwargs):
                            global _download_cancelled
                            if _download_cancelled:
                                service_name = getattr(self, 'service_name', 'Unknown')
                                raise DownloadCancelledError(f"Download cancelled before {service_name} {media_type} processing")
                            original_print = self.print

                            def cancellation_checking_print(message, drop_level=0):
                                if _download_cancelled:
                                    service_name = getattr(self, 'service_name', 'Unknown')
                                    raise DownloadCancelledError(f"Download cancelled during {service_name} {media_type} processing")
                                return original_print(message, drop_level=drop_level)
                            self.print = cancellation_checking_print

                            try:
                                return original_method(self, *args, **kwargs)
                            finally:
                                self.print = original_print

                        return universal_cancellable_download
                    download_methods = [
                        ('download_track', 'track'),
                        ('download_album', 'album'),
                        ('download_playlist', 'playlist'),
                        ('download_artist', 'artist')
                    ]

                    for method_name, media_type in download_methods:
                        original_attr_name = f'_original_{method_name}_universal_patch'
                        if not hasattr(Downloader, original_attr_name):
                            original_method = getattr(Downloader, method_name)
                            setattr(Downloader, original_attr_name, original_method)
                            cancellable_method = create_universal_cancellable_method(original_method, method_name, media_type)
                            setattr(Downloader, method_name, cancellable_method)

                    print("[Patch] Applied universal cancellation patches for all music services (tracks, albums, playlists, and artists).")

                except Exception as universal_e:
                    print(f"[Patch Warning] Could not patch universal cancellation: {universal_e}")

            except Exception as other_e:
                print(f"[Patch Warning] Could not patch other download methods: {other_e}")

        except Exception as concurrent_e:
            print(f"[Patch Warning] Could not patch concurrent downloads: {concurrent_e}")

    except Exception as e:
        print(f"[Patch Warning] Could not patch download_file for cancellation: {e}")


def run_download_in_thread(orpheus, url, output_path, gui_settings, search_result_data=None):
    """Runs the download using the provided global Orpheus instance."""
    global output_queue, stop_event, app, download_process_active, DEFAULT_SETTINGS, _queue_log_handler_instance, _current_download_context
    import time
    import threading
    
    if _queue_log_handler_instance:
        _queue_log_handler_instance.reset_ffmpeg_state_for_current_download()

    if orpheus is None:
        logging.error("Orpheus instance not available. Cannot start download.")
        try:
            if 'app' in globals() and app and app.winfo_exists():
                 app.after(0, lambda: set_ui_state_downloading(False))
        except NameError: pass
        except Exception as e: logging.error(f"Error scheduling UI reset after Orpheus instance error: {e}")
        return
    def yield_to_gui():
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.update_idletasks()
            time.sleep(0.001)
        except:
            pass
    yielding_active = threading.Event()
    yielding_active.set()
    
    def periodic_yield():
        while yielding_active.is_set():
            yield_to_gui()
            time.sleep(0.1)
    yield_thread = threading.Thread(target=periodic_yield, daemon=True)
    yield_thread.start()

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    dummy_stderr = DummyStderr()
    is_cancelled = False
    download_exception_occurred = False
    start_time = datetime.datetime.now()
    media_type = None
    yield_to_gui()

    try:
        queue_writer = QueueWriter(output_queue, media_type=media_type)
        sys.stdout = queue_writer
        sys.stderr = dummy_stderr
        yield_to_gui()
        
        downloader_settings = {
            "general": {
                "download_path": gui_settings.get("globals", {}).get("general", {}).get("output_path", DEFAULT_SETTINGS["globals"]["general"]["output_path"]),
                "download_quality": gui_settings.get("globals", {}).get("general", {}).get("quality", DEFAULT_SETTINGS["globals"]["general"]["quality"]),
                "search_limit": gui_settings.get("globals", {}).get("general", {}).get("search_limit", DEFAULT_SETTINGS["globals"]["general"]["search_limit"]),
                "concurrent_downloads": gui_settings.get("globals", {}).get("general", {}).get("concurrent_downloads", DEFAULT_SETTINGS["globals"]["general"]["concurrent_downloads"]),
                "play_sound_on_finish": gui_settings.get("globals", {}).get("general", {}).get("play_sound_on_finish", DEFAULT_SETTINGS["globals"]["general"]["play_sound_on_finish"]),
                "progress_bar": False
            },
            **{k: v for k, v in gui_settings.get("globals", {}).items() if k != "general"}
        }
        if "advanced" in downloader_settings and \
           "conversion_flags" in downloader_settings["advanced"] and \
           "mp3" in downloader_settings["advanced"]["conversion_flags"]:
            mp3_flags = downloader_settings["advanced"]["conversion_flags"]["mp3"]
            if "audio_bitrate" in mp3_flags and "qscale:a" in mp3_flags:
                if gui_settings.get("globals",{}).get("advanced",{}).get("conversion_flags",{}).get("mp3",{}).get("audio_bitrate"):
                    cleaned_mp3_flags = {"audio_bitrate": gui_settings["globals"]["advanced"]["conversion_flags"]["mp3"]["audio_bitrate"]}
                    downloader_settings["advanced"]["conversion_flags"]["mp3"] = cleaned_mp3_flags
                elif gui_settings.get("globals",{}).get("advanced",{}).get("conversion_flags",{}).get("mp3",{}).get("qscale:a"):
                    cleaned_mp3_flags = {"qscale:a": gui_settings["globals"]["advanced"]["conversion_flags"]["mp3"]["qscale:a"]}
                    downloader_settings["advanced"]["conversion_flags"]["mp3"] = cleaned_mp3_flags

        yield_to_gui()

        module_controls_dict = orpheus.module_controls
        oprinter = Oprinter()
        downloader = Downloader(settings=downloader_settings, module_controls=module_controls_dict, oprinter=oprinter, path=output_path)
        downloader.full_settings = {
            'global': downloader_settings,
            'modules': gui_settings.get('modules', {})
        }

        settings_global_for_defaults = gui_settings.get("globals", DEFAULT_SETTINGS["globals"])
        module_defaults = settings_global_for_defaults.get("module_defaults", {})
        third_party_modules_dict = { ModuleModes.lyrics: module_defaults.get("lyrics") if module_defaults.get("lyrics") != "default" else None, ModuleModes.covers: module_defaults.get("covers") if module_defaults.get("covers") != "default" else None, ModuleModes.credits: module_defaults.get("credits") if module_defaults.get("credits") != "default" else None }
        downloader.third_party_modules = third_party_modules_dict
        parsed_url = urlparse(url); components = parsed_url.path.split('/'); module_name = None
        for netloc_pattern, mod_name in orpheus.module_netloc_constants.items():
            if re.findall(netloc_pattern, parsed_url.netloc): module_name = mod_name; break
        if not module_name: raise ValueError(f"Could not determine module for URL host: {parsed_url.netloc}")
        
        yield_to_gui()
        
        try:
            if orpheus.module_settings[module_name].url_decoding is ManualEnum.manual:
                module_instance = orpheus.load_module(module_name)
                media_ident: MediaIdentification = module_instance.custom_url_parse(url)
                if not media_ident: raise ValueError(f"Module '{module_name}' custom_url_parse failed for URL: {url}")
                media_type = media_ident.media_type; media_id = media_ident.media_id
                if hasattr(media_ident, 'extra_kwargs') and media_ident.extra_kwargs:
                    downloader.extra_kwargs = media_ident.extra_kwargs
            else:
                media_id = None
                media_type = None
                if module_name == 'jiosaavn' and len(components) > 2 and components[1] == 'song':
                    media_type = DownloadTypeEnum.track
                    media_id = components[-1]
                if media_id is None or media_type is None:
                    if not components or len(components) <= 2:
                         if len(components) == 2 and components[1]: raise ValueError(f"Could not determine media type from short URL path: {parsed_url.path}")
                         else: raise ValueError(f"Invalid URL path structure: {parsed_url.path}")
                    url_constants = orpheus.module_settings[module_name].url_constants
                    if not url_constants: url_constants = {'track': DownloadTypeEnum.track, 'album': DownloadTypeEnum.album, 'release': DownloadTypeEnum.album, 'playlist': DownloadTypeEnum.playlist, 'artist': DownloadTypeEnum.artist}
                    type_matches = []; parsed_media_id = None
                    for i, component in enumerate(components):
                        if isinstance(component, str):
                            for url_keyword, type_enum in url_constants.items():
                                if component == url_keyword:
                                    type_matches.append(type_enum)
                                    break
                            if type_matches: break
                    if not type_matches: raise ValueError(f"Could not determine media type from URL path components: {components}")
                    media_type = type_matches[-1]
                    if len(components) > 1:
                        media_id = components[-1]                    
                    else:
                        raise ValueError(f"Could not determine media ID from URL path: {parsed_url.path}")
                if module_name == 'beatsource' and 'playlist' in components and len(components) > 2:
                    media_type = DownloadTypeEnum.playlist
                    media_id = components[-1]
                elif module_name == 'beatport' and 'chart' in components and len(components) > 2:
                    media_type = DownloadTypeEnum.playlist
                    media_id = components[-1]
                else:
                    if media_id is None or media_type is None:
                        if not components or len(components) <= 2:
                             if len(components) == 2 and components[1]: raise ValueError(f"Could not determine media type from short URL path: {parsed_url.path}")
                             else: raise ValueError(f"Invalid URL path structure: {parsed_url.path}")
                        url_constants = orpheus.module_settings[module_name].url_constants
                        if not url_constants: url_constants = {'track': DownloadTypeEnum.track, 'album': DownloadTypeEnum.album, 'release': DownloadTypeEnum.album, 'playlist': DownloadTypeEnum.playlist, 'artist': DownloadTypeEnum.artist}
                        type_matches = []; parsed_media_id = None
                        for i, component in enumerate(components):
                            if isinstance(component, str):
                                for url_keyword, type_enum in url_constants.items():
                                    if component == url_keyword:
                                        type_matches.append(type_enum)
                                        break
                                if type_matches: break
                        if not type_matches: raise ValueError(f"Could not determine media type from URL path components: {components}")
                        media_type = type_matches[-1]
                        if len(components) > 1:
                            media_id = components[-1]                        
                        else:
                            raise ValueError(f"Could not determine media ID from URL path: {parsed_url.path}")

            downloader.service = orpheus.load_module(module_name)
            downloader.service_name = module_name
            downloader.download_mode = media_type
            queue_writer.media_type = media_type
            _current_download_context = media_type
            
            yield_to_gui()
            
            is_beatport_chart = False
            
            if media_type == DownloadTypeEnum.track:
                downloader.set_indent_number(0)

                if stop_event.is_set(): is_cancelled = True
                else:
                    try:
                        yield_to_gui()
                        oprinter.oprint(f"Fetching data. Please wait...\n")
                        run_interruptible_download(
                            downloader.download_track,
                            stop_event,
                            track_id=str(media_id),
                            album_location=output_path + '/'
                        )
                        yield_to_gui()
                    except DownloadCancelledError:
                        is_cancelled = True
                        print("|GRAY|Stop requested. Cancelling during track download.|RESET|")
            elif media_type == DownloadTypeEnum.playlist:
                _current_download_context = DownloadTypeEnum.playlist
                oprinter.oprint(f'Fetching data. Please wait...\n')
                if stop_event.is_set():
                    is_cancelled = True
                    print("|GRAY|Stop requested. Cancelling before playlist download.|RESET|")
                else:
                    try:
                        if hasattr(downloader, 'extra_kwargs') and downloader.extra_kwargs:
                            run_interruptible_download(
                                downloader.download_playlist,
                                stop_event,
                                media_id,
                                extra_kwargs=downloader.extra_kwargs
                            )
                        else:
                            run_interruptible_download(
                                downloader.download_playlist,
                                stop_event,
                                media_id
                            )
                        yield_to_gui()
                    except DownloadCancelledError:
                        is_cancelled = True
                        try:
                            print(f"=== ❌ Playlist {media_id} cancelled ===")
                        except UnicodeEncodeError:
                            print(f"=== X Playlist {media_id} cancelled ===")
                        print()
                        print("|GRAY|Stop requested. Cancelling during playlist download.|RESET|")
                    except Exception as e:
                        oprinter.oprint(f"Playlist download failed: {str(e)}")
                        download_exception_occurred = True
            elif media_type == DownloadTypeEnum.album:
                _current_download_context = DownloadTypeEnum.album
                oprinter.oprint(f'Fetching data. Please wait...\n')
                if stop_event.is_set():
                    is_cancelled = True
                    print("|GRAY|Stop requested. Cancelling before album download.|RESET|")
                else:
                    try:
                        if hasattr(downloader, 'extra_kwargs') and downloader.extra_kwargs:
                            run_interruptible_download(
                                downloader.download_album,
                                stop_event,
                                media_id,
                                path=output_path,
                                extra_kwargs=downloader.extra_kwargs
                            )
                        else:
                            extra_kwargs = {} if downloader.service_name in ['deezer', 'jiosaavn'] else None
                            run_interruptible_download(
                                downloader.download_album,
                                stop_event,
                                media_id,
                                path=output_path,
                                extra_kwargs=extra_kwargs
                            )
                        yield_to_gui()
                    except DownloadCancelledError:
                        is_cancelled = True
                        try:
                            print(f"=== ❌ Album {media_id} cancelled ===")
                        except UnicodeEncodeError:
                            print(f"=== X Album {media_id} cancelled ===")
                        print()
                        print("|GRAY|Stop requested. Cancelling during album download.|RESET|")
                    except Exception as e:
                        oprinter.oprint(f"Album download failed: {str(e)}")
                        download_exception_occurred = True
            elif media_type == DownloadTypeEnum.artist:
                _current_download_context = DownloadTypeEnum.artist
                oprinter.oprint(f'Fetching data. Please wait...\n')
                if stop_event.is_set():
                    is_cancelled = True
                    print("|GRAY|Stop requested. Cancelling before artist download.|RESET|")
                else:
                    try:
                        if hasattr(downloader, 'extra_kwargs') and downloader.extra_kwargs:
                            run_interruptible_download(
                                downloader.download_artist,
                                stop_event,
                                media_id,
                                extra_kwargs=downloader.extra_kwargs
                            )
                        else:
                            run_interruptible_download(
                                downloader.download_artist,
                                stop_event,
                                media_id
                            )
                        yield_to_gui()
                    except DownloadCancelledError:
                        is_cancelled = True
                        try:
                            print(f"=== ❌ Artist {media_id} cancelled ===")
                        except UnicodeEncodeError:
                            print(f"=== X Artist {media_id} cancelled ===")
                        print()
                        print("|GRAY|Stop requested. Cancelling during artist download.|RESET|")
                    except Exception as e:
                        oprinter.oprint(f"Artist download failed: {str(e)}")
                        download_exception_occurred = True
            else: print(f"ERROR: Unknown media type '{media_type.name if hasattr(media_type, 'name') else media_type}' encountered.")

            if is_cancelled: print("\nDownload Cancelled.")
        except FileNotFoundError as fnf_e:
            ffmpeg_path_setting = gui_settings.get("globals", {}).get("advanced", {}).get("ffmpeg_path", "ffmpeg").strip()
            is_ffmpeg_error = False
            tb_str = traceback.format_exc()
            if "ffmpeg" in tb_str.lower():
                is_ffmpeg_error = True
            elif "ffmpeg" in str(fnf_e).lower():
                is_ffmpeg_error = True
            elif platform.system() == "Windows" and hasattr(fnf_e, 'winerror') and fnf_e.winerror == 2:
                is_ffmpeg_error = True
            elif any(phrase in str(fnf_e).lower() for phrase in ["no such file or directory", "the system cannot find the file specified", "cannot find"]):
                if hasattr(fnf_e, 'errno') and fnf_e.errno == 2:
                    is_ffmpeg_error = True
            
            if is_ffmpeg_error:
                download_exception_occurred = True
                user_msg = (
                    "\n[FFMPEG ERROR] FFmpeg was not found. This is required for audio conversion.\n\n"
                    "Possible Solutions:\n"
                    "1. Install FFmpeg: If not installed, download from ffmpeg.org and install it.\n"
                    "2. Check PATH: Ensure the directory containing ffmpeg.exe (or ffmpeg) is in your system's PATH environment variable.\n"
                    "3. or Configure in GUI: Go to Settings > Global > Advanced > FFmpeg Path, and set the full path to your ffmpeg executable.\n\n"
                    f"Current FFmpeg Path setting in GUI: '{ffmpeg_path_setting}'\n\n"
                    "Download process aborted."
                )
                print(user_msg + "\n")
            else:
                raise fnf_e

    except (DownloadCancelledError, AuthenticationError, DownloadError, NetworkError, OrpheusdlError) as e:
        download_exception_occurred = True
        if isinstance(e, DownloadCancelledError):
             is_cancelled = True; download_exception_occurred = False
             print("Download Cancelled.")
        else: error_type = type(e).__name__; print(f"\nERROR: {error_type}.\nDetails: {e}\n")
    except Exception as e:
        download_exception_occurred = True
        error_type = type(e).__name__; error_repr = repr(e)
        tb_str_generic = traceback.format_exc()
        tb_str_generic_lower = tb_str_generic.lower()

        is_soundcloud_hls_ffmpeg_issue = False
        if ("soundcloud" in tb_str_generic_lower and
            "hls_unexpected_error_in_try_block" in tb_str_generic_lower and
            "ffmpeg" in tb_str_generic_lower and
            ("[winerror 2]" in tb_str_generic_lower or
             "no such file or directory" in tb_str_generic_lower or
             "system cannot find the file specified" in tb_str_generic_lower)):
            is_soundcloud_hls_ffmpeg_issue = True

        if is_soundcloud_hls_ffmpeg_issue:
            ffmpeg_path_setting = gui_settings.get("globals", {}).get("advanced", {}).get("ffmpeg_path", "ffmpeg").strip()
            user_msg = (
                "\n[FFMPEG ERROR - SoundCloud HLS] FFmpeg was not found or is misconfigured.\nThis is required for processing SoundCloud HLS streams.\n\n"
                "Possible Solutions:\n"
                "1. Install FFmpeg: If not installed, download from ffmpeg.org and install it.\n"
                "2. Check PATH: Ensure the directory containing ffmpeg.exe (or ffmpeg) is in your system's PATH environment variable.\n"
                "3. Configure in GUI: Go to Settings > Global > Advanced > FFmpeg Path, and set the full path to your ffmpeg executable.\n\n"
                f"Current FFmpeg Path setting in GUI: '{ffmpeg_path_setting}'\n\n"
                "Download process aborted."
            )
            print(user_msg + "\n")
        else:
            try:
                print(f"\nUNEXPECTED ERROR during download thread.\nType: {error_type}\nDetails: {error_repr}\nTraceback:\n{tb_str_generic}")
            except UnicodeEncodeError:
                safe_error_type = str(error_type).encode('ascii', 'replace').decode('ascii')
                safe_error_repr = str(error_repr).encode('ascii', 'replace').decode('ascii')
                safe_tb_str = str(tb_str_generic).encode('ascii', 'replace').decode('ascii')
                print(f"\nUNEXPECTED ERROR during download thread.\nType: {safe_error_type}\nDetails: {safe_error_repr}\nTraceback:\n{safe_tb_str}")
    finally:
        yielding_active.clear()
        
        end_time = datetime.datetime.now(); total_duration = end_time - start_time; formatted_time = beauty_format_seconds(total_duration.total_seconds())
        time_taken_message = f"Total time taken: {formatted_time}\n"
        if _queue_log_handler_instance and _queue_log_handler_instance._specific_ffmpeg_hls_error_logged_this_download:
            download_exception_occurred = True

        if is_cancelled:            
            pass
        else:
            final_status_message = "Download Finished." 
            print(final_status_message)
        
        print(time_taken_message)
        print("\n")

        sys.stdout = original_stdout
        sys.stderr = original_stderr
        _current_download_context = None

        download_successful = not is_cancelled and not download_exception_occurred

        def final_ui_update(success=False):
            global progress_bar, stop_button, download_process_active, app, file_download_queue, current_batch_output_path, current_settings, DEFAULT_SETTINGS

            try:
                if 'progress_bar' in globals() and progress_bar and progress_bar.winfo_exists(): progress_bar.set(0)
                if 'stop_button' in globals() and stop_button and stop_button.winfo_exists(): stop_button.configure(state=tkinter.DISABLED)
                download_process_active = False
                if file_download_queue:
                    next_url = file_download_queue.pop(0)
                    print(f"Queueing next download from file: {next_url} ({len(file_download_queue)} remaining)")
                    if 'app' in globals() and app and app.winfo_exists() and current_batch_output_path:
                        app.after(100, lambda u=next_url, p=current_batch_output_path: _start_single_download(u, p, None))
                    else:
                        print("[Error] Cannot queue next download: App not available or batch path missing.")
                        set_ui_state_downloading(False)
                        file_download_queue.clear()
                        current_batch_output_path = None
                else:
                    set_ui_state_downloading(False)
                    is_batch_finish = (current_batch_output_path is not None)

                    if is_batch_finish:
                         print("File download queue is empty. Batch finished.")
                         current_batch_output_path = None
                    play_sound = False
                    try:
                        play_sound = current_settings.get("globals", {}).get("general", {}).get("play_sound_on_finish", DEFAULT_SETTINGS["globals"]["general"]["play_sound_on_finish"])
                    except Exception as setting_e: print(f"[Sound] Error reading play_sound setting: {setting_e}")

                    if play_sound:
                        sound_played = False
                        try:
                            current_platform = platform.system()
                            sound_module_available = (current_platform == "Windows" and 'winsound' in sys.modules)

                            if sound_module_available:
                                sound_alias_to_play = "SystemAsterisk" if success else "SystemHand"
                                winsound.PlaySound(sound_alias_to_play, winsound.SND_ALIAS | winsound.SND_ASYNC)
                                sound_played = True
                            elif current_platform == "Darwin":
                                sound_file = "/System/Library/Sounds/Glass.aiff" if success else "/System/Library/Sounds/Sosumi.aiff"
                                if os.path.exists(sound_file):
                                    subprocess.Popen(["afplay", sound_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    sound_played = True
                                
                            if sound_played:
                                status_text = "completion" if success else "failure/cancellation"
                                finish_context = "Batch" if is_batch_finish else "Download"
                                print(f"[Sound] Played {finish_context} {status_text} sound ({current_platform}).")
                        except NameError:
                            print("[Sound] Sound playback skipped (winsound not available on this platform).")
                        except Exception as sound_e:
                            print(f"[Warning] Could not play completion/failure sound: {sound_e}")

            except NameError as final_ne:
                print(f"[Error] NameError during final UI update (widget missing?): {final_ne}")
                download_process_active = False; set_ui_state_downloading(False)
            except tkinter.TclError as final_tcl_e:
                 print(f"[Error] TclError during final UI update (widget destroyed?): {final_tcl_e}")
                 download_process_active = False
            except Exception as final_e:
                 print(f"[Error] Exception scheduling final UI update: {final_e}")
                 download_process_active = False; set_ui_state_downloading(False)

        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(0, lambda s=download_successful: final_ui_update(success=s))
            else: print("[Debug] 'app' not found in finally block for UI update scheduling.")
        except NameError:
            print("[Debug] 'app' NameError in finally block.")
        except Exception as final_e:
             print(f"[Error] Exception scheduling final UI update: {final_e}")

def _start_single_download(url_to_download, output_path_final, search_result_data=None):
    """Starts the download in a separate thread for a single URL."""
    global download_process_active, current_settings, orpheus_instance, stop_event
    
    if orpheus_instance is None:
        print("Download cancelled: Orpheus instance is None.")
        try:
            if 'app' in globals() and app and app.winfo_exists():
                 show_centered_messagebox("Error", "Orpheus library not initialized.", dialog_type="error")
        except Exception: pass
        return False
    
    if download_process_active:
        print(f"Skipping start for {url_to_download}: A download is currently active.")
        return False
    
    try:
        parsed_url = urlparse(url_to_download)
        if not parsed_url.scheme in ['http', 'https'] or not parsed_url.netloc:
            show_centered_messagebox("Invalid Input", f"Input is not a valid URL or file path.\nPlease enter a valid web URL (http:// or https://) or the full path to a .txt file.", dialog_type="warning")
            return False
    except Exception as parse_e:
        show_centered_messagebox("Input Error", f"Could not process input: {url_to_download}\nError: {parse_e}\nPlease enter a valid web URL or .txt file path.", dialog_type="error")
        return False
    
    try:
        set_ui_state_downloading(True)
        stop_event.clear()
        download_process_active = True

        download_thread = threading.Thread(
            target=run_download_in_thread,
            args=(orpheus_instance, url_to_download, output_path_final, current_settings, search_result_data),
            daemon=True
        )
        print(f"Starting download thread for: {url_to_download}")
        download_thread.start()
        if platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                thread_handle = ctypes.windll.kernel32.OpenThread(0x0002, False, download_thread.ident)
                if thread_handle:
                    ctypes.windll.kernel32.SetThreadPriority(thread_handle, -2)
                    ctypes.windll.kernel32.CloseHandle(thread_handle)
            except Exception:
                pass
        
        return True

    except Exception as e:
        print(f"Unexpected error starting download thread for {url_to_download}: {e}")
        show_centered_messagebox("Error", f"Failed to start download thread for {url_to_download}. Error: {e}", dialog_type="error")
        set_ui_state_downloading(False)
        download_process_active = False
        return False

def start_download_thread(search_result_data=None):
    """Validates inputs (URL or file path) and starts the download process(es). Queues downloads from files."""
    global download_process_active, current_settings, orpheus_instance, url_entry, path_var_main, stop_event
    global file_download_queue, current_batch_output_path

    if orpheus_instance is None:
        show_centered_messagebox("Error", "Orpheus library not initialized. Cannot start download.", dialog_type="error")
        print("Download cancelled: Orpheus instance is None.")
        return

    try:
        if 'url_entry' not in globals() or not url_entry or not url_entry.winfo_exists():
            print("Error: URL entry widget not available."); return
        if 'path_var_main' not in globals() or not path_var_main:
            print("Error: Path variable not available."); return

        input_text = url_entry.get().strip()
        if not input_text:
             show_centered_messagebox("Info", "Please enter a URL or a file path.", dialog_type="warning"); return

        output_path = path_var_main.get().strip()
        if not output_path:
            show_centered_messagebox("Info", "Please select a download path.", dialog_type="warning"); return
        output_path_final = ""
        try:
            norm_path = os.path.normpath(output_path)
            output_path_final = os.path.join(norm_path, '')
            if os.path.exists(norm_path):
                if not os.path.isdir(norm_path):
                    show_centered_messagebox("Error", f"Output path '{norm_path}' exists but is a file.", dialog_type="error"); return
            else:
                os.makedirs(norm_path, exist_ok=True)
                print(f"Created output directory: {norm_path}")
        except OSError as e:
            show_centered_messagebox("Error", f"Invalid or inaccessible output path: '{output_path}'.\nError: {e}", dialog_type="error"); return
        except Exception as e:
            show_centered_messagebox("Error", f"An unexpected error occurred validating path '{output_path}'.\nError: {e}", dialog_type="error"); return
        if os.path.exists(input_text) and os.path.isfile(input_text):
            print(f"Detected file input: {input_text}")
            file_download_queue.clear()
            current_batch_output_path = output_path_final
            urls_in_file = []
            try:
                with open(input_text, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            urls_in_file.append(line)
            except Exception as e:
                show_centered_messagebox("File Error", f"Error reading file: {input_text}\n{e}", dialog_type="error")
                current_batch_output_path = None
                return

            if not urls_in_file:
                show_centered_messagebox("Info", f"File '{input_text}' is empty or contains no valid URLs.", dialog_type="warning")
                current_batch_output_path = None
                return
            file_download_queue.extend(urls_in_file)
            print(f"Added {len(file_download_queue)} URLs to the download queue.")
            if file_download_queue:
                first_url = file_download_queue.pop(0)
                print(f"Attempting to start first download from file queue: {first_url}")
                _start_single_download(first_url, current_batch_output_path, None)
            else:
                 print("File queue was unexpectedly empty after population.")
                 current_batch_output_path = None

        else:
            file_download_queue.clear()
            current_batch_output_path = None
            print(f"Treating input as single URL: {input_text}")
            _start_single_download(input_text, output_path_final, search_result_data)

    except Exception as e:
        print(f"Unexpected error in start_download_thread: {e}")
        show_centered_messagebox("Error", f"An unexpected error occurred: {e}", dialog_type="error")
        file_download_queue.clear()
        current_batch_output_path = None

def stop_download():
    global stop_event, output_queue
    stop_event.set()
    output_queue.put("|GRAY|Download stop requested... Please wait.|RESET|\n")

def on_platform_change(*args):
    global platform_var
    try:
        if 'platform_var' in globals() and platform_var:
            platform = platform_var.get(); update_search_types(platform)
    except NameError: pass
    except Exception as e: print(f"Error in on_platform_change: {e}")

def update_search_types(platform):
    global type_var, type_combo
    platform_types = {}    
    all_search_types = sorted(["track", "artist", "playlist", "album"])
    available_types = sorted(platform_types.get(platform, all_search_types))
    try:
        if 'type_var' in globals() and type_var and 'type_combo' in globals() and type_combo and type_combo.winfo_exists():
            current_type = type_var.get(); type_combo.configure(values=available_types)
            if current_type in available_types: type_var.set(current_type)
            elif "track" in available_types: type_var.set("track")
            elif available_types: type_var.set(available_types[0])
            else: type_var.set("")
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError updating search types (widget destroyed?): {e}")
    except Exception as e: print(f"Error updating search types: {e}")

def clear_treeview():
    global tree, scrollbar, app
    try:
        if 'tree' in globals() and tree and tree.winfo_exists():
            for item in tree.get_children(): tree.delete(item)
        if 'app' in globals() and app and app.winfo_exists() and 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists():
            app.after(0, lambda: _check_and_toggle_scrollbar(tree, scrollbar))
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing treeview (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing treeview: {e}")

def clear_search_results_data():
     global search_results_data, selection_var, search_download_button
     search_results_data = []
     try:
        if 'selection_var' in globals() and selection_var:
            if selection_var.get() != "": selection_var.set("")
        if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists():
            search_download_button.configure(state="disabled", text="Download")
     except NameError: pass
     except tkinter.TclError as e: print(f"TclError clearing search results data (widget destroyed?): {e}")
     except Exception as e: print(f"Error clearing search results data: {e}")

def clear_search_ui():
    global search_entry, search_progress_bar

    clear_treeview(); clear_search_results_data()
    try:
        if 'search_progress_bar' in globals() and search_progress_bar and search_progress_bar.winfo_exists():
            search_progress_bar.stop(); search_progress_bar.set(0)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError resetting search progress bar (widget destroyed?): {e}")
    except Exception as e: print(f"Error resetting search progress bar: {e}")

def display_results(results):
    global search_results_data, tree, scrollbar, app, platform_var, type_var    
    clear_treeview(); search_results_data = []
    item_number = 1
    seen_ids = set()
    local_DownloadTypeEnum = DownloadTypeEnum
    try:
        current_search_type_str = type_var.get() if ('type_var' in globals() and type_var) else "track"
        current_platform_str = platform_var.get() if ('platform_var' in globals() and platform_var) else "Unknown"
    except NameError:
        current_search_type_str = "track"
        current_platform_str = "Unknown"
    except Exception as e:
        print(f"Error getting search type/platform: {e}")
        current_search_type_str = "track"
        current_platform_str = "Unknown"

    for result in results:
        res_id = result.get('id', f'sim_{item_number}')
        name = result.get('title', 'N/A')
        artist_str = result.get('artist', 'N/A')
        duration_str = result.get('duration', '-')
        year = str(result.get('year', '-'))
        explicit = result.get('explicit', '')
        additional_str = result.get('quality', 'N/A')
        unique_tree_iid = f"item_{item_number}"
        
        result_entry = {
            "id": res_id, "number": str(item_number), "title": name,
            "artist": artist_str, "duration": duration_str, "year": year,
            "additional": additional_str, "explicit": explicit,
            "platform": current_platform_str, "type": current_search_type_str,
            "raw_result": result.get('raw_result'),
            "tree_iid": unique_tree_iid
        }
        if current_search_type_str == "artist":
            result_entry["title"] = ""
            result_entry["artist"] = name

        search_results_data.append(result_entry)

        try:
            if 'tree' in globals() and tree and tree.winfo_exists():
                if current_search_type_str == "artist":
                    values = (
                        str(item_number),
                        "",
                        name,
                        "",
                        "",
                        additional_str,
                        explicit,
                        res_id
                    )
                else:
                    values = (
                        str(item_number),
                        name,
                        artist_str,
                        duration_str,
                        year,
                        additional_str,
                        explicit,
                        res_id
                    )
                tree.insert("", "end", iid=unique_tree_iid, values=values)
                item_number += 1
                seen_ids.add(res_id)
            else:
                break
        except NameError: break
        except tkinter.TclError as e: 
            if not getattr(sys, 'frozen', False):
                print(f"TclError inserting into treeview (widget destroyed?): {e}", file=sys.__stderr__)
                print(f"[GUI Debug] Failed to insert item {item_number} with iid '{unique_tree_iid}' and res_id '{res_id}'", file=sys.__stderr__)
            break
        except Exception as e: 
            if not getattr(sys, 'frozen', False):
                print(f"Error inserting into treeview: {e}", file=sys.__stderr__)
    
    try:
        if 'app' in globals() and app and app.winfo_exists() and 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists():
            app.after(50, lambda: _check_and_toggle_scrollbar(tree, scrollbar))
    except NameError: pass
    except Exception as e: 
        if not getattr(sys, 'frozen', False):
            print(f"Error scheduling scrollbar check after display: {e}")
    except Exception as e: print(f"Error scheduling scrollbar check after display: {e}")

def run_search_thread_target(orpheus, platform_name, search_type_str, query, gui_settings):
    """Runs the search using the provided global Orpheus instance."""
    global search_process_active, app, output_queue, DEFAULT_SETTINGS
    local_DownloadTypeEnum = DownloadTypeEnum

    if orpheus is None:
        if 'output_queue' in globals() and output_queue:
            output_queue.put("ERROR: Orpheus instance not available. Cannot start search.\n")
        print("ERROR: run_search_thread_target called with invalid Orpheus instance.")
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(0, lambda: set_ui_state_searching(False))
        except NameError: pass
        except Exception as e: print(f"Error scheduling UI reset after Orpheus instance error: {e}")
        return

    results = []
    error_message = None
    try:
        search_limit = gui_settings.get("globals", {}).get("general", {}).get("search_limit", 20)
        try: search_limit = int(search_limit)
        except (ValueError, TypeError): print(f"Warning: Invalid search_limit '{search_limit}', defaulting to 20.", file=sys.stderr); search_limit = 20
        search_type_map = { "track": local_DownloadTypeEnum.track, "album": local_DownloadTypeEnum.album, "artist": local_DownloadTypeEnum.artist, "playlist": local_DownloadTypeEnum.playlist }
        query_type = search_type_map.get(search_type_str.lower())
        if not query_type: raise ValueError(f"Invalid search type: {search_type_str}")
        module_instance = orpheus.load_module(platform_name.lower())
        search_results = module_instance.search(query_type, query, limit=search_limit)
        formatted_results = []
        for result in search_results:
            formatted_result = { 'id': str(getattr(result, 'result_id', '')), 'title': str(getattr(result, 'name', 'N/A')), 'artist': ', '.join([str(a) for a in getattr(result, 'artists', [])]) if getattr(result, 'artists', []) else '-', 'duration': beauty_format_seconds(getattr(result, 'duration', None)) if getattr(result, 'duration', None) else '-', 'year': str(getattr(result, 'year', '-')), 'quality': ', '.join([str(q) for q in getattr(result, 'additional', [])]) if getattr(result, 'additional', []) else 'N/A', 'explicit': 'Y' if getattr(result, 'explicit', False) else '', 'raw_result': result }
            formatted_results.append(formatted_result)
        results = formatted_results
    except TypeError as e:
        if "'NoneType' object is not iterable" in str(e):
            error_message = f"Search Error ({platform_name}): Module returned no iterable results. This might be an API issue with the service or a module bug."
            print(f"[Search Thread Error] Caught NoneType iterable error for {platform_name}. Module likely returned None.", file=sys.stderr)            
            results = [] 
        else:
            error_message = f"Type Error during search: {str(e)}"
            print(f"[Search Thread Error] {error_message}", file=sys.stderr)
            import traceback
            tb_str = traceback.format_exc()
            print(tb_str, file=sys.stderr)
            results = []
    except Exception as e:
         error_message = f"Error during search: {str(e)}"
         print(f"[Search Thread Error] {error_message}", file=sys.stderr)
         import traceback
         tb_str = traceback.format_exc()
         print(tb_str, file=sys.stderr)
         results = []
    finally:

        def _update_ui():
            global search_process_active
            set_ui_state_searching(False)
            if error_message: show_centered_messagebox("Search Error", error_message, dialog_type="error"); clear_treeview(); clear_search_results_data()
            elif not results: show_centered_messagebox("No Results", "The search completed successfully, but found no results matching your query.", dialog_type="info"); display_results([])
            else: display_results(results)
            search_process_active = False
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(0, _update_ui)
            else:
                print("[Debug] 'app' not found for search UI update.")
                search_process_active = False
        except NameError:
            search_process_active = False
        except Exception as e:
            print(f"Error scheduling search UI update: {e}")
            search_process_active = False

def start_search():
    """Validates input and starts the search process in a separate thread using the global Orpheus instance."""
    global search_process_active, current_settings, orpheus_instance, search_entry, platform_var, type_var

    if orpheus_instance is None:
        show_centered_messagebox("Error", "Orpheus library not initialized. Cannot start search.", dialog_type="error")
        print("Search cancelled: Orpheus instance is None.")
        return

    try:
        if 'search_entry' not in globals() or not search_entry or not search_entry.winfo_exists(): print("Error: Search entry widget not available."); return
        if 'platform_var' not in globals() or not platform_var: print("Error: Platform variable not available."); return
        if 'type_var' not in globals() or not type_var: print("Error: Type variable not available."); return

        query = search_entry.get().strip(); platform_name = platform_var.get(); search_type_str = type_var.get()
        if not query: show_centered_messagebox("Info", "Please enter a search query.", dialog_type="warning"); return
        if not platform_name: show_centered_messagebox("Info", "Please select a platform.", dialog_type="warning"); return
        if not search_type_str: show_centered_messagebox("Info", "Please select a search type.", dialog_type="warning"); return
        if search_process_active: show_centered_messagebox("Busy", "A search is already in progress!", dialog_type="warning"); return

        clear_search_ui()
        set_ui_state_searching(True)
        search_process_active = True
        search_thread = threading.Thread(target=run_search_thread_target, args=(orpheus_instance, platform_name, search_type_str, query, current_settings), daemon=True)        
        search_thread.start()
    except NameError as e:
        print(f"Error starting search (widgets not ready?): {e}")
        search_process_active = False
    except Exception as e:
        print(f"Unexpected error in start_search: {e}")
        set_ui_state_searching(False)
        search_process_active = False

def on_tree_select(event):
    global tree, search_results_data, selection_var, search_download_button
    try:
        if 'tree' not in globals() or not tree or not tree.winfo_exists(): return
        if 'selection_var' not in globals() or not selection_var: return
        if 'search_download_button' not in globals() or not search_download_button or not search_download_button.winfo_exists(): return

        selection = tree.selection()
        if selection:
            selected_count = len(selection)
            if selected_count == 1:
                selected_iid = selection[0]
                selected_item_data = next((item for item in search_results_data if str(item.get('tree_iid')) == str(selected_iid)), None)
                if selected_item_data: 
                    selection_var.set(selected_item_data['number'])
                    search_download_button.configure(state="normal", text="Download")
                else: 
                    print(f"Selected iid {selected_iid} not found in search_results_data.")
                    selection_var.set("")
                    search_download_button.configure(state="disabled", text="Download")
            else:
                selected_numbers = []
                for selected_iid in selection:
                    selected_item_data = next((item for item in search_results_data if str(item.get('tree_iid')) == str(selected_iid)), None)
                    if selected_item_data:
                        selected_numbers.append(selected_item_data['number'])
                try:
                    selected_numbers.sort(key=int)
                except ValueError:
                    pass
                
                selection_var.set(",".join(selected_numbers))
                search_download_button.configure(state="normal", text=f"Download {selected_count} IDs")
        else: 
            selection_var.set("")
            search_download_button.configure(state="disabled", text="Download")
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError in tree select (widget destroyed?): {e}")
    except Exception as e: print(f"Error in tree select: {e}")

def on_selection_change(*args):
    global selection_var, search_results_data, search_download_button
    try:
        if 'selection_var' not in globals() or not selection_var: return
        if 'search_download_button' not in globals() or not search_download_button or not search_download_button.winfo_exists(): return

        selection_str = selection_var.get().strip()
        if not selection_str: 
            search_download_button.configure(state="disabled", text="Download")
            return
        if "," in selection_str:
            return
        try:
            selection_num = int(selection_str)
            matching_item = next((item for item in search_results_data if item.get('number') == str(selection_num)), None)
            search_download_button.configure(state="normal" if matching_item else "disabled", text="Download")
        except ValueError:
            search_download_button.configure(state="disabled", text="Download")
            
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError in selection change (widget destroyed?): {e}")
    except Exception as e:
        print(f"Error in selection change validation: {e}")
        if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists():
            search_download_button.configure(state="disabled", text="Download")

def get_selected_item_data():
    global selection_var, search_results_data
    try:
        if 'selection_var' not in globals() or not selection_var: return None

        selection_num_str = selection_var.get().strip()
        if not selection_num_str: return None
        selection_num = int(selection_num_str)
        return next((item for item in search_results_data if item.get('number') == str(selection_num)), None)
    except NameError: return None
    except (ValueError, Exception): return None

def get_selected_items_data():
    """Get data for all currently selected items in the tree."""
    global tree, search_results_data
    try:
        if 'tree' not in globals() or not tree or not tree.winfo_exists(): return []
        if 'search_results_data' not in globals() or not search_results_data: return []

        selection = tree.selection()
        if not selection: return []
        
        selected_items = []
        for selected_iid in selection:
            selected_item_data = next((item for item in search_results_data if str(item.get('tree_iid')) == str(selected_iid)), None)
            if selected_item_data:
                selected_items.append(selected_item_data)
            else:
                print(f"Selected iid {selected_iid} not found in search_results_data.")
        
        return selected_items
    except NameError: return []
    except Exception as e: 
        print(f"Error getting selected items data: {e}")
        return []

def build_url_from_result(result_data):
    platform = result_data.get('platform'); search_type = result_data.get('type'); item_id = result_data.get('id'); raw_result_obj = result_data.get('raw_result')
    if not all([platform, search_type, item_id]): print("[URL Build] Missing data."); return None

    p_lower = platform.lower(); t_lower = search_type.lower()

    base_urls = { "qobuz": "https://open.qobuz.com", "tidal": "https://listen.tidal.com", "deezer": "https://www.deezer.com", "beatport": "https://www.beatport.com", "beatsource": "https://www.beatsource.com", "napster": "https://web.napster.com", "idagio": "https://app.idagio.com", "spotify": "https://open.spotify.com", "applemusic": "https://music.apple.com" }
    type_paths = { 
        "qobuz": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"},
        "tidal": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"},
        "deezer": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"},
        "beatport": {"track": "track", "album": "release", "artist": "artist", "playlist": "chart"},
        "beatsource": {"track": "track", "album": "release", "artist": "artist", "playlist": "playlist"},
        "napster": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"},
        "idagio": {"track": "recording", "album": "album", "artist": "artist"},
        "spotify": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"},
        "applemusic": {"track": "song", "album": "album", "artist": "artist", "playlist": "playlist"}
    }

    if p_lower == "soundcloud":
        if raw_result_obj:
            permalink = getattr(raw_result_obj, 'permalink_url', None)
            if permalink: print(f"[SC URL] Using permalink: {permalink}"); return permalink            
        if t_lower == 'track': sc_entity = 'tracks'
        elif t_lower == 'playlist' or t_lower == 'album': sc_entity = 'playlists'
        elif t_lower == 'artist': sc_entity = 'users'
        else: print(f"[SC URL] Unknown type '{t_lower}'."); return None
        sc_api_url = f"https://api.soundcloud.com/{sc_entity}/{item_id}"
        widget_api_url = f'https://api-widget.soundcloud.com/resolve?url={sc_api_url}&format=json&client_id=gqKBMSuBw5rbN9rDRYPqKNvF17ovlObu&app_version=1742894364'
        headers = {'Referer': 'https://w.soundcloud.com/', 'Origin': 'https://w.soundcloud.com/', 'User-Agent': 'Mozilla/5.0'}
        try:
            print(f"[SC URL] Requesting widget API: {widget_api_url}")
            response = requests.get(widget_api_url, headers=headers, timeout=10); response.raise_for_status(); data = response.json()
            permalink_from_api = data.get('permalink_url')
            if permalink_from_api: print(f"[SC URL] Resolved via API: {permalink_from_api}"); return permalink_from_api
            else: print(f"[SC URL] API Error: No permalink in response: {data}"); return None
        except requests.exceptions.RequestException as e: print(f"[SC URL] API Request Error: {e}"); return None
        except json.JSONDecodeError as e: print(f"[SC URL] API JSON Error: {e}"); return None
        except Exception as e: print(f"[SC URL] API Unexpected Error: {e}"); return None
        return None

    elif p_lower == "beatport":
        if raw_result_obj:
            permalink = getattr(raw_result_obj, 'permalink_url', None)
            if not permalink:
                permalink = getattr(raw_result_obj, 'url', None)
            
            if permalink:
                print(f"[URL Build - Beatport] Using attribute permalink/url: {permalink}")
                return permalink

            slug = getattr(raw_result_obj, 'slug', None)
            if not slug:
                name_for_slug = getattr(raw_result_obj, 'name', None)
                if name_for_slug:
                    derived_slug = _simple_slugify(name_for_slug)
                    if derived_slug:
                        print(f"[URL Build - Beatport] Derived slug '{derived_slug}' from name '{name_for_slug}'.")
                        slug = derived_slug
                    else:
                        print(f"[URL Build - Beatport] Could not derive a valid slug from name: '{name_for_slug}'.")
                else:
                    print(f"[URL Build - Beatport] No 'name' attribute to derive slug from.")

            if slug and item_id and t_lower in type_paths.get(p_lower, {}):
                url_path_segment = type_paths[p_lower][t_lower]
                slug_str = str(slug).strip()
                if slug_str: 
                    url = f"{base_urls[p_lower]}/{url_path_segment}/{slug_str}/{item_id}"
                    print(f"[URL Build - Beatport] Constructed with slug '{slug_str}': {url}")
                    return url
                else:
                    print(f"[URL Build - Beatport] Slug (original or derived) was empty after processing. Falling back.")
            else:
                print(f"[URL Build - Beatport] No valid slug, or item_id/type invalid for slug path. Slug: {slug}, ID: {item_id}, Type: {t_lower}")
        else:
            print(f"[URL Build - Beatport] raw_result_obj is None. Cannot get permalink or slug.")

        print(f"[URL Build - Beatport] Attempting fallback URL construction (slug not available/derivable or other issue).")
        if p_lower in base_urls and p_lower in type_paths and t_lower in type_paths[p_lower]:
            url_path_segment = type_paths[p_lower][t_lower]
            url = f"{base_urls[p_lower]}/{url_path_segment}/{item_id}"
            print(f"[URL Build - Beatport] Fallback (no slug/permalink found): {url}")
            return url
        else:
            print(f"[URL Build - Beatport] Fallback failed: Path construction not supported for type '{t_lower}'.")
            return None
    elif p_lower == "applemusic":
        print(f"[URL Build - Apple Music] Building URL for {t_lower} with ID {item_id}")
        country = "us"
        if raw_result_obj:
            try:
                if hasattr(raw_result_obj, 'href') and raw_result_obj.href:
                    href_parts = raw_result_obj.href.split('/')
                    if len(href_parts) > 3:
                        potential_country = href_parts[3]
                        if len(potential_country) == 2:
                            country = potential_country
                elif hasattr(raw_result_obj, 'attributes') and 'url' in raw_result_obj.attributes:
                    url_parts = raw_result_obj.attributes['url'].split('/')
                    if len(url_parts) > 3:
                        potential_country = url_parts[3]
                        if len(potential_country) == 2:
                            country = potential_country
            except Exception as e:
                print(f"[URL Build - Apple Music] Could not extract country from raw result: {e}")
        type_mapping = {
            "track": "song",
            "album": "album", 
            "artist": "artist",
            "playlist": "playlist"
        }
        
        apple_music_type = type_mapping.get(t_lower, "song")
        url_name = "unknown"
        if raw_result_obj:
            try:
                if hasattr(raw_result_obj, 'attributes') and 'name' in raw_result_obj.attributes:
                    name = raw_result_obj.attributes['name']
                    url_name = _simple_slugify(name) or "unknown"
                elif hasattr(raw_result_obj, 'name'):
                    name = raw_result_obj.name
                    url_name = _simple_slugify(name) or "unknown"
            except Exception as e:
                print(f"[URL Build - Apple Music] Could not extract name from raw result: {e}")
        apple_music_url = f"https://music.apple.com/{country}/{apple_music_type}/{url_name}/{item_id}"
        print(f"[URL Build - Apple Music] Constructed URL: {apple_music_url}")
        return apple_music_url
    
    else:
        if p_lower in base_urls and p_lower in type_paths and t_lower in type_paths[p_lower]:
            url_path_segment = type_paths[p_lower][t_lower]; url = f"{base_urls[p_lower]}/{url_path_segment}/{item_id}"
            print(f"[URL Build - {platform}] Constructed: {url}"); return url
        else: print(f"[URL Build - {platform}] Not supported for type '{t_lower}'."); return None

def download_selected():
    global tabview, url_entry, file_download_queue, current_batch_output_path
    try:
        selected_items = get_selected_items_data()
        if not selected_items: 
            show_centered_messagebox("Error", "No items selected.", dialog_type="warning")
            return
        
        if len(selected_items) == 1:
            selected_data = selected_items[0]
            url_to_download = build_url_from_result(selected_data)
            if url_to_download:
                print(f"Switching tab and starting download for: {url_to_download}")
                if 'tabview' in globals() and tabview and tabview.winfo_exists():
                    tabview.set("Download")
                if 'url_entry' in globals() and url_entry and url_entry.winfo_exists():
                    url_entry.delete(0, "end"); url_entry.insert(0, url_to_download)
                else: print("Warning: url_entry not found.")
                start_download_thread(search_result_data=selected_data)
            else: 
                show_centered_messagebox("Error", f"Could not determine URL for selected item.", dialog_type="error")
        else:
            print(f"Starting batch download for {len(selected_items)} items")
            urls_to_download = []
            failed_items = []
            
            for item_data in selected_items:
                url = build_url_from_result(item_data)
                if url:
                    urls_to_download.append(url)
                else:
                    failed_items.append(f"{item_data.get('title', 'Unknown')} by {item_data.get('artist', 'Unknown')}")
            
            if failed_items:
                failed_list = '\n'.join(failed_items[:5])
                if len(failed_items) > 5:
                    failed_list += f'\n... and {len(failed_items) - 5} more'
                show_centered_messagebox("Warning", 
                    f"Could not build URLs for {len(failed_items)} item(s):\n{failed_list}\n\nProceeding with {len(urls_to_download)} valid items.", 
                    dialog_type="warning")
            
            if not urls_to_download:
                show_centered_messagebox("Error", "Could not build URLs for any selected items.", dialog_type="error")
                return
            if 'tabview' in globals() and tabview and tabview.winfo_exists():
                tabview.set("Download")
            global current_batch_output_path
            if 'path_var_main' in globals() and path_var_main:
                output_path = path_var_main.get().strip()
                if output_path:
                    try:
                        norm_path = os.path.normpath(output_path)
                        current_batch_output_path = os.path.join(norm_path, '')
                        if not os.path.exists(norm_path):
                            os.makedirs(norm_path, exist_ok=True)
                        print(f"Set batch output path to: {current_batch_output_path}")
                    except Exception as e:
                        print(f"Error setting up batch output path: {e}")
                        current_batch_output_path = None
                else:
                    current_batch_output_path = None
            else:
                current_batch_output_path = None
            file_download_queue.clear()
            file_download_queue.extend(urls_to_download)
            if file_download_queue:
                first_url = file_download_queue.pop(0)
                print(f"Starting batch download with first URL: {first_url}")
                print(f"Remaining in queue: {len(file_download_queue)} items")
                if 'url_entry' in globals() and url_entry and url_entry.winfo_exists():
                    url_entry.delete(0, "end")
                    url_entry.insert(0, first_url)
                else: 
                    print("Warning: url_entry not found.")
                _start_single_download(first_url, current_batch_output_path, selected_items[0])
            else:
                print("Error: Queue was empty after setup")
            
    except NameError as e: print(f"Error in download_selected (widget not ready?): {e}")
    except tkinter.TclError as e: print(f"TclError in download_selected (widget destroyed?): {e}")
    except Exception as e: print(f"Unexpected error in download_selected: {e}")

def sort_results(column):
    global sort_states, search_results_data, tree
    try:
        if 'tree' not in globals() or not tree or not tree.winfo_exists(): return
        is_numeric = column in ["#", "Year"]; is_reverse = sort_states.get(column, False)

        def sort_key(item):
            key_map = {"#": "number", "Year": "year", "Title": "title", "Artist": "artist", "Duration": "duration", "Additional": "additional", "Explicit": "explicit", "ID": "id"}
            dict_key = key_map.get(column, column); value = item.get(dict_key, "")
            if value is None: value = ""
            if is_numeric: return int(value) if str(value).isdigit() else 0
            else: return str(value).lower()
        search_results_data.sort(key=sort_key, reverse=is_reverse)
        sort_states[column] = not is_reverse
        clear_treeview()
        for item_data in search_results_data:
            try:
                if 'tree' in globals() and tree and tree.winfo_exists():
                    values = ( item_data.get('number', ''), item_data.get('title', ''), item_data.get('artist', ''), item_data.get('duration', ''), item_data.get('year', ''), item_data.get('additional', ''), item_data.get('explicit', ''), item_data.get('id', '') )
                    tree_iid = item_data.get('tree_iid', item_data.get('id', ''))
                    tree.insert("", "end", iid=tree_iid, values=values)
                else: break
            except NameError: break
            except tkinter.TclError as e: print(f"TclError repopulating sorted treeview (widget destroyed?): {e}"); break
            except Exception as e: print(f"Error repopulating sorted treeview: {e}")
        defined_columns = ("#", "Title", "Artist", "Duration", "Year", "Additional", "Explicit", "ID")
        for col in defined_columns:
            if 'tree' in globals() and tree and tree.winfo_exists():
                try:
                    heading_text = tree.heading(col, "text").replace(" ▲", "").replace(" ▼", "")
                    indicator = "" if col != column else (" ▼" if is_reverse else " ▲")
                    tree.heading(col, text=heading_text + indicator)
                except tkinter.TclError: pass
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError sorting results (widget destroyed?): {e}")
    except Exception as e: print(f"Error sorting results by '{column}': {e}"); show_centered_messagebox("Error", f"Sort failed: {e}", dialog_type="error")

def _update_settings_tab_widgets():
    """Refreshes ONLY the Global settings tab widgets from current_settings."""
    global current_settings, settings_vars, path_var_main, DEFAULT_SETTINGS
    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
        print("Refreshing Global Settings tab UI from current_settings...")
    try:
        for key, var in settings_vars.get("globals", {}).items():
            if key in ["advanced.codec_conversions"]:
                continue

            if key == "advanced.codec_conversions":
                current_codec_conversions_setting = current_settings.get("globals", {}).get("advanced", {}).get("codec_conversions", {})
                
                if isinstance(var, dict) and isinstance(current_codec_conversions_setting, dict):
                    for source_codec_from_settings, target_codec_from_settings in current_codec_conversions_setting.items():
                        source_var_key = f"{source_codec_from_settings}_source"
                        target_var_key = f"{source_codec_from_settings}_target"

                        if source_var_key in var and isinstance(var[source_var_key], tkinter.StringVar):
                            try: var[source_var_key].set(source_codec_from_settings)
                            except Exception as e_set_src: print(f"Error setting source var {source_var_key}: {e_set_src}")

                        if target_var_key in var and isinstance(var[target_var_key], tkinter.StringVar):
                            try: var[target_var_key].set(target_codec_from_settings)
                            except Exception as e_set_tgt: print(f"Error setting target var {target_var_key}: {e_set_tgt}")
                continue
            if not isinstance(var, tkinter.Variable):
                 if isinstance(var, dict):
                     if not var:
                         pass 
                 else:
                    print(f"[Update Settings UI WARN] Skipping key '{key}' in settings_vars: value is type {type(var)}, not a tkinter.Variable or handled dict.")
            keys = key.split('.')
            temp_dict = current_settings.get("globals", {})
            valid_path = True
            for k_part in keys:
                if isinstance(temp_dict, dict):
                    temp_dict = temp_dict.get(k_part)
                else:
                    valid_path = False
                    break
            value_from_dict = temp_dict if valid_path else None
            
            if value_from_dict is not None:
                try:
                    if isinstance(var, tkinter.BooleanVar):
                        var.set(bool(value_from_dict))
                    else:
                        var.set(str(value_from_dict))
                except tkinter.TclError as e_set:
                    if "invalid command name" in str(e_set): pass
                    else: print(f"Error setting variable for {key}: {e_set}")
                except Exception as e_set_other:
                    print(f"Error setting variable for {key}: {e_set_other}")
        if 'path_var_main' in globals() and isinstance(path_var_main, tkinter.Variable) and "general.output_path" not in settings_vars.get("globals", {}):
             main_path_val = current_settings.get("globals", {}).get("general", {}).get("output_path")
             if main_path_val is not None:
                  try: path_var_main.set(main_path_val)
                  except tkinter.TclError as e_set_main:
                      if "invalid command name" in str(e_set_main): pass
                      else: print(f"Error setting main path variable: {e_set_main}")
                  except Exception as e_set_main_other:
                      print(f"Error setting main path variable: {e_set_main_other}")
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print("Global Settings tab UI refresh finished.")
    except Exception as e: print(f"Error during Global settings UI refresh: {e}"); import traceback; traceback.print_exc()

    try:
        for key, var in settings_vars.get("globals", {}).items():

            if key == "advanced.codec_conversions":
                current_codec_conversions_setting = current_settings.get("globals", {}).get("advanced", {}).get("codec_conversions", {})
                
                if isinstance(var, dict) and isinstance(current_codec_conversions_setting, dict):
                    for source_codec_from_settings, target_codec_from_settings in current_codec_conversions_setting.items():
                        source_var_key = f"{source_codec_from_settings}_source"
                        target_var_key = f"{source_codec_from_settings}_target"

                        if source_var_key in var and isinstance(var[source_var_key], tkinter.StringVar):
                            try: var[source_var_key].set(source_codec_from_settings)
                            except Exception as e_set_src: print(f"Error setting source var {source_var_key}: {e_set_src}")

                        if target_var_key in var and isinstance(var[target_var_key], tkinter.StringVar):
                            try: var[target_var_key].set(target_codec_from_settings)
                            except Exception as e_set_tgt: print(f"Error setting target var {target_var_key}: {e_set_tgt}")
                continue
            if not isinstance(var, tkinter.Variable):
                 if isinstance(var, dict):
                     if not var:
                         pass 
                 else:
                    print(f"[Update Settings UI WARN] Skipping key '{key}' in settings_vars: value is type {type(var)}, not a tkinter.Variable or handled dict.")
            keys = key.split('.')
            temp_dict = current_settings.get("globals", {})
            valid_path = True
            for k_part in keys:
                if isinstance(temp_dict, dict):
                    temp_dict = temp_dict.get(k_part)
                else:
                    valid_path = False
                    break
            value_from_dict = temp_dict if valid_path else None
            
            if value_from_dict is not None:
                try:
                    if isinstance(var, tkinter.BooleanVar):
                        var.set(bool(value_from_dict))
                    else:
                        var.set(str(value_from_dict))
                except tkinter.TclError as e_set:
                    if "invalid command name" in str(e_set): pass
                    else: print(f"Error setting variable for {key}: {e_set}")
                except Exception as e_set_other:
                    print(f"Error setting variable for {key}: {e_set_other}")
        aac_br_var = settings_vars.get("globals", {}).get("advanced.conversion_flags.aac.audio_bitrate")
        if aac_br_var and isinstance(aac_br_var, tkinter.StringVar):
            aac_default_val = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["aac"]["audio_bitrate"]
            aac_current_br_from_settings = str(current_settings.get("globals", {}).get("advanced", {}).get("conversion_flags", {}).get("aac", {}).get("audio_bitrate", aac_default_val))
            aac_br_var.set(aac_current_br_from_settings)
        flac_cl_var = settings_vars.get("globals", {}).get("advanced.conversion_flags.flac.compression_level")
        if flac_cl_var and isinstance(flac_cl_var, tkinter.StringVar):
            flac_default_val = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["flac"]["compression_level"]
            flac_current_cl_from_settings = str(current_settings.get("globals", {}).get("advanced", {}).get("conversion_flags", {}).get("flac", {}).get("compression_level", flac_default_val))
            flac_cl_var.set(flac_current_cl_from_settings)
        mp3_setting_var = settings_vars.get("globals", {}).get("advanced.conversion_flags.mp3.setting")
        if mp3_setting_var and isinstance(mp3_setting_var, tkinter.StringVar):
            mp3_conf_flags_loaded = current_settings.get("globals", {}).get("advanced", {}).get("conversion_flags", {}).get("mp3", {})
            mp3_default_conf_flags_loaded = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["mp3"]
            
            resolved_display_val = None
            if isinstance(mp3_conf_flags_loaded, dict):
                if "audio_bitrate" in mp3_conf_flags_loaded and isinstance(mp3_conf_flags_loaded["audio_bitrate"], str) and mp3_conf_flags_loaded["audio_bitrate"].endswith('k'):
                    resolved_display_val = mp3_conf_flags_loaded["audio_bitrate"]
                elif "qscale:a" in mp3_conf_flags_loaded and mp3_conf_flags_loaded["qscale:a"] == "0":
                    resolved_display_val = "VBR -V0"
            if resolved_display_val is None:
                if "audio_bitrate" in mp3_default_conf_flags_loaded and isinstance(mp3_default_conf_flags_loaded["audio_bitrate"], str) and mp3_default_conf_flags_loaded["audio_bitrate"].endswith('k'):
                    resolved_display_val = mp3_default_conf_flags_loaded["audio_bitrate"]
                elif "qscale:a" in mp3_default_conf_flags_loaded and mp3_default_conf_flags_loaded["qscale:a"] == "0":
                    resolved_display_val = "VBR -V0"
            valid_mp3_ui_options = ["128k", "192k", "256k", "320k", "VBR -V0"]
            if resolved_display_val is None or resolved_display_val not in valid_mp3_ui_options:
                resolved_display_val = "VBR -V0"

            mp3_setting_var.set(resolved_display_val)

        if 'path_var_main' in globals() and isinstance(path_var_main, tkinter.Variable) and "general.output_path" not in settings_vars.get("globals", {}):
             main_path_val = current_settings.get("globals", {}).get("general", {}).get("output_path")
             if main_path_val is not None:
                  try: path_var_main.set(main_path_val)
                  except tkinter.TclError as e_set_main:
                      if "invalid command name" in str(e_set_main): pass
                      else: print(f"Error setting main path variable: {e_set_main}")
                  except Exception as e_set_main_other:
                      print(f"Error setting main path variable: {e_set_main_other}")
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print("Global Settings tab UI refresh finished.")
    except Exception as e: print(f"Error during Global settings UI refresh: {e}"); import traceback; traceback.print_exc()

def _create_credential_tab_content(platform_name, tab_frame):
    """Creates the labels and entry fields for a given platform's credentials."""
    global settings_vars, current_settings, DEFAULT_SETTINGS
    try:
        if 'settings_vars' not in globals() or 'credentials' not in settings_vars: settings_vars['credentials'] = {}
        if platform_name not in settings_vars['credentials']: settings_vars['credentials'][platform_name] = {}
        default_platform_fields = DEFAULT_SETTINGS.get("credentials", {}).get(platform_name, {})

        if not default_platform_fields:
            label = customtkinter.CTkLabel(tab_frame, text=f"No configurable credentials for {platform_name}.")
            label.pack(pady=10, padx=10)
            return

        for i, (key, value) in enumerate(default_platform_fields.items()):
            pady_config = (15, 2) if i == 0 else 2
            label_text = key.replace('_', ' ').title()
            label = customtkinter.CTkLabel(tab_frame, text=f"{label_text}:")
            label.grid(row=i, column=0, sticky="w", padx=10, pady=pady_config)
            
            current_value = current_settings.get("credentials", {}).get(platform_name, {}).get(key, value)

            if isinstance(value, bool):
                var = tkinter.BooleanVar(value=current_value)
                widget = customtkinter.CTkCheckBox(tab_frame, text="", variable=var)
                widget.grid(row=i, column=1, sticky="w", padx=10, pady=pady_config)
            else:
                var = tkinter.StringVar(value=str(current_value))
                widget = customtkinter.CTkEntry(tab_frame)
                widget.configure(textvariable=var)
                widget.grid(row=i, column=1, sticky="ew", padx=10, pady=pady_config)
                tab_frame.grid_columnconfigure(1, weight=1)
                widget.bind("<Button-3>", show_context_menu)
                widget.bind("<Button-2>", show_context_menu)
                widget.bind("<Control-Button-1>", show_context_menu)
                widget.bind("<FocusIn>", lambda e, w=widget: handle_focus_in(w))
                widget.bind("<FocusOut>", lambda e, w=widget: handle_focus_out(w))
            
            if platform_name not in settings_vars['credentials']:
                settings_vars['credentials'][platform_name] = {}
            settings_vars['credentials'][platform_name][key] = var
            if isinstance(var, (tkinter.StringVar, tkinter.BooleanVar)):
                var.trace_add('write', _auto_save_credential_change)
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.__stderr__)

def _handle_settings_tab_change():
    global loaded_credential_tabs, settings_tabview, credential_tabs_config
    selected_tab_name = settings_tabview.get()
    
    if selected_tab_name not in loaded_credential_tabs:
        for tab_name, tab_info in credential_tabs_config.items():
            if tab_name == selected_tab_name:
                _create_credential_tab_content(tab_name, tab_info['frame'])
                loaded_credential_tabs.add(tab_name)
                break

def update_search_platform_dropdown():
    """Updates the platform dropdown in the Search tab based on current settings AND installed modules."""
    global platform_combo, platform_var, current_settings, DEFAULT_SETTINGS, installed_platform_keys
    if not all(var in globals() for var in ['platform_combo', 'platform_var', 'current_settings', 'DEFAULT_SETTINGS', 'installed_platform_keys']):
        if not getattr(sys, 'frozen', False):
            print("[Update Platforms] Critical variables not found. Skipping update.")
        return

    if not platform_combo or not platform_combo.winfo_exists():
        if not getattr(sys, 'frozen', False):
            print("[Update Platforms] Platform combo widget not available. Skipping update.")
        return

    try:
        if not getattr(sys, 'frozen', False) and current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print("[Update Platforms] Refreshing Search tab platform dropdown...")
        
        base_available_platforms = [pk for pk in installed_platform_keys if pk != "Musixmatch"]
        configured_platforms = []

        for platform_name_iter in base_available_platforms:
            default_platform_fields = DEFAULT_SETTINGS.get("credentials", {}).get(platform_name_iter, {})
            if not default_platform_fields:
                configured_platforms.append(platform_name_iter)
                continue

            current_platform_creds = current_settings.get("credentials", {}).get(platform_name_iter, {})
            is_fully_filled = True
            for field_key in default_platform_fields.keys():
                field_value = current_platform_creds.get(field_key, "")                
                if isinstance(default_platform_fields[field_key], bool):
                    pass
                elif not str(field_value).strip():
                    is_fully_filled = False
                    break
            
            if is_fully_filled:
                configured_platforms.append(platform_name_iter)
        
        platforms_to_show = sorted(configured_platforms)
        
        current_selection = platform_var.get()
        platform_combo.configure(values=platforms_to_show)

        if platforms_to_show:
            if current_selection in platforms_to_show:
                platform_var.set(current_selection)
            else:
                platform_var.set(platforms_to_show[0])
        else:
            platform_var.set("")
        
        on_platform_change()

        if not getattr(sys, 'frozen', False) and current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print(f"[Update Platforms] Dropdown updated with: {platforms_to_show}. Selected: {platform_var.get()}")

    except tkinter.TclError as e:
        if "invalid command name" in str(e):
            if not getattr(sys, 'frozen', False):
                print(f"[Update Platforms] TclError (widget likely destroyed): {e}")
        else:
            if not getattr(sys, 'frozen', False):
                print(f"[Update Platforms] TclError: {e}")
    except Exception as e:
        if not getattr(sys, 'frozen', False):
            print(f"[Update Platforms] Unexpected error: {e}")
        import traceback
        if not getattr(sys, 'frozen', False):
            traceback.print_exc()

def _on_hyperlink_click(event):
    global log_textbox
    if 'log_textbox' not in globals() or not log_textbox or not log_textbox.winfo_exists():
        return
    try:
        index = log_textbox.index(f"@{event.x},{event.y}")
        
        tag_ranges = log_textbox.tag_ranges("hyperlink")
        
        clicked_url = None
        for i in range(0, len(tag_ranges), 2):
            start = tag_ranges[i]
            end = tag_ranges[i+1]
            if log_textbox.compare(index, ">=", start) and log_textbox.compare(index, "<", end):
                clicked_url = log_textbox.get(start, end)
                break
        
        if clicked_url:            
            if clicked_url.endswith('.') or clicked_url.endswith(')'):
                 if not any(char.isalnum() for char in clicked_url[-3:]):
                    clicked_url = clicked_url[:-1]

            print(f"Opening URL: {clicked_url}")
            webbrowser.open_new_tab(clicked_url)
    except Exception as e:
        print(f"Error opening hyperlink: {e}")

def _on_gui_exit():
    """Handles cleanup when the GUI is closing."""
    global app, _mutex_handle
    print("[Exit] GUI closing. Cleaning up temp directory...")
    try:
        shutil.rmtree('temp', ignore_errors=True)
        print("[Exit] Temp directory removed.")
    except Exception as e:
        print(f"[Exit] Error removing temp directory: {e}")
    if platform.system() == "Windows" and _mutex_handle:
        try:
            from ctypes import windll, wintypes
            CloseHandle = windll.kernel32.CloseHandle
            CloseHandle.argtypes = [wintypes.HANDLE]
            CloseHandle.restype = wintypes.BOOL
            if CloseHandle(_mutex_handle):
                print("[Instance Check] Released mutex.")
            else:
                print("[Instance Check] Failed to release mutex.")
            _mutex_handle = None
        except Exception as e:
            print(f"[Instance Check] Error releasing mutex: {e}")

    if 'app' in globals() and app and app.winfo_exists():
        app.destroy()
    print("[Exit] Application shutdown complete.")

def _setup_macos_window_management():
    """Sets up macOS-specific window management to handle minimize behavior."""
    global app
    
    if platform.system() != "Darwin":
        return
    global _is_window_minimized, _restore_timer_id
    _is_window_minimized = False
    _restore_timer_id = None
    
    def restore_window():
        """Restore the window from minimized state."""
        global _is_window_minimized, _restore_timer_id
        try:
            if _is_window_minimized:
                print("[macOS] Restoring window from minimized state")
                _is_window_minimized = False
                if _restore_timer_id:
                    app.after_cancel(_restore_timer_id)
                    _restore_timer_id = None
                app.deiconify()
                app.lift()
                app.focus_force()
        except Exception as e:
            print(f"[macOS] Error restoring window: {e}")
    
    def on_window_unmap(event=None):
        """Handle window unmap events (minimize/hide)."""
        global _is_window_minimized, _restore_timer_id
        
        if event and event.widget != app:
            return
        
        try:
            current_state = app.state()
            if current_state == 'iconic' and not _is_window_minimized:
                print("[macOS] Window minimized, switching to withdraw() to fix dock behavior")
                _is_window_minimized = True
                app.after_idle(lambda: app.withdraw())
                def check_for_restore():
                    global _restore_timer_id
                    if _is_window_minimized:
                        _restore_timer_id = app.after(200, check_for_restore)
                
                check_for_restore()
                
        except Exception as e:
            print(f"[macOS] Error in window unmap handler: {e}")
    
    def on_window_map(event=None):
        """Handle window map events (restore/show)."""
        global _is_window_minimized, _restore_timer_id
        
        if event and event.widget != app:
            return
            
        if _is_window_minimized:
            print("[macOS] Window mapped - restoring from minimized state")
            _is_window_minimized = False
            if _restore_timer_id:
                app.after_cancel(_restore_timer_id)
                _restore_timer_id = None
    
    def on_focus_in(event=None):
        """Handle window focus events."""
        global _is_window_minimized
        if _is_window_minimized and event and event.widget == app:
            restore_window()
    
    try:
        app.bind('<Unmap>', on_window_unmap)
        app.bind('<Map>', on_window_map)
        app.bind('<FocusIn>', on_focus_in)
        try:
            app.createcommand('::tk::mac::ReopenApplication', restore_window)
            print("[macOS] Added dock menu restore command")
        except Exception as menu_e:
            print(f"[macOS] Could not set up dock menu (normal on non-bundled apps): {menu_e}")
        
        print("[macOS] Window management setup complete")
        
    except Exception as e:
        print(f"[macOS] Error setting up window management: {e}")

def validate_codec_conversions():
    """Validate codec conversions to prevent circular references and duplicates."""
    global settings_vars
    
    try:
        codec_vars = settings_vars.get("globals", {}).get("advanced.codec_conversions", {})
        if not isinstance(codec_vars, dict):
            return True
        conversions = {}
        sources_used = set()
        
        for key, var in codec_vars.items():
            if key.endswith("_source") and isinstance(var, tkinter.StringVar):
                source_codec = var.get().lower().strip()
                target_key = key.replace("_source", "_target")
                
                if target_key in codec_vars and isinstance(codec_vars[target_key], tkinter.StringVar):
                    target_codec = codec_vars[target_key].get().lower().strip()
                    if not source_codec or not target_codec:
                        continue
                    if source_codec in sources_used:
                        show_centered_messagebox("Codec Conversion Error", 
                                                f"Duplicate source format '{source_codec}' detected!\nEach source format can only have one conversion rule.", 
                                                "error")
                        return False
                    
                    sources_used.add(source_codec)
                    conversions[source_codec] = target_codec
        for source, target in conversions.items():
            if target in conversions and conversions[target] == source and source != target:
                show_centered_messagebox("Codec Conversion Error", 
                                        f"Circular conversion detected!\n'{source}' → '{target}' and '{target}' → '{source}'\n\nThis would create an infinite loop. Please remove one of these conversions.", 
                                        "error")
                return False
        
        return True
        
    except Exception as e:
        print(f"Error validating codec conversions: {e}")
        return True

def browse_ffmpeg_path(path_variable):
    filetypes = [("All files", "*.*")]
    if platform.system() == "Windows":
        filetypes.insert(0, ("Executable files", "*.exe"))

    filepath = tkinter.filedialog.askopenfilename(
        initialdir=os.path.dirname(path_variable.get()) if path_variable.get() and path_variable.get() != "ffmpeg" else os.path.expanduser("~"),
        filetypes=filetypes,
        title="Select FFmpeg Executable"
    )
    if filepath:
        path_variable.set(filepath)

def run_download_in_subprocess(url, output_path, gui_settings, search_result_data, output_queue_mp):
    """Runs the download in a separate subprocess for complete GUI isolation."""
    import sys
    import os
    try:
        script_dir = get_script_directory()
        if script_dir and os.path.isdir(script_dir):
            os.chdir(script_dir)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
        import orpheus.core
        from orpheus.core import Orpheus
        from orpheus.music_downloader import Downloader
        from utils.models import Oprinter
        orpheus_subprocess = Orpheus()
        class SubprocessQueueWriter:
            def __init__(self, queue_ref):
                self.queue = queue_ref
            
            def write(self, msg):
                try:
                    self.queue.put(msg, timeout=1)
                except:
                    pass
            
            def flush(self):
                pass
        queue_writer = SubprocessQueueWriter(output_queue_mp)
        sys.stdout = queue_writer
        run_download_in_thread(orpheus_subprocess, url, output_path, gui_settings, search_result_data)
        
    except Exception as e:
        try:
            output_queue_mp.put(f"Subprocess error: {e}\n", timeout=1)
        except:
            pass

def final_download_cleanup(success=False):
    """Handles UI cleanup when download process completes."""
    global download_process_active, file_download_queue, current_batch_output_path, app
    
    try:
        download_process_active = False
        set_ui_state_downloading(False)
        if file_download_queue:
            next_url = file_download_queue.pop(0)
            print(f"Queueing next download from file: {next_url} ({len(file_download_queue)} remaining)")
            if current_batch_output_path:
                app.after(100, lambda u=next_url, p=current_batch_output_path: _start_single_download(u, p, None))
            else:
                print("[Error] Batch path missing.")
                file_download_queue.clear()
        else:
            if current_batch_output_path:
                print("File download queue is empty. Batch finished.")
                current_batch_output_path = None
        
        print(f"Download process completed. Success: {success}")
        
    except Exception as e:
        print(f"Error in download cleanup: {e}")
        download_process_active = False
        set_ui_state_downloading(False)

def run_download_in_thread_responsive(orpheus, url, output_path, gui_settings, search_result_data=None):
    """Runs the download with aggressive yielding to keep GUI responsive."""
    global output_queue, stop_event, app, download_process_active, DEFAULT_SETTINGS, _queue_log_handler_instance
    import time
    
    if _queue_log_handler_instance:
        _queue_log_handler_instance.reset_ffmpeg_state_for_current_download()

    if orpheus is None:
        logging.error("Orpheus instance not available. Cannot start download.")
        try:
            if 'app' in globals() and app and app.winfo_exists():
                 app.after(0, lambda: set_ui_state_downloading(False))
        except NameError: pass
        except Exception as e: logging.error(f"Error scheduling UI reset after Orpheus instance error: {e}")
        return
    def yield_to_gui(duration=0.001):
        time.sleep(duration)
        if 'app' in globals() and app:
            try:
                app.update_idletasks()
            except:
                pass

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    dummy_stderr = DummyStderr()
    is_cancelled = False
    download_exception_occurred = False
    start_time = datetime.datetime.now()
    media_type = None
    yield_to_gui(0.01)

    try:
        queue_writer = QueueWriter(output_queue, media_type=media_type)
        sys.stdout = queue_writer
        sys.stderr = dummy_stderr
        yield_to_gui()
        
        downloader_settings = {
            "general": {
                "download_path": gui_settings.get("globals", {}).get("general", {}).get("output_path", DEFAULT_SETTINGS["globals"]["general"]["output_path"]),
                "download_quality": gui_settings.get("globals", {}).get("general", {}).get("quality", DEFAULT_SETTINGS["globals"]["general"]["quality"]),
                "search_limit": gui_settings.get("globals", {}).get("general", {}).get("search_limit", DEFAULT_SETTINGS["globals"]["general"]["search_limit"]),
                "progress_bar": False
            },
            **{k: v for k, v in gui_settings.get("globals", {}).items() if k != "general"}
        }
        
        yield_to_gui()
        def yielding_download():
            return run_download_in_thread(orpheus, url, output_path, gui_settings, search_result_data)
        download_result = yielding_download()
        
    except Exception as e:
        print(f"Error in responsive download: {e}")
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        def final_cleanup():
            global download_process_active
            download_process_active = False
            set_ui_state_downloading(False)
        
        try:
            if 'app' in globals() and app and app.winfo_exists():
                app.after(0, final_cleanup)
        except:
            final_cleanup()

def _auto_save_credential_change(*args):
    """Callback to save settings when a credential value changes."""
    save_settings(show_confirmation=False)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    _mutex_handle = None
    if platform.system() == "Windows":
        try:
            from ctypes import windll, wintypes

            ERROR_ALREADY_EXISTS = 183
            mutex_name = "OrpheusDL_GUI_Instance_Mutex_8E1D3B4C_A5F8_4B9A_8D7C_6F0A1B3E4D5C"
            CreateMutexW = windll.kernel32.CreateMutexW
            CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            CreateMutexW.restype = wintypes.HANDLE
            GetLastError = windll.kernel32.GetLastError
            GetLastError.restype = wintypes.DWORD
            _mutex_handle = CreateMutexW(None, True, mutex_name)

            last_error = GetLastError()

            if last_error == ERROR_ALREADY_EXISTS:
                print("[Instance Check] Mutex already exists. Another instance is running. Exiting.")
                sys.exit()
            elif _mutex_handle is None or _mutex_handle == 0:
                print(f"[Instance Check] Failed to create mutex. Error code: {last_error}")
                sys.exit("Error creating application mutex.")
            else:
                print("[Instance Check] Acquired mutex. This is the first instance.")

        except ImportError:
             print("[Instance Check] Warning: Could not import ctypes/windll. Single instance check skipped.")
        except Exception as e:
            print(f"[Instance Check] Error during single instance check: {e}")
            sys.exit("Failed single instance check.")
    if multiprocessing.parent_process() is None:
        print(f"[Main Process {os.getpid()}] Starting application...")
        _SCRIPT_DIR = get_script_directory()
        try:
            os.makedirs(os.path.join(_SCRIPT_DIR if _SCRIPT_DIR and os.path.isdir(_SCRIPT_DIR) else os.getcwd(), 'temp'), exist_ok=True)
            print("[Init] Ensured temp directory exists.")
            if _SCRIPT_DIR and os.path.isdir(_SCRIPT_DIR):
                os.chdir(_SCRIPT_DIR)
                print(f"[CWD] Changed working directory to: {_SCRIPT_DIR}")
            elif _SCRIPT_DIR:
                print(f"[CWD] FATAL: _SCRIPT_DIR \'{_SCRIPT_DIR}\' is not a valid directory. Application might fail.")
                if 'show_centered_messagebox' in globals() and callable(show_centered_messagebox):
                    show_centered_messagebox("Critical Path Error", f"Application base directory \'{_SCRIPT_DIR}\' is invalid. Cannot continue.", dialog_type="error")
                else:
                    tkinter.messagebox.showerror("Critical Path Error", f"Application base directory \'{_SCRIPT_DIR}\' is invalid. Cannot continue.")
                sys.exit(1)
            else:
                print(f"[CWD] FATAL: _SCRIPT_DIR could not be determined. Application will likely fail.")
                if 'show_centered_messagebox' in globals() and callable(show_centered_messagebox):
                    show_centered_messagebox("Critical Path Error", "Could not determine application base directory. Cannot continue.", dialog_type="error")
                else:
                    tkinter.messagebox.showerror("Critical Path Error", "Could not determine application base directory. Cannot continue.")
                sys.exit(1)
        except Exception as e_chdir:
            print(f"[CWD] Warning: Failed to change working directory or create temp: {e_chdir}")

        CONFIG_DIR = os.path.join(_SCRIPT_DIR, 'config')
        MODULES_DIR = os.path.join(_SCRIPT_DIR, 'modules')
        CONFIG_FILE_NAME = 'settings.json'
        CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)
        if os.path.isdir(MODULES_DIR):
            if MODULES_DIR not in sys.path:
                sys.path.insert(0, MODULES_DIR)
                print(f"[SysPath] Added external modules directory: {MODULES_DIR}")
            else:
                print(f"[SysPath] External modules directory already in sys.path: {MODULES_DIR}")
        else:
            print(f"[SysPath] External modules directory not found: {MODULES_DIR}")
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            os.makedirs(MODULES_DIR, exist_ok=True)
            print(f"[Init] Ensured config directory exists: {CONFIG_DIR}")
            print(f"[Init] Ensured modules directory exists: {MODULES_DIR}")
        except OSError as e:
            print(f"[Error] Could not create config/data/modules directories: {e}")
        DEFAULT_SETTINGS = {
            "globals": {
                "general": {
                    "output_path": os.path.join(_SCRIPT_DIR, "Downloads"),
                    "quality": "hifi",
                    "search_limit": 20,
                    "concurrent_downloads": 5,
                    "play_sound_on_finish": True
                },
                "artist_downloading": { "return_credited_albums": True, "separate_tracks_skip_downloaded": True },
                "formatting": { "album_format": "{name}{explicit}", "playlist_format": "{name}{explicit}", "track_filename_format": "{track_number}. {name}", "single_full_path_format": "{name}", "enable_zfill": True, "force_album_format": False },
                "codecs": {
                    "proprietary_codecs": False,
                    "spatial_codecs": True
                },
                "module_defaults": { "lyrics": "default", "covers": "default", "credits": "default" },
                "lyrics": { "embed_lyrics": True, "embed_synced_lyrics": False, "save_synced_lyrics": True },
                "covers": { "embed_cover": True, "main_compression": "high", "main_resolution": 1400, "save_external": False, "external_format": "png", "external_compression": "low", "external_resolution": 3000, "save_animated_cover": True },
                "playlist": { "save_m3u": True, "paths_m3u": "absolute", "extended_m3u": True },
                "advanced": {
                    "advanced_login_system": False,
                    "codec_conversions": { "alac": "flac", "wav": "flac", "vorbis": "vorbis" }, 
                    "conversion_flags": {
                        "flac": { "compression_level": 5 },
                        "mp3": { "qscale:a": "0" },
                        "aac": { "audio_bitrate": "256k" }
                    },
                    "conversion_keep_original": False,
                    "ffmpeg_path": "ffmpeg",
                    "cover_variance_threshold": 8,
                    "debug_mode": False,
                    "disable_subscription_checks": False,
                    "enable_undesirable_conversions": False,
                    "ignore_existing_files": False,
                    "ignore_different_artists": True
                }
            },
            "credentials": {
                "AppleMusic": { "cookies_path": "./config/cookies.txt", "language": "en-US", "codec": "aac", "quality": "high" },
                "Beatport": { "username": "", "password": "" },
                "Beatsource": { "username": "", "password": "" },
                "Bugs": { "username": "", "password": "" },
                "Deezer": { "client_id": "", "client_secret": "", "bf_secret": "", "email": "", "password": "" },
                "Idagio": { "username": "", "password": "" }, 
                "KKBOX": { "kc1_key": "", "secret_key": "", "email": "", "password": "" },
                "Musixmatch": { "token_limit": 10, "lyrics_format": "standard", "custom_time_decimals": False },
                "Napster": { "api_key": "", "customer_secret": "", "requested_netloc": "", "username": "", "password": "" },
                "Nugs": { "username": "", "password": "", "client_id": "", "dev_key": "" },
                "Qobuz": { "app_id": "", "app_secret": "", "quality_format": "{sample_rate}kHz {bit_depth}bit", "username": "", "password": "" },
                "SoundCloud": { "web_access_token": "" },
                "Spotify": { "username": "", "download_pause_seconds": 30 },
                "Tidal": { "tv_atmos_token": "", "tv_atmos_secret": "", "mobile_atmos_hires_token": "", "mobile_hires_token": "", "enable_mobile": True, "prefer_ac4": False, "fix_mqa": True }
            }
        }
        installed_platform_keys = []
        if os.path.isdir(MODULES_DIR):
            try:                
                module_subdirs_in_dir = [d.lower() for d in os.listdir(MODULES_DIR) if os.path.isdir(os.path.join(MODULES_DIR, d))]
                
                default_credential_platform_names = list(DEFAULT_SETTINGS.get("credentials", {}).keys())

                for platform_key in default_credential_platform_names:
                    expected_subdir_name = platform_key.lower()
                    
                    if expected_subdir_name in module_subdirs_in_dir:
                        installed_platform_keys.append(platform_key)
                
                installed_platform_keys = sorted(list(set(installed_platform_keys)))
                print(f"[Module Check] Detected installed platform keys based on './modules/' subfolders: {installed_platform_keys}")
            except Exception as e:
                print(f"[Module Check] Error scanning './modules/' subdirectories: {e}. Proceeding with empty list.")
                installed_platform_keys = []
        else:
            print(f"[Module Check] Modules directory '{MODULES_DIR}' not found. No external modules will be loaded.")
            installed_platform_keys = []        
        output_queue = queue.Queue()
        stop_event = threading.Event()
        search_results_data = []
        sort_states = {}
        search_process_active = False
        download_process_active = False
        _last_message_was_empty = False
        _download_cancelled = False
        _created_credential_tabs = set()
        credential_tab_frames = {}
        _context_menu = None
        _target_widget = None
        patch_download_file_for_cancellation()
        print("[Patch] Enabled improved download cancellation")
        _hide_menu_binding_id = None
        BUTTON_COLOR = ("#E0E0E0", "#303030")
        BORDER = "#565B5E"
        current_settings = {}
        settings_vars = {"globals": {}, "credentials": {}}
        orpheus_instance = None
        try:
            load_settings()
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG] After load_settings: output_path = {current_settings.get('globals', {}).get('general', {}).get('output_path')}")
            initialize_orpheus()
        except FileNotFoundError as e:
             print(f"Initialization failed: {e}")
             sys.exit(1)
        except Exception as e:
             print(f"Unexpected error during initialization: {e}")
        if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
            print(f"[DEBUG] Before GUI setup: output_path = {current_settings.get('globals', {}).get('general', {}).get('output_path')}")
        app = customtkinter.CTk()
        app.title("OrpheusDL GUI")
        app.geometry("940x600")
        try:
            icon_filename = "icon.icns" if platform.system() == "Darwin" else "icon.ico"
            icon_path = resource_path(icon_filename)
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"Looking for main window icon at: {icon_path}")
            if os.path.exists(icon_path):
                if platform.system() != "Darwin":
                    app.iconbitmap(icon_path)
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print(f"Set window icon from: {icon_path}")
                else:
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print("Skipping app.iconbitmap on macOS (use .icns for app bundle/dock).")
            else:
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"Window icon file not found: {icon_path}")
        except Exception as e:
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"Error setting window icon: {e}")
        screen_width = app.winfo_screenwidth()
        screen_height = app.winfo_screenheight()
        window_width = 940
        window_height = 600
        x_pos = (screen_width // 2) - (window_width // 2)
        y_pos = (screen_height // 2) - (window_height // 2)
        app.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

        global loaded_credential_tabs, credential_tabs_config
        loaded_credential_tabs = {"Global"}
        credential_tabs_config = {}

        def _on_tab_change():
            selected_tab = tabview.get()
            if selected_tab == "Search":
                if 'update_search_platform_dropdown' in globals() and callable(update_search_platform_dropdown):
                    app.after(10, update_search_platform_dropdown)
            elif selected_tab == "Settings":
                if 'settings_tabview' in globals() and settings_tabview and settings_tabview.winfo_exists() and '_handle_settings_tab_change' in globals() and callable(_handle_settings_tab_change):
                     app.after(10, _handle_settings_tab_change)

        tabview = customtkinter.CTkTabview(master=app, command=_on_tab_change)
        tabview.pack(padx=10, pady=10, expand=True, fill="both")
        download_tab = tabview.add("Download")
        download_tab.grid_columnconfigure(1, weight=1); download_tab.grid_rowconfigure(2, weight=1)
        url_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); url_frame.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(15,5)); url_frame.grid_columnconfigure(1, weight=1)
        url_label = customtkinter.CTkLabel(url_frame, text="Input"); url_label.grid(row=0, column=0, sticky="w", padx=5)
        url_entry = customtkinter.CTkEntry(url_frame, placeholder_text="Enter URL or text-file (e.g. urls.txt)...", height=30, placeholder_text_color="#7F7F7F"); url_entry.grid(row=0, column=1, sticky="ew", padx=5)
        url_entry.bind("<Return>", lambda event: start_download_thread()); url_entry.bind("<Button-3>", show_context_menu); url_entry.bind("<Button-2>", show_context_menu); url_entry.bind("<Control-Button-1>", show_context_menu)
        url_entry.bind("<FocusIn>", lambda e, w=url_entry: handle_focus_in(w))
        url_entry.bind("<FocusOut>", lambda e, w=url_entry: handle_focus_out(w))
        clear_url_button = customtkinter.CTkButton(url_frame, text="Clear", width=100, height=30, command=clear_url_entry, fg_color="#343638", hover_color="#1F6AA5"); clear_url_button.grid(row=0, column=2, sticky="e", padx=5)
        download_button = customtkinter.CTkButton(url_frame, text="Download", width=100, height=30, command=start_download_thread, fg_color="#343638", hover_color="#1F6AA5"); download_button.grid(row=0, column=3, sticky="e", padx=5)
        path_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); path_frame.grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=5); path_frame.grid_columnconfigure(1, weight=1)
        path_label = customtkinter.CTkLabel(path_frame, text="Output Path"); path_label.grid(row=0, column=0, sticky="w", padx=5)
        path_var_main = tkinter.StringVar(value=current_settings.get("globals", {}).get("general", {}).get("output_path", DEFAULT_SETTINGS["globals"]["general"]["output_path"]))
        path_var_main.trace_add("write", _auto_save_path_change)
        path_entry = customtkinter.CTkEntry(path_frame, textvariable=path_var_main, height=30); path_entry.grid(row=0, column=1, sticky="ew", padx=5)
        path_entry.bind("<Button-3>", show_context_menu); path_entry.bind("<Button-2>", show_context_menu); path_entry.bind("<Control-Button-1>", show_context_menu)
        path_entry.bind("<FocusIn>", lambda e, w=path_entry: handle_focus_in(w))
        path_entry.bind("<FocusOut>", lambda e, w=path_entry: handle_focus_out(w))
        path_button = customtkinter.CTkButton(path_frame, text="Browse", width=100, height=30, command=lambda: browse_output_path(path_var_main), fg_color="#343638", hover_color="#1F6AA5"); path_button.grid(row=0, column=2, sticky="e", padx=5)
        open_path_button = customtkinter.CTkButton(path_frame, text="Open", width=100, height=30, command=open_download_path, fg_color="#343638", hover_color="#1F6AA5"); open_path_button.grid(row=0, column=3, sticky="e", padx=5)
        output_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); output_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=15, pady=(15, 15)); output_frame.grid_rowconfigure(1, weight=1); output_frame.grid_columnconfigure(0, weight=1)
        output_label = customtkinter.CTkLabel(output_frame, text="OUTPUT", text_color="#898c8d", font=("Segoe UI", 11)); output_label.grid(row=0, column=0, sticky="w", pady=(0, 3)) 
        textbox_container = customtkinter.CTkFrame(output_frame, fg_color="#1D1E1E"); textbox_container.grid(row=1, column=0, sticky="nsew"); textbox_container.grid_columnconfigure(0, weight=1); textbox_container.grid_rowconfigure(0, weight=1); textbox_container.grid_columnconfigure(1, weight=0)  
        current_os = platform.system()
        if current_os == "Windows":
            log_font_family = "Consolas"
            log_font_size = 10
        elif current_os == "Darwin":
            log_font_family = "Menlo"
            log_font_size = 12
        else:
            log_font_family = "DejaVu Sans Mono"
            log_font_size = 11
        log_font = (log_font_family, log_font_size)

        log_textbox = tkinter.Text(textbox_container, wrap=tkinter.WORD, state='disabled', font=log_font, 
                                   bg="#1D1E1E", fg="#DCE4EE", insertbackground="#DCE4EE", 
                                   selectbackground="#1F6AA5", selectforeground="#FFFFFF",
                                   relief="flat", borderwidth=0, highlightthickness=0)
        log_textbox.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=3)
        log_scrollbar = customtkinter.CTkScrollbar(textbox_container, command=log_textbox.yview); log_textbox.configure(yscrollcommand=log_scrollbar.set)
        log_textbox.bind("<Configure>", lambda event: _check_and_toggle_text_scrollbar(log_textbox, log_scrollbar) if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists() and 'log_scrollbar' in globals() and log_scrollbar and log_scrollbar.winfo_exists() else None)
        bottom_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); bottom_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(5, 10)); bottom_frame.grid_columnconfigure(0, weight=1)
        progress_bar = customtkinter.CTkProgressBar(bottom_frame); progress_bar.set(0); progress_bar.grid(row=0, column=0, sticky="ew", padx=(5, 5))
        clear_output_button = customtkinter.CTkButton(bottom_frame, text="Clear Output", width=100, height=30, command=clear_output_log, fg_color="#343638", hover_color="#1F6AA5"); clear_output_button.grid(row=0, column=1, sticky="e", padx=(5, 10))
        stop_button = customtkinter.CTkButton(bottom_frame, text="Stop", width=100, height=30, command=stop_download, fg_color="#343638", hover_color="#1F6AA5", state=tkinter.DISABLED); stop_button.grid(row=0, column=2, sticky="e", padx=(0, 5))
        search_tab = tabview.add("Search"); search_main_frame = customtkinter.CTkFrame(search_tab, fg_color="transparent"); search_main_frame.pack(fill="both", expand=True, padx=9, pady=(10,0))
        controls_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); controls_frame.pack(fill="x", pady=(5, 10)); controls_frame.grid_columnconfigure(4, weight=1)
        customtkinter.CTkLabel(controls_frame, text="Platform").grid(row=0, column=0, padx=(5,1), sticky="w")
        search_tab_initial_platforms = [pk for pk in installed_platform_keys if pk != "Musixmatch"]
        platform_var = tkinter.StringVar(value=search_tab_initial_platforms[0] if search_tab_initial_platforms else ""); 
        platform_combo = customtkinter.CTkComboBox(controls_frame, values=search_tab_initial_platforms, variable=platform_var, width=140, state="readonly", height=30, dropdown_fg_color="#2B2B2B"); 
        platform_combo.grid(row=0, column=1, padx=(5, 6)); 
        platform_var.trace_add("write", on_platform_change)
        customtkinter.CTkLabel(controls_frame, text="Type").grid(row=0, column=2, padx=(5,5), sticky="w"); type_var = tkinter.StringVar(); type_combo = customtkinter.CTkComboBox(controls_frame, values=[], variable=type_var, width=100, state="readonly", height=30, dropdown_fg_color="#2B2B2B"); type_combo.grid(row=0, column=3, padx=(2, 1), sticky="w")
        search_input_frame = customtkinter.CTkFrame(controls_frame, fg_color="transparent"); search_input_frame.grid(row=0, column=4, sticky="ew", padx=(10, 5))
        search_entry = customtkinter.CTkEntry(search_input_frame, placeholder_text="Enter search query...", height=30, placeholder_text_color="#7F7F7F"); search_entry.pack(side="left", fill="x", expand=True, padx=(0, 0))
        search_entry.bind("<Return>", lambda e: start_search()); search_entry.bind("<Button-3>", show_context_menu); search_entry.bind("<Button-2>", show_context_menu); search_entry.bind("<Control-Button-1>", show_context_menu)
        search_entry.bind("<FocusIn>", lambda e, w=search_entry: handle_focus_in(w))
        search_entry.bind("<FocusOut>", lambda e, w=search_entry: handle_focus_out(w))
        clear_search_button = customtkinter.CTkButton(search_input_frame, text="Clear", command=clear_search_entry, width=100, height=30, fg_color="#343638", hover_color="#1F6AA5"); clear_search_button.pack(side="left", padx=(10, 0))
        button_search_frame = customtkinter.CTkFrame(controls_frame, fg_color="transparent"); button_search_frame.grid(row=0, column=5, padx=(5,0))
        search_button = customtkinter.CTkButton(button_search_frame, text="Search", command=start_search, width=100, height=30, fg_color="#343638", hover_color="#1F6AA5"); search_button.pack(side="left", padx=(0, 6))
        update_search_types(platform_var.get())
        results_outer_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); results_outer_frame.pack(fill="both", expand=True, pady=(8,8))
        results_label = customtkinter.CTkLabel(results_outer_frame, text="RESULTS", text_color="#898c8d", font=("Segoe UI", 11)); results_label.pack(anchor="w", padx=6, pady=0)
        treeview_container = customtkinter.CTkFrame(results_outer_frame, fg_color="#1D1E1E"); treeview_container.pack(fill="both", expand=True, padx=6, pady=(3,0)); treeview_container.grid_columnconfigure(0, weight=1); treeview_container.grid_rowconfigure(0, weight=1); treeview_container.grid_columnconfigure(1, weight=0)
        style = ttk.Style();
        try: style.theme_use('clam')
        except Exception: print("Clam theme not available.")
        heading_font_config = None

        if platform.system() == "Windows":
            try:
                scaling_factor = app.tk.call('tk', 'scaling')
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"[Style] Detected scaling factor: {scaling_factor}")
            except Exception as e:
                print(f"[Style] Error getting scaling factor: {e}. Defaulting to 1.0")
                scaling_factor = 1.0
            if scaling_factor > 1.5:
                base_font_size = 6
            else:
                base_font_size = 7

            scaled_font_size = max(8, round(base_font_size * scaling_factor))
            if scaling_factor > 1.5:
                row_height_multiplier = 3.4
            else:
                row_height_multiplier = 2.9

            scaled_row_height = max(20, round(scaled_font_size * row_height_multiplier))
            tree_font_family = "Segoe UI"
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[Style Windows] Using font: {tree_font_family} {scaled_font_size}pt (Scaled from {base_font_size}pt), Row height: {scaled_row_height}px")
            heading_font_config = (tree_font_family, scaled_font_size)

        else:
            scaled_font_size = 13
            scaled_row_height = max(20, round(scaled_font_size * 2.2))
            tree_font_family = None
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[Style Non-Windows] Using system default font, Row height: {scaled_row_height}px")
            heading_font_config = (None, 10, 'normal')
        tree_bg_color = "#1D1E1E"; tree_fg_color = "#DCE4EE"; tree_header_bg = "#1D1E1E"; tree_header_fg = "gray"; tree_selected_bg = "#1F6AA5"; tree_selected_fg = "#FFFFFF"
        style.configure("Custom.Treeview",
                        background=tree_bg_color,
                        foreground=tree_fg_color,
                        fieldbackground=tree_bg_color,
                        borderwidth=0,
                        relief="flat",
                        rowheight=scaled_row_height)
        if platform.system() == "Windows":
            style.configure("Custom.Treeview", font=(tree_font_family, scaled_font_size))
        style.configure("Custom.Treeview.Heading",
                        background=tree_header_bg,
                        foreground=tree_header_fg,
                        borderwidth=0,
                        relief="flat",
                        padding=(5, 3))
        if heading_font_config:
            style.configure("Custom.Treeview.Heading", font=heading_font_config)

        style.layout("Custom.Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        style.map("Custom.Treeview", background=[('selected', tree_selected_bg)], foreground=[('selected', tree_selected_fg)])
        style.map("Custom.Treeview.Heading", background=[('active', "#1F6AA5"), ('!active', tree_header_bg)], foreground=[('active', tree_selected_fg), ('!active', tree_header_fg)])
        columns = ("#", "Title", "Artist", "Duration", "Year", "Additional", "Explicit", "ID"); tree = ttk.Treeview(treeview_container, columns=columns, show="headings", selectmode="extended", style="Custom.Treeview"); tree.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=3)
        col_configs = {"#": {"text": "#", "width": 40, "anchor": "w"}, "Title": {"text": "Title", "width": 300, "anchor": "w"}, "Artist": {"text": "Artist", "width": 200, "anchor": "w"}, "Duration": {"text": "Duration", "width": 80, "anchor": "center"}, "Year": {"text": "Year", "width": 60, "anchor": "center"}, "Additional": {"text": "Additional", "width": 120, "anchor": "w"}, "Explicit": {"text": "E", "width": 30, "anchor": "center"}, "ID": {"text": "ID", "width": 0, "anchor": "w"}}
        for col in columns: cfg = col_configs[col]; tree.heading(col, text=cfg["text"], anchor=cfg["anchor"], command=lambda c=col: sort_results(c)); tree.column(col, width=cfg["width"], anchor=cfg["anchor"], stretch=False)
        tree.column("Title", stretch=True); tree.column("Artist", stretch=True)
        scrollbar = customtkinter.CTkScrollbar(treeview_container, command=tree.yview); tree.configure(yscrollcommand=scrollbar.set)
        tree.bind("<<TreeviewSelect>>", on_tree_select); tree.bind("<Configure>", lambda event: _check_and_toggle_scrollbar(tree, scrollbar) if 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists() else None)
        if platform.system() == "Darwin":
            def handle_macos_click(event):
                """Handle macOS-specific multi-selection with Command/Shift keys."""
                item = tree.identify_row(event.y)
                if not item:
                    return
                if event.state & 0x8:
                    if item in tree.selection():
                        tree.selection_remove(item)
                    else:
                        tree.selection_add(item)
                    return "break"
                elif event.state & 0x1:
                    current_selection = tree.selection()
                    if current_selection:
                        all_items = tree.get_children()
                        try:
                            last_selected = current_selection[-1]
                            start_idx = all_items.index(last_selected)
                            end_idx = all_items.index(item)
                            if start_idx > end_idx:
                                start_idx, end_idx = end_idx, start_idx
                            tree.selection_set(all_items[start_idx:end_idx + 1])
                        except (ValueError, IndexError):
                            tree.selection_set(item)
                    else:
                        tree.selection_set(item)
                    return "break"
                tree.selection_set(item)
                return "break"
            tree.bind("<Button-1>", handle_macos_click)
        selection_label_var = tkinter.StringVar(value="Selection: None")
        selection_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); selection_frame.pack(fill="x", pady=(12, 10), side="bottom")
        search_progress_bar = customtkinter.CTkProgressBar(selection_frame); search_progress_bar.pack(side="left", fill="x", expand=True, padx=(6, 5)); search_progress_bar.set(0)
        selection_controls_frame = customtkinter.CTkFrame(selection_frame, fg_color="transparent"); selection_controls_frame.pack(side="right")
        customtkinter.CTkLabel(selection_controls_frame, text="Selection").pack(side="left", padx=(8, 6)); selection_var = tkinter.StringVar(); selection_entry = customtkinter.CTkEntry(selection_controls_frame, textvariable=selection_var, width=35, height=30); selection_entry.pack(side="left", padx=4); selection_var.trace_add("write", on_selection_change)
        selection_entry.bind("<FocusIn>", lambda e, w=selection_entry: handle_focus_in(w))
        selection_entry.bind("<FocusOut>", lambda e, w=selection_entry: handle_focus_out(w))
        search_download_button = customtkinter.CTkButton(selection_controls_frame, text="Download", command=download_selected, width=100, height=30, state="disabled", fg_color="#343638", hover_color="#1F6AA5"); search_download_button.pack(side="left", padx=(5, 6))
        settings_tab = tabview.add("Settings")
        settings_tabview = customtkinter.CTkTabview(master=settings_tab, command=_handle_settings_tab_change)
        settings_tabview.pack(expand=True, fill="both", padx=5, pady=5)
        global_settings_tab = settings_tabview.add("Global")
        global_settings_frame = customtkinter.CTkScrollableFrame(global_settings_tab)
        global_settings_frame.pack(expand=True, fill="both", padx=0, pady=(0, 5))
        global_settings_frame.grid_columnconfigure(1, weight=1)
        global_settings_frame.grid_columnconfigure(0, uniform="settings_label_column")
        global_settings_frame.grid_columnconfigure(2, weight=0)
        row = 0
        tooltip_texts = {
            "general.output_path": "The main folder where all downloads will be saved.",
            "general.quality": "Select the desired audio quality preference.",
            "general.search_limit": "Maximum number of results to display in the Search tab.",
            "general.concurrent_downloads": "Number of tracks to download simultaneously (1-10).\n\nRecommended values:\n• 1-3: Slower systems, limited bandwidth\n• 4-6: Most systems (balanced speed/stability)\n• 7-10: High-end systems, fast internet.",
            "general.play_sound_on_finish": "Play a notification sound when a download completes.",
            "artist_downloading.return_credited_albums": "Include albums where the artist is credited but not the main artist.",
            "artist_downloading.separate_tracks_skip_downloaded": "When downloading artists, skip tracks that are part of albums already downloaded.",
            "formatting.album_format": """Folder structure for albums. Variables:
 {name}, {id}, {artist}, {artist_id}, {release_year}, {upc}, {explicit}, {quality}, {artist_initials}""",
            "formatting.playlist_format": """Folder structure for playlists. Variables:
 {name}, {creator}, {tracks}, {release_year}, {explicit}, {creator_id}""",
            "formatting.track_filename_format": """Filename format for tracks. Variables:
 {track_number}, {total_tracks}, {disc_number}, {total_discs}, {name}, {id}, {album},
 {album_id}, {artist}, {artist_id}, {isrc}, {release_year}, {explicit}, {quality}, {artist_initials}""",
            "formatting.single_full_path_format": """Full path format (folder + filename) for single tracks not part of an album download.\nUses same variables as Track Filename Format.""",
            "formatting.enable_zfill": "Pads track/disc numbers with leading zeros (e.g., 01, 02).",
            "formatting.force_album_format": "Use the album_format structure even for single track downloads.",
            "codecs.proprietary_codecs": "Enable potentially proprietary codecs like MQA (if supported by module).",
            "codecs.spatial_codecs": "Enable spatial audio codecs like Dolby Atmos (if supported by module).",
            "module_defaults.lyrics": "Default module to use for fetching lyrics.",
            "module_defaults.covers": "Default module to use for fetching cover art.",
            "module_defaults.credits": "Default module to use for fetching track credits.",
            "lyrics.embed_lyrics": "Embed standard (unsynced) lyrics into the audio file.",
            "lyrics.embed_synced_lyrics": "Embed synced (LRC) lyrics into the audio file (requires embed_lyrics).",
            "lyrics.save_synced_lyrics": "Save synced lyrics as a separate .lrc file alongside the track.",
            "covers.embed_cover": "Embed the main cover art into the audio file.",
            "covers.main_compression": "Compression level for embedded/saved main cover art.",
            "covers.main_resolution": "Maximum resolution (pixels) for the main cover art.",
            "covers.save_external": "Save cover art from a third-party module (if configured).",
            "covers.external_format": "Format for the saved external cover art.",
            "covers.external_compression": "Compression level for the saved external cover art.",
            "covers.external_resolution": "Maximum resolution (pixels) for the saved external cover art.",
            "covers.save_animated_cover": "Save animated cover art (GIF/MP4) if available.",
            "playlist.save_m3u": "Create an M3U playlist file for playlist downloads.",
            "playlist.paths_m3u": "Select 'relative' or 'absolute' paths in M3U file.",
            "playlist.extended_m3u": "Include extended info like track length in M3U file.",
            "advanced.advanced_login_system": "Enable advanced login system (Use only if instructed by module documentation).",
            "advanced.ffmpeg_path": "Full path to the ffmpeg executable \nIf set to just 'ffmpeg', it's assumed to be in the system PATH.\nThis is used for codec conversions.",
            "advanced.codec_conversions": "Defines custom codec conversions (e.g., alac to flac). Enter source format on the left, target on the right.",
            "advanced.conversion_keep_original": "Keep the original file after successful codec conversion.",
            "advanced.cover_variance_threshold": "Tolerance for accepting covers with slightly different sizes (0-100).",
            "advanced.debug_mode": "Allows various detailed informational and diagnostic messages to be printed to the console.\nIntended for troubleshooting issues only.",
            "advanced.disable_subscription_checks": "Prevents from checking if subscription for music service you are trying to download from is active.",
            "advanced.enable_undesirable_conversions": """Controls allowance to perform codec conversions that might result in quality loss or are not recommended.
Examples:
Lossy-to-Lossy
Lossless-to-Lossy (if not preferred)
Unnecessary Lossless-to-Lossless""",
            "advanced.ignore_existing_files": "Skips downloading files, if a file with the target name already exists in the output directory.",
            "advanced.ignore_different_artists": "When downloading albums, ignore tracks where the artist differs from the main album artist.",
            "advanced.conversion_flags.aac.audio_bitrate": "Set AAC audio bitrate. Higher is better quality but larger file. Options: 128k, 192k, 256k, 320k.",
            "advanced.conversion_flags.flac.compression_level": "Set FLAC compression level (0-8). Higher level means smaller file but slower encoding, 0 is fastest, 8 is smallest."
        }
        for section_key, section_value in DEFAULT_SETTINGS["globals"].items():
            if isinstance(section_value, dict):
                customtkinter.CTkLabel(global_settings_frame, text=section_key.replace("_", " ").upper(), text_color="#898c8d", font=("Segoe UI", 11)).grid(row=row, column=0, columnspan=3, sticky="w", padx=(0, 10), pady=(10, 5)); row += 1
                for field, default_value in section_value.items():
                    current_value = current_settings["globals"].get(section_key, {}).get(field, default_value); full_key = f"{section_key}.{field}"
                    if full_key == "advanced.conversion_flags":
                        aac_label_text = "AAC Audio Bitrate"
                        aac_full_key = "advanced.conversion_flags.aac.audio_bitrate"
                        aac_default_val = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["aac"]["audio_bitrate"]
                        aac_current_val = str(current_settings["globals"].get("advanced", {}).get("conversion_flags", {}).get("aac", {}).get("audio_bitrate", aac_default_val))
                        
                        customtkinter.CTkLabel(global_settings_frame, text=aac_label_text).grid(row=row, column=0, sticky="w", padx=(20, 10), pady=2)
                        aac_slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                        aac_slider_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
                        aac_slider_frame.grid_columnconfigure(0, weight=1)

                        aac_options_list = ["128k", "192k", "256k", "320k"]
                        aac_options_map = {val: i for i, val in enumerate(aac_options_list)}
                        
                        aac_var = tkinter.StringVar(value=aac_current_val)
                        if "globals" not in settings_vars: settings_vars["globals"] = {}
                        settings_vars["globals"][aac_full_key] = aac_var
                        
                        aac_value_disp_label = customtkinter.CTkLabel(aac_slider_frame, text=aac_current_val, width=70, anchor="e")
                        aac_value_disp_label.grid(row=0, column=1, sticky="e")

                        def _update_aac_slider_display(slider_value_idx, var=aac_var, disp_label=aac_value_disp_label):
                            selected_bitrate = aac_options_list[int(slider_value_idx)]
                            var.set(selected_bitrate)
                            disp_label.configure(text=selected_bitrate)

                        aac_slider_pos = aac_options_map.get(aac_current_val, aac_options_map.get(aac_default_val, 2))
                        aac_slider_widget = customtkinter.CTkSlider(aac_slider_frame, from_=0, to=len(aac_options_list)-1, number_of_steps=len(aac_options_list)-1, command=_update_aac_slider_display)
                        aac_slider_widget.set(aac_slider_pos)
                        aac_slider_widget.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                        CTkToolTip(aac_slider_frame, message=tooltip_texts.get(aac_full_key, ""), bg_color="#1D1D1D")
                        row += 1
                        flac_label_text = "FLAC Compression Level"
                        flac_full_key = "advanced.conversion_flags.flac.compression_level"
                        flac_default_val = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["flac"]["compression_level"]
                        flac_current_val = int(current_settings["globals"].get("advanced", {}).get("conversion_flags", {}).get("flac", {}).get("compression_level", flac_default_val))

                        customtkinter.CTkLabel(global_settings_frame, text=flac_label_text).grid(row=row, column=0, sticky="w", padx=(20, 10), pady=2)
                        flac_slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                        flac_slider_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
                        flac_slider_frame.grid_columnconfigure(0, weight=1)
                        
                        flac_var = tkinter.StringVar(value=str(flac_current_val))
                        settings_vars["globals"][flac_full_key] = flac_var

                        flac_value_disp_label = customtkinter.CTkLabel(flac_slider_frame, text=str(flac_current_val), width=70, anchor="e")
                        flac_value_disp_label.grid(row=0, column=1, sticky="e")

                        def _update_flac_slider_display(slider_value, var=flac_var, disp_label=flac_value_disp_label):
                            val_int = int(slider_value)
                            var.set(str(val_int))
                            disp_label.configure(text=str(val_int))
                        
                        flac_slider_widget = customtkinter.CTkSlider(flac_slider_frame, from_=0, to=8, number_of_steps=8, command=_update_flac_slider_display)
                        flac_slider_widget.set(flac_current_val)
                        flac_slider_widget.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                        CTkToolTip(flac_slider_frame, message=tooltip_texts.get(flac_full_key, ""), bg_color="#1D1D1D")
                        row += 1
                        mp3_label_text = "MP3 Encoding"
                        mp3_setting_key = "advanced.conversion_flags.mp3.setting"
                        mp3_conf_flags = current_settings["globals"].get("advanced", {}).get("conversion_flags", {}).get("mp3", {})
                        mp3_default_conf_flags = DEFAULT_SETTINGS["globals"]["advanced"]["conversion_flags"]["mp3"]

                        mp3_options_list = ["128k", "192k", "256k", "320k", "VBR -V0"]
                        mp3_options_map = {val: i for i, val in enumerate(mp3_options_list)}
                        
                        current_mp3_display_val = "VBR -V0"
                        if "audio_bitrate" in mp3_conf_flags:
                            current_mp3_display_val = mp3_conf_flags["audio_bitrate"]
                        elif "qscale:a" in mp3_conf_flags and mp3_conf_flags["qscale:a"] == "0":
                            current_mp3_display_val = "VBR -V0"
                        
                        customtkinter.CTkLabel(global_settings_frame, text=mp3_label_text).grid(row=row, column=0, sticky="w", padx=(20, 10), pady=2)
                        mp3_slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                        mp3_slider_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
                        mp3_slider_frame.grid_columnconfigure(0, weight=1)

                        mp3_var = tkinter.StringVar(value=current_mp3_display_val)
                        settings_vars["globals"][mp3_setting_key] = mp3_var
                        settings_vars["globals"].pop("advanced.conversion_flags.mp3.qscale:a", None)
                        settings_vars["globals"].pop("advanced.conversion_flags.mp3.audio_bitrate", None)

                        mp3_value_disp_label = customtkinter.CTkLabel(mp3_slider_frame, text=current_mp3_display_val, width=70, anchor="e")
                        mp3_value_disp_label.grid(row=0, column=1, sticky="e")

                        def _update_mp3_slider_display(slider_value_idx, var=mp3_var, disp_label=mp3_value_disp_label):
                            selected_text = mp3_options_list[int(slider_value_idx)]
                            var.set(selected_text)
                            disp_label.configure(text=selected_text)

                        mp3_slider_pos = mp3_options_map.get(current_mp3_display_val, len(mp3_options_list)-1)
                        mp3_slider_widget = customtkinter.CTkSlider(mp3_slider_frame, from_=0, to=len(mp3_options_list)-1, number_of_steps=len(mp3_options_list)-1, command=_update_mp3_slider_display)
                        mp3_slider_widget.set(mp3_slider_pos)
                        mp3_slider_widget.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                        tooltip_mp3_text = tooltip_texts.get("advanced.conversion_flags.mp3.setting", "MP3 Encoding Settings:\n128k-320k are Constant Bitrate (CBR).\nVBR -V0 uses qscale:a 0 for highest variable bitrate quality.")
                        CTkToolTip(mp3_slider_frame, message=tooltip_mp3_text, bg_color="#1D1D1D")
                        row += 1
                        continue
                    label_widget = customtkinter.CTkLabel(global_settings_frame, text=field.replace("_", " ").title())
                    label_widget.grid(row=row, column=0, sticky="w", padx=(10, 10), pady=2)
                    widget = None; browse_btn = None

                    if isinstance(default_value, bool):
                        var = tkinter.BooleanVar(value=bool(current_value)); settings_vars["globals"][full_key] = var
                        widget = customtkinter.CTkCheckBox(global_settings_frame, text="", variable=var)
                        widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                    elif isinstance(default_value, dict):
                        if field == "codec_conversions":
                            codec_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            codec_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            codec_frame.grid_columnconfigure(2, weight=1)
                            if isinstance(current_value, dict) and current_value:
                                current_conversions = current_value
                            else:
                                current_conversions = default_value if isinstance(default_value, dict) else {}
                            
                            conversion_row = 0
                            
                            if current_conversions:
                                for source_codec, target_codec in current_conversions.items():
                                    source_var = tkinter.StringVar(value=str(source_codec).lower())
                                    codec_options = ['flac', 'alac', 'wav', 'vorbis', 'mp3', 'aac']
                                    source_dropdown = customtkinter.CTkComboBox(codec_frame, variable=source_var, values=codec_options, width=100, state="readonly", dropdown_fg_color="#2B2B2B")
                                    source_dropdown.grid(row=conversion_row, column=0, sticky="w", padx=(0, 3), pady=1)
                                    
                                    arrow_label = customtkinter.CTkLabel(codec_frame, text="---->", width=40)
                                    arrow_label.grid(row=conversion_row, column=1, sticky="w", padx=(0, 3), pady=1)
                                    target_var = tkinter.StringVar(value=str(target_codec).lower())
                                    target_dropdown = customtkinter.CTkComboBox(codec_frame, variable=target_var, values=codec_options, width=100, state="readonly", dropdown_fg_color="#2B2B2B")
                                    target_dropdown.grid(row=conversion_row, column=2, sticky="w", padx=(0, 5), pady=1)
                                    
                                    if full_key not in settings_vars["globals"]: settings_vars["globals"][full_key] = {}
                                    settings_vars["globals"][full_key][f"{source_codec}_source"] = source_var
                                    settings_vars["globals"][full_key][f"{source_codec}_target"] = target_var
                                    
                                    conversion_row += 1
                        else:
                            widget = customtkinter.CTkLabel(global_settings_frame, text="(Complex Setting)")
                            widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                            settings_vars["globals"][full_key] = {}
                    else:
                         var = tkinter.StringVar(value=str(current_value)); settings_vars["globals"][full_key] = var
                         if section_key == "general" and field == "output_path":
                            widget = customtkinter.CTkEntry(global_settings_frame, textvariable=var)
                            widget.grid(row=row, column=1, sticky="ew", padx=(5,1))
                            widget.bind("<Button-3>", show_context_menu)
                            widget.bind("<FocusIn>", lambda e, w=widget: handle_focus_in(w))
                            widget.bind("<FocusOut>", lambda e, w=widget: handle_focus_out(w))
                            browse_btn = customtkinter.CTkButton(global_settings_frame, text="Browse", width=80, height=widget._current_height,
                                                               command=lambda v=var: browse_output_path(v),
                                                               fg_color=widget._fg_color, hover_color="#1F6AA5",
                                                               border_width=widget._border_width if hasattr(widget, '_border_width') else 0, 
                                                               border_color=widget._border_color if hasattr(widget, '_border_color') else None)
                            browse_btn.grid(row=row, column=2, sticky="w", padx=(1,5))
                         elif section_key == "general" and field == "quality":
                            quality_options = ["hifi", "lossless", "high", "low"]
                            current_val_str = var.get().lower()
                            if current_val_str not in quality_options: var.set(quality_options[0])
                            widget = customtkinter.CTkComboBox(global_settings_frame, variable=var, values=quality_options, state="readonly", dropdown_fg_color="#2B2B2B")
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                         elif section_key == "general" and field == "concurrent_downloads":
                            try:
                                current_concurrent = int(var.get())
                                if current_concurrent < 1 or current_concurrent > 10:
                                    current_concurrent = 3
                            except (ValueError, TypeError):
                                current_concurrent = 3

                            slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            slider_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            slider_frame.grid_columnconfigure(0, weight=1)

                            value_label = customtkinter.CTkLabel(slider_frame, text=f"{current_concurrent}", width=70)
                            value_label.grid(row=0, column=1, sticky="e")

                            def update_concurrent_value(value, var_ref=var, label_ref=value_label):
                                int_value = int(round(value))
                                var_ref.set(str(int_value))
                                label_ref.configure(text=f"{int_value}")

                            slider = customtkinter.CTkSlider(slider_frame, from_=1, to=10, number_of_steps=9, command=update_concurrent_value)
                            slider.set(current_concurrent)
                            slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))

                            var.set(str(current_concurrent))

                            widget = slider_frame
                         elif section_key == "covers" and field == "main_compression":
                            compression_options = ["high", "low"]
                            if var.get() not in compression_options: var.set(compression_options[0])
                            
                            radio_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            radio_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            
                            high_radio = customtkinter.CTkRadioButton(radio_frame, text="High", variable=var, value="high")
                            high_radio.pack(side="left", padx=(0, 10))
                            
                            low_radio = customtkinter.CTkRadioButton(radio_frame, text="Low", variable=var, value="low")
                            low_radio.pack(side="left")
                            
                            widget = radio_frame
                         elif section_key == "covers" and field == "external_format":
                            format_options = ["png", "jpg", "webp"]
                            if var.get() not in format_options: var.set(format_options[0])
                            
                            radio_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            radio_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            
                            png_radio = customtkinter.CTkRadioButton(radio_frame, text="PNG", variable=var, value="png")
                            png_radio.pack(side="left", padx=(0, 10))
                            
                            jpg_radio = customtkinter.CTkRadioButton(radio_frame, text="JPG", variable=var, value="jpg")
                            jpg_radio.pack(side="left", padx=(0, 10))
                            
                            webp_radio = customtkinter.CTkRadioButton(radio_frame, text="WebP", variable=var, value="webp")
                            webp_radio.pack(side="left")
                            
                            widget = radio_frame
                         elif section_key == "covers" and field == "external_compression":
                            compression_options = ["low", "high"]
                            if var.get() not in compression_options: var.set(compression_options[0])
                            
                            radio_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            radio_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            
                            low_radio = customtkinter.CTkRadioButton(radio_frame, text="Low", variable=var, value="low")
                            low_radio.pack(side="left", padx=(0, 10))
                            
                            high_radio = customtkinter.CTkRadioButton(radio_frame, text="High", variable=var, value="high")
                            high_radio.pack(side="left")
                            
                            widget = radio_frame
                         elif section_key == "covers" and field == "main_resolution":
                            try:
                                current_res = int(var.get())
                                if current_res < 100 or current_res > 1400:
                                    current_res = 1400
                            except (ValueError, TypeError):
                                current_res = 1400
                            
                            current_res = round(current_res / 100) * 100
                            
                            slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            slider_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            slider_frame.grid_columnconfigure(0, weight=1)
                            
                            value_label = customtkinter.CTkLabel(slider_frame, text=f"{current_res}px", width=70)
                            value_label.grid(row=0, column=1, sticky="e")
                            
                            def update_resolution_value(value, var_ref=var, label_ref=value_label):
                                int_value = round(value / 100) * 100
                                var_ref.set(str(int_value))
                                label_ref.configure(text=f"{int_value}px")
                        
                            slider = customtkinter.CTkSlider(slider_frame, from_=100, to=1400, number_of_steps=13, command=update_resolution_value)
                            slider.set(current_res)
                            slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                            
                            var.set(str(current_res))
                            
                            widget = slider_frame
                         elif section_key == "covers" and field == "external_resolution":
                            try:
                                current_res = int(var.get())
                                if current_res < 200 or current_res > 3000:
                                    current_res = 3000
                            except (ValueError, TypeError):
                                current_res = 3000
                            
                            current_res = round(current_res / 200) * 200
                            
                            slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            slider_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            slider_frame.grid_columnconfigure(0, weight=1)
                            
                            value_label = customtkinter.CTkLabel(slider_frame, text=f"{current_res}px", width=70)
                            value_label.grid(row=0, column=1, sticky="e")
                            
                            def update_external_resolution_value(value, var_ref=var, label_ref=value_label):
                                int_value = round(value / 200) * 200
                                var_ref.set(str(int_value))
                                label_ref.configure(text=f"{int_value}px")
                            
                            slider = customtkinter.CTkSlider(slider_frame, from_=200, to=3000, number_of_steps=14, command=update_external_resolution_value)
                            slider.set(current_res)
                            slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                            
                            var.set(str(current_res))
                            
                            widget = slider_frame
                         elif section_key == "playlist" and field == "paths_m3u":
                            paths_options = ["absolute", "relative"]
                            if var.get() not in paths_options: var.set(paths_options[0])
                            
                            radio_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            radio_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            
                            absolute_radio = customtkinter.CTkRadioButton(radio_frame, text="Absolute", variable=var, value="absolute")
                            absolute_radio.pack(side="left", padx=(0, 10))
                            
                            relative_radio = customtkinter.CTkRadioButton(radio_frame, text="Relative", variable=var, value="relative")
                            relative_radio.pack(side="left")
                            
                            widget = radio_frame
                         elif section_key == "advanced" and field == "cover_variance_threshold":
                            try:
                                current_threshold = int(var.get())
                                if current_threshold < 0 or current_threshold > 100:
                                    current_threshold = 0
                            except (ValueError, TypeError):
                                current_threshold = 0
                            
                            current_threshold = round(current_threshold / 2) * 2
                            
                            slider_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            slider_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            slider_frame.grid_columnconfigure(0, weight=1)
                            
                            value_label = customtkinter.CTkLabel(slider_frame, text=f"{current_threshold}%", width=70)
                            value_label.grid(row=0, column=1, sticky="e")
                            
                            def update_threshold_value(value, var_ref=var, label_ref=value_label):
                                int_value = round(value / 2) * 2
                                var_ref.set(str(int_value))
                                label_ref.configure(text=f"{int_value}%")
                            
                            slider = customtkinter.CTkSlider(slider_frame, from_=0, to=100, number_of_steps=50, command=update_threshold_value)
                            slider.set(current_threshold)
                            slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
                            
                            var.set(str(current_threshold))

                            widget = slider_frame
                         elif section_key == "advanced" and field == "ffmpeg_path":
                            ffmpeg_path_frame = customtkinter.CTkFrame(global_settings_frame, fg_color="transparent")
                            ffmpeg_path_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
                            ffmpeg_path_frame.grid_columnconfigure(0, weight=1)

                            widget = customtkinter.CTkEntry(ffmpeg_path_frame, textvariable=var)
                            widget.grid(row=0, column=0, sticky="ew", padx=(0,1))
                            widget.bind("<Button-3>", show_context_menu)
                            widget.bind("<FocusIn>", lambda e, w=widget: handle_focus_in(w))
                            widget.bind("<FocusOut>", lambda e, w=widget: handle_focus_out(w))

                            browse_btn = customtkinter.CTkButton(ffmpeg_path_frame, text="Browse", width=80, height=widget._current_height,
                                                               command=lambda v=var: browse_ffmpeg_path(v),
                                                               fg_color=widget._fg_color, hover_color="#1F6AA5",
                                                               border_width=widget._border_width if hasattr(widget, '_border_width') else 0, 
                                                               border_color=widget._border_color if hasattr(widget, '_border_color') else None)
                            browse_btn.grid(row=0, column=1, sticky="w", padx=(1,0))
                         else:
                            widget = customtkinter.CTkEntry(global_settings_frame, textvariable=var)
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                            widget.bind("<Button-3>", show_context_menu)
                            widget.bind("<FocusIn>", lambda e, w=widget: handle_focus_in(w))
                            widget.bind("<FocusOut>", lambda e, w=widget: handle_focus_out(w))

                    tooltip_text = tooltip_texts.get(full_key)
                    if tooltip_text and widget:
                         CTkToolTip(widget, message=tooltip_text, bg_color="#1D1D1D")

                    row += 1
        credential_keys_for_settings_tabs = [pk for pk in installed_platform_keys if pk != "Musixmatch"]        
        
        sorted_platform_keys_for_tabs = sorted(credential_keys_for_settings_tabs)
        for platform_key in sorted_platform_keys_for_tabs:
            platform_tab_frame = settings_tabview.add(platform_key)
            credential_tabs_config[platform_key] = {'frame': platform_tab_frame}
        settings_tabview.set("Global")
        save_controls_frame = customtkinter.CTkFrame(settings_tab, fg_color="transparent"); save_controls_frame.pack(side="bottom", anchor="se", padx=10, pady=(0, 10))
        save_status_var = tkinter.StringVar(); save_status_label = customtkinter.CTkLabel(save_controls_frame, textvariable=save_status_var, text_color=("#00C851", "#00C851"))
        globals()['save_status_label'] = save_status_label
        save_status_label.pack(side="left", padx=(0, 10))
        save_button = customtkinter.CTkButton(save_controls_frame, text="Save", width=100, height=30, command=handle_save_settings, fg_color="#343638", hover_color="#1F6AA5"); save_button.pack(side="left", padx=5, pady=(0, 0))
        about_tab = tabview.add("About"); about_container = customtkinter.CTkFrame(about_tab, fg_color="transparent"); about_container.pack(fill="both", expand=True, padx=16, pady=(0, 0)); canvas = customtkinter.CTkFrame(about_container, fg_color="transparent"); canvas.pack(fill="both", expand=True); about_frame = customtkinter.CTkFrame(canvas, fg_color="transparent"); about_frame.pack(fill="x", expand=False, pady=10)
        icon_title_frame = customtkinter.CTkFrame(about_frame, fg_color="transparent")
        icon_title_frame.pack(pady=(0, 5))
        try:
            current_platform = platform.system()
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG AboutIcon] Platform detected: {current_platform}")
            if current_platform == "Linux":
                icon_filename = "icon.png"
                icon_display_size = (48, 48)
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"[DEBUG AboutIcon] Set Linux display size to {icon_display_size}")
            elif current_platform == "Darwin":
                icon_filename = "icon.icns"
                icon_display_size = (72, 72)
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"[DEBUG AboutIcon] Set macOS display size to {icon_display_size}")
            else:
                icon_filename = "icon.ico"
                icon_display_size = (48, 48)
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"[DEBUG AboutIcon] Set default display size to {icon_display_size}")
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG AboutIcon] Determined icon filename: {icon_filename}")
            icon_path = resource_path(icon_filename)
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG AboutIcon] Generated icon path: {icon_path}")
                print(f"[DEBUG AboutIcon] Looking for AboutTab icon at: {icon_path}")

            icon_exists = os.path.exists(icon_path)
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG AboutIcon] Does icon exist at path? {icon_exists}")

            if icon_path and icon_exists:

                try:
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print("[DEBUG AboutIcon] Attempting to open image...")
                    img = Image.open(icon_path).resize(icon_display_size, Image.LANCZOS)
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print("[DEBUG AboutIcon] Image opened successfully.")
                    icon_image = customtkinter.CTkImage(light_image=img, dark_image=img, size=icon_display_size)
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print("[DEBUG AboutIcon] CTkImage created successfully.")
                    icon_label = customtkinter.CTkLabel(icon_title_frame, text="", image=icon_image)
                    icon_pady = 0 if current_platform == "Darwin" else 5
                    icon_label.pack(pady=icon_pady)
                except Exception as img_e:
                    if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                        print(f"[DEBUG AboutIcon] Could not load/process icon image: {type(img_e).__name__}: {img_e}")
            else:
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print(f"[DEBUG AboutIcon] Icon file not found or path invalid: {icon_path}")
        except Exception as path_e:
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print(f"[DEBUG AboutIcon] Error during icon path processing/loading: {type(path_e).__name__}: {path_e}")
        title_label = customtkinter.CTkLabel(icon_title_frame, text="OrpheusDL GUI", font=customtkinter.CTkFont(weight="bold"))
        title_label.pack(pady=(0, 0))
        description_text = ("Makes downloading music with OrpheusDL easy on Win, macOS & Linux.\nSearch multiple platforms & download high-quality audio with metadata."); description_label = customtkinter.CTkLabel(about_frame, text=description_text, justify="center", wraplength=450); description_label.pack(pady=(0, 10))
        github_url = "https://github.com/bascurtiz/OrpheusDL-GUI"
        command = lambda u=github_url: os.startfile(u) if platform.system() == "Windows" else subprocess.Popen(["open", u]) if platform.system() == "Darwin" else subprocess.Popen(["xdg-open", u])
        github_button = customtkinter.CTkButton(about_frame, text="GitHub", command=command, width=110, fg_color="#343638", hover_color="#1F6AA5")
        github_button.pack(pady=10)
        section_header_font = ("Segoe UI", 11)
        section_header_color = "#898c8d"
        version_heading_label = customtkinter.CTkLabel(about_frame, text="GUI VERSION", font=section_header_font, text_color=section_header_color)
        version_heading_label.pack(pady=(10, 0))
        version_number_label = customtkinter.CTkLabel(about_frame, text=__version__)
        version_number_label.pack(pady=(0, 10))
        credits_heading_label = customtkinter.CTkLabel(about_frame, text="CREDITS", font=section_header_font, text_color=section_header_color)
        credits_heading_label.pack(pady=(0, 2))
        credits_names_text = ("""OrfiDev (Project Lead)\nDniel97 (Current Lead Developer)\nCommunity developers (Modules)\nBas Curtiz (GUI)"""); credits_names_label = customtkinter.CTkLabel(about_frame, text=credits_names_text.strip(), justify="center"); credits_names_label.pack(pady=(0, 0))
        modules_title = customtkinter.CTkLabel(about_frame, text="MODULES", font=section_header_font, text_color=section_header_color)
        modules_title.pack(pady=(20, 5))
        modules_frame = customtkinter.CTkFrame(about_frame, fg_color="transparent"); modules_frame.pack(fill="x", padx=20, pady=(0, 10))
        module_buttons_data = [
            ("Apple Music", "https://github.com/bascurtiz/orpheusdl-applemusic"),
            ("Beatport", "https://github.com/bascurtiz/orpheusdl-beatport"),
            ("Beatsource", "https://github.com/bascurtiz/orpheusdl-beatsource"),
            ("Bugs", "https://github.com/Dniel97/orpheusdl-bugsmusic"),
            ("Deezer", "https://github.com/uhwot/orpheusdl-deezer"),            
            ("Genius", "https://github.com/Dniel97/orpheusdl-genius"),
            ("Idagio", "https://github.com/Dniel97/orpheusdl-idagio"),
            ("JioSaavn", "https://github.com/bunnykek/orpheusdl-jiosaavn"),
            ("KKBOX", "https://github.com/uhwot/orpheusdl-kkbox"),
            ("Musixmatch", "https://github.com/yarrm80s/orpheusdl-musixmatch"),
            ("Napster", "https://github.com/yarrm80s/orpheusdl-napster"),
            ("Nugs.net", "https://github.com/Dniel97/orpheusdl-nugs"),
            ("Qobuz", "https://github.com/bascurtiz/orpheusdl-qobuz"),            
            ("SoundCloud", "https://github.com/bascurtiz/orpheusdl-soundcloud"),
            ("Spotify", "https://github.com/bascurtiz/orpheusdl-spotify"),
            ("Tidal", "https://github.com/Dniel97/orpheusdl-tidal")
        ]
        module_buttons_data.sort(key=lambda item: item[0])
        cols = 8
        rows = (len(module_buttons_data) + cols - 1) // cols if module_buttons_data else 0
        for i in range(cols):
            modules_frame.grid_columnconfigure(i, weight=1)
        button_width = 110
        button_padx = 2
        button_pady = 2
        for index, (name, url) in enumerate(module_buttons_data):
            row = index // cols
            col = index % cols
            command = lambda u=url: (subprocess.Popen(["open", u]) if platform.system() == "Darwin" else subprocess.Popen(["xdg-open", u]) if platform.system() == "Linux" else os.startfile(u))
            button = customtkinter.CTkButton(
                modules_frame,
                text=name,
                command=command,
                width=button_width,
                fg_color="#343638",
                hover_color="#1F6AA5"
            )
            button.grid(row=row, column=col, padx=button_padx, pady=button_pady, sticky="nsew")
        if not orpheus_instance:
            print("Disabling Download/Search buttons due to Orpheus initialization failure.")
            if 'download_button' in globals() and download_button and download_button.winfo_exists(): download_button.configure(state="disabled")
            if 'search_button' in globals() and search_button and search_button.winfo_exists(): search_button.configure(state="disabled")
            if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists(): search_download_button.configure(state="disabled")
        setup_logging(output_queue)
        update_log_area()
        try:
            run_check_in_thread(__version__, app)
        except Exception as update_err:
            print(f"[Error] Failed to start update check: {update_err}")

        def _initial_ui_update():
            if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                print("[DEBUG] Running _initial_ui_update...")
            try:
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print("  -> Calling _update_settings_tab_widgets()")
                _update_settings_tab_widgets()
                if current_settings.get("globals", {}).get("advanced", {}).get("debug_mode", False):
                    print("[DEBUG] _initial_ui_update finished.")
            except Exception as e_init_update:
                 print(f"[Error] in _initial_ui_update: {e_init_update}")

        _initial_ui_update()
        app.protocol("WM_DELETE_WINDOW", _on_gui_exit)
        _setup_macos_window_management()
        
        app.mainloop()
    else:
        print(f"[Child Process {os.getpid()}] Detected, exiting.")
        sys.exit()