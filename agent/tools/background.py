"""Background task execution via daemon threads.

The agent fires a command and gets a task_id back immediately.
Completion notifications are drained into the conversation before
each LLM call so the model learns about results without polling.

Security: reuses the same safety-checked runner from filesystem.py
so the 'dangerous command' block is applied consistently.
"""
from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from agent.tools._safety import is_dangerous

_BG_TIMEOUT = 300  # longer than foreground bash — background tasks run async


class BackgroundManager:
    """Runs shell commands in daemon threads; queues completion notifications."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.tasks: dict[str, dict] = {}
        self._queue: list[dict] = []
        self._lock = threading.Lock()

    def run(self, command: str) -> str:
        """Start command in a background thread. Returns task_id immediately."""
        # Apply the safety check before spawning — same rules as foreground bash
        if is_dangerous(command):
            return "Error: Dangerous command blocked"

        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "status": "running",
            "result": None,
            "command": command,
        }
        thread = threading.Thread(
            target=self._execute, args=(task_id, command), daemon=True
        )
        thread.start()
        return f"Background task {task_id} started: {command[:80]}"

    def _execute(self, task_id: str, command: str) -> None:
        try:
            r = subprocess.run(
                command,
                shell=True,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=_BG_TIMEOUT,
            )
            output = (r.stdout + r.stderr).strip()[:50_000] or "(no output)"
            status = "completed"
        except subprocess.TimeoutExpired:
            output = f"Error: Timeout ({_BG_TIMEOUT}s)"
            status = "timeout"
        except Exception as exc:
            output = f"Error: {exc}"
            status = "error"

        self.tasks[task_id]["status"] = status
        self.tasks[task_id]["result"] = output
        with self._lock:
            self._queue.append({
                "task_id": task_id,
                "status": status,
                "command": command[:80],
                "result": output[:500],
            })

    def check(self, task_id: str = None) -> str:
        """Return status of one task, or a summary of all tasks."""
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"Error: Unknown task {task_id}"
            return f"[{t['status']}] {t['command'][:60]}\n{t.get('result') or '(running)'}"
        if not self.tasks:
            return "No background tasks."
        lines = [
            f"{tid}: [{t['status']}] {t['command'][:60]}"
            for tid, t in self.tasks.items()
        ]
        return "\n".join(lines)

    def drain(self) -> list[dict]:
        """Return and clear all pending completion notifications."""
        with self._lock:
            notifs = list(self._queue)
            self._queue.clear()
        return notifs


def create_background_tools(manager: BackgroundManager) -> list:
    @tool
    def background_run(command: str) -> str:
        """Run a shell command in a background thread.

        Returns a task_id immediately — the agent can continue working.
        Results arrive as background-results notifications before the next LLM call.
        Use check_background to poll status explicitly.
        """
        return manager.run(command)

    @tool
    def check_background(task_id: str = None) -> str:
        """Check the status of a background task.

        Omit *task_id* to list all background tasks.
        """
        return manager.check(task_id)

    return [background_run, check_background]
