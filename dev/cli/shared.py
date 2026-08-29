"""
Shared utilities for all CLI modules.

Provides:
- Config loading/saving with encryption
- Provider initialization (NVIDIA NIM, OpenRouter, Bytez)
- Runtime creation with all tools registered
- System prompt building
- Constants and console reference
"""

from __future__ import annotations

import json
import os
import re as _ansi_re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..providers.nim_provider import NimProvider, RateLimitConfig
from ..providers.unified_provider import UnifiedProvider
from ..agents.runtime import AgentRuntime, ToolRegistry
from ..agents.agent_definition import get_agent, list_agents
from ..agents.production_loop import ProductionAgentLoop, LoopConfig
from ..utils.rules import RulesLoader

from .commands import register_new_tools, add_new_commands

__version__ = "1.0.0"

ANSI_ESCAPE = _ansi_re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def _sanitize_ansi(text: str) -> str:
    """Remove ANSI escape sequences to prevent terminal hijacking."""
    return ANSI_ESCAPE.sub('', text)


app = typer.Typer(
    name="dev",
    help="Dev - Free 24/7 AI coding agent powered by NVIDIA NIMs",
    no_args_is_help=False,
)

# Sub-apps
approval_app = typer.Typer(help="Manage approval modes")
checkpoint_app = typer.Typer(help="Manage checkpoints (undo/redo)")
team_app = typer.Typer(help="Manage agent teams")
mode_app = typer.Typer(help="Switch plan/act modes")
schedule_app = typer.Typer(help="Manage scheduled agents")
messaging_app = typer.Typer(help="Connect messaging platforms")

app.add_typer(approval_app, name="approval")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(team_app, name="team")
app.add_typer(mode_app, name="mode")
app.add_typer(schedule_app, name="schedule")
app.add_typer(messaging_app, name="connect")

console = Console()

CONFIG_DIR = Path.home() / ".dev"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Load config from disk, decrypting API keys."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            config = json.load(f)
        # Decrypt API keys using key vault
        try:
            from ..security.key_vault import decrypt_config_keys
            config = decrypt_config_keys(config)
        except Exception:
            pass  # Fall back to plaintext
        return config
    return {}


def save_config(config: dict, encrypt_keys: bool = True):
    """Save config to disk. API keys encrypted with machine-derived key."""
    import stat
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Encrypt API keys before saving
    if encrypt_keys:
        try:
            from ..security.key_vault import encrypt_config_keys
            config = encrypt_config_keys(config)
        except Exception:
            pass  # Fall back to plaintext
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    # Restrict file permissions to owner only (defense in depth)
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod the same way


async def get_provider():
    """Initialize the unified multi-provider system."""
    from ..providers.unified_provider import UnifiedProvider
    from ..config.provider_config import get_api_keys, has_any_key

    all_keys = get_api_keys()

    if not has_any_key():
        # First-run wizard: ask for API keys interactively
        from ..config.first_run import run_first_run_wizard
        all_keys = run_first_run_wizard()
        if not any(all_keys.values()):
            raise typer.Exit(1)

    provider = UnifiedProvider(keys=all_keys)
    await provider.initialize()

    # Log provider status
    total_keys = sum(len(v) for v in all_keys.values())
    providers = [p for p, v in all_keys.items() if v]
    console.print(f"[green]Using {', '.join(providers)} ({total_keys} keys, free tier)[/green]")

    return provider


def get_runtime(provider: NimProvider, project: str = ".") -> AgentRuntime:
    """Create an AgentRuntime with ALL tools registered."""
    registry = ToolRegistry()
    abs_project = os.path.abspath(project)

    # Real tools (file I/O, shell, git, web)
    register_new_tools(registry, abs_project)

    # Agent tools
    from ..tools.agent_tools import WriteTodosTool, TaskCompletedTool, SpawnAgentsTool
    registry.register("write_todos", WriteTodosTool())
    registry.register("task_completed", TaskCompletedTool())
    spawn_tool = SpawnAgentsTool()
    registry.register("spawn_agents", spawn_tool)

    # Context tools
    from ..tools.context_tools import RepoMapTool, ContextStatsTool, SummarizeTool
    registry.register("repo_map", RepoMapTool())
    registry.register("context_stats", ContextStatsTool())
    registry.register("summarize", SummarizeTool())

    # Sandbox tools
    from ..sandbox.sandbox_manager import SandboxManager, SandboxConfig
    from ..sandbox.exec_policy import create_default_policy
    from ..tools.sandbox_tools import SandboxedRunTool, SandboxStatusTool
    sandbox_config = SandboxConfig(project_path=abs_project)
    policy = create_default_policy(project)
    sandbox_mgr = SandboxManager(config=sandbox_config, policy=policy)
    registry.register("sandboxed_run", SandboxedRunTool(sandbox_mgr))
    registry.register("sandbox_status", SandboxStatusTool(sandbox_mgr))

    # Skills
    from ..skills.loader import SkillLoader, SkillTool
    skill_loader = SkillLoader(skills_dir=os.path.join(project, ".dev", "skills"))
    skill_loader.load_from_disk()
    registry.register("skill", SkillTool(skill_loader))

    # Tool search
    from ..tools.tool_search import ToolSearchTool
    registry.register("tool_search", ToolSearchTool())

    # Free APIs and MCP
    from ..tools.api_tools import FreeApiTool, ListApisTool, ListMcpTools, InstallMcpTool, KrokiDiagramTool
    registry.register("free_api", FreeApiTool())
    registry.register("list_apis", ListApisTool())
    registry.register("list_mcp_servers", ListMcpTools())
    registry.register("install_mcp", InstallMcpTool())
    registry.register("generate_diagram", KrokiDiagramTool())

    # Browser and Docker tools
    from ..tools.browser_tools import (
        BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool,
        DockerRunTool, DockerBuildTool,
    )
    registry.register("browser_screenshot", BrowserScreenshotTool())
    registry.register("browser_navigate", BrowserNavigateTool())
    registry.register("browser_click", BrowserClickTool())
    registry.register("docker_run", DockerRunTool())
    registry.register("docker_build", DockerBuildTool())

    # Multimodal tools (image + PDF)
    from ..tools.multimodal_tools import ReadImageTool, ReadPdfTool
    registry.register("read_image", ReadImageTool())
    registry.register("read_pdf", ReadPdfTool())

    # Multi-file atomic edit
    from ..tools.multi_edit_tool import MultiEditTool
    registry.register("multi_edit", MultiEditTool())

    # MCP servers are loaded lazily via McpRegistry
    try:
        from ..mcp.registry import ALL_MCPS
        registry._mcp_servers = ALL_MCPS
    except Exception:
        pass  # Intentional: MCP registry may not be available

    runtime = AgentRuntime(provider=provider, tool_registry=registry)
    spawn_tool.runtime = runtime
    return runtime


def build_system_prompt(agent_id: str, project_path: str, extra_rules: str = "") -> str:
    """Build a complete system prompt with agent definition, project rules, and context."""
    agent_def = get_agent(agent_id)
    parts = [agent_def.system_prompt]

    if agent_def.instructions_prompt:
        parts.append(f"\n\n## Instructions\n{agent_def.instructions_prompt}")

    # Load project rules
    rules_loader = RulesLoader(project_path)
    rules_config = rules_loader.load()
    all_rules = rules_config.get_all_rules()
    if all_rules:
        rules_text = "\n".join(f"- [{r.priority}] {r.name}: {r.content}" for r in all_rules)
        parts.append(f"\n\n## Project Rules\n{rules_text}")

    # Auto-load relevant skills based on project type
    try:
        from ..agents.skill_integration import SkillIntegration
        si = SkillIntegration(project_path)
        skill_prompt = si.build_skill_prompt("build a web application")
        if skill_prompt and len(skill_prompt) > 50:
            parts.append(f"\n\n## Relevant Skills\n{skill_prompt[:2000]}")
    except Exception:
        pass  # Skills not available, skip

    # Extra rules from --append-system-prompt
    if extra_rules:
        parts.append(f"\n\n## Additional Instructions\n{extra_rules}")

    return "\n".join(parts)


# Register additional commands from commands.py
add_new_commands(app)
