"""
Sandbox tools for Dev.

Wraps the sandbox system as agent tools, following the same pattern
as Freebuff's tool system.
"""

from __future__ import annotations

from typing import Any

from .base import Tool


class SandboxedRunTool(Tool):
    """
    Execute a command in a sandboxed environment.
    
    This replaces the basic run_terminal_command with a sandboxed version
    that checks execution policies before running.
    """
    
    name = "sandboxed_run"
    description = "Execute a command with sandbox restrictions. Checks execution policies before running."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: project root)",
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Timeout in seconds",
            },
        },
        "required": ["command"],
    }
    
    def __init__(self, sandbox_manager: Any = None):
        self.sandbox = sandbox_manager
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        command = input_data["command"]
        cwd = input_data.get("cwd", project_path)
        timeout = input_data.get("timeout", 30)
        
        if not self.sandbox:
            # Fallback to basic execution
            import asyncio
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exitCode": proc.returncode,
            }
        
        result = await self.sandbox.execute(command, cwd=cwd, timeout=timeout)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.exit_code,
            "blocked": result.blocked,
            "blockReason": result.block_reason,
            "timedOut": result.timed_out,
        }


class SandboxStatusTool(Tool):
    """
    Get sandbox status and violations.
    
    Shows the current sandbox configuration and any violations.
    """
    
    name = "sandbox_status"
    description = "Get sandbox status, policy info, and violation log"
    parameters = {
        "type": "object",
        "properties": {},
    }
    
    def __init__(self, sandbox_manager: Any = None):
        self.sandbox = sandbox_manager
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        if not self.sandbox:
            return {"status": "no sandbox configured"}
        
        violations = self.sandbox.get_violations()
        
        return {
            "sandbox_type": self.sandbox.get_sandbox_type(),
            "project_path": self.sandbox.config.project_path,
            "read_only": self.sandbox.config.read_only,
            "violation_count": len(violations),
            "recent_violations": violations[-10:] if violations else [],
        }
__all__ = ["SandboxedRunTool", "SandboxStatusTool"]
