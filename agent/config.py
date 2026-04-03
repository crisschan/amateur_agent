from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    """Central configuration for the agent.

    All feature flags, paths, and model settings live here so nothing
    is hard-coded in individual modules.
    """

    # LLM backend
    model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "kimi-k2.5:cloud")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    temperature: float = 0.2
    max_tokens: int = 4096

    # Working directory — set at construction time, not at import time
    workdir: Path = field(default_factory=Path.cwd)

    # Context-compaction knobs
    context_threshold: int = 50_000   # ~chars before auto-compact kicks in
    keep_recent_tools: int = 3        # tool results to keep verbatim in micro-compact

    # Todo nag: remind the model to update todos every N tool-call rounds
    todo_nag_interval: int = 3

    # Feature flags — disable capabilities you don't need
    enable_todo: bool = True          # in-memory todo list
    enable_tasks: bool = True         # persistent JSON task store
    enable_skills: bool = True        # on-demand SKILL.md loading
    enable_background: bool = True    # background thread execution
    enable_subagent: bool = True      # subagent spawning
    enable_compact: bool = True       # context compaction

    # ------------------------------------------------------------------ paths
    @property
    def skills_dir(self) -> Path:
        return self.workdir / "skills"

    @property
    def tasks_dir(self) -> Path:
        return self.workdir / ".tasks"

    @property
    def transcripts_dir(self) -> Path:
        return self.workdir / ".transcripts"
