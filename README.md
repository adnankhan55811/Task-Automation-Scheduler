# Task Scheduler

A desktop application to schedule daily **file copy** and **folder backup** operations at a specific time.

Built with **Python** and **Tkinter**.

![Screenshot](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)

---

## Features

- 📁 **File Copy** — Copy a single file to a destination folder on a daily schedule
- 📂 **Folder Backup** — Recursively back up an entire directory daily
- ⏰ **12-hour Time Picker** — Set the schedule time with AM/PM selection
- 📋 **Task History Log** — See timestamped results of past executions in the UI
- 🛑 **Stop / Cancel** — Stop a scheduled task at any time
- 📝 **File Logging** — All activity is logged to `scheduler.log`
- ✅ **Input Validation** — Paths and times are validated before scheduling

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python task_scheduler.py
```

---

## How It Works

1. Select an operation (**File Copy** or **Folder Backup**)
2. Browse for a **source** file or folder
3. Browse for a **destination** folder
4. Set the **time** (hours, minutes, AM/PM)
5. Click **START AUTOMATION** — the task will run daily at the scheduled time
6. Click **STOP ALL** to cancel

The scheduler runs in a background thread so the UI stays responsive. Logs are saved to `scheduler.log` in the same directory.

---

## Project Structure

```
project/
├── task_scheduler.py   # Main application
├── requirements.txt    # Python dependencies
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

---

## Requirements

- Python 3.9+
- Tkinter (included with standard Python on Windows/macOS)
- `schedule` library

---

## License

MIT
