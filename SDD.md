# Software Design Document — Amateur Agent

**Version:** 1.0  
**Date:** 2026-04-13  
**Status:** Draft

---

## 1. Overview

Amateur Agent is an interactive AI coding agent CLI. It connects a local LLM (via Ollama) to a set of tools for file manipulation, shell execution, task tracking, and background processing. The user types requests in a REPL; the agent reasons, calls tools, and loops until the task is done.

### 1.1 Goals

- Provide a local, self-contained coding assistant that can read, write, and execute code
- Keep context manageable across long sessions via automatic compaction
- Allow parallel work via background execution and subagent delegation
- Be modular: every feature can be disabled independently

### 1.2 Non-Goals

- Cloud deployment or multi-user support
- Sandboxed execution (commands run with the user's OS permissions)
- GUI or web interface

---

## 2. Architecture

### 2.1 High-Level Structure

```
main.py
  └─ Agent (agent/agent.py)
       ├─ AgentConfig (agent/config.py)
       ├─ AgentLoop (agent/loop.py)
       │    └─ LoopConfig (middleware wiring)
       ├─ Tools
       │    ├─ Filesystem  (agent/tools/filesystem.py)
       │    ├─ Todo        (agent/tools/todo.py)
       │    ├─ Tasks       (agent/tools/tasks.py)
       │    ├─ Background  (agent/tools/background.py)
       │    ├─ Skills      (agent/tools/skills.py)
       │    └─ Subagent    (agent/tools/subagent.py)
       └─ Memory
            └─ CompactManager (agent/memory/compact.py)
```

### 2.2 Request Lifecycle

```
User types input
      │
      ▼
HumanMessage appended to history
      │
      ▼
AgentLoop.run(history)
  ┌───────────────────────────────────────┐
  │  Pre-call middleware                  │
  │  ├─ Drain background notifications   │
  │  ├─ Inject todo-nag (if due)         │
  │  └─ Run context compaction           │
  │                                       │
  │  LLM call → AIMessage                │
  │                                       │
  │  No tool calls? → return             │
  │                                       │
  │  Tool calls? → execute each          │
  │  └─ Append ToolMessage results       │
  │  └─ Loop back to pre-call            │
  └───────────────────────────────────────┘
      │
      ▼
Print final AIMessage to user
```

---

## 3. Components

### 3.1 Configuration — `agent/config.py`

`AgentConfig` is a dataclass that holds all runtime settings. Every feature flag and tuning parameter lives here.

| Field | Default | Purpose |
|---|---|---|
| `model` | `OLLAMA_MODEL` env or `kimi-k2.5:cloud` | Ollama model name |
| `base_url` | `OLLAMA_BASE_URL` env or `http://localhost:11434` | Ollama endpoint |
| `temperature` | `0.2` | LLM sampling temperature |
| `max_tokens` | `4096` | Max tokens per LLM response |
| `workdir` | `Path.cwd()` | Workspace root; all file ops are scoped here |
| `context_threshold` | `50000` | Char count that triggers auto-compact |
| `keep_recent_tools` | `3` | Tool results preserved verbatim during micro-compact |
| `todo_nag_interval` | `3` | Rounds before reminding model to update todos |
| `enable_todo` | `True` | In-memory todo list |
| `enable_tasks` | `True` | Persistent JSON task store |
| `enable_skills` | `True` | On-demand skill loading |
| `enable_background` | `True` | Background shell execution |
| `enable_subagent` | `True` | Subagent spawning |
| `enable_compact` | `True` | Context compaction |

Derived paths (read-only properties):
- `skills_dir` → `workdir/skills`
- `tasks_dir` → `workdir/.tasks`
- `transcripts_dir` → `workdir/.transcripts`

### 3.2 Agent — `agent/agent.py`

Top-level class. Owns the REPL and assembles all subsystems.

**Initialization (`_build`):**
1. Create `ChatOllama` client
2. Build filesystem tools (always enabled)
3. Conditionally instantiate managers based on feature flags
4. Bind all tools to the client
5. Create `AgentLoop` with `LoopConfig`
6. Build system prompt

**Public API:**

```python
agent = Agent(config)
agent.repl()                          # interactive session
agent.run_query("list Python files")  # single stateless query
```

**System Prompt** is assembled from enabled features. Each manager contributes a short guidance block. The model is told to act, not explain.

### 3.3 Agent Loop — `agent/loop.py`

Implements the LLM ↔ tool cycle. Stateless between turns; the caller owns the message list.

**`LoopConfig`** wires in optional middleware:
- `compact_manager` — handles compaction
- `bg_manager` — drains background notifications
- `todo_manager` — tracks todo usage for nag counter
- `todo_nag_interval` — rounds before nag

**`AgentLoop.run(messages)`** — executes one full turn and returns when the model stops requesting tools.

### 3.4 Filesystem Tools — `agent/tools/filesystem.py`

Always enabled. All paths are validated to stay within `workdir`.

| Tool | Args | Notes |
|---|---|---|
| `bash` | `command: str` | 120s timeout; dangerous commands blocked |
| `read_file` | `path: str, limit: int = None` | Output capped at 50 KB |
| `write_file` | `path: str, content: str` | Creates parent directories |
| `edit_file` | `path: str, old_text: str, new_text: str` | Replaces first occurrence |

**Path safety** (`_make_safe_path`): resolves the path and checks it is relative to `workdir`. Raises `ValueError` if not.

**Dangerous command detection** (`_safety.py`): string-match against a blocklist (`rm -rf /`, `sudo`, `shutdown`, `reboot`, fork bomb, etc.).

### 3.5 Todo Manager — `agent/tools/todo.py`

In-memory list of up to 20 items. Resets when the process exits.

**Schema:**
```python
{"id": str, "text": str, "status": "pending" | "in_progress" | "completed"}
```

**Constraints:** only one item may be `in_progress` at a time.

**Tool:** `todo(items: list) → str` — replaces the entire list on each call.

**Nag mechanism:** `AgentLoop` counts rounds since the last `todo` call. When the count exceeds `todo_nag_interval`, a reminder is injected as a `HumanMessage` before the next LLM call.

### 3.6 Task Manager — `agent/tools/tasks.py`

Persistent task store. Each task is a JSON file in `.tasks/`.

**Schema:**
```json
{
  "id": 1,
  "subject": "...",
  "description": "...",
  "status": "pending | in_progress | completed",
  "blockedBy": [2, 3],
  "blocks": [4],
  "owner": "..."
}
```

**Dependency graph:** bidirectional. When task A is set to block task B, B's `blockedBy` is updated. When a task completes, it is removed from all other tasks' `blockedBy` lists.

| Tool | Purpose |
|---|---|
| `task_create(subject, description)` | Create a new task |
| `task_update(task_id, status, add_blocked_by, add_blocks)` | Update status or dependencies |
| `task_list()` | List all tasks |
| `task_get(task_id)` | Get full task details |

### 3.7 Background Manager — `agent/tools/background.py`

Runs shell commands in daemon threads so the agent can continue working.

**Execution:**
- `background_run(command)` — safety check, spawn daemon thread, return `task_id` (UUID[:8]) immediately
- Thread runs subprocess with 300s timeout, captures stdout+stderr (capped at 50 KB), stores result, queues notification

**Notification drain:** before each LLM call, `AgentLoop` drains the notification queue and injects completed task summaries as `HumanMessage` entries.

**`check_background(task_id=None)`** — returns status of one task or all tasks.

### 3.8 Skill Loader — `agent/tools/skills.py`

Two-layer skill injection to keep the system prompt lean.

**Layer 1 (always):** skill names + one-line descriptions injected into system prompt at startup.

**Layer 2 (on demand):** `load_skill(name)` returns the full SKILL.md body when the model needs it.

**SKILL.md format:**
```markdown
---
name: skill-name
description: One-line description
tags: tag1, tag2
---

## Full instructions...
```

Skills are discovered by scanning `skills/*/SKILL.md` at startup.

### 3.9 Subagent — `agent/tools/subagent.py`

Spawns a child agent with a fresh context and a reduced tool set.

**Child tools:** filesystem + skills only. No task/todo/background/compact tools. No recursive spawning.

**`task(prompt, description)`** — creates a child `Agent`, runs it to completion, returns the final `AIMessage` content as a string.

**Isolation:** the child has no access to the parent's message history, preventing context leakage and unbounded recursion.

### 3.10 Compact Manager — `agent/memory/compact.py`

Three-layer strategy to prevent context overflow.

**Layer 1 — Micro-compact (every turn, silent):**
- Replaces old `ToolMessage` content with one-line placeholders
- Keeps the last `keep_recent_tools` results verbatim
- Mutates the message list in place; no LLM call needed

**Layer 2 — Auto-compact (threshold-triggered):**
- Triggered when `estimate_tokens(messages) > context_threshold`
- Saves full transcript to `.transcripts/transcript_{ts}.jsonl` (JSONL format)
- Calls LLM to generate a continuity summary
- Replaces all messages with `[HumanMessage: summary] + [AIMessage: ack]`

**Layer 3 — Manual compact (model-initiated):**
- Model calls `compact(focus="...")` tool
- Sets a flag; actual compaction runs before the next LLM call so the tool result is included in the summary

**Token estimation:** `len(str(messages)) // 4`

---

## 4. Data Flows

### 4.1 File Operations

```
Model calls read_file("src/main.py")
  → _make_safe_path validates path stays in workdir
  → file read, output capped at 50 KB
  → ToolMessage returned to model
```

### 4.2 Background Task Lifecycle

```
Model calls background_run("pytest tests/")
  → safety check passes
  → daemon thread spawned, task_id returned immediately
  → [thread] subprocess runs, result stored, notification queued
  → [next turn] AgentLoop drains queue, injects HumanMessage
  → model learns task completed
```

### 4.3 Context Compaction

```
[Every turn]
  micro-compact: old tool results → placeholders

[When chars > threshold]
  save transcript → .transcripts/
  LLM generates summary
  messages reset to [summary, ack]

[Model calls compact()]
  flag set → compaction runs before next LLM call
```

### 4.4 Subagent Delegation

```
Model calls task("refactor auth module")
  → child Agent created (filesystem + skills tools only)
  → child runs its own AgentLoop to completion
  → child's final AIMessage returned as string
  → parent receives summary as ToolMessage
```

---

## 5. Security

### 5.1 Path Traversal

Every path passed to filesystem tools is resolved and checked against `workdir`. Paths that escape the workspace raise `ValueError` before any I/O occurs.

### 5.2 Dangerous Command Blocking

String-match blocklist applied to all shell execution (foreground and background):

```
rm -rf /    rm -rf ~    sudo     shutdown    reboot
> /dev/     mkfs        dd if=/dev/zero      dd if=/dev/urandom
:(){ :|:& };:   (fork bomb)
```

**Known limitation:** obfuscated commands (e.g., base64-encoded payloads) are not detected.

### 5.3 Subagent Isolation

Child agents receive only filesystem and skill tools. They cannot create tasks, spawn further subagents, or access the parent's conversation history.

### 5.4 No Sandboxing

Commands execute with the user's OS permissions. There are no resource limits (CPU, memory, disk). This is a deliberate trade-off for simplicity in a local developer tool.

---

## 6. Error Handling

| Scenario | Behavior |
|---|---|
| Tool raises exception | Caught; error string returned as `ToolMessage`; model can retry |
| Bash timeout (120s) | Returns `"Error: Timeout (120s)"` |
| Background task timeout (300s) | Task status set to `"timeout"` |
| LLM call failure | Exception propagates to REPL; printed as traceback |
| Path escapes workdir | `ValueError` returned as tool error |
| Dangerous command | `ValueError` returned as tool error |

There is no automatic retry logic. The model sees the error and decides how to proceed.

---

## 7. Extension Points

### 7.1 Adding a Tool

1. Create `agent/tools/my_tool.py` with `@tool`-decorated functions
2. Add a factory function `create_my_tools(config) -> list`
3. Instantiate in `Agent._build()` behind a feature flag
4. Add to the `tools` list passed to the client

### 7.2 Adding a Skill

Create `skills/my-skill/SKILL.md` with YAML front-matter. It is auto-discovered at startup.

### 7.3 Adding Loop Middleware

Add a field to `LoopConfig` and call it in the pre-call section of `AgentLoop.run()`.

### 7.4 Changing the System Prompt

Edit `Agent._build_system()`. Each manager contributes a block; add or remove blocks as needed.

---

## 8. Configuration Reference

### 8.1 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `kimi-k2.5:cloud` | Default model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service URL |

### 8.2 CLI Flags

```
python main.py [options]

  --model MODEL        Ollama model name
  --workdir DIR        Workspace directory
  --no-todo            Disable in-memory todo list
  --no-tasks           Disable persistent task store
  --no-skills          Disable skill loading
  --no-background      Disable background execution
  --no-subagent        Disable subagent spawning
  --no-compact         Disable context compaction
```

### 8.3 Runtime Directories

| Path | Purpose |
|---|---|
| `skills/*/SKILL.md` | Skill definitions |
| `.tasks/task_N.json` | Persistent task files |
| `.transcripts/transcript_*.jsonl` | Compaction transcripts |

---

## 9. Known Limitations

| # | Issue | Impact |
|---|---|---|
| 1 | No max iteration limit in agent loop | Model could loop indefinitely |
| 2 | Dangerous command detection is string matching | Obfuscated commands bypass it |
| 3 | No OS-level sandboxing | Commands run with full user permissions |
| 4 | Symlinks not validated | Could escape workdir via symlink |
| 5 | No automated tests | Regressions not caught automatically |
| 6 | LLM call failures not retried | Single failure aborts the turn |

---

## 10. Dependencies

```
langchain-ollama    # LangChain Ollama integration
langchain-core      # Messages, tool abstractions
pyyaml              # SKILL.md front-matter parsing
```

**Runtime requirements:**
- Python 3.10+
- Ollama service running and accessible
- At least one model pulled (e.g., `ollama pull kimi-k2.5:cloud`)
