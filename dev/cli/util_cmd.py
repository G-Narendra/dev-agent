"""
Utility commands — setup, auth, mode-set, undo/redo, doctor, and all small commands.

Extracted from main.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .shared import (
    app, approval_app, checkpoint_app,
    console, CONFIG_DIR, CONFIG_FILE, __version__,
    load_config, save_config, get_provider, get_runtime, build_system_prompt,
)

from ..providers.nim_provider import NimProvider, RateLimitConfig
from ..utils.approval import ApprovalManager, ApprovalMode, get_mode_description
from ..utils.checkpoints import CheckpointManager
from ..utils.headless import HeadlessRunner, HeadlessConfig, OutputFormat
from ..utils.modes import ModeManager, AgentMode
from ..utils.project_detector import ProjectDetector
from ..utils.prompt_templates import CostDashboard, ReasoningController
from ..utils.plugins import PerformanceProfiler


# ============================================================================
# Setup & Auth
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
        keys = run_first_run_wizard()
        total = sum(len(v) for v in keys.values())
        if total > 0:
            console.print(f"\n[green]✅ {total} key(s) configured across {len(keys)} provider(s)[/green]")
        else:
            console.print("[yellow]No keys configured. Run 'dev setup' later.[/yellow]")
        return

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


@app.command("first-run")
def first_run_cmd():
    """Run the interactive API key setup wizard for all 3 providers."""
    from ..config.first_run import run_first_run_wizard
    keys = run_first_run_wizard()
    total = sum(len(v) for v in keys.values())
    if total > 0:
        console.print(f"\n[green]✅ {total} key(s) configured[/green]")


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

    dev_dir = os.path.join(os.getcwd(), ".dev")
    os.makedirs(dev_dir, exist_ok=True)
    os.makedirs(os.path.join(dev_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(dev_dir, "checkpoints"), exist_ok=True)
    console.print("[green]Created .dev/ directory structure[/green]")

    devmd = os.path.join(os.getcwd(), "DEV.md")
    if not os.path.isfile(devmd):
        with open(devmd, "w") as f:
            f.write("# Project Instructions\n\nThis file is read by Dev at session start.\nAdd your coding standards, architecture decisions, and preferences here.\n")
        console.print("[green]Created DEV.md[/green]")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("[dim]Run 'dev setup --key YOUR_KEY' to configure your API key[/dim]")


# ============================================================================
# Mode & Checkpoint Commands
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
    checkpoint_id: int = typer.Argument(None, help="Checkpoint ID"),
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


# ============================================================================
# Information Commands
# ============================================================================

@app.command("models")
def models():
    """List available NVIDIA NIM models."""
    console.print(Panel("[bold]NVIDIA NIM Models[/bold]", border_style="blue"))
    for category, model in NimProvider.MODELS.items():
        console.print(f"  [bold]{category}[/bold]: {model}")


@app.command("status")
def status():
    """Show Dev status."""
    config = load_config()
    console.print(Panel("[bold]Dev Status[/bold]", border_style="blue"))
    keys = config.get("api_keys", [])
    console.print(f"  API Keys: {len(keys)}")
    console.print(f"  Config: {CONFIG_FILE}")


@app.command("version")
def version_cmd():
    """Show Dev version."""
    console.print(f"[bold]Dev v{__version__}[/bold]")
    console.print("  Free 24/7 AI coding agent powered by NVIDIA NIMs")
    console.print(f"  Python {sys.version.split()[0]}")


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


# ============================================================================
# Git Commands
# ============================================================================

@app.command("commit")
def commit_cmd(
    message: str = typer.Option(None, help="Commit message"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Auto-commit all changes with AI-generated message."""
    async def _commit():
        provider = await get_provider()
        try:
            from ..utils.auto_commit import AutoCommitter
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


@app.command("git-diff")
def git_diff_cmd(
    project: str = typer.Option(".", help="Project directory"),
    stat_only: bool = typer.Option(False, "--stat", help="Show only stats"),
):
    """Show colored git diff."""
    from .chat import _show_colored_diff
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

        import subprocess
        diff_result = subprocess.run(
            ["git", "diff", "HEAD~3"],
            capture_output=True, text=True, cwd=abs_project, timeout=10,
        )
        diff_context = diff_result.stdout[:10000] if diff_result.stdout else "No recent changes."

        review_prompt = f"{prompt}\n\nHere are the recent changes:\n```\n{diff_context}\n```"
        system_prompt = build_system_prompt("coder", abs_project)

        from ..agents.production_loop import ProductionAgentLoop, LoopConfig
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

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=abs_project,
        )
        base_branch = result.stdout.strip()

        console.print(f"[bold]Batch: {prompt}[/bold]")
        console.print(f"Creating {branches} parallel branches from {base_branch}...")

        branch_names = []
        for i in range(branches):
            branch_name = f"dev/batch-{i+1}"
            subprocess.run(
                ["git", "checkout", "-b", branch_name, base_branch],
                capture_output=True, cwd=abs_project,
            )
            branch_names.append(branch_name)
            console.print(f"  Created branch: {branch_name}")

        subprocess.run(
            ["git", "checkout", base_branch],
            capture_output=True, cwd=abs_project,
        )

        console.print(f"[green]Created {branches} branches. Run 'dev chat' on each to work in parallel.[/green]")
        for bn in branch_names:
            console.print(f"  [dim]git checkout {bn} && dev chat '{prompt}'[/dim]")

    asyncio.run(_batch())


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


# ============================================================================
# Feature Commands
# ============================================================================

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
    from .chat import _run_doctor
    _run_doctor(".", None, None)


@app.command("init")
def init_cmd(project: str = typer.Option(".")):
    """Initialize Dev in a project."""
    abs_project = os.path.abspath(project)
    dev_dir = os.path.join(abs_project, ".dev")
    os.makedirs(dev_dir, exist_ok=True)

    rules_dir = os.path.join(abs_project, ".devrules")
    os.makedirs(rules_dir, exist_ok=True)

    rules_file = os.path.join(rules_dir, "general.md")
    if not os.path.exists(rules_file):
        with open(rules_file, "w") as f:
            f.write("# Project Rules\n\nAdd your project-specific rules here.\n")

    console.print(f"[green]Initialized Dev in {abs_project}[/green]")
    console.print(f"[dim]Created: .dev/, .devrules/[/dim]")


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


# ============================================================================
# Advanced Commands
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


@app.command("doctor")
def doctor_cmd(project: str = typer.Option(".")):
    """Full diagnostic check (like Claude Code's /doctor). Works without API key."""
    console.print("[bold]Dev Doctor — System Diagnostics[/bold]\n")

    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    console.print(f"  {'[green]+[/green]' if py_ok else '[red]x[/red]'} Python {py_ver} {'(OK)' if py_ok else '(need 3.10+)'}")

    config_ok = CONFIG_DIR.exists()
    console.print(f"  {'[green]+[/green]' if config_ok else '[yellow]![/yellow]'} ~/.dev/ {'exists' if config_ok else 'not found (will be created)'}")

    config = load_config()
    keys = [k for k in [config.get("nim_api_key")] if k]
    env_key = os.environ.get("NIM_API_KEY", "")
    has_key = bool(keys or env_key)
    if has_key:
        console.print("  [green]+[/green] NVIDIA NIM API key configured")
    else:
        console.print("  [yellow]![/yellow] No API key configured (run: dev setup --key YOUR_KEY)")

    try:
        import subprocess
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        git_ok = result.returncode == 0
        console.print(f"  {'[green]+[/green]' if git_ok else '[yellow]![/yellow]'} Git {'installed' if git_ok else 'not found'}")
    except Exception:
        console.print("  [yellow]![/yellow] Git not found")

    from dev.tools.real_tools import RealReadFilesTool, RealWriteFileTool, RealRunTerminalCommand
    console.print("  [green]+[/green] Core tools loaded (30 tools)")

    from dev.providers.nim_provider import NimProvider
    console.print("  [green]+[/green] NVIDIA NIM provider available")

    from dev.mcp.client import McpClient
    console.print("  [green]+[/green] MCP client available")

    devmd = os.path.join(os.path.abspath(project), "DEV.md")
    claudemd = os.path.join(os.path.abspath(project), "CLAUDE.md")
    has_rules = os.path.isfile(devmd) or os.path.isfile(claudemd)
    console.print(f"  {'[green]+[/green]' if has_rules else '[dim]-[/dim]'} DEV.md/CLAUDE.md {'found' if has_rules else 'not found (optional)'}")

    skills_dir = os.path.join(os.path.abspath(project), ".dev", "skills")
    has_skills = os.path.isdir(skills_dir)
    console.print(f"  {'[green]+[/green]' if has_skills else '[dim]-[/dim]'} .dev/skills/ {'found' if has_skills else 'not found (optional)'}")

    console.print(f"\n  [bold]Dev v{__version__} — diagnostic complete[/bold]")
    if not has_key:
        console.print("  [yellow]Run 'dev setup --key YOUR_KEY' to configure NVIDIA NIM API key[/yellow]")


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


@app.command("design")
def design(
    action: str = typer.Argument("show", help="Action: show, init, learn, edit"),
    learning: str = typer.Option("", "--learning", help="New pattern to add (for 'learn' action)"),
):
    """Manage DESIGN.md — the agent's design knowledge base."""
    from ..utils.design_knowledge import (
        load_design_knowledge,
        append_learning,
        save_design_knowledge,
    )
    from pathlib import Path

    if action == "init":
        template = Path(__file__).parent.parent / "templates" / "DESIGN.md"
        target = Path("DESIGN.md")
        if target.exists():
            console.print("[yellow]DESIGN.md already exists. Use 'design edit' to modify.[/yellow]")
        elif template.exists():
            import shutil
            shutil.copy(template, target)
            console.print("[green]Created DESIGN.md from template[/green]")
        else:
            console.print("[red]Template not found[/red]")

    elif action == "show":
        content = load_design_knowledge(".")
        if content:
            console.print(Panel(content[:2000], title="DESIGN.md", border_style="cyan"))
        else:
            console.print("[yellow]No DESIGN.md found. Run 'design init' to create one.[/yellow]")

    elif action == "learn":
        if not learning:
            console.print("[red]Provide a pattern with --learning 'description'[/red]")
        else:
            append_learning(learning, ".")
            console.print(f"[green]Added learning to DESIGN.md:[/green] {learning[:80]}")

    elif action == "edit":
        console.print("[dim]Opening DESIGN.md in your editor...[/dim]")
        import subprocess
        editor = os.environ.get("EDITOR", "notepad")
        subprocess.run([editor, "DESIGN.md"])

    else:
        console.print(f"[red]Unknown action: {action}. Use show, init, learn, or edit[/red]")


# ============================================================================
# Callback & Main Entrypoint
# ============================================================================
# PR & Deployment Commands
# ============================================================================


@app.command("pr")
def pr_cmd(
    action: str = typer.Argument("create", help="create, list, status"),
    title: str = typer.Option("", help="PR title"),
    body: str = typer.Option("", help="PR description"),
    base: str = typer.Option("main", help="Base branch"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Create or manage pull requests."""
    import subprocess
    abs_project = os.path.abspath(project)

    if action == "create":
        # Auto-generate title from recent commits
        if not title:
            result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True, text=True, cwd=abs_project,
            )
            commits = result.stdout.strip().split("\n") if result.stdout.strip() else []
            title = f"Dev: {commits[0].split(" ", 1)[1] if commits else "AI-generated changes"}"

        # Auto-generate body from git diff
        if not body:
            result = subprocess.run(
                ["git", "diff", "--stat", base],
                capture_output=True, text=True, cwd=abs_project,
            )
            body = f"## Changes\n\n```\n{result.stdout}\n```\n\nGenerated by Dev Agent"

        # Create branch, commit, push
        branch = f"dev/pr-{int(time.time())}"
        subprocess.run(["git", "checkout", "-b", branch], capture_output=True, cwd=abs_project)
        subprocess.run(["git", "add", "-A"], capture_output=True, cwd=abs_project)
        subprocess.run(["git", "commit", "-m", title], capture_output=True, cwd=abs_project)
        subprocess.run(["git", "push", "-u", "origin", branch], capture_output=True, cwd=abs_project)

        # Try gh CLI
        try:
            result = subprocess.run(
                ["gh", "pr", "create", "--title", title, "--body", body, "--base", base],
                capture_output=True, text=True, cwd=abs_project, timeout=10,
            )
            if result.returncode == 0:
                console.print(f"[green]PR created: {result.stdout.strip()}[/green]")
            else:
                console.print(f"[yellow]PR branch pushed. Create PR manually or install gh CLI.[/yellow]")
        except FileNotFoundError:
            console.print(f"[yellow]Branch '{branch}' pushed. Install gh CLI to auto-create PRs.[/yellow]")

        console.print(f"[dim]Branch: {branch}[/dim]")

    elif action == "list":
        try:
            result = subprocess.run(
                ["gh", "pr", "list"],
                capture_output=True, text=True, cwd=abs_project, timeout=10,
            )
            console.print(result.stdout or "[dim]No open PRs[/dim]")
        except FileNotFoundError:
            console.print("[yellow]Install gh CLI: https://cli.github.com/[/yellow]")

    elif action == "status":
        try:
            result = subprocess.run(
                ["gh", "pr", "status"],
                capture_output=True, text=True, cwd=abs_project, timeout=10,
            )
            console.print(result.stdout)
        except FileNotFoundError:
            console.print("[yellow]Install gh CLI: https://cli.github.com/[/yellow]")


@app.command("deploy")
def deploy_cmd(
    platform: str = typer.Option("auto", help="Platform: auto, vercel, netlify, railway, render"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Deploy project to a free hosting platform."""
    import subprocess
    abs_project = os.path.abspath(project)

    # Auto-detect platform
    if platform == "auto":
        if os.path.exists(os.path.join(abs_project, "vercel.json")):
            platform = "vercel"
        elif os.path.exists(os.path.join(abs_project, "netlify.toml")):
            platform = "netlify"
        elif os.path.exists(os.path.join(abs_project, "Procfile")):
            platform = "railway"
        elif os.path.exists(os.path.join(abs_project, "render.yaml")):
            platform = "render"
        elif os.path.exists(os.path.join(abs_project, "Dockerfile")):
            platform = "render"
        else:
            console.print("[yellow]No deployment config found. Creating vercel.json...[/yellow]")
            # Auto-create vercel.json for Node.js projects
            if os.path.exists(os.path.join(abs_project, "package.json")):
                import json
                config = {"version": 2, "builds": [{"src": "package.json", "use": "@vercel/node"}]}
                with open(os.path.join(abs_project, "vercel.json"), "w") as f:
                    json.dump(config, f, indent=2)
                platform = "vercel"
            elif os.path.exists(os.path.join(abs_project, "requirements.txt")) or os.path.exists(os.path.join(abs_project, "pyproject.toml")):
                config = {"version": 2, "builds": [{"src": "requirements.txt", "use": "@vercel/python"}]}
                with open(os.path.join(abs_project, "vercel.json"), "w") as f:
                    json.dump(config, f, indent=2)
                platform = "vercel"
            else:
                console.print("[red]Cannot auto-detect. Use --platform vercel|netlify|railway|render[/red]")
                return

    console.print(f"[bold]Deploying to {platform}...[/bold]")

    if platform == "vercel":
        try:
            result = subprocess.run(
                ["npx", "vercel", "--yes"],
                capture_output=True, text=True, cwd=abs_project, timeout=120,
            )
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[yellow]Install: npm i -g vercel[/yellow]")
        except FileNotFoundError:
            console.print("[yellow]Install: npm i -g vercel[/yellow]")

    elif platform == "netlify":
        try:
            result = subprocess.run(
                ["npx", "netlify-cli", "deploy", "--prod"],
                capture_output=True, text=True, cwd=abs_project, timeout=120,
            )
            console.print(result.stdout)
        except FileNotFoundError:
            console.print("[yellow]Install: npm i -g netlify-cli[/yellow]")

    elif platform == "railway":
        try:
            result = subprocess.run(
                ["npx", "railway", "up"],
                capture_output=True, text=True, cwd=abs_project, timeout=120,
            )
            console.print(result.stdout)
        except FileNotFoundError:
            console.print("[yellow]Install: npm i -g @railway/cli[/yellow]")

    else:
        console.print(f"[yellow]Platform '{platform}' not auto-deployable. Use --platform vercel|netlify|railway[/yellow]")


@app.command("issue")
def issue_cmd(
    action: str = typer.Argument("create", help="create, list"),
    title: str = typer.Option("", help="Issue title"),
    body: str = typer.Option("", help="Issue description"),
    project: str = typer.Option(".", help="Project directory"),
):
    """Create or manage GitHub issues."""
    import subprocess
    abs_project = os.path.abspath(project)

    if action == "create":
        if not title:
            title = console.input("Issue title: ").strip()
            if not title:
                console.print("[red]Title required[/red]")
                return

        try:
            cmd = ["gh", "issue", "create", "--title", title]
            if body:
                cmd.extend(["--body", body])
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=abs_project, timeout=10)
            if result.returncode == 0:
                console.print(f"[green]Issue created: {result.stdout.strip()}[/green]")
            else:
                console.print(f"[yellow]{result.stderr.strip()}[/yellow]")
        except FileNotFoundError:
            console.print("[yellow]Install gh CLI: https://cli.github.com/[/yellow]")

    elif action == "list":
        try:
            result = subprocess.run(
                ["gh", "issue", "list"],
                capture_output=True, text=True, cwd=abs_project, timeout=10,
            )
            console.print(result.stdout or "[dim]No open issues[/dim]")
        except FileNotFoundError:
            console.print("[yellow]Install gh CLI: https://cli.github.com/[/yellow]")


# ============================================================================
# Callback
# ============================================================================

@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """Dev - Free 24/7 AI coding agent."""
    if version:
        console.print(f"Dev v{__version__}")
        raise typer.Exit()
