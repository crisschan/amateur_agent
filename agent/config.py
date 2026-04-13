from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class AgentConfig:
    """Central configuration for the agent.

    All feature flags, paths, and model settings live here so nothing
    is hard-coded in individual modules.

    Load priority: dataclass defaults < agent.json values < CLI overrides.
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

    # Working directory
    workdir: Path = field(default_factory=Path.cwd)

    # Workspace boundary -- if set, all file ops are restricted to this path.
    # Defaults to workdir when not explicitly configured.
    workspace: Optional[Path] = None

    # Context-compaction knobs
    context_threshold: int = 50_000
    keep_recent_tools: int = 3

    # Todo nag
    todo_nag_interval: int = 3

    # Feature flags
    enable_todo: bool = True
    enable_tasks: bool = True
    enable_skills: bool = True
    enable_background: bool = True
    enable_subagent: bool = True
    enable_compact: bool = True

    # --------- paths

    @property
    def effective_workspace(self) -> Path:
        """The enforced file-operation boundary. Falls back to workdir."""
        return self.workspace if self.workspace is not None else self.workdir

    @property
    def skills_dir(self) -> Path:
        return self.workdir / "skills"

    @property
    def tasks_dir(self) -> Path:
        return self.workdir / ".tasks"

    @property
    def transcripts_dir(self) -> Path:
        return self.workdir / ".transcripts"

    # ------- class methods

    @classmethod
    def from_file(cls, config_path: Path) -> "AgentConfig":
        """Load config from an agent.json file.

        Only keys present in the file override defaults; missing keys keep
        their dataclass defaults. Unknown keys are silently ignored.
        Paths are resolved relative to the config file directory.
        """
        data: dict = json.loads(config_path.read_text())
        cfg = cls()
        config_dir = config_path.parent.resolve()

        str_fields = {"model", "base_url"}
        float_fields = {"temperature"}
        int_fields = {"max_tokens", "context_threshold", "keep_recent_tools", "todo_nag_interval"}
        bool_fields = {
          "enable_todo", "enable_tasks", "enable_skills",
          "enable_background", "enable_subagent", "enable_compact",
        }
        path_fields = {"workdir", "workspace"}

        for key, val in data.items():
          if key in str_fields:
                setattr(cfg, key, str(val))
          elif key in float_fields:
                setattr(cfg, key, float(val))
          elif key in int_fields:
                setattr(cfg, key, int(val))
          elif key in bool_fields:
                setattr(cfg, key, bool(val))
          elif key in path_fields:
                setattr(cfg, key, (config_dir / val).resolve())

        return cfg
