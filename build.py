"""Build script to package Claude Session Manager into an executable."""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def build():
    """Build the executable using PyInstaller."""
    system = platform.system()

    # Set Tcl/Tk library paths so PyInstaller's tkinter detection works
    # (required when system Tcl configuration is broken/mislocated)
    if system == "Windows":
        py_base = os.path.dirname(sys.executable)
        tcl_lib = os.path.join(py_base, "tcl", "tcl8.6")
        tk_lib = os.path.join(py_base, "tcl", "tk8.6")
        if os.path.isdir(tcl_lib):
            os.environ["TCL_LIBRARY"] = tcl_lib
        if os.path.isdir(tk_lib):
            os.environ["TK_LIBRARY"] = tk_lib

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

    # Include Tcl/Tk libraries (needed when system tkinter is broken/misconfigured)
    # PyInstaller expects these at _tcl_data and _tk_data paths in onefile mode
    if system == "Windows":
        py_base = os.path.dirname(sys.executable)
        # Force-include tkinter binaries that PyInstaller excludes
        tkinter_bins = [
            os.path.join(py_base, "DLLs", "_tkinter.pyd"),
            os.path.join(py_base, "DLLs", "tcl86t.dll"),
            os.path.join(py_base, "DLLs", "tk86t.dll"),
        ]
        for binary in tkinter_bins:
            if os.path.exists(binary):
                cmd.extend(["--add-binary", f"{binary}{os.pathsep}."])
        # Force-include tkinter module and data
        cmd.extend(["--hidden-import", "tkinter"])
        tcl8_path = os.path.join(py_base, "tcl", "tcl8.6")
        tk8_path = os.path.join(py_base, "tcl", "tk8.6")
        if os.path.isdir(tcl8_path):
            cmd.extend(["--add-data", f"{tcl8_path}{os.pathsep}_tcl_data"])
        if os.path.isdir(tk8_path):
            cmd.extend(["--add-data", f"{tk8_path}{os.pathsep}_tk_data"])

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
