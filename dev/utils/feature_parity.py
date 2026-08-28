"""
Feature Parity Module for Dev.

Implements all missing features to match Claude Code / Cline / Aider / Codex.
"""

from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# 1. /powerup — Interactive Learning (Claude Code feature)
# ============================================================================

class PowerUp:
    """Interactive learning system — teaches users Dev features progressively."""
    
    LESSONS = [
        {
            "id": "basics",
            "title": "Getting Started with Dev",
            "content": """## Welcome to Dev!

Dev is a free AI coding agent powered by NVIDIA NIMs.

### Quick Start
1. `dev setup --key YOUR_NIM_KEY` — Configure your API key
2. `dev chat` — Start interactive coding session
3. `dev run "build a REST API"` — One-shot task

### Key Concepts
- **Streaming**: Responses appear token-by-token
- **Tools**: Dev can read/write files, run commands, search code
- **Approval modes**: Control what Dev can do automatically
- **Auto-commit**: Changes are committed automatically with AI messages

Try it now: `dev chat` and type `/help` for all commands.""",
            "difficulty": "beginner",
        },
        {
            "id": "approval-modes",
            "title": "Understanding Approval Modes",
            "content": """## Approval Modes

Dev has 3 approval modes that control what it can do:

### suggest (safest)
- Only read-only tools are auto-approved
- File writes require your approval (y/n/e)
- Use: `/approve suggest` or `--approval suggest`

### auto-edit (default)
- File edits are auto-approved
- Dangerous commands (rm -rf, etc.) require approval
- Git push requires approval
- Use: `/approve auto-edit`

### full-auto (most powerful)
- Everything is auto-approved
- Use: `/approve full-auto` or `--approval full-auto`

### Plan Mode
- Only read-only tools allowed
- Perfect for exploration and planning
- Use: `/plan` to toggle

Switch modes mid-chat with `/approve <mode>`.""",
            "difficulty": "beginner",
        },
        {
            "id": "context-management",
            "title": "Managing Context Window",
            "content": """## Context Window Management

Dev automatically manages your context window:

### Auto-Compact
When context exceeds 80%, Dev automatically summarizes older messages.

### Manual Compact
Use `/compact` to manually summarize the conversation.

### Context Visualization
Use `/context` to see a visual bar of context usage:
```
Context: ████████░░░░░░░░ 52.3% (64,000/128,000 tokens)
```

### Best Practices
- Start new sessions for unrelated tasks
- Use `/compact` when context feels bloated
- Use `--bare` mode for quick tasks (skips rules loading)""",
            "difficulty": "intermediate",
        },
        {
            "id": "skills-and-rules",
            "title": "Skills and Project Rules",
            "content": """## Skills and Rules

### Project Rules (.devrules/)
Create `.devrules/` directory with `.md` files:
```bash
dev rules create  # Creates default rules
```

### DEV.md (like CLAUDE.md)
Put project instructions in `DEV.md` at your project root.
Dev reads this at the start of every session.

### @import in Rules
Include other files in your rules:
```markdown
@import "./coding-standards.md"
@import "./architecture.md"
```

### Skills
Skills are loadable instruction sets:
```bash
dev skills-list     # List available skills
dev skill python    # Load Python skill
```

### Auto-Memory
Dev learns from your sessions and saves learnings to `.dev/memory/auto_memory.md`.""",
            "difficulty": "intermediate",
        },
        {
            "id": "advanced-features",
            "title": "Advanced Features",
            "content": """## Advanced Features

### Multi-Agent Teams
Create teams of specialized agents:
```bash
dev team create auth-sprint
dev team status auth-sprint
```

### Scheduled Agents
Run tasks on a schedule:
```bash
dev schedule add daily-review --prompt "Review PRs" --cron "0 9 * * *"
```

### Hooks
Run commands before/after tool use:
```bash
dev hooks list  # See configured hooks
```

### MCP Servers
Connect to external tools:
```bash
dev tool-rules add "git push" deny "No pushes allowed"
```

### Headless Mode (CI/CD)
Run in pipelines:
```bash
echo "fix tests" | dev headless --json
dev headless "review changes" --json -q
```

### Workflow Templates
```bash
dev templates           # List templates
dev template-run code-review  # Run a template
```""",
            "difficulty": "advanced",
        },
        {
            "id": "keyboard-shortcuts",
            "title": "Keyboard Shortcuts in Chat",
            "content": """## Chat Commands Reference

### Core
- `/help` — Show all commands
- `/quit` or `/exit` — Exit chat
- `/clear` — Clear screen

### Session
- `/save` — Save conversation
- `/history` — List saved conversations
- `/name <name>` — Name this session
- `/context` — Show context usage with visual bar
- `/compact` — Manually compact context

### Agent Control
- `/approve <mode>` — Set approval mode
- `/plan` — Toggle plan mode (read-only)
- `/model` — Show/switch NIM model
- `/effort <level>` — Set reasoning effort
- `/verbose` — Toggle verbose mode

### Project
- `/detect` — Detect project type
- `/git` — Show colored git diff
- `/rules` — Show project rules
- `/doctor` — Run diagnostics

### Information
- `/stats` — Show token/request stats
- `/cost` — Show cost dashboard
- `/agents` — List available agents
- `/templates` — List workflow templates""",
            "difficulty": "beginner",
        },
    ]
    
    def __init__(self, progress_file: str = ".dev/powerup_progress.json"):
        self.progress_file = progress_file
        self._progress: dict[str, bool] = {}
        self._load_progress()
    
    def _load_progress(self):
        """Load lesson completion progress."""
        if os.path.isfile(self.progress_file):
            try:
                with open(self.progress_file) as f:
                    self._progress = json.load(f)
            except Exception:
                self._progress = {}
    
    def _save_progress(self):
        """Save lesson completion progress."""
        os.makedirs(os.path.dirname(self.progress_file) or ".", exist_ok=True)
        with open(self.progress_file, "w") as f:
            json.dump(self._progress, f, indent=2)
    
    def list_lessons(self) -> list[dict]:
        """List all lessons with completion status."""
        return [
            {
                "id": lesson["id"],
                "title": lesson["title"],
                "difficulty": lesson["difficulty"],
                "completed": self._progress.get(lesson["id"], False),
            }
            for lesson in self.LESSONS
        ]
    
    def get_lesson(self, lesson_id: str) -> Optional[dict]:
        """Get a specific lesson."""
        for lesson in self.LESSONS:
            if lesson["id"] == lesson_id:
                return lesson
        return None
    
    def complete_lesson(self, lesson_id: str):
        """Mark a lesson as completed."""
        self._progress[lesson_id] = True
        self._save_progress()
    
    def get_progress(self) -> dict:
        """Get overall progress."""
        total = len(self.LESSONS)
        completed = sum(1 for l in self.LESSONS if self._progress.get(l["id"], False))
        return {
            "total": total,
            "completed": completed,
            "percentage": (completed / total * 100) if total > 0 else 0,
            "next_lesson": self._find_next_lesson(),
        }
    
    def _find_next_lesson(self) -> Optional[str]:
        """Find the next uncompleted lesson."""
        for lesson in self.LESSONS:
            if not self._progress.get(lesson["id"], False):
                return lesson["id"]
        return None


# ============================================================================
# 2. Real-time Context Visualization
# ============================================================================

class ContextVisualizer:
    """Real-time context window visualization."""
    
    @staticmethod
    def format_bar(tokens: int, max_tokens: int, width: int = 30) -> str:
        """Format a visual context usage bar."""
        pct = tokens / max_tokens if max_tokens > 0 else 0
        filled = int(width * pct)
        bar = "\u2588" * filled + "\u2591" * (width - filled)
        
        if pct < 0.5:
            color = "green"
        elif pct < 0.8:
            color = "yellow"
        else:
            color = "red"
        
        return f"[{color}]{bar}[/{color}] {pct*100:.1f}% ({tokens:,}/{max_tokens:,} tokens)"
    
    @staticmethod
    def format_detailed(messages: list, max_tokens: int) -> dict:
        """Format detailed context information."""
        total_tokens = 0
        by_role = {}
        
        for msg in messages:
            role = msg.role if hasattr(msg, "role") else msg.get("role", "unknown")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            tokens = len(content) // 3
            
            if role not in by_role:
                by_role[role] = {"count": 0, "tokens": 0}
            by_role[role]["count"] += 1
            by_role[role]["tokens"] += tokens
            total_tokens += tokens
        
        return {
            "total_tokens": total_tokens,
            "max_tokens": max_tokens,
            "usage_pct": (total_tokens / max_tokens * 100) if max_tokens > 0 else 0,
            "message_count": len(messages),
            "by_role": by_role,
        }


# ============================================================================
# 3. /config In-Session UI
# ============================================================================

class ConfigManager:
    """In-session configuration management."""
    
    def __init__(self, config_dir: str = ".dev"):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.json")
        self._config: dict = {}
        self._load()
    
    def _load(self):
        """Load configuration."""
        if os.path.isfile(self.config_file):
            try:
                with open(self.config_file) as f:
                    self._config = json.load(f)
            except Exception:
                self._config = {}
    
    def _save(self):
        """Save configuration."""
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set a config value."""
        self._config[key] = value
        self._save()
    
    def list_all(self) -> dict:
        """List all configuration."""
        return dict(self._config)
    
    def reset(self):
        """Reset to defaults."""
        self._config = {}
        self._save()
    
    def format_config(self) -> str:
        """Format config for display."""
        lines = ["Configuration:"]
        for key, value in sorted(self._config.items()):
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


# ============================================================================
# 4. Settings File Watching
# ============================================================================

class SettingsWatcher:
    """Watch settings files for changes and auto-reload."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._watching = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list = []
        self._last_mtime: float = 0
    
    def add_callback(self, callback):
        """Add a callback for settings changes."""
        self._callbacks.append(callback)
    
    def start(self):
        """Start watching settings files."""
        if self._watching:
            return
        self._watching = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching."""
        self._watching = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _watch_loop(self):
        """Background watch loop."""
        while self._watching:
            time.sleep(1)
            try:
                if os.path.isfile(self.config_manager.config_file):
                    mtime = os.path.getmtime(self.config_manager.config_file)
                    if mtime > self._last_mtime and self._last_mtime > 0:
                        self.config_manager._load()
                        for cb in self._callbacks:
                            try:
                                cb(self.config_manager._config)
                            except Exception:
                                pass  # Intentional: non-critical: best-effort operation
                    self._last_mtime = mtime
            except Exception:
                pass  # Intentional: non-critical: best-effort operation


# ============================================================================
# 5. Hierarchical Settings (Claude Code pattern)
# ============================================================================

@dataclass
class SettingsLevel:
    """A settings level (managed, user, project, local)."""
    name: str
    path: str
    priority: int  # Higher = overrides lower
    settings: dict = field(default_factory=dict)


class HierarchicalSettings:
    """
    Claude Code-style hierarchical settings.
    
    Priority (highest to lowest):
    1. CLI flags (--model, --approval, etc.)
    2. Local settings (.dev/local.json)
    3. Project settings (.dev/settings.json)
    4. User settings (~/.dev/settings.json)
    5. Managed settings (~/.dev/managed.json)
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._levels: list[SettingsLevel] = []
        self._init_levels()
    
    def _init_levels(self):
        """Initialize settings levels."""
        home = Path.home()
        
        self._levels = [
            SettingsLevel(
                name="managed",
                path=str(home / ".dev" / "managed.json"),
                priority=1,
            ),
            SettingsLevel(
                name="user",
                path=str(home / ".dev" / "settings.json"),
                priority=2,
            ),
            SettingsLevel(
                name="project",
                path=os.path.join(self.project_path, ".dev", "settings.json"),
                priority=3,
            ),
            SettingsLevel(
                name="local",
                path=os.path.join(self.project_path, ".dev", "local.json"),
                priority=4,
            ),
        ]
        
        # Load all levels
        for level in self._levels:
            if os.path.isfile(level.path):
                try:
                    with open(level.path) as f:
                        level.settings = json.load(f)
                except Exception:
                    level.settings = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value (highest priority wins)."""
        # Sort by priority (highest first)
        sorted_levels = sorted(self._levels, key=lambda l: l.priority, reverse=True)
        for level in sorted_levels:
            if key in level.settings:
                return level.settings[key]
        return default
    
    def set(self, key: str, value: Any, level: str = "project"):
        """Set a setting value at a specific level."""
        for lvl in self._levels:
            if lvl.name == level:
                lvl.settings[key] = value
                os.makedirs(os.path.dirname(lvl.path), exist_ok=True)
                with open(lvl.path, "w") as f:
                    json.dump(lvl.settings, f, indent=2)
                return
    
    def list_all(self) -> dict:
        """List all settings by level."""
        result = {}
        sorted_levels = sorted(self._levels, key=lambda l: l.priority, reverse=True)
        for level in sorted_levels:
            if level.settings:
                result[level.name] = level.settings
        return result
    
    def format_settings(self) -> str:
        """Format settings for display."""
        lines = ["Hierarchical Settings (highest priority first):"]
        sorted_levels = sorted(self._levels, key=lambda l: l.priority, reverse=True)
        for level in sorted_levels:
            if level.settings:
                lines.append(f"\n  [{level.name}] (priority {level.priority}):")
                for key, value in level.settings.items():
                    lines.append(f"    {key}: {value}")
        return "\n".join(lines)


# ============================================================================
# 6. GitLab CI Integration
# ============================================================================

class GitLabCI:
    """Generate GitLab CI/CD pipeline files."""
    
    TEMPLATE = """# Dev CI/CD Pipeline for GitLab
# Generated by Dev Agent

stages:
  - lint
  - test
  - review
  - deploy

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

cache:
  paths:
    - .cache/pip/
    - venv/

before_script:
  - python -m venv venv
  - source venv/bin/activate
  - pip install -r requirements.txt

lint:
  stage: lint
  script:
    - python -m py_compile **/*.py
    - pip install ruff && ruff check .
  allow_failure: true

test:
  stage: test
  script:
    - pytest --tb=short -q
  artifacts:
    reports:
      junit: report.xml
    when: always

ai-review:
  stage: review
  script:
    - pip install dev-agent
    - dev headless "Review the changes in this MR for bugs and improvements" --json
  only:
    - merge_requests
  allow_failure: true

deploy-staging:
  stage: deploy
  script:
    - echo "Deploy to staging"
  only:
    - main
  when: manual
"""
    
    @staticmethod
    def generate(project_path: str = ".") -> str:
        """Generate GitLab CI config."""
        ci_path = os.path.join(project_path, ".gitlab-ci.yml")
        with open(ci_path, "w") as f:
            f.write(GitLabCI.TEMPLATE)
        return ci_path


# ============================================================================
# 7. Custom Commit Attribution
# ============================================================================

class CommitAttribution:
    """Custom git commit attribution."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def set_author(self, name: str, email: str):
        """Set custom commit author."""
        import subprocess
        subprocess.run(
            ["git", "config", "user.name", name],
            capture_output=True, cwd=self.project_path,
        )
        subprocess.run(
            ["git", "config", "user.email", email],
            capture_output=True, cwd=self.project_path,
        )
    
    def get_author(self) -> dict:
        """Get current commit author."""
        import subprocess
        name = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, cwd=self.project_path,
        ).stdout.strip()
        email = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, cwd=self.project_path,
        ).stdout.strip()
        return {"name": name, "email": email}
    
    def create_co_authored_message(self, message: str, agent_name: str = "Dev") -> str:
        """Create a commit message with co-author attribution."""
        return f"""{message}

Co-authored-by: {agent_name} <dev-agent@local>
Generated with Dev Agent 🤖"""


# ============================================================================
# 8. JSON Schema Validation
# ============================================================================

class JSONSchemaValidator:
    """Validate JSON output against a schema."""
    
    @staticmethod
    def validate(data: dict, schema: dict) -> tuple[bool, list[str]]:
        """Validate data against a JSON schema."""
        errors = []
        
        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Check field types
        properties = schema.get("properties", {})
        for field, prop_schema in properties.items():
            if field in data:
                expected_type = prop_schema.get("type")
                value = data[field]
                
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' should be string, got {type(value).__name__}")
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{field}' should be number, got {type(value).__name__}")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{field}' should be boolean, got {type(value).__name__}")
                elif expected_type == "array" and not isinstance(value, list):
                    errors.append(f"Field '{field}' should be array, got {type(value).__name__}")
                elif expected_type == "object" and not isinstance(value, dict):
                    errors.append(f"Field '{field}' should be object, got {type(value).__name__}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def wrap_output(data: dict, schema: Optional[dict] = None) -> dict:
        """Wrap output with schema validation info."""
        result = {"data": data}
        
        if schema:
            is_valid, errors = JSONSchemaValidator.validate(data, schema)
            result["schema_valid"] = is_valid
            if errors:
                result["schema_errors"] = errors
        
        return result


# ============================================================================
# 9. Subdirectory Memory (Claude Code pattern)
# ============================================================================

class SubdirectoryMemory:
    """
    Lazy-loaded memory for subdirectories.
    Only loads memory when a directory is first accessed.
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._memory_cache: dict[str, str] = {}
        self._loaded_dirs: set[str] = set()
    
    def get_memory(self, directory: str) -> str:
        """Get memory for a directory (lazy-loaded)."""
        abs_dir = os.path.join(self.project_path, directory) if not os.path.isabs(directory) else directory
        
        if abs_dir in self._loaded_dirs:
            return self._memory_cache.get(abs_dir, "")
        
        # Try to load memory from directory
        memory_file = os.path.join(abs_dir, ".dev", "memory", "auto_memory.md")
        if os.path.isfile(memory_file):
            try:
                with open(memory_file, "r", encoding="utf-8", errors="replace") as f:
                    self._memory_cache[abs_dir] = f.read()
            except Exception:
                self._memory_cache[abs_dir] = ""
        else:
            self._memory_cache[abs_dir] = ""
        
        self._loaded_dirs.add(abs_dir)
        return self._memory_cache[abs_dir]
    
    def save_memory(self, directory: str, content: str):
        """Save memory for a directory."""
        abs_dir = os.path.join(self.project_path, directory) if not os.path.isabs(directory) else directory
        memory_dir = os.path.join(abs_dir, ".dev", "memory")
        os.makedirs(memory_dir, exist_ok=True)
        
        memory_file = os.path.join(memory_dir, "auto_memory.md")
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        self._memory_cache[abs_dir] = content
        self._loaded_dirs.add(abs_dir)
    
    def list_directories_with_memory(self) -> list[str]:
        """List all directories that have memory."""
        dirs = []
        for root, subdirs, files in os.walk(self.project_path):
            if ".dev" in subdirs:
                memory_file = os.path.join(root, ".dev", "memory", "auto_memory.md")
                if os.path.isfile(memory_file):
                    rel_dir = os.path.relpath(root, self.project_path)
                    dirs.append(rel_dir)
        return dirs


# ============================================================================
# 10. Session-to-PR Linking
# ============================================================================

class SessionPRLinker:
    """Link sessions to pull requests."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._links_file = os.path.join(project_path, ".dev", "session_pr_links.json")
        self._links: dict[str, dict] = {}
        self._load()
    
    def _load(self):
        if os.path.isfile(self._links_file):
            try:
                with open(self._links_file) as f:
                    self._links = json.load(f)
            except Exception:
                self._links = {}
    
    def _save(self):
        os.makedirs(os.path.dirname(self._links_file), exist_ok=True)
        with open(self._links_file, "w") as f:
            json.dump(self._links, f, indent=2)
    
    def link(self, session_id: str, pr_number: int, pr_url: str = ""):
        """Link a session to a PR."""
        self._links[session_id] = {
            "pr_number": pr_number,
            "pr_url": pr_url,
            "linked_at": time.time(),
        }
        self._save()
    
    def unlink(self, session_id: str):
        """Remove a session-PR link."""
        self._links.pop(session_id, None)
        self._save()
    
    def get_pr_for_session(self, session_id: str) -> Optional[dict]:
        """Get PR linked to a session."""
        return self._links.get(session_id)
    
    def get_sessions_for_pr(self, pr_number: int) -> list[str]:
        """Get all sessions linked to a PR."""
        return [
            sid for sid, link in self._links.items()
            if link.get("pr_number") == pr_number
        ]
    
    def list_links(self) -> dict:
        """List all session-PR links."""
        return dict(self._links)
