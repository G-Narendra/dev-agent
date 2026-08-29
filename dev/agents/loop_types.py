"""
Data classes and constants for the production agent loop.

Extracted from production_loop.py to reduce file size and improve maintainability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


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
    max_tokens: int = 32768  # High enough for complete file generation in one shot
    max_retries: int = 5
    retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    auto_lint: bool = True
    auto_test: bool = True
    auto_commit: bool = True
    verbose: bool = False
    show_diffs: bool = True
    use_repo_map: bool = True
    repo_map_tokens: int = 1024
    max_context_tokens: int = 128_000  # NVIDIA NIM context window
    approval_mode: str = "auto-edit"  # suggest, auto-edit, full-auto
    diff_preview: bool = False  # Show diff before applying edits
    enforce_plan_mode: bool = False  # If True, only read-only actions allowed
    # Research-backed loop safety (Codex/smolagents patterns)
    max_identical_tool_repeats: int = 3  # Same tool+args N times consecutively → inject correction
    max_consecutive_empty: int = 3  # Empty responses in a row → corrective nudge, then abort
    max_consecutive_failures: int = 4  # Failed LLM steps in a row → abort early with summary


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
    # Additional fields used by production loop
    context_tokens: int = 0
    max_context_tokens: int = 128_000
    current_step: int = 0
    max_steps: int = 50
    tool_stats: list[dict] = field(default_factory=list)


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
