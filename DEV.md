# Dev Agent — Developer Guide

## Prerequisites

- Python 3.11+
- Node.js 18+ (for npm publishing)
- Git

## Development Setup

```bash
# Clone the repo
git clone https://github.com/dev-agent/dev-agent.git
cd dev-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[full]"

# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v
```

## Project Architecture

### Core Components

1. **`dev/providers/nim_provider.py`** — NVIDIA NIMs API client
   - Multi-key rotation with round-robin
   - Rate limiting (40 RPM per key)
   - Streaming SSE support
   - Automatic retry with backoff

2. **`dev/agents/production_loop.py`** — Main agent loop
   - Streaming with tool execution
   - Context pruning and auto-compaction
   - Budget tracking
   - Error recovery
   - Hook system
   - Parallel tool execution

3. **`dev/agents/runtime.py`** — Tool registry and runtime
   - Dynamic tool registration
   - Tool validation
   - MCP tool integration

4. **`dev/cli/main.py`** — CLI entry point
   - 68+ commands via typer
   - First-run wizard
   - Session management
   - Interactive chat

5. **`dev/tools/`** — 35 agent tools
   - File I/O (read, write, edit, multi-edit)
   - Shell execution (sandboxed)
   - Git operations
   - Web browsing
   - Docker management
   - MCP integration
   - Multimodal (image, PDF)

### Utility Modules

- `dev/utils/first_run.py` — First-run API key wizard
- `dev/utils/budget.py` — Token/cost tracking
- `dev/utils/hooks.py` — Pre/post tool hooks
- `dev/utils/tool_rules.py` — Per-project tool allow/deny
- `dev/utils/error_recovery.py` — Automatic retry logic
- `dev/utils/session_manager.py` — Session persistence
- `dev/utils/context_pruner.py` — Context window management
- `dev/utils/quality_gates.py` — Auto-lint and auto-test
- `dev/utils/memory.py` — Auto-memory (learn from sessions)
- `dev/utils/file_watcher.py` — File change detection

## Adding a New Tool

1. Create `dev/tools/my_tool.py`:

```python
from dev.agents.runtime import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input text"}
        },
        "required": ["input"]
    }

    async def execute(self, args: dict, project_path: str = ".") -> dict:
        input_text = args["input"]
        # Do something
        return {"result": f"Processed: {input_text}"}
```

2. Register in `dev/cli/main.py` `get_runtime()`:

```python
from ..tools.my_tool import MyTool
registry.register("my_tool", MyTool())
```

3. Add tool definition in `dev/tools/tool_defs.py`:

```python
"my_tool": {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "Does something useful",
        "parameters": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text"}
            },
            "required": ["input"]
        }
    }
}
```

4. Add tests in `tests/test_all.py`

## Adding a New CLI Command

In `dev/cli/main.py`:

```python
@app.command()
def my_command(
    arg: str = typer.Argument(..., help="My argument"),
    flag: bool = typer.Option(False, "--flag", help="My flag"),
):
    """Description of my command."""
    console.print(f"Running my command with {arg}")
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_core.py -v

# Run with coverage
pytest tests/ --cov=dev --cov-report=html

# Run syntax check on all files
python -c "
import ast, os
errors = []
for root, dirs, files in os.walk('dev'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    ast.parse(fh.read())
            except SyntaxError as e:
                errors.append(f'{path}: {e}')
print(f'Checked files, {len(errors)} errors')
for e in errors:
    print(f'  ERROR: {e}')
"
```

## Building for Distribution

### Python Package (PyPI)

```bash
# Install build tools
pip install build twine

# Build
python -m build

# Check
twine check dist/*

# Publish (requires PyPI account + API token)
twine upload dist/*
```

### npm Package

```bash
# Build the npm package
npm pack

# Test locally
npm install -g ./dev-agent-1.0.0.tgz

# Publish (requires npm account)
npm publish
```

### GitHub Release

```bash
# Tag a release
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions will automatically:
# 1. Run tests on Python 3.11/3.12/3.13 on Linux/Windows/macOS
# 2. Build wheel and sdist
# 3. Publish to PyPI
# 4. Publish to npm
```

## Configuration

Config file: `~/.dev/config.json`

```json
{
  "api_keys": ["nvapi-xxx"],
  "rpm": 40,
  "setup_complete": true
}
```

## Environment Variables

None required. All configuration is in `~/.dev/config.json`.

## Code Style

- Python 3.11+ features (type hints, match/case)
- Async/await for all I/O
- Rich for terminal output
- Typer for CLI
- Pydantic for data validation
- No global state (all state in config files)
