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
import time
from typing import AsyncIterator, Optional

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
        import sys
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
            title="🤖 Welcome",
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
            ("/files", "List files in chat"),
            ("/drop <file>", "Remove file from chat"),
            ("/add <file>", "Add file to chat"),
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
        self._tool_count += 1
        
        # Format args nicely
        if len(str(args)) > 100:
            args_str = str(args)[:100] + "..."
        else:
            args_str = str(args)
        
        self.console.print(
            f"  [tool]🔧 {tool_name}[/tool] [dim]{args_str}[/dim]"
        )
    
    def show_tool_result(self, result: dict, success: bool = True):
        """Show tool result."""
        if success:
            if "diff" in result and result["diff"]:
                self.console.print(f"  [success]✓[/success]")
                self.console.print(f"  [dim]{result['diff'][:500]}[/dim]")
            elif "content" in result and len(str(result["content"])) > 200:
                self.console.print(f"  [success]✓[/success] [dim]{len(str(result['content']))} chars[/dim]")
            else:
                self.console.print(f"  [success]✓[/success]")
        else:
            error = result.get("error", "Unknown error")
            self.console.print(f"  [error]✗ {error[:200]}[/error]")
    
    def show_response(self, content: str):
        """Show agent response."""
        self._message_count += 1
        self.console.print()
        self.console.print(Panel(
            Markdown(content),
            title="[agent]Dev[/agent]",
            border_style="blue",
            padding=(0, 1),
        ))
    
    def show_error(self, message: str):
        """Show error."""
        self.console.print(f"[error]Error: {message}[/error]")
    
    def show_warning(self, message: str):
        """Show warning."""
        self.console.print(f"[warning]Warning: {message}[/warning]")
    
    def show_streaming_start(self):
        """Start streaming display."""
        self.console.print()
        self.console.print("[agent]Dev:[/agent] ", end="")
    
    def show_streaming_chunk(self, chunk: str):
        """Show streaming chunk."""
        self.console.print(chunk, end="", highlight=False)
    
    def show_streaming_end(self):
        """End streaming display."""
        self.console.print()
    
    def get_input(self) -> str | None:
        """Get user input."""
        try:
            user_input = self.console.input("[user]You:[/user] ")
            return user_input.strip() if user_input.strip() else None
        except (EOFError, KeyboardInterrupt):
            return None
    
    def show_quit(self):
        """Show quit message."""
        self.console.print("[dim]Goodbye![/dim]")
    
    def clear(self):
        """Clear screen."""
        self.console.clear()
    
    def show_model_info(self, model: str, provider: str):
        """Show model information."""
        self.console.print(
            f"[dim]Model: {model} | Provider: {provider}[/dim]"
        )
    
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


class StreamingDisplay:
    """
    Live streaming display for agent responses.
    
    From Freebuff's streaming pattern.
    """
    
    def __init__(self, tui: DevTUI):
        self.tui = tui
        self._buffer = ""
        self._live: Optional[Live] = None
    
    def start(self):
        """Start streaming display."""
        self.tui.show_streaming_start()
        self._buffer = ""
    
    def update(self, chunk: str):
        """Update with a new chunk with live panel."""
        self._buffer += chunk
        from rich.text import Text as RichText
        if self._live is None:
            self._live = Live(RichText(self._buffer), console=self.tui.console, refresh_per_second=10, transient=True)
            self._live.start()
        else:
            self._live.update(RichText(self._buffer))
    
    def end(self):
        """End streaming display."""
        if self._live is not None:
            self._live.stop()
            self._live = None
            # Print final buffered text (safe encoding for Windows)
            try:
                self.tui.console.print(self._buffer, highlight=False)
            except UnicodeEncodeError:
                safe = self._buffer.encode('ascii', errors='replace').decode('ascii')
                self.tui.console.print(safe, highlight=False)
        self._buffer = ""
