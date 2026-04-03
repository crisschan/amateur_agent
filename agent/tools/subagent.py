"""Subagent spawning: delegate subtasks with a fresh, isolated context.

The parent's conversation history stays clean; the subagent works in
its own message list, shares the filesystem, then returns only a summary.

Subagents intentionally receive a reduced tool set (filesystem + skills only)
to keep them focused and prevent accidental cross-contamination of task/todo
state or recursive spawning.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


def create_subagent_tool(
    client: ChatOllama,
    workdir: Path,
    child_tools: list,
):
    """Return a *task* tool that spawns a subagent with *child_tools*.

    Args:
        client: The LLM client (without tools bound — we bind child_tools here).
        workdir: Workspace path, embedded in the subagent system prompt.
        child_tools: Tools the subagent may use. Must NOT include the task tool
                     itself to prevent recursive spawning.
    """
    child_tool_map = {t.name: t for t in child_tools}
    child_client = client.bind_tools(child_tools)
    subagent_system = (
        f"You are a coding subagent at {workdir}. "
        "Complete the given task thoroughly using your tools, "
        "then return a concise summary of what you did and what you found."
    )

    def _run_child(messages: list) -> str:
        """Inner loop for the subagent — no recursion allowed."""
        while True:
            response = child_client.invoke(messages)
            messages.append(response)
            if not response.tool_calls:
                return response.content or ""
            for tc in response.tool_calls:
                fn = child_tool_map.get(tc["name"])
                try:
                    output = (
                        fn.invoke(tc["args"]) if fn
                        else f"Unknown tool: {tc['name']}"
                    )
                except Exception as exc:
                    output = f"Error: {exc}"
                print(f"  \033[35m[subagent] > {tc['name']}\033[0m: {str(output)[:200]}")
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=tc["id"])
                )

    @tool
    def task(prompt: str, description: str = "") -> str:
        """Delegate a subtask to a subagent with a fresh context window.

        The subagent has access to filesystem and skill tools but NOT
        task-management or background tools — it focuses on one job.
        Returns the subagent's summary when done.

        Args:
            prompt: Full instructions for the subagent.
            description: Short label shown in the console (optional).
        """
        label = description or prompt[:60]
        print(f"\033[35m[subagent spawned] {label}\033[0m")
        child_messages = [
            SystemMessage(content=subagent_system),
            HumanMessage(content=prompt),
        ]
        return _run_child(child_messages) or "(subagent produced no output)"

    return task
