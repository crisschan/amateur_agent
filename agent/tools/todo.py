"""In-memory todo list for tracking multi-step work within a conversation.

Intentionally lightweight — state lives in memory, not on disk.
For work that must survive context compression, use tasks.py instead.
"""
from __future__ import annotations

from langchain_core.tools import tool


class TodoManager:
    """Validates and renders a small, in-memory task list."""

    _VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})
    _MARKERS = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}

    def __init__(self) -> None:
        self.items: list[dict] = []

    def update(self, items: list) -> str:
        if len(items) > 20:
            raise ValueError("Max 20 todos allowed")

        validated: list[dict] = []
        in_progress_count = 0

        for i, raw in enumerate(items):
            text = str(raw.get("text", "")).strip()
            status = str(raw.get("status", "pending")).lower()
            item_id = str(raw.get("id", str(i + 1)))

            if not text:
                raise ValueError(f"Item {item_id}: 'text' is required")
            if status not in self._VALID_STATUSES:
                raise ValueError(
                    f"Item {item_id}: invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(self._VALID_STATUSES))}"
                )
            if status == "in_progress":
                in_progress_count += 1

            validated.append({"id": item_id, "text": text, "status": status})

        if in_progress_count > 1:
            raise ValueError("Only one task may be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines = [
            f"{self._MARKERS[t['status']]} #{t['id']}: {t['text']}"
            for t in self.items
        ]
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)


def create_todo_tool(manager: TodoManager):
    @tool
    def todo(items: list) -> str:
        """Update the in-memory todo list.

        Each item must be a dict: {"id": str, "text": str, "status": str}.
        status values: "pending" | "in_progress" | "completed".
        Only one item may be in_progress at a time. Maximum 20 items.
        """
        try:
            return manager.update(items)
        except ValueError as exc:
            return f"Error: {exc}"

    return todo
