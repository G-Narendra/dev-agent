"""
Production TUI for Dev using Rich.

Adapted from Freebuff's terminal UI and Codex's TUI patterns.
Features:
- Live streaming display
- Tool output formatting
- Status bar
- Error display
- Session persistence
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, AsyncIterator, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


# Custom theme
THEME = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
    "agent": "bold blue",
    "tool": "dim cyan",
    "user": "bold white",
    "thinking": "dim italic",
})


class DevTUI:
    """
    Production terminal UI for Dev.
    
    From Freebuff's CLI and Codex's TUI.
    """
    
    def __init__(self):
        # Force UTF-8 on Windows to prevent cp1252 encoding errors
        if sys.platform == "win32":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
                sys.stderr.reconfigure(encoding="utf-8")
            except Exception:
                pass
        self.console = Console(theme=THEME, force_terminal=True)
        self._start_time = time.time()
        self._session_cost = 0.0
        self._tool_count = 0
        self._message_count = 0
    
    def show_welcome(self, model: str = "default", approval: str = "auto-edit", effort: str = "medium"):
        """Show welcome screen with status info."""
        from rich.columns import Columns
        
        # Build status bar items
        status_items = [
            f"[bold cyan]Model:[/bold cyan] {model}",
            f"[bold green]Approval:[/bold green] {approval}",
            f"[bold yellow]Effort:[/bold yellow] {effort}",
        ]
        status_text = " | ".join(status_items)
        
        self.console.print(Panel(
            "[bold blue]Dev[/bold blue] - Free 24/7 AI Coding Agent\n"
            f"[dim]{status_text}[/dim]\n"
            "[dim]Type your request. Use /help for commands.[/dim]",
            title="[bold]Dev[/bold]",
            border_style="blue",
        ))
    
    def show_help(self):
        """Show help screen."""
        table = Table(title="Commands", show_header=True)
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        
        commands = [
            ("/help", "Show this help"),
            ("/clear", "Clear screen"),
            ("/status", "Show session status"),
            ("/cost", "Show cost/token usage"),
            ("/undo", "Undo last edit"),
            ("/diff", "Show last diff"),
            ("/quit", "Exit"),
        ]
        
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        
        self.console.print(table)
    
    def show_status(self):
        """Show session status."""
        elapsed = time.time() - self._start_time
        
        table = Table(title="Session Status", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value")
        
        table.add_row("Duration", f"{elapsed:.0f}s")
        table.add_row("Messages", str(self._message_count))
        table.add_row("Tool calls", str(self._tool_count))
        table.add_row("Cost", f"${self._session_cost:.4f}")
        
        self.console.print(table)
    
    def show_thinking(self, message: str = "Thinking..."):
        """Show thinking indicator with animated dots."""
        self.console.print(f"  [bold blue]|[/bold blue] [dim]{message}[/dim]", end="\r")
    
    def show_tool_call(self, tool_name: str, args: dict):
        """Show tool call with formatted args."""
        # Format args nicely based on tool type
        args_str = str(args)[:120]
        if tool_name == "write_file" and isinstance(args, dict):
            path = args.get("path", "")
            content_len = len(args.get("content", ""))
            args_str = f"path={path} ({content_len} chars)"
        elif tool_name == "str_replace" and isinstance(args, dict):
            path = args.get("path", "")
            old = args.get("oldString", "")
            args_str = f"path={path} (replacing {len(old)} chars)"
        elif tool_name == "run_terminal_command" and isinstance(args, dict):
            args_str = f"{args.get('command', '')}"
        elif tool_name == "read_files" and isinstance(args, dict):
            paths = args.get("paths", [])
            if isinstance(paths, list):
                args_str = f"{len(paths)} file(s)"
        
        self.console.print(f"  [bold cyan]  -> {tool_name}[/bold cyan] [dim]{args_str}[/dim]")
        self._tool_count += 1
    
    def show_tool_result(self, tool_name: str, result: Any):
        """Show tool result with formatted output."""
        if isinstance(result, dict) and "error" in result:
            self.console.print(f"  [red]  <- {tool_name}: ERROR {result['error'][:150]}[/red]")
        elif isinstance(result, dict) and "blocked" in result:
            self.console.print(f"  [yellow]  <- {tool_name}: BLOCKED - {result['blocked'][:150]}[/yellow]")
        elif isinstance(result, dict) and result.get("success"):
            # Show success with relevant details
            details = []
            if "lines" in result:
                details.append(f"{result['lines']} lines")
            if "bytes" in result:
                details.append(f"{result['bytes']} bytes")
            detail_str = f" ({', '.join(details)})" if details else ""
            self.console.print(f"  [green]  <- {tool_name}: OK{detail_str}[/green]")
        else:
            result_str = str(result)[:200] if result else "ok"
            self.console.print(f"  [dim]  <- {tool_name}: {result_str}[/dim]")
    
    def show_error(self, message: str):
        """Show error message."""
        self.console.print(f"[error]Error: {message}[/error]")
    
    def show_streaming_start(self):
        """Show streaming start."""
        self.console.print("Dev: ", end="")
    
    def show_streaming_chunk(self, chunk: str):
        """Show streaming chunk."""
        self.console.print(chunk, end="", highlight=False)
    
    def show_streaming_end(self):
        """End streaming display."""
        self.console.print()
    
    def show_token_usage(self, tokens_in: int, tokens_out: int):
        """Show token usage."""
        self.console.print(
            f"[dim]Tokens: {tokens_in:,} in / {tokens_out:,} out[/dim]"
        )
    
    def show_cost(self, cost: float):
        """Show cost."""
        self._session_cost += cost
        if cost > 0:
            self.console.print(f"[dim]Cost: ${cost:.4f} (total: ${self._session_cost:.4f})[/dim]")
    
    def render_markdown(self, text: str):
        """Render text as markdown."""
        try:
            self.console.print(Markdown(text))
        except Exception:
            self.console.print(text)


class StreamingDisplay:
    """
    Live streaming display for agent responses.
    
    Streams token-by-token using console.out for immediate feedback.
    Handles Unicode encoding issues on Windows terminals.
    """
    
    def __init__(self, tui: DevTUI):
        self.tui = tui
        self._buffer = ""
        self._started = False
    
    def start(self):
        """Start streaming display with agent label."""
        self._buffer = ""
        self._started = True
        try:
            self.tui.console.out("\nDev: ", end="", highlight=False)
        except Exception:
            pass
    
    def update(self, chunk: str):
        """Update with a new chunk — stream token by token with flush."""
        if not self._started:
            self.start()
        self._buffer += chunk
        try:
            self.tui.console.out(chunk, end="", highlight=False, flush=True)
        except UnicodeEncodeError:
            safe = chunk.encode("ascii", errors="replace").decode("ascii")
            self.tui.console.out(safe, end="", highlight=False, flush=True)
        except Exception:
            pass
    
    def end(self):
        """End streaming display with newline."""
        if self._started:
            try:
                self.tui.console.out("", end="\n", flush=True)
            except Exception:
                pass
        self._buffer = ""
        self._started = False
    
    def get_buffer(self) -> str:
        """Get the full accumulated buffer."""
        return self._buffer
        self.tui.console.print()  # Final newline
