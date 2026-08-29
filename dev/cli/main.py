"""
Dev CLI — Main entry point.

Thin entrypoint that imports all command modules.
Each module registers its commands on the shared `app` instance.

Modules:
- shared.py     — Config, provider, runtime, constants
- chat.py       — Interactive chat command + slash commands
- run_cmd.py    — Single-task run, background tasks, worker
- session_cmd.py — Session management (resume, fork, stop, etc.)
- agent_cmd.py  — Teams, scheduling, messaging, daemon
- tools_cmd.py  — Tool listing, rules, MCP, project rules
- util_cmd.py   — Setup, auth, doctor, and all small commands
"""

from __future__ import annotations

# Import shared module first — defines `app` and all sub-apps
from .shared import app, console, __version__

# Import all command modules — they register on `app` via decorators
from . import chat          # noqa: F401 — registers chat command
from . import run_cmd       # noqa: F401 — registers run, task, serve
from . import session_cmd   # noqa: F401 — registers sessions, resume, fork, etc.
from . import agent_cmd     # noqa: F401 — registers team, schedule, connect, daemon
from . import tools_cmd     # noqa: F401 — registers tools-list, tool-rules, mcp
from . import util_cmd      # noqa: F401 — registers setup, auth, doctor, etc.

# Re-export for backward compatibility
__all__ = ["app", "__version__"]

if __name__ == "__main__":
    app()
