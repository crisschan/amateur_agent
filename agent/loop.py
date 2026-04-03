"""Core agent loop.

The loop is a pure while-loop that calls the LLM, executes tools, and
feeds results back until the model stops requesting tools.

Middleware is injected via LoopConfig — none of the feature-specific
managers are imported here, only their protocols are used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama

# Type aliases — avoid importing concrete classes to keep loop.py thin
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent.memory.compact import CompactManager
    from agent.tools.background import BackgroundManager
    from agent.tools.todo import TodoManager


@dataclass
class LoopConfig:
    """Middleware configuration for AgentLoop."""

    compact_manager: Optional["CompactManager"] = None
    bg_manager: Optional["BackgroundManager"] = None
    todo_manager: Optional["TodoManager"] = None

    # Name of the todo tool — used to detect when it was called so the nag
    # counter resets. Kept configurable to avoid hard-coding strings here.
    todo_tool_name: str = "todo"
    todo_nag_interval: int = 3   # remind after N consecutive rounds without todo update


class AgentLoop:
    """Drives the LLM ↔ tool interaction cycle with optional middleware.

    Usage:
        loop = AgentLoop(client_with_tools, tool_map, config)
        loop.run(messages)   # mutates messages in place
    """

    def __init__(
        self,
        client_with_tools: ChatOllama,
        tool_map: dict,
        config: LoopConfig,
    ) -> None:
        self.client = client_with_tools
        self.tool_map = tool_map
        self.config = config

    def run(self, messages: list) -> None:
        """Run until the model returns a response with no tool calls."""
        rounds_since_todo = 0

        while True:
            # ---- pre-call middleware ----------------------------------------

            # 1. Drain background-task completion notifications
            if self.config.bg_manager:
                notifs = self.config.bg_manager.drain()
                if notifs:
                    notif_text = "\n".join(
                        f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                        for n in notifs
                    )
                    messages.append(
                        HumanMessage(
                            content=f"<background-results>\n{notif_text}\n</background-results>"
                        )
                    )
                    messages.append(
                        AIMessage(content="Noted background task results.")
                    )

            # 2. Inject todo-nag reminder if the model has been ignoring todos
            cfg = self.config
            if (
                cfg.todo_manager
                and rounds_since_todo >= cfg.todo_nag_interval
            ):
                messages.append(
                    HumanMessage(content="<reminder>Update your todo list.</reminder>")
                )
                rounds_since_todo = 0

            # 3. Context compaction (micro always, auto/manual when needed)
            if cfg.compact_manager:
                cfg.compact_manager.process(messages)

            # ---- LLM call ---------------------------------------------------
            response = self.client.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                return  # model is done

            # ---- tool execution ---------------------------------------------
            used_todo = False
            for tc in response.tool_calls:
                fn = self.tool_map.get(tc["name"])
                try:
                    output = (
                        fn.invoke(tc["args"]) if fn
                        else f"Unknown tool: {tc['name']}"
                    )
                except Exception as exc:
                    output = f"Error: {exc}"

                print(f"\033[33m> {tc['name']}\033[0m: {str(output)[:200]}")
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=tc["id"])
                )

                if tc["name"] == cfg.todo_tool_name:
                    used_todo = True

            rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
