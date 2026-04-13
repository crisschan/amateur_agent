"""Agent: the top-level class that assembles tools and runs the REPL.

Responsibilities:
  - Instantiate all managers from AgentConfig
  - Build tool lists (parent set and child set for subagents)
  - Construct the system prompt from enabled features
  - Expose run_query() for programmatic use and repl() for interactive use
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from agent.config import AgentConfig
from agent.loop import AgentLoop, LoopConfig
from agent.memory.compact import CompactManager, create_compact_tool
from agent.tools.background import BackgroundManager, create_background_tools
from agent.tools.filesystem import create_filesystem_tools
from agent.tools.skills import SkillLoader, create_skill_tool
from agent.tools.subagent import create_subagent_tool
from agent.tools.tasks import TaskManager, create_task_tools
from agent.tools.todo import TodoManager, create_todo_tool


class Agent:
    """Full-featured coding agent.

    Assembles all enabled capabilities from an AgentConfig, then provides
    a REPL or single-query interface.

    Example::

        agent = Agent()          # uses defaults + env vars
        agent.repl()             # start interactive session

        # Or programmatically:
        agent = Agent(AgentConfig(enable_background=False))
        response = agent.run_query("list all Python files")
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self._build()

    # ----------------------------------------------------------------- private

    def _build(self) -> None:
        cfg = self.config

        # LLM client (no tools bound yet)
        self._client = ChatOllama(
            model=cfg.model,
            base_url=cfg.base_url,
            temperature=cfg.temperature,
            num_predict=cfg.max_tokens,
        )

        # Core filesystem tools — always enabled
        fs_tools, _run_bash = create_filesystem_tools(cfg.workdir, cfg.workspace)
        tools: list = list(fs_tools)

        # Tools available to subagent children (filesystem only, + skills below)
        child_tools: list = list(fs_tools)

        # Optional: in-memory todo list
        todo_mgr: TodoManager | None = None
        if cfg.enable_todo:
            todo_mgr = TodoManager()
            tools.append(create_todo_tool(todo_mgr))
            # Intentionally NOT added to child_tools — children focus on subtasks

        # Optional: persistent JSON task store
        if cfg.enable_tasks:
            task_mgr = TaskManager(cfg.tasks_dir)
            tools.extend(create_task_tools(task_mgr))
            # Intentionally NOT added to child_tools

        # Optional: on-demand skill loading
        skill_descriptions = ""
        if cfg.enable_skills:
            skill_loader = SkillLoader(cfg.skills_dir)
            skill_tool = create_skill_tool(skill_loader)
            tools.append(skill_tool)
            child_tools.append(skill_tool)   # children benefit from skills
            skill_descriptions = skill_loader.get_descriptions()

        # Optional: background task execution
        bg_mgr: BackgroundManager | None = None
        if cfg.enable_background:
            bg_mgr = BackgroundManager(cfg.workdir)
            tools.extend(create_background_tools(bg_mgr))
            # Intentionally NOT added to child_tools

        # Optional: context compaction
        compact_mgr: CompactManager | None = None
        if cfg.enable_compact:
            compact_mgr = CompactManager(
                client=self._client,
                transcripts_dir=cfg.transcripts_dir,
                threshold=cfg.context_threshold,
                keep_recent=cfg.keep_recent_tools,
            )
            tools.append(create_compact_tool(compact_mgr))
            # Intentionally NOT added to child_tools

        # Optional: subagent spawning — must be last so child_tools is finalised
        if cfg.enable_subagent:
            task_tool = create_subagent_tool(self._client, cfg.workdir, child_tools)
            tools.append(task_tool)

        # Bind tools and build loop
        self._tool_map = {t.name: t for t in tools}
        client_with_tools = self._client.bind_tools(tools)
        self._loop = AgentLoop(
            client_with_tools=client_with_tools,
            tool_map=self._tool_map,
            config=LoopConfig(
                compact_manager=compact_mgr,
                bg_manager=bg_mgr,
                todo_manager=todo_mgr,
                todo_nag_interval=cfg.todo_nag_interval,
            ),
        )

        self._system_prompt = self._build_system(skill_descriptions)

    def _build_system(self, skill_descriptions: str) -> str:
        cfg = self.config
        parts = [
            f"You are a coding agent working in {cfg.workdir}.",
            "Use your tools to solve tasks. Act, don't explain.",
        ]
        if cfg.workspace is not None:
            parts.append(
                f"WORKSPACE RESTRICTION: You are restricted to {cfg.workspace}. "
                "All file operations must stay within this directory. "
              "Do not attempt to read, write, or execute commands that access paths outside it."
            )
        if cfg.enable_todo:
            parts.append(
                "Use the todo tool to plan and track multi-step work within this session."
            )
        if cfg.enable_tasks:
            parts.append(
                "Use task_create/task_update/task_list/task_get for persistent tasks "
                "that survive context resets."
            )
        if cfg.enable_skills and skill_descriptions:
            parts.append(
                f"\nSkills available (load full instructions with load_skill <name>):\n"
                + skill_descriptions
            )
        if cfg.enable_background:
            parts.append(
                "Use background_run for long-running commands so you can keep working "
                "while they execute."
            )
        if cfg.enable_compact:
            parts.append("Use compact to manually free up the context window when needed.")
        if cfg.enable_subagent:
            parts.append(
                "Use task to delegate exploration or subtasks to a subagent with a "
                "fresh context; it returns only a summary."
            )
        return "\n".join(parts)

    # ------------------------------------------------------------------ public

    def run_query(self, query: str, history: list | None = None) -> str:
        """Run a single query and return the final text response.

        Args:
            query: The user's input.
            history: Existing message history. A fresh history is created when
                     omitted, so each call is stateless by default.

        Returns:
            The model's final text response (may be empty if it only used tools).
        """
        if history is None:
            history = [SystemMessage(content=self._system_prompt)]
        history.append(HumanMessage(content=query))
        self._loop.run(history)
        last = history[-1]
        return last.content if isinstance(last, AIMessage) and last.content else ""

    def repl(self, prompt: str = "amateur_agent") -> None:
        """Start an interactive REPL session.

        Maintains full conversation history across turns.
        Type 'q', 'exit', or press Ctrl-C / Ctrl-D to quit.
        """
        history = [SystemMessage(content=self._system_prompt)]
        enabled = [
            name for name, flag in [
                ("todo", self.config.enable_todo),
                ("tasks", self.config.enable_tasks),
                ("skills", self.config.enable_skills),
                ("background", self.config.enable_background),
                ("compact", self.config.enable_compact),
                ("subagent", self.config.enable_subagent),
            ] if flag
        ]
        print(
            f"\033[32m[Agent ready]\033[0m "
            f"model={self.config.model}  "
            f"features=[{', '.join(enabled)}]  "
            f"workdir={self.config.workdir}"
        )
        print("Type 'q' or press Ctrl-C to quit.\n")

        while True:
            try:
                query = input(f"\033[36m{prompt} >> \033[0m")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if query.strip().lower() in ("q", "exit"):
                break
            if not query.strip():
                # 空输入不处理，继续等待
                continue
            history.append(HumanMessage(content=query))
            try:
                self._loop.run(history)
                last = history[-1]
                if isinstance(last, AIMessage) and last.content:
                    print(last.content)
            except Exception as e:
                print(f"\n\033[31mError: {e}\033[0m")
                import traceback
                traceback.print_exc()
            # 强制换行并清空行缓冲，防止提示符重叠
            import sys
            sys.stdout.write('\n')
            sys.stdout.flush()
