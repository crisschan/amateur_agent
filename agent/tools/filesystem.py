'''Core filesystem tools: bash, read_file, write_file, edit_file.

All file tools are scoped to a workspace boundary via path-traversal protection.
When workspace is set, that path is used as the boundary; otherwise workdir is used.
The bash tool additionally checks absolute paths in commands against the workspace.
'''
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from langchain_core.tools import tool

from agent.tools._safety import is_dangerous

_BASH_TIMEOUT = 120  # seconds

# Absolute paths always allowed in bash commands (system paths)
_ALLOWED_PREFIXES = ("/tmp/", "/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr")


def _make_safe_path(workspace: Path) -> Callable[[str], Path]:
    '''Return a path validator scoped to workspace.'''
    def safe_path(p: str) -> Path:
        resolved = (workspace / p).resolve()
        if not resolved.is_relative_to(workspace):
            raise ValueError(f'Path escapes workspace: {p}')
        return resolved
    return safe_path

def _check_workspace_paths(command: str, workspace: Path) -> Optional[str]:
    '''Return an error string if command references absolute paths outside workspace.
    Returns None when the command is safe to run.
    '''
    abs_paths = re.findall(r'(?<![\w])/(?:[\w./-]+)', command)
    for p in abs_paths:
        if any(p.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
            continue
        try:
            resolved = Path(p).resolve()
        except Exception:
            continue
        if not resolved.is_relative_to(workspace):
            return (
                f'Workspace violation: {p!r} is outside workspace {str(workspace)!r}. '
                'Only paths within the workspace are allowed.'
            )
    return None


def _make_bash_runner(workdir: Path, workspace: Optional[Path] = None) -> Callable[[str], str]:
    def run_bash(command: str) -> str:
        if is_dangerous(command):
            return 'Error: Dangerous command blocked'
        if workspace is not None:
            err = _check_workspace_paths(command, workspace)
            if err:
                return f'Error: {err}'
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
            return out[:50_000] if out else '(no output)'
        except subprocess.TimeoutExpired:
            return f'Error: Timeout ({_BASH_TIMEOUT}s)'
    return run_bash


def create_filesystem_tools(
    workdir: Path,
    workspace: Optional[Path] = None,
) -> tuple[list, Callable[[str], str]]:
    '''Create filesystem tools bound to workdir with workspace as the file boundary.

    Args:
        workdir: Directory where shell commands run (cwd for bash).
        workspace: File-operation boundary. Defaults to workdir when None.

    Returns:
        (tools, run_bash): the tool list and the raw bash runner.
    '''
    effective = workspace if workspace is not None else workdir
    safe_path = _make_safe_path(effective)
    run_bash = _make_bash_runner(workdir, workspace)

    @tool
    def bash(command: str) -> str:
        '''Run a shell command in the workspace directory (blocking, 120 s timeout).'''
        return run_bash(command)

    @tool
    def read_file(path: str, limit: int = None) -> str:
        '''Read a workspace file. limit caps the number of lines returned.'''
        try:
            lines = safe_path(path).read_text().splitlines()
            if limit and limit < len(lines):
                lines = lines[:limit] + [f'... ({len(lines) - limit} more lines)']
            return '\n'.join(lines)[:50_000]
        except Exception as exc:
            return f'Error: {exc}'

    @tool
    def write_file(path: str, content: str) -> str:
        '''Write content to a workspace file, creating parent directories as needed.'''
        try:
            fp = safe_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
            return f'Wrote {len(content)} bytes to {path}'
        except Exception as exc:
            return f'Error: {exc}'

    @tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        '''Replace the first occurrence of old_text with new_text in a workspace file.'''
        try:
            fp = safe_path(path)
            content = fp.read_text()
            if old_text not in content:
                return f'Error: old_text not found in {path}'
            fp.write_text(content.replace(old_text, new_text, 1))
            return f'Edited {path}'
        except Exception as exc:
            return f'Error: {exc}'

    return [bash, read_file, write_file, edit_file], run_bash
