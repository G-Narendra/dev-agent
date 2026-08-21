"""
Git Auto-Commit for Dev.

From Aider's repo.py auto-commit pattern.
Automatically commits changes with meaningful messages.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional


class GitAutoCommit:
    """
    Automatically commits changes after edits.
    
    From Aider's auto_commit pattern.
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._last_commit_hash: str = ""
    
    def is_git_repo(self) -> bool:
        """Check if we're in a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                cwd=self.project_path,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_diff(self, files: list[str] | None = None) -> str:
        """Get the current diff."""
        cmd = ["git", "diff"]
        if files:
            cmd.extend(files)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=10,
            )
            return result.stdout
        except Exception:
            return ""
    
    def get_staged_diff(self) -> str:
        """Get staged diff."""
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=10,
            )
            return result.stdout
        except Exception:
            return ""
    
    def get_status(self) -> dict:
        """Get git status."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=10,
            )
            
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            modified = []
            untracked = []
            
            for line in lines:
                if len(line) >= 3:
                    status = line[:2].strip()
                    file = line[3:].strip()
                    if status in ("M", "MM", "AM"):
                        modified.append(file)
                    elif status == "??":
                        untracked.append(file)
            
            return {
                "modified": modified,
                "untracked": untracked,
                "clean": len(lines) == 0,
            }
        except Exception:
            return {"modified": [], "untracked": [], "clean": True}
    
    def stage_files(self, files: list[str]) -> bool:
        """Stage files for commit."""
        try:
            subprocess.run(
                ["git", "add"] + files,
                capture_output=True,
                cwd=self.project_path,
                timeout=10,
            )
            return True
        except Exception:
            return False
    
    def commit(self, message: str, files: list[str] | None = None) -> str | None:
        """
        Commit changes with a message.
        
        From Aider's commit pattern.
        """
        if not self.is_git_repo():
            return None
        
        # Stage files
        if files:
            self.stage_files(files)
        else:
            # Stage all modified files
            status = self.get_status()
            all_files = status["modified"] + status["untracked"]
            if all_files:
                self.stage_files(all_files)
        
        # Check if there's anything to commit
        staged = self.get_staged_diff()
        if not staged:
            return None
        
        # Commit
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=10,
            )
            
            if result.returncode == 0:
                # Get commit hash
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_path,
                    timeout=5,
                )
                self._last_commit_hash = hash_result.stdout.strip()
                return self._last_commit_hash
            
            return None
        except Exception:
            return None
    
    def generate_commit_message(self, files: list[str], diff: str) -> str:
        """
        Generate a meaningful commit message.
        
        From Aider's commit message generation.
        """
        # Simple heuristic-based message generation
        if not files:
            return "Update files"
        
        if len(files) == 1:
            file = files[0]
            ext = os.path.splitext(file)[1].lower()
            
            # Language-specific prefixes
            prefixes = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".tsx": "React",
                ".jsx": "React",
                ".rs": "Rust",
                ".go": "Go",
                ".java": "Java",
                ".rb": "Ruby",
                ".php": "PHP",
                ".html": "HTML",
                ".css": "CSS",
                ".scss": "SCSS",
                ".json": "JSON",
                ".yaml": "Config",
                ".yml": "Config",
                ".md": "Docs",
                ".sh": "Script",
            }
            
            prefix = prefixes.get(ext, "")
            name = os.path.basename(file)
            
            if prefix:
                return f"{prefix}: update {name}"
            else:
                return f"Update {name}"
        else:
            # Multiple files
            return f"Update {len(files)} files"
    
    def auto_commit_after_edit(self, files: list[str]) -> str | None:
        """
        Auto-commit after editing files.
        
        Main entry point for auto-commit.
        """
        if not self.is_git_repo():
            return None
        
        # Generate message
        diff = self.get_diff(files)
        message = self.generate_commit_message(files, diff)
        
        # Commit
        return self.commit(message, files)
    
    def undo_last_commit(self) -> bool:
        """Undo the last commit."""
        try:
            subprocess.run(
                ["git", "reset", "--soft", "HEAD~1"],
                capture_output=True,
                cwd=self.project_path,
                timeout=10,
            )
            return True
        except Exception:
            return False
    
    def get_log(self, count: int = 10) -> list[dict]:
        """Get recent commits."""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{count}"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=10,
            )
            
            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1],
                        })
            
            return commits
        except Exception:
            return []
