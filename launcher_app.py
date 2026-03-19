import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def resolve_project_dir():
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "app.py").exists():
            return exe_dir
        if (exe_dir.parent / "app.py").exists():
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


def resolve_python_exe(base_dir):
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python

    if getattr(sys, "frozen", False):
        return Path("py")

    return Path(sys.executable)


def run():
    base_dir = resolve_project_dir()
    os.chdir(base_dir)

    python_exe = resolve_python_exe(base_dir)

    # Ensure dependencies are installed in the current environment.
    subprocess.run([str(python_exe), "-m", "pip", "install", "-r", "requirements.txt"], check=False)
    subprocess.run([str(python_exe), "-m", "pip", "install", "playwright"], check=False)
    subprocess.run([str(python_exe), "-m", "playwright", "install", "chromium"], check=False)

    webbrowser.open("http://127.0.0.1:5000")
    subprocess.run([str(python_exe), "app.py"], check=False)


if __name__ == "__main__":
    run()
