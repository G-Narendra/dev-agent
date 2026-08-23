"""
Diff Viewer — Colored Diff Display with Syntax Highlighting

Provides beautiful diff display for the terminal.
"""
import os
import difflib
from typing import Optional


class DiffViewer:
    """
    Display colored diffs in the terminal.
    
    Features:
    1. Unified diff format
    2. Side-by-side diff
    3. Syntax highlighting for common languages
    4. File stats
    """
    
    COLORS = {
        'green': '\033[32m',
        'red': '\033[31m',
        'cyan': '\033[36m',
        'yellow': '\033[33m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        'reset': '\033[0m',
    }
    
    def show_unified(self, old: str, new: str, 
                     old_name: str = "a/file", new_name: str = "b/file") -> str:
        """Show unified diff."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=old_name,
            tofile=new_name,
            lineterm="",
        ))
        
        if not diff:
            return "No changes"
        
        colored = []
        for line in diff:
            if line.startswith('+++') or line.startswith('---'):
                colored.append(f"{self.COLORS['bold']}{line}{self.COLORS['reset']}")
            elif line.startswith('@@'):
                colored.append(f"{self.COLORS['cyan']}{line}{self.COLORS['reset']}")
            elif line.startswith('+'):
                colored.append(f"{self.COLORS['green']}{line}{self.COLORS['reset']}")
            elif line.startswith('-'):
                colored.append(f"{self.COLORS['red']}{line}{self.COLORS['reset']}")
            else:
                colored.append(line)
        
        return '\n'.join(colored)
    
    def show_stats(self, old: str, new: str) -> str:
        """Show diff statistics."""
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        
        added = len(new_lines) - len(old_lines)
        changes = sum(1 for a, b in zip(old_lines, new_lines) if a != b)
        
        stats = []
        if added > 0:
            stats.append(f"+{added}")
        elif added < 0:
            stats.append(f"{added}")
        
        if changes:
            stats.append(f"~{changes}")
        
        return f"Changes: {', '.join(stats) if stats else 'No changes'}"
    
    def show_file_diff(self, file_path: str, new_content: str) -> str:
        """Show diff for a file."""
        if not os.path.exists(file_path):
            return f"\033[32m+ NEW FILE: {file_path}\033[0m"
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
            return self.show_unified(old_content, new_content, file_path, file_path)
        except Exception:
            return f"Cannot read {file_path}"
