import datetime
import platform
import sys
import os
import subprocess
import threading
from tkinter import messagebox
import tkinter as tk
from base.screen_recorder_base import ScreenRecorderBase

class LinuxRecorder(ScreenRecorderBase):
    def __init__(self, root):
        super().__init__(root)
    
    def set_icon(self):
        self.icon = tk.PhotoImage(file='video.png')
        self.root.iconphoto(True, self.icon)
        
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
                self.logger.error("No active audio devices were found. Please check your audio settings.")
                messagebox.showerror("Error", "No active audio devices were found. Please check your audio settings.")

        except Exception as e:
            self.logger.error(f"Error getting audio devices: {e}")
            messagebox.showerror("Error", f"Error getting audio devices: {e}")
            
        return devices
            
    def _normalize_audio_device_name(self, audio_device):
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252']

        for encoding in encodings_to_try:
            try:
                audio_device = audio_device.encode(encoding).decode('utf-8')
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            
        return audio_device
        
    def get_ffmpeg_path(self):
        return "ffmpeg"
        
    def initialize_ffmpeg(self):
        try:
            result = subprocess.run(["ffmpeg", "-version"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            if result.returncode != 0:
                self.logger.error("FFmpeg not found or not working properly.")
                messagebox.showerror("Error", "FFmpeg not found or not working properly.")
                sys.exit(1)
            self.logger.info("FFmpeg was found.")
        except FileNotFoundError:
            self.logger.error("FFmpeg not found in system PATH.")
            messagebox.showerror("Error", "FFmpeg not found in system PATH.")
            sys.exit(1)
        
    def start_recording(self, continue_timer=False):
        video_name = f"Video.{datetime.datetime.now().strftime('%m-%d-%Y.%H.%M.%S')}.{self.format_combo.get()}"
        self.video_path = os.path.join(self.output_folder, video_name)

        fps = int(self.fps_combo.get())
        bitrate = self.bitrate_combo.get()
        codec = self.codec_combo.get()
        audio_device = self.audio_combo.get()
        volume = self.volume_scale.get()

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

        display = os.getenv('DISPLAY')
        ffmpeg_args = [
            "ffmpeg",
            "-f", "x11grab",
            "-framerate", str(fps),
            "-video_size", f"{width}x{height}",
            "-i", f"{display}+{x1+monitor.x},{y1+monitor.y}",
            "-f", "pulse",
            "-i", audio_device,
            "-filter:a", f"volume={volume/150}",
            "-threads", "0",
            "-pix_fmt", "yuv420p",
            "-loglevel", "info",
            "-hide_banner"
        ]

        if codec == "libx264":
            ffmpeg_args.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-x264-params", f"bitrate={bitrate.rstrip('k')}:vbv-maxrate={bitrate.rstrip('k')}:vbv-bufsize={int(int(bitrate.rstrip('k'))/2)}:nal-hrd=cbr",
            ])
        elif codec == "libx265":
            ffmpeg_args.extend([
                "-c:v", "libx265",
                "-preset", "ultrafast",
                "-x265-params", f"bitrate={int(bitrate.rstrip('k'))}:vbv-maxrate={int(bitrate.rstrip('k'))}:vbv-bufsize={int(int(bitrate.rstrip('k'))/2)}:rc-lookahead=20:cbqpoffs=0:crqpoffs=0:crf=23",
            ])
        else:
            ffmpeg_args.extend([
                "-c:v", codec,
                "-b:v", bitrate,
            ])

        ffmpeg_args.append(self.video_path)

        try:
            self.recording_process = subprocess.Popen(
                ffmpeg_args, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, 
                universal_newlines=True
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
            concat_file = os.path.join(self.output_folder, "concat_list.txt")     
            output_file = os.path.join(self.output_folder, f"Video_{datetime.datetime.now().strftime('%m-%d-%Y.%H.%M.%S')}.{self.format_combo.get()}")

            with open(concat_file, 'w') as f:
                for video in self.video_parts:
                    f.write(f"file '{os.path.basename(video)}'\n")
            
            concat_command = [
                "ffmpeg",
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
                    os.remove(video)
                
            except subprocess.CalledProcessError as e:
                error_message = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
                messagebox.showerror(self.t("error"), self.t("error_concat_video").format(error=error_message))
                self.logger.error(f"ERROR MERGING VIDEO: {error_message}")
                self.update_status_label_error_recording(self.t("error_recording"))

            self.video_parts = []
            self.current_video_part = 0
            
    def open_output_folder(self):
        subprocess.Popen(["xdg-open", self.output_folder])