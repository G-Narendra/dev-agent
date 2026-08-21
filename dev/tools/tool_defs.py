"""
Complete tool definitions for all 31 Dev tools.

Every tool the LLM can call must have an OpenAI-compatible schema here.
This was the #1 critical bug — only 13 tools had schemas.
"""

from __future__ import annotations

from typing import Any


TOOL_DEFINITIONS = {
    # =========================================================================
    # CORE FILE TOOLS (the ones the LLM uses most)
    # =========================================================================
    "read_files": {
        "type": "function",
        "function": {
            "name": "read_files",
            "description": "Read files from disk. Supports line ranges and multiple files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "offset": {"type": "integer", "minimum": 1},
                                        "limit": {"type": "integer", "minimum": 1, "default": 2000},
                                    },
                                    "required": ["path"],
                                },
                            ],
                        },
                        "description": "List of file paths or {path, offset, limit} objects",
                    },
                },
                "required": ["paths"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content. Use for new files or complete rewrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete file content to write",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "One-sentence description of what this change does",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    "str_replace": {
        "type": "function",
        "function": {
            "name": "str_replace",
            "description": "Replace exact strings within a file. Use for targeted edits to existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to edit",
                    },
                    "replacements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "oldString": {
                                    "type": "string",
                                    "description": "Exact string to find (must match exactly, including whitespace)",
                                },
                                "newString": {
                                    "type": "string",
                                    "description": "Replacement string (empty string to delete)",
                                },
                                "allowMultiple": {
                                    "type": "boolean",
                                    "default": False,
                                    "description": "Allow replacing multiple occurrences",
                                },
                            },
                            "required": ["oldString", "newString"],
                        },
                        "description": "List of replacements to make",
                    },
                },
                "required": ["path", "replacements"],
            },
        },
    },
    "apply_patch": {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a unified diff patch to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "Unified diff patch content",
                    },
                },
                "required": ["patch"],
            },
        },
    },
    "edit_block": {
        "type": "function",
        "function": {
            "name": "edit_block",
            "description": "Edit a specific block in a file by old/new strings (like Aider's edit).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "old_block": {"type": "string", "description": "Exact block to replace"},
                    "new_block": {"type": "string", "description": "Replacement block"},
                },
                "required": ["path", "old_block", "new_block"],
            },
        },
    },

    # =========================================================================
    # SHELL & TERMINAL
    # =========================================================================
    "run_terminal_command": {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Execute a shell command. Returns stdout, stderr, and exit code. Use for builds, tests, git, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (default: project root)",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "default": 30,
                        "description": "Timeout in seconds",
                    },
                },
                "required": ["command"],
            },
        },
    },

    # =========================================================================
    # CODE SEARCH & NAVIGATION
    # =========================================================================
    "code_search": {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": "Search code files for patterns using regex. Use for finding function definitions, variable usage, imports, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "flags": {
                        "type": "string",
                        "description": "ripgrep flags (e.g. '-i' case-insensitive, '-n' line numbers, '-t py' file type)",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Directory to search in (default: project root)",
                    },
                    "maxResults": {
                        "type": "integer",
                        "default": 15,
                        "description": "Max results per file",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    "glob": {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern. Use for discovering files by name/extension.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '**/*.ts', 'src/**/*.test.ts')",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Directory to search in",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 50,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    "list_directory": {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in a path. Use for exploring project structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list",
                    },
                },
                "required": ["path"],
            },
        },
    },

    # =========================================================================
    # GIT OPERATIONS
    # =========================================================================
    "git_operations": {
        "type": "function",
        "function": {
            "name": "git_operations",
            "description": "Execute git commands (diff, log, commit, branch, status, add, push, pull).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["diff", "log", "commit", "branch", "status", "add", "push", "pull"],
                        "description": "Git action to perform",
                    },
                    "args": {
                        "type": "string",
                        "description": "Additional arguments (e.g. file paths, branch names)",
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message (for commit action)",
                    },
                },
                "required": ["action"],
            },
        },
    },

    # =========================================================================
    # WEB TOOLS
    # =========================================================================
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use for finding documentation, examples, news.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    "read_url": {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Fetch and read readable text from a URL (strips HTML/JS/CSS). Use for documentation, articles, API docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                    "max_chars": {
                        "type": "integer",
                        "default": 20000,
                        "description": "Max characters to return",
                    },
                },
                "required": ["url"],
            },
        },
    },

    # =========================================================================
    # AGENT TOOLS
    # =========================================================================
    "write_todos": {
        "type": "function",
        "function": {
            "name": "write_todos",
            "description": "Write a todo list to track multi-step tasks. Call frequently to stay on track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                                "completed": {"type": "boolean"},
                            },
                            "required": ["task", "completed"],
                        },
                        "description": "List of tasks with completion status",
                    },
                },
                "required": ["todos"],
            },
        },
    },
    "task_completed": {
        "type": "function",
        "function": {
            "name": "task_completed",
            "description": "Signal that the current task is complete with a summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "result": {"type": "string", "description": "Summary of what was done"},
                },
                "required": ["task"],
            },
        },
    },
    "spawn_agents": {
        "type": "function",
        "function": {
            "name": "spawn_agents",
            "description": "Spawn a sub-agent for a specialized task (researcher, reviewer, planner, browser).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "enum": ["researcher", "reviewer", "planner", "browser"],
                        "description": "Type of agent to spawn",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Task prompt for the sub-agent",
                    },
                },
                "required": ["agent_id", "prompt"],
            },
        },
    },

    # =========================================================================
    # CONTEXT TOOLS
    # =========================================================================
    "repo_map": {
        "type": "function",
        "function": {
            "name": "repo_map",
            "description": "Generate a map of the repository showing files, classes, and function definitions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_tokens": {
                        "type": "integer",
                        "default": 1024,
                        "description": "Max tokens for the map",
                    },
                },
            },
        },
    },
    "context_stats": {
        "type": "function",
        "function": {
            "name": "context_stats",
            "description": "Show current context window usage statistics (tokens used, messages, files).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "summarize": {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": "Summarize text to reduce context size. Use when context is getting large.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to summarize"},
                    "max_length": {"type": "integer", "description": "Max summary length in chars"},
                },
                "required": ["text"],
            },
        },
    },

    # =========================================================================
    # SANDBOX TOOLS
    # =========================================================================
    "sandboxed_run": {
        "type": "function",
        "function": {
            "name": "sandboxed_run",
            "description": "Run a command with policy checks (blocks dangerous commands).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    "sandbox_status": {
        "type": "function",
        "function": {
            "name": "sandbox_status",
            "description": "Show sandbox configuration and violation log.",
            "parameters": {"type": "object", "properties": {}},
        },
    },

    # =========================================================================
    # API & MCP TOOLS
    # =========================================================================
    "free_api": {
        "type": "function",
        "function": {
            "name": "free_api",
            "description": "Call a free public API from the public-apis registry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "api_name": {"type": "string", "description": "API name from the registry"},
                    "endpoint": {"type": "string", "description": "API endpoint path"},
                    "params": {"type": "object", "description": "Query parameters"},
                },
                "required": ["api_name"],
            },
        },
    },
    "list_apis": {
        "type": "function",
        "function": {
            "name": "list_apis",
            "description": "List available free APIs by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category (e.g. weather, finance, animals)"},
                },
            },
        },
    },
    "list_mcp_servers": {
        "type": "function",
        "function": {
            "name": "list_mcp_servers",
            "description": "List available free MCP servers that can be connected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category"},
                },
            },
        },
    },
    "install_mcp": {
        "type": "function",
        "function": {
            "name": "install_mcp",
            "description": "Install and connect to an MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "MCP server name to install"},
                },
                "required": ["name"],
            },
        },
    },
    "generate_diagram": {
        "type": "function",
        "function": {
            "name": "generate_diagram",
            "description": "Generate a diagram using Mermaid or PlantUML syntax.",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagram_type": {
                        "type": "string",
                        "enum": ["mermaid", "plantuml"],
                        "description": "Diagram format",
                    },
                    "content": {
                        "type": "string",
                        "description": "Diagram definition",
                    },
                },
                "required": ["diagram_type", "content"],
            },
        },
    },

    # =========================================================================
    # BROWSER AUTOMATION
    # =========================================================================
    "browser_screenshot": {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of a web page using Playwright.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to screenshot"},
                    "full_page": {"type": "boolean", "default": False, "description": "Capture full scrollable page"},
                },
                "required": ["url"],
            },
        },
    },
    "browser_navigate": {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate to a URL and extract content (text, links, or HTML).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to visit"},
                    "extract": {
                        "type": "string",
                        "enum": ["text", "links", "html"],
                        "default": "text",
                        "description": "What to extract",
                    },
                    "selector": {"type": "string", "description": "CSS selector to extract specific elements"},
                },
                "required": ["url"],
            },
        },
    },
    "browser_click": {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on a web page by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Page URL"},
                    "selector": {"type": "string", "description": "CSS selector to click"},
                },
                "required": ["url", "selector"],
            },
        },
    },

    # =========================================================================
    # DOCKER
    # =========================================================================
    "docker_run": {
        "type": "function",
        "function": {
            "name": "docker_run",
            "description": "Run a command inside a Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "default": "python:3.11-slim", "description": "Docker image"},
                    "command": {"type": "string", "description": "Command to run"},
                    "volumes": {"type": "array", "items": {"type": "string"}, "description": "Volume mounts"},
                    "timeout": {"type": "integer", "default": 60, "description": "Timeout seconds"},
                },
                "required": ["image", "command"],
            },
        },
    },
    "docker_build": {
        "type": "function",
        "function": {
            "name": "docker_build",
            "description": "Build a Docker image from a Dockerfile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dockerfile": {"type": "string", "default": "Dockerfile"},
                    "tag": {"type": "string", "description": "Image tag"},
                    "context": {"type": "string", "description": "Build context directory"},
                },
                "required": ["tag"],
            },
        },
    },
    "read_image": {
        "type": "function",
        "function": {
            "name": "read_image",
            "description": "Read an image file (png, jpg, gif, webp) for analysis. Use for screenshots, diagrams, photos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the image file"},
                },
                "required": ["path"],
            },
        },
    },
    "read_pdf": {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "Read a PDF document and extract its text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the PDF file"},
                    "max_pages": {"type": "integer", "description": "Max pages to read (default 50)", "default": 50},
                },
                "required": ["path"],
            },
        },
    },
    "multi_edit": {
        "type": "function",
        "function": {
            "name": "multi_edit",
            "description": "Edit multiple files atomically. All edits succeed or all roll back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "description": "List of edits",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string", "description": "Full file content"},
                                "old": {"type": "string", "description": "Old string to replace"},
                                "new": {"type": "string", "description": "New string"},
                            },
                            "required": ["path"],
                        },
                    },
                },
                "required": ["edits"],
            },
        },
    },
}


def get_tool_definition(tool_name: str) -> dict | None:
    """Get OpenAI-compatible tool definition by name."""
    return TOOL_DEFINITIONS.get(tool_name)


def get_all_definitions() -> list[dict]:
    """Get all tool definitions as a list."""
    return list(TOOL_DEFINITIONS.values())


def get_tool_names() -> list[str]:
    """Get all tool names that have definitions."""
    return list(TOOL_DEFINITIONS.keys())


def patch_tool(tool_handler: Any, tool_name: str):
    """Add definition property to a tool handler if missing."""
    if not hasattr(tool_handler, "definition") or tool_handler.definition is None:
        def_def = TOOL_DEFINITIONS.get(tool_name)
        if def_def:
            tool_handler.definition = def_def
