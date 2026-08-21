"""
Multi-Language Skills, Plugin Marketplace, and Performance Profiling.

Improvement #28: Multi-language skills
Improvement #29: Plugin marketplace
Improvement #30: Performance profiling
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ============================================================================
# Multi-Language Skills (#28)
# ============================================================================

MULTI_LANGUAGE_SKILLS = {
    "python": {
        "name": "Python",
        "system_prompt": """You are an expert Python developer.

## Best Practices
- Use type hints for all function signatures
- Follow PEP 8 style guide
- Use async/await for I/O-bound operations
- Write docstrings for all public functions
- Use dataclasses or pydantic for data structures
- Handle exceptions explicitly

## Common Patterns
- Use pathlib.Path instead of os.path
- Use context managers for resource management
- Use generators for memory-efficient iteration
- Use f-strings for string formatting
- Use list comprehensions over map/filter

## Testing
- Write pytest tests with descriptive names
- Use fixtures for common test data
- Mock external dependencies
- Aim for >80% coverage""",
    },
    "javascript": {
        "name": "JavaScript",
        "system_prompt": """You are an expert JavaScript developer.

## Best Practices
- Use const/let instead of var
- Use arrow functions for callbacks
- Use destructuring for objects/arrays
- Use template literals for strings
- Use optional chaining (?.) and nullish coalescing (??)
- Use async/await for promises

## Common Patterns
- Use ES modules (import/export)
- Use Array methods (map, filter, reduce)
- Use spread operator for immutability
- Use Promise.all for parallel async operations
- Use Error classes for custom errors

## Node.js
- Use fs/promises for async file operations
- Use path.join for cross-platform paths
- Use environment variables for configuration""",
    },
    "typescript": {
        "name": "TypeScript",
        "system_prompt": """You are an expert TypeScript developer.

## Best Practices
- Use strict mode (strict: true in tsconfig)
- Define interfaces for all data structures
- Use type guards for runtime type checking
- Use generics for reusable components
- Use utility types (Partial, Pick, Omit, Record)
- Use discriminated unions for state management

## Patterns
- Use branded types for type safety
- Use const assertions for literal types
- Use template literal types for string patterns
- Use conditional types for type logic
- Use mapped types for object transformations

## React + TypeScript
- Type all props with interfaces
- Use React.FC for functional components
- Type event handlers properly
- Use generic components for reuse""",
    },
    "go": {
        "name": "Go",
        "system_prompt": """You are an expert Go developer.

## Best Practices
- Handle all errors explicitly
- Use context.Context for cancellation
- Use channels for concurrent communication
- Use sync.WaitGroup for synchronization
- Keep functions small and focused
- Use meaningful variable names

## Patterns
- Use interfaces for abstraction
- Use struct embedding for composition
- Use goroutines for concurrency
- Use select for channel operations
- Use defer for cleanup

## Project Structure
- cmd/ for entry points
- internal/ for private packages
- pkg/ for public packages
- Use go modules for dependencies""",
    },
    "rust": {
        "name": "Rust",
        "system_prompt": """You are an expert Rust developer.

## Best Practices
- Use Result for error handling
- Use Option for nullable values
- Use iterators over loops
- Use pattern matching extensively
- Use traits for polymorphism
- Use lifetimes for memory safety

## Patterns
- Use newtype pattern for type safety
- Use builder pattern for complex construction
- Use RAII for resource management
- Use Arc<Mutex> for shared state
- Use channels for message passing

## Common Crates
- tokio for async runtime
- serde for serialization
- clap for CLI arguments
- reqwest for HTTP
- sqlx for database""",
    },
    "react": {
        "name": "React",
        "system_prompt": """You are an expert React developer.

## Best Practices
- Use functional components with hooks
- Keep components small and focused
- Use custom hooks for reusable logic
- Use context for global state
- Use memo for performance optimization
- Use error boundaries for error handling

## Hooks
- useState for local state
- useEffect for side effects
- useMemo for expensive computations
- useCallback for memoized functions
- useRef for mutable references
- useContext for context consumption

## Patterns
- Container/Presentational pattern
- Compound components
- Render props
- Higher-order components
- Custom hooks composition""",
    },
    "nextjs": {
        "name": "Next.js",
        "system_prompt": """You are an expert Next.js developer.

## Best Practices
- Use App Router (app/ directory)
- Use Server Components by default
- Use Client Components only when needed
- Use Server Actions for mutations
- Use streaming with Suspense
- Use parallel routes for complex layouts

## Data Fetching
- Fetch in Server Components directly
- Use SWR/React Query for client data
- Use Route Handlers for API endpoints
- Use middleware for auth/redirects

## Performance
- Use Image component for optimization
- Use next/font for font loading
- Use dynamic imports for code splitting
- Use ISR for static generation
- Use SSR for dynamic content""",
    },
    "vue": {
        "name": "Vue",
        "system_prompt": """You are an expert Vue developer.

## Best Practices
- Use Composition API (script setup)
- Use computed for derived state
- Use watchers for side effects
- Use provide/inject for dependency injection
- Use Teleport for portal components
- Use Suspense for async components

## Patterns
- Single File Components (.vue)
- Composable functions for reuse
- Reactive refs and computed
- Template refs for DOM access
- Async components with defineAsyncComponent

## Nuxt.js
- Use useFetch for data fetching
- Use useState for server/client state
- Use middleware for route guards
- Use plugins for global features""",
    },
}


# ============================================================================
# Plugin Marketplace (#29)
# ============================================================================

@dataclass
class MarketplacePlugin:
    """Information about a plugin."""
    name: str
    version: str
    description: str
    author: str = ""
    tools: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    url: str = ""


class PluginMarketplace:
    """
    Plugin marketplace for Dev.
    
    Features:
    - Discover plugins
    - Install plugins
    - Plugin registry
    """
    
    def __init__(self, plugins_dir: str = ".dev/plugins"):
        self.plugins_dir = plugins_dir
        self._registry: dict[str, MarketplacePlugin] = {}
        self._installed: dict[str, MarketplacePlugin] = {}
        
        # Built-in plugins
        self._registry["docker"] = MarketplacePlugin(
            name="docker",
            version="1.0.0",
            description="Docker container management tools",
            tools=["docker_run", "docker_build", "docker_compose"],
        )
        self._registry["browser"] = MarketplacePlugin(
            name="browser",
            version="1.0.0",
            description="Browser automation tools",
            tools=["browser_screenshot", "browser_navigate", "browser_click"],
        )
        self._registry["database"] = MarketplacePlugin(
            name="database",
            version="1.0.0",
            description="Database query tools",
            tools=["sqlite_query", "postgres_query"],
        )
        self._registry["git-advanced"] = MarketplacePlugin(
            name="git-advanced",
            version="1.0.0",
            description="Advanced git operations",
            tools=["git_blame", "git_bisect", "git_rebase"],
        )
        self._registry["testing"] = MarketplacePlugin(
            name="testing",
            version="1.0.0",
            description="Testing tools and frameworks",
            tools=["pytest_run", "jest_run", "coverage_report"],
        )
    
    def search(self, query: str) -> list[MarketplacePlugin]:
        """Search for plugins."""
        results = []
        query_lower = query.lower()
        
        for plugin in self._registry.values():
            if (query_lower in plugin.name.lower() or
                query_lower in plugin.description.lower() or
                any(query_lower in t.lower() for t in plugin.tools)):
                results.append(plugin)
        
        return results
    
    def install(self, plugin_name: str) -> MarketplacePlugin | None:
        """Install a plugin."""
        plugin = self._registry.get(plugin_name)
        if plugin:
            self._installed[plugin_name] = plugin
            return plugin
        return None
    
    def uninstall(self, plugin_name: str) -> bool:
        """Uninstall a plugin."""
        if plugin_name in self._installed:
            del self._installed[plugin_name]
            return True
        return False
    
    def list_installed(self) -> list[MarketplacePlugin]:
        """List installed plugins."""
        return list(self._installed.values())
    
    def list_available(self) -> list[MarketplacePlugin]:
        """List available plugins."""
        return list(self._registry.values())
    
    def get_plugin_tools(self) -> list[str]:
        """Get all tools from installed plugins."""
        tools = []
        for plugin in self._installed.values():
            tools.extend(plugin.tools)
        return tools


# ============================================================================
# Performance Profiling (#30)
# ============================================================================

@dataclass
class ProfileEntry:
    """A profiling entry."""
    name: str
    duration: float
    start_time: float
    end_time: float
    metadata: dict = field(default_factory=dict)


class PerformanceProfiler:
    """
    Performance profiling for Dev.
    
    Tracks:
    - Tool execution times
    - LLM call latency
    - Memory usage
    - Request throughput
    """
    
    def __init__(self):
        self._entries: list[ProfileEntry] = []
        self._active_timers: dict[str, float] = {}
    
    def start_timer(self, name: str):
        """Start a timer."""
        self._active_timers[name] = time.time()
    
    def stop_timer(self, name: str, **metadata) -> ProfileEntry | None:
        """Stop a timer and record the entry."""
        if name not in self._active_timers:
            return None
        
        start = self._active_timers.pop(name)
        end = time.time()
        duration = end - start
        
        entry = ProfileEntry(
            name=name,
            duration=duration,
            start_time=start,
            end_time=end,
            metadata=metadata,
        )
        self._entries.append(entry)
        return entry
    
    async def profile_async(self, name: str, coro, **metadata) -> Any:
        """Profile an async operation."""
        self.start_timer(name)
        try:
            result = await coro
            return result
        finally:
            self.stop_timer(name, **metadata)
    
    def get_stats(self) -> dict:
        """Get profiling statistics."""
        if not self._entries:
            return {"entries": 0}
        
        durations = [e.duration for e in self._entries]
        
        # Group by name
        by_name = defaultdict(list)
        for entry in self._entries:
            by_name[entry.name].append(entry.duration)
        
        stats = {
            "entries": len(self._entries),
            "total_time": sum(durations),
            "avg_time": sum(durations) / len(durations),
            "min_time": min(durations),
            "max_time": max(durations),
            "by_name": {},
        }
        
        for name, name_durations in by_name.items():
            stats["by_name"][name] = {
                "count": len(name_durations),
                "total": sum(name_durations),
                "avg": sum(name_durations) / len(name_durations),
                "min": min(name_durations),
                "max": max(name_durations),
            }
        
        return stats
    
    def format_report(self) -> str:
        """Format profiling report."""
        stats = self.get_stats()
        
        lines = [
            "=" * 60,
            "  DEV PERFORMANCE REPORT",
            "=" * 60,
            "",
            f"  Total Entries: {stats.get('entries', 0)}",
            f"  Total Time:    {stats.get('total_time', 0):.2f}s",
            f"  Average Time:  {stats.get('avg_time', 0):.3f}s",
            f"  Min Time:      {stats.get('min_time', 0):.3f}s",
            f"  Max Time:      {stats.get('max_time', 0):.3f}s",
            "",
            "  Breakdown:",
        ]
        
        for name, data in stats.get("by_name", {}).items():
            lines.append(
                f"    {name:30} {data['count']:5} calls  "
                f"avg {data['avg']:.3f}s  total {data['total']:.2f}s"
            )
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def get_slowest(self, n: int = 10) -> list[ProfileEntry]:
        """Get the N slowest operations."""
        return sorted(self._entries, key=lambda e: -e.duration)[:n]
    
    def get_recent(self, n: int = 10) -> list[ProfileEntry]:
        """Get the N most recent operations."""
        return self._entries[-n:]
