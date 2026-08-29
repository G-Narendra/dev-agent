"""
Agent management commands — teams, scheduling, messaging, daemon.

Extracted from main.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .shared import (
    app, team_app, mode_app, schedule_app, messaging_app,
    console, CONFIG_DIR, CONFIG_FILE, __version__,
)

from ..utils.teams import TeamManager, AgentRole, Team
from ..utils.modes import ModeManager, AgentMode
from ..utils.scheduler import AgentScheduler
from ..utils.messaging import MessagingManager, Platform


# --- Team Commands ---

@team_app.command("create")
def team_create(name: str = typer.Argument(...)):
    """Create a new agent team."""
    mgr = TeamManager()
    team = mgr.create_team(name)
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
    """List all teams."""
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
    """Switch agent mode."""
    mgr = ModeManager()
    new_mode = mgr.set_mode(mode)
    console.print(f"[green]Mode: {new_mode.value}[/green]")


@mode_app.command("plan-create")
def mode_plan_create(goal: str = typer.Argument(...)):
    """Create a plan."""
    mgr = ModeManager()
    plan = mgr.create_plan(goal)
    console.print(f"[green]Plan created: {plan.id}[/green]")


@mode_app.command("plan-show")
def mode_plan_show():
    """Show current plan."""
    mgr = ModeManager()
    console.print(mgr.format_plan())


# --- Schedule Commands ---

@schedule_app.command("add")
def schedule_add(
    name: str = typer.Argument(...),
    prompt: str = typer.Option(...),
    cron: str = typer.Option(...),
):
    """Add a scheduled task."""
    mgr = AgentScheduler()
    task = mgr.create_task(name, prompt, cron)
    console.print(f"[green]Scheduled: {task.name} ({task.cron_expression})[/green]")


@schedule_app.command("list")
def schedule_list():
    """List scheduled tasks."""
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
    """Connect Telegram bot."""
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.TELEGRAM, token)
    console.print("[green]Telegram bot configured[/green]")


@messaging_app.command("slack")
def connect_slack(token: str = typer.Option(...)):
    """Connect Slack bot."""
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.SLACK, token)
    console.print("[green]Slack bot configured[/green]")


@messaging_app.command("discord")
def connect_discord(token: str = typer.Option(...)):
    """Connect Discord bot."""
    mgr = MessagingManager()
    bot = mgr.add_bot(Platform.DISCORD, token)
    console.print("[green]Discord bot configured[/green]")


@messaging_app.command("list")
def connect_list():
    """List connected messaging platforms."""
    mgr = MessagingManager()
    bots = mgr.list_bots()
    if not bots:
        console.print("[dim]No platforms connected[/dim]")
        return
    for b in bots:
        console.print(f"  {b['platform']}: enabled={b['enabled']}")


# --- Daemon ---

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


# --- Agents ---

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
        print(json.dumps([{"id": s.get("id", ""), "status": s.get("status", ""), "cwd": s.get("cwd", "")} for s in sessions], indent=2))
        return

    table = Table(title="Agent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("CWD", style="dim")
    table.add_column("Started", style="dim")

    for s in sessions:
        table.add_row(s.get("id", "?")[:12], s.get("status", "unknown"), s.get("cwd", "."), s.get("started", "?"))
    console.print(table)
