"""
Context Pruner for Dev.

Adapted from:
- Aider's history.py (ChatSummary) - recursive summarization
- Freebuff's context-pruner.ts - message truncation and tool call summarization

Handles:
1. Token counting and budget management
2. Message summarization when context exceeds limits
3. Tool call result truncation
4. Progressive context compression
"""

from __future__ import annotations

import json
from typing import Any, Optional


# Approximate characters per token (matches Freebuff's heuristic)
CHARS_PER_TOKEN = 3

# Limits for truncating long messages (in estimated tokens)
USER_MESSAGE_LIMIT = 13_000
ASSISTANT_MESSAGE_LIMIT = 1_300
TOOL_ENTRY_LIMIT = 5_000

# Token budgets for summary
ASSISTANT_TOOL_BUDGET = 20_000
USER_BUDGET = 50_000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def truncate_long_text(text: str, limit: int) -> str:
    """
    Truncate long text with 80% from beginning and 20% from end.
    From Freebuff's context-pruner.ts.
    """
    if len(text) <= limit * CHARS_PER_TOKEN:
        return text
    
    char_limit = limit * CHARS_PER_TOKEN
    available = char_limit - 50  # Reserve for truncation notice
    prefix_len = int(available * 0.8)
    suffix_len = available - prefix_len
    
    prefix = text[:prefix_len]
    suffix = text[-suffix_len:] if suffix_len > 0 else ""
    truncated_chars = len(text) - prefix_len - suffix_len
    
    return f"{prefix}\n\n[...truncated {truncated_chars} chars...]\n\n{suffix}"


def summarize_tool_call(tool_name: str, tool_input: dict) -> str:
    """
    Summarize a tool call into a human-readable description.
    From Freebuff's context-pruner.ts.
    """
    if tool_name == "read_files":
        paths = tool_input.get("paths", [])
        if isinstance(paths, list):
            return f"Read {len(paths)} file(s): {', '.join(str(p)[:30] for p in paths[:5])}"
        return "Read files"
    
    elif tool_name == "write_file":
        path = tool_input.get("path", "unknown")
        return f"Write file: {path}"
    
    elif tool_name == "str_replace":
        path = tool_input.get("path", "unknown")
        replacements = tool_input.get("replacements", [])
        return f"Edit {path} ({len(replacements)} replacement(s))"
    
    elif tool_name == "run_terminal_command":
        cmd = tool_input.get("command", "")
        return f"Run: {cmd[:60]}"
    
    elif tool_name == "code_search":
        pattern = tool_input.get("pattern", "")
        return f"Search: {pattern[:40]}"
    
    elif tool_name == "web_search":
        query = tool_input.get("query", "")
        return f"Web search: {query[:40]}"
    
    elif tool_name == "read_url":
        url = tool_input.get("url", "")
        return f"Read URL: {url[:60]}"
    
    elif tool_name == "spawn_agents":
        agents = tool_input.get("agents", [])
        types = [a.get("agent_type", "?") for a in agents]
        return f"Spawn agents: {', '.join(types)}"
    
    elif tool_name == "write_todos":
        todos = tool_input.get("todos", [])
        completed = sum(1 for t in todos if t.get("completed"))
        return f"Update todos: {completed}/{len(todos)} completed"
    
    else:
        return f"Tool: {tool_name}"


class ContextPruner:
    """
    Manages conversation context within token limits.
    
    Adapted from Aider's ChatSummary and Freebuff's context-pruner.
    """
    
    def __init__(
        self,
        max_tokens: int = 100_000,
        warning_threshold: float = 0.8,
    ):
        self.max_tokens = max_tokens
        self.warning_threshold = warning_threshold
    
    def count_message_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in message history."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += estimate_tokens(part["text"])
            # Add overhead for message structure
            total += 4
        return total
    
    def needs_pruning(self, messages: list[dict]) -> bool:
        """Check if context needs pruning."""
        tokens = self.count_message_tokens(messages)
        return tokens > self.max_tokens * self.warning_threshold
    
    def prune(
        self,
        messages: list[dict],
        target_tokens: int | None = None,
    ) -> list[dict]:
        """
        Prune message history to fit within token limits.
        
        Strategy (from Aider's recursive approach):
        1. Keep recent messages intact
        2. Summarize older messages
        3. If still too large, recurse with deeper compression
        """
        if target_tokens is None:
            target_tokens = int(self.max_tokens * 0.7)
        
        current_tokens = self.count_message_tokens(messages)
        
        if current_tokens <= target_tokens:
            return messages
        
        # Split into head (old) and tail (recent)
        # Keep the last ~40% of messages as-is
        split_index = int(len(messages) * 0.6)
        
        # Ensure we split at a user message boundary
        while split_index > 0 and messages[split_index - 1].get("role") != "user":
            split_index -= 1
        
        if split_index < 4:
            # Not enough to summarize, truncate instead
            return self._truncate_messages(messages, target_tokens)
        
        head = messages[:split_index]
        tail = messages[split_index:]
        
        # Summarize the head
        summary = self._summarize_messages(head)
        
        # Combine summary + tail
        result = summary + tail
        
        # Check if we need to recurse
        result_tokens = self.count_message_tokens(result)
        if result_tokens > target_tokens:
            # Recurse with deeper compression
            return self.prune(result, target_tokens)
        
        return result
    
    def _summarize_messages(self, messages: list[dict]) -> list[dict]:
        """
        Summarize a list of messages into a compact format.
        
        From Aider's summarize_all:
        - Extract key information from user/assistant exchanges
        - Truncate long tool results
        - Preserve important context
        """
        summary_parts = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                # Keep system messages but truncate
                if isinstance(content, str):
                    summary_parts.append(f"[System]: {truncate_long_text(content, 500)}")
            
            elif role == "user":
                # Keep user messages but truncate long ones
                if isinstance(content, str):
                    truncated = truncate_long_text(content, USER_MESSAGE_LIMIT // 10)
                    summary_parts.append(f"[User]: {truncated}")
            
            elif role == "assistant":
                # Summarize assistant messages
                if isinstance(content, str):
                    truncated = truncate_long_text(content, ASSISTANT_MESSAGE_LIMIT // 10)
                    summary_parts.append(f"[Assistant]: {truncated}")
                
                # Summarize tool calls
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func = tc.get("function", {})
                        name = func.get("name", "unknown")
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        summary_parts.append(f"  -> {summarize_tool_call(name, args)}")
            
            elif role == "tool":
                # Truncate tool results heavily
                if isinstance(content, str):
                    truncated = truncate_long_text(content, TOOL_ENTRY_LIMIT // 10)
                    summary_parts.append(f"[Tool result]: {truncated}")
        
        # Create summary message
        summary_text = "\n".join(summary_parts)
        summary_text = (
            "This is a summary of the conversation so far. "
            "The original messages have been condensed to save context space.\n\n"
            + summary_text
            + "\n\n[End of summary. Continue from the live user message below.]"
        )
        
        return [{"role": "user", "content": summary_text}]
    
    def _truncate_messages(self, messages: list[dict], target_tokens: int) -> list[dict]:
        """Brute-force truncation as last resort."""
        result = []
        current_tokens = 0
        
        # Always keep the system message
        for msg in messages:
            if msg.get("role") == "system":
                result.append(msg)
                current_tokens += estimate_tokens(msg.get("content", ""))
        
        # Add messages from the end (most recent) until we hit the limit
        for msg in reversed(messages):
            if msg.get("role") == "system":
                continue
            
            msg_tokens = estimate_tokens(json.dumps(msg))
            if current_tokens + msg_tokens > target_tokens:
                break
            
            result.insert(-1 if result and result[0].get("role") == "system" else 0, msg)
            current_tokens += msg_tokens
        
        return result
    
    def get_context_stats(self, messages: list[dict]) -> dict:
        """Get statistics about the current context."""
        tokens = self.count_message_tokens(messages)
        return {
            "current_tokens": tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": round(tokens / self.max_tokens * 100, 1),
            "needs_pruning": self.needs_pruning(messages),
            "message_count": len(messages),
        }


class PruningContextManager:
    """
    Manages context for an agent run.
    
    Combines repo map, conversation history, and tool results
    within token budgets.
    """
    
    def __init__(
        self,
        max_context_tokens: int = 100_000,
        repo_map_tokens: int = 1024,
        system_prompt_tokens: int = 2000,
    ):
        self.max_context_tokens = max_context_tokens
        self.repo_map_tokens = repo_map_tokens
        self.system_prompt_tokens = system_prompt_tokens
        self.pruner = ContextPruner(max_tokens=max_context_tokens)
    
    def build_context(
        self,
        system_prompt: str,
        messages: list[dict],
        repo_map: str = "",
        extra_context: str = "",
    ) -> list[dict]:
        """
        Build a context window that fits within token limits.
        
        Priority:
        1. System prompt (always included)
        2. Repo map (high priority)
        3. Recent messages (high priority)
        4. Older messages (pruned if needed)
        """
        context = []
        used_tokens = 0
        
        # 1. System prompt
        system_tokens = estimate_tokens(system_prompt)
        used_tokens += system_tokens
        context.append({"role": "system", "content": system_prompt})
        
        # 2. Repo map (if space allows)
        if repo_map:
            map_tokens = estimate_tokens(repo_map)
            if used_tokens + map_tokens < self.max_context_tokens * 0.3:
                context.append({
                    "role": "system",
                    "content": f"Repository structure:\n{repo_map}",
                })
                used_tokens += map_tokens
        
        # 3. Extra context
        if extra_context:
            extra_tokens = estimate_tokens(extra_context)
            if used_tokens + extra_tokens < self.max_context_tokens * 0.4:
                context.append({"role": "system", "content": extra_context})
                used_tokens += extra_tokens
        
        # 4. Messages (with pruning if needed)
        available_tokens = self.max_context_tokens - used_tokens - 4096  # Reserve for response
        
        if messages:
            msg_tokens = self.pruner.count_message_tokens(messages)
            
            if msg_tokens <= available_tokens:
                context.extend(messages)
            else:
                # Prune messages to fit
                pruned = self.pruner.prune(messages, target_tokens=available_tokens)
                context.extend(pruned)
        
        return context
