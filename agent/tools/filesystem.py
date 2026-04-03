"""Core filesystem tools: bash, read_file, write_file, edit_file.

All tools are scoped to a single *workdir* via path-traversal protection.
Returns (tools_list, run_bash_fn) so callers that need the raw bash runner
(e.g. BackgroundManager) can reuse it without importing subprocess directly.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from agent.tools._safety import is_dangerous

_BASH_TIMEOUT = 120  # seconds


def _make_safe_path(workdir: Path) -> Callable[[str], Path]:
    def safe_path(p: str) -> Path:
        resolved = (workdir / p).resolve()
        if not resolved.is_relative_to(workdir):
            raise ValueError(f"Path escapes workspace: {p}")
        return resolved
    return safe_path


def _make_bash_runner(workdir: Path) -> Callable[[str], str]:
    def run_bash(command: str) -> str:
        if is_dangerous(command):
            return "Error: Dangerous command blocked"
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=_BASH_TIMEOUT,
            )
            out = (result.stdout + result.stderr).strip()
            return out[:50_000] if out else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Timeout ({_BASH_TIMEOUT}s)"
    return run_bash


def create_filesystem_tools(
    workdir: Path,
) -> tuple[list, Callable[[str], str]]:
    """Create filesystem tools bound to *workdir*.

    Returns:
        (tools, run_bash): the tool list and the raw bash runner so
        BackgroundManager can reuse the same safety-checked runner.
    """
    safe_path = _make_safe_path(workdir)
    run_bash = _make_bash_runner(workdir)

    @tool
    def bash(command: str) -> str:
        """Run a shell command in the workspace directory (blocking, 120 s timeout)."""
        return run_bash(command)

    @tool
    def read_file(path: str, limit: int = None) -> str:
        """Read a workspace file. *limit* caps the number of lines returned."""
        try:
            lines = safe_path(path).read_text().splitlines()
            if limit and limit < len(lines):
                lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
            return "\n".join(lines)[:50_000]
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write *content* to a workspace file, creating parent directories as needed."""
        try:
            fp = safe_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
            return f"Wrote {len(content)} bytes to {path}"
        except Exception as exc:
            return f"Error: {exc}"

    @tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of *old_text* with *new_text* in a workspace file."""
        try:
            fp = safe_path(path)
            content = fp.read_text()
            if old_text not in content:
                return f"Error: old_text not found in {path}"
            fp.write_text(content.replace(old_text, new_text, 1))
            return f"Edited {path}"
        except Exception as exc:
            return f"Error: {exc}"

    return [bash, read_file, write_file, edit_file], run_bash
