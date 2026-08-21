"""
Git Auto-Commit for Dev.

Automatically commits code changes with meaningful AI-generated messages.
Adapted from Aider's git integration.

Improvement #6: Git auto-commit with AI messages
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any, Optional


class AutoCommitter:
    """
    Auto-commits code changes with meaningful messages.
    
    From Aider's commit pattern:
    1. Check for changes
    2. Generate commit message
    3. Stage and commit
    """
    
    def __init__(self, project_path: str, provider: Any = None):
        self.project_path = project_path
        self.provider = provider
        self._last_commit_hash: str = ""
    
    async def auto_commit(self, edited_files: list[str] | None = None) -> dict:
        """
        Auto-commit changes.
        
        Returns commit hash or error.
        """
        # Check if we're in a git repo
        if not self._is_git_repo():
            return {"error": "Not a git repository"}
        
        # Check for detached HEAD — commits would be dangling
        if self._is_detached_head():
            return {"error": "Detached HEAD state. Cannot auto-commit. Switch to a branch first."}
        
        # Check for changes
        status = self._get_status()
        if not status.get("has_changes"):
            return {"message": "No changes to commit"}
        
        # Generate commit message
        message = await self._generate_commit_message(edited_files or status.get("changed_files", []))
        
        # Stage and commit
        result = await self._commit(message, status.get("staged_files", []))
        
        return result
    
    async def commit_specific(self, files: list[str], message: str | None = None) -> dict:
        """Commit specific files."""
        if not self._is_git_repo():
            return {"error": "Not a git repository"}
        
        # Stage files
        for f in files:
            await self._run_git(["add", f])
        
        # Generate message if not provided
        if not message:
            message = await self._generate_commit_message(files)
        
        # Commit
        return await self._commit(message)
    
    def _is_detached_head(self) -> bool:
        """Check if repo is in detached HEAD state."""
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "-q", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            return result.returncode != 0  # non-zero = detached
        except Exception:
            return False

    def _is_git_repo(self) -> bool:
        """Check if we're in a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.project_path,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _get_status(self) -> dict:
        """Get git status."""
        try:
            # Get status
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            lines = proc.stdout.strip().splitlines()
            
            changed_files = []
            staged_files = []
            
            for line in lines:
                if not line:
                    continue
                status = line[:2]
                filename = line[3:].strip()
                
                changed_files.append(filename)
                
                # Staged if first char is not space or ?
                if status[0] not in (" ", "?"):
                    staged_files.append(filename)
            
            # Get diff for unstaged changes
            diff = ""
            if changed_files:
                proc = subprocess.run(
                    ["git", "diff", "--stat"],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                diff = proc.stdout
            
            return {
                "has_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "staged_files": staged_files,
                "diff_stat": diff,
            }
        except Exception as e:
            return {"error": str(e), "has_changes": False}
    
    async def _generate_commit_message(self, files: list[str]) -> str:
        """Generate a commit message using the LLM."""
        if not self.provider:
            return f"Update {len(files)} file(s)"
        
        try:
            # Get diff
            proc = subprocess.run(
                ["git", "diff", "--cached"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            diff = proc.stdout[:3000]  # Limit diff size
            
            if not diff:
                proc = subprocess.run(
                    ["git", "diff"],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                diff = proc.stdout[:3000]
            
            # Generate message with LLM
            messages = [
                {"role": "system", "content": (
                    "You are a git commit message generator. "
                    "Generate a concise, descriptive commit message for the following changes. "
                    "Use conventional commit format (feat:, fix:, refactor:, etc.). "
                    "Keep it under 72 characters. Output ONLY the commit message, nothing else."
                )},
                {"role": "user", "content": f"Files changed: {', '.join(files)}\n\nDiff:\n{diff}"},
            ]
            
            response = await self.provider.chat_completion(
                messages=messages,
                model="nvidia/llama-3.1-8b-instruct",  # Use fast model
                max_tokens=100,
                temperature=0.3,
            )
            
            message = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return message.strip() or f"Update {len(files)} file(s)"
        except Exception:
            return f"Update {len(files)} file(s)"
    
    async def _commit(self, message: str, staged_files: list[str] | None = None) -> dict:
        """Stage and commit changes."""
        try:
            # Only stage specific files if provided, otherwise stage only tracked modified files
            if staged_files:
                for f in staged_files:
                    await self._run_git(["add", f])
            else:
                # Only add tracked (modified) files, not untracked new files
                # This prevents accidentally committing .env, secrets, etc.
                status = await self._run_git(["diff", "--name-only"])
                if status:
                    for f in status.strip().split("\n"):
                        if f:
                            await self._run_git(["add", f])
            
            # Commit
            result = await self._run_git(["commit", "-m", message])
            
            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            self._last_commit_hash = hash_result.stdout.strip()
            
            return {
                "success": True,
                "commit_hash": self._last_commit_hash,
                "message": message,
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _run_git(self, args: list[str]) -> str:
        """Run a git command with lock file retry."""
        for attempt in range(3):
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=self.project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            result = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            if "index.lock" in err:
                await asyncio.sleep(1)
                continue
            return result
        return result
