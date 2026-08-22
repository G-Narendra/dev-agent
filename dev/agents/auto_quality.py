"""
Auto Quality — Lint, Test, and Validate After Every Edit

Inspired by Aider's auto-lint and auto-test features, this module
automatically checks code quality after every edit and can fix issues.

Key features:
1. Auto-lint: Run linter after every file edit
2. Auto-test: Run tests after every change
3. Error loop: Send errors back to LLM for fixing
4. Language detection: Auto-detect linter/test framework
"""
import os
import subprocess
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class LintResult:
    """Result of linting."""
    success: bool
    file_path: str = ""
    errors: list = None
    raw_output: str = ""
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass 
class TestResult:
    """Result of testing."""
    success: bool
    test_file: str = ""
    passed: int = 0
    failed: int = 0
    errors: list = None
    raw_output: str = ""
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AutoQuality:
    """
    Automatically lint and test code after edits.
    
    Usage:
        aq = AutoQuality(project_path=".")
        
        # After editing a file
        lint_result = aq.lint_file("server.js")
        if not lint_result.success:
            # Send errors to LLM for fixing
            fix_prompt = aq.get_fix_prompt(lint_result)
        
        # After all files are created
        test_result = aq.run_tests()
    """
    
    # Linter commands by language
    LINTERS = {
        '.py': ['python', '-m', 'py_compile', '{file}'],
        '.js': ['node', '--check', '{file}'],
        '.ts': ['npx', 'tsc', '--noEmit', '{file}'],
        '.jsx': ['npx', 'eslint', '{file}'],
        '.tsx': ['npx', 'eslint', '{file}'],
        '.go': ['gofmt', '-e', '{file}'],
        '.rs': ['rustc', '--edition', '2021', '--crate-type', 'lib', '{file}'],
    }
    
    # Test commands by project type
    TEST_COMMANDS = {
        'python': ['python', '-m', 'pytest', '-x', '-q'],
        'javascript': ['npm', 'test'],
        'typescript': ['npm', 'test'],
        'go': ['go', 'test', './...'],
        'rust': ['cargo', 'test'],
    }
    
    # Syntax check commands (lighter than full lint)
    SYNTAX_CHECK = {
        '.py': ['python', '-m', 'py_compile', '{file}'],
        '.js': ['node', '--check', '{file}'],
        '.go': ['go', 'vet', '{file}'],
    }
    
    def __init__(self, project_path: str = ".", verbose: bool = False):
        self.project_path = os.path.abspath(project_path)
        self.verbose = verbose
        self._last_lint_errors = {}
    
    def lint_file(self, file_path: str) -> LintResult:
        """
        Lint a single file.
        
        Returns LintResult with errors list.
        """
        abs_path = self._resolve_path(file_path)
        
        if not os.path.exists(abs_path):
            return LintResult(
                success=False,
                file_path=file_path,
                errors=[f"File not found: {file_path}"]
            )
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # Try syntax check first (faster)
        syntax_cmd = self.SYNTAX_CHECK.get(ext)
        if syntax_cmd:
            cmd = [c.replace('{file}', abs_path) for c in syntax_cmd]
            result = self._run_command(cmd)
            
            if result['returncode'] != 0:
                errors = self._parse_errors(result['stderr'] or result['stdout'], ext)
                return LintResult(
                    success=False,
                    file_path=file_path,
                    errors=errors,
                    raw_output=result['stderr'] or result['stdout'],
                )
        
        # Try full linter
        linter_cmd = self.LINTERS.get(ext)
        if linter_cmd:
            cmd = [c.replace('{file}', abs_path) for c in linter_cmd]
            result = self._run_command(cmd)
            
            if result['returncode'] != 0:
                errors = self._parse_errors(result['stderr'] or result['stdout'], ext)
                return LintResult(
                    success=False,
                    file_path=file_path,
                    errors=errors,
                    raw_output=result['stderr'] or result['stdout'],
                )
        
        return LintResult(success=True, file_path=file_path)
    
    def run_tests(self, test_command: str = None) -> TestResult:
        """
        Run tests for the project.
        
        Auto-detects test framework if not specified.
        """
        # Detect project type
        project_type = self._detect_project_type()
        
        if test_command:
            cmd = test_command.split()
        elif project_type in self.TEST_COMMANDS:
            cmd = self.TEST_COMMANDS[project_type]
        else:
            return TestResult(
                success=False,
                errors=["No test command found. Specify test_command or use a supported project type."]
            )
        
        result = self._run_command(cmd, cwd=self.project_path, timeout=120)
        
        # Parse test output
        passed, failed, errors = self._parse_test_output(result['stdout'] + result['stderr'])
        
        return TestResult(
            success=result['returncode'] == 0,
            passed=passed,
            failed=failed,
            errors=errors,
            raw_output=result['stdout'] + result['stderr'],
        )
    
    def check_syntax(self, file_path: str) -> LintResult:
        """Quick syntax check only (no full lint)."""
        abs_path = self._resolve_path(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        
        syntax_cmd = self.SYNTAX_CHECK.get(ext)
        if not syntax_cmd:
            # No syntax checker available, assume OK
            return LintResult(success=True, file_path=file_path)
        
        cmd = [c.replace('{file}', abs_path) for c in syntax_cmd]
        result = self._run_command(cmd)
        
        if result['returncode'] != 0:
            errors = self._parse_errors(result['stderr'] or result['stdout'], ext)
            return LintResult(
                success=False,
                file_path=file_path,
                errors=errors,
                raw_output=result['stderr'] or result['stdout'],
            )
        
        return LintResult(success=True, file_path=file_path)
    
    def get_fix_prompt(self, lint_result: LintResult) -> str:
        """
        Generate a prompt for the LLM to fix lint errors.
        
        This is sent back to the agent after a failed lint.
        """
        if lint_result.success:
            return ""
        
        errors_text = '\n'.join(f"- {e}" for e in lint_result.errors[:10])
        
        return f"""The file {lint_result.file_path} has lint errors:

{errors_text}

Fix these errors. Use str_replace to fix each error precisely.
Do NOT rewrite the entire file — only fix the specific lines with errors."""
    
    def get_test_fix_prompt(self, test_result: TestResult) -> str:
        """Generate a prompt for the LLM to fix test failures."""
        if test_result.success:
            return ""
        
        # Extract relevant error info
        error_lines = []
        for line in test_result.raw_output.split('\n'):
            if any(kw in line.lower() for kw in ['error', 'fail', 'assert', 'traceback']):
                error_lines.append(line.strip())
        
        errors_text = '\n'.join(error_lines[:20])
        
        return f"""Tests failed ({test_result.failed} failures):

{errors_text}

Fix the failing tests. Read the test file and the source file,
then fix the issues causing test failures."""
    
    def _detect_project_type(self) -> str:
        """Detect project type from files."""
        if os.path.exists(os.path.join(self.project_path, 'package.json')):
            return 'javascript'
        elif os.path.exists(os.path.join(self.project_path, 'requirements.txt')) or \
             os.path.exists(os.path.join(self.project_path, 'setup.py')) or \
             os.path.exists(os.path.join(self.project_path, 'pyproject.toml')):
            return 'python'
        elif os.path.exists(os.path.join(self.project_path, 'go.mod')):
            return 'go'
        elif os.path.exists(os.path.join(self.project_path, 'Cargo.toml')):
            return 'rust'
        return 'unknown'
    
    def _run_command(self, cmd: list, cwd: str = None, 
                     timeout: int = 30) -> dict:
        """Run a command and capture output."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': f'Command timed out after {timeout}s',
            }
        except FileNotFoundError:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': f'Command not found: {cmd[0]}',
            }
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
            }
    
    def _parse_errors(self, output: str, ext: str) -> list:
        """Parse linter output into error list."""
        errors = []
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Python: file.py:line:col: error: message
            if ext == '.py':
                m = re.match(r'.+:(\d+):(\d+):\s*(\w+):\s*(.+)', line)
                if m:
                    errors.append(f"Line {m.group(1)}: {m.group(4)}")
                    continue
            
            # JavaScript: file.js:line:col: error: message
            if ext in ('.js', '.ts', '.jsx', '.tsx'):
                m = re.match(r'.+:(\d+):(\d+):\s*(error|warning):\s*(.+)', line)
                if m:
                    errors.append(f"Line {m.group(1)}: {m.group(4)}")
                    continue
            
            # Generic: just add the line if it looks like an error
            if any(kw in line.lower() for kw in ['error', 'warning', 'fail']):
                errors.append(line[:200])
        
        if not errors and output.strip():
            # Couldn't parse, just add raw output
            errors.append(output.strip()[:500])
        
        return errors[:20]  # Limit to 20 errors
    
    def _parse_test_output(self, output: str) -> tuple:
        """Parse test output for pass/fail counts."""
        passed = 0
        failed = 0
        errors = []
        
        for line in output.split('\n'):
            # pytest: "5 passed, 2 failed"
            m = re.search(r'(\d+)\s+passed', line)
            if m:
                passed += int(m.group(1))
            m = re.search(r'(\d+)\s+failed', line)
            if m:
                failed += int(m.group(1))
            
            # Jest: "Tests: 2 failed, 5 passed, 7 total"
            m = re.search(r'(\d+)\s+failed', line)
            if m and 'test' in line.lower():
                failed = max(failed, int(m.group(1)))
            m = re.search(r'(\d+)\s+passed', line)
            if m and 'test' in line.lower():
                passed = max(passed, int(m.group(1)))
            
            # Collect error lines
            if any(kw in line.lower() for kw in ['error', 'fail', 'assert']):
                errors.append(line.strip()[:200])
        
        return passed, failed, errors[:10]
    
    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.project_path, path))


import re  # For error parsing
