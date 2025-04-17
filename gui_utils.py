import customtkinter
import tkinter # For TclError exception handling, though implicitly used by CTk

# --- Centered Message Box ---
def show_centered_messagebox(title, message, dialog_type="info", parent=None):
    """Creates and displays a centered CTkToplevel message box."""
    # This function no longer needs access to the global 'app'
    # It relies on the 'parent' argument being passed correctly.
    if parent is None:
         print("ERROR: Cannot show messagebox, parent window not provided.")
         # Optionally, could try to find the root window automatically,
         # but it's safer to rely on the caller providing it.
         # try:
         #     parent = customtkinter.CTk() # Get root if it exists
         # except RuntimeError: # No root window yet
         #     return
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
        # Catch errors that might occur if the parent window is destroyed
        # during dialog creation/display
        print(f"Error displaying centered messagebox (window destroyed?): {e}")
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error in show_centered_messagebox: {e}") 