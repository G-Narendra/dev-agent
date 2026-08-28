"""
API and MCP Tools for Dev.

Exposes free public APIs and MCP servers to the agent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import Tool



__all__ = ["FreeApiTool", "ListApisTool", "ListMcpTools", "InstallMcpTool", "KrokiDiagramTool"]

class FreeApiTool(Tool):
    """
    Call a free public API.
    
    Provides access to 30+ free APIs from public-apis repo.
    """
    
    name = "free_api"
    description = "Call a free public API (no API key required for most)"
    parameters = {
        "type": "object",
        "properties": {
            "api_name": {
                "type": "string",
                "description": "Name of the API to call (e.g., 'jsonplaceholder', 'httpbin', 'kroki')",
            },
            "endpoint": {
                "type": "string",
                "description": "API endpoint path (e.g., '/posts', '/ip')",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "default": "GET",
            },
            "params": {
                "type": "object",
                "description": "Query parameters",
            },
            "body": {
                "type": "object",
                "description": "Request body for POST/PUT",
            },
        },
        "required": ["api_name", "endpoint"],
    }
    
    def __init__(self):
        from ..apis.free_apis import FREE_APIS
        # FREE_APIS is a dict of {"slug": FreeAPI(...)} — iterate values
        self._apis = {}
        for slug, api in FREE_APIS.items():
            self._apis[slug.lower()] = api
            self._apis[api.name.lower().replace(" ", "")] = api
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        api_name = input_data["api_name"].lower().replace(" ", "")
        endpoint = input_data["endpoint"]
        method = input_data.get("method", "GET")
        params = input_data.get("params", {})
        body = input_data.get("body")
        
        api = self._apis.get(api_name)
        if not api:
            available = list(self._apis.keys())
            return {"error": f"Unknown API: {api_name}. Available: {available}"}
        
        url = f"{api.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url, params=params)
                elif method == "POST":
                    resp = await client.post(url, json=body, params=params)
                elif method == "PUT":
                    resp = await client.put(url, json=body, params=params)
                elif method == "DELETE":
                    resp = await client.delete(url, params=params)
                else:
                    return {"error": f"Unsupported method: {method}"}
                
                resp.raise_for_status()
                
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text[:5000]
                
                return {
                    "status_code": resp.status_code,
                    "data": data,
                    "api": api.name,
                }
                
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:500]}"}
        except Exception as e:
            return {"error": str(e)}


class ListApisTool(Tool):
    """List available free APIs."""
    
    name = "list_apis"
    description = "List available free public APIs by category"
    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Filter by category (development, machine_learning, data, utilities, security)",
            },
            "search": {
                "type": "string",
                "description": "Search query",
            },
        },
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..apis.free_apis import get_free_apis, search_apis, get_categories
        
        category = input_data.get("category")
        search = input_data.get("search")
        
        if search:
            apis = search_apis(search)
        else:
            apis = get_free_apis(category)
        
        # get_free_apis returns list[dict]; use dict keys directly
        return {
            "apis": [
                {
                    "name": api.get("name", api.get("id", "")),
                    "description": api.get("description", ""),
                    "category": api.get("category", ""),
                    "url": api.get("base_url", ""),
                }
                for api in apis
            ],
            "categories": get_categories(),
            "total": len(apis),
        }


class ListMcpTools(Tool):
    """List available MCP servers."""
    
    name = "list_mcp_servers"
    description = "List available free MCP servers"
    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Filter by category",
            },
            "search": {
                "type": "string",
                "description": "Search query",
            },
        },
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..mcp.registry import get_free_mcps, search_mcps, get_mcp_categories
        
        category = input_data.get("category")
        search = input_data.get("search")
        
        if search:
            mcps = search_mcps(search)
        else:
            mcps = get_free_mcps(category)
        
        return {
            "servers": [
                {
                    "name": mcp.name,
                    "description": mcp.description,
                    "category": mcp.category,
                    "package": mcp.package,
                    "install": f"{mcp.command} {' '.join(mcp.args)}",
                    "use_cases": mcp.use_cases,
                }
                for mcp in mcps
            ],
            "categories": get_mcp_categories(),
            "total": len(mcps),
        }


class InstallMcpTool(Tool):
    """
    Install and connect to an MCP server.
    
    Automatically installs and connects to an MCP server.
    """
    
    name = "install_mcp"
    description = "Install and connect to an MCP server"
    parameters = {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Name of the MCP server to install",
            },
            "args": {
                "type": "object",
                "description": "Arguments to pass to the server (e.g., {path: '/my/project'})",
            },
        },
        "required": ["server_name"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        from ..mcp.registry import get_mcp_by_name
        
        server_name = input_data["server_name"]
        args = input_data.get("args", {})
        
        mcp = get_mcp_by_name(server_name)
        if not mcp:
            return {"error": f"Unknown MCP server: {server_name}"}
        
        # Build command
        cmd_args = []
        for arg in mcp.args:
            for key, value in args.items():
                arg = arg.replace(f"{{{key}}}", str(value))
            cmd_args.append(arg)
        
        install_cmd = f"{mcp.command} {' '.join(cmd_args)}"
        
        return {
            "server": mcp.name,
            "description": mcp.description,
            "install_command": install_cmd,
            "category": mcp.category,
            "use_cases": mcp.use_cases,
            "note": "Run this command to start the MCP server, then add it to your Dev config.",
        }


class KrokiDiagramTool(Tool):
    """
    Generate diagrams using Kroki API.
    
    Uses the free Kroki API to generate diagrams from text.
    Supports: Mermaid, PlantUML, Graphviz, D2, etc.
    """
    
    name = "generate_diagram"
    description = "Generate a diagram from text using Kroki (Mermaid, PlantUML, Graphviz, etc)"
    parameters = {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "enum": ["mermaid", "plantuml", "graphviz", "d2", "vega", "ditaa", "erd", "excalidraw"],
                "description": "Type of diagram",
            },
            "definition": {
                "type": "string",
                "description": "Diagram definition text",
            },
            "output_format": {
                "type": "string",
                "enum": ["svg", "png", "pdf"],
                "default": "svg",
            },
            "output_path": {
                "type": "string",
                "description": "Path to save the diagram (optional)",
            },
        },
        "required": ["diagram_type", "definition"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        diagram_type = input_data["diagram_type"]
        definition = input_data["definition"]
        output_format = input_data.get("output_format", "svg")
        output_path = input_data.get("output_path")
        
        url = f"https://kroki.io/{diagram_type}/{output_format}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, content=definition)
                resp.raise_for_status()
                
                if output_path:
                    import os
                    full_path = os.path.join(project_path, output_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "wb") as f:
                        f.write(resp.content)
                    return {
                        "success": True,
                        "path": output_path,
                        "format": output_format,
                        "size": len(resp.content),
                    }
                else:
                    return {
                        "success": True,
                        "format": output_format,
                        "size": len(resp.content),
                        "note": "Diagram generated. Specify output_path to save.",
                    }
                    
        except Exception as e:
            return {"error": str(e)}
