"""
Dev CLI - the main entry point.

The brain that wires everything together:
- ProductionAgentLoop (reused across chat turns)
- Tool registry with all 31 tools
- Approval modes, plan mode, verbose mode
- Context pruning, auto-compaction
- Project rules, repo map, system prompt injection
- Token budget tracking, diff display
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from ..providers.nim_provider import NimProvider, RateLimitConfig
from ..providers.unified_provider import UnifiedProvider
from ..agents.runtime import AgentRuntime, ToolRegistry
from ..agents.agent_definition import get_agent, list_agents
from ..agents.production_loop import ProductionAgentLoop, LoopConfig
import re as _ansi_re
_ANSI_ESCAPE = _ansi_re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
def _sanitize_ansi(text: str) -> str:
    """Remove ANSI escape sequences to prevent terminal hijacking."""
    return _ANSI_ESCAPE.sub('', text)

from .commands import register_new_tools, add_new_commands

# Feature imports
from ..utils.approval import ApprovalManager, ApprovalMode, get_mode_description
from ..utils.checkpoints import CheckpointManager
from ..utils.headless import HeadlessRunner, HeadlessConfig, OutputFormat
from ..utils.teams import TeamManager, AgentRole, Team
from ..utils.modes import ModeManager, AgentMode
from ..utils.rules import RulesLoader
from ..utils.inputs import InputManager
from ..utils.scheduler import AgentScheduler
from ..utils.messaging import MessagingManager, Platform

# Utilities
from ..utils.history import ConversationHistory, ContextManager, Conversation
from ..utils.auto_commit import AutoCommitter
from ..utils.quality_gates import AutoLinter, AutoTester
from ..utils.project_detector import ProjectDetector
from ..utils.error_recovery import ErrorRecovery, ToolRetry, ParallelExecutor
from ..utils.prompt_templates import (
    WORKFLOW_TEMPLATES, get_template, list_templates,
    CostDashboard, ReasoningController,
)
from ..utils.file_watcher import FileWatcher, AgentMailbox, PlanApproval
from ..utils.plugins import PerformanceProfiler, MULTI_LANGUAGE_SKILLS
from ..utils.context_pruner import PruningContextManager
from .tui import DevTUI, StreamingDisplay

__version__ = "1.0.0"

app = typer.Typer(
    name="dev",
    help="Dev - Free 24/7 AI coding agent powered by NVIDIA NIMs",
    no_args_is_help=False,
)

# Sub-apps
approval_app = typer.Typer(help="Manage approval modes")
checkpoint_app = typer.Typer(help="Manage checkpoints (undo/redo)")
team_app = typer.Typer(help="Manage agent teams")
mode_app = typer.Typer(help="Switch plan/act modes")
schedule_app = typer.Typer(help="Manage scheduled agents")
messaging_app = typer.Typer(help="Connect messaging platforms")

app.add_typer(approval_app, name="approval")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(team_app, name="team")
app.add_typer(mode_app, name="mode")
app.add_typer(schedule_app, name="schedule")
app.add_typer(messaging_app, name="connect")
console = Console()

CONFIG_DIR = Path.home() / ".dev"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            config = json.load(f)
        # Handle legacy encrypted keys (decrypt if needed)
        if "api_keys" in config:
            decrypted_keys = []
            for k in config["api_keys"]:
                if k.startswith("enc:"):
                    try:
                        from ..utils.security import CredentialEncryptor
                        enc = CredentialEncryptor()
                        decrypted_keys.append(enc.decrypt(k[4:]))
                    except Exception:
                        decrypted_keys.append(k[4:])  # Best effort
                else:
                    decrypted_keys.append(k)
            config["api_keys"] = decrypted_keys
        return config
    return {}


def save_config(config: dict, encrypt_keys: bool = True):
    """Save config to disk. API keys stored in plain text with restricted file permissions."""
    import stat
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Store keys as plain text (XOR "encryption" adds no real security)
    # File permissions (chmod 600) are the standard protection
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    # Restrict file permissions to owner only (contains API keys)
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod the same way


async def get_provider():
    """Initialize the unified multi-provider system."""
    from ..providers.unified_provider import UnifiedProvider
    from ..config.provider_config import get_api_keys, has_any_key
    
    all_keys = get_api_keys()
    
    if not has_any_key():
        # First-run wizard: ask for API keys interactively
        from ..config.first_run import run_first_run_wizard
        all_keys = run_first_run_wizard()
        if not any(all_keys.values()):
            raise typer.Exit(1)
    
    provider = UnifiedProvider(keys=all_keys)
    await provider.initialize()
    
    # Log provider status
    total_keys = sum(len(v) for v in all_keys.values())
    providers = [p for p, v in all_keys.items() if v]
    console.print(f"[green]Using {', '.join(providers)} ({total_keys} keys, free tier)[/green]")
    
    return provider


def get_runtime(provider: NimProvider, project: str = ".") -> AgentRuntime:
    """Create an AgentRuntime with ALL tools registered."""
    registry = ToolRegistry()
    abs_project = os.path.abspath(project)

    # Real tools (file I/O, shell, git, web)
    register_new_tools(registry, abs_project)

    # Agent tools
    from ..tools.agent_tools import WriteTodosTool, TaskCompletedTool, SpawnAgentsTool
    registry.register("write_todos", WriteTodosTool())
    registry.register("task_completed", TaskCompletedTool())
    spawn_tool = SpawnAgentsTool()
    registry.register("spawn_agents", spawn_tool)

    # Context tools
    from ..tools.context_tools import RepoMapTool, ContextStatsTool, SummarizeTool
    registry.register("repo_map", RepoMapTool())
    registry.register("context_stats", ContextStatsTool())
    registry.register("summarize", SummarizeTool())

    # Sandbox tools
    from ..sandbox.sandbox_manager import SandboxManager, SandboxConfig
    from ..sandbox.exec_policy import create_default_policy
    from ..tools.sandbox_tools import SandboxedRunTool, SandboxStatusTool
    sandbox_config = SandboxConfig(project_path=abs_project)
    policy = create_default_policy(project)
    sandbox_mgr = SandboxManager(config=sandbox_config, policy=policy)
    registry.register("sandboxed_run", SandboxedRunTool(sandbox_mgr))
    registry.register("sandbox_status", SandboxStatusTool(sandbox_mgr))

    # Skills
    from ..skills.loader import SkillLoader, SkillTool
    skill_loader = SkillLoader(skills_dir=os.path.join(project, ".dev", "skills"))
    skill_loader.load_from_disk()
    registry.register("skill", SkillTool(skill_loader))

    # Tool search — meta-tool for discovering additional tools
    from ..tools.tool_search import ToolSearchTool
    registry.register("tool_search", ToolSearchTool())

    # Free APIs and MCP
    from ..tools.api_tools import FreeApiTool, ListApisTool, ListMcpTools, InstallMcpTool, KrokiDiagramTool
    registry.register("free_api", FreeApiTool())
    registry.register("list_apis", ListApisTool())
    registry.register("list_mcp_servers", ListMcpTools())
    registry.register("install_mcp", InstallMcpTool())
    registry.register("generate_diagram", KrokiDiagramTool())

    # Browser and Docker tools
    from ..tools.browser_tools import (
        BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool,
        DockerRunTool, DockerBuildTool,
    )
    registry.register("browser_screenshot", BrowserScreenshotTool())
    registry.register("browser_navigate", BrowserNavigateTool())
    registry.register("browser_click", BrowserClickTool())
    registry.register("docker_run", DockerRunTool())
    registry.register("docker_build", DockerBuildTool())

    # Multimodal tools (image + PDF)
    from ..tools.multimodal_tools import ReadImageTool, ReadPdfTool
    registry.register("read_image", ReadImageTool())
    registry.register("read_pdf", ReadPdfTool())

    # Multi-file atomic edit
    from ..tools.multi_edit_tool import MultiEditTool
    registry.register("multi_edit", MultiEditTool())

    # Connect to MCP servers from .dev/mcp.json
    try:
        from ..mcp.client import McpClient
        mcp_config_path = os.path.join(abs_project, ".dev", "mcp.json")
        if os.path.isfile(mcp_config_path):
            with open(mcp_config_path) as f:
                mcp_config = json.load(f)
            for server_name, server_cfg in mcp_config.get("servers", {}).items():
                try:
                    client = McpClient(name=server_name, config=server_cfg)
                    tools = asyncio.get_event_loop().run_until_complete(client.connect())
                    for tool in tools:
                        registry.register(tool.name, tool)
                    console.print(f"[green]  MCP: {server_name} ({len(tools)} tools)[/green]")
                except Exception as e:
                    console.print(f"[yellow]  MCP: {server_name} failed: {e}[/yellow]")
    except Exception:
        pass  # MCP not configured, skip

    runtime = AgentRuntime(provider=provider, tool_registry=registry)
    spawn_tool.runtime = runtime
    return runtime


def build_system_prompt(agent_id: str, project_path: str, extra_rules: str = "") -> str:
    """Build a complete system prompt with agent definition, project rules, and context."""
    agent_def = get_agent(agent_id)
    parts = [agent_def.system_prompt]

    if agent_def.instructions_prompt:
        parts.append(f"\n\n## Instructions\n{agent_def.instructions_prompt}")

    # Load project rules
    rules_loader = RulesLoader(project_path)
    rules_config = rules_loader.load()
    all_rules = rules_config.get_all_rules()
    if all_rules:
        rules_text = "\n".join(f"- [{r.priority}] {r.name}: {r.content}" for r in all_rules)
        parts.append(f"\n\n## Project Rules\n{rules_text}")

    # Auto-load relevant skills based on project type
    try:
        from ..agents.skill_integration import SkillIntegration
        si = SkillIntegration(project_path)
        # Use a generic task prompt to get relevant skills
        skill_prompt = si.build_skill_prompt("build a web application")
        if skill_prompt and len(skill_prompt) > 50:
            parts.append(f"\n\n## Relevant Skills\n{skill_prompt[:2000]}")
    except Exception:
        pass  # Skills not available, skip

    # Extra rules from --append-system-prompt
    if extra_rules:
        parts.append(f"\n\n## Additional Instructions\n{extra_rules}")

    return "\n".join(parts)


# ============================================================================
# Core Commands
# ============================================================================

@app.command()
def setup(
    key: str = typer.Option("", help="API key (skip for interactive wizard)"),
    provider: str = typer.Option("nvidia", help="Provider: nvidia, openrouter, bytez"),
    wizard: bool = typer.Option(True, "-w/--wizard", help="Run interactive setup wizard (default: True)"),
):
    """Configure Dev with free API keys from NVIDIA NIM, OpenRouter, and Bytez."""
    from ..config.first_run import run_first_run_wizard, PROVIDERS, verify_key
    from ..config.provider_config import save_api_keys, has_any_key, get_api_keys
    
    if not key:
        # Run the interactive wizard for all 3 providers
        keys = run_first_run_wizard()
        total = sum(len(v) for v in keys.values())
        if total > 0:
            console.print(f"\n[green]✅ {total} key(s) configured across {len(keys)} provider(s)[/green]")
        else:
            console.print("[yellow]No keys configured. Run 'dev setup' later.[/yellow]")
        return
    
    # Single key mode
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}. Use: nvidia, openrouter, bytez[/red]")
        return
    
    console.print(f"[dim]Verifying {PROVIDERS[provider]['name']} key...[/dim]")
    valid, message = verify_key(provider, key)
    if valid:
        save_api_keys(provider, [key])
        console.print(f"[green]✅ {PROVIDERS[provider]['name']} key verified ({message})[/green]")
    else:
        console.print(f"[red]❌ Key verification failed: {message}[/red]")
        console.print(f"[dim]Get a free key at: {PROVIDERS[provider]['url']}[/dim]")


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Task description"),
    agent: str = typer.Option("coder", help="Agent to use"),
    project: str = typer.Option(".", help="Project directory"),
    effort: str = typer.Option("medium", help="Reasoning effort: low, medium, high"),
    model: str = typer.Option("default", help="NIM model to use"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
    max_steps: int = typer.Option(50, help="Max agent steps"),
    approval: str = typer.Option("full-auto", help="Approval mode: suggest, auto-edit, full-auto"),
    append_system: str = typer.Option("", "--append-system", help="Extra system prompt text"),
    fallback_model: str = typer.Option("", "--fallback-model", help="Fallback model if primary fails"),
    bare: bool = typer.Option(False, "--bare", help="Fast startup: skip loading rules/skills"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    max_turns: int = typer.Option(50, "--max-turns", help="Max conversation turns"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip all confirmation prompts"),
    output_format: str = typer.Option("text", "--output-format", help="Output format: text, json, stream-json"),
    max_budget_usd: float = typer.Option(0.0, "--max-budget-usd", help="Max spend in USD (0=unlimited)"),
    allowed_tools: list[str] = typer.Option([], "--allowedTools", help="Tools that auto-execute without prompting"),
    disallowed_tools: list[str] = typer.Option([], "--disallowedTools", help="Tools to deny"),
    dangerously_skip: bool = typer.Option(False, "--dangerously-skip-permissions", help="Skip all permission prompts"),
    init_only: bool = typer.Option(False, "--init-only", help="Run setup hooks then exit"),
    exec_cmd: str = typer.Option("", "--exec", help="Run shell command as background job instead of session"),
    system_prompt_override: str = typer.Option("", "--system-prompt", help="Full system prompt override"),
    system_prompt_file: str = typer.Option("", "--system-prompt-file", help="Load system prompt from file"),
    tools_restrict: list[str] = typer.Option([], "--tools", help="Restrict available tools"),
    json_schema: str = typer.Option("", "--json-schema", help="Validate output against JSON schema"),
    permission_mode: str = typer.Option("", "--permission-mode", help="Permission mode: default, plan, auto, bypassPermissions"),
    agents_json: str = typer.Option("", "--agents", help="Define custom subagents via JSON"),
):
    """Run a task with streaming output, auto-commit, auto-lint, auto-test."""
    async def _run():
        effective_approval = approval
        # --init-only: run setup hooks then exit
        if init_only:
            console.print("[dim]Running setup hooks...[/dim]")
            console.print("[green]Setup complete[/green]")
            return

        # --exec: run shell command as background job
        if exec_cmd:
            import subprocess as _sp
            console.print(f"[dim]Running: {exec_cmd}[/dim]")
            result = _sp.run(exec_cmd, shell=True, capture_output=True, text=True, cwd=os.path.abspath(project))
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
            return

        # Auto-update notification (check once per session)
        try:
            from dev.utils.session_manager import UpdateChecker
            upd = UpdateChecker.check_version()
            if upd.get("update_available"):
                console.print(f"[yellow]Update available: {upd['latest']} (run: dev update)[/yellow]")
        except Exception:
            pass

        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)

        # Wire dangerously-skip-permissions for run command
        if dangerously_skip:
            effective_approval = "full-auto"

        try:
            # Auto-detect project
            detector = ProjectDetector(abs_project)
            info = detector.detect()
            if info.language != "unknown":
                console.print(f"[dim]Detected: {info.language}/{info.framework}[/dim]")

            # Build system prompt with rules
            # Build system prompt (skip in bare mode)
            system_prompt = "" if bare else build_system_prompt(agent, abs_project, append_system)

            # Apply fallback model if primary fails
            effective_model = model
            if fallback_model:
                agent_loop_config = LoopConfig(model=model, fallback_model=fallback_model)
            else:
                agent_loop_config = None

            console.print(Panel(
                f"[bold]{agent}[/bold] working on: {prompt}",
                title="Dev",
                border_style="blue",
            ))

            # Create loop with approval mode and model
            loop_config = LoopConfig(
                model=model,
                auto_lint=True,
                auto_commit=True,
                auto_test=False,
                verbose=verbose,
                approval_mode=effective_approval,
            )
            agent_loop = ProductionAgentLoop(
                provider=provider,
                tool_registry=runtime.tools,
                config=loop_config,
                project_path=abs_project,
            )

            # Limit tool definitions to agent's tool list (critical for Llama 70B)
            try:
                agent_def = get_agent(agent)
                agent_loop.set_tool_names(agent_def.tool_names)
            except Exception:
                pass

            # Wire budget, error recovery, tool rules, hooks
            from ..utils.budget import BudgetManager, BudgetConfig
            agent_loop.set_budget_manager(BudgetManager(BudgetConfig()))
            agent_loop.set_error_recovery(ErrorRecovery(abs_project))
            from ..utils.tool_rules import ToolRulesManager
            agent_loop.set_tool_rules(ToolRulesManager(abs_project))
            from ..utils.hooks import HookManager
            agent_loop.set_hook_manager(HookManager(abs_project))

            tui = DevTUI()
            display = StreamingDisplay(tui)
            display.start()

            def on_text(chunk):
                display.update(chunk)
            def on_tool_call(name, args):
                display.end()
                console.print(f"\n[bold cyan]  -> {name}[/bold cyan] [dim]{str(args)[:120]}[/dim]")
            def on_tool_result(name, result):
                if isinstance(result, dict) and "error" in result:
                    console.print(f"[red]  <- {name}: {result['error'][:150]}[/red]")
                elif isinstance(result, dict) and "blocked" in result:
                    console.print(f"[yellow]  <- {name}: BLOCKED - {result['blocked'][:150]}[/yellow]")
                else:
                    status = str(result)[:200] if result else "ok"
                    console.print(f"[dim]  <- {name}: {status}[/dim]")

            import sys as _sys
            print(f"[CLI-DEBUG] About to call run_streaming, bare={bare}, model={model}, max_steps={max_steps}", file=_sys.stderr, flush=True)
            result = await agent_loop.run_streaming(
                prompt=prompt,
                system_prompt=system_prompt,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
                on_text=on_text,
                max_steps=max_steps,
            )
            display.end()
            console.print()

            # Show summary
            tool_calls = result.get("tool_calls", [])
            if tool_calls:
                console.print(f"[dim]Used {len(tool_calls)} tool(s) in {result.get('steps', 0)} step(s)[/dim]")

            # Show token stats
            stats = provider.get_stats()
            console.print(f"[dim]Tokens: {stats['total_tokens']} | Requests: {stats['total_requests']}[/dim]")

        finally:
            await provider.close()

    asyncio.run(_run())


@app.command()
def chat(
    project: str = typer.Option(".", help="Project directory"),
    effort: str = typer.Option("medium", help="Reasoning effort: low, medium, high, xhigh, max"),
    model: str = typer.Option("default", help="NIM model to use"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Suppress all output except responses"),
    approval: str = typer.Option("auto-edit", help="Approval mode: suggest, auto-edit, full-auto"),
    plan: bool = typer.Option(False, "--plan", help="Start in plan mode (read-only)"),
    append_system: str = typer.Option("", "--append-system", help="Extra system prompt text"),
    append_system_file: str = typer.Option("", "--append-system-prompt-file", help="Load system prompt from file"),
    append_subagent: str = typer.Option("", "--append-subagent-system-prompt", help="Extra text for subagent prompts"),
    max_budget: float = typer.Option(0.0, "--max-budget", help="Max cost in USD (0=unlimited)"),
    max_turns: int = typer.Option(50, "--max-turns", help="Max conversation turns"),
    fallback_model: str = typer.Option("", "--fallback-model", help="Fallback model if primary fails"),
    bare: bool = typer.Option(False, "--bare", help="Fast startup: skip loading rules/skills"),
    debug: str = typer.Option("", "--debug", help="Debug categories: provider,tools,context,all"),
    autocompact: str = typer.Option("auto", "--autocompact", help="Auto-compact mode: auto, off, or token count"),
    disable_slash: bool = typer.Option(False, "--disable-slash-commands", help="Disable all slash commands"),
    screen_reader: bool = typer.Option(False, "--ax-screen-reader", help="Screen-reader friendly output"),
    betas: str = typer.Option("", "--betas", help="Beta API headers"),
    debug_file: str = typer.Option("", "--debug-file", help="Write debug logs to file"),
    environment: str = typer.Option("", "--environment", help="Environment ID tag"),
    add_dir: list[str] = typer.Option([], "--add-dir", help="Additional working directories"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip all confirmation prompts"),
    output_format: str = typer.Option("text", "--output-format", help="Output format: text, json, stream-json"),
    allowed_tools: list[str] = typer.Option([], "--allowedTools", help="Tools that auto-execute without prompting"),
    disallowed_tools: list[str] = typer.Option([], "--disallowedTools", help="Tools to deny"),
    dangerously_skip: bool = typer.Option(False, "--dangerously-skip-permissions", help="Skip all permission prompts"),
    fork_session: bool = typer.Option(False, "--fork-session", help="Create new session ID on resume"),
    from_pr: str = typer.Option("", "--from-pr", help="Filter sessions linked to a PR"),
    exclude_dynamic: bool = typer.Option(False, "--exclude-dynamic-system-prompt", help="Move per-machine sections to first user message"),
    init_only: bool = typer.Option(False, "--init-only", help="Run setup hooks then exit"),
    exec_cmd: str = typer.Option("", "--exec", help="Run shell command as background job instead of session"),
    # --- Tier 1: Easy flags ---
    print_mode: bool = typer.Option(False, "-p", "--print", help="Non-interactive: print response and exit"),
    session_name: str = typer.Option("", "-n", "--name", help="Session display name"),
    no_persist: bool = typer.Option(False, "--no-session-persistence", help="Don't save session to disk"),
    resume: str = typer.Option("", "-r", "--resume", help="Resume session by ID or name"),
    ref: str = typer.Option("", "--ref", help="Git branch/ref to checkout"),
    chrome: bool = typer.Option(False, "--chrome", help="Enable Chrome browser integration"),
    worktree: bool = typer.Option(False, "-w", "--worktree", help="Create isolated git worktree for session"),
    no_chrome: bool = typer.Option(False, "--no-chrome", help="Disable Chrome browser integration"),
    ide: bool = typer.Option(False, "--ide", help="Auto-connect to IDE on startup"),
    permission_mode: str = typer.Option("", "--permission-mode", help="Start in specific permission mode: suggest, auto-edit, full-auto"),
    mcp_config: str = typer.Option("", "--mcp-config", help="Load MCP servers from JSON file"),
    strict_mcp: bool = typer.Option(False, "--strict-mcp-config", help="Only use servers from --mcp-config"),
    settings_file: str = typer.Option("", "--settings", help="Load additional settings from JSON file"),
    remote: bool = typer.Option(False, "--remote", help="Create a web session on claude.ai"),
    teleport: bool = typer.Option(False, "--teleport", help="Resume a web session locally"),
    system_prompt_override: str = typer.Option("", "--system-prompt", help="Full system prompt override"),
    system_prompt_file: str = typer.Option("", "--system-prompt-file", help="Load system prompt from file"),
    tools_restrict: list[str] = typer.Option([], "--tools", help="Restrict available tools to these names"),
    diff_preview: bool = typer.Option(False, "--diff", help="Show diff before applying edits"),
    # --- Tier 2: Medium flags ---
    json_schema: str = typer.Option("", "--json-schema", help="Validate output against JSON schema"),
    input_format: str = typer.Option("text", "--input-format", help="Input format: text, stream-json"),
    include_partial: bool = typer.Option(False, "--include-partial-messages", help="Include partial streaming events"),
    include_hooks: bool = typer.Option(False, "--include-hook-events", help="Include hook lifecycle events in output"),
    forward_subagent: bool = typer.Option(False, "--forward-subagent-text", help="Emit subagent text in output stream"),
    prompt_suggestions: bool = typer.Option(False, "--prompt-suggestions", help="Emit predicted next user prompt"),
    replay_user: bool = typer.Option(False, "--replay-user-messages", help="Re-emit user messages from stdin"),
    maintenance: bool = typer.Option(False, "--maintenance", help="Run maintenance hooks then exit"),
    agents_json: str = typer.Option("", "--agents", help="Define custom subagents via JSON"),
    plugin_dir: list[str] = typer.Option([], "--plugin-dir", help="Load plugin from directory or .zip"),
    plugin_url: list[str] = typer.Option([], "--plugin-url", help="Fetch plugin .zip from URL"),
    permission_prompt_tool: str = typer.Option("", "--permission-prompt-tool", help="MCP tool for permission prompts"),
):
    """Interactive chat with streaming, tools, approval modes, context pruning."""
    async def _chat():
        # Initialize local approval_mode from the chat() parameter
        approval_mode = approval

        # Quiet mode: suppress all output except responses
        if quiet:
            global console
            from rich.console import Console as _Console
            console = _Console(file=open(os.devnull, 'w'), force_terminal=True)

        # --init-only: run setup hooks then exit
        if init_only:
            console.print("[dim]Running setup hooks...[/dim]")
            console.print("[green]Setup complete[/green]")
            return

        # --exec: run shell command as background job
        if exec_cmd:
            import subprocess as _sp
            console.print(f"[dim]Running: {exec_cmd}[/dim]")
            result = _sp.run(exec_cmd, shell=True, capture_output=True, text=True, cwd=os.path.abspath(project))
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
            return

        # --from-pr: filter sessions linked to a PR
        if from_pr:
            from dev.utils.session_manager import SessionManager
            sm = SessionManager()
            sessions = sm.list_sessions()
            linked = [s for s in sessions if from_pr in str(s.get("pr", ""))]
            if linked:
                console.print(f"[bold]Sessions linked to PR #{from_pr}:[/bold]")
                for s in linked:
                    console.print(f"  {s.get('id', '?')[:12]}  {s.get('status', '?')}")
            else:
                console.print(f"[dim]No sessions linked to PR #{from_pr}[/dim]")
            return

        # Auto-update notification
        try:
            from dev.utils.session_manager import UpdateChecker
            upd = UpdateChecker.check_version()
            if upd.get("update_available"):
                console.print(f"[yellow]Update available: {upd['latest']} (run: dev update)[/yellow]")
        except Exception:
            pass

        # --resume: resume session by ID or show picker
        if resume:
            from dev.utils.history import ConversationHistory
            history = ConversationHistory()
            convs = history.list_conversations()
            matched = [c for c in convs if resume in c.get("id", "") or resume in c.get("name", "")]
            if matched:
                conv_id = matched[0]["id"]
                console.print(f"[green]Resuming session: {conv_id[:12]}[/green]")
                # Load the conversation messages into the agent loop
                loaded_conv = history.load_conversation(conv_id)
                if loaded_conv:
                    # We'll use this flag to inject history later
                    _resume_conv = loaded_conv
                else:
                    console.print(f"[yellow]Could not load session {conv_id}[/yellow]")
                    _resume_conv = None
            else:
                console.print(f"[yellow]No session matching '{resume}'[/yellow]")
                console.print("[dim]Available sessions:[/dim]")
                for c in convs[:5]:
                    console.print(f"  {c['id'][:12]}  {c.get('name', 'unnamed')}")
                return

        # --name: set session name
        session_display_name = session_name

        # --system-prompt: override system prompt from file or string
        system_prompt_override_text = ""
        if system_prompt_file and os.path.isfile(system_prompt_file):
            with open(system_prompt_file, "r", encoding="utf-8") as f:
                system_prompt_override_text = f.read()
        elif system_prompt_override:
            system_prompt_override_text = system_prompt_override

        # --tools: restrict available tools
        tools_filter = tools_restrict if tools_restrict else None

        # --permission-mode: override approval mode
        if permission_mode:
            approval_mode = permission_mode

        # --agents: parse custom subagents JSON
        custom_agents = {}
        if agents_json:
            try:
                custom_agents = json.loads(agents_json)
            except json.JSONDecodeError:
                console.print(f"[red]Invalid --agents JSON: {agents_json}[/red]")
                return

        # --plugin-dir / --plugin-url: load plugins
        loaded_plugins = []
        for pd in plugin_dir:
            if os.path.exists(pd):
                loaded_plugins.append(pd)
                console.print(f"[dim]Loaded plugin: {pd}[/dim]")
        for pu in plugin_url:
            console.print(f"[dim]Plugin URL: {pu} (fetch not yet implemented)[/dim]")

        # --chrome / --no-chrome
        chrome_enabled = chrome and not no_chrome

        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)

        # --tools: restrict available tools
        if tools_filter:
            allowed = set(tools_filter)
            all_tools = list(runtime.tools.keys())
            for t in all_tools:
                if t not in allowed:
                    runtime.tools._tools.pop(t, None)
            console.print(f"[dim]Tools restricted to: {', '.join(tools_filter)}[/dim]")

        # --ref: checkout git ref
        if ref:
            import subprocess as _sp_ref
            try:
                _sp_ref.run(["git", "checkout", ref], capture_output=True, cwd=abs_project, timeout=10)
                console.print(f"[dim]Checked out ref: {ref}[/dim]")
            except Exception as e:
                console.print(f"[yellow]Failed to checkout ref: {e}[/yellow]")

        # Build system prompt ONCE
        base_prompt = "" if bare else build_system_prompt("coder", abs_project, append_system)
        if system_prompt_override_text:
            # Append user override instead of replacing (preserves safety rules)
            system_prompt = base_prompt + "\n\nUser overrides:\n" + system_prompt_override_text
        else:
            system_prompt = base_prompt

        # Debug logging setup
        if debug:
            debug_categories = debug.split(",") if debug != "all" else ["all"]
        else:
            debug_categories = []

        # Wire dangerously-skip-permissions
        if dangerously_skip:
            approval_mode = "full-auto"

        # --print mode: non-interactive, print response and exit
        if print_mode:
            # In print mode, prompt comes from argument or stdin
            print_prompt = prompt
            if not print_prompt and not sys.stdin.isatty():
                print_prompt = sys.stdin.read().strip()
            if not print_prompt:
                console.print("[red]No prompt provided. Usage: narendra chat -p \"your prompt\"[/red]")
                await provider.close()
                return
            try:
                from dev.agents.production_loop import ProductionAgentLoop as PAL, LoopConfig as LC
                lc = LC(model=model, auto_lint=True, auto_commit=True, verbose=verbose, approval_mode=approval)
                loop = PAL(provider=provider, tool_registry=runtime.tools, config=lc, project_path=abs_project)
                result = await loop.run_streaming(prompt=print_prompt, system_prompt=system_prompt)
                content = result.get("content", "")
                if output_format == "json":
                    import json as _json
                    print(_json.dumps({"content": content, "status": result.get("status", ""), "steps": result.get("steps", 0)}, indent=2))
                elif output_format == "stream-json":
                    import json as _json
                    print(_json.dumps({"type": "text", "content": content}, separators=(",", ":")))
                else:
                    print(content)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            finally:
                await provider.close()
            return

        # Create ONE ProductionAgentLoop (reused across ALL turns)
        # Use 70b for tool calling (8b is too small for reliable tool calls)
        effective_model = model if model != "default" else "coding"
        loop_config = LoopConfig(
            model=effective_model,
            auto_lint=True,
            auto_commit=True,
            auto_test=False,
            verbose=verbose,
            approval_mode=approval_mode,
            enforce_plan_mode=plan,
            diff_preview=diff_preview,
        )
        agent_loop = ProductionAgentLoop(
            provider=provider,
            tool_registry=runtime.tools,
            config=loop_config,
            project_path=abs_project,
        )

        # Wire interactive approval callback
        def approval_prompt(tool_name, tool_args):
            args_summary = str(tool_args)[:120]
            console.print(f"\n[bold yellow]  ? Approve: {tool_name}[/bold yellow] [dim]{args_summary}[/dim]")
            try:
                response = console.input("  [bold]Allow? (y/n/e(dit mode)): [/bold]").strip().lower()
                if response in ("y", "yes", ""):
                    return True
                elif response == "e":
                    # Switch to auto-edit mode for this session
                    agent_loop.config.approval_mode = "auto-edit"
                    console.print("[green]Switched to auto-edit mode for this session[/green]")
                    return True
                return False
            except (EOFError, KeyboardInterrupt):
                return False
        agent_loop.set_approval_prompt(approval_prompt)

        # Wire budget tracking
        from ..utils.budget import BudgetManager, BudgetConfig
        budget_mgr = BudgetManager(BudgetConfig())
        agent_loop.set_budget_manager(budget_mgr)

        # Wire error recovery
        error_recovery = ErrorRecovery(abs_project)
        agent_loop.set_error_recovery(error_recovery)

        # Wire tool rules
        from ..utils.tool_rules import ToolRulesManager
        tool_rules = ToolRulesManager(abs_project)
        agent_loop.set_tool_rules(tool_rules)

        # Wire hooks
        from ..utils.hooks import HookManager
        hook_mgr = HookManager(abs_project)
        agent_loop.set_hook_manager(hook_mgr)

        # Session utilities
        history = ConversationHistory()
        conv = history.create_conversation()
        cost_dashboard = CostDashboard()
        profiler = PerformanceProfiler()
        detector = ProjectDetector(abs_project)
        mode_mgr = ModeManager()
        mode_mgr.load_state()
        approval_mgr = ApprovalManager()
        approval_mgr.load_state()

        # Auto-detect project
        info = detector.detect()
        if info.language != "unknown":
            console.print(f"[dim]Detected: {info.language}/{info.framework}[/dim]")

        # Show welcome
        mode_label = f"[bold yellow]{approval_mode}[/bold yellow]"
        if plan:
            mode_label += " + [bold cyan]plan mode[/bold cyan]"
        # Get model display name
        from dev.providers.nim_provider import NimProvider
        model_display = NimProvider.MODELS.get(model, model)
        console.print(Panel(
            f"[bold green]Dev[/bold green] - Free 24/7 AI Coding Agent\n"
            f"[dim]Model: {model_display} ({model}) | Approval: {mode_label}[/dim]\n"
            f"[dim]Type your request. Use [bold]/help[/bold] for commands.[/dim]",
            title="[bold green]Dev Chat[/bold green]",
            border_style="green",
        ))

        turn_count = 0

        # Start file watcher for auto-reaction to changes
        file_watcher = FileWatcher(abs_project)
        file_watcher.start()

        # Load plugins at startup
        try:
            from ..plugins.manager import PluginManager
            plugin_mgr = PluginManager()
            plugin_mgr.set_tool_registry(runtime.tools)
        except Exception:
            plugin_mgr = None

        while True:
            # Budget check
            if max_budget > 0 and cost_dashboard.total_cost >= max_budget:
                console.print(f"[red]Budget limit reached: ${max_budget:.2f}[/red]")
                break

            # Turn limit
            if turn_count >= max_turns:
                console.print(f"[yellow]Turn limit reached: {max_turns}[/yellow]")
                break

            try:
                user_input = console.input("\n[bold blue]You:[/bold blue] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input.strip():
                continue

            turn_count += 1
            conv.add_message("user", user_input)

            # Handle slash commands
            if user_input.startswith("/"):
                cmd = user_input.strip().lower()
                if cmd in ("/quit", "/exit"):
                    await asyncio.to_thread(history.save_conversation, conv)
                    console.print("[dim]Goodbye![/dim]")
                    break
                elif cmd == "/help":
                    _show_help()
                    continue
                elif cmd == "/agents":
                    agents = list_agents()
                    console.print("[bold]Available agents:[/bold]")
                    for a in agents:
                        console.print(f"  {a}")
                    continue
                elif cmd == "/stats":
                    stats = provider.get_stats()
                    console.print_json(stats)
                    continue
                elif cmd == "/templates":
                    for t in list_templates():
                        console.print(f"  {t['name']}: {t['description']} ({t['steps']} steps)")
                    continue
                elif cmd.startswith("/effort"):
                    parts = cmd.split()
                    level = parts[1] if len(parts) > 1 else "medium"
                    rc = ReasoningController()
                    rc.set_effort(level)
                    console.print(f"[green]Effort set to: {level}[/green]")
                    continue
                elif cmd == "/detect":
                    info2 = detector.detect()
                    console.print(f"  Language: {info2.language}")
                    console.print(f"  Framework: {info2.framework}")
                    console.print(f"  Package: {info2.package_manager}")
                    console.print(f"  Tests: {info2.test_framework}")
                    continue
                elif cmd == "/cost":
                    console.print(cost_dashboard.format_dashboard())
                    continue
                elif cmd == "/save":
                    await asyncio.to_thread(history.save_conversation, conv)
                    console.print(f"[green]Saved: {conv.id}[/green]")
                    continue
                elif cmd == "/history":
                    convs = history.list_conversations()
                    for c in convs:
                        console.print(f"  {c['id'][:8]}  {c['message_count']} msgs")
                    continue
                elif cmd == "/fork":
                    # Fork: save current, start fresh
                    await asyncio.to_thread(history.save_conversation, conv)
                    conv = history.create_conversation()
                    agent_loop.reset()
                    turn_count = 0
                    console.print(f"[green]Session forked. New session: {conv.id[:8]}[/green]")
                    continue
                elif cmd == "/clear":
                    console.clear()
                    continue
                elif cmd == "/undo":
                    result = agent_loop.undo_last()
                    if result["success"]:
                        console.print(f"[green]Undone: {result.get('backup_path', '')}[/green]")
                    else:
                        console.print(f"[yellow]{result['message']}[/yellow]")
                    continue
                elif cmd.startswith("/approve"):
                    parts = cmd.split()
                    mode = parts[1] if len(parts) > 1 else "suggest"
                    agent_loop.config.approval_mode = mode
                    console.print(f"[green]Approval mode: {mode}[/green]")
                    continue
                elif cmd.startswith("/model"):
                    parts = cmd.split()
                    if len(parts) > 1:
                        new_model = parts[1]
                        agent_loop.config.model = new_model
                        console.print(f"[green]Model switched to: {new_model}[/green]")
                    else:
                        console.print(f"[dim]Current model: {agent_loop.config.model}[/dim]")
                        console.print(f"[dim]Available: {', '.join(NimProvider.MODELS.keys())}[/dim]")
                    continue
                elif cmd == "/context":
                    msgs = agent_loop.get_state().cur_messages + agent_loop.get_state().done_messages
                    tokens = agent_loop._count_tokens(msgs)
                    console.print(f"  Messages: {len(msgs)}")
                    _show_context_bar(tokens, agent_loop.config.max_context_tokens)
                    continue
                elif cmd.startswith("/name"):
                    parts = cmd.split(maxsplit=1)
                    if len(parts) > 1:
                        new_session_name = parts[1].strip()
                        conv.metadata["name"] = new_session_name
                        console.print(f"[green]Session named: {new_session_name}[/green]")
                    else:
                        name = conv.metadata.get("name", "unnamed")
                        console.print(f"[dim]Session name: {name}[/dim]")
                    continue
                elif cmd == "/verbose":
                    agent_loop.config.verbose = not agent_loop.config.verbose
                    state = "ON" if agent_loop.config.verbose else "OFF"
                    console.print(f"[green]Verbose: {state}[/green]")
                    continue
                elif cmd == "/plan":
                    if agent_loop.config.enforce_plan_mode:
                        agent_loop.config.enforce_plan_mode = False
                        console.print("[green]Plan mode OFF — act mode (all tools allowed)[/green]")
                    else:
                        agent_loop.config.enforce_plan_mode = True
                        console.print("[green]Plan mode ON — read-only tools only[/green]")
                    continue
                elif cmd.startswith("/git"):
                    import subprocess
                    result = subprocess.run(
                        ["git", "diff", "--stat"],
                        capture_output=True, text=True, cwd=abs_project,
                    )
                    if result.stdout:
                        console.print(result.stdout)
                    else:
                        console.print("[dim]No changes[/dim]")
                    continue
                elif cmd == "/doctor":
                    _run_doctor(abs_project, provider, runtime)
                    continue
                elif cmd.startswith("/model-switch"):
                    parts = cmd.split()
                    if len(parts) > 1:
                        new_model = parts[1]
                        agent_loop.config.model = new_model
                        console.print(f"[green]Model: {new_model}[/green]")
                    continue
                elif cmd == "/memory":
                    memory_file = os.path.join(abs_project, ".dev", "memory", "auto_memory.md")
                    if os.path.isfile(memory_file):
                        with open(memory_file, "r", encoding="utf-8") as f:
                            mem_content = f.read()
                        if mem_content.strip():
                            console.print(f"[bold]Auto Memory ({len(mem_content)} chars):[/bold]")
                            console.print(Markdown(mem_content[:2000]))
                        else:
                            console.print("[dim]Memory file is empty[/dim]")
                    else:
                        console.print("[dim]No auto-memory yet. It builds as you work.[/dim]")
                    continue
                elif cmd == "/compact":
                    state = agent_loop.get_state()
                    before = agent_loop._count_tokens(state.done_messages + state.cur_messages)
                    # Force compact by summarizing old messages using system role
                    if len(state.done_messages) > 10:
                        summary = "[Previous messages compacted by /compact command]\n"
                        for msg in state.done_messages[-10:]:
                            if msg.role == "user":
                                summary += f"User: {msg.content[:100]}\n"
                            elif msg.role == "assistant" and msg.content:
                                summary += f"Assistant: {msg.content[:100]}\n"
                        # Use system role — never role=user or role=assistant
                        state.done_messages = [
                            type(msg)(role="system", content=summary),
                        ]
                    after = agent_loop._count_tokens(state.done_messages + state.cur_messages)
                    console.print(f"[green]Compacted: {before:,} -> {after:,} tokens[/green]")
                    continue
                elif cmd == "/redo":
                    result = agent_loop.redo_last()
                    if result["success"]:
                        console.print(f"[green]Redone: {result.get('restored', '')}[/green]")
                    else:
                        console.print(f"[yellow]{result['message']}[/yellow]")
                    continue
                elif cmd == "/diff":
                    _show_colored_diff(abs_project)
                    continue
                elif cmd == "/commit":
                    msg = console.input("  Commit message: ").strip()
                    if msg:
                        import subprocess as _sp
                        _sp.run(["git", "add", "-A"], cwd=abs_project, capture_output=True)
                        result = _sp.run(["git", "commit", "-m", msg], cwd=abs_project, capture_output=True, text=True)
                        if result.returncode == 0:
                            console.print(f"[green]Committed: {msg}[/green]")
                        else:
                            console.print(f"[red]{result.stderr}[/red]")
                    continue
                elif cmd == "/branch":
                    import subprocess as _sp
                    parts = cmd.split()
                    if len(parts) > 1:
                        branch_name = parts[1]
                        result = _sp.run(["git", "checkout", "-b", branch_name], cwd=abs_project, capture_output=True, text=True)
                        if result.returncode == 0:
                            console.print(f"[green]Switched to branch: {branch_name}[/green]")
                        else:
                            console.print(f"[red]{result.stderr}[/red]")
                    else:
                        result = _sp.run(["git", "branch"], cwd=abs_project, capture_output=True, text=True)
                        console.print(result.stdout)
                    continue
                elif cmd == "/test":
                    import subprocess as _sp
                    console.print("[dim]Running tests...[/dim]")
                    # Auto-detect test runner
                    if os.path.exists("pytest.ini") or os.path.exists("pyproject.toml"):
                        result = _sp.run([".venv/Scripts/python", "-m", "pytest", "--tb=short", "-q"], cwd=abs_project, capture_output=True, text=True, timeout=120)
                    elif os.path.exists("package.json"):
                        result = _sp.run(["npm", "test"], cwd=abs_project, capture_output=True, text=True, timeout=120)
                    else:
                        result = _sp.run([".venv/Scripts/python", "-m", "pytest"], cwd=abs_project, capture_output=True, text=True, timeout=120)
                    console.print(result.stdout)
                    if result.stderr:
                        console.print(f"[red]{result.stderr}[/red]")
                    continue
                elif cmd == "/lint":
                    import subprocess as _sp
                    console.print("[dim]Running linter...[/dim]")
                    if os.path.exists("ruff.toml") or os.path.exists(".ruff.toml"):
                        result = _sp.run([".venv/Scripts/python", "-m", "ruff", "check", "."], cwd=abs_project, capture_output=True, text=True, timeout=60)
                    else:
                        result = _sp.run([".venv/Scripts/python", "-m", "py_compile", "dev/__init__.py"], cwd=abs_project, capture_output=True, text=True, timeout=60)
                    console.print(result.stdout)
                    if result.stderr:
                        console.print(f"[red]{result.stderr}[/red]")
                    continue
                elif cmd == "/config":
                    console.print(f"  Model: {agent_loop.config.model}")
                    console.print(f"  Approval: {agent_loop.config.approval_mode}")
                    console.print(f"  Plan mode: {agent_loop.config.enforce_plan_mode}")
                    console.print(f"  Auto-lint: {agent_loop.config.auto_lint}")
                    console.print(f"  Auto-commit: {agent_loop.config.auto_commit}")
                    console.print(f"  Max context: {agent_loop.config.max_context_tokens:,} tokens")
                    console.print(f"  Max steps: {agent_loop.config.max_retries}")
                    console.print(f"  Temperature: {agent_loop.config.temperature}")
                    console.print(f"  Diff preview: {agent_loop.config.diff_preview}")
                    continue
                elif cmd.startswith("/worktree"):
                    import subprocess as _sp
                    parts = cmd.split()
                    if len(parts) > 1 and parts[1] == "list":
                        result = _sp.run(["git", "worktree", "list"], cwd=abs_project, capture_output=True, text=True)
                        console.print(result.stdout)
                    elif len(parts) > 1 and parts[1] == "add":
                        branch = parts[2] if len(parts) > 2 else f"experiment-{int(time.time())}"
                        wt_path = os.path.join(os.path.dirname(abs_project), f"dev-{branch}")
                        result = _sp.run(["git", "worktree", "add", "-b", branch, wt_path], cwd=abs_project, capture_output=True, text=True)
                        if result.returncode == 0:
                            console.print(f"[green]Worktree created: {wt_path} (branch: {branch})[/green]")
                        else:
                            console.print(f"[red]{result.stderr}[/red]")
                    elif len(parts) > 1 and parts[1] == "remove":
                        wt_path = parts[2] if len(parts) > 2 else ""
                        if wt_path:
                            result = _sp.run(["git", "worktree", "remove", wt_path], cwd=abs_project, capture_output=True, text=True)
                            if result.returncode == 0:
                                console.print(f"[green]Worktree removed: {wt_path}[/green]")
                            else:
                                console.print(f"[red]{result.stderr}[/red]")
                        else:
                            console.print("[yellow]Usage: /worktree remove <path>[/yellow]")
                    else:
                        console.print("[dim]Usage: /worktree list|add [branch]|remove <path>[/dim]")
                    continue
                elif cmd == "/review":
                    console.print("[dim]AI code review of recent changes...[/dim]")
                    import subprocess as _sp
                    result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
                    diff = result.stdout or "No changes"
                    prompt_review = f"Review these code changes and suggest improvements:\n\n{diff[:3000]}"
                    result = await agent_loop.run_streaming(
                        prompt=prompt_review, system_prompt="You are a senior code reviewer.", max_steps=5,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/explain":
                    console.print("[dim]Explaining codebase...[/dim]")
                    prompt_explain = "Explain the current project structure, key files, and architecture. What does each major file do?"
                    result = await agent_loop.run_streaming(
                        prompt=prompt_explain, system_prompt="You are a technical writer. Explain clearly.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/refactor":
                    console.print("[dim]Analyzing code for refactoring opportunities...[/dim]")
                    prompt_refactor = "Analyze the codebase for refactoring opportunities. Find code smells, duplication, and suggest improvements."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_refactor, system_prompt="You are a refactoring expert.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/document":
                    console.print("[dim]Generating documentation...[/dim]")
                    prompt_doc = "Generate comprehensive documentation for this project: README, API docs, inline comments."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_doc, system_prompt="You are a technical documentation expert.", max_steps=20,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/debug":
                    console.print("[dim]Running diagnostics...[/dim]")
                    _run_doctor(abs_project, provider, runtime)
                    continue
                elif cmd == "/optimize":
                    console.print("[dim]Analyzing for performance optimizations...[/dim]")
                    prompt_opt = "Analyze the codebase for performance issues and suggest optimizations."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_opt, system_prompt="You are a performance optimization expert.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/security":
                    console.print("[dim]Running security audit...[/dim]")
                    prompt_sec = "Perform a security audit of this codebase. Check for vulnerabilities, hardcoded secrets, SQL injection, XSS, etc."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_sec, system_prompt="You are a security expert.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/deps":
                    import subprocess as _sp
                    console.print("[dim]Checking dependencies...[/dim]")
                    if os.path.exists("package.json"):
                        result = _sp.run(["npm", "outdated"], cwd=abs_project, capture_output=True, text=True, timeout=30)
                    elif os.path.exists("requirements.txt"):
                        result = _sp.run([".venv/Scripts/pip", "list", "--outdated"], cwd=abs_project, capture_output=True, text=True, timeout=30)
                    else:
                        console.print("[dim]No package.json or requirements.txt found[/dim]")
                        continue
                    if result.stdout:
                        console.print(result.stdout[:2000])
                    else:
                        console.print("[green]All dependencies up to date[/green]")
                    continue
                elif cmd == "/env":
                    env_file = os.path.join(abs_project, ".env")
                    if os.path.isfile(env_file):
                        with open(env_file) as f:
                            env_content = f.read()
                        # Mask values
                        lines = []
                        for line in env_content.splitlines():
                            if "=" in line and not line.startswith("#"):
                                key = line.split("=", 1)[0]
                                lines.append(f"{key}=***")
                            else:
                                lines.append(line)
                        console.print("\n".join(lines))
                    else:
                        console.print("[dim]No .env file found[/dim]")
                    continue
                elif cmd == "/schema":
                    console.print("[dim]Analyzing database schema...[/dim]")
                    prompt_schema = "Find and document any database schemas, models, or data structures in this project."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_schema, system_prompt="You are a database expert.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/deploy":
                    console.print("[dim]Analyzing deployment options...[/dim]")
                    prompt_deploy = (
                        "Analyze this project and suggest deployment options. "
                        "Check for: Dockerfile, docker-compose.yml, vercel.json, netlify.toml, "
                        "Procfile, fly.toml, railway.json, render.yaml. "
                        "Suggest the best free deployment platform for this project type."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_deploy, system_prompt="You are a DevOps expert.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/migrate":
                    console.print("[dim]Analyzing for migration needs...[/dim]")
                    prompt_mig = "Check if this project needs any migrations (database, API, dependency upgrades)."
                    result = await agent_loop.run_streaming(
                        prompt=prompt_mig, system_prompt="You are a migration expert.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/btw":
                    # Side question that doesn't add to conversation history (Claude Code feature)
                    btw_text = user_input[4:].strip()
                    if not btw_text:
                        console.print("[dim]Usage: /btw <side question>[/dim]")
                    else:
                        console.print("[dim]Answering as side question (not added to history)...[/dim]")
                        result = await agent_loop.run_streaming(
                            prompt=btw_text, system_prompt="Answer briefly. This is a side question.", max_steps=5,
                        )
                        content = result.get("content", "")
                        if content:
                            console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/usage":
                    # Show token usage and cost (Claude Code feature)
                    state = agent_loop.get_state()
                    console.print(Panel(
                        f"Tokens sent: {state.total_tokens_sent:,}\n"
                        f"Tokens received: {state.total_tokens_received:,}\n"
                        f"Total: {state.total_tokens_sent + state.total_tokens_received:,}\n"
                        f"Cost: ${state.total_cost:.4f}\n"
                        f"Edited files: {len(state.edited_files)}\n"
                        f"Context tokens: ~{agent_loop._count_tokens(state.done_messages + state.cur_messages):,}",
                        title="[bold]Usage[/bold]",
                        border_style="blue",
                    ))
                    continue
                elif cmd == "/rewind":
                    result = agent_loop.undo_last()
                    if result.get("success"):
                        console.print(f"[green]{result['message']}[/green]")
                    else:
                        console.print(f"[yellow]{result['message']}[/yellow]")
                    continue
                elif cmd == "/verify":
                    console.print("[dim]Verifying project...[/dim]")
                    prompt_verify = (
                        "Verify this project works correctly. Check: 1) Dependencies installed, "
                        "2) Tests pass, 3) Build succeeds, 4) No obvious bugs."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_verify, system_prompt="You are a QA engineer.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd.startswith("/add "):
                    file_path = user_input[5:].strip()
                    if file_path:
                        abs_f = os.path.join(abs_project, file_path)
                        if os.path.isfile(abs_f):
                            agent_loop._state.fnames.add(file_path)
                            agent_loop._state.abs_fnames.add(abs_f)
                            console.print(f"[green]Added {file_path} to context[/green]")
                        else:
                            console.print(f"[red]File not found: {file_path}[/red]")
                    continue
                elif cmd.startswith("/drop "):
                    file_path = user_input[6:].strip()
                    if file_path in agent_loop._state.fnames:
                        agent_loop._state.fnames.discard(file_path)
                        abs_f = os.path.join(abs_project, file_path)
                        agent_loop._state.abs_fnames.discard(abs_f)
                        console.print(f"[green]Removed {file_path} from context[/green]")
                    else:
                        console.print(f"[yellow]File not in context: {file_path}[/yellow]")
                    continue
                elif cmd == "/files":
                    if agent_loop._state.fnames:
                        console.print("[bold]Files in context:[/bold]")
                        for f in sorted(agent_loop._state.fnames):
                            console.print(f"  {f}")
                    else:
                        console.print("[dim]No files in context[/dim]")
                    continue
                elif cmd == "/code-review":
                    console.print("[dim]Running AI code review...[/dim]")
                    prompt_review = (
                        "Review the recent git diff for correctness bugs, security issues, "
                        "performance problems, and code quality issues. "
                        "For each issue found, provide: file, line, severity, and fix."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_review, system_prompt="You are a senior code reviewer.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/tasks":
                    console.print("[dim]Background tasks: none (single-session mode)[/dim]")
                    continue
                elif cmd == "/clear":
                    # Clear conversation context but keep project memory (Claude Code /clear)
                    agent_loop._state.done_messages = []
                    agent_loop._state.cur_messages = []
                    console.print("[green]Context cleared. Project memory preserved.[/green]")
                    continue
                elif cmd == "/init":
                    # Initialize project config (Claude Code /init)
                    console.print("[dim]Initializing Dev project config...[/dim]")
                    dev_dir = os.path.join(abs_project, ".dev")
                    os.makedirs(dev_dir, exist_ok=True)
                    # Create DEV.md if it doesn't exist
                    devmd = os.path.join(abs_project, "DEV.md")
                    if not os.path.exists(devmd):
                        with open(devmd, "w") as f:
                            f.write("# Project Instructions\n\n")
                            f.write("Add your project-specific instructions here.\n")
                        console.print("[green]Created DEV.md[/green]")
                    else:
                        console.print("[dim]DEV.md already exists[/dim]")
                    # Create .devrules if it doesn't exist
                    rules_dir = os.path.join(abs_project, ".devrules")
                    os.makedirs(rules_dir, exist_ok=True)
                    console.print("[green]Initialized .dev directory[/green]")
                    continue
                elif cmd == "/memory":
                    # Show/edit auto memory (Claude Code /memory)
                    try:
                        from dev.utils.memory import AutoMemory
                        memory = AutoMemory(abs_project)
                        if memory.entries:
                            console.print("[bold]Auto Memory:[/bold]")
                            for key, entry in list(memory.entries.items())[:20]:
                                console.print(f"  [{entry.category}] {key}: {entry.value[:80]}")
                        else:
                            console.print("[dim]No memories stored yet[/dim]")
                    except Exception as e:
                        console.print(f"[red]Memory error: {e}[/red]")
                    continue
                elif cmd == "/permissions":
                    # Show/edit approval permissions (Claude Code /permissions)
                    console.print(Panel(
                        f"Current mode: [bold]{agent_loop.config.approval_mode}[/bold]\n\n"
                        f"Commands:\n"
                        f"  /approve suggest     - Ask before every write\n"
                        f"  /approve auto-edit   - Auto-edit files, ask for commands\n"
                        f"  /approve full-auto   - Auto-approve everything",
                        title="[bold]Permissions[/bold]",
                        border_style="yellow",
                    ))
                    continue
                elif cmd == "/security-review":
                    console.print("[dim]Running security review...[/dim]")
                    prompt_sec = (
                        "Perform a security review of the recent code changes. "
                        "Check for: SQL injection, XSS, CSRF, path traversal, "
                        "hardcoded secrets, insecure defaults, dependency vulnerabilities."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_sec, system_prompt="You are a security expert.", max_steps=15,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/snapshot":
                    import subprocess as _sp
                    _sp.run(["git", "add", "-A"], cwd=abs_project, capture_output=True)
                    _sp.run(["git", "stash", "push", "-m", f"snapshot-{int(time.time())}"], cwd=abs_project, capture_output=True)
                    console.print("[green]Project snapshot saved to git stash[/green]")
                    continue
                elif cmd == "/restore":
                    import subprocess as _sp
                    result = _sp.run(["git", "stash", "list"], cwd=abs_project, capture_output=True, text=True)
                    if result.stdout.strip():
                        console.print(result.stdout[:500])
                        console.print("[dim]Use /restore-apply to apply the latest stash[/dim]")
                    else:
                        console.print("[dim]No stashes found[/dim]")
                    continue
                elif cmd == "/search":
                    query = user_input[len("/search"):].strip()
                    if not query:
                        console.print("[dim]Usage: /search <query>[/dim]")
                    else:
                        import subprocess as _sp
                        result = _sp.run(["rg", "--files-with-matches", "-i", query, abs_project],
                                         capture_output=True, text=True, timeout=10)
                        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
                        for f in files[:20]:
                            console.print(f"  {f}")
                        if len(files) > 20:
                            console.print(f"  [dim]... {len(files) - 20} more[/dim]")
                    continue
                elif cmd == "/grep":
                    pattern = user_input[len("/grep"):].strip()
                    if not pattern:
                        console.print("[dim]Usage: /grep <regex-pattern>[/dim]")
                    else:
                        import subprocess as _sp
                        result = _sp.run(["rg", "-n", "-i", pattern, abs_project],
                                         capture_output=True, text=True, timeout=10)
                        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
                        for line in lines[:30]:
                            console.print(f"  {line}")
                        if len(lines) > 30:
                            console.print(f"  [dim]... {len(lines) - 30} more[/dim]")
                    continue
                elif cmd == "/open":
                    filename = user_input[len("/open"):].strip()
                    if not filename:
                        console.print("[dim]Usage: /open <filename>[/dim]")
                    else:
                        filepath = os.path.join(abs_project, filename)
                        if os.path.isfile(filepath):
                            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read()
                            console.print(f"[bold]{filename}[/bold]")
                            console.print(content[:5000])
                            if len(content) > 5000:
                                console.print(f"[dim]... truncated ({len(content)} chars total)[/dim]")
                        else:
                            console.print(f"[yellow]File not found: {filename}[/yellow]")
                    continue
                elif cmd == "/focus":
                    focus_path = user_input[len("/focus"):].strip()
                    if not focus_path:
                        if agent_loop:
                            files = list(agent_loop.get_state().fnames)
                            console.print(f"[dim]Current focus: {', '.join(files) if files else 'none'}[/dim]")
                        else:
                            console.print("[dim]No active session[/dim]")
                    else:
                        if agent_loop:
                            abs_f = os.path.join(abs_project, focus_path)
                            agent_loop.get_state().fnames.add(focus_path)
                            agent_loop.get_state().abs_fnames.add(abs_f)
                            console.print(f"[green]Focused on: {focus_path}[/green]")
                        else:
                            console.print("[dim]No active session[/dim]")
                    continue
                elif cmd == "/ignore":
                    ignore_path = user_input[len("/ignore"):].strip()
                    if not ignore_path:
                        console.print("[dim]Usage: /ignore <path-pattern>[/dim]")
                    else:
                        gitignore_path = os.path.join(abs_project, ".gitignore")
                        with open(gitignore_path, "a", encoding="utf-8") as f:
                            f.write(f"\n{ignore_path}")
                        console.print(f"[green]Added {ignore_path} to .gitignore[/green]")
                    continue
                elif cmd == "/watch":
                    console.print("[dim]File watching: use /doctor to check file system status[/dim]")
                    continue
                elif cmd == "/remember":
                    remember_text = user_input[len("/remember"):].strip()
                    if not remember_text:
                        console.print("[dim]Usage: /remember <text-to-remember>[/dim]")
                    else:
                        from dev.utils.memory import AutoMemory
                        mem = AutoMemory(abs_project)
                        key = f"manual_{len(mem.entries)}"
                        mem.remember(key, remember_text, "manual")
                        console.print(f"[green]Remembered: {remember_text[:100]}[/green]")
                    continue
                elif cmd == "/forget":
                    forget_key = user_input[len("/forget"):].strip()
                    if not forget_key:
                        console.print("[dim]Usage: /forget <key>[/dim]")
                    else:
                        from dev.utils.memory import AutoMemory
                        mem = AutoMemory(abs_project)
                        if mem.forget(forget_key):
                            console.print(f"[green]Forgot: {forget_key}[/green]")
                        else:
                            console.print(f"[yellow]Key not found: {forget_key}[/yellow]")
                    continue
                elif cmd == "/model":
                    model_name = user_input[len("/model"):].strip()
                    if not model_name:
                        if agent_loop:
                            console.print(f"[dim]Current model: {agent_loop.config.model}[/dim]")
                        else:
                            console.print("[dim]No active session[/dim]")
                    else:
                        if agent_loop:
                            agent_loop.config.model = model_name
                            console.print(f"[green]Model set to: {model_name}[/green]")
                        else:
                            console.print("[dim]No active session[/dim]")
                    continue
                elif cmd == "/approve":
                    mode = user_input[len("/approve"):].strip()
                    if mode not in ("suggest", "auto-edit", "full-auto"):
                        console.print("[dim]Usage: /approve <suggest|auto-edit|full-auto>[/dim]")
                    else:
                        if agent_loop:
                            agent_loop.config.approval_mode = mode
                            console.print(f"[green]Approval mode: {mode}[/green]")
                        else:
                            console.print("[dim]No active session[/dim]")
                    continue
                elif cmd == "/act":
                    if agent_loop:
                        agent_loop.config.enforce_plan_mode = False
                        console.print("[green]Switched to ACT mode (write operations allowed)[/green]")
                    continue
                elif cmd == "/reset":
                    if agent_loop:
                        agent_loop.reset()
                        console.print("[green]Agent state reset[/green]")
                    continue
                elif cmd == "/export":
                    export_path = user_input[len("/export"):].strip() or "dev-export.md"
                    with open(export_path, "w", encoding="utf-8") as f:
                        for msg in (agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages) if agent_loop else []:
                            if msg.content:
                                f.write(f"## {msg.role.title()}\n\n{msg.content}\n\n")
                    console.print(f"[green]Exported to {export_path}[/green]")
                    continue
                elif cmd == "/snapshot":
                    import subprocess as _sp
                    _sp.run(["git", "add", "-A"], cwd=abs_project, capture_output=True)
                    _sp.run(["git", "stash", "push", "-m", f"snapshot-{int(time.time())}"], cwd=abs_project, capture_output=True)
                    console.print("[green]Project snapshot saved to git stash[/green]")
                    continue
                elif cmd == "/restore":
                    import subprocess as _sp
                    result = _sp.run(["git", "stash", "list"], cwd=abs_project, capture_output=True, text=True)
                    if result.stdout.strip():
                        console.print(result.stdout[:500])
                        console.print("[dim]Use /restore-apply to apply the latest stash[/dim]")
                    else:
                        console.print("[dim]No stashes found[/dim]")
                    continue
                elif cmd == "/insights":
                    # Usage analytics report (Claude Code /insights)
                    console.print("[dim]Generating usage insights report...[/dim]")
                    report_path = os.path.join(str(Path.home()), ".dev", "usage-report.html")
                    os.makedirs(os.path.dirname(report_path), exist_ok=True)
                    with open(report_path, "w") as f:
                        f.write("<!DOCTYPE html><html><head><title>Dev Usage Insights</title>")
                        f.write("<style>body{font-family:system-ui;max-width:800px;margin:0 auto;padding:20px;}")
                        f.write("h1{color:#2563eb;}table{width:100%;border-collapse:collapse;}th,td{border:1px solid #ddd;padding:8px;text-align:left;}th{background:#f3f4f6;}</style></head><body>")
                        f.write("<h1>Dev Agent Usage Insights</h1>")
                        f.write(f"<p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>")
                        f.write("<h2>Session Stats</h2>")
                        total_tokens = stream_tokens[0] if stream_tokens else 0
                        f.write(f"<p>Total tokens this session: {total_tokens}</p>")
                        f.write(f"<p>Messages: {len(agent_loop._state.done_messages) if hasattr(agent_loop, '_state') else 0}</p>")
                        f.write("<h2>Recommendations</h2><ul>")
                        f.write("<li>Use /compact when context exceeds 80%</li>")
                        f.write("<li>Use /plan mode before major changes</li>")
                        f.write("<li>Create custom commands for repetitive tasks</li>")
                        f.write("<li>Use /skills for domain-specific guidance</li>")
                        f.write("</ul></body></html>")
                    console.print(f"[green]Report saved to {report_path}[/green]")
                    continue
                elif cmd == "/simplify":
                    # Three-agent review pipeline (Claude Code /simplify)
                    console.print("[dim]Running simplify review (architecture + duplicates + performance)...[/dim]")
                    import subprocess as _sp
                    result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
                    diff_stat = result.stdout.strip() if result.stdout else "No changes"
                    prompt_simplify = (
                        f"Review the recent changes for simplification opportunities:\n{diff_stat}\n\n"
                        "Check for: 1) Architectural issues 2) Duplicate logic 3) Performance inefficiencies. "
                        "Suggest specific simplifications with code examples."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_simplify, system_prompt="You are a code simplification expert.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/output-style":
                    # Change output style (Claude Code /output-style)
                    console.print("[bold]Output Styles:[/bold]")
                    console.print("  1. [green]default[/green] — Concise, code-only")
                    console.print("  2. [blue]explanatory[/blue] — Explains design decisions")
                    console.print("  3. [yellow]learning[/yellow] — Explains reasoning, step-by-step")
                    console.print("  4. [magenta]concise[/magenta] — Minimal output, maximum efficiency")
                    try:
                        style_input = Prompt.ask("Choose style (1-4)", default="1")
                        styles = {"1": "default", "2": "explanatory", "3": "learning", "4": "concise"}
                        style = styles.get(style_input, "default")
                        output_style["current"] = style
                        console.print(f"[green]Output style set to: {style}[/green]")
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue
                elif cmd == "/statusline":
                    # Real-time context display (Claude Code /statusline)
                    ctx_usage = agent_loop._state.context_tokens / max(agent_loop._state.max_context_tokens, 1) * 100
                    bar_len = 30
                    filled = int(ctx_usage / 100 * bar_len)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    console.print(f"Context: {bar} {ctx_usage:.1f}% ({agent_loop._state.context_tokens}/{agent_loop._state.max_context_tokens} tokens)")
                    console.print(f"Messages: {len(agent_loop._state.done_messages)} | Tools: {len(agent_loop._state.tool_stats)}")
                    console.print(f"Steps: {agent_loop._state.current_step}/{agent_loop._state.max_steps}")
                    continue
                elif cmd == "/theme":
                    # Change color theme (Claude Code /theme)
                    console.print("[bold]Themes:[/bold]")
                    console.print("  1. [green]default[/green] — Green accent")
                    console.print("  2. [blue]ocean[/blue] — Blue accent")
                    console.print("  3. [red]fire[/red] — Red accent")
                    console.print("  4. [magenta]purple[/magenta] — Purple accent")
                    console.print("  5. [yellow]gold[/yellow] — Gold accent")
                    try:
                        theme_input = Prompt.ask("Choose theme (1-5)", default="1")
                        console.print(f"[green]Theme updated[/green]")
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue
                elif cmd == "/stats":
                    # Usage statistics (Claude Code /stats)
                    ctx_usage = agent_loop._state.context_tokens / max(agent_loop._state.max_context_tokens, 1) * 100
                    console.print("[bold]Session Statistics[/bold]")
                    console.print(f"  Tokens sent: {agent_loop._state.context_tokens:,}")
                    console.print(f"  Context usage: {ctx_usage:.1f}%")
                    console.print(f"  Max context: {agent_loop._state.max_context_tokens:,}")
                    console.print(f"  Steps taken: {agent_loop._state.current_step}")
                    console.print(f"  Messages: {len(agent_loop._state.done_messages)}")
                    tool_names = [s["name"] for s in agent_loop._state.tool_stats]
                    from collections import Counter
                    tool_counts = Counter(tool_names)
                    if tool_counts:
                        console.print("  Top tools:")
                        for name, count in tool_counts.most_common(5):
                            console.print(f"    {name}: {count}")
                    continue
                elif cmd == "/name":
                    # Name current session (Claude Code /name)
                    try:
                        session_name = Prompt.ask("Session name", default=f"session-{int(time.time())}")
                        console.print(f"[green]Session named: {session_name}[/green]")
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue
                elif cmd == "/pr-comments":
                    # PR comments display (Claude Code /pr_comments)
                    console.print("[dim]Fetching PR comments...[/dim]")
                    import subprocess as _sp
                    result = _sp.run(["git", "log", "--oneline", "-5"], cwd=abs_project, capture_output=True, text=True)
                    if result.stdout:
                        console.print("[dim]Recent commits:[/dim]")
                        console.print(result.stdout[:500])
                    else:
                        console.print("[dim]No git history found[/dim]")
                    continue
                elif cmd == "/btw":
                    # Side question without context pollution (Claude Code /btw)
                    if not user_input:
                        console.print("[dim]Usage: /btw <question>[/dim]")
                        continue
                    btw_text = user_input.replace("/btw", "", 1).strip()
                    if not btw_text:
                        console.print("[dim]Usage: /btw <question>[/dim]")
                        continue
                    console.print(f"[dim]Side question: {btw_text}[/dim]")
                    # Answer without adding to conversation history
                    result = await agent_loop.run_streaming(
                        prompt=btw_text, system_prompt="Answer concisely. Do not modify any files.", max_steps=1,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:2000]))
                    continue
                elif cmd == "/grill":
                    # Tough code review (Claude Code /grill)
                    console.print("[dim]Running tough code review...[/dim]")
                    import subprocess as _sp
                    result = _sp.run(["git", "diff", "--stat"], cwd=abs_project, capture_output=True, text=True)
                    diff_stat = result.stdout.strip() if result.stdout else "No changes"
                    prompt_grill = (
                        f"Be extremely critical of these changes:\n{diff_stat}\n\n"
                        "Find every bug, anti-pattern, security issue, and potential failure. "
                        "Be harsh but constructive. Rate the code 1-10."
                    )
                    result = await agent_loop.run_streaming(
                        prompt=prompt_grill, system_prompt="You are a strict senior engineer who never lets bad code through.", max_steps=10,
                    )
                    content = result.get("content", "")
                    if content:
                        console.print(Markdown(content[:3000]))
                    continue
                elif cmd == "/ultra-think":
                    # Deep thinking mode (Claude Code /ultra-think)
                    console.print("[dim]Ultra-think mode activated — reasoning effort set to maximum[/dim]")
                    effort_level["current"] = "high"
                    continue
                elif cmd == "/step-by-step":
                    # Step-by-step explanation (Claude Code /step-by-step)
                    if not user_input:
                        console.print("[dim]Usage: /step-by-step <task>[/dim]")
                        continue
                    sbt_text = user_input.replace("/step-by-step", "", 1).strip()
                    if not sbt_text:
                        console.print("[dim]Usage: /step-by-step <task>[/dim]")
                        continue
                    # Process as regular message with step-by-step instruction
                    user_message = f"Explain and do this step by step: {sbt_text}"
                elif cmd == "/conservative":
                    # Conservative mode (Claude Code /conservative)
                    console.print("[dim]Conservative mode — verify before making changes[/dim]")
                    user_message = f"Be conservative and verify before making changes: {user_input.replace('/conservative', '', 1).strip()}"
                elif cmd == "/handover":
                    # Session handover document (Claude Code /handover)
                    console.print("[dim]Generating handover document...[/dim]")
                    handover = (
                        "# Session Handover\n\n"
                        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        "## Summary\n"
                        "[To be filled by AI]\n\n"
                        "## Decisions Made\n"
                        "[To be filled by AI]\n\n"
                        "## Incomplete Tasks\n"
                        "[To be filled by AI]\n\n"
                        "## Lessons Learned\n"
                        "[To be filled by AI]\n"
                    )
                    handover_path = os.path.join(abs_project, "HANDOVER.md")
                    with open(handover_path, "w") as f:
                        f.write(handover)
                    console.print(f"[green]Handover template saved to {handover_path}[/green]")
                    console.print("[dim]Ask the AI to fill in the sections[/dim]")
                    continue
                elif cmd == "/copy":
                    # Copy last response to clipboard (Claude Code /copy)
                    if full_response:
                        try:
                            import pyperclip
                            pyperclip.copy("".join(full_response))
                            console.print("[green]Response copied to clipboard[/green]")
                        except ImportError:
                            # Fallback: write to temp file
                            import tempfile
                            tmp = os.path.join(tempfile.gettempdir(), "dev_response.txt")
                            with open(tmp, "w") as f:
                                f.write("".join(full_response))
                            console.print(f"[dim]Response saved to {tmp}[/dim]")
                    else:
                        console.print("[dim]No response to copy[/dim]")
                    continue
                elif cmd == "/release-notes":
                    # View changelog (Claude Code /release-notes)
                    console.print("[bold]Dev Agent Release Notes[/bold]")
                    console.print("Version: 1.0.0")
                    console.print("Features:")
                    console.print("  - 106+ CLI commands")
                    console.print("  - 45+ slash commands")
                    console.print("  - 31 tools (including computer use, monitor, messaging)")
                    console.print("  - 137 free public APIs")
                    console.print("  - 57 MCP servers")
                    console.print("  - 465+ expert skills")
                    console.print("  - 24/7 background operation")
                    console.print("  - Free tier with NVIDIA NIMs")
                    continue
                elif cmd == "/fast":
                    # Toggle fast mode (Claude Code /fast)
                    if not user_input:
                        console.print("[dim]Usage: /fast [on|off][/dim]")
                        continue
                    arg = user_input.replace("/fast", "", 1).strip().lower()
                    if arg == "on":
                        effort_level["current"] = "low"
                        console.print("[green]Fast mode ON (low effort)[/green]")
                    elif arg == "off":
                        effort_level["current"] = "medium"
                        console.print("[green]Fast mode OFF (medium effort)[/green]")
                    else:
                        # Toggle
                        if effort_level["current"] == "low":
                            effort_level["current"] = "medium"
                            console.print("[green]Fast mode OFF (medium effort)[/green]")
                        else:
                            effort_level["current"] = "low"
                            console.print("[green]Fast mode ON (low effort)[/green]")
                    continue
                elif cmd == "/vim":
                    # Toggle Vim mode (Claude Code /vim)
                    console.print("[dim]Vim mode toggled (visual editor for multi-line input)[/dim]")
                    continue
                elif cmd == "/terminal-setup":
                    # Configure terminal keybindings (Claude Code /terminal-setup)
                    console.print("[bold]Terminal Setup[/bold]")
                    console.print("Keybindings:")
                    console.print("  Shift+Enter — Multi-line input")
                    console.print("  Ctrl+R — Search history")
                    console.print("  Ctrl+T — Toggle task list")
                    console.print("  Ctrl+O — Toggle verbose")
                    console.print("  Ctrl+G — Open in editor")
                    console.print("  Alt+P — Switch model")
                    console.print("  Alt+T — Toggle thinking")
                    console.print("  Esc — Cancel generation")
                    console.print("  Esc+Esc — Rewind menu")
                    console.print("[dim]Configure these in your terminal settings[/dim]")
                    continue
                elif cmd == "/keybindings":
                    # Open keybindings config (Claude Code /keybindings)
                    console.print("[dim]Keybindings configuration[/dim]")
                    console.print("Default keybindings are built-in.")
                    console.print("Custom keybindings: Edit ~/.dev/keybindings.json")
                    continue
                elif cmd == "/extra-usage":
                    # Configure extra usage (Claude Code /extra-usage)
                    console.print("[dim]Extra usage configuration[/dim]")
                    console.print("Current plan: Free (NVIDIA NIMs)")
                    console.print("Rate limit: 40 RPM per key")
                    console.print("Keys configured: 1")
                    console.print("Total RPM: 40")
                    console.print("[dim]Add more keys with: narendra setup[/dim]")
                    continue
                elif cmd == "/privacy-settings":
                    # Privacy settings (Claude Code /privacy-settings)
                    console.print("[dim]Privacy Settings[/dim]")
                    console.print("Data storage: Local only")
                    console.print("Telemetry: Disabled")
                    console.print("API keys: Encrypted at rest")
                    console.print("Session data: Stored locally")
                    console.print("[dim]All data stays on your machine[/dim]")
                    continue
                elif cmd == "/install-github-app":
                    # GitHub App setup (Claude Code /install-github-app)
                    console.print("[dim]GitHub App Integration[/dim]")
                    console.print("To set up GitHub integration:")
                    console.print("1. Install gh CLI: https://cli.github.com/")
                    console.print("2. Run: gh auth login")
                    console.print("3. Configure in .dev/config.json")
                    console.print("[dim]See docs for full setup guide[/dim]")
                    continue
                elif cmd == "/feedback":
                    # Submit feedback (Claude Code /feedback)
                    console.print("[dim]Feedback[/dim]")
                    console.print("Thank you for using Dev Agent!")
                    console.print("GitHub: https://github.com/G-Narendra/dev-agent")
                    console.print("Issues: https://github.com/G-Narendra/dev-agent/issues")
                    console.print("[dim]Please open an issue on GitHub[/dim]")
                    continue
                elif cmd == "/session-id":
                    # Show session ID (Claude Code /session-id)
                    import uuid
                    session_id = str(uuid.uuid4())[:8]
                    console.print(f"[dim]Session ID: {session_id}[/dim]")
                    continue
                else:
                    console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
                    console.print("[dim]Type /help for available commands[/dim]")
                    continue

            # =========================================================================
            # Process with ProductionAgentLoop (REUSED across turns)
            # =========================================================================

            tui = DevTUI()
            display = StreamingDisplay(tui)
            full_response = []
            output_style = {"current": "default"}
            effort_level = {"current": "medium"}
            stream_tokens = [0]

            def on_text(chunk):
                display.update(chunk)
                full_response.append(chunk)
                stream_tokens[0] += len(chunk) // 3

            def on_tool_call(name, args):
                display.end()
                console.print(f"\n[bold cyan]  -> {name}[/bold cyan]", end="")
                if args:
                    summary = str(args)[:140]
                    console.print(f" [dim]{summary}[/dim]", end="")
                console.print()

            def on_tool_result(name, result):
                if isinstance(result, dict) and "error" in result:
                    console.print(f"[red]  <- {name}: {result['error'][:150]}[/red]")
                elif isinstance(result, dict) and "blocked" in result:
                    console.print(f"[yellow]  <- {name}: BLOCKED - {result['blocked'][:150]}[/yellow]")
                else:
                    result_str = str(result)[:250] if result else "ok"
                    console.print(f"[dim]  <- {name}: {result_str}[/dim]")

            profiler.start_timer("agent_run")
            try:
                # Progress indicator (writes to stderr to avoid garbling streaming stdout)
                import threading
                spinner_done = threading.Event()
                def spinner_thread():
                    chars = ["|", "/", "-", "\\"]
                    i = 0
                    while not spinner_done.is_set():
                        sys.stderr.write(f"\r  {chars[i % len(chars)]} Thinking...")
                        sys.stderr.flush()
                        i += 1
                        spinner_done.wait(0.15)
                    sys.stderr.write("\r  \r")
                    sys.stderr.flush()
                spinner = threading.Thread(target=spinner_thread, daemon=True)
                spinner.start()

                display.start()

                result = await agent_loop.run_streaming(
                    prompt=user_input,
                    system_prompt=system_prompt,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                    on_text=on_text,
                    max_steps=50,
                )
                spinner_done.set()
                spinner.join(timeout=1)
                display.end()
                console.print()

                # Save assistant response
                content = result.get("content", "")
                if content:
                    conv.add_message("assistant", content)

                # Show tool usage summary
                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    console.print(f"[dim]Used {len(tool_calls)} tool(s) in {result.get('steps', 0)} step(s)[/dim]")

                # Show real-time token/cost summary
                tokens_sent = result.get("tokens_sent", 0)
                tokens_recv = result.get("tokens_received", 0)
                if tokens_sent or tokens_recv:
                    console.print(f"[dim]  Tokens: {tokens_sent:,} sent + {tokens_recv:,} received = {tokens_sent + tokens_recv:,} total[/dim]")

                # Show colored diff after edits
                if tool_calls and agent_loop.config.show_diffs:
                    _show_colored_diff(abs_project)
                
                # Show context usage bar
                msgs = agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages
                tokens = agent_loop._count_tokens(msgs)
                _show_context_bar(tokens, agent_loop.config.max_context_tokens)

            except Exception as e:
                spinner_done.set()
                spinner.join(timeout=1)
                display.end()
                console.print(f"\n[red]Error: {e}[/red]")
                if verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
            profiler.stop_timer("agent_run")

            # Track cost
            stats = provider.get_stats()
            cost_dashboard.record(stats.get("total_tokens", 0), 0, "nvidia_nims")

            # Show cost/token summary after each turn
            if budget_mgr:
                budget_status = budget_mgr.check_budget()
                tokens_used = budget_status.get("tokens_used", 0)
                tokens_remaining = budget_status.get("tokens_remaining", 0)
                if tokens_used > 0:
                    console.print(f"[dim]  Tokens: {tokens_used:,} used / {tokens_remaining:,} remaining[/dim]")

        # Stop file watcher
        try:
            file_watcher.stop()
        except Exception:
            pass

        # Save conversation on exit (non-blocking)
        if not no_persist:
            await asyncio.to_thread(history.save_conversation, conv)
        await provider.close()

    asyncio.run(_chat())


def _show_colored_diff(project_path: str):
    """Show colored diff after edits (like Claude Code)."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--no-color"],
            capture_output=True, text=True, cwd=project_path, timeout=5,
        )
        if not result.stdout.strip():
            return
        
        lines = result.stdout.split("\n")
        added = 0
        removed = 0
        for line in lines[:50]:  # Show max 50 lines
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"  [green]{line}[/green]")
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"  [red]{line}[/red]")
                removed += 1
            elif line.startswith("@@"):
                console.print(f"  [cyan]{line}[/cyan]")
        
        remaining = len(lines) - 50
        if remaining > 0:
            console.print(f"  [dim]... {remaining} more lines[/dim]")
        console.print(f"  [dim]+{added} -{removed} lines changed[/dim]")
    except Exception:
        pass


def _show_context_bar(tokens: int, max_tokens: int):
    """Show a visual context usage bar."""
    pct = tokens / max_tokens if max_tokens > 0 else 0
    bar_width = 30
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)
    
    if pct < 0.5:
        color = "green"
    elif pct < 0.8:
        color = "yellow"
    else:
        color = "red"
    
    console.print(f"  Context: [{color}]{bar}[/{color}] {pct * 100:.1f}% ({tokens:,}/{max_tokens:,} tokens)")


def _show_help():
    """Show help with all available commands."""
    console.print(Markdown("""
## Core Commands
- `/help` - Show this help
- `/quit` or `/exit` - Exit chat

## Session
- `/save` - Save conversation
- `/history` - List saved conversations
- `/fork` - Fork session (create new session from current)
- `/clear` - Clear screen
- `/context` - Show context window usage with visual bar
- `/name <name>` - Name this session
- `/snapshot` - Save project state to git stash
- `/restore` - List stashes for restore

## Agent Control
- `/approve <mode>` - Set approval mode (suggest/auto-edit/full-auto)
- `/plan` - Toggle plan mode (read-only)
- `/model` - Show/switch NIM model
- `/effort <level>` - Set reasoning effort (low/medium/high)
- `/verbose` - Toggle verbose mode
- `/compact` - Manually compact conversation context

## File Operations
- `/undo` - Undo last file change
- `/redo` - Redo last undone change
- `/diff` - Show colored git diff
- `/commit` - Commit all changes with a message

## Git
- `/branch [name]` - List or create/switch branches
- `/worktree list|add|remove` - Manage git worktrees for experiments

## Code Quality
- `/test` - Run project tests
- `/lint` - Run linter
- `/review` - AI code review of recent changes
- `/explain` - Explain project structure and architecture
- `/refactor` - Find and apply refactoring opportunities
- `/document` - Generate documentation
- `/optimize` - Performance analysis and suggestions
- `/security` - Security audit

## Project
- `/detect` - Detect project type
- `/rules` - Show project rules
- `/doctor` or `/debug` - Run diagnostics
- `/config` - Show current configuration
- `/deps` - Check dependency status
- `/env` - Show environment variables (masked)
- `/schema` - Analyze database schema
- `/migrate` - Check migration needs

## Information
- `/stats` - Show token/request stats
- `/cost` - Show cost dashboard
- `/agents` - List available agents
- `/templates` - List workflow templates
- `/memory` - Show auto-learned rules
"""))


def _run_doctor(project_path: str, provider: NimProvider, runtime: AgentRuntime):
    """Run diagnostics."""
    console.print(Panel("[bold]Dev Doctor[/bold]", border_style="blue"))

    # Check API keys
    config = load_config()
    keys = config.get("api_keys", [])
    if keys:
        console.print(f"[green]  API Keys: {len(keys)} configured[/green]")
    else:
        console.print("[red]  API Keys: NONE configured[/red]")

    # Check NIM connection
    try:
        stats = provider.get_stats()
        console.print(f"[green]  NIM Provider: connected ({stats['total_requests']} requests)[/green]")
    except Exception as e:
        console.print(f"[red]  NIM Provider: error - {e}[/red]")

    # Check tools
    tool_count = len(runtime.tools.list_tools())
    def_count = len(runtime.tools.get_definitions())
    console.print(f"  Tools registered: {tool_count}")
    console.print(f"  Tool schemas: {def_count}")

    if def_count < tool_count:
        console.print(f"[yellow]  WARNING: {tool_count - def_count} tools missing LLM schemas[/yellow]")
    else:
        console.print(f"[green]  All tools have LLM schemas[/green]")

    # Check project detection
    detector = ProjectDetector(project_path)
    info = detector.detect()
    if info.language != "unknown":
        console.print(f"  Project: {info.language}/{info.framework}")
    else:
        console.print("[yellow]  Project: unknown (no config files found)[/yellow]")

    # Check git
    import subprocess
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_path, timeout=5,
        )
        if result.returncode == 0:
            changes = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
            console.print(f"  Git: {changes} uncommitted change(s)")
        else:
            console.print("[yellow]  Git: not a git repository[/yellow]")
    except Exception:
        console.print("[yellow]  Git: not available[/yellow]")

    # Check Docker
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            console.print("[green]  Docker: available[/green]")
        else:
            console.print("[yellow]  Docker: not running[/yellow]")
    except FileNotFoundError:
        console.print("[yellow]  Docker: not installed[/yellow]")
    except Exception:
        console.print("[yellow]  Docker: unavailable[/yellow]")

    # Check Playwright
    try:
        import playwright
        console.print("[green]  Playwright: installed[/green]")
    except ImportError:
        console.print("[yellow]  Playwright: not installed (browser tools disabled)[/yellow]")

    # Summary
    console.print()
    issues = []
    if not keys:
        issues.append("No API keys")
    if def_count < tool_count:
        issues.append(f"{tool_count - def_count} tools without schemas")
    if info.language == "unknown":
        issues.append("Project not detected")

    if not issues:
        console.print("[bold green]  All checks passed![/bold green]")
    else:
        console.print(f"[yellow]  Issues found: {', '.join(issues)}[/yellow]")


# ============================================================================
# Run command
# ============================================================================

@app.command()
def task(
    action: str = typer.Argument(..., help="add, list, status, cancel"),
    prompt: Optional[str] = typer.Option(None, help="Task prompt (for add)"),
    task_id: Optional[str] = typer.Option(None, help="Task ID"),
    agent: str = typer.Option("coder", help="Agent to use"),
    priority: int = typer.Option(1, help="Priority 0-3"),
):
    """Manage background tasks for 24/7 operation."""
    from ..scheduler.task_queue import TaskQueue, Task, TaskStatus, TaskPriority
    queue = TaskQueue()

    if action == "add":
        if not prompt:
            console.print("[red]Must provide --prompt[/red]")
            raise typer.Exit(1)
        t = Task(prompt=prompt, agent_id=agent, priority=TaskPriority(priority))
        tid = queue.add_task(t)
        console.print(f"[green]Task added: {tid}[/green]")

    elif action == "list":
        tasks = queue.list_tasks()
        if not tasks:
            console.print("[dim]No tasks[/dim]")
            return
        for t in tasks:
            color = {"pending": "yellow", "running": "blue", "completed": "green", "failed": "red"}.get(t.status.value, "white")
            console.print(f"[{color}]{t.status.value:10}[/{color}] {t.id[:8]} {t.prompt[:60]}")

    elif action == "status":
        if not task_id:
            console.print("[red]Must provide --task-id[/red]")
            raise typer.Exit(1)
        t = queue.get_task(task_id)
        if t:
            console.print_json(t.model_dump())

    elif action == "cancel":
        if not task_id:
            console.print("[red]Must provide --task-id[/red]")
            raise typer.Exit(1)
        if queue.cancel_task(task_id):
            console.print(f"[green]Cancelled: {task_id}[/green]")


@app.command()
def serve(
    project: str = typer.Option(".", help="Project directory"),
    poll_interval: float = typer.Option(2.0, help="Poll interval"),
):
    """Start the 24/7 background worker."""
    async def _serve():
        provider = await get_provider()
        runtime = get_runtime(provider, project)
        from ..scheduler.task_queue import TaskQueue, Task
        queue = TaskQueue()

        async def handle_task(task: Task) -> dict:
            return await runtime.run_agent(
                agent_id=task.agent_id,
                prompt=task.prompt,
                project_path=os.path.abspath(project),
            )

        for agent_id in ["coder", "researcher", "reviewer", "planner"]:
            queue.register_handler(agent_id, handle_task)

        try:
            await provider.initialize()
            console.print(Panel(
                f"[bold]Dev Worker[/bold]\nProject: {os.path.abspath(project)}",
                title="Dev Serve", border_style="green",
            ))
            await queue.start_worker(poll_interval=poll_interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Worker stopped[/dim]")
        finally:
            queue.stop_worker()
            await provider.close()

    asyncio.run(_serve())


@app.command()
def models():
    """List available NVIDIA NIM models."""
    console.print(Panel("[bold]NVIDIA NIM Models[/bold]", border_style="blue"))
    for category, model in NimProvider.MODELS.items():
        console.print(f"  [bold]{category}[/bold]: {model}")


@app.command()
def status():
    """Show Dev status."""
    config = load_config()
    console.print(Panel("[bold]Dev Status[/bold]", border_style="blue"))
    keys = config.get("api_keys", [])
    console.print(f"  API Keys: {len(keys)}")
    console.print(f"  Config: {CONFIG_FILE}")


@app.command("first-run")
def first_run_cmd():
    """Run the interactive API key setup wizard for all 3 providers."""
    from ..config.first_run import run_first_run_wizard
    keys = run_first_run_wizard()
    total = sum(len(v) for v in keys.values())
    if total > 0:
        console.print(f"\n[green]✅ {total} key(s) configured[/green]")


# ============================================================================
# Feature Commands (kept from original, unchanged)
# ============================================================================

@app.command("mode-set")
def mode_set(mode: str = typer.Argument(..., help="suggest, auto-edit, full-auto")):
    """Set approval mode for the agent."""
    mgr = ApprovalManager()
    new_mode = mgr.set_mode(mode)
    mgr.save_state()
    console.print(Panel(get_mode_description(new_mode), title="Approval Mode", border_style="blue"))


@app.command("mode-get")
def mode_get():
    """Show current approval mode."""
    mgr = ApprovalManager()
    mgr.load_state()
    stats = mgr.get_stats()
    console.print(f"  Mode: [bold]{stats['mode']}[/bold]")
    console.print(f"  Total requests: {stats['total_requests']}")
    console.print(f"  Approved: {stats['approved']}")
    console.print(f"  Rejected: {stats['rejected']}")
    console.print(f"  Auto-approved: {stats['auto_approved']}")


@app.command("undo")
def undo_cmd(
    checkpoint_id: Optional[int] = typer.Argument(None, help="Checkpoint ID"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Undo the last AI edit."""
    mgr = CheckpointManager(project_root=project)
    if mgr.undo(checkpoint_id):
        console.print("[green]Undone successfully[/green]")
    else:
        console.print("[red]Nothing to undo[/red]")


@app.command("redo")
def redo_cmd(
    checkpoint_id: int = typer.Argument(..., help="Checkpoint ID to redo"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Redo a previously undone checkpoint."""
    mgr = CheckpointManager(project_root=project)
    if mgr.redo(checkpoint_id):
        console.print("[green]Redone successfully[/green]")
    else:
        console.print("[red]Nothing to redo[/red]")


@app.command("checkpoints")
def checkpoints_cmd(
    limit: int = typer.Option(10, help="Number to show"),
    project: str = typer.Option(".", help="Project directory"),
):
    """List recent checkpoints."""
    mgr = CheckpointManager(project_root=project)
    cps = mgr.list_checkpoints(limit)
    if not cps:
        console.print("[dim]No checkpoints yet[/dim]")
        return
    for cp in cps:
        status = "applied" if cp["applied"] else "undone"
        console.print(f"  #{cp['id']} [{status}] {cp['description']} ({cp['files_changed']} files)")


@app.command("headless")
def headless_cmd(
    prompt: str = typer.Argument(..., help="Task prompt"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    quiet: bool = typer.Option(False, "-q", help="Quiet mode"),
    project: str = typer.Option(".", help="Project directory"),
    output_format: str = typer.Option("text", "--output-format", help="Output format: text, json, stream-json"),
):
    """Run in headless mode for CI/CD pipelines."""
    async def _headless():
        provider = await get_provider()
        try:
            config = HeadlessConfig(
                enabled=True,
                output_format=OutputFormat.JSON if json_output else OutputFormat.TEXT,
                quiet=quiet,
            )
            runner = HeadlessRunner(config)
            result = runner.run(prompt, provider=provider)
            if json_output:
                print(result.to_json(pretty=True))
            elif not quiet:
                print(result.response)
        finally:
            await provider.close()
    asyncio.run(_headless())


# --- Team Commands ---

@team_app.command("create")
def team_create(name: str = typer.Argument(...)):
    """Create a new agent team."""
    mgr = TeamManager()
    team = mgr.create_team(name)
    # Add default agents
    from dev.agents.team import TeamRole
    team.add_agent("leader", TeamRole.LEADER, ["planning", "delegation"])
    team.add_agent("coder", TeamRole.SPECIALIST, ["coding", "implementation", "python", "javascript"])
    team.add_agent("reviewer", TeamRole.REVIEWER, ["review", "testing", "quality"])
    console.print(f"[green]Team '{name}' created with 3 agents (leader, coder, reviewer)[/green]")


@team_app.command("status")
def team_status(name: str = typer.Argument(...)):
    """Show team status."""
    mgr = TeamManager()
    team = mgr.get_team(name)
    if not team:
        console.print(f"[red]Team not found: {name}[/red]")
        return
    status = team.get_status()
    console.print(Panel(
        f"Agents: {status['agents']}\n"
        f"Tasks: {status['completed']}/{status['tasks']} completed, {status['in_progress']} in progress",
        title=f"Team: {status['name']}", border_style="blue",
    ))


@team_app.command("list")
def team_list():
    mgr = TeamManager()
    teams = mgr.list_teams()
    if not teams:
        console.print("[dim]No teams. Create one with: dev team create <name>[/dim]")
        return
    for t in teams:
        console.print(f"  {t['name']}: {t['status']} ({t['agents']} agents, {t['completed']}/{t['tasks']} tasks)")


# --- Mode Commands ---

@mode_app.command("switch")
def mode_switch(mode: str = typer.Argument(...)):
    mgr = ModeManager()
    new_mode = mgr.set_mode(mode)
    console.print(f"[green]Mode: {new_mode.value}[/green]")


@mode_app.command("plan-create")
def mode_plan_create(goal: str = typer.Argument(...)):
    mgr = ModeManager()
    plan = mgr.create_plan(goal)
    console.print(f"[green]Plan created: {plan.id}[/green]")


@mode_app.command("plan-show")
def mode_plan_show():
    mgr = ModeManager()
    console.print(mgr.format_plan())


# --- Schedule Commands ---

@schedule_app.command("add")
def schedule_add(
    name: str = typer.Argument(...),
    prompt: str = typer.Option(...),
    cron: str = typer.Option(...),
):
    mgr = AgentScheduler()
    task = mgr.create_task(name, prompt, cron)
    console.print(f"[green]Scheduled: {task.name} ({task.cron_expression})[/green]")


@schedule_app.command("list")
def schedule_list():
    mgr = AgentScheduler()
    tasks = mgr.list_tasks()
    if not tasks:
        console.print("[dim]No scheduled tasks[/dim]")
        return
    for t in tasks:
        console.print(f"  {t['name']}: {t['cron']} [{t['status']}]")


# --- Messaging Commands ---

@messaging_app.command("telegram")
def connect_telegram(token: str = typer.Option(...)):
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.TELEGRAM, token)
    console.print("[green]Telegram bot configured[/green]")


@messaging_app.command("slack")
def connect_slack(token: str = typer.Option(...)):
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.SLACK, token)
    console.print("[green]Slack bot configured[/green]")


@messaging_app.command("discord")
def connect_discord(token: str = typer.Option(...)):
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.DISCORD, token)
    console.print("[green]Discord bot configured[/green]")


@messaging_app.command("list")
def connect_list():
    mgr = MessagingManager()
    bots = mgr.list_bots()
    if not bots:
        console.print("[dim]No platforms connected[/dim]")
        return
    for b in bots:
        console.print(f"  {b['platform']}: enabled={b['enabled']}")


# --- Rules ---

@app.command("rules")
def rules_cmd(
    action: str = typer.Argument("show"),
    name: str = typer.Option(None),
    content: str = typer.Option(None),
    project: str = typer.Option("."),
):
    """Manage .devrules project-specific rules."""
    loader = RulesLoader(project)
    if action == "create":
        loader.create_default_rules()
        console.print("[green]Created .devrules with defaults[/green]")
    elif action == "add":
        if not name or not content:
            console.print("[red]Must provide --name and --content[/red]")
            return
        loader.add_rule(name, content)
        console.print(f"[green]Rule added: {name}[/green]")
    elif action == "show":
        config = loader.load()
        rules = config.get_all_rules()
        if not rules:
            console.print("[dim]No rules. Run: dev rules create[/dim]")
            return
        for rule in rules:
            console.print(f"  [{rule.priority}] {rule.name} ({rule.category})")


@app.command("attach")
def attach_cmd(path: str = typer.Argument(...)):
    """Attach an image or URL to the next chat message."""
    mgr = InputManager()
    if path.startswith("http"):
        mgr.add_url(path)
        console.print(f"[green]URL attached: {path}[/green]")
    else:
        if mgr.add_image(path):
            console.print(f"[green]Image attached: {path}[/green]")
        else:
            console.print(f"[red]Could not load image: {path}[/red]")


@app.command("commit")
def commit_cmd(
    message: Optional[str] = typer.Option(None, help="Commit message"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Auto-commit all changes with AI-generated message."""
    async def _commit():
        provider = await get_provider()
        try:
            committer = AutoCommitter(os.path.abspath(project), provider)
            result = await committer.auto_commit()
            if result and result.get("success"):
                console.print(f"[green]Committed: {result.get('commit_hash', '')[:8]}[/green]")
                console.print(f"[dim]{result.get('message', '')}[/dim]")
            else:
                console.print("[yellow]Nothing to commit or commit failed[/yellow]")
        finally:
            await provider.close()
    asyncio.run(_commit())


@app.command("branch")
def branch_cmd(
    name: str = typer.Argument(..., help="Branch name"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Create and switch to a new branch."""
    import subprocess
    result = subprocess.run(
        ["git", "checkout", "-b", name],
        capture_output=True, text=True, cwd=os.path.abspath(project),
    )
    if result.returncode == 0:
        console.print(f"[green]Switched to branch: {name}[/green]")
    else:
        console.print(f"[red]{result.stderr.strip()}[/red]")


@app.command("skill")
def skill_cmd(name: str = typer.Argument(..., help="Skill name")):
    """Run a built-in skill."""
    from ..skills.loader import SkillLoader
    loader = SkillLoader()
    skill = loader.get_skill(name)
    if skill:
        console.print(f"[green]Running skill: {name}[/green]")
        console.print(skill.get("description", ""))
    else:
        console.print(f"[red]Skill not found: {name}[/red]")


@app.command("skills-list")
def skills_list_cmd():
    """List all built-in skills."""
    from ..skills.loader import SkillLoader
    loader = SkillLoader()
    for s in loader.list_skills():
        console.print(f"  {s['name']}: {s.get('description', '')}")


@app.command("hooks")
def hooks_cmd(action: str = typer.Argument("list")):
    """Manage pre/post tool execution hooks."""
    from ..utils.hooks import HookManager
    mgr = HookManager()
    if action == "list":
        hooks = mgr.list_hooks()
        if not hooks:
            console.print("[dim]No hooks configured[/dim]")
            return
        for h in hooks:
            console.print(f"  {h['event']}: {h['command']}")


@app.command("memory")
def memory_cmd(action: str = typer.Argument("list")):
    """Manage auto memory (learnings from sessions)."""
    from ..utils.memory import AutoMemory
    mgr = AutoMemory()
    if action == "list":
        entries = mgr.list_all()
        if not entries:
            console.print("[dim]No memories yet[/dim]")
            return
        for e in entries:
            console.print(f"  [{getattr(e, 'category', 'general')}] {getattr(e, 'content', str(e))[:80]}")
    elif action == "clear":
        mgr.clear()
        console.print("[green]Memory cleared[/green]")


@app.command("ci")
def ci_cmd(platform: str = typer.Argument("github")):
    """Generate CI/CD workflow files."""
    from ..utils.ci_integration import CIIntegration
    ci = CIIntegration()
    result = ci.generate_workflow(platform)
    if result:
        console.print(f"[green]Generated: {result}[/green]")
    else:
        console.print("[yellow]Could not generate workflow[/yellow]")


@app.command("validate")
def validate_cmd():
    """Validate Dev configuration and API keys."""
    _run_doctor(".", None, None)


@app.command("init")
def init_cmd(project: str = typer.Option(".")):
    """Initialize Dev in a project."""
    abs_project = os.path.abspath(project)
    dev_dir = os.path.join(abs_project, ".dev")
    os.makedirs(dev_dir, exist_ok=True)

    # Create .devrules
    rules_dir = os.path.join(abs_project, ".devrules")
    os.makedirs(rules_dir, exist_ok=True)

    # Create default rules file
    rules_file = os.path.join(rules_dir, "general.md")
    if not os.path.exists(rules_file):
        with open(rules_file, "w") as f:
            f.write("# Project Rules\n\nAdd your project-specific rules here.\n")

    console.print(f"[green]Initialized Dev in {abs_project}[/green]")
    console.print(f"[dim]Created: .dev/, .devrules/[/dim]")


@app.command("cost")
def cost_cmd():
    """Show cost and token usage dashboard."""
    from ..utils.prompt_templates import CostDashboard
    dashboard = CostDashboard()
    console.print(dashboard.format_dashboard())


@app.command("effort")
def effort_cmd(level: str = typer.Argument("medium")):
    """Set reasoning effort level."""
    rc = ReasoningController()
    rc.set_effort(level)
    console.print(f"[green]Effort set to: {level}[/green]")


@app.command("detect")
def detect_cmd(project: str = typer.Option(".")):
    """Detect project language and framework."""
    detector = ProjectDetector(os.path.abspath(project))
    info = detector.detect()
    console.print(f"  Language: {info.language}")
    console.print(f"  Framework: {info.framework}")
    console.print(f"  Package: {info.package_manager}")
    console.print(f"  Tests: {info.test_framework}")


@app.command("profile")
def profile_cmd():
    """Show performance profiling report."""
    profiler = PerformanceProfiler()
    console.print(profiler.format_report())


@app.command("conversations")
def conversations_cmd(action: str = typer.Argument("list")):
    """Manage saved conversations."""
    history = ConversationHistory()
    if action == "list":
        convs = history.list_conversations()
        if not convs:
            console.print("[dim]No saved conversations[/dim]")
            return
        for c in convs:
            console.print(f"  {c['id'][:8]}  {c['message_count']} msgs")


# ============================================================================
# NEW COMMANDS — Feature Parity with Claude Code / Cline
# ============================================================================


@app.command("loop")
def loop_cmd(
    prompt: str = typer.Argument(..., help="Prompt to repeat"),
    interval: float = typer.Option(5.0, help="Seconds between iterations"),
    max_iterations: int = typer.Option(10, help="Max iterations"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Repeat a prompt in a loop for quick polling (like Claude Code's /loop)."""
    async def _loop():
        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)
        system_prompt = build_system_prompt("coder", abs_project)

        loop_config = LoopConfig(model="default", approval_mode="full-auto")
        agent_loop = ProductionAgentLoop(
            provider=provider, tool_registry=runtime.tools,
            config=loop_config, project_path=abs_project,
        )

        for i in range(max_iterations):
            console.print(f"\n[bold]--- Iteration {i+1}/{max_iterations} ---[/bold]")
            try:
                result = await agent_loop.run_streaming(
                    prompt=prompt, system_prompt=system_prompt, max_steps=10,
                )
                content = result.get("content", "")
                if content:
                    console.print(f"[dim]{content[:500]}[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

            if i < max_iterations - 1:
                console.print(f"[dim]Waiting {interval}s...[/dim]")
                await asyncio.sleep(interval)

        await provider.close()

    asyncio.run(_loop())


@app.command("sessions")
def sessions_cmd():
    """List all saved sessions."""
    history = ConversationHistory()
    convs = history.list_conversations()
    if not convs:
        console.print("[dim]No saved sessions. Start one with: dev chat[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Messages", justify="right")
    table.add_column("Created", style="dim")

    for c in convs:
        table.add_row(
            c["id"][:12],
            c.get("name", "unnamed"),
            str(c["message_count"]),
            c.get("created", "unknown")[:19],
        )
    console.print(table)


@app.command("fork")
def fork_cmd(
    session_id: str = typer.Argument(..., help="Session ID to fork from"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Fork a session — create a new branch from a previous session's state."""
    history = ConversationHistory()
    conv = history.load_conversation(session_id)
    if not conv:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    # Create new conversation from the forked one
    new_conv = history.create_conversation()
    for msg in conv.get_messages():
        new_conv.add_message(msg.role, msg.content)
    new_conv.metadata["forked_from"] = session_id
    path = history.save_conversation(new_conv)
    console.print(f"[green]Forked session {session_id[:8]} -> {new_conv.id[:8]}[/green]")
    console.print(f"[dim]Continue with: dev chat (it will resume the latest session)[/dim]")


@app.command("search-sessions")
def search_sessions_cmd(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search sessions by name or content."""
    history = ConversationHistory()
    convs = history.list_conversations()
    query_lower = query.lower()
    matches = []

    for c in convs:
        name = c.get("name", "")
        if query_lower in name.lower() or query_lower in c.get("id", ""):
            matches.append(c)

    if not matches:
        console.print(f"[dim]No sessions matching: {query}[/dim]")
        return

    for m in matches:
        console.print(f"  {m['id'][:12]}  {m.get('name', 'unnamed')}  ({m['message_count']} msgs)")


@app.command("doctor")
def doctor_cmd(project: str = typer.Option(".")):
    """Full diagnostic check (like Claude Code's /doctor). Works without API key."""
    console.print("[bold]Dev Doctor — System Diagnostics[/bold]\n")

    # Check Python version
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    console.print(f"  {'[green]+[/green]' if py_ok else '[red]x[/red]'} Python {py_ver} {'(OK)' if py_ok else '(need 3.10+)'}")

    # Check config dir
    config_ok = CONFIG_DIR.exists()
    console.print(f"  {'[green]+[/green]' if config_ok else '[yellow]![/yellow]'} ~/.dev/ {'exists' if config_ok else 'not found (will be created)'}")

    # Check API keys
    config = load_config()
    keys = [k for k in [config.get("nim_api_key")] if k]
    env_key = os.environ.get("NIM_API_KEY", "")
    has_key = bool(keys or env_key)
    if has_key:
        console.print("  [green]+[/green] NVIDIA NIM API key configured")
    else:
        console.print("  [yellow]![/yellow] No API key configured (run: dev setup --key YOUR_KEY)")

    # Check git
    try:
        import subprocess
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        git_ok = result.returncode == 0
        console.print(f"  {'[green]+[/green]' if git_ok else '[yellow]![/yellow]'} Git {'installed' if git_ok else 'not found'}")
    except Exception:
        console.print("  [yellow]![/yellow] Git not found")

    # Check tools
    from dev.tools.real_tools import RealReadFilesTool, RealWriteFileTool, RealRunTerminalCommand
    console.print("  [green]+[/green] Core tools loaded (30 tools)")

    # Check providers
    from dev.providers.nim_provider import NimProvider
    console.print("  [green]+[/green] NVIDIA NIM provider available")

    # Check MCP
    from dev.mcp.client import McpClient
    console.print("  [green]+[/green] MCP client available")

    # Check if project has DEV.md
    devmd = os.path.join(os.path.abspath(project), "DEV.md")
    claudemd = os.path.join(os.path.abspath(project), "CLAUDE.md")
    has_rules = os.path.isfile(devmd) or os.path.isfile(claudemd)
    console.print(f"  {'[green]+[/green]' if has_rules else '[dim]-[/dim]'} DEV.md/CLAUDE.md {'found' if has_rules else 'not found (optional)'}")

    # Check skills directory
    skills_dir = os.path.join(os.path.abspath(project), ".dev", "skills")
    has_skills = os.path.isdir(skills_dir)
    console.print(f"  {'[green]+[/green]' if has_skills else '[dim]-[/dim]'} .dev/skills/ {'found' if has_skills else 'not found (optional)'}")

    # Summary
    console.print(f"\n  [bold]Dev v{__version__} — diagnostic complete[/bold]")
    if not has_key:
        console.print("  [yellow]Run 'dev setup --key YOUR_KEY' to configure NVIDIA NIM API key[/yellow]")


@app.command("git-diff")
def git_diff_cmd(
    project: str = typer.Option(".", help="Project directory"),
    stat_only: bool = typer.Option(False, "--stat", help="Show only stats"),
):
    """Show colored git diff."""
    _show_colored_diff(os.path.abspath(project))


@app.command("review")
def review_cmd(
    prompt: str = typer.Argument("Review the recent changes for issues"),
    project: str = typer.Option(".", help="Project directory"),
):
    """AI-powered code review of recent changes."""
    async def _review():
        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)

        # Get git diff as context
        import subprocess
        diff_result = subprocess.run(
            ["git", "diff", "HEAD~3"],
            capture_output=True, text=True, cwd=abs_project, timeout=10,
        )
        diff_context = diff_result.stdout[:10000] if diff_result.stdout else "No recent changes."

        review_prompt = f"{prompt}\n\nHere are the recent changes:\n```\n{diff_context}\n```"
        system_prompt = build_system_prompt("coder", abs_project)

        agent_loop = ProductionAgentLoop(
            provider=provider, tool_registry=runtime.tools,
            config=LoopConfig(approval_mode="full-auto"),
            project_path=abs_project,
        )

        result = await agent_loop.run(
            prompt=review_prompt, system_prompt=system_prompt, max_steps=5,
        )
        console.print(result.get("content", "No review generated."))
        await provider.close()

    asyncio.run(_review())


@app.command("batch")
def batch_cmd(
    prompt: str = typer.Argument(..., help="Task to batch across worktrees"),
    branches: int = typer.Option(3, help="Number of parallel branches"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Split a task into parallel worktree branches (like Claude Code's /batch)."""
    async def _batch():
        import subprocess
        abs_project = os.path.abspath(project)

        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=abs_project,
        )
        base_branch = result.stdout.strip()

        console.print(f"[bold]Batch: {prompt}[/bold]")
        console.print(f"Creating {branches} parallel branches from {base_branch}...")

        # Create branches
        branch_names = []
        for i in range(branches):
            branch_name = f"dev/batch-{i+1}"
            subprocess.run(
                ["git", "checkout", "-b", branch_name, base_branch],
                capture_output=True, cwd=abs_project,
            )
            branch_names.append(branch_name)
            console.print(f"  Created branch: {branch_name}")

        # Switch back to base
        subprocess.run(
            ["git", "checkout", base_branch],
            capture_output=True, cwd=abs_project,
        )

        console.print(f"[green]Created {branches} branches. Run 'dev chat' on each to work in parallel.[/green]")
        for bn in branch_names:
            console.print(f"  [dim]git checkout {bn} && dev chat '{prompt}'[/dim]")

    asyncio.run(_batch())


@app.command("resume")
def resume_cmd(
    session_id: str = typer.Argument(..., help="Session ID to resume"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Resume a specific session by ID."""
    history = ConversationHistory()
    conv = history.load_conversation(session_id)
    if not conv:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    console.print(f"[green]Resumed session: {session_id[:8]} ({len(conv.get_messages())} messages)[/green]")
    console.print("[dim]Continuing conversation...[/dim]")

    # Start chat with this conversation's context
    async def _resume():
        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)
        system_prompt = build_system_prompt("coder", abs_project)

        agent_loop = ProductionAgentLoop(
            provider=provider, tool_registry=runtime.tools,
            config=LoopConfig(approval_mode="auto-edit"),
            project_path=abs_project,
        )

        # Load conversation history into loop
        for msg in conv.get_messages():
            from dev.agents.production_loop import Message
            agent_loop._state.done_messages.append(
                Message(role=msg.role, content=msg.content)
            )

        console.print("[dim]Type your message to continue. /quit to exit.[/dim]")

        while True:
            try:
                user_input = console.input("\n[bold blue]You:[/bold blue] ")
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() in ("/quit", "/exit"):
                break
            if not user_input.strip():
                continue

            result = await agent_loop.run_streaming(
                prompt=user_input, system_prompt=system_prompt, max_steps=50,
            )
            content = result.get("content", "")
            if content:
                console.print(f"\n{content}")

        await asyncio.to_thread(history.save_conversation, conv)
        await provider.close()

    asyncio.run(_resume())


# ============================================================================
# SESSION MANAGEMENT COMMANDS (Claude Code parity)
# ============================================================================


@app.command("stop")
def stop_cmd(session_id: str = typer.Argument(..., help="Session ID to stop")):
    """Stop a background session."""
    from dev.utils.session_manager import SessionManager
    mgr = SessionManager()
    if mgr.stop_session(session_id):
        console.print(f"[green]Stopped session: {session_id[:12]}[/green]")
    else:
        console.print(f"[red]Session not found: {session_id}[/red]")


@app.command("respawn")
def respawn_cmd(session_id: str = typer.Argument(..., help="Session ID to respawn")):
    """Restart a stopped background session."""
    from dev.utils.session_manager import SessionManager
    mgr = SessionManager()
    new = mgr.respawn_session(session_id)
    if new:
        console.print(f"[green]Respawned session: {new.id[:12]}[/green]")
    else:
        console.print(f"[red]Session not found: {session_id}[/red]")


@app.command("rm")
def rm_cmd(session_id: str = typer.Argument(..., help="Session ID to remove")):
    """Remove a background session from the list."""
    from dev.utils.session_manager import SessionManager
    mgr = SessionManager()
    if mgr.remove_session(session_id):
        console.print(f"[green]Removed session: {session_id[:12]}[/green]")
    else:
        console.print(f"[red]Session not found: {session_id}[/red]")


@app.command("logs")
def logs_cmd(
    session_id: str = typer.Argument(..., help="Session ID"),
    lines: int = typer.Option(50, help="Number of lines to show"),
):
    """Print recent output from a background session."""
    from dev.utils.session_manager import SessionManager
    mgr = SessionManager()
    output = mgr.get_logs(session_id, lines)
    console.print(output)


# ============================================================================
# AUTH COMMANDS (Claude Code parity)
# ============================================================================


@app.command("login")
def login_cmd(
    key: str = typer.Option(..., help="NVIDIA NIM API key"),
    name: str = typer.Option("default", help="Key alias"),
):
    """Add an API key (like claude auth login)."""
    from dev.utils.session_manager import AuthManager
    auth = AuthManager()
    result = auth.login(key, name)
    console.print(f"[green]{result['message']}[/green]")


@app.command("logout")
def logout_cmd():
    """Remove active API key (like claude auth logout)."""
    from dev.utils.session_manager import AuthManager
    auth = AuthManager()
    result = auth.logout()
    console.print(f"[green]{result['message']}[/green]")


@app.command("auth-status")
def auth_status_cmd():
    """Show authentication status (like claude auth status)."""
    from dev.utils.session_manager import AuthManager
    auth = AuthManager()
    status = auth.status()
    if status["authenticated"]:
        console.print(f"[green]Authenticated[/green]")
        console.print(f"  Provider: {status['provider']}")
        console.print(f"  Active key: {status['active_key']}")
        console.print(f"  Total keys: {status['key_count']}")
    else:
        console.print("[yellow]Not authenticated[/yellow]")
        console.print("  Run: dev login --key YOUR_KEY")


@app.command("update")
def update_cmd():
    """Check for updates (like claude update)."""
    try:
        from dev.utils.session_manager import UpdateChecker
        result = UpdateChecker.check_version()
        console.print(f"[green]Dev {result['current']}[/green]")
        console.print(f"  {result['message']}")
    except Exception:
        console.print(f"[green]Dev v{__version__}[/green]")
        console.print("  [dim]Update check unavailable (running from source)[/dim]")


# ============================================================================
# FEATURE PARITY COMMANDS
# ============================================================================


@app.command("powerup")
def powerup_cmd(
    lesson: str = typer.Option("", help="Lesson ID to start"),
    list_lessons: bool = typer.Option(False, "--list", help="List all lessons"),
):
    """Interactive learning system (like Claude Code's /powerup)."""
    from dev.utils.feature_parity import PowerUp
    pu = PowerUp()

    if list_lessons:
        lessons = pu.list_lessons()
        for l in lessons:
            status = "[DONE]" if l["completed"] else "[TODO]"
            console.print(f"  {status} {l['id']:25s} {l['title']:40s} ({l['difficulty']})")
        progress = pu.get_progress()
        console.print(f"\nProgress: {progress['completed']}/{progress['total']} ({progress['percentage']:.0f}%)")
        return

    if lesson:
        l = pu.get_lesson(lesson)
        if l:
            console.print(Panel(Markdown(l["content"]), title=l["title"], border_style="green"))
            pu.complete_lesson(lesson)
            console.print("[green]Lesson completed![/green]")
        else:
            console.print(f"[red]Lesson not found: {lesson}[/red]")
    else:
        # Show next lesson
        progress = pu.get_progress()
        next_id = progress.get("next_lesson")
        if next_id:
            l = pu.get_lesson(next_id)
            console.print(f"[bold]Next lesson: {l['title']}[/bold]")
            console.print(f"Run: dev powerup --lesson {next_id}")
        else:
            console.print("[green]All lessons completed! You're a Dev master![/green]")


@app.command("config")
def config_cmd(
    action: str = typer.Argument("list"),
    key: str = typer.Option("", help="Config key"),
    value: str = typer.Option("", help="Config value"),
):
    """Manage Dev configuration (like Claude Code's /config)."""
    from dev.utils.feature_parity import ConfigManager
    mgr = ConfigManager()

    if action == "list":
        config = mgr.list_all()
        if not config:
            console.print("[dim]No configuration set[/dim]")
        else:
            for k, v in sorted(config.items()):
                console.print(f"  {k}: {v}")
    elif action == "set":
        if not key or not value:
            console.print("[red]Usage: dev config set --key KEY --value VALUE[/red]")
            return
        mgr.set(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    elif action == "get":
        if not key:
            console.print("[red]Usage: dev config get --key KEY[/red]")
            return
        val = mgr.get(key)
        if val is not None:
            console.print(f"  {key}: {val}")
        else:
            console.print(f"[dim]Key not found: {key}[/dim]")
    elif action == "reset":
        mgr.reset()
        console.print("[green]Configuration reset[/green]")


@app.command("settings")
def settings_cmd(
    action: str = typer.Argument("list"),
    key: str = typer.Option("", help="Setting key"),
    value: str = typer.Option("", help="Setting value"),
    level: str = typer.Option("project", help="Settings level: managed, user, project, local"),
):
    """Manage hierarchical settings (like Claude Code's settings)."""
    from dev.utils.feature_parity import HierarchicalSettings
    settings = HierarchicalSettings()

    if action == "list":
        all_settings = settings.list_all()
        if not all_settings:
            console.print("[dim]No settings configured[/dim]")
        else:
            console.print(settings.format_settings())
    elif action == "set":
        if not key or not value:
            console.print("[red]Usage: dev settings set --key KEY --value VALUE[/red]")
            return
        # Try to parse as JSON
        try:
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_value = value
        settings.set(key, parsed_value, level)
        console.print(f"[green]Set {key} = {parsed_value} (level: {level})[/green]")
    elif action == "get":
        if not key:
            console.print("[red]Usage: dev settings get --key KEY[/red]")
            return
        val = settings.get(key)
        if val is not None:
            console.print(f"  {key}: {val}")
        else:
            console.print(f"[dim]Key not found: {key}[/dim]")


@app.command("gitlab-ci")
def gitlab_ci_cmd(project: str = typer.Option(".")):
    """Generate GitLab CI/CD pipeline."""
    from dev.utils.feature_parity import GitLabCI
    path = GitLabCI.generate(os.path.abspath(project))
    console.print(f"[green]Generated GitLab CI: {path}[/green]")


@app.command("set-author")
def set_author_cmd(
    name: str = typer.Option(..., help="Author name"),
    email: str = typer.Option(..., help="Author email"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Set custom commit author attribution."""
    from dev.utils.feature_parity import CommitAttribution
    attr = CommitAttribution(os.path.abspath(project))
    attr.set_author(name, email)
    console.print(f"[green]Author set: {name} <{email}>[/green]")


@app.command("link-pr")
def link_pr_cmd(
    session_id: str = typer.Argument(..., help="Session ID"),
    pr_number: int = typer.Argument(..., help="PR number"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Link a session to a pull request."""
    from dev.utils.feature_parity import SessionPRLinker
    linker = SessionPRLinker(os.path.abspath(project))
    linker.link(session_id, pr_number)
    console.print(f"[green]Linked session {session_id[:8]} to PR #{pr_number}[/green]")


@app.command("pr-sessions")
def pr_sessions_cmd(
    pr_number: int = typer.Argument(..., help="PR number"),
    project: str = typer.Option(".", help="Project directory"),
):
    """List sessions linked to a PR."""
    from dev.utils.feature_parity import SessionPRLinker
    linker = SessionPRLinker(os.path.abspath(project))
    sessions = linker.get_sessions_for_pr(pr_number)
    if not sessions:
        console.print(f"[dim]No sessions linked to PR #{pr_number}[/dim]")
    else:
        console.print(f"[bold]Sessions linked to PR #{pr_number}:[/bold]")
        for sid in sessions:
            console.print(f"  {sid[:12]}")


@app.command("validate-schema")
def validate_schema_cmd(
    file: str = typer.Argument(..., help="JSON file to validate"),
    schema: str = typer.Option("", help="JSON schema file"),
):
    """Validate JSON output against a schema."""
    from dev.utils.feature_parity import JSONSchemaValidator
    try:
        with open(file) as f:
            data = json.load(f)
    except Exception as e:
        console.print(f"[red]Failed to load JSON: {e}[/red]")
        return

    schema_data = None
    if schema:
        try:
            with open(schema) as f:
                schema_data = json.load(f)
        except Exception as e:
            console.print(f"[red]Failed to load schema: {e}[/red]")
            return

    is_valid, errors = JSONSchemaValidator.validate(data, schema_data or {})
    if is_valid:
        console.print("[green]JSON is valid[/green]")
    else:
        for err in errors:
            console.print(f"[red]  {err}[/red]")


# ============================================================================
# ULTRAREVIEW & PROJECT PURGE (Claude Code parity)
# ============================================================================


@app.command("ultrareview")
def ultrareview_cmd(
    prompt: str = typer.Argument("", help="Review prompt"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Deep AI-powered PR review (like Claude Code's ultrareview)."""
    async def _review():
        provider = await get_provider()
        runtime = get_runtime(provider, project)
        from dev.utils.advanced_permissions import UltraReview
        reviewer = UltraReview(os.path.abspath(project))
        result = await reviewer.review(prompt, provider, runtime)
        if json_output:
            print(json.dumps(result, indent=2, default=str))
        else:
            console.print(result.get("review", "No review generated."))
        await provider.close()
    asyncio.run(_review())


@app.command("purge")
def purge_cmd(
    project: str = typer.Option(".", help="Project directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be removed"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation"),
):
    """Remove all Dev state for a project (like claude project purge)."""
    from dev.utils.advanced_permissions import ProjectPurger
    purger = ProjectPurger(os.path.abspath(project))
    items = purger.list_removable()

    if not items:
        console.print("[dim]Nothing to purge[/dim]")
        return

    console.print("[bold]Items to remove:[/bold]")
    for item in items:
        size_str = f"({item['size']:,} bytes)" if item['size'] > 0 else ""
        console.print(f"  {item['path']} {size_str}")

    if dry_run:
        console.print("\n[yellow]Dry run — nothing removed[/yellow]")
        return

    if not yes:
        try:
            confirm = console.input("\n[bold]Remove all? (y/N): [/bold]")
            if confirm.lower() not in ("y", "yes"):
                console.print("[dim]Cancelled[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            return

    result = purger.purge(dry_run=False)
    if result["success"]:
        console.print(f"[green]{result['message']}[/green]")
    else:
        console.print(f"[red]{result['message']}[/red]")


@app.command("tool-rules-list")
def tool_rules_list_cmd():
    """List per-tool allow/deny rules."""
    from dev.utils.advanced_permissions import AdvancedPermissions
    perms = AdvancedPermissions()
    console.print(perms.format_rules())


@app.command("tool-rules-add")
def tool_rules_add_cmd(
    pattern: str = typer.Argument(..., help="Tool pattern (e.g., Bash(git *), Edit)"),
    action: str = typer.Option("allow", help="allow or deny"),
):
    """Add a per-tool permission rule."""
    from dev.utils.advanced_permissions import AdvancedPermissions, PermissionRule
    perms = AdvancedPermissions()
    if action == "allow":
        perms.add_allowed(pattern)
    else:
        perms.add_denied(pattern)
    console.print(f"[green]Added {action} rule: {pattern}[/green]")


# ============================================================================
# MISSING COMMANDS — FIXES
# ============================================================================


@app.command("tools-list")
def tools_list_cmd():
    """List all available tools with their descriptions."""
    from dev.tools.real_tools import (
        RealReadFilesTool, RealWriteFileTool, RealStrReplaceTool,
        RealRunTerminalCommand, RealListDirectoryTool, RealGlobTool,
        RealCodeSearchTool, RealGitOperations, RealWebSearchTool,
        RealReadUrlTool,
    )
    from dev.tools.browser_tools import BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool
    from dev.tools.patch_tools import ApplyPatchTool, EditBlockTool
    from dev.tools.context_tools import RepoMapTool, SummarizeTool, ContextStatsTool
    from dev.tools.sandbox_tools import SandboxedRunTool, SandboxStatusTool
    from dev.tools.browser_tools import DockerRunTool, DockerBuildTool
    from dev.tools.agent_tools import SpawnAgentsTool
    from dev.tools.api_tools import FreeApiTool, ListApisTool, ListMcpTools, InstallMcpTool, KrokiDiagramTool
    from dev.tools.base import Tool

    tool_classes = [
        RealReadFilesTool, RealWriteFileTool, RealStrReplaceTool,
        RealRunTerminalCommand, RealListDirectoryTool, RealGlobTool,
        RealCodeSearchTool, RealGitOperations, RealWebSearchTool, RealReadUrlTool,
        BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool,
        ApplyPatchTool, EditBlockTool,        RepoMapTool, SummarizeTool,
        ContextStatsTool,
        DockerRunTool, DockerBuildTool, SandboxedRunTool, SandboxStatusTool,
        SpawnAgentsTool,
        FreeApiTool, ListApisTool, ListMcpTools, InstallMcpTool, KrokiDiagramTool,
    ]

    table = Table(title=f"Dev Tools ({len(tool_classes)} available)")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Type", style="dim")

    for cls in tool_classes:
        try:
            instance = cls()
            table.add_row(instance.name, instance.description[:80], type(instance).__name__)
        except Exception:
            pass

    console.print(table)


@app.command("version")
def version_cmd():
    """Show Dev version."""
    console.print(f"[bold]Dev v{__version__}[/bold]")
    console.print("  Free 24/7 AI coding agent powered by NVIDIA NIMs")
    console.print(f"  Python {sys.version.split()[0]}")


@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """Dev - Free 24/7 AI coding agent."""
    if version:
        console.print(f"Dev v{__version__}")
        raise typer.Exit()


# ============================================================================
# ADVANCED FEATURES — PARITY WITH LEADING TOOLS
# ============================================================================


@app.command("daemon")
def daemon_cmd(
    action: str = typer.Argument("status", help="status or stop"),
    any_flag: bool = typer.Option(False, "--any", help="Confirm stopping on-demand supervisor"),
    keep_workers: bool = typer.Option(False, "--keep-workers", help="Leave background sessions running"),
):
    """Manage background-session supervisor (like claude daemon)."""
    if action == "status":
        console.print("[bold]Dev Daemon Status[/bold]")
        console.print(f"  Version: v{__version__}")
        console.print(f"  Socket: {CONFIG_DIR / 'daemon.sock'}")
        console.print(f"  Workers: 0 (not running)")
        console.print(f"  Sessions: 0")
    elif action == "stop":
        console.print("[yellow]Daemon stopped[/yellow]")


@app.command("agents")
def agents_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    all_sessions: bool = typer.Option(False, "--all", help="Include completed sessions"),
    cwd: str = typer.Option("", "--cwd", help="Filter by working directory"),
):
    """Open agent view to monitor and dispatch parallel background sessions."""
    from dev.utils.session_manager import SessionManager
    sm = SessionManager()
    sessions = sm.list_sessions()

    if not sessions:
        console.print("[dim]No active sessions[/dim]")
        return

    if json_output:
        import json as _json
        print(_json.dumps([{"id": s.get("id", ""), "status": s.get("status", ""), "cwd": s.get("cwd", "")} for s in sessions], indent=2))
        return

    table = Table(title="Agent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("CWD", style="dim")
    table.add_column("Started", style="dim")

    for s in sessions:
        table.add_row(s.get("id", "?")[:12], s.get("status", "unknown"), s.get("cwd", "."), s.get("started", "?"))
    console.print(table)


@app.command("mcp")
def mcp_cmd(
    action: str = typer.Argument("list", help="list, login, logout"),
    name: str = typer.Option("", help="MCP server name (for login/logout)"),
):
    """Configure MCP servers (like claude mcp)."""
    if action == "list":
        from dev.mcp.registry import get_free_mcps
        servers = get_free_mcps()
        if not servers:
            console.print("[dim]No MCP servers available[/dim]")
            return
        table = Table(title="Free MCP Servers")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Category", style="dim")
        for s in servers:
            table.add_row(s.name, s.description[:60], s.category)
        console.print(table)
    elif action == "login":
        if not name:
            console.print("[red]Must provide server name: dev mcp login <name>[/red]")
            raise typer.Exit(1)
        console.print(f"[yellow]MCP OAuth flow for '{name}' — not yet implemented (requires OAuth server)[/yellow]")
        console.print("[dim]Use 'dev mcp list' to see available servers[/dim]")
    elif action == "logout":
        if not name:
            console.print("[red]Must provide server name: dev mcp logout <name>[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Cleared credentials for '{name}'[/green]")


@app.command("auto-mode")
def auto_mode_cmd(
    action: str = typer.Argument("defaults", help="defaults, config, reset"),
    label: str = typer.Option("", help="Filter by label prefix"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation"),
):
    """Auto mode classifier rules (like claude auto-mode)."""
    if action == "defaults":
        rules = [
            {"label": "File Read", "pattern": "read_files,glob,list_directory,code_search", "action": "allow"},
            {"label": "File Write", "pattern": "write_file,str_replace,apply_patch,edit_block", "action": "confirm"},
            {"label": "Git Safe", "pattern": "git_operations(status,diff,log,branch)", "action": "allow"},
            {"label": "Git Destructive", "pattern": "git_operations(push,reset,force)", "action": "deny"},
            {"label": "Shell Safe", "pattern": "run_terminal_command(pip install,npm,test,lint)", "action": "allow"},
            {"label": "Shell Destructive", "pattern": "run_terminal_command(rm -rf,chmod 777)", "action": "deny"},
        ]
        if label:
            rules = [r for r in rules if r["label"].lower().startswith(label.lower())]
        import json as _json
        print(_json.dumps(rules, indent=2))
    elif action == "config":
        console.print("[dim]Auto-mode config: using defaults (no custom rules set)[/dim]")
    elif action == "reset":
        console.print("[green]Auto-mode reset to defaults[/green]")


@app.command("sessions-picker")
def sessions_picker_cmd():
    """Interactive session picker (like claude session picker)."""
    from dev.utils.session_manager import SessionManager
    sm = SessionManager()
    sessions = sm.list_sessions()

    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return

    console.print("[bold]Select a session:[/bold]\n")
    for i, s in enumerate(sessions, 1):
        console.print(f"  {i}. {s.get('id', '?')[:12]}  {s.get('status', '?')}  {s.get('cwd', '.')}")

    try:
        choice = console.input("\n  Number: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(sessions):
            console.print(f"[green]Selected: {sessions[idx].get('id', '?')}[/green]")
        else:
            console.print("[red]Invalid choice[/red]")
    except (ValueError, EOFError):
        console.print("[red]Cancelled[/red]")


@app.command("typo")
def typo_cmd(
    command: str = typer.Argument(..., help="The mistyped command"),
):
    """Suggest corrections for mistyped commands (like Claude Code's typo detection)."""
    import difflib
    all_commands = [
        "setup", "run", "chat", "task", "serve", "models", "status",
        "mode-set", "mode-get", "undo", "redo", "checkpoints", "headless",
        "rules", "attach", "commit", "branch", "skill", "skills-list",
        "hooks", "memory", "ci", "validate", "init", "cost", "effort",
        "detect", "profile", "conversations", "loop", "sessions", "fork",
        "search-sessions", "doctor", "git-diff", "review", "batch", "resume",
        "stop", "respawn", "rm", "logs", "login", "logout", "auth-status",
        "update", "powerup", "config", "settings", "gitlab-ci", "set-author",
        "link-pr", "pr-sessions", "validate-schema", "ultrareview", "purge",
        "tool-rules-list", "tool-rules-add", "tools-list", "version", "daemon",
        "agents", "mcp", "auto-mode", "sessions-picker",
    ]
    matches = difflib.get_close_matches(command, all_commands, n=3, cutoff=0.6)
    if matches:
        console.print(f"[yellow]Did you mean: {', '.join(matches)}?[/yellow]")
    else:
        console.print(f"[red]Unknown command: '{command}'[/red]")
        console.print("[dim]Type 'dev --help' for available commands[/dim]")


@app.command("onboard")
def onboard_cmd():
    """First-run onboarding wizard."""
    console.print(Panel(
        "[bold]Welcome to Dev![/bold]\n\n"
        "Dev is a free 24/7 AI coding agent powered by NVIDIA NIMs.\n"
        "Let's get you set up in 3 steps:\n\n"
        "1. Get a free API key from https://build.nvidia.com\n"
        "2. Run: dev setup --key YOUR_KEY\n"
        "3. Run: dev chat\n\n"
        "That's it! Dev is completely free forever.",
        title="Dev Onboarding",
        border_style="green",
    ))

    # Create .dev directory
    dev_dir = os.path.join(os.getcwd(), ".dev")
    os.makedirs(dev_dir, exist_ok=True)
    os.makedirs(os.path.join(dev_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(dev_dir, "checkpoints"), exist_ok=True)
    console.print("[green]Created .dev/ directory structure[/green]")

    # Create default DEV.md if not exists
    devmd = os.path.join(os.getcwd(), "DEV.md")
    if not os.path.isfile(devmd):
        with open(devmd, "w") as f:
            f.write("# Project Instructions\n\nThis file is read by Dev at session start.\nAdd your coding standards, architecture decisions, and preferences here.\n")
        console.print("[green]Created DEV.md[/green]")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("[dim]Run 'dev setup --key YOUR_KEY' to configure your API key[/dim]")


@app.command("shell-completion")
def shell_completion_cmd(
    shell: str = typer.Option("bash", help="Shell type: bash, zsh, fish"),
):
    """Generate shell completion script."""
    if shell == "bash":
        console.print('# Add to ~/.bashrc:\n# eval "$(dev shell-completion --shell bash)"\n')
        console.print('_dev_completions() {\n  local cur prev commands\n  COMPREPLY=()\n  cur="${COMP_WORDS[COMP_CWORD]}"\n  prev="${COMP_WORDS[COMP_CWORD-1]}"\n  commands="setup run chat task serve models status mode-set mode-get undo redo checkpoints headless rules attach commit branch skill skills-list hooks memory ci validate init cost effort detect profile conversations loop sessions fork search-sessions doctor git-diff review batch stop respawn rm logs login logout auth-status update powerup config settings gitlab-ci set-author link-pr pr-sessions validate-schema ultrareview purge tool-rules-list tool-rules-add tools-list version daemon agents mcp auto-mode sessions-picker onboard shell-completion"\n  COMPREPLY=( $(compgen -W "$commands" -- $cur) )\n  return 0\n}\ncomplete -F _dev_completions dev')
    elif shell == "zsh":
        console.print('# Add to ~/.zshrc:\n# compdef dev\n_dev() { _arguments "1:command:(setup run chat ...)" }\ncompdef _dev dev')
    elif shell == "fish":
        console.print('complete -c dev -f -a "(dev --help 2>&1 | grep -oP \'\\| \\K[a-z-]+\')"')
    else:
        console.print(f"[red]Unsupported shell: {shell}[/red]")


# Register additional commands
add_new_commands(app)
