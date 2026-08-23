"""
MCP Client — Connect to External Tools via Model Context Protocol

MCP (Model Context Protocol) is an open standard for connecting AI agents
to external tools like databases, browsers, filesystems, and APIs.

This client supports:
1. stdio transport (local subprocess servers)
2. HTTP transport (remote servers)
3. Multiple server connections
4. Tool discovery and execution

Built-in MCP servers:
- filesystem: Read/write files outside project
- sqlite: Query SQLite databases
- fetch: HTTP requests to APIs
- memory: Persistent key-value storage
"""
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict
    server_name: str = ""


@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    command: str = ""  # For stdio transport
    args: list = field(default_factory=list)
    url: str = ""  # For HTTP transport
    env: dict = field(default_factory=dict)
    enabled: bool = True


class MCPClient:
    """
    Connect to MCP servers and execute tools.
    
    Usage:
        client = MCPClient()
        
        # Add servers
        client.add_server(MCPServer(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
        ))
        
        # Connect and discover tools
        await client.connect_all()
        tools = await client.list_tools()
        
        # Execute a tool
        result = await client.call_tool("filesystem", "read_file", {"path": "/path/to/file"})
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.servers: dict[str, MCPServer] = {}
        self.connections: dict[str, Any] = {}
        self.tools: dict[str, MCPTool] = {}
        self._initialized = False
    
    def add_server(self, server: MCPServer):
        """Add an MCP server configuration."""
        self.servers[server.name] = server
    
    def remove_server(self, name: str):
        """Remove an MCP server."""
        self.servers.pop(name, None)
        self.connections.pop(name, None)
        # Remove tools from this server
        self.tools = {k: v for k, v in self.tools.items() if v.server_name != name}
    
    async def connect_all(self) -> dict[str, bool]:
        """Connect to all configured servers. Returns success status."""
        results = {}
        for name, server in self.servers.items():
            if not server.enabled:
                results[name] = False
                continue
            try:
                await self.connect_server(name)
                results[name] = True
            except Exception as e:
                print(f"Failed to connect to {name}: {e}")
                results[name] = False
        self._initialized = True
        return results
    
    async def connect_server(self, name: str) -> bool:
        """Connect to a specific MCP server."""
        server = self.servers.get(name)
        if not server:
            raise ValueError(f"Server '{name}' not configured")
        
        if server.url:
            # HTTP transport
            return await self._connect_http(name, server)
        elif server.command:
            # stdio transport
            return await self._connect_stdio(name, server)
        else:
            raise ValueError(f"Server '{name}' has no command or URL")
    
    async def _connect_stdio(self, name: str, server: MCPServer) -> bool:
        """Connect to an MCP server via stdio."""
        try:
            # Build command
            cmd = [server.command] + server.args
            
            # Set up environment
            env = os.environ.copy()
            env.update(server.env)
            
            # Start subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.project_path,
            )
            
            self.connections[name] = {
                "type": "stdio",
                "process": proc,
            }
            
            # Initialize MCP connection
            await self._send_request(name, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "dev-agent",
                    "version": "1.0.0",
                },
            })
            
            # Send initialized notification
            await self._send_notification(name, "notifications/initialized", {})
            
            # Discover tools
            await self._discover_tools(name)
            
            return True
        except Exception as e:
            print(f"stdio connection failed for {name}: {e}")
            return False
    
    async def _connect_http(self, name: str, server: MCPServer) -> bool:
        """Connect to an MCP server via HTTP."""
        try:
            import urllib.request
            
            # Initialize
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "dev-agent",
                        "version": "1.0.0",
                    },
                },
            }
            
            req = urllib.request.Request(
                server.url,
                data=json.dumps(init_request).encode(),
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read())
            
            self.connections[name] = {
                "type": "http",
                "url": server.url,
            }
            
            # Discover tools
            await self._discover_tools(name)
            
            return True
        except Exception as e:
            print(f"HTTP connection failed for {name}: {e}")
            return False
    
    async def _discover_tools(self, server_name: str):
        """Discover tools from an MCP server."""
        try:
            result = await self._send_request(server_name, "tools/list", {})
            
            if result and "tools" in result:
                for tool_data in result["tools"]:
                    tool = MCPTool(
                        name=tool_data.get("name", ""),
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", {}),
                        server_name=server_name,
                    )
                    # Prefix tool name with server name to avoid conflicts
                    full_name = f"{server_name}_{tool.name}"
                    self.tools[full_name] = tool
        except Exception as e:
            print(f"Tool discovery failed for {server_name}: {e}")
    
    async def list_tools(self) -> list[MCPTool]:
        """List all available tools from all connected servers."""
        return list(self.tools.values())
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call a tool on an MCP server.
        
        Args:
            tool_name: Full tool name (server_toolname format)
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}
        
        try:
            result = await self._send_request(
                tool.server_name,
                "tools/call",
                {
                    "name": tool.name,
                    "arguments": arguments,
                }
            )
            
            if result and "content" in result:
                # MCP returns content as a list of content blocks
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    return {"result": content[0].get("text", str(content))}
                return {"result": str(content)}
            
            return {"result": str(result) if result else "No result"}
        except Exception as e:
            return {"error": f"Tool execution failed: {e}"}
    
    async def _send_request(self, server_name: str, method: str, 
                            params: dict) -> Optional[dict]:
        """Send a JSON-RPC request to an MCP server."""
        conn = self.connections.get(server_name)
        if not conn:
            raise ValueError(f"Not connected to {server_name}")
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        
        if conn["type"] == "stdio":
            return await self._send_stdio(conn["process"], request)
        elif conn["type"] == "http":
            return await self._send_http(conn["url"], request)
        
        return None
    
    async def _send_notification(self, server_name: str, method: str, 
                                  params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        conn = self.connections.get(server_name)
        if not conn or conn["type"] != "stdio":
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        
        message = json.dumps(notification) + "\n"
        conn["process"].stdin.write(message.encode())
        await conn["process"].stdin.drain()
    
    async def _send_stdio(self, proc, request: dict) -> Optional[dict]:
        """Send request via stdio and wait for response."""
        message = json.dumps(request) + "\n"
        proc.stdin.write(message.encode())
        await proc.stdin.drain()
        
        # Read response
        response_line = await asyncio.wait_for(
            proc.stdout.readline(),
            timeout=30,
        )
        
        if response_line:
            return json.loads(response_line.decode())
        return None
    
    async def _send_http(self, url: str, request: dict) -> Optional[dict]:
        """Send request via HTTP."""
        import urllib.request
        
        req = urllib.request.Request(
            url,
            data=json.dumps(request).encode(),
            headers={"Content-Type": "application/json"},
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    
    async def disconnect_all(self):
        """Disconnect from all servers."""
        for name, conn in self.connections.items():
            if conn["type"] == "stdio" and "process" in conn:
                try:
                    conn["process"].terminate()
                    await asyncio.wait_for(conn["process"].wait(), timeout=5)
                except Exception:
                    pass
        self.connections.clear()
        self.tools.clear()
        self._initialized = False
    
    def get_tool_definitions(self) -> list[dict]:
        """Get OpenAI-compatible tool definitions for all MCP tools."""
        definitions = []
        for full_name, tool in self.tools.items():
            definitions.append({
                "type": "function",
                "function": {
                    "name": full_name,
                    "description": f"[MCP:{tool.server_name}] {tool.description}",
                    "parameters": tool.input_schema,
                },
            })
        return definitions


class MCPManager:
    """
    Manages MCP server configurations and provides built-in servers.
    
    Configuration is stored in .dev/mcp.json
    """
    
    CONFIG_FILE = ".dev/mcp.json"
    
    # Built-in server templates
    BUILTIN_SERVERS = {
        "filesystem": {
            "description": "Read/write files on the filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {},
        },
        "fetch": {
            "description": "HTTP requests to APIs and web pages",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
            "env": {},
        },
        "sqlite": {
            "description": "Query SQLite databases",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sqlite"],
            "env": {},
        },
        "memory": {
            "description": "Persistent key-value storage",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {},
        },
        "brave-search": {
            "description": "Web search via Brave Search API",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {"BRAVE_API_KEY": ""},
        },
        "github": {
            "description": "GitHub API integration",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        },
    }
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.config_path = os.path.join(self.project_path, self.CONFIG_FILE)
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load MCP configuration from file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"servers": {}}
    
    def _save_config(self):
        """Save MCP configuration to file."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def add_server(self, name: str, command: str = "", args: list = None,
                   url: str = "", env: dict = None, enabled: bool = True):
        """Add an MCP server to configuration."""
        self.config["servers"][name] = {
            "command": command,
            "args": args or [],
            "url": url,
            "env": env or {},
            "enabled": enabled,
        }
        self._save_config()
    
    def remove_server(self, name: str):
        """Remove an MCP server from configuration."""
        self.config["servers"].pop(name, None)
        self._save_config()
    
    def list_servers(self) -> dict:
        """List all configured servers."""
        return self.config.get("servers", {})
    
    def list_builtin(self) -> dict:
        """List available built-in servers."""
        return self.BUILTIN_SERVERS
    
    def enable_builtin(self, name: str, **kwargs):
        """Enable a built-in server with custom configuration."""
        template = self.BUILTIN_SERVERS.get(name)
        if not template:
            raise ValueError(f"Unknown built-in server: {name}")
        
        args = template["args"] + kwargs.get("args", [])
        env = {**template.get("env", {}), **kwargs.get("env", {})}
        
        self.add_server(
            name=name,
            command=template["command"],
            args=args,
            env=env,
        )
    
    def create_client(self) -> MCPClient:
        """Create an MCP client from configuration."""
        client = MCPClient(project_path=self.project_path)
        
        for name, server_config in self.config.get("servers", {}).items():
            server = MCPServer(
                name=name,
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                url=server_config.get("url", ""),
                env=server_config.get("env", {}),
                enabled=server_config.get("enabled", True),
            )
            client.add_server(server)
        
        return client
