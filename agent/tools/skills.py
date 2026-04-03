"""On-demand skill loading from SKILL.md files.

Two-layer injection to keep the system prompt small:
  Layer 1 (cheap)  — skill names + short descriptions in the system prompt
  Layer 2 (on demand) — full body returned via the load_skill tool result
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from langchain_core.tools import tool


class SkillLoader:
    """Scans *skills_dir* for SKILL.md files with YAML front-matter."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self.skills: dict[str, dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            meta, body = self._parse_frontmatter(f.read_text())
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body, "path": str(f)}

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        """Split YAML front-matter from body. Returns ({}, text) if no front-matter."""
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()

    # ----------------------------------------------------------- public helpers

    def get_descriptions(self) -> str:
        """Layer 1: short one-liners for the system prompt."""
        if not self.skills:
            return "(no skills available)"
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "No description")
            tags = skill["meta"].get("tags", "")
            line = f"  - {name}: {desc}"
            if tags:
                line += f" [{tags}]"
            lines.append(line)
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        """Layer 2: full skill body wrapped in <skill> tags."""
        skill = self.skills.get(name)
        if not skill:
            available = ", ".join(self.skills) if self.skills else "none"
            return f"Error: Unknown skill '{name}'. Available: {available}"
        return f'<skill name="{name}">\n{skill["body"]}\n</skill>'


def create_skill_tool(loader: SkillLoader):
    @tool
    def load_skill(name: str) -> str:
        """Load the full instructions for a named skill.

        Call this before tackling a specialised task.
        The system prompt lists available skill names.
        """
        return loader.get_content(name)

    return load_skill
