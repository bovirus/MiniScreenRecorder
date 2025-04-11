import datetime
import platform
import sys
import os
import subprocess
import locale
import threading
from tkinter import messagebox
from base.screen_recorder_base import ScreenRecorderBase

class WindowsRecorder(ScreenRecorderBase):
    def __init__(self, root):
        super().__init__(root)
        self.initialize_ffmpeg()
    
    def set_icon(self):
        self.root.iconbitmap('video.ico')
        
    def get_audio_devices(self):
        ffmpeg_path = self.get_ffmpeg_path()
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
                self.logger.error("No active audio devices were found. Please check your audio settings.")
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

        encodings_to_try = ['utf-8', 'latin-1', 'cp1252']

        for encoding in encodings_to_try:
            try:
                audio_device = audio_device.encode(encoding).decode('utf-8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            
        return audio_device
    
    def platform_initialize(self):
        self.initialize_ffmpeg()
        
    def get_ffmpeg_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        ffmpeg_path = os.path.join(base_path, 'ffmpeg_files', 'ffmpeg.exe')
        
        return ffmpeg_path if os.path.exists(ffmpeg_path) else None
        
    def initialize_ffmpeg(self):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            self.logger.error("FFmpeg not found.")
            if hasattr(self, 'status_label') and self.status_label:
                self.update_status_label_error_recording(self.t("error_recording"))
            messagebox.showerror("Error", f"FFmpeg not found.")
            sys.exit(1)
        self.logger.info("FFmpeg was found.")
        
    def start_recording(self, continue_timer=False):
        video_name = f"Video.{datetime.datetime.now().strftime('%m-%d-%Y.%H.%M.%S')}.{self.format_combo.get()}"
        self.video_path = os.path.join(self.output_folder, video_name)

        fps = int(self.fps_combo.get())
        bitrate = self.bitrate_combo.get()
        codec = self.codec_combo.get()
        audio_device = self.audio_combo.get()
        volume = self.volume_scale.get()

        audio_device = self._normalize_audio_device_name(audio_device)

        monitor_index = self.monitor_combo.current()
        monitor = self.monitors[monitor_index]

        if self.record_area:
            x1, y1, x2, y2 = self.record_area
            width = x2 - x1
            height = y2 - y1

            if width <= 0 or height <= 0:
                messagebox.showerror(self.t("error"), self.t("error_invalid_area"))
                self.update_status_label_error_recording(self.t("error_recording"))
                self.stop_recording()
                self.stop_timer()
                self.toggle_widgets(False)
                return

            width -= width % 2
            height -= height % 2
            if width <= 0 or height <= 0:
                messagebox.showerror(self.t("error"), self.t("error_adjusted_area"))
                self.update_status_label_error_recording(self.t("error_recording"))
                self.stop_recording()
                self.stop_timer()
                self.toggle_widgets(False)
                return
        else:
            x1 = y1 = 0
            width = monitor.width
            height = monitor.height

        ffmpeg_path = self.get_ffmpeg_path()
        ffmpeg_args = [
            ffmpeg_path,
            "-f", "gdigrab",
            "-framerate", str(fps),
            "-offset_x", str(x1 + monitor.x),
            "-offset_y", str(y1 + monitor.y),
            "-video_size", f"{width}x{height}",
            "-i", "desktop",
            "-f", "dshow",
            "-i", f"audio={audio_device}",
            "-filter:a", f"volume={volume/100}",
            "-threads", "0",
            "-pix_fmt", "yuv420p",
            "-loglevel", "info",
            "-hide_banner"
        ]

        if codec == "libx264":
            ffmpeg_args.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-b:v", bitrate,
            ])
        elif codec == "libx265":
            ffmpeg_args.extend([
                "-c:v", "libx265",
                "-preset", "medium",
                "-b:v", bitrate,
            ])
        else:
            ffmpeg_args.extend([
                "-c:v", codec,
                "-b:v", bitrate,
            ])

        ffmpeg_args.append(self.video_path)

        creationflags = subprocess.CREATE_NO_WINDOW
        try:
            self.recording_process = subprocess.Popen(
                ffmpeg_args, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, 
                universal_newlines=True,
                creationflags=creationflags
            )
        except FileNotFoundError as e:
            messagebox.showerror("Error", f"FFmpeg not found.")
            self.update_status_label_error_recording(self.t("error_recording"))
            self.logger.error(f"FFmpeg not found: {e}")
            self.stop_recording()
            self.stop_timer()
            self.toggle_widgets(False)
            return
        except Exception as e:
            messagebox.showerror("Error", f"An error has occurred.")
            self.update_status_label_error_recording(self.t("error_recording"))
            self.logger.error(f"Error starting recording: {e}")
            self.stop_recording()
            self.stop_timer()
            self.toggle_widgets(False)
            return

        self.toggle_widgets(recording=True)
        self.status_label.config(text=self.t("status_recording"))

        if not continue_timer:
            self.start_timer()

        threading.Thread(target=self.read_ffmpeg_output, daemon=True).start()
        
    def stop_recording(self):
        if self.recording_process:
            try:
                self.recording_process.stdin.write('q')
                self.recording_process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            try:
                self.recording_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.recording_process.terminate()
                try:
                    self.recording_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.recording_process.kill()

            for pipe in [self.recording_process.stdin, self.recording_process.stdout, self.recording_process.stderr]:
                try:
                    pipe.close()
                except:
                    pass

            if os.path.exists(self.video_path) and os.path.getsize(self.video_path) > 0:
                self.video_parts.append(self.video_path)

            self.recording_process = None

        self.concat_video_parts()
        
        self.toggle_widgets(recording=False)
        self.stop_timer()
        self.status_label.config(text=self.t("status_ready"))
        
        self.record_area = None
        self.running = False
        
    def read_ffmpeg_output(self):
        if self.recording_process:
            buffer = []
            try:
                for stdout_line in iter(self.recording_process.stderr.readline, ""):
                    line = stdout_line.strip()
                    
                    if "error" in line.lower() or "fatal" in line.lower():
                        self.logger.error(f"FFmpeg Error: {line}")
                    
                    elif "warning" in line.lower():
                        self.logger.warning(f"FFmpeg Warning: {line}")
                    
                    elif "frame=" in line or "fps=" in line or "size=" in line:
                        self.logger.debug(f"FFmpeg Progress: {line}")
                    
                    elif "configuration:" not in line and "libav" not in line:
                        buffer.append(line)
                        if len(buffer) >= 10:
                            self.logger.info(f"FFmpeg Output: {' | '.join(buffer)}")
                            buffer = []
                    
            except BrokenPipeError:
                self.logger.warning("FFMPEG PROCESS HAS BEEN CLOSED")
            except Exception as e:
                self.logger.error(f"ERROR READING FFMPEG OUTPUT: {e}")
            finally:
                if buffer:
                    self.logger.info(f"FFmpeg Output: {' | '.join(buffer)}")
                    
    def concat_video_parts(self):
        if len(self.video_parts) > 0:
            ffmpeg_path = self.get_ffmpeg_path()
            concat_file = os.path.join(self.output_folder, "concat_list.txt")
            output_file = os.path.join(self.output_folder, f"Video_{datetime.datetime.now().strftime('%m-%d-%Y.%H.%M.%S')}.{self.format_combo.get()}")

            with open(concat_file, 'w') as f:
                for video in self.video_parts:
                    f.write(f"file '{os.path.abspath(video)}'\n")

            concat_command = [
                ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy", 
                "-movflags", "+faststart",
                output_file
            ]

            try:
                print(f"Executing command: {' '.join(concat_command)}")
                result = subprocess.run(concat_command, check=True, capture_output=True, text=True)
                print(f"FFmpeg output: {result.stderr}")

                os.remove(concat_file)
                for video in self.video_parts:
                    if os.path.exists(video):
                        os.remove(video)

            except subprocess.CalledProcessError as e:
                error_message = e.stderr if e.stderr else str(e)
                messagebox.showerror(self.t("error"), self.t("error_concat_video").format(error=error_message))
                self.logger.error(f"ERROR MERGING VIDEO: {error_message}")
                self.update_status_label_error_recording(self.t("error_recording"))

            self.video_parts = []
            self.current_video_part = 0
            
    def open_output_folder(self):
        os.startfile(self.output_folder)