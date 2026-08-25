"""
Agent Definition types for Dev.

Directly adapted from Freebuff's agent-definition.ts pattern:
- AgentDefinition with id, model, toolNames, spawnableAgents
- handleSteps generator pattern for programmatic control
- Input/output schema definitions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generator, Optional


class OutputMode(str, Enum):
    LAST_MESSAGE = "last_message"
    ALL_MESSAGES = "all_messages"
    STRUCTURED_OUTPUT = "structured_output"


class StepAction(str, Enum):
    """Actions that handleSteps can yield."""
    STEP = "STEP"          # Run model for one assistant message
    STEP_ALL = "STEP_ALL"  # Run model until end_turn or no tool calls
    RETURN = "RETURN"      # End the turn


@dataclass
class ToolCall:
    """A tool call yielded by handleSteps."""
    tool_name: str
    input: dict[str, Any]
    include_tool_call: bool = True


@dataclass
class AgentStepContext:
    """Context provided to handleSteps generator."""
    agent_state: "AgentState"
    prompt: str | None = None
    params: dict[str, Any] | None = None
    model: str | None = None
    logger: Any = None


@dataclass
class AgentState:
    """Mutable state for a running agent instance."""
    agent_id: str
    run_id: str
    parent_id: str | None = None
    message_history: list[dict] = field(default_factory=list)
    output: dict[str, Any] | None = None
    system_prompt: str = ""
    tool_definitions: dict[str, dict] = field(default_factory=dict)
    context_token_count: int = 0


@dataclass
class AgentDefinition:
    """
    Definition of an agent. Adapted from Freebuff's AgentDefinition.
    
    Each agent has:
    - A unique id and display name
    - A model assignment (NVIDIA NIM model)
    - A set of tools it can use
    - Other agents it can spawn
    - Prompts that shape its behavior
    - An optional handleSteps generator for programmatic control
    """
    id: str
    display_name: str
    model: str = "default"
    
    # Tools and subagents
    tool_names: list[str] = field(default_factory=list)
    spawnable_agents: list[str] = field(default_factory=list)
    
    # Input/Output
    input_schema: dict[str, Any] | None = None
    output_mode: OutputMode = OutputMode.LAST_MESSAGE
    output_schema: dict[str, Any] | None = None
    
    # Prompts
    spawner_prompt: str = ""
    system_prompt: str = ""
    instructions_prompt: str = ""
    step_prompt: str = ""
    
    # Behavior flags
    include_message_history: bool = False
    windowed_file_reads: bool = True
    compact_context: bool = True
    
    # MCP servers
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    
    # Programmatic step control (generator function)
    handle_steps: Callable[..., Generator] | None = None


# ============================================================================
# Built-in Agent Definitions
# ============================================================================

def get_coder_agent() -> AgentDefinition:
    """The main coding agent - writes and edits code."""
    return AgentDefinition(
        id="coder",
        display_name="Dev Coder",
        model="coding",  # Poolside Laguna S 2.1 (OpenRouter free) or 70B Llama (NIM fallback)
        tool_names=[
            "read_files", "write_file", "str_replace",
            "run_terminal_command", "code_search", "glob", "list_directory",
            "git_operations", "write_todos", "task_completed",
            "web_search", "read_url",
            "summarize", "free_api", "skill", "tool_search",
        ],
        spawnable_agents=["researcher", "reviewer"],
        system_prompt="""You are Dev, an autonomous AI coding agent. BUILD production-ready software — don't describe, plan, or stub. BUILD IT.

## RULES
1. Use write_file tool for EVERY file — complete content, no placeholders, no TODOs
2. One file per tool call. Each file must be production-quality.
3. CSS: 100+ lines with gradients, animations, shadows, responsive design, Google Fonts
4. HTML: Semantic tags, real content (not lorem ipsum), images via URL, meta tags
5. JS: Full implementations with event handlers, callbacks, fetch calls
6. Backend: Complete routes, error handling, middleware
7. After all files created, run_terminal_command to install deps and test
8. NEVER stop until project works. NEVER return text when files remain to create.

## FILE CREATION FORMAT
write_file: {"path": "project/file.ext", "content": "COMPLETE file content"}
One file per call. Full content. No shortcuts.

## read_files FORMAT
[{"path": "file.txt", "offset": 1, "limit": 2000}]

## BUILD FLOW
1. write_todos (list ALL files)
2. write_file for EACH file (complete, production-quality)
3. run_terminal_command (npm init, pip install, etc.)
4. Test. Fix if broken. Repeat until working.

Deliver WORKING software. Use tools every single time.""",
        instructions_prompt="""When working on tasks:
1. First understand the codebase by reading relevant files
2. Plan your approach with write_todos
3. Implement changes incrementally
4. Verify with type checking and tests
5. Commit with clear messages

Always prefer editing existing files over creating new ones.
Match the project's existing code style and conventions.""",
    )


def get_researcher_agent() -> AgentDefinition:
    """Research agent - reads docs, searches web, investigates."""
    return AgentDefinition(
        id="researcher",
        display_name="Dev Researcher",
        model="coding",  # Nemotron for reasoning
        tool_names=[
            "read_files", "code_search", "glob", "list_directory",
            "web_search", "read_url", "read_docs",
        ],
        system_prompt="""You are a research agent. Your job is to gather information and report back.

You can:
- Search the web for documentation and examples
- Read URLs and extract content
- Search codebases for patterns
- Look up library documentation

Report your findings clearly and concisely. Include source URLs when available.""",
        instructions_prompt="""Research thoroughly before reporting. Use web_search and read_url
for current information. Use code_search to find patterns in the codebase.
Always cite your sources.""",
    )


def get_reviewer_agent() -> AgentDefinition:
    """Code review agent - reviews changes and suggests improvements."""
    return AgentDefinition(
        id="reviewer",
        display_name="Dev Reviewer",
        model="coding",
        tool_names=[
            "read_files", "code_search", "glob", "run_terminal_command",
        ],
        system_prompt="""You are a code review agent. You review code changes for:
- Bugs and potential issues
- Security vulnerabilities
- Performance problems
- Code style and conventions
- Missing error handling
- Test coverage gaps

Provide specific, actionable feedback. Reference line numbers when possible.""",
        instructions_prompt="""Review code thoroughly. Check for:
1. Correctness - does the code do what it's supposed to?
2. Security - any injection, auth, or data exposure risks?
3. Performance - any N+1 queries, unnecessary loops, memory issues?
4. Maintainability - is it readable and well-structured?
5. Testing - are edge cases covered?

Be constructive but direct. Prioritize critical issues.""",
    )


def get_planner_agent() -> AgentDefinition:
    """Planning agent - decomposes complex tasks into steps."""
    return AgentDefinition(
        id="planner",
        display_name="Dev Planner",
        model="reasoning",
        tool_names=[
            "read_files", "code_search", "glob", "list_directory",
            "write_todos", "spawn_agents",
        ],
        spawnable_agents=["researcher"],
        system_prompt="""You are a planning agent. You break complex tasks into clear,
actionable steps. You think through dependencies, risks, and alternatives.

Create detailed plans with:
1. Clear task breakdown
2. Dependencies between tasks
3. Estimated complexity
4. Potential risks and mitigations""",
        instructions_prompt="""Before creating a plan:
1. Understand the full scope by reading relevant files
2. Research any unknowns
3. Identify dependencies and ordering
4. Consider edge cases and failure modes
5. Create a clear, ordered task list with write_todos""",
    )


def get_browser_agent() -> AgentDefinition:
    """Browser automation agent - interacts with web pages."""
    return AgentDefinition(
        id="browser",
        display_name="Dev Browser",
        model="fast",
        tool_names=[
            "browser_navigate", "browser_click", "browser_type",
            "browser_screenshot", "browser_evaluate",
        ],
        system_prompt="""You are a browser automation agent. You interact with web pages
to test applications, fill forms, and verify UI behavior.

Use Playwright-based tools to:
- Navigate to URLs
- Click elements
- Fill forms
- Take screenshots
- Evaluate JavaScript""",
    )


# Agent registry
BUILTIN_AGENTS: dict[str, Callable[[], AgentDefinition]] = {
    "coder": get_coder_agent,
    "researcher": get_researcher_agent,
    "reviewer": get_reviewer_agent,
    "planner": get_planner_agent,
    "browser": get_browser_agent,
}


def get_agent(agent_id: str) -> AgentDefinition:
    """Get a built-in agent definition by ID."""
    factory = BUILTIN_AGENTS.get(agent_id)
    if factory:
        return factory()
    raise ValueError(f"Unknown agent: {agent_id}")


def list_agents() -> list[str]:
    """List all available built-in agent IDs."""
    return list(BUILTIN_AGENTS.keys())
