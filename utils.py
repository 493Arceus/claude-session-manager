"""Utility functions for Claude Session Manager."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def get_claude_dir() -> Path:
    """Get the Claude Code configuration directory."""
    home = Path.home()
    return home / ".claude"


def get_projects_dir() -> Path:
    """Get the projects directory."""
    return get_claude_dir() / "projects"


def get_sessions_dir() -> Path:
    """Get the active sessions directory."""
    return get_claude_dir() / "sessions"


def _launch_windows_terminal(cwd: str, cmd: str) -> None:
    """Launch a new terminal on Windows using os.system for reliability."""
    safe_cwd = cwd.replace('"', '\\"')
    # Use start command with a title, cd /d handles drive changes
    full_cmd = f'start "Claude" cmd /k "cd /d \"{safe_cwd}\" && {cmd}"'
    os.system(full_cmd)


def launch_claude_session(session_id: str, cwd: str, mode: str = "resume") -> None:
    """Launch a Claude session in a new terminal window.

    Args:
        session_id: The session UUID
        cwd: Working directory
        mode: 'resume' (default), 'fork', or 'new'
    """
    system = platform.system()

    if mode == "resume":
        cmd = f"claude --resume {session_id}"
    elif mode == "fork":
        cmd = f"claude --resume {session_id} --fork-session"
    elif mode == "new":
        cmd = "claude"
    else:
        cmd = f"claude --resume {session_id}"

    if system == "Windows":
        _launch_windows_terminal(cwd, cmd)
    elif system == "Darwin":
        script = f'tell application "Terminal" to do script "cd \\"{cwd}\\" && {cmd}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        # Linux - try common terminals
        terminals = [
            ["gnome-terminal", "--", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
            ["konsole", "-e", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
            ["xfce4-terminal", "-e", f"bash -c 'cd \"{cwd}\" && {cmd}; exec bash'"],
            ["xterm", "-e", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
        ]
        for term in terminals:
            try:
                subprocess.Popen(term)
                return
            except FileNotFoundError:
                continue


def launch_claude_resume(cwd: str) -> None:
    """Launch Claude with --resume in a new terminal."""
    system = platform.system()
    cmd = "claude --resume"

    if system == "Windows":
        _launch_windows_terminal(cwd, cmd)
    elif system == "Darwin":
        script = f'tell application "Terminal" to do script "cd \\"{cwd}\\" && {cmd}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        terminals = [
            ["gnome-terminal", "--", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
            ["konsole", "-e", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
            ["xfce4-terminal", "-e", f"bash -c 'cd \"{cwd}\" && {cmd}; exec bash'"],
            ["xterm", "-e", "bash", "-c", f"cd '{cwd}' && {cmd}; exec bash"],
        ]
        for term in terminals:
            try:
                subprocess.Popen(term)
                return
            except FileNotFoundError:
                continue


def open_in_file_manager(path: str) -> None:
    """Open a directory in the system's file manager."""
    system = platform.system()

    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ")
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
