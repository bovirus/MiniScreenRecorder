import abc
import logging
import os
import datetime
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import time
import mss
import numpy as np
import cv2
from PIL import Image, ImageTk

from common.area_selector import AreaSelector
from common.themes import set_dark_theme, set_light_theme, set_dark_blue_theme, set_light_green_theme, set_purple_theme, set_starry_night_theme
from common.translation_manager import TranslationManager
from common.logging_config import setup_logging
from configparser import ConfigParser
from screeninfo import get_monitors

class ScreenRecorderBase(abc.ABC):
    def __init__(self, root):
        self.root = root
        if not hasattr(self.__class__, '_logger_initialized'):
            self.logger = setup_logging()
            self.__class__._logger_initialized = True
        else:
            self.logger = logging.getLogger()
        
        self.logger.info("APPLICATION STARTED")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.title("Mini Screen Recorder")
        
        self.root.geometry("900x600")

        self.config = ConfigParser()
        self.config_file = 'config.ini'
        self.load_config()

        self.translation_manager = TranslationManager(self.config.get('Settings', 'language', fallback='en-US'))
        self.set_theme(self.config.get('Settings', 'theme', fallback='dark'))

        self.set_icon()
        
        self.monitors = self.get_monitors()
        if len(self.monitors) == 0:
            messagebox.showerror("Error", "No monitors found.")
            return

        self.audio_devices = self.get_audio_devices()
        if len(self.audio_devices) == 0:
            messagebox.showerror("Error", "No audio devices.")
            return

        self.init_ui()

        self.platform_initialize()

        self.create_output_folder()
        self.recording_process = None
        self.running = False
        self.elapsed_time = 0
        self.record_area = None
        self.area_selector = AreaSelector(root)
        self.preview_window = None
        self.preview_running = False

        self.current_video_part = 0
        self.video_parts = []

    def platform_initialize(self):
        pass
    
    def t(self, key):
        return self.translation_manager.t(key)
        
    @abc.abstractmethod
    def set_icon(self):
        pass
        
    def change_theme(self, event=None):
        theme = self.theme_combo.get().lower()
        self.set_theme(theme)
        
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Combobox):
                widget.update()
        
        self.save_config()
        
    def set_theme(self, theme):
        if theme == "dark":
            set_dark_theme(self.root)
        elif theme == "light":
            set_light_theme(self.root)
        elif theme == "dark blue":
            set_dark_blue_theme(self.root)
        elif theme == "light green":
            set_light_green_theme(self.root)
        elif theme == "purple":
            set_purple_theme(self.root)
        elif theme == "starry night":
            set_starry_night_theme(self.root)

        self.current_theme = theme
        
    def save_config(self, event=None):
        self.config['Settings'] = {
            'language': self.translation_manager.language,
            'theme': self.theme_combo.get().lower(),
            'monitor': self.monitor_combo.current(),
            'fps': self.fps_combo.current(),
            'bitrate': self.bitrate_combo.current(),
            'codec': self.codec_combo.current(),
            'format': self.format_combo.current(),
            'audio': self.audio_combo.current(),
            'output_folder': self.output_folder
        }
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)
        
    def load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            self.config['Settings'] = {
                'language': 'en-US',
                'theme': 'dark',
                'monitor': 0,
                'fps': 1,
                'bitrate': 0,
                'codec': 0,
                'format': 0,
                'audio': 0,
                'output_folder': os.path.join(os.getcwd(), "OutputFiles")
            }
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)
        
        self.output_folder = self.config.get('Settings', 'output_folder', 
                                        fallback=os.path.join(os.getcwd(), "OutputFiles"))
                
    def change_language(self, event=None):
        selected_language = self.language_combo.get()
        language_map = {
            'English': 'en-US',
            'Español': 'es-CL',
            '简体中文': 'zh-Hans',
            "繁體中文": 'zh-Hant',
            'Italiano': 'it-IT',
            'Français': 'fr-FR',
            'हिन्दी': 'hi-IN',
            'Deutsch': 'de-DE',
            'Português': 'pt-BR',
            'Pусский': 'ru-RU',
            "日本語": 'ja-JP',
            "한국어": 'ko-KR',
            "Polski": 'pl-PL',
            "العربية": 'ar',
            "Tiếng Việt": 'vi-VN',
            "українська мова": 'uk-UA',
            "ไทยกลาง": 'th-TH',
            "Filipino": 'fil-PH',
            "Türkçe": 'tr-TR'
        }
        new_language = language_map.get(selected_language, 'en-US')
        
        if new_language != self.translation_manager.language:
            self.translation_manager.change_language(new_language)
            self.save_config()
            self.update_ui_texts()
            messagebox.showinfo(self.t("language_change"), self.t("language_changed_success"))

    def update_ui_texts(self):
        self.top_panel.configure(text=self.t("app_settings"))
        self.monitor_frame.configure(text=self.t("monitor"))
        self.video_settings_frame.configure(text=self.t("video_settings"))
        self.audio_settings_frame.configure(text=self.t("audio_settings"))
        self.preview_frame.configure(text=self.t("preview"))
        self.controls_frame.configure(text=self.t("controls"))
        
        self.language_label.configure(text=self.t("Language") + ":")
        self.theme_label.configure(text=self.t("theme") + ":")
        self.fps_label.configure(text=self.t("framerate") + ":")
        self.bitrate_label.configure(text=self.t("bitrate") + ":")
        self.codec_label.configure(text=self.t("video_codec") + ":")
        self.format_label.configure(text=self.t("output_format") + ":")
        self.audio_label.configure(text=self.t("audio_device") + ":")
        self.volume_label.configure(text=self.t("volume") + ":")
        self.output_settings_frame.configure(text=self.t("output_settings"))
        self.output_folder_label.configure(text=self.t("output_folder") + ":")
        
        self.toggle_btn.configure(text=self.t("start_recording") if not self.running else self.t("stop_recording"))
        self.preview_btn.configure(text=self.t("start_preview") if not self.preview_running else self.t("stop_preview"))
        self.select_area_btn.configure(text=self.t("select_recording_area"))
        self.open_folder_btn.configure(text=self.t("open_output_folder"))
        self.info_btn.configure(text=self.t("about"))
        
        self.status_label.configure(text=self.t("status_recording") if self.running else self.t("status_ready"))

    def init_ui(self):
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.top_panel = ttk.LabelFrame(self.main_frame, text=self.t("app_settings"))
        self.top_panel.pack(fill=tk.X, padx=5, pady=5)
 
        self.language_label = ttk.Label(self.top_panel, text=self.t("Language") + ":")
        self.language_label.grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.language_combo = ttk.Combobox(self.top_panel, values=["English", "Español", "简体中文", "繁體中文", "Italiano", "Français", 
                                                                "हिन्दी", "Deutsch", "Português", "Pусский", 
                                                                "日本語", "한국어", "Polski", "العربية", "Tiếng Việt", 
                                                                "українська мова", "ไทยกลาง", "Filipino", "Türkçe"], width=25)
        self.language_combo.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        self.language_combo.current(["en-US", "es-CL", "zh-Hans", "zh-Hant", "it-IT", "fr-FR", "hi-IN", "de-DE", "pt-BR", "ru-RU", 
                                    "ja-JP", "ko-KR", "pl-PL", "ar", "vi-VN", "uk-UA", "th-TH", "fil-PH", "tr-TR"].index(self.translation_manager.language))
        self.language_combo.config(state="readonly")
        self.language_combo.bind("<<ComboboxSelected>>", self.change_language)
        
        self.theme_label = ttk.Label(self.top_panel, text=self.t("theme") + ":")
        self.theme_label.grid(row=0, column=2, padx=10, pady=5, sticky="e")
        self.theme_combo = ttk.Combobox(self.top_panel, values=["Dark", "Light", "Dark Blue", "Light Green", "Purple", "Starry Night"], width=25)
        self.theme_combo.grid(row=0, column=3, padx=10, pady=5, sticky="w")
        current_theme = self.config.get('Settings', 'theme', fallback='dark')
        theme_index = {"dark": 0, "light": 1, "dark blue": 2, "light green": 3, "purple": 4, "starry night": 5}.get(current_theme, 0)
        self.theme_combo.current(theme_index)
        self.theme_combo.config(state="readonly")
        self.theme_combo.bind("<<ComboboxSelected>>", self.change_theme)

        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.left_panel = ttk.Frame(self.content_frame, width=400)
        self.left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        self.left_panel.pack_propagate(False)
        
        self.monitor_frame = ttk.LabelFrame(self.left_panel, text=self.t("monitor"))
        self.monitor_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.monitor_combo = ttk.Combobox(self.monitor_frame, values=[f"Monitor {i+1}: ({monitor.width}x{monitor.height})" for i, monitor in enumerate(self.monitors)], width=45)
        self.monitor_combo.pack(padx=10, pady=10, fill=tk.X)
        self.monitor_combo.current(0)
        self.monitor_combo.config(state="readonly")
        self.monitor_combo.bind("<<ComboboxSelected>>", self.on_monitor_change)

        self.video_settings_frame = ttk.LabelFrame(self.left_panel, text=self.t("video_settings"))
        self.video_settings_frame.pack(fill=tk.X, padx=10, pady=5)

        self.fps_frame = ttk.Frame(self.video_settings_frame)
        self.fps_frame.pack(fill=tk.X, padx=10, pady=5)
        self.fps_label = ttk.Label(self.fps_frame, text=self.t("framerate") + ":")
        self.fps_label.pack(side=tk.LEFT, padx=5)
        self.fps_combo = ttk.Combobox(self.fps_frame, values=["30", "60"], width=10)
        self.fps_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.fps_combo.current(self.config.getint('Settings', 'fps'))
        self.fps_combo.config(state="readonly")
        self.fps_combo.bind("<<ComboboxSelected>>", self.save_config)
        
        self.bitrate_frame = ttk.Frame(self.video_settings_frame)
        self.bitrate_frame.pack(fill=tk.X, padx=10, pady=5)
        self.bitrate_label = ttk.Label(self.bitrate_frame, text=self.t("bitrate") + ":")
        self.bitrate_label.pack(side=tk.LEFT, padx=5)
        self.bitrate_combo = ttk.Combobox(self.bitrate_frame, values=["1000k", "2000k", "4000k", "6000k", "8000k", "10000k", "15000k", "20000k"], width=10)
        self.bitrate_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.bitrate_combo.current(self.config.getint('Settings', 'bitrate'))
        self.bitrate_combo.config(state="readonly")
        self.bitrate_combo.bind("<<ComboboxSelected>>", self.save_config)

        self.codec_frame = ttk.Frame(self.video_settings_frame)
        self.codec_frame.pack(fill=tk.X, padx=10, pady=5)
        self.codec_label = ttk.Label(self.codec_frame, text=self.t("video_codec") + ":")
        self.codec_label.pack(side=tk.LEFT, padx=5)
        self.codec_combo = ttk.Combobox(self.codec_frame, values=["libx264", "libx265"], width=10)
        self.codec_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.codec_combo.current(self.config.getint('Settings', 'codec'))
        self.codec_combo.config(state="readonly")
        self.codec_combo.bind("<<ComboboxSelected>>", self.save_config)

        self.format_frame = ttk.Frame(self.video_settings_frame)
        self.format_frame.pack(fill=tk.X, padx=10, pady=5)
        self.format_label = ttk.Label(self.format_frame, text=self.t("output_format") + ":")
        self.format_label.pack(side=tk.LEFT, padx=5)
        self.format_combo = ttk.Combobox(self.format_frame, values=["mkv", "mp4"], width=10)
        self.format_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.format_combo.current(self.config.getint('Settings', 'format'))
        self.format_combo.config(state="readonly")
        self.format_combo.bind("<<ComboboxSelected>>", self.save_config)

        self.audio_settings_frame = ttk.LabelFrame(self.left_panel, text=self.t("audio_settings"))
        self.audio_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.audio_label = ttk.Label(self.audio_settings_frame, text=self.t("audio_device") + ":")
        self.audio_label.pack(anchor=tk.W, padx=10, pady=(10,2))
        
        self.audio_combo = ttk.Combobox(self.audio_settings_frame, values=self.audio_devices, width=45)
        self.audio_combo.pack(padx=10, pady=(0,10), fill=tk.X)
        self.audio_combo.current(self.config.getint('Settings', 'audio'))
        self.audio_combo.config(state="readonly")
        self.audio_combo.bind("<<ComboboxSelected>>", self.save_config)
        
        self.volume_frame = ttk.Frame(self.audio_settings_frame)
        self.volume_frame.pack(fill=tk.X, padx=10, pady=10)
        self.volume_label = ttk.Label(self.volume_frame, text=self.t("volume") + ":")
        self.volume_label.pack(side=tk.LEFT, padx=5)
        self.volume_scale = ttk.Scale(self.volume_frame, from_=0, to=100, orient=tk.HORIZONTAL)
        self.volume_scale.set(100)
        self.volume_scale.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.output_settings_frame = ttk.LabelFrame(self.left_panel, text=self.t("output_settings"))
        self.output_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.output_folder_frame = ttk.Frame(self.output_settings_frame)
        self.output_folder_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.output_folder_label = ttk.Label(self.output_folder_frame, text=self.t("output_folder") + ":")
        self.output_folder_label.pack(side=tk.LEFT, padx=5)
        
        self.output_folder_var = tk.StringVar()
        self.output_folder_var.set(self.output_folder)
        
        self.output_folder_entry = ttk.Entry(self.output_folder_frame, textvariable=self.output_folder_var, width=30)
        self.output_folder_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.browse_folder_btn = ttk.Button(self.output_folder_frame, text="...", width=3,
                                        command=self.browse_output_folder)
        self.browse_folder_btn.pack(side=tk.LEFT, padx=5)
        
        self.right_panel = ttk.Frame(self.content_frame)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.preview_outer_frame = ttk.Frame(self.right_panel)
        self.preview_outer_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.preview_frame = ttk.LabelFrame(self.preview_outer_frame, text=self.t("preview"))
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        self.preview_container = ttk.Frame(self.preview_frame)
        self.preview_container.pack(fill=tk.BOTH, expand=True)

        self.preview_label = ttk.Label(self.preview_container)
        self.preview_label.pack(anchor=tk.CENTER)

        self.controls_spacer = ttk.Frame(self.right_panel, height=165)
        self.controls_spacer.pack(side=tk.BOTTOM, fill=tk.X)


        self.controls_frame = ttk.LabelFrame(self.controls_spacer, text=self.t("controls"))
        self.controls_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.main_buttons_frame = ttk.Frame(self.controls_frame)
        self.main_buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        self.toggle_btn_frame = ttk.Frame(self.main_buttons_frame, width=160, height=35)
        self.toggle_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        

        self.preview_btn_frame = ttk.Frame(self.main_buttons_frame, width=160, height=35)
        self.preview_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        

        self.select_area_btn_frame = ttk.Frame(self.main_buttons_frame, width=160, height=35)
        self.select_area_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        

        self.toggle_btn = ttk.Button(self.toggle_btn_frame, text=self.t("start_recording"), 
                                command=self.toggle_recording, style="Accent.TButton")
        self.toggle_btn.pack(fill=tk.BOTH, expand=True)

        self.preview_btn = ttk.Button(self.preview_btn_frame, text=self.t("start_preview"), 
                                    command=self.toggle_preview_monitor)
        self.preview_btn.pack(fill=tk.BOTH, expand=True)

        self.select_area_btn = ttk.Button(self.select_area_btn_frame, text=self.t("select_recording_area"), 
                                        command=self.select_area)
        self.select_area_btn.pack(fill=tk.BOTH, expand=True)

        self.extra_buttons_frame = ttk.Frame(self.controls_frame)
        self.extra_buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        self.folder_btn_frame = ttk.Frame(self.extra_buttons_frame, width=245, height=35)
        self.folder_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        self.folder_btn_frame.pack_propagate(False)

        self.info_btn_frame = ttk.Frame(self.extra_buttons_frame, width=245, height=35)
        self.info_btn_frame.pack(side=tk.LEFT, padx=5, pady=5)
        self.info_btn_frame.pack_propagate(False)

        self.open_folder_btn = ttk.Button(self.folder_btn_frame, text=self.t("open_output_folder"), 
                                        command=self.open_output_folder)
        self.open_folder_btn.pack(fill=tk.BOTH, expand=True)

        self.info_btn = ttk.Button(self.info_btn_frame, text=self.t("about"), 
                                command=self.show_info)
        self.info_btn.pack(fill=tk.BOTH, expand=True)
        
        self.bottom_panel = ttk.Frame(self.main_frame)
        self.bottom_panel.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        
        self.timer_label = ttk.Label(self.bottom_panel, text="00:00:00")
        self.timer_label.pack(side=tk.LEFT, padx=20, pady=5)
        self.timer_label.config(font=("Arial", 12, "bold"))
        
        self.status_label = ttk.Label(self.bottom_panel, text=self.t("status_ready"))
        self.status_label.pack(side=tk.RIGHT, padx=20, pady=5)
        self.status_label.config(font=("Arial", 10))

        style = ttk.Style()
        style.configure("Accent.TButton")
        style.configure("Stop.TButton", background="#d9534f", foreground="white")
        style.map("Stop.TButton", background=[('active', '#c9302c')], foreground=[('active', 'white')])
        
        self.root.minsize(950, 600)
    
    @abc.abstractmethod
    def get_audio_devices(self):
        pass
        
    def toggle_preview_monitor(self):
        if self.preview_running:
            self.close_preview()
            self.preview_btn.config(text=self.t("start_preview"))
        else:
            self.preview_running = True
            self.update_preview_loop()
            self.preview_btn.config(text=self.t("stop_preview"))
            
    def update_preview_loop(self):
        self.preview_thread = threading.Thread(target=self._update_preview_thread, daemon=True)
        self.preview_thread.start()
        
    def _update_preview_thread(self):
        with mss.mss() as sct:
            while self.preview_running:
                try:
                    if self.monitor_combo and self.monitor_combo.winfo_exists():
                        monitor_index = self.monitor_combo.current()
                    else:
                        break
                    
                    if monitor_index < len(sct.monitors) - 1:
                        monitor = sct.monitors[monitor_index + 1]
                        
                        if self.record_area:
                            x1, y1, x2, y2 = self.record_area
                            monitor = {
                                "left": x1 + monitor.get("left", 0),
                                "top": y1 + monitor.get("top", 0),
                                "width": x2 - x1,
                                "height": y2 - y1
                            }
                    else:
                        monitor = sct.monitors[0]

                    screenshot = np.array(sct.grab(monitor))
                    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2RGB)
                    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)

                    try:
                        self.root.update_idletasks()
                        
                        max_available_height = self.right_panel.winfo_height() - self.controls_spacer.winfo_height() - 50
                        
                        if max_available_height > 100:
                            aspect_ratio = screenshot.shape[1] / screenshot.shape[0]
                            max_width = self.preview_frame.winfo_width() - 20 
                            
                            preview_height = min(max_available_height, screenshot.shape[0])
                            preview_width = int(preview_height * aspect_ratio)
                            
                            if preview_width > max_width:
                                preview_width = max_width
                                preview_height = int(preview_width / aspect_ratio)
                            
                            screenshot = cv2.resize(screenshot, (preview_width, preview_height), interpolation=cv2.INTER_AREA)
                        else:
                            screenshot = cv2.resize(screenshot, (320, 180), interpolation=cv2.INTER_AREA)
                            
                    except (tk.TclError, AttributeError) as e:
                        screenshot = cv2.resize(screenshot, (400, 225), interpolation=cv2.INTER_AREA)

                    image = Image.fromarray(screenshot)
                    tk_image = ImageTk.PhotoImage(image=image)

                    if self.preview_label and self.preview_label.winfo_exists():
                        self.root.after(0, self._update_preview_label, tk_image)

                    time.sleep(0.03)
                except tk.TclError:
                    break
                except Exception as e:
                    self.logger.error(f"Error en la vista previa: {e}")
                    time.sleep(1)  
                
    def _update_preview_label(self, tk_image):
        if self.preview_running:
            self.preview_label.config(image=tk_image)
            self.preview_label.image = tk_image
            
    def close_preview(self):
        self.preview_running = False
        if hasattr(self, 'preview_thread'):
            self.preview_thread.join(timeout=1.0)
        self.preview_label.config(image='')
        self.preview_label.image = None
        
    def on_closing(self):
        self.close_preview()
        if self.running:
            if messagebox.askokcancel(self.t("warning"), self.t("warning_quit")):
                self.stop_recording()
                self.root.destroy()
        else:
            self.root.destroy()

    def browse_output_folder(self):
        from tkinter import filedialog
        
        new_folder = filedialog.askdirectory(
            title=self.t("select_output_folder"),
            initialdir=self.output_folder
        )
        
        if new_folder:
            self.output_folder = new_folder
            self.output_folder_var.set(new_folder)
            self.save_config()
            self.create_output_folder()
            
    def on_monitor_change(self, event=None):
        if self.running:
            self.stop_current_recording()
            self.start_new_recording()
        self.save_config()
        
    def start_new_recording(self):
        self.create_new_video_file()
        self.start_recording(continue_timer=True)
        
    def create_new_video_file(self):
        video_name = f"Video_part{self.current_video_part}.{datetime.datetime.now().strftime('%m-%d-%Y.%H.%M.%S')}.mkv"
        self.video_path = os.path.join(self.output_folder, video_name)
        
    def stop_current_recording(self):
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

            if os.path.exists(self.video_path) and os.path.getsize(self.video_path) > 0:
                self.video_parts.append(self.video_path)
            self.current_video_part += 1
            self.recording_process = None
            
    def toggle_recording(self):
        if not self.running:
            self.start_recording()
            self.toggle_btn.config(text=self.t("stop_recording"))
        else:
            self.stop_recording()
            self.toggle_btn.config(text=self.t("start_recording"))
            
    def create_output_folder(self):
        if not hasattr(self, 'output_folder') or not self.output_folder:
            self.output_folder = os.path.join(os.getcwd(), "OutputFiles")
        
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            
    def get_monitors(self):
        return get_monitors()
        
    def select_area(self):
        self.area_selector.select_area(self.set_record_area)
        
    def set_record_area(self, record_area):
        self.record_area = record_area
        if self.record_area:
            self.preview_record_area()
            
    def preview_record_area(self):
        x1, y1, x2, y2 = self.record_area
        width = x2 - x1
        height = y2 - y1
        preview_window = tk.Toplevel(self.root)
        preview_window.geometry(f"{width}x{height}+{x1}+{y1}")
        preview_window.overrideredirect(True)
        preview_window.attributes('-alpha', 0.3)
        preview_canvas = tk.Canvas(preview_window, width=width, height=height)
        preview_canvas.pack()
        preview_canvas.create_rectangle(0, 0, width, height, outline='red', width=2)
        preview_window.after(1000, preview_window.destroy)
        
    @abc.abstractmethod
    def get_ffmpeg_path(self):
        pass
        
    @abc.abstractmethod
    def start_recording(self, continue_timer=False):
        pass
        
    def update_status_label_error_recording(self, text):
        self.status_label.after(0, lambda: self.status_label.config(text=text))
        
    @abc.abstractmethod
    def stop_recording(self):
        pass
        
    @abc.abstractmethod
    def read_ffmpeg_output(self):
        pass
        
    @abc.abstractmethod
    def concat_video_parts(self):
        pass
        
    def toggle_widgets(self, recording):
        state = "disabled" if recording else "normal"
        readonly_state = "disabled" if recording else "readonly"
        
        self.fps_combo.config(state=readonly_state)
        self.bitrate_combo.config(state=readonly_state)
        self.codec_combo.config(state=readonly_state)
        self.format_combo.config(state=readonly_state)
        self.audio_combo.config(state=readonly_state)
        self.language_combo.config(state=readonly_state)
        self.theme_combo.config(state=readonly_state)
        self.output_folder_entry.config(state=readonly_state)

        self.volume_scale.config(state=state)
        self.select_area_btn.config(state=state)
        self.open_folder_btn.config(state=state)
        self.info_btn.config(state=state)
        self.browse_folder_btn.config(state=state)

        self.toggle_btn.config(
            text=self.t("stop_recording") if recording else self.t("start_recording"),
            style="Stop.TButton" if recording else "Accent.TButton"
        )
        
        if recording:
            style = ttk.Style()
            style.configure("Stop.TButton", background="#d9534f", foreground="white")
            style.map("Stop.TButton", background=[('active', '#c9302c')], foreground=[('active', 'white')])
        
        self.status_label.config(text=self.t("status_recording") if recording else self.t("status_ready"))
        
    @abc.abstractmethod
    def open_output_folder(self):
        pass
        
    def start_timer(self):
        self.running = True
        self.elapsed_time = 0
        self.update_timer()
        
    def stop_timer(self):
        self.running = False
        if self.current_theme == "light":
            self.timer_label.config(text="00:00:00", foreground="black")
        else:
            self.timer_label.config(text="00:00:00", foreground="white")
            
    def update_timer(self):
        if self.running:
            self.elapsed_time += 1
            elapsed_time_str = time.strftime("%H:%M:%S", time.gmtime(self.elapsed_time))
            self.timer_label.config(text=elapsed_time_str, foreground="red")
            self.root.after(1000, self.update_timer)
            
    def show_info(self):
        info_window = tk.Toplevel(self.root)
        info_window.title(self.t("about"))
        info_window.geometry("360x260")
        info_window.resizable(0, 0)

        text = self.t("version_info")

        if self.translation_manager.is_rtl:
            justify = tk.RIGHT
        else:
            justify = tk.LEFT

        text_widget = tk.Text(info_window, wrap=tk.WORD, padx=10, pady=10, bg=info_window.cget("bg"), bd=0, font=("Arial", 10))
        text_widget.insert(tk.END, text)
        text_widget.configure(state=tk.DISABLED) 
        text_widget.pack(fill=tk.BOTH, expand=True)

        text_widget.tag_configure("justify", justify=justify)
        text_widget.tag_add("justify", "1.0", tk.END)
            
    def reload_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.init_ui()