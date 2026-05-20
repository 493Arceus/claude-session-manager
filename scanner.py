"""Session scanner - discovers and parses Claude Code sessions."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import Project, Session, decode_project_name
from utils import get_projects_dir, get_sessions_dir

# File-level cache: filepath -> (mtime, Session)
_session_cache: dict[str, tuple[float, Session]] = {}


def parse_iso_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string."""
    if not ts:
        return None
    try:
        ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def parse_timestamp_ms(ts: int | float) -> Optional[datetime]:
    """Parse millisecond timestamp."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000)
    except (ValueError, TypeError, OSError):
        return None


def extract_message_preview(msg: dict) -> Optional[str]:
    """Extract human-readable preview from a message."""
    msg_type = msg.get("type", "")

    if msg_type == "user":
        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content if content.strip() else None
        if content and isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif "text" in part:
                        text_parts.append(part["text"])
            result = " ".join(text_parts).strip()
            return result if result else None
        return None

    if msg_type == "assistant":
        content = msg.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content if content.strip() else None
        if content and isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            result = " ".join(text_parts).strip()
            return result if result else None
        return None

    if msg_type == "ai-title":
        title = msg.get("aiTitle")
        if title:
            return title
        return msg.get("message", {}).get("title")

    if msg_type == "last-prompt":
        prompt = msg.get("lastPrompt")
        if prompt:
            return prompt
        return msg.get("display")

    return None


def scan_session_file(filepath: Path) -> Optional[Session]:
    """Parse a single .jsonl session file and extract metadata.

    Uses file-level cache based on mtime to avoid re-parsing unchanged files.
    """
    global _session_cache

    if not filepath.exists() or not filepath.is_file():
        return None

    cache_key = str(filepath)
    try:
        mtime = filepath.stat().st_mtime
    except OSError:
        return None

    # Check cache
    if cache_key in _session_cache:
        cached_mtime, cached_session = _session_cache[cache_key]
        if cached_mtime == mtime:
            return replace(cached_session)

    session_id = filepath.stem
    project_name = filepath.parent.name
    project_path = decode_project_name(project_name)
    file_size = filepath.stat().st_size

    title: Optional[str] = None
    last_prompt: Optional[str] = None
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    message_count = 0
    last_user_message: Optional[str] = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline()
            if first_line.strip():
                try:
                    first_msg = json.loads(first_line)
                    cwd = first_msg.get("cwd")
                    if cwd:
                        project_path = cwd
                    ts = first_msg.get("timestamp")
                    if ts:
                        first_timestamp = parse_iso_timestamp(ts)
                    if not first_timestamp:
                        started_at = first_msg.get("startedAt")
                        if started_at:
                            first_timestamp = parse_timestamp_ms(started_at)
                except json.JSONDecodeError:
                    pass

            prev_line = ""
            for line in f:
                prev_line = line
                message_count += 1
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not project_path or project_path == decode_project_name(project_name):
                    cwd = msg.get("cwd")
                    if cwd:
                        project_path = cwd

                if msg.get("type") == "ai-title":
                    new_title = extract_message_preview(msg)
                    if new_title:
                        title = new_title

                if msg.get("type") == "user":
                    preview = extract_message_preview(msg)
                    if preview:
                        last_user_message = preview

                if msg.get("type") == "last-prompt":
                    preview = extract_message_preview(msg)
                    if preview:
                        last_prompt = preview

            if prev_line.strip():
                try:
                    last_msg = json.loads(prev_line)
                    ts = last_msg.get("timestamp")
                    if ts:
                        last_timestamp = parse_iso_timestamp(ts)
                except json.JSONDecodeError:
                    pass

    except OSError:
        return None

    if not last_prompt and last_user_message:
        last_prompt = last_user_message

    if not title and last_prompt:
        title = last_prompt[:60]

    session = Session(
        session_id=session_id,
        project_name=project_name,
        project_path=project_path,
        file_path=str(filepath),
        title=title,
        message_count=message_count,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        last_prompt=last_prompt,
        file_size=file_size,
    )

    _session_cache[cache_key] = (mtime, session)
    return replace(session)


def load_active_sessions() -> dict[str, int]:
    """Load active session IDs mapped to their PIDs."""
    active: dict[str, int] = {}
    sessions_dir = get_sessions_dir()

    if not sessions_dir.exists():
        return active

    for pid_file in sessions_dir.glob("*.json"):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            session_id = data.get("sessionId")
            pid = data.get("pid")
            if session_id and pid:
                if is_process_running(pid):
                    active[session_id] = pid
        except (json.JSONDecodeError, OSError):
            continue

    return active


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is still running."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def scan_all_projects() -> list[Project]:
    """Scan all projects and their sessions."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return []

    active_sessions = load_active_sessions()
    projects: list[Project] = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        decoded_path = decode_project_name(project_dir.name)
        project = Project(name=project_dir.name, decoded_path=decoded_path)

        for session_file in project_dir.glob("*.jsonl"):
            session = scan_session_file(session_file)
            if session:
                if session.session_id in active_sessions:
                    session = replace(session, is_active=True, active_pid=active_sessions[session.session_id])
                project.sessions.append(session)

        if project.sessions:
            project.sessions.sort(
                key=lambda s: s.last_timestamp or datetime.min,
                reverse=True,
            )
            projects.append(project)

    projects.sort(
        key=lambda p: (p.latest_session().last_timestamp or datetime.min),
        reverse=True,
    )

    return projects


def delete_session(session: Session) -> bool:
    """Delete a session and its associated data."""
    global _session_cache
    try:
        filepath = Path(session.file_path)
        if filepath.exists():
            filepath.unlink()
            # Remove from cache
            _session_cache.pop(str(filepath), None)

        session_dir = filepath.parent / session.session_id
        if session_dir.exists() and session_dir.is_dir():
            import shutil
            shutil.rmtree(session_dir)

        return True
    except OSError:
        return False


def get_session_preview_messages(filepath: Path, count: int = 5) -> list[dict]:
    """Get the last N messages from a session file for preview."""
    messages = []
    if not filepath.exists():
        return messages

    try:
        lines = []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in reversed(lines):
            if len(messages) >= count:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "unknown")
            preview = extract_message_preview(msg)
            if not preview:
                continue

            ts = msg.get("timestamp")
            dt = parse_iso_timestamp(ts) if ts else None

            messages.append({
                "type": msg_type,
                "preview": preview,
                "timestamp": dt,
            })

    except OSError:
        pass

    messages.reverse()
    return messages
