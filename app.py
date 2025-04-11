import tkinter as tk
import platform
import sys
import os
import logging

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from common.logging_config import setup_logging

logger = setup_logging()

def main():
    logger.info(f"Starting Mini Screen Recorder on {platform.system()} platform.")
    
    root = tk.Tk()
    
    if platform.system() == 'Windows':
        from platforms.windows_recorder import WindowsRecorder
        app = WindowsRecorder(root)
    elif platform.system() == 'Linux':
        from platforms.linux_recorder import LinuxRecorder
        app = LinuxRecorder(root)
    else:
        error_msg = f"Platform not supported: {platform.system()}"
        logger.error(error_msg)
        raise NotImplementedError(error_msg)
    
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
        print(f"Error: {e}")
        if tk._default_root:
            from tkinter import messagebox
            messagebox.showerror("Error", f"An unexpected error has occurred: {e}")