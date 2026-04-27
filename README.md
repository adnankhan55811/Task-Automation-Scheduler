# Advanced Task Scheduler

A powerful desktop application to schedule and automate **file operations**, **commands**, and **backups**.

Built with **Python** and **Tkinter**.

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📋 **Multiple Task Queue** | Create, edit, delete, and manage multiple scheduled tasks |
| 💾 **Config Persistence** | Tasks auto-save to `config.json` and reload on startup |
| 🔁 **Repeat Options** | Once, Daily, Hourly, Weekly (pick days), Every X Minutes |
| ⏯ **Pause / Resume** | Per-task pause and resume controls (toolbar + right-click) |
| 🎨 **Dark / Light Theme** | Toggle between dark and light UI themes |
| 🔔 **Desktop Notifications** | Native toast notifications on task success/failure |
| 💿 **Disk Space Check** | Verifies free space before copying |
| 🖱️ **Drag & Drop** | Drop files/folders directly onto input fields |
| 📝 **Task History Log** | Timestamped in-app log of all events |
| 🔒 **Input Validation** | Path existence, time ranges, disk space checks |
| 📄 **File Logging** | All activity logged to `scheduler.log` |

### Operations

| Operation | Description |
|-----------|-------------|
| 📄 **File Copy** | Copy a file to a destination folder |
| 📁 **Folder Backup** | Back up an entire folder (timestamped) |
| 📦 **Move File** | Move a file to a new location |
| ⚡ **Run Command** | Execute any shell command or script |
| 🗜️ **Zip Archive** | Compress a folder into a `.zip` file |

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python task_scheduler.py
```

---

## 📖 How to Use

1. Click **➕ Add Task** to create a new scheduled task
2. Choose an **operation** (File Copy, Folder Backup, Move File, Run Command, Zip Archive)
3. Fill in the source, destination, schedule, and time
4. The task appears in the task table with its status
5. **Right-click** a task for options: Run Now, Edit, Pause/Resume, Delete
6. Use **⏯ Pause / Resume** in the toolbar to control individual tasks
7. Click **☀️ Light / 🌙 Dark** to toggle the theme
8. All tasks auto-save and reload when you restart the app

### Schedule Types

| Type | Behavior |
|------|----------|
| **Once** | Runs once at the specified time, then auto-disables |
| **Daily** | Runs every day at the specified time |
| **Hourly** | Runs every hour |
| **Weekly** | Runs on selected days at the specified time |
| **Every X Minutes** | Runs at a custom interval (e.g. every 30 minutes) |

---

## 📂 Project Structure

```
├── task_scheduler.py   # Main application
├── config.json         # Auto-generated task storage
├── scheduler.log       # Activity log
├── requirements.txt    # Python dependencies
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

---

## 🔧 Dependencies

| Package | Purpose |
|---------|---------|
| `schedule` | Job scheduling engine |
| `plyer` | Desktop toast notifications (optional) |
| `tkinterdnd2` | Drag & drop support (optional) |

> **Note:** `plyer` and `tkinterdnd2` are optional — the app gracefully falls back if they are missing.

---

## 📋 Requirements

- Python 3.9+
- Tkinter (included with Python on Windows/macOS)

---

## License

MIT
