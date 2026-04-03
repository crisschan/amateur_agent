"""Persistent task store backed by JSON files in .tasks/.

Tasks survive context compression because state is on disk, not in
the conversation. Each task carries a dependency graph (blockedBy / blocks).
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


class TaskManager:
    """CRUD task store with a simple dependency graph."""

    _VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})
    _MARKERS = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}

    def __init__(self, tasks_dir: Path) -> None:
        self.dir = tasks_dir
        self.dir.mkdir(exist_ok=True)
        self._next_id = self._max_id() + 1

    # ---------------------------------------------------------------- internal

    def _max_id(self) -> int:
        ids = [
            int(f.stem.split("_")[1])
            for f in self.dir.glob("task_*.json")
            if f.stem.split("_")[1].isdigit()
        ]
        return max(ids) if ids else 0

    def _path(self, task_id: int) -> Path:
        return self.dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> dict:
        p = self._path(task_id)
        if not p.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(p.read_text())

    def _save(self, task: dict) -> None:
        self._path(task["id"]).write_text(json.dumps(task, indent=2))

    def _clear_dependency(self, completed_id: int) -> None:
        """Remove *completed_id* from every other task's blockedBy list."""
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text())
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)

    # ------------------------------------------------------------------ public

    def create(self, subject: str, description: str = "") -> str:
        task = {
            "id": self._next_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2)

    def get(self, task_id: int) -> str:
        try:
            return json.dumps(self._load(task_id), indent=2)
        except ValueError as exc:
            return f"Error: {exc}"

    def update(
        self,
        task_id: int,
        status: str = None,
        add_blocked_by: list = None,
        add_blocks: list = None,
    ) -> str:
        try:
            task = self._load(task_id)
        except ValueError as exc:
            return f"Error: {exc}"

        if status is not None:
            if status not in self._VALID_STATUSES:
                return f"Error: Invalid status '{status}'"
            task["status"] = status
            if status == "completed":
                self._clear_dependency(task_id)

        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))

        if add_blocks:
            task["blocks"] = list(set(task["blocks"] + add_blocks))
            # Keep the graph bidirectional
            for blocked_id in add_blocks:
                try:
                    blocked = self._load(blocked_id)
                    if task_id not in blocked["blockedBy"]:
                        blocked["blockedBy"].append(task_id)
                        self._save(blocked)
                except ValueError:
                    pass  # target task doesn't exist — ignore

        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [
            json.loads(f.read_text())
            for f in sorted(self.dir.glob("task_*.json"))
        ]
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            marker = self._MARKERS.get(t["status"], "[?]")
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{blocked}")
        return "\n".join(lines)


def create_task_tools(manager: TaskManager) -> list:
    @tool
    def task_create(subject: str, description: str = "") -> str:
        """Create a new persistent task. Returns the task JSON."""
        return manager.create(subject, description)

    @tool
    def task_update(
        task_id: int,
        status: str = None,
        add_blocked_by: list = None,
        add_blocks: list = None,
    ) -> str:
        """Update a persistent task.

        status: "pending" | "in_progress" | "completed"
        add_blocked_by: list of task IDs this task depends on
        add_blocks: list of task IDs this task blocks
        """
        return manager.update(task_id, status, add_blocked_by, add_blocks)

    @tool
    def task_list() -> str:
        """List all persistent tasks with their status and blocked-by info."""
        return manager.list_all()

    @tool
    def task_get(task_id: int) -> str:
        """Get full details of a persistent task by ID."""
        return manager.get(task_id)

    return [task_create, task_update, task_list, task_get]
