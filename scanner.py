"""Session scanner - discovers and parses Claude Code sessions."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import Project, Session, decode_project_name
from utils import get_projects_dir, get_sessions_dir


def parse_iso_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string."""
    if not ts:
        return None
    try:
        # Handle Z suffix
        ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        # Convert offset-aware to offset-naive for consistent comparison
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
        # ai-title has aiTitle at top level or nested
        title = msg.get("aiTitle")
        if title:
            return title
        return msg.get("message", {}).get("title")

    if msg_type == "last-prompt":
        # last-prompt has lastPrompt at top level
        prompt = msg.get("lastPrompt")
        if prompt:
            return prompt
        return msg.get("display")

    return None


def scan_session_file(filepath: Path) -> Optional[Session]:
    """Parse a single .jsonl session file and extract metadata.

    Uses efficient streaming to handle large files.
    """
    if not filepath.exists() or not filepath.is_file():
        return None

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
                    # Extract cwd from first message for accurate project path
                    cwd = first_msg.get("cwd")
                    if cwd:
                        project_path = cwd
                    ts = first_msg.get("timestamp")
                    if ts:
                        first_timestamp = parse_iso_timestamp(ts)
                    # Fallback: check for startedAt in first message
                    if not first_timestamp:
                        started_at = first_msg.get("startedAt")
                        if started_at:
                            first_timestamp = parse_timestamp_ms(started_at)
                except json.JSONDecodeError:
                    pass

            # Read line by line for the rest
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

                # Extract cwd from any message (first one with cwd wins)
                if not project_path or project_path == decode_project_name(project_name):
                    cwd = msg.get("cwd")
                    if cwd:
                        project_path = cwd

                # Extract title
                if msg.get("type") == "ai-title":
                    new_title = extract_message_preview(msg)
                    if new_title:
                        title = new_title

                # Extract last user prompt
                if msg.get("type") == "user":
                    preview = extract_message_preview(msg)
                    if preview:
                        last_user_message = preview

                # Extract last-prompt
                if msg.get("type") == "last-prompt":
                    preview = extract_message_preview(msg)
                    if preview:
                        last_prompt = preview

            # Last line timestamp
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

    # Use last user message as last_prompt if not found
    if not last_prompt and last_user_message:
        last_prompt = last_user_message

    # If no title found, try to derive from first user message
    if not title and last_prompt:
        title = last_prompt[:60]

    return Session(
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


def load_active_sessions() -> dict[str, int]:
    """Load active session IDs mapped to their PIDs.

    Returns:
        Dict mapping session_id -> pid
    """
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
                # Verify process is still running
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
    """Scan all projects and their sessions.

    Returns:
        List of Project objects sorted by latest activity.
    """
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
                # Check if active
                if session.session_id in active_sessions:
                    session.is_active = True
                    session.active_pid = active_sessions[session.session_id]
                project.sessions.append(session)

        if project.sessions:
            # Sort sessions by last activity (newest first)
            project.sessions.sort(
                key=lambda s: s.last_timestamp or datetime.min,
                reverse=True,
            )
            projects.append(project)

    # Sort projects by latest session activity
    projects.sort(
        key=lambda p: (p.latest_session().last_timestamp or datetime.min),
        reverse=True,
    )

    return projects


def delete_session(session: Session) -> bool:
    """Delete a session and its associated data.

    Returns True if successful.
    """
    try:
        # Delete the main jsonl file
        filepath = Path(session.file_path)
        if filepath.exists():
            filepath.unlink()

        # Delete session subdirectory if exists
        session_dir = filepath.parent / session.session_id
        if session_dir.exists() and session_dir.is_dir():
            import shutil

            shutil.rmtree(session_dir)

        return True
    except OSError:
        return False


def get_session_preview_messages(filepath: Path, count: int = 5) -> list[dict]:
    """Get the last N messages from a session file for preview.

    Returns list of dicts with 'type', 'preview', 'timestamp'.
    """
    messages = []
    if not filepath.exists():
        return messages

    try:
        lines = []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        # Take last N non-empty lines
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

    # Reverse to get chronological order
    messages.reverse()
    return messages
