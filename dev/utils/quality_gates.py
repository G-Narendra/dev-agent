"""
Quality Gates for Dev.

Auto-lint and auto-test after file changes.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LintResult:
    """Result of linting a file."""
    file_path: str = ""
    success: bool = True
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of running tests."""
    success: bool = True
    tests_run: int = 0
    passed: int = 0
    failed: int = 0
    output: str = ""


class AutoLinter:
    """Automatically lint files after changes."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    async def lint_file(self, file_path: str) -> LintResult:
        """Lint a specific file."""
        abs_path = os.path.join(self.project_path, file_path) if not os.path.isabs(file_path) else file_path
        result = LintResult(file_path=file_path)
        
        if not os.path.isfile(abs_path):
            result.success = False
            result.errors = [{"message": f"File not found: {file_path}"}]
            return result
        
        ext = os.path.splitext(abs_path)[1].lower()
        
        try:
            if ext == ".py":
                return await self._lint_python(abs_path, result)
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                return await self._lint_javascript(abs_path, result)
            elif ext == ".json":
                return await self._lint_json(abs_path, result)
            elif ext in (".yaml", ".yml"):
                return await self._lint_yaml(abs_path, result)
            elif ext == ".css":
                return await self._lint_css(abs_path, result)
            elif ext == ".html":
                return await self._lint_html(abs_path, result)
            elif ext == ".md":
                return await self._lint_markdown(abs_path, result)
            elif ext == ".sh":
                return await self._lint_shell(abs_path, result)
            else:
                return result  # No linter for this file type
        except Exception as e:
            result.success = False
            result.errors = [{"message": str(e)}]
            return result
    
    async def _lint_python(self, file_path: str, result: LintResult) -> LintResult:
        """Lint a Python file."""
        # Try ruff first (fast)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ruff", "check", "--output-format=json", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            
            if proc.returncode != 0:
                try:
                    errors = json.loads(stdout.decode())
                    result.errors = [
                        {"line": e.get("location", {}).get("row", 0),
                         "message": e.get("message", ""),
                         "code": e.get("code", "")}
                        for e in errors
                    ]
                    result.success = False
                except json.JSONDecodeError:
                    pass
            return result
        except FileNotFoundError:
            pass
        except asyncio.TimeoutError:
            pass
        
        # Fallback: try python -m py_compile
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "py_compile", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            
            if proc.returncode != 0:
                error_msg = stderr.decode(errors="replace").strip()
                result.errors = [{"message": error_msg}]
                result.success = False
            return result
        except Exception:
            return result
    
    async def _lint_javascript(self, file_path: str, result: LintResult) -> LintResult:
        """Lint a JavaScript/TypeScript file."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "eslint", "--format=json", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            
            if proc.returncode != 0:
                try:
                    errors = json.loads(stdout.decode())
                    for file_errors in errors:
                        for msg in file_errors.get("messages", []):
                            result.errors.append({
                                "line": msg.get("line", 0),
                                "message": msg.get("message", ""),
                                "rule": msg.get("ruleId", ""),
                            })
                    result.success = len(result.errors) == 0
                except json.JSONDecodeError:
                    pass
        except (FileNotFoundError, asyncio.TimeoutError):
            pass
        
        return result
    
    async def _lint_json(self, file_path: str, result: LintResult) -> LintResult:
        """Validate JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            result.success = False
            result.errors = [{"line": e.lineno, "message": str(e)}]
        except Exception as e:
            result.success = False
            result.errors = [{"message": str(e)}]
        return result
    
    async def _lint_yaml(self, file_path: str, result: LintResult) -> LintResult:
        """Validate YAML file."""
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
        except ImportError:
            pass  # PyYAML not installed
        except Exception as e:
            result.success = False
            result.errors = [{"message": str(e)}]
        return result
    
    async def _lint_css(self, file_path: str, result: LintResult) -> LintResult:
        """Basic CSS validation (check for syntax errors)."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # Check for unclosed braces
            open_braces = content.count('{')
            close_braces = content.count('}')
            if open_braces != close_braces:
                result.success = False
                result.errors = [{"message": f"Unbalanced braces: {open_braces} open, {close_braces} close"}]
            # Check for common CSS errors
            if ';;' in content:
                result.warnings = [{"message": "Double semicolons found"}]
        except Exception as e:
            result.errors = [{"message": str(e)}]
            result.success = False
        return result
    
    async def _lint_html(self, file_path: str, result: LintResult) -> LintResult:
        """Basic HTML validation."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # Check for unclosed tags (basic)
            import re
            open_tags = re.findall(r'<([a-zA-Z]+)[\s>]', content)
            close_tags = re.findall(r'</([a-zA-Z]+)>', content)
            # Self-closing tags
            self_closing = {'meta', 'link', 'img', 'br', 'hr', 'input', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr'}
            open_counts = {}
            close_counts = {}
            for tag in open_tags:
                if tag.lower() not in self_closing:
                    open_counts[tag.lower()] = open_counts.get(tag.lower(), 0) + 1
            for tag in close_tags:
                close_counts[tag.lower()] = close_counts.get(tag.lower(), 0) + 1
            for tag, count in open_counts.items():
                if close_counts.get(tag, 0) != count:
                    result.warnings = [{"message": f"Potentially unclosed <{tag}> tag ({count} open, {close_counts.get(tag, 0)} close)"}]
        except Exception as e:
            result.errors = [{"message": str(e)}]
            result.success = False
        return result
    
    async def _lint_markdown(self, file_path: str, result: LintResult) -> LintResult:
        """Basic Markdown validation."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Check for common issues
            for i, line in enumerate(lines, 1):
                # Trailing whitespace
                if line.rstrip() != line.rstrip('\n') and line.strip():
                    result.warnings = [{"line": i, "message": "Trailing whitespace"}]
                    break  # Only report first
        except Exception as e:
            result.errors = [{"message": str(e)}]
            result.success = False
        return result
    
    async def _lint_shell(self, file_path: str, result: LintResult) -> LintResult:
        """Basic shell script validation."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", "-n", file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode != 0:
                error_msg = stderr.decode(errors="replace").strip()
                result.errors = [{"message": error_msg}]
                result.success = False
        except (FileNotFoundError, asyncio.TimeoutError):
            pass  # bash not available
        except Exception as e:
            result.errors = [{"message": str(e)}]
            result.success = False
        return result
    
    async def lint_project(self) -> dict:
        """Lint the entire project."""
        results = {"files": 0, "errors": 0, "warnings": 0}
        
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != "node_modules"]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml")):
                    fpath = os.path.join(root, f)
                    rel_path = os.path.relpath(fpath, self.project_path)
                    result = await self.lint_file(rel_path)
                    results["files"] += 1
                    results["errors"] += len(result.errors)
                    results["warnings"] += len(result.warnings)
        
        results["success"] = results["errors"] == 0
        return results


class AutoTester:
    """Automatically run tests after file changes."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    async def run_tests(self, test_path: str = "") -> TestResult:
        """Run tests."""
        result = TestResult()
        
        # Detect test framework and run
        frameworks = [
            (["pytest", test_path or ".", "-v", "--tb=short"], "pytest"),
            (["python", "-m", "pytest", test_path or ".", "-v"], "pytest-module"),
            (["npx", "jest", "--passWithNoTests"], "jest"),
            (["npx", "vitest", "run"], "vitest"),
        ]
        
        for cmd, name in frameworks:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.project_path,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                
                output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
                result.output = output[-5000:]
                result.success = proc.returncode == 0
                
                # Parse test counts from output
                import re
                # pytest pattern
                match = re.search(r"(\d+) passed.*?(\d+) failed", output)
                if match:
                    result.passed = int(match.group(1))
                    result.failed = int(match.group(2))
                    result.tests_run = result.passed + result.failed
                    return result
                
                # jest pattern
                match = re.search(r"Tests:\s+(\d+)\s+failed.*?(\d+)\s+passed", output)
                if match:
                    result.failed = int(match.group(1))
                    result.passed = int(match.group(2))
                    result.tests_run = result.passed + result.failed
                    return result
                
                # Simple count
                result.tests_run = output.count(" PASSED") + output.count(" FAILED")
                result.passed = output.count(" PASSED")
                result.failed = output.count(" FAILED")
                return result
                
            except FileNotFoundError:
                continue
            except asyncio.TimeoutError:
                result.success = False
                result.output = f"Tests timed out with {name}"
                return result
        
        result.success = False
        result.output = "No test framework found"
        return result
    
    async def run_related_tests(self, changed_file: str) -> TestResult:
        """Run tests related to a changed file."""
        # Try to find related test files
        base_name = os.path.splitext(os.path.basename(changed_file))[0]
        
        # Look for test files
        test_patterns = [
            f"tests/test_{base_name}.py",
            f"tests/{base_name}_test.py",
            f"test_{base_name}.py",
            f"tests/test_{base_name}.test.js",
            f"tests/test_{base_name}.test.ts",
        ]
        
        for pattern in test_patterns:
            test_path = os.path.join(self.project_path, pattern)
            if os.path.isfile(test_path):
                return await self.run_tests(pattern)
        
        # No specific test file found, run all tests
        return await self.run_tests()
