"""
Web UI for Dev.

A lightweight web interface using Python's built-in http.server.
No external dependencies required.
"""

from __future__ import annotations

import asyncio
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
import threading


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dev - AI Coding Agent</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; }
        .container { max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { padding: 20px 0; border-bottom: 1px solid #30363d; margin-bottom: 20px; }
        .header h1 { color: #58a6ff; font-size: 24px; }
        .header p { color: #8b949e; font-size: 14px; }
        .chat { flex: 1; overflow-y: auto; padding: 20px 0; }
        .message { margin-bottom: 16px; padding: 12px 16px; border-radius: 8px; }
        .message.user { background: #1f2937; border-left: 3px solid #58a6ff; }
        .message.assistant { background: #161b22; border-left: 3px solid #3fb950; }
        .message.tool { background: #1a1e24; border-left: 3px solid #d29922; font-family: monospace; font-size: 13px; }
        .message.error { background: #1a1e24; border-left: 3px solid #f85149; }
        .message pre { background: #0d1117; padding: 12px; border-radius: 4px; overflow-x: auto; margin-top: 8px; }
        .message code { font-family: 'Fira Code', monospace; }
        .input-area { display: flex; gap: 12px; padding: 20px 0; }
        .input-area textarea { flex: 1; background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 12px; border-radius: 8px; font-size: 14px; resize: vertical; min-height: 60px; }
        .input-area textarea:focus { outline: none; border-color: #58a6ff; }
        .input-area button { background: #238636; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
        .input-area button:hover { background: #2ea043; }
        .input-area button:disabled { background: #21262d; cursor: not-allowed; }
        .status { display: flex; gap: 16px; padding: 12px 0; border-top: 1px solid #30363d; color: #8b949e; font-size: 13px; }
        .status span { display: flex; align-items: center; gap: 4px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; }
        .dot.green { background: #3fb950; }
        .dot.yellow { background: #d29922; }
        .dot.red { background: #f85149; }
        .tools-panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
        .tools-panel h3 { color: #58a6ff; margin-bottom: 12px; font-size: 14px; }
        .tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
        .tool-item { background: #0d1117; padding: 8px 12px; border-radius: 4px; font-size: 13px; }
        .tool-item .name { color: #58a6ff; }
        .tool-item .desc { color: #8b949e; }
        .loading { display: inline-block; width: 16px; height: 16px; border: 2px solid #30363d; border-top-color: #58a6ff; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Dev</h1>
            <p>Free 24/7 AI Coding Agent - Runs 100% offline</p>
        </div>
        
        <div class="tools-panel">
            <h3>🛠️ Available Tools</h3>
            <div class="tool-grid" id="tools"></div>
        </div>
        
        <div class="chat" id="chat"></div>
        
        <div class="input-area">
            <textarea id="input" placeholder="Describe what you want to build..." rows="2"></textarea>
            <button id="send" onclick="sendMessage()">Send</button>
        </div>
        
        <div class="status">
            <span><span class="dot green"></span> Connected</span>
            <span id="model-status">Model: Loading...</span>
            <span id="token-count">Tokens: 0</span>
        </div>
    </div>
    
    <script>
        let messages = [];
        let isProcessing = false;
        
        async function loadTools() {
            const resp = await fetch('/api/tools');
            const data = await resp.json();
            const grid = document.getElementById('tools');
            grid.innerHTML = data.tools.map(t => 
                `<div class="tool-item"><span class="name">${t.name}</span> <span class="desc">${t.description.substring(0, 50)}</span></div>`
            ).join('');
        }
        
        async function sendMessage() {
            const input = document.getElementById('input');
            const msg = input.value.trim();
            if (!msg || isProcessing) return;
            
            isProcessing = true;
            document.getElementById('send').disabled = true;
            
            addMessage('user', msg);
            input.value = '';
            
            try {
                const resp = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg})
                });
                
                const data = await resp.json();
                addMessage('assistant', data.response);
                
                if (data.tool_calls) {
                    data.tool_calls.forEach(tc => {
                        addMessage('tool', `🔧 ${tc.name}: ${JSON.stringify(tc.args).substring(0, 100)}`);
                    });
                }
                
                document.getElementById('token-count').textContent = `Tokens: ${data.tokens || 0}`;
            } catch (e) {
                addMessage('error', `Error: ${e.message}`);
            }
            
            isProcessing = false;
            document.getElementById('send').disabled = false;
        }
        
        function addMessage(role, content) {
            const chat = document.getElementById('chat');
            const div = document.createElement('div');
            div.className = `message ${role}`;
            div.innerHTML = `<pre>${escapeHtml(content)}</pre>`;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            messages.push({role, content});
        }
        
        function escapeHtml(text) {
            return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
        
        document.getElementById('input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        loadTools();
    </script>
</body>
</html>"""


class DevWebHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for Dev web UI."""
    
    def __init__(self, *args, runtime=None, **kwargs):
        self.runtime = runtime
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif self.path == '/api/tools':
            self.send_json(self._get_tools())
        elif self.path == '/api/status':
            self.send_json({"status": "running"})
        else:
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/chat':
            content_length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(content_length))
            response = self._handle_chat(body.get('message', ''))
            self.send_json(response)
        else:
            self.send_error(404)
    
    def _get_tools(self) -> dict:
        if self.runtime:
            tools = []
            for name in self.runtime.tools.list_tools():
                handler = self.runtime.tools.get(name)
                if handler:
                    tools.append({
                        "name": name,
                        "description": getattr(handler, "description", ""),
                    })
            return {"tools": tools}
        return {"tools": []}
    
    def _handle_chat(self, message: str) -> dict:
        if not self.runtime:
            return {"response": "Runtime not initialized", "tokens": 0}
        
        try:
            from ..agents.production_loop import ProductionAgentLoop, LoopConfig
            from ..cli.main import build_system_prompt
            
            loop = asyncio.new_event_loop()
            agent_loop = ProductionAgentLoop(
                provider=self.runtime.provider,
                tool_registry=self.runtime.tools,
                config=LoopConfig(model="default", auto_lint=True, auto_commit=True),
            )
            system_prompt = build_system_prompt("coder", ".")
            result = loop.run_until_complete(
                agent_loop.run(prompt=message, system_prompt=system_prompt, max_steps=10)
            )
            loop.close()
            
            return {
                "response": result.get("content", str(result)),
                "tokens": result.get("tokens_sent", 0) + result.get("tokens_received", 0),
                "tool_calls": result.get("tool_calls", []),
            }
        except Exception as e:
            return {"response": f"Error: {str(e)}", "tokens": 0}
    
    def send_json(self, data: dict):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs


def start_web_ui(runtime: Any, port: int = 8080):
    """Start the web UI server."""
    handler = lambda *args: DevWebHandler(*args, runtime=runtime)
    
    server = HTTPServer(('localhost', port), handler)
    
    print(f"🌐 Dev Web UI running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb UI stopped.")
        server.server_close()
