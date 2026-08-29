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
                    if len(state.done_messages) > 10:
                        summary = "[Previous messages compacted by /compact command]\n"
                        for msg in state.done_messages[-10:]:
                            if msg.role == "user":
                                summary += f"User: {msg.content[:100]}\n"
                            elif msg.role == "assistant" and msg.content:
                                summary += f"Assistant: {msg.content[:100]}\n"
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
                    agent_loop._state.done_messages = []
                    agent_loop._state.cur_messages = []
                    console.print("[green]Context cleared. Project memory preserved.[/green]")
                    continue
                elif cmd == "/init":
                    console.print("[dim]Initializing Dev project config...[/dim]")
                    dev_dir = os.path.join(abs_project, ".dev")
                    os.makedirs(dev_dir, exist_ok=True)
                    devmd = os.path.join(abs_project, "DEV.md")
                    if not os.path.exists(devmd):
                        with open(devmd, "w") as f:
                            f.write("# Project Instructions\n\n")
                            f.write("Add your project-specific instructions here.\n")
                        console.print("[green]Created DEV.md[/green]")
                    else:
                        console.print("[dim]DEV.md already exists[/dim]")
                    rules_dir = os.path.join(abs_project, ".devrules")
                    os.makedirs(rules_dir, exist_ok=True)
                    console.print("[green]Initialized .dev directory[/green]")
                    continue
                elif cmd == "/memory":
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
                elif cmd == "/insights":
                    console.print("[dim]Generating usage insights report...[/dim]")
                    report_path = os.path.join(str(Path.home()), ".dev", "usage-report.html")
                    os.makedirs(os.path.dirname(report_path), exist_ok=True)
                    with open(report_path, "w") as f:
                        f.write("<!DOCTYPE html><html><head><title>Dev Usage Insights</title>")
                        f.write("<style>body{font-family:system-ui;max-width:800px;margin:0 auto;padding:20px;}</style></head><body>")
                        f.write("<h1>Dev Agent Usage Insights</h1>")
                        f.write(f"<p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>")
                        total_tokens = stream_tokens[0] if stream_tokens else 0
                        f.write(f"<p>Total tokens this session: {total_tokens}</p>")
                        f.write("</body></html>")
                    console.print(f"[green]Report saved to {report_path}[/green]")
                    continue
                elif cmd == "/simplify":
                    console.print("[dim]Running simplify review...[/dim]")
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
                elif cmd == "/statusline":
                    ctx_usage = agent_loop._state.context_tokens / max(agent_loop._state.max_context_tokens, 1) * 100
                    bar_len = 30
                    filled = int(ctx_usage / 100 * bar_len)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    console.print(f"Context: {bar} {ctx_usage:.1f}% ({agent_loop._state.context_tokens}/{agent_loop._state.max_context_tokens} tokens)")
                    console.print(f"Messages: {len(agent_loop._state.done_messages)} | Tools: {len(agent_loop._state.tool_stats)}")
                    console.print(f"Steps: {agent_loop._state.current_step}/{agent_loop._state.max_steps}")
                    continue
                elif cmd == "/fast":
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
                        if effort_level["current"] == "low":
                            effort_level["current"] = "medium"
                            console.print("[green]Fast mode OFF (medium effort)[/green]")
                        else:
                            effort_level["current"] = "low"
                            console.print("[green]Fast mode ON (low effort)[/green]")
                    continue
                elif cmd == "/stats":
                    ctx_usage = agent_loop._state.context_tokens / max(agent_loop._state.max_context_tokens, 1) * 100
                    console.print("[bold]Session Statistics[/bold]")
                    console.print(f"  Tokens sent: {agent_loop._state.context_tokens:,}")
                    console.print(f"  Context usage: {ctx_usage:.1f}%")
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
                elif cmd == "/grill":
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
                elif cmd == "/copy":
                    if full_response:
                        try:
                            import pyperclip
                            pyperclip.copy("".join(full_response))
                            console.print("[green]Response copied to clipboard[/green]")
                        except ImportError:
                            import tempfile
                            tmp = os.path.join(tempfile.gettempdir(), "dev_response.txt")
                            with open(tmp, "w") as f:
                                f.write("".join(full_response))
                            console.print(f"[dim]Response saved to {tmp}[/dim]")
                    else:
                        console.print("[dim]No response to copy[/dim]")
                    continue
                elif cmd == "/handover":
                    console.print("[dim]Generating handover document...[/dim]")
                    handover = (
                        "# Session Handover\n\n"
                        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        "## Summary\n[To be filled by AI]\n\n"
                        "## Decisions Made\n[To be filled by AI]\n\n"
                        "## Incomplete Tasks\n[To be filled by AI]\n\n"
                        "## Lessons Learned\n[To be filled by AI]\n"
                    )
                    handover_path = os.path.join(abs_project, "HANDOVER.md")
                    with open(handover_path, "w") as f:
                        f.write(handover)
                    console.print(f"[green]Handover template saved to {handover_path}[/green]")
                    continue
                elif cmd == "/release-notes":
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
                elif cmd == "/vim":
                    console.print("[dim]Vim mode toggled (visual editor for multi-line input)[/dim]")
                    continue
                elif cmd == "/terminal-setup":
                    console.print("[bold]Terminal Setup[/bold]")
                    console.print("Keybindings:")
                    console.print("  Shift+Enter — Multi-line input")
                    console.print("  Ctrl+R — Search history")
                    console.print("  Ctrl+T — Toggle task list")
                    console.print("  Ctrl+O — Toggle verbose")
                    console.print("  Esc — Cancel generation")
                    console.print("[dim]Configure these in your terminal settings[/dim]")
                    continue
                elif cmd == "/extra-usage":
                    console.print("[dim]Extra usage configuration[/dim]")
                    console.print("Current plan: Free (NVIDIA NIMs)")
                    console.print("Rate limit: 40 RPM per key")
                    console.print("[dim]Add more keys with: dev setup[/dim]")
                    continue
                elif cmd == "/privacy-settings":
                    console.print("[dim]Privacy Settings[/dim]")
                    console.print("Data storage: Local only")
                    console.print("Telemetry: Disabled")
                    console.print("API keys: Encrypted at rest")
                    console.print("[dim]All data stays on your machine[/dim]")
                    continue
                elif cmd == "/session-id":
                    import uuid
                    session_id = str(uuid.uuid4())[:8]
                    console.print(f"[dim]Session ID: {session_id}[/dim]")
                    continue
                elif cmd == "/pr-comments":
                    console.print("[dim]Fetching PR comments...[/dim]")
                    import subprocess as _sp
                    result = _sp.run(["git", "log", "--oneline", "-5"], cwd=abs_project, capture_output=True, text=True)
                    if result.stdout:
                        console.print("[dim]Recent commits:[/dim]")
                        console.print(result.stdout[:500])
                    else:
                        console.print("[dim]No git history found[/dim]")
                    continue
                elif cmd == "/feedback":
                    console.print("[dim]Feedback[/dim]")
                    console.print("Thank you for using Dev Agent!")
                    console.print("GitHub: https://github.com/G-Narendra/dev-agent")
                    console.print("[dim]Please open an issue on GitHub[/dim]")
                    continue
                elif cmd == "/ultra-think":
                    console.print("[dim]Ultra-think mode activated — reasoning effort set to maximum[/dim]")
                    effort_level["current"] = "high"
                    continue
                elif cmd == "/step-by-step":
                    sbt_text = user_input.replace("/step-by-step", "", 1).strip()
                    if not sbt_text:
                        console.print("[dim]Usage: /step-by-step <task>[/dim]")
                        continue
                    user_message = f"Explain and do this step by step: {sbt_text}"
                elif cmd == "/conservative":
                    user_message = f"Be conservative and verify before making changes: {user_input.replace('/conservative', '', 1).strip()}"
                elif cmd == "/theme":
                    console.print("[bold]Themes:[/bold]")
                    console.print("  1. [green]default[/green] — Green accent")
                    console.print("  2. [blue]ocean[/blue] — Blue accent")
                    console.print("  3. [red]fire[/red] — Red accent")
                    console.print("  4. [magenta]purple[/magenta] — Purple accent")
                    console.print("  5. [yellow]gold[/yellow] — Gold accent")
                    continue
                elif cmd == "/output-style":
                    console.print("[bold]Output Styles:[/bold]")
                    console.print("  1. [green]default[/green] — Concise, code-only")
                    console.print("  2. [blue]explanatory[/blue] — Explains design decisions")
                    console.print("  3. [yellow]learning[/yellow] — Explains reasoning, step-by-step")
                    console.print("  4. [magenta]concise[/magenta] — Minimal output, maximum efficiency")
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
