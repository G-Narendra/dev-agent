"""
Progress Indicators — Spinners, Progress Bars, Status Display

Provides beautiful terminal feedback during long operations.
"""
import sys
import time
import threading
from typing import Optional


class Spinner:
    """Animated spinner for terminal."""
    
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, message: str = "", color: str = "\033[36m"):
        self.message = message
        self.color = color
        self.reset = "\033[0m"
        self.frame = 0
        self.running = False
        self.thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the spinner."""
        self.running = True
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()
    
    def _animate(self):
        while self.running:
            frame = self.FRAMES[self.frame % len(self.FRAMES)]
            sys.stdout.write(f"\r{self.color}{frame}{self.reset} {self.message}")
            sys.stdout.flush()
            self.frame += 1
            time.sleep(0.1)
    
    def update(self, message: str):
        """Update the spinner message."""
        self.message = message
    
    def stop(self, message: str = None):
        """Stop the spinner."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        sys.stdout.write(f"\r\033[K")
        if message:
            sys.stdout.write(f"\033[32m✓{self.reset} {message}\n")
        sys.stdout.flush()
    
    def fail(self, message: str):
        """Stop with failure."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        sys.stdout.write(f"\r\033[K")
        sys.stdout.write(f"\033[31m✗{self.reset} {message}\n")
        sys.stdout.flush()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()


class ProgressBar:
    """Progress bar for terminal."""
    
    def __init__(self, total: int, message: str = "", width: int = 30):
        self.total = total
        self.current = 0
        self.message = message
        self.width = width
    
    def update(self, n: int = 1):
        """Update progress by n steps."""
        self.current += n
        self._display()
    
    def _display(self):
        """Display the progress bar."""
        if self.total == 0:
            return
        
        pct = self.current / self.total
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        
        sys.stdout.write(f"\r\033[36m{bar}\033[0m {pct*100:.0f}% {self.message}")
        sys.stdout.flush()
    
    def complete(self, message: str = "Done"):
        """Mark as complete."""
        self.current = self.total
        self._display()
        sys.stdout.write(f"\r\033[K\033[32m✓ {message}\033[0m\n")
        sys.stdout.flush()


class StepIndicator:
    """Multi-step progress indicator."""
    
    def __init__(self, steps: list[str]):
        self.steps = steps
        self.current = 0
        self.results = []
    
    def start(self, step_num: int):
        """Start a step."""
        self.current = step_num
        if step_num <= len(self.steps):
            name = self.steps[step_num - 1]
            sys.stdout.write(f"\n\033[36m[{step_num}/{len(self.steps)}]\033[0m {name}...")
            sys.stdout.flush()
    
    def complete(self, step_num: int, success: bool = True):
        """Complete a step."""
        if step_num <= len(self.steps):
            icon = "\033[32m✓\033[0m" if success else "\033[31m✗\033[0m"
            sys.stdout.write(f"\r\033[K{icon} [{step_num}/{len(self.steps)}] {self.steps[step_num - 1]}\n")
            sys.stdout.flush()
            self.results.append(success)
    
    def summary(self):
        """Print summary."""
        passed = sum(1 for r in self.results if r)
        total = len(self.results)
        print(f"\n{'='*40}")
        print(f"Results: \033[32m{passed} passed\033[0m, \033[31m{total - passed} failed\033[0m")


class StatusDisplay:
    """Live status display for agent operations."""
    
    def __init__(self):
        self.lines = []
        self.token_sent = 0
        self.token_received = 0
        self.cost = 0.0
    
    def add_line(self, line: str):
        """Add a status line."""
        self.lines.append(line)
        if len(self.lines) > 5:
            self.lines = self.lines[-5:]
        self._display()
    
    def update_tokens(self, sent: int, received: int):
        """Update token counts."""
        self.token_sent = sent
        self.token_received = received
    
    def _display(self):
        """Display status."""
        # Move up and overwrite
        sys.stdout.write(f"\033[{len(self.lines)}A")
        for line in self.lines:
            sys.stdout.write(f"\033[K{line}\n")
        sys.stdout.flush()
