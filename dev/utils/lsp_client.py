"""
LSP (Language Server Protocol) client for Dev.

Connects to language servers for code intelligence:
- Diagnostics (errors/warnings)
- Completions
- Definitions
- References
- Symbols

Gracefully degrades when no LSP server is available.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LSPDiagnostic:
    """A diagnostic message from the LSP server."""
    file: str = ""
    line: int = 0
    column: int = 0
    message: str = ""
    severity: str = "info"  # "error", "warning", "info"


@dataclass
class LSPSymbol:
    """A symbol from the LSP server."""
    name: str = ""
    kind: str = ""
    location: str = ""
    container: str = ""


class LSPClient:
    """
    Client for connecting to Language Servers.
    
    Supports pyright, typescript-language-server, and other LSP servers.
    """
    
    def __init__(self, language: str = "python", project_path: str = "."):
        self.language = language
        self.project_path = os.path.abspath(project_path)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._connected = False
        self._request_id = 0
        self._server_cmd = self._find_server()
    
    def _find_server(self) -> Optional[str]:
        """Find the appropriate LSP server for the language."""
        servers = {
            "python": ["pyright-langserver", "--stdio"],
            "javascript": ["typescript-language-server", "--stdio"],
            "typescript": ["typescript-language-server", "--stdio"],
            "go": ["gopls"],
            "rust": ["rust-analyzer"],
        }
        return servers.get(self.language)
    
    async def initialize(self) -> bool:
        """Initialize connection to the LSP server."""
        if not self._server_cmd:
            return False
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._server_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # Send initialize request
            await self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": f"file://{self.project_path}",
                "capabilities": {},
            })
            
            self._connected = True
            return True
            
        except FileNotFoundError:
            self._connected = False
            return False
        except Exception:
            self._connected = False
            return False
    
    async def close(self):
        """Close the LSP connection."""
        if self._process:
            try:
                await self._send_request("shutdown", {})
                await self._send_notification("exit", {})
            except Exception:
                pass  # Intentional: non-critical: best-effort operation
            self._process.terminate()
        self._connected = False
    
    async def get_diagnostics(self, file_path: str) -> list[LSPDiagnostic]:
        """Get diagnostics for a file."""
        if not self._connected:
            return []
        
        try:
            # Open the file first
            await self._send_notification("textDocument/didOpen", {
                "textDocument": {
                    "uri": f"file://{os.path.abspath(file_path)}",
                    "languageId": self.language,
                    "version": 0,
                    "text": open(file_path, encoding="utf-8", errors="replace").read(),
                }
            })
            
            result = await self._send_request("textDocument/diagnostic", {
                "textDocument": {"uri": f"file://{os.path.abspath(file_path)}"}
            })
            
            diagnostics = []
            for diag in result.get("diagnostics", []):
                severity = {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(
                    diag.get("severity", 1), "info"
                )
                pos = diag.get("range", {}).get("start", {})
                diagnostics.append(LSPDiagnostic(
                    file=file_path,
                    line=pos.get("line", 0),
                    column=pos.get("character", 0),
                    message=diag.get("message", ""),
                    severity=severity,
                ))
            return diagnostics
        except Exception:
            return []
    
    async def get_completions(self, file_path: str, line: int, column: int) -> list[dict]:
        """Get completions at a position."""
        if not self._connected:
            return []
        
        try:
            result = await self._send_request("textDocument/completion", {
                "textDocument": {"uri": f"file://{os.path.abspath(file_path)}"},
                "position": {"line": line, "character": column},
            })
            return result.get("items", [])[:20]
        except Exception:
            return []
    
    async def get_definition(self, file_path: str, line: int, column: int) -> Optional[dict]:
        """Get definition location."""
        if not self._connected:
            return None
        
        try:
            result = await self._send_request("textDocument/definition", {
                "textDocument": {"uri": f"file://{os.path.abspath(file_path)}"},
                "position": {"line": line, "character": column},
            })
            locations = result if isinstance(result, list) else [result] if result else []
            return locations[0] if locations else None
        except Exception:
            return None
    
    async def get_references(self, file_path: str, line: int, column: int) -> list[dict]:
        """Get all references to a symbol."""
        if not self._connected:
            return []
        
        try:
            result = await self._send_request("textDocument/references", {
                "textDocument": {"uri": f"file://{os.path.abspath(file_path)}"},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": True},
            })
            return result or []
        except Exception:
            return []
    
    async def get_symbols(self, file_path: str) -> list[LSPSymbol]:
        """Get document symbols."""
        if not self._connected:
            return []
        
        try:
            result = await self._send_request("textDocument/documentSymbol", {
                "textDocument": {"uri": f"file://{os.path.abspath(file_path)}"},
            })
            
            kind_map = {
                1: "file", 2: "module", 3: "namespace", 4: "package",
                5: "class", 6: "method", 7: "property", 8: "field",
                9: "constructor", 10: "enum", 11: "interface", 12: "function",
                13: "variable", 14: "constant",
            }
            
            symbols = []
            for sym in (result or []):
                symbols.append(LSPSymbol(
                    name=sym.get("name", ""),
                    kind=kind_map.get(sym.get("kind", 0), "unknown"),
                    location=str(sym.get("location", "")),
                ))
            return symbols
        except Exception:
            return []
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request."""
        if not self._process or not self._process.stdin:
            return {}
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        
        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self._process.stdin.write(message.encode())
        await self._process.stdin.drain()
        
        try:
            # Read response
            header = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=10,
            )
            if header:
                # Parse Content-Length
                length = int(header.decode().strip().split(": ")[1])
                body = await asyncio.wait_for(
                    self._process.stdout.readexactly(length),
                    timeout=10,
                )
                response = json.loads(body.decode())
                return response.get("result", {})
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
        
        return {}
    
    async def _send_notification(self, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        
        content = json.dumps(notification)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self._process.stdin.write(message.encode())
        await self._process.stdin.drain()
