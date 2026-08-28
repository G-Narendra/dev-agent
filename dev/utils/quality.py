"""
Quality gates for Dev - auto-lint and auto-test.

Adapted from Aider's linter.py and auto-test patterns.
Runs linters and tests after code changes to catch errors early.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


from .quality_gates import LintResult, TestResult  # Re-export from quality_gates


# Language to linter/test command mapping
LINTERS = {
    ".py": {
        "lint": "ruff check {file} --output-format=json",
        "fix": "ruff check {file} --fix",
        "format": "ruff format {file}",
    },
    ".js": {
        "lint": "eslint {file} --format=json",
        "fix": "eslint {file} --fix",
        "format": "prettier --write {file}",
    },
    ".ts": {
        "lint": "eslint {file} --format=json",
        "fix": "eslint {file} --fix",
        "format": "prettier --write {file}",
        "typecheck": "tsc --noEmit",
    },
    ".tsx": {
        "lint": "eslint {file} --format=json",
        "fix": "eslint {file} --fix",
        "format": "prettier --write {file}",
    },
    ".jsx": {
        "lint": "eslint {file} --format=json",
        "fix": "eslint {file} --fix",
        "format": "prettier --write {file}",
    },
    ".rs": {
        "lint": "cargo clippy --message-format=json",
        "fix": "cargo clippy --fix --allow-dirty",
        "format": "cargo fmt",
    },
    ".go": {
        "lint": "golangci-lint run {file}",
        "fix": "gofmt -w {file}",
        "format": "gofmt -w {file}",
    },
}

TEST_COMMANDS = {
    "python": "pytest {test_path} -v",
    "javascript": "npm test -- {test_path}",
    "typescript": "npm test -- {test_path}",
    "rust": "cargo test",
    "go": "go test ./...",
}


class QualityChecker:
    """
    Runs linters and tests after code changes.
    
    From Aider's linter.py and auto-test patterns.
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._last_lint_result: LintResult | None = None
    
    async def lint_file(self, file_path: str) -> LintResult:
        """
        Lint a single file.
        
        From Aider's linter.py.
        """
        ext = Path(file_path).suffix
        linter_config = LINTERS.get(ext)
        
        if not linter_config:
            return LintResult(
                success=True,
                errors=[],
                warnings=[],
                file_path=file_path,
            )
        
        lint_cmd = linter_config.get("lint", "")
        if not lint_cmd:
            return LintResult(
                success=True,
                errors=[],
                warnings=[],
                file_path=file_path,
            )
        
        # Check if the linter binary is available before running
        import shutil as _shutil
        linter_binary = lint_cmd.split()[0]
        if not _shutil.which(linter_binary):
            return LintResult(
                success=True,
                errors=[],
                warnings=[{"message": f"Linter '{linter_binary}' not found in PATH. Skipping lint."}],
                file_path=file_path,
            )
        
        # Format command — quote paths to prevent shell injection
        abs_path = os.path.join(self.project_path, file_path)
        cmd = lint_cmd.format(file=shlex.quote(abs_path), file_path=shlex.quote(file_path))
        
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self.project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            # Parse output
            errors = []
            warnings = []
            
            output = stdout.decode("utf-8", errors="replace")
            
            # Try JSON parsing (for ruff, eslint)
            try:
                import json
                issues = json.loads(output)
                for issue in issues:
                    entry = {
                        "line": issue.get("line", 0),
                        "column": issue.get("column", 0),
                        "message": issue.get("message", ""),
                        "code": issue.get("code", ""),
                    }
                    if issue.get("severity") == "error" or issue.get("type") == "error":
                        errors.append(entry)
                    else:
                        warnings.append(entry)
            except (json.JSONDecodeError, KeyError):
                # Fallback: parse line-by-line
                for line in output.split("\n"):
                    if "error" in line.lower():
                        errors.append({"message": line})
                    elif "warning" in line.lower():
                        warnings.append({"message": line})
            
            return LintResult(
                success=proc.returncode == 0,
                errors=errors,
                warnings=warnings,
                file_path=file_path,
            )
            
        except asyncio.TimeoutError:
            return LintResult(
                success=False,
                errors=[{"message": "Lint timed out"}],
                warnings=[],
                file_path=file_path,
            )
        except FileNotFoundError:
            # Linter not installed
            return LintResult(
                success=True,
                errors=[],
                warnings=[{"message": f"Linter not found for {ext}"}],
                file_path=file_path,
            )
    
    async def fix_file(self, file_path: str) -> dict:
        """
        Auto-fix lint issues.
        
        From Aider's linter auto-fix.
        """
        ext = Path(file_path).suffix
        linter_config = LINTERS.get(ext, {})
        
        fix_cmd = linter_config.get("fix")
        if not fix_cmd:
            return {"success": False, "error": "No auto-fix available"}
        
        # Check if the linter binary is available
        import shutil as _shutil
        linter_binary = fix_cmd.split()[0]
        if not _shutil.which(linter_binary):
            return {"success": False, "error": f"Linter '{linter_binary}' not found in PATH"}
        
        abs_path = os.path.join(self.project_path, file_path)
        cmd = fix_cmd.format(file=shlex.quote(abs_path))
        
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self.project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def format_file(self, file_path: str) -> dict:
        """
        Format a file.
        
        From Aider's linter.
        """
        ext = Path(file_path).suffix
        linter_config = LINTERS.get(ext, {})
        
        format_cmd = linter_config.get("format")
        if not format_cmd:
            return {"success": False, "error": "No formatter available"}
        
        # Check if the formatter binary is available
        import shutil as _shutil
        formatter_binary = format_cmd.split()[0]
        if not _shutil.which(formatter_binary):
            return {"success": False, "error": f"Formatter '{formatter_binary}' not found in PATH"}
        
        abs_path = os.path.join(self.project_path, file_path)
        cmd = format_cmd.format(file=shlex.quote(abs_path))
        
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self.project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def run_tests(self, test_path: str = "") -> TestResult:
        """
        Run tests for the project.
        
        From Aider's auto-test pattern.
        """
        # Detect project type
        language = self._detect_language()
        test_cmd = TEST_COMMANDS.get(language)
        
        if not test_cmd:
            return TestResult(
                success=True,
                output="No test command configured for this project type",
            )
        
        cmd = test_cmd.format(test_path=shlex.quote(test_path) if test_path else '')
        
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=self.project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            
            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")
            
            # Parse test results
            passed = 0
            failed = 0
            error_list = []
            
            # Simple parsing
            if "passed" in output:
                import re
                passed_match = re.search(r'(\d+) passed', output)
                if passed_match:
                    passed = int(passed_match.group(1))
            
            if "failed" in output:
                import re
                failed_match = re.search(r'(\d+) failed', output)
                if failed_match:
                    failed = int(failed_match.group(1))
            
            if errors:
                error_list.append(errors[:500])
            
            return TestResult(
                success=proc.returncode == 0,
                passed=passed,
                failed=failed,
                errors=error_list,
                output=output[:2000],
            )
            
        except asyncio.TimeoutError:
            return TestResult(
                success=False,
                errors=["Tests timed out after 120s"],
            )
        except FileNotFoundError:
            return TestResult(
                success=True,
                output="Test runner not found",
            )
    
    def analyze_code_quality(self) -> dict:
        """Run comprehensive code quality analysis."""
        results = {
            "lint": None,
            "circular_deps": [],
            "unused_imports": [],
            "complexity": {},
        }
        
        # Lint all files
        try:
            results["lint"] = self._lint_project()
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        # Detect circular dependencies
        try:
            from .project_detector import ProjectDetector
            detector = ProjectDetector(self.project_path)
            results["circular_deps"] = detector.detect_circular_dependencies()
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        # Detect unused imports
        try:
            from .project_detector import ProjectDetector
            detector = ProjectDetector(self.project_path)
            results["unused_imports"] = detector.detect_unused_imports()
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        # Calculate cyclomatic complexity
        try:
            results["complexity"] = self._calculate_complexity()
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        return results
    
    def _lint_project(self) -> dict:
        """Lint all files in the project."""
        import asyncio
        results = {"files": 0, "errors": 0, "warnings": 0}
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
                "dist", "build",
            )]
            for f in files:
                ext = Path(f).suffix
                if ext in LINTERS:
                    fpath = os.path.join(root, f)
                    rel_path = os.path.relpath(fpath, self.project_path)
                    result = asyncio.run(
                        self.lint_file(rel_path)
                    )
                    results["files"] += 1
                    results["errors"] += len(result.errors)
                    results["warnings"] += len(result.warnings)
        
        results["success"] = results["errors"] == 0
        return results
    
    def _calculate_complexity(self) -> dict:
        """Calculate cyclomatic complexity for Python files."""
        import re
        complexity = {}
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
            )]
            for f in files:
                if not f.endswith(".py"):
                    continue
                fpath = os.path.join(root, f)
                rel_path = os.path.relpath(fpath, self.project_path)
                
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    
                    # Count branching keywords
                    branches = len(re.findall(
                        r'\b(if|elif|for|while|and|or|except|case)\b',
                        content
                    ))
                    complexity[rel_path] = {
                        "branches": branches,
                        "lines": content.count("\n") + 1,
                        "complexity": branches + 1,  # McCabe complexity
                    }
                except Exception:
                    pass  # Intentional: non-critical: best-effort operation
        
        return complexity
    
    def _detect_language(self) -> str:
        """Detect project language."""
        if os.path.exists(os.path.join(self.project_path, "pyproject.toml")):
            return "python"
        if os.path.exists(os.path.join(self.project_path, "package.json")):
            return "javascript"
        if os.path.exists(os.path.join(self.project_path, "Cargo.toml")):
            return "rust"
        if os.path.exists(os.path.join(self.project_path, "go.mod")):
            return "go"
        return "unknown"
