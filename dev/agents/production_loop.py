"""
Production Agent Loop for Dev — the CORE of the entire agent.

Modeled after Claude Code's run.ts + Aider's base_coder.py.
Every chat/run/headless command flows through here.

Features:
- Streaming with retry + exponential backoff
- Approval mode enforcement (suggest/auto-edit/full-auto)
- Plan mode enforcement (read-only tools only)
- File backup before edits (undo/redo support)
- Auto-compact when context > 80%
- Auto-lint, auto-test, auto-commit after edits
- Hook system (pre/post tool execution)
- Auto-memory injection into system prompt
- Git diff display after edits
- Verbose logging throughout
- Proper token counting
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional


@dataclass
class Message:
    """A chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""
    _cached_tokens: int = field(default=-1, repr=False)

    def estimated_tokens(self) -> int:
        """Estimate token count with caching."""
        if self._cached_tokens == -1:
            self._cached_tokens = len(self.content) // 3 + 4
            if self.tool_calls:
                self._cached_tokens += len(json.dumps(self.tool_calls)) // 3
        return self._cached_tokens


@dataclass
class LoopConfig:
    """Agent configuration."""
    model: str = "default"
    temperature: float = 0.7
    max_tokens: int = 4096
    max_retries: int = 5
    retry_delay: float = 0.25
    max_retry_delay: float = 30.0
    auto_lint: bool = True
    auto_test: bool = False
    auto_commit: bool = True
    verbose: bool = False
    show_diffs: bool = True
    use_repo_map: bool = True
    repo_map_tokens: int = 1024
    max_context_tokens: int = 128_000  # NVIDIA NIM context window
    approval_mode: str = "auto-edit"  # suggest, auto-edit, full-auto
    enforce_plan_mode: bool = False  # If True, only read-only actions allowed


@dataclass
class EditResult:
    """Result of applying an edit."""
    success: bool
    file_path: str = ""
    error: str = ""
    diff: str = ""
    lint_errors: list[str] = field(default_factory=list)
    test_passed: bool = True


@dataclass
class LoopState:
    """Mutable state for an agent run."""
    messages: list[Message] = field(default_factory=list)
    done_messages: list[Message] = field(default_factory=list)
    cur_messages: list[Message] = field(default_factory=list)
    fnames: set[str] = field(default_factory=set)
    abs_fnames: set[str] = field(default_factory=set)
    abs_read_only_fnames: set[str] = field(default_factory=set)
    total_cost: float = 0.0
    total_tokens_sent: int = 0
    total_tokens_received: int = 0
    num_exhausted_context_windows: int = 0
    num_malformed_responses: int = 0
    num_reflections: int = 0
    max_reflections: int = 3
    last_commit_hash: str = ""
    edited_files: set[str] = field(default_factory=set)
    backup_dir: str = ".dev/checkpoints"
    seen_tool_ids: set[str] = field(default_factory=set)


# Tools that modify the filesystem (need approval/backup)
MODIFYING_TOOLS = frozenset({
    "write_file", "str_replace", "apply_patch", "edit_block",
    "run_terminal_command", "docker_run", "sandboxed_run",
    "git_operations",
})

# Tools that are read-only (always allowed in plan mode)
READ_ONLY_TOOLS = frozenset({
    "read_files", "code_search", "glob", "list_directory",
    "repo_map", "context_stats", "summarize",
    "web_search", "read_url",
    "browser_screenshot",  # screenshot is read-only, but navigate/click are not
    "list_apis", "list_mcp_servers", "free_api",
    "sandbox_status", "generate_diagram", "write_todos",
    "task_completed",
})

# Commit-triggering tools
COMMIT_TOOLS = frozenset({
    "write_file", "str_replace", "apply_patch", "edit_block",
})

# Tools that should NOT run in parallel (write operations, side effects)
DANGEROUS_TOOLS = frozenset({
    "run_terminal_command", "sandboxed_run", "docker_run", "docker_build",
    "git_operations", "write_file", "str_replace", "apply_patch", "edit_block",
    "multi_edit", "browser_click", "browser_navigate",
})

# Dangerous terminal command patterns
DANGEROUS_COMMANDS = [
    "rm -rf /", "rm -r /", "dd if=", "mkfs", "> /dev/sd",
    "shutdown", "reboot", "format c:", ":(){ :|:& };:",
    "chmod -R 777 /", "wget", "curl|sh", "curl|bash",
]


class ProductionAgentLoop:
    """
    Production-quality agent loop — the brain of Dev.

    Modeled after Claude Code's run.ts with Aider-style context management.
    Every interaction flows through here.
    """

    def __init__(
        self,
        provider: Any,
        tool_registry: Any,
        config: LoopConfig | None = None,
        project_path: str = ".",
    ):
        self.provider = provider
        self.tools = tool_registry
        self.config = config or LoopConfig()
        self.project_path = os.path.abspath(project_path)
        self._state = LoopState()
        self._abort = False
        self._checkpoint_id = 0
        self._on_tool_call = None
        self._on_tool_result = None
        self._interactive_allowed = True
        self._on_approval_prompt = None
        self._hook_manager = None
        self._error_recovery = None
        self._tool_rules = None
        self._budget_manager = None
        self._session_id = None
        self._session_history = None

    def set_approval_prompt(self, callback):
        """Set a callback for interactive approval prompts."""
        self._on_approval_prompt = callback

    def set_hook_manager(self, hook_manager):
        """Set the hook manager for pre/post tool hooks."""
        self._hook_manager = hook_manager

    def set_error_recovery(self, error_recovery):
        """Set the error recovery system."""
        self._error_recovery = error_recovery

    def set_tool_rules(self, tool_rules):
        """Set the tool rules manager."""
        self._tool_rules = tool_rules

    def set_budget_manager(self, budget_manager):
        """Set the budget manager."""
        self._budget_manager = budget_manager

    def set_session(self, session_id: str, session_history):
        """Set session ID and history for persistence."""
        self._session_id = session_id
        self._session_history = session_history

    def _log(self, msg: str):
        """Verbose logging — only prints when verbose mode is on."""
        if self.config.verbose:
            print(f"[dev:verbose] {msg}")

    def abort(self):
        """Abort the current run."""
        self._abort = True

    def reset(self):
        """Reset the agent state."""
        self._state = LoopState()
        self._abort = False
        self._checkpoint_id = 0

    def get_state(self) -> LoopState:
        """Get current state (for external inspection)."""
        return self._state

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    async def run(
        self,
        prompt: str,
        system_prompt: str = "",
        repo_map: str = "",
        files: list[str] | None = None,
        max_steps: int = 50,
        on_tool_call: Callable | None = None,
        on_tool_result: Callable | None = None,
    ) -> dict:
        """
        Run the agent loop (non-streaming, with full feature parity to run_streaming).

        Features:
        - Retry with exponential backoff on API errors
        - Error recovery for tool failures
        - Auto-compact when context > 80%
        - Git diff display after edits
        - File backup before edits
        - Hook system (pre/post tool execution)
        - Verbose logging throughout
        """
        self._abort = False

        if files:
            for f in files:
                abs_f = os.path.join(self.project_path, f)
                self._state.fnames.add(f)
                self._state.abs_fnames.add(abs_f)

        self._state.cur_messages.append(
            Message(role="user", content=prompt)
        )

        full_system = self._build_system_prompt(system_prompt, repo_map)
        all_tool_calls = []
        all_tool_results = []
        reflection_count = 0
        last_error = None

        for step in range(max_steps):
            if self._abort:
                return {"status": "aborted", "step": step}

            self._log(f"Step {step + 1}/{max_steps}, context tokens: ~{self._count_tokens(self._state.done_messages + self._state.cur_messages):,}")

            messages = self._format_messages(full_system)
            messages = self._prune_if_needed(messages, full_system)

            # Auto-compact if context is getting full
            await self._auto_compact_if_needed(messages, full_system)

            # Re-format after potential compaction
            messages = self._format_messages(full_system)

            response = await self._call_llm_with_retries(messages)

            if not response:
                return {"status": "error", "message": "No response from LLM after retries"}

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            self._state.cur_messages.append(
                Message(role="assistant", content=content, tool_calls=tool_calls)
            )

            if not tool_calls and content:
                self._state.done_messages.extend(self._state.cur_messages)
                self._state.cur_messages = []
                return {
                    "status": "completed",
                    "content": content,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "steps": step + 1,
                    "cost": self._state.total_cost,
                    "tokens_sent": self._state.total_tokens_sent,
                    "tokens_received": self._state.total_tokens_received,
                }

            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    try:
                        raw_args = tc.get("function", {}).get("arguments", "{}")
                        tool_args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError as e:
                        self._log(f"JSON parse error for {tool_name}: {e}")
                        tool_args = {}
                    if not isinstance(tool_args, dict):
                        tool_args = {}

                    # Check approval + plan mode
                    approval = self._check_tool_allowed(tool_name, tool_args)
                    if not approval["allowed"]:
                        if self.config.approval_mode == "suggest" and self._interactive_allowed:
                            approved = await self._prompt_user_approval(tool_name, tool_args)
                            if not approved:
                                self._state.cur_messages.append(
                                    Message(role="tool", tool_call_id=tc.get("id", ""),
                                            name=tool_name,
                                            content=json.dumps({"blocked": "User rejected"}))
                                )
                                continue
                        else:
                            self._state.cur_messages.append(
                                Message(role="tool", tool_call_id=tc.get("id", ""),
                                        name=tool_name,
                                        content=json.dumps({"blocked": approval["reason"]}))
                            )
                            continue

                    # Backup file before modifications
                    if tool_name in COMMIT_TOOLS:
                        file_path = tool_args.get("path", "")
                        if file_path:
                            self._backup_file(file_path)

                    if on_tool_call:
                        on_tool_call(tool_name, tool_args)

                    result = await self._execute_tool_with_hooks(tool_name, tool_args, tc.get("id", ""))

                    if on_tool_result:
                        on_tool_result(tool_name, result)

                    all_tool_calls.append({"name": tool_name, "args": tool_args})
                    all_tool_results.append({"name": tool_name, "result": result})

                    # Truncate large tool results
                    result_str = json.dumps(result)
                    MAX_TOOL_RESULT_CHARS = 50000
                    if len(result_str) > MAX_TOOL_RESULT_CHARS:
                        result_str = result_str[:MAX_TOOL_RESULT_CHARS] + f"\n\n... [Truncated: {len(json.dumps(result)):,} chars total]"

                    self._state.cur_messages.append(
                        Message(
                            role="tool",
                            tool_call_id=tc.get("id", ""),
                            name=tool_name,
                            content=result_str,
                        )
                    )

                    # Track edited files
                    if tool_name in COMMIT_TOOLS:
                        edited_path = tool_args.get("path", "")
                        if edited_path:
                            self._state.edited_files.add(edited_path)

                    # Auto-lint after file changes
                    if self.config.auto_lint and tool_name in COMMIT_TOOLS:
                        lint_result = await self._auto_lint(tool_args)
                        if lint_result and lint_result.get("errors"):
                            self._log(f"Lint errors: {lint_result['errors']}")

                    # Auto-commit after file changes
                    if self.config.auto_commit and tool_name in COMMIT_TOOLS:
                        commit_result = await self._auto_commit()
                        if commit_result and commit_result.get("success"):
                            self._log(f"Auto-committed: {commit_result.get('hash', 'ok')}")

            # Show git diff after all tool calls in this step
            if self.config.show_diffs and all_tool_calls:
                self._show_git_diff()

            # Save session state after each step
            await self._save_session()

            # Check reflection loop
            if last_error and last_error == content:
                reflection_count += 1
                if reflection_count >= self.config.max_reflections:
                    return {
                        "status": "stuck",
                        "message": "Agent stuck in reflection loop",
                        "last_error": content,
                    }
            else:
                reflection_count = 0
                last_error = content

        # Check for pending partial tool calls on MAX_STEPS
        partial_warning = None
        if self._state.cur_messages:
            last_msg = self._state.cur_messages[-1]
            if last_msg.role == "assistant" and last_msg.tool_calls:
                partial_warning = f"Agent stopped at MAX_STEPS with {len(last_msg.tool_calls)} unexecuted tool call(s). Results may be incomplete."
                self._log(partial_warning)

        return {
            "status": "max_steps",
            "steps": max_steps,
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "warning": partial_warning,
        }

    async def run_streaming(
        self,
        prompt: str,
        system_prompt: str = "",
        repo_map: str = "",
        on_tool_call: Callable | None = None,
        on_tool_result: Callable | None = None,
        on_text: Callable | None = None,
        max_steps: int = 50,
    ) -> dict:
        """
        Run the agent with streaming AND tool execution.

        This is the PRIMARY entry point for interactive chat.
        Streams text token-by-token, executes tools inline, loops until done.

        Features (modeled after Claude Code):
        - Retry with exponential backoff on API errors
        - Error recovery for tool failures
        - Auto-compact when context > 80%
        - Git diff display after edits
        - Verbose logging throughout
        """
        self._abort = False
        self._on_tool_call = on_tool_call
        self._on_tool_result = on_tool_result

        self._state.cur_messages.append(
            Message(role="user", content=prompt)
        )

        full_system = self._build_system_prompt(system_prompt, repo_map)
        all_tool_calls = []
        all_tool_results = []
        final_content = ""

        for step in range(max_steps):
            if self._abort:
                return {"status": "aborted", "step": step}

            self._log(f"Step {step + 1}/{max_steps}, context tokens: ~{self._count_tokens(self._state.done_messages + self._state.cur_messages):,}")

            messages = self._format_messages(full_system)
            messages = self._prune_if_needed(messages, full_system)

            # Auto-compact if context is getting full
            await self._auto_compact_if_needed(messages, full_system)

            # Re-format after potential compaction
            messages = self._format_messages(full_system)

            # Convert to dicts for API
            msg_dicts = self._messages_to_dicts(messages)

            # Get tool definitions — always include them
            tool_defs = self.tools.get_definitions()
            self._log(f"Sending {len(msg_dicts)} messages, {len(tool_defs)} tool schemas to LLM")

            # Stream the response WITH retry logic
            full_content = ""
            tool_calls_data = []
            stream_success = False
            last_error = None
            # Checkpoint message count before retry — rollback on failure to prevent duplicates
            msg_checkpoint = len(self._state.cur_messages)

            # Budget check before LLM call
            if self._budget_manager:
                budget_status = self._budget_manager.check_budget()
                if not budget_status["allowed"]:
                    self._log(f"Budget limit: {budget_status['reason']}")
                    return {
                        "status": "budget_exceeded",
                        "message": budget_status["reason"],
                        "budget": budget_status,
                        "tool_calls": all_tool_calls,
                        "tool_results": all_tool_results,
                        "steps": step + 1,
                    }
                self._budget_manager.record_request()

            for attempt in range(self.config.max_retries):
                try:
                    full_content = ""
                    tool_calls_data = []

                    async for event in self.provider.chat_completion_stream_events(
                        messages=msg_dicts,
                        model=self.config.model,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_tokens,
                        tools=tool_defs if tool_defs else None,
                    ):
                        if self._abort:
                            break

                        event_type = event.get("type", "")

                        if event_type == "text":
                            text_chunk = event.get("content", "")
                            full_content += text_chunk
                            if on_text:
                                on_text(text_chunk)

                        elif event_type == "tool_call":
                            tool_calls_data.append(event.get("tool_call", {}))

                        elif event_type == "usage":
                            usage = event.get("usage", {})
                            self._state.total_tokens_sent += usage.get("prompt_tokens", 0)
                            self._state.total_tokens_received += usage.get("completion_tokens", 0)

                    stream_success = True
                    break  # Success — exit retry loop

                except Exception as e:
                    last_error = str(e)

                    # On 400 (context length exceeded), shrink the context window and retry
                    if "400" in last_error or "context" in last_error.lower():
                        old_limit = self.config.max_context_tokens
                        self.config.max_context_tokens = int(old_limit * 0.7)
                        self._log(f"Context too large — reducing limit from {old_limit:,} to {self.config.max_context_tokens:,} tokens")
                        # Prune aggressively before retrying
                        self._state.cur_messages = self._state.cur_messages[-4:]
                        if self._state.done_messages:
                            self._state.done_messages = self._state.done_messages[-2:]
                        continue

                    is_retryable = any(
                        kw in last_error.lower()
                        for kw in ["rate", "timeout", "502", "503", "504",
                                   "overloaded", "econnrefused", "econnreset",
                                   "connection", "network", "reset"]
                    )

                    if not is_retryable:
                        self._log(f"Non-retryable error: {last_error}")
                        break

                    retry_delay = min(
                        self.config.retry_delay * (2 ** attempt),
                        self.config.max_retry_delay,
                    )
                    self._log(f"Retry {attempt + 1}/{self.config.max_retries} after {retry_delay:.1f}s: {last_error}")

                    if on_text:
                        on_text(f"\n⚠️ Retrying... ({attempt + 1}/{self.config.max_retries})\n")

                    await asyncio.sleep(retry_delay)

            if not stream_success:
                # Rollback to checkpoint to prevent duplicate messages on retry
                self._state.cur_messages = self._state.cur_messages[:msg_checkpoint]
                error_msg = f"LLM call failed after {self.config.max_retries} retries: {last_error}"
                self._log(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "steps": step + 1,
                }

            # Add assistant message to history
            self._state.cur_messages.append(
                Message(role="assistant", content=full_content, tool_calls=tool_calls_data)
            )

            # No tool calls = done
            if not tool_calls_data:
                final_content = full_content
                self._state.done_messages.extend(self._state.cur_messages)
                self._state.cur_messages = []

                return {
                    "status": "completed",
                    "content": final_content,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "steps": step + 1,
                    "cost": self._state.total_cost,
                    "tokens_sent": self._state.total_tokens_sent,
                    "tokens_received": self._state.total_tokens_received,
                }

            # Execute tool calls
            # Cap tool calls per turn to prevent context overflow
            MAX_TOOL_CALLS_PER_TURN = 10
            if len(tool_calls_data) > MAX_TOOL_CALLS_PER_TURN:
                self._log(f"Warning: LLM requested {len(tool_calls_data)} tools. Capping at {MAX_TOOL_CALLS_PER_TURN}.")
                tool_calls_data = tool_calls_data[:MAX_TOOL_CALLS_PER_TURN]

            # Separate read-only and write tools for parallel execution
            read_only_tcs = []
            write_tcs = []
            for tc in tool_calls_data:
                tn = tc.get("function", {}).get("name", "")
                if tn in READ_ONLY_TOOLS and tn not in DANGEROUS_TOOLS:
                    read_only_tcs.append(tc)
                else:
                    write_tcs.append(tc)

            # Execute read-only tools in parallel (up to 5 concurrent)
            if len(read_only_tcs) > 1:
                self._log(f"Parallel execution: {len(read_only_tcs)} read-only tools")
                async def _exec_read_only(rtc):
                    return await self._execute_single_tool(rtc, on_tool_call, on_tool_result)
                read_results = await asyncio.gather(
                    *[_exec_read_only(tc) for tc in read_only_tcs],
                    return_exceptions=True,
                )
                for tc, res in zip(read_only_tcs, read_results):
                    if isinstance(res, Exception):
                        res = {"error": str(res)}
                    # Results already added to cur_messages inside _execute_single_tool

            # Execute write tools sequentially
            for tc in write_tcs:
                tool_name = tc.get("function", {}).get("name", "")
                try:
                    raw_args = tc.get("function", {}).get("arguments", "{}")
                    tool_args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as e:
                    self._log(f"JSON parse error for {tool_name}: {e}")
                    tool_args = {}
                if not isinstance(tool_args, dict):
                    tool_args = {}

                # Check approval + plan mode
                approval = self._check_tool_allowed(tool_name, tool_args)
                if not approval["allowed"]:
                    if self.config.approval_mode == "suggest" and self._interactive_allowed:
                        approved = await self._prompt_user_approval(tool_name, tool_args)
                        if not approved:
                            blocked_result = {"blocked": "User rejected"}
                            if on_tool_result:
                                on_tool_result(tool_name, blocked_result)
                            self._state.cur_messages.append(
                                Message(role="tool", tool_call_id=tc.get("id", ""),
                                        name=tool_name, content=json.dumps(blocked_result))
                            )
                            continue
                    else:
                        blocked_result = {"blocked": approval["reason"]}
                        if on_tool_result:
                            on_tool_result(tool_name, blocked_result)
                        self._state.cur_messages.append(
                            Message(role="tool", tool_call_id=tc.get("id", ""),
                                    name=tool_name, content=json.dumps(blocked_result))
                        )
                        continue

                # Backup file before modifications
                if tool_name in COMMIT_TOOLS:
                    file_path = tool_args.get("path", "")
                    if file_path:
                        self._backup_file(file_path)

                if on_tool_call:
                    on_tool_call(tool_name, tool_args)

                # Check if tool exists in registry
                if tool_name not in self.tools:
                    result = {"error": f"Tool '{tool_name}' does not exist. Available: {list(self.tools.keys())}"}
                    self._state.cur_messages.append(
                        Message(role="tool", tool_call_id=tc.get("id", ""),
                                name=tool_name, content=json.dumps(result))
                    )
                    if on_tool_result:
                        on_tool_result(tool_name, result)
                    continue

                # Check tool rules (allow/deny)
                if self._tool_rules:
                    rule_check = self._tool_rules.check_tool(tool_name)
                    if not rule_check["allowed"]:
                        result = {"blocked": rule_check["reason"]}
                        if on_tool_result:
                            on_tool_result(tool_name, result)
                        self._state.cur_messages.append(
                            Message(role="tool", tool_call_id=tc.get("id", ""),
                                    name=tool_name, content=json.dumps(result))
                        )
                        continue

                # Execute with hooks + error recovery
                result = await self._execute_tool_with_hooks(tool_name, tool_args, tc.get("id", ""))

                if on_tool_result:
                    on_tool_result(tool_name, result)

                all_tool_calls.append({"name": tool_name, "args": tool_args})
                all_tool_results.append({"name": tool_name, "result": result})

                # Update tc args to reflect any mutations from hooks
                tc["function"]["arguments"] = json.dumps(tool_args)

                # Truncate large tool results to prevent context overflow
                result_str = json.dumps(result)
                MAX_TOOL_RESULT_CHARS = 50000  # ~16K tokens
                if len(result_str) > MAX_TOOL_RESULT_CHARS:
                    result_str = result_str[:MAX_TOOL_RESULT_CHARS] + f"\n\n... [Truncated: {len(json.dumps(result)):,} chars total, showing first {MAX_TOOL_RESULT_CHARS:,}]"
                    self._log(f"Tool {tool_name} result truncated from {len(json.dumps(result)):,} to {MAX_TOOL_RESULT_CHARS:,} chars")

                # Add tool result to history
                self._state.cur_messages.append(
                    Message(
                        role="tool",
                        tool_call_id=tc.get("id", ""),
                        name=tool_name,
                        content=result_str,
                    )
                )

                # Track edited files
                if tool_name in COMMIT_TOOLS:
                    edited_path = tool_args.get("path", "")
                    if edited_path:
                        self._state.edited_files.add(edited_path)

                # Auto-lint after file changes
                if self.config.auto_lint and tool_name in COMMIT_TOOLS:
                    lint_result = await self._auto_lint(tool_args)
                    if lint_result and lint_result.get("errors"):
                        self._log(f"Lint errors: {lint_result['errors']}")

                    # Check for missing dependencies
                    dep_suggestions = await self._check_dependencies(tool_args)
                    if dep_suggestions:
                        self._log(f"Dependency suggestions: {dep_suggestions}")

                # Auto-commit after file changes
                if self.config.auto_commit and tool_name in COMMIT_TOOLS:
                    commit_result = await self._auto_commit()
                    if commit_result and commit_result.get("success"):
                        self._log(f"Auto-committed: {commit_result.get('hash', 'ok')}")

            # Show git diff after all tool calls in this step
            if self.config.show_diffs and all_tool_calls:
                self._show_git_diff()

            # Save session state after each step
            await self._save_session()

            # Auto-learn from session (last step only to avoid overhead)
            if step == max_steps - 1 or not tool_calls_data:
                await self._learn_from_session()

        # Check for pending partial tool calls on MAX_STEPS
        partial_warning = None
        if self._state.cur_messages:
            last_msg = self._state.cur_messages[-1]
            if last_msg.role == "assistant" and last_msg.tool_calls:
                partial_warning = f"Agent stopped at MAX_STEPS with {len(last_msg.tool_calls)} unexecuted tool call(s). Results may be incomplete."
                self._log(partial_warning)

        return {
            "status": "max_steps",
            "steps": max_steps,
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "warning": partial_warning,
        }

    # =========================================================================
    # Tool Execution with Hooks + Error Recovery
    # =========================================================================

    async def _execute_tool_with_hooks(self, tool_name: str, tool_args: dict, call_id: str = "") -> Any:
        """Execute a tool with pre/post hooks and error recovery."""
        # Run pre-hooks
        if self._hook_manager:
            try:
                await self._hook_manager.run_hooks("pre_tool_use", {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                })
            except Exception as e:
                self._log(f"Pre-hook error: {e}")

        # Execute the tool
        result = await self._execute_tool(tool_name, tool_args)

        # Run post-hooks
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
            result_str = result_str[:MAX_TOOL_RESULT_CHARS] + f"\n\n... [Truncated]"

        self._state.cur_messages.append(
            Message(role="tool", tool_call_id=tc.get("id", ""),
                    name=tool_name, content=result_str)
        )
        return result

    # =========================================================================
    # Approval & Plan Mode Enforcement
    # =========================================================================

    def _check_tool_allowed(self, tool_name: str, tool_args: dict) -> dict:
        """
        Check if a tool call is allowed based on approval mode and plan mode.

        Returns {"allowed": True/False, "reason": "..."}
        """
        # Plan mode: only read-only tools allowed
        if self.config.enforce_plan_mode:
            if tool_name not in READ_ONLY_TOOLS:
                return {
                    "allowed": False,
                    "reason": f"Plan mode: '{tool_name}' is a write operation. Switch to act mode to execute.",
                }

        # Approval modes
        mode = self.config.approval_mode

        if mode == "full-auto":
            return {"allowed": True, "reason": "full-auto: auto-approved"}

        if mode == "suggest":
            # Suggest mode: only read-only tools auto-approved
            if tool_name in READ_ONLY_TOOLS:
                return {"allowed": True, "reason": "suggest: read-only tool auto-approved"}
            return {
                "allowed": False,
                "reason": f"suggest mode: '{tool_name}' requires user approval. Use /approve auto-edit or /approve full-auto.",
            }

        if mode == "auto-edit":
            # Auto-edit: file edits auto-approved, dangerous commands need approval
            if tool_name in READ_ONLY_TOOLS:
                return {"allowed": True, "reason": "auto-edit: read-only auto-approved"}
            if tool_name in COMMIT_TOOLS:
                return {"allowed": True, "reason": "auto-edit: file edit auto-approved"}
            # Terminal commands — check for dangerous patterns
            if tool_name == "run_terminal_command":
                cmd = tool_args.get("command", "")
                for pattern in DANGEROUS_COMMANDS:
                    if pattern in cmd:
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: dangerous command detected: '{pattern}'. Use /approve full-auto.",
                        }
                return {"allowed": True, "reason": "auto-edit: terminal command auto-approved"}
            if tool_name == "git_operations":
                action = tool_args.get("action", "")
                if action in ("push",):
                    return {
                        "allowed": False,
                        "reason": "auto-edit: git push requires approval. Use /approve full-auto.",
                    }
                return {"allowed": True, "reason": "auto-edit: git operation auto-approved"}
            return {"allowed": True, "reason": "auto-edit: tool auto-approved"}

        return {"allowed": True, "reason": "default: allowed"}

    async def _prompt_user_approval(self, tool_name: str, tool_args: dict) -> bool:
        """Prompt user for approval in suggest mode (async-safe)."""
        if self._on_approval_prompt:
            # Run the potentially blocking prompt in a thread to avoid blocking the event loop
            return await asyncio.to_thread(self._on_approval_prompt, tool_name, tool_args)
        return False

    # =========================================================================
    # File Backup for Undo/Redo
    # =========================================================================

    MAX_CHECKPOINTS = 100

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
            pass

    def _backup_file(self, file_path: str) -> str | None:
        """Create a backup of a file before modification. Returns backup path."""
        abs_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(abs_path):
            return None

        backup_dir = os.path.join(self.project_path, self._state.backup_dir)
        os.makedirs(backup_dir, exist_ok=True)
        self._cleanup_old_checkpoints(backup_dir)

        self._checkpoint_id += 1
        safe_name = file_path.replace("/", "_").replace("\\", "_").replace(":", "_")
        backup_path = os.path.join(backup_dir, f"cp{self._checkpoint_id}_{safe_name}")

        try:
            temp_backup = backup_path + ".tmp"
            shutil.copy2(abs_path, temp_backup)
            os.replace(temp_backup, backup_path)
            # Save original path as .meta sidecar for undo
            with open(backup_path + ".meta", "w", encoding="utf-8") as f:
                f.write(abs_path)
            self._log(f"Backed up: {file_path} -> {backup_path}")
            return backup_path
        except Exception as e:
            self._log(f"Backup failed: {e}")
            return None

    def undo_last(self) -> dict:
        """Undo the last checkpoint (restore backed-up file)."""
        if self._checkpoint_id <= 0:
            return {"success": False, "message": "No checkpoints to undo"}

        backup_dir = os.path.join(self.project_path, self._state.backup_dir)
        if not os.path.isdir(backup_dir):
            return {"success": False, "message": "No backup directory"}

        # Find the most recent backup
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("cp")],
            reverse=True,
        )
        if not backups:
            return {"success": False, "message": "No backup files"}

        latest = backups[0]
        safe_name = latest.split("_", 1)[1] if "_" in latest else latest
        backup_path = os.path.join(backup_dir, latest)

        # Read the original path from .meta sidecar file
        meta_path = backup_path + ".meta"
        original_path = None
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                original_path = f.read().strip()

        if not original_path or not os.path.isfile(backup_path):
            return {"success": False, "message": "Backup file not found"}

        # Actually restore the file
        try:
            shutil.copy2(backup_path, original_path)
            return {
                "success": True,
                "message": f"Restored: {original_path}",
                "restored": original_path,
                "from_backup": backup_path,
            }
        except Exception as e:
            return {"success": False, "message": f"Restore failed: {e}"}

    # =========================================================================
    # Auto-Compact (Claude Code pattern)
    # =========================================================================

    async def _auto_compact_if_needed(self, messages: list[Message], system_prompt: str):
        """Auto-compact context when usage exceeds 80%."""
        tokens = self._count_tokens(messages)
        threshold = self.config.max_context_tokens * 0.8

        if tokens <= threshold or len(self._state.done_messages) <= 6:
            return

        self._log(f"Auto-compact triggered: {tokens:,} tokens ({tokens / self.config.max_context_tokens * 100:.0f}% of {self.config.max_context_tokens:,})")

        # Compact: summarize old messages, keep recent ones
        if len(self._state.done_messages) > 6:
            # Summarize all but last 6 done messages
            old_msgs = self._state.done_messages[:-6]
            keep_msgs = self._state.done_messages[-6:]

            summary_parts = []
            for msg in old_msgs:
                if msg.role == "user":
                    summary_parts.append(f"User: {msg.content[:200]}")
                elif msg.role == "assistant" and msg.content:
                    summary_parts.append(f"Assistant: {msg.content[:200]}")
                elif msg.role == "tool":
                    tool_name = msg.name or "tool"
                    content_preview = msg.content[:100]
                    summary_parts.append(f"Tool({tool_name}): {content_preview}")

            summary_text = (
                "[Previous conversation summary — auto-compacted to save context]\n"
                + "\n".join(summary_parts[-30:])
                + "\n\n[End of summary. Continue from the live message below.]"
            )

            summary_msg = Message(role="system", content=summary_text)
            self._state.done_messages = [summary_msg] + keep_msgs

            new_tokens = self._count_tokens(self._state.done_messages + self._state.cur_messages)
            self._log(f"Auto-compact: {tokens:,} -> {new_tokens:,} tokens")

    # =========================================================================
    # Git Diff Display
    # =========================================================================

    def _show_git_diff(self):
        """Show git diff --stat after edits."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.stdout.strip():
                self._log(f"Git changes:\n{result.stdout.strip()}")
        except Exception:
            pass  # Not a git repo or git not available

    # =========================================================================
    # System Prompt & Context
    # =========================================================================

    def _build_system_prompt(self, base_prompt: str, repo_map: str = "") -> str:
        """Build the full system prompt with all context."""
        parts = []

        # Base prompt
        if base_prompt:
            parts.append(base_prompt)

        # Repo map
        if repo_map and self.config.use_repo_map:
            parts.append(f"\n\n## Repository Structure\n{repo_map}")

        # File list
        if self._state.fnames:
            file_list = "\n".join(f"- {f}" for f in sorted(self._state.fnames))
            parts.append(f"\n\n## Files in Chat\n{file_list}")

        # Project rules (DEV.md, .devrules, .dev/)
        rules = self._load_project_rules()
        if rules:
            parts.append(f"\n\n## Project Rules\n{rules}")
            parts.append("\n\n**Rule Precedence:** .devrules overrides DEV.md. When rules conflict, follow the most specific source.")

        # Auto-memory from previous sessions
        memory = self._load_auto_memory()
        if memory:
            parts.append(f"\n\n## Auto Memory (learned from previous sessions)\n{memory}")

        # Git context
        git_ctx = self._get_git_context()
        if git_ctx:
            parts.append(f"\n\n## Git Status\n{git_ctx}")

        # Plan mode notice
        if self.config.enforce_plan_mode:
            parts.append("\n\n## CURRENT MODE: PLAN (read-only)\nYou can ONLY use read-only tools. To make changes, the user must switch to act mode.")

        return "\n".join(parts)

    def _load_project_rules(self) -> str:
        """Load project rules from DEV.md, .devrules, and .dev/ directory."""
        parts = []

        # 1. DEV.md (like CLAUDE.md — the primary project instructions file)
        for devmd_name in ["DEV.md", "CLAUDE.md", ".dev.md"]:
            devmd_path = os.path.join(self.project_path, devmd_name)
            if os.path.isfile(devmd_path):
                try:
                    with open(devmd_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if "@import" in content:
                        content = self._resolve_imports(content, self.project_path)
                    parts.append(f"## Project Instructions ({devmd_name})\n{content}")
                    break  # Only load one
                except Exception:
                    pass

        # 2. .devrules directory (multiple .md files)
        rules_dir = os.path.join(self.project_path, ".devrules")
        rules_file = os.path.join(self.project_path, ".devrules.md")

        if os.path.isfile(rules_file):
            try:
                with open(rules_file, "r", encoding="utf-8", errors="replace") as f:
                    parts.append(f.read())
            except Exception:
                pass

        if os.path.isdir(rules_dir):
            for fname in sorted(os.listdir(rules_dir)):
                if fname.endswith(".md"):
                    try:
                        fpath = os.path.join(rules_dir, fname)
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        if "@import" in content:
                            content = self._resolve_imports(content, rules_dir)
                        parts.append(f"### {fname}\n{content}")
                    except Exception:
                        pass

        return "\n\n".join(parts)

    def _load_auto_memory(self) -> str:
        """Load auto-memory from .dev/memory/auto_memory.md."""
        memory_file = os.path.join(self.project_path, ".dev", "memory", "auto_memory.md")
        if os.path.isfile(memory_file):
            try:
                with open(memory_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if content.strip():
                    return content
            except Exception:
                pass
        return ""

    def _resolve_imports(self, content: str, base_dir: str, _seen: set | None = None) -> str:
        """Resolve @import directives in rules files (with circular reference protection)."""
        import re
        if _seen is None:
            _seen = set()

        def replace_import(match):
            import_path = match.group(1).strip()
            full_path = os.path.normpath(os.path.join(base_dir, import_path))
            # Circular reference protection
            if full_path in _seen:
                return f"[circular import: {import_path}]"
            if os.path.isfile(full_path):
                _seen.add(full_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        file_content = f.read()
                    # Recursively resolve imports in imported file
                    file_dir = os.path.dirname(full_path)
                    return self._resolve_imports(file_content, file_dir, _seen)
                except Exception:
                    return f"[import failed: {import_path}]"
            return f"[import not found: {import_path}]"

        return re.sub(r'@import\s+["\'](.+?)["\']', replace_import, content)

    # =========================================================================
    # Message Formatting & Pruning
    # =========================================================================

    def _format_messages(self, system_prompt: str) -> list[Message]:
        """Format messages for the LLM."""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.extend(self._state.done_messages)
        messages.extend(self._state.cur_messages)
        return messages

    def _messages_to_dicts(self, messages: list[Message]) -> list[dict]:
        """Convert Message objects to API-compatible dicts.
        
        Some NIM endpoints reject messages with both content and tool_calls.
        Strip content when tool_calls are present to avoid 400 errors.
        """
        result = []
        for m in messages:
            md = {"role": m.role}
            # Strip content if tool_calls are present (avoids 400 on strict APIs)
            if m.tool_calls:
                md["tool_calls"] = m.tool_calls
                # Don't include content — some APIs reject hybrid messages
            else:
                md["content"] = m.content or ""
            if m.tool_call_id:
                md["tool_call_id"] = m.tool_call_id
            if m.name:
                md["name"] = m.name
            result.append(md)
        return result

    def _count_tokens(self, messages: list[Message]) -> int:
        """Estimate total token count across all messages."""
        import re
        total = 0
        for m in messages:
            content = m.content
            if content:
                # Dense text detection: minified code, base64, hex dumps
                # have much higher token density (1 char ~ 1 token)
                sample = content[:1000]
                if not re.search(r'\s', sample):
                    # No whitespace in first 1000 chars = dense text
                    total += len(content) // 2
                else:
                    # Normal text (~3 chars per token)
                    total += len(content) // 3
            # Tool calls
            if m.tool_calls:
                total += len(json.dumps(m.tool_calls)) // 3
            # Message overhead (~4 tokens per message)
            total += 4
        return total

    def _check_token_limits(self, messages: list[Message]) -> bool:
        """Check if messages fit within token limits."""
        estimated_tokens = self._count_tokens(messages)
        return estimated_tokens <= self.config.max_context_tokens

    def _prune_if_needed(self, messages: list[Message], system_prompt: str) -> list[Message]:
        """Prune messages if they exceed token limits.
        
        Strategy:
        1. Check if within limits — return as-is
        2. If over 80%, summarize old messages (auto-compact)
        3. If still over, truncate oldest messages
        """
        tokens = self._count_tokens(messages)
        threshold = self.config.max_context_tokens * 0.8

        if tokens <= threshold:
            return messages

        # Summarize old messages
        if len(messages) > 10:
            return self._prune_messages(messages, system_prompt)

        # Last resort: truncate
        return self._truncate_to_fit(messages)

    def _prune_messages(self, messages: list[Message], system_prompt: str) -> list[Message]:
        """Prune messages to fit within token limits."""
        if len(messages) <= 10:
            return self._truncate_to_fit(messages)

        # Keep system + last 8 messages
        system = [messages[0]] if messages[0].role == "system" else []
        recent = messages[-8:]
        middle = messages[len(system):-8] if system else messages[:-8]

        # Summarize middle into one message
        summary_parts = []
        for msg in middle:
            if msg.role == "user":
                summary_parts.append(f"User: {msg.content[:200]}")
            elif msg.role == "assistant" and msg.content:
                summary_parts.append(f"Assistant: {msg.content[:200]}")
            elif msg.role == "tool":
                tool_name = msg.name or "tool"
                content_preview = msg.content[:100]
                summary_parts.append(f"Tool({tool_name}): {content_preview}")
            elif msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("function", {}).get("name", "?")
                    summary_parts.append(f"Called: {name}")

        summary_text = (
            "[Previous conversation summary — original messages condensed to save context]\n"
            + "\n".join(summary_parts[-30:])
            + "\n\n[End of summary. Continue from the live message below.]"
        )

        summary_msg = Message(role="system", content=summary_text)
        pruned = system + [summary_msg] + recent

        return self._truncate_to_fit(pruned)

    def _truncate_to_fit(self, messages: list[Message]) -> list[Message]:
        """Brute-force truncation to fit within token limits.
        
        Keeps tool_call and tool_result pairs atomic — if we remove
        an assistant message with tool_calls, we also remove the
        corresponding tool result messages that follow it.
        """
        result = list(messages)
        while self._count_tokens(result) > self.config.max_context_tokens and len(result) > 3:
            # Remove the oldest non-system message
            if result[0].role == "system":
                result = [result[0]] + result[2:]
            else:
                # If removing an assistant with tool_calls, also remove
                # the following tool result messages
                removed = result[1]
                if removed.role == "assistant" and removed.tool_calls:
                    # Collect tool_call_ids from the assistant message
                    tc_ids = {tc.get("id", "") for tc in removed.tool_calls}
                    # Remove the assistant + all matching tool results
                    idx = 1
                    while idx < len(result) and result[idx].role == "tool" and result[idx].tool_call_id in tc_ids:
                        idx += 1
                    result = [result[0]] + result[idx:]
                else:
                    result = [result[0]] + result[1:]
        return result

    # =========================================================================
    # LLM Call with Retries
    # =========================================================================

    async def _call_llm_with_retries(self, messages: list[Message]) -> dict | None:
        """Call LLM with retry logic and exponential backoff."""
        retry_delay = self.config.retry_delay
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                msg_dicts = self._messages_to_dicts(messages)
                tool_defs = self.tools.get_definitions()

                response = await self.provider.chat_completion(
                    messages=msg_dicts,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    tools=tool_defs if tool_defs else None,
                )

                usage = response.get("usage", {})
                self._state.total_tokens_sent += usage.get("prompt_tokens", 0)
                self._state.total_tokens_received += usage.get("completion_tokens", 0)

                choice = response.get("choices", [{}])[0]
                message = choice.get("message", {})

                return {
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                    "finish_reason": choice.get("finish_reason", ""),
                }

            except Exception as e:
                last_error = str(e)

                # On 400 (context length exceeded), shrink context and retry
                if "400" in last_error or "context" in last_error.lower():
                    old_limit = self.config.max_context_tokens
                    self.config.max_context_tokens = int(old_limit * 0.7)
                    self._log(f"Context too large — reducing limit from {old_limit:,} to {self.config.max_context_tokens:,}")
                    self._state.cur_messages = self._state.cur_messages[-4:]
                    if self._state.done_messages:
                        self._state.done_messages = self._state.done_messages[-2:]
                    # Rebuild messages with smaller context and retry
                    messages = self._format_messages("")
                    continue

                is_retryable = any(
                    kw in last_error.lower()
                    for kw in ["rate", "timeout", "502", "503", "504",
                               "overloaded", "econnrefused", "econnreset"]
                )

                if not is_retryable:
                    self._log(f"Non-retryable error: {last_error}")
                    break

                retry_delay = min(retry_delay * 2, self.config.max_retry_delay)
                self._log(f"Retry {attempt + 1}/{self.config.max_retries} after {retry_delay:.1f}s: {last_error}")
                await asyncio.sleep(retry_delay)

        self._log(f"LLM call failed after {self.config.max_retries} retries: {last_error}")
        return None

    # =========================================================================
    # Tool Execution
    # =========================================================================

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> Any:
        """Execute a tool call with error handling."""
        handler = self.tools.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            if asyncio.iscoroutinefunction(handler.execute):
                result = await handler.execute(tool_args, self._state, self.project_path)
            else:
                result = handler.execute(tool_args, self._state, self.project_path)
            return result
        except Exception as e:
            error_result = {"error": f"Tool execution failed: {str(e)}", "traceback": traceback.format_exc()}
            self._log(f"Tool {tool_name} failed: {e}")

            # Try error recovery if available
            if self._error_recovery:
                try:
                    recovered = await self._error_recovery.recover(tool_name, tool_args, e)
                    if recovered:
                        self._log(f"Error recovered for {tool_name}")
                        return recovered
                except Exception:
                    pass

            return error_result

    # =========================================================================
    # Session Persistence
    # =========================================================================

    async def _save_session(self):
        """Save session state for resume support."""
        if not self._session_id or not self._session_history:
            return
        try:
            session_data = {
                "id": self._session_id,
                "messages": [
                    {"role": m.role, "content": m.content, "name": m.name,
                     "tool_call_id": m.tool_call_id}
                    for m in (self._state.done_messages + self._state.cur_messages)
                    if m.role in ("user", "assistant") and m.content
                ],
                "edited_files": list(self._state.edited_files),
                "total_tokens_sent": self._state.total_tokens_sent,
                "total_tokens_received": self._state.total_tokens_received,
            }
            await asyncio.to_thread(self._session_history.save_session, self._session_id, session_data)
        except Exception as e:
            self._log(f"Session save failed: {e}")

    # =========================================================================
    # Git-Aware Context
    # =========================================================================

    def _get_git_context(self) -> str:
        """Get git context for the system prompt (branch, status, recent commits)."""
        parts = []
        try:
            # Current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                parts.append(f"Branch: {branch}")

            # Staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.stdout.strip():
                parts.append(f"Staged changes:\n{result.stdout.strip()}")

            # Untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.stdout.strip():
                untracked = result.stdout.strip().split("\n")[:10]
                parts.append(f"Untracked files: {', '.join(untracked)}")

            # Recent commits (last 3)
            result = subprocess.run(
                ["git", "log", "--oneline", "-3"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.stdout.strip():
                parts.append(f"Recent commits:\n{result.stdout.strip()}")
        except Exception:
            pass  # Not a git repo or git not available

        return "\n".join(parts)

    # =========================================================================
    # Auto Quality Gates
    # =========================================================================

    async def _auto_lint(self, tool_args: dict) -> dict | None:
        """Auto-lint after file changes."""
        file_path = tool_args.get("path", "")
        if not file_path:
            return None

        try:
            from ..utils.quality_gates import AutoLinter
            linter = AutoLinter(self.project_path)
            # lint_file is async — check and call properly
            if asyncio.iscoroutinefunction(linter.lint_file):
                result = await linter.lint_file(file_path)
            else:
                result = linter.lint_file(file_path)

            # Handle result properly
            if hasattr(result, "errors"):
                errors = [e.get("message", "") if isinstance(e, dict) else str(e) for e in result.errors]
                return {"success": len(errors) == 0, "errors": errors}
            elif isinstance(result, dict):
                return result
            return {"success": True, "errors": []}
        except Exception as e:
            self._log(f"Auto-lint failed: {e}")
            return None

    async def _check_dependencies(self, tool_args: dict) -> list[str]:
        """Check if imports in a written file are available. Returns list of suggestions."""
        file_path = tool_args.get("path", "")
        if not file_path:
            return []

        abs_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.isfile(abs_path) or not file_path.endswith(".py"):
            return []

        suggestions = []
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            import re
            # Find import statements
            imports = re.findall(r'^(?:from\s+(\S+)|import\s+(\S+))', content, re.MULTILINE)
            for group in imports:
                module = group or group
                if not module:
                    continue
                # Skip stdlib modules (heuristic)
                top_level = module.split(".")[0]
                stdlib_modules = {
                    "os", "sys", "json", "re", "time", "datetime", "pathlib",
                    "asyncio", "subprocess", "shutil", "io", "base64", "hashlib",
                    "urllib", "http", "email", "html", "xml", "csv", "sqlite3",
                    "threading", "multiprocessing", "typing", "dataclasses", "enum",
                    "abc", "collections", "itertools", "functools", "operator",
                    "contextlib", "textwrap", "difflib", "fnmatch", "glob", "uuid",
                    "secrets", "hmac", "logging", "argparse", "configparser",
                    "struct", "socket", "ssl", "select", "signal", "stat",
                    "tempfile", "getpass", "platform", "ctypes", "pickle",
                }
                if top_level in stdlib_modules:
                    continue
                # Check if module is importable
                try:
                    __import__(top_level)
                except ImportError:
                    suggestions.append(f"Missing dependency: {top_level} (install with: pip install {top_level})")
        except Exception:
            pass

        return suggestions

    async def _learn_from_session(self):
        """Auto-learn rules from successful session interactions."""
        try:
            from ..utils.memory import AutoMemory
            memory = AutoMemory(self.project_path)

            # Learn from edited files (what patterns were used)
            for fpath in self._state.edited_files:
                ext = os.path.splitext(fpath)[1]
                if ext:
                    memory.remember(
                        f"edited_{ext}_files",
                        f"Successfully edited {ext} files in this project",
                        "pattern",
                    )

            # Learn from tool usage patterns
            tool_counts = {}
            for msg in self._state.done_messages:
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = tc.get("function", {}).get("name", "")
                        tool_counts[name] = tool_counts.get(name, 0) + 1
            for tool_name, count in tool_counts.items():
                if count >= 3:
                    memory.remember(
                        f"frequent_tool_{tool_name}",
                        f"Tool '{tool_name}' used {count} times — commonly needed for this project",
                        "pattern",
                    )

            # Learn project type from detector
            try:
                from ..utils.project_detector import ProjectDetector
                detector = ProjectDetector(self.project_path)
                info = detector.detect()
                if info.language != "unknown":
                    memory.remember(
                        "project_type",
                        f"Project: {info.language}/{info.framework} with {info.package_manager}",
                        "build",
                    )
            except Exception:
                pass

            self._log(f"Auto-memory updated: {len(memory.entries)} entries")
        except Exception as e:
            self._log(f"Auto-memory update failed: {e}")

    async def _auto_commit(self) -> dict | None:
        """Auto-commit after file changes."""
        try:
            from ..utils.auto_commit import AutoCommitter
            committer = AutoCommitter(self.project_path, self.provider)
            if asyncio.iscoroutinefunction(committer.auto_commit):
                return await committer.auto_commit()
            else:
                return committer.auto_commit()
        except Exception as e:
            self._log(f"Auto-commit failed: {e}")
            return None
