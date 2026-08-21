"""
Plugin System for Dev.

From Codex's plugin pattern and Kilocode's integration system.
Provides:
- Tool registration from plugins
- Agent registration from plugins
- Hook system for lifecycle events
- Plugin discovery and loading
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class PluginInfo:
    """Information about a plugin."""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    tools: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


class PluginHook:
    """
    Hook that plugins can register for.
    
    From Codex's hook system.
    """
    
    def __init__(self, name: str):
        self.name = name
        self._handlers: list[Callable] = []
    
    def register(self, handler: Callable):
        """Register a handler for this hook."""
        self._handlers.append(handler)
    
    async def trigger(self, *args, **kwargs) -> list[Any]:
        """Trigger all registered handlers."""
        results = []
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(*args, **kwargs)
                else:
                    result = handler(*args, **kwargs)
                results.append(result)
            except Exception as e:
                print(f"Hook {self.name} handler error: {e}")
        return results


class PluginManager:
    """
    Manages plugins for Dev.
    
    From Codex's plugin system.
    """
    
    def __init__(self, plugins_dir: str | None = None):
        self._plugins: dict[str, PluginInfo] = {}
        self._hooks: dict[str, PluginHook] = {}
        self._tool_registry: Any = None
        self._agent_registry: Any = None
        self._plugins_dir = plugins_dir or os.path.expanduser("~/.dev/plugins")
    
    def set_tool_registry(self, registry: Any):
        """Set the tool registry for plugin tool registration."""
        self._tool_registry = registry
    
    def set_agent_registry(self, registry: Any):
        """Set the agent registry for plugin agent registration."""
        self._agent_registry = registry
    
    def get_hook(self, name: str) -> PluginHook:
        """Get or create a hook."""
        if name not in self._hooks:
            self._hooks[name] = PluginHook(name)
        return self._hooks[name]
    
    def discover_plugins(self) -> list[PluginInfo]:
        """
        Discover plugins in the plugins directory.
        
        Plugins are Python packages with a dev_plugin.py entry point.
        """
        discovered = []
        
        if not os.path.isdir(self._plugins_dir):
            return discovered
        
        for entry in os.listdir(self._plugins_dir):
            plugin_path = os.path.join(self._plugins_dir, entry)
            
            if os.path.isdir(plugin_path):
                # Check for dev_plugin.py
                init_file = os.path.join(plugin_path, "dev_plugin.py")
                if os.path.exists(init_file):
                    try:
                        info = self._load_plugin_info(plugin_path, entry)
                        if info:
                            discovered.append(info)
                    except Exception as e:
                        print(f"Failed to load plugin {entry}: {e}")
        
        return discovered
    
    def load_plugin(self, plugin_name: str) -> bool:
        """
        Load a plugin by name.
        
        The plugin must have a dev_plugin.py with:
        - PLUGIN_INFO: PluginInfo
        - register_tools(registry): function to register tools
        - register_agents(registry): function to register agents
        """
        plugin_path = os.path.join(self._plugins_dir, plugin_name)
        
        if not os.path.isdir(plugin_path):
            return False
        
        init_file = os.path.join(plugin_path, "dev_plugin.py")
        if not os.path.exists(init_file):
            return False
        
        try:
            # Import the plugin module
            spec = importlib.util.spec_from_file_location(
                f"dev_plugin_{plugin_name}",
                init_file,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get plugin info
            info = getattr(module, "PLUGIN_INFO", None)
            if not info:
                info = PluginInfo(name=plugin_name)
            
            # Register tools
            register_tools = getattr(module, "register_tools", None)
            if register_tools and self._tool_registry:
                register_tools(self._tool_registry)
                info.tools = list(self._tool_registry.list_tools())
            
            # Register agents
            register_agents = getattr(module, "register_agents", None)
            if register_agents and self._agent_registry:
                register_agents(self._agent_registry)
            
            # Register hooks
            register_hooks = getattr(module, "register_hooks", None)
            if register_hooks:
                register_hooks(self)
            
            self._plugins[plugin_name] = info
            return True
            
        except Exception as e:
            print(f"Failed to load plugin {plugin_name}: {e}")
            return False
    
    def _load_plugin_info(self, plugin_path: str, name: str) -> PluginInfo | None:
        """Load plugin info from a plugin directory."""
        init_file = os.path.join(plugin_path, "dev_plugin.py")
        
        try:
            spec = importlib.util.spec_from_file_location(
                f"dev_plugin_info_{name}",
                init_file,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return getattr(module, "PLUGIN_INFO", PluginInfo(name=name))
        except Exception:
            return PluginInfo(name=name)
    
    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins."""
        return list(self._plugins.values())
    
    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get a plugin by name."""
        return self._plugins.get(name)
    
    async def trigger_hook(self, hook_name: str, *args, **kwargs) -> list[Any]:
        """Trigger a hook across all plugins."""
        hook = self._hooks.get(hook_name)
        if not hook:
            return []
        return await hook.trigger(*args, **kwargs)
