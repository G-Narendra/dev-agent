"""
Computer Use tools for Dev Agent.

Provides basic screenshot, mouse, and keyboard control capabilities.
Similar to Claude Code's computer use feature but for Windows/Linux.

Requires: pyautogui (optional, for mouse/keyboard control)
          Pillow (for screenshots)
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from typing import Any

from .base import Tool


class ComputerScreenshotTool(Tool):
    """Take screenshots of the desktop or specific windows."""
    
    name = "computer_screenshot"
    description = "Take a screenshot of the desktop or a specific application window."
    parameters = {
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "description": "Screen region to capture: 'full', 'center', or 'x,y,w,h' pixel coordinates",
                "default": "full",
            },
            "save_path": {
                "type": "string",
                "description": "Path to save the screenshot (optional, returns base64 if not provided)",
            },
        },
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        region = input_data.get("region", "full")
        save_path = input_data.get("save_path")
        
        try:
            # Try Pillow first
            from PIL import ImageGrab
            
            if region == "full":
                screenshot = ImageGrab.grab()
            elif region == "center":
                # Capture center 800x600 region
                screen = ImageGrab.grab()
                w, h = screenshot.size
                left = (w - 800) // 2
                top = (h - 600) // 2
                screenshot = ImageGrab.grab(bbox=(left, top, left + 800, top + 600))
            elif "," in region:
                # Parse x,y,w,h
                parts = [int(x.strip()) for x in region.split(",")]
                screenshot = ImageGrab.grab(bbox=tuple(parts))
            else:
                screenshot = ImageGrab.grab()
            
            if save_path:
                os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
                screenshot.save(save_path)
                return {"success": True, "path": save_path, "size": list(screenshot.size)}
            else:
                # Save to temp file
                temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                screenshot.save(temp.name)
                return {"success": True, "path": temp.name, "size": list(screenshot.size)}
                
        except ImportError:
            # Fallback to platform-specific tools
            return await self._platform_screenshot(region, save_path)
    
    async def _platform_screenshot(self, region: str, save_path: str | None) -> dict:
        """Platform-specific screenshot fallback."""
        system = platform.system()
        output_path = save_path or os.path.join(tempfile.gettempdir(), "dev_screenshot.png")
        
        try:
            if system == "Windows":
                # Use PowerShell to take screenshot
                cmd = [
                    "powershell", "-Command",
                    f"Add-Type -AssemblyName System.Windows.Forms; "
                    f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds | "
                    f"ForEach-Object {{ "
                    f"  $bmp = New-Object System.Drawing.Bitmap($_.Width, $_.Height); "
                    f"  $graphics = [System.Drawing.Graphics]::FromImage($bmp); "
                    f"  $graphics.CopyFromScreen($_.Location, [System.Drawing.Point]::Empty, $_.Size); "
                    f"  $bmp.Save('{output_path}'); "
                    f"}}"
                ]
                subprocess.run(cmd, capture_output=True, timeout=10)
            elif system == "Darwin":
                # macOS screencapture
                subprocess.run(
                    ["screencapture", "-x", output_path],
                    capture_output=True, timeout=10,
                )
            elif system == "Linux":
                # Try scrot, then import (ImageMagick)
                try:
                    subprocess.run(["scrot", output_path], capture_output=True, timeout=10)
                except FileNotFoundError:
                    subprocess.run(
                        ["import", "-window", "root", output_path],
                        capture_output=True, timeout=10,
                    )
            
            if os.path.exists(output_path):
                return {"success": True, "path": output_path}
            else:
                return {"success": False, "error": f"Screenshot not available on {system}. Install Pillow: pip install Pillow"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComputerMouseMoveTool(Tool):
    """Move the mouse cursor to a specific position."""
    
    name = "computer_mouse_move"
    description = "Move the mouse cursor to a specific position on screen."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
        },
        "required": ["x", "y"],
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        x = input_data.get("x", 0)
        y = input_data.get("y", 0)
        
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=0.3)
            return {"success": True, "position": [x, y]}
        except ImportError:
            return {"success": False, "error": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComputerClickTool(Tool):
    """Click at a specific position on screen."""
    
    name = "computer_click"
    description = "Click at a specific position on screen."
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
            "button": {
                "type": "string",
                "description": "Mouse button: 'left', 'right', 'middle'",
                "default": "left",
            },
            "clicks": {"type": "integer", "description": "Number of clicks", "default": 1},
        },
        "required": ["x", "y"],
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        x = input_data.get("x", 0)
        y = input_data.get("y", 0)
        button = input_data.get("button", "left")
        clicks = input_data.get("clicks", 1)
        
        try:
            import pyautogui
            pyautogui.click(x, y, clicks=clicks, button=button)
            return {"success": True, "clicked": [x, y], "button": button}
        except ImportError:
            return {"success": False, "error": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComputerTypeTool(Tool):
    """Type text at the current cursor position."""
    
    name = "computer_type"
    description = "Type text at the current cursor position."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to type"},
            "interval": {"type": "number", "description": "Delay between characters in seconds", "default": 0.05},
        },
        "required": ["text"],
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        text = input_data.get("text", "")
        interval = input_data.get("interval", 0.05)
        
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=interval)
            return {"success": True, "typed": len(text)}
        except ImportError:
            return {"success": False, "error": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComputerKeyTool(Tool):
    """Press a keyboard shortcut or special key."""
    
    name = "computer_key"
    description = "Press a keyboard shortcut or special key (e.g., 'enter', 'ctrl+c', 'alt+tab')."
    parameters = {
        "type": "object",
        "properties": {
            "keys": {
                "type": "string",
                "description": "Key combination (e.g., 'enter', 'ctrl+c', 'alt+tab')",
            },
        },
        "required": ["keys"],
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        keys = input_data.get("keys", "")
        
        try:
            import pyautogui
            # Handle key combinations
            if "+" in keys:
                parts = [k.strip() for k in keys.split("+")]
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(keys)
            return {"success": True, "pressed": keys}
        except ImportError:
            return {"success": False, "error": "pyautogui not installed. Install with: pip install pyautogui"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComputerOpenAppTool(Tool):
    """Open an application by name."""
    
    name = "computer_open_app"
    description = "Open an application by name (e.g., 'notepad', 'chrome', 'vscode')."
    parameters = {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name to open"},
        },
        "required": ["app_name"],
    }
    
    async def execute(self, input_data: dict, state=None, project_path=".") -> dict:
        app_name = input_data.get("app_name", "")
        
        system = platform.system()
        
        try:
            if system == "Windows":
                # Try start command
                result = subprocess.run(
                    ["cmd", "/c", "start", "", app_name],
                    capture_output=True, timeout=10,
                )
            elif system == "Darwin":
                # macOS open command
                result = subprocess.run(
                    ["open", "-a", app_name],
                    capture_output=True, timeout=10,
                )
            elif system == "Linux":
                # Try xdg-open
                result = subprocess.run(
                    ["xdg-open", app_name],
                    capture_output=True, timeout=10,
                )
            
            return {"success": True, "app": app_name, "platform": system}
            
        except FileNotFoundError:
            return {"success": False, "error": f"Application '{app_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Export all computer use tools
COMPUTER_USE_TOOLS = [
    ComputerScreenshotTool,
    ComputerMouseMoveTool,
    ComputerClickTool,
    ComputerTypeTool,
    ComputerKeyTool,
    ComputerOpenAppTool,
]
