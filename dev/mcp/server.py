"""
MCP Server for Dev.

Exposes Dev's tools as an MCP server so other tools can connect to it.
Adapted from Codex's MCP server pattern.

Usage:
    dev mcp-server
    
Other tools can then connect to Dev via MCP protocol.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Optional


class McpServer:
    """
    MCP server that exposes Dev's tools.
    
    From Codex's mcp-server pattern.
    """
    
    def __init__(self, name: str = "dev-agent", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self._tools: dict[str, dict] = {}
        self._handlers: dict[str, Any] = {}
    
    def register_tool(self, name: str, definition: dict, handler: Any):
        """Register a tool with the server."""
        self._tools[name] = definition
        self._handlers[name] = handler
    
    async def start_stdio(self):
        """Start the MCP server on stdio transport."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())
        
        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                
                request = json.loads(line.decode())
                response = await self._handle_request(request)
                
                if response:
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -1, "message": str(e)},
                }
                writer.write(json.dumps(error_response).encode() + b"\n")
                await writer.drain()
    
    async def _handle_request(self, request: dict) -> dict | None:
        """Handle a JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            }
        
        elif method == "tools/list":
            tools = []
            for name, defn in self._tools.items():
                tools.append({
                    "name": name,
                    "description": defn.get("description", ""),
                    "inputSchema": defn.get("parameters", {}),
                })
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
        
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            handler = self._handlers.get(tool_name)
            if not handler:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -1, "message": f"Unknown tool: {tool_name}"},
                }
            
            try:
                result = await handler(arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}]
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -1, "message": str(e)},
                }
        
        elif method == "notifications/initialized":
            return None
        
        return None


def create_mcp_server(runtime: Any, project_path: str = ".") -> McpServer:
    """Create an MCP server from Dev's runtime."""
    server = McpServer()
    
    # Register all tools from the runtime
    for tool_name in runtime.tools.list_tools():
        handler = runtime.tools.get(tool_name)
        if handler:
            server.register_tool(
                name=tool_name,
                definition=handler.definition,
                handler=lambda args, h=handler: h.execute(args, None, project_path),
            )
    
    return server
