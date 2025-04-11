import subprocess
from tkinter import messagebox
from base.audio_manager_base import AudioManagerBase

class LinuxAudioManager(AudioManagerBase):
    def get_audio_devices(self):
        devices = []
        cmd = ["pactl", "list", "sources"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            lines = result.stdout.splitlines()

            current_device = None
            for line in lines:
                if "Name:" in line:
                    parts = line.split()
                    if len(parts) > 1:
                        current_device = parts[1]
                elif "Description:" in line and current_device:
                    description = line.split(":", 1)[1].strip()
                    normalized_name = self._normalize_audio_device_name(current_device)
                    devices.append(f"{description} ({normalized_name})")
                    current_device = None

            if not devices:
                print("No active audio devices were found. Please check your audio settings.")
                messagebox.showerror("Error", "No active audio devices were found. Please check your audio settings.")

        except Exception as e:
            print(f"Error getting audio devices: {e}")
            messagebox.showerror("Error", f"Error getting audio devices: {e}")
            
        return devices