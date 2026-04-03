"""Three-layer context compaction to keep conversations from growing unbounded.

Layer 1 — micro_compact (every turn, silent):
  Old tool-result messages are replaced with one-line placeholders.

Layer 2 — auto_compact (when token estimate > threshold):
  Full transcript saved to .transcripts/; LLM generates a summary;
  all messages replaced with [summary, ack].

Layer 3 — compact tool (model-initiated):
  The model calls compact() to request immediate Layer-2 compaction.
  A flag is set; the actual compaction happens at the start of the
  next loop iteration so the tool result is included in what gets summarised.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


def estimate_tokens(messages: list) -> int:
    """Rough estimate: 1 token ≈ 4 chars of string representation."""
    return len(str(messages)) // 4


def micro_compact(messages: list, keep_recent: int = 3) -> None:
    """Replace the content of old ToolMessages with compact placeholders.

    Mutates *messages* in place.
    """
    # Build id -> tool_name map from AIMessage tool_calls
    id_to_name: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in (msg.tool_calls or []):
                id_to_name[tc["id"]] = tc["name"]

    tool_indices = [
        (i, msg) for i, msg in enumerate(messages) if isinstance(msg, ToolMessage)
    ]
    if len(tool_indices) <= keep_recent:
        return

    for i, msg in tool_indices[:-keep_recent]:
        if isinstance(msg.content, str) and len(msg.content) > 100:
            tool_name = id_to_name.get(msg.tool_call_id, "unknown")
            messages[i] = ToolMessage(
                content=f"[Previous: used {tool_name}]",
                tool_call_id=msg.tool_call_id,
            )


def auto_compact(
    messages: list,
    client: ChatOllama,
    transcripts_dir: Path,
) -> list:
    """Save the full transcript and replace messages with an LLM summary.

    Returns the new (short) message list.
    """
    transcripts_dir.mkdir(exist_ok=True)
    ts = int(time.time())
    transcript_path = transcripts_dir / f"transcript_{ts}.jsonl"

    # Serialize messages as readable JSONL records (type + content as text)
    with open(transcript_path, "w", encoding="utf-8") as f:
        for msg in messages:
            record = {
                "type": type(msg).__name__,
                "content": str(msg.content)[:2000],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[compact: transcript saved to {transcript_path}]")

    # Build a plain-text representation for the summarisation prompt
    conversation_text = "\n".join(
        f"[{type(msg).__name__}]: {str(msg.content)[:400]}"
        for msg in messages
    )[:80_000]

    prompt = (
        "Summarise this AI coding-agent conversation for continuity.\n"
        "Include:\n"
        "  1. What was accomplished\n"
        "  2. Current state and next steps\n"
        "  3. Key decisions or findings\n\n"
        + conversation_text
    )
    summary = client.invoke([HumanMessage(content=prompt)]).content

    return [
        HumanMessage(
            content=(
                f"[Context compressed — full transcript at {transcript_path}]\n\n"
                + summary
            )
        ),
        AIMessage(content="Understood. Continuing with the summarised context."),
    ]


class CompactManager:
    """Orchestrates all three compaction layers."""

    def __init__(
        self,
        client: ChatOllama,
        transcripts_dir: Path,
        threshold: int = 50_000,
        keep_recent: int = 3,
    ) -> None:
        self.client = client
        self.transcripts_dir = transcripts_dir
        self.threshold = threshold
        self.keep_recent = keep_recent
        self._manual_requested = False

    def request_manual(self) -> None:
        """Called by the compact tool to schedule immediate compaction."""
        self._manual_requested = True

    def process(self, messages: list) -> None:
        """Run micro-compact, then auto-compact if needed. Mutates *messages*."""
        micro_compact(messages, self.keep_recent)

        should_compact = (
            self._manual_requested
            or estimate_tokens(messages) > self.threshold
        )
        if should_compact:
            kind = "manual" if self._manual_requested else "auto"
            print(f"[compact: {kind}]")
            self._manual_requested = False
            new_messages = auto_compact(messages, self.client, self.transcripts_dir)
            messages[:] = new_messages


def create_compact_tool(manager: CompactManager):
    @tool
    def compact(focus: str = "") -> str:
        """Trigger immediate context compression to free up the conversation window.

        Args:
            focus: Optional hint about what to preserve in the summary.
        """
        manager.request_manual()
        hint = f" (focus: {focus})" if focus else ""
        return f"Compression scheduled{hint}. It will run before the next LLM call."

    return compact
