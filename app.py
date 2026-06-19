import glob
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from ctypes import windll

try:
    import psutil
except Exception:
    psutil = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    HAVE_DND = False

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config" / "settings.json"
DEFAULT_SERVER_JAR = "server.jar"
RUNTIME_DIR = ROOT_DIR / "runtime"
JAVA_DIR = RUNTIME_DIR / "java"


class MinecraftServerManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Server Control Center")
        self.root.geometry("1400x900")
        self.root.minsize(1240, 840)
        self.root.configure(bg="#eef4ff")
        self.root.option_add("*tearOff", False)
        self.root.bind("<Configure>", self.on_window_configure)

        if os.name == "nt":
            try:
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.config = self.load_config()
        self.server_process = None
        self.monitor_thread = None
        self.server_start_time = None
        self.log_path = ROOT_DIR / "logs" / "server_manager.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.chart_history = []
        self.chart_cpu_history = []
        self.chart_ram_history = []
        self.chart_activity = 0
        self.player_count = 0
        self.chart_last_activity = 0
        self.chart_cpu_value = 0
        self.chart_ram_value = 0
        self.backup_count = 0
        self.stop_requested = False
        self.auto_restart_enabled = self.config.get("auto_restart", True)
        self.auto_restart_var = tk.BooleanVar(value=self.auto_restart_enabled)
        self.cpu_warning_triggered = False
        self.ram_warning_triggered = False

        self.show_loading_splash()
        self.build_ui()
        self.refresh_profile_list()
        self.refresh_plugin_list()
        self.refresh_mod_list()
        self.update_dashboard_info()
        self.update_java_status()
        self.update_status_summary()

        self.root.after(300, self.hide_loading_splash)
        self.root.after(250, self.auto_prepare)

    def load_config(self):
        default = {
            "profiles": [],
            "selected_profile": "",
            "server_dir": str(ROOT_DIR / "servers"),
            "java_path": "",
            "memory": "2G",
            "min_memory": "1G",
            "max_memory": "2G",
            "jvm_args": "",
            "server_type": "Paper",
            "minecraft_version": "1.21.4",
            "version": "Paper",
            "server_domain": "play.example.com",
            "ftp_host": "localhost",
            "ftp_port": 21,
            "ftp_username": "serveradmin",
            "ftp_password": "Server123!",
            "plugins": [],
            "mods": [],
            "theme": "light",
            "max_players": 10,
            "server_port": 25565,
            "motd": "play.example.com",
            "online_mode": "false",
            "enable_command_block": "false",
            "pvp": "true",
            "auto_restart": True,
        }
        if not CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(default, indent=2), encoding="utf-8")
            return default

        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                return default
            merged = default.copy()
            merged.update(loaded)
            return merged
        except Exception:
            return default

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    def apply_theme(self):
        theme = self.theme_var.get()
        self.config["theme"] = theme
        self.save_config()
        if theme == "dark":
            bg = "#120f1f"
            fg = "#f4edff"
            card = "#1b1532"
            sidebar = "#171126"
            main = "#0f0b18"
            console_bg = "#140f22"
            console_fg = "#f5edff"
            accent = "#c59bff"
            muted = "#b7a8e3"
            success_bg = "#5f3fb1"
            danger_bg = "#9b4d7a"
            warning_bg = "#b9892a"
            primary_bg = "#7c5cff"
            entry_bg = "#241a44"
            entry_fg = "#f8f4ff"
            self.theme_toggle.config(text="Light Mode")
        else:
            bg = "#f7f1ff"
            fg = "#2d1f52"
            card = "#ffffff"
            sidebar = "#f2eaff"
            main = "#f8f5ff"
            console_bg = "#ffffff"
            console_fg = "#241a44"
            accent = "#7c5cff"
            muted = "#6d5b99"
            success_bg = "#8b5cf6"
            danger_bg = "#d946ef"
            warning_bg = "#f59e0b"
            primary_bg = "#8b5cf6"
            entry_bg = "#ffffff"
            entry_fg = "#2d1f52"
            self.theme_toggle.config(text="Dark Mode")

        style = ttk.Style(self.root)
        style.configure("Card.TFrame", background=card, relief="solid", borderwidth=1)
        style.configure("Sidebar.TFrame", background=sidebar, relief="flat")
        style.configure("Main.TFrame", background=main, relief="flat")
        style.configure("PanelTitle.TLabel", background=card, foreground=fg, font=("Segoe UI", 13, "bold"))
        style.configure("SectionTitle.TLabel", background=main, foreground=fg, font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background=card, foreground=muted, font=("Segoe UI", 10))
        style.configure("Accent.TLabel", background=sidebar, foreground=accent, font=("Segoe UI", 10, "bold"))
        style.configure("Success.TButton", background=success_bg, foreground="#ffffff")
        style.configure("Danger.TButton", background=danger_bg, foreground="#ffffff")
        style.configure("Warning.TButton", background=warning_bg, foreground="#ffffff")
        style.configure("Primary.TButton", background=primary_bg, foreground="#ffffff")
        style.map("Success.TButton", background=[("active", "#7c3aed" if theme == "light" else "#6d28d9")])
        style.map("Danger.TButton", background=[("active", "#c026d3" if theme == "light" else "#a21caf")])
        style.map("Warning.TButton", background=[("active", "#d97706" if theme == "light" else "#b45309")])
        style.map("Primary.TButton", background=[("active", "#6d28d9" if theme == "light" else "#5b21b6")])

        self.root.configure(bg=bg)
        self.top_bar.configure(style="Card.TFrame")
        self.main.configure(style="Main.TFrame")
        self.sidebar.configure(style="Sidebar.TFrame")
        self.content.configure(style="Main.TFrame")
        self.dashboard_view.configure(style="Main.TFrame")
        self.console_view.configure(style="Main.TFrame")
        self.root.option_add("*Background", bg)
        self.root.option_add("*Foreground", fg)
        self.root.option_add("*Entry*Background", entry_bg)
        self.root.option_add("*Entry*Foreground", entry_fg)
        self.root.option_add("*Text*Background", console_bg)
        self.root.option_add("*Text*Foreground", console_fg)
        self.root.option_add("*TCombobox*Listbox*Background", card)
        self.root.option_add("*TCombobox*Listbox*Foreground", fg)
        self.root.option_add("*Listbox*Background", card)
        self.root.option_add("*Listbox*Foreground", fg)
        self.root.option_add("*TCombobox*Background", entry_bg)
        self.root.option_add("*TCombobox*Foreground", entry_fg)
        self.root.option_add("*SelectBackground", primary_bg)
        self.root.option_add("*SelectForeground", "#ffffff")

        if hasattr(self, 'console'):
            self.console.configure(bg=console_bg, fg=console_fg, insertbackground=console_fg)
        if hasattr(self, 'plugin_list'):
            self.plugin_list.configure(bg=card, fg=fg, selectbackground=primary_bg, selectforeground="#ffffff")
        if hasattr(self, 'mod_list'):
            self.mod_list.configure(bg=card, fg=fg, selectbackground=primary_bg, selectforeground="#ffffff")
        if hasattr(self, 'server_address_label'):
            self.server_address_label.configure(foreground=accent)
        if hasattr(self, 'profile_name'):
            self.profile_name.configure(foreground=entry_fg, background=entry_bg)
        if hasattr(self, 'server_dir_var'):
            pass

    def toggle_theme(self):
        self.theme_var.set("dark" if self.theme_var.get() != "dark" else "light")
        self.apply_theme()

    def on_window_configure(self, event=None):
        if hasattr(self, 'status_var'):
            self.update_status_summary()

    def show_loading_splash(self):
        self.loading_splash = tk.Toplevel(self.root)
        self.loading_splash.overrideredirect(True)
        self.loading_splash.configure(bg="#f7f1ff")
        self.loading_splash.geometry("420x140")
        self.loading_splash.transient(self.root)
        self.loading_splash.attributes("-topmost", True)
        x = (self.root.winfo_screenwidth() - 420) // 2
        y = (self.root.winfo_screenheight() - 140) // 2
        self.loading_splash.geometry(f"420x140+{x}+{y}")
        ttk.Label(
            self.loading_splash,
            text="Server Control Center",
            font=("Segoe UI", 16, "bold"),
            foreground="#6d28d9"
        ).pack(pady=(22, 8))
        ttk.Label(
            self.loading_splash,
            text="Loading dashboard and runtime checks...",
            foreground="#5b21b6"
        ).pack()
        self.loading_splash.update_idletasks()

    def hide_loading_splash(self):
        if hasattr(self, 'loading_splash') and self.loading_splash.winfo_exists():
            self.loading_splash.destroy()

    def update_status_summary(self):
        if hasattr(self, 'server_dir_var'):
            server_dir = self.server_dir_var.get().strip() or self.config.get("server_dir", str(ROOT_DIR / "servers"))
            java_path = self.java_var.get().strip() or self.config.get("java_path", "")
            memory = self.memory_var.get().strip() if hasattr(self, 'memory_var') else self.config.get("memory", "2G")
            min_ram = self.min_ram_var.get().strip() if hasattr(self, 'min_ram_var') else self.config.get("min_memory", memory)
            max_ram = self.max_ram_var.get().strip() if hasattr(self, 'max_ram_var') else self.config.get("max_memory", memory)
            server_state = self.server_state_var.get()
            uptime = "Running" if self.server_process and self.server_process.poll() is None and self.server_start_time else self.format_uptime()
            if hasattr(self, 'summary_server_dir_var'):
                self.summary_server_dir_var.set(server_dir)
            if hasattr(self, 'summary_java_var'):
                self.summary_java_var.set(java_path or "Not detected")
            if hasattr(self, 'summary_memory_var'):
                self.summary_memory_var.set(f"{memory} (Min: {min_ram}, Max: {max_ram})")
            if hasattr(self, 'summary_status_var'):
                self.summary_status_var.set(server_state)
            if hasattr(self, 'summary_uptime_var'):
                self.summary_uptime_var.set(uptime)

    def update_chart(self):
        if not hasattr(self, 'chart_canvas') or not self.chart_canvas.winfo_exists():
            return

        if psutil is not None:
            try:
                self.chart_cpu_value = min(100, max(0, psutil.cpu_percent(interval=None)))
                ram = psutil.virtual_memory()
                self.chart_ram_value = min(100, max(0, ram.percent))
            except Exception:
                self.chart_cpu_value = 0
                self.chart_ram_value = 0
        else:
            self.chart_cpu_value = 0
            self.chart_ram_value = 0

        if self.server_process and self.server_process.poll() is None:
            self.chart_activity = min(100, max(self.chart_activity, 55))
            if time.time() - self.chart_last_activity < 2:
                self.chart_activity = min(100, self.chart_activity + 5)
            self.chart_status_var.set("Healthy")
        else:
            self.chart_activity = max(0, self.chart_activity - 8)
            self.chart_status_var.set("Offline" if self.chart_activity < 15 else "Warning")

        if self.chart_cpu_value >= 85 and not self.cpu_warning_triggered:
            self.cpu_warning_triggered = True
            self.log("Warning: CPU usage is high.")
        elif self.chart_cpu_value < 80:
            self.cpu_warning_triggered = False

        if self.chart_ram_value >= 85 and not self.ram_warning_triggered:
            self.ram_warning_triggered = True
            self.log("Warning: RAM usage is high.")
        elif self.chart_ram_value < 80:
            self.ram_warning_triggered = False

        self.chart_history.append(self.chart_activity)
        if len(self.chart_history) > 48:
            self.chart_history = self.chart_history[-48:]
        self.chart_cpu_history.append(self.chart_cpu_value)
        self.chart_ram_history.append(self.chart_ram_value)
        if len(self.chart_cpu_history) > 48:
            self.chart_cpu_history = self.chart_cpu_history[-48:]
            self.chart_ram_history = self.chart_ram_history[-48:]

        self.chart_player_var.set(f"Players: {self.player_count}")
        self.chart_cpu_var.set(f"CPU: {self.chart_cpu_value:.0f}%")
        self.chart_ram_var.set(f"RAM: {self.chart_ram_value:.0f}%")
        self.chart_backup_var.set(f"Backups: {self.backup_count}")
        self.draw_chart()
        self.root.after(1000, self.update_chart)

    def draw_chart(self, event=None):
        if not hasattr(self, 'chart_canvas') or not self.chart_canvas.winfo_exists():
            return

        canvas = self.chart_canvas
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.delete("all")

        is_dark = self.theme_var.get() == "dark"
        bg = "#120f1f" if is_dark else "#f8f5ff"
        grid = "#2a1d4d" if is_dark else "#ece3ff"
        cpu_color = "#8b5cf6" if is_dark else "#7c5cff"
        ram_color = "#f59e0b" if is_dark else "#f59e0b"
        text_color = "#f4edff" if is_dark else "#7c5cff"
        canvas.create_rectangle(0, 0, width, height, fill=bg, outline="")
        for y in range(0, height, 40):
            canvas.create_line(0, y, width, y, fill=grid, width=1)

        cpu_values = self.chart_cpu_history or [0] * 12
        ram_values = self.chart_ram_history or [0] * 12
        if len(cpu_values) < 12:
            cpu_values = cpu_values + [cpu_values[-1] if cpu_values else 0] * (12 - len(cpu_values))
        if len(ram_values) < 12:
            ram_values = ram_values + [ram_values[-1] if ram_values else 0] * (12 - len(ram_values))

        max_value = max(max(cpu_values), max(ram_values), 1)
        points_cpu = []
        points_ram = []
        for i, (cpu_val, ram_val) in enumerate(zip(cpu_values, ram_values)):
            x = (i / (len(cpu_values) - 1)) * (width - 1) if len(cpu_values) > 1 else width // 2
            cpu_y = height - (cpu_val / max_value) * (height - 12) - 6
            ram_y = height - (ram_val / max_value) * (height - 12) - 6
            points_cpu.append((x, cpu_y))
            points_ram.append((x, ram_y))

        if len(points_cpu) >= 2:
            canvas.create_line(points_cpu, fill=cpu_color, width=2, smooth=True)
            for x, y in points_cpu:
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=cpu_color, outline=cpu_color)
        if len(points_ram) >= 2:
            canvas.create_line(points_ram, fill=ram_color, width=2, smooth=True)
            for x, y in points_ram:
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=ram_color, outline=ram_color)

        canvas.create_text(width - 4, 8, text="CPU/RAM", anchor="ne", fill=text_color, font=("Segoe UI", 9, "bold"))

    def format_uptime(self):
        if not self.server_start_time:
            return "Not running"
        elapsed = int(time.time() - self.server_start_time)
        hours, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def create_backup(self):
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            messagebox.showwarning("Server folder missing", "Please choose or create a server folder first.")
            return
        backup_dir = ROOT_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target = backup_dir / f"server_backup_{timestamp}"
        shutil.copytree(server_dir, target, dirs_exist_ok=True)
        self.backup_count = len([p for p in backup_dir.iterdir() if p.is_dir()])
        self.chart_backup_var.set(f"Backups: {self.backup_count}")
        self.log(f"Created backup: {target}")
        self.status_var.set("Backup created")

    def get_backup_list(self):
        backup_dir = ROOT_DIR / "backups"
        if not backup_dir.exists():
            return []
        return sorted([p for p in backup_dir.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)

    def restore_backup_dialog(self):
        backups = self.get_backup_list()
        if not backups:
            messagebox.showwarning("No backups found", "Create a backup first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Backup")
        dialog.geometry("420x280")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#f8f5ff")

        ttk.Label(dialog, text="Select a backup to restore:", font=("Segoe UI", 11, "bold")).pack(pady=(12, 8))
        listbox = tk.Listbox(dialog, height=10, width=50)
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        for backup in backups:
            listbox.insert(tk.END, backup.name)

        def restore_selected():
            selection = listbox.curselection()
            if not selection:
                return
            chosen = backups[selection[0]]
            self.restore_backup(chosen)
            dialog.destroy()

        button_row = ttk.Frame(dialog)
        button_row.pack(pady=(0, 10))
        ttk.Button(button_row, text="Restore", command=restore_selected, style="Warning.TButton").pack(side="left")
        ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side="left", padx=(8, 0))

    def restore_backup(self, backup_path):
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            messagebox.showwarning("Server folder missing", "Please choose or create a server folder first.")
            return
        for item in backup_path.iterdir():
            dest = server_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        self.log(f"Restored backup from {backup_path}")
        self.status_var.set("Backup restored")

    def toggle_auto_restart(self):
        self.auto_restart_enabled = self.auto_restart_var.get()
        self.config["auto_restart"] = self.auto_restart_enabled
        self.save_config()
        self.status_var.set("Auto restart enabled" if self.auto_restart_enabled else "Auto restart disabled")

    def ensure_log_file(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")

    def write_log_entry(self, message):
        self.ensure_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")

    def build_ui(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("Sidebar.TFrame", background="#f3eaff", relief="flat")
        style.configure("Main.TFrame", background="#f8f5ff", relief="flat")
        style.configure("PanelTitle.TLabel", background="#ffffff", foreground="#2d1f52", font=("Segoe UI", 13, "bold"))
        style.configure("SectionTitle.TLabel", background="#f8f5ff", foreground="#2d1f52", font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#6d5b99", font=("Segoe UI", 10))
        style.configure("Accent.TLabel", background="#f3eaff", foreground="#7c5cff", font=("Segoe UI", 10, "bold"))
        style.configure("Success.TButton", background="#8b5cf6", foreground="#ffffff")
        style.configure("Danger.TButton", background="#d946ef", foreground="#ffffff")
        style.configure("Warning.TButton", background="#f59e0b", foreground="#ffffff")
        style.configure("Primary.TButton", background="#7c5cff", foreground="#ffffff")
        style.map("Success.TButton", background=[("active", "#7c3aed")])
        style.map("Danger.TButton", background=[("active", "#c026d3")])
        style.map("Warning.TButton", background=[("active", "#d97706")])
        style.map("Primary.TButton", background=[("active", "#6d28d9")])

        self.top_bar = ttk.Frame(self.root, padding=(18, 14), style="Card.TFrame")
        self.top_bar.pack(fill="x")
        self.top_bar.configure(borderwidth=0)

        ttk.Label(self.top_bar, text="Server Control Center", font=("Segoe UI", 18, "bold"), foreground="#2d1f52").pack(side="left")
        self.status_var = tk.StringVar(value="Preparing environment")
        self.server_state_var = tk.StringVar(value="Server stopped")
        self.server_banner_var = tk.StringVar(value="Server is offline")
        self.theme_var = tk.StringVar(value=self.config.get("theme", "light"))
        self.theme_toggle = ttk.Button(self.top_bar, text="Toggle Theme", command=self.toggle_theme)
        self.theme_toggle.pack(side="right", padx=(0, 12))
        self.last_action_var = tk.StringVar(value="Ready")
        ttk.Label(self.top_bar, textvariable=self.last_action_var, foreground="#7c5cff", font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 12))
        ttk.Label(self.top_bar, textvariable=self.server_state_var, foreground="#0f766e", font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 12))
        ttk.Label(self.top_bar, textvariable=self.status_var, foreground="#7c5cff", font=("Segoe UI", 10, "bold")).pack(side="right")

        self.main = ttk.Frame(self.root, padding=(14, 14, 14, 14), style="Main.TFrame")
        self.main.pack(fill="both", expand=True)

        self.sidebar = ttk.Frame(self.main, padding=(10, 10, 10, 10), style="Sidebar.TFrame")
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.configure(width=360)

        self.content = ttk.Frame(self.main, style="Main.TFrame")
        self.content.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        # Sidebar cards
        overview = ttk.Frame(self.sidebar, padding=16, style="Card.TFrame")
        overview.pack(fill="x", pady=(0, 10))
        ttk.Label(overview, text="Overview", style="PanelTitle.TLabel").pack(anchor="w")
        self.server_status_label = ttk.Label(overview, text="Offline", foreground="#d9534f", font=("Segoe UI", 11, "bold"))
        self.server_status_label.pack(anchor="w", pady=(6, 0))
        self.server_address_label = ttk.Label(overview, text="Join address: loading...", style="Muted.TLabel", cursor="hand2")
        self.server_address_label.pack(anchor="w")
        self.server_address_label.bind("<Button-1>", self.copy_join_address)

        java_card = ttk.Frame(self.sidebar, padding=16, style="Card.TFrame")
        java_card.pack(fill="x", pady=(0, 10))
        ttk.Label(java_card, text="Runtime", style="PanelTitle.TLabel").pack(anchor="w")
        self.java_path_label = ttk.Label(java_card, text="Not detected", style="Muted.TLabel")
        self.java_path_label.pack(anchor="w", pady=(6, 0))
        ttk.Button(java_card, text="Install / Repair Java", command=self.run_java_installer).pack(anchor="w", pady=(8, 0))

        ftp_card = ttk.Frame(self.sidebar, padding=16, style="Card.TFrame")
        ftp_card.pack(fill="x", pady=(0, 10))
        ttk.Label(ftp_card, text="FTP Access", style="PanelTitle.TLabel").pack(anchor="w")
        self.ftp_host_var = tk.StringVar(value="Host: loading...")
        self.ftp_port_var = tk.StringVar(value="Port: 21")
        self.ftp_user_var = tk.StringVar(value="User: serveradmin")
        self.ftp_pass_var = tk.StringVar(value="Password: Server123!")
        self.ftp_path_var = tk.StringVar(value="Folder: /")
        for var in (self.ftp_host_var, self.ftp_port_var, self.ftp_user_var, self.ftp_pass_var, self.ftp_path_var):
            ttk.Label(ftp_card, textvariable=var, style="Muted.TLabel", justify="left", wraplength=320).pack(anchor="w", pady=(2, 0))
        ttk.Button(ftp_card, text="Copy FTP Details", command=self.copy_ftp_details).pack(anchor="w", pady=(8, 0))
        ttk.Button(ftp_card, text="Open Server Folder", command=self.open_server_folder).pack(anchor="w", pady=(4, 0))

        nav_card = ttk.Frame(self.sidebar, padding=16, style="Card.TFrame")
        nav_card.pack(fill="x")
        ttk.Label(nav_card, text="View", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Button(nav_card, text="Open Console", command=self.show_console_view).pack(anchor="w", pady=(8, 0))
        ttk.Button(nav_card, text="Open Plugins", command=self.show_plugins_view).pack(anchor="w", pady=(0, 6))
        ttk.Button(nav_card, text="Open Mods", command=self.show_mods_view).pack(anchor="w", pady=(0, 6))
        ttk.Button(nav_card, text="Back to Dashboard", command=self.show_dashboard_view).pack(anchor="w", pady=(6, 0))

        # Dashboard view (scrollable)
        self.dashboard_canvas = tk.Canvas(self.content, highlightthickness=0, bg="#f8f5ff")
        self.dashboard_scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=self.dashboard_canvas.yview)
        self.dashboard_canvas.configure(yscrollcommand=self.dashboard_scrollbar.set)
        self.dashboard_view = ttk.Frame(self.dashboard_canvas, style="Main.TFrame")
        self.dashboard_canvas_window = self.dashboard_canvas.create_window((0, 0), window=self.dashboard_view, anchor="nw")

        def _dashboard_configure(event):
            self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))
            self.dashboard_canvas.itemconfig(self.dashboard_canvas_window, width=event.width)

        self.dashboard_view.bind("<Configure>", _dashboard_configure)
        self.dashboard_canvas.bind("<Configure>", _dashboard_configure)
        self.dashboard_canvas.bind_all("<MouseWheel>", lambda event: self.dashboard_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        # Configuration form
        config_card = ttk.Frame(self.dashboard_view, padding=(0, 0, 0, 12), style="Main.TFrame")
        config_card.pack(fill="x")
        form = ttk.Frame(config_card, padding=16, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Profile Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        self.profile_name = ttk.Entry(form)
        self.profile_name.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Server Folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        self.server_dir_var = tk.StringVar(value=self.config.get("server_dir", str(ROOT_DIR / "servers")))
        dir_row = ttk.Frame(form)
        dir_row.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Entry(dir_row, textvariable=self.server_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_row, text="Browse", command=self.choose_server_dir).pack(side="left", padx=(6, 0))

        ttk.Label(form, text="Join Address").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        self.domain_var = tk.StringVar(value=self.config.get("server_domain", "play.example.com"))
        ttk.Entry(form, textvariable=self.domain_var).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Server Type", style="SectionTitle.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 4))
        ttk.Label(form, text="Server Type").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=6)
        self.server_type_var = tk.StringVar(value=self.config.get("server_type", self.config.get("version", "Paper")))
        ttk.Combobox(
            form,
            textvariable=self.server_type_var,
            values=["Paper", "Purpur", "Spigot", "Bukkit", "Fabric", "Vanilla"],
            state="readonly"
        ).grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Minecraft Version").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=6)
        self.minecraft_version_var = tk.StringVar(value=self.config.get("minecraft_version", "1.21.4"))
        ttk.Combobox(
            form,
            textvariable=self.minecraft_version_var,
            values=[
                "1.20", "1.20.1", "1.20.2", "1.20.3", "1.20.4", "1.20.5", "1.20.6",
                "1.21", "1.21.1", "1.21.2", "1.21.3", "1.21.4"
            ],
            state="readonly"
        ).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Memory").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=6)
        self.memory_var = tk.StringVar(value=self.config.get("memory", "2G"))
        ttk.Combobox(
            form,
            textvariable=self.memory_var,
            values=["1G", "2G", "3G", "4G", "6G", "8G", "12G", "16G"],
            state="readonly"
        ).grid(row=6, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="RAM").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=6)
        self.ram_var = tk.StringVar(value=self.config.get("max_memory", self.config.get("memory", "2G")))
        ttk.Combobox(
            form,
            textvariable=self.ram_var,
            values=["1G", "2G", "3G", "4G", "6G", "8G", "12G", "16G"],
            state="readonly"
        ).grid(row=7, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="Java Path").grid(row=8, column=0, sticky="w", padx=(0, 8), pady=6)
        self.java_var = tk.StringVar(value=self.config.get("java_path", ""))
        java_row = ttk.Frame(form)
        java_row.grid(row=8, column=1, sticky="ew", pady=6)
        ttk.Entry(java_row, textvariable=self.java_var).pack(side="left", fill="x", expand=True)
        ttk.Button(java_row, text="Detect", command=self.detect_java).pack(side="left", padx=(6, 0))

        button_row = ttk.Frame(form)
        button_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(button_row, text="Save Profile", command=self.save_profile).pack(side="left")
        ttk.Button(button_row, text="Setup Files", command=self.setup_server_files).pack(side="left", padx=(6, 0))
        ttk.Button(button_row, text="Download Server Jar", command=self.download_server_jar).pack(side="left", padx=(6, 0))

        action_panel = ttk.Frame(self.dashboard_view, padding=(0, 0, 0, 12), style="Main.TFrame")
        action_panel.pack(fill="x")
        action_frame = ttk.Frame(action_panel, padding=16, style="Card.TFrame")
        action_frame.pack(fill="x")
        ttk.Label(action_frame, text="Server Actions", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(action_frame, textvariable=self.server_banner_var, foreground="#dc2626", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(8, 0))
        action_buttons = ttk.Frame(action_frame)
        action_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(action_buttons, text="Start", command=self.start_server, style="Success.TButton").pack(side="left")
        ttk.Button(action_buttons, text="Stop", command=self.stop_server, style="Danger.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(action_buttons, text="Restart", command=self.restart_server, style="Warning.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(action_buttons, text="Copy Join IP", command=self.copy_join_address).pack(side="left", padx=(6, 0))
        ttk.Button(action_buttons, text="Copy FTP", command=self.copy_ftp_details).pack(side="left", padx=(6, 0))

        stats_panel = ttk.Frame(self.dashboard_view, padding=(0, 0, 0, 12), style="Main.TFrame")
        stats_panel.pack(fill="x")
        stats_frame = ttk.Frame(stats_panel, padding=16, style="Card.TFrame")
        stats_frame.pack(fill="x")
        ttk.Label(stats_frame, text="Quick Stats", style="PanelTitle.TLabel").pack(anchor="w")
        self.summary_status_var = tk.StringVar(value="Stopped")
        self.summary_uptime_var = tk.StringVar(value="Not running")
        self.summary_server_dir_var = tk.StringVar(value=self.config.get("server_dir", str(ROOT_DIR / "servers")))
        self.summary_java_var = tk.StringVar(value=self.config.get("java_path", "Not detected"))
        self.summary_memory_var = tk.StringVar(value=f"{self.config.get('memory', '2G')} (Min: {self.config.get('min_memory', self.config.get('memory', '1G'))}, Max: {self.config.get('max_memory', self.config.get('memory', '2G'))})")
        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack(fill="x", pady=(10, 0))
        for label, var in (
            ("State", self.summary_status_var),
            ("Uptime", self.summary_uptime_var),
            ("Server Folder", self.summary_server_dir_var),
            ("Java", self.summary_java_var),
            ("Memory", self.summary_memory_var),
        ):
            ttk.Label(stats_inner, text=f"{label}:", foreground="#6d5b99", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(stats_inner, textvariable=var, wraplength=980, justify="left").pack(anchor="w", pady=(0, 6))

        settings_panel = ttk.Frame(self.dashboard_view, padding=(0, 0, 0, 12), style="Main.TFrame")
        settings_panel.pack(fill="x")
        settings_frame = ttk.Frame(settings_panel, padding=16, style="Card.TFrame")
        settings_frame.pack(fill="x")
        ttk.Label(settings_frame, text="Advanced Server Settings", style="PanelTitle.TLabel").pack(anchor="w")

        settings_inner = ttk.Frame(settings_frame)
        settings_inner.pack(fill="x", pady=(10, 0))
        settings_inner.columnconfigure(1, weight=1)

        ttk.Label(settings_inner, text="Min RAM").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        self.min_ram_var = tk.StringVar(value=self.config.get("min_memory", self.config.get("memory", "1G")))
        ttk.Combobox(settings_inner, textvariable=self.min_ram_var, values=["1G", "2G", "3G", "4G", "6G", "8G"], state="readonly").grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Max RAM").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        self.max_ram_var = tk.StringVar(value=self.config.get("max_memory", self.config.get("memory", "2G")))
        ttk.Combobox(settings_inner, textvariable=self.max_ram_var, values=["1G", "2G", "3G", "4G", "6G", "8G", "12G", "16G"], state="readonly").grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="JVM Args").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        self.jvm_args_var = tk.StringVar(value=self.config.get("jvm_args", ""))
        ttk.Entry(settings_inner, textvariable=self.jvm_args_var).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Max Players").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        self.max_players_var = tk.StringVar(value=str(self.config.get("max_players", 10)))
        ttk.Entry(settings_inner, textvariable=self.max_players_var).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Port").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=6)
        self.server_port_var = tk.StringVar(value=str(self.config.get("server_port", 25565)))
        ttk.Entry(settings_inner, textvariable=self.server_port_var).grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Motd").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=6)
        self.motd_var = tk.StringVar(value=self.config.get("motd", self.config.get("server_domain", "play.example.com")))
        ttk.Entry(settings_inner, textvariable=self.motd_var).grid(row=5, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Online Mode").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=6)
        self.online_mode_var = tk.StringVar(value=str(self.config.get("online_mode", "false")))
        ttk.Combobox(settings_inner, textvariable=self.online_mode_var, values=["true", "false"], state="readonly").grid(row=6, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="Command Blocks").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=6)
        self.command_block_var = tk.StringVar(value=str(self.config.get("enable_command_block", "false")))
        ttk.Combobox(settings_inner, textvariable=self.command_block_var, values=["true", "false"], state="readonly").grid(row=7, column=1, sticky="ew", pady=6)

        ttk.Label(settings_inner, text="PvP").grid(row=8, column=0, sticky="w", padx=(0, 8), pady=6)
        self.pvp_var = tk.StringVar(value=str(self.config.get("pvp", "true")))
        ttk.Combobox(settings_inner, textvariable=self.pvp_var, values=["true", "false"], state="readonly").grid(row=8, column=1, sticky="ew", pady=6)

        # Plugins view (scrollable)
        self.plugins_canvas = tk.Canvas(self.content, highlightthickness=0, bg="#f8f5ff")
        self.plugins_scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=self.plugins_canvas.yview)
        self.plugins_canvas.configure(yscrollcommand=self.plugins_scrollbar.set)
        self.plugins_view = ttk.Frame(self.plugins_canvas, style="Main.TFrame")
        self.plugins_canvas_window = self.plugins_canvas.create_window((0, 0), window=self.plugins_view, anchor="nw")

        def _plugins_configure(event):
            self.plugins_canvas.configure(scrollregion=self.plugins_canvas.bbox("all"))
            self.plugins_canvas.itemconfig(self.plugins_canvas_window, width=event.width)

        self.plugins_view.bind("<Configure>", _plugins_configure)
        self.plugins_canvas.bind("<Configure>", _plugins_configure)
        self.plugins_canvas.bind_all("<MouseWheel>", lambda event: self.plugins_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        plugins_panel = ttk.Frame(self.plugins_view, padding=(0, 0, 0, 0), style="Main.TFrame")
        plugins_panel.pack(fill="both", expand=True)
        plugins_frame = ttk.Frame(plugins_panel, padding=16, style="Card.TFrame")
        plugins_frame.pack(fill="both", expand=True)

        plugins_header = ttk.Frame(plugins_frame)
        plugins_header.pack(fill="x")
        ttk.Button(plugins_header, text="← Back", command=self.show_dashboard_view).pack(side="left")
        ttk.Label(plugins_header, text="Plugins", style="PanelTitle.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(plugins_frame, text="Manage plugins for the server", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))
        self.plugin_list = tk.Listbox(
            plugins_frame,
            height=18,
            bg="#f7f9ff",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            exportselection=False
        )
        self.plugin_list.pack(fill="both", expand=True, pady=(8, 0))
        self.plugin_list.bind("<Configure>", lambda e: self.plugin_list.configure(bg="#f7f9ff"))
        if HAVE_DND and DND_FILES is not None and hasattr(self.plugin_list, "drop_target_register"):
            try:
                self.plugin_list.drop_target_register(DND_FILES)
                self.plugin_list.dnd_bind("<<Drop>>", self.handle_plugin_drop)
            except Exception:
                pass
        plugin_buttons = ttk.Frame(plugins_frame)
        plugin_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(plugin_buttons, text="Add Plugin", command=self.add_plugin, style="Primary.TButton").pack(side="left")
        ttk.Button(plugin_buttons, text="Remove Plugin", command=self.remove_plugin, style="Danger.TButton").pack(side="left", padx=(6, 0))

        # Mods view (scrollable)
        self.mods_canvas = tk.Canvas(self.content, highlightthickness=0, bg="#f8f5ff")
        self.mods_scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=self.mods_canvas.yview)
        self.mods_canvas.configure(yscrollcommand=self.mods_scrollbar.set)
        self.mods_view = ttk.Frame(self.mods_canvas, style="Main.TFrame")
        self.mods_canvas_window = self.mods_canvas.create_window((0, 0), window=self.mods_view, anchor="nw")

        def _mods_configure(event):
            self.mods_canvas.configure(scrollregion=self.mods_canvas.bbox("all"))
            self.mods_canvas.itemconfig(self.mods_canvas_window, width=event.width)

        self.mods_view.bind("<Configure>", _mods_configure)
        self.mods_canvas.bind("<Configure>", _mods_configure)
        self.mods_canvas.bind_all("<MouseWheel>", lambda event: self.mods_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

        mods_panel = ttk.Frame(self.mods_view, padding=(0, 0, 0, 0), style="Main.TFrame")
        mods_panel.pack(fill="both", expand=True)
        mods_frame = ttk.Frame(mods_panel, padding=16, style="Card.TFrame")
        mods_frame.pack(fill="both", expand=True)

        mods_header = ttk.Frame(mods_frame)
        mods_header.pack(fill="x")
        ttk.Button(mods_header, text="← Back", command=self.show_dashboard_view).pack(side="left")
        ttk.Label(mods_header, text="Mods", style="PanelTitle.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(mods_frame, text="Manage mods for the server", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))
        self.mod_list = tk.Listbox(
            mods_frame,
            height=18,
            bg="#f7f9ff",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            exportselection=False
        )
        self.mod_list.pack(fill="both", expand=True, pady=(8, 0))
        self.mod_list.bind("<Configure>", lambda e: self.mod_list.configure(bg="#f7f9ff"))
        if HAVE_DND and DND_FILES is not None and hasattr(self.mod_list, "drop_target_register"):
            try:
                self.mod_list.drop_target_register(DND_FILES)
                self.mod_list.dnd_bind("<<Drop>>", self.handle_mod_drop)
            except Exception:
                pass
        mod_buttons = ttk.Frame(mods_frame)
        mod_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(mod_buttons, text="Add Mod", command=self.add_mod, style="Primary.TButton").pack(side="left")
        ttk.Button(mod_buttons, text="Remove Mod", command=self.remove_mod, style="Danger.TButton").pack(side="left", padx=(6, 0))

        # Console view
        self.console_view = ttk.Frame(self.content, style="Main.TFrame")
        self.console_view.pack(fill="both", expand=True)
        self.console_view.pack_forget()

        console_panel = ttk.Frame(self.console_view, padding=(0, 0, 0, 0), style="Main.TFrame")
        console_panel.pack(fill="both", expand=True)
        console_frame = ttk.Frame(console_panel, padding=16, style="Card.TFrame")
        console_frame.pack(fill="both", expand=True)

        console_header = ttk.Frame(console_frame)
        console_header.pack(fill="x")
        ttk.Button(console_header, text="← Back", command=self.show_dashboard_view).pack(side="left")
        ttk.Label(console_header, text="Console", style="PanelTitle.TLabel").pack(side="left", padx=(10, 0))

        controls = ttk.Frame(console_frame)
        controls.pack(fill="x", pady=(8, 6))
        ttk.Button(controls, text="Start", command=self.start_server, style="Success.TButton").pack(side="left")
        ttk.Button(controls, text="Stop", command=self.stop_server, style="Danger.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Restart", command=self.restart_server, style="Warning.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Clear Log", command=self.clear_console, style="Primary.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Save Log", command=self.save_log_file, style="Primary.TButton").pack(side="left", padx=(6, 0))

        command_row = ttk.Frame(console_frame)
        command_row.pack(fill="x", pady=(0, 6))
        self.console_command_var = tk.StringVar()
        self.console_command_entry = ttk.Entry(command_row, textvariable=self.console_command_var)
        self.console_command_entry.pack(side="left", fill="x", expand=True)
        self.console_command_entry.bind("<Return>", lambda event: self.send_console_command())
        ttk.Button(command_row, text="Send", command=self.send_console_command, style="Primary.TButton").pack(side="left", padx=(6, 0))

        console_body = ttk.Frame(console_frame)
        console_body.pack(fill="both", expand=True)

        console_left = ttk.Frame(console_body)
        console_left.pack(side="left", fill="both", expand=True)
        self.console = tk.Text(
            console_left,
            wrap="word",
            state="disabled",
            bg="#0f1117",
            fg="#e6eefc",
            font=("Consolas", 11),
            height=28
        )
        self.console.pack(fill="both", expand=True)

        chart_panel = ttk.Frame(console_body, padding=10, style="Card.TFrame")
        chart_panel.pack(side="right", fill="y", padx=(8, 0))
        chart_panel.configure(width=320)
        chart_panel.columnconfigure(0, weight=1)
        ttk.Label(chart_panel, text="Server Health", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.chart_status_var = tk.StringVar(value="Offline")
        self.chart_player_var = tk.StringVar(value="Players: 0")
        self.chart_cpu_var = tk.StringVar(value="CPU: 0%")
        self.chart_ram_var = tk.StringVar(value="RAM: 0%")
        self.chart_backup_var = tk.StringVar(value="Backups: 0")
        ttk.Label(chart_panel, textvariable=self.chart_status_var, foreground="#7c5cff", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(chart_panel, textvariable=self.chart_player_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(chart_panel, textvariable=self.chart_cpu_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 0))
        ttk.Label(chart_panel, textvariable=self.chart_ram_var, style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Label(chart_panel, textvariable=self.chart_backup_var, style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 6))
        ttk.Button(chart_panel, text="⟳ Backup", command=self.create_backup, style="Primary.TButton").grid(row=6, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(chart_panel, text="↺ Restore", command=self.restore_backup_dialog, style="Warning.TButton").grid(row=7, column=0, sticky="ew")
        ttk.Checkbutton(
            chart_panel,
            text="Auto Restart on Crash",
            variable=self.auto_restart_var,
            command=self.toggle_auto_restart,
            onvalue=True,
            offvalue=False
        ).grid(row=8, column=0, sticky="w", pady=(6, 0))
        self.chart_canvas = tk.Canvas(chart_panel, height=220, bg="#f8f5ff", highlightthickness=0)
        self.chart_canvas.grid(row=9, column=0, sticky="ew")
        self.chart_canvas.bind("<Configure>", self.draw_chart)

        self.profile_combo = ttk.Combobox(form, values=[], state="readonly")
        self.profile_combo.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.profile_combo.bind("<<ComboboxSelected>>", self.select_profile)
        self.profile_combo.set(self.config.get("selected_profile", ""))

        self.show_dashboard_view()
        self.apply_theme()
        self.root.after(500, self.update_chart)

    def get_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return None

    def copy_join_address(self, event=None):
        join_value = self.server_address_label.cget("text").replace("Join address: ", "")
        if join_value and join_value != "loading...":
            self.root.clipboard_clear()
            self.root.clipboard_append(join_value)
            self.status_var.set("Join address copied")

    def copy_ftp_details(self):
        details = (
            f"Host: {self.ftp_host_var.get().replace('Host: ', '')}\n"
            f"Port: {self.ftp_port_var.get().replace('Port: ', '')}\n"
            f"User: {self.ftp_user_var.get().replace('User: ', '')}\n"
            f"Password: {self.ftp_pass_var.get().replace('Password: ', '')}\n"
            f"Folder: {self.ftp_path_var.get().replace('Folder: ', '')}"
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(details)
        self.status_var.set("FTP details copied")

    def show_console_view(self):
        self.dashboard_canvas.pack_forget()
        self.dashboard_scrollbar.pack_forget()
        self.plugins_canvas.pack_forget()
        self.plugins_scrollbar.pack_forget()
        self.mods_canvas.pack_forget()
        self.mods_scrollbar.pack_forget()
        self.console_view.pack(fill="both", expand=True)
        self.root.update_idletasks()

    def show_plugins_view(self):
        self.dashboard_canvas.pack_forget()
        self.dashboard_scrollbar.pack_forget()
        self.console_view.pack_forget()
        self.mods_canvas.pack_forget()
        self.mods_scrollbar.pack_forget()
        self.plugins_canvas.pack(side="left", fill="both", expand=True)
        self.plugins_scrollbar.pack(side="right", fill="y")
        self.plugins_canvas.update_idletasks()
        self.plugins_canvas.configure(scrollregion=self.plugins_canvas.bbox("all"))
        self.root.update_idletasks()

    def show_mods_view(self):
        self.dashboard_canvas.pack_forget()
        self.dashboard_scrollbar.pack_forget()
        self.console_view.pack_forget()
        self.plugins_canvas.pack_forget()
        self.plugins_scrollbar.pack_forget()
        self.mods_canvas.pack(side="left", fill="both", expand=True)
        self.mods_scrollbar.pack(side="right", fill="y")
        self.mods_canvas.update_idletasks()
        self.mods_canvas.configure(scrollregion=self.mods_canvas.bbox("all"))
        self.root.update_idletasks()

    def show_dashboard_view(self):
        self.console_view.pack_forget()
        self.plugins_canvas.pack_forget()
        self.plugins_scrollbar.pack_forget()
        self.mods_canvas.pack_forget()
        self.mods_scrollbar.pack_forget()
        self.dashboard_canvas.pack(side="left", fill="both", expand=True)
        self.dashboard_scrollbar.pack(side="right", fill="y")
        self.dashboard_canvas.update_idletasks()
        self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))
        self.root.update_idletasks()

    def update_dashboard_info(self):
        local_ip = self.get_local_ip()
        join_address = f"{local_ip}:25565" if local_ip else "IP not detected"
        domain = self.domain_var.get().strip()
        if domain and domain != "play.example.com":
            join_address = f"{domain}:25565"
        self.server_address_label.config(text=f"Join address: {join_address}")

        ftp_host = self.config.get("ftp_host") or local_ip or domain or "localhost"
        ftp_port = self.config.get("ftp_port", 21)
        ftp_user = self.config.get("ftp_username", "serveradmin")
        ftp_pass = self.config.get("ftp_password", "Server123!")
        ftp_folder = self.server_dir_var.get().strip() or self.config.get("server_dir", str(ROOT_DIR / "servers"))

        self.config["ftp_host"] = ftp_host
        self.config["ftp_port"] = ftp_port
        self.config["ftp_username"] = ftp_user
        self.config["ftp_password"] = ftp_pass

        self.ftp_host_var.set(f"Host: {ftp_host}")
        self.ftp_port_var.set(f"Port: {ftp_port}")
        self.ftp_user_var.set(f"User: {ftp_user}")
        self.ftp_pass_var.set(f"Password: {ftp_pass}")
        self.ftp_path_var.set(f"Folder: {ftp_folder}")

    def refresh_profile_list(self):
        profiles = self.config.get("profiles", [])
        self.profile_combo["values"] = [p["name"] for p in profiles]
        selected = self.config.get("selected_profile", "")
        if selected in [p["name"] for p in profiles]:
            self.profile_combo.set(selected)
        elif profiles:
            self.profile_combo.set(profiles[0]["name"])

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            messagebox.showerror("Missing profile name", "Please enter a profile name.")
            return

        profile = {
            "name": name,
            "server_dir": self.server_dir_var.get().strip(),
            "server_type": self.server_type_var.get(),
            "minecraft_version": self.minecraft_version_var.get(),
            "version": self.server_type_var.get(),
            "memory": self.memory_var.get(),
            "min_memory": self.min_ram_var.get(),
            "max_memory": self.max_ram_var.get(),
            "jvm_args": self.jvm_args_var.get(),
            "java_path": self.java_var.get().strip(),
            "server_domain": self.domain_var.get().strip(),
            "max_players": self.max_players_var.get(),
            "server_port": self.server_port_var.get(),
            "motd": self.motd_var.get(),
            "online_mode": self.online_mode_var.get(),
            "enable_command_block": self.command_block_var.get(),
            "pvp": self.pvp_var.get(),
        }

        profiles = self.config.get("profiles", [])
        existing = next((p for p in profiles if p["name"] == name), None)
        if existing:
            profiles.remove(existing)
        profiles.append(profile)
        self.config["profiles"] = profiles
        self.config["selected_profile"] = name
        self.config["server_dir"] = profile["server_dir"]
        self.config["server_type"] = profile["server_type"]
        self.config["minecraft_version"] = profile["minecraft_version"]
        self.config["version"] = profile["version"]
        self.config["memory"] = profile["memory"]
        self.config["min_memory"] = profile["min_memory"]
        self.config["max_memory"] = profile["max_memory"]
        self.config["jvm_args"] = profile["jvm_args"]
        self.config["java_path"] = profile["java_path"]
        self.config["server_domain"] = profile["server_domain"]
        self.config["max_players"] = profile["max_players"]
        self.config["server_port"] = profile["server_port"]
        self.config["motd"] = profile["motd"]
        self.config["online_mode"] = profile["online_mode"]
        self.config["enable_command_block"] = profile["enable_command_block"]
        self.config["pvp"] = profile["pvp"]
        self.save_config()
        self.refresh_profile_list()
        self.update_dashboard_info()
        self.status_var.set(f"Profile saved: {name}")

    def select_profile(self, event=None):
        name = self.profile_combo.get()
        self.config["selected_profile"] = name
        self.save_config()
        for p in self.config.get("profiles", []):
            if p["name"] == name:
                self.profile_name.delete(0, tk.END)
                self.profile_name.insert(0, name)
                self.server_dir_var.set(p.get("server_dir", ""))
                self.server_type_var.set(p.get("server_type", p.get("version", "Paper")))
                self.minecraft_version_var.set(p.get("minecraft_version", self.config.get("minecraft_version", "1.21.4")))
                self.memory_var.set(p.get("memory", "2G"))
                self.min_ram_var.set(p.get("min_memory", self.config.get("min_memory", "1G")))
                self.max_ram_var.set(p.get("max_memory", self.config.get("max_memory", "2G")))
                self.jvm_args_var.set(p.get("jvm_args", self.config.get("jvm_args", "")))
                self.java_var.set(p.get("java_path", ""))
                self.domain_var.set(p.get("server_domain", self.config.get("server_domain", "play.example.com")))
                self.max_players_var.set(str(p.get("max_players", self.config.get("max_players", 10))))
                self.server_port_var.set(str(p.get("server_port", self.config.get("server_port", 25565))))
                self.motd_var.set(p.get("motd", self.config.get("motd", self.config.get("server_domain", "play.example.com"))))
                self.online_mode_var.set(str(p.get("online_mode", self.config.get("online_mode", "false"))))
                self.command_block_var.set(str(p.get("enable_command_block", self.config.get("enable_command_block", "false"))))
                self.pvp_var.set(str(p.get("pvp", self.config.get("pvp", "true"))))
                self.update_dashboard_info()
                break

    def choose_server_dir(self):
        directory = filedialog.askdirectory(title="Choose server folder")
        if directory:
            self.server_dir_var.set(directory)
            self.update_dashboard_info()

    def open_server_folder(self):
        folder = Path(self.server_dir_var.get().strip())
        if folder.exists():
            os.startfile(str(folder))
        else:
            messagebox.showwarning("Folder missing", "The server folder is not created yet.")

    def get_java_version(self, java_path):
        if not java_path or not os.path.exists(java_path):
            return None

        # First try the actual runtime output.
        try:
            result = subprocess.run(
                [java_path, "-version"],
                capture_output=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            output = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            match = re.search(r'(?i)version\s+"?(\d+)', output)
            if match:
                return int(match.group(1))

            match = re.search(r'(?i)(?:openjdk|temurin).*?(\d+)\.', output)
            if match:
                return int(match.group(1))
        except Exception:
            output = ""

        # Fallback: inspect the installed path name itself.
        normalized = os.path.normpath(java_path).lower()
        for pattern in [
            r"jdk-(\d+)",
            r"jdk_(\d+)",
            r"java(\d+)"
        ]:
            match = re.search(pattern, normalized)
            if match:
                return int(match.group(1))

        # Final fallback: look for a plausible Java 21 path in common folders.
        for expected in [
            r"C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\jdk-21.0.4.7-hotspot\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-21.0.4.7-hotspot\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot\bin\java.exe"
        ]:
            if os.path.normpath(java_path).lower() == os.path.normpath(expected).lower():
                return 21 if "jdk-21" in expected.lower() else 17

        return None

    def detect_java(self):
        candidates = []
        java_in_path = shutil.which("java")
        if java_in_path:
            candidates.append(java_in_path)

        java_home = os.environ.get("JAVA_HOME", "")
        if java_home:
            candidates.append(os.path.join(java_home, "bin", "java.exe"))

        for candidate in [
            r"C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\jdk-21.0.4.7-hotspot\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-21.0.4.7-hotspot\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot\bin\java.exe",
            r"C:\Program Files\Java\jdk-21\bin\java.exe",
            r"C:\Program Files\Java\jre1.8.0_491\bin\java.exe"
        ]:
            if candidate and os.path.exists(candidate):
                candidates.append(candidate)

        for pattern in [
            r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk-*\bin\java.exe",
            r"C:\Program Files\Java\*\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\*\java.exe"
        ]:
            candidates.extend(glob.glob(pattern))

        unique_candidates = []
        for candidate in candidates:
            if candidate not in unique_candidates:
                unique_candidates.append(candidate)

        best_path = None
        best_version = -1
        for candidate in unique_candidates:
            version = self.get_java_version(candidate)
            if version is not None and version > best_version:
                best_version = version
                best_path = candidate

        if best_path:
            self.java_var.set(best_path)
            self.config["java_path"] = best_path
            self.save_config()
            self.update_java_status()
            return True
        return False

    def update_java_status(self):
        java_path = self.java_var.get().strip() or self.config.get("java_path", "")
        if java_path and os.path.exists(java_path):
            java_version = self.get_java_version(java_path)
            version_text = f" (Java {java_version})" if java_version is not None else ""
            self.java_path_label.config(text=f"{java_path}{version_text}")
            if java_version is not None and java_version >= 21:
                self.status_var.set("Runtime ready")
                self.server_status_label.config(text="Ready", foreground="#2e7d32")
            else:
                self.status_var.set("Java version may be too old")
                self.server_status_label.config(text="Needs update", foreground="#f59e0b")
        else:
            self.java_path_label.config(text="Not detected")
            self.status_var.set("Waiting for runtime")
            self.server_status_label.config(text="Offline", foreground="#d9534f")

    def auto_prepare(self):
        if not self.detect_java():
            self.log("Java was not found. Starting automatic installer...")
            self.run_java_installer()
        else:
            self.log("Java runtime detected successfully.")
        self.ensure_server_folder()

    def ensure_server_folder(self):
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            server_dir.mkdir(parents=True, exist_ok=True)
            (server_dir / "plugins").mkdir(exist_ok=True)
            self.log(f"Created server folder: {server_dir}")

    def setup_server_files(self):
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir:
            messagebox.showerror("Missing folder", "Please choose a server folder first.")
            return
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "plugins").mkdir(exist_ok=True)
        (server_dir / "mods").mkdir(exist_ok=True)

        domain = self.domain_var.get().strip() or "play.example.com"
        max_players = self.max_players_var.get().strip() or "10"
        server_port = self.server_port_var.get().strip() or "25565"
        motd = self.motd_var.get().strip() or domain
        online_mode = self.online_mode_var.get().strip().lower() or "false"
        command_block = self.command_block_var.get().strip().lower() or "false"
        pvp = self.pvp_var.get().strip().lower() or "true"

        (server_dir / "server.properties").write_text(
            f"enable-command-block={command_block}\n"
            f"max-players={max_players}\n"
            f"server-port={server_port}\n"
            f"motd={motd}\n"
            f"online-mode={online_mode}\n"
            f"pvp={pvp}\n",
            encoding="utf-8"
        )
        (server_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        (server_dir / "ops.json").write_text("[]\n", encoding="utf-8")
        self.config["server_dir"] = str(server_dir)
        self.config["server_domain"] = domain
        self.config["max_players"] = max_players
        self.config["server_port"] = server_port
        self.config["motd"] = motd
        self.config["online_mode"] = online_mode
        self.config["enable_command_block"] = command_block
        self.config["pvp"] = pvp
        self.save_config()
        self.update_dashboard_info()
        self.log(f"Created server folder and base config files for {domain}.")
        self.status_var.set("Server files ready")

    def prompt_accept_eula(self, server_dir):
        eula_path = server_dir / "eula.txt"
        if not eula_path.exists():
            return True

        try:
            eula_text = eula_path.read_text(encoding="utf-8")
        except Exception:
            eula_text = ""

        if "eula=true" in eula_text.lower():
            return True

        popup = tk.Toplevel(self.root)
        popup.title("Accept EULA")
        popup.geometry("380x150")
        popup.transient(self.root)
        popup.grab_set()
        popup.configure(bg="#f8fafc")

        ttk.Label(
            popup,
            text="You need to accept the Minecraft EULA before the server can start.",
            wraplength=340,
            foreground="#0f172a",
            justify="center"
        ).pack(pady=(18, 10))

        def accept_and_close():
            eula_path.write_text("eula=true\n", encoding="utf-8")
            popup.destroy()

        button_row = ttk.Frame(popup)
        button_row.pack(pady=(6, 0))
        ttk.Button(button_row, text="Accept", command=accept_and_close).pack(side="left")
        ttk.Button(button_row, text="Cancel", command=popup.destroy).pack(side="left", padx=(8, 0))

        self.root.wait_window(popup)
        return "eula=true" in (eula_path.read_text(encoding="utf-8") if eula_path.exists() else "").lower()

    def run_java_installer(self):
        script = ROOT_DIR / "scripts" / "setup_windows.ps1"
        if not script.exists():
            messagebox.showerror("Missing script", "The Windows setup script was not found.")
            return
        try:
            self.log("Launching Java installation script...")
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script)
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.log("Installer opened in a new terminal window.")
        except Exception as exc:
            self.log(f"Installer error: {exc}")
            messagebox.showerror("Installer failed", str(exc))

    def get_download_url(self, project, version):
        if project == "Paper":
            api_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}"
            info = json.loads(urllib.request.urlopen(api_url).read().decode("utf-8"))
            builds = info.get("builds", [])
            if not builds:
                return None
            build = builds[-1]
            return (
                f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{build}"
                f"/downloads/paper-{version}-{build}.jar"
            )
        if project == "Purpur":
            api_url = f"https://api.purpurmc.org/v2/purpur/{version}"
            info = json.loads(urllib.request.urlopen(api_url).read().decode("utf-8"))
            builds = info.get("builds", [])
            if not builds:
                return None
            build = builds[-1]
            return f"https://api.purpurmc.org/v2/purpur/{version}/{build}/download"
        if project == "Spigot":
            return f"https://download.getbukkit.org/spigot/spigot-{version}.jar"
        if project == "Bukkit":
            return f"https://download.getbukkit.org/bukkit/bukkit-{version}.jar"
        return None

    def download_server_jar(self):
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            self.ensure_server_folder()
            server_dir = Path(self.server_dir_var.get().strip())
        server_type = self.server_type_var.get()
        minecraft_version = self.minecraft_version_var.get()
        destination = server_dir / DEFAULT_SERVER_JAR
        if destination.exists():
            self.log(f"Server jar already exists: {destination}")
            return

        url = self.get_download_url(server_type, minecraft_version)
        if not url:
            self.log(f"Automatic download is not available for server type '{server_type}' yet.")
            return

        self.log(f"Downloading {server_type} {minecraft_version} server jar...")
        try:
            urllib.request.urlretrieve(url, destination)
            self.log(f"Downloaded server jar to {destination}")
        except Exception as exc:
            self.log(f"Download failed: {exc}")
            messagebox.showerror("Download failed", str(exc))

    def add_plugin(self):
        plugin_path = filedialog.askopenfilename(
            title="Choose plugin JAR",
            filetypes=[("Plugin files", "*.jar"), ("All files", "*.*")]
        )
        if plugin_path:
            self.install_plugin_from_path(plugin_path)

    def install_plugin_from_path(self, plugin_path):
        plugin_file = Path(plugin_path)
        if plugin_file.suffix.lower() != ".jar":
            messagebox.showwarning("Unsupported file", "Please drop or select a .jar file.")
            return
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            messagebox.showerror("Server folder missing", "Create or select a server folder first.")
            return
        target = server_dir / "plugins" / plugin_file.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_file, target)
        self.config.setdefault("plugins", [])
        if str(target) not in self.config["plugins"]:
            self.config["plugins"].append(str(target))
        self.save_config()
        self.refresh_plugin_list()
        self.log(f"Added plugin: {plugin_file.name}")

    def handle_plugin_drop(self, event):
        dropped = event.data
        if dropped.startswith("{") and dropped.endswith("}"):
            return
        paths = self._decode_drop_paths(dropped)
        for path in paths:
            self.install_plugin_from_path(path)

    def _decode_drop_paths(self, data):
        if not data:
            return []
        if data.startswith("{") and data.endswith("}"):
            candidate = data[1:-1]
            return [candidate] if candidate else []
        matches = re.findall(r'\{([^{}]+)\}', data)
        if matches:
            return [m for m in matches if m]
        return [part for part in data.split() if part]

    def remove_plugin(self):
        selected = self.plugin_list.curselection()
        if not selected:
            return
        item = self.plugin_list.get(selected[0])
        plugin_path = Path(item)
        if plugin_path.exists():
            plugin_path.unlink(missing_ok=True)
        self.config["plugins"] = [p for p in self.config.get("plugins", []) if p != str(plugin_path)]
        self.save_config()
        self.refresh_plugin_list()
        self.log(f"Removed plugin: {plugin_path.name}")

    def add_mod(self):
        mod_path = filedialog.askopenfilename(
            title="Choose mod file",
            filetypes=[("Mod files", "*.jar"), ("All files", "*.*")]
        )
        if mod_path:
            self.install_mod_from_path(mod_path)

    def install_mod_from_path(self, mod_path):
        mod_file = Path(mod_path)
        if mod_file.suffix.lower() != ".jar":
            messagebox.showwarning("Unsupported file", "Please drop or select a .jar file.")
            return
        server_dir = Path(self.server_dir_var.get().strip())
        if not server_dir.exists():
            messagebox.showerror("Server folder missing", "Create or select a server folder first.")
            return
        target = server_dir / "mods" / mod_file.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mod_file, target)
        self.config.setdefault("mods", [])
        if str(target) not in self.config["mods"]:
            self.config["mods"].append(str(target))
        self.save_config()
        self.refresh_mod_list()
        self.log(f"Added mod: {mod_file.name}")

    def handle_mod_drop(self, event):
        dropped = event.data
        if dropped.startswith("{") and dropped.endswith("}"):
            return
        paths = self._decode_drop_paths(dropped)
        for path in paths:
            self.install_mod_from_path(path)

    def remove_mod(self):
        selected = self.mod_list.curselection()
        if not selected:
            return
        item = self.mod_list.get(selected[0])
        mod_path = Path(item)
        if mod_path.exists():
            mod_path.unlink(missing_ok=True)
        self.config["mods"] = [p for p in self.config.get("mods", []) if p != str(mod_path)]
        self.save_config()
        self.refresh_mod_list()
        self.log(f"Removed mod: {mod_path.name}")

    def refresh_plugin_list(self):
        plugins = self.config.get("plugins", [])
        self.plugin_list.delete(0, tk.END)
        for plugin in plugins:
            self.plugin_list.insert(tk.END, plugin)

    def refresh_mod_list(self):
        mods = self.config.get("mods", [])
        self.mod_list.delete(0, tk.END)
        for mod in mods:
            self.mod_list.insert(tk.END, mod)

    def start_server(self):
        if self.server_process and self.server_process.poll() is None:
            self.log("Server is already running.")
            return

        if not self.detect_java():
            self.log("Java runtime was not detected automatically. Trying installer...")
            self.run_java_installer()
            return

        java_path = self.java_var.get().strip() or self.config.get("java_path", "")
        server_dir = Path(self.server_dir_var.get().strip())
        if not java_path or not os.path.exists(java_path):
            messagebox.showerror("Java missing", "Please install or detect Java first.")
            return

        java_version = self.get_java_version(java_path)
        selected_version = self.minecraft_version_var.get().strip()
        match = re.match(r"^(\d+)\.(\d+)", selected_version)
        requires_java_21 = False
        if match:
            requires_java_21 = (int(match.group(1)), int(match.group(2))) >= (1, 20)
        required_version = 21 if requires_java_21 else 17
        if java_version is None or java_version < required_version:
            messagebox.showerror(
                "Java version mismatch",
                f"The selected Minecraft version ({selected_version}) needs Java {required_version}+ but the detected runtime is {java_version or 'unknown'}.\nPlease install the correct Java version first."
            )
            self.run_java_installer()
            return

        if not server_dir.exists():
            messagebox.showerror("Server folder missing", "Please create or select a server folder first.")
            return

        if not self.prompt_accept_eula(server_dir):
            self.log("Server start cancelled because the EULA was not accepted.")
            return

        jar_path = server_dir / DEFAULT_SERVER_JAR
        if not jar_path.exists():
            self.log(f"Server jar not found at {jar_path}. Trying automatic download...")
            self.download_server_jar()
            jar_path = server_dir / DEFAULT_SERVER_JAR
        if not jar_path.exists():
            messagebox.showwarning(
                "Server jar missing",
                f"Expected {jar_path.name} in the selected folder. Please download it first or select another folder."
            )
            return

        min_ram = self.min_ram_var.get().strip() or self.memory_var.get().strip() or self.config.get("min_memory", "1G")
        max_ram = self.max_ram_var.get().strip() or self.memory_var.get().strip() or self.config.get("max_memory", "2G")
        jvm_args = self.jvm_args_var.get().strip()

        self.config.update({
            "server_dir": str(server_dir),
            "java_path": java_path,
            "memory": self.memory_var.get().strip() or "2G",
            "min_memory": min_ram,
            "max_memory": max_ram,
            "jvm_args": jvm_args,
            "minecraft_version": selected_version,
            "server_type": self.server_type_var.get(),
            "version": self.server_type_var.get(),
        })
        self.save_config()

        command = [java_path, f"-Xms{min_ram}", f"-Xmx{max_ram}"]
        if jvm_args:
            command.extend(jvm_args.split())
        command.extend(["-jar", str(jar_path), "nogui"])
        self.log(f"Starting server with: {' '.join(command)}")
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")
        self.console_command_var.set("")
        self.server_start_time = time.time()
        self.stop_requested = False
        self.chart_history = [0] * 12
        self.chart_activity = 60
        self.chart_last_activity = time.time()
        self.server_banner_var.set("Server is starting...")
        self.server_state_var.set("Server starting...")
        self.server_status_label.config(text="Starting", foreground="#f59e0b")
        self.status_var.set("Starting server")
        self.last_action_var.set("Starting server")
        self.server_process = subprocess.Popen(
            command,
            cwd=str(server_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=False,
            bufsize=1,
            creationflags=0,
        )
        self.monitor_thread = threading.Thread(target=self.monitor_output, daemon=True)
        self.monitor_thread.start()
        self.root.after(500, self.refresh_server_live_state)
        self.update_status_summary()

    def refresh_server_live_state(self):
        if not self.server_process or self.server_process.poll() is not None:
            return

        current_state = self.server_state_var.get()
        if current_state not in ("Server starting...", "Server restarting..."):
            return

        if time.time() - self.server_start_time >= 3:
            self.server_banner_var.set("Server is online and ready")
            self.server_status_label.config(text="Running", foreground="#16a34a")
            self.server_state_var.set("Server running")
            self.status_var.set("Server running")
            self.last_action_var.set(
                "Server started" if current_state == "Server starting..." else "Server restarted"
            )
            self.update_status_summary()
        else:
            self.root.after(500, self.refresh_server_live_state)

    def stop_server(self):
        self.stop_requested = True
        if self.server_process and self.server_process.poll() is None:
            try:
                if self.server_process.stdin:
                    self.server_process.stdin.write(("say §6[Server] §cServer is shutting down now!§r\n").encode("utf-8"))
                    self.server_process.stdin.flush()
            except Exception:
                pass
            self.server_banner_var.set("Server is shutting down")
            self.server_status_label.config(text="Stopping", foreground="#f97316")
            self.server_state_var.set("Server stopping...")
            self.status_var.set("Stopping server")
            self.last_action_var.set("Stopping server")
            self.log("Server shutdown requested. A final message was sent to the server.")
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log("Server did not exit in time. Forcing termination.")
                self.server_process.kill()
                self.server_process.wait(timeout=5)
            finally:
                self.server_process = None
                self.server_start_time = None
            self.log("Server stopped.")
            self.server_banner_var.set("Server is offline")
            self.server_status_label.config(text="Stopped", foreground="#d9534f")
            self.server_state_var.set("Server stopped")
            self.status_var.set("Server stopped")
            self.last_action_var.set("Server stopped")
            self.update_status_summary()
        else:
            self.log("No running server to stop.")

    def restart_server(self):
        self.stop_requested = True
        self.server_banner_var.set("Server is restarting...")
        self.server_status_label.config(text="Restarting", foreground="#a855f7")
        self.server_state_var.set("Server restarting...")
        self.status_var.set("Restarting server")
        self.last_action_var.set("Restarting server")
        self.update_status_summary()
        self.stop_server()
        self.start_server()

    def decode_output(self, raw_bytes):
        encodings = ("utf-8", "cp850", "cp437", "cp1252", "latin-1")
        for encoding in encodings:
            try:
                decoded = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                decoded = None
        if decoded is None:
            decoded = raw_bytes.decode("utf-8", errors="replace")

        decoded = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", decoded)
        decoded = "".join(
            char for char in decoded
            if char in "\n\r\t" or unicodedata.category(char) not in {"Cc", "Cs", "Co", "Cn"}
        )
        return decoded

    def monitor_output(self):
        if not self.server_process or not self.server_process.stdout:
            return
        for raw_line in iter(lambda: self.server_process.stdout.readline(), b""):
            decoded_line = self.decode_output(raw_line)
            if decoded_line:
                self.log(decoded_line.rstrip("\n"))
        try:
            self.server_process.stdout.close()
        except Exception:
            pass

        crashed = self.server_process is not None and self.server_process.poll() is not None
        self.server_process = None
        self.server_start_time = None
        self.server_banner_var.set("Server is offline")
        self.server_status_label.config(text="Stopped", foreground="#d9534f")
        self.server_state_var.set("Server stopped")
        self.status_var.set("Server stopped")
        self.last_action_var.set("Server stopped")
        self.chart_activity = max(0, self.chart_activity - 15)
        self.chart_last_activity = time.time()
        if self.auto_restart_enabled and not self.stop_requested and crashed:
            self.log("Server exited unexpectedly. Auto-restart is enabled.")
            self.root.after(500, self.start_server)
        self.update_status_summary()

    def send_console_command(self):
        command = self.console_command_var.get().strip()
        if not command:
            return
        if not self.server_process or self.server_process.poll() is not None or not self.server_process.stdin:
            messagebox.showwarning("Server not running", "Start the server before sending commands.")
            return
        try:
            self.server_process.stdin.write((command + "\n").encode("utf-8"))
            self.server_process.stdin.flush()
            self.log(f"> {command}")
            self.console_command_var.set("")
        except Exception as exc:
            self.log(f"Command failed: {exc}")

    def log(self, message):
        self.ensure_log_file()
        self.write_log_entry(message)
        player_match = re.search(r'(\d+)\s*/\s*(\d+)\s*players?', message, re.IGNORECASE)
        if player_match:
            self.player_count = int(player_match.group(1))
        self.chart_last_activity = time.time()
        self.chart_activity = min(100, self.chart_activity + 6)
        if hasattr(self, 'console'):
            self.console.configure(state="normal")
            self.console.insert(tk.END, f"{message}\n")
            self.console.see(tk.END)
            self.console.configure(state="disabled")

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")

    def save_log_file(self):
        if not hasattr(self, 'console'):
            return
        log_content = self.console.get("1.0", tk.END)
        file_path = filedialog.asksaveasfilename(
            title="Save log",
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            Path(file_path).write_text(log_content, encoding="utf-8")
            self.last_action_var.set("Log saved")


if __name__ == "__main__":
    if HAVE_DND and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
    else:
        root = tk.Tk()
    app = MinecraftServerManager(root)
    root.mainloop()
