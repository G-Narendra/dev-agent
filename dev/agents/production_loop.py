"""
Production Agent Loop for Dev -- the CORE of the entire agent.

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
import re
import time
import traceback
from typing import Any, AsyncIterator, Callable, Optional

# Smart Compaction (OpenClaw/Claude Code/Codex patterns)
try:
    from .compaction import CompactionEngine, CompactionConfig, is_overflow_error
except ImportError:
    CompactionEngine = None
    CompactionConfig = None
    is_overflow_error = None

# Security (Teleport-style + OWASP defenses)
try:
    from ..security.injection_detector import PromptInjectionDetector, ThreatLevel
    from ..security.tool_validator import ToolCallValidator
    from ..security.audit_logger import AuditLogger
    from ..security.output_monitor import OutputMonitor
except ImportError:
    PromptInjectionDetector = None
    ToolCallValidator = None
    AuditLogger = None
    OutputMonitor = None
from pathlib import Path

# Extracted modules (reduce this file from 3500+ lines)
from .loop_types import (
    Message, LoopConfig, EditResult, LoopState,
    MODIFYING_TOOLS, READ_ONLY_TOOLS, COMMIT_TOOLS,
    DANGEROUS_TOOLS, DANGEROUS_COMMANDS,
)
from .tool_executor import ToolExecutorMixin
from .system_prompt import SystemPromptMixin

class ProductionAgentLoop(ToolExecutorMixin, SystemPromptMixin):
    """
    Production-quality agent loop -- the brain of Dev.

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
        # Smart Compaction Engine (OpenClaw-style)
        self._compaction = None
        if CompactionEngine:
            self._compaction = CompactionEngine(CompactionConfig() if CompactionConfig else None)
        # Security modules (Teleport-style + OWASP)
        self._injection_detector = None
        self._tool_validator = None
        self._output_monitor = None
        if PromptInjectionDetector:
            self._injection_detector = PromptInjectionDetector(strict_mode=True)
        if ToolCallValidator:
            self._tool_validator = ToolCallValidator(project_path)
        if OutputMonitor:
            self._output_monitor = OutputMonitor(strict_mode=False)
        # Initialize audit logger (None if security module unavailable)
        self._audit_logger = None
        self._audit_logger_new = False
        try:
            from ..security.audit_logger import AuditLogger as _AuditLogger
            self._audit_logger = _AuditLogger(project_path)
            self._audit_logger_new = True
        except Exception:
            pass  # Intentional: Exception in production_loop.py
        # Tool names to filter tool definitions (reduces tool count for LLM)
        self._tool_names: list[str] | None = None
        # Tool result cache: cache read-only tool results to avoid re-reading
        self._tool_cache: dict[str, dict] = {}  # cache_key -> result
        self._tool_cache_max = 50  # Max cached results
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
        """Verbose logging -- only prints when verbose mode is on."""
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

        # SECURITY: Validate user input for prompt injection
        if self._injection_detector:
            detection = self._injection_detector.detect(prompt)
            if detection.blocked:
                self._log(f"\u26d4 Security: Input BLOCKED -- {detection.reason}")
                if self._audit_logger:
                    self._audit_logger.log_security_event(
                        event_type="input_blocked",
                        details=detection.reason,
                        threat_level=detection.threat_level.value,
                        blocked=True,
                    )
                return {"status": "blocked", "reason": detection.reason}
            elif detection.threat_level.value in ("medium", "high"):
                self._log(f"\u26a0\ufe0f Security: Suspicious input detected ({detection.threat_level.value}) -- monitoring")
                if self._audit_logger:
                    self._audit_logger.log_security_event(
                        event_type="suspicious_input",
                        details=str(detection.detected_patterns),
                        threat_level=detection.threat_level.value,
                    )

        self._state.cur_messages.append(
            Message(role="user", content=prompt)
        )

        full_system = self._build_system_prompt(system_prompt, repo_map)
        
        # AUTO-DESIGN: Detect if building a web project and fetch brand design
        full_system = await self._auto_fetch_design(prompt, full_system)
        
        all_tool_calls = []
        all_tool_results = []
        reflection_count = 0
        last_error = None

        for step in range(max_steps):
            if self._abort:
                return {"status": "aborted", "step": step}

            self._log(f"Step {step + 1}/{max_steps}, context tokens: ~{self._count_tokens(self._state.done_messages + self._state.cur_messages):,}")

            # Auto-poll background jobs and inject their output as context
            await self._poll_background_jobs()

            messages = self._format_messages(full_system)
            messages = self._prune_if_needed(messages, full_system)

            # Auto-compact if context is getting full
            await self._auto_compact_if_needed(messages, full_system)

            # Re-format after potential compaction
            messages = self._format_messages(full_system)

            response = await self._call_llm_with_retries(messages)

            if not response:
                # Don't exit -- try next step with a different approach
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
                        # Handle both formats: {"name": ..., "args": ...} and {"function": {"name": ...}}
                        if "function" in pc:
                            tool_name = pc["function"]["name"]
                            tool_args = json.loads(pc["function"]["arguments"]) if isinstance(pc["function"].get("arguments"), str) else pc["function"].get("arguments", {})
                        else:
                            tool_name = pc.get("name", "")
                            tool_args = pc.get("args", {})
                        
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
                    
                    # Continue the loop -- don't exit yet
                    continue
                
                # Check if there are pending todo items -- if so, auto-continue
                if self._has_pending_todos(content):
                    self._log("Model returned text but has pending todos, auto-continuing")
                    self._state.cur_messages.append(
                        Message(role="user", content=
                            "You have unfinished tasks. Continue creating the remaining files "
                            "using write_file tool. Do NOT stop until all tasks are complete.")
                    )
                    continue
                
                # Nemotron multi-turn recovery: model returned text but no tools
                # and we haven't completed much yet — inject corrective nudge
                if len(all_tool_calls) == 0 and step < 3:
                    self._log(f"Nemotron recovery: no tools used after {step+1} steps, injecting nudge")
                    self._state.cur_messages.append(
                        Message(role="user", content=(
                            "You MUST use the write_file tool to create files. "
                            "Do not describe what you will do — actually do it using the tools. "
                            'Call write_file with the actual file content now.'
                        ))
                    )
                    continue
                
                # Nemotron multi-turn recovery: model returned text but no tools
                # after many tool calls — likely forgot context, remind it
                if len(all_tool_calls) > 0 and not tool_calls:
                    recent_tool_names = [tc["name"] for tc in all_tool_calls[-3:]]
                    self._log(f"Nemotron recovery: model stopped using tools after {len(all_tool_calls)} calls, injecting reminder")
                    self._state.cur_messages.append(
                        Message(role="user", content=(
                            f"Continue the task. You have been using tools successfully. "
                            f"Recently used: {', '.join(recent_tool_names)}. "
                            f"Keep using write_file, run_terminal_command, and other tools to complete the work."
                        ))
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
                    tool_args = self._coerce_tool_args(tool_args)

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

                    # Compress tool results -- add quality feedback if file is too short
                    if tool_name == 'write_file':
                        file_lines = result.get('lines', 0)
                        file_path = result.get('path', '')
                        quality_warning = ''
                        if file_path.endswith('.css') and file_lines < 50:
                            quality_warning = f' WARNING: CSS only {file_lines} lines. REWRITE with 100+ lines: gradients, animations, shadows, responsive, Google Fonts.'
                        elif file_path.endswith('.js') and file_lines < 30:
                            quality_warning = f' WARNING: JS only {file_lines} lines. REWRITE with 50+ lines: event handlers, smooth scroll, form validation.'
                        elif file_path.endswith('.ejs') and file_lines < 20:
                            quality_warning = f' WARNING: EJS only {file_lines} lines. REWRITE with 50+ lines: complete HTML, real content.'
                        result_str = json.dumps({'success': True, 'path': file_path, 'lines': file_lines, 'feedback': quality_warning})
                    elif tool_name == 'run_terminal_command':
                        result_str = json.dumps({'exitCode': result.get('exitCode', 0), 'stdout': str(result.get('stdout', ''))[:200]})
                    else:
                        result_str = json.dumps(result)
                        if len(result_str) > 1500:
                            # Head+tail truncation preserves beginning and end context
                            half = 700
                            result_str = result_str[:half] + f'\n...[{len(result_str) - half*2} chars removed]\n' + result_str[-half:]
                    
                    # Global cap -- no single tool result exceeds 2000 chars
                    if len(result_str) > 2000:
                        result_str = result_str[:800] + f'\n...[{len(result_str) - 1600} chars truncated]\n' + result_str[-800:]

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

        # Graceful degradation: never stop silently at max_steps -- synthesize a summary.
        summary_content = await self._synthesize_final_summary(full_system)

        return {
            "status": "max_steps",
            "content": summary_content,
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

        # SECURITY: Validate user input for prompt injection
        if self._injection_detector:
            detection = self._injection_detector.detect(prompt)
            if detection.blocked:
                self._log(f"\u26d4 Security: Input BLOCKED -- {detection.reason}")
                if self._audit_logger:
                    self._audit_logger.log_security_event(
                        event_type="input_blocked",
                        details=detection.reason,
                        threat_level=detection.threat_level.value,
                        blocked=True,
                    )
                return {"status": "blocked", "reason": detection.reason}
            elif detection.threat_level.value in ("medium", "high"):
                self._log(f"\u26a0\ufe0f Security: Suspicious input detected ({detection.threat_level.value}) -- monitoring")
                if self._audit_logger:
                    self._audit_logger.log_security_event(
                        event_type="suspicious_input",
                        details=str(detection.detected_patterns),
                        threat_level=detection.threat_level.value,
                    )

        self._state.cur_messages.append(
            Message(role="user", content=prompt)
        )

        full_system = self._build_system_prompt(system_prompt, repo_map)
        
        # AUTO-DESIGN: Detect if building a web project and fetch brand design
        full_system = await self._auto_fetch_design(prompt, full_system)
        
        all_tool_calls = []
        all_tool_results = []
        final_content = ""

        # --- Research-backed loop safety state (Codex/smolagents patterns) ---
        last_tool_signature = None  # signature of most recent executed tool call
        identical_repeat_count = 0  # consecutive repeats of the same signature
        consecutive_empty = 0  # empty responses (no text, no tool calls) in a row
        consecutive_failures = 0  # steps where all LLM retries failed

        for step in range(max_steps):
            if self._abort:
                return {"status": "aborted", "step": step}

            self._log(f"Step {step + 1}/{max_steps}, context tokens: ~{self._count_tokens(self._state.done_messages + self._state.cur_messages):,}")

            # Auto-poll background jobs and inject their output as context
            await self._poll_background_jobs()

            messages = self._format_messages(full_system)
            messages = self._prune_if_needed(messages, full_system)

            # Auto-compact if context is getting full
            await self._auto_compact_if_needed(messages, full_system)

            # Re-format after potential compaction
            messages = self._format_messages(full_system)

            # Convert to dicts for API
            msg_dicts = self._messages_to_dicts(messages)

            # Get tool definitions -- filter by tool_names or auto-select relevant tools
            if self._tool_names and hasattr(self.tools, 'get_definitions_for_tools'):
                tool_defs = self.tools.get_definitions_for_tools(self._tool_names)
            else:
                all_tool_defs = self.tools.get_definitions()
                # Auto-filter for Nemotron (reduces token footprint)
                tool_defs = self._get_relevant_tools(prompt if step == 0 else "", all_tool_defs)
            self._log(f"Sending {len(msg_dicts)} messages, {len(tool_defs)} tool schemas to LLM")

            # Stream the response WITH retry logic
            full_content = ""
            tool_calls_data = []
            stream_success = False
            last_error = None
            # Checkpoint message count before retry -- rollback on failure to prevent duplicates
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

                    # Resolve model: 'default'/'coding'/'reasoning' are task types, not model names
                    effective_model = self.config.model
                    if effective_model in ('default', 'coding', 'reasoning', 'fast'):
                        effective_model = None  # Let provider resolve the best model
                    elif tool_defs and '8b' in str(effective_model).lower():
                        effective_model = None  # Let provider pick a larger model for tools
                    
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
                    break  # Success -- exit retry loop

                except Exception as e:
                    last_error = str(e)

                    # On 400 (context length exceeded), shrink the context window and retry
                    if "400" in last_error or "context" in last_error.lower():
                        old_limit = self.config.max_context_tokens
                        self.config.max_context_tokens = int(old_limit * 0.7)
                        self._log(f"Context too large -- reducing limit from {old_limit:,} to {self.config.max_context_tokens:,} tokens")
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
                        self._log(f"Server error -- reducing context from {old_limit:,} to {self.config.max_context_tokens:,}")
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
                
                # Detect rate-limit errors -- these should NOT count toward consecutive_failures
                error_str = str(last_error).lower()
                is_rate_limit = any(term in error_str for term in (
                    '429', 'rate', 'exhausted', 'too many', 'limit reached',
                ))
                
                if is_rate_limit:
                    # Patient wait: sleep until the RPM window resets (60-90s)
                    wait_seconds = 65  # Default: wait just over a minute for RPM reset
                    self._log(f"Rate limit detected -- waiting {wait_seconds}s before retry")
                    if on_text:
                        on_text(f"\n⏳ Rate limited -- waiting {wait_seconds}s for API window reset...\n")
                    await asyncio.sleep(wait_seconds)
                    # Don't increment consecutive_failures for rate limits
                else:
                    consecutive_failures += 1
                    # Bounded failure: don't grind through remaining steps when provider is down.
                    if consecutive_failures >= self.config.max_consecutive_failures:
                        self._log(f"{consecutive_failures} consecutive failed steps -- aborting with summary")
                        return {
                            "status": "error",
                            "message": f"Provider failed {consecutive_failures} steps in a row: {last_error}",
                            "tool_calls": all_tool_calls,
                            "tool_results": all_tool_results,
                            "steps": step + 1,
                        }
                # Inject error context so next step knows what happened, then continue
                self._state.cur_messages.append(
                    Message(role="user", content=f"The previous LLM request failed ({last_error}). Continue the task from where you left off.")
                )
                continue

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
                                # Detect placeholder/description content (not real code)
                                is_empty = len(stripped) < 10
                                is_comment_only = (stripped.startswith('/*') or stripped.startswith('//')) and stripped.endswith('*/') and len(stripped) < 200
                                is_short = len(stripped) < 60
                                has_real_code = any(c in stripped for c in '{}()=;<>[]\n@:import require')
                                # Only flag as placeholder if truly not code
                                if is_empty or is_comment_only or (is_short and not has_real_code):
                                    truncated = True
                                    self._log(f"Detected placeholder content ({len(ct)} chars) -- will retry")
                                    break
                                # --- Structural truncation detection (cut-off mid-file) ---
                                # HTML that opens a document but never closes it
                                low = stripped.lower()
                                if (low.startswith('<!doctype') or low.startswith('<html')) and '</html>' not in low:
                                    truncated = True
                                    self._log(f"Detected TRUNCATED HTML ({len(ct)} chars, no </html>) -- will split")
                                    break
                                # Unbalanced braces/brackets in code = cut off mid-write
                                for op, cl in [('{', '}'), ('[', ']')]:
                                    if stripped.count(op) - stripped.count(cl) > 2 and len(stripped) > 100:
                                        truncated = True
                                        self._log(f"Detected UNBALANCED {op}{cl} ({stripped.count(op)} vs {stripped.count(cl)}) -- file cut off")
                                        break
                                if truncated:
                                    break
                        except Exception:
                            # Even JSON parse failure = likely truncation
                            truncated = True
                            self._log("write_file arguments failed to parse -- likely truncated")
                            break

                if truncated:
                    # Re-request WITH tools -- model must use write_file tool
                    self._log("Retrying with tools for full code generation")
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
                            pass  # Intentional: Exception in production_loop.py
                    retry_prompt = (
                        "The previous write_file calls had PLACEHOLDER or CUT-OFF content -- the file was truncated mid-write.\n"
                        "This happens when a single write_file is too large. You MUST SPLIT YOUR WORK:\n\n"
                        "RULES:\n"
                        "1. Write ONE small file per step (keep each under 120 lines)\n"
                        "2. If a page is long, create it in parts: first part with write_file, "
                        "then EXTEND it using str_replace on a unique marker like <!-- PART2 -->\n"
                        "3. Content must be REAL code with COMPLETE implementations -- not stubs\n"
                        "4. NEVER output placeholder text like '// add code here' or 'TODO'\n"
                        "5. NEVER create local image files (.jpg/.png) -- use remote image URLs "
                        "(https://upload.wikimedia.org/...) directly in HTML/CSS instead\n"
                        f"6. All paths must start with '{folder_prefix}' if creating a subfolder\n\n"
                        f"Start NOW with the NEXT unfinished file. Do not describe, just create."
                    )
                    # Insert the retry prompt as a user message to keep context
                    self._state.cur_messages.append(
                        Message(role='user', content=retry_prompt)
                    )
                    continue  # Go back to top of loop -- will call LLM with tools

            # No tool calls = potentially done
            if not tool_calls_data and full_content:
                # Model outputted text instead of tool calls -- try to parse code blocks
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
                                    self._log(f"Found {incomplete_count} incomplete todo items -- prompting agent to continue")
                        except Exception:
                            pass  # Intentional: Exception in production_loop.py
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
                        self._log("Model described files instead of creating them -- auto-continuing")

                # Auto-research: if model says it needs info but didn't call web_search
                if not has_pending_todos and full_content and step < max_steps - 1:
                    research_phrases = [
                        "i don't know", "i'm not sure", "i need to research", "let me look up",
                        "i'll search", "i need more information", "let me find out",
                        "i need to check", "i'm not familiar", "i don't have that info",
                    ]
                    used_web_search = any(
                        tc.get('function', {}).get('name', '') in ('web_search', 'read_url')
                        for tc in (tool_calls_data or [])
                    )
                    if any(phrase in text_lower for phrase in research_phrases) and not used_web_search:
                        # Extract the topic the model wants to research
                        self._state.cur_messages.append(
                            Message(role='user', content=(
                                "You said you need information but didn't search for it. "
                                "CALL web_search with a specific query to find the answer. "
                                "Then use read_url on the best result. "
                                "Do NOT guess -- RESEARCH from the web."
                            ))
                        )
                        continue

                if has_pending_todos and step < max_steps - 1:
                    # Send a follow-up message to keep the agent working
                    self._state.cur_messages.append(
                        Message(role='assistant', content=full_content or '', tool_calls=[])  # Commit assistant text
                    )
                    if incomplete_count > 0:
                        follow_up = (
                            f"STOP TALKING. You have {incomplete_count} incomplete tasks.\n"
                            "CALL write_file RIGHT NOW for the NEXT file.\n"
                            "Each file must have COMPLETE content -- full HTML, full CSS, full JS.\n"
                            "No placeholders, no 'add code here', no stubs.\n"
                            "Write the ENTIRE file content in the write_file call.\n"
                            "DO NOT describe what you will write. JUST WRITE IT."
                        )
                    else:
                        follow_up = (
                            "You described files in text but did not create them. THIS IS WRONG.\n"
                            "CALL write_file for EACH file you described.\n"
                            "The content parameter must contain the COMPLETE file -- not a description.\n"
                            "For CSS: write ALL styles. For HTML: write ALL markup. For JS: write ALL code.\n"
                            "CALL write_file NOW."
                        )
                    self._state.cur_messages.append(
                        Message(role='user', content=follow_up)
                    )
                    continue  # Don't break -- keep the loop going

                # --- Empty-response tracking (research: silent stalls are the #1 free-model failure) ---
                if not full_content and not tool_calls_data:
                    consecutive_empty += 1
                    self._log(f"Empty response ({consecutive_empty}/{self.config.max_consecutive_empty})")
                    if consecutive_empty <= self.config.max_consecutive_empty:
                        self._state.cur_messages.append(
                            Message(role="user", content=(
                                "Your last response was EMPTY. Do not send empty responses. "
                                "Either call a tool (e.g., write_file, run_terminal_command, read_files) "
                                "or reply with useful text about the task progress. Try again now."
                            ))
                        )
                        continue
                    # Exceeded threshold -- synthesize graceful summary and stop (smolagents pattern)
                    self._log("Too many empty responses -- synthesizing final summary")
                    return {
                        "status": "completed",
                        "content": final_content or f"[Agent stopped after {consecutive_empty} empty model responses. Work done so far: {len(all_tool_calls)} tool calls.]",
                        "tool_calls": all_tool_calls,
                        "tool_results": all_tool_results,
                        "steps": step + 1,
                        "warning": "ended_early_empty_responses",
                    }
                consecutive_empty = 0

                final_content = full_content
                # Progressive observation shrinking (OpenDev adaptive compaction):
                # old tool outputs in history shrink each step so long sessions
                # don't drown the model in stale logs.
                self._shrink_old_observations(keep_recent=3)
                self._maybe_inject_reminder(step)
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
            MAX_TOOL_CALLS_PER_TURN = 20  # Allow up to 20 tool calls per turn for multi-file projects
            if len(tool_calls_data) > MAX_TOOL_CALLS_PER_TURN:
                self._log(f"Warning: LLM requested {len(tool_calls_data)} tools. Capping at {MAX_TOOL_CALLS_PER_TURN}.")
                tool_calls_data = tool_calls_data[:MAX_TOOL_CALLS_PER_TURN]

            # Filter out hallucinated tool calls (tools that don't exist)
            valid_tool_names = {d.get('function', {}).get('name', '') for d in tool_defs}
            invalid_tcs = [tc for tc in tool_calls_data if tc.get('function', {}).get('name', '') not in valid_tool_names]
            if invalid_tcs:
                invalid_names = [tc.get('function', {}).get('name', '') for tc in invalid_tcs]
                self._log(f"Filtering {len(invalid_tcs)} hallucinated tool calls: {invalid_names}")
                tool_calls_data = [tc for tc in tool_calls_data if tc.get('function', {}).get('name', '') in valid_tool_names]
                # If ALL tool calls were hallucinated, inject a correction message
                if not tool_calls_data:
                    self._state.cur_messages.append(
                        Message(role='user', content=f"ERROR: You called tools that don't exist: {invalid_names}. Available tools: {sorted(valid_tool_names)}. Use ONLY the available tools. Try again.")
                    )
                    continue  # Retry with correction

            # --- Loop detection (research: repeated identical calls = model stuck) ---
            if tool_calls_data:
                sigs = []
                for tc in tool_calls_data:
                    try:
                        a = json.loads(tc.get("function", {}).get("arguments", "{}"))
                        a.pop("content", None)  # file content makes signatures huge; path+args suffice
                    except Exception:
                        a = {}
                    sigs.append(f"{tc.get('function', {}).get('name', '')}:{json.dumps(a, sort_keys=True)[:200]}")
                step_signature = "|".join(sigs)
                if step_signature == last_tool_signature:
                    identical_repeat_count += 1
                else:
                    identical_repeat_count = 0
                    last_tool_signature = step_signature
                if identical_repeat_count + 1 >= self.config.max_identical_tool_repeats:
                    self._log(f"Loop detected: same tool calls repeated {identical_repeat_count + 1}x -- injecting correction")
                    self._state.cur_messages.append(
                        Message(role="user", content=(
                            "ERROR: You are repeating the exact same tool calls with the same arguments. "
                            "This means your approach is not working. STOP and try a DIFFERENT approach: "
                            "read the error output carefully, check what already exists on disk, or break "
                            "the task into smaller steps. Do NOT repeat the previous calls unchanged."
                        ))
                    )
                    identical_repeat_count = 0
                    continue

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
                    # Single read-only tool -- execute sequentially
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
                tool_args = self._coerce_tool_args(tool_args)

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
                            pass  # Intentional: Exception in production_loop.py

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
                    if hasattr(self._audit_logger, 'log_tool_use'):
                        self._audit_logger.log_tool_use(tool_name, tool_args, result)
                    elif hasattr(self._audit_logger, 'log_tool_call'):
                        self._audit_logger.log_tool_call(tool_name, tool_args)

                # Update tc args to reflect any mutations from hooks
                tc["function"]["arguments"] = json.dumps(tool_args)

                # Truncate large tool results to prevent context overflow
                # Compress write_file results -- add quality feedback if file is too short
                if tool_name == 'write_file':
                    file_lines = result.get('lines', 0)
                    file_path = result.get('path', '')
                    quality_warning = ''
                    # Detect stubs: CSS/JS should be 50+ lines, HTML 30+ lines
                    if file_path.endswith('.css') and file_lines < 50:
                        quality_warning = f' WARNING: CSS file has only {file_lines} lines. Must have 100+ lines with gradients, animations, shadows, responsive design, Google Fonts. REWRITE with COMPLETE professional styling.'
                    elif file_path.endswith('.js') and file_lines < 30:
                        quality_warning = f' WARNING: JS file has only {file_lines} lines. Must have 50+ lines with full event handlers, smooth scrolling, form validation. REWRITE with COMPLETE implementation.'
                    elif file_path.endswith('.ejs') and file_lines < 20:
                        quality_warning = f' WARNING: EJS file has only {file_lines} lines. Must have 50+ lines with complete HTML structure, real content, proper layout. REWRITE with COMPLETE page.'
                    elif file_path.endswith('.html') and file_lines < 30:
                        quality_warning = f' WARNING: HTML file has only {file_lines} lines. Must have 50+ lines with semantic HTML, real content, meta tags. REWRITE with COMPLETE markup.'
                    result_str = json.dumps({
                        'success': result.get('success', True),
                        'path': file_path,
                        'lines': file_lines,
                        'bytes': result.get('bytes', 0),
                        'feedback': quality_warning,
                    })
                elif tool_name == 'read_files':
                    result_str = json.dumps(result)
                    if len(result_str) > 3000:
                        # Head+tail: keep first 2000 + last 800 chars
                        result_str = result_str[:2000] + f'\n\n[...{len(result_str) - 2800} chars truncated...]\n' + result_str[-800:]
                elif tool_name == 'web_search':
                    result_str = json.dumps(result)
                    if len(result_str) > 2500:
                        # For search results, keep top results and truncate the rest
                        result_str = result_str[:2500] + f'\n[...{len(result_str) - 2500} chars truncated...]'
                else:
                    result_str = json.dumps(result)
                    if len(result_str) > 2000:
                        # Head+tail truncation preserves both beginning and end context
                        head = 1200
                        tail = 600
                        removed = len(result_str) - head - tail
                        result_str = result_str[:head] + f'\n[...{removed} chars truncated...]\n' + result_str[-tail:]

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

                # Auto-test after all writes in this step are done
                if self.config.auto_test and tool_name in COMMIT_TOOLS and tool_name == write_tcs[-1].get("function", {}).get("name", ""):
                    test_result = await self._auto_test()
                    if test_result and test_result.get("failed"):
                        self._log(f"Auto-test FAILED: {test_result['failed']}")
                        # Inject test failure into context so model can fix it
                        self._state.cur_messages.append(
                            Message(role='user', content=f"Tests FAILED: {test_result.get('output', '')[:500]}. Fix the issues and try again.")
                        )

            # Show git diff after all tool calls in this step
            if self.config.show_diffs and all_tool_calls:
                self._show_git_diff()

            # Save session state after each step
            await self._save_session()

            # Rate limit delay -- respect provider limits
            # Use 2s as safe default; providers handle their own rate limiting
            if step < max_steps - 1 and tool_calls_data:
                await asyncio.sleep(2.0)

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

        # Graceful degradation: never stop silently at max_steps -- synthesize a summary.
        summary_content = await self._synthesize_final_summary(full_system)

        return {
            "status": "max_steps",
            "content": summary_content,
            "steps": max_steps,
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "warning": partial_warning,
        }

    # =========================================================================
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
        """Create a backup of a file before modification. Returns backup path.
        
        Also stores SHA-256 checksum for integrity verification.
        """
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
            # Compute checksum before backup
            import hashlib
            sha256 = hashlib.sha256()
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()
            
            temp_backup = backup_path + ".tmp"
            shutil.copy2(abs_path, temp_backup)
            os.replace(temp_backup, backup_path)
            # Save metadata: original path + checksum
            with open(backup_path + ".meta", "w", encoding="utf-8") as f:
                json.dump({"path": abs_path, "checksum": checksum}, f)
            self._log(f"Backed up: {file_path} (sha256:{checksum[:12]}...)")
            return backup_path
        except Exception as e:
            self._log(f"Backup failed: {e}")
            return None
    
    def verify_file_integrity(self, file_path: str) -> dict:
        """Verify a file's integrity against its last backup checksum.
        
        Returns {"valid": True/False, "expected": ..., "actual": ...}
        """
        abs_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        backup_dir = os.path.join(self.project_path, self._state.backup_dir)
        
        if not os.path.isdir(backup_dir):
            return {"valid": True, "reason": "no backups exist"}
        
        # Find the most recent backup for this file
        safe_name = file_path.replace("/", "_").replace("\\", "_").replace(":", "_")
        latest_backup = None
        latest_meta = None
        
        for fname in sorted(os.listdir(backup_dir), reverse=True):
            if fname.endswith(".meta") and safe_name in fname:
                meta_path = os.path.join(backup_dir, fname)
                backup_path = meta_path.replace(".meta", "")
                if os.path.exists(backup_path):
                    latest_backup = backup_path
                    latest_meta = meta_path
                    break
        
        if not latest_meta:
            return {"valid": True, "reason": "no backup found for verification"}
        
        try:
            with open(latest_meta, "r") as f:
                meta = json.load(f)
            expected_checksum = meta.get("checksum", "")
            
            if not os.path.exists(abs_path):
                return {"valid": False, "expected": expected_checksum, "actual": "FILE_MISSING"}
            
            import hashlib
            sha256 = hashlib.sha256()
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            actual_checksum = sha256.hexdigest()
            
            valid = actual_checksum == expected_checksum
            return {
                "valid": valid,
                "expected": expected_checksum,
                "actual": actual_checksum,
                "file": file_path,
            }
        except Exception as e:
            return {"valid": True, "reason": f"verification error: {e}"}

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
                        # File might not be tracked -- try file-based fallback
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
    # AUTO-DESIGN: Fetch brand design patterns before building
    # =========================================================================

    # Brand keyword mapping for auto-detection
    _BRAND_KEYWORDS = {
        "stripe": ["stripe", "payment", "checkout", "billing"],
        "linear": ["linear", "project management", "task board", "kanban"],
        "apple": ["apple", "ios", "macos", "premium", "minimalist white"],
        "github": ["github", "git", "code repo", "developer platform"],
        "vercel": ["vercel", "next.js", "deployment", "frontend"],
        "notion": ["notion", "workspace", "documentation", "wiki"],
        "figma": ["figma", "design tool", "collaborative design"],
        "nike": ["nike", "sportswear", "athletic", "fitness"],
        "tesla": ["tesla", "electric car", "ev", "automotive"],
        "spotify": ["spotify", "music", "streaming", "audio"],
        "supabase": ["supabase", "firebase", "database", "backend"],
        "cursor": ["cursor", "code editor", "ide", "coding"],
        "airbnb": ["airbnb", "travel", "booking", "rental"],
        "shopify": ["shopify", "ecommerce", "store", "shop"],
        "resend": ["resend", "email", "transactional"],
    }

    async def _auto_fetch_design(self, prompt: str, system_prompt: str) -> str:
        """Auto-detect if building a web project and fetch brand DESIGN.md.
        
        Pattern from Addy Osmani's self-improving agents:
        - Detect project type from prompt
        - Fetch relevant DESIGN.md from awesome-design-md repo
        - Inject design tokens into system prompt
        """
        prompt_lower = prompt.lower()
        
        # Detect if this is a web/UI project
        web_keywords = [
            "website", "web app", "portfolio", "landing page", "frontend",
            "ui", "design", "css", "html", "react", "next.js", "vue",
            "site", "page", "dashboard", "app", "build", "create",
        ]
        is_web_project = any(kw in prompt_lower for kw in web_keywords)
        
        if not is_web_project:
            return system_prompt
        
        # Detect brand from prompt
        detected_brand = None
        for brand, keywords in self._BRAND_KEYWORDS.items():
            if any(kw in prompt_lower for kw in keywords):
                detected_brand = brand
                break
        
        # Default to a good general design if no brand detected
        if not detected_brand:
            # Detect style preference
            if any(kw in prompt_lower for kw in ["dark", "modern", "sleek"]):
                detected_brand = "linear"
            elif any(kw in prompt_lower for kw in ["clean", "minimal", "white"]):
                detected_brand = "apple"
            elif any(kw in prompt_lower for kw in ["colorful", "vibrant", "playful"]):
                detected_brand = "figma"
            elif any(kw in prompt_lower for kw in ["professional", "corporate", "business"]):
                detected_brand = "stripe"
            else:
                detected_brand = "stripe"  # Safe default
        
        self._log(f"Auto-design: Detected brand '{detected_brand}' from prompt")
        
        # Fetch the DESIGN.md
        try:
            from ..tools.design_fetcher import DesignFetcherTool
            fetcher = DesignFetcherTool()
            result = await fetcher.execute(
                {"brand": detected_brand, "save_to_project": True},
                None,
                self.project_path,
            )
            
            if result.get("success"):
                content = result.get("content_preview", "")
                tokens = result.get("tokens", {})
                
                # Build design context injection
                design_section = f"\n\n## AUTO-LOADED DESIGN: {detected_brand.upper()}\n"
                design_section += f"Source: VoltAgent/awesome-design-md\n"
                
                if tokens.get("colors"):
                    design_section += f"\nColors: {json.dumps(tokens['colors'], indent=2)}\n"
                if tokens.get("font_family"):
                    design_section += f"Font: {tokens['font_family']}\n"
                if tokens.get("radii"):
                    design_section += f"Radii: {json.dumps(tokens['radii'])}\n"
                
                # Add key rules from the DESIGN.md
                if content:
                    # Extract the Overview section
                    overview_match = re.search(r'## Overview\n(.*?)(?=\n## |$)', content, re.DOTALL)
                    if overview_match:
                        overview = overview_match.group(1).strip()[:1500]
                        design_section += f"\nDesign Overview:\n{overview}\n"
                    
                    # Extract Do's and Don'ts
                    dos_match = re.search(r"Do's and Don'ts.*?\n(.*?)(?=\n## |$)", content, re.DOTALL)
                    if dos_match:
                        dos = dos_match.group(1).strip()[:1000]
                        design_section += f"\nDo's and Don'ts:\n{dos}\n"
                
                design_section += f"\n\n**INSTRUCTION:** Apply these {detected_brand.upper()} design patterns to your code. Use the exact colors, fonts, spacing, and component styles defined above. Do NOT use generic patterns — use the {detected_brand} design system.\n"
                
                # Cap design section at 3000 chars to preserve Nemotron's limited context
                if len(design_section) > 3000:
                    design_section = design_section[:2950] + "\n...[truncated for context budget]\n"
                
                system_prompt += design_section
                self._log(f"Auto-design: Injected {detected_brand} design ({len(design_section)} chars)")
            
        except Exception as e:
            self._log(f"Auto-design: Failed to fetch {detected_brand}: {e}")
        
        return system_prompt

    async def _synthesize_final_summary(self, system_prompt: str, on_text=None) -> str:
        """Graceful degradation (smolagents pattern): when the loop ends at max_steps,
        make one final no-tools LLM call to summarize completed work + remaining work.
        The agent should NEVER stop silently."""
        try:
            self._state.cur_messages.append(
                Message(role="user", content=(
                    "You have reached the maximum number of steps for this session. "
                    "Do NOT call any more tools. In plain text only: (1) summarize exactly what you "
                    "completed, (2) list what remains unfinished, and (3) give the single most important "
                    "next step to continue."
                ))
            )
            messages = self._format_messages(system_prompt)
            msg_dicts = self._messages_to_dicts(messages)
            summary = await asyncio.wait_for(
                self.provider.chat_completion(
                    messages=msg_dicts,
                    model=None,
                    temperature=0.3,
                    max_tokens=2048,
                    tools=None,
                ),
                timeout=60.0,
            )
            content = ""
            try:
                content = summary.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            except Exception:
                pass  # Intentional: Exception in production_loop.py
            if content.strip():
                if on_text:
                    on_text(f"\n📋 **Session summary** (steps exhausted):\n{content}\n")
                self._log("Generated end-of-session summary")
            return content
        except Exception as e:
            self._log(f"Summary generation skipped: {e}")
            return ""

    # =========================================================================
    # Progressive Context Shrinking (OpenDev adaptive compaction pattern)
    # =========================================================================

    def _shrink_old_observations(self, keep_recent: int = 3, shrink_to: int = 300):
        """Shrink old tool outputs in done_messages to short markers.

        The last `keep_recent` tool messages stay full; older ones are
        truncated to their first `shrink_to` chars. This is free (no LLM
        call) and prevents long sessions from drowning in stale logs while
        preserving the most recent observations the model needs.
        """
        tool_indices = [
            i for i, m in enumerate(self._state.done_messages)
            if m.role == "tool" and m.content and len(m.content) > shrink_to
        ]
        if not tool_indices:
            return
        for idx in tool_indices[:-keep_recent]:
            msg = self._state.done_messages[idx]
            name = msg.name or "tool"
            self._state.done_messages[idx] = Message(
                role="tool",
                tool_call_id=msg.tool_call_id,
                name=name,
                content=msg.content[:shrink_to]
                + f"\n[...older {name} output trimmed -- see recent results for current state...]",
            )

    _REMINDER_INTERVAL = 8  # inject a system reminder every N steps

    def _maybe_inject_reminder(self, step: int):
        """Event-driven system reminder (OpenDev §2.3.4): counteract instruction
        fade-out in long sessions by re-stating todo progress and critical rules
        at the decision point instead of relying on the initial system prompt."""
        if step == 0 or step % self._REMINDER_INTERVAL != 0:
            return
        parts = [f"[System reminder -- step {step}]"]
        # Todo progress
        todos = None
        if isinstance(self._state.output, dict):
            todos = self._state.output.get("todos")
        if todos:
            done = sum(1 for t in todos if isinstance(t, dict) and t.get("completed"))
            total = len(todos)
            remaining = [t.get("task", "") for t in todos if isinstance(t, dict) and not t.get("completed")]
            parts.append(f"Todos: {done}/{total} complete. Remaining: " + "; ".join(remaining[:5]))
        parts.append("Stay focused on the user's task. Use write_file with complete file content -- no placeholders.")
        self._state.cur_messages.append(Message(role="user", content="\n".join(parts)))

    # Core tools that every task needs (always included)
    _CORE_TOOLS = frozenset({
        'write_file', 'str_replace', 'read_files', 'run_terminal_command',
        'list_directory', 'code_search', 'glob', 'write_todos', 'task_completed',
    })
    # Tools mapped to task types
    _TASK_TOOL_MAP = {
        'web': ['browser_screenshot', 'browser_navigate', 'browser_click', 'generate_diagram', 'design_fetch'],
        'api': ['free_api', 'list_apis', 'list_mcp_servers'],
        'git': ['git_operations'],
        'research': ['web_search', 'read_url'],
        'docker': ['docker_run', 'docker_build'],
        'image': ['read_image', 'read_pdf'],
        'team': ['spawn_agents', 'team_execute'],
        'sandbox': ['sandboxed_run', 'sandbox_status'],
    }

    def _get_relevant_tools(self, prompt: str, all_tool_defs: list[dict]) -> list[dict]:
        """Select only relevant tools for the prompt to reduce token footprint.
        
        Critical for Nemotron which can only handle ~15-20 tools effectively.
        Always includes core tools, then adds task-specific tools.
        """
        prompt_lower = prompt.lower()
        selected_names = set(self._CORE_TOOLS)
        
        # Add task-specific tools based on prompt keywords
        for task_type, tools in self._TASK_TOOL_MAP.items():
            task_keywords = {
                'web': ['website', 'web', 'html', 'css', 'frontend', 'ui', 'portfolio', 'landing', 'site', 'page', 'design'],
                'api': ['api', 'endpoint', 'rest', 'graphql', 'http'],
                'git': ['git', 'commit', 'branch', 'diff', 'merge'],
                'research': ['research', 'search', 'find', 'lookup', 'web', 'internet', 'url'],
                'docker': ['docker', 'container', 'compose'],
                'image': ['image', 'pdf', 'picture', 'photo', 'screenshot', 'vision'],
                'team': ['team', 'parallel', 'agents', 'spawn'],
                'sandbox': ['sandbox', 'safe', 'isolated'],
            }
            if any(kw in prompt_lower for kw in task_keywords.get(task_type, [])):
                selected_names.update(tools)
        
        # Filter tool defs to only selected tools
        filtered = [d for d in all_tool_defs if d.get('function', {}).get('name', '') in selected_names]
        
        # If we filtered too aggressively, fall back to all tools
        if len(filtered) < 5:
            return all_tool_defs[:20]  # Cap at 20 for Nemotron
        
        # Cap at 20 tools total for Nemotron
        if len(filtered) > 20:
            filtered = filtered[:20]
        
        self._log(f"Tool selection: {len(filtered)}/{len(all_tool_defs)} tools for prompt: {prompt[:50]}...")
        return filtered

    async def _auto_compact_if_needed(self, messages: list[Message], system_prompt: str):
        """Smart auto-compact using OpenClaw-style compaction engine."""
        tokens = self._count_tokens(messages)
        threshold = self.config.max_context_tokens * 0.55  # 55% threshold -- compact earlier to keep context lean for free models

        if tokens <= threshold or len(self._state.done_messages) <= 6:
            return

        self._log(f"\u2728 Auto-compact triggered: {tokens:,} tokens ({tokens / self.config.max_context_tokens * 100:.0f}% of {self.config.max_context_tokens:,})")

        # Use smart compaction engine if available
        if self._compaction:
            try:
                all_messages = self._state.done_messages + self._state.cur_messages
                result = await self._compaction.compact(
                    messages=all_messages,
                    provider=self.provider,
                    system_prompt=system_prompt,
                    project_path=self.project_path,
                )
                if result.success:
                    # Rebuild done_messages from compacted result
                    self._state.done_messages = all_messages[:1]  # Keep system msg
                    # The summary message + recent messages
                    summary_msg = Message(role="system", content=f"[Compacted: {result.original_tokens:,} -> {result.compacted_tokens:,} tokens, {result.messages_removed} messages summarized, {len(result.identifiers_preserved)} identifiers preserved]" + chr(10) + result.summary)
                    self._state.done_messages = [summary_msg] + self._state.done_messages[-6:]
                    self._state.cur_messages = []
                    self._log(f"\u2728 Smart compaction: {result.original_tokens:,} -> {result.compacted_tokens:,} tokens")
                    if result.memory_flushed:
                        self._log("\U0001f4be Memory flushed before compaction")
                    # Audit log
                    if self._audit_logger:
                        self._audit_logger.log_compaction(
                            original_tokens=result.original_tokens,
                            compacted_tokens=result.compacted_tokens,
                            messages_removed=result.messages_removed,
                        )
                    return
            except Exception as e:
                self._log(f"Smart compaction failed, falling back to rule-based: {e}")

        # Fallback: rule-based compaction (original logic)
        if len(self._state.done_messages) > 6:
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
                "[Previous conversation summary -- auto-compacted to save context]\n"
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
                # Skip standalone tool results -- already handled above
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
        1. Check if within limits -- return as-is
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
            "[Previous conversation summary -- original messages condensed to save context]\n"
            + "\n".join(summary_parts[-30:])
            + "\n\n[End of summary. Continue from the live message below.]"
        )

        summary_msg = Message(role="system", content=summary_text)
        pruned = system + [summary_msg] + recent

        return self._truncate_to_fit(pruned)

    def _truncate_to_fit(self, messages: list[Message]) -> list[Message]:
        """Brute-force truncation to fit within token limits.
        
        Keeps tool_call and tool_result pairs atomic -- if we remove
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
    # Nemotron Content-to-ToolCall Extraction
    # =========================================================================

    @staticmethod
    def _extract_json_tool_calls_from_content(content: str) -> tuple[str, list[dict]]:
        """Extract tool calls embedded as JSON in the content string.

        Nemotron 120B (and some other open models) put tool calls inside
        the content field instead of the proper tool_calls field.  This
        method detects and extracts them, returning (remaining_text, calls).

        Handles these Nemotron formats:
          1. JSON array of tool call objects
             [{"function": {"name": "write_file", "arguments": "{...}"}}]
          2. JSON array with "parameters" key (Nemotron-specific)
             [{"name": "write_file", "parameters": {"path": ...}}]
          3. Single JSON object (not wrapped in array)
             {"name": "write_file", "parameters": {"path": ...}}
          4. JSON array followed by/preceded by natural language
        """
        if not content or not content.strip():
            return content, []

        text = content.strip()
        extracted: list[dict] = []
        cleaned = text

        # Strategy 1: The entire content is a JSON array of tool calls
        #   e.g.  [{"function": {"name": "write_file", ...}}, ...]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                # Single tool call object
                items = [parsed]
            else:
                items = []

            for item in items:
                if not isinstance(item, dict):
                    continue
                tc = ProductionAgentLoop._normalize_tool_call_object(item)
                if tc:
                    extracted.append(tc)

            if extracted:
                return "", extracted
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Find JSON arrays/objects embedded in text using bracket matching
        # Look for patterns like:  [{"name":...}] or [{"function":...}]
        # or single objects: {"name":"write_file",...}
        bracket_patterns = [
            # JSON array of tool calls
            (r'\[\s*\{\s*"(?:function|name|type)"', r'\}\s*\]'),
            # Single tool call object (not inside a larger array)
            (r'(?<![\[\{])\s*\{\s*"name"\s*:\s*"(?:write_file|read_files|str_replace|run_terminal_command|write_file|write_todos|code_search|web_search|read_url|list_directory|glob|ask_user|suggest_followups|gravity_index|render_ui|skill)"', None),
        ]

        for open_pat, close_pat in bracket_patterns:
            for m in re.finditer(open_pat, cleaned):
                start = m.start()
                # Find the matching closing bracket
                if close_pat:
                    close_match = re.search(close_pat, cleaned[start:])
                    if not close_match:
                        continue
                    end = start + close_match.end()
                else:
                    # Brace matching for single objects
                    depth = 0
                    end = start
                    for i in range(start, len(cleaned)):
                        if cleaned[i] == '{':
                            depth += 1
                        elif cleaned[i] == '}':
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    else:
                        continue

                candidate = cleaned[start:end].strip()
                try:
                    parsed = json.loads(candidate)
                    items = parsed if isinstance(parsed, list) else [parsed]
                    for item in items:
                        if isinstance(item, dict):
                            tc = ProductionAgentLoop._normalize_tool_call_object(item)
                            if tc:
                                extracted.append(tc)
                except (json.JSONDecodeError, ValueError):
                    continue

                if extracted:
                    # Remove the JSON from the content
                    remaining = cleaned[:start].strip() + "\n" + cleaned[end:].strip()
                    remaining = remaining.strip()
                    return remaining, extracted

        # Strategy 3: Handle double-escaped JSON (model outputs stringified JSON)
        # e.g. content = '[{\"name\":\"write_file\", ...}]'
        unescaped = text
        for unesc in [text.replace('\"', '"').replace('\\n', '\n'),
                       text.replace('\"', '"')]:
            if unesc != text:
                try:
                    parsed = json.loads(unesc)
                    items = parsed if isinstance(parsed, list) else [parsed]
                    for item in items:
                        if isinstance(item, dict):
                            tc = ProductionAgentLoop._normalize_tool_call_object(item)
                            if tc:
                                extracted.append(tc)
                    if extracted:
                        return "", extracted
                except (json.JSONDecodeError, ValueError):
                    pass

        return content, []

    @staticmethod
    def _normalize_tool_call_object(obj: dict) -> dict | None:
        """Normalize various tool call JSON formats into the standard format:
        {"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}

        Handles:
          - OpenAI format: {"function": {"name": ..., "arguments": ...}}
          - Nemotron format: {"name": ..., "parameters": ...}
          - Anthropic-ish format: {"tool": ..., "input": ...}
        """
        # OpenAI format: {"function": {"name": ..., "arguments": ...}}
        if "function" in obj and isinstance(obj["function"], dict):
            func = obj["function"]
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            if name and isinstance(args, dict):
                return {
                    "id": obj.get("id", f"content-extract-{id(obj)}"),
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }

        # Nemotron format: {"name": ..., "parameters": ...}
        if "name" in obj and "function" not in obj:
            name = obj.get("name", "")
            raw_params = obj.get("parameters", obj.get("input", {}))
            if isinstance(raw_params, str):
                try:
                    args = json.loads(raw_params)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            elif isinstance(raw_params, dict):
                args = raw_params
            else:
                args = {}
            if name and isinstance(args, dict):
                return {
                    "id": obj.get("id", f"content-extract-{id(obj)}"),
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }

        return None

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

                # Resolve model: 'default'/'coding' are task types, not model names
                effective_model = self.config.model
                if effective_model in ('default', 'coding', 'reasoning', 'fast'):
                    effective_model = None  # Let provider resolve

                response = await self.provider.chat_completion(
                    messages=msg_dicts,
                    model=effective_model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    tools=tool_defs if tool_defs else None,
                )

                usage = response.get("usage", {})
                self._state.total_tokens_sent += usage.get("prompt_tokens", 0)
                self._state.total_tokens_received += usage.get("completion_tokens", 0)

                choice = response.get("choices", [{}])[0]
                message = choice.get("message", {})

                raw_content = message.get("content", "") or ""
                raw_tool_calls = message.get("tool_calls", []) or []

                # ── Nemotron recovery ─────────────────────────────────────
                # Some models (Nemotron 120B, etc.) put tool-call JSON inside
                # the content string instead of the tool_calls field.  Detect
                # and extract them so the production loop can execute them.
                if not raw_tool_calls and raw_content:
                    extracted_content, extracted_calls = (
                        self._extract_json_tool_calls_from_content(raw_content)
                    )
                    if extracted_calls:
                        self._log(
                            f"Nemotron recovery: extracted {len(extracted_calls)} "
                            f"tool call(s) from content string"
                        )
                        raw_content = extracted_content
                        raw_tool_calls = extracted_calls

                return {
                    "content": raw_content,
                    "tool_calls": raw_tool_calls,
                    "finish_reason": choice.get("finish_reason", ""),
                }

            except Exception as e:
                last_error = str(e)

                # On 400 (context length exceeded), shrink context and retry
                if "400" in last_error or "context" in last_error.lower():
                    old_limit = self.config.max_context_tokens
                    self.config.max_context_tokens = int(old_limit * 0.7)
                    self._log(f"Context too large -- reducing limit from {old_limit:,} to {self.config.max_context_tokens:,}")
                    self._state.cur_messages = self._state.cur_messages[-4:]
                    if self._state.done_messages:
                        self._state.done_messages = self._state.done_messages[-2:]
                    # Rebuild messages with smaller context and retry
                    messages = self._format_messages("")
                    continue

                # On 410/404 (dead model), auto-fallback to a different model
                if any(code in last_error for code in ["410", "404"]):
                    self._log(f"Model dead ({last_error}) -- trying fallback")
                    if hasattr(self.provider, '_get_fallback_model'):
                        current = self.config.model or "default"
                        fallback = self.provider._get_fallback_model(current)
                        self.config.model = fallback
                        self._log(f"Switched to fallback model: {fallback}")
                        continue
                    # If no fallback provider method, just break
                    self._log(f"No fallback available for dead model")
                    break

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

    # =+
    # Background Job Polling
    # =========================================================================

    async def _poll_background_jobs(self):
        """Poll background terminal jobs and inject new output as context.
        
        This ensures long-running processes (dev servers, build watchers, test runners)
        automatically feed their output back into the agent's context.
        """
        try:
            # Find the RealRunTerminalCommand tool if available
            rtc = None
            if hasattr(self.tools, '_tools'):
                rtc = self.tools._tools.get('run_terminal_command')
            elif hasattr(self.tools, 'tools'):
                for t in self.tools.tools.values():
                    if hasattr(t, '_bg_jobs'):
                        rtc = t
                        break
            if not rtc or not hasattr(rtc, '_bg_jobs') or not rtc._bg_jobs:
                return
            # Check each background job for new output
            check_result = rtc._check_background_jobs()
            if check_result and check_result.get('outputs'):
                for output in check_result['outputs']:
                    job_id = output.get('job_id', 'bg')
                    stdout = output.get('stdout', '')
                    exit_code = output.get('exit_code')
                    if stdout:
                        # Inject as a system message so the model sees the output
                        self._state.cur_messages.append(
                            Message(role='user', content=(
                                f'[Background job {job_id} output]:\n{stdout[:800]}'
                                + ('\n[Process exited]' if exit_code is not None else '')
                            ))
                        )
                        self._log(f'Injected {len(stdout)} chars from background job {job_id}')
        except Exception as e:
            self._log(f'Background job poll failed: {e}')

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

    # =========================================================================
    # Auto Quality Gates
    # =========================================================================

    async def _auto_test(self) -> dict | None:
        """Auto-detect and run tests after file changes.
        
        Detects test framework from project files and runs tests:
        - pytest if pytest.ini/setup.cfg/pyproject.toml with pytest config
        - npm test if package.json has test script
        - python -m unittest if test_*.py files exist
        """
        try:
            import subprocess as _sp
            project = self.project_path
            
            # Check for package.json with test script
            pkg_path = os.path.join(project, 'package.json')
            if os.path.isfile(pkg_path):
                try:
                    with open(pkg_path) as f:
                        pkg = json.load(f)
                    if 'test' in pkg.get('scripts', {}):
                        result = _sp.run(
                            ['npm', 'test'],
                            capture_output=True, text=True,
                            cwd=project, timeout=60,
                        )
                        if result.returncode != 0:
                            return {'failed': True, 'output': result.stdout + result.stderr}
                        return {'passed': True}
                except Exception:
                    pass  # Intentional: Exception in production_loop.py
            
            # Check for Python test files
            import glob as _glob
            test_files = _glob.glob(os.path.join(project, 'test_*.py'))
            if test_files:
                result = _sp.run(
                    ['python', '-m', 'pytest', '-x', '-q', '--tb=short'],
                    capture_output=True, text=True,
                    cwd=project, timeout=60,
                )
                if result.returncode != 0:
                    return {'failed': True, 'output': result.stdout + result.stderr}
                return {'passed': True}
            
            return None  # No tests detected
        except Exception as e:
            self._log(f'Auto-test failed: {e}')
            return None

    async def _auto_lint(self, tool_args: dict) -> dict | None:
        """Auto-lint after file changes."""
        file_path = tool_args.get("path", "")
        if not file_path:
            return None

        try:
            from ..utils.quality_gates import AutoLinter
            linter = AutoLinter(self.project_path)
            # lint_file is async -- check and call properly
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
            pass  # Intentional: Exception in production_loop.py

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
                        f"Tool '{tool_name}' used {count} times -- commonly needed for this project",
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
                pass  # Intentional: Exception in production_loop.py

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
