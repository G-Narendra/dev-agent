"""
Apply Patch tool for Dev.

Adapted from Codex's apply-patch and Freebuff's apply-patch.ts.
Provides reliable file editing using unified diff format.
"""

from __future__ import annotations

import os
import re
from typing import Any

from .base import Tool



__all__ = ["ApplyPatchTool", "EditBlockTool"]

class ApplyPatchTool(Tool):
    """
    Apply a patch to a file using unified diff format.
    
    From Codex's apply-patch: atomic file changes with conflict detection.
    """
    
    name = "apply_patch"
    description = "Apply a patch to a file using unified diff format. More reliable than str_replace for large changes."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to patch",
            },
            "patch": {
                "type": "string",
                "description": "Unified diff patch (--- / +++ format)",
            },
        },
        "required": ["file_path", "patch"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        file_path = input_data["file_path"]
        patch = input_data["patch"]
        
        full_path = os.path.join(project_path, file_path)
        
        try:
            # Read original file
            with open(full_path, "r", encoding="utf-8") as f:
                original_lines = f.readlines()
            
            # Parse the patch
            hunks = self._parse_patch(patch)
            
            if not hunks:
                return {"success": False, "error": "No valid hunks found in patch"}
            
            # Apply hunks
            modified_lines = list(original_lines)
            applied_count = 0
            
            for hunk in reversed(hunks):  # Apply in reverse to maintain line numbers
                start_line = hunk["start_line"] - 1  # Convert to 0-indexed
                removed = hunk.get("removed", [])
                added = hunk.get("added", [])
                
                # Find the context lines to verify match
                context_before = hunk.get("context_before", [])
                
                # Verify context matches
                if context_before:
                    match_start = start_line - len(context_before)
                    if match_start >= 0:
                        actual_context = [
                            l.rstrip('\n') for l in original_lines[match_start:match_start + len(context_before)]
                        ]
                        expected_context = [l[1:].rstrip('\n') if l.startswith(' ') else l.rstrip('\n') for l in context_before]
                        
                        # Allow fuzzy matching (skip leading space)
                        for actual, expected in zip(actual_context, expected_context):
                            if actual.strip() != expected.strip():
                                return {
                                    "success": False,
                                    "error": f"Context mismatch at line {match_start + 1}",
                                    "expected": expected,
                                    "actual": actual,
                                }
                
                # Replace lines
                end_line = start_line + len(removed)
                modified_lines[start_line:end_line] = [l + '\n' for l in added]
                applied_count += 1
            
            # Write modified file
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(modified_lines)
            
            return {
                "success": True,
                "file_path": file_path,
                "hunks_applied": applied_count,
                "lines_changed": len(patch.split('\n')),
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _parse_patch(self, patch: str) -> list[dict]:
        """Parse a unified diff patch into hunks."""
        hunks = []
        lines = patch.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for hunk header: @@ -old,count +new,count @@
            hunk_match = re.match(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if hunk_match:
                start_line = int(hunk_match.group(2))
                i += 1
                
                context_before = []
                removed = []
                added = []
                
                while i < len(lines):
                    line = lines[i]
                    
                    if line.startswith('@@') or line.startswith('diff --git'):
                        break
                    
                    if line.startswith('-'):
                        removed.append(line[1:])
                    elif line.startswith('+'):
                        added.append(line[1:])
                    elif line.startswith(' '):
                        context_before.append(line)
                    elif line.startswith('\\'):
                        # "\ No newline at end of file"
                        pass
                    
                    i += 1
                
                hunks.append({
                    "start_line": start_line,
                    "context_before": context_before,
                    "removed": removed,
                    "added": added,
                })
            else:
                i += 1
        
        return hunks


class EditBlockTool(Tool):
    """
    Edit block format (SEARCH/REPLACE).
    
    From Aider's editblock_coder.py.
    More natural for LLMs to generate than unified diffs.
    """
    
    name = "edit_block"
    description = "Edit a file using SEARCH/REPLACE blocks. Specify exact text to find and its replacement."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to edit",
            },
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "Exact text to find (must match exactly)",
                        },
                        "replace": {
                            "type": "string",
                            "description": "Replacement text",
                        },
                    },
                    "required": ["search", "replace"],
                },
                "description": "List of SEARCH/REPLACE edits to apply",
            },
        },
        "required": ["file_path", "edits"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        file_path = input_data["file_path"]
        edits = input_data["edits"]
        
        full_path = os.path.join(project_path, file_path)
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            applied = 0
            for edit in edits:
                search = edit["search"]
                replace = edit["replace"]
                
                if search not in content:
                    return {
                        "success": False,
                        "error": f"Search text not found: {search[:50]}...",
                    }
                
                # Check for ambiguity
                count = content.count(search)
                if count > 1:
                    return {
                        "success": False,
                        "error": f"Ambiguous edit: {count} matches found for search text",
                    }
                
                content = content.replace(search, replace, 1)
                applied += 1
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return {
                "success": True,
                "file_path": file_path,
                "edits_applied": applied,
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
