"""
MCP (Model Context Protocol) client for Dev.

Supports connecting to MCP servers over stdio and SSE,
and exposing their tools to the agent system.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from ..tools.base import Tool


class McpTool(Tool):
    """A tool provided by an MCP server."""
    
    def __init__(self, name: str, description: str, parameters: dict, server_name: str):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.server_name = server_name
        self._client: McpClient | None = None
        # Generate OpenAI-compatible definition for LLM schemas
        self.definition = {
            "type": "function",
            "function": {
                "name": name,
                "description": description or f"MCP tool from {server_name}",
                "parameters": parameters if parameters else {
                    "type": "object",
                    "properties": {},
                },
            },
        }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> Any:
        if not self._client:
            return {"error": "MCP client not connected"}
        return await self._client.call_tool(self.name, input_data)


class McpClient:
    """
    Client for connecting to MCP servers.
    
    Supports:
    - stdio transport (spawning a process)
    - SSE transport (connecting to an HTTP endpoint)
    """
    
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._transport = config.get("transport", "stdio")
        self._tools: dict[str, McpTool] = {}
        self._connected = False
        self._request_id = 0
    
    async def connect(self) -> list[McpTool]:
        """Connect to the MCP server and discover tools."""
        if self._transport == "stdio":
            return await self._connect_stdio()
        elif self._transport == "sse":
            return await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self._transport}")
    
    async def _connect_stdio(self) -> list[McpTool]:
        """Connect via stdio transport."""
        command = self.config.get("command", "")
        args = self.config.get("args", [])
        env = self.config.get("env", {})
        
        if not command:
            raise ValueError(f"No command specified for MCP server: {self.name}")
        
        # Validate that local script paths in args remain within project bounds
        for arg in args:
            if arg.endswith('.js') or arg.endswith('.py') or arg.endswith('.ts'):
                abs_arg = os.path.abspath(os.path.join(os.getcwd(), arg))
                if not abs_arg.startswith(os.getcwd()):
                    raise PermissionError(f"MCP server script {arg} escapes workspace")
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                command, *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={**__import__("os").environ, **env},
            )
            
            # Initialize connection
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "dev-agent",
                    "version": "0.1.0",
                },
            })
            
            # List available tools
            result = await self._send_request("tools/list", {})
            tools = result.get("tools", [])
            
            for tool_def in tools:
                tool = McpTool(
                    name=f"{self.name}/{tool_def['name']}",
                    description=tool_def.get("description", ""),
                    parameters=tool_def.get("inputSchema", {}),
                    server_name=self.name,
                )
                tool._client = self
                self._tools[tool.name] = tool
            
            self._connected = True
            return list(self._tools.values())
            
        except FileNotFoundError:
            raise ValueError(f"MCP server command not found: {command}")
        except Exception as e:
            raise ValueError(f"Failed to connect to MCP server {self.name}: {e}")
    
    async def _connect_sse(self) -> list[McpTool]:
        """Connect via SSE transport."""
        url = self.config.get("url", "")
        if not url:
            raise ValueError(f"No URL specified for MCP server: {self.name}")
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                # Try to discover tools via HTTP
                resp = await client.get(f"{url}/tools")
                if resp.status_code == 200:
                    tools_data = resp.json().get("tools", [])
                    for tool_def in tools_data:
                        tool = McpTool(
                            name=f"{self.name}/{tool_def['name']}",
                            description=tool_def.get("description", ""),
                            parameters=tool_def.get("inputSchema", {}),
                            server_name=self.name,
                        )
                        tool._client = self
                        self._tools[tool.name] = tool
        except ImportError:
            pass  # httpx not installed, skip SSE
        except Exception:
            pass  # SSE discovery failed, return empty
        
        self._connected = True
        return list(self._tools.values())
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool on the MCP server."""
        if not self._connected:
            return {"error": "Not connected to MCP server"}
        
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        
        return result
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request to the MCP server."""
        if not self._process or not self._process.stdin:
            return {"error": "Not connected"}
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        
        # Send request
        message = json.dumps(request) + "\n"
        self._process.stdin.write(message.encode())
        await self._process.stdin.drain()
        
        # Read response
        try:
            if self._process.stdout:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=30,
                )
                if line:
                    response = json.loads(line.decode())
                    return response.get("result", {})
        except asyncio.TimeoutError:
            return {"error": "MCP server response timeout"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from MCP server"}
        
        return {}
    
    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
        
        self._connected = False
        self._tools.clear()
    
    def get_tools(self) -> list[McpTool]:
        """Get all tools from this server."""
        return list(self._tools.values())


class McpManager:
    """
    Manages multiple MCP server connections.
    """
    
    def __init__(self):
        self._clients: dict[str, McpClient] = {}
        self._all_tools: dict[str, McpTool] = {}
    
    async def add_server(self, name: str, config: dict) -> list[McpTool]:
        """Add and connect to an MCP server."""
        client = McpClient(name, config)
        tools = await client.connect()
        
        self._clients[name] = client
        for tool in tools:
            self._all_tools[tool.name] = tool
        
        return tools
    
    async def remove_server(self, name: str):
        """Disconnect and remove an MCP server."""
        client = self._clients.pop(name, None)
        if client:
            await client.disconnect()
            self._all_tools = {
                k: v for k, v in self._all_tools.items()
                if v.server_name != name
            }
    
    def get_all_tools(self) -> list[McpTool]:
        """Get all tools from all connected servers."""
        return list(self._all_tools.values())
    
    def get_tool(self, name: str) -> Optional[McpTool]:
        """Get a specific tool by name."""
        return self._all_tools.get(name)
    
    async def disconnect_all(self):
        """Disconnect from all servers."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        self._all_tools.clear()
