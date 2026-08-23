"""
Real Tool Implementations for Dev.

File I/O, shell execution, git operations, web tools.
All tools have execute() methods that actually work.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import glob as glob_module
import time
from pathlib import Path
from typing import Any

from .base import Tool


class RealReadFilesTool(Tool):
    """Read files from disk with line ranges."""
    name = "read_files"
    description = "Read files from disk. Supports line ranges and multiple files."
    parameters = {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {"type": "string"},
                        {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "offset": {"type": "integer", "minimum": 1},
                                "limit": {"type": "integer", "minimum": 1, "default": 2000},
                            },
                            "required": ["path"],
                        },
                    ],
                },
                "description": "List of file paths or {path, offset, limit} objects",
            },
        },
        "required": ["paths"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        paths = input_data.get("paths", [])
        # LLM may send paths as a JSON string instead of a list
        if isinstance(paths, str):
            try:
                paths = json.loads(paths)
            except (json.JSONDecodeError, TypeError):
                paths = [paths]
        if not isinstance(paths, list):
            paths = [paths]
        results = []

        for path_info in paths:
            if isinstance(path_info, str):
                file_path = path_info
                offset = 1
                limit = 2000
            else:
                file_path = path_info.get("path", "")
                offset = path_info.get("offset", 1)
                limit = path_info.get("limit", 2000)

            abs_path = self._resolve_path(file_path, project_path)

            try:
                if not os.path.exists(abs_path):
                    results.append({"path": file_path, "error": f"File not found: {file_path}"})
                    continue
                if os.path.isdir(abs_path):
                    results.append({"path": file_path, "error": f"Is a directory: {file_path}. Use list_directory instead."})
                    continue

                # File size limit: 10MB
                file_size = os.path.getsize(abs_path)
                if file_size > 10 * 1024 * 1024:
                    results.append({"path": file_path, "error": f"File too large ({file_size // 1024}KB). Max 10MB."})
                    continue

                # Detect binary files by checking for null bytes
                try:
                    with open(abs_path, "rb") as f:
                        chunk = f.read(1024)
                        if b'\x00' in chunk:
                            results.append({"path": file_path, "error": "Cannot read binary file"})
                            continue
                except Exception:
                    pass

                # Try UTF-8 first, then fallback to system encoding
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    try:
                        with open(abs_path, "r", encoding="latin-1") as f:
                            lines = f.readlines()
                    except Exception:
                        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()

                total_lines = len(lines)
                start = max(0, offset - 1)
                end = min(total_lines, start + limit)
                selected = lines[start:end]

                content = "".join(selected)
                results.append({
                    "path": file_path,
                    "content": content,
                    "total_lines": total_lines,
                    "offset": offset,
                    "limit": limit,
                })
            except Exception as e:
                results.append({"path": file_path, "error": str(e)})

        return {"files": results}

    def _resolve_path(self, path: str, project_path: str) -> str:
        if os.path.isabs(path):
            abs_path = os.path.normpath(os.path.abspath(path))
        else:
            abs_path = os.path.normpath(os.path.abspath(os.path.join(project_path, path)))
        # Path traversal protection: ensure resolved path is within project
        abs_project = os.path.normpath(os.path.abspath(project_path))
        # Resolve symlinks and check target is within project
        try:
            real_path = os.path.realpath(abs_path)
            real_project = os.path.realpath(abs_project)
            if not real_path.startswith(real_project):
                raise ValueError(f"Symlink escape blocked: {path} -> {real_path} resolves outside project")
        except (OSError, ValueError):
            pass
        if not abs_path.startswith(abs_project):
            raise ValueError(f"Path traversal blocked: {path} resolves outside project")
        # Windows MAX_PATH workaround
        if os.name == 'nt' and len(abs_path) > 240 and not abs_path.startswith('\\\\?\\'):
            abs_path = '\\\\?\\' + abs_path
        return abs_path



class RealWriteFileTool(Tool):
    """Write content to a file."""
    name = "write_file"
    description = "Create or replace a file with the given content."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to project root"},
            "content": {"type": "string", "description": "Content to write"},
            "instructions": {"type": "string", "description": "What the change is intended to do"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        path = input_data.get("path", "")
        if os.name == 'nt' and path:
            # Sanitize trailing spaces on Windows to prevent ghost files
            path = '/'.join(p.rstrip() for p in path.replace('\\', '/').split('/'))
        content = input_data.get("content", "")
        instructions = input_data.get("instructions", "")

        # Validate content is not empty
        if not content or not content.strip():
            return {"error": "Cannot write empty content", "path": path}

        # Content size limit: 5MB
        content_bytes = len(content.encode('utf-8'))
        if content_bytes > 5 * 1024 * 1024:
            return {"error": f"Content too large ({content_bytes // 1024}KB). Max 5MB.", "path": path}

        abs_path = self._resolve_path(path, project_path)

        # Check for concurrent modification by user
        expected_mtime = input_data.get("expected_mtime")
        if expected_mtime and os.path.exists(abs_path):
            current_mtime = os.path.getmtime(abs_path)
            if current_mtime > expected_mtime:
                return {"error": "File was modified externally. Please re-read the file.", "path": path}

        try:
            parent_dir = os.path.dirname(abs_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            # Atomic write: write to temp file first, then replace
            temp_path = abs_path + ".writetmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, abs_path)
            except OSError:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
            return {
                "success": True,
                "path": path,
                "lines": content.count("\n") + 1,
                "bytes": len(content.encode("utf-8")),
                "instructions": instructions,
            }
        except Exception as e:
            return {"error": str(e), "path": path}

    def _resolve_path(self, path: str, project_path: str) -> str:
        # Always resolve to absolute first
        if os.path.isabs(path):
            abs_path = os.path.normpath(path)
        else:
            abs_path = os.path.normpath(os.path.abspath(os.path.join(project_path, path)))
        abs_project = os.path.normpath(os.path.abspath(project_path))
        if not abs_path.startswith(abs_project):
            raise ValueError(f"Path traversal blocked: {path} resolves outside project")
        # Windows MAX_PATH workaround
        if os.name == 'nt' and len(abs_path) > 240 and not abs_path.startswith('\\\\?\\'):
            abs_path = '\\\\?\\' + abs_path
        return abs_path


class RealStrReplaceTool(Tool):
    """Replace strings in a file."""
    name = "str_replace"
    description = "Replace strings in a file with new strings."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "replacements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "oldString": {"type": "string"},
                        "newString": {"type": "string"},
                        "allowMultiple": {"type": "boolean", "default": False},
                    },
                    "required": ["oldString", "newString"],
                },
                "description": "List of replacements to make",
            },
        },
        "required": ["path", "replacements"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        path = input_data.get("path", "")
        replacements = input_data.get("replacements", [])

        abs_path = self._resolve_path(path, project_path)

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content
            applied = 0
            errors = []

            for replacement in replacements:
                old = replacement.get("oldString", "")
                new = replacement.get("newString", "")
                allow_multiple = replacement.get("allowMultiple", False)

                if not old:
                    errors.append("Empty oldString")
                    continue
                if not content:
                    errors.append("File is empty")
                    continue

                # Normalize line endings to prevent CRLF/LF mismatch
                normalized_content = content.replace('\r\n', '\n')
                normalized_old = old.replace('\r\n', '\n')
                normalized_new = new.replace('\r\n', '\n')

                count = normalized_content.count(normalized_old)

                if count == 0:
                    errors.append(f"String not found: {repr(old[:80])}")
                    continue

                if count > 1 and not allow_multiple:
                    errors.append(f"Multiple occurrences ({count}) of: {repr(old[:80])}")
                    continue

                content = normalized_content.replace(normalized_old, normalized_new, 1 if not allow_multiple else count)
                applied += 1

            if applied > 0:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(content)

            return {
                "success": applied > 0,
                "path": path,
                "applied": applied,
                "errors": errors,
                "diff": self._make_diff(original_content, content, path),
            }
        except Exception as e:
            return {"error": str(e), "path": path}

    def _make_diff(self, old: str, new: str, path: str) -> str:
        """Create a unified diff."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        diff_lines = []
        max_lines = max(len(old_lines), len(new_lines))

        for i in range(max_lines):
            old_line = old_lines[i] if i < len(old_lines) else None
            new_line = new_lines[i] if i < len(new_lines) else None

            if old_line != new_line:
                line_num = i + 1
                if old_line:
                    diff_lines.append(f"  L{line_num} - {old_line.rstrip()}")
                if new_line:
                    diff_lines.append(f"  L{line_num} + {new_line.rstrip()}")

        return "\n".join(diff_lines[:50])

    def _resolve_path(self, path: str, project_path: str) -> str:
        # Always resolve to absolute first
        if os.path.isabs(path):
            abs_path = os.path.normpath(path)
        else:
            abs_path = os.path.normpath(os.path.abspath(os.path.join(project_path, path)))
        abs_project = os.path.normpath(os.path.abspath(project_path))
        if not abs_path.startswith(abs_project):
            raise ValueError(f"Path traversal blocked: {path} resolves outside project")
        # Windows MAX_PATH workaround
        if os.name == 'nt' and len(abs_path) > 240 and not abs_path.startswith('\\\\?\\'):
            abs_path = '\\\\?\\' + abs_path
        return abs_path


class RealCodeSearchTool(Tool):
    """Search code using ripgrep-style patterns."""
    name = "code_search"
    description = "Search through code files for patterns."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern (regex)"},
            "flags": {"type": "string", "description": "ripgrep flags (e.g., -i, -n)"},
            "cwd": {"type": "string", "description": "Directory to search in"},
            "maxResults": {"type": "integer", "description": "Max results per file", "default": 15},
        },
        "required": ["pattern"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        pattern = input_data.get("pattern", "")
        flags = input_data.get("flags", "")
        cwd = input_data.get("cwd", ".")
        max_results = input_data.get("maxResults", 15)

        search_dir = os.path.join(project_path, cwd) if not os.path.isabs(cwd) else cwd

        # Try ripgrep first
        try:
            cmd = ["rg", "--json", "-n", pattern]
            if "-i" in flags:
                cmd.append("-i")
            cmd.append(search_dir)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode == 0:
                results = {}
                for line in stdout.decode().splitlines():
                    try:
                        data = json.loads(line)
                        if data.get("type") == "match":
                            path = data["data"]["path"]["text"]
                            line_num = data["data"]["line_number"]
                            text = data["data"]["lines"]["text"]
                            rel_path = os.path.relpath(path, project_path)
                            if rel_path not in results:
                                results[rel_path] = []
                            if len(results[rel_path]) < max_results:
                                results[rel_path].append({"line": line_num, "text": text.rstrip()})
                    except (json.JSONDecodeError, KeyError):
                        continue
                return {"matches": results, "tool": "ripgrep"}
        except (FileNotFoundError, asyncio.TimeoutError):
            pass

        # Fallback to Python
        results = {}
        try:
            regex = re.compile(pattern, re.IGNORECASE if "-i" in flags else 0)
        except re.error:
            return {"error": f"Invalid regex pattern: {pattern}"}

        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", "venv", ".venv", "vendor", "dist", "build", ".git"
            )]
            for fname in files:
                if fname.startswith(".") or not any(fname.endswith(ext) for ext in (
                    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb",
                    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".sh", ".bash",
                    ".yaml", ".yml", ".toml", ".json", ".md", ".txt", ".html", ".css",
                    ".sql", ".graphql", ".proto", ".lua", ".php", ".r", ".scala",
                )):
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, project_path)

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                if rel_path not in results:
                                    results[rel_path] = []
                                if len(results[rel_path]) < max_results:
                                    results[rel_path].append({"line": i, "text": line.rstrip()})
                except (UnicodeDecodeError, PermissionError):
                    continue

        return {"matches": results, "tool": "python"}


class RealGlobTool(Tool):
    """Find files by glob pattern."""
    name = "glob"
    description = "Search for files matching a glob pattern."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern"},
            "cwd": {"type": "string", "description": "Directory to search in"},
            "max_results": {"type": "integer", "description": "Max results", "default": 50},
        },
        "required": ["pattern"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        pattern = input_data.get("pattern", "")
        cwd = input_data.get("cwd", ".")
        max_results = min(input_data.get("maxResults", 50), 1000)  # Hard cap at 1000

        search_dir = os.path.join(project_path, cwd) if not os.path.isabs(cwd) else cwd
        full_pattern = os.path.join(search_dir, pattern)

        matches = []
        total = 0
        for match in glob_module.iglob(full_pattern, recursive=True):
            total += 1
            if len(matches) >= max_results:
                continue  # Keep counting total
            rel_path = os.path.relpath(match, project_path)
            matches.append(rel_path)

        result = {"paths": sorted(matches)}
        if total > max_results:
            result["warning"] = f"Truncated from {total} results to {max_results}"
        return result


class RealListDirectoryTool(Tool):
    """List directory contents."""
    name = "list_directory"
    description = "List files and directories in a path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path"},
        },
        "required": ["path"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        path = input_data.get("path", ".")
        abs_path = os.path.join(project_path, path) if not os.path.isabs(path) else path

        try:
            entries = os.listdir(abs_path)
            files = []
            dirs = []
            for entry in sorted(entries):
                full = os.path.join(abs_path, entry)
                if os.path.isdir(full):
                    dirs.append(entry)
                else:
                    files.append(entry)
            return {"path": path, "files": files, "directories": dirs}
        except Exception as e:
            return {"error": str(e), "path": path}


class RealRunTerminalCommand(Tool):
    """Run shell commands."""
    name = "run_terminal_command"
    description = "Execute a shell command."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
            "timeout_seconds": {"type": "integer", "description": "Timeout", "default": 30},
        },
        "required": ["command"],
    }

    def _find_bash(self) -> str | None:
        """Find bash executable on Windows."""
        import shutil
        # Check common locations
        for bash in ["bash", "C:\\Program Files\\Git\\bin\\bash.exe", "C:\\Windows\\System32\\bash.exe"]:
            if shutil.which(bash):
                return bash
        return None

    # Dangerous command patterns that should be blocked
    BLOCKED_PATTERNS = [
        "rm -rf /", "rm -r /", "rm -rf /*", "rm -r /*",
        "dd if=", "mkfs", "> /dev/sd",
        "shutdown", "reboot", "halt", "poweroff",
        "format c:", ":(){ :|:& };:",
        "chmod -R 777 /", "chmod -R 777 /*",
        "wget|sh", "wget|bash", "curl|sh", "curl|bash",
        "eval $(", "exec ",
        "cd / &&", "cd /root &&",
        "cat /etc/shadow", "cat /etc/passwd",
        # Additional safety patterns
        "rm -rf .", "rm -r .",  # Recursive delete in current dir
        "git push --force", "git push -f",  # Force push
        "DROP TABLE", "DROP DATABASE",  # SQL injection
        "TRUNCATE TABLE", "DELETE FROM",  # SQL data loss
        "npm uninstall -g",  # Global uninstall
        "pip uninstall -y",  # Force uninstall
        "docker rm -f",  # Force remove container
        "docker rmi -f",  # Force remove image
        "kubectl delete",  # K8s deletion
        "terraform destroy",  # Infra destruction
        "heroku ps:scale 0",  # Scale to zero
        "echo '' > ",  # Truncate file
        "> /dev/null 2>&1",  # Suppress errors (security)
        "xargs rm",  # Pipe to rm
        "find . -delete",  # Find and delete
        "find . -exec rm",  # Find and exec rm
        "git checkout -- .",  # Discard all changes
        "git reset --hard",  # Hard reset
    ]
    
    def _is_safe_command(self, command: str) -> tuple[bool, str]:
        """Check if a command is safe to execute.
        
        Returns (is_safe, reason).
        """
        cmd_lower = command.lower().strip()
        
        # Check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in cmd_lower:
                return False, f"Blocked dangerous command: {pattern}"
        
        # Block sudo
        if cmd_lower.startswith("sudo "):
            return False, "Blocked: sudo not allowed"
        
        # Block command chaining with dangerous commands
        if "&&" in cmd_lower or ";" in cmd_lower:
            parts = cmd_lower.replace("&&", ";").split(";")
            for part in parts:
                part = part.strip()
                for pattern in self.BLOCKED_PATTERNS:
                    if pattern.lower() in part:
                        return False, f"Blocked dangerous command in chain: {pattern}"
        
        # Block pipe to shell
        if "| sh" in cmd_lower or "| bash" in cmd_lower:
            return False, "Blocked: pipe to shell not allowed"
        
        # Block writing to system directories
        system_dirs = ["/etc/", "/usr/", "/var/", "/sys/", "/proc/", "/dev/", "/boot/"]
        for sys_dir in system_dirs:
            if f" > {sys_dir}" in cmd_lower or f"> {sys_dir}" in cmd_lower:
                return False, f"Blocked: writing to {sys_dir}"
        
        return True, "OK"
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        command = input_data.get("command", "")
        cwd = input_data.get("cwd", project_path)
        if not cwd or not os.path.isdir(cwd):
            cwd = project_path
        timeout = input_data.get("timeout_seconds", 30)
        # LLM may send timeout as string
        if isinstance(timeout, str):
            try:
                timeout = int(timeout)
            except (ValueError, TypeError):
                timeout = 30
        
        # Safety check: block dangerous commands
        is_safe, reason = self._is_safe_command(command)
        if not is_safe:
            return {"error": reason, "command": command, "blocked": True}

        import signal as _signal
        is_windows = os.name == 'nt'
        try:
            kwargs = {
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "cwd": cwd,
            }
            if not is_windows:
                kwargs["preexec_fn"] = os.setsid

            # On Windows, use cmd /c for complex commands
            effective_command = command
            if is_windows:
                import shlex
                # If command starts with ./ or uses bash syntax, try to use bash
                if command.startswith('./') or command.startswith('bash '):
                    bash_path = self._find_bash()
                    if bash_path:
                        effective_command = f'{bash_path} -c {shlex.quote(command)}'

            # Force UTF-8 encoding on Windows to prevent cp1252 errors
            import copy
            env = copy.copy(os.environ)
            env['PYTHONUTF8'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'
            kwargs['env'] = env
            proc = await asyncio.create_subprocess_shell(effective_command, **kwargs)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            return {
                "command": command,
                "exitCode": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:30000],
                "stderr": stderr.decode(errors="replace")[:5000],
            }
        except asyncio.TimeoutError:
            try:
                if is_windows:
                    proc.send_signal(_signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            await proc.wait()
            return {"error": f"Command timed out after {timeout}s", "command": command}
        except Exception as e:
            return {"error": str(e), "command": command}


class RealGitOperations(Tool):
    """Git operations."""
    name = "git_operations"
    description = "Execute git commands."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "git action (diff, log, commit, branch, status)"},
            "args": {"type": "string", "description": "Additional arguments"},
            "message": {"type": "string", "description": "Commit message"},
        },
        "required": ["action"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        action = input_data.get("action", "status")
        args = input_data.get("args", "")
        message = input_data.get("message", "")        # Safety: block dangerous git operations
        blocked_actions = {
            "push --force", "push -f", "push --force-with-lease",
            "reset --hard", "reset --mixed",
            "checkout -- .", "checkout --",
            "clean -fd", "clean -f",
            "rebase --abort",
            "stash drop", "stash clear",
        }
        action_lower = action.lower()
        args_lower = args.lower() if args else ""
        for blocked in blocked_actions:
            if blocked in action_lower or blocked in args_lower:
                return {"error": f"Blocked dangerous git operation: {action} {args}", "blocked": True}
        
        cmd_map = {
            "diff": "git diff",
            "diff-stat": "git diff --stat",
            "log": "git log --oneline -20",
            "status": "git status",
            "branch": "git branch",
            "commit": f'git commit -m "{message}"' if message else "git commit",
            "add": f"git add {args}" if args else "git add .",
            "push": "git push",
            "pull": "git pull",
            "stash": "git stash push",
            "stash-list": "git stash list",
            "stash-pop": "git stash pop",
        }
        
        cmd = cmd_map.get(action, f"git {action} {args}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            return {
                "action": action,
                "exitCode": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:30000],
                "stderr": stderr.decode(errors="replace")[:5000],
            }
        except Exception as e:
            return {"error": str(e), "action": action}


class RealWebSearchTool(Tool):
    """Web search using multiple free fallbacks."""
    name = "web_search"
    description = "Search the web for information."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        query = input_data.get("query", "")
        if not query:
            return {"error": "No query provided"}

        try:
            import httpx

            # Try multiple search approaches
            results = []

            # 1. DuckDuckGo API (JSON, more reliable than HTML scraping)
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                try:
                    resp = await client.get(
                        "https://api.duckduckgo.com/",
                        params={"q": query, "format": "json", "no_redirect": "1"},
                        headers={"User-Agent": "Dev/1.0"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Abstract
                        abstract = data.get("Abstract", "")
                        if abstract:
                            results.append({
                                "title": data.get("Heading", query),
                                "snippet": abstract,
                                "url": data.get("AbstractURL", ""),
                            })
                        # Related topics
                        for topic in data.get("RelatedTopics", [])[:5]:
                            if isinstance(topic, dict) and "Text" in topic:
                                results.append({
                                    "title": topic.get("Text", "")[:100],
                                    "snippet": topic.get("Text", ""),
                                    "url": topic.get("FirstURL", ""),
                                })
                except Exception:
                    pass

                # 2. DuckDuckGo HTML lite (fallback)
                if not results:
                    try:
                        resp = await client.get(
                            "https://lite.duckduckgo.com/lite",
                            params={"q": query},
                            headers={"User-Agent": "Mozilla/5.0 (Dev/1.0)"},
                        )
                        if resp.status_code == 200:
                            text = resp.text
                            # Parse result links
                            links = re.findall(r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', text)
                            snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', text)

                            for i, (url, title) in enumerate(links[:5]):
                                snippet = snippets[i].strip() if i < len(snippets) else ""
                                # Clean HTML tags
                                title = re.sub(r'<[^>]+>', '', title).strip()
                                snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                                results.append({
                                    "title": title[:100],
                                    "snippet": snippet[:300],
                                    "url": url,
                                })
                    except Exception:
                        pass

                # 3. Google Custom Search (free tier) as last resort
                if not results:
                    try:
                        resp = await client.get(
                            "https://www.google.com/search",
                            params={"q": query, "num": 5},
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        )
                        if resp.status_code == 200:
                            # Simple extraction
                            titles = re.findall(r'<h3[^>]*>(.*?)</h3>', resp.text)
                            for title in titles[:5]:
                                clean = re.sub(r'<[^>]+>', '', title).strip()
                                if clean:
                                    results.append({"title": clean, "snippet": "", "url": ""})
                    except Exception:
                        pass

            return {"query": query, "results": results[:10], "count": len(results)}

        except Exception as e:
            return {"query": query, "error": str(e)}


class RealReadUrlTool(Tool):
    """Read URL content with proper HTML-to-text extraction."""
    name = "read_url"
    description = "Fetch and read readable text from a URL."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "max_chars": {"type": "integer", "description": "Max characters to return", "default": 20000},
        },
        "required": ["url"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "")
        max_chars = input_data.get("max_chars", 20000)

        if not url:
            return {"error": "No URL provided"}

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Dev/1.0; +https://github.com/dev)"},
            ) as client:
                resp = await client.get(url)

                if resp.status_code != 200:
                    return {"url": url, "error": f"HTTP {resp.status_code}"}

                content_type = resp.headers.get("content-type", "")
                raw_html = resp.text

                # If it's JSON, return formatted
                if "json" in content_type:
                    try:
                        data = resp.json()
                        text = json.dumps(data, indent=2)[:max_chars]
                        return {"url": url, "content": text, "type": "json", "status": 200}
                    except Exception:
                        pass

                # Extract readable text from HTML
                text = self._html_to_text(raw_html)

                # Try to get title
                title_match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""

                # Get meta description
                meta_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', raw_html, re.IGNORECASE)
                description = meta_match.group(1).strip() if meta_match else ""

                # Build result
                parts = []
                if title:
                    parts.append(f"# {title}")
                if description:
                    parts.append(f"\n{description}")
                parts.append(f"\n---\n\n{text[:max_chars - len(title) - len(description) - 20]}")

                return {
                    "url": url,
                    "title": title,
                    "content": "\n".join(parts),
                    "type": "html",
                    "status": 200,
                    "content_length": len(text),
                }

        except Exception as e:
            return {"url": url, "error": str(e)}

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to readable text."""
        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove nav, footer, header, sidebar
        for tag in ['nav', 'footer', 'header', 'aside', 'form']:
            text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Convert common elements
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n## \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)

        # Extract links
        text = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&nbsp;', ' ')

        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        lines = [line.strip() for line in text.splitlines()]
        text = '\n'.join(lines)

        return text.strip()
