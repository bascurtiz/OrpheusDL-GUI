# update_checker.py
import requests
import threading
# import tkinter.messagebox <<< Keep commented
import webbrowser
from packaging.version import parse as parse_version # Requires 'packaging' package

# <<< Remove this import >>>
# from gui_utils import show_centered_messagebox

# <<< Add necessary imports for the function >>>
import customtkinter
import tkinter

# --- Configuration ---
# Replace with your actual GitHub username and repository name
GITHUB_REPO_OWNER = "bascurtiz"
GITHUB_REPO_NAME = "OrpheusDL-GUI"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"

# --- Update Check Logic ---

def get_latest_release_info():
    """Fetches the latest release information from the GitHub API."""
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=10) # 10 second timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Update Check] Network or API error: {e}")
        return None
    except Exception as e: # Catch other potential errors (e.g., JSON decoding)
        print(f"[Update Check] Unexpected error fetching release info: {e}")
        return None

def compare_versions(current_version_str, latest_version_str):
    """
    Compares the current version with the latest version tag.
    Returns True if the latest version is newer, False otherwise.
    Handles potential 'v' prefix in tags (e.g., v1.0.0).
    """
    try:
        # Normalize tags by removing potential leading 'v'
        current_version_str = current_version_str.lstrip('v')
        latest_version_str = latest_version_str.lstrip('v')

        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)

        return latest_version > current_version
    except Exception as e:
        print(f"[Update Check] Error comparing versions ('{current_version_str}' vs '{latest_version_str}'): {e}")
        return False # Treat comparison errors as 'no update found'

def show_centered_messagebox(title, message, dialog_type="info", parent=None):
    """Creates and displays a centered CTkToplevel message box."""
    # This function relies on the 'parent' argument being passed correctly.
    if parent is None:
         print("ERROR: Cannot show messagebox, parent window not provided.")
         return # Cannot proceed without a parent window

    try:
        # Check if parent is a valid Tkinter window
        if not isinstance(parent, (tkinter.Tk, tkinter.Toplevel, customtkinter.CTk, customtkinter.CTkToplevel)) or not parent.winfo_exists():
            print("ERROR: Invalid or destroyed parent window provided to show_centered_messagebox.")
            return

        dialog = customtkinter.CTkToplevel(parent)
        dialog.title(title)
        dialog.geometry("450x150")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(parent)

        # Centering logic
        dialog.update_idletasks()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        center_x = parent_x + (parent_width // 2) - (dialog_width // 2)
        center_y = parent_y + (parent_height // 2) - (dialog_height // 2)
        dialog.geometry(f"+{center_x}+{center_y}")

        # Content
        message_label = customtkinter.CTkLabel(dialog, text=message, wraplength=400, justify="left")
        message_label.pack(pady=(20, 10), padx=20, expand=True, fill="both")

        ok_button = customtkinter.CTkButton(dialog, text="OK", command=dialog.destroy, width=100)
        ok_button.pack(pady=(0, 20))
        ok_button.focus_set()
        dialog.bind("<Return>", lambda event: ok_button.invoke())

        # Make modal
        dialog.grab_set()
        dialog.wait_window()

    except (tkinter.TclError, RuntimeError) as e:
        print(f"Error displaying centered messagebox (window destroyed?): {e}")
    except Exception as e:
        print(f"Unexpected error in show_centered_messagebox: {e}")

def show_update_dialog(new_version_tag, parent_window):
    """Displays a styled dialog box informing the user about the update."""
    title = "Update Available"
    message = (
        f"A new version ({new_version_tag}) is available!\n\n"
        f"Visit the Releases page on GitHub to download (About tab)."
    )
    # Use the custom message box
    # Ensure parent_window is passed correctly
    show_centered_messagebox(title, message, parent=parent_window)
    # No return value needed, and no automatic browser opening for now
    # if tkinter.messagebox.askyesno(title, message, icon=tkinter.messagebox.INFO):
    #     try:
    #         webbrowser.open(RELEASES_PAGE_URL, new=2) # Open in new tab/window
    #     except Exception as e:
    #         print(f"[Update Check] Failed to open web browser: {e}")
    #         # Show error using the custom dialog as well
    #         error_message = f"Could not open the releases page automatically.\n\nPlease visit:\n{RELEASES_PAGE_URL}"
    #         show_centered_messagebox("Error", error_message, parent=parent_window)

def check_for_updates(current_version):
    """
    Performs the update check: fetches latest release, compares versions,
    and shows dialog if an update is found.
    Designed to be run in a separate thread.
    """
    print("[Update Check] Checking for updates...")
    release_info = get_latest_release_info()

    if not release_info or 'tag_name' not in release_info:
        print("[Update Check] Could not retrieve valid release information.")
        return # Silently fail if no info or tag_name

    latest_tag = release_info['tag_name']
    print(f"[Update Check] Latest release tag: {latest_tag}, Current version: {current_version}")

    if compare_versions(current_version, latest_tag):
        print(f"[Update Check] New version found: {latest_tag}")
        # Schedule the dialog box to run in the main Tkinter thread
        # Assuming 'app' is the global root CustomTkinter window instance in gui.py
        # This needs coordination with how gui.py is structured.
        # For now, we'll call it directly, but this WILL cause issues if
        # check_for_updates is called from a non-main thread without scheduling.
        # We will address this when integrating into gui.py.
        # <<< This direct call is problematic, the threaded version handles scheduling >>>
        # show_update_dialog(latest_tag)
        pass # The direct call was incorrect, rely on the threaded approach
    else:
        print("[Update Check] Application is up-to-date.")

# --- Helper for Threaded Check ---

def run_check_in_thread(current_version, root_window):
    """
    Starts the update check in a separate thread.
    Schedules the dialog display using root_window.after if an update is found.
    """
    def threaded_task():
        print("[Update Check] Starting update check thread...")
        release_info = get_latest_release_info()

        if not release_info or 'tag_name' not in release_info:
            print("[Update Check] Could not retrieve valid release information from thread.")
            return

        latest_tag = release_info['tag_name']
        print(f"[Update Check Thread] Latest: {latest_tag}, Current: {current_version}")

        if compare_versions(current_version, latest_tag):
            print(f"[Update Check Thread] New version found: {latest_tag}. Scheduling dialog.")
            # Safely schedule the dialog call in the main GUI thread
            # Pass the root_window as the parent argument
            root_window.after(0, lambda: show_update_dialog(latest_tag, parent_window=root_window))
        else:
            print("[Update Check Thread] Application is up-to-date.")

    # Create and start the daemon thread
    update_thread = threading.Thread(target=threaded_task, daemon=True)
    update_thread.start() 