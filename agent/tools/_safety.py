"""Shared safety utilities for command execution.

Centralised here so filesystem.py and background.py apply
identical checks — no divergence between sync and async runners.
"""
from __future__ import annotations

# Patterns that indicate a potentially destructive command.
# Note: we use "sudo " (with trailing space) to avoid blocking
# legitimate words like "pseudocode" or "sudoku".
_BLOCKED: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf ~",
    "sudo ",
    "shutdown",
    "reboot",
    "> /dev/",
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/urandom",
    ":(){ :|:& };:",   # fork bomb
)


def is_dangerous(command: str) -> bool:
    """Return True if *command* matches any blocked pattern."""
    return any(pat in command for pat in _BLOCKED)
