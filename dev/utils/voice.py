"""
Voice Input for Dev.

Supports voice-to-text input via speech_recognition library.
Gracefully degrades when not available.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional


class VoiceInput:
    """Voice input using speech_recognition."""
    
    def __init__(self):
        self._available = False
        self._recognizer = None
        self._microphone = None
        
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone()
            self._available = True
        except (ImportError, OSError):
            self._available = False
    
    def is_available(self) -> bool:
        """Check if voice input is available."""
        return self._available
    
    def listen(self, timeout: int = 5, language: str = "en-US") -> Optional[str]:
        """Listen for voice input and return transcribed text."""
        if not self._available:
            return None
        
        try:
            import speech_recognition as sr
            
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout)
            
            # Try Google free speech recognition
            text = self._recognizer.recognize_google(audio, language=language)
            return text
            
        except Exception:
            return None


def generate_vscode_extension(output_dir: str = ".") -> str:
    """Generate a VS Code extension for Dev."""
    ext_dir = os.path.join(output_dir, "dev-vscode")
    os.makedirs(ext_dir, exist_ok=True)
    
    # Create package.json
    import json
    pkg = {
        "name": "dev-agent",
        "displayName": "Dev Agent",
        "description": "AI coding agent for VS Code",
        "version": "0.1.0",
        "engines": {"vscode": "^1.80.0"},
        "activationEvents": ["onLanguage:python", "onLanguage:typescript"],
        "main": "./extension.js",
        "contributes": {
            "commands": [
                {"command": "dev.chat", "title": "Dev: Chat"},
                {"command": "dev.run", "title": "Dev: Run Task"},
            ]
        },
    }
    with open(os.path.join(ext_dir, "package.json"), "w") as f:
        json.dump(pkg, f, indent=2)
    
    # Create extension.js
    ext_js = '''
const vscode = require('vscode');
const { spawn } = require('child_process');

function activate(context) {
    let chatCmd = vscode.commands.registerCommand('dev.chat', () => {
        const terminal = vscode.window.createTerminal('Dev Chat');
        terminal.sendText('dev chat');
        terminal.show();
    });
    context.subscriptions.push(chatCmd);
}

module.exports = { activate };
'''
    with open(os.path.join(ext_dir, "extension.js"), "w") as f:
        f.write(ext_js)
    
    return ext_dir


class ToolWizard:
    """Create custom tools from natural language descriptions."""
    
    def __init__(self, tools_dir: str = ".dev/custom_tools"):
        self.tools_dir = tools_dir
        os.makedirs(tools_dir, exist_ok=True)
    
    def create_from_description(self, name: str, description: str, language: str = "python") -> dict:
        """Create a tool from a natural language description."""
        # Generate a basic tool template
        if language == "python":
            template = f'''"""
Custom tool: {name}
{description}
"""

from __future__ import annotations
from typing import Any


class {name.title().replace("_", "")}Tool:
    """{description}"""
    
    name = "{name}"
    description = "{description}"
    parameters = {{
        "type": "object",
        "properties": {{
            "input": {{"type": "string", "description": "Input data"}},
        }},
        "required": ["input"],
    }}
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        # TODO: Implement tool logic
        return {{"error": "Not implemented yet"}}
'''
            file_path = os.path.join(self.tools_dir, f"{name}.py")
            with open(file_path, "w") as f:
                f.write(template)
            
            return {
                "success": True,
                "path": file_path,
                "name": name,
                "message": f"Tool created at {file_path}. Implement the execute() method.",
            }
        
        return {"error": f"Unsupported language: {language}"}
    
    def create_tool(self, name: str, code: str) -> dict:
        """Create a tool from raw code."""
        file_path = os.path.join(self.tools_dir, f"{name}.py")
        with open(file_path, "w") as f:
            f.write(code)
        
        return {
            "success": True,
            "path": file_path,
            "name": name,
        }
    
    def list_custom_tools(self) -> list[dict]:
        """List all custom tools."""
        tools = []
        if os.path.isdir(self.tools_dir):
            for f in os.listdir(self.tools_dir):
                if f.endswith(".py") and not f.startswith("_"):
                    tools.append({
                        "name": f[:-3],
                        "path": os.path.join(self.tools_dir, f),
                    })
        return tools
