"""Build script to package Claude Session Manager into an executable."""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def build():
    """Build the executable using PyInstaller."""
    system = platform.system()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "ClaudeSessionManager",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
    ]

    # Include customtkinter assets
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        cmd.extend(["--add-data", f"{ctk_path}{os.pathsep}customtkinter"])
    except ImportError:
        print("Warning: customtkinter not found, build may fail.")

    # Icon (optional)
    icon_path = "icon.ico" if system == "Windows" else ("icon.icns" if system == "Darwin" else None)
    if icon_path and os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])

    cmd.append("session_manager.py")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n[OK] Build successful!")
        print(f"Executable located at: dist/ClaudeSessionManager{'(.exe)' if system == 'Windows' else ''}")
    else:
        print("\n[ERROR] Build failed!")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
