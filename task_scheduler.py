"""
Advanced Task Scheduler — Schedule daily file copy and folder backup operations.

Features:
  - File copy & folder backup scheduling
  - 12-hour AM/PM time picker
  - Background scheduler thread (daemon)
  - Task history log in the UI
  - Input & path validation
  - Thread-safe UI updates
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import shutil
import os
import schedule
import time
import threading
import logging
from datetime import datetime

# --- Logging Setup ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Colors & Styles ---
BG_COLOR = "#1E2A38"        # Deep navy
FRAME_COLOR = "#273647"     # Slightly lighter navy
BTN_COLOR = "#27AE60"       # Emerald green
BTN_HOVER = "#2ECC71"       # Lighter green on hover
STOP_COLOR = "#E74C3C"      # Red
STOP_HOVER = "#FF6B6B"      # Lighter red on hover
BROWSE_COLOR = "#3498DB"    # Blue
BROWSE_HOVER = "#5DADE2"    # Lighter blue on hover
TEXT_COLOR = "#ECF0F1"      # Cloud white
MUTED_COLOR = "#7F8C8D"     # Grey
ACCENT_COLOR = "#F39C12"    # Amber for status
ENTRY_BG = "#34495E"        # Entry field background
ENTRY_FG = "#ECF0F1"        # Entry field text
LOG_BG = "#1A2430"          # Log area background


class TaskSchedulerApp:
    """Main application class for the Task Scheduler."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_job = None
        self._build_ui()
        self._start_scheduler_thread()
        logger.info("Application started.")

    # ------------------------------------------------------------------ #
    #                           UI CONSTRUCTION                          #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        """Build the entire user interface."""
        self.root.title("Advanced Task Automator")
        self.root.geometry("540x750")
        self.root.minsize(480, 700)
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Title ---
        title_frame = tk.Frame(self.root, bg=BG_COLOR)
        title_frame.pack(pady=(20, 5))
        tk.Label(
            title_frame, text="⏰", font=("Segoe UI Emoji", 24),
            bg=BG_COLOR, fg=TEXT_COLOR,
        ).pack(side="left", padx=(0, 8))
        tk.Label(
            title_frame, text="TASK SCHEDULER", font=("Helvetica", 22, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR,
        ).pack(side="left")

        # --- Main Container ---
        main_frame = tk.Frame(
            self.root, bg=FRAME_COLOR, bd=0, relief="flat", padx=24, pady=20,
        )
        main_frame.pack(pady=10, padx=24, fill="both")

        # 1. Task selection
        self._section_label(main_frame, "Select Operation:")
        self.task_var = tk.StringVar(value="File Copy")
        task_menu = tk.OptionMenu(main_frame, self.task_var, "File Copy", "Folder Backup")
        task_menu.config(
            bg=ENTRY_BG, fg=ENTRY_FG, activebackground=BROWSE_COLOR,
            activeforeground="white", highlightthickness=0, width=20,
            font=("Arial", 10), relief="flat",
        )
        task_menu["menu"].config(bg=ENTRY_BG, fg=ENTRY_FG)
        task_menu.pack(pady=5, fill="x")

        # 2. Source path
        self._section_label(main_frame, "Source Path (File / Folder):")
        self.src_entry = self._styled_entry(main_frame)
        self._browse_button(main_frame, "Browse Source", self._browse_source)

        # 3. Destination path
        self._section_label(main_frame, "Destination Path:")
        self.dest_entry = self._styled_entry(main_frame)
        self._browse_button(main_frame, "Browse Destination", self._browse_dest)

        # 4. Time selection
        self._section_label(main_frame, "Schedule Time:")
        time_frame = tk.Frame(main_frame, bg=FRAME_COLOR)
        time_frame.pack(pady=5)

        self.hour_entry = tk.Entry(
            time_frame, width=3, font=("Arial", 16, "bold"), justify="center",
            bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG, relief="flat",
        )
        self.hour_entry.pack(side="left", padx=2)

        tk.Label(
            time_frame, text=":", font=("Arial", 16, "bold"),
            bg=FRAME_COLOR, fg=TEXT_COLOR,
        ).pack(side="left")

        self.minute_entry = tk.Entry(
            time_frame, width=3, font=("Arial", 16, "bold"), justify="center",
            bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG, relief="flat",
        )
        self.minute_entry.pack(side="left", padx=2)

        self.am_pm_var = tk.StringVar(value="AM")
        am_pm_menu = tk.OptionMenu(time_frame, self.am_pm_var, "AM", "PM")
        am_pm_menu.config(
            bg=ENTRY_BG, fg=ENTRY_FG, activebackground=BROWSE_COLOR,
            activeforeground="white", highlightthickness=0,
            font=("Arial", 12), relief="flat",
        )
        am_pm_menu["menu"].config(bg=ENTRY_BG, fg=ENTRY_FG)
        am_pm_menu.pack(side="left", padx=10)

        # --- Action Buttons ---
        btn_frame = tk.Frame(self.root, bg=BG_COLOR)
        btn_frame.pack(pady=15)

        self.start_btn = self._action_button(
            btn_frame, "▶  START AUTOMATION", BTN_COLOR, BTN_HOVER,
            self.start_scheduling,
        )
        self.start_btn.pack(side="left", padx=8)

        self.stop_btn = self._action_button(
            btn_frame, "■  STOP ALL", STOP_COLOR, STOP_HOVER,
            self.stop_scheduling,
        )
        self.stop_btn.pack(side="left", padx=8)

        # --- Status Label ---
        self.status_var = tk.StringVar(value="No task scheduled")
        tk.Label(
            self.root, textvariable=self.status_var, font=("Arial", 10, "italic"),
            bg=BG_COLOR, fg=ACCENT_COLOR,
        ).pack(pady=(0, 5))

        # --- Task History Log ---
        log_label_frame = tk.Frame(self.root, bg=BG_COLOR)
        log_label_frame.pack(fill="x", padx=24)
        tk.Label(
            log_label_frame, text="Task History", font=("Arial", 10, "bold"),
            bg=BG_COLOR, fg=MUTED_COLOR,
        ).pack(anchor="w")

        log_frame = tk.Frame(self.root, bg=LOG_BG, bd=0, relief="flat")
        log_frame.pack(padx=24, pady=(2, 10), fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame, height=6, bg=LOG_BG, fg=MUTED_COLOR,
            font=("Consolas", 9), relief="flat", state="disabled",
            wrap="word", padx=8, pady=6,
        )
        self.log_text.pack(fill="both", expand=True)

        # --- Footer ---
        tk.Label(
            self.root, text="Built with Python & Tkinter",
            font=("Arial", 8, "italic"), bg=BG_COLOR, fg="#4A6278",
        ).pack(side="bottom", pady=5)

    # ------------------------------------------------------------------ #
    #                         UI HELPER METHODS                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _section_label(parent, text):
        tk.Label(
            parent, text=text, font=("Arial", 10, "bold"),
            bg=FRAME_COLOR, fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(12, 0))

    @staticmethod
    def _styled_entry(parent) -> tk.Entry:
        entry = tk.Entry(
            parent, font=("Arial", 10), bd=0, relief="flat",
            bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
        )
        entry.pack(fill="x", pady=5, ipady=4)
        return entry

    def _browse_button(self, parent, text, command):
        btn = tk.Button(
            parent, text=text, command=command,
            bg=BROWSE_COLOR, fg="white", activebackground=BROWSE_HOVER,
            activeforeground="white", font=("Arial", 9, "bold"),
            relief="flat", cursor="hand2", bd=0,
        )
        btn.pack(fill="x", ipady=2)
        btn.bind("<Enter>", lambda e: btn.config(bg=BROWSE_HOVER))
        btn.bind("<Leave>", lambda e: btn.config(bg=BROWSE_COLOR))

    @staticmethod
    def _action_button(parent, text, bg, hover_bg, command):
        btn = tk.Button(
            parent, text=text, bg=bg, fg="white", activebackground=hover_bg,
            activeforeground="white", font=("Arial", 12, "bold"),
            relief="flat", cursor="hand2", bd=0, padx=20, pady=10,
            command=command,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _append_log(self, message: str):
        """Append a timestamped message to the in-app task history (thread-safe)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}]  {message}\n"
        self.log_text.config(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ------------------------------------------------------------------ #
    #                          BROWSE ACTIONS                            #
    # ------------------------------------------------------------------ #

    def _browse_source(self):
        if self.task_var.get() == "File Copy":
            path = filedialog.askopenfilename()
        else:
            path = filedialog.askdirectory()
        if path:
            self.src_entry.delete(0, tk.END)
            self.src_entry.insert(0, path)

    def _browse_dest(self):
        path = filedialog.askdirectory()
        if path:
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, path)

    # ------------------------------------------------------------------ #
    #                        SCHEDULING LOGIC                            #
    # ------------------------------------------------------------------ #

    def _perform_task(self, task_type: str, src: str, dest: str):
        """Execute the copy/backup. Called from the scheduler (background thread)."""
        try:
            if task_type == "File Copy":
                shutil.copy(src, dest)
                msg = f"File copied → {dest}"
            else:
                folder_name = os.path.basename(src)
                final_dest = os.path.join(dest, folder_name)
                shutil.copytree(src, final_dest, dirs_exist_ok=True)
                msg = f"Backup created → {final_dest}"

            logger.info(msg)
            # Thread-safe UI updates via root.after()
            self.root.after(0, lambda: self._append_log(f"✅ {msg}"))
            self.root.after(0, lambda: self.status_var.set(f"Last run: {msg}"))

        except Exception as e:
            error_msg = f"Task failed: {e}"
            logger.error(error_msg)
            self.root.after(0, lambda: self._append_log(f"❌ {error_msg}"))
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

    def start_scheduling(self):
        """Validate inputs and schedule the task."""
        src = self.src_entry.get().strip()
        dest = self.dest_entry.get().strip()
        h = self.hour_entry.get().strip()
        m = self.minute_entry.get().strip()
        p = self.am_pm_var.get()

        # --- Validation ---
        if not all([src, dest, h, m]):
            messagebox.showwarning("Input Error", "Please fill in all fields!")
            return

        if not os.path.exists(src):
            messagebox.showwarning("Path Error", f"Source path does not exist:\n{src}")
            return

        if self.task_var.get() == "File Copy" and not os.path.isfile(src):
            messagebox.showwarning("Path Error", "Source must be a file for 'File Copy'.")
            return

        if self.task_var.get() == "Folder Backup" and not os.path.isdir(src):
            messagebox.showwarning("Path Error", "Source must be a folder for 'Folder Backup'.")
            return

        if not os.path.isdir(dest):
            messagebox.showwarning("Path Error", f"Destination folder does not exist:\n{dest}")
            return

        # Time validation
        try:
            hour = int(h)
            minute = int(m)
            if not (1 <= hour <= 12):
                raise ValueError("Hour must be 1–12")
            if not (0 <= minute <= 59):
                raise ValueError("Minute must be 0–59")

            time_input = f"{hour}:{minute:02d} {p}"
            t_struct = time.strptime(time_input, "%I:%M %p")
            t_24hr = time.strftime("%H:%M", t_struct)
        except ValueError as e:
            messagebox.showerror("Time Error", f"Invalid time: {e}\nUse format like 10:30")
            return

        # Cancel previous job if any
        if self.current_job is not None:
            schedule.cancel_job(self.current_job)
            logger.info("Previous scheduled job cancelled.")

        # Schedule the new job
        task_type = self.task_var.get()
        self.current_job = (
            schedule.every().day.at(t_24hr).do(self._perform_task, task_type, src, dest)
        )

        display_time = f"{hour}:{minute:02d} {p}"
        self.status_var.set(f"Scheduled: {task_type} daily at {display_time}")
        self._append_log(f"📅 Scheduled '{task_type}' → {display_time}")
        logger.info(f"Task scheduled: {task_type} at {t_24hr} | {src} → {dest}")
        messagebox.showinfo("Scheduled", f"Task set for {display_time} daily!")

    def stop_scheduling(self):
        """Cancel all scheduled tasks."""
        if self.current_job is not None:
            schedule.cancel_job(self.current_job)
            self.current_job = None
            self.status_var.set("All tasks stopped")
            self._append_log("🛑 All scheduled tasks stopped.")
            logger.info("All tasks stopped by user.")
            messagebox.showinfo("Stopped", "All scheduled tasks have been stopped.")
        else:
            messagebox.showinfo("Nothing to Stop", "No task is currently scheduled.")

    # ------------------------------------------------------------------ #
    #                      SCHEDULER THREAD                              #
    # ------------------------------------------------------------------ #

    def _start_scheduler_thread(self):
        """Start the background scheduler loop."""
        def _run():
            while True:
                schedule.run_pending()
                time.sleep(1)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.info("Scheduler thread started.")

    def _on_close(self):
        """Clean shutdown."""
        logger.info("Application closed.")
        self.root.destroy()


# ======================================================================
#                            ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = TaskSchedulerApp(root)
    root.mainloop()
