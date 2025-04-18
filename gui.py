# --- Table Of Contents ---
# 1. IMPORTS
# 2. (MONKEY)PATCHES
# 3. LOCAL DEFINITIONS
# 4. UTILITY FUNCTIONS
# 5. INITIALIZATION & CONFIGURATION HANDLING
# 6. GUI HELPER FUNCTIONS
# 7. DOWNLOAD LOGIC
# 8. SEARCH LOGIC
# 9. SETTINGS TAB LOGIC
# 10. MAIN EXECUTION

# =============================================================================
# --- 1. IMPORTS ---
# =============================================================================
import copy
import customtkinter
import datetime
import enum
import importlib.util
import inspect
import io
import json
import multiprocessing # <-- Added for process check
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
from CTkToolTip import CTkToolTip
from PIL import Image
from pathlib import Path
from tkinter import ttk
from tqdm import tqdm
from urllib.parse import urlparse

# Application Version
__version__ = "1.0.1" # <<< Add version here

# --- Import Update Checker ---
from update_checker import run_check_in_thread # <<< Import the checker function

# --- Platform-specific imports ---
if platform.system() == "Windows":
    try:
        import winsound
    except ImportError:
        print("[Warning] 'winsound' module not found, sound notifications disabled on Windows.")
        winsound = None # Define as None if import fails
else:
    winsound = None # Define as None on non-Windows platforms

# --- DPI Awareness Call (Windows Only) ---
if platform.system() == "Windows":
    try:
        from ctypes import windll
        # Try Per Monitor V2 DPI Awareness (Requires Windows 10 Creators Update+) - Preferred
        windll.shcore.SetProcessDpiAwareness(2) 
        print("[DPI] Set Per Monitor V2 DPI Awareness (2)")
    except Exception as e1:
        try:
            # Fallback to System DPI Awareness (Vista+)
            windll.user32.SetProcessDpiAware()
            print("[DPI] Set System DPI Awareness (Legacy) - Fallback")
        except Exception as e2:
            print(f"[DPI] Warning: Could not set DPI awareness ({e1} / {e2})")

# =============================================================================
# --- 2. (MONKEY)PATCHES: Mainly to support PyInstaller's compiled exe/app ---
# =============================================================================

# --- Define Script Directory Function FIRST ---
# This needs to be defined early as it might be used by patching or path setup below.
def get_script_directory():
    """Gets the directory containing the script/executable, handling bundled apps."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled app (PyInstaller)
        application_path = os.path.dirname(sys.executable)
        if platform.system() == "Darwin":
            # On macOS, sys.executable is inside Contents/MacOS
            # Go up 3 levels to get the directory *containing* the .app bundle
            # e.g., /path/to/OrpheusDL_GUI.app/Contents/MacOS -> /path/to/
            bundle_dir = os.path.abspath(os.path.join(application_path, '..', '..', '..'))
            return bundle_dir
        else:
            # On Windows/Linux, dirname(sys.executable) is usually the containing folder
            return application_path
    else:
        # Running as a standard Python script
        try:
            script_path = os.path.dirname(os.path.abspath(__file__))
        except NameError: # __file__ is not defined, e.g., in interactive mode
            try:
                script_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
            except AttributeError: # inspect might fail in some environments
                script_path = os.path.abspath(os.path.dirname(sys.argv[0]))
        return script_path

# --- Resource Path Function for PyInstaller ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        # print(f"[Resource Path] Running bundled, _MEIPASS: {base_path}") # Optional debug
    except Exception:
        # _MEIPASS not found, running in normal Python environment
        try:
             # Use the directory of the script file
             base_path = os.path.dirname(os.path.abspath(__file__))
             # print(f"[Resource Path] Running as script, using __file__: {base_path}") # Optional debug
        except NameError:
             # Fallback if __file__ is not defined (e.g., interactive, frozen but no _MEIPASS?)
             base_path = os.path.abspath(".")
             # print(f"[Resource Path] Running fallback, using cwd: {base_path}") # Optional debug
        # Ensure the fallback path exists, otherwise use script directory as last resort
        if not os.path.isdir(base_path):
             base_path = get_script_directory() # Fallback to original method if others fail

    final_path = os.path.join(base_path, relative_path)
    # print(f"[Resource Path] Resolved '{relative_path}' to '{final_path}'") # Optional debug
    return final_path

# --- Ensure the script's directory is in sys.path for bundled apps ---
# This needs to run early, before potentially importing local packages like 'orpheus'.
_app_dir = get_script_directory()
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

# --- Attempt to import Orpheus core FIRST to allow patching ---
# This is necessary because we need to patch *before* other parts of Orpheus are imported.
try:
    import orpheus.core
    _orpheus_core_available = True
except ImportError as e:
    print(f"ERROR: Failed to import orpheus.core: {e}. Patching and core functionality might fail.")
    _orpheus_core_available = False
    orpheus = type('obj', (object,), {'core': None})() # Create dummy structure if import fails

# --- Monkey-patch orpheus.core.resource_path (if core was imported) ---
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

# --- Import Orpheus components AFTER potential patching ---
# Use the previously determined availability flag.
if _orpheus_core_available:
    try:
        from orpheus.core import Orpheus, MediaIdentification, ManualEnum, ModuleModes
        from orpheus.music_downloader import beauty_format_seconds, Downloader
        from utils.models import (ImageFileTypeEnum, CoverCompressionEnum, Oprinter, DownloadTypeEnum) # Import utils here
        ORPHEUS_AVAILABLE = True
    except (ImportError, AttributeError) as e:
        print(f"ERROR: Failed to import Orpheus library components after patching: {e}. Core functionality will be unavailable.")
        # Define dummy classes/functions if import fails
        class Orpheus: pass
        class MediaIdentification: pass
        class ManualEnum: manual = 1
        class ModuleModes: lyrics=1; covers=2; credits=3
        def beauty_format_seconds(s): return str(s)
        class Downloader: pass
        # Define dummy utils models if needed
        class ImageFileTypeEnum(enum.Enum): pass
        class CoverCompressionEnum(enum.Enum): pass
        class Oprinter: pass
        class DownloadTypeEnum(enum.Enum): track="track"; artist="artist"; playlist="playlist"; album="album" # Basic definition
        ORPHEUS_AVAILABLE = False
else:
    # Define dummy classes/functions if core wasn't even available
    print("Skipping import of Orpheus components as orpheus.core was not found.")
    class Orpheus: pass
    class MediaIdentification: pass
    class ManualEnum: manual = 1
    class ModuleModes: lyrics=1; covers=2; credits=3
    def beauty_format_seconds(s): return str(s)
    class Downloader: pass
    # Define dummy utils models if needed
    class ImageFileTypeEnum(enum.Enum): pass
    class CoverCompressionEnum(enum.Enum): pass
    class Oprinter: pass
    class DownloadTypeEnum(enum.Enum): track="track"; artist="artist"; playlist="playlist"; album="album" # Basic definition
    ORPHEUS_AVAILABLE = False

# --- Monkey-patch os.get_terminal_size for pythonw.exe ---
# This patch is generally safe and might be needed early by libraries.
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

# --- Monkey-patch CustomTkinter Drawing Errors ---
try:
    from customtkinter.windows.widgets import CTkEntry, CTkCheckBox, CTkComboBox # <<< Import CTkComboBox
    # tkinter is likely already imported, but ensure it is for the exception type
    import tkinter

    print("[Patch] Attempting to patch CTkEntry, CTkCheckBox, and CTkComboBox _draw methods...") # <<< Updated print

    # --- CTkEntry Patch ---
    _original_ctkentry_draw = CTkEntry._draw

    def _patched_ctkentry_draw(self, *args, **kwargs):
        try:
            # Call the original method
            return _original_ctkentry_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                # Suppress the specific TclError related to drawing on potentially destroyed canvas
                pass # print(f"[Patch Suppressed] TclError in CTkEntry._draw for {self}: {e}") # Optional debug
            else:
                # Re-raise other TclErrors
                raise e
        except Exception as e:
            # Catch and report other unexpected errors during draw
            print(f"[Patch Error] Unexpected error in CTkEntry._draw for {self}: {type(e).__name__}: {e}")
            raise e # Re-raise other exceptions

    CTkEntry._draw = _patched_ctkentry_draw
    print("[Patch] Patched CTkEntry._draw method.")

    # --- CTkCheckBox Patch ---
    _original_ctkcheckbox_draw = CTkCheckBox._draw

    def _patched_ctkcheckbox_draw(self, *args, **kwargs):
        try:
            # Call the original method
            return _original_ctkcheckbox_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                # Suppress the specific TclError related to drawing on potentially destroyed canvas
                pass # print(f"[Patch Suppressed] TclError in CTkCheckBox._draw for {self}: {e}") # Optional debug
            else:
                # Re-raise other TclErrors
                raise e
        except Exception as e:
             # Catch and report other unexpected errors during draw
            print(f"[Patch Error] Unexpected error in CTkCheckBox._draw for {self}: {type(e).__name__}: {e}")
            raise e # Re-raise other exceptions

    CTkCheckBox._draw = _patched_ctkcheckbox_draw
    print("[Patch] Patched CTkCheckBox._draw method.")

    # --- CTkComboBox Patch ---
    _original_ctkcombobox_draw = CTkComboBox._draw
                                                                                  
    def _patched_ctkcombobox_draw(self, *args, **kwargs):
        try:
            # Call the original method
            return _original_ctkcombobox_draw(self, *args, **kwargs)
        except tkinter.TclError as e:
            if "invalid command name" in str(e):
                # Suppress the specific TclError
                pass # print(f"[Patch Suppressed] TclError in CTkComboBox._draw for {self}: {e}") # Optional debug
            else:
                # Re-raise other TclErrors
                raise e
        except Exception as e:
             # Catch and report other unexpected errors during draw
            print(f"[Patch Error] Unexpected error in CTkComboBox._draw for {self}: {type(e).__name__}: {e}")
            raise e # Re-raise other exceptions
                                                                                  
    CTkComboBox._draw = _patched_ctkcombobox_draw
    print("[Patch] Patched CTkComboBox._draw method.")

except ImportError:
    print("[Patch Warning] Could not import CTkEntry, CTkCheckBox, or CTkComboBox for patching _draw methods.")
except Exception as e:
    print(f"[Patch Error] Failed to apply CustomTkinter _draw patches: {e}")

# =============================================================================
# --- 3. LOCAL DEFINITIONS (Simulated Library/Missing Parts) ---
# =============================================================================

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

# =============================================================================
# --- 4. UTILITY FUNCTIONS ---
# =============================================================================

def deep_merge(dict1, dict2):
    """Deep merge two dictionaries."""
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            deep_merge(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

# =============================================================================
# --- 5. INITIALIZATION & CONFIGURATION HANDLING ---
# =============================================================================

def load_settings():
    """Loads settings directly from ./config/settings.json."""
    # Access global variables defined within the main process block
    global current_settings, CONFIG_FILE_PATH, DEFAULT_SETTINGS

    settings = {
        "globals": copy.deepcopy(DEFAULT_SETTINGS["globals"]),
        "credentials": {}
    }

    if not os.path.exists(CONFIG_FILE_PATH):
        error_message = f"CRITICAL ERROR: Configuration file not found at '{CONFIG_FILE_PATH}'. Cannot start without settings."
        print(error_message)
        raise FileNotFoundError(error_message)

    try:
        print(f"Directly reading settings from {CONFIG_FILE_PATH}...")
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            file_settings = json.load(f)
        print("File read successfully.")

        # Merge Globals
        if "global" in file_settings:
            orpheus_global_from_file = file_settings["global"]
            if "general" in orpheus_global_from_file:
                orpheus_general = orpheus_global_from_file["general"]
                if "general" not in settings["globals"]: settings["globals"]["general"] = {}
                if "download_path" in orpheus_general: settings["globals"]["general"]["output_path"] = orpheus_general["download_path"]
                if "download_quality" in orpheus_general: settings["globals"]["general"]["quality"] = orpheus_general["download_quality"]
                if "search_limit" in orpheus_general: settings["globals"]["general"]["search_limit"] = orpheus_general["search_limit"]
            for section_key, section_data in orpheus_global_from_file.items():
                 if section_key != "general" and section_key in settings["globals"]:
                     if isinstance(section_data, dict) and isinstance(settings["globals"].get(section_key), dict):
                         deep_merge(settings["globals"][section_key], section_data)

        # Merge Credentials
        if "modules" in file_settings:
            platform_map_from_orpheus = { "bugs": "BugsMusic", "nugs": "Nugs", "soundcloud": "SoundCloud", "tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer", "idagio": "Idagio", "kkbox": "KKBOX", "napster": "Napster", "beatport": "Beatport", "musixmatch": "Musixmatch" }
            for orpheus_platform, creds_from_file in file_settings["modules"].items():
                gui_platform = platform_map_from_orpheus.get(orpheus_platform)
                if gui_platform and gui_platform in DEFAULT_SETTINGS["credentials"]:
                    platform_defaults = copy.deepcopy(DEFAULT_SETTINGS["credentials"][gui_platform])
                    deep_merge(platform_defaults, creds_from_file)
                    settings["credentials"][gui_platform] = platform_defaults

        print(f"Settings loaded and mapped from {CONFIG_FILE_PATH}")

    except (json.JSONDecodeError, IOError, TypeError, KeyError) as e:
        print(f"Error loading/mapping '{CONFIG_FILE_NAME}': {e}")
        print("Using default settings ONLY for globals. Credentials will be empty.")
        settings = {
            "globals": copy.deepcopy(DEFAULT_SETTINGS["globals"]),
            "credentials": {}
        }

    current_settings = settings
    return settings

def initialize_orpheus():
    """Attempts to initialize the global Orpheus instance."""
    # Access global variables defined within the main process block
    global orpheus_instance, app, download_button, search_button, DATA_DIR

    if not ORPHEUS_AVAILABLE:
        print("Orpheus library not available. Skipping initialization.")
        return False
    if orpheus_instance is None:
        try:
            # Directly initialize Orpheus without data_path
            print("Initializing global Orpheus instance...")
            orpheus_instance = Orpheus()
            print("Global Orpheus instance initialized successfully.")
            # Optional: Keep the warning if extensions might still be relevant?
            # print("[Warning] Orpheus initialized without explicit data_path. 'extensions' folder might still cause issues.")
            return True
        except Exception as e:
            # Catch any general initialization errors
            import traceback
            tb_str = traceback.format_exc()
            error_message = f"FATAL: Failed to initialize Orpheus library: {e}\\nTraceback:\\n{tb_str}"

            print(error_message)
            try: # Try to show error in GUI (check if app exists)
                if 'app' in globals() and app and app.winfo_exists():
                    app.after(100, lambda: show_centered_messagebox("Initialization Error", error_message, dialog_type="error"))
                # Check if buttons exist before configuring
                if 'download_button' in globals() and download_button and download_button.winfo_exists():
                    download_button.configure(state="disabled")
                if 'search_button' in globals() and search_button and search_button.winfo_exists():
                    search_button.configure(state="disabled")
            except NameError: pass # If app/buttons not defined yet
            except Exception as gui_e: print(f"Error showing init error in GUI: {gui_e}")
            return False
    return True # Already initialized

def save_settings(show_confirmation: bool = True):
    """Loads existing settings, merges UI changes, validates, maps, and saves back to settings.json.

    Args:
        show_confirmation: If True, displays a success message box.

    Returns:
        True if save was successful, False otherwise.
    """
    # (The actual logic from the previous save_settings function body goes here)
    # ... (Load, Gather/Validate, Map, Merge, Write code as above) ...

    # --- Start of actual logic (replacing the placeholder above) ---
    # Access global variables defined within the main process block
    global settings_vars, current_settings, DEFAULT_SETTINGS, CONFIG_FILE_PATH

    print("[Save Settings] Starting load-merge-save process...")

    # --- 1. Load Existing Settings File ---
    existing_settings = {}
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f: existing_settings = json.load(f)
            print(f"[Save Settings] Loaded existing settings from {CONFIG_FILE_PATH}")
        else:
            print(f"[Save Settings] No existing settings file found at {CONFIG_FILE_PATH}. Will create a new one.")
            existing_settings = { "global": {"general": {},"formatting": {},"codecs": {},"covers": {},"playlist": {},"advanced": {},"module_defaults": {},"artist_downloading": {},"lyrics": {}}, "modules": {} }
    except (json.JSONDecodeError, IOError) as e:
        error_message = f"Error loading existing settings file '{CONFIG_FILE_PATH}':\n{type(e).__name__}: {e}. Cannot proceed with save."
        print(f"[Save Settings] {error_message}", exc_info=True)
        show_centered_messagebox("Settings Error", error_message, dialog_type="error")
        return False

    # --- 2. Gather and Validate UI Values ---
    updated_gui_settings = {"globals": {}, "credentials": {}}
    parse_errors = []
    # Globals
    for key_path_str, var in settings_vars.get("globals", {}).items():
        if not isinstance(var, tkinter.Variable):
            if isinstance(var, dict) and not var: pass; continue
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
        except Exception as e: error_msg = f"Error processing global setting '{key_path_str}': {e}"; print(f"[Save Settings] {error_msg}", exc_info=True); parse_errors.append(error_msg)
    # Credentials
    for platform_name, fields in settings_vars.get("credentials", {}).items():
         if platform_name not in updated_gui_settings["credentials"]: updated_gui_settings["credentials"][platform_name] = {}
         for field_key, var in fields.items():
              if not isinstance(var, tkinter.Variable): continue
              updated_gui_settings["credentials"][platform_name][field_key] = str(var.get())

    # --- 3. Check for Parse Errors ---
    if parse_errors:
         error_list = "\n - ".join(parse_errors)
         show_centered_messagebox("Settings Error", f"Could not save due to invalid values:\n - {error_list}", dialog_type="error")
         print(f"[Save Settings] Validation failed: {error_list}")
         return False

    # --- 4. Map Validated UI data to Orpheus Structure ---
    mapped_orpheus_updates = { "global": {"general": {},"formatting": {},"codecs": {},"covers": {},"playlist": {},"advanced": {},"module_defaults": {},"artist_downloading": {},"lyrics": {}}, "modules": {} }
    gui_globals = updated_gui_settings.get("globals", {})
    general_map_gui_to_orpheus = { "output_path": "download_path", "quality": "download_quality", "search_limit": "search_limit" }
    if "general" in gui_globals:
        gui_general_section = gui_globals["general"]
        if "general" not in mapped_orpheus_updates["global"]: mapped_orpheus_updates["global"]["general"] = {}
        for gui_key, orpheus_key in general_map_gui_to_orpheus.items():
            if gui_key in gui_general_section: mapped_orpheus_updates["global"]["general"][orpheus_key] = gui_general_section[gui_key]
    for section_key, section_data in gui_globals.items():
         if section_key != "general" and section_key in mapped_orpheus_updates["global"]:
             if isinstance(section_data, dict) and isinstance(mapped_orpheus_updates["global"].get(section_key), dict):
                  if section_key not in mapped_orpheus_updates["global"]: mapped_orpheus_updates["global"][section_key] = {}
                  for item_key, item_value in section_data.items(): mapped_orpheus_updates["global"][section_key][item_key] = item_value
    platform_map_to_orpheus = { "BugsMusic": "bugs", "Nugs": "nugs", "SoundCloud": "soundcloud", "Tidal": "tidal", "Qobuz": "qobuz", "Deezer": "deezer", "Idagio": "idagio", "KKBOX": "kkbox", "Napster": "napster", "Beatport": "beatport", "Musixmatch": "musixmatch" }
    for gui_platform, creds in updated_gui_settings.get("credentials", {}).items():
        orpheus_platform = platform_map_to_orpheus.get(gui_platform)
        if orpheus_platform:
            if orpheus_platform not in mapped_orpheus_updates["modules"]: mapped_orpheus_updates["modules"][orpheus_platform] = {}
            mapped_orpheus_updates["modules"][orpheus_platform] = creds.copy()

    # --- 5. Deep Merge Mapped Updates into Existing Settings ---
    print("[Save Settings] Merging validated UI changes into existing settings structure...")
    final_settings_to_save = deep_merge(existing_settings, mapped_orpheus_updates)

    # --- 6. Perform the Direct File Write ---
    try:
        print(f"[Save Settings] Attempting to write merged settings to {CONFIG_FILE_PATH}")
        config_dir = os.path.dirname(CONFIG_FILE_PATH)
        if not os.path.exists(config_dir): os.makedirs(config_dir); print(f"[Save Settings] Created config directory: {config_dir}")
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f: json.dump(final_settings_to_save, f, indent=4, ensure_ascii=False, sort_keys=True)
        print(f"[Save Settings] Settings successfully written to {CONFIG_FILE_PATH}.")

        # --- 7. Update in-memory current_settings AFTER successful save ---
        print("[Save Settings] Updating in-memory 'current_settings' from GUI values...")
        deep_merge(current_settings, updated_gui_settings)
        print("[Save Settings] In-memory 'current_settings' updated.")

        # --- 8. Re-initialize Orpheus instance AFTER successful save ---
        print("[Save Settings] Re-initializing Orpheus instance with updated settings...")
        # Access the global instance
        global orpheus_instance
        orpheus_instance = None # Clear the existing instance
        # Call initialize_orpheus() which now handles passing DATA_DIR
        initialize_orpheus()
        print("[Save Settings] Orpheus instance re-initialized.")

        # <<< Show confirmation only if requested >>>
        if show_confirmation:
            show_centered_messagebox("Settings Saved", "Settings have been saved successfully.", dialog_type="info")

        return True # Indicate success

    except IOError as e:
         error_message = f"Error writing settings file '{CONFIG_FILE_PATH}':\n{type(e).__name__}: {e}"; print(f"[Save Settings] {error_message}", exc_info=True); show_centered_messagebox("Settings Error", error_message, dialog_type="error"); return False
    except Exception as e:
        error_message = f"Unexpected error saving settings:\n{type(e).__name__}: {e}"; print(f"[Save Settings] {error_message}", exc_info=True); show_centered_messagebox("Settings Error", error_message, dialog_type="error"); return False
    # --- End of actual logic ---

def handle_save_settings():
    """Handles the save settings button click."""
    # Access global variables defined within the main process block
    global save_status_var, app

    try:
        print("[Handle Save] Calling save_settings function with confirmation...")
        # <<< Call save_settings with show_confirmation=True >>>
        save_attempt_successful = save_settings(show_confirmation=True)
        print(f"[Handle Save] save_settings returned: {save_attempt_successful}")

        print("[Handle Save] Refreshing UI from updated in-memory settings...")
        # Ensure app exists before scheduling
        if 'app' in globals() and app and app.winfo_exists():
            app.after(50, _update_settings_tab_widgets)

        # <<< Update status based on return value >>>
        if save_attempt_successful:
            # show_centered_messagebox("Settings Saved", "Settings have been saved successfully.", dialog_type="info") # Removed, handled by save_settings
            if 'save_status_var' in globals() and save_status_var:
                save_status_var.set("Settings saved.")
        else:
            if 'save_status_var' in globals() and save_status_var:
                save_status_var.set("Failed to save settings.")

    except Exception as e:
        err_msg = f"Unexpected error during save handling:\n{type(e).__name__}: {e}"
        if 'save_status_var' in globals() and save_status_var:
            save_status_var.set(f"Error handling save: {type(e).__name__}")
        show_centered_messagebox("Save Error", err_msg, dialog_type="error")
        print(f"[DEBUG] Error in handle_save_settings: {err_msg}", exc_info=True)
    finally:
        # Ensure app and var exist before scheduling clear
        if 'app' in globals() and app and app.winfo_exists() and 'save_status_var' in globals() and save_status_var:
            app.after(4000, lambda: save_status_var.set("") if save_status_var else None)

def _auto_save_path_change(*args):
    """Callback triggered when path_var_main changes. Updates in-memory setting AND saves to file."""
    # Access global variables defined within the main process block
    global current_settings, path_var_main, settings_vars, save_status_var, app
    try:
        # Ensure path_var_main exists
        if 'path_var_main' not in globals() or not path_var_main: return

        new_path = path_var_main.get()
        current_path = current_settings.get("globals", {}).get("general", {}).get("output_path")

        if new_path != current_path:
            print(f"Download path changed in UI: {new_path}. Updating in-memory setting.")
            if "globals" not in current_settings: current_settings["globals"] = {}
            if "general" not in current_settings["globals"]: current_settings["globals"]["general"] = {}
            current_settings["globals"]["general"]["output_path"] = new_path

            # Update the settings tab UI (check if var exists)
            if "globals" in settings_vars and "general.output_path" in settings_vars["globals"] and settings_vars["globals"]["general.output_path"]:
                settings_vars["globals"]["general.output_path"].set(new_path)

            # <<< Call save_settings without confirmation >>>
            print(f"[Auto Save Path] Triggering automatic save for path: {new_path}")
            save_successful = save_settings(show_confirmation=False)
            print(f"[Auto Save Path] Automatic save result: {save_successful}")

            # Update status label (check if exists)
            if 'save_status_var' in globals() and save_status_var:
                if save_successful:
                    save_status_var.set("Path saved.")
                else:
                    save_status_var.set("Auto-save failed!")
                # Ensure app exists before scheduling clear
                if 'app' in globals() and app and app.winfo_exists():
                    app.after(3000, lambda: save_status_var.set("") if save_status_var else None)

    except Exception as e:
        print(f"Error in _auto_save_path_change: {e}")
        if 'save_status_var' in globals() and save_status_var:
             save_status_var.set("Error saving path!")
             if 'app' in globals() and app and app.winfo_exists():
                  app.after(3000, lambda: save_status_var.set("") if save_status_var else None)

# =============================================================================
# --- 6. GUI HELPER FUNCTIONS ---
# =============================================================================

# --- Focus Handling for Entry Background ---
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
        else:
            print(f"Warning: Original color not found for {widget} on focus out.")
            pass
    except Exception as e:
        print(f"Error in handle_focus_out for {widget}: {e}")

# --- Centered Message Box ---
def show_centered_messagebox(title, message, dialog_type="info", parent=None):
    """Creates and displays a centered CTkToplevel message box."""
    # Access global 'app' defined in main process block
    global app
    if parent is None:
        # Ensure app exists before using it as default parent
        parent = app if 'app' in globals() and app else None
        if parent is None:
             print("ERROR: Cannot show messagebox, main app window not available.")
             return # Cannot proceed without a parent window

    dialog = customtkinter.CTkToplevel(parent); dialog.title(title); dialog.geometry("450x150"); dialog.resizable(False, False); dialog.attributes("-topmost", True); dialog.transient(parent)
    dialog.update_idletasks(); parent_width = parent.winfo_width(); parent_height = parent.winfo_height(); parent_x = parent.winfo_x(); parent_y = parent.winfo_y(); dialog_width = dialog.winfo_width(); dialog_height = dialog.winfo_height()
    center_x = parent_x + (parent_width // 2) - (dialog_width // 2); center_y = parent_y + (parent_height // 2) - (dialog_height // 2); dialog.geometry(f"+{center_x}+{center_y}")
    message_label = customtkinter.CTkLabel(dialog, text=message, wraplength=400, justify="left"); message_label.pack(pady=(20, 10), padx=20, expand=True, fill="both")
    ok_button = customtkinter.CTkButton(dialog, text="OK", command=dialog.destroy, width=100); ok_button.pack(pady=(0, 20)); ok_button.focus_set(); dialog.bind("<Return>", lambda event: ok_button.invoke())
    dialog.grab_set(); dialog.wait_window()

# --- Context Menu (Copy/Paste) ---
def _create_menu():
    # Access global variables defined within the main process block
    global _context_menu, app, BUTTON_COLOR
    if _context_menu and _context_menu.winfo_exists(): return
    # Ensure app exists before creating menu
    if 'app' not in globals() or not app: return
    _context_menu = customtkinter.CTkFrame(app, border_width=1, border_color="#565B5E")
    copy_button = customtkinter.CTkButton(_context_menu, text="Copy", command=copy_text, width=100, height=28, fg_color=BUTTON_COLOR, hover_color="#1F6AA5", text_color_disabled="gray", border_width=0); copy_button.pack(pady=(2, 1), padx=2, fill="x")
    paste_button = customtkinter.CTkButton(_context_menu, text="Paste", command=paste_text, width=100, height=28, fg_color=BUTTON_COLOR, hover_color="#1F6AA5", text_color_disabled="gray", border_width=0); paste_button.pack(pady=(1, 2), padx=2, fill="x")
    _context_menu.pack_forget()

def show_context_menu(event):
    # Access global variables defined within the main process block
    global _context_menu, _target_widget, _hide_menu_binding_id, app
    _create_menu();
    if not _context_menu: print("Context menu: Failed to create menu frame."); return
    hide_context_menu()
    # Ensure app exists
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
    # Access global variables defined within the main process block
    global _context_menu, _target_widget, _hide_menu_binding_id, app
    # Ensure app exists
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
    # Access global variables defined within the main process block
    global _target_widget, app
    if not isinstance(_target_widget, customtkinter.CTkEntry): hide_context_menu(); return
    # Ensure app exists
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
    # Access global variables defined within the main process block
    global _target_widget, app
    if not isinstance(_target_widget, customtkinter.CTkEntry): hide_context_menu(); return
    # Ensure app exists
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

# --- Output Log Handling ---
def log_to_textbox(msg, error=False):
    # Access global variables defined within the main process block
    global _last_message_was_empty, log_textbox
    try:
        # Ensure log_textbox exists and is valid
        if 'log_textbox' not in globals() or not log_textbox or not log_textbox.winfo_exists(): return
        content_to_insert = msg; is_current_empty = not content_to_insert.strip()
        if is_current_empty and _last_message_was_empty: return
        _last_message_was_empty = is_current_empty
        if content_to_insert:
            log_textbox.configure(state="normal"); log_textbox.insert("end", content_to_insert); log_textbox.see("end"); log_textbox.configure(state="disabled")
    except NameError: print("[Debug] log_to_textbox: NameError (likely widget not ready)")
    except tkinter.TclError as e: print(f"TclError in log_to_textbox (widget destroyed?): {e}")
    except Exception as e:
        print(f"Error in log_to_textbox: {e}")
        try:
            if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists():
                log_textbox.configure(state="disabled")
        except: pass

def update_log_area():
    # Access global variables defined within the main process block
    global output_queue, app
    try:
        while True:
            try: msg = output_queue.get_nowait(); log_to_textbox(msg)
            except queue.Empty: break
            except Exception as e: print(f"Error processing message from queue: {e}")
    except Exception as e: print(f"[ERROR] Exception in update_log_area loop: {type(e).__name__}: {e}")
    finally:
        try:
            # Ensure app exists and is valid before scheduling next update
            if 'app' in globals() and app and app.winfo_exists():
                app.after(100, update_log_area)
            else:
                # If app doesn't exist, we can't reschedule. Stop polling.
                print("[Debug] update_log_area: 'app' not found or destroyed, stopping log polling.")
        except NameError: print("[Debug] update_log_area: NameError accessing 'app'.")
        except Exception as e_sched: print(f"[Error] Could not reschedule update_log_area: {e_sched}")

def clear_output_log():
    # Access global 'log_textbox' defined in main process block
    global log_textbox
    try:
        if 'log_textbox' in globals() and log_textbox and log_textbox.winfo_exists():
            log_textbox.configure(state='normal'); log_textbox.delete('1.0', tkinter.END); log_textbox.configure(state='disabled')
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing log (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing log: {e}")

# --- Path/URL Input Handling ---
def browse_output_path(path_variable):
    directory = tkinter.filedialog.askdirectory(initialdir=path_variable.get())
    if directory: path_variable.set(directory)

def clear_url_entry():
    # Access global 'url_entry' defined in main process block
    global url_entry
    try:
        if 'url_entry' in globals() and url_entry and url_entry.winfo_exists():
            url_entry.delete(0, tkinter.END)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing URL entry (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing URL entry: {e}")

def open_download_path():
    # Access global 'path_var_main' defined in main process block
    global path_var_main
    try:
        # Ensure path_var_main exists
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
    # Access global 'search_entry' defined in main process block
    global search_entry
    try:
        if 'search_entry' in globals() and search_entry and search_entry.winfo_exists():
            search_entry.delete(0, tkinter.END)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing search entry (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing search entry: {e}")

# --- UI State Control ---
def set_ui_state_downloading(is_downloading):
    # Access global widgets defined in main process block
    global download_button, stop_button, progress_bar, app
    def _update_state():
        download_state = "disabled" if is_downloading else "normal"; stop_state = "normal" if is_downloading else "disabled"
        try:
            # Check if widgets exist and are valid before configuring
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
        # Ensure app exists and is valid before scheduling update
        if 'app' in globals() and app and app.winfo_exists():
            app.after(0, _update_state)
        else: print("[Debug] 'app' not found for download UI state update.")
    except NameError: print("[Debug] NameError accessing 'app' for download UI state update.")
    except Exception as e: print(f"Error scheduling download UI state update: {e}")

def set_ui_state_searching(is_searching):
    # Access global widgets defined in main process block
    global search_button, clear_search_button, platform_combo, type_combo, search_entry, search_progress_bar, app
    def _update_state():
        state = "disabled" if is_searching else "normal"; combo_state = "disabled" if is_searching else "readonly"
        try:
            # Check if widgets exist and are valid before configuring
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
        # Ensure app exists and is valid before scheduling update
        if 'app' in globals() and app and app.winfo_exists():
            app.after(0, _update_state)
        else: print("[Debug] 'app' not found for search UI state update.")
    except NameError: pass
    except Exception as e: print(f"Error scheduling search UI state update: {e}")

# --- Treeview Scrollbar Management ---
def _check_and_toggle_scrollbar(tree_widget, scrollbar_widget):
    if not tree_widget or not tree_widget.winfo_exists() or not scrollbar_widget or not scrollbar_widget.winfo_exists(): return
    try:
        tree_widget.update_idletasks(); yview_info = tree_widget.yview()
        if yview_info[1] < 1.0 and tree_widget.get_children():
            if not scrollbar_widget.winfo_ismapped(): scrollbar_widget.grid(row=0, column=1, sticky='ns', pady=3, padx=(0,5))
        else:
             if scrollbar_widget.winfo_ismapped(): scrollbar_widget.grid_remove()
    except Exception as e:
        # Ignore TclError which might happen if widget is destroyed during check
        if isinstance(e, tkinter.TclError): pass
        else: print(f"Error checking/toggling scrollbar: {e}")

# =============================================================================
# --- 7. DOWNLOAD LOGIC ---
# =============================================================================

# --- Queue Writer for Stdout Redirection ---
class QueueWriter(io.TextIOBase):
    def __init__(self, queue_instance): self.queue = queue_instance

    def write(self, msg):
        # Access global 'output_queue' defined in main process block
        # No, QueueWriter is instantiated with the queue, so it uses self.queue
        msg_strip = msg.lstrip()

        is_fetching_line = False
        if msg_strip.startswith("Fetching "):
            parts = msg_strip.split(None, 1)
            if len(parts) > 1 and '/' in parts[1]:
                num_parts = parts[1].split('/', 1)
                if len(num_parts) > 1 and num_parts[0].isdigit():
                    is_fetching_line = True

        if is_fetching_line:
             pass
        else:
            is_progress_line = False
            if msg_strip and msg_strip[0].isdigit():
                parts = msg_strip.split('|')
                if len(parts) > 1 and parts[0].endswith('%'):
                     if any(unit in msg for unit in ['MB/s', 'KB/s', 'B/s', '[', ']']):
                          is_progress_line = True

            if is_progress_line:
                pass
            else:
                self.queue.put(msg.replace('\r', ''))

        return len(msg)

    def flush(self): # Add flush method, often needed for TextIOBase
        pass

    def readable(self): # Add readable method
        return False

    def seekable(self): # Add seekable method
        return False

    def writable(self): # Add writable method
        return True

# --- Download Thread Target ---
def run_download_in_thread(orpheus, url, output_path, gui_settings, search_result_data=None):
    """Runs the download using the provided global Orpheus instance."""
    # Access global variables defined within the main process block
    global output_queue, stop_event, app, download_process_active, DEFAULT_SETTINGS

    if orpheus is None:
        output_queue.put("ERROR: Orpheus instance not available. Cannot start download.\n")
        print("ERROR: run_download_in_thread called with invalid Orpheus instance.")
        try:
            # Ensure app exists before scheduling UI reset
            if 'app' in globals() and app and app.winfo_exists():
                 app.after(0, lambda: set_ui_state_downloading(False))
        except NameError: pass
        except Exception as e: print(f"Error scheduling UI reset after Orpheus instance error: {e}")
        return

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    queue_writer = QueueWriter(output_queue)
    is_cancelled = False
    download_exception_occurred = False # <<< Flag to track download errors
    start_time = datetime.datetime.now()

    try:
        sys.stdout = queue_writer
        sys.stderr = queue_writer
        print("[INIT] Starting download thread setup...")
        # Ensure 'temp' directory exists relative to script/executable
        temp_dir = os.path.join(get_script_directory(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        print(f"[INIT] Ensured temp directory exists: {temp_dir}")

        # Prepare Downloader settings
        downloader_settings = {
            "general": {
                "download_path": gui_settings.get("globals", {}).get("general", {}).get("output_path", DEFAULT_SETTINGS["globals"]["general"]["output_path"]),
                "download_quality": gui_settings.get("globals", {}).get("general", {}).get("quality", DEFAULT_SETTINGS["globals"]["general"]["quality"]),
                "search_limit": gui_settings.get("globals", {}).get("general", {}).get("search_limit", DEFAULT_SETTINGS["globals"]["general"]["search_limit"])
            },
            **{k: v for k, v in gui_settings.get("globals", {}).items() if k != "general"}
        }
        module_controls_dict = orpheus.module_controls
        oprinter = Oprinter()

        # Initialize Downloader
        downloader = Downloader(settings=downloader_settings, module_controls=module_controls_dict, oprinter=oprinter, path=output_path)
        settings_global_for_defaults = gui_settings.get("globals", DEFAULT_SETTINGS["globals"])
        module_defaults = settings_global_for_defaults.get("module_defaults", {})
        third_party_modules_dict = { ModuleModes.lyrics: module_defaults.get("lyrics") if module_defaults.get("lyrics") != "default" else None, ModuleModes.covers: module_defaults.get("covers") if module_defaults.get("covers") != "default" else None, ModuleModes.credits: module_defaults.get("credits") if module_defaults.get("credits") != "default" else None }
        downloader.third_party_modules = third_party_modules_dict

        # --- URL Parsing Logic ---
        parsed_url = urlparse(url); components = parsed_url.path.split('/'); module_name = None
        for netloc_pattern, mod_name in orpheus.module_netloc_constants.items():
            if re.findall(netloc_pattern, parsed_url.netloc): module_name = mod_name; break
        if not module_name: raise ValueError(f"Could not determine module for URL host: {parsed_url.netloc}")

        if orpheus.module_settings[module_name].url_decoding is ManualEnum.manual:
            module_instance = orpheus.load_module(module_name)
            media_ident: MediaIdentification = module_instance.custom_url_parse(url)
            if not media_ident: raise ValueError(f"Module '{module_name}' custom_url_parse failed for URL: {url}")
            media_type = media_ident.media_type; media_id = media_ident.media_id
        else:
            # <<< START JioSaavn Specific Check >>>
            media_id = None # Initialize
            media_type = None # Initialize
            if module_name == 'jiosaavn' and len(components) > 2 and components[1] == 'song':
                # Specific handling for jiosaavn.com/song/name/id URLs
                media_type = DownloadTypeEnum.track
                media_id = components[-1] # Assume ID is the last part
                print(f"[URL Parse - JioSaavn Specific] Detected Type: {media_type}, ID: {media_id}")
            # <<< END JioSaavn Specific Check >>>

            # <<< General Parsing Logic (only if JioSaavn check didn't set ID/Type) >>>
            if media_id is None or media_type is None:
                print("[URL Parse] Using general parsing logic...") # Optional debug
                if not components or len(components) <= 2:
                     if len(components) == 2 and components[1]: raise ValueError(f"Could not determine media type from short URL path: {parsed_url.path}")
                     else: raise ValueError(f"Invalid URL path structure: {parsed_url.path}")
                url_constants = orpheus.module_settings[module_name].url_constants
                if not url_constants: url_constants = {'track': DownloadTypeEnum.track, 'album': DownloadTypeEnum.album, 'release': DownloadTypeEnum.album, 'playlist': DownloadTypeEnum.playlist, 'artist': DownloadTypeEnum.artist}
                type_matches = []; parsed_media_id = None # Use temporary variable name here
                for i, component in enumerate(components):
                    # Ensure component is a string before comparing
                    if isinstance(component, str):
                        for url_keyword, type_enum in url_constants.items():
                            if component == url_keyword:
                                type_matches.append(type_enum)
                                if i + 1 < len(components): parsed_media_id = components[i+1]
                                break
                        if type_matches and parsed_media_id is not None: break
                if not type_matches: raise ValueError(f"Could not determine media type from URL path components: {components}")
                media_type = type_matches[-1]
                if parsed_media_id is None:
                    if len(components) > 1: parsed_media_id = components[-1]
                    else: raise ValueError(f"Could not determine media ID from URL path: {parsed_url.path}")
                media_id = parsed_media_id # Assign to the main variable
                print(f"[URL Parse - General] Detected Type: {media_type}, ID: {media_id}")

        downloader.service = orpheus.load_module(module_name)
        downloader.service_name = module_name
        downloader.download_mode = media_type

        # --- Download Logic by Type ---
        if media_type == DownloadTypeEnum.track:
            if stop_event.is_set(): is_cancelled = True
            else:
                oprinter.oprint(f"Processing track: {media_id}")
                downloader.download_track(track_id=str(media_id), album_location=output_path + '/')
                output_queue.put('\n')
        elif media_type == DownloadTypeEnum.playlist:
            oprinter.oprint(f"Fetching playlist info: {media_id}")
            data_dict = {}; raw_result = search_result_data.get('raw_result') if search_result_data else None
            if downloader.service_name == 'soundcloud':
                try:
                    oprinter.oprint(f"Resolving SoundCloud URL for playlist {media_id}...")
                    resolved_data = downloader.service.websession.resolve_url(url)
                    if resolved_data and resolved_data.get('id') == media_id: data_dict = {media_id: resolved_data}
                    else: oprinter.oprint(f"[Warning] Failed to resolve SoundCloud URL or ID mismatch for {media_id}. Proceeding without pre-fetched data."); data_dict = {}
                except Exception as e: oprinter.oprint(f"[Error] Resolving SoundCloud URL failed: {e}"); data_dict = {}
            # Call get_playlist_info with appropriate parameters based on service
            playlist_info = None # Initialize
            try:
                if downloader.service_name == 'soundcloud':
                    playlist_info = downloader.service.get_playlist_info(playlist_id=media_id, data=data_dict)
                elif downloader.service_name == 'deezer':
                    playlist_info = downloader.service.get_playlist_info(playlist_id=media_id, data={}) # Deezer needs empty dict
                else: # Qobuz, Tidal, Beatport etc. don't expect 'data'
                    playlist_info = downloader.service.get_playlist_info(playlist_id=media_id)
            except Exception as e:
                oprinter.oprint(f"[Error] Failed to get playlist info for {media_id}: {e}")

            if playlist_info and playlist_info.tracks:
                num_tracks = len(playlist_info.tracks); oprinter.oprint(f"Playlist '{playlist_info.name}' contains {num_tracks} tracks.")
                playlist_tags = {}; raw_tags = playlist_info.asdict() if hasattr(playlist_info, 'asdict') else vars(playlist_info)
                for k, v in raw_tags.items():
                    if isinstance(v, (str, int, bool, float)): playlist_tags[k] = re.sub(r'[\\/:*?"<>|]', '_', str(v)).strip() if isinstance(v, str) else v
                playlist_tags['explicit'] = ' [E]' if playlist_info.explicit else ''; playlist_path_format = downloader_settings['formatting']['playlist_format']
                output_queue.put(f"Starting playlist download: '{playlist_info.name}' ({num_tracks} tracks)\n")
                try: relative_playlist_path = playlist_path_format.format(**playlist_tags)
                except KeyError as fmt_e: print(f"[Warning] Formatting KeyError for playlist path: {fmt_e}. Using default name."); relative_playlist_path = f"Playlist_{media_id}"
                relative_playlist_path = re.sub(r'[\\/:*?"<>|]', '_', relative_playlist_path).strip(); full_playlist_path = os.path.join(output_path, relative_playlist_path) + '/'; os.makedirs(full_playlist_path, exist_ok=True)

                for index, track_id in enumerate(playlist_info.tracks, start=1):
                    if stop_event.is_set(): is_cancelled = True; oprinter.oprint(f"Stop requested. Cancelling before track {index}/{num_tracks}."); break
                    output_queue.put("\n")
                    oprinter.oprint(f"Processing playlist track {index}/{num_tracks}: {track_id}")
                    percentage = (index / num_tracks) * 100; output_queue.put(f"Progress: Track {index}/{num_tracks} ({percentage:.0f}%)"); output_queue.put('\n\n')
                    downloader.download_track(track_id=track_id, album_location=full_playlist_path, track_index=index, number_of_tracks=num_tracks, extra_kwargs=playlist_info.track_extra_kwargs)
                    output_queue.put('\n')
            else: oprinter.oprint(f"Could not retrieve playlist info or playlist is empty.")
        elif media_type == DownloadTypeEnum.album:
            oprinter.oprint(f"Fetching album info: {media_id}")
            data_dict = {}; raw_result = search_result_data.get('raw_result') if search_result_data else None
            if downloader.service_name == 'soundcloud':
                try:
                    oprinter.oprint(f"Resolving SoundCloud URL for album {media_id}...")
                    resolved_data = downloader.service.websession.resolve_url(url)
                    if resolved_data and resolved_data.get('id') == media_id: data_dict = {media_id: resolved_data}
                    else: oprinter.oprint(f"[Warning] Failed to resolve SoundCloud URL or ID mismatch for album {media_id}."); data_dict = {}
                except Exception as e: oprinter.oprint(f"[Error] Resolving SoundCloud URL failed: {e}"); data_dict = {}

            album_info = None # Initialize
            try:
                # Call get_album_info with appropriate parameters based on service
                if downloader.service_name == 'soundcloud':
                    album_info = downloader.service.get_album_info(album_id=media_id, data=data_dict)
                elif downloader.service_name == 'deezer':
                     album_info = downloader.service.get_album_info(album_id=media_id, data={})
                else: # Qobuz, Tidal, Beatport etc. don't expect 'data'
                    album_info = downloader.service.get_album_info(album_id=media_id)
            except Exception as e:
                 oprinter.oprint(f"[Error] Failed to get album info for {media_id}: {e}")

            if album_info and album_info.tracks:
                num_tracks = len(album_info.tracks); output_queue.put(f"Starting album download: '{album_info.name}' ({num_tracks} tracks)\n")
                album_path = downloader._create_album_location(output_path, media_id, album_info); downloader.print(f'=== Downloading album {album_info.name} ({media_id}) ==='); downloader._download_album_files(album_path, album_info)
                for index, track_id in enumerate(album_info.tracks, start=1):
                    if stop_event.is_set(): is_cancelled = True; oprinter.oprint(f"Stop requested. Cancelling before track {index}/{num_tracks}."); break
                    output_queue.put("\n")
                    downloader.set_indent_number(2); oprinter.oprint(f"Processing album track {index}/{num_tracks}: {track_id}")
                    percentage = (index / num_tracks) * 100; output_queue.put(f"Progress: Track {index}/{num_tracks} ({percentage:.0f}%)"); output_queue.put('\n\n')
                    downloader.download_track(track_id=track_id, album_location=album_path, track_index=index, number_of_tracks=num_tracks, extra_kwargs=album_info.track_extra_kwargs, indent_level=2)
                    output_queue.put('\n')
                downloader.set_indent_number(1)
            else: oprinter.oprint(f"Could not retrieve album info or album is empty.")
        elif media_type == DownloadTypeEnum.artist:
            oprinter.oprint(f"Fetching artist info: {media_id}")
            data_dict = {}; raw_result = search_result_data.get('raw_result') if search_result_data else None
            if downloader.service_name == 'soundcloud':
                try:
                    oprinter.oprint(f"Resolving SoundCloud URL for artist {media_id}...")
                    resolved_data = downloader.service.websession.resolve_url(url)
                    if resolved_data and resolved_data.get('id') == media_id: data_dict = {media_id: resolved_data}
                    else: oprinter.oprint(f"[Warning] Failed to resolve SoundCloud URL or ID mismatch for {media_id}. Proceeding without pre-fetched data."); data_dict = {}
                except Exception as e: oprinter.oprint(f"[Error] Resolving SoundCloud URL failed: {e}"); data_dict = {}

            artist_info = None # Initialize
            try:
                # Call get_artist_info with appropriate parameters based on service
                if downloader.service_name == 'soundcloud':
                    artist_info = downloader.service.get_artist_info(artist_id=media_id, get_credited_albums=downloader_settings['artist_downloading']['return_credited_albums'], data=data_dict)
                else: # Deezer, Qobuz, Tidal, Beatport etc. don't expect 'data'
                    artist_info = downloader.service.get_artist_info(artist_id=media_id, get_credited_albums=downloader_settings['artist_downloading']['return_credited_albums'])
            except Exception as e:
                 oprinter.oprint(f"[Error] Failed to get artist info for {media_id}: {e}")

            if artist_info:
                artist_name = artist_info.name; oprinter.oprint(f"=== Downloading artist {artist_name} ({media_id}) ===")
                sanitized_artist_name = re.sub(r'[\\/:*?"<>|]', '_', artist_name).strip(); artist_path = os.path.join(output_path, sanitized_artist_name) + '/'; os.makedirs(artist_path, exist_ok=True)
                num_albums = len(artist_info.albums); tracks_downloaded_in_albums = []
                output_queue.put(f"Starting artist download: '{artist_name}' ({num_albums} albums + {len(artist_info.tracks)} potential tracks)\n")
                oprinter.oprint(f"Processing {num_albums} albums...")

                for index, album_id in enumerate(artist_info.albums, start=1):
                    if stop_event.is_set(): is_cancelled = True; oprinter.oprint(f"Stop requested. Cancelling before album {index}/{num_albums}."); break
                    output_queue.put("\n")
                    oprinter.oprint(f"Processing album {index}/{num_albums}: {album_id}")
                    data_dict_for_album = {}
                    album_info_for_artist = None # Initialize

                    try:
                        if downloader.service_name == 'soundcloud':
                            try:
                                oprinter.oprint(f"  Fetching SoundCloud album metadata for {album_id}...")
                                fetched_album_data = downloader.service.websession._get(f'playlists/{album_id}')
                                if fetched_album_data: data_dict_for_album = {album_id: fetched_album_data}
                                else: oprinter.oprint(f"  [Warning] Could not fetch metadata for SoundCloud album {album_id}.")
                            except Exception as e_sc_album: oprinter.oprint(f"  [Error] Fetching SoundCloud album metadata failed: {e_sc_album}")
                            album_info_for_artist = downloader.service.get_album_info(album_id=album_id, data=data_dict_for_album)
                        elif downloader.service_name == 'deezer':
                            album_info_for_artist = downloader.service.get_album_info(album_id=album_id, data={})
                        else:
                            album_info_for_artist = downloader.service.get_album_info(album_id=album_id)
                    except Exception as e_album_get:
                        oprinter.oprint(f"Could not get info for album {album_id}, skipping. Error: {e_album_get}")
                        continue # Skip to next album if getting info fails

                    if album_info_for_artist and album_info_for_artist.tracks:
                         album_path = downloader._create_album_location(artist_path, album_id, album_info_for_artist); downloader._download_album_files(album_path, album_info_for_artist)
                         num_album_tracks = len(album_info_for_artist.tracks); output_queue.put(f"Artist Progress: Album {index}/{num_albums} - '{album_info_for_artist.name}' ({num_album_tracks} tracks)\n")
                         for track_index, track_id in enumerate(album_info_for_artist.tracks, start=1):
                             if stop_event.is_set(): is_cancelled = True; oprinter.oprint(f"Stop requested. Cancelling during album '{album_info_for_artist.name}' before track {track_index}/{num_album_tracks}."); break
                             output_queue.put("\n")
                             downloader.set_indent_number(3); oprinter.oprint(f"Processing album track {track_index}/{num_album_tracks}: {track_id}")
                             track_percentage = (track_index / num_album_tracks) * 100; output_queue.put(f"  -> Album Track {track_index}/{num_album_tracks} ({track_percentage:.0f}%)"); output_queue.put('\n\n')
                             downloader.download_track(track_id=track_id, album_location=album_path, track_index=track_index, number_of_tracks=num_album_tracks, main_artist=artist_name, extra_kwargs=album_info_for_artist.track_extra_kwargs, indent_level=3)
                             output_queue.put('\n'); tracks_downloaded_in_albums.append(track_id)
                         if is_cancelled: break
                    # No 'else' needed here because the 'continue' above handles the case where album_info failed
                if is_cancelled: pass
                elif not is_cancelled:
                    skip_tracks = downloader_settings['artist_downloading']['separate_tracks_skip_downloaded']
                    standalone_tracks = [tid for tid in artist_info.tracks if not skip_tracks or tid not in tracks_downloaded_in_albums]; num_standalone = len(standalone_tracks)
                    if num_standalone > 0:
                        oprinter.oprint(f"Processing {num_standalone} standalone tracks..."); output_queue.put(f"Artist Progress: Processing {num_standalone} standalone tracks...\n")
                        for index, track_id in enumerate(standalone_tracks, start=1):
                            if stop_event.is_set(): is_cancelled = True; oprinter.oprint(f"Stop requested. Cancelling before standalone track {index}/{num_standalone}."); break
                            output_queue.put("\n")
                            downloader.set_indent_number(2); oprinter.oprint(f"Processing standalone track {index}/{num_standalone}: {track_id}")
                            standalone_percentage = (index / num_standalone) * 100; output_queue.put(f"  -> Standalone Track {index}/{num_standalone} ({standalone_percentage:.0f}%)"); output_queue.put('\n\n')
                            downloader.download_track(track_id=track_id, album_location=artist_path, main_artist=artist_name, number_of_tracks=1, indent_level=2, extra_kwargs=artist_info.track_extra_kwargs)
                            output_queue.put('\n')
            else: oprinter.oprint(f"Could not retrieve artist info.")
        else: print(f"ERROR: Unknown media type '{media_type.name if hasattr(media_type, 'name') else media_type}' encountered.")

        if is_cancelled: print("\nDownload Cancelled.")
        else: print("\nDownload process finished.")

    except (DownloadCancelledError, AuthenticationError, DownloadError, NetworkError, OrpheusdlError) as e:
        download_exception_occurred = True # <<< Mark exception occurred
        if isinstance(e, DownloadCancelledError):
             is_cancelled = True; download_exception_occurred = False # Cancellation is not an error for the sound
             print("\nDownload Cancelled (during file transfer).")
        else: error_type = type(e).__name__; print(f"\nERROR: {error_type}.\nDetails: {e}\n")
    except Exception as e:
        download_exception_occurred = True # <<< Mark exception occurred
        error_type = type(e).__name__; error_repr = repr(e); import traceback; tb_str = traceback.format_exc()
        print(f"\nUNEXPECTED ERROR during download thread.\nType: {error_type}\nDetails: {error_repr}\nTraceback:\n{tb_str}")
    finally:
        end_time = datetime.datetime.now(); total_duration = end_time - start_time; formatted_time = beauty_format_seconds(total_duration.total_seconds())
        final_status_message = "Download Cancelled." if is_cancelled else "Download Finished."
        summary_message = f"{final_status_message}\nTotal time taken: {formatted_time}\n"
        print(summary_message)

        sys.stdout = original_stdout
        sys.stderr = original_stderr

        download_successful = not is_cancelled and not download_exception_occurred # <<< Determine success

        def final_ui_update(success=False): # <<< Added success parameter
            # Access global widgets defined in main process block
            global download_process_active, download_button, progress_bar, stop_button, winsound # Add winsound to globals access
            try:
                # Check if widgets exist before configuring
                if 'download_button' in globals() and download_button and download_button.winfo_exists():
                    download_button.configure(state="normal")
                if 'progress_bar' in globals() and progress_bar and progress_bar.winfo_exists():
                    progress_bar.stop(); progress_bar.set(0)
                if 'stop_button' in globals() and stop_button and stop_button.winfo_exists():
                    stop_button.configure(state="disabled")
                download_process_active = False # Reset flag

                # <<< Play platform-specific sound based on success/failure >>>
                current_platform = platform.system()
                sound_played = False # Flag to track if sound was attempted

                if current_platform == "Darwin":
                    try:
                        success_sound = "/System/Library/Sounds/Glass.aiff"
                        failure_sound = "/System/Library/Sounds/Sosumi.aiff" # Common macOS alert sound
                        sound_to_play = success_sound if success else failure_sound
                        status_text = "completion" if success else "failure/cancellation"

                        if os.path.exists(sound_to_play):
                            subprocess.run(["afplay", sound_to_play], check=False, capture_output=True)
                            print(f"[Sound] Played download {status_text} sound (macOS).")
                            sound_played = True
                        else:
                            print(f"[Sound] Warning: Sound file not found: {sound_to_play}")
                    except Exception as sound_e:
                        print(f"[Sound] Error playing sound (macOS): {sound_e}")

                elif current_platform == "Windows":
                    # Check if winsound was imported successfully (using the global variable)
                    if winsound:
                        try:
                            success_alias = "SystemAsterisk"
                            failure_alias = "SystemHand" # Common Windows error/stop sound
                            sound_alias_to_play = success_alias if success else failure_alias
                            status_text = "completion" if success else "failure/cancellation"

                            # SND_ALIAS: Play system sound alias, SND_ASYNC: Play asynchronously
                            winsound.PlaySound(sound_alias_to_play, winsound.SND_ALIAS | winsound.SND_ASYNC)
                            print(f"[Sound] Played download {status_text} sound (Windows).")
                            sound_played = True
                        except RuntimeError as sound_e: # Catches errors like sound device unavailable
                            print(f"[Sound] Error playing sound (Windows): {sound_e}")
                        except Exception as sound_e:
                             print(f"[Sound] Unexpected error playing sound (Windows): {sound_e}")
                    # else: # winsound was not imported, message already printed at startup
                    #    pass

                if not sound_played:
                    print("[Sound] No sound played for download result.")

            except NameError: print("[Debug] UI element(s) not found in final_ui_update.")
            except tkinter.TclError as e: print(f"TclError in final UI update (widget destroyed?): {e}")
            except Exception as ui_update_e: print(f"[Error] Exception during final UI update: {ui_update_e}")
            finally:
                 download_process_active = False # Ensure flag is reset even on error

        try:
            # Ensure app exists before scheduling update
            if 'app' in globals() and app and app.winfo_exists():
                # <<< Pass success status to lambda >>>
                app.after(0, lambda s=download_successful: final_ui_update(success=s))
            else: print("[Debug] 'app' not found in finally block for UI update scheduling.")
        except NameError:
            print("[Debug] 'app' NameError in finally block.")
        except Exception as final_e:
             print(f"[Error] Exception scheduling final UI update: {final_e}")

# --- Start Download Thread ---
def start_download_thread(search_result_data=None):
    """Validates inputs and starts the download process in a separate thread using the global Orpheus instance."""
    # Access global variables defined within the main process block
    global download_process_active, current_settings, orpheus_instance, url_entry, path_var_main, stop_event

    if orpheus_instance is None:
        show_centered_messagebox("Error", "Orpheus library not initialized. Cannot start download.", dialog_type="error")
        print("Download cancelled: Orpheus instance is None.")
        return

    try:
        # Ensure widgets exist before accessing .get()
        if 'url_entry' not in globals() or not url_entry or not url_entry.winfo_exists():
            print("Error: URL entry widget not available."); return
        if 'path_var_main' not in globals() or not path_var_main:
            print("Error: Path variable not available."); return

        url = url_entry.get().strip()
        if not url: show_centered_messagebox("Info", "Please enter a URL.", dialog_type="warning"); return
        try: parsed_url = urlparse(url)
        except Exception as parse_e: show_centered_messagebox("URL Error", f"Could not parse the entered URL: {parse_e}", dialog_type="error"); return
        if not parsed_url.scheme in ['http', 'https'] or not parsed_url.netloc: show_centered_messagebox("Invalid URL", "Please enter a valid web URL starting with http(s)://", dialog_type="warning"); return

        output_path = path_var_main.get().strip()
        if not output_path: show_centered_messagebox("Info", "Please select a download path.", dialog_type="warning"); return
        if download_process_active: show_centered_messagebox("Busy", "A download is already in progress!", dialog_type="warning"); return

        try:
            norm_path = os.path.normpath(output_path); output_path_final = os.path.join(norm_path, '') # Ensure trailing slash for consistency maybe? Orpheus handles it.
            if os.path.exists(norm_path):
                if not os.path.isdir(norm_path): show_centered_messagebox("Error", f"Output path '{norm_path}' exists but is a file.", dialog_type="error"); return
            else: os.makedirs(norm_path, exist_ok=True); print(f"Created output directory: {norm_path}")
        except OSError as e: show_centered_messagebox("Error", f"Invalid or inaccessible output path: '{output_path}'.\nError: {e}", dialog_type="error"); return
        except Exception as e: show_centered_messagebox("Error", f"An unexpected error occurred validating path '{output_path}'.\nError: {e}", dialog_type="error"); return

        set_ui_state_downloading(True)
        stop_event.clear()
        download_process_active = True

        # Pass the *global* orpheus_instance
        download_thread = threading.Thread(target=run_download_in_thread, args=(orpheus_instance, url, output_path_final, current_settings, search_result_data), daemon=True)
        print("Starting download thread...")
        download_thread.start()
    except NameError as e:
        print(f"Error starting download (widgets not ready?): {e}")
        download_process_active = False # Reset flag if start fails
    except Exception as e:
        print(f"Unexpected error in start_download_thread: {e}")
        set_ui_state_downloading(False) # Try to reset UI
        download_process_active = False # Reset flag

def stop_download():
    # Access global variables defined within the main process block
    global stop_event, output_queue
    stop_event.set()
    output_queue.put("Download stop requested...\n")

# =============================================================================
# --- 8. SEARCH LOGIC ---
# =============================================================================

# --- Search Platform/Type Handling ---
def on_platform_change(*args):
    # Access global 'platform_var' defined in main process block
    global platform_var
    try:
        # Ensure var exists
        if 'platform_var' in globals() and platform_var:
            platform = platform_var.get(); update_search_types(platform)
    except NameError: pass # Should not happen with check
    except Exception as e: print(f"Error in on_platform_change: {e}")

def update_search_types(platform):
    # Access global 'type_var', 'type_combo' defined in main process block
    global type_var, type_combo
    platform_types = { "Beatport": ["track", "artist", "album"], "Qobuz": ["track", "artist", "playlist", "album"], "Tidal": ["track", "artist", "playlist", "album"], "Deezer": ["track", "artist", "playlist", "album"], "SoundCloud": ["track", "artist", "playlist"], "Napster": ["track", "artist", "playlist", "album"], "Idagio": ["track", "artist", "album"], "BugsMusic": ["track", "artist", "album"], "KKBOX": ["track", "artist", "playlist", "album"], "Nugs": ["track", "artist", "album"], }
    all_search_types = sorted(["track", "artist", "playlist", "album"])
    available_types = sorted(platform_types.get(platform, all_search_types))
    try:
        # Ensure widgets/vars exist
        if 'type_var' in globals() and type_var and 'type_combo' in globals() and type_combo and type_combo.winfo_exists():
            current_type = type_var.get(); type_combo.configure(values=available_types)
            if current_type in available_types: type_var.set(current_type)
            elif "track" in available_types: type_var.set("track")
            elif available_types: type_var.set(available_types[0])
            else: type_var.set("")
    except NameError: pass # Should not happen with checks
    except tkinter.TclError as e: print(f"TclError updating search types (widget destroyed?): {e}")
    except Exception as e: print(f"Error updating search types: {e}")

# --- Search Results Handling ---
def clear_treeview():
    # Access global 'tree', 'scrollbar', 'app' defined in main process block
    global tree, scrollbar, app
    try:
        # Ensure widgets exist
        if 'tree' in globals() and tree and tree.winfo_exists():
            for item in tree.get_children(): tree.delete(item)
        # Ensure app exists before scheduling scrollbar check
        if 'app' in globals() and app and app.winfo_exists() and 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists():
            app.after(0, lambda: _check_and_toggle_scrollbar(tree, scrollbar))
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError clearing treeview (widget destroyed?): {e}")
    except Exception as e: print(f"Error clearing treeview: {e}")

def clear_search_results_data():
     # Access global variables defined within the main process block
     global search_results_data, selection_var, search_download_button
     search_results_data = []
     try:
        # Ensure widgets/vars exist
        if 'selection_var' in globals() and selection_var:
            if selection_var.get() != "": selection_var.set("")
        if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists():
            search_download_button.configure(state="disabled")
     except NameError: pass
     except tkinter.TclError as e: print(f"TclError clearing search results data (widget destroyed?): {e}")
     except Exception as e: print(f"Error clearing search results data: {e}")

def clear_search_ui():
    # Access global 'search_entry', 'search_progress_bar' defined in main process block
    global search_entry, search_progress_bar
    # REMOVED: Don't clear the search entry itself
    # try:
    #     if 'search_entry' in globals() and search_entry and search_entry.winfo_exists():
    #         search_entry.delete(0, tkinter.END)
    # except NameError: pass
    # except tkinter.TclError as e: print(f"TclError clearing search UI (widget destroyed?): {e}")
    # except Exception as e: print(f"Error clearing search UI: {e}")

    clear_treeview(); clear_search_results_data()
    try:
        if 'search_progress_bar' in globals() and search_progress_bar and search_progress_bar.winfo_exists():
            search_progress_bar.stop(); search_progress_bar.set(0)
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError resetting search progress bar (widget destroyed?): {e}")
    except Exception as e: print(f"Error resetting search progress bar: {e}")

def display_results(results):
    # Access global variables defined within the main process block
    global search_results_data, tree, scrollbar, app, platform_var, type_var
    print(f"Received {len(results)} search results to display.")
    clear_treeview(); search_results_data = []
    item_number = 1
    # Local scope DownloadTypeEnum is fine here if ORPHEUS_AVAILABLE is false, otherwise use imported one
    local_DownloadTypeEnum = DownloadTypeEnum # Use imported if available, else local dummy
    try:
        # Ensure vars exist
        current_search_type_str = type_var.get() if ('type_var' in globals() and type_var) else "track" # Default to track if var missing
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
        name = result.get('title', 'N/A')         # Main name (Track, Album, Artist, Playlist)
        artist_str = result.get('artist', 'N/A') # Artist field from formatted result
        duration_str = result.get('duration', '-')
        year = str(result.get('year', '-'))
        explicit = result.get('explicit', '')
        additional_str = result.get('quality', 'N/A')

        result_entry = {
            "id": res_id, "number": str(item_number), "title": name,
            "artist": artist_str, "duration": duration_str, "year": year,
            "additional": additional_str, "explicit": explicit,
            "platform": current_platform_str, "type": current_search_type_str,
            "raw_result": result.get('raw_result')
        }
        # Store slightly differently for artist search type for clarity internally
        if current_search_type_str == "artist": # Compare with string directly
            result_entry["title"] = "" # No title for artist
            result_entry["artist"] = name # Artist name is the main 'name'

        search_results_data.append(result_entry)

        try:
            # Ensure tree exists
            if 'tree' in globals() and tree and tree.winfo_exists():
                # Explicitly define values tuple based on type
                if current_search_type_str == "artist":
                    # Artist Search: # | Title='' | Artist=name | Duration='' | Year='' | Add | Exp | ID
                    values = (
                        str(item_number),
                        "",             # Index 1: Title Column
                        name,           # Index 2: Artist Column
                        "",             # Index 3: Duration Column
                        "",             # Index 4: Year Column
                        additional_str, # Index 5: Additional Column
                        explicit,       # Index 6: Explicit Column
                        res_id          # Index 7: ID Column (hidden)
                    )
                else:
                    # Other searches: # | Title=name | Artist=artist_str | Duration | Year | Add | Exp | ID
                    values = (
                        str(item_number),
                        name,           # Index 1: Title Column
                        artist_str,     # Index 2: Artist Column
                        duration_str,   # Index 3: Duration Column
                        year,           # Index 4: Year Column
                        additional_str, # Index 5: Additional Column
                        explicit,       # Index 6: Explicit Column
                        res_id          # Index 7: ID Column (hidden)
                    )

                tree.insert("", "end", iid=res_id, values=values)
                item_number += 1
            else:
                break # Stop if tree is gone
        except NameError: break
        except tkinter.TclError as e: print(f"TclError inserting into treeview (widget destroyed?): {e}"); break
        except Exception as e: print(f"Error inserting into treeview: {e}")
    print(f"Displayed {item_number - 1} results.")
    try:
        # Ensure app exists before scheduling scrollbar check
        if 'app' in globals() and app and app.winfo_exists() and 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists():
            app.after(50, lambda: _check_and_toggle_scrollbar(tree, scrollbar))
    except NameError: pass
    except Exception as e: print(f"Error scheduling scrollbar check after display: {e}")

# --- Search Thread Target ---
def run_search_thread_target(orpheus, platform_name, search_type_str, query, gui_settings):
    """Runs the search using the provided global Orpheus instance."""
    # Access global variables defined within the main process block
    global search_process_active, app, output_queue, DEFAULT_SETTINGS
    # Local scope DownloadTypeEnum is fine here if ORPHEUS_AVAILABLE is false, otherwise use imported one
    local_DownloadTypeEnum = DownloadTypeEnum # Use imported if available, else local dummy

    if orpheus is None:
        # Ensure output_queue exists before putting message
        if 'output_queue' in globals() and output_queue:
            output_queue.put("ERROR: Orpheus instance not available. Cannot start search.\n")
        print("ERROR: run_search_thread_target called with invalid Orpheus instance.")
        try:
            # Ensure app exists before scheduling UI reset
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
        except (ValueError, TypeError): print(f"Warning: Invalid search_limit '{search_limit}', defaulting to 20."); search_limit = 20
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
    except Exception as e: error_message = f"Error during search: {str(e)}"; print(error_message)
    finally:
        def _update_ui():
            # Access global 'search_process_active' defined in main process block
            global search_process_active
            set_ui_state_searching(False)
            if error_message: show_centered_messagebox("Search Error", error_message, dialog_type="error"); clear_treeview(); clear_search_results_data()
            elif not results: show_centered_messagebox("No Results", "The search completed successfully, but found no results matching your query.", dialog_type="info"); display_results([])
            else: display_results(results)
            search_process_active = False # Reset flag
        try:
            # Ensure app exists before scheduling update
            if 'app' in globals() and app and app.winfo_exists():
                app.after(0, _update_ui)
            else:
                print("[Debug] 'app' not found for search UI update.")
                search_process_active = False # Reset flag anyway
        except NameError:
            search_process_active = False # Reset flag
        except Exception as e:
            print(f"Error scheduling search UI update: {e}")
            search_process_active = False # Reset flag

# --- Start Search ---
def start_search():
    """Validates input and starts the search process in a separate thread using the global Orpheus instance."""
    # Access global variables defined within the main process block
    global search_process_active, current_settings, orpheus_instance, search_entry, platform_var, type_var

    if orpheus_instance is None:
        show_centered_messagebox("Error", "Orpheus library not initialized. Cannot start search.", dialog_type="error")
        print("Search cancelled: Orpheus instance is None.")
        return

    try:
        # Ensure widgets/vars exist
        if 'search_entry' not in globals() or not search_entry or not search_entry.winfo_exists(): print("Error: Search entry widget not available."); return
        if 'platform_var' not in globals() or not platform_var: print("Error: Platform variable not available."); return
        if 'type_var' not in globals() or not type_var: print("Error: Type variable not available."); return

        query = search_entry.get().strip(); platform_name = platform_var.get(); search_type_str = type_var.get()
        if not query: show_centered_messagebox("Info", "Please enter a search query.", dialog_type="warning"); return
        if not platform_name: show_centered_messagebox("Info", "Please select a platform.", dialog_type="warning"); return
        if not search_type_str: show_centered_messagebox("Info", "Please select a search type.", dialog_type="warning"); return
        if search_process_active: show_centered_messagebox("Busy", "A search is already in progress!", dialog_type="warning"); return

        clear_search_ui() # Use helper that already checks widget existence
        set_ui_state_searching(True)
        search_process_active = True

        # Pass the *global* orpheus_instance
        search_thread = threading.Thread(target=run_search_thread_target, args=(orpheus_instance, platform_name, search_type_str, query, current_settings), daemon=True)
        print("Starting search thread...")
        search_thread.start()
    except NameError as e:
        print(f"Error starting search (widgets not ready?): {e}")
        search_process_active = False # Reset flag
    except Exception as e:
        print(f"Unexpected error in start_search: {e}")
        set_ui_state_searching(False) # Try to reset UI
        search_process_active = False # Reset flag

# --- Search Result Selection and Handling ---
def on_tree_select(event):
    # Access global variables defined within the main process block
    global tree, search_results_data, selection_var, search_download_button
    try:
        # Ensure widgets/vars exist
        if 'tree' not in globals() or not tree or not tree.winfo_exists(): return
        if 'selection_var' not in globals() or not selection_var: return
        if 'search_download_button' not in globals() or not search_download_button or not search_download_button.winfo_exists(): return

        selection = tree.selection()
        if selection:
            selected_iid = selection[0]
            selected_item_data = next((item for item in search_results_data if str(item.get('id')) == str(selected_iid)), None)
            if selected_item_data: selection_var.set(selected_item_data['number']); search_download_button.configure(state="normal")
            else: print(f"Selected iid {selected_iid} not found."); selection_var.set(""); search_download_button.configure(state="disabled")
        else: selection_var.set(""); search_download_button.configure(state="disabled")
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError in tree select (widget destroyed?): {e}")
    except Exception as e: print(f"Error in tree select: {e}")

def on_selection_change(*args):
    # Access global variables defined within the main process block
    global selection_var, search_results_data, search_download_button
    try:
        # Ensure widgets/vars exist
        if 'selection_var' not in globals() or not selection_var: return
        if 'search_download_button' not in globals() or not search_download_button or not search_download_button.winfo_exists(): return

        selection_num_str = selection_var.get().strip()
        if not selection_num_str: search_download_button.configure(state="disabled"); return
        selection_num = int(selection_num_str)
        matching_item = next((item for item in search_results_data if item.get('number') == str(selection_num)), None)
        search_download_button.configure(state="normal" if matching_item else "disabled")
    except NameError: pass
    except ValueError:
        if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists():
            search_download_button.configure(state="disabled")
    except tkinter.TclError as e: print(f"TclError in selection change (widget destroyed?): {e}")
    except Exception as e:
        print(f"Error in selection change validation: {e}")
        if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists():
            search_download_button.configure(state="disabled")

def get_selected_item_data():
    # Access global variables defined within the main process block
    global selection_var, search_results_data
    try:
        # Ensure var exists
        if 'selection_var' not in globals() or not selection_var: return None

        selection_num_str = selection_var.get().strip()
        if not selection_num_str: return None
        selection_num = int(selection_num_str)
        return next((item for item in search_results_data if item.get('number') == str(selection_num)), None)
    except NameError: return None
    except (ValueError, Exception): return None

def build_url_from_result(result_data):
    platform = result_data.get('platform'); search_type = result_data.get('type'); item_id = result_data.get('id'); raw_result_obj = result_data.get('raw_result')
    if not all([platform, search_type, item_id]): print("[URL Build] Missing data."); return None
    p_lower = platform.lower(); t_lower = search_type.lower()
    if p_lower == "soundcloud":
        if raw_result_obj:
            permalink = getattr(raw_result_obj, 'permalink_url', None)
            if permalink: print(f"[SC URL] Using permalink: {permalink}"); return permalink
            else: print("[SC URL] No permalink in raw. Fallback.")
        else: print("[SC URL] No raw result. Fallback.")
        if t_lower == 'track': sc_entity = 'tracks'
        elif t_lower == 'playlist': sc_entity = 'playlists'
        elif t_lower == 'artist': sc_entity = 'users'
        else: print(f"[SC URL] Unknown type '{t_lower}'."); return None
        sc_api_url = f"https://api.soundcloud.com/{sc_entity}/{item_id}"
        widget_api_url = f'https://api-widget.soundcloud.com/resolve?url={sc_api_url}&format=json&client_id=gqKBMSuBw5rbN9rDRYPqKNvF17ovlObu&app_version=1742894364' # Client ID might change
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
    else:
        base_urls = { "qobuz": "https://open.qobuz.com", "tidal": "https://listen.tidal.com", "deezer": "https://www.deezer.com", "beatport": "https://www.beatport.com", "napster": "https://web.napster.com", "idagio": "https://app.idagio.com" }
        type_paths = { "qobuz": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"}, "tidal": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"}, "deezer": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"}, "beatport": {"track": "track", "album": "release", "artist": "artist"}, "napster": {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist"}, "idagio": {"track": "recording", "album": "album", "artist": "artist"} }
        if p_lower in base_urls and p_lower in type_paths and t_lower in type_paths[p_lower]:
            url_path_segment = type_paths[p_lower][t_lower]; url = f"{base_urls[p_lower]}/{url_path_segment}/{item_id}"
            print(f"[URL Build - {platform}] Constructed: {url}"); return url
        else: print(f"[URL Build - {platform}] Not supported for type '{t_lower}'."); return None

def download_selected():
    # Access global 'tabview', 'url_entry' defined in main process block
    global tabview, url_entry
    try:
        selected_data = get_selected_item_data()
        if not selected_data: show_centered_messagebox("Error", "Invalid selection.", dialog_type="warning"); return
        url_to_download = build_url_from_result(selected_data)
        if url_to_download:
            print(f"Switching tab and starting download for: {url_to_download}")
            # Ensure widgets exist
            if 'tabview' in globals() and tabview and tabview.winfo_exists():
                tabview.set("Download")
            if 'url_entry' in globals() and url_entry and url_entry.winfo_exists():
                url_entry.delete(0, "end"); url_entry.insert(0, url_to_download)
            else: print("Warning: url_entry not found.")
            start_download_thread(search_result_data=selected_data) # Pass data which includes raw_result
        else: show_centered_messagebox("Error", f"Could not determine URL for selected item.", dialog_type="error")
    except NameError as e: print(f"Error in download_selected (widget not ready?): {e}")
    except tkinter.TclError as e: print(f"TclError in download_selected (widget destroyed?): {e}")
    except Exception as e: print(f"Unexpected error in download_selected: {e}")

# --- Search Result Sorting ---
def sort_results(column):
    # Access global variables defined within the main process block
    global sort_states, search_results_data, tree
    try:
        # Ensure tree exists
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
        clear_treeview() # Uses helper that checks widget existence
        for item_data in search_results_data:
            try:
                # Check tree existence again inside loop (paranoid)
                if 'tree' in globals() and tree and tree.winfo_exists():
                    values = ( item_data.get('number', ''), item_data.get('title', ''), item_data.get('artist', ''), item_data.get('duration', ''), item_data.get('year', ''), item_data.get('additional', ''), item_data.get('explicit', ''), item_data.get('id', '') )
                    tree.insert("", "end", iid=item_data['id'], values=values)
                else: break # Stop if tree is gone
            except NameError: break
            except tkinter.TclError as e: print(f"TclError repopulating sorted treeview (widget destroyed?): {e}"); break
            except Exception as e: print(f"Error repopulating sorted treeview: {e}")
        defined_columns = ("#", "Title", "Artist", "Duration", "Year", "Additional", "Explicit", "ID")
        for col in defined_columns:
            # Check tree existence before accessing heading
            if 'tree' in globals() and tree and tree.winfo_exists():
                try:
                    heading_text = tree.heading(col, "text").replace(" ▲", "").replace(" ▼", "")
                    indicator = "" if col != column else (" ▼" if is_reverse else " ▲")
                    tree.heading(col, text=heading_text + indicator)
                except tkinter.TclError: pass # Ignore if heading cannot be accessed
    except NameError: pass
    except tkinter.TclError as e: print(f"TclError sorting results (widget destroyed?): {e}")
    except Exception as e: print(f"Error sorting results by '{column}': {e}"); show_centered_messagebox("Error", f"Sort failed: {e}", dialog_type="error")

# =============================================================================
# --- 9. SETTINGS TAB LOGIC ---
# =============================================================================

def _update_settings_tab_widgets():
    # Access global variables defined within the main process block
    global current_settings, settings_vars, path_var_main, DEFAULT_SETTINGS
    print("Refreshing Settings tab UI from current_settings...")
    try:
        # Globals
        for key, var in settings_vars.get("globals", {}).items(): # Reverted loop iteration
            # <<< ADDED CHECK TO SKIP SPECIFIC ADVANCED SETTINGS >>>
            if key in ["advanced.codec_conversions", "advanced.conversion_flags"]:
                continue

            if not isinstance(var, tkinter.Variable):
                 # Skip if the structure is unexpected (e.g., complex dict placeholder)
                 if isinstance(var, dict) and not var: # Check for empty dict placeholder
                     pass
                 else:
                    continue

            keys = key.split('.'); temp_dict = current_settings.get("globals", {}); valid_path = True
            for k in keys:
                if isinstance(temp_dict, dict): temp_dict = temp_dict.get(k)
                else: valid_path = False; break
            value_from_dict = temp_dict if valid_path else None
            if value_from_dict is not None:
                try:
                    # Wrap var.set() in try...except
                    if isinstance(var, tkinter.BooleanVar):
                        var.set(bool(value_from_dict))
                    else:
                        var.set(str(value_from_dict))
                except tkinter.TclError as e_set:
                    if "invalid command name" in str(e_set):
                        # print(f"[TclError Suppressed] Setting variable for {key}: {e_set}")
                        pass # Suppress specific TclError
                    else:
                        print(f"Error setting variable for {key}: {e_set}") # Print/log other errors
                except Exception as e_set_other:
                    print(f"Error setting variable for {key}: {e_set_other}")

        # Credentials
        if 'DEFAULT_SETTINGS' not in globals(): return
        sorted_platforms = sorted(DEFAULT_SETTINGS["credentials"].keys())
        for platform_name in sorted_platforms:
            for field_key, var in settings_vars.get("credentials", {}).get(platform_name, {}).items(): # Reverted loop iteration
                if not isinstance(var, tkinter.Variable):
                     continue # Skip unexpected structure

                value_from_dict = current_settings.get("credentials", {}).get(platform_name, {}).get(field_key)
                if value_from_dict is not None:
                    try:
                         # Wrap var.set() in try...except
                         var.set(str(value_from_dict))
                    except tkinter.TclError as e_set_cred:
                        if "invalid command name" in str(e_set_cred):
                            # print(f"[TclError Suppressed] Setting variable for {platform_name}.{field_key}: {e_set_cred}")
                            pass # Suppress specific TclError
                        else:
                            print(f"Error setting variable for {platform_name}.{field_key}: {e_set_cred}")
                    except Exception as e_set_cred_other:
                        print(f"Error setting variable for {platform_name}.{field_key}: {e_set_cred_other}")

        # Main Path
        if 'path_var_main' in globals() and isinstance(path_var_main, tkinter.Variable):
             main_path_val = current_settings.get("globals", {}).get("general", {}).get("output_path")
             if main_path_val is not None:
                  try:
                      # Wrap path_var_main.set() in try...except
                      path_var_main.set(main_path_val)
                  except tkinter.TclError as e_set_main:
                      if "invalid command name" in str(e_set_main):
                          # print(f"[TclError Suppressed] Setting main path variable: {e_set_main}")
                          pass # Suppress specific TclError
                      else:
                          print(f"Error setting main path variable: {e_set_main}")
                  except Exception as e_set_main_other:
                      print(f"Error setting main path variable: {e_set_main_other}")

        print("Settings tab UI refresh finished.")
    except Exception as e: print(f"Error during settings UI refresh: {e}"); import traceback; traceback.print_exc()

# =============================================================================
# --- 10. MAIN EXECUTION ---
# =============================================================================

if __name__ == "__main__":
    multiprocessing.freeze_support() # Essential for PyInstaller bundling

    # --- Single Instance Check (Windows Only) ---
    _mutex_handle = None # Keep handle globally accessible if needed later, though OS cleanup is often enough
    if platform.system() == "Windows":
        try:
            from ctypes import windll, wintypes

            ERROR_ALREADY_EXISTS = 183
            mutex_name = "OrpheusDL_GUI_Instance_Mutex_8E1D3B4C_A5F8_4B9A_8D7C_6F0A1B3E4D5C"

            # Define CreateMutexW prototype for better error checking
            CreateMutexW = windll.kernel32.CreateMutexW
            CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            CreateMutexW.restype = wintypes.HANDLE

            # Define GetLastError prototype
            GetLastError = windll.kernel32.GetLastError
            GetLastError.restype = wintypes.DWORD

            # Attempt to create the mutex. Request initial ownership (bInitialOwner = True).
            _mutex_handle = CreateMutexW(None, True, mutex_name)

            last_error = GetLastError() # Check error code immediately after creation attempt

            if last_error == ERROR_ALREADY_EXISTS:
                print("[Instance Check] Mutex already exists. Another instance is running. Exiting.")
                # We didn't successfully create the handle if it already existed
                # No need to close _mutex_handle here as it would be NULL or invalid
                sys.exit()
            elif _mutex_handle is None or _mutex_handle == 0:
                # Handle other potential creation errors
                print(f"[Instance Check] Failed to create mutex. Error code: {last_error}")
                sys.exit("Error creating application mutex.")
            else:
                # Mutex created successfully, this is the first instance
                print("[Instance Check] Acquired mutex. This is the first instance.")
                # Keep _mutex_handle alive. OS should release on termination.

        except ImportError:
             print("[Instance Check] Warning: Could not import ctypes/windll. Single instance check skipped.")
        except Exception as e:
            print(f"[Instance Check] Error during single instance check: {e}")
            # Exit cautiously if the check fails
            sys.exit("Failed single instance check.")

    # --- Check if this is the MAIN process, not a spawned child ---
    if multiprocessing.parent_process() is None:
        print(f"[Main Process {os.getpid()}] Starting application...")

        # =====================================================================
        # --- GLOBAL VARIABLES & CONSTANTS (Main Process Only) ---
        # =====================================================================
        # Define globals that need function calls or are complex literals here
        _SCRIPT_DIR = get_script_directory() # Use the function defined at the top

        # --- Change CWD to script directory (especially for bundled apps) ---
        try:
            os.chdir(_SCRIPT_DIR)
            print(f"[CWD] Changed working directory to: {_SCRIPT_DIR}")
        except Exception as e_chdir:
            print(f"[CWD] Warning: Failed to change working directory: {e_chdir}")

        CONFIG_DIR = os.path.join(_SCRIPT_DIR, 'config')
        # DATA_DIR = os.path.join(_SCRIPT_DIR, 'data') # <<< Removed
        MODULES_DIR = os.path.join(_SCRIPT_DIR, 'modules') # <<< Define MODULES_DIR
        CONFIG_FILE_NAME = 'settings.json'
        CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)

        # --- Add external modules directory to sys.path --- 
        if os.path.isdir(MODULES_DIR):
            if MODULES_DIR not in sys.path:
                sys.path.insert(0, MODULES_DIR)
                print(f"[SysPath] Added external modules directory: {MODULES_DIR}")
            else:
                print(f"[SysPath] External modules directory already in sys.path: {MODULES_DIR}")
        else:
            print(f"[SysPath] External modules directory not found: {MODULES_DIR}")

        # --- Create necessary directories ---
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            # os.makedirs(DATA_DIR, exist_ok=True) # <<< Removed
            os.makedirs(MODULES_DIR, exist_ok=True)
            print(f"[Init] Ensured config directory exists: {CONFIG_DIR}")
            # print(f"[Init] Ensured data directory exists: {DATA_DIR}") # <<< Removed
            print(f"[Init] Ensured modules directory exists: {MODULES_DIR}")
        except OSError as e:
            print(f"[Error] Could not create config/data/modules directories: {e}")
            # Decide if critical, maybe exit? For now, just print.

        # --- Default Settings Structure ---
        DEFAULT_SETTINGS = {
            "globals": {
                "general": {
                    "output_path": os.path.join(_SCRIPT_DIR, "Downloads"),
                    "quality": "hifi",
                    "search_limit": 20
                },
                "artist_downloading": { "return_credited_albums": True, "separate_tracks_skip_downloaded": True },
                "formatting": { "album_format": "{name}{explicit}", "playlist_format": "{name}{explicit}", "track_filename_format": "{track_number}. {name}", "single_full_path_format": "{name}", "enable_zfill": True, "force_album_format": False },
                "codecs": { "proprietary_codecs": False, "spatial_codecs": True },
                "module_defaults": { "lyrics": "default", "covers": "default", "credits": "default" },
                "lyrics": { "embed_lyrics": True, "embed_synced_lyrics": False, "save_synced_lyrics": True },
                "covers": { "embed_cover": True, "main_compression": "high", "main_resolution": 1400, "save_external": False, "external_format": "png", "external_compression": "low", "external_resolution": 3000, "save_animated_cover": True },
                "playlist": { "save_m3u": True, "paths_m3u": "absolute", "extended_m3u": True },
                "advanced": { "advanced_login_system": False, "codec_conversions": { "alac": "flac", "wav": "flac" }, "conversion_flags": { "flac": { "compression_level": "5" } }, "conversion_keep_original": False, "cover_variance_threshold": 8, "debug_mode": False, "disable_subscription_checks": False, "enable_undesirable_conversions": False, "ignore_existing_files": False, "ignore_different_artists": True }
            },
            "credentials": {
                "Tidal": { "tv_atmos_token": "", "tv_atmos_secret": "", "mobile_atmos_hires_token": "", "mobile_hires_token": "", "enable_mobile": True, "prefer_ac4": False, "fix_mqa": True },
                "Qobuz": { "app_id": "", "app_secret": "", "quality_format": "{sample_rate}kHz {bit_depth}bit", "username": "", "password": "" },
                "Deezer": { "client_id": "", "client_secret": "", "bf_secret": "", "email": "", "password": "" },
                "SoundCloud": { "web_access_token": "" },
                "Napster": { "api_key": "", "customer_secret": "", "requested_netloc": "", "username": "", "password": "" },
                "Beatport": { "username": "", "password": "" },
                "BugsMusic": { "username": "", "password": "" },
                "Idagio": { "username": "", "password": "" },
                "KKBOX": { "kc1_key": "", "secret_key": "", "email": "", "password": "" },
                "Nugs": { "username": "", "password": "", "client_id": "", "dev_key": "" },
                "Musixmatch": { "token_limit": 10, "lyrics_format": "standard", "custom_time_decimals": False }
            }
        }

        # --- GUI State Variables ---
        output_queue = queue.Queue()
        stop_event = threading.Event()
        search_results_data = []
        sort_states = {}
        search_process_active = False
        download_process_active = False
        _last_message_was_empty = False # For log formatting

        # --- Context Menu Globals ---
        _context_menu = None
        _target_widget = None
        _hide_menu_binding_id = None
        BUTTON_COLOR = ("#E0E0E0", "#303030")
        # Add theme colors here
        BORDER = "#565B5E" # A neutral dark grey border
        # BUTTON_HOVER_COLOR unused

        # --- In-memory Settings & Global Orpheus Instance ---
        current_settings = {} # Loaded by load_settings()
        settings_vars = {"globals": {}, "credentials": {}} # Holds Tkinter variables linked to settings
        orpheus_instance = None # <<< Global Orpheus instance

        # =====================================================================
        # --- INITIALIZATION (Main Process Only) ---
        # =====================================================================
        try:
            load_settings()
            # <<< Debug Print 1 >>>
            print(f"[DEBUG] After load_settings: output_path = {current_settings.get('globals', {}).get('general', {}).get('output_path')}")
            initialize_orpheus() # <<< Attempt to initialize the global instance
        except FileNotFoundError as e:
             print(f"Initialization failed: {e}")
             # Optionally show a message box and exit if settings are critical
             # show_centered_messagebox("Fatal Error", str(e), dialog_type="error")
             sys.exit(1) # Exit if settings file is missing
        except Exception as e:
             print(f"Unexpected error during initialization: {e}")
             # Decide if the app can continue partially or should exit
             # show_centered_messagebox("Fatal Error", f"Initialization failed: {e}", dialog_type="error")
             # sys.exit(1)

        # =====================================================================
        # --- GUI SETUP (Main Process Only) ---
        # =====================================================================
        # <<< Debug Print 2 >>>
        print(f"[DEBUG] Before GUI setup: output_path = {current_settings.get('globals', {}).get('general', {}).get('output_path')}")
        app = customtkinter.CTk()
        app.title("OrpheusDL GUI")
        app.geometry("940x600")

        # Icon - Updated to check OS and look in root folder
        try:
            icon_filename = "icon.icns" if platform.system() == "Darwin" else "icon.ico"
            # Use resource_path to find the icon, works for dev and bundle
            icon_path = resource_path(icon_filename)
            print(f"Looking for main window icon at: {icon_path}")
            if os.path.exists(icon_path):
                if platform.system() != "Darwin":
                    app.iconbitmap(icon_path)
                    print(f"Set window icon from: {icon_path}")
                else:
                    print("Skipping app.iconbitmap on macOS (use .icns for app bundle/dock).")
            else:
                print(f"Window icon file not found: {icon_path}")
        except Exception as e:
            print(f"Error setting window icon: {e}")

        # Center Window (Reverted to simple calculation)
        screen_width = app.winfo_screenwidth()
        screen_height = app.winfo_screenheight()
        window_width = 940  # Use intended width
        window_height = 600 # Use intended height
        x_pos = (screen_width // 2) - (window_width // 2)
        y_pos = (screen_height // 2) - (window_height // 2)
        app.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}") # Apply intended size and calculated position

        # --- Main TabView ---
        tabview = customtkinter.CTkTabview(master=app); tabview.pack(padx=10, pady=10, expand=True, fill="both")

        # --- Download Tab ---
        download_tab = tabview.add("Download"); download_tab.grid_columnconfigure(1, weight=1); download_tab.grid_rowconfigure(2, weight=1)
        # URL Row
        url_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); url_frame.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(15,5)); url_frame.grid_columnconfigure(1, weight=1)
        url_label = customtkinter.CTkLabel(url_frame, text="URL"); url_label.grid(row=0, column=0, sticky="w", padx=5)
        url_entry = customtkinter.CTkEntry(url_frame, placeholder_text="Enter URL...", height=30, placeholder_text_color="#7F7F7F"); url_entry.grid(row=0, column=1, sticky="ew", padx=5)
        url_entry.bind("<Return>", lambda event: start_download_thread()); url_entry.bind("<Button-3>", show_context_menu); url_entry.bind("<Button-2>", show_context_menu); url_entry.bind("<Control-Button-1>", show_context_menu)
        url_entry.bind("<FocusIn>", lambda e, w=url_entry: handle_focus_in(w))
        url_entry.bind("<FocusOut>", lambda e, w=url_entry: handle_focus_out(w))
        clear_url_button = customtkinter.CTkButton(url_frame, text="Clear", width=100, height=30, command=clear_url_entry, fg_color="#343638", hover_color="#1F6AA5"); clear_url_button.grid(row=0, column=2, sticky="e", padx=5)
        download_button = customtkinter.CTkButton(url_frame, text="Download", width=100, height=30, command=start_download_thread, fg_color="#343638", hover_color="#1F6AA5"); download_button.grid(row=0, column=3, sticky="e", padx=5)
        # Path Row
        path_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); path_frame.grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=5); path_frame.grid_columnconfigure(1, weight=1)
        path_label = customtkinter.CTkLabel(path_frame, text="Output Path"); path_label.grid(row=0, column=0, sticky="w", padx=5)
        # Use current_settings which was loaded within this block
        path_var_main = tkinter.StringVar(value=current_settings.get("globals", {}).get("general", {}).get("output_path", DEFAULT_SETTINGS["globals"]["general"]["output_path"]))
        path_var_main.trace_add("write", _auto_save_path_change)
        path_entry = customtkinter.CTkEntry(path_frame, textvariable=path_var_main, height=30); path_entry.grid(row=0, column=1, sticky="ew", padx=5)
        path_entry.bind("<Button-3>", show_context_menu); path_entry.bind("<Button-2>", show_context_menu); path_entry.bind("<Control-Button-1>", show_context_menu)
        path_entry.bind("<FocusIn>", lambda e, w=path_entry: handle_focus_in(w))
        path_entry.bind("<FocusOut>", lambda e, w=path_entry: handle_focus_out(w))
        path_button = customtkinter.CTkButton(path_frame, text="Browse", width=100, height=30, command=lambda: browse_output_path(path_var_main), fg_color="#343638", hover_color="#1F6AA5"); path_button.grid(row=0, column=2, sticky="e", padx=5)
        open_path_button = customtkinter.CTkButton(path_frame, text="Open", width=100, height=30, command=open_download_path, fg_color="#343638", hover_color="#1F6AA5"); open_path_button.grid(row=0, column=3, sticky="e", padx=5)
        # Output Area
        output_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); output_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=15, pady=(15, 15)); output_frame.grid_rowconfigure(1, weight=1); output_frame.grid_columnconfigure(0, weight=1)
        # Remove explicit font from label
        output_label = customtkinter.CTkLabel(output_frame, text="OUTPUT", text_color="#898c8d", font=("Segoe UI", 11)); output_label.grid(row=0, column=0, sticky="w", pady=(0, 3))
        log_textbox = customtkinter.CTkTextbox(output_frame, wrap=tkinter.WORD, state='disabled', font=("Consolas", 12)); log_textbox.grid(row=1, column=0, sticky="nsew")
        # Bottom Controls
        bottom_frame = customtkinter.CTkFrame(download_tab, fg_color="transparent"); bottom_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(5, 10)); bottom_frame.grid_columnconfigure(0, weight=1)
        progress_bar = customtkinter.CTkProgressBar(bottom_frame); progress_bar.set(0); progress_bar.grid(row=0, column=0, sticky="ew", padx=(5, 5))
        clear_output_button = customtkinter.CTkButton(bottom_frame, text="Clear Output", width=100, height=30, command=clear_output_log, fg_color="#343638", hover_color="#1F6AA5"); clear_output_button.grid(row=0, column=1, sticky="e", padx=(5, 10))
        stop_button = customtkinter.CTkButton(bottom_frame, text="Stop", width=100, height=30, command=stop_download, fg_color="#343638", hover_color="#1F6AA5", state=tkinter.DISABLED); stop_button.grid(row=0, column=2, sticky="e", padx=(0, 5))

        # --- Search Tab ---
        search_tab = tabview.add("Search"); search_main_frame = customtkinter.CTkFrame(search_tab, fg_color="transparent"); search_main_frame.pack(fill="both", expand=True, padx=9, pady=(10,0))
        # Controls Frame
        controls_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); controls_frame.pack(fill="x", pady=(5, 10)); controls_frame.grid_columnconfigure(4, weight=1)
        customtkinter.CTkLabel(controls_frame, text="Platform").grid(row=0, column=0, padx=(5,5), sticky="w")
        # Use current_settings which was loaded within this block
        all_module_keys = current_settings.get("credentials", {}).keys(); platforms = sorted([name for name in all_module_keys if name != "Musixmatch"])
        platform_var = tkinter.StringVar(value=platforms[0] if platforms else ""); platform_combo = customtkinter.CTkComboBox(controls_frame, values=platforms, variable=platform_var, width=140, state="readonly", height=30, dropdown_fg_color="#2B2B2B"); platform_combo.grid(row=0, column=1, padx=5); platform_var.trace_add("write", on_platform_change)
        customtkinter.CTkLabel(controls_frame, text="Type").grid(row=0, column=2, padx=(5,5), sticky="w"); type_var = tkinter.StringVar(); type_combo = customtkinter.CTkComboBox(controls_frame, values=[], variable=type_var, width=100, state="readonly", height=30, dropdown_fg_color="#2B2B2B"); type_combo.grid(row=0, column=3, padx=5, sticky="w")
        search_input_frame = customtkinter.CTkFrame(controls_frame, fg_color="transparent"); search_input_frame.grid(row=0, column=4, sticky="ew", padx=(10, 5))
        search_entry = customtkinter.CTkEntry(search_input_frame, placeholder_text="Enter search query...", height=30, placeholder_text_color="#7F7F7F"); search_entry.pack(side="left", fill="x", expand=True, padx=(0, 0))
        search_entry.bind("<Return>", lambda e: start_search()); search_entry.bind("<Button-3>", show_context_menu); search_entry.bind("<Button-2>", show_context_menu); search_entry.bind("<Control-Button-1>", show_context_menu)
        search_entry.bind("<FocusIn>", lambda e, w=search_entry: handle_focus_in(w))
        search_entry.bind("<FocusOut>", lambda e, w=search_entry: handle_focus_out(w))
        clear_search_button = customtkinter.CTkButton(search_input_frame, text="Clear", command=clear_search_entry, width=100, height=30, fg_color="#343638", hover_color="#1F6AA5"); clear_search_button.pack(side="left", padx=(10, 0))
        button_search_frame = customtkinter.CTkFrame(controls_frame, fg_color="transparent"); button_search_frame.grid(row=0, column=5, padx=(5,0))
        search_button = customtkinter.CTkButton(button_search_frame, text="Search", command=start_search, width=100, height=30, fg_color="#343638", hover_color="#1F6AA5"); search_button.pack(side="left", padx=(0, 6))
        update_search_types(platform_var.get()) # Initial population
        # Results Area
        results_outer_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); results_outer_frame.pack(fill="both", expand=True, pady=(8,8))
        # Remove explicit font from label
        results_label = customtkinter.CTkLabel(results_outer_frame, text="RESULTS", text_color="#898c8d", font=("Segoe UI", 11)); results_label.pack(anchor="w", padx=6, pady=0)
        treeview_container = customtkinter.CTkFrame(results_outer_frame, fg_color="#1D1E1E"); treeview_container.pack(fill="both", expand=True, padx=6, pady=(3,0)); treeview_container.grid_columnconfigure(0, weight=1); treeview_container.grid_rowconfigure(0, weight=1); treeview_container.grid_columnconfigure(1, weight=0)
        # Style Treeview
        style = ttk.Style();
        try: style.theme_use('clam')
        except Exception: print("Clam theme not available.")

        # --- Font and Scaling Setup ---
        heading_font_config = None # Initialize

        if platform.system() == "Windows":
            try:
                # Get scaling factor (relative to 72 DPI)
                scaling_factor = app.tk.call('tk', 'scaling')
                print(f"[Style] Detected scaling factor: {scaling_factor}")
            except Exception as e:
                print(f"[Style] Error getting scaling factor: {e}. Defaulting to 1.0")
                scaling_factor = 1.0

            # --- Conditional Base Font Size (Windows Only) ---
            if scaling_factor > 1.5: # Heuristic for ~125% scaling or higher
                base_font_size = 6
            else: # For ~100% scaling or lower
                base_font_size = 7

            scaled_font_size = max(8, round(base_font_size * scaling_factor)) # Ensure minimum size 8

            # --- Conditional Row Height Multiplier (Windows Only) ---
            if scaling_factor > 1.5:
                row_height_multiplier = 3.4 # Target 34px for 10pt font
            else:
                row_height_multiplier = 2.9 # Target 26px for 9pt font

            scaled_row_height = max(20, round(scaled_font_size * row_height_multiplier)) # Calculate based on conditional multiplier
            tree_font_family = "Segoe UI" # Preferred Windows font
            print(f"[Style Windows] Using font: {tree_font_family} {scaled_font_size}pt (Scaled from {base_font_size}pt), Row height: {scaled_row_height}px")
            # Define font config for Windows heading (family, size) - assumes default weight is normal
            heading_font_config = (tree_font_family, scaled_font_size)

        else: # --- Default Settings for Non-Windows (macOS, Linux, etc.) ---
            scaled_font_size = 13 # Default size mainly for row height calculation
            scaled_row_height = max(20, round(scaled_font_size * 2.2)) # Use a standard multiplier
            tree_font_family = None # Use system default font family for base Treeview
            print(f"[Style Non-Windows] Using system default font, Row height: {scaled_row_height}px")
            # Define heading font config: Default family, explicit size 10, normal weight
            heading_font_config = (None, 10, 'normal')

        # --- Style Configuration (Applies chosen settings) ---
        tree_bg_color = "#1D1E1E"; tree_fg_color = "#DCE4EE"; tree_header_bg = "#1D1E1E"; tree_header_fg = "gray"; tree_selected_bg = "#1F6AA5"; tree_selected_fg = "#FFFFFF"

        # Configure base Treeview style
        style.configure("Custom.Treeview",
                        background=tree_bg_color,
                        foreground=tree_fg_color,
                        fieldbackground=tree_bg_color,
                        borderwidth=0,
                        relief="flat",
                        rowheight=scaled_row_height) # Apply scaled row height
        # Don't set base font explicitly on non-windows, let it default
        if platform.system() == "Windows":
            style.configure("Custom.Treeview", font=(tree_font_family, scaled_font_size))

        # Configure Heading style
        style.configure("Custom.Treeview.Heading",
                        background=tree_header_bg,
                        foreground=tree_header_fg,
                        borderwidth=0,
                        relief="flat",
                        padding=(5, 3))
        # Apply the conditionally determined heading font config
        if heading_font_config:
            style.configure("Custom.Treeview.Heading", font=heading_font_config)

        style.layout("Custom.Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        style.map("Custom.Treeview", background=[('selected', tree_selected_bg)], foreground=[('selected', tree_selected_fg)])
        # Keep header hover distinct for better feedback
        style.map("Custom.Treeview.Heading", background=[('active', "#1F6AA5"), ('!active', tree_header_bg)], foreground=[('active', tree_selected_fg), ('!active', tree_header_fg)])

        # Create Treeview
        columns = ("#", "Title", "Artist", "Duration", "Year", "Additional", "Explicit", "ID"); tree = ttk.Treeview(treeview_container, columns=columns, show="headings", selectmode="browse", style="Custom.Treeview"); tree.grid(row=0, column=0, sticky="nsew", padx=(5,0), pady=3)
        col_configs = {"#": {"text": "#", "width": 40, "anchor": "w"}, "Title": {"text": "Title", "width": 300, "anchor": "w"}, "Artist": {"text": "Artist", "width": 200, "anchor": "w"}, "Duration": {"text": "Duration", "width": 80, "anchor": "center"}, "Year": {"text": "Year", "width": 60, "anchor": "center"}, "Additional": {"text": "Additional", "width": 120, "anchor": "w"}, "Explicit": {"text": "E", "width": 30, "anchor": "center"}, "ID": {"text": "ID", "width": 0, "anchor": "w"}}
        for col in columns: cfg = col_configs[col]; tree.heading(col, text=cfg["text"], anchor=cfg["anchor"], command=lambda c=col: sort_results(c)); tree.column(col, width=cfg["width"], anchor=cfg["anchor"], stretch=False)
        tree.column("Title", stretch=True); tree.column("Artist", stretch=True)
        scrollbar = customtkinter.CTkScrollbar(treeview_container, command=tree.yview); tree.configure(yscrollcommand=scrollbar.set)
        tree.bind("<<TreeviewSelect>>", on_tree_select); tree.bind("<Configure>", lambda event: _check_and_toggle_scrollbar(tree, scrollbar) if 'tree' in globals() and tree and tree.winfo_exists() and 'scrollbar' in globals() and scrollbar and scrollbar.winfo_exists() else None)
        # Selection Frame
        selection_label_var = tkinter.StringVar(value="Selection: None") # Unused?
        selection_frame = customtkinter.CTkFrame(search_main_frame, fg_color="transparent"); selection_frame.pack(fill="x", pady=(12, 10), side="bottom")
        search_progress_bar = customtkinter.CTkProgressBar(selection_frame); search_progress_bar.pack(side="left", fill="x", expand=True, padx=(6, 5)); search_progress_bar.set(0)
        selection_controls_frame = customtkinter.CTkFrame(selection_frame, fg_color="transparent"); selection_controls_frame.pack(side="right")
        customtkinter.CTkLabel(selection_controls_frame, text="Selection").pack(side="left", padx=(8, 6)); selection_var = tkinter.StringVar(); selection_entry = customtkinter.CTkEntry(selection_controls_frame, textvariable=selection_var, width=35, height=30); selection_entry.pack(side="left", padx=4); selection_var.trace_add("write", on_selection_change)
        selection_entry.bind("<FocusIn>", lambda e, w=selection_entry: handle_focus_in(w))
        selection_entry.bind("<FocusOut>", lambda e, w=selection_entry: handle_focus_out(w))
        search_download_button = customtkinter.CTkButton(selection_controls_frame, text="Download", command=download_selected, width=100, height=30, state="disabled", fg_color="#343638", hover_color="#1F6AA5"); search_download_button.pack(side="left", padx=(5, 6))

        # --- Settings Tab ---
        settings_tab = tabview.add("Settings"); settings_tabview = customtkinter.CTkTabview(master=settings_tab); settings_tabview.pack(expand=True, fill="both", padx=5, pady=5)
        # Global Settings Sub-Tab
        global_settings_tab = settings_tabview.add("Global"); global_settings_frame = customtkinter.CTkScrollableFrame(global_settings_tab); global_settings_frame.pack(expand=True, fill="both", padx=5, pady=(0, 5)); global_settings_frame.grid_columnconfigure(1, weight=1)
        row = 0

        # --- Tooltip Texts ---
        tooltip_texts = {
            "general.output_path": "Set the absolute or relative output path with / as the delimiter",
            "general.quality": """\"hifi\": FLAC higher than 44.1/16 if available
\"lossless\": FLAC with 44.1/16 if available
\"high\": lossy codecs such as MP3, AAC, ... in a higher bitrate
\"low\": lossy codecs such as MP3, AAC, ... in a lower bitrate
NOTE: The download_quality really depends on the used modules, so check out the modules README.md""",
            "general.search_limit": "How many search results are shown",
            "formatting.track_filename_format": """How tracks are formatted in albums and playlists.
track_filename_format variables are:
 {name}, {album}, {album_artist}, {album_id}, {track_number},
 {total_tracks}, {disc_number}, {total_discs}, {release_date}, {release_year}, {artist_id},
 {isrc}, {upc}, {explicit}, {copyright}, {codec}, {sample_rate}, {bit_depth}.""",
            "formatting.album_format": """Base directories for their respective formats - tracks and cover art are stored here.
May have slashes in it, for instance {artist}/{album}.
album_format variables are:
 {name}, {id}, {artist}, {artist_id}, {release_year}, {upc}, {explicit}, {quality}, {artist_initials}.""",
            "formatting.playlist_format": """Base directories for their respective formats - tracks and cover art are stored here.
May have slashes in it, for instance {artist}/{album}.
playlist_format variables are:
 {name}, {creator}, {tracks}, {release_year}, {explicit}, {creator_id}""",
            "formatting.single_full_path_format": """How singles are handled, which is separate to how the above work.
Instead, this has both the folder's name and the track's name.""",
            "formatting.enable_zfill": "Enables zero padding for track_number, total_tracks, disc_number, total_discs if the corresponding number has more than 2 digits",
            "formatting.force_album_format": "Forces the album_format for tracks instead of the single_full_path_format and also uses album_format in the playlist_format folder",
            "codecs.proprietary_codecs": """Enable it to allow MQA, E-AC-3 JOC or AC-4 IMS
Note: spatial_codecs has priority over proprietary_codecs when deciding if a codec is enabled""",
            "codecs.spatial_codecs": """Enable it to allow MPEG-H 3D, E-AC-3 JOC or AC-4 IMS
Note: spatial_codecs has priority over proprietary_codecs when deciding if a codec is enabled""",
            "module_defaults.lyrics": "Change default to the module name under /modules in order to retrieve lyrics from the selected module",
            "module_defaults.covers": "Change default to the module name under /modules in order to retrieve covers from the selected module",
            "module_defaults.credits": "Change default to the module name under /modules in order to retrieve credits from the selected module",
            "lyrics.embed_lyrics": "Embeds the (unsynced) lyrics inside every track",
            "lyrics.embed_synced_lyrics": "Embeds the synced lyrics inside every track (needs embed_lyrics to be enabled) (required for Roon)",
            "lyrics.save_synced_lyrics": "Saves the synced lyrics inside a .lrc file in the same directory as the track with the same track_format variables",
            "covers.embed_cover": "Enable it to embed the album cover inside every track",
            "covers.main_compression": "Compression of the main cover",
            "covers.main_resolution": "Resolution (in pixels) of the cover of the module used",
            "covers.save_external": "Enable it to save the cover from a third party cover module",
            "covers.external_format": "Format of the third party cover, supported values: jpg, png, webp",
            "covers.external_compression": "Compression of the third party cover, supported values: low, high",
            "covers.external_resolution": "Resolution (in pixels) of the third party cover",
            "covers.save_animated_cover": "Enable saving the animated cover when supported from the module (often in MPEG-4 format)"
        }

        # Use DEFAULT_SETTINGS which was defined within this block
        for section_key, section_value in DEFAULT_SETTINGS["globals"].items():
            if isinstance(section_value, dict):
                # Remove explicit font from label
                customtkinter.CTkLabel(global_settings_frame, text=section_key.replace("_", " ").upper(), text_color="#898c8d", font=("Segoe UI", 11)).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5)); row += 1
                for field, default_value in section_value.items():
                    # Use current_settings which was loaded within this block
                    current_value = current_settings["globals"].get(section_key, {}).get(field, default_value); full_key = f"{section_key}.{field}"

                    # <<< ADDED CHECK TO SKIP SPECIFIC ADVANCED SETTINGS >>>
                    if full_key in ["advanced.codec_conversions", "advanced.conversion_flags"]:
                        continue

                    label_widget = customtkinter.CTkLabel(global_settings_frame, text=field.replace("_", " ").title())
                    label_widget = customtkinter.CTkLabel(global_settings_frame, text=field.replace("_", " ").title())
                    label_widget.grid(row=row, column=0, sticky="w", padx=10, pady=2)

                    widget = None; browse_btn = None

                    if isinstance(default_value, bool):
                        var = tkinter.BooleanVar(value=bool(current_value)); settings_vars["globals"][full_key] = var # Store only var
                        widget = customtkinter.CTkCheckBox(global_settings_frame, text="", variable=var)
                        widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                    elif isinstance(default_value, dict):
                         widget = customtkinter.CTkLabel(global_settings_frame, text="(Complex Setting)")
                         widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                         settings_vars["globals"][full_key] = {} # Store empty dict placeholder
                    else:
                         var = tkinter.StringVar(value=str(current_value)); settings_vars["globals"][full_key] = var # Store only var
                         if section_key == "general" and field == "output_path":
                            widget = customtkinter.CTkEntry(global_settings_frame, textvariable=var)
                            widget.grid(row=row, column=1, sticky="ew", padx=(5, 0), pady=2)
                            widget.bind("<Button-3>", show_context_menu)
                            widget.bind("<FocusIn>", lambda e, w=widget: handle_focus_in(w))
                            widget.bind("<FocusOut>", lambda e, w=widget: handle_focus_out(w))
                            browse_btn = customtkinter.CTkButton(global_settings_frame, text="⋯", width=30, height=widget._current_height,
                                                               command=lambda v=var: browse_output_path(v),
                                                               fg_color=widget._fg_color, hover_color="#1F6AA5",
                                                               border_width=2, border_color=widget._border_color)
                            browse_btn.grid(row=row, column=2, sticky="w", padx=(1, 5))
                         elif section_key == "general" and field == "quality":
                            quality_options = ["hifi", "lossless", "high", "low"]
                            current_val_str = var.get().lower()
                            if current_val_str not in quality_options: var.set(quality_options[0])
                            widget = customtkinter.CTkComboBox(global_settings_frame, variable=var, values=quality_options, state="readonly", dropdown_fg_color="#2B2B2B")
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                         elif section_key == "covers" and field == "main_compression":
                            compression_options = ["high", "low"]
                            if var.get() not in compression_options: var.set(compression_options[0])
                            widget = customtkinter.CTkComboBox(global_settings_frame, variable=var, values=compression_options, state="readonly", dropdown_fg_color="#2B2B2B")
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                         elif section_key == "covers" and field == "external_format":
                            format_options = ["png", "jpg", "webp"]
                            if var.get() not in format_options: var.set(format_options[0])
                            widget = customtkinter.CTkComboBox(global_settings_frame, variable=var, values=format_options, state="readonly", dropdown_fg_color="#2B2B2B")
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
                         elif section_key == "covers" and field == "external_compression":
                            compression_options = ["low", "high"]
                            if var.get() not in compression_options: var.set(compression_options[0])
                            widget = customtkinter.CTkComboBox(global_settings_frame, variable=var, values=compression_options, state="readonly", dropdown_fg_color="#2B2B2B")
                            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2, columnspan=2)
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

        # Credential Sub-Tabs
        # Dynamically determine installed/loadable modules
        installed_platform_names = []
        if orpheus_instance and hasattr(orpheus_instance, 'module_settings') and hasattr(orpheus_instance, 'load_module'):
            known_module_names = list(orpheus_instance.module_settings.keys())
            platform_map_from_orpheus = {
                "bugs": "BugsMusic", "nugs": "Nugs", "soundcloud": "SoundCloud",
                "tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer",
                "idagio": "Idagio", "kkbox": "KKBOX", "napster": "Napster",
                "beatport": "Beatport", "musixmatch": "Musixmatch"
                # Add other mappings if needed
            }
            print(f"[Settings Tabs] Checking known modules: {known_module_names}")
            for module_name in known_module_names:
                try:
                    # Use importlib to check if module spec exists without full initialization/login
                    module_spec = importlib.util.find_spec(f"modules.{module_name}")
                    if module_spec:
                        # Module exists, now check mapping and default settings
                        gui_platform_name = platform_map_from_orpheus.get(module_name)
                        if gui_platform_name and gui_platform_name in DEFAULT_SETTINGS["credentials"]:
                            installed_platform_names.append(gui_platform_name)
                            print(f"  -> Found module files: {module_name} ({gui_platform_name})")
                        # else: # Optional: Log if mapping or default settings are missing
                        #    print(f"  -> Module {module_name} found but no GUI mapping/default found.")
                    # else: # Optional: Log if spec not found
                    #     print(f"  -> Module spec not found for: {module_name}")

                except Exception as e_check:
                    print(f"  -> Error checking module spec {module_name}: {e_check}") # Log other errors
            sorted_installed_platforms = sorted(installed_platform_names)
            print(f"[Settings Tabs] Will display tabs for: {sorted_installed_platforms}")
        else:
            print("[Settings Tabs] Orpheus instance not available or modules cannot be listed. Skipping credential tabs.")
            sorted_installed_platforms = [] # Ensure it's an empty list if Orpheus isn't ready

        # Use the dynamic list of installed platforms
        for platform_name in sorted_installed_platforms:
            # The rest of the loop remains largely the same, ensure defaults are still used for structure
            # Note: We already confirmed platform_name is in DEFAULT_SETTINGS["credentials"] above
            fields = current_settings.get("credentials", {}).get(platform_name, {}) # Get loaded or empty dict
            default_platform_fields = DEFAULT_SETTINGS["credentials"].get(platform_name, {}) # Get defaults

            platform_tab = settings_tabview.add(platform_name.replace("_", " ")); settings_vars["credentials"][platform_name] = {}; platform_tab.grid_columnconfigure(1, weight=1); row = 0
            for field_key, default_value in default_platform_fields.items():
                current_value = fields.get(field_key, default_value); var = tkinter.StringVar(value=str(current_value)); settings_vars["credentials"][platform_name][field_key] = var # Store only var
                current_pady = (13 if row == 0 else 2, 2); customtkinter.CTkLabel(platform_tab, text=f"{field_key.replace('_', ' ').title()}:").grid(row=row, column=0, sticky="w", padx=10, pady=current_pady)
                entry = customtkinter.CTkEntry(platform_tab, textvariable=var); entry.grid(row=row, column=1, sticky="ew", padx=10, pady=current_pady); entry.bind("<Button-3>", show_context_menu); entry.bind("<Button-2>", show_context_menu); entry.bind("<Control-Button-1>", show_context_menu)
                entry.bind("<FocusIn>", lambda e, w=entry: handle_focus_in(w))
                entry.bind("<FocusOut>", lambda e, w=entry: handle_focus_out(w))
                row += 1
        # Save Controls Frame
        save_controls_frame = customtkinter.CTkFrame(settings_tab, fg_color="transparent"); save_controls_frame.pack(side="bottom", anchor="se", padx=10, pady=(0, 10))
        save_status_var = tkinter.StringVar(); save_status_label = customtkinter.CTkLabel(save_controls_frame, textvariable=save_status_var, text_color=("green", "lightgreen")); save_status_label.pack(side="left", padx=(0, 10))
        save_button = customtkinter.CTkButton(save_controls_frame, text="Save", width=100, height=30, command=handle_save_settings, fg_color="#343638", hover_color="#1F6AA5"); save_button.pack(side="left", padx=5, pady=(0, 0))

        # --- About Tab ---
        about_tab = tabview.add("About"); about_container = customtkinter.CTkFrame(about_tab, fg_color="transparent"); about_container.pack(fill="both", expand=True, padx=16, pady=(0, 0)); canvas = customtkinter.CTkFrame(about_container, fg_color="transparent"); canvas.pack(fill="both", expand=True); about_frame = customtkinter.CTkFrame(canvas, fg_color="transparent"); about_frame.pack(fill="x", expand=False, pady=10)
        # Icon and Title
        icon_title_frame = customtkinter.CTkFrame(about_frame, fg_color="transparent")
        icon_title_frame.pack(pady=(0, 5)) # Reduced bottom padding from 15 to 5
        try:
            current_platform = platform.system() # <-- Added
            print(f"[DEBUG AboutIcon] Platform detected: {current_platform}") # <-- Added

            # <<< Platform-specific icon filename and size for About tab >>>
            if current_platform == "Linux": # <-- Check against variable
                icon_filename = "icon.png" # Use PNG on Linux
                icon_display_size = (48, 48) # Default size
                print(f"[DEBUG AboutIcon] Set Linux display size to {icon_display_size}")
            elif current_platform == "Darwin": # <-- Check against variable
                icon_filename = "icon.icns"
                icon_display_size = (72, 72) # 1.5x size for macOS
                print(f"[DEBUG AboutIcon] Set macOS display size to {icon_display_size}")
            else: # Default to Windows/Other
                icon_filename = "icon.ico" # Default to ICO for Windows/Other
                icon_display_size = (48, 48) # Default size
                print(f"[DEBUG AboutIcon] Set default display size to {icon_display_size}")

            print(f"[DEBUG AboutIcon] Determined icon filename: {icon_filename}") # <-- Added

            # Use resource_path to find the icon, works for dev and bundle
            icon_path = resource_path(icon_filename)
            print(f"[DEBUG AboutIcon] Generated icon path: {icon_path}") # <-- Added
            print(f"[DEBUG AboutIcon] Looking for AboutTab icon at: {icon_path}")

            icon_exists = os.path.exists(icon_path) # <-- Added
            print(f"[DEBUG AboutIcon] Does icon exist at path? {icon_exists}") # <-- Added

            # <<< icon_display_size is now defined based on platform BEFORE usage >>>

            if icon_path and icon_exists: # <-- Check variable
                # ... (existing size calculation logic) ...

                try:
                    print("[DEBUG AboutIcon] Attempting to open image...") # <-- Added
                    # Resize and create CTkImage using the determined size
                    img = Image.open(icon_path).resize(icon_display_size, Image.LANCZOS)
                    print("[DEBUG AboutIcon] Image opened successfully.") # <-- Added
                    icon_image = customtkinter.CTkImage(light_image=img, dark_image=img, size=icon_display_size)
                    print("[DEBUG AboutIcon] CTkImage created successfully.") # <-- Added
                    icon_label = customtkinter.CTkLabel(icon_title_frame, text="", image=icon_image)
                    # <<< Conditional padding for the icon label >>>
                    icon_pady = 0 if current_platform == "Darwin" else 5 # <-- Check against variable
                    icon_label.pack(pady=icon_pady)
                except Exception as img_e:
                    print(f"[DEBUG AboutIcon] Could not load/process icon image: {type(img_e).__name__}: {img_e}") # <-- Modified
            else:
                print(f"[DEBUG AboutIcon] Icon file not found or path invalid: {icon_path}") # <-- Modified
        except Exception as path_e:
            print(f"[DEBUG AboutIcon] Error during icon path processing/loading: {type(path_e).__name__}: {path_e}") # <-- Modified
        # ... (rest of About tab) ...

        # Make title bold and remove bottom padding
        title_label = customtkinter.CTkLabel(icon_title_frame, text="OrpheusDL GUI", font=customtkinter.CTkFont(weight="bold"))
        title_label.pack(pady=(0, 0))

        # Description, GitHub, Version, Credits
        description_text = ("Makes downloading music with OrpheusDL easy on Win, macOS & Linux.\nSearch multiple platforms & download high-quality audio with metadata."); description_label = customtkinter.CTkLabel(about_frame, text=description_text, justify="center", wraplength=450); description_label.pack(pady=(0, 10))
        github_url = "https://github.com/bascurtiz/OrpheusDL-GUI"
        command = lambda u=github_url: os.startfile(u) if platform.system() == "Windows" else subprocess.Popen(["open", u]) if platform.system() == "Darwin" else subprocess.Popen(["xdg-open", u])
        github_button = customtkinter.CTkButton(about_frame, text="GitHub", command=command, width=110, fg_color="#343638", hover_color="#1F6AA5")
        github_button.pack(pady=10)

        # Define styles for section headers
        section_header_font = ("Segoe UI", 11)
        section_header_color = "#898c8d"

        # Version (split into heading and number)
        version_heading_label = customtkinter.CTkLabel(about_frame, text="GUI VERSION", font=section_header_font, text_color=section_header_color)
        version_heading_label.pack(pady=(10, 0)) # Small padding below heading
        # Use the global __version__ variable defined at the top of the file
        version_number_label = customtkinter.CTkLabel(about_frame, text=__version__) # Use __version__ here
        version_number_label.pack(pady=(0, 10)) # Original padding below number

        # Credits Section
        credits_heading_label = customtkinter.CTkLabel(about_frame, text="CREDITS", font=section_header_font, text_color=section_header_color)
        credits_heading_label.pack(pady=(0, 2))
        credits_names_text = ("""OrfiDev (Project Lead)\nDniel97 (Current Lead Developer)\nCommunity developers (Modules)\nBas Curtiz (GUI)"""); credits_names_label = customtkinter.CTkLabel(about_frame, text=credits_names_text.strip(), justify="center"); credits_names_label.pack(pady=(0, 0))

        # Modules Section
        modules_title = customtkinter.CTkLabel(about_frame, text="MODULES", font=section_header_font, text_color=section_header_color)
        modules_title.pack(pady=(20, 5))
        modules_frame = customtkinter.CTkFrame(about_frame, fg_color="transparent"); modules_frame.pack(fill="x", padx=20, pady=(0, 10))
        module_buttons_data = [ ("Apple Music", "https://github.com/yarrm80s/orpheusdl-applemusic-basic"), ("Beatport", "https://github.com/Dniel97/orpheusdl-beatport"), ("Bugs", "https://github.com/Dniel97/orpheusdl-bugsmusic"), ("Deezer (acc)", "https://github.com/uhwot/orpheusdl-deezer"), ("Deezer (arl)", "https://github.com/thekvt/orpheusdl-deezer"), ("Genius", "https://github.com/Dniel97/orpheusdl-genius"), ("Idagio", "https://github.com/Dniel97/orpheusdl-idagio"), ("JioSaavn", "https://github.com/bunnykek/orpheusdl-jiosaavn"), ("KKBOX", "https://github.com/uhwot/orpheusdl-kkbox"), ("Musixmatch", "https://github.com/yarrm80s/orpheusdl-musixmatch"), ("Napster", "https://github.com/yarrm80s/orpheusdl-napster"), ("Nugs.net", "https://github.com/Dniel97/orpheusdl-nugs"), ("Qobuz (acc)", "https://github.com/yarrm80s/orpheusdl-qobuz"), ("Qobuz (id/tok)", "https://github.com/thekvt/orpheusdl-qobuz"), ("SoundCloud", "https://github.com/yarrm80s/orpheusdl-soundcloud"), ("Tidal", "https://github.com/Dniel97/orpheusdl-tidal") ]
        cols = 8
        for i, (text, url) in enumerate(module_buttons_data):
            row = i // cols; col = i % cols
            command = lambda u=url: os.startfile(u) if platform.system() == "Windows" else subprocess.Popen(["open", u]) if platform.system() == "Darwin" else subprocess.Popen(["xdg-open", u])
            btn = customtkinter.CTkButton(modules_frame, text=text, command=command, width=110, fg_color="#343638", hover_color="#1F6AA5")
            btn.grid(row=row, column=col, padx=5, pady=5)
        for c in range(cols): modules_frame.grid_columnconfigure(c, weight=1)

        # --- Disable buttons if Orpheus failed to initialize ---
        # Check orpheus_instance which was initialized in this block
        if not orpheus_instance:
            print("Disabling Download/Search buttons due to Orpheus initialization failure.")
            # Check if buttons exist before configuring
            if 'download_button' in globals() and download_button and download_button.winfo_exists(): download_button.configure(state="disabled")
            if 'search_button' in globals() and search_button and search_button.winfo_exists(): search_button.configure(state="disabled")
            if 'search_download_button' in globals() and search_download_button and search_download_button.winfo_exists(): search_download_button.configure(state="disabled")

        # =====================================================================
        # --- START MAIN LOOP (Main Process Only) ---
        # =====================================================================
        update_log_area() # Start polling the output queue

        # --- Start Update Check ---
        # Use __version__ defined at top and app instance defined in this block
        try:
            run_check_in_thread(__version__, app)
        except Exception as update_err:
            print(f"[Error] Failed to start update check: {update_err}")

        # --- Explicitly update UI vars after main loop starts ---
        def _initial_ui_update():
            print("[DEBUG] Running _initial_ui_update...")
            try:
                # Re-set main path variable
                if 'path_var_main' in globals() and path_var_main:
                    main_path_val = current_settings.get("globals", {}).get("general", {}).get("output_path")
                    if main_path_val is not None:
                        print(f"  -> Setting path_var_main to: {main_path_val}")
                        path_var_main.set(main_path_val)
                    else:
                        print("  -> main_path_val is None")
                else:
                    print("  -> path_var_main not found")

                # Refresh settings tab
                print("  -> Calling _update_settings_tab_widgets()")
                _update_settings_tab_widgets()
                print("[DEBUG] _initial_ui_update finished.")

            except Exception as e_init_update:
                 print(f"[Error] in _initial_ui_update: {e_init_update}")

        app.after(10, _initial_ui_update) # Schedule the update shortly after start

        app.mainloop() # Start the Tkinter event loop

    else:
        # --- Code running in a SPAWNED CHILD process ---
        # Exit immediately to prevent re-running GUI/initialization
        print(f"[Child Process {os.getpid()}] Detected, exiting.") # Optional debug
        sys.exit() # Crucial step

# --- End Of File ---