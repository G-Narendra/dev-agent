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
    diff_preview: bool = False  # Show diff before applying edits
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
        # Tool names to filter tool definitions (reduces tool count for LLM)
        self._tool_names: list[str] | None = None
        # Tool result cache: cache read-only tool results to avoid re-reading
        self._tool_cache: dict[str, dict] = {}  # cache_key -> result
        self._tool_cache_max = 50  # Max cached results
        # Audit logger for security-sensitive operations
        self._audit_logger = None
        try:
            from ..utils.security import AuditLogger
            self._audit_logger = AuditLogger(project_path)
        except Exception:
            pass
        # Approval history: track all approval decisions for review
        self._approval_history: list[dict] = []
        # Plan persistence
        self._plan_file = os.path.join(self.project_path, ".dev", "current_plan.json")

    def set_approval_prompt(self, callback):
        """Set a callback for interactive approval prompts."""
        self._on_approval_prompt = callback

    def set_hook_manager(self, hook_manager):
        """Set the hook manager for pre/post tool hooks."""
        self._hook_manager = hook_manager

    def set_tool_names(self, tool_names: list[str]):
        """Set the list of tool names to expose to the LLM.
        
        Limits tool definitions sent to the model, which is critical
        for models like Llama 3.1 70B that can only handle ~15-20 tools.
        """
        self._tool_names = tool_names

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
            try:
                from ..utils.logger import get_logger
                get_logger("dev.agent").debug(msg)
            except Exception:
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
                # Don't exit — try next step with a different approach
                self._log(f"No response from LLM at step {step + 1}, retrying...")
                self._state.cur_messages.append(
                    Message(role="user", content="Please continue with the task. If there was an error, try a different approach.")
                )
                continue

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            self._state.cur_messages.append(
                Message(role="assistant", content=content, tool_calls=tool_calls)
            )

            if not tool_calls and content:
                # Check if content has code blocks that should be file writes
                parsed_calls = self._parse_code_blocks(content)
                if parsed_calls:
                    self._log(f"Found {len(parsed_calls)} code blocks in text, converting to tool calls")
                    # Execute each parsed code block as a tool call
                    for pc in parsed_calls:
                        tool_name = pc["name"]
                        tool_args = pc["args"]
                        
                        if on_tool_call:
                            on_tool_call(tool_name, tool_args)
                        
                        result = await self._execute_tool_with_hooks(tool_name, tool_args, "parsed")
                        
                        if on_tool_result:
                            on_tool_result(tool_name, result)
                        
                        all_tool_calls.append({"name": tool_name, "args": tool_args})
                        all_tool_results.append({"name": tool_name, "result": result})
                        
                        result_str = json.dumps(result)
                        self._state.cur_messages.append(
                            Message(role="tool", tool_call_id="parsed",
                                    name=tool_name, content=result_str))
                        
                        if tool_name in COMMIT_TOOLS:
                            edited_path = tool_args.get("path", "")
                            if edited_path:
                                self._state.edited_files.add(edited_path)
                    
                    # Continue the loop — don't exit yet
                    continue
                
                # Check if there are pending todo items — if so, auto-continue
                if self._has_pending_todos(content):
                    self._log("Model returned text but has pending todos, auto-continuing")
                    self._state.cur_messages.append(
                        Message(role="user", content=
                            "You have unfinished tasks. Continue creating the remaining files "
                            "using write_file tool. Do NOT stop until all tasks are complete.")
                    )
                    continue
                
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

            # Get tool definitions — filter by tool_names if set (reduces for LLM)
            if self._tool_names and hasattr(self.tools, 'get_definitions_for_tools'):
                tool_defs = self.tools.get_definitions_for_tools(self._tool_names)
            else:
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

            # Clear tool cache between steps to avoid stale reads after edits
            if all_tool_calls:
                self._tool_cache.clear()

            for attempt in range(self.config.max_retries):
                try:
                    full_content = ""
                    tool_calls_data = []

                    # Use 70B for tool calls (8B truncates tool args)
                    effective_model = self.config.model
                    if tool_defs and '8b' in self.config.model.lower():
                        effective_model = 'meta/llama-3.1-70b-instruct'
                    
                    async for event in self.provider.chat_completion_stream_events(
                        messages=msg_dicts,
                        model=effective_model,
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
                        for kw in ["rate", "timeout", "500", "502", "503", "504",
                                   "overloaded", "econnrefused", "econnreset",
                                   "connection", "network", "reset"]
                    )

                    if not is_retryable:
                        self._log(f"Non-retryable error: {last_error}")
                        break

                    # On server errors, prune context to reduce payload size
                    if '500' in last_error:
                        old_limit = self.config.max_context_tokens
                        self.config.max_context_tokens = int(old_limit * 0.7)
                        self._log(f"Server error — reducing context from {old_limit:,} to {self.config.max_context_tokens:,}")
                        self._state.cur_messages = self._state.cur_messages[-6:]
                        if self._state.done_messages:
                            self._state.done_messages = self._state.done_messages[-3:]

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

            # If no tool calls from API, try to extract from text output
            if not tool_calls_data and full_content:
                parsed_calls = self._parse_text_tool_calls(full_content)
                if parsed_calls:
                    tool_calls_data = parsed_calls
                    self._log(f"Extracted {len(parsed_calls)} tool calls from text output")
                    # IMPORTANT: Update the assistant message so the model sees tool calls
                    self._state.cur_messages[-1] = Message(
                        role="assistant", content=full_content, tool_calls=tool_calls_data
                    )

            # Detect truncated write_file tool calls (NIM free tier limits tool arg tokens)
            if tool_calls_data:
                truncated = False
                for tc in tool_calls_data:
                    tn = tc.get("function", {}).get("name", "")
                    if tn == "write_file":
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            ct = args.get("content", "")
                            # Detect truncation: NIM free tier caps tool args severely
                            # Check if content looks like actual code vs a placeholder/description
                            if ct:
                                stripped = ct.strip()
                                # Common placeholder patterns that are NOT real code
                                # Detect placeholder/description content
                                placeholder_patterns = [
                                    '', 'TODO', 'placeholder', 'code here',
                                    'Add your', 'Write your', 'Insert your',
                                    'Put your', 'Add the', 'Write the',
                                ]
                                is_placeholder = any(p.lower() in stripped.lower() for p in placeholder_patterns)
                                is_comment_only = stripped.startswith('/*') and stripped.endswith('*/') and len(stripped) < 100
                                is_short = len(stripped) < 80
                                has_real_code = any(c in stripped for c in '{}()=;<>[]\n@:import require')
                                if is_placeholder or is_comment_only or (is_short and not has_real_code):
                                    truncated = True
                                    self._log(f"Detected placeholder/description content ({len(ct)} chars) — will retry as text")
                                    break
                        except Exception:
                            # Even JSON parse failure = likely truncation
                            truncated = True
                            self._log("write_file arguments failed to parse — likely truncated")
                            break

                if truncated:
                    # Re-request WITHOUT tools — model generates full code as text
                    self._log("Retrying without tools for full code generation")
                    # Extract the folder prefix from the original request if present
                    folder_prefix = ""
                    for tc in tool_calls_data:
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            p = args.get("path", "")
                            if "/" in p:
                                folder_prefix = p.split("/")[0] + "/"
                                break
                        except Exception:
                            pass
                    retry_prompt = (
                        "Generate COMPLETE code for ALL files. Write EVERY file as a fenced code block.\n\n"
                        f"IMPORTANT: All file paths must start with '{folder_prefix}' prefix.\n\n"
                        "FORMAT — follow EXACTLY:\n"
                        "```filename: folder/file.ext\n"
                        "<complete file content with REAL newlines, not escaped>\n"
                        "```\n\n"
                        "Rules:\n"
                        f"- All paths MUST start with '{folder_prefix}' (e.g. {folder_prefix}server.js, {folder_prefix}views/index.ejs)\n"
                        "- Use the format: ```filename: path/to/file\n"
                        "- Each file gets its own fenced code block\n"
                        "- Write COMPLETE files with REAL newlines — no placeholders, no truncation\n"
                        "- Create ALL files needed for the project\n"
                    )
                    retry_msg_dicts = [
                        {"role": "system", "content": retry_prompt},
                        msg_dicts[1],  # Original user message
                    ]
                    try:
                        retry_content = ""
                        async for event in self.provider.chat_completion_stream_events(
                            messages=retry_msg_dicts,
                            model=self.config.model,
                            temperature=self.config.temperature,
                            max_tokens=16384,
                            tools=None,
                        ):
                            if event.get("type") == "text":
                                retry_content += event.get("content", "")

                        if retry_content:
                            # Parse code blocks into write_file calls
                            parsed = self._parse_code_blocks(retry_content)
                            if parsed:
                                tool_calls_data = parsed
                                self._log(f"Parsed {len(parsed)} file(s) from code blocks")
                                # Update the assistant message with the full content
                                self._state.cur_messages[-1] = Message(
                                    role="assistant", content=retry_content, tool_calls=tool_calls_data
                                )
                    except Exception as e:
                        self._log(f"Retry without tools failed: {e}")

            # No tool calls = potentially done
            if not tool_calls_data and full_content:
                # Model outputted text instead of tool calls — try to parse code blocks
                parsed = self._parse_code_blocks(full_content)
                if parsed:
                    tool_calls_data = parsed
                    self._log(f"Parsed {len(parsed)} file(s) from text output (no tool calls)")
                    # Update the assistant message with the parsed tool calls
                    self._state.cur_messages[-1] = Message(
                        role="assistant", content=full_content, tool_calls=tool_calls_data
                    )

            if not tool_calls_data:
                # Check if there's a pending todo list with unchecked items
                has_pending_todos = False
                incomplete_count = 0
                for msg in reversed(self._state.done_messages + self._state.cur_messages):
                    if msg.role == 'tool' and msg.name == 'write_todos' and msg.content:
                        try:
                            data = json.loads(msg.content)
                            # Tool returns {"todos": [...], "display": ..., "completed_count": N, "total_count": N}
                            if isinstance(data, dict):
                                todos = data.get("todos", [])
                            elif isinstance(data, list):
                                todos = data
                            else:
                                todos = []
                            if isinstance(todos, list):
                                incomplete = [t for t in todos if isinstance(t, dict) and not t.get('completed', False)]
                                if incomplete:
                                    has_pending_todos = True
                                    incomplete_count = len(incomplete)
                                    self._log(f"Found {incomplete_count} incomplete todo items — prompting agent to continue")
                        except Exception:
                            pass
                        break

                # Also auto-continue if the model described files in text without creating them
                if not has_pending_todos and full_content and step < max_steps - 1:
                    text_lower = full_content.lower()
                    # Detect if model described what it would do instead of doing it
                    description_phrases = [
                        "i'll create", "i will create", "here is", "here are the files",
                        "the file would be", "the project structure", "let me create",
                        "i would create", "here is the code", "below is the",
                    ]
                    if any(phrase in text_lower for phrase in description_phrases):
                        has_pending_todos = True
                        self._log("Model described files instead of creating them — auto-continuing")

                if has_pending_todos and step < max_steps - 1:
                    # Send a follow-up message to keep the agent working
                    self._state.cur_messages.append(
                        Message(role='assistant', content=full_content or '', tool_calls=[])  # Commit assistant text
                    )
                    if incomplete_count > 0:
                        follow_up = f"You are NOT done. You have {incomplete_count} incomplete tasks. Continue creating files using write_file tool. Create the NEXT file NOW. Do NOT describe files — actually create them with write_file."
                    else:
                        follow_up = "You described files but did not create them. Use write_file tool to ACTUALLY CREATE each file. Do NOT just describe what you would write — use write_file to create real files."
                    self._state.cur_messages.append(
                        Message(role='user', content=follow_up)
                    )
                    continue  # Don't break — keep the loop going

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

            # Execute read-only tools (parallel if multiple, sequential if single)
            if read_only_tcs:
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
                else:
                    # Single read-only tool — execute sequentially
                    await self._execute_single_tool(read_only_tcs[0], on_tool_call, on_tool_result)

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
                        self._record_approval(tool_name, tool_args, approved, "User" if approved else "User rejected")
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
                        self._record_approval(tool_name, tool_args, False, approval["reason"])
                        blocked_result = {"blocked": approval["reason"]}
                        if on_tool_result:
                            on_tool_result(tool_name, blocked_result)
                        self._state.cur_messages.append(
                            Message(role="tool", tool_call_id=tc.get("id", ""),
                                    name=tool_name, content=json.dumps(blocked_result))
                        )
                        continue

                # Diff preview before modifications
                if self.config.diff_preview and tool_name in COMMIT_TOOLS:
                    file_path = tool_args.get("path", "")
                    if file_path and os.path.isfile(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                                current = f.read()
                            # Show what will change
                            if tool_name == "str_replace":
                                old = tool_args.get("old_string", "")
                                new = tool_args.get("new_string", "")
                                if old in current:
                                    preview = current.replace(old, new, 1)
                                    import difflib
                                    diff = list(difflib.unified_diff(
                                        current.splitlines(keepends=True),
                                        preview.splitlines(keepends=True),
                                        fromfile=f"a/{file_path}",
                                        tofile=f"b/{file_path}",
                                        lineterm="",
                                    ))
                                    if diff:
                                        self._log("--- Diff Preview ---")
                                        for line in diff[:30]:
                                            self._log(line.rstrip())
                        except Exception:
                            pass

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

                # Audit log for non-read-only tools
                if self._audit_logger and tool_name not in READ_ONLY_TOOLS:
                    self._audit_logger.log_tool_use(tool_name, tool_args, result)

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
                # Check for network calls (curl, wget, fetch)
                network_patterns = ["curl ", "wget ", "fetch(", "http://", "https://"]
                for np in network_patterns:
                    if np in cmd.lower():
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: network call detected: '{np}'. Use /approve full-auto.",
                        }
                # Check for dependency installation (npm install, pip install)
                install_patterns = ["npm install", "npm i ", "pip install", "pip i ", "yarn add", "pnpm add"]
                for ip in install_patterns:
                    if ip in cmd.lower():
                        return {
                            "allowed": False,
                            "reason": f"auto-edit: dependency install detected: '{ip}'. Use /approve full-auto.",
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

    def _parse_text_tool_calls(self, text: str) -> list[dict]:
        """Extract tool calls from text when model outputs code instead of API tool calls.
        
        Handles Meta <|python_tag|> format, raw Python calls, and code-fenced output.
        """
        import re, sys
        calls = []
        Q = r'["\x27]'  # quote char class
        
        # Strip Meta model artifacts and code fences
        clean = text
        clean = re.sub(r'<\|python_tag\|>', '', clean)
        clean = re.sub(r'```\w*', '', clean)
        clean = clean.strip()
        
        # Helper: extract string value from kwarg
        def _kw_val(block, key):
            m = re.search(key + r'\s*=\s*"([^"]+)"', block)
            if m:
                return m.group(1)
            m = re.search(key + r"\s*=\s*'([^']+)'", block)
            if m:
                return m.group(1)
            return ''
        
        # --- JSON tool call format: {"name": "write_file", "parameters": {...}} ---
        for m in re.finditer(r'\{\s*"name"\s*:\s*"write_file"\s*,\s*"parameters"\s*:\s*(\{.*?\})\s*\}', clean, re.DOTALL):
            try:
                params = json.loads(m.group(1))
                path = params.get('path', '')
                content = params.get('content', '')
                instructions = params.get('instructions', '')
                # Strip description prefixes like "Create a new file called...\n\n"
                content = re.sub(r'^(?:Create a new file called.*?with the following content:\s*\n\s*\n?)', '', content)
                if path and content:
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': content,
                                                              'instructions': instructions})},
                    })
            except Exception:
                pass

        # --- write_file with kwargs ---
        for m in re.finditer(r'write_file\s*\((.+?)\n\s*\)', clean, re.DOTALL):
            block = m.group(1)
            p = _kw_val(block, 'path')
            if not p:
                continue
            ct = _kw_val(block, 'content')
            # Try triple quotes
            tq = re.search(r'content\s*=\s*"""(.+?)"""', block, re.DOTALL)
            if tq:
                ct = tq.group(1)
            calls.append({
                'id': f'parsed-{len(calls)}', 'type': 'function',
                'function': {'name': 'write_file',
                             'arguments': json.dumps({'path': p, 'content': ct})},
            })
        
        # --- write_file positional: write_file("path", "content") ---
        if not calls:
            for m in re.finditer(r'write_file\s*\(\s*"([^"]+)"\s*,\s*"(.+?)"\s*\)', clean, re.DOTALL):
                calls.append({
                    'id': f'parsed-{len(calls)}', 'type': 'function',
                    'function': {'name': 'write_file',
                                 'arguments': json.dumps({'path': m.group(1), 'content': m.group(2)})},
                })
            for m in re.finditer(r"write_file\s*\(\s*'([^']+)'\s*,\s*'(.+?)'\s*\)", clean, re.DOTALL):
                calls.append({
                    'id': f'parsed-{len(calls)}', 'type': 'function',
                    'function': {'name': 'write_file',
                                 'arguments': json.dumps({'path': m.group(1), 'content': m.group(2)})},
                })
        
        # --- run_terminal_command ---
        for m in re.finditer(r'run_terminal_command\s*\(\s*"([^"]+)"', clean):
            calls.append({
                'id': f'parsed-{len(calls)}', 'type': 'function',
                'function': {'name': 'run_terminal_command',
                             'arguments': json.dumps({'command': m.group(1)})},
            })
        for m in re.finditer(r"run_terminal_command\s*\(\s*'([^']+)'", clean):
            calls.append({
                'id': f'parsed-{len(calls)}', 'type': 'function',
                'function': {'name': 'run_terminal_command',
                             'arguments': json.dumps({'command': m.group(1)})},
            })
        
        # --- read_files ---
        for m in re.finditer(r'read_files\s*\(\s*\[(.+?)\]', clean, re.DOTALL):
            paths = re.findall(r'"([^"]+)"', m.group(1))
            if not paths:
                paths = re.findall(r"'([^']+)'", m.group(1))
            if paths:
                calls.append({
                    'id': f'parsed-{len(calls)}', 'type': 'function',
                    'function': {'name': 'read_files',
                                 'arguments': json.dumps({'paths': paths})},
                })
        
        # --- list_directory ---
        for m in re.finditer(r'list_directory\s*\(\s*"([^"]+)"', clean):
            calls.append({
                'id': f'parsed-{len(calls)}', 'type': 'function',
                'function': {'name': 'list_directory',
                             'arguments': json.dumps({'path': m.group(1)})},
            })
        
        # --- Python with open(...) patterns ---
        # Instead of parsing Python string concat (fragile), execute the code directly
        if 'with open(' in clean or 'os.system(' in clean:
            # Extract the Python code block (everything after <|python_tag|>)
            code = clean
            # Find where actual code starts (after import os or similar)
            code_match = re.search(r'(import\s+os.*)', code, re.DOTALL)
            if code_match:
                code = code_match.group(1)
            # Remove find/cat commands (read-only) and replace with no-ops
            code = re.sub(r'os\.system\s*\(\s*["\x27]find\s+[^"\x27]*["\x27]\s*\)', 'pass', code)
            code = re.sub(r'os\.system\s*\(\s*["\x27]cat\s+[^"\x27]*["\x27]\s*\)', 'pass', code)
            try:
                # Execute the Python code in a subprocess for safety
                import subprocess as _sp
                result = _sp.run(
                    [sys.executable, '-c', code],
                    capture_output=True, text=True, timeout=30,
                    cwd=os.path.abspath(self.project_path) if hasattr(self, 'project_path') else '.',
                    env={**os.environ, 'PYTHONUTF8': '1'},
                )
                if result.returncode == 0:
                    self._log(f'Executed Python code block successfully')
                    # Return a synthetic success for all file writes
                    files_written = re.findall(r'open\s*\(\s*"([^"]+)"', code)
                    for fw in files_written:
                        calls.append({
                            'id': f'parsed-{len(calls)}', 'type': 'function',
                            'function': {'name': 'write_file',
                                         'arguments': json.dumps({'path': fw, 'content': '[executed via python]'})},
                        })
                    # Also catch os.system commands
                    for cmd in re.findall(r'os\.system\s*\(\s*"([^"]+)"', code):
                        if 'find ' not in cmd and 'cat ' not in cmd:
                            calls.append({
                                'id': f'parsed-{len(calls)}', 'type': 'function',
                                'function': {'name': 'run_terminal_command',
                                             'arguments': json.dumps({'command': cmd})},
                            })
                else:
                    self._log(f'Python code execution failed: {result.stderr[:200]}')
            except Exception as e:
                self._log(f'Python code execution error: {e}')
        
        return calls

    def _has_pending_todos(self, content: str) -> bool:
        """Check if there are pending todo items in the last assistant message."""
        # Look for write_todos results in recent tool results
        for msg in reversed(self._state.cur_messages):
            if msg.role == "tool" and msg.name == "write_todos":
                try:
                    data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    todos = data.get("todos", []) if isinstance(data, dict) else []
                    for t in todos:
                        if isinstance(t, dict) and not t.get("completed", False):
                            return True
                except (json.JSONDecodeError, AttributeError):
                    pass
        return False

    def _parse_code_blocks(self, text: str) -> list[dict]:
        """Parse fenced code blocks into write_file tool calls.

        Handles ALL model output formats:
        1. ```filename: path/to/file.js\n<code>\n```
        2. ```path/to/file.js\n<code>\n```
        3. ```\n// filename: path\n<code>\n```
        4. ```<lang>\n// path\n<code>\n```
        """
        import re
        calls = []
        seen_paths = set()

        def _is_file_path(s: str) -> bool:
            """Check if a string looks like a file path."""
            s = s.strip()
            return bool(re.match(r'^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)*\.[a-zA-Z0-9]{1,10}$', s))

        def _extract_path_from_line(line: str) -> str | None:
            """Extract file path from a line. Returns None if not a path."""
            line = line.strip()
            # // filename: path/to/file.js
            m = re.match(r'^//\s*(?:(?:filename|file|path):\s*)(.+)$', line)
            if m:
                candidate = m.group(1).strip()
                if _is_file_path(candidate):
                    return candidate
            # // path/to/file.js
            m = re.match(r'^//\s+(.+)$', line)
            if m:
                candidate = m.group(1).strip()
                if _is_file_path(candidate):
                    return candidate
            # path/to/file.js (bare)
            if _is_file_path(line):
                return line
            return None

        def _unescape_content(s: str) -> str:
            """Fix escaped newlines and quotes that the model outputs literally."""
            # Only unescape if the string contains double-escaped sequences
            # (i.e., the model output has literal backslash-n, not actual newline)
            if '\\\\n' in s:
                s = s.replace('\\\\n', '\n')
            elif '\n' in s:
                # Already has real newlines, don't double-escape
                pass
            else:
                # Model output has literal \n (backslash followed by n)
                s = s.replace('\n', '\n')
            if '\\t' in s:
                s = s.replace('\\t', '\t')
            if '\\"' in s:
                s = s.replace('\\"', '"')
            if "\\'" in s:
                s = s.replace("\\'", "'")
            return s

        # --- Approach 1: ```path/to/file.js\n<code>\n``` (path as lang tag) ---
        fence_inline = re.compile(
            r'(?:^|\n)```((?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10})\s*\n(.*?)```',
            re.DOTALL
        )
        for m in fence_inline.finditer(text):
            path = m.group(1).strip()
            code = _unescape_content(m.group(2).strip())
            if path and code and path not in seen_paths:
                seen_paths.add(path)
                calls.append({
                    'id': f'parsed-{len(calls)}', 'type': 'function',
                    'function': {'name': 'write_file',
                                 'arguments': json.dumps({'path': path, 'content': code,
                                                          'instructions': f'Create {path}'})},
                })

        # --- Approach 2: ```<lang>\n// filename: path\n<code>\n``` ---
        if not calls:
            fence_comment = re.compile(
                r'(?:^|\n)```\w+\s*\n//\s*(?:(?:filename|file|path):\s*)?([^\n]+\.[a-zA-Z0-9]{1,10})\s*\n(.*?)```',
                re.DOTALL
            )
            for m in fence_comment.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and _is_file_path(path) and path not in seen_paths:
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 3: ```filename: path\n<code>\n``` (inline filename: prefix) ---
        if not calls:
            fence_filename = re.compile(
                r'(?:^|\n)```(?:filename|file|path):\s*((?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10})\s*\n(.*?)```',
                re.DOTALL
            )
            for m in fence_filename.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths:
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 4: ```<lang>\n# filename: path\n<code>\n``` (Python comment style) ---
        if not calls:
            fence_python = re.compile(
                r'(?:^|\n)```\w+\s*\n#\s*(?:filename|file|path):\s*([^\n]+\.[a-zA-Z0-9]{1,10})\s*\n(.*?)```',
                re.DOTALL
            )
            for m in fence_python.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths:
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 5: ```<lang>\n<!-- filename: path -->\n<code>\n``` (HTML comment style) ---
        if not calls:
            fence_html = re.compile(
                r'(?:^|\n)```\w+\s*\n<!--\s*(?:filename|file|path):\s*([^\-]+\.[a-zA-Z0-9]{1,10})\s*-->\s*\n(.*?)```',
                re.DOTALL
            )
            for m in fence_html.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths:
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 6: ```bash\nwrite_file <path>\n``` followed by ```<lang>\n<code>\n``` ---
        # Model outputs: heading + bash block with write_file + code block with content
        if not calls:
            # Pattern: write_file <path> in a code block, followed by another code block with content
            write_cmd_pattern = re.compile(
                r'```(?:bash|shell|sh)?\s*\n\s*write_file\s+(\S+)\s*\n```\s*\n.*?```\w*\s*\n(.*?)```',
                re.DOTALL
            )
            for m in write_cmd_pattern.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths and not code.startswith('write_file'):
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 7: Heading + code block with file path as first line ---
        # Model outputs: ### Creating filename\n```lang\n<code>\n```
        if not calls:
            heading_pattern = re.compile(
                r'(?:#{1,3})\s*(?:Creating|File|Write)\s+((?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10})\s*\n.*?```\w*\s*\n(.*?)```',
                re.DOTALL
            )
            for m in heading_pattern.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths and not code.startswith('write_file'):
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 8: XML-style <write_file><path>...</path><content>...</content></write_file> ---
        if not calls:
            xml_pattern = re.compile(
                r'<write_file>\s*<path>(.*?)</path>\s*<content>(.*?)</content>\s*</write_file>',
                re.DOTALL
            )
            for m in xml_pattern.finditer(text):
                path = m.group(1).strip()
                code = m.group(2).strip()
                if path and code and path not in seen_paths:
                    seen_paths.add(path)
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'write_file',
                                     'arguments': json.dumps({'path': path, 'content': code,
                                                              'instructions': f'Create {path}'})},
                    })

        # --- Approach 9: run_terminal_command with npm init/install ---
        if not calls:
            terminal_pattern = re.compile(
                r'<run_terminal_command>\s*<command>(.*?)</command>\s*</run_terminal_command>',
                re.DOTALL
            )
            for m in terminal_pattern.finditer(text):
                cmd = m.group(1).strip()
                if cmd and '/workspace' not in cmd:
                    calls.append({
                        'id': f'parsed-{len(calls)}', 'type': 'function',
                        'function': {'name': 'run_terminal_command',
                                     'arguments': json.dumps({'command': cmd})},
                    })

        # Fallback: try write_file() text calls
        if not calls:
            calls = self._parse_text_tool_calls(text)

        return calls

    # =========================================================================
    # Plan Persistence
    # =========================================================================

    def save_plan(self, plan: list[dict]) -> None:
        """Persist plan items to disk with versioning."""
        try:
            os.makedirs(os.path.dirname(self._plan_file), exist_ok=True)
            # Load existing plan for versioning
            existing = self.load_plan()
            version = 1
            if os.path.isfile(self._plan_file):
                try:
                    with open(self._plan_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    version = data.get("version", 1) + 1
                except Exception:
                    pass
            # Save versioned plan
            with open(self._plan_file, "w", encoding="utf-8") as f:
                json.dump({
                    "plan": plan,
                    "version": version,
                    "updated_at": time.time(),
                    "project": self.project_path,
                }, f, indent=2)
            # Archive previous version
            archive_dir = os.path.join(self.project_path, ".dev", "plan_archive")
            os.makedirs(archive_dir, exist_ok=True)
            archive_file = os.path.join(archive_dir, f"plan_v{version - 1}.json")
            if os.path.isfile(self._plan_file) and version > 1:
                try:
                    with open(self._plan_file, "r") as src:
                        with open(archive_file, "w") as dst:
                            dst.write(src.read())
                except Exception:
                    pass
            self._log(f"Plan saved (v{version})")
        except Exception as e:
            self._log(f"Plan save failed: {e}")

    def load_plan(self) -> list[dict]:
        """Load persisted plan items."""
        if os.path.isfile(self._plan_file):
            try:
                with open(self._plan_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("plan", [])
            except Exception:
                pass
        return []

    def update_plan_item(self, item_index: int, status: str, notes: str = "") -> bool:
        """Update a specific plan item's status (for progress tracking)."""
        plan = self.load_plan()
        if 0 <= item_index < len(plan):
            plan[item_index]["status"] = status
            plan[item_index]["completed"] = status == "done"
            if notes:
                plan[item_index]["notes"] = notes
            self.save_plan(plan)
            return True
        return False

    def get_approval_history(self) -> list[dict]:
        """Return the full approval history for this session."""
        return list(self._approval_history)

    def _record_approval(self, tool_name: str, tool_args: dict, approved: bool, reason: str = "") -> None:
        """Record an approval decision for audit."""
        entry = {
            "timestamp": time.time(),
            "tool": tool_name,
            "approved": approved,
            "reason": reason,
            "args_preview": {k: str(v)[:100] for k, v in tool_args.items()},
        }
        self._approval_history.append(entry)
        # Keep only last 200 entries
        if len(self._approval_history) > 200:
            self._approval_history = self._approval_history[-200:]

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
        """Undo the last edit using git (Aider pattern).
        
        Uses git checkout to restore files to their previous state.
        Falls back to file-based backup for non-git projects.
        """
        # Try git-based undo first
        if self._state.edited_files:
            try:
                # Get the list of edited files
                files_to_restore = list(self._state.edited_files)
                # Use git checkout to restore each file to HEAD~1
                for f in files_to_restore:
                    abs_f = os.path.join(self.project_path, f) if not os.path.isabs(f) else f
                    rel_f = os.path.relpath(abs_f, self.project_path)
                    result = subprocess.run(
                        ["git", "checkout", "HEAD~1", "--", rel_f],
                        capture_output=True, text=True, cwd=self.project_path, timeout=10
                    )
                    if result.returncode != 0:
                        # File might not be tracked — try file-based fallback
                        self._restore_from_backup(f)
                # Clear the edited files set
                self._state.edited_files.clear()
                return {
                    "success": True,
                    "message": f"Undone: {len(files_to_restore)} file(s) restored via git",
                    "restored": files_to_restore,
                }
            except Exception as e:
                self._log(f"Git undo failed: {e}, falling back to file backup")
        
        # Fallback: file-based backup
        if self._checkpoint_id <= 0:
            return {"success": False, "message": "No checkpoints to undo"}

        backup_dir = os.path.join(self.project_path, self._state.backup_dir)
        if not os.path.isdir(backup_dir):
            return {"success": False, "message": "No backup directory"}

        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("cp")],
            reverse=True,
        )
        if not backups:
            return {"success": False, "message": "No backup files"}

        latest = backups[0]
        backup_path = os.path.join(backup_dir, latest)
        meta_path = backup_path + ".meta"
        original_path = None
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                original_path = f.read().strip()

        if not original_path or not os.path.isfile(backup_path):
            return {"success": False, "message": "Backup file not found"}

        try:
            shutil.copy2(backup_path, original_path)
            return {
                "success": True,
                "message": f"Restored: {original_path}",
                "restored": original_path,
            }
        except Exception as e:
            return {"success": False, "message": f"Restore failed: {e}"}

    def redo_last(self) -> dict:
        """Redo the last undone change (re-apply from current file to backup state)."""
        # Redo = re-read the backup and apply it as a new edit
        if self._checkpoint_id <= 0:
            return {"success": False, "message": "No checkpoints to redo"}

        backup_dir = os.path.join(self.project_path, self._state.backup_dir)
        if not os.path.isdir(backup_dir):
            return {"success": False, "message": "No backup directory"}

        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("cp")],
            reverse=True,
        )
        if not backups:
            return {"success": False, "message": "No backup files"}

        latest = backups[0]
        backup_path = os.path.join(backup_dir, latest)
        meta_path = backup_path + ".meta"
        original_path = None
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                original_path = f.read().strip()

        if not original_path:
            return {"success": False, "message": "No original path recorded"}

        # Redo = the backup IS the new state, so we just confirm it's applied
        # (undo already restored it; redo is a no-op if already restored)
        return {
            "success": True,
            "message": f"Redo applied: {original_path}",
            "restored": original_path,
        }

    # =========================================================================
    # Auto-Compact (Claude Code pattern)
    # =========================================================================

    async def _auto_compact_if_needed(self, messages: list[Message], system_prompt: str):
        """Auto-compact context when usage exceeds 70%."""
        tokens = self._count_tokens(messages)
        threshold = self.config.max_context_tokens * 0.7

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
        """Build the full system prompt with all context. Cached to avoid rebuilds."""
        # Cache key based on base_prompt + repo_map + project rules
        cache_key = f"{base_prompt[:200]}:{repo_map[:200]}:{self._state.fnames and sorted(self._state.fnames)[0]}"
        if hasattr(self, '_system_prompt_cache') and self._system_prompt_cache.get('key') == cache_key:
            return self._system_prompt_cache['value']
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

        # Skills integration — inject expert role instructions
        try:
            from .skill_integration import SkillIntegration
            si = SkillIntegration(skills_path=os.path.join(self.project_path, "skills"))
            # Get the user's task from current messages
            task = ""
            for msg in self._state.done_messages + self._state.cur_messages:
                if msg.role == "user":
                    task = msg.content or ""
                    break
            if task:
                skill_prompt = si.build_skill_prompt(task)
                if skill_prompt:
                    parts.append(f"\n\n{skill_prompt}")
        except Exception:
            pass  # Skills folder not available

        # NIM model instruction: use write_file tool one file at a time
        parts.append("""

## CRITICAL RULES — FOLLOW EXACTLY

### File Creation
When creating files, use the write_file tool ONE FILE AT A TIME with COMPLETE content.
Do NOT describe what you will create — just create it.
Do NOT use code blocks or text descriptions — use the write_file tool directly.
Do NOT overwrite or modify files in the skills/ folder.
Each file must be PRODUCTION-QUALITY code, not placeholders.

### Multi-File Projects
When building a project with multiple files:
1. First, create a todo list with write_todos listing ALL files needed
2. Then create EACH file one by one using write_file
3. After creating each file, move to the next — do NOT stop
4. After ALL files are created, use run_terminal_command to install dependencies if needed
5. Only say "done" when ALL files from your todo list are created

### Step-by-Step
- Create ONE file per tool call — complete, production-quality code
- Never truncate, never use placeholders, never say "similar to above"
- Keep creating files until your todo list is fully checked off
- You MUST keep working — do not stop until every file is created
- Run npm install after package.json is created
- Test the server starts correctly after all files are created
""")

        result = "\n".join(parts)
        # Cache for reuse
        if not hasattr(self, '_system_prompt_cache'):
            self._system_prompt_cache = {}
        self._system_prompt_cache = {'key': cache_key, 'value': result}
        return result

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
        
        NVIDIA NIM models (especially Llama 3.1 on NIM) only support
        single tool-calls per assistant message. This method splits
        multi-tool-call assistant messages into individual pairs:
          assistant(tc1) -> tool(result1) -> assistant(tc2) -> tool(result2)
        """
        # First, collect tool results by tool_call_id for easy lookup
        tool_results_by_id = {}
        for m in messages:
            if m.role == "tool" and m.tool_call_id:
                tool_results_by_id[m.tool_call_id] = m

        result = []
        for m in messages:
            if m.role == "assistant" and m.tool_calls and len(m.tool_calls) > 1:
                # Split multi-tool-call assistant into individual pairs
                for tc in m.tool_calls:
                    tc_id = tc.get("id", "")
                    # Assistant message with single tool call
                    result.append({
                        "role": "assistant",
                        "content": m.content or "",
                        "tool_calls": [tc],
                    })
                    # Corresponding tool result
                    tool_m = tool_results_by_id.get(tc_id)
                    if tool_m:
                        result.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_m.name or tc.get("function", {}).get("name", ""),
                            "content": tool_m.content or "{}",
                        })
            elif m.role == "tool" and m.tool_call_id:
                # Skip standalone tool results — already handled above
                continue
            else:
                md = {"role": m.role}
                md["content"] = m.content or ""
                if m.tool_calls:
                    md["tool_calls"] = m.tool_calls
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
                if self._tool_names and hasattr(self.tools, 'get_definitions_for_tools'):
                    tool_defs = self.tools.get_definitions_for_tools(self._tool_names)
                else:
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
        """Execute a tool call with error handling and caching for read-only tools."""
        handler = self.tools.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        # Cache read-only tool results to avoid re-reading the same files
        if tool_name in READ_ONLY_TOOLS:
            cache_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            if cache_key in self._tool_cache:
                self._log(f"Cache hit: {tool_name}")
                return self._tool_cache[cache_key]

        try:
            if asyncio.iscoroutinefunction(handler.execute):
                result = await handler.execute(tool_args, self._state, self.project_path)
            else:
                result = handler.execute(tool_args, self._state, self.project_path)

            # Cache read-only results
            if tool_name in READ_ONLY_TOOLS and isinstance(result, dict):
                if len(self._tool_cache) >= self._tool_cache_max:
                    # Evict oldest entry
                    oldest_key = next(iter(self._tool_cache))
                    del self._tool_cache[oldest_key]
                self._tool_cache[cache_key] = result

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

            # Recent file changes (last 5 files changed)
            result = subprocess.run(
                ["git", "log", "--diff-filter=AM", "--name-only", "--pretty=format:", "-5"],
                capture_output=True, text=True, cwd=self.project_path, timeout=5,
            )
            if result.stdout.strip():
                recent_files = [f for f in result.stdout.strip().split("\n") if f][:5]
                if recent_files:
                    parts.append(f"Recently changed files: {', '.join(recent_files)}")
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
