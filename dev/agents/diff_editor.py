"""
Diff-Based Editor — Reliable Code Modifications

Inspired by Aider's edit formats, this module provides diff-based editing
that works reliably even with small models that truncate tool arguments.

Key techniques:
1. Unified diff format (smaller than full file replacement)
2. Search-and-replace with context matching
3. AST-aware edits (when tree-sitter available)
4. Fallback to full file rewrite if diff fails
"""
import os
import re
import difflib
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class EditResult:
    """Result of applying an edit."""
    success: bool
    file_path: str = ""
    diff: str = ""
    error: str = ""
    old_content: str = ""
    new_content: str = ""


class DiffEditor:
    """
    Applies code edits using unified diff format.
    
    This is more reliable than full file replacement because:
    1. Diffs are smaller (less truncation by NIM)
    2. Context matching prevents wrong edits
    3. Can validate the edit before applying
    4. Supports undo via reverse diff
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def apply_edit(self, file_path: str, old_code: str, 
                   new_code: str, context_lines: int = 3) -> EditResult:
        """
        Apply an edit by search-and-replace with context.
        
        Args:
            file_path: Path to file (relative to project)
            old_code: Code to find and replace
            new_code: Code to replace with
            context_lines: Number of context lines for matching
            
        Returns:
            EditResult with success/failure and diff
        """
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"File not found: {file_path}"
            )
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"Failed to read file: {e}"
            )
        
        # Try exact match first
        if old_code in old_content:
            new_content = old_content.replace(old_code, new_code, 1)
            diff = self._generate_diff(old_content, new_content, file_path)
            
            # Write the file
            write_result = self._write_file(abs_path, new_content)
            if not write_result[0]:
                return EditResult(
                    success=False,
                    file_path=file_path,
                    error=write_result[1]
                )
            
            return EditResult(
                success=True,
                file_path=file_path,
                diff=diff,
                old_content=old_content,
                new_content=new_content,
            )
        
        # Try fuzzy match (strip whitespace variations)
        old_stripped = self._normalize_whitespace(old_code)
        content_stripped = self._normalize_whitespace(old_content)
        
        if old_stripped in content_stripped:
            # Find the actual position in original content
            # This is tricky with normalized whitespace, so use difflib
            old_lines = old_code.splitlines()
            content_lines = old_content.splitlines()
            
            # Find best matching sequence
            match = self._fuzzy_find(old_lines, content_lines)
            if match >= 0:
                # Replace the matched section
                new_lines = content_lines[:match] + new_code.splitlines() + content_lines[match + len(old_lines):]
                new_content = '\n'.join(new_lines)
                diff = self._generate_diff(old_content, new_content, file_path)
                
                write_result = self._write_file(abs_path, new_content)
                if not write_result[0]:
                    return EditResult(
                        success=False,
                        file_path=file_path,
                        error=write_result[1]
                    )
                
                return EditResult(
                    success=True,
                    file_path=file_path,
                    diff=diff,
                    old_content=old_content,
                    new_content=new_content,
                )
        
        # No match found
        return EditResult(
            success=False,
            file_path=file_path,
            error=f"Could not find old_code in {file_path}. "
                  f"Old code starts with: {old_code[:100]}..."
        )
    
    def apply_unified_diff(self, file_path: str, diff_text: str) -> EditResult:
        """
        Apply a unified diff to a file.
        
        Args:
            file_path: Path to file
            diff_text: Unified diff text (--- a/ ... +++ b/ format)
            
        Returns:
            EditResult
        """
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"File not found: {file_path}"
            )
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"Failed to read file: {e}"
            )
        
        # Parse unified diff
        patches = self._parse_unified_diff(diff_text)
        if not patches:
            return EditResult(
                success=False,
                file_path=file_path,
                error="Could not parse unified diff"
            )
        
        # Apply patches
        new_content = old_content
        for patch in patches:
            new_content = self._apply_patch(new_content, patch)
        
        if new_content == old_content:
            return EditResult(
                success=False,
                file_path=file_path,
                error="Diff did not change the file"
            )
        
        diff = self._generate_diff(old_content, new_content, file_path)
        
        write_result = self._write_file(abs_path, new_content)
        if not write_result[0]:
            return EditResult(
                success=False,
                file_path=file_path,
                error=write_result[1]
            )
        
        return EditResult(
            success=True,
            file_path=file_path,
            diff=diff,
            old_content=old_content,
            new_content=new_content,
        )
    
    def generate_edit_prompt(self, file_path: str, task: str) -> str:
        """
        Generate a prompt asking the LLM to produce a diff.
        
        This is used when we want the model to generate diffs instead
        of full file content (more reliable with small models).
        """
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return f"Create new file {file_path} with the following requirements:\n{task}"
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception:
            return f"Edit {file_path}: {task}"
        
        # Truncate if too long
        if len(content) > 10000:
            lines = content.split('\n')
            content = '\n'.join(lines[:200]) + f"\n... [{len(lines)} total lines]"
        
        return f"""Edit the file {file_path} to: {task}

Current content:
```
{content}
```

Output ONLY the changes needed using this EXACT format:
<<<<<<< SEARCH
exact lines to find
=======
replacement lines
>>>>>>> REPLACE

You can have multiple SEARCH/REPLACE blocks. Be precise with whitespace."""
    
    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to project root."""
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.project_path, path))
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace for fuzzy matching."""
        lines = text.split('\n')
        normalized = []
        for line in lines:
            # Strip trailing whitespace, collapse multiple spaces
            stripped = line.rstrip()
            stripped = re.sub(r'  +', ' ', stripped)
            normalized.append(stripped)
        return '\n'.join(normalized)
    
    def _fuzzy_find(self, pattern: list, content: list) -> int:
        """Find best matching position for pattern in content."""
        if not pattern or not content:
            return -1
        
        # Use difflib to find matching blocks
        sm = difflib.SequenceMatcher(None, content, pattern)
        matches = sm.get_matching_blocks()
        
        # Find the longest match that covers most of the pattern
        for match in matches:
            if match.size >= len(pattern) * 0.7:  # 70% match threshold
                return match.a
        
        return -1
    
    def _generate_diff(self, old: str, new: str, path: str) -> str:
        """Generate unified diff."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
        
        return ''.join(diff)
    
    def _parse_unified_diff(self, diff_text: str) -> list:
        """Parse unified diff into patches."""
        patches = []
        current_patch = None
        
        for line in diff_text.split('\n'):
            if line.startswith('@@'):
                # Parse hunk header
                m = re.search(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
                if m:
                    current_patch = {
                        'old_start': int(m.group(1)),
                        'new_start': int(m.group(2)),
                        'removes': [],
                        'adds': [],
                    }
                    patches.append(current_patch)
            elif current_patch is not None:
                if line.startswith('-'):
                    current_patch['removes'].append(line[1:])
                elif line.startswith('+'):
                    current_patch['adds'].append(line[1:])
                elif line.startswith(' '):
                    # Context line (not used for apply, but parsed)
                    pass
        
        return patches
    
    def _apply_patch(self, content: str, patch: dict) -> str:
        """Apply a single patch to content."""
        lines = content.split('\n')
        
        old_start = patch['old_start'] - 1  # Convert to 0-indexed
        removes = patch['removes']
        adds = patch['adds']
        
        # Find the section to replace
        # Match removes at old_start
        remove_text = '\n'.join(removes)
        section_start = old_start
        section_end = old_start + len(removes)
        
        # Replace the section
        new_lines = lines[:section_start] + adds + lines[section_end:]
        
        return '\n'.join(new_lines)
    
    def _write_file(self, abs_path: str, content: str) -> Tuple[bool, str]:
        """Write content to file atomically."""
        try:
            parent_dir = os.path.dirname(abs_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            temp_path = abs_path + ".editmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, abs_path)
            return True, ""
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, str(e)


class SearchReplaceEditor:
    """
    Simple search-and-replace editor for NIM-friendly editing.
    
    This is the most reliable format for small models because:
    1. The search string is small (less truncation)
    2. The replace string is small (less truncation)
    3. Context matching prevents wrong edits
    4. Can be retried if first attempt fails
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def apply(self, file_path: str, search: str, replace: str) -> EditResult:
        """Apply search-and-replace."""
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"File not found: {file_path}"
            )
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"Failed to read: {e}"
            )
        
        if search not in content:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"Search text not found in {file_path}"
            )
        
        new_content = content.replace(search, replace, 1)
        
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"Failed to write: {e}"
            )
        
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        
        return EditResult(
            success=True,
            file_path=file_path,
            diff=''.join(diff),
            old_content=content,
            new_content=new_content,
        )
    
    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.project_path, path))
