"""
Repository Map for Dev.

Heavily adapted from Aider's repomap.py (867 lines).
Uses tree-sitter to parse code and extract definitions/references,
then uses a graph-based ranking algorithm (PageRank) to determine
which files are most relevant to the current context.

Key concepts from Aider:
1. Parse each file with tree-sitter to extract tags (defs/refs)
2. Build a graph where edges represent references between files
3. Use PageRank to rank files by importance
4. Generate a tree-formatted map showing relevant code sections
"""

from __future__ import annotations

import os
import math
import stat
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


# Language to file extension mapping
LANG_EXTENSIONS = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx", ".mts"],
    "rust": [".rs"],
    "go": [".go"],
    "java": [".java"],
    "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
    "c": [".c", ".h"],
    "ruby": [".rb"],
    "php": [".php"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "scala": [".scala"],
    "html": [".html", ".htm"],
    "css": [".css", ".scss", ".less"],
    "sql": [".sql"],
    "sh": [".sh", ".bash"],
    "json": [".json"],
    "yaml": [".yaml", ".yml"],
    "toml": [".toml"],
    "markdown": [".md", ".markdown"],
}

# Extensions to language mapping
EXT_TO_LANG = {}
for lang, exts in LANG_EXTENSIONS.items():
    for ext in exts:
        EXT_TO_LANG[ext] = lang

# Skip patterns
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target",
    "vendor", ".cache", ".tox", "egg-info",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll",
    ".exe", ".bin", ".dat", ".db", ".sqlite",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
}


class RepoMap:
    """
    Repository map generator.
    
    Adapted from Aider's RepoMap class.
    Parses code with regex (lightweight alternative to tree-sitter)
    and builds a ranked map of the codebase.
    """
    
    def __init__(
        self,
        root: str = ".",
        max_map_tokens: int = 1024,
        map_mul_no_files: int = 8,
    ):
        self.root = os.path.abspath(root)
        self.max_map_tokens = max_map_tokens
        self.map_mul_no_files = map_mul_no_files
        self._tag_cache: dict[str, list[dict]] = {}
        self._file_cache: dict[str, str] = {}
    
    def _get_rel_path(self, fname: str) -> str:
        """Get relative path from root."""
        try:
            return os.path.relpath(fname, self.root)
        except ValueError:
            return fname
    
    def _should_skip(self, path: str) -> bool:
        """Check if a path should be skipped."""
        parts = Path(path).parts
        for part in parts:
            if part in SKIP_DIRS or part.startswith("."):
                return True
        ext = Path(path).suffix.lower()
        if ext in SKIP_EXTENSIONS:
            return True
        return False
    
    def _read_file(self, fname: str) -> Optional[str]:
        """Read a file with caching."""
        if fname in self._file_cache:
            return self._file_cache[fname]
        try:
            with open(fname, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._file_cache[fname] = content
            return content
        except (OSError, PermissionError):
            return None
    
    def _extract_tags_tree_sitter(self, fname: str, rel_fname: str, content: str, ext: str) -> list[dict]:
        """
        Extract definitions using tree-sitter for accurate AST parsing.
        Falls back to regex if tree-sitter is not available.
        """
        try:
            import tree_sitter_languages
            lang_name = {
                '.py': 'python', '.js': 'javascript', '.jsx': 'javascript',
                '.ts': 'typescript', '.tsx': 'typescript',
                '.go': 'go', '.rs': 'rust', '.java': 'java',
                '.rb': 'ruby', '.c': 'c', '.cpp': 'cpp', '.h': 'c',
            }.get(ext)
            if not lang_name:
                return []
            
            parser = tree_sitter_languages.get_parser(lang_name)
            tree = parser.parse(content.encode('utf-8'))
            root_node = tree.root_node
            
            tags = []
            # Map node types to tag kinds
            def_nodes = {
                'python': ['function_definition', 'class_definition', 'decorated_definition'],
                'javascript': ['function_declaration', 'class_declaration', 'arrow_function', 'variable_declaration'],
                'typescript': ['function_declaration', 'class_declaration', 'arrow_function', 'variable_declaration', 'interface_declaration', 'type_alias_declaration'],
                'go': ['function_declaration', 'method_declaration', 'type_declaration'],
                'rust': ['function_item', 'struct_item', 'enum_item', 'impl_item'],
                'java': ['method_declaration', 'class_declaration', 'interface_declaration'],
                'ruby': ['method', 'class'],
                'c': ['function_definition', 'declaration'],
                'cpp': ['function_definition', 'declaration', 'class_specifier'],
            }
            
            target_types = def_nodes.get(lang_name, [])
            
            def walk(node, depth=0):
                if depth > 10:
                    return  # Prevent infinite recursion
                if node.type in target_types:
                    # Extract name from child nodes
                    name = ''
                    for child in node.children:
                        if child.type == 'identifier' or child.type == 'name':
                            name = child.text.decode('utf-8')
                            break
                    if name:
                        tags.append({
                            'name': name,
                            'kind': 'def',
                            'line': node.start_point[0],
                            'type': node.type,
                        })
                for child in node.children:
                    walk(child, depth + 1)
            
            walk(root_node)
            return tags
        except Exception:
            return []  # Fall back to regex
    
    def _extract_tags_regex(self, fname: str, rel_fname: str) -> list[dict]:
        """
        Extract definitions and references from a file.
        
        Uses tree-sitter if available (accurate AST parsing),
        falls back to regex (lightweight alternative).
        """
        if fname in self._tag_cache:
            return self._tag_cache[fname]
        
        content = self._read_file(fname)
        if not content:
            return []
        
        ext = Path(fname).suffix.lower()
        
        # Try tree-sitter first (accurate AST parsing)
        ts_tags = self._extract_tags_tree_sitter(fname, rel_fname, content, ext)
        if ts_tags:
            self._tag_cache[fname] = ts_tags
            return ts_tags
        
        # Fall back to regex
        tags = []
        
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Python definitions
            if ext == ".py":
                if stripped.startswith("def "):
                    name = stripped[4:].split("(")[0].strip()
                    tags.append({"name": name, "kind": "def", "line": i})
                elif stripped.startswith("class "):
                    name = stripped[6:].split("(")[0].split(":")[0].strip()
                    tags.append({"name": name, "kind": "def", "line": i})
                elif stripped.startswith("import ") or stripped.startswith("from "):
                    tags.append({"name": stripped, "kind": "ref", "line": i})
            
            # JavaScript/TypeScript definitions
            elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs"):
                if "function " in stripped or "=>" in stripped:
                    # Extract function names
                    for keyword in ["function ", "const ", "let ", "var "]:
                        if keyword in stripped:
                            after = stripped.split(keyword, 1)[1]
                            name = after.split("(")[0].split("=")[0].strip()
                            if name and not name.startswith("'") and not name.startswith('"'):
                                tags.append({"name": name, "kind": "def", "line": i})
                                break
                elif stripped.startswith("export ") or stripped.startswith("import "):
                    tags.append({"name": stripped[:80], "kind": "ref", "line": i})
                elif "class " in stripped and "{" in stripped:
                    name = stripped.split("class ")[1].split("{")[0].split("extends")[0].strip()
                    tags.append({"name": name, "kind": "def", "line": i})
            
            # Rust definitions
            elif ext == ".rs":
                for keyword in ["fn ", "struct ", "enum ", "impl ", "trait ", "pub fn ", "pub struct "]:
                    if keyword in stripped:
                        after = stripped.split(keyword, 1)[1]
                        name = after.split("(")[0].split("{")[0].split("<")[0].strip()
                        if name:
                            tags.append({"name": name, "kind": "def", "line": i})
                            break
                if stripped.startswith("use ") or stripped.startswith("mod "):
                    tags.append({"name": stripped[:80], "kind": "ref", "line": i})
            
            # Go definitions
            elif ext == ".go":
                for keyword in ["func ", "type ", "struct ", "interface "]:
                    if keyword in stripped:
                        after = stripped.split(keyword, 1)[1]
                        name = after.split("(")[0].split("{")[0].strip()
                        if name:
                            tags.append({"name": name, "kind": "def", "line": i})
                            break
                if stripped.startswith("import ") or stripped.startswith("package "):
                    tags.append({"name": stripped[:80], "kind": "ref", "line": i})
            
            # Generic: look for common patterns
            else:
                # Function-like definitions
                for pattern in ["def ", "function ", "fn ", "func "]:
                    if pattern in stripped:
                        after = stripped.split(pattern, 1)[1]
                        name = after.split("(")[0].split("{")[0].split(":")[0].strip()
                        if name and len(name) > 1:
                            tags.append({"name": name, "kind": "def", "line": i})
                            break
        
        self._tag_cache[fname] = tags
        return tags
    
    def _build_reference_graph(
        self,
        files: list[str],
        chat_files: set[str],
        mentioned_idents: set[str],
    ) -> dict[str, float]:
        """
        Build a reference graph and rank files using a simplified PageRank.
        
        From Aider's approach:
        - Files that define things referenced by chat files get higher rank
        - Files with more meaningful names get higher rank
        - Chat files get a personalization boost
        """
        # Collect all definitions and references
        defines = defaultdict(set)  # name -> set of files that define it
        references = defaultdict(list)  # name -> list of files that reference it
        
        for fname in files:
            rel_fname = self._get_rel_path(fname)
            tags = self._extract_tags_regex(fname, rel_fname)
            
            for tag in tags:
                if tag["kind"] == "def":
                    defines[tag["name"]].add(rel_fname)
                elif tag["kind"] == "ref":
                    references[tag["name"]].append(rel_fname)
        
        # Build scoring
        scores = defaultdict(float)
        
        # Base score for all files
        for fname in files:
            rel_fname = self._get_rel_path(fname)
            scores[rel_fname] = 1.0
        
        # Boost for chat files
        for fname in chat_files:
            rel_fname = self._get_rel_path(fname)
            scores[rel_fname] += 100.0
        
        # Score based on cross-references
        for ident in set(defines.keys()) | set(references.keys()):
            definers = defines.get(ident, set())
            referrers = references.get(ident, [])
            
            if not definers or not referrers:
                continue
            
            # Boost for meaningful identifiers
            mul = 1.0
            if ident in mentioned_idents:
                mul *= 10.0
            if len(ident) >= 8 and ("_" in ident or any(c.isupper() for c in ident)):
                mul *= 5.0
            if ident.startswith("_"):
                mul *= 0.1
            
            # Score: files that define things referenced by others
            for referrer in set(referrers):
                for definer in definers:
                    if referrer in chat_files:
                        scores[definer] += mul * 5.0
                    else:
                        scores[definer] += mul * 0.5
        
        return dict(scores)
    
    def _render_tree(
        self,
        ranked_files: list[tuple[str, float]],
        chat_rel_fnames: set[str],
        max_tokens: int,
    ) -> str:
        """
        Render a tree-formatted repo map.
        
        From Aider's to_tree: shows file paths with line numbers
        for relevant definitions.
        """
        output_lines = []
        estimated_tokens = 0
        
        for rel_fname, score in ranked_files:
            if rel_fname in chat_rel_fnames:
                continue
            
            abs_fname = os.path.join(self.root, rel_fname)
            tags = self._extract_tags_regex(abs_fname, rel_fname)
            
            # Estimate tokens for this file entry
            # File header: ~10 tokens
            # Each tag line: ~5 tokens
            file_tokens = 10 + len(tags) * 5
            
            if estimated_tokens + file_tokens > max_tokens:
                break
            
            # File header
            output_lines.append(f"\n{rel_fname}:")
            estimated_tokens += 10
            
            # Show definitions with line numbers
            for tag in tags:
                if tag["kind"] == "def":
                    line_str = f"  L{tag['line'] + 1}: {tag['name']}"
                    output_lines.append(line_str)
                    estimated_tokens += 5
        
        return "\n".join(output_lines)
    
    def get_repo_map(
        self,
        chat_files: list[str] | None = None,
        other_files: list[str] | None = None,
        mentioned_fnames: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
        max_map_tokens: int | None = None,
    ) -> str:
        """
        Generate a repo map for the given files.
        
        Args:
            chat_files: Files currently in the conversation
            other_files: Other files in the repo
            mentioned_fnames: File names mentioned in the prompt
            mentioned_idents: Identifiers (function/class names) mentioned
            max_map_tokens: Maximum tokens for the map
        
        Returns:
            A formatted string showing the repo structure
        """
        if max_map_tokens is None:
            max_map_tokens = self.max_map_tokens
        
        if not chat_files:
            chat_files = []
        if not other_files:
            other_files = []
        if not mentioned_fnames:
            mentioned_fnames = set()
        if not mentioned_idents:
            mentioned_idents = set()
        
        # Collect all files
        all_files = list(set(chat_files + other_files))
        if not all_files:
            # Scan the repo
            all_files = self._scan_repo()
        
        chat_rel_fnames = {self._get_rel_path(f) for f in chat_files}
        
        # Build reference graph and rank files
        scores = self._build_reference_graph(all_files, set(chat_files), mentioned_idents)
        
        # Sort by score (descending)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Render tree
        tree = self._render_tree(ranked, chat_rel_fnames, max_map_tokens)
        
        return tree
    
    MAX_FILES = 2000

    def _scan_repo(self) -> list[str]:
        """Scan the repository for source files."""
        files = []
        seen_inodes: set[int] = set()  # Track inodes to detect symlink loops
        for root, dirs, filenames in os.walk(self.root, followlinks=False):
            # Skip directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            
            for fname in filenames:
                fpath = os.path.join(root, fname)
                try:
                    st = os.lstat(fpath)
                    # Skip symlinks (prevent loops)
                    if stat.S_ISLNK(st.st_mode):
                        continue
                    # Skip device files, sockets, fifos
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    # Skip duplicate inodes (hardlink loops)
                    if st.st_ino in seen_inodes:
                        continue
                    seen_inodes.add(st.st_ino)
                except (OSError, PermissionError):
                    continue
                if not self._should_skip(fpath):
                    files.append(fpath)
                    if len(files) >= self.MAX_FILES:
                        return files
        
        return files


def get_repo_map(
    root: str = ".",
    chat_files: list[str] | None = None,
    max_tokens: int = 1024,
) -> str:
    """Convenience function to get a repo map."""
    rm = RepoMap(root=root, max_map_tokens=max_tokens)
    return rm.get_repo_map(chat_files=chat_files)
