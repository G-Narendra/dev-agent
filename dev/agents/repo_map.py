"""
Repo Map — Tree-Sitter Based Codebase Understanding

Inspired by Aider's repomap.py, this module builds a ranked map of the
codebase that helps the LLM understand project structure without reading
every file.

Key techniques:
1. Tree-sitter AST parsing for function/class extraction
2. Rank files by relevance to current task
3. Fit within token budget
4. Cache parsed results for performance
"""
import os
import re
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CodeTag:
    """A code entity (function, class, method, etc.)."""
    name: str
    kind: str  # "function", "class", "method", "variable", "import"
    line: int
    path: str
    signature: str = ""  # First line of the definition
    docstring: str = ""  # First docstring if present


@dataclass
class FileMap:
    """Map of a single file's code entities."""
    path: str
    tags: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    size: int = 0
    mtime: float = 0.0


class RepoMap:
    """
    Builds a ranked map of the codebase using regex-based parsing.
    
    For each file, extracts:
    - Function definitions
    - Class definitions
    - Method definitions
    - Imports
    
    Then ranks files by relevance to the current task and fits
    within a token budget.
    """
    
    # File extensions to analyze
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs',
        '.rb', '.cpp', '.c', '.h', '.hpp', '.cs', '.php', '.swift',
        '.kt', '.scala', '.clj', '.ex', '.exs', '.erl', '.hs',
        '.ml', '.fs', '.vue', '.svelte', '.astro',
    }
    
    # Directories to skip
    SKIP_DIRS = {
        'node_modules', '.git', '__pycache__', '.venv', 'venv',
        'dist', 'build', '.next', '.nuxt', 'coverage',
        '.dev', 'outputs', 'skills',
    }
    
    def __init__(self, root: str = ".", max_tokens: int = 1024,
                 cache_dir: str = ".dev/repo_map_cache"):
        self.root = os.path.abspath(root)
        self.max_tokens = max_tokens
        self.cache_dir = os.path.join(self.root, cache_dir)
        self._file_cache = {}
        self._map_cache = None
        self._cache_key = None
    
    def get_repo_map(self, chat_files: list = None, 
                     other_files: list = None,
                     mentioned_fnames: set = None,
                     mentioned_idents: set = None) -> str:
        """
        Get a ranked repo map fitting within token budget.
        
        Args:
            chat_files: Files currently in chat (full context)
            other_files: Other files in repo (summaries only)
            mentioned_fnames: File names mentioned in conversation
            mentioned_idents: Function/class names mentioned
            
        Returns:
            Formatted repo map string
        """
        if chat_files is None:
            chat_files = []
        if other_files is None:
            other_files = self._discover_files()
        if mentioned_fnames is None:
            mentioned_fnames = set()
        if mentioned_idents is None:
            mentioned_idents = set()
        
        # Build file maps
        file_maps = {}
        for f in other_files:
            if f in chat_files:
                continue  # Skip files already in chat
            file_map = self._get_file_map(f)
            if file_map and file_map.tags:
                file_maps[f] = file_map
        
        if not file_maps:
            return ""
        
        # Rank files by relevance
        ranked = self._rank_files(
            file_maps, chat_files, mentioned_fnames, mentioned_idents
        )
        
        # Fit within token budget
        result = self._format_within_budget(ranked, self.max_tokens)
        
        return result
    
    def _discover_files(self) -> list:
        """Discover all code files in the repository."""
        files = []
        for root, dirs, filenames in os.walk(self.root):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.CODE_EXTENSIONS:
                    files.append(os.path.join(root, fname))
        
        return files
    
    def _get_file_map(self, filepath: str) -> Optional[FileMap]:
        """Parse a file and extract code entities."""
        # Check cache
        cache_key = self._cache_key_for(filepath)
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]
        
        try:
            stat = os.stat(filepath)
            content = self._read_file(filepath)
            if not content:
                return None
            
            tags = self._extract_tags(filepath, content)
            imports = self._extract_imports(content)
            
            file_map = FileMap(
                path=filepath,
                tags=tags,
                imports=imports,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
            
            self._file_cache[cache_key] = file_map
            return file_map
            
        except Exception:
            return None
    
    def _read_file(self, filepath: str) -> str:
        """Read file content safely."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception:
            return ""
    
    def _extract_tags(self, filepath: str, content: str) -> list:
        """Extract code tags (functions, classes, methods) using regex."""
        tags = []
        ext = os.path.splitext(filepath)[1].lower()
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Python
            if ext == '.py':
                tags.extend(self._extract_python_tags(filepath, lines, i))
            
            # JavaScript/TypeScript
            elif ext in ('.js', '.ts', '.jsx', '.tsx'):
                tags.extend(self._extract_js_tags(filepath, lines, i))
            
            # Go
            elif ext == '.go':
                tags.extend(self._extract_go_tags(filepath, lines, i))
            
            # Rust
            elif ext == '.rs':
                tags.extend(self._extract_rust_tags(filepath, lines, i))
            
            # Generic (C, Java, etc.)
            else:
                tags.extend(self._extract_generic_tags(filepath, lines, i))
        
        return tags
    
    def _extract_python_tags(self, filepath: str, lines: list, idx: int) -> list:
        """Extract Python function/class definitions."""
        tags = []
        line = lines[idx].strip()
        
        # Class definition
        m = re.match(r'^class\s+(\w+)', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="class",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
            return tags
        
        # Function/method definition
        m = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\(', line)
        if m:
            # Check if it's a method (indented inside a class)
            is_method = lines[idx].startswith(' ') or lines[idx].startswith('\t')
            tags.append(CodeTag(
                name=m.group(1),
                kind="method" if is_method else "function",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
        
        return tags
    
    def _extract_js_tags(self, filepath: str, lines: list, idx: int) -> list:
        """Extract JavaScript/TypeScript function/class definitions."""
        tags = []
        line = lines[idx].strip()
        
        # Class definition
        m = re.match(r'^(?:export\s+)?(?:default\s+)?class\s+(\w+)', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="class",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
            return tags
        
        # Function definition (various patterns)
        patterns = [
            r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)',
            r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(',
            r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?function',
            r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*\(',
        ]
        for pattern in patterns:
            m = re.match(pattern, line)
            if m:
                tags.append(CodeTag(
                    name=m.group(1),
                    kind="function",
                    line=idx + 1,
                    path=filepath,
                    signature=line[:100],
                ))
                break
        
        return tags
    
    def _extract_go_tags(self, filepath: str, lines: list, idx: int) -> list:
        """Extract Go function/type definitions."""
        tags = []
        line = lines[idx].strip()
        
        # Function
        m = re.match(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="function",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
        
        # Type
        m = re.match(r'^type\s+(\w+)\s+struct', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="class",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
        
        return tags
    
    def _extract_rust_tags(self, filepath: str, lines: list, idx: int) -> list:
        """Extract Rust function/struct definitions."""
        tags = []
        line = lines[idx].strip()
        
        # Function
        m = re.match(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="function",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
        
        # Struct
        m = re.match(r'^(?:pub\s+)?struct\s+(\w+)', line)
        if m:
            tags.append(CodeTag(
                name=m.group(1),
                kind="class",
                line=idx + 1,
                path=filepath,
                signature=line,
            ))
        
        return tags
    
    def _extract_generic_tags(self, filepath: str, lines: list, idx: int) -> list:
        """Generic tag extraction for unsupported languages."""
        tags = []
        line = lines[idx].strip()
        
        # Function/method patterns
        patterns = [
            r'^(?:public|private|protected|static|async|export|const)?\s*(?:function|def|fn|func|sub)\s+(\w+)',
            r'^(?:public|private|protected)\s+(?:static\s+)?(?:async\s+)?(\w+)\s*\(',
        ]
        for pattern in patterns:
            m = re.match(pattern, line)
            if m:
                tags.append(CodeTag(
                    name=m.group(1),
                    kind="function",
                    line=idx + 1,
                    path=filepath,
                    signature=line[:100],
                ))
                break
        
        return tags
    
    def _extract_imports(self, content: str) -> list:
        """Extract import statements."""
        imports = []
        for line in content.split('\n')[:30]:  # Only first 30 lines
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ', 'require(', 'use ')):
                imports.append(stripped[:100])
        return imports
    
    def _rank_files(self, file_maps: dict, chat_files: list,
                    mentioned_fnames: set, mentioned_idents: set) -> list:
        """Rank files by relevance to current context."""
        scored = []
        
        for path, file_map in file_maps.items():
            score = 0
            
            # Boost for files with many tags (important files)
            score += len(file_map.tags) * 2
            
            # Boost for files mentioned by name
            fname = os.path.basename(path)
            if fname in mentioned_fnames:
                score += 50
            
            # Boost for files with mentioned identifiers
            for tag in file_map.tags:
                if tag.name in mentioned_idents:
                    score += 30
            
            # Boost for files imported by chat files
            for chat_file in chat_files:
                chat_map = self._get_file_map(chat_file)
                if chat_map:
                    for imp in chat_map.imports:
                        if fname in imp:
                            score += 20
            
            # Boost for smaller files (more focused)
            if file_map.size < 5000:
                score += 5
            
            scored.append((score, path, file_map))
        
        # Sort by score descending
        scored.sort(reverse=True, key=lambda x: x[0])
        
        return scored
    
    def _format_within_budget(self, ranked_files: list, max_tokens: int) -> str:
        """Format ranked files within token budget."""
        parts = ["## Repository Structure\n"]
        current_tokens = len(parts[0]) // 4
        
        for score, path, file_map in ranked_files:
            if current_tokens >= max_tokens:
                break
            
            # Format file summary
            rel_path = os.path.relpath(path, self.root)
            
            # List tags (functions/classes)
            tag_names = []
            for tag in file_map.tags:
                icon = {"function": "fn", "method": "fn", "class": "cl"}.get(tag.kind, "?")
                tag_names.append(f"{icon}:{tag.name}")
            
            if tag_names:
                file_summary = f"- {rel_path}: {', '.join(tag_names[:10])}"
            else:
                file_summary = f"- {rel_path}"
            
            # Estimate tokens
            summary_tokens = len(file_summary) // 4
            if current_tokens + summary_tokens > max_tokens:
                break
            
            parts.append(file_summary)
            current_tokens += summary_tokens
        
        return '\n'.join(parts)
    
    def _cache_key_for(self, filepath: str) -> str:
        """Generate cache key for a file."""
        try:
            stat = os.stat(filepath)
            return f"{filepath}:{stat.st_mtime}:{stat.st_size}"
        except Exception:
            return filepath
    
    def invalidate_cache(self, filepath: str = None):
        """Invalidate cache for a file or all files."""
        if filepath:
            key = self._cache_key_for(filepath)
            self._file_cache.pop(key, None)
        else:
            self._file_cache.clear()
