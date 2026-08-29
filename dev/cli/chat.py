"""
Chat command — the core interactive CLI experience.

Extracted from main.py to reduce file size.
Contains: chat command, slash command handling, streaming display, helpers.
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

from .shared import (
    app, console, CONFIG_DIR, CONFIG_FILE, __version__,
    load_config, save_config, get_provider, get_runtime, build_system_prompt,
)

from ..providers.nim_provider import NimProvider, RateLimitConfig
from ..agents.runtime import AgentRuntime, ToolRegistry
from ..agents.agent_definition import get_agent, list_agents
from ..agents.production_loop import ProductionAgentLoop, LoopConfig

from ..utils.approval import ApprovalManager, ApprovalMode, get_mode_description
from ..utils.checkpoints import CheckpointManager
from ..utils.teams import TeamManager, AgentRole, Team
from ..utils.modes import ModeManager, AgentMode
from ..utils.rules import RulesLoader
from ..utils.inputs import InputManager

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


# ============================================================================
# Helper functions
# ============================================================================


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
        pass  # Intentional: diff display is best-effort


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


def _run_doctor(project_path: str, provider, runtime):
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
# Chat command
# ============================================================================


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
        # Use the chat() parameter directly (don't shadow with local assignment)
        _approval_mode = approval

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
            pass  # Intentional: update check is best-effort

        # --resume: resume session by ID or show picker
        if resume:
            from dev.utils.history import ConversationHistory
            history = ConversationHistory()
            convs = history.list_conversations()
            matched = [c for c in convs if resume in c.get("id", "") or resume in c.get("name", "")]
            if matched:
                conv_id = matched[0]["id"]
                console.print(f"[green]Resuming session: {conv_id[:12]}[/green]")
                loaded_conv = history.load_conversation(conv_id)
                if loaded_conv:
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
            console.print("\n" + "=" * 60)
            console.print("[bold red]⚠️  SECURITY WARNING: --dangerously-skip-permissions[/bold red]")
            console.print("[red]All permission prompts are DISABLED.[/red]")
            console.print("[red]The agent can execute ANY command without approval.[/red]")
            console.print("[red]This includes: file deletion, network access, system commands.[/red]")
            console.print("[dim]Press Ctrl+C within 3 seconds to abort...[/dim]")
            import time as _time
            try:
                _time.sleep(3)
            except KeyboardInterrupt:
                console.print("\n[yellow]Aborted by user.[/yellow]")
                raise typer.Exit(0)
            console.print("=" * 60 + "\n")

        # --print mode: non-interactive, print response and exit
        if print_mode:
            print_prompt = prompt
            if not print_prompt and not sys.stdin.isatty():
                print_prompt = sys.stdin.read().strip()
            if not print_prompt:
                console.print('[red]No prompt provided. Usage: narendra chat -p "your prompt"[/red]')
                await provider.close()
                return
            try:
                from dev.agents.production_loop import ProductionAgentLoop as PAL, LoopConfig as LC
                lc = LC(model=model, auto_lint=True, auto_commit=True, verbose=verbose, approval_mode=approval or "auto-edit")
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
        model_display = NimProvider.MODELS.get(model, model)
        console.print(Panel(
            f"[bold green]Dev[/bold green] - Free 24/7 AI Coding Agent\n"
            f"[dim]Model: {model_display} ({model}) | Approval: {mode_label}[/dim]\n"
            f"[dim]Type your request. Use [bold]/help[/bold] for commands.[/dim]",
            title="[bold green]Dev Chat[/bold green]",
            border_style="green",
        ))

        turn_count = 0

        # Start file watcher
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

            # Handle slash commands via dedicated handler
            if user_input.startswith("/"):
                from .slash_handler import SlashCommandHandler
                handler = SlashCommandHandler(
                    console=console, agent_loop=agent_loop, conv=conv,
                    history=history, provider=provider, abs_project=abs_project,
                    cost_dashboard=cost_dashboard, detector=detector,
                    effort_level=effort_level, output_style=output_style,
                    stream_tokens=stream_tokens, full_response=full_response,
                    budget_mgr=budget_mgr,
                )
                action, should_continue = await handler.handle(cmd, user_input)
                if action == "quit":
                    break
                elif action == "message":
                    # Transform input and process normally
                    user_message = user_input
                elif not should_continue:
                    break
                else:
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
                # Live context bar update after each tool call
                try:
                    msgs = agent_loop.get_state().done_messages + agent_loop.get_state().cur_messages
                    tokens = agent_loop._count_tokens(msgs)
                    _show_context_bar(tokens, agent_loop.config.max_context_tokens)
                except Exception:
                    pass  # Intentional: context bar is best-effort

            profiler.start_timer("agent_run")
            try:
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

                content = result.get("content", "")
                if content:
                    conv.add_message("assistant", content)

                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    console.print(f"[dim]Used {len(tool_calls)} tool(s) in {result.get('steps', 0)} step(s)[/dim]")

                tokens_sent = result.get("tokens_sent", 0)
                tokens_recv = result.get("tokens_received", 0)
                if tokens_sent or tokens_recv:
                    console.print(f"[dim]  Tokens: {tokens_sent:,} sent + {tokens_recv:,} received = {tokens_sent + tokens_recv:,} total[/dim]")

                if tool_calls and agent_loop.config.show_diffs:
                    _show_colored_diff(abs_project)

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
                # Auto-save session on error
                if not no_persist:
                    try:
                        conv.add_message("system", f"[Error: {e}]")
                        await asyncio.to_thread(history.save_conversation, conv)
                        console.print("[dim]Session auto-saved.[/dim]")
                    except Exception:
                        pass  # Intentional: best-effort save on error
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
            pass  # Intentional: file watcher cleanup is best-effort

        # Save conversation on exit
        if not no_persist:
            await asyncio.to_thread(history.save_conversation, conv)
        await provider.close()

    asyncio.run(_chat())
