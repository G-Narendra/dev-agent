"""
Streaming Display — Real Token-by-Token Terminal Output

Provides beautiful streaming output with:
1. Token-by-token display
2. Thinking indicators
3. Tool call visualization
4. Status bar
"""
import sys
import time
from typing import Optional


class StreamingDisplay:
    """
    Real-time streaming display for terminal.
    
    Shows:
    - Token-by-token text output
    - Thinking animation
    - Tool call status
    - Token counter
    """
    
    COLORS = {
        'cyan': '\033[36m',
        'green': '\033[32m',
        'red': '\033[31m',
        'yellow': '\033[33m',
        'dim': '\033[2m',
        'bold': '\033[1m',
        'reset': '\033[0m',
    }
    
    THINK_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self):
        self.output = []
        self.thinking = False
        self.frame = 0
        self.tokens_sent = 0
        self.tokens_received = 0
        self.current_line = ""
    
    def start_thinking(self):
        """Show thinking indicator."""
        self.thinking = True
        sys.stdout.write(f"\r{self.COLORS['cyan']}⠋{self.COLORS['reset']} Thinking...")
        sys.stdout.flush()
    
    def stop_thinking(self):
        """Hide thinking indicator."""
        self.thinking = False
        sys.stdout.write(f"\r\033[K")
        sys.stdout.flush()
    
    def on_text(self, chunk: str):
        """Handle streaming text chunk."""
        if self.thinking:
            self.stop_thinking()
        
        # Print chunk character by character for effect
        for char in chunk:
            sys.stdout.write(char)
            sys.stdout.flush()
            self.current_line += char
        
        self.tokens_received += 1
    
    def on_tool_call(self, name: str, args: dict):
        """Display tool call."""
        sys.stdout.write(f"\n{self.COLORS['yellow']}  → {name}{self.COLORS['reset']}")
        if args:
            # Show abbreviated args
            arg_str = str(args)[:100]
            sys.stdout.write(f" {self.COLORS['dim']}{arg_str}...{self.COLORS['reset']}")
        sys.stdout.flush()
    
    def on_tool_result(self, name: str, result: dict):
        """Display tool result."""
        success = result.get("success", False) or not result.get("error")
        icon = f"{self.COLORS['green']}✓{self.COLORS['reset']}" if success else f"{self.COLORS['red']}✗{self.COLORS['reset']}"
        sys.stdout.write(f" {icon}\n")
        sys.stdout.flush()
    
    def update_status(self, tokens_sent: int, tokens_received: int):
        """Update status bar."""
        self.tokens_sent = tokens_sent
        self.tokens_received = tokens_received
    
    def show_status_bar(self):
        """Display status bar."""
        sys.stdout.write(f"\r\033[K")
        sys.stdout.write(
            f"{self.COLORS['dim']}Tokens: {self.tokens_sent:,} sent + "
            f"{self.tokens_received:,} received{self.COLORS['reset']}"
        )
        sys.stdout.flush()
    
    def newline(self):
        """Print newline."""
        sys.stdout.write("\n")
        sys.stdout.flush()
    
    def clear_line(self):
        """Clear current line."""
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


class TokenCounter:
    """Count tokens in real-time."""
    
    def __init__(self):
        self.sent = 0
        self.received = 0
        self.cost = 0.0
    
    def add_sent(self, count: int = 1):
        self.sent += count
    
    def add_received(self, count: int = 1):
        self.received += count
    
    def get_total(self) -> int:
        return self.sent + self.received
    
    def format(self) -> str:
        return f"{self.sent:,} sent + {self.received:,} received = {self.get_total():,} total"
