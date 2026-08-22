"""
Context Compression Pipeline — Recursive Summarization

Inspired by Aider's ChatSummary, this module compresses conversation history
to fit within model context windows while preserving recent context.

Key techniques:
1. Recursive summarization: compress old messages into summaries
2. Smart truncation: keep recent messages in full, compress older ones
3. Tool result compression: compress verbose tool outputs
4. File context injection: add relevant code snippets on demand
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompressedContext:
    """Result of context compression."""
    messages: list  # Compressed message list
    original_tokens: int = 0
    compressed_tokens: int = 0
    summary: str = ""
    files_included: list = field(default_factory=list)


class ContextCompressor:
    """
    Compresses conversation history to fit within model context windows.
    
    Uses recursive summarization (Aider pattern):
    1. If total tokens > max_tokens, split messages in half
    2. Summarize the older half
    3. Keep the newer half intact
    4. If still too big, recurse (max depth 3)
    
    Also compresses:
    - Tool results (verbose outputs → key facts)
    - File contents (full files → relevant sections)
    - Old assistant messages (detailed → summary)
    """
    
    def __init__(self, provider=None, max_tokens: int = 128000, 
                 keep_recent: int = 6, max_depth: int = 3):
        """
        Args:
            provider: NIM provider for summarization calls
            max_tokens: Maximum tokens for compressed context
            keep_recent: Number of recent messages to keep in full
            max_depth: Maximum recursion depth for summarization
        """
        self.provider = provider
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self.max_depth = max_depth
        self._summary_cache = {}
    
    def compress(self, messages: list, task: str = "") -> CompressedContext:
        """
        Compress message history to fit within context window.
        
        Args:
            messages: List of Message objects
            task: Current task description for relevance scoring
            
        Returns:
            CompressedContext with compressed messages
        """
        if not messages:
            return CompressedContext(messages=[])
        
        # Estimate total tokens
        original_tokens = self._estimate_tokens(messages)
        
        # If already within budget, return as-is
        if original_tokens <= self.max_tokens * 0.8:
            return CompressedContext(
                messages=messages,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
            )
        
        # Split into system + conversation
        system_msgs = []
        conversation_msgs = []
        for msg in messages:
            if msg.role == "system":
                system_msgs.append(msg)
            else:
                conversation_msgs.append(msg)
        
        # Recursively compress conversation
        compressed_conversation = self._recursive_compress(
            conversation_msgs, depth=0
        )
        
        # Reconstruct full message list
        compressed_messages = system_msgs + compressed_conversation
        
        # Calculate compressed tokens
        compressed_tokens = self._estimate_tokens(compressed_messages)
        
        return CompressedContext(
            messages=compressed_messages,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            summary=f"Compressed from {original_tokens:,} to {compressed_tokens:,} tokens "
                    f"({(1 - compressed_tokens/original_tokens)*100:.0f}% reduction)",
        )
    
    def _recursive_compress(self, messages: list, depth: int) -> list:
        """Recursively compress messages until they fit within budget."""
        if depth > self.max_depth:
            return self._summarize_all(messages)
        
        total_tokens = self._estimate_tokens(messages)
        
        # If fits within budget, return as-is
        if total_tokens <= self.max_tokens * 0.7:
            return messages
        
        # Need at least 4 messages to split
        if len(messages) <= 4:
            return self._summarize_all(messages)
        
        # Split: keep recent half in full, summarize older half
        # Find split point (aim for 50/50 token split)
        half_tokens = self.max_tokens // 2
        tail_tokens = 0
        split_index = len(messages)
        
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = self._estimate_tokens([messages[i]])
            if tail_tokens + msg_tokens < half_tokens:
                tail_tokens += msg_tokens
                split_index = i
            else:
                break
        
        # Ensure split is at a reasonable point (after assistant message)
        while split_index > 1 and messages[split_index - 1].role != "assistant":
            split_index -= 1
        
        if split_index <= 2:
            # Can't split further, summarize everything
            return self._summarize_all(messages)
        
        # Split into head (compress) and tail (keep)
        head = messages[:split_index]
        tail = messages[split_index:]
        
        # Summarize head
        summarized_head = self._summarize_all(head)
        
        # Combine and check if fits
        result = summarized_head + tail
        result_tokens = self._estimate_tokens(result)
        
        if result_tokens <= self.max_tokens * 0.8:
            return result
        
        # Still too big, recurse with increased depth
        return self._recursive_compress(result, depth + 1)
    
    def _summarize_all(self, messages: list) -> list:
        """Summarize a list of messages into a single summary message."""
        if not messages:
            return []
        
        # Build content for summarization
        content_parts = []
        for msg in messages:
            role = msg.role.upper()
            if role not in ("USER", "ASSISTANT", "TOOL"):
                continue
            
            # Compress tool results
            if role == "TOOL":
                summary = self._compress_tool_result(msg)
                content_parts.append(f"# TOOL RESULT ({msg.name or 'unknown'})\n{summary}")
            else:
                # Truncate long messages
                text = msg.content or ""
                if len(text) > 2000:
                    text = text[:2000] + "\n... [truncated]"
                content_parts.append(f"# {role}\n{text}")
        
        if not content_parts:
            return []
        
        content = "\n\n".join(content_parts)
        
        # Try to summarize with LLM
        summary = self._llm_summarize(content)
        
        if summary:
            from dev.agents.production_loop import Message
            return [Message(
                role="assistant", 
                content=f"[Context Summary — {len(messages)} previous messages compressed]\n\n{summary}"
            )]
        
        # Fallback: keep last few messages, discard rest
        return messages[-self.keep_recent:]
    
    def _compress_tool_result(self, msg) -> str:
        """Compress a tool result to key facts only."""
        content = msg.content or ""
        
        # If short enough, keep as-is
        if len(content) < 500:
            return content
        
        # Try to parse as JSON (tool results are often JSON)
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                # Extract key info
                parts = []
                if "success" in data:
                    parts.append(f"Success: {data['success']}")
                if "path" in data:
                    parts.append(f"Path: {data['path']}")
                if "lines" in data:
                    parts.append(f"Lines: {data['lines']}")
                if "bytes" in data:
                    parts.append(f"Bytes: {data['bytes']}")
                if "error" in data:
                    parts.append(f"Error: {data['error']}")
                if "command" in data:
                    parts.append(f"Command: {data['command']}")
                if "stdout" in data:
                    stdout = data["stdout"]
                    if len(stdout) > 500:
                        stdout = stdout[:500] + "... [truncated]"
                    parts.append(f"Output: {stdout}")
                if parts:
                    return "; ".join(parts)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Generic compression: keep first 500 chars
        return content[:500] + f"\n... [compressed from {len(content)} chars]"
    
    def _llm_summarize(self, content: str) -> str:
        """Use LLM to summarize content. Returns None if fails."""
        if not self.provider:
            return None
        
        # Truncate if too long for summarization
        if len(content) > 30000:
            content = content[:30000] + "\n... [truncated for summarization]"
        
        try:
            import asyncio
            
            summary_prompt = f"""Summarize this conversation history concisely.
Focus on:
1. What the user asked for
2. What files were created/modified
3. Key decisions made
4. Current state of the project
5. What remains to be done

Keep the summary under 500 words. Be factual, not verbose.

CONVERSATION HISTORY:
{content}"""
            
            messages = [
                {"role": "system", "content": "You are a concise summarizer. Output only the summary."},
                {"role": "user", "content": summary_prompt},
            ]
            
            # Run async provider call
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context, use a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._async_summarize(messages)
                    )
                    result = future.result(timeout=30)
                    return result
            else:
                return asyncio.run(self._async_summarize(messages))
                
        except Exception as e:
            return None
    
    async def _async_summarize(self, messages: list) -> str:
        """Async LLM summarization call."""
        try:
            content = ""
            async for event in self.provider.chat_completion_stream_events(
                messages=messages,
                model="meta/llama-3.1-8b-instruct",
                temperature=0.3,
                max_tokens=1024,
                tools=None,
            ):
                if event.get("type") == "text":
                    content += event.get("content", "")
            return content.strip()
        except Exception:
            return None
    
    def compress_tool_results(self, messages: list) -> list:
        """Compress all tool results in a message list."""
        from dev.agents.production_loop import Message
        
        result = []
        for msg in messages:
            if msg.role == "tool":
                compressed_content = self._compress_tool_result(msg)
                result.append(Message(
                    role="tool",
                    content=compressed_content,
                    name=msg.name,
                    tool_call_id=msg.tool_call_id,
                ))
            else:
                result.append(msg)
        return result
    
    def get_relevant_files(self, task: str, file_contents: dict, 
                           max_tokens: int = 4000) -> str:
        """
        Extract relevant code sections based on task description.
        
        Args:
            task: Task description
            file_contents: Dict of {path: content}
            max_tokens: Maximum tokens for file context
            
        Returns:
            Formatted string with relevant code sections
        """
        if not file_contents:
            return ""
        
        # Simple keyword-based relevance scoring
        task_words = set(task.lower().split())
        
        scored_files = []
        for path, content in file_contents.items():
            # Skip binary/very large files
            if len(content) > 50000:
                continue
            
            # Score based on keyword overlap
            content_words = set(content.lower().split())
            overlap = len(task_words & content_words)
            
            # Boost score for file name matching task
            path_words = set(path.lower().replace("/", " ").replace(".", " ").split())
            path_overlap = len(task_words & path_words)
            
            score = overlap + (path_overlap * 3)
            scored_files.append((score, path, content))
        
        # Sort by score, take top files
        scored_files.sort(reverse=True)
        
        result_parts = []
        total_tokens = 0
        
        for score, path, content in scored_files:
            if total_tokens >= max_tokens:
                break
            
            # Truncate if needed
            file_tokens = len(content) // 4  # rough estimate
            if total_tokens + file_tokens > max_tokens:
                remaining = max_tokens - total_tokens
                content = content[:remaining * 4]
            
            result_parts.append(f"## {path}\n```\n{content}\n```")
            total_tokens += len(content) // 4
        
        return "\n\n".join(result_parts)
    
    def _estimate_tokens(self, messages: list) -> int:
        """Estimate token count for a list of messages."""
        total = 0
        for msg in messages:
            # Rough estimate: 1 token per 4 characters
            content = msg.content or ""
            total += len(content) // 4
            # Add overhead for role, tool calls, etc.
            total += 10
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                total += len(msg.tool_calls) * 50
        return total
