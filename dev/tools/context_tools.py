"""
Context tools for Dev - repo map and context pruning.

These wrap the repo_map and context_pruner utilities as agent tools,
following the same pattern as Freebuff's tools.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Tool


class RepoMapTool(Tool):
    """
    Generate a repository map showing code structure.
    
    Adapted from Aider's repo map - uses graph-based ranking
    to show the most relevant files and their definitions.
    """
    
    name = "repo_map"
    description = "Generate a map of the repository showing relevant files and their definitions. Use this to understand codebase structure before making changes."
    parameters = {
        "type": "object",
        "properties": {
            "chat_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files currently being discussed/edited",
            },
            "max_tokens": {
                "type": "integer",
                "default": 1024,
                "description": "Maximum tokens for the map",
            },
        },
    }
    
    def __init__(self):
        self._mapper = None
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..utils.repo_map import RepoMap
        
        chat_files = input_data.get("chat_files", [])
        max_tokens = input_data.get("max_tokens", 1024)
        
        # Resolve chat files to absolute paths
        abs_chat_files = []
        for f in chat_files:
            if os.path.isabs(f):
                abs_chat_files.append(f)
            else:
                abs_chat_files.append(os.path.join(project_path, f))
        
        mapper = RepoMap(root=project_path, max_map_tokens=max_tokens)
        repo_map = mapper.get_repo_map(chat_files=abs_chat_files)
        
        return {
            "repo_map": repo_map,
            "token_estimate": len(repo_map) // 3,
        }


class ContextStatsTool(Tool):
    """
    Get context usage statistics.
    
    Shows current token usage, message count, and whether pruning is needed.
    """
    
    name = "context_stats"
    description = "Get statistics about current context usage (tokens, messages, pruning status)"
    parameters = {
        "type": "object",
        "properties": {},
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..utils.context_pruner import ContextPruner
        
        pruner = ContextPruner()
        messages = state.message_history if state else []
        
        return pruner.get_context_stats(messages)


class SummarizeTool(Tool):
    """
    Summarize a conversation or text.
    
    Adapted from Aider's ChatSummary.summarize_all.
    """
    
    name = "summarize"
    description = "Summarize a text or conversation to reduce context size"
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to summarize",
            },
            "max_tokens": {
                "type": "integer",
                "default": 500,
                "description": "Maximum tokens in summary",
            },
        },
        "required": ["text"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..utils.context_pruner import truncate_long_text, estimate_tokens
        
        text = input_data["text"]
        # Coerce model-supplied values — models often send numbers as strings
        try:
            max_tokens = int(input_data.get("max_tokens", 500))
        except (TypeError, ValueError):
            max_tokens = 500
        
        current_tokens = estimate_tokens(text)
        
        if current_tokens <= max_tokens:
            return {"summary": text, "original_tokens": current_tokens, "summary_tokens": current_tokens}
        
        # Simple extractive summary: keep first 70% and last 30%
        char_limit = max_tokens * 3
        prefix_len = int(char_limit * 0.7)
        suffix_len = char_limit - prefix_len
        
        summary = text[:prefix_len] + "\n[...]\n" + text[-suffix_len:]
        
        return {
            "summary": summary,
            "original_tokens": current_tokens,
            "summary_tokens": estimate_tokens(summary),
        }
