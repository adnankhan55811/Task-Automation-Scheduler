"""
Advanced Task Scheduler — A full-featured desktop task automation tool.

Features:
  - Multiple task queue with add / edit / delete / run-now
  - Operations: File Copy, Folder Backup, Move File
  - Repeat options: Once, Hourly, Daily, Weekly, Every X Minutes
  - Dark / Light theme toggle
  - Disk space check before copy
  - Drag & drop files/folders onto entry fields (tkinterdnd2)
  - Config persistence (config.json)
  - Desktop toast notifications (plyer)
  - Thread-safe UI, file logging, input validation
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import shutil
import os
import json
import uuid
import schedule
import time
import threading
import logging

from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

# --- Optional imports (graceful fallback) ---
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    from plyer import notification as desktop_notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

# ---------------------------------------------------------------------------
#                              LOGGING
# ---------------------------------------------------------------------------
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.log")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#                            THEME SYSTEM
# ---------------------------------------------------------------------------

THEMES = {
    "dark": {
        "BG": "#0F1923",
        "SURFACE": "#1A2735",
        "CARD": "#213243",
        "PRIMARY": "#00E676",
        "PRIMARY_DK": "#00C853",
        "DANGER": "#FF5252",
        "DANGER_DK": "#D32F2F",
        "ACCENT": "#448AFF",
        "ACCENT_DK": "#2979FF",
        "AMBER": "#FFD740",
        "TEXT": "#ECEFF1",
        "TEXT_SEC": "#78909C",
        "ENTRY_BG": "#263545",
        "ENTRY_FG": "#ECEFF1",
        "LOG_BG": "#0D1520",
        "TREEVIEW_BG": "#162230",
        "TREEVIEW_FG": "#CFD8DC",
        "TREEVIEW_SEL": "#1B3A4D",
        "HEADER_BG": "#1E3045",
    },
    "light": {
        "BG": "#EFF1F5",
        "SURFACE": "#FFFFFF",
        "CARD": "#FFFFFF",
        "PRIMARY": "#00C853",
        "PRIMARY_DK": "#009624",
        "DANGER": "#E53935",
        "DANGER_DK": "#C62828",
        "ACCENT": "#1E88E5",
        "ACCENT_DK": "#1565C0",
        "AMBER": "#E65100",
        "TEXT": "#1A1A2E",
        "TEXT_SEC": "#546E7A",
        "ENTRY_BG": "#DEE2E8",
        "ENTRY_FG": "#1A1A2E",
        "LOG_BG": "#F5F7FA",
        "TREEVIEW_BG": "#FFFFFF",
        "TREEVIEW_FG": "#37474F",
        "TREEVIEW_SEL": "#BBDEFB",
        "HEADER_BG": "#E3F2FD",
    },
}

# Active colour variables — initialised from the dark theme.
BG          = "#0F1923"
SURFACE     = "#1A2735"
CARD        = "#213243"
PRIMARY     = "#00E676"
PRIMARY_DK  = "#00C853"
DANGER      = "#FF5252"
DANGER_DK   = "#D32F2F"
ACCENT      = "#448AFF"
ACCENT_DK   = "#2979FF"
AMBER       = "#FFD740"
TEXT        = "#ECEFF1"
TEXT_SEC    = "#78909C"
ENTRY_BG    = "#263545"
ENTRY_FG    = "#ECEFF1"
LOG_BG      = "#0D1520"
TREEVIEW_BG = "#162230"
TREEVIEW_FG = "#CFD8DC"
TREEVIEW_SEL = "#1B3A4D"
HEADER_BG   = "#1E3045"


def _apply_global_theme(name: str):
    """Update all module-level colour variables to match the given theme."""
    global BG, SURFACE, CARD, PRIMARY, PRIMARY_DK, DANGER, DANGER_DK
    global ACCENT, ACCENT_DK, AMBER, TEXT, TEXT_SEC
    global ENTRY_BG, ENTRY_FG, LOG_BG, TREEVIEW_BG, TREEVIEW_FG
    global TREEVIEW_SEL, HEADER_BG

    t = THEMES.get(name, THEMES["dark"])
    BG          = t["BG"]
    SURFACE     = t["SURFACE"]
    CARD        = t["CARD"]
    PRIMARY     = t["PRIMARY"]
    PRIMARY_DK  = t["PRIMARY_DK"]
    DANGER      = t["DANGER"]
    DANGER_DK   = t["DANGER_DK"]
    ACCENT      = t["ACCENT"]
    ACCENT_DK   = t["ACCENT_DK"]
    AMBER       = t["AMBER"]
    TEXT        = t["TEXT"]
    TEXT_SEC    = t["TEXT_SEC"]
    ENTRY_BG    = t["ENTRY_BG"]
    ENTRY_FG    = t["ENTRY_FG"]
    LOG_BG      = t["LOG_BG"]
    TREEVIEW_BG = t["TREEVIEW_BG"]
    TREEVIEW_FG = t["TREEVIEW_FG"]
    TREEVIEW_SEL = t["TREEVIEW_SEL"]
    HEADER_BG   = t["HEADER_BG"]


# ---------------------------------------------------------------------------
#                           CONSTANTS
# ---------------------------------------------------------------------------

SCHEDULE_TYPES = ["Once", "Daily", "Hourly", "Weekly", "Every X Minutes"]
TASK_TYPES = ["File Copy", "Folder Backup", "Move File"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_MAP = {
    "Mon": "monday", "Tue": "tuesday", "Wed": "wednesday",
    "Thu": "thursday", "Fri": "friday", "Sat": "saturday", "Sun": "sunday",
}

# ---------------------------------------------------------------------------
#                           DATA MODEL
# ---------------------------------------------------------------------------

@dataclass
class TaskConfig:
    id: str = ""
    name: str = ""
    task_type: str = "File Copy"
    source: str = ""
    destination: str = ""
    schedule_type: str = "Daily"
    time_hour: str = "12"
    time_minute: str = "00"
    time_ampm: str = "AM"
    weekly_days: list = field(default_factory=lambda: ["Mon"])
    interval_minutes: int = 30
    enabled: bool = True  # False = paused

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:8]

    def display_schedule(self) -> str:
        if self.schedule_type == "Daily":
            return f"Daily @ {self.time_hour}:{self.time_minute} {self.time_ampm}"
        elif self.schedule_type == "Hourly":
            return "Every hour"
        elif self.schedule_type == "Weekly":
            days = ",".join(self.weekly_days)
            return f"Weekly ({days}) @ {self.time_hour}:{self.time_minute} {self.time_ampm}"
        elif self.schedule_type == "Every X Minutes":
            return f"Every {self.interval_minutes} min"
        elif self.schedule_type == "Once":
            return f"Once @ {self.time_hour}:{self.time_minute} {self.time_ampm}"
        return self.schedule_type

    def get_24hr_time(self) -> str:
        time_input = f"{self.time_hour}:{self.time_minute} {self.time_ampm}"
        t_struct = time.strptime(time_input, "%I:%M %p")
        return time.strftime("%H:%M", t_struct)


# ---------------------------------------------------------------------------
#                       UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def get_folder_size(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def check_disk_space(source: str, dest: str, is_file: bool) -> tuple:
    """Returns (has_space: bool, needed: int, available: int)."""
    try:
        if is_file:
            needed = os.path.getsize(source)
        else:
            needed = get_folder_size(source)
        usage = shutil.disk_usage(dest)
        return usage.free >= needed, needed, usage.free
    except Exception:
        return True, 0, 0


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def send_notification(title: str, message: str):
    if HAS_PLYER:
        try:
            desktop_notification.notify(
                title=title,
                message=message,
                app_name="Task Scheduler",
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"Notification failed: {e}")


# ---------------------------------------------------------------------------
#                     ADD / EDIT TASK DIALOG
# ---------------------------------------------------------------------------

class TaskDialog:
    """Modal dialog for adding or editing a task."""

    def __init__(self, parent, title="Add New Task", task: Optional[TaskConfig] = None):
        self.result: Optional[TaskConfig] = None
        self.task = task or TaskConfig()

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("500x560")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        self._build()
        self._populate()
        parent.wait_window(self.win)

    def _build(self):
        # Title
        tk.Label(self.win, text="📝", font=("Segoe UI Emoji", 18), bg=BG, fg=TEXT
                 ).pack(pady=(18, 0))

        frame = tk.Frame(self.win, bg=CARD, bd=0, padx=20, pady=16)
        frame.pack(padx=20, pady=10, fill="both", expand=True)

        # Task Name
        self._label(frame, "Task Name:")
        self.name_entry = self._entry(frame)

        # Operation
        self._label(frame, "Operation:")
        self.type_var = tk.StringVar(value=self.task.task_type)
        type_menu = tk.OptionMenu(frame, self.type_var, *TASK_TYPES,
                                  command=self._on_type_change)
        self._style_menu(type_menu)
        type_menu.pack(fill="x", pady=3)

        # Source
        self.src_label = tk.Label(frame, text="Source Path:", font=("Arial", 9, "bold"),
                                  bg=CARD, fg=TEXT)
        self.src_label.pack(anchor="w", pady=(8, 0))
        src_frame = tk.Frame(frame, bg=CARD)
        src_frame.pack(fill="x", pady=3)
        self.src_entry = self._entry(src_frame, pack=False)
        self.src_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.src_browse_btn = self._small_btn(src_frame, "Browse", self._browse_src)
        self.src_browse_btn.pack(side="right", padx=(6, 0))

        # Enable drag & drop on source entry
        if HAS_DND:
            self.src_entry.drop_target_register(DND_FILES)
            self.src_entry.dnd_bind("<<Drop>>", lambda e: self._on_drop(e, self.src_entry))

        # Destination
        self.dest_label = tk.Label(frame, text="Destination Path:", font=("Arial", 9, "bold"),
                                   bg=CARD, fg=TEXT)
        self.dest_label.pack(anchor="w", pady=(8, 0))
        self.dest_frame = tk.Frame(frame, bg=CARD)
        self.dest_frame.pack(fill="x", pady=3)
        self.dest_entry = self._entry(self.dest_frame, pack=False)
        self.dest_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.dest_browse_btn = self._small_btn(self.dest_frame, "Browse", self._browse_dest)
        self.dest_browse_btn.pack(side="right", padx=(6, 0))

        if HAS_DND:
            self.dest_entry.drop_target_register(DND_FILES)
            self.dest_entry.dnd_bind("<<Drop>>", lambda e: self._on_drop(e, self.dest_entry))

        # Schedule Type
        self._label(frame, "Schedule:")
        self.sched_var = tk.StringVar(value=self.task.schedule_type)
        sched_menu = tk.OptionMenu(frame, self.sched_var, *SCHEDULE_TYPES,
                                   command=self._on_sched_change)
        self._style_menu(sched_menu)
        sched_menu.pack(fill="x", pady=3)

        # Time row
        self.time_frame = tk.Frame(frame, bg=CARD)
        self.time_frame.pack(fill="x", pady=3)
        tk.Label(self.time_frame, text="Time:", font=("Arial", 9, "bold"),
                 bg=CARD, fg=TEXT_SEC).pack(side="left")
        self.hour_e = tk.Entry(self.time_frame, width=3, font=("Arial", 13, "bold"),
                               justify="center", bg=ENTRY_BG, fg=ENTRY_FG,
                               insertbackground=ENTRY_FG, relief="flat")
        self.hour_e.pack(side="left", padx=4)
        tk.Label(self.time_frame, text=":", font=("Arial", 13, "bold"),
                 bg=CARD, fg=TEXT).pack(side="left")
        self.min_e = tk.Entry(self.time_frame, width=3, font=("Arial", 13, "bold"),
                              justify="center", bg=ENTRY_BG, fg=ENTRY_FG,
                              insertbackground=ENTRY_FG, relief="flat")
        self.min_e.pack(side="left", padx=4)
        self.ampm_var = tk.StringVar(value=self.task.time_ampm)
        ampm = tk.OptionMenu(self.time_frame, self.ampm_var, "AM", "PM")
        self._style_menu(ampm)
        ampm.pack(side="left", padx=6)

        # Weekly days row
        self.days_frame = tk.Frame(frame, bg=CARD)
        self.days_frame.pack(fill="x", pady=3)
        tk.Label(self.days_frame, text="Days:", font=("Arial", 9, "bold"),
                 bg=CARD, fg=TEXT_SEC).pack(side="left")
        self.day_vars = {}
        for d in WEEKDAYS:
            var = tk.BooleanVar(value=d in self.task.weekly_days)
            self.day_vars[d] = var
            cb = tk.Checkbutton(self.days_frame, text=d, variable=var,
                                bg=CARD, fg=TEXT, selectcolor=ENTRY_BG,
                                activebackground=CARD, activeforeground=TEXT,
                                font=("Arial", 8))
            cb.pack(side="left", padx=2)

        # Interval row
        self.interval_frame = tk.Frame(frame, bg=CARD)
        self.interval_frame.pack(fill="x", pady=3)
        tk.Label(self.interval_frame, text="Every", font=("Arial", 9, "bold"),
                 bg=CARD, fg=TEXT_SEC).pack(side="left")
        self.interval_e = tk.Entry(self.interval_frame, width=5, font=("Arial", 11),
                                   justify="center", bg=ENTRY_BG, fg=ENTRY_FG,
                                   insertbackground=ENTRY_FG, relief="flat")
        self.interval_e.pack(side="left", padx=6)
        tk.Label(self.interval_frame, text="minutes", font=("Arial", 9),
                 bg=CARD, fg=TEXT_SEC).pack(side="left")

        # Buttons
        btn_bar = tk.Frame(self.win, bg=BG)
        btn_bar.pack(pady=14)
        self._action_btn(btn_bar, "💾  Save", PRIMARY, PRIMARY_DK, self._save).pack(side="left", padx=8)
        self._action_btn(btn_bar, "Cancel", DANGER, DANGER_DK, self.win.destroy).pack(side="left", padx=8)

        # Show/hide conditional fields
        self._on_sched_change(self.sched_var.get())
        self._on_type_change(self.type_var.get())

    def _populate(self):
        self.name_entry.insert(0, self.task.name)
        self.src_entry.insert(0, self.task.source)
        self.dest_entry.insert(0, self.task.destination)
        self.hour_e.insert(0, self.task.time_hour)
        self.min_e.insert(0, self.task.time_minute)
        self.interval_e.insert(0, str(self.task.interval_minutes))

    def _on_type_change(self, val):
        """Adapt field labels and visibility based on the selected operation type."""
        if val == "Move File":
            self.src_label.config(text="Source File:")
            self.src_browse_btn.pack(side="right", padx=(6, 0))
            self.dest_label.config(text="Move To Folder:")
        elif val == "Folder Backup":
            self.src_label.config(text="Source Folder:")
            self.src_browse_btn.pack(side="right", padx=(6, 0))
            self.dest_label.config(text="Backup To:")
        else:  # File Copy
            self.src_label.config(text="Source File:")
            self.src_browse_btn.pack(side="right", padx=(6, 0))
            self.dest_label.config(text="Copy To Folder:")

    def _on_sched_change(self, val):
        if val in ("Hourly", "Every X Minutes"):
            self.time_frame.pack_forget()
        else:
            self.time_frame.pack(fill="x", pady=3)

        if val == "Weekly":
            self.days_frame.pack(fill="x", pady=3)
        else:
            self.days_frame.pack_forget()

        if val == "Every X Minutes":
            self.interval_frame.pack(fill="x", pady=3)
        else:
            self.interval_frame.pack_forget()

    def _save(self):
        name = self.name_entry.get().strip()
        src = self.src_entry.get().strip()
        dest = self.dest_entry.get().strip()
        sched = self.sched_var.get()
        task_type = self.type_var.get()

        # --- Validation ---
        if not name:
            messagebox.showwarning("Validation", "Task name is required.", parent=self.win)
            return
        if not src:
            messagebox.showwarning("Validation", "Source path is required.", parent=self.win)
            return

        if not dest:
            messagebox.showwarning("Validation", "Destination path is required.", parent=self.win)
            return

        if not os.path.exists(src):
            messagebox.showwarning("Validation", f"Source does not exist:\n{src}", parent=self.win)
            return

        if task_type == "File Copy" and src and os.path.exists(src) and not os.path.isfile(src):
            messagebox.showwarning("Validation", "Source must be a file for 'File Copy'.", parent=self.win)
            return
        if task_type == "Move File" and src and os.path.exists(src) and not os.path.isfile(src):
            messagebox.showwarning("Validation", "Source must be a file for 'Move File'.", parent=self.win)
            return
        if task_type == "Folder Backup" and src and os.path.exists(src) and not os.path.isdir(src):
            messagebox.showwarning("Validation", "Source must be a folder for 'Folder Backup'.", parent=self.win)
            return

        if dest and not os.path.isdir(dest):
            messagebox.showwarning("Validation", f"Destination folder does not exist:\n{dest}", parent=self.win)
            return

        # Time validation
        h_val, m_val = "12", "00"
        if sched not in ("Hourly", "Every X Minutes"):
            h_str = self.hour_e.get().strip()
            m_str = self.min_e.get().strip()
            try:
                h_int = int(h_str)
                m_int = int(m_str)
                if not (1 <= h_int <= 12):
                    raise ValueError("Hour must be 1–12")
                if not (0 <= m_int <= 59):
                    raise ValueError("Minute must be 0–59")
                h_val = str(h_int)
                m_val = f"{m_int:02d}"
            except ValueError as e:
                messagebox.showerror("Time Error", f"Invalid time: {e}", parent=self.win)
                return

        # Interval validation
        interval = 30
        if sched == "Every X Minutes":
            try:
                interval = int(self.interval_e.get().strip())
                if interval < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Interval Error", "Enter a positive number of minutes.", parent=self.win)
                return

        # Weekly days
        weekly = [d for d, v in self.day_vars.items() if v.get()]
        if sched == "Weekly" and not weekly:
            messagebox.showwarning("Validation", "Select at least one day for Weekly schedule.", parent=self.win)
            return

        self.result = TaskConfig(
            id=self.task.id,
            name=name,
            task_type=task_type,
            source=src,
            destination=dest,
            schedule_type=sched,
            time_hour=h_val,
            time_minute=m_val,
            time_ampm=self.ampm_var.get(),
            weekly_days=weekly,
            interval_minutes=interval,
            enabled=self.task.enabled,
        )
        self.win.destroy()

    # ---- Browse / DnD helpers ----

    def _browse_src(self):
        tt = self.type_var.get()
        if tt == "Folder Backup":
            path = filedialog.askdirectory(parent=self.win)
        else:
            path = filedialog.askopenfilename(parent=self.win)
        if path:
            self.src_entry.delete(0, tk.END)
            self.src_entry.insert(0, path)

    def _browse_dest(self):
        path = filedialog.askdirectory(parent=self.win)
        if path:
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, path)

    def _on_drop(self, event, entry_widget):
        path = event.data.strip()
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)

    # ---- Widget factories ----

    @staticmethod
    def _label(parent, text):
        tk.Label(parent, text=text, font=("Arial", 9, "bold"),
                 bg=CARD, fg=TEXT).pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _entry(parent, pack=True) -> tk.Entry:
        e = tk.Entry(parent, font=("Arial", 10), bd=0, relief="flat",
                     bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG)
        if pack:
            e.pack(fill="x", pady=3, ipady=4)
        return e

    @staticmethod
    def _style_menu(menu):
        menu.config(bg=ENTRY_BG, fg=ENTRY_FG, activebackground=ACCENT,
                    activeforeground="white", highlightthickness=0,
                    font=("Arial", 10), relief="flat")
        menu["menu"].config(bg=ENTRY_BG, fg=ENTRY_FG)

    @staticmethod
    def _small_btn(parent, text, command):
        btn = tk.Button(parent, text=text, command=command,
                        bg=ACCENT, fg="white", activebackground=ACCENT_DK,
                        font=("Arial", 8, "bold"), relief="flat",
                        cursor="hand2", bd=0, padx=10, pady=2)
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_DK))
        btn.bind("<Leave>", lambda e: btn.config(bg=ACCENT))
        return btn

    @staticmethod
    def _action_btn(parent, text, bg_c, hover_c, cmd):
        btn = tk.Button(parent, text=text, bg=bg_c, fg="white",
                        activebackground=hover_c, activeforeground="white",
                        font=("Arial", 11, "bold"), relief="flat",
                        cursor="hand2", bd=0, padx=20, pady=8, command=cmd)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_c))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg_c))
        return btn


# ---------------------------------------------------------------------------
#                      MAIN APPLICATION
# ---------------------------------------------------------------------------

class TaskSchedulerApp:
    """Main application window."""

    def __init__(self, root):
        self.root = root
        self.tasks: list[TaskConfig] = []
        self.jobs: dict[str, list] = {}   # task_id -> [schedule.Job, ...]
        self.current_theme = "dark"

        self._build_ui()
        self._load_tasks()
        self._start_scheduler_thread()
        logger.info("Application started.")

    # ================================================================== #
    #                          UI BUILD                                  #
    # ================================================================== #

    def _build_ui(self):
        self.root.title("Task Scheduler")
        self.root.geometry("720x780")
        self.root.minsize(660, 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ------- Title -------
        self.hdr_frame = tk.Frame(self.root, bg=SURFACE, pady=12)
        self.hdr_frame.pack(fill="x")
        self.hdr_icon = tk.Label(self.hdr_frame, text="⏰",
                                 font=("Segoe UI Emoji", 22), bg=SURFACE, fg=TEXT)
        self.hdr_icon.pack(side="left", padx=(20, 8))
        self.hdr_title = tk.Label(self.hdr_frame, text="TASK SCHEDULER",
                                  font=("Helvetica", 18, "bold"), bg=SURFACE, fg=TEXT)
        self.hdr_title.pack(side="left")

        # ------- Toolbar -------
        self.toolbar = tk.Frame(self.root, bg=BG, pady=8)
        self.toolbar.pack(fill="x", padx=16)

        self._toolbar_btn(self.toolbar, "➕  Add Task", PRIMARY, PRIMARY_DK,
                          self._add_task).pack(side="left", padx=4)
        self._toolbar_btn(self.toolbar, "▶  Start All", ACCENT, ACCENT_DK,
                          self._start_all).pack(side="left", padx=4)
        self._toolbar_btn(self.toolbar, "■  Stop All", DANGER, DANGER_DK,
                          self._stop_all).pack(side="left", padx=4)


        # Right-side: theme toggle
        self.theme_btn = self._toolbar_btn(self.toolbar, "☀️  Light", "#546E7A", "#455A64",
                                           self._toggle_theme)
        self.theme_btn.pack(side="right", padx=4)

        # ------- Task Table (Treeview) -------
        self.tree_frame = tk.Frame(self.root, bg=BG)
        self.tree_frame.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Task.Treeview",
                             background=TREEVIEW_BG, foreground=TREEVIEW_FG,
                             fieldbackground=TREEVIEW_BG, rowheight=30,
                             font=("Arial", 10))
        self.style.configure("Task.Treeview.Heading",
                             background=HEADER_BG, foreground=TEXT,
                             font=("Arial", 10, "bold"), relief="flat")
        self.style.map("Task.Treeview",
                       background=[("selected", TREEVIEW_SEL)],
                       foreground=[("selected", TEXT)])

        cols = ("name", "type", "schedule", "status")
        self.tree = ttk.Treeview(self.tree_frame, columns=cols, show="headings",
                                 style="Task.Treeview", selectmode="browse")
        self.tree.heading("name", text="Task Name")
        self.tree.heading("type", text="Operation")
        self.tree.heading("schedule", text="Schedule")
        self.tree.heading("status", text="Status")

        self.tree.column("name", width=180, minwidth=120)
        self.tree.column("type", width=120, minwidth=90)
        self.tree.column("schedule", width=220, minwidth=140)
        self.tree.column("status", width=100, minwidth=70, anchor="center")

        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Right-click context menu
        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                                activebackground=ACCENT, activeforeground="white",
                                font=("Arial", 10))
        self.ctx_menu.add_command(label="▶  Run Now", command=self._run_selected_now)
        self.ctx_menu.add_command(label="✏️  Edit", command=self._edit_task)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="⏸  Enable / Disable", command=self._toggle_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="🗑  Delete", command=self._delete_task)
        self.tree.bind("<Button-3>", self._show_ctx_menu)
        self.tree.bind("<Double-1>", lambda e: self._edit_task())

        # ------- Task History Log -------
        self.log_lbl_frame = tk.Frame(self.root, bg=BG)
        self.log_lbl_frame.pack(fill="x", padx=16, pady=(8, 0))
        self.log_lbl = tk.Label(self.log_lbl_frame, text="Task History",
                                font=("Arial", 10, "bold"), bg=BG, fg=TEXT_SEC)
        self.log_lbl.pack(anchor="w")

        self.log_frame = tk.Frame(self.root, bg=LOG_BG, bd=0)
        self.log_frame.pack(fill="x", padx=16, pady=(2, 8))
        self.log_text = tk.Text(self.log_frame, height=7, bg=LOG_BG, fg=TEXT_SEC,
                                font=("Consolas", 9), relief="flat", state="disabled",
                                wrap="word", padx=8, pady=6)
        self.log_text.pack(fill="x")

        # ------- Status Bar -------
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Frame(self.root, bg=SURFACE, pady=6)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(self.status_bar, textvariable=self.status_var,
                                     font=("Arial", 9), bg=SURFACE, fg=AMBER)
        self.status_label.pack(side="left", padx=16)
        self.footer_label = tk.Label(self.status_bar, text="Built with Python & Tkinter",
                                     font=("Arial", 8, "italic"), bg=SURFACE, fg="#37474F")
        self.footer_label.pack(side="right", padx=16)

    # ================================================================== #
    #                       UI HELPERS                                   #
    # ================================================================== #

    @staticmethod
    def _toolbar_btn(parent, text, bg_c, hover_c, cmd):
        btn = tk.Button(parent, text=text, bg=bg_c, fg="white",
                        activebackground=hover_c, activeforeground="white",
                        font=("Arial", 10, "bold"), relief="flat",
                        cursor="hand2", bd=0, padx=14, pady=6, command=cmd)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_c))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg_c))
        return btn

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}]  {msg}\n"
        self.log_text.config(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        active_count = 0
        for t in self.tasks:
            if not t.enabled:
                status = "⏸ Paused"
            elif t.id in self.jobs:
                status = "▶ Active"
                active_count += 1
            else:
                status = "● Idle"
            self.tree.insert("", "end", iid=t.id, values=(
                t.name, t.task_type, t.display_schedule(), status))
        self.status_var.set(f"{len(self.tasks)} tasks | {active_count} active")

    def _get_selected_task(self) -> Optional[TaskConfig]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Task", "Please select a task first.")
            return None
        task_id = sel[0]
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def _show_ctx_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.ctx_menu.tk_popup(event.x_root, event.y_root)

    # ================================================================== #
    #                    TASK CRUD OPERATIONS                             #
    # ================================================================== #

    def _add_task(self):
        dlg = TaskDialog(self.root, title="Add New Task")
        if dlg.result:
            self.tasks.append(dlg.result)
            self._schedule_task(dlg.result)
            self._save_and_refresh()
            self._append_log(f"➕ Added '{dlg.result.name}'")
            logger.info(f"Task added: {dlg.result.name}")

    def _edit_task(self):
        task = self._get_selected_task()
        if not task:
            return
        dlg = TaskDialog(self.root, title="Edit Task", task=task)
        if dlg.result:
            self._unschedule_task(task.id)
            for i, t in enumerate(self.tasks):
                if t.id == task.id:
                    self.tasks[i] = dlg.result
                    break
            if dlg.result.enabled:
                self._schedule_task(dlg.result)
            self._save_and_refresh()
            self._append_log(f"✏️ Edited '{dlg.result.name}'")
            logger.info(f"Task edited: {dlg.result.name}")

    def _delete_task(self):
        task = self._get_selected_task()
        if not task:
            return
        if not messagebox.askyesno("Delete Task", f"Delete '{task.name}'?"):
            return
        self._unschedule_task(task.id)
        self.tasks = [t for t in self.tasks if t.id != task.id]
        self._save_and_refresh()
        self._append_log(f"🗑 Deleted '{task.name}'")
        logger.info(f"Task deleted: {task.name}")

    def _toggle_selected(self):
        task = self._get_selected_task()
        if not task:
            return
        task.enabled = not task.enabled
        if task.enabled:
            self._schedule_task(task)
            self._append_log(f"▶ Resumed '{task.name}'")
        else:
            self._unschedule_task(task.id)
            self._append_log(f"⏸ Paused '{task.name}'")
        self._save_and_refresh()

    def _run_selected_now(self):
        task = self._get_selected_task()
        if not task:
            return
        self._append_log(f"🚀 Running '{task.name}' now...")
        threading.Thread(target=self._perform_task, args=(task,), daemon=True).start()

    def _save_and_refresh(self):
        self._save_tasks()
        self._refresh_tree()

    # ================================================================== #
    #                     SCHEDULING ENGINE                               #
    # ================================================================== #

    def _schedule_task(self, task: TaskConfig):
        if not task.enabled:
            return
        self._unschedule_task(task.id)

        jobs = []
        try:
            if task.schedule_type == "Daily":
                t24 = task.get_24hr_time()
                job = schedule.every().day.at(t24).do(self._perform_task, task)
                jobs.append(job)

            elif task.schedule_type == "Hourly":
                job = schedule.every().hour.do(self._perform_task, task)
                jobs.append(job)

            elif task.schedule_type == "Weekly":
                t24 = task.get_24hr_time()
                for day_name in task.weekly_days:
                    sched_day = WEEKDAY_MAP.get(day_name)
                    if sched_day:
                        job = getattr(schedule.every(), sched_day).at(t24).do(
                            self._perform_task, task)
                        jobs.append(job)

            elif task.schedule_type == "Every X Minutes":
                job = schedule.every(task.interval_minutes).minutes.do(
                    self._perform_task, task)
                jobs.append(job)

            elif task.schedule_type == "Once":
                t24 = task.get_24hr_time()
                job = schedule.every().day.at(t24).do(self._perform_once, task)
                jobs.append(job)

            if jobs:
                self.jobs[task.id] = jobs
                logger.info(f"Scheduled '{task.name}': {task.display_schedule()}")
        except Exception as e:
            logger.error(f"Scheduling error for '{task.name}': {e}")
            self.root.after(0, lambda: self._append_log(f"❌ Schedule error: {e}"))

    def _unschedule_task(self, task_id: str):
        if task_id in self.jobs:
            for job in self.jobs[task_id]:
                schedule.cancel_job(job)
            del self.jobs[task_id]

    def _start_all(self):
        count = 0
        for task in self.tasks:
            if task.enabled and task.id not in self.jobs:
                self._schedule_task(task)
                count += 1
        self._refresh_tree()
        self._append_log(f"▶ Started {count} task(s)")
        logger.info(f"Start All: {count} tasks scheduled")

    def _stop_all(self):
        ids = list(self.jobs.keys())
        for tid in ids:
            self._unschedule_task(tid)
        self._refresh_tree()
        self._append_log("■ All tasks stopped")
        logger.info("Stop All executed")

    def _perform_once(self, task: TaskConfig):
        """Run once, then auto-unschedule."""
        self._perform_task(task)
        self.root.after(0, lambda: self._unschedule_task(task.id))
        task.enabled = False
        self.root.after(0, self._save_and_refresh)
        return schedule.CancelJob

    # ================================================================== #
    #                     TASK EXECUTION                                  #
    # ================================================================== #

    def _perform_task(self, task: TaskConfig):
        """Execute the task operation. Runs in a background thread."""
        try:
            if task.task_type == "File Copy":
                self._exec_file_copy(task)

            elif task.task_type == "Folder Backup":
                self._exec_folder_backup(task)

            elif task.task_type == "Move File":
                self._exec_move_file(task)

            else:
                raise ValueError(f"Unknown task type: {task.task_type}")

        except Exception as e:
            err = f"[{task.name}] Failed: {e}"
            logger.error(err)
            self.root.after(0, lambda: self._append_log(f"❌ {err}"))
            send_notification(f"❌ {task.name}", str(e))

    # ---- Individual operation handlers ----

    def _exec_file_copy(self, task: TaskConfig):
        has_space, needed, available = check_disk_space(task.source, task.destination, True)
        if not has_space:
            self._disk_space_warning(task, needed, available)
            return
        shutil.copy2(task.source, task.destination)
        msg = f"File copied → {task.destination}"
        self._task_success(task, msg)

    def _exec_folder_backup(self, task: TaskConfig):
        has_space, needed, available = check_disk_space(task.source, task.destination, False)
        if not has_space:
            self._disk_space_warning(task, needed, available)
            return
        folder_name = os.path.basename(task.source)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        final_dest = os.path.join(task.destination, f"{folder_name}_{ts}")
        shutil.copytree(task.source, final_dest, dirs_exist_ok=True)
        msg = f"Backup created → {final_dest}"
        self._task_success(task, msg)

    def _exec_move_file(self, task: TaskConfig):
        if not os.path.isfile(task.source):
            raise FileNotFoundError(f"Source file not found: {task.source}")
        shutil.move(task.source, task.destination)
        msg = f"File moved → {task.destination}"
        self._task_success(task, msg)



    # ---- Shared result helpers ----

    def _task_success(self, task: TaskConfig, msg: str):
        logger.info(f"[{task.name}] {msg}")
        self.root.after(0, lambda: self._append_log(f"✅ [{task.name}] {msg}"))
        self.root.after(0, lambda: self.status_var.set(f"Last: {task.name} ✓"))
        send_notification(f"✅ {task.name}", msg)

    def _disk_space_warning(self, task: TaskConfig, needed: int, available: int):
        err = (f"Not enough disk space for '{task.name}'!\n"
               f"Needed: {format_bytes(needed)} | Available: {format_bytes(available)}")
        logger.warning(err)
        self.root.after(0, lambda: self._append_log(f"⚠️ {err}"))
        send_notification("Disk Space Warning", err)

    # ================================================================== #
    #               PERSISTENCE (config.json)                            #
    # ================================================================== #

    def _load_tasks(self):
        """Load tasks and theme from config.json."""
        self.tasks = []
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Load tasks
                for t_dict in data.get("tasks", []):
                    try:
                        task = TaskConfig(
                            id=t_dict.get("id", ""),
                            name=t_dict.get("name", ""),
                            task_type=t_dict.get("task_type", "File Copy"),
                            source=t_dict.get("source", ""),
                            destination=t_dict.get("destination", ""),
                            schedule_type=t_dict.get("schedule_type", "Daily"),
                            time_hour=t_dict.get("time_hour", "12"),
                            time_minute=t_dict.get("time_minute", "00"),
                            time_ampm=t_dict.get("time_ampm", "AM"),
                            weekly_days=t_dict.get("weekly_days", ["Mon"]),
                            interval_minutes=t_dict.get("interval_minutes", 30),
                            enabled=t_dict.get("enabled", True),
                        )
                        self.tasks.append(task)
                    except Exception as e:
                        logger.warning(f"Skipping malformed task entry: {e}")

                # Load theme preference
                saved_theme = data.get("theme", "dark")
                if saved_theme != self.current_theme:
                    self.current_theme = saved_theme
                    _apply_global_theme(saved_theme)
                    self._apply_theme()

                logger.info(f"Loaded {len(self.tasks)} tasks from config.json")
                self._append_log(f"📂 Loaded {len(self.tasks)} task(s) from config")
        except json.JSONDecodeError as e:
            logger.error(f"Config file is corrupted: {e}")
            self._append_log("⚠️ Config file corrupted — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

        # Schedule all enabled tasks
        for task in self.tasks:
            if task.enabled:
                self._schedule_task(task)

        self._refresh_tree()

    def _save_tasks(self):
        """Persist tasks and theme to config.json."""
        try:
            data = {
                "theme": self.current_theme,
                "tasks": [asdict(t) for t in self.tasks],
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.tasks)} tasks to config.json")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            self.root.after(0, lambda: self._append_log(f"❌ Save error: {e}"))

    # ================================================================== #
    #                    THEME SWITCHING                                  #
    # ================================================================== #

    def _toggle_theme(self):
        """Switch between dark and light themes."""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.current_theme = new_theme
        _apply_global_theme(new_theme)
        self._apply_theme()
        self._save_tasks()
        self._append_log(f"🎨 Switched to {new_theme} theme")

    def _apply_theme(self):
        """Reconfigure all widgets to match the current theme."""
        self.root.configure(bg=BG)

        # Header
        self.hdr_frame.configure(bg=SURFACE)
        self.hdr_icon.configure(bg=SURFACE, fg=TEXT)
        self.hdr_title.configure(bg=SURFACE, fg=TEXT)

        # Toolbar
        self.toolbar.configure(bg=BG)

        # Theme button label
        if self.current_theme == "dark":
            self.theme_btn.config(text="☀️  Light")
        else:
            self.theme_btn.config(text="🌙  Dark")

        # Tree frame
        self.tree_frame.configure(bg=BG)

        # Treeview style
        self.style.configure("Task.Treeview",
                             background=TREEVIEW_BG, foreground=TREEVIEW_FG,
                             fieldbackground=TREEVIEW_BG)
        self.style.configure("Task.Treeview.Heading",
                             background=HEADER_BG, foreground=TEXT)
        self.style.map("Task.Treeview",
                       background=[("selected", TREEVIEW_SEL)],
                       foreground=[("selected", TEXT)])

        # Context menu
        self.ctx_menu.configure(bg=CARD, fg=TEXT, activebackground=ACCENT)

        # Log area
        self.log_lbl_frame.configure(bg=BG)
        self.log_lbl.configure(bg=BG, fg=TEXT_SEC)
        self.log_frame.configure(bg=LOG_BG)
        self.log_text.configure(bg=LOG_BG, fg=TEXT_SEC)

        # Status bar
        self.status_bar.configure(bg=SURFACE)
        self.status_label.configure(bg=SURFACE, fg=AMBER)
        self.footer_label.configure(bg=SURFACE,
                                    fg="#546E7A" if self.current_theme == "light" else "#37474F")

    # ================================================================== #
    #                    SCHEDULER THREAD                                 #
    # ================================================================== #

    def _start_scheduler_thread(self):
        def _run():
            while True:
                schedule.run_pending()
                time.sleep(1)
        threading.Thread(target=_run, daemon=True).start()
        logger.info("Scheduler thread started.")

    def _on_close(self):
        self._save_tasks()
        logger.info("Application closed.")
        self.root.destroy()


# ======================================================================
#                            ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = TaskSchedulerApp(root)
    root.mainloop()