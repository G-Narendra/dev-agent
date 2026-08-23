"""
Project Auto-Detect for Dev.

Detects project language, framework, and configuration.
Adapted from Aider's project detection patterns.

Improvement #14: Project auto-detect
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProjectInfo:
    """Detected project information."""
    language: str = "unknown"
    framework: str = "unknown"
    package_manager: str = "unknown"
    test_framework: str = "unknown"
    linter: str = "unknown"
    formatter: str = "unknown"
    root_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    source_dirs: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)


class ProjectDetector:
    """
    Detects project type and configuration.
    
    From Aider's project detection:
    - Detect language from file extensions
    - Detect framework from dependencies
    - Detect package manager from lock files
    - Detect test framework from config
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
    
    def detect(self) -> ProjectInfo:
        """Detect project information."""
        info = ProjectInfo()
        
        # Detect language
        info.language = self._detect_language()
        
        # Detect framework
        info.framework = self._detect_framework()
        
        # Detect package manager
        info.package_manager = self._detect_package_manager()
        
        # Detect test framework
        info.test_framework = self._detect_test_framework()
        
        # Detect linter
        info.linter = self._detect_linter()
        
        # Detect formatter
        info.formatter = self._detect_formatter()
        
        # Find config files
        info.config_files = self._find_config_files()
        
        # Find source dirs
        info.source_dirs = self._find_source_dirs()
        
        # Find test dirs
        info.test_dirs = self._find_test_dirs()
        
        # Find entry points
        info.entry_points = self._find_entry_points()
        
        # Load dependencies
        deps = self._load_dependencies()
        info.dependencies = deps.get("dependencies", {})
        info.dev_dependencies = deps.get("dev_dependencies", {})
        
        return info
    
    def _detect_language(self) -> str:
        """Detect primary language."""
        ext_counts = {}
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
                "dist", "build", ".next",
            )]
            
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php"):
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
        
        if not ext_counts:
            return "unknown"
        
        # Map extensions to languages
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
        }
        
        max_ext = max(ext_counts, key=ext_counts.get)
        return ext_to_lang.get(max_ext, "unknown")
    
    def _detect_framework(self) -> str:
        """Detect framework from config files and dependencies."""
        # Check for Python frameworks
        if os.path.exists(os.path.join(self.project_path, "manage.py")):
            return "django"
        if os.path.exists(os.path.join(self.project_path, "requirements.txt")):
            try:
                with open(os.path.join(self.project_path, "requirements.txt")) as f:
                    reqs = f.read().lower()
                    if "flask" in reqs:
                        return "flask"
                    if "fastapi" in reqs:
                        return "fastapi"
                    if "django" in reqs:
                        return "django"
            except Exception:
                pass
        
        # Check for Node.js frameworks
        if os.path.exists(os.path.join(self.project_path, "package.json")):
            try:
                with open(os.path.join(self.project_path, "package.json")) as f:
                    import json
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    
                    if "next" in deps:
                        return "next.js"
                    if "nuxt" in deps:
                        return "nuxt"
                    if "react" in deps:
                        return "react"
                    if "vue" in deps:
                        return "vue"
                    if "angular" in deps or "@angular/core" in deps:
                        return "angular"
                    if "svelte" in deps:
                        return "svelte"
                    if "express" in deps:
                        return "express"
                    if "fastify" in deps:
                        return "fastify"
            except Exception:
                pass
        
        # Check for Go
        if os.path.exists(os.path.join(self.project_path, "go.mod")):
            return "go"
        
        # Check for Rust
        if os.path.exists(os.path.join(self.project_path, "Cargo.toml")):
            return "rust"
        
        return "unknown"
    
    def _detect_package_manager(self) -> str:
        """Detect package manager."""
        lock_files = {
            "package-lock.json": "npm",
            "yarn.lock": "yarn",
            "pnpm-lock.yaml": "pnpm",
            "bun.lockb": "bun",
            "Pipfile.lock": "pipenv",
            "poetry.lock": "poetry",
            "pdm.lock": "pdm",
            "Cargo.lock": "cargo",
            "go.sum": "go",
            "Gemfile.lock": "bundler",
            "composer.lock": "composer",
        }
        
        for lock_file, manager in lock_files.items():
            if os.path.exists(os.path.join(self.project_path, lock_file)):
                return manager
        
        # Check for pyproject.toml (could be poetry or pdm)
        if os.path.exists(os.path.join(self.project_path, "pyproject.toml")):
            try:
                with open(os.path.join(self.project_path, "pyproject.toml")) as f:
                    content = f.read()
                    if "[tool.poetry]" in content:
                        return "poetry"
                    if "[tool.pdm]" in content:
                        return "pdm"
            except Exception:
                pass
        
        return "unknown"
    
    def _detect_test_framework(self) -> str:
        """Detect test framework."""
        # Python
        if os.path.exists(os.path.join(self.project_path, "pytest.ini")):
            return "pytest"
        if os.path.exists(os.path.join(self.project_path, "conftest.py")):
            return "pytest"
        
        # Node.js
        if os.path.exists(os.path.join(self.project_path, "package.json")):
            try:
                with open(os.path.join(self.project_path, "package.json")) as f:
                    import json
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "jest" in deps:
                        return "jest"
                    if "vitest" in deps:
                        return "vitest"
                    if "mocha" in deps:
                        return "mocha"
            except Exception:
                pass
        
        return "unknown"
    
    def _detect_linter(self) -> str:
        """Detect linter."""
        if os.path.exists(os.path.join(self.project_path, ".flake8")):
            return "flake8"
        if os.path.exists(os.path.join(self.project_path, "setup.cfg")):
            try:
                with open(os.path.join(self.project_path, "setup.cfg")) as f:
                    if "[flake8]" in f.read():
                        return "flake8"
            except Exception:
                pass
        if os.path.exists(os.path.join(self.project_path, "pyproject.toml")):
            try:
                with open(os.path.join(self.project_path, "pyproject.toml")) as f:
                    content = f.read()
                    if "[tool.ruff]" in content:
                        return "ruff"
                    if "[tool.black]" in content:
                        return "black"
            except Exception:
                pass
        if os.path.exists(os.path.join(self.project_path, ".eslintrc")):
            return "eslint"
        if os.path.exists(os.path.join(self.project_path, ".eslintrc.js")):
            return "eslint"
        if os.path.exists(os.path.join(self.project_path, "eslint.config.js")):
            return "eslint"
        return "unknown"
    
    def _detect_formatter(self) -> str:
        """Detect formatter."""
        if os.path.exists(os.path.join(self.project_path, ".prettierrc")):
            return "prettier"
        if os.path.exists(os.path.join(self.project_path, ".prettierrc.js")):
            return "prettier"
        if os.path.exists(os.path.join(self.project_path, "pyproject.toml")):
            try:
                with open(os.path.join(self.project_path, "pyproject.toml")) as f:
                    content = f.read()
                    if "[tool.black]" in content:
                        return "black"
                    if "[tool.ruff]" in content:
                        return "ruff"
            except Exception:
                pass
        return "unknown"
    
    def _find_config_files(self) -> list[str]:
        """Find configuration files."""
        config_files = []
        config_names = [
            "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
            "package.json", "tsconfig.json", "next.config.js", "next.config.ts",
            "vite.config.js", "vite.config.ts", "webpack.config.js",
            ".gitignore", ".env", ".env.example", "docker-compose.yml",
            "Dockerfile", "Makefile", "CMakeLists.txt", "go.mod", "Cargo.toml",
        ]
        
        for name in config_names:
            if os.path.exists(os.path.join(self.project_path, name)):
                config_files.append(name)
        
        return config_files
    
    def _find_source_dirs(self) -> list[str]:
        """Find source directories."""
        common_dirs = ["src", "lib", "app", "pkg", "internal", "cmd"]
        found = []
        
        for d in common_dirs:
            if os.path.isdir(os.path.join(self.project_path, d)):
                found.append(d)
        
        return found or ["."]
    
    def _find_test_dirs(self) -> list[str]:
        """Find test directories."""
        test_dirs = ["tests", "test", "__tests__", "spec"]
        found = []
        
        for d in test_dirs:
            if os.path.isdir(os.path.join(self.project_path, d)):
                found.append(d)
        
        return found
    
    def _find_entry_points(self) -> list[str]:
        """Find entry points."""
        entry_points = []
        
        # Python
        for name in ["main.py", "app.py", "server.py", "cli.py", "__main__.py"]:
            if os.path.exists(os.path.join(self.project_path, name)):
                entry_points.append(name)
        
        # Node.js
        if os.path.exists(os.path.join(self.project_path, "package.json")):
            try:
                with open(os.path.join(self.project_path, "package.json")) as f:
                    import json
                    pkg = json.load(f)
                    main = pkg.get("main")
                    if main:
                        entry_points.append(main)
            except Exception:
                pass
        
        return entry_points
    
    def _load_dependencies(self) -> dict:
        """Load dependencies."""
        deps = {}
        
        # Python requirements.txt
        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if "==" in line:
                                name, version = line.split("==", 1)
                                deps.setdefault("dependencies", {})[name] = version
                            else:
                                deps.setdefault("dependencies", {})[line] = "*"
            except Exception:
                pass
        
        # Node.js package.json
        pkg_file = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_file):
            try:
                with open(pkg_file) as f:
                    import json
                    pkg = json.load(f)
                    deps["dependencies"] = pkg.get("dependencies", {})
                    deps["dev_dependencies"] = pkg.get("devDependencies", {})
            except Exception:
                pass
        
        return deps
    
    def detect_monorepo(self) -> dict:
        """Detect monorepo structure and workspaces."""
        result = {
            "is_monorepo": False,
            "workspaces": [],
            "package_manager": "npm",
            "root_package_manager": None,
        }
        
        # Check for npm/yarn/pnpm workspaces
        pkg_file = os.path.join(self.project_path, "package.json")
        if os.path.exists(pkg_file):
            try:
                with open(pkg_file) as f:
                    import json
                    pkg = json.load(f)
                    workspaces = pkg.get("workspaces", [])
                    if workspaces:
                        result["is_monorepo"] = True
                        result["workspaces"] = workspaces
                        result["package_manager"] = "npm"
            except Exception:
                pass
        
        # Check for lerna.json
        if os.path.exists(os.path.join(self.project_path, "lerna.json")):
            result["is_monorepo"] = True
            result["package_manager"] = "lerna"
        
        # Check for pnpm-workspace.yaml
        if os.path.exists(os.path.join(self.project_path, "pnpm-workspace.yaml")):
            result["is_monorepo"] = True
            result["package_manager"] = "pnpm"
        
        # Check for Cargo workspaces (Rust)
        cargo_file = os.path.join(self.project_path, "Cargo.toml")
        if os.path.exists(cargo_file):
            try:
                with open(cargo_file) as f:
                    content = f.read()
                    if "[workspace]" in content:
                        result["is_monorepo"] = True
                        result["package_manager"] = "cargo"
                        # Extract workspace members
                        import re
                        members = re.findall(r'members\s*=\s*\[([^\]]+)\]', content)
                        if members:
                            result["workspaces"] = [m.strip().strip('"').strip("'") for m in members[0].split(",")]
            except Exception:
                pass
        
        # Check for pyproject.toml workspaces
        pyproject = os.path.join(self.project_path, "pyproject.toml")
        if os.path.exists(pyproject):
            try:
                with open(pyproject) as f:
                    content = f.read()
                    if "[tool.poetry]" in content and "packages" in content:
                        result["is_monorepo"] = True
                        result["package_manager"] = "poetry"
            except Exception:
                pass
        
        # Check for go.work (Go workspaces)
        if os.path.exists(os.path.join(self.project_path, "go.work")):
            result["is_monorepo"] = True
            result["package_manager"] = "go"
        
        return result
    
    def build_import_graph(self) -> dict:
        """Build import/dependency graph for Python files."""
        graph = {}  # file -> [imported_files]
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
                "dist", "build",
            )]
            
            for f in files:
                if not f.endswith(".py"):
                    continue
                fpath = os.path.join(root, f)
                rel_path = os.path.relpath(fpath, self.project_path)
                
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    
                    # Extract imports
                    import re
                    imports = []
                    for match in re.finditer(r'^(?:from\s+(\S+)|import\s+(\S+))', content, re.MULTILINE):
                        module = match.group(1) or match.group(2)
                        imports.append(module.split(".")[0])  # Get top-level module
                    
                    # Check if imported modules are local files
                    local_imports = []
                    for imp in imports:
                        # Check if it's a local module (exists as .py file)
                        local_path = os.path.join(root, f"{imp}.py")
                        if os.path.exists(local_path):
                            local_imports.append(os.path.relpath(local_path, self.project_path))
                    
                    if local_imports:
                        graph[rel_path] = local_imports
                except Exception:
                    pass
        
        return graph
