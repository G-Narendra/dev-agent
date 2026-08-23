"""
Additional CLI commands for Dev.

Registers all new tools and features.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

# New tool imports
from ..tools.real_tools import (
    RealReadFilesTool, RealWriteFileTool, RealStrReplaceTool,
    RealCodeSearchTool, RealGlobTool, RealListDirectoryTool,
    RealRunTerminalCommand, RealGitOperations,
    RealWebSearchTool, RealReadUrlTool, RealPipelineTool,
)
from ..tools.patch_tools import ApplyPatchTool, EditBlockTool
from ..tools.browser_tools import (
    BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool,
    DockerRunTool, DockerBuildTool,
)

# New utility imports
from ..utils.history import ConversationHistory, ContextManager
from ..utils.auto_commit import AutoCommitter
from ..utils.quality_gates import AutoLinter, AutoTester
from ..utils.project_detector import ProjectDetector
from ..utils.error_recovery import ErrorRecovery, ToolRetry, ParallelExecutor
from ..utils.lsp_client import LSPClient
from ..utils.prompt_templates import (
    WORKFLOW_TEMPLATES, get_template, list_templates,
    CostDashboard, ReasoningController,
)
from ..utils.file_watcher import FileWatcher, AgentMailbox, PlanApproval
from ..utils.voice import VoiceInput, ToolWizard, generate_vscode_extension
from ..utils.plugins import (
    MULTI_LANGUAGE_SKILLS, PluginMarketplace, PerformanceProfiler,
)


console = Console()


def register_new_tools(registry, project_path: str):
    """Register all new tools with the tool registry."""
    # Real tools
    registry.register("read_files", RealReadFilesTool())
    registry.register("write_file", RealWriteFileTool())
    registry.register("str_replace", RealStrReplaceTool())
    registry.register("code_search", RealCodeSearchTool())
    registry.register("glob", RealGlobTool())
    registry.register("list_directory", RealListDirectoryTool())
    registry.register("run_terminal_command", RealRunTerminalCommand())
    registry.register("git_operations", RealGitOperations())
    registry.register("web_search", RealWebSearchTool())
    registry.register("read_url", RealReadUrlTool())
    
    # Unified diff tools
    registry.register("edit_block", EditBlockTool())
    registry.register("apply_patch", ApplyPatchTool())
    
    # Browser tools
    registry.register("browser_screenshot", BrowserScreenshotTool())
    registry.register("browser_navigate", BrowserNavigateTool())
    registry.register("browser_click", BrowserClickTool())
    
    # Docker tools
    registry.register("docker_run", DockerRunTool())
    registry.register("docker_build", DockerBuildTool())
    
    # Pipeline tool (chain multiple tool calls)
    registry.register("pipeline", RealPipelineTool())
    
    return registry


def add_new_commands(app):
    """Add new CLI commands."""
    
    @app.command()
    def templates():
        """List available workflow templates."""
        templates = list_templates()
        
        table = Table(title="Workflow Templates", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Steps", justify="right")
        
        for t in templates:
            table.add_row(t["name"], t["description"], str(t["steps"]))
        
        console.print(table)
    
    @app.command()
    def template_run(
        name: str = typer.Argument(..., help="Template name"),
        project: str = typer.Option(".", help="Project directory"),
    ):
        """Run a workflow template."""
        template = get_template(name)
        if not template:
            console.print(f"[red]Template not found: {name}[/red]")
            console.print("Use 'dev templates' to list available templates")
            raise typer.Exit(1)
        
        console.print(Panel(
            f"[bold]{template['name']}[/bold]\n{template['description']}\n\n"
            f"Steps: {len(template['steps'])}",
            title="📋 Template",
            border_style="blue",
        ))
        
        # Execute template steps
        async def _run_template():
            from ..providers.nim_provider import NimProvider
            from ..agents.runtime import AgentRuntime, ToolRegistry
            
            # Load config
            import json
            config_path = Path.home() / ".dev" / "config.json"
            if not config_path.exists():
                console.print("[red]No config found. Run: dev setup --key YOUR_KEY[/red]")
                raise typer.Exit(1)
            
            with open(config_path) as f:
                config = json.load(f)
            
            keys = config.get("api_keys", [])
            if not keys:
                console.print("[red]No API keys configured[/red]")
                raise typer.Exit(1)
            
            provider = NimProvider(keys=keys)
            await provider.initialize()
            
            registry = ToolRegistry()
            register_new_tools(registry, os.path.abspath(project))
            
            runtime = AgentRuntime(provider=provider, tool_registry=registry)
            
            for i, step in enumerate(template["steps"], 1):
                console.print(f"\n[bold blue]Step {i}/{len(template['steps'])}:[/bold blue] {step['prompt']}")
                
                result = await runtime.run_agent(
                    agent_id=step.get("agent", "coder"),
                    prompt=step["prompt"],
                    project_path=os.path.abspath(project),
                )
                
                output = result.get("output", {})
                if isinstance(output, dict) and "content" in output:
                    console.print(Markdown(output["content"]))
            
            await provider.close()
        
        asyncio.run(_run_template())
    
    @app.command()
    def cost():
        """Show cost and token usage dashboard."""
        # This would need access to the session's cost dashboard
        dashboard = CostDashboard()
        console.print(dashboard.format_dashboard())
    
    @app.command()
    def effort(
        level: str = typer.Argument("medium", help="Effort level: low, medium, high, creative, precise"),
    ):
        """Set reasoning effort level."""
        controller = ReasoningController()
        config = controller.set_effort(level)
        
        console.print(Panel(
            f"Effort: {config.effort}\n"
            f"Max Tokens: {config.max_tokens}\n"
            f"Temperature: {config.temperature}\n"
            f"Top P: {config.top_p}",
            title="🧠 Reasoning Effort",
            border_style="blue",
        ))
    
    @app.command()
    def detect(
        project: str = typer.Option(".", help="Project directory"),
    ):
        """Detect project language and framework."""
        detector = ProjectDetector(os.path.abspath(project))
        info = detector.detect()
        
        table = Table(title="Project Detection", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        
        table.add_row("Language", info.language)
        table.add_row("Framework", info.framework)
        table.add_row("Package Manager", info.package_manager)
        table.add_row("Test Framework", info.test_framework)
        table.add_row("Linter", info.linter)
        table.add_row("Formatter", info.formatter)
        table.add_row("Source Dirs", ", ".join(info.source_dirs))
        table.add_row("Test Dirs", ", ".join(info.test_dirs))
        table.add_row("Entry Points", ", ".join(info.entry_points))
        
        console.print(table)
    
    @app.command()
    def skills():
        """List available language skills."""
        table = Table(title="Language Skills", show_header=True)
        table.add_column("Language", style="cyan")
        table.add_column("Description")
        
        for lang, skill in MULTI_LANGUAGE_SKILLS.items():
            table.add_row(lang, skill["name"])
        
        console.print(table)
    
    @app.command()
    def plugins_list():
        """List available plugins."""
        marketplace = PluginMarketplace()
        
        table = Table(title="Plugins", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Description")
        table.add_column("Tools", justify="right")
        
        for plugin in marketplace.list_available():
            table.add_row(
                plugin.name,
                plugin.version,
                plugin.description,
                str(len(plugin.tools)),
            )
        
        console.print(table)
    
    @app.command()
    def plugin_install(
        name: str = typer.Argument(..., help="Plugin name"),
    ):
        """Install a plugin."""
        marketplace = PluginMarketplace()
        plugin = marketplace.install(name)
        
        if plugin:
            console.print(f"[green]✓ Installed: {plugin.name} v{plugin.version}[/green]")
            console.print(f"  Tools: {', '.join(plugin.tools)}")
        else:
            console.print(f"[red]Plugin not found: {name}[/red]")
    
    @app.command()
    def vscode(
        output: str = typer.Option(".dev/vscode-extension", help="Output directory"),
    ):
        """Generate VS Code extension."""
        path = generate_vscode_extension(os.path.abspath(output))
        console.print(f"[green]✓ VS Code extension generated: {path}[/green]")
        console.print("Install in VS Code:")
        console.print(f"  code --install-extension {path}")
    
    @app.command()
    def tool_create(
        name: str = typer.Argument(..., help="Tool name"),
        description: str = typer.Option("", help="Tool description"),
    ):
        """Create a custom tool."""
        wizard = ToolWizard()
        path = wizard.create_tool(name, description or f"Custom tool: {name}")
        console.print(f"[green]✓ Tool created: {path}[/green]")
    
    @app.command()
    def profile():
        """Show performance profiling report."""
        # This would need access to the session's profiler
        profiler = PerformanceProfiler()
        console.print(profiler.format_report())
    
    @app.command()
    def mailbox(
        action: str = typer.Argument("status", help="action: status, read, send"),
        agent_id: str = typer.Option("coder", help="Agent ID"),
        message: str = typer.Option("", help="Message to send"),
    ):
        """Manage agent mailbox."""
        mailbox = AgentMailbox()
        
        if action == "status":
            status = asyncio.get_event_loop().run_until_complete(
                mailbox.get_mailbox_status(agent_id)
            )
            console.print_json(status)
        elif action == "read":
            messages = asyncio.get_event_loop().run_until_complete(
                mailbox.receive(agent_id)
            )
            for msg in messages:
                console.print(f"[cyan]{msg.sender}:[/cyan] {msg.subject}")
                console.print(f"  {msg.body[:100]}")
        elif action == "send":
            if not message:
                console.print("[red]Must provide --message[/red]")
                raise typer.Exit(1)
            asyncio.get_event_loop().run_until_complete(
                mailbox.send("user", agent_id, "Message", message)
            )
            console.print(f"[green]✓ Message sent to {agent_id}[/green]")
    
    @app.command()
    def plan(
        action: str = typer.Argument("list", help="action: list, approve, reject"),
        plan_id: str = typer.Option("", help="Plan ID"),
    ):
        """Manage execution plans."""
        approval = PlanApproval()
        
        if action == "list":
            pending = approval.get_pending()
            if not pending:
                console.print("[dim]No pending plans[/dim]")
            for plan in pending:
                console.print(approval.format_plan(plan))
        elif action == "approve":
            if not plan_id:
                console.print("[red]Must provide --plan-id[/red]")
                raise typer.Exit(1)
            plan = approval.approve(plan_id)
            if plan:
                console.print(f"[green]✓ Plan approved: {plan.title}[/green]")
        elif action == "reject":
            if not plan_id:
                console.print("[red]Must provide --plan-id[/red]")
                raise typer.Exit(1)
            plan = approval.reject(plan_id)
            if plan:
                console.print(f"[red]✗ Plan rejected: {plan.title}[/red]")
    
    @app.command()
    def init(
        project: str = typer.Option(".", help="Project directory"),
    ):
        """Initialize Dev in a project (creates .dev directory)."""
        dev_dir = os.path.join(os.path.abspath(project), ".dev")
        os.makedirs(dev_dir, exist_ok=True)
        os.makedirs(os.path.join(dev_dir, "skills"), exist_ok=True)
        os.makedirs(os.path.join(dev_dir, "tools"), exist_ok=True)
        os.makedirs(os.path.join(dev_dir, "plugins"), exist_ok=True)
        
        # Create default config
        config_path = os.path.join(dev_dir, "config.json")
        if not os.path.exists(config_path):
            import json
            with open(config_path, "w") as f:
                json.dump({"sandbox_mode": "default", "auto_commit": True}, f, indent=2)
        
        console.print(f"[green]Dev initialized in {dev_dir}[/green]")
        console.print("Directories created: .dev/skills, .dev/tools, .dev/plugins")
    
    @app.command()
    def validate():
        """Validate Dev configuration and API keys."""
        import json
        config_path = Path.home() / ".dev" / "config.json"
        
        if not config_path.exists():
            console.print("[red]No config found. Run: dev setup --key YOUR_KEY[/red]")
            return
        
        with open(config_path) as f:
            config = json.load(f)
        
        keys = config.get("api_keys", [])
        console.print(f"API Keys: {len(keys)} configured")
        
        if not keys:
            console.print("[red]No API keys configured[/red]")
            return
        
        # Test first key
        async def _validate():
            from ..providers.nim_provider import NimProvider
            nim = NimProvider(keys=[keys[0]])
            await nim.initialize()
            try:
                result = await nim.chat_completion(
                    messages=[{"role": "user", "content": "Say hello in one word"}],
                    model="nvidia/llama-3.1-8b-instruct",
                    max_tokens=10,
                )
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                console.print(f"[green]API key valid - Model responded: {content[:50]}[/green]")
            except Exception as e:
                console.print(f"[red]API key invalid: {e}[/red]")
            finally:
                await nim.close()
        
        asyncio.run(_validate())
    
    @app.command()
    def conversations(
        action: str = typer.Argument("list", help="action: list, show, delete"),
        conv_id: str = typer.Option("", help="Conversation ID"),
    ):
        """Manage saved conversations."""
        from ..utils.history import ConversationHistory
        history = ConversationHistory()
        
        if action == "list":
            convs = history.list_conversations()
            if not convs:
                console.print("[dim]No saved conversations[/dim]")
                return
            for c in convs:
                console.print(f"  {c['id'][:12]}  {c['message_count']} msgs  {c.get('metadata', {})}")
        elif action == "show":
            if not conv_id:
                console.print("[red]Must provide --conv-id[/red]")
                raise typer.Exit(1)
            conv = history.get_conversation(conv_id)
            if not conv:
                console.print(f"[red]Not found: {conv_id}[/red]")
                return
            for msg in conv.messages[-20:]:
                role_color = "blue" if msg.role == "user" else "green" if msg.role == "assistant" else "dim"
                console.print(f"[{role_color}]{msg.role}:[/{role_color}] {msg.content[:200]}")
        elif action == "delete":
            if not conv_id:
                console.print("[red]Must provide --conv-id[/red]")
                raise typer.Exit(1)
            if history.delete_conversation(conv_id):
                console.print(f"[green]Deleted: {conv_id}[/green]")
    
    # --- Workflow Commands ---

    @app.command("workflow-list")
    def workflow_list_cmd():
        """List saved workflows."""
        from ..utils.workflows import WorkflowManager, BUILTIN_WORKFLOWS
        mgr = WorkflowManager()
        workflows = mgr.list_workflows()
        all_workflows = list(BUILTIN_WORKFLOWS.keys()) + [w['name'] for w in workflows]
        if not all_workflows:
            console.print("[dim]No workflows[/dim]")
            return
        console.print("[bold]Built-in workflows:[/bold]")
        for name, wf in BUILTIN_WORKFLOWS.items():
            console.print(f"  {name}: {wf['description']}")
        if workflows:
            console.print("[bold]Custom workflows:[/bold]")
            for w in workflows:
                console.print(f"  {w['name']}: {w['description']} ({w['steps']} steps)")

    @app.command("workflow-run")
    def workflow_run_cmd(
        name: str = typer.Argument(..., help="Workflow name"),
        project: str = typer.Option(".", help="Project directory"),
    ):
        """Run a workflow."""
        import asyncio
        from ..utils.workflows import WorkflowManager, WorkflowEngine, Workflow, BUILTIN_WORKFLOWS
        from ..providers.nim_provider import NimProvider
        from ..agents.runtime import AgentRuntime, ToolRegistry

        # Load workflow
        wf_data = BUILTIN_WORKFLOWS.get(name)
        if wf_data:
            workflow = Workflow.from_dict(wf_data)
        else:
            mgr = WorkflowManager(project)
            workflow = mgr.load_workflow(name)

        if not workflow:
            console.print(f"[red]Workflow not found: {name}[/red]")
            raise typer.Exit(1)

        console.print(Panel(
            f"[bold]{workflow.name}[/bold]\n{workflow.description}\nSteps: {len(workflow.steps)}",
            title="Running Workflow", border_style="blue",
        ))

        async def _run():
            config_path = Path.home() / ".dev" / "config.json"
            if not config_path.exists():
                console.print("[red]No config. Run: dev setup --key YOUR_KEY[/red]")
                raise typer.Exit(1)
            with open(config_path) as f:
                config = json.load(f)
            keys = config.get("api_keys", [])
            nim = NimProvider(keys=keys)
            await nim.initialize()
            try:
                runtime = AgentRuntime(provider=nim, tool_registry=ToolRegistry())
                from ..cli.main import get_runtime
                runtime = get_runtime(nim, project)
                engine = WorkflowEngine(runtime=runtime, provider=nim)
                result = await engine.execute(workflow)
                console.print(f"\n[green]Workflow {'completed' if result['completed'] else 'failed'}[/green]")
                for step_id, step_result in result.get('results', {}).items():
                    status = 'ok' if step_result.get('success', True) else 'FAILED'
                    console.print(f"  {step_id}: {status}")
            finally:
                await nim.close()

        asyncio.run(_run())

    # --- Tool Rules Commands ---

    @app.command("tool-rules")
    def tool_rules_cmd(
        action: str = typer.Argument("list", help="list, add, remove, defaults"),
        pattern: str = typer.Option(None, help="Tool pattern (for add/remove)"),
        action_type: str = typer.Option("allow", help="allow or deny (for add)"),
        reason: str = typer.Option("", help="Reason (for add)"),
        project: str = typer.Option(".", help="Project directory"),
    ):
        """Manage per-tool allow/deny rules."""
        from ..utils.tool_rules import ToolRulesManager
        mgr = ToolRulesManager(project)

        if action == "list":
            rules = mgr.list_rules()
            if not rules:
                console.print("[dim]No rules. Run: dev tool-rules defaults[/dim]")
                return
            for r in rules:
                color = "green" if r["action"] == "allow" else "red"
                console.print(f"  [{color}]{r['action']}[/{color}] {r['pattern']} {r.get('reason', '')}")
        elif action == "add":
            if not pattern:
                console.print("[red]Must provide --pattern[/red]")
                raise typer.Exit(1)
            mgr.add_rule(pattern, action_type, reason)
            console.print(f"[green]Rule added: {action_type} {pattern}[/green]")
        elif action == "remove":
            if not pattern:
                console.print("[red]Must provide --pattern[/red]")
                raise typer.Exit(1)
            mgr.remove_rule(pattern)
            console.print(f"[green]Rule removed: {pattern}[/green]")
        elif action == "defaults":
            mgr.add_defaults()
            console.print("[green]Default rules added[/green]")

    return app
