"""
Session management commands.

Extracted from main.py: sessions, resume, fork, stop, respawn, rm, logs.
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
    app, console, CONFIG_DIR, CONFIG_FILE, __version__,
    load_config, save_config, get_provider, get_runtime, build_system_prompt,
)

from ..agents.production_loop import ProductionAgentLoop, LoopConfig
from ..utils.history import ConversationHistory, ContextManager, Conversation


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

        from dev.agents.production_loop import Message
        msg_count = 0
        tool_call_count = 0
        edited_files = set()
        for msg in conv.get_messages():
            role = msg.role
            content = msg.content or ""
            tool_calls = getattr(msg, 'tool_calls', None) or []
            if role == 'tool':
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and 'path' in data:
                        edited_files.add(data['path'])
                except Exception:
                    pass  # Intentional: tool result parsing is best-effort
            if tool_calls:
                tool_call_count += len(tool_calls)
            agent_loop._state.done_messages.append(
                Message(role=role, content=content, tool_calls=tool_calls)
            )
            msg_count += 1
        if edited_files:
            agent_loop._state.edited_files = edited_files
        console.print(f"[dim]Restored {msg_count} messages, {tool_call_count} tool calls, {len(edited_files)} edited files[/dim]")
        if edited_files:
            console.print(f"[dim]Files modified: {', '.join(sorted(edited_files)[:10])}{'...' if len(edited_files) > 10 else ''}[/dim]")
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
