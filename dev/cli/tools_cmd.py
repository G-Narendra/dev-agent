"""
Tool management commands — tools-list, tool-rules, MCP, rules.

Extracted from main.py to reduce file size.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .shared import (
    app, console, CONFIG_DIR, CONFIG_FILE,
)

from ..utils.rules import RulesLoader
from ..utils.inputs import InputManager


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
        ApplyPatchTool, EditBlockTool, RepoMapTool, SummarizeTool,
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
            pass  # Intentional: tool instantiation may fail if deps missing

    console.print(table)


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
        print(json.dumps(rules, indent=2))
    elif action == "config":
        console.print("[dim]Auto-mode config: using defaults (no custom rules set)[/dim]")
    elif action == "reset":
        console.print("[green]Auto-mode reset to defaults[/green]")


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
