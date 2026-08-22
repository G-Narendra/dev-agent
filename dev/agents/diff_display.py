"""
Diff Display — Colored Diff Output and Git Integration

Provides:
1. Colored unified diff display
2. Auto-commit before edits
3. Undo via git reset
4. Diff preview before applying edits
"""
import os
import subprocess
import difflib
from typing import Optional


class DiffDisplay:
    """Display colored diffs and manage git integration."""
    
    # ANSI color codes
    COLORS = {
        'green': '\033[32m',
        'red': '\033[31m',
        'cyan': '\033[36m',
        'yellow': '\033[33m',
        'bold': '\033[1m',
        'reset': '\033[0m',
        'dim': '\033[2m',
    }
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def show_diff(self, old_content: str, new_content: str, 
                  file_path: str = "") -> str:
        """
        Show a colored unified diff.
        
        Returns colored diff string for terminal display.
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{file_path}" if file_path else "/dev/null",
            tofile=f"b/{file_path}" if file_path else "/dev/null",
            lineterm="",
        ))
        
        if not diff:
            return ""
        
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
    
    def show_file_diff(self, file_path: str, new_content: str) -> str:
        """Show diff for a file change."""
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return f"{self.COLORS['green']}+ NEW FILE: {file_path}{self.COLORS['reset']}"
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
            return self.show_diff(old_content, new_content, file_path)
        except Exception:
            return f"Cannot read {file_path} for diff"
    
    def auto_commit_before_edit(self, file_path: str) -> bool:
        """
        Auto-commit current state before making an edit.
        This enables undo via git reset.
        """
        try:
            # Stage the file
            subprocess.run(
                ["git", "add", file_path],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            
            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain", file_path],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if not status.stdout.strip():
                return True  # Nothing to commit, that's fine
            
            # Commit with auto message
            subprocess.run(
                ["git", "commit", "-m", f"auto: save {file_path} before edit",
                 "--allow-empty"],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            
            return True
        except Exception:
            return False
    
    def commit_after_edit(self, file_path: str, 
                          message: str = None) -> bool:
        """Commit after an edit."""
        try:
            subprocess.run(
                ["git", "add", file_path],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            
            if not message:
                message = f"edit: update {file_path}"
            
            subprocess.run(
                ["git", "commit", "-m", message, "--allow-empty"],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            
            return True
        except Exception:
            return False
    
    def undo_last_edit(self) -> str:
        """Undo the last edit via git reset."""
        try:
            result = subprocess.run(
                ["git", "reset", "--hard", "HEAD~1"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                return "Undid last edit"
            return f"Nothing to undo: {result.stderr}"
        except Exception as e:
            return f"Undo failed: {e}"
    
    def get_git_status(self) -> str:
        """Get formatted git status."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if not result.stdout.strip():
                return "Clean working tree"
            
            lines = []
            for line in result.stdout.strip().split('\n'):
                status = line[:2]
                file = line[3:]
                
                if status[0] == 'A':
                    lines.append(f"{self.COLORS['green']}+ {file}{self.COLORS['reset']}")
                elif status[0] == 'M':
                    lines.append(f"{self.COLORS['yellow']}~ {file}{self.COLORS['reset']}")
                elif status[0] == 'D':
                    lines.append(f"{self.COLORS['red']}- {file}{self.COLORS['reset']}")
                else:
                    lines.append(f"  {file}")
            
            return '\n'.join(lines)
        except Exception:
            return "Not a git repo"
    
    def get_recent_commits(self, count: int = 5) -> str:
        """Get recent git commits."""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{count}"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            return result.stdout.strip() or "No commits"
        except Exception:
            return "Not a git repo"
    
    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.project_path, path))
