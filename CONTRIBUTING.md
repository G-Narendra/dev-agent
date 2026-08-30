# Contributing to Dev Agent

Thank you for your interest in contributing to Dev Agent! This guide will help you get started.

---

## Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/dev-agent.git
cd dev-agent

# 2. Create virtual environment
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# 3. Run tests
.venv/Scripts/python -m pytest tests/ -q

# 4. Create a branch
git checkout -b feature/amazing-feature

# 5. Make changes, run tests, commit
.venv/Scripts/python -m pytest tests/ -q
git commit -m "Add amazing feature"

# 6. Push and create PR
git push origin feature/amazing-feature
```

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for npm installation)
- Git

### Installation

```bash
# Clone the repo
git clone https://github.com/G-Narendra/dev-agent.git
cd dev-agent

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux)
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Verify installation
python -m dev --version
python -m pytest tests/ -q
```

---

## Project Structure

```
dev-agent/
├── dev/                    # Main package
│   ├── agents/            # Agent loop, compaction, teams
│   ├── apis/              # Free API integrations
│   ├── cli/               # CLI commands
│   ├── config/            # Configuration management
│   ├── mcp/               # MCP server integration
│   ├── providers/         # AI model providers
│   ├── sandbox/           # Command sandboxing
│   ├── security/          # Security layers
│   ├── skills/            # Skill definitions
│   ├── tools/             # Tool implementations
│   └── utils/             # Shared utilities
├── tests/                 # Test suite
├── skills/                # Skill markdown files
├── docs/                  # Documentation
├── pyproject.toml         # Package config
└── README.md              # Project README
```

---

## Code Style

### Python

- **Type hints** on all functions
- **Docstrings** on all classes and public methods
- **No bare excepts** — always catch specific exceptions
- **`# Intentional:`** comments on swallowed exceptions
- **`__all__`** exports in all modules
- **Max line length**: 120 characters

### Example

```python
from __future__ import annotations

import asyncio
from typing import Optional

from .base import Tool


class MyTool(Tool):
    """Description of what this tool does.
    
    Features:
    - Feature 1
    - Feature 2
    """
    
    name = "my_tool"
    description = "Short description"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input text"}
        },
        "required": ["input"]
    }
    
    async def execute(
        self,
        input_data: dict,
        state: Any,
        project_path: str,
    ) -> dict:
        """Execute the tool.
        
        Args:
            input_data: Tool input parameters
            state: Agent state
            project_path: Project root directory
            
        Returns:
            Tool execution result
        """
        try:
            result = await self._process(input_data["input"])
            return {"result": result}
        except ValueError as e:
            return {"error": str(e)}
        except Exception:  # best-effort: unexpected error
            return {"error": "Tool execution failed"}
```

---

## Testing

### Running Tests

```bash
# All tests
python -m pytest tests/ -q

# Unit tests only
python -m pytest tests/ -q --ignore=tests/test_integration_nim.py

# Integration tests (requires API keys)
python -m pytest tests/test_integration_nim.py -q -m integration

# With coverage
python -m pytest tests/ --cov=dev --cov-report=term-missing

# Specific test file
python -m pytest tests/test_all.py -q

# Verbose output
python -m pytest tests/ -v
```

### Writing Tests

```python
import pytest
from dev.tools.real_tools import WriteFileTool


class TestWriteFileTool:
    """Tests for WriteFileTool."""
    
    def test_write_file(self, tmp_path):
        """Test basic file writing."""
        tool = WriteFileTool()
        result = tool.execute(
            {"path": str(tmp_path / "test.txt"), "content": "hello"},
            None,
            str(tmp_path),
        )
        assert result["success"] is True
        assert (tmp_path / "test.txt").read_text() == "hello"
    
    def test_write_file_creates_dirs(self, tmp_path):
        """Test that nested directories are created."""
        tool = WriteFileTool()
        result = tool.execute(
            {"path": str(tmp_path / "a" / "b" / "test.txt"), "content": "hello"},
            None,
            str(tmp_path),
        )
        assert result["success"] is True
```

### Test Categories

- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test with real API calls (marked with `@pytest.mark.integration`)
- **Security tests**: Test security features
- **Streaming tests**: Test streaming behavior

---

## Adding Features

### Adding a New Tool

1. Create the tool class:
```python
# dev/tools/my_tool.py
from .base import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "What it does"
    parameters = {...}
    
    async def execute(self, input_data, state, project_path):
        ...
```

2. Register in `dev/cli/commands.py`:
```python
from ..tools.my_tool import MyTool
registry.register("my_tool", MyTool())
```

3. Add to `dev/tools/tool_defs.py`

4. Add to `dev/tools/__init__.py`

5. Write tests in `tests/`

### Adding a New Slash Command

1. Add handler in `dev/cli/slash_handler.py`:
```python
if cmd == "/my-command":
    # Implementation
    self.console.print("Done!")
    return "continue", True
```

2. Update `/help` in `dev/cli/chat.py`

3. Write tests in `tests/test_chat_command.py`

### Adding a New API Integration

1. Add config in `dev/apis/free_apis.py`
2. Test with `free_api` tool
3. Document in README

### Adding a New Skill

1. Create markdown file in `skills/`
2. Follow the existing skill format
3. Test with `narendra skill <name>`

---

## Pull Request Process

1. **Create a feature branch** from `main`
2. **Make your changes** with tests
3. **Run the full test suite**: `python -m pytest tests/ -q`
4. **Update documentation** if needed
5. **Write a clear commit message**
6. **Push and create PR**

### PR Checklist

- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] No syntax errors: `python -c "import py_compile; py_compile.compile('dev/...', doraise=True)"`
- [ ] Type hints on new functions
- [ ] Docstrings on new classes/methods
- [ ] No bare excepts (use specific exceptions)
- [ ] `__all__` exports in new modules
- [ ] README updated if needed

### Commit Messages

Use conventional commits:

```
feat: Add new tool for X
fix: Fix Y in Z
docs: Update documentation for W
test: Add tests for V
refactor: Simplify U
chore: Update dependencies
```

---

## Reporting Issues

### Bug Reports

Include:
- Python version
- OS
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error output

### Feature Requests

Include:
- Use case
- Proposed solution
- Alternatives considered

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## Questions?

Open an issue on GitHub or start a discussion.
