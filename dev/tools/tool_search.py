"""
ToolSearch — Meta-tool for discovering and using additional tools.

Inspired by Claude Code's ToolSearch pattern: instead of sending all 59 tools
to the LLM (which confuses smaller models), we send 15 core tools + this
meta-tool. The model can search for and use any tool on demand.

This solves the problem of Llama 70B being overwhelmed by too many tool definitions.
"""

from __future__ import annotations

from typing import Any

from .base import Tool


# All available tools with descriptions — populated at runtime
_TOOL_CATALOG: list[dict] | None = None


def _build_catalog() -> list[dict]:
    """Build a catalog of all available tools with descriptions."""
    global _TOOL_CATALOG
    if _TOOL_CATALOG is not None:
        return _TOOL_CATALOG

    catalog = []

    # Import all tool classes to get their descriptions
    tool_modules = [
        ("dev.tools.real_tools", [
            "RealReadFilesTool", "RealWriteFileTool", "RealStrReplaceTool",
            "RealCodeSearchTool", "RealGlobTool", "RealListDirectoryTool",
            "RealRunTerminalCommand", "RealGitOperations", "RealWebSearchTool",
            "RealReadUrlTool", "RealPipelineTool",
        ]),
        ("dev.tools.agent_tools", ["WriteTodosTool", "TaskCompletedTool", "SpawnAgentsTool"]),
        ("dev.tools.context_tools", ["RepoMapTool", "ContextStatsTool", "SummarizeTool"]),
        ("dev.tools.sandbox_tools", ["SandboxedRunTool", "SandboxStatusTool"]),
        ("dev.tools.api_tools", ["FreeApiTool", "ListApisTool", "ListMcpTools", "InstallMcpTool", "KrokiDiagramTool"]),
        ("dev.tools.browser_tools", [
            "BrowserScreenshotTool", "BrowserNavigateTool", "BrowserClickTool",
            "DockerRunTool", "DockerBuildTool",
        ]),
        ("dev.tools.multimodal_tools", ["ReadImageTool", "ReadPdfTool"]),
        ("dev.tools.multi_edit_tool", ["MultiEditTool"]),
        ("dev.tools.patch_tools", ["ApplyPatchTool", "EditBlockTool"]),
        ("dev.tools.skill_tool", ["SkillTool"]),
        ("dev.tools.computer_use", [
            "ComputerScreenshotTool", "ComputerMouseMoveTool", "ComputerClickTool",
            "ComputerTypeTool", "ComputerKeyTool", "ComputerOpenAppTool",
        ]),
        ("dev.tools.session_messaging", [
            "SendMessageTool", "ReceiveMessagesTool", "ListSessionsTool", "BroadcastTool",
        ]),
        ("dev.tools.monitor", [
            "MonitorProcessTool", "MonitorFileTool", "MonitorDirectoryTool", "MonitorLogTool",
        ]),
        ("dev.tools.team_tools", [
            "TeamCreateTool", "TeamExecuteTool", "TeamStatusTool", "TeamMergeTool", "TeamCleanupTool",
        ]),
        ("dev.tools.mcp_tools", [
            "MCPAddServerTool", "MCPConnectTool", "MCPListServersTool", "MCPListToolsTool", "MCPCallTool",
        ]),
    ]

    for module_name, class_names in tool_modules:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            for cls_name in class_names:
                try:
                    cls = getattr(mod, cls_name)
                    instance = cls()
                    catalog.append({
                        "name": instance.name,
                        "description": instance.description[:200],
                        "class": cls_name,
                        "module": module_name,
                    })
                except (AttributeError, Exception):
                    pass
        except ImportError:
            pass

    _TOOL_CATALOG = catalog
    return catalog


class ToolSearchTool(Tool):
    """
    Search for and discover available tools beyond the core set.

    Use this when you need a capability not in your core tool list.
    For example, if you need to read a PDF, search for "pdf" to find the read_pdf tool.
    If you need to monitor a file, search for "monitor" to find monitoring tools.
    """

    name = "tool_search"
    description = (
        "Search for available tools by keyword. Returns tool names and descriptions. "
        "Use this when you need a capability not in your core tool list."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword (e.g., 'pdf', 'browser', 'monitor', 'git', 'api')",
            },
        },
        "required": ["query"],
    }

    async def execute(self, input_data: dict, state: Any = None, project_path: str = ".") -> dict:
        query = input_data.get("query", "").lower().strip()
        if not query:
            return {"error": "query is required"}

        catalog = _build_catalog()

        # Search by name and description
        results = []
        for tool in catalog:
            if (query in tool["name"].lower() or
                query in tool["description"].lower() or
                query in tool["class"].lower()):
                results.append(tool)

        # Also search by module name
        if not results:
            for tool in catalog:
                if query in tool["module"].lower():
                    results.append(tool)

        if not results:
            # Show all tools as fallback
            return {
                "query": query,
                "matches": 0,
                "hint": f"No tools found for '{query}'. Here are all available tools:",
                "all_tools": [{"name": t["name"], "description": t["description"][:100]} for t in catalog],
            }

        return {
            "query": query,
            "matches": len(results),
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"][:150],
                    "class": t["class"],
                }
                for t in results
            ],
        }
