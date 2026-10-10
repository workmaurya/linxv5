"""
L.I.N.X - Full-Stack Desktop Voice Assistant
A modern, dark-themed GUI voice assistant with Gemini AI integration and function calling.
"""

import os
import sys
import threading
import queue
import time
import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext, messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk
import psutil
import speech_recognition as sr
import pyttsx3
import sounddevice as sd
import numpy as np
import requests
from functools import wraps
import traceback

# Google GenAI SDK
try:
    import google.genai as genai
except ImportError:
    print("Warning: google-genai not installed. Install with: pip install google-genai")
    genai = None

# Optional: pycaw for volume control
try:
    from ctypes import *
    from comtypes import *
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    print("Warning: pycaw not installed. Volume control will be limited.")

# ============================================================================
# CONSTANTS & CONFIG
# ============================================================================
LINX_THEME = {
    "bg_dark": "#0b0f19",
    "accent_cyan": "#00f0ff",
    "border_dark": "#1a233a",
    "text_light": "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "status_online": "#00ff41",
    "status_offline": "#ff0041",
}

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")  # Set via environment variable
MODEL_NAME = "gemini-2.0-flash"  # Updated model name
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

# Ensure directories exist
Path("screenshots").mkdir(exist_ok=True)
Path("conversations").mkdir(exist_ok=True)

# ============================================================================
# TOOL DEFINITIONS FOR GEMINI FUNCTION CALLING
# ============================================================================

def lock_pc():
    """Lock the Windows PC."""
    try:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "PC locked successfully."
    except Exception as e:
        return f"Failed to lock PC: {e}"

def shutdown_pc():
    """Shutdown the Windows PC."""
    try:
        os.system("shutdown /s /t 10")
        return "PC will shut down in 10 seconds."
    except Exception as e:
        return f"Failed to shutdown: {e}"

def restart_pc():
    """Restart the Windows PC."""
    try:
        os.system("shutdown /r /t 10")
        return "PC will restart in 10 seconds."
    except Exception as e:
        return f"Failed to restart: {e}"

def adjust_volume(level):
    """Adjust system volume (0-100 or 'mute'/'unmute')."""
    try:
        if level == "mute":
            os.system("nircmd.exe mutesysvolume 1")
            return "System volume muted."
        elif level == "unmute":
            os.system("nircmd.exe mutesysvolume 0")
            return "System volume unmuted."
        else:
            level = max(0, min(100, int(level)))
            os.system(f"nircmd.exe setsysvolume {level * 655}")
            return f"Volume set to {level}%."
    except Exception as e:
        return f"Volume adjustment failed: {e}"

def take_screenshot():
    """Take a screenshot and save it."""
    try:
        import pyautogui
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshots/screenshot_{timestamp}.png"
        pyautogui.screenshot(filename)
        return f"Screenshot saved: {filename}"
    except Exception as e:
        return f"Screenshot failed: {e}"

def create_file(filename, content):
    """Create a file with the given content."""
    try:
        filepath = Path(filename)
        filepath.write_text(content)
        return f"File created: {filename}"
    except Exception as e:
        return f"File creation failed: {e}"

def open_file(filepath):
    """Open a file with the default OS handler."""
    try:
        os.startfile(filepath)
        return f"Opened: {filepath}"
    except Exception as e:
        return f"Failed to open file: {e}"

def move_file(source, destination):
    """Move a file from source to destination."""
    try:
        shutil.move(source, destination)
        return f"File moved: {source} -> {destination}"
    except Exception as e:
        return f"Move failed: {e}"

def delete_file(filepath):
    """Delete a file safely."""
    try:
        if Path(filepath).exists():
            Path(filepath).unlink()
            return f"File deleted: {filepath}"
        return f"File not found: {filepath}"
    except Exception as e:
        return f"Delete failed: {e}"

def launch_app(app_name):
    """Launch a Windows application."""
    app_map = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "media player": "wmplayer.exe",
        "chrome": "chrome.exe",
        "spotify": "spotify.exe",
        "edge": "msedge.exe",
        "explorer": "explorer.exe",
    }
    try:
        cmd = app_map.get(app_name.lower(), app_name)
        subprocess.Popen(cmd)
        return f"Launched: {app_name}"
    except Exception as e:
        return f"Launch failed: {e}"

def close_app(app_name):
    """Close a Windows application by process name."""
    try:
        os.system(f'taskkill /IM {app_name}.exe /F')
        return f"Closed: {app_name}"
    except Exception as e:
        return f"Close failed: {e}"

def open_google():
    """Open Google in the default browser."""
    try:
        os.startfile("https://www.google.com")
        return "Opened Google."
    except Exception as e:
        return f"Failed to open Google: {e}"

def open_youtube():
    """Open YouTube in the default browser."""
    try:
        os.startfile("https://www.youtube.com")
        return "Opened YouTube."
    except Exception as e:
        return f"Failed to open YouTube: {e}"

def web_search(query):
    """Open a web search in the default browser."""
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        os.startfile(search_url)
        return f"Searching for: {query}"
    except Exception as e:
        return f"Search failed: {e}"

# Tool registry for Gemini
TOOLS = {
    "lock_pc": lock_pc,
    "shutdown_pc": shutdown_pc,
    "restart_pc": restart_pc,
    "adjust_volume": adjust_volume,
    "take_screenshot": take_screenshot,
    "create_file": create_file,
    "open_file": open_file,
    "move_file": move_file,
    "delete_file": delete_file,
    "launch_app": launch_app,
    "close_app": close_app,
    "open_google": open_google,
    "open_youtube": open_youtube,
    "web_search": web_search,
}

# Gemini Tool Definitions
def get_gemini_tools():
    """Return tool definitions for Gemini API."""
    return [
        {
            "name": "lock_pc",
            "description": "Lock the Windows PC immediately.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "shutdown_pc",
            "description": "Shutdown the Windows PC in 10 seconds.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "restart_pc",
            "description": "Restart the Windows PC in 10 seconds.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "adjust_volume",
            "description": "Adjust system volume. Use level 0-100 for percentage, or 'mute'/'unmute'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "description": "Volume level (0-100) or 'mute'/'unmute'",
                    }
                },
                "required": ["level"],
            },
        },
        {
            "name": "take_screenshot",
            "description": "Take a screenshot and save it to the screenshots directory.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "create_file",
            "description": "Create a file with given content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to create",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to file",
                    },
                },
                "required": ["filename", "content"],
            },
        },
        {
            "name": "open_file",
            "description": "Open a file with the default OS handler.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file to open",
                    }
                },
                "required": ["filepath"],
            },
        },
        {
            "name": "move_file",
            "description": "Move a file from source to destination.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path"},
                    "destination": {
                        "type": "string",
                        "description": "Destination file path",
                    },
                },
                "required": ["source", "destination"],
            },
        },
        {
            "name": "delete_file",
            "description": "Delete a file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file to delete",
                    }
                },
                "required": ["filepath"],
            },
        },
        {
            "name": "launch_app",
            "description": "Launch a Windows application (notepad, calculator, chrome, spotify, etc.).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the application to launch",
                    }
                },
                "required": ["app_name"],
            },
        },
        {
            "name": "close_app",
            "description": "Close a Windows application by process name.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Process name of the application to close",
                    }
                },
                "required": ["app_name"],
            },
        },
        {
            "name": "open_google",
            "description": "Open Google search in the default browser.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "open_youtube",
            "description": "Open YouTube in the default browser.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for a query in the default browser.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    }
                },
                "required": ["query"],
            },
        },
    ]

# ============================================================================
# VOICE ENGINE
# ============================================================================

class VoiceEngine:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000
        self.recognizer.dynamic_energy_threshold = True
        
        # Initialize pyttsx3
        self.tts_engine = None
        self._init_tts()
        self.is_speaking = False

    def _init_tts(self):
        """Initialize text-to-speech engine safely."""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 215)  # Words per minute
            self.tts_engine.setProperty('volume', 1.0)
        except Exception as e:
            print(f"TTS init error: {e}")

    def listen(self, timeout=10):
        """
        Listen for audio input from microphone.
        Returns transcribed text or None on timeout/error.
        """
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=30)
            
            text = self.recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            return None
        except Exception as e:
            print(f"Listen error: {e}")
            return None

    def speak(self, text):
        """Speak the given text (thread-safe)."""
        if not self.tts_engine:
            return
        
        self.is_speaking = True
        try:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception as e:
            print(f"Speech error: {e}")
        finally:
            self.is_speaking = False

# ============================================================================
# GEMINI AI BRAIN
# ============================================================================

class GeminiBrain:
    def __init__(self, api_key):
        self.api_key = api_key
        if genai and api_key:
            genai.configure(api_key=api_key)
        self.conversation_history = []

    def process_input(self, user_message):
        """
        Process user message and return AI response with function calls.
        Returns: (response_text, tool_calls_list)
        """
        if not genai or not self.api_key:
            return "Gemini API not configured. Set GOOGLE_API_KEY environment variable.", []

        self.conversation_history.append({
            "role": "user",
            "parts": [user_message],
        })

        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=self.conversation_history,
                tools=get_gemini_tools(),
            )

            # Extract text and tool calls
            response_text = ""
            tool_calls = []

            if response.text:
                response_text = response.text

            # Check for function calls in response
            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_calls.append({
                        "name": tool_call.name,
                        "args": tool_call.args if hasattr(tool_call, 'args') else {},
                    })

            # Add assistant response to history
            self.conversation_history.append({
                "role": "model",
                "parts": [response],
            })

            return response_text, tool_calls

        except Exception as e:
            error_msg = f"Gemini error: {str(e)}"
            print(error_msg)
            return error_msg, []

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

def create_arc_reactor(size=200, bg_color=LINX_THEME["bg_dark"]):
    """Create an animated arc reactor image."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = (size // 2, size // 2)
    radius = size // 3

    # Outer ring
    draw.ellipse(
        [center[0] - radius, center[1] - radius,
         center[0] + radius, center[1] + radius],
        outline=LINX_THEME["accent_cyan"],
        width=3
    )

    # Inner rings
    for r in [radius * 0.7, radius * 0.5, radius * 0.3]:
        draw.ellipse(
            [center[0] - r, center[1] - r,
             center[0] + r, center[1] + r],
            outline=LINX_THEME["accent_cyan"],
            width=2
        )

    # Center dot
    dot_r = 8
    draw.ellipse(
        [center[0] - dot_r, center[1] - dot_r,
         center[0] + dot_r, center[1] + dot_r],
        fill=LINX_THEME["accent_cyan"]
    )

    return ImageTk.PhotoImage(img)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class LINXApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("L.I.N.X - Voice Assistant")
        self.geometry("1600x900")
        self.configure(fg_color=LINX_THEME["bg_dark"])

        # Initialize components
        self.voice_engine = VoiceEngine()
        self.brain = GeminiBrain(GOOGLE_API_KEY)
        self.conversation_history = []
        self.listening = False
        self.message_queue = queue.Queue()

        # System stats
        self.cpu_usage = 0
        self.ram_usage = 0
        self.storage_usage = 0
        self.start_time = time.time()
        self.message_count = 0

        # Build UI
        self.setup_ui()
        
        # Start background threads
        self.after(100, self.process_queue)
        self.after(1000, self.update_system_stats)

    def setup_ui(self):
        """Build the complete UI layout."""
        # Main grid: 3 columns (sidebar, center, chat)
        self.grid_rowconfigure(0, weight=0)  # Top bar
        self.grid_rowconfigure(1, weight=1)  # Content
        self.grid_columnconfigure(0, weight=0)  # Left sidebar
        self.grid_columnconfigure(1, weight=1)  # Center
        self.grid_columnconfigure(2, weight=0)  # Right sidebar

        # ================== TOP BAR ==================
        self.top_bar = ctk.CTkFrame(
            self, fg_color=LINX_THEME["border_dark"], height=60
        )
        self.top_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=0, pady=0)
        self.top_bar.grid_rowconfigure(0, weight=1)
        self.top_bar.grid_columnconfigure(1, weight=1)

        # Left: Title & Status
        left_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(
            left_frame, text="L.I.N.X", font=("Courier", 18, "bold"),
            text_color=LINX_THEME["accent_cyan"]
        ).pack(side="left", padx=5)

        self.status_indicator = ctk.CTkLabel(
            left_frame, text="● Online", font=("Courier", 10),
            text_color=LINX_THEME["status_online"]
        )
        self.status_indicator.pack(side="left", padx=10)

        # Center: Clock & Date
        center_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        center_frame.grid(row=0, column=1, sticky="center")

        self.clock_label = ctk.CTkLabel(
            center_frame, text="00:00:00", font=("Courier", 12),
            text_color=LINX_THEME["text_light"]
        )
        self.clock_label.pack()

        self.date_label = ctk.CTkLabel(
            center_frame, text="", font=("Courier", 10),
            text_color=LINX_THEME["text_secondary"]
        )
        self.date_label.pack()

        # Right: Weather (placeholder)
        right_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_frame.grid(row=0, column=2, padx=15, pady=10, sticky="e")

        self.weather_label = ctk.CTkLabel(
            right_frame, text="22°C Clear", font=("Courier", 10),
            text_color=LINX_THEME["text_light"]
        )
        self.weather_label.pack()

        # ================== LEFT SIDEBAR ==================
        self.left_sidebar = ctk.CTkFrame(
            self, fg_color=LINX_THEME["bg_dark"], width=300
        )
        self.left_sidebar.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.left_sidebar.grid_propagate(False)

        # System Stats Card
        stats_card = ctk.CTkFrame(
            self.left_sidebar, fg_color=LINX_THEME["border_dark"], corner_radius=10
        )
        stats_card.pack(fill="both", padx=5, pady=5)

        ctk.CTkLabel(
            stats_card, text="System Stats", font=("Courier", 12, "bold"),
            text_color=LINX_THEME["accent_cyan"]
        ).pack(pady=10, padx=10, anchor="w")

        # CPU
        ctk.CTkLabel(
            stats_card, text="CPU", font=("Courier", 10),
            text_color=LINX_THEME["text_secondary"]
        ).pack(anchor="w", padx=15)
        self.cpu_bar = ctk.CTkProgressBar(stats_card, fg_color=LINX_THEME["border_dark"])
        self.cpu_bar.pack(fill="x", padx=15, pady=2)
        self.cpu_label = ctk.CTkLabel(
            stats_card, text="0%", font=("Courier", 9),
            text_color=LINX_THEME["text_light"]
        )
        self.cpu_label.pack(anchor="e", padx=15)

        # RAM
        ctk.CTkLabel(
            stats_card, text="RAM", font=("Courier", 10),
            text_color=LINX_THEME["text_secondary"]
        ).pack(anchor="w", padx=15, pady=(10, 0))
        self.ram_bar = ctk.CTkProgressBar(stats_card, fg_color=LINX_THEME["border_dark"])
        self.ram_bar.pack(fill="x", padx=15, pady=2)
        self.ram_label = ctk.CTkLabel(
            stats_card, text="0%", font=("Courier", 9),
            text_color=LINX_THEME["text_light"]
        )
        self.ram_label.pack(anchor="e", padx=15)

        # Storage
        ctk.CTkLabel(
            stats_card, text="Storage", font=("Courier", 10),
            text_color=LINX_THEME["text_secondary"]
        ).pack(anchor="w", padx=15, pady=(10, 0))
        self.storage_bar = ctk.CTkProgressBar(stats_card, fg_color=LINX_THEME["border_dark"])
        self.storage_bar.pack(fill="x", padx=15, pady=2)
        self.storage_label = ctk.CTkLabel(
            stats_card, text="0%", font=("Courier", 9),
            text_color=LINX_THEME["text_light"]
        )
        self.storage_label.pack(anchor="e", padx=15, pady=(0, 10))

        # Uptime Card
        uptime_card = ctk.CTkFrame(
            self.left_sidebar, fg_color=LINX_THEME["border_dark"], corner_radius=10
        )
        uptime_card.pack(fill="both", padx=5, pady=5)

        ctk.CTkLabel(
            uptime_card, text="Session", font=("Courier", 12, "bold"),
            text_color=LINX_THEME["accent_cyan"]
        ).pack(pady=10, padx=10, anchor="w")

        self.uptime_label = ctk.CTkLabel(
            uptime_card, text="00:00:00", font=("Courier", 10),
            text_color=LINX_THEME["text_light"]
        )
        self.uptime_label.pack(padx=10, pady=2, anchor="w")

        self.message_count_label = ctk.CTkLabel(
            uptime_card, text="Messages: 0", font=("Courier", 10),
            text_color=LINX_THEME["text_light"]
        )
        self.message_count_label.pack(padx=10, pady=2, anchor="w")

        # ================== CENTER PANEL (Arc Reactor) ==================
        self.center_panel = ctk.CTkFrame(self, fg_color=LINX_THEME["bg_dark"])
        self.center_panel.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.center_panel.grid_rowconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(1, weight=0)

        # Arc Reactor
        reactor_frame = ctk.CTkFrame(self.center_panel, fg_color="transparent")
        reactor_frame.grid(row=0, column=0, sticky="nsew")
        reactor_frame.grid_rowconfigure(0, weight=1)
        reactor_frame.grid_columnconfigure(0, weight=1)

        self.reactor_image = create_arc_reactor(size=250)
        self.reactor_label = ctk.CTkLabel(
            reactor_frame, image=self.reactor_image, text="",
            fg_color="transparent"
        )
        self.reactor_label.grid(row=0, column=0, sticky="center")

        # Status text
        self.status_text = ctk.CTkLabel(
            reactor_frame, text="● Listening for wake word...",
            font=("Courier", 11), text_color=LINX_THEME["accent_cyan"]
        )
        self.status_text.grid(row=1, column=0, pady=20)

        # Bottom action bar
        action_bar = ctk.CTkFrame(self.center_panel, fg_color="transparent")
        action_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

        self.mic_button = ctk.CTkButton(
            action_bar, text="🎤 Start Listening", width=120,
            fg_color=LINX_THEME["accent_cyan"], text_color=LINX_THEME["bg_dark"],
            command=self.toggle_listening
        )
        self.mic_button.pack(side="left", padx=5)

        self.screenshot_button = ctk.CTkButton(
            action_bar, text="📸 Screenshot", width=120,
            fg_color=LINX_THEME["accent_cyan"], text_color=LINX_THEME["bg_dark"],
            command=lambda: self.message_queue.put(("tool_call", "take_screenshot", {}))
        )
        self.screenshot_button.pack(side="left", padx=5)

        # ================== RIGHT SIDEBAR (Chat Panel) ==================
        self.right_sidebar = ctk.CTkFrame(
            self, fg_color=LINX_THEME["bg_dark"], width=380
        )
        self.right_sidebar.grid(row=1, column=2, sticky="nsew", padx=10, pady=10)
        self.right_sidebar.grid_propagate(False)

        # Chat header
        chat_header = ctk.CTkFrame(self.right_sidebar, fg_color="transparent")
        chat_header.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            chat_header, text="Conversation", font=("Courier", 12, "bold"),
            text_color=LINX_THEME["accent_cyan"]
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            chat_header, text="Clear", width=60, height=24,
            fg_color=LINX_THEME["border_dark"],
            command=self.clear_chat
        )
        clear_btn.pack(side="right", padx=5)

        export_btn = ctk.CTkButton(
            chat_header, text="Export", width=60, height=24,
            fg_color=LINX_THEME["border_dark"],
            command=self.export_conversation
        )
        export_btn.pack(side="right", padx=5)

        # Chat display (scrolled text with custom styling)
        self.chat_display = scrolledtext.ScrolledText(
            self.right_sidebar, wrap=tk.WORD, font=("Courier", 9),
            bg=LINX_THEME["border_dark"], fg=LINX_THEME["text_light"],
            insertbackground=LINX_THEME["accent_cyan"],
            relief=tk.FLAT, borderwidth=0
        )
        self.chat_display.pack(fill="both", expand=True, padx=5, pady=5)
        self.chat_display.config(state=tk.DISABLED)

        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground=LINX_THEME["accent_cyan"], font=("Courier", 9, "bold"))
        self.chat_display.tag_configure("ai", foreground="#00aa00", font=("Courier", 9, "bold"))
        self.chat_display.tag_configure("tool", foreground="#ffaa00", font=("Courier", 8))

        # Chat input
        input_frame = ctk.CTkFrame(self.right_sidebar, fg_color="transparent")
        input_frame.pack(fill="x", padx=5, pady=5)

        self.text_input = ctk.CTkEntry(
            input_frame, placeholder_text="Type message or speak...",
            fg_color=LINX_THEME["border_dark"],
            text_color=LINX_THEME["text_light"]
        )
        self.text_input.pack(side="left", fill="both", expand=True, padx=5)
        self.text_input.bind("<Return>", lambda e: self.send_message())

        self.send_button = ctk.CTkButton(
            input_frame, text="Send", width=60,
            fg_color=LINX_THEME["accent_cyan"], text_color=LINX_THEME["bg_dark"],
            command=self.send_message
        )
        self.send_button.pack(side="right", padx=5)

        # Start clock update
        self.update_clock()

    def update_clock(self):
        """Update clock and date labels."""
        now = datetime.now()
        self.clock_label.configure(text=now.strftime("%H:%M:%S"))
        self.date_label.configure(text=now.strftime("%A, %B %d, %Y"))
        self.after(1000, self.update_clock)

    def update_system_stats(self):
        """Update system stats every second."""
        try:
            self.cpu_usage = psutil.cpu_percent(interval=0.1)
            self.ram_usage = psutil.virtual_memory().percent
            self.storage_usage = psutil.disk_usage('/').percent

            self.cpu_bar.set(self.cpu_usage / 100)
            self.cpu_label.configure(text=f"{self.cpu_usage:.1f}%")

            self.ram_bar.set(self.ram_usage / 100)
            self.ram_label.configure(text=f"{self.ram_usage:.1f}%")

            self.storage_bar.set(self.storage_usage / 100)
            self.storage_label.configure(text=f"{self.storage_usage:.1f}%")

            # Uptime
            uptime_seconds = int(time.time() - self.start_time)
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.uptime_label.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        except Exception as e:
            print(f"Stats update error: {e}")

        self.after(1000, self.update_system_stats)

    def toggle_listening(self):
        """Start/stop listening for voice input."""
        self.listening = not self.listening
        if self.listening:
            self.mic_button.configure(text="🎤 Listening...")
            self.status_text.configure(text="● Listening...")
            self.listening_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listening_thread.start()
        else:
            self.mic_button.configure(text="🎤 Start Listening")
            self.status_text.configure(text="● Ready")

    def listen_loop(self):
        """Background thread for voice listening."""
        while self.listening:
            try:
                text = self.voice_engine.listen(timeout=5)
                if text:
                    self.message_queue.put(("user_message", text))
                    self.listening = False  # Stop after one message
            except Exception as e:
                print(f"Listen loop error: {e}")
                self.listening = False

    def send_message(self):
        """Send a text message."""
        text = self.text_input.get().strip()
        if text:
            self.text_input.delete(0, tk.END)
            self.message_queue.put(("user_message", text))

    def process_queue(self):
        """Process messages from the queue."""
        try:
            while True:
                msg_type, *data = self.message_queue.get_nowait()

                if msg_type == "user_message":
                    self.handle_user_message(data[0])
                elif msg_type == "ai_response":
                    self.display_chat("AI", data[0], tag="ai")
                elif msg_type == "tool_call":
                    tool_name, tool_args = data[0], data[1]
                    self.execute_tool(tool_name, tool_args)

        except queue.Empty:
            pass

        self.after(100, self.process_queue)

    def handle_user_message(self, text):
        """Handle user message: display, send to Gemini, handle response."""
        # Display user message
        self.display_chat("You", text, tag="user")
        self.message_count += 1
        self.message_count_label.configure(text=f"Messages: {self.message_count}")

        # Get AI response
        self.status_text.configure(text="● Processing...")
        response_text, tool_calls = self.brain.process_input(text)

        if response_text:
            self.message_queue.put(("ai_response", response_text))

        # Execute tool calls if any
        for tool_call in tool_calls:
            self.message_queue.put(("tool_call", tool_call["name"], tool_call.get("args", {})))

        self.status_text.configure(text="● Ready")

    def execute_tool(self, tool_name, tool_args):
        """Execute a tool function."""
        if tool_name not in TOOLS:
            self.display_chat("System", f"Unknown tool: {tool_name}", tag="tool")
            return

        try:
            tool_func = TOOLS[tool_name]
            
            # Call tool with unpacked arguments
            if tool_args:
                result = tool_func(**tool_args)
            else:
                result = tool_func()
            
            self.display_chat("System", f"[{tool_name}] {result}", tag="tool")
            
            # Speak the result
            threading.Thread(
                target=lambda: self.voice_engine.speak(result),
                daemon=True
            ).start()

        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            self.display_chat("System", error_msg, tag="tool")
            print(traceback.format_exc())

    def display_chat(self, sender, message, tag="ai"):
        """Display a chat message."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"{sender}: ", tag)
        self.chat_display.insert(tk.END, f"{message}\n\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def clear_chat(self):
        """Clear chat display and history."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.conversation_history = []
        self.brain.clear_history()
        self.message_count = 0
        self.message_count_label.configure(text="Messages: 0")

    def export_conversation(self):
        """Export conversation to a file."""
        if not self.conversation_history:
            messagebox.showinfo("Export", "No conversation to export.")
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversations/conversation_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(self.conversation_history, f, indent=2)
            
            messagebox.showinfo("Export", f"Conversation exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        print("\n" + "="*60)
        print("WARNING: GOOGLE_API_KEY environment variable not set!")
        print("Set it with: set GOOGLE_API_KEY=your_api_key")
        print("Get your API key at: https://aistudio.google.com/app/apikey")
        print("="*60 + "\n")

    app = LINXApp()
    app.mainloop()
