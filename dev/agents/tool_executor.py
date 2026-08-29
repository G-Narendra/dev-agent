"""
Tool execution mixin for ProductionAgentLoop.

Extracted from production_loop.py to reduce file size.
Handles: tool execution, approval, backup, text parsing, code block extraction.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
from typing import Any, Callable

from .loop_types import (
    Message, LoopConfig, EditResult, LoopState,
    MODIFYING_TOOLS, READ_ONLY_TOOLS, COMMIT_TOOLS,
    DANGEROUS_TOOLS, DANGEROUS_COMMANDS,
)


class ToolExecutorMixin:
    """Mixin providing tool execution, approval, and parsing methods."""

    # These will be set by ProductionAgentLoop.__init__
    _hook_manager: Any = None
    _tool_validator: Any = None
    _audit_logger: Any = None
    _injection_detector: Any = None
    _output_monitor: Any = None
    _error_recovery: Any = None
    _on_approval_prompt: Callable | None = None
    _tool_cache: dict = {}
    _tool_cache_max: int = 100
    _state: LoopState = None
    config: LoopConfig = None
    tools: Any = None
    project_path: str = ""

    def _log(self, msg: str):
        """Log a message if verbose."""
        if self.config and self.config.verbose:
            print(f"  [DEV] {msg}")

    MAX_CHECKPOINTS = 100

    async def _execute_tool_with_hooks(self, tool_name: str, tool_args: dict, call_id: str = "") -> Any:
        """Execute a tool with pre/post hooks and error recovery."""
        if self._hook_manager:
            try:
                await self._hook_manager.run_hooks("pre_tool_use", {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                })
            except Exception as e:
                self._log(f"Pre-hook error: {e}")

        result = await self._execute_tool(tool_name, tool_args)

        if self._hook_manager:
            try:
                await self._hook_manager.run_hooks("post_tool_use", {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "result": result,
                })
            except Exception as e:
                self._log(f"Post-hook error: {e}")

        return result

    @staticmethod
    def _coerce_tool_args(args: dict) -> dict:
        """Coerce model-supplied arg values: models often send numbers/booleans as strings."""
        STRING_ONLY_KEYS = {"path", "content", "command", "pattern", "text", "query", "name",
                            "description", "instructions", "old_string", "new_string", "message",
                            "url", "cwd"}
        coerced = {}
        for k, v in args.items():
            if k in STRING_ONLY_KEYS:
                coerced[k] = v
            elif isinstance(v, str):
                s = v.strip()
                if s.startswith("[") or s.startswith("{"):
                    try:
                        coerced[k] = json.loads(s)
                        continue
                    except json.JSONDecodeError:
                        pass
                if s.lower() in ("true", "false"):
                    coerced[k] = s.lower() == "true"
                else:
                    try:
                        coerced[k] = int(s)
                    except ValueError:
                        try:
                            coerced[k] = float(s)
                        except ValueError:
                            coerced[k] = v
            else:
                coerced[k] = v
        return coerced

    async def _execute_single_tool(self, tc: dict, on_tool_call: Callable | None, on_tool_result: Callable | None) -> Any:
        """Execute a single tool call (used for parallel read-only execution)."""
        tool_name = tc.get("function", {}).get("name", "")
        try:
            raw_args = tc.get("function", {}).get("arguments", "{}")
            tool_args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            tool_args = {}
        if not isinstance(tool_args, dict):
            tool_args = {}
        tool_args = self._coerce_tool_args(tool_args)

        if on_tool_call:
            on_tool_call(tool_name, tool_args)

        if tool_name not in self.tools:
            result = {"error": f"Tool '{tool_name}' does not exist."}
        else:
            result = await self._execute_tool_with_hooks(tool_name, tool_args, tc.get("id", ""))

        if on_tool_result:
            on_tool_result(tool_name, result)

        result_str = json.dumps(result)
        MAX_TOOL_RESULT_CHARS = 50000
        if len(result_str) > MAX_TOOL_RESULT_CHARS:
            result_str = result_str[:MAX_TOOL_RESULT_CHARS] + "\n\n... [Truncated]"

        self._state.cur_messages.append(
            Message(role="tool", tool_call_id=tc.get("id", ""),
                    name=tool_name, content=result_str)
        )
        return result

    def _check_tool_allowed(self, tool_name: str, tool_args: dict) -> dict:
        """Check if a tool call is allowed based on approval mode and plan mode."""
        if self.config.enforce_plan_mode:
            if tool_name not in READ_ONLY_TOOLS:
                return {
                    "allowed": False,
                    "reason": f"Plan mode: '{tool_name}' is a write operation. Switch to act mode to execute.",
                }

        mode = self.config.approval_mode

        if mode == "full-auto":
            return {"allowed": True, "reason": "full-auto: auto-approved"}

        if mode == "suggest":
            if tool_name in READ_ONLY_TOOLS:
                return {"allowed": True, "reason": "suggest: read-only tool auto-approved"}
            return {
                "allowed": False,
                "reason": f"suggest mode: '{tool_name}' requires user approval.",
            }

        if mode == "auto-edit":
            if tool_name in READ_ONLY_TOOLS:
                return {"allowed": True, "reason": "auto-edit: read-only auto-approved"}
            if tool_name in COMMIT_TOOLS:
                return {"allowed": True, "reason": "auto-edit: file edit auto-approved"}
            if tool_name == "run_terminal_command":
                cmd = tool_args.get("command", "")
                for pattern in DANGEROUS_COMMANDS:
                    if pattern in cmd:
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: dangerous command detected: '{pattern}'.",
                        }
                network_patterns = ["curl ", "wget ", "fetch(", "http://", "https://"]
                for np in network_patterns:
                    if np in cmd.lower():
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: network call detected: '{np}'.",
                        }
                install_patterns = ["npm install", "npm i ", "pip install", "pip i ", "yarn add", "pnpm add"]
                for ip in install_patterns:
                    if ip in cmd.lower():
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: dependency install detected: '{ip}'.",
                        }
                return {"allowed": True, "reason": "auto-edit: terminal command auto-approved"}
            if tool_name == "git_operations":
                action = tool_args.get("action", "")
                if action in ("push",):
                    return {
                        "allowed": False,
                        "reason": "auto-edit: git push requires approval.",
                    }
                return {"allowed": True, "reason": "auto-edit: git operation auto-approved"}
            return {"allowed": True, "reason": "auto-edit: tool auto-approved"}

        return {"allowed": True, "reason": "default: allowed"}

    async def _prompt_user_approval(self, tool_name: str, tool_args: dict) -> bool:
        """Prompt user for approval in suggest mode (async-safe)."""
        if self._on_approval_prompt:
            return await asyncio.to_thread(self._on_approval_prompt, tool_name, tool_args)
        return False

    def _cleanup_old_checkpoints(self, backup_dir: str):
        """Remove old checkpoints beyond MAX_CHECKPOINTS limit."""
        try:
            backups = [f for f in os.listdir(backup_dir) if f.startswith("cp") and not f.endswith(".meta")]
            if len(backups) > self.MAX_CHECKPOINTS:
                backups.sort()
                for old in backups[:len(backups) - self.MAX_CHECKPOINTS]:
                    old_path = os.path.join(backup_dir, old)
                    meta_path = old_path + ".meta"
                    os.remove(old_path)
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
        except Exception:
            pass  # Intentional: checkpoint cleanup is best-effort

    def _parse_text_tool_calls(self, text: str) -> list[dict]:
        """Extract tool calls from text when model outputs code instead of API tool calls."""
        calls = []
        # Pattern 1: tool_name(args) format
        pattern = r'(\w+)\(([^)]*)\)'
        for match in re.finditer(pattern, text):
            func_name = match.group(1)
            args_str = match.group(2)
            if func_name in ("def", "class", "import", "from", "if", "for", "while", "return", "print", "len", "str", "int", "float", "list", "dict", "set", "tuple", "range", "enumerate", "zip", "map", "filter", "sorted", "reversed", "any", "all", "min", "max", "sum", "abs", "round", "type", "isinstance", "hasattr", "getattr", "setattr"):
                continue
            try:
                args = json.loads(f"{{{args_str}}}") if args_str.strip() else {}
            except json.JSONDecodeError:
                args = {"raw": args_str}
            calls.append({
                "function": {"name": func_name, "arguments": json.dumps(args)},
                "id": f"text_{len(calls)}",
            })
        return calls

    def _has_pending_todos(self, content: str) -> bool:
        """Check if content has pending todos that need completion."""
        return "pending" in content.lower() and "todo" in content.lower()

    def _parse_code_blocks(self, text: str) -> list[dict]:
        """Parse fenced code blocks into write_file tool calls."""
        calls = []
        seen_paths = set()

        # Pattern 1: ```filename: path\n<code>\n``` or ```path\n<code>\n```
        for m in re.finditer(
            r'```\w*\s*(?:filename:\s*)?((?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10})\s*\n(.*?)```',
            text, re.DOTALL
        ):
            path = m.group(1)
            code = m.group(2)
            if path not in seen_paths:
                seen_paths.add(path)
                calls.append({
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": path, "content": code, "instructions": f"Create {path}"}),
                    },
                    "id": f"code_{len(calls)}",
                })

        # Pattern 2: // filename: path\n<code>\n```
        for m in re.finditer(
            r'//\s*(?:filename:\s*)?((?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10})\s*\n```(?:\w*)\n(.*?)```',
            text, re.DOTALL
        ):
            path = m.group(1)
            code = m.group(2)
            if path not in seen_paths:
                seen_paths.add(path)
                calls.append({
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": path, "content": code, "instructions": f"Create {path}"}),
                    },
                    "id": f"code_{len(calls)}",
                })

        return calls

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> Any:
        """Execute a tool call with security validation, error handling, and caching."""
        handler = self.tools.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        # SECURITY: Validate tool call against permission rules
        if self._tool_validator:
            validation = self._tool_validator.validate(tool_name, tool_args)
            if not validation.allowed:
                self._log(f"⛔ Security: Tool call BLOCKED: {tool_name} -- {validation.reason}")
                if self._audit_logger:
                    self._audit_logger.log_security_event(
                        event_type="tool_blocked",
                        details=f"{tool_name}: {validation.reason}",
                        threat_level="high",
                        blocked=True,
                    )
                return {"blocked": f"Security: {validation.reason}"}

        # Cache read-only tool results
        cache_key = None
        if tool_name in READ_ONLY_TOOLS:
            cache_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            if cache_key in self._tool_cache:
                self._log(f"Cache hit: {tool_name}")
                return self._tool_cache[cache_key]

        # Audit log
        start_time = time.time()
        if self._audit_logger and hasattr(self._audit_logger, 'log_tool_call'):
            self._audit_logger.log_tool_call(tool_name, tool_args)

        try:
            if asyncio.iscoroutinefunction(handler.execute):
                result = await handler.execute(tool_args, self._state, self.project_path)
            else:
                result = handler.execute(tool_args, self._state, self.project_path)

            # SECURITY: Scan tool output for injection patterns
            if self._injection_detector and isinstance(result, dict):
                result_str = json.dumps(result)
                if len(result_str) > 100:
                    detection = self._injection_detector.detect_in_file_content(result_str, tool_name)
                    if detection.threat_level.value in ("high", "critical"):
                        self._log(f"⚠️ Security: Injection pattern detected in {tool_name} output")

            # SECURITY: Monitor output for sensitive data leakage
            if self._output_monitor and isinstance(result, dict):
                result_str = json.dumps(result)
                monitor_result = self._output_monitor.check(result_str)
                if not monitor_result.safe:
                    self._log(f"🛡️ Security: Sensitive data in {tool_name} output")

            # Cache read-only results
            if cache_key and isinstance(result, dict):
                if len(self._tool_cache) >= self._tool_cache_max:
                    oldest_key = next(iter(self._tool_cache))
                    del self._tool_cache[oldest_key]
                self._tool_cache[cache_key] = result

            # Audit log success
            if self._audit_logger and hasattr(self._audit_logger, 'log_tool_call'):
                duration_ms = (time.time() - start_time) * 1000
                self._audit_logger.log_tool_call(
                    tool_name, tool_args, success=True,
                    result=json.dumps(result)[:500], duration_ms=duration_ms,
                )

            return result
        except Exception as e:
            error_result = {"error": f"Tool execution failed: {str(e)}", "traceback": traceback.format_exc()}
            self._log(f"Tool {tool_name} failed: {e}")
            if self._audit_logger and hasattr(self._audit_logger, 'log_tool_call'):
                duration_ms = (time.time() - start_time) * 1000
                self._audit_logger.log_tool_call(
                    tool_name, tool_args, success=False,
                    error=str(e), duration_ms=duration_ms,
                )

            if self._error_recovery:
                try:
                    recovered = await self._error_recovery.recover(tool_name, tool_args, e)
                    if recovered:
                        self._log(f"Error recovered for {tool_name}")
                        return recovered
                except Exception:
                    pass  # Intentional: error recovery failure is non-critical

            return error_result

    def _record_approval(self, tool_name: str, tool_args: dict, approved: bool, reason: str = "") -> None:
        """Record an approval decision."""
        if self._audit_logger and hasattr(self._audit_logger, 'log_approval'):
            self._audit_logger.log_approval(tool_name, tool_args, approved, reason)

    def get_approval_history(self) -> list[dict]:
        """Get approval history."""
        if self._audit_logger and hasattr(self._audit_logger, 'get_approvals'):
            return self._audit_logger.get_approvals()
        return []

    def _backup_file(self, file_path: str) -> str | None:
        """Create a backup of a file before modification."""
        try:
            if not os.path.exists(file_path):
                return None
            backup_dir = os.path.join(self.project_path, self._state.backup_dir)
            os.makedirs(backup_dir, exist_ok=True)
            import hashlib
            file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
            backup_name = f"cp_{int(time.time())}_{file_hash}"
            backup_path = os.path.join(backup_dir, backup_name)
            import shutil
            shutil.copy2(file_path, backup_path)
            # Save metadata
            meta_path = backup_path + ".meta"
            with open(meta_path, "w") as f:
                json.dump({"original_path": file_path, "timestamp": time.time()}, f)
            self._cleanup_old_checkpoints(backup_dir)
            return backup_path
        except Exception:
            return None

    def verify_file_integrity(self, file_path: str) -> dict:
        """Verify file hasn't been tampered with since backup."""
        try:
            backup_dir = os.path.join(self.project_path, self._state.backup_dir)
            if not os.path.isdir(backup_dir):
                return {"verified": True, "reason": "no backups"}
            backups = sorted([f for f in os.listdir(backup_dir) if not f.endswith(".meta")])
            if not backups:
                return {"verified": True, "reason": "no backups"}
            latest = os.path.join(backup_dir, backups[-1])
            meta_path = latest + ".meta"
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                if meta.get("original_path") == file_path:
                    import hashlib
                    with open(latest, "rb") as f:
                        backup_hash = hashlib.md5(f.read()).hexdigest()
                    with open(file_path, "rb") as f:
                        current_hash = hashlib.md5(f.read()).hexdigest()
                    return {"verified": backup_hash == current_hash, "reason": "hash match" if backup_hash == current_hash else "hash mismatch"}
            return {"verified": True, "reason": "no matching backup"}
        except Exception:
            return {"verified": True, "reason": "verification error"}

    def undo_last(self) -> dict:
        """Undo the last file edit."""
        try:
            backup_dir = os.path.join(self.project_path, self._state.backup_dir)
            if not os.path.isdir(backup_dir):
                return {"success": False, "message": "No backups found"}
            backups = sorted([f for f in os.listdir(backup_dir) if not f.endswith(".meta")])
            if not backups:
                return {"success": False, "message": "No backups found"}
            latest = backups[-1]
            backup_path = os.path.join(backup_dir, latest)
            meta_path = backup_path + ".meta"
            if not os.path.exists(meta_path):
                return {"success": False, "message": "Backup metadata missing"}
            with open(meta_path) as f:
                meta = json.load(f)
            original_path = meta["original_path"]
            import shutil
            shutil.copy2(backup_path, original_path)
            return {"success": True, "message": f"Restored {original_path}", "backup_path": backup_path}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def redo_last(self) -> dict:
        """Redo the last undone edit (placeholder)."""
        return {"success": False, "message": "Redo not yet implemented"}

    def save_plan(self, plan: list[dict]) -> None:
        """Save an execution plan."""
        plan_path = os.path.join(self.project_path, ".dev", "plan.json")
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)

    def load_plan(self) -> list[dict]:
        """Load the execution plan."""
        plan_path = os.path.join(self.project_path, ".dev", "plan.json")
        if os.path.exists(plan_path):
            with open(plan_path) as f:
                return json.load(f)
        return []

    def update_plan_item(self, item_index: int, status: str, notes: str = "") -> bool:
        """Update a plan item's status."""
        plan = self.load_plan()
        if 0 <= item_index < len(plan):
            plan[item_index]["status"] = status
            if notes:
                plan[item_index]["notes"] = notes
            self.save_plan(plan)
            return True
        return False
