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
    
    def show_welcome(self):
        """Show welcome screen."""
        self.console.print(Panel(
            "[bold blue]Dev[/bold blue] - Free 24/7 AI Coding Agent\n"
            "[dim]Powered by NVIDIA NIMs free tier (no local GPU required)[/dim]\n\n"
            "Type your request. Use /help for commands.",
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
        """Show thinking indicator."""
        self.console.print(f"[thinking]{message}[/thinking]", end="")
    
    def show_tool_call(self, tool_name: str, args: dict):
        """Show tool call."""
        self.console.print(f"  [bold cyan]  -> {tool_name}[/bold cyan] [dim]{str(args)[:120]}[/dim]")
        self._tool_count += 1
    
    def show_tool_result(self, tool_name: str, result: Any):
        """Show tool result."""
        if isinstance(result, dict) and "error" in result:
            self.console.print(f"  [red]  <- {tool_name}: ERROR {result['error'][:100]}[/red]")
        elif isinstance(result, dict) and "blocked" in result:
            self.console.print(f"  [yellow]  <- {tool_name}: BLOCKED - {result['blocked'][:100]}[/yellow]")
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
    
    Uses Rich Live for real-time token-by-token display.
    """
    
    def __init__(self, tui: DevTUI):
        self.tui = tui
        self._buffer = ""
        self._live: Optional[Live] = None
    
    def start(self):
        """Start streaming display."""
        self._buffer = ""
        self.tui.console.print("Dev: ", end="", highlight=False)
    
    def update(self, chunk: str):
        """Update with a new chunk — stream token by token."""
        self._buffer += chunk
        # Print each chunk immediately for real streaming feel
        try:
            self.tui.console.out(chunk, end="", highlight=False)
        except UnicodeEncodeError:
            safe = chunk.encode("ascii", errors="replace").decode("ascii")
            self.tui.console.out(safe, end="", highlight=False)
    
    def end(self):
        """End streaming display."""
        self._buffer = ""
        self.tui.console.print()  # Final newline
