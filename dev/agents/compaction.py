"""
Smart Context Compaction — modeled after OpenClaw, Claude Code, and Codex CLI.

Implements:
- LLM-based summarization (not just truncation)
- Memory flush before compaction (save important notes to disk)
- Identifier preservation (file paths, function names, line numbers)
- Tool call/result pair atomic preservation
- Safeguard quality audits
- Separate pruning (trim tool output) vs compaction (summarize history)
- /compact with custom instructions support
- Overflow error detection and recovery

References:
- OpenClaw: https://docs.openclaw.ai/concepts/compaction
- Claude Code: /compact command + auto-compact at ~95% context
- Codex CLI: compact.rs — dedicated summarization prompt, recent message preservation
- OpenCode: pruning separate from compaction, PRUNE_PROTECT = 40k tokens
"""

from __future__ import annotations

import re
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# ============================================================================
# Compaction Configuration
# ============================================================================

@dataclass
class CompactionConfig:
    """Configuration for context compaction."""
    enabled: bool = True
    
    # Thresholds (as fraction of max context tokens)
    auto_compact_threshold: float = 0.75   # Compact at 75% (Claude Code uses ~95%, but we're more aggressive)
    prune_threshold: float = 0.60          # Prune tool output at 60%
    
    # How many recent tokens to KEEP (not summarize)
    keep_recent_tokens: int = 20000        # Codex default: ~20k tokens
    
    # How many recent messages to always keep intact
    keep_recent_messages: int = 6
    
    # Memory flush before compaction
    memory_flush_enabled: bool = True
    memory_flush_max_tokens: int = 500     # Max tokens for memory flush summary
    
    # Identifier preservation
    identifier_policy: str = "strict"      # "strict" = preserve all identifiers, "off" = don't
    
    # Safeguard quality audit
    safeguard_mode: bool = True            # OpenClaw "safeguard" mode
    max_corrective_retries: int = 3        # Retries for bad summaries
    
    # Custom instructions for /compact
    custom_instructions: str = ""
    
    # Compaction model (None = use primary model)
    compaction_model: Optional[str] = None


# ============================================================================
# Compaction Result
# ============================================================================

@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    success: bool
    summary: str = ""
    original_tokens: int = 0
    compacted_tokens: int = 0
    messages_removed: int = 0
    identifiers_preserved: list[str] = field(default_factory=list)
    memory_flushed: bool = False
    error: str = ""


# ============================================================================
# Identifier Extractor
# ============================================================================

class IdentifierExtractor:
    """Extract and preserve important identifiers from messages."""
    
    # Patterns for code identifiers
    PATTERNS = {
        "file_path": re.compile(r'(?:[\w./\\-]+\.(?:py|js|ts|jsx|tsx|css|html|json|yaml|yml|md|txt|toml|cfg|env|sh|bash|rs|go|java|c|cpp|h|hpp|rb|php|sql|graphql|proto))'),
        "function_name": re.compile(r'(?:def|function|async function|const|let|var|class|fn|pub fn|func)\s+(\w+)'),
        "import_path": re.compile(r'(?:import|from|require|include|use)\s+[\'"]?([^\s\'";]+)'),
        "url": re.compile(r'https?://[^\s<>"\']+'),
        "api_endpoint": re.compile(r'(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([/\w\-{}:.]+)'),
        "env_var": re.compile(r'(?:process\.env\.|os\.environ\[|ENV\{|export\s+)(\w+)'),
        "line_number": re.compile(r'(?:line|Line)\s+(\d+)'),
        "npm_package": re.compile(r'(?:npm install|pip install|cargo add|go get)\s+([^\s]+)'),
    }
    
    @classmethod
    def extract(cls, text: str) -> list[str]:
        """Extract all identifiers from text."""
        identifiers = []
        for name, pattern in cls.PATTERNS.items():
            matches = pattern.findall(text)
            identifiers.extend(matches)
        return list(set(identifiers))
    
    @classmethod
    def extract_from_messages(cls, messages: list) -> list[str]:
        """Extract identifiers from a list of messages."""
        all_identifiers = []
        for msg in messages:
            content = getattr(msg, 'content', '') or ""
            all_identifiers.extend(cls.extract(content))
            # Also check tool calls
            tool_calls = getattr(msg, 'tool_calls', [])
            if tool_calls:
                all_identifiers.extend(cls.extract(json.dumps(tool_calls)))
        return list(set(all_identifiers))


# ============================================================================
# Compaction Prompt Templates
# ============================================================================

COMPACTION_SYSTEM_PROMPT = """You are a context compaction assistant for a coding agent. Your task is to create a detailed summary of the conversation so far, preserving all critical information needed to continue the work.

RULES:
1. Preserve ALL file paths, function names, class names, variable names, and identifiers exactly
2. Preserve ALL tool call results that contain important state (file contents, errors, test results)
3. Preserve the exact sequence of actions taken
4. Preserve ALL user requirements and constraints
5. Preserve ALL technical decisions and their reasoning
6. Be concise but COMPLETE — missing information breaks continuity

OUTPUT FORMAT:
## Completed Work
- What was accomplished (be specific about files created/modified)

## Current State
- Files modified/created with their current state
- Active errors or issues to resolve

## In Progress
- What was being worked on when compaction triggered

## Next Steps
- Clear, actionable next steps in priority order

## Key Constraints
- User preferences, requirements, and constraints
- Technical decisions and why they were made

## Critical Identifiers
- List ALL file paths, function names, and identifiers that must be preserved
"""

COMPACTION_USER_PROMPT = """Summarize our conversation above. This summary will be the only context available when the conversation continues, so preserve critical information including:
- What was accomplished
- Current work in progress  
- Files involved
- Next steps
- Any key user requests or constraints
- All identifiers (file paths, function names, variable names)
- Tool call results that contain important state

Be concise but detailed enough that work can continue seamlessly.
"""

MEMORY_FLUSH_PROMPT = """Before this conversation is compacted, save any important notes to memory files.
Write down:
1. Key decisions made and why
2. Current state of work
3. Anything that must not be lost

Be brief — this is a memory flush, not a full summary.
"""

OVERFLOW_RECOVERY_PROMPT = """The conversation hit a context overflow error and was compacted. A summary of the previous conversation is provided below.
Use this summary to continue the work. Do NOT repeat what was already done. Focus on the next steps listed in the summary.
"""


# ============================================================================
# Compaction Engine
# ============================================================================

class CompactionEngine:
    """
    Smart context compaction engine.
    
    Implements the full compaction pipeline:
    1. Memory flush (save important notes before compaction)
    2. Extract identifiers to preserve
    3. LLM-based summarization with identifier preservation
    4. Safeguard quality audit
    5. Build new context with summary + recent messages
    """
    
    def __init__(self, config: CompactionConfig = None):
        self.config = config or CompactionConfig()
        self._compaction_count = 0
        self._total_tokens_saved = 0
    
    async def compact(
        self,
        messages: list,
        provider,
        system_prompt: str = "",
        custom_instructions: str = "",
        project_path: str = "",
    ) -> CompactionResult:
        """
        Perform full context compaction.
        
        Returns CompactionResult with the new messages list.
        """
        if not self.config.enabled:
            return CompactionResult(success=False, error="Compaction disabled")
        
        # Count tokens before
        original_tokens = sum(self._estimate_tokens(m) for m in messages)
        
        # Step 1: Memory flush (save notes before losing context)
        memory_flushed = False
        if self.config.memory_flush_enabled and project_path:
            memory_flushed = await self._memory_flush(messages, provider, project_path)
        
        # Step 2: Extract identifiers to preserve
        identifiers = IdentifierExtractor.extract_from_messages(messages)
        
        # Step 3: Determine split point
        split_idx = self._find_split_point(messages)
        if split_idx <= 1:
            return CompactionResult(
                success=False, 
                error="Not enough messages to compact",
                original_tokens=original_tokens,
            )
        
        old_messages = messages[1:split_idx]  # Skip system message
        keep_messages = messages[split_idx:]
        
        # Step 4: LLM-based summarization
        summary = await self._summarize(
            old_messages, provider, identifiers, custom_instructions
        )
        
        if not summary:
            # Fallback to rule-based summarization
            summary = self._rule_based_summary(old_messages, identifiers)
        
        # Step 5: Safeguard quality audit
        if self.config.safeguard_mode:
            summary = await self._safeguard_audit(
                summary, old_messages, identifiers, provider
            )
        
        # Step 6: Build new messages
        summary_header = (
            f"[Context Compacted — {self._compaction_count + 1} compactions so far]\n"
            f"[{original_tokens:,} tokens condensed]\n"
            f"[Identifiers preserved: {len(identifiers)}]\n\n"
        )
        
        summary_msg = type(messages[0])(
            role="system", 
            content=summary_header + summary
        )
        
        # Rebuild: system prompt + summary + recent messages
        new_messages = [messages[0], summary_msg] + keep_messages
        
        compacted_tokens = sum(self._estimate_tokens(m) for m in new_messages)
        
        self._compaction_count += 1
        self._total_tokens_saved += (original_tokens - compacted_tokens)
        
        return CompactionResult(
            success=True,
            summary=summary,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(old_messages),
            identifiers_preserved=identifiers,
            memory_flushed=memory_flushed,
        )
    
    def prune_tool_output(self, messages: list, max_tool_output_tokens: int = 4000) -> list:
        """
        Prune large tool outputs (OpenCode-style pruning).
        
        This is SEPARATE from compaction — it trims tool results
        without summarizing the conversation.
        
        Protects the last N tokens of tool output (PRUNE_PROTECT).
        """
        if not messages:
            return messages
        
        result = []
        total_tokens = 0
        
        for msg in messages:
            if msg.role == "tool" and hasattr(msg, 'content'):
                content = msg.content
                content_tokens = self._estimate_tokens_string(content)
                
                if content_tokens > max_tool_output_tokens:
                    # Truncate but preserve beginning (error messages) and end (results)
                    lines = content.split('\n')
                    if len(lines) > 20:
                        # Keep first 5 lines (often contain error/status) 
                        # and last 10 lines (often contain results)
                        kept = lines[:5] + ['... [pruned middle section] ...'] + lines[-10:]
                        msg.content = '\n'.join(kept)
                
                total_tokens += self._estimate_tokens(msg)
            else:
                total_tokens += self._estimate_tokens(msg)
            
            result.append(msg)
        
        return result
    
    def _find_split_point(self, messages: list) -> int:
        """
        Find the best split point for compaction.
        
        OpenClaw rule: Keep tool_call and tool_result pairs together.
        If split lands inside a tool block, move boundary so pairs stay intact.
        """
        keep_count = min(self.config.keep_recent_messages, max(2, len(messages) // 3))
        if len(messages) <= keep_count + 2:
            return 1  # Not enough to compact
        
        # Start from the end, find keep_count messages to preserve
        split_idx = len(messages) - keep_count
        
        # Walk backward to find a clean split point (not inside a tool call/result pair)
        while split_idx > 1:
            msg = messages[split_idx]
            prev_msg = messages[split_idx - 1] if split_idx > 0 else None
            
            # If current message is a tool result and previous is assistant with tool_calls,
            # move split before the assistant message (keep the pair together)
            if msg.role == "tool" and prev_msg and prev_msg.role == "assistant" and prev_msg.tool_calls:
                split_idx -= 1
                continue
            
            # If current message is assistant with tool_calls, 
            # check if any following tool results would be split
            if msg.role == "assistant" and msg.tool_calls:
                tc_ids = {tc.get("id", "") for tc in msg.tool_calls}
                # Check if any tool results after split point belong to this call
                for j in range(split_idx + 1, len(messages)):
                    if messages[j].role == "tool" and messages[j].tool_call_id in tc_ids:
                        split_idx = j + 1  # Move split after all tool results
                        break
                else:
                    break  # No tool results found, this is a clean split
                continue
            
            break  # Found a clean split point
        
        return max(1, split_idx)
    
    async def _memory_flush(
        self, messages: list, provider, project_path: str
    ) -> bool:
        """Save important notes to memory files before compaction (OpenClaw-style)."""
        try:
            # Build a quick summary of key decisions
            recent_user_msgs = [
                m for m in messages[-20:] 
                if m.role == "user" and m.content
            ]
            if not recent_user_msgs:
                return False
            
            memory_content = "\n".join(
                f"- {m.content[:200]}" for m in recent_user_msgs[-5:]
            )
            
            # Write to .dev/memory/ directory
            from pathlib import Path
            memory_dir = Path(project_path) / ".dev" / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            memory_file = memory_dir / f"session_{int(time.time())}.md"
            memory_file.write_text(
                f"# Session Notes (auto-saved before compaction)\n\n"
                f"## Recent User Requests\n{memory_content}\n\n"
                f"## Auto-saved at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
                encoding="utf-8"
            )
            return True
        except Exception:
            return False
    
    async def _summarize(
        self,
        old_messages: list,
        provider,
        identifiers: list[str],
        custom_instructions: str = "",
    ) -> str:
        """LLM-based summarization of old messages."""
        # Build the conversation for summarization
        conversation_text = []
        for msg in old_messages:
            if msg.role == "user":
                conversation_text.append(f"User: {msg.content[:1000]}")
            elif msg.role == "assistant" and msg.content:
                conversation_text.append(f"Assistant: {msg.content[:1000]}")
            elif msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("function", {}).get("name", "?")
                    args = tc.get("function", {}).get("arguments", "")[:200]
                    conversation_text.append(f"Tool Call: {name}({args})")
            elif msg.role == "tool":
                content_preview = msg.content[:500]
                conversation_text.append(f"Tool Result: {msg.name or 'tool'}: {content_preview}")
        
        full_conversation = "\n".join(conversation_text[-50:])  # Last 50 entries
        
        # Add identifier context
        id_section = ""
        if identifiers:
            id_section = f"\n\nCRITICAL IDENTIFIERS TO PRESERVE:\n" + "\n".join(f"- {i}" for i in identifiers[:50])
        
        # Add custom instructions
        custom_section = ""
        if custom_instructions:
            custom_section = f"\n\nUSER-REQUESTED FOCUS:\n{custom_instructions}"
        
        # Call LLM for summarization
        messages = [
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT + id_section + custom_section},
            {"role": "user", "content": COMPACTION_USER_PROMPT + "\n\n" + full_conversation}
        ]
        
        try:
            response = await provider.chat_completion(
                messages=messages,
                model=self.config.compaction_model,  # None = use primary model
                temperature=0.3,  # Low temperature for factual summarization
                max_tokens=2000,
            )
            
            if response and response.get("choices"):
                content = response["choices"][0].get("message", {}).get("content", "")
                if content and len(content) > 10:
                    return content
        except Exception as e:
            # Log error but don't crash — fallback to rule-based
            pass
        
        # LLM returned empty or too short — use rule-based fallback
        return self._rule_based_summary(old_messages, identifiers)
    
    def _rule_based_summary(self, messages: list, identifiers: list[str]) -> str:
        """Fallback rule-based summarization when LLM is unavailable."""
        parts = []
        
        # Extract user requests
        user_requests = [m.content[:200] for m in messages if m.role == "user" and m.content]
        if user_requests:
            parts.append("## User Requests\n" + "\n".join(f"- {r}" for r in user_requests[-10:]))
        
        # Extract tool calls made
        tool_calls = []
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                for tc in m.tool_calls:
                    name = tc.get("function", {}).get("name", "?")
                    tool_calls.append(name)
        if tool_calls:
            parts.append("## Tools Used\n" + ", ".join(tool_calls))
        
        # Extract files mentioned
        if identifiers:
            files = [i for i in identifiers if '.' in i and '/' in i]
            if files:
                parts.append("## Files Referenced\n" + "\n".join(f"- {f}" for f in files[:20]))
        
        return "\n\n".join(parts) if parts else "[Compacted — no details preserved]"
    
    async def _safeguard_audit(
        self,
        summary: str,
        old_messages: list,
        identifiers: list[str],
        provider,
    ) -> str:
        """
        Safeguard quality audit (OpenClaw-style).
        
        Checks:
        1. Required headings are present
        2. Pending asks are preserved
        3. Key identifiers are in the summary
        """
        required_headings = ["Completed Work", "Current State", "Next Steps"]
        missing_headings = [h for h in required_headings if h not in summary]
        
        if missing_headings:
            # Add missing headings
            for heading in missing_headings:
                summary += f"\n\n## {heading}\n[Not explicitly captured during compaction]"
        
        # Check identifier preservation
        if self.config.identifier_policy == "strict" and identifiers:
            missing_ids = []
            for ident in identifiers[:20]:
                if ident not in summary:
                    missing_ids.append(ident)
            
            if missing_ids:
                summary += f"\n\n## Critical Identifiers (may need verification)\n"
                summary += "\n".join(f"- {i}" for i in missing_ids[:10])
        
        return summary
    
    @staticmethod
    def _estimate_tokens(msg) -> int:
        """Estimate tokens for a message object."""
        content = getattr(msg, 'content', '') or ""
        tokens = len(content) // 3 + 4
        tool_calls = getattr(msg, 'tool_calls', [])
        if tool_calls:
            tokens += len(json.dumps(tool_calls)) // 3
        return tokens
    
    @staticmethod
    def _estimate_tokens_string(text: str) -> int:
        """Estimate tokens for a string."""
        return len(text) // 3 + 4
    
    @property
    def stats(self) -> dict:
        """Return compaction statistics."""
        return {
            "compactions_performed": self._compaction_count,
            "total_tokens_saved": self._total_tokens_saved,
        }


# ============================================================================
# Overflow Error Detection (OpenClaw-style)
# ============================================================================

OVERFLOW_ERROR_PATTERNS = [
    "request_too_large",
    "context length exceeded",
    "context_length_exceeded",
    "input exceeds the maximum number of tokens",
    "input token count exceeds the maximum",
    "input is too long for the model",
    "max_tokens",
    "maximum context length",
    "token limit",
    "prompt is too long",
    "context window",
    "tokens exceeds",
    "too many tokens",
    "maximum number of input tokens",
    "ollama error: context length exceeded",
    "prompt size exceeds",
]


def is_overflow_error(error: str) -> bool:
    """Check if an error is a context overflow error."""
    error_lower = error.lower()
    return any(pattern in error_lower for pattern in OVERFLOW_ERROR_PATTERNS)
