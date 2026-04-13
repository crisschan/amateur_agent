#!/usr/bin/env python3
"""Amateur Agent -- interactive AI coding agent CLI.

Usage:
    python main.py            # default settings
    python main.py --config agent.json          # load config file
    python main.py --config agent.json --model qwen2.5-coder  # override model
    python main.py --no-background         # disable background tasks
"""
from __future__ import annotations

import argparse
from pathlib import Path

from agent.agent import Agent
from agent.config import AgentConfig


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Amateur Agent -- AI coding agent REPL backed by Ollama"
    )
    p.add_argument("--config", default=None, type=Path,
        help="Path to agent.json config file (default: auto-detect agent.json in cwd)")
    p.add_argument("--model", default=None, help="Ollama model name (overrides config)")
    p.add_argument("--workdir", default=None, type=Path, help="Working directory (overrides config)")
    p.add_argument("--workspace", default=None, type=Path, help="Workspace boundary for file ops (overrides config)")
    p.add_argument("--no-todo", action="store_true", help="Disable in-memory todo list")
    p.add_argument("--no-tasks", action="store_true", help="Disable persistent task store")
    p.add_argument("--no-skills", action="store_true", help="Disable skill loading")
    p.add_argument("--no-background", action="store_true", help="Disable background execution")
    p.add_argument("--no-subagent", action="store_true", help="Disable subagent spawning")
    p.add_argument("--no-compact", action="store_true", help="Disable context compaction")
    return p.parse_args()


def _load_config(args: argparse.Namespace) -> AgentConfig:
    """Build AgentConfig: file defaults -> agent.json -> CLI overrides."""
    # 1. Determine config file path
    config_path: Path | None = None
    if args.config:
        config_path = args.config.resolve()
    else:
        candidate = Path.cwd() / "agent.json"
        if candidate.exists():
            config_path = candidate

    # 2. Load from file or use defaults
    if config_path is not None:
        cfg = AgentConfig.from_file(config_path)
    else:
        cfg = AgentConfig()

    # 3. Apply CLI overrides (only when explicitly provided)
    if args.model:
        cfg.model = args.model
    if args.workdir:
        cfg.workdir = args.workdir.resolve()
    if args.workspace:
        cfg.workspace = args.workspace.resolve()
    if args.no_todo:
        cfg.enable_todo = False
    if args.no_tasks:
        cfg.enable_tasks = False
    if args.no_skills:
        cfg.enable_skills = False
    if args.no_background:
        cfg.enable_background = False
    if args.no_subagent:
        cfg.enable_subagent = False
    if args.no_compact:
        cfg.enable_compact = False

    return cfg


def main() -> None:
    args = parse_args()
    cfg = _load_config(args)
    Agent(cfg).repl()


if __name__ == "__main__":
    main()
