import os
import sys
import subprocess
import locale
from tkinter import messagebox
from base.audio_manager_base import AudioManagerBase

class WindowsAudioManager(AudioManagerBase):
    def get_audio_devices(self):
        ffmpeg_path = self._get_ffmpeg_path()
        if not ffmpeg_path:
            return []
        
        cmd = [ffmpeg_path, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            lines = result.stderr.splitlines()
            devices = []
            
            for line in lines:
                if "audio" in line and len(line.split("\"")) > 1:
                    device_name = line.split("\"")[1]
                    normalized_name = self._normalize_audio_device_name(device_name)
                    devices.append(normalized_name)

            if not devices:
                print("No active audio devices were found. Please check your audio settings.")
                messagebox.showerror("Error", "No active audio devices were found. Please check your audio settings.")

            return devices

        except subprocess.CalledProcessError as e:
            print(f"Error running FFmpeg (Audio): {e}")
            return []
        except FileNotFoundError:
            print(f"FFmpeg (Audio) not found at {ffmpeg_path}")
            return []
            
    def _normalize_audio_device_name(self, audio_device):
        system_locale = locale.getdefaultlocale()[0]
        return super()._normalize_audio_device_name(audio_device)
            
    def _get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        ffmpeg_path = os.path.join(base_path, 'ffmpeg_files', 'ffmpeg.exe')
        return ffmpeg_path if os.path.exists(ffmpeg_path) else None