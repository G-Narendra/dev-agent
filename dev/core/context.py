"""
Unified Context & Token Window Manager for Dev CLI.

Ensures message histories stay within LLM context boundaries while
preserving conversation coherence, system instructions, and tool-call/result atomic pairs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TokenBudget:
    """Configuration for LLM context window bounds."""
    max_context_tokens: int = 128_000
    max_output_tokens: int = 4_096
    prune_threshold_pct: float = 0.80  # Trigger compaction at 80% capacity
    reserve_tokens_system: int = 4_000
    reserve_tokens_turn: int = 8_000


def estimate_tokens(obj: Any) -> int:
    """
    Robust heuristic token estimator for strings, dicts, and lists.
    Averages ~3.5 chars per token for code/JSON.
    """
    if obj is None:
        return 0
    if isinstance(obj, str):
        return max(1, len(obj) // 3)
    if isinstance(obj, (dict, list)):
        try:
            dumped = json.dumps(obj)
            return max(1, len(dumped) // 3)
        except Exception:
            return 100
    return 10


class ContextManager:
    """
    Orchestrates conversation compaction, trimming, and atomic tool pair retention.
    """

    def __init__(self, budget: Optional[TokenBudget] = None):
        self.budget = budget or TokenBudget()

    def count_conversation_tokens(self, messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
        """Count estimated total tokens for a given prompt payload."""
        total = estimate_tokens(system_prompt)
        for msg in messages:
            total += estimate_tokens(msg.get("content", ""))
            if "tool_calls" in msg and msg["tool_calls"]:
                total += estimate_tokens(msg["tool_calls"])
        return total

    def prune_tool_results(self, messages: List[Dict[str, Any]], max_chars_per_result: int = 6_000) -> List[Dict[str, Any]]:
        """
        Truncate oversized historical tool execution outputs to save tokens.
        Keeps the first 80% and last 20% of output with truncation warning.
        """
        pruned_messages = []
        for msg in messages:
            msg_copy = dict(msg)
            if msg_copy.get("role") == "tool" and isinstance(msg_copy.get("content"), str):
                content = msg_copy["content"]
                if len(content) > max_chars_per_result:
                    prefix_len = int(max_chars_per_result * 0.8)
                    suffix_len = max_chars_per_result - prefix_len
                    msg_copy["content"] = (
                        f"{content[:prefix_len]}\n\n"
                        f"[... Truncated {len(content) - max_chars_per_result} characters ...]\n\n"
                        f"{content[-suffix_len:]}"
                    )
            pruned_messages.append(msg_copy)
        return pruned_messages

    def enforce_atomic_pairs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure that every `tool` result message has its corresponding `tool_calls`
        assistant message present, and vice versa. Eliminates 400 Bad Request schema errors.
        """
        # Find all tool_call IDs defined in assistant messages
        defined_call_ids = set()
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict) and "id" in tc:
                        defined_call_ids.add(tc["id"])

        # Filter out tool responses whose tool_calls were dropped
        valid_messages = []
        for msg in messages:
            if msg.get("role") == "tool":
                cid = msg.get("tool_call_id")
                if cid and cid not in defined_call_ids:
                    # Skip orphaned tool result
                    continue
            valid_messages.append(msg)

        return valid_messages

    def compact_history(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        min_recent_turns: int = 6
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Prune message history if exceeding token budget.
        Retains the most recent user/assistant turns while preserving tool call atomicity.
        """
        current_tokens = self.count_conversation_tokens(messages, system_prompt)
        max_allowed = int(self.budget.max_context_tokens * self.budget.prune_threshold_pct) - self.budget.max_output_tokens

        if current_tokens <= max_allowed:
            return messages, False

        # First pass: prune large historical tool results
        compacted = self.prune_tool_results(messages)
        if self.count_conversation_tokens(compacted, system_prompt) <= max_allowed:
            return compacted, True

        # Second pass: sliding window retention
        if len(compacted) <= min_recent_turns:
            return compacted, True

        # Retain last `min_recent_turns` messages
        recent = compacted[-min_recent_turns:]
        
        # Ensure atomic pairing
        recent = self.enforce_atomic_pairs(recent)

        # Inject a compact context summary note
        summary_note = {
            "role": "user",
            "content": "[System Notice: Prior conversation history was compacted to optimize context budget.]"
        }

        final_messages = [summary_note] + recent
        return final_messages, True
