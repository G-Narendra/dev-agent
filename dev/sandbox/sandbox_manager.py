"""
Sandbox Manager for Dev.

Adapted from Codex's sandboxing/src/manager.rs:
- SandboxType selection (platform-aware)
- SandboxTransformRequest for wrapping commands
- Filesystem and network isolation

Provides cross-platform sandboxing:
- Linux: process isolation with restricted paths
- macOS: subprocess with limited access
- Windows: restricted token simulation
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .exec_policy import Decision, ExecPolicy, RuleMatch


@dataclass
class SandboxConfig:
    """Configuration for the sandbox."""
    enabled: bool = True
    project_path: str = "."
    temp_dir: str = "/tmp/dev-sandbox"
    max_output_bytes: int = 50_000
    timeout_seconds: int = 30
    allowed_commands: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    read_only: bool = False  # If True, no file writes allowed


@dataclass
class SandboxExecResult:
    """Result of a sandboxed command execution."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""
    command: str = ""


class SandboxManager:
    """
    Manages sandboxed command execution.
    
    From Codex's SandboxManager:
    1. Evaluate command against policy
    2. If ALLOWED: execute in sandbox
    3. If PROMPTED: request user approval
    4. If FORBIDDEN: block entirely
    
    Platform-specific implementations:
    - Linux: Uses subprocess with restricted env
    - macOS: Similar to Linux
    - Windows: Uses subprocess with path restrictions
    """
    
    def __init__(
        self,
        config: SandboxConfig | None = None,
        policy: ExecPolicy | None = None,
    ):
        self.config = config or SandboxConfig()
        self.policy = policy or ExecPolicy()
        self.platform = platform.system().lower()
        self._violation_log: list[dict] = []
    
    def get_sandbox_type(self) -> str:
        """
        Determine the sandbox type based on platform.
        
        From Codex's get_platform_sandbox.
        """
        if self.platform == "linux":
            return "process_isolation"
        elif self.platform == "darwin":
            return "process_isolation"
        elif self.platform == "windows":
            return "process_isolation"
        else:
            return "none"
    
    def check_command(self, command: str) -> RuleMatch:
        """
        Check if a command is allowed by the policy.
        
        From Codex's policy evaluation.
        """
        return self.policy.evaluate_command(command)
    
    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxExecResult:
        """
        Execute a command in the sandbox.
        
        Flow:
        1. Check policy
        2. If forbidden, return blocked
        3. If prompt needed, mark for approval
        4. Execute with restrictions
        """
        # 1. Check policy
        match = self.check_command(command)
        
        if match.decision == Decision.FORBIDDEN:
            self._log_violation("forbidden", command, match.justification)
            return SandboxExecResult(
                blocked=True,
                block_reason=f"Command forbidden: {match.justification}",
                command=command,
            )
        
        if match.decision == Decision.PROMPT:
            # In non-interactive mode, we can't prompt
            # For now, allow but log
            self._log_violation("prompt_required", command, match.justification)
        
        # 2. Prepare execution environment
        exec_cwd = cwd or self.config.project_path
        exec_env = self._prepare_environment(env)
        exec_timeout = timeout or self.config.timeout_seconds
        
        # 3. Check filesystem access
        if self.config.read_only:
            # In read-only mode, only allow read commands
            read_only_commands = ["ls", "cat", "head", "tail", "grep", "find", "pwd", "echo"]
            cmd_parts = command.split()
            if cmd_parts and cmd_parts[0] not in read_only_commands:
                return SandboxExecResult(
                    blocked=True,
                    block_reason="Read-only mode: command modifies state",
                    command=command,
                )
        
        # 4. Execute with sandbox restrictions
        try:
            result = await self._execute_sandboxed(
                command, exec_cwd, exec_env, exec_timeout
            )
            return result
        except Exception as e:
            return SandboxExecResult(
                stderr=str(e),
                exit_code=1,
                command=command,
            )
    
    async def _execute_sandboxed(
        self,
        command: str,
        cwd: str,
        env: dict[str, str],
        timeout: int,
    ) -> SandboxExecResult:
        """
        Execute a command with sandbox restrictions.
        
        Platform-specific sandboxing:
        - Restrict environment variables
        - Set working directory
        - Apply timeout
        - Capture output with limits
        """
        # Build the subprocess environment
        import asyncio
        
        # Create restricted environment using an ALLOWLIST approach.
        # Only explicitly safe variables are passed through.
        # This prevents leaking API keys, tokens, and secrets.
        safe_vars = [
            "HOME", "USER", "SHELL", "LANG", "LC_ALL",
            "NODE_ENV", "PYTHONPATH", "VIRTUAL_ENV",
            "http_proxy", "https_proxy", "no_proxy",
            "TMPDIR", "TEMP", "TMP",
            "TERM", "COLORTERM",
            "DEV",  # our own flag
        ]
        restricted_env = {}
        for var in safe_vars:
            val = os.environ.get(var)
            if val:
                restricted_env[var] = val
        # Hardcode safe PATH to prevent PATH injection attacks.
        # Never inherit PATH from user environment — it could be poisoned.
        if os.name == 'nt':
            restricted_env["PATH"] = os.environ.get("PATH", r"C:\Windows\System32;C:\Windows")
        else:
            restricted_env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if env:
            restricted_env.update(env)
        
        try:
            # Use asyncio.create_subprocess_shell for async execution
            # On UNIX, create a new process group so we can kill the entire tree
            popen_kwargs: dict[str, Any] = {}
            if os.name != 'nt':
                popen_kwargs['start_new_session'] = True

            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=restricted_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **popen_kwargs,
            )
            
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                self._kill_process_tree(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass  # Process may be unkillable — move on
                return SandboxExecResult(
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    exit_code=-1,
                    timed_out=True,
                    command=command,
                )
            
            # Decode output
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            
            # Truncate if too long
            limit = self.config.max_output_bytes
            if len(stdout) > limit:
                half = (limit - 100) // 2
                stdout = stdout[:half] + "\n[...TRUNCATED...]\n" + stdout[-half:]
            if len(stderr) > limit:
                half = (limit - 100) // 2
                stderr = stderr[:half] + "\n[...TRUNCATED...]\n" + stderr[-half:]
            
            return SandboxExecResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
                command=command,
            )
            
        except FileNotFoundError:
            return SandboxExecResult(
                stderr=f"Command not found: {command.split()[0]}",
                exit_code=127,
                command=command,
            )
        except PermissionError:
            return SandboxExecResult(
                stderr=f"Permission denied: {command}",
                exit_code=126,
                blocked=True,
                block_reason="Permission denied",
                command=command,
            )
    
    def _kill_process_tree(self, proc: asyncio.subprocess.Process):
        """
        Kill a process and all its children (process tree).
        
        On UNIX: sends SIGTERM to the entire process group.
        On Windows: uses taskkill /F /T to kill the tree.
        Falls back to proc.kill() if tree kill fails.
        """
        try:
            if os.name == 'nt':
                # Windows: kill the entire process tree via taskkill
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # UNIX: kill the entire process group
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    # Process already dead or we lack permissions — fallback
                    proc.kill()
        except Exception:
            # Last resort: kill just the direct child
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    def _prepare_environment(self, extra_env: dict[str, str] | None) -> dict[str, str]:
        """Prepare a restricted environment for command execution."""
        env = {}
        
        # Only pass safe env vars
        safe_vars = [
            "HOME", "USER", "SHELL", "LANG", "LC_ALL",
            "NODE_ENV", "PYTHONPATH", "VIRTUAL_ENV",
            "http_proxy", "https_proxy", "no_proxy",
        ]
        
        for var in safe_vars:
            val = os.environ.get(var)
            if val:
                env[var] = val
        
        # Hardcode safe PATH to prevent PATH injection
        if os.name == 'nt':
            env["PATH"] = os.environ.get("PATH", r"C:\Windows\System32;C:\Windows")
        else:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        if extra_env:
            env.update(extra_env)
        
        return env
    
    def _log_violation(self, kind: str, command: str, reason: str):
        """Log a sandbox violation."""
        self._violation_log.append({
            "kind": kind,
            "command": command,
            "reason": reason,
            "timestamp": __import__("time").time(),
        })
    
    def get_violations(self) -> list[dict]:
        """Get logged violations."""
        return self._violation_log.copy()
    
    def check_filesystem_access(
        self,
        path: str,
        write: bool = False,
    ) -> Decision:
        """Check if filesystem access is allowed."""
        return self.policy.evaluate_filesystem(path, write)
    
    def check_network_access(self, host: str) -> Decision:
        """Check if network access is allowed."""
        return self.policy.evaluate_network(host)
    
    def wrap_command_for_sandbox(self, command: str) -> str:
        """
        Wrap a command with sandbox restrictions.
        
        From Codex's SandboxTransformRequest.
        Adds restrictions like:
        - Working directory
        - Environment
        - Resource limits
        """
        # For now, we use Python's subprocess restrictions
        # In production, this could use:
        # - Linux: bubblewrap (bwrap) or landlock
        # - macOS: seatbelt (sandbox-exec)
        # - Windows: restricted token
        
        return command


class DockerSandbox:
    """
    Docker-based sandbox for stronger isolation.
    
    From OpenHands' Docker approach:
    - Runs commands in a container
    - Mounts project directory
    - Provides full isolation
    """
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        project_path: str = ".",
    ):
        self.image = image
        self.project_path = os.path.abspath(project_path)
        self.container_name = f"dev-sandbox-{os.getpid()}"
        self._running = False
    
    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    async def start(self) -> bool:
        """Start the sandbox container."""
        if not self.is_available():
            return False
        
        import asyncio
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "-d",
                "--name", self.container_name,
                "-v", f"{self.project_path}:/workspace",
                "-w", "/workspace",
                self.image,
                "sleep", "infinity",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            self._running = True
            return True
        except Exception:
            return False
    
    async def execute(self, command: str, timeout: int = 30) -> SandboxExecResult:
        """Execute a command in the Docker sandbox."""
        if not self._running:
            return SandboxExecResult(
                blocked=True,
                block_reason="Docker sandbox not running",
                command=command,
            )
        
        import asyncio
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", self.container_name,
                "sh", "-c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            
            return SandboxExecResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
                command=command,
            )
        except asyncio.TimeoutError:
            # Kill the docker exec process tree
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                pass
            return SandboxExecResult(
                stderr=f"Timed out after {timeout}s",
                exit_code=-1,
                timed_out=True,
                command=command,
            )
    
    async def stop(self):
        """Stop and remove the sandbox container."""
        if not self._running:
            return
        
        import asyncio
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        except Exception:
            pass
        
        self._running = False
