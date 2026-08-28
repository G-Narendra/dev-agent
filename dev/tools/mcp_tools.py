"""
MCP Tools — Agent tools that connect to MCP servers

These tools allow the agent to:
1. List available MCP servers and tools
2. Connect to MCP servers
3. Execute MCP tools
4. Manage MCP configuration
"""
import json
from typing import Any

from .base import Tool


class MCPListServersTool(Tool):
    """List all configured MCP servers and their connection status."""
    
    name = "mcp_list_servers"
    description = "List all configured MCP servers and their status."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    
    def __init__(self, mcp_manager=None):
        self.mcp_manager = mcp_manager
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        if not self.mcp_manager:
            return {"error": "MCP manager not initialized"}
        
        servers = self.mcp_manager.list_servers()
        builtin = self.mcp_manager.list_builtin()
        
        return {
            "configured_servers": servers,
            "available_builtin": list(builtin.keys()),
        }


class MCPConnectTool(Tool):
    """Connect to an MCP server by name to activate its tools."""
    
    name = "mcp_connect"
    description = "Connect to an MCP server to access its tools."
    parameters = {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "Server name to connect to"},
        },
        "required": ["server"],
    }
    
    def __init__(self, mcp_client=None):
        self.mcp_client = mcp_client
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        server_name = input_data.get("server", "")
        if not server_name:
            return {"error": "Server name required"}
        
        if not self.mcp_client:
            return {"error": "MCP client not initialized"}
        
        try:
            success = await self.mcp_client.connect_server(server_name)
            if success:
                tools = [t.name for t in self.mcp_client.tools.values() 
                        if t.server_name == server_name]
                return {"success": True, "tools": tools}
            return {"error": f"Failed to connect to {server_name}"}
        except Exception as e:
            return {"error": str(e)}


class MCPListToolsTool(Tool):
    """List all tools available from a connected MCP server."""
    
    name = "mcp_list_tools"
    description = "List all available tools from connected MCP servers."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    
    def __init__(self, mcp_client=None):
        self.mcp_client = mcp_client
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        if not self.mcp_client:
            return {"error": "MCP client not initialized"}
        
        tools = await self.mcp_client.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "server": t.server_name,
                }
                for t in tools
            ]
        }


class MCPCallTool(Tool):
    """Call a tool on an MCP server with specified arguments."""
    
    name = "mcp_call"
    description = "Execute a tool on an MCP server."
    parameters = {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "description": "Full tool name (server_toolname)"},
            "arguments": {"type": "object", "description": "Tool arguments"},
        },
        "required": ["tool"],
    }
    
    def __init__(self, mcp_client=None):
        self.mcp_client = mcp_client
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        tool_name = input_data.get("tool", "")
        arguments = input_data.get("arguments", {})
        
        if not tool_name:
            return {"error": "Tool name required"}
        
        if not self.mcp_client:
            return {"error": "MCP client not initialized"}
        
        try:
            result = await self.mcp_client.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            return {"error": str(e)}


class MCPAddServerTool(Tool):
    """Add a new MCP server configuration to the registry."""
    
    name = "mcp_add_server"
    description = "Add a new MCP server to the configuration."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Server name"},
            "command": {"type": "string", "description": "Command to run (for stdio)"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
            "url": {"type": "string", "description": "URL (for HTTP transport)"},
            "builtin": {"type": "string", "description": "Use a built-in server template"},
        },
        "required": ["name"],
    }
    
    def __init__(self, mcp_manager=None):
        self.mcp_manager = mcp_manager
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        if not self.mcp_manager:
            return {"error": "MCP manager not initialized"}
        
        name = input_data.get("name", "")
        builtin = input_data.get("builtin", "")
        
        try:
            if builtin:
                self.mcp_manager.enable_builtin(builtin, args=input_data.get("args", []))
                return {"success": True, "message": f"Enabled built-in server: {builtin}"}
            else:
                self.mcp_manager.add_server(
                    name=name,
                    command=input_data.get("command", ""),
                    args=input_data.get("args", []),
                    url=input_data.get("url", ""),
                )
                return {"success": True, "message": f"Added server: {name}"}
        except Exception as e:
            return {"error": str(e)}
__all__ = ["MCPListServersTool", "MCPConnectTool", "MCPListToolsTool", "MCPCallTool", "MCPAddServerTool"]
