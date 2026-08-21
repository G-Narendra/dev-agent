"""
Hook system for pre/post tool execution.

Like Claude Code's hooks:
- Run shell commands before/after tool use
- Auto-format after file edits
- Auto-lint before commits
- Custom validation on any action
"""
from __future__ import annotations
import os
import json
import subprocess
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime
from enum import Enum


class HookEvent(str, Enum):
    PRE_TOOL_USE = "pre_tool_use"      # Before a tool is executed
    POST_TOOL_USE = "post_tool_use"    # After a tool is executed
    PRE_FILE_EDIT = "pre_file_edit"    # Before file is modified
    POST_FILE_EDIT = "post_file_edit"  # After file is modified
    PRE_COMMIT = "pre_commit"          # Before git commit
    POST_COMMIT = "post_commit"        # After git commit
    SESSION_START = "session_start"    # When session begins
    SESSION_END = "session_end"        # When session ends


@dataclass
class Hook:
    """A hook configuration."""
    event: HookEvent
    command: str
    description: str = ""
    timeout_seconds: int = 30
    enabled: bool = True
    pattern: Optional[str] = None  # Only run for matching tool names
    working_dir: Optional[str] = None


@dataclass
class HookResult:
    """Result of running a hook."""
    hook: Hook
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    success: bool = True
    skipped: bool = False


class HookManager:
    """Manages pre/post tool execution hooks."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.hooks: list[Hook] = []
        self._config_path = os.path.join(self.project_root, ".dev", "hooks.json")
        self._load_config()

    def _load_config(self):
        """Load hooks from disk."""
        if os.path.exists(self._config_path):
            with open(self._config_path) as f:
                data = json.load(f)
            for h_data in data.get("hooks", []):
                hook = Hook(
                    event=HookEvent(h_data["event"]),
                    command=h_data["command"],
                    description=h_data.get("description", ""),
                    timeout_seconds=h_data.get("timeout_seconds", 30),
                    enabled=h_data.get("enabled", True),
                    pattern=h_data.get("pattern"),
                )
                self.hooks.append(hook)

    def _save_config(self):
        """Save hooks to disk."""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        data = {
            "hooks": [
                {
                    "event": h.event.value,
                    "command": h.command,
                    "description": h.description,
                    "timeout_seconds": h.timeout_seconds,
                    "enabled": h.enabled,
                    "pattern": h.pattern,
                }
                for h in self.hooks
            ]
        }
        with open(self._config_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_hook(self, event: HookEvent, command: str, description: str = "",
                 pattern: str = None, timeout: int = 30) -> Hook:
        """Add a hook."""
        hook = Hook(
            event=event,
            command=command,
            description=description,
            pattern=pattern,
            timeout_seconds=timeout,
        )
        self.hooks.append(hook)
        self._save_config()
        return hook

    def remove_hook(self, index: int) -> bool:
        """Remove a hook by index."""
        if 0 <= index < len(self.hooks):
            self.hooks.pop(index)
            self._save_config()
            return True
        return False

    def get_hooks(self, event: HookEvent, tool_name: str = None) -> list[Hook]:
        """Get hooks matching an event and optional tool name."""
        result = []
        for hook in self.hooks:
            if not hook.enabled or hook.event != event:
                continue
            if hook.pattern and tool_name:
                if not self._match_pattern(hook.pattern, tool_name):
                    continue
            elif hook.pattern and not tool_name:
                continue
            result.append(hook)
        return result

    def _match_pattern(self, pattern: str, tool_name: str) -> bool:
        """Simple pattern matching for tool names."""
        import fnmatch
        return fnmatch.fnmatch(tool_name, pattern)

    async def run_hooks(self, event: HookEvent, tool_name: str = None,
                        context: dict = None) -> list[HookResult]:
        """Run all hooks for an event."""
        hooks = self.get_hooks(event, tool_name)
        results = []
        
        for hook in hooks:
            result = await self._run_hook(hook, context)
            results.append(result)
            
            # If a pre-hook fails, stop execution
            if event.value.startswith("pre_") and not result.success:
                break
        
        return results

    async def _run_hook(self, hook: Hook, context: dict = None) -> HookResult:
        """Run a single hook."""
        import time
        start = time.time()
        
        # Substitute variables in command
        cmd = hook.command
        if context:
            cmd = cmd.replace("{file}", context.get("file", ""))
            cmd = cmd.replace("{tool}", context.get("tool", ""))
            cmd = cmd.replace("{project}", self.project_root)
        
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=hook.working_dir or self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=hook.timeout_seconds,
            )
            
            duration_ms = int((time.time() - start) * 1000)
            return HookResult(
                hook=hook,
                exit_code=proc.returncode or 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                duration_ms=duration_ms,
                success=(proc.returncode == 0),
            )
        except asyncio.TimeoutError:
            return HookResult(
                hook=hook,
                exit_code=-1,
                stdout="",
                stderr=f"Hook timed out after {hook.timeout_seconds}s",
                duration_ms=hook.timeout_seconds * 1000,
                success=False,
            )
        except Exception as e:
            return HookResult(
                hook=hook,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.time() - start) * 1000),
                success=False,
            )

    def list_hooks(self) -> list[dict]:
        """List all hooks."""
        return [
            {
                "index": i,
                "event": h.event.value,
                "command": h.command,
                "description": h.description,
                "enabled": h.enabled,
                "pattern": h.pattern,
            }
            for i, h in enumerate(self.hooks)
        ]

    def enable_hook(self, index: int) -> bool:
        """Enable a hook."""
        if 0 <= index < len(self.hooks):
            self.hooks[index].enabled = True
            self._save_config()
            return True
        return False

    def disable_hook(self, index: int) -> bool:
        """Disable a hook."""
        if 0 <= index < len(self.hooks):
            self.hooks[index].enabled = False
            self._save_config()
            return True
        return False

    def setup_defaults(self):
        """Set up default hooks for common workflows."""
        self.add_hook(
            HookEvent.POST_FILE_EDIT,
            "echo '[hook] File edited: {file}'",
            description="Log file edits",
        )
        self.add_hook(
            HookEvent.PRE_COMMIT,
            "echo '[hook] About to commit'",
            description="Pre-commit notification",
        )
