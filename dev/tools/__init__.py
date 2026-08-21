"""Agent tools for Dev."""

from .base import Tool
from .tool_defs import get_tool_definition, get_all_definitions, patch_tool
from .real_tools import (
    RealReadFilesTool, RealWriteFileTool, RealStrReplaceTool,
    RealCodeSearchTool, RealGlobTool, RealListDirectoryTool,
    RealRunTerminalCommand, RealGitOperations,
    RealWebSearchTool, RealReadUrlTool,
)
from .patch_tools import ApplyPatchTool, EditBlockTool
from .context_tools import RepoMapTool, ContextStatsTool, SummarizeTool
from .sandbox_tools import SandboxedRunTool, SandboxStatusTool
from .api_tools import (
    FreeApiTool, ListApisTool, ListMcpTools,
    InstallMcpTool, KrokiDiagramTool,
)
from .agent_tools import WriteTodosTool, TaskCompletedTool, SpawnAgentsTool
from .browser_tools import (
    BrowserScreenshotTool, BrowserNavigateTool, BrowserClickTool,
    DockerRunTool, DockerBuildTool,
)

__all__ = [
    "Tool",
    "get_tool_definition", "get_all_definitions", "patch_tool",
    "RealReadFilesTool", "RealWriteFileTool", "RealStrReplaceTool",
    "RealCodeSearchTool", "RealGlobTool", "RealListDirectoryTool",
    "RealRunTerminalCommand", "RealGitOperations",
    "RealWebSearchTool", "RealReadUrlTool",
    "ApplyPatchTool", "EditBlockTool",
    "RepoMapTool", "ContextStatsTool", "SummarizeTool",
    "SandboxedRunTool", "SandboxStatusTool",
    "FreeApiTool", "ListApisTool", "ListMcpTools",
    "InstallMcpTool", "KrokiDiagramTool",
    "WriteTodosTool", "TaskCompletedTool", "SpawnAgentsTool",
    "BrowserScreenshotTool", "BrowserNavigateTool", "BrowserClickTool",
    "DockerRunTool", "DockerBuildTool",
]
