"""
Advanced Task Scheduler — A full-featured desktop task automation tool.

Features:
  - Multiple task queue with add / edit / delete / run-now
  - Repeat options: Once, Hourly, Daily, Weekly, Every X Minutes
  - System tray minimize (pystray)
  - Versioned backups with timestamps
  - Desktop toast notifications (plyer)
  - Disk space check before copy
  - Drag & drop files/folders onto entry fields (tkinterdnd2)
  - Thread-safe UI, file logging, input validation
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import shutil
import os

import uuid
import schedule
import time
import threading
import logging
from datetime import datetime
from dataclasses import dataclass, field
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

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ---------------------------------------------------------------------------
#                              LOGGING
# ---------------------------------------------------------------------------
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#                            COLOUR PALETTE
# ---------------------------------------------------------------------------
BG          = "#0F1923"
SURFACE     = "#1A2735"
CARD        = "#213243"
PRIMARY     = "#00E676"   # Green
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

# ---------------------------------------------------------------------------
#                           CONSTANTS
# ---------------------------------------------------------------------------

SCHEDULE_TYPES = ["Once", "Daily", "Hourly", "Weekly", "Every X Minutes"]
TASK_TYPES = ["File Copy", "Folder Backup"]
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
    versioned: bool = False
    enabled: bool = True

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
        return True, 0, 0  # If we can't check, proceed anyway


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


def create_tray_icon_image():
    """Programmatically create a 64×64 tray icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle background
    draw.ellipse([4, 4, 60, 60], fill="#00E676")
    # Clock hands
    draw.line([32, 32, 32, 14], fill="white", width=3)
    draw.line([32, 32, 44, 32], fill="white", width=3)
    # Center dot
    draw.ellipse([29, 29, 35, 35], fill="white")
    return img


# ---------------------------------------------------------------------------
#                     ADD / EDIT TASK DIALOG
# ---------------------------------------------------------------------------

class TaskDialog:
    """Modal dialog for adding or editing a task."""

    def __init__(self, parent, title="Add New Task", task: Optional[TaskConfig] = None):
        self.result: Optional[TaskConfig] = None
        self.task = task or TaskConfig()

        # Create toplevel
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("500x620")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        self._build()
        self._populate()
        parent.wait_window(self.win)

    def _build(self):
        pad = {"padx": 20, "pady": (8, 0)}

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
        type_menu = tk.OptionMenu(frame, self.type_var, *TASK_TYPES)
        self._style_menu(type_menu)
        type_menu.pack(fill="x", pady=3)

        # Source
        self._label(frame, "Source Path:")
        src_frame = tk.Frame(frame, bg=CARD)
        src_frame.pack(fill="x", pady=3)
        self.src_entry = self._entry(src_frame, pack=False)
        self.src_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._small_btn(src_frame, "Browse", self._browse_src).pack(side="right", padx=(6, 0))

        # Enable drag & drop on source entry
        if HAS_DND:
            self.src_entry.drop_target_register(DND_FILES)
            self.src_entry.dnd_bind("<<Drop>>", lambda e: self._on_drop(e, self.src_entry))

        # Destination
        self._label(frame, "Destination Path:")
        dest_frame = tk.Frame(frame, bg=CARD)
        dest_frame.pack(fill="x", pady=3)
        self.dest_entry = self._entry(dest_frame, pack=False)
        self.dest_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._small_btn(dest_frame, "Browse", self._browse_dest).pack(side="right", padx=(6, 0))

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

        # Versioned toggle
        self.versioned_var = tk.BooleanVar(value=self.task.versioned)
        tk.Checkbutton(frame, text="  Versioned Backups (timestamped folders)",
                       variable=self.versioned_var, bg=CARD, fg=AMBER,
                       selectcolor=ENTRY_BG, activebackground=CARD,
                       activeforeground=AMBER, font=("Arial", 9, "bold")
                       ).pack(anchor="w", pady=(10, 0))

        # Buttons
        btn_bar = tk.Frame(self.win, bg=BG)
        btn_bar.pack(pady=14)
        self._action_btn(btn_bar, "💾  Save", PRIMARY, PRIMARY_DK, self._save).pack(side="left", padx=8)
        self._action_btn(btn_bar, "Cancel", DANGER, DANGER_DK, self.win.destroy).pack(side="left", padx=8)

        # Show/hide conditional fields
        self._on_sched_change(self.sched_var.get())

    def _populate(self):
        self.name_entry.insert(0, self.task.name)
        self.src_entry.insert(0, self.task.source)
        self.dest_entry.insert(0, self.task.destination)
        self.hour_e.insert(0, self.task.time_hour)
        self.min_e.insert(0, self.task.time_minute)
        self.interval_e.insert(0, str(self.task.interval_minutes))

    def _on_sched_change(self, val):
        # Time row: hide for "Hourly" and "Every X Minutes"
        if val in ("Hourly", "Every X Minutes"):
            self.time_frame.pack_forget()
        else:
            self.time_frame.pack(fill="x", pady=3)

        # Days row: show only for "Weekly"
        if val == "Weekly":
            self.days_frame.pack(fill="x", pady=3)
        else:
            self.days_frame.pack_forget()

        # Interval row: show only for "Every X Minutes"
        if val == "Every X Minutes":
            self.interval_frame.pack(fill="x", pady=3)
        else:
            self.interval_frame.pack_forget()

    def _save(self):
        name = self.name_entry.get().strip()
        src = self.src_entry.get().strip()
        dest = self.dest_entry.get().strip()
        sched = self.sched_var.get()

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
        if not os.path.isdir(dest):
            messagebox.showwarning("Validation", f"Destination folder does not exist:\n{dest}", parent=self.win)
            return

        task_type = self.type_var.get()
        if task_type == "File Copy" and not os.path.isfile(src):
            messagebox.showwarning("Validation", "Source must be a file for 'File Copy'.", parent=self.win)
            return
        if task_type == "Folder Backup" and not os.path.isdir(src):
            messagebox.showwarning("Validation", "Source must be a folder for 'Folder Backup'.", parent=self.win)
            return

        # Time validation (skip for hourly / every-x-min)
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

        # Build result
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
            versioned=self.versioned_var.get(),
            enabled=self.task.enabled,
        )
        self.win.destroy()

    # ---- Browse / DnD helpers ----

    def _browse_src(self):
        if self.type_var.get() == "File Copy":
            path = filedialog.askopenfilename(parent=self.win)
        else:
            path = filedialog.askdirectory(parent=self.win)
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
        # tkdnd wraps paths with spaces in braces
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
    """Main application window with all 8 advanced features."""

    def __init__(self, root):
        self.root = root
        self.tasks: list[TaskConfig] = []
        self.jobs: dict[str, list] = {}  # task_id -> [schedule.Job, ...]
        self.tray_icon = None
        self._hidden = False

        self._build_ui()
        self._load_tasks()
        self._start_scheduler_thread()
        logger.info("Application started.")

    # ================================================================== #
    #                          UI BUILD                                  #
    # ================================================================== #

    def _build_ui(self):
        self.root.title("Task Scheduler")
        self.root.geometry("680x780")
        self.root.minsize(620, 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ------- Title -------
        hdr = tk.Frame(self.root, bg=SURFACE, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⏰", font=("Segoe UI Emoji", 22), bg=SURFACE, fg=TEXT
                 ).pack(side="left", padx=(20, 8))
        tk.Label(hdr, text="TASK SCHEDULER", font=("Helvetica", 18, "bold"),
                 bg=SURFACE, fg=TEXT).pack(side="left")

        # ------- Toolbar -------
        tb = tk.Frame(self.root, bg=BG, pady=8)
        tb.pack(fill="x", padx=16)
        self._toolbar_btn(tb, "➕  Add Task", PRIMARY, PRIMARY_DK, self._add_task).pack(side="left", padx=4)
        self._toolbar_btn(tb, "▶  Start All", ACCENT, ACCENT_DK, self._start_all).pack(side="left", padx=4)
        self._toolbar_btn(tb, "■  Stop All", DANGER, DANGER_DK, self._stop_all).pack(side="left", padx=4)
        if HAS_TRAY:
            self._toolbar_btn(tb, "🔽  Tray", "#546E7A", "#455A64", self._minimize_to_tray
                              ).pack(side="right", padx=4)

        # ------- Task Table (Treeview) -------
        tree_frame = tk.Frame(self.root, bg=BG)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Task.Treeview",
                        background=TREEVIEW_BG, foreground=TREEVIEW_FG,
                        fieldbackground=TREEVIEW_BG, rowheight=30,
                        font=("Arial", 10))
        style.configure("Task.Treeview.Heading",
                        background=HEADER_BG, foreground=TEXT,
                        font=("Arial", 10, "bold"), relief="flat")
        style.map("Task.Treeview",
                  background=[("selected", TREEVIEW_SEL)],
                  foreground=[("selected", TEXT)])

        cols = ("name", "type", "schedule", "versioned", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                 style="Task.Treeview", selectmode="browse")
        self.tree.heading("name", text="Task Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("schedule", text="Schedule")
        self.tree.heading("versioned", text="Versioned")
        self.tree.heading("status", text="Status")

        self.tree.column("name", width=160, minwidth=100)
        self.tree.column("type", width=100, minwidth=80)
        self.tree.column("schedule", width=200, minwidth=120)
        self.tree.column("versioned", width=80, minwidth=60, anchor="center")
        self.tree.column("status", width=80, minwidth=60, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
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
        log_lbl = tk.Frame(self.root, bg=BG)
        log_lbl.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(log_lbl, text="Task History", font=("Arial", 10, "bold"),
                 bg=BG, fg=TEXT_SEC).pack(anchor="w")

        log_frame = tk.Frame(self.root, bg=LOG_BG, bd=0)
        log_frame.pack(fill="x", padx=16, pady=(2, 8))
        self.log_text = tk.Text(log_frame, height=7, bg=LOG_BG, fg=TEXT_SEC,
                                font=("Consolas", 9), relief="flat", state="disabled",
                                wrap="word", padx=8, pady=6)
        self.log_text.pack(fill="x")

        # ------- Status Bar -------
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Frame(self.root, bg=SURFACE, pady=6)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, textvariable=self.status_var, font=("Arial", 9),
                 bg=SURFACE, fg=AMBER).pack(side="left", padx=16)
        tk.Label(status_bar, text="Built with Python & Tkinter",
                 font=("Arial", 8, "italic"), bg=SURFACE, fg="#37474F"
                 ).pack(side="right", padx=16)

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
            status = "Active" if (t.enabled and t.id in self.jobs) else (
                "Enabled" if t.enabled else "Disabled")
            if t.enabled and t.id in self.jobs:
                active_count += 1
            self.tree.insert("", "end", iid=t.id, values=(
                t.name, t.task_type, t.display_schedule(),
                "Yes" if t.versioned else "No", status))
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
            # Unschedule old
            self._unschedule_task(task.id)
            # Replace in list
            for i, t in enumerate(self.tasks):
                if t.id == task.id:
                    self.tasks[i] = dlg.result
                    break
            # Re-schedule
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
            self._append_log(f"✅ Enabled '{task.name}'")
        else:
            self._unschedule_task(task.id)
            self._append_log(f"⏸ Disabled '{task.name}'")
        self._save_and_refresh()

    def _run_selected_now(self):
        task = self._get_selected_task()
        if not task:
            return
        self._append_log(f"🚀 Running '{task.name}' now...")
        threading.Thread(target=self._perform_task, args=(task,), daemon=True).start()

    def _save_and_refresh(self):
        self._refresh_tree()

    # ================================================================== #
    #                     SCHEDULING ENGINE                               #
    # ================================================================== #

    def _schedule_task(self, task: TaskConfig):
        if not task.enabled:
            return
        self._unschedule_task(task.id)  # clear old jobs first

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
        """Execute the actual file copy / folder backup. Runs in background thread."""
        is_file = task.task_type == "File Copy"

        # --- Disk space check ---
        has_space, needed, available = check_disk_space(task.source, task.destination, is_file)
        if not has_space:
            err = (f"Not enough disk space for '{task.name}'!\n"
                   f"Needed: {format_bytes(needed)} | Available: {format_bytes(available)}")
            logger.warning(err)
            self.root.after(0, lambda: self._append_log(f"⚠️ {err}"))
            send_notification("Disk Space Warning", err)
            return

        try:
            if is_file:
                # File copy
                if task.versioned:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    base = os.path.splitext(os.path.basename(task.source))
                    versioned_name = f"{base[0]}_{ts}{base[1]}"
                    final_dest = os.path.join(task.destination, versioned_name)
                    shutil.copy2(task.source, final_dest)
                    msg = f"File copied → {final_dest}"
                else:
                    shutil.copy2(task.source, task.destination)
                    msg = f"File copied → {task.destination}"
            else:
                # Folder backup
                folder_name = os.path.basename(task.source)
                if task.versioned:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    folder_name = f"{folder_name}_{ts}"
                final_dest = os.path.join(task.destination, folder_name)
                shutil.copytree(task.source, final_dest, dirs_exist_ok=True)
                msg = f"Backup created → {final_dest}"

            logger.info(f"[{task.name}] {msg}")
            self.root.after(0, lambda: self._append_log(f"✅ [{task.name}] {msg}"))
            self.root.after(0, lambda: self.status_var.set(f"Last: {task.name} ✓"))
            send_notification(f"✅ {task.name}", msg)

        except Exception as e:
            err = f"[{task.name}] Failed: {e}"
            logger.error(err)
            self.root.after(0, lambda: self._append_log(f"❌ {err}"))
            send_notification(f"❌ {task.name}", str(e))

    def _load_tasks(self):
        self.tasks = []
        self._refresh_tree()

    # ================================================================== #
    #                      SYSTEM TRAY                                   #
    # ================================================================== #

    def _minimize_to_tray(self):
        if not HAS_TRAY:
            return
        self.root.withdraw()
        self._hidden = True

        icon_img = create_tray_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._restore_from_tray, default=True),
            pystray.MenuItem("Start All", lambda: self.root.after(0, self._start_all)),
            pystray.MenuItem("Stop All", lambda: self.root.after(0, self._stop_all)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._tray_exit),
        )
        self.tray_icon = pystray.Icon("TaskScheduler", icon_img,
                                       "Task Scheduler", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        send_notification("Task Scheduler", "Minimized to system tray")
        logger.info("Minimized to system tray")

    def _restore_from_tray(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after(0, self.root.deiconify)
        self._hidden = False

    def _tray_exit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self._on_close)

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
