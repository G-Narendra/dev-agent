"""
Monitor Tool for Dev Agent.

Provides real-time monitoring of background tasks, processes, and logs.
Similar to Claude Code's Monitor tool.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Optional

from .base import Tool



__all__ = ["MonitorProcessTool", "MonitorFileTool", "MonitorDirectoryTool", "MonitorLogTool"]

class MonitorProcessTool(Tool):
    """Monitor a running process for a specified duration, capturing stdout/stderr output."""
    
    name = "monitor_process"
    description = "Monitor a running process and stream its output in real-time."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to monitor"},
            "duration": {"type": "integer", "description": "How long to monitor in seconds", "default": 10},
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["command"],
    }
    
    async def execute(self, input_data: dict, state: Any = None, project_path: str = "") -> dict:
        args = input_data
        command = args.get("command", "")
        duration = args.get("duration", 10)
        cwd = args.get("cwd", ".")
        
        if not command:
            return {"success": False, "error": "command is required"}
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
            )
            
            output_lines = []
            start_time = time.time()
            
            while time.time() - start_time < duration:
                line = process.stdout.readline()
                if line:
                    output_lines.append(line.rstrip())
                elif process.poll() is not None:
                    break
                else:
                    time.sleep(0.1)
            
            # Get remaining output
            remaining = process.stdout.read()
            if remaining:
                output_lines.extend(remaining.splitlines())
            
            return {
                "success": True,
                "exit_code": process.returncode,
                "output": output_lines[-50:],  # Last 50 lines
                "total_lines": len(output_lines),
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class MonitorFileTool(Tool):
    """Monitor a file for changes (line count, modification time) over a duration."""
    
    name = "monitor_file"
    description = "Monitor a file for new lines being added (like tail -f)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to monitor"},
            "duration": {"type": "integer", "description": "How long to monitor in seconds", "default": 5},
            "lines": {"type": "integer", "description": "Number of recent lines to show first", "default": 10},
        },
        "required": ["path"],
    }
    
    async def execute(self, input_data: dict, state: Any = None, project_path: str = "") -> dict:
        args = input_data
        path = args.get("path", "")
        duration = args.get("duration", 5)
        num_lines = args.get("lines", 10)
        
        if not path or not os.path.exists(path):
            return {"success": False, "error": f"File not found: {path}"}
        
        try:
            # Read existing content
            with open(path, "r", errors="replace") as f:
                existing = f.readlines()
            
            recent = existing[-num_lines:] if len(existing) > num_lines else existing
            
            # Watch for new lines
            new_lines = []
            start_time = time.time()
            
            with open(path, "r", errors="replace") as f:
                # Seek to end
                f.seek(0, 2)
                
                while time.time() - start_time < duration:
                    line = f.readline()
                    if line:
                        new_lines.append(line.rstrip())
                    else:
                        time.sleep(0.2)
            
            return {
                "success": True,
                "recent_lines": [l.rstrip() for l in recent],
                "new_lines": new_lines,
                "total_new": len(new_lines),
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class MonitorDirectoryTool(Tool):
    """Monitor a directory for file creation, modification, or deletion events."""
    
    name = "monitor_directory"
    description = "Monitor a directory for file creation, modification, or deletion."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to monitor"},
            "duration": {"type": "integer", "description": "How long to monitor in seconds", "default": 5},
            "pattern": {"type": "string", "description": "File pattern to filter (e.g., '*.py')"},
        },
        "required": ["path"],
    }
    
    async def execute(self, input_data: dict, state: Any = None, project_path: str = "") -> dict:
        args = input_data
        path = args.get("path", ".")
        duration = args.get("duration", 5)
        pattern = args.get("pattern", "*")
        
        if not os.path.exists(path):
            return {"success": False, "error": f"Directory not found: {path}"}
        
        try:
            import fnmatch
            
            # Get initial state
            initial_files = {}
            for root, dirs, files in os.walk(path):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        filepath = os.path.join(root, f)
                        initial_files[filepath] = os.path.getmtime(filepath)
            
            # Wait and check for changes
            time.sleep(duration)
            
            current_files = {}
            changes = []
            
            for root, dirs, files in os.walk(path):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        filepath = os.path.join(root, f)
                        mtime = os.path.getmtime(filepath)
                        current_files[filepath] = mtime
                        
                        if filepath not in initial_files:
                            changes.append({"type": "created", "path": filepath})
                        elif mtime > initial_files[filepath]:
                            changes.append({"type": "modified", "path": filepath})
            
            # Check for deleted files
            for filepath in initial_files:
                if filepath not in current_files:
                    changes.append({"type": "deleted", "path": filepath})
            
            return {
                "success": True,
                "changes": changes,
                "total_changes": len(changes),
                "duration": duration,
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class MonitorLogTool(Tool):
    """Monitor a log file for new entries matching a pattern."""
    
    name = "monitor_log"
    description = "Run a command and monitor its log output for patterns."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to run"},
            "pattern": {"type": "string", "description": "Pattern to search for in output"},
            "duration": {"type": "integer", "description": "How long to monitor in seconds", "default": 10},
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["command"],
    }
    
    async def execute(self, input_data: dict, state: Any = None, project_path: str = "") -> dict:
        args = input_data
        command = args.get("command", "")
        pattern = args.get("pattern", "")
        duration = args.get("duration", 10)
        cwd = args.get("cwd", ".")
        
        if not command:
            return {"success": False, "error": "command is required"}
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
            )
            
            all_lines = []
            matched_lines = []
            start_time = time.time()
            
            while time.time() - start_time < duration:
                line = process.stdout.readline()
                if line:
                    line = line.rstrip()
                    all_lines.append(line)
                    
                    if pattern and pattern in line:
                        matched_lines.append(line)
                    elif not pattern:
                        matched_lines.append(line)
                elif process.poll() is not None:
                    break
                else:
                    time.sleep(0.1)
            
            return {
                "success": True,
                "matched_lines": matched_lines[-20:],  # Last 20 matches
                "total_matched": len(matched_lines),
                "total_lines": len(all_lines),
                "exit_code": process.returncode,
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# Export all monitor tools
MONITOR_TOOLS = [
    MonitorProcessTool,
    MonitorFileTool,
    MonitorDirectoryTool,
    MonitorLogTool,
]
