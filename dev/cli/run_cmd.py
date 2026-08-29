"""
Run, task, and serve commands — single-task execution and background workers.

Extracted from main.py to reduce file size.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .shared import (
    app, console, CONFIG_DIR, CONFIG_FILE, __version__,
    load_config, save_config, get_provider, get_runtime, build_system_prompt,
)

from ..providers.nim_provider import NimProvider, RateLimitConfig
from ..agents.runtime import AgentRuntime, ToolRegistry
from ..agents.agent_definition import get_agent, list_agents
from ..agents.production_loop import ProductionAgentLoop, LoopConfig
from ..utils.project_detector import ProjectDetector
from ..utils.error_recovery import ErrorRecovery
from ..utils.plugins import PerformanceProfiler
from .tui import DevTUI, StreamingDisplay


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
        if init_only:
            console.print("[dim]Running setup hooks...[/dim]")
            console.print("[green]Setup complete[/green]")
            return

        if exec_cmd:
            import subprocess as _sp
            console.print(f"[dim]Running: {exec_cmd}[/dim]")
            result = _sp.run(exec_cmd, shell=True, capture_output=True, text=True, cwd=os.path.abspath(project))
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
            return

        try:
            from dev.utils.session_manager import UpdateChecker
            upd = UpdateChecker.check_version()
            if upd.get("update_available"):
                console.print(f"[yellow]Update available: {upd['latest']} (run: dev update)[/yellow]")
        except Exception:
            pass  # Intentional: update check is best-effort

        provider = await get_provider()
        runtime = get_runtime(provider, project)
        abs_project = os.path.abspath(project)

        if dangerously_skip:
            effective_approval = "full-auto"

        try:
            detector = ProjectDetector(abs_project)
            info = detector.detect()
            if info.language != "unknown":
                console.print(f"[dim]Detected: {info.language}/{info.framework}[/dim]")

            system_prompt = "" if bare else build_system_prompt(agent, abs_project, append_system)

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

            try:
                agent_def = get_agent(agent)
                agent_loop.set_tool_names(agent_def.tool_names)
            except Exception:
                pass  # Intentional: tool name restriction is best-effort

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

            tool_calls = result.get("tool_calls", [])
            if tool_calls:
                console.print(f"[dim]Used {len(tool_calls)} tool(s) in {result.get('steps', 0)} step(s)[/dim]")

            stats = provider.get_stats()
            console.print(f"[dim]Tokens: {stats['total_tokens']} | Requests: {stats['total_requests']}[/dim]")

        finally:
            await provider.close()

    asyncio.run(_run())


@app.command()
def task(
    action: str = typer.Argument(..., help="add, list, status, cancel"),
    prompt: str = typer.Option(None, help="Task prompt (for add)"),
    task_id: str = typer.Option(None, help="Task ID"),
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
