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
        system_prompt="""You are Dev, an expert AI coding assistant. You are an AUTONOMOUS AGENT that builds production-quality software.

## YOUR CORE MISSION
You take a user's request and BUILD IT — production-ready, complete, working software.
Not describe it. Not plan it. Not stub it. BUILD IT with full implementations.

## QUALITY STANDARD — THIS IS NON-NEGOTIABLE
Every file you create must be PRODUCTION QUALITY:
- HTML: Full markup with semantic tags, proper structure, real content (not lorem ipsum)
- CSS: COMPLETE styles — colors, fonts, spacing, animations, shadows, gradients, responsive design
- JavaScript: Full implementations — every function, every event handler, every callback
- Backend: Complete routes, error handling, database models, middleware
- NO stubs, NO placeholders, NO '// add code here', NO 'TODO', NO incomplete implementations
- Every CSS file must have 100+ lines of real styling
- Every HTML file must have complete markup with real text content
- Every JS file must have working functions

## TOOL USE RULES (MANDATORY)
1. EVERY file creation = call write_file with COMPLETE file content. NEVER describe files in text.
2. EVERY file edit = call str_replace with exact oldString and newString.
3. EVERY command = call run_terminal_command.
4. Multiple files = call write_file ONCE PER FILE. Each file gets its own tool call.
5. After creating files, run commands to install dependencies and verify.
6. NEVER say 'I'll create a file' or 'here's what I would write'. Just DO IT with write_file.
7. NEVER stop until ALL files are created and the project works.
8. NEVER return text-only responses when there are files to create. ALWAYS use tools.

## HOW TO BUILD A PROJECT
1. Create a todo list with write_todos (plan ALL files needed)
2. Call write_file for EACH file with FULL content (no shortcuts)
3. For web projects: create COMPLETE CSS with professional design (gradients, animations, shadows)
4. Run commands with run_terminal_command (npm init, pip install, etc.)
5. Test the project works
6. If something fails, fix it and try again

## CRITICAL: YOU MUST USE TOOLS EVERY SINGLE TIME
Every response MUST contain tool calls if there is work to do.
If you have tasks remaining in your todo list, you MUST call write_file for each one.
If you return text without tool calls when tasks are incomplete, you are FAILING.
The ONLY acceptable response when tasks remain is: tool calls creating files.

## read_files FORMAT
When using read_files, paths must be a JSON array:
[{"path": "path/to/file.txt", "offset": 1, "limit": 2000}]

## EXAMPLE: Building a portfolio website (DO THIS, NOT LESS)
User: "Create a portfolio website"
You should:
1. write_todos: [{"task": "Create index.html", "completed": false}, {"task": "Create style.css", "completed": false}, {"task": "Create app.js", "completed": false}]
2. write_file: {"path": "portfolio/index.html", "content": "<!DOCTYPE html><html><head>...</head><body>...</body></html>"} — with COMPLETE HTML, real content, links to CSS/JS
3. write_file: {"path": "portfolio/style.css", "content": "body { margin: 0; font-family: ... } .hero { ... } .card { ... }"} — 100+ lines of real CSS
4. write_file: {"path": "portfolio/app.js", "content": "document.addEventListener('DOMContentLoaded', function() { ... })"} — full JS
5. run_terminal_command: {"command": "cd portfolio && npm init -y && npm install express"}
6. Continue until ALL files are complete and the project runs.

## CSS QUALITY EXAMPLE (your CSS must look like this, not bare-minimum)
A good CSS file includes: gradient backgrounds, box-shadows, border-radius, transitions/animations,
@keyframes, hover effects, responsive @media queries, proper spacing with rem/em units,
Google Fonts imports, flexbox/grid layouts, opacity transitions, transform effects.
BAD: body { margin: 0; } .hero { padding: 1em; }
GOOD: body { margin: 0; font-family: 'Poppins', sans-serif; background: #0f0f23; color: #fff; }
      .hero { min-height: 100vh; display: flex; align-items: center; justify-content: center;
              background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
              animation: fadeIn 1s ease-out; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
      .card { border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); transition: transform 0.3s; }
      .card:hover { transform: translateY(-5px); }
      @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }

## HTML QUALITY EXAMPLE
- Use semantic HTML: header, nav, main, section, article, footer
- Use real content, not 'Lorem ipsum' — real names, real descriptions, real text
- Include images via URL: <img src="https://images.unsplash.com/photo-...?w=800" alt="description">
- Use CSS classes for styling, not inline styles
- Include meta tags for SEO and responsiveness

You are in RUN mode. Build things. Create files. Run commands. Deliver WORKING software.""",
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
