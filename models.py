"""Data models for Claude Session Manager."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Session:
    """Represents a single Claude Code session."""

    session_id: str
    project_name: str
    project_path: str
    file_path: str
    title: Optional[str] = None
    message_count: int = 0
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    last_prompt: Optional[str] = None
    is_active: bool = False
    active_pid: Optional[int] = None
    file_size: int = 0

    def display_title(self) -> str:
        """Return a human-readable title."""
        if self.title:
            return self.title
        return f"Session {self.session_id[:8]}..."

    def display_time(self) -> str:
        """Return relative last activity time."""
        if not self.last_timestamp:
            return "Unknown"
        return format_relative_time(self.last_timestamp)

    def short_id(self) -> str:
        """Return short session ID."""
        return self.session_id[:8]

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "project_name": self.project_name,
            "project_path": self.project_path,
            "message_count": self.message_count,
            "last_timestamp": self.last_timestamp.isoformat() if self.last_timestamp else None,
            "is_active": self.is_active,
        }


@dataclass
class Project:
    """Represents a project directory containing sessions."""

    name: str
    decoded_path: str
    sessions: list[Session] = field(default_factory=list)

    def session_count(self) -> int:
        """Total sessions in this project."""
        return len(self.sessions)

    def total_messages(self) -> int:
        """Total messages across all sessions."""
        return sum(s.message_count for s in self.sessions)

    def latest_session(self) -> Optional[Session]:
        """Return the most recently active session."""
        if not self.sessions:
            return None
        return max(
            self.sessions,
            key=lambda s: s.last_timestamp or datetime.min,
        )


def format_relative_time(dt: datetime) -> str:
    """Format a datetime as relative time string (Chinese)."""
    now = datetime.now()
    diff = now - dt

    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} 分钟前"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} 小时前"
    if seconds < 604800:
        days = seconds // 86400
        return f"{days} 天前"
    if seconds < 2592000:
        weeks = seconds // 604800
        return f"{weeks} 周前"

    return dt.strftime("%Y-%m-%d")


def decode_project_name(name: str) -> str:
    """Decode a project directory name to a path.

    Examples:
        D--AI-cc-tools -> D:\AI\cc-tools (Windows)
        D--AI-OpenCode-WorkSpace-DND-- -> D:\AI\OpenCode-WorkSpace-DND\
        home-user-proj -> /home/user/proj (Unix)
    """
    parts = name.split("--")
    if not parts:
        return name

    # Filter out empty strings (from trailing --)
    parts = [p for p in parts if p]
    if not parts:
        return name

    # Heuristic: if first part is a single letter, treat as Windows drive
    if len(parts[0]) == 1 and parts[0].isalpha():
        # Windows path
        return parts[0].upper() + ":\\" + "\\".join(parts[1:])

    # Unix path
    return "/" + "/".join(parts)


def get_project_display_name(decoded_path: str) -> str:
    """Get a clean display name from a decoded project path.

    Handles trailing backslashes gracefully.
    """
    # Remove trailing backslashes/slashes
    cleaned = decoded_path.rstrip("\\/")
    if not cleaned:
        return decoded_path
    import os
    name = os.path.basename(cleaned)
    if name:
        return name
    # Fallback: use second-to-last component
    parts = [p for p in cleaned.replace("/", "\\").split("\\") if p]
    return parts[-1] if parts else decoded_path


def encode_project_name(path: str) -> str:
    """Encode a path to a project directory name.

    Examples:
        D:\AI\cc-tools -> D--AI-cc-tools
        /home/user/proj -> home-user-proj
    """
    path = path.replace("/", "\\")
    parts = path.split("\\")
    return "--".join(parts)
