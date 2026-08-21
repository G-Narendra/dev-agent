"""
Free MCP Tools Registry for Dev.

All MCP servers listed here are FREE and open source.
From https://github.com/modelcontextprotocol/servers

Categories:
- Filesystem (secure file operations)
- Git (repository management)
- Web (fetching, search)
- Database (SQLite, PostgreSQL)
- Memory (persistent knowledge)
- Browser (automation)
- Development (code, packages)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class McpServerEntry:
    """A free MCP server."""
    name: str
    package: str  # npm package or pip package
    command: str  # npx, uvx, or python -m
    args: list[str] = field(default_factory=list)
    description: str = ""
    category: str = ""
    transport: str = "stdio"  # stdio or sse
    env_vars: dict[str, str] = field(default_factory=dict)
    use_cases: list[str] = field(default_factory=list)


# ============================================================================
# REFERENCE MCP SERVERS (from modelcontextprotocol/servers)
# ============================================================================

REFERENCE_MCPS: list[McpServerEntry] = [
    # === Filesystem ===
    McpServerEntry(
        name="filesystem",
        package="@modelcontextprotocol/server-filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "{path}"],
        description="Secure file operations with configurable access controls",
        category="filesystem",
        use_cases=["read files", "write files", "list directories"],
    ),
    
    # === Git ===
    McpServerEntry(
        name="git",
        package="mcp-server-git",
        command="uvx",
        args=["mcp-server-git", "--repository", "{path}"],
        description="Tools to read, search, and manipulate Git repositories",
        category="git",
        use_cases=["git log", "git diff", "git blame", "search history"],
    ),
    
    # === Web ===
    McpServerEntry(
        name="fetch",
        package="@modelcontextprotocol/server-fetch",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-fetch"],
        description="Web content fetching and conversion for efficient LLM usage",
        category="web",
        use_cases=["fetch web pages", "convert to markdown", "scrape content"],
    ),
    
    # === Memory ===
    McpServerEntry(
        name="memory",
        package="@modelcontextprotocol/server-memory",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        description="Knowledge graph-based persistent memory system",
        category="memory",
        use_cases=["persistent memory", "knowledge graph", "remember facts"],
    ),
    
    # === Sequential Thinking ===
    McpServerEntry(
        name="sequential-thinking",
        package="@modelcontextprotocol/server-sequential-thinking",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        description="Dynamic and reflective problem-solving through thought sequences",
        category="reasoning",
        use_cases=["complex reasoning", "step-by-step thinking"],
    ),
    
    # === Time ===
    McpServerEntry(
        name="time",
        package="@modelcontextprotocol/server-time",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-time"],
        description="Time and timezone conversion capabilities",
        category="utilities",
        use_cases=["timezone conversion", "world time", "scheduling"],
    ),
]


# ============================================================================
# COMMUNITY MCP SERVERS (from ecosystem)
# ============================================================================

COMMUNITY_MCPS: list[McpServerEntry] = [
    # === Database ===
    McpServerEntry(
        name="sqlite",
        package="mcp-server-sqlite",
        command="uvx",
        args=["mcp-server-sqlite", "--db-path", "{db_path}"],
        description="SQLite database interaction and business intelligence",
        category="database",
        use_cases=["SQL queries", "database exploration", "analytics"],
    ),
    McpServerEntry(
        name="postgres",
        package="@modelcontextprotocol/server-postgres",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres", "{connection_string}"],
        description="PostgreSQL read-only database access with schema inspection",
        category="database",
        use_cases=["SQL queries", "schema inspection", "data analysis"],
    ),
    McpServerEntry(
        name="redis",
        package="mcp-server-redis",
        command="uvx",
        args=["mcp-server-redis"],
        description="Interact with Redis key-value stores",
        category="database",
        use_cases=["caching", "key-value store", "pub/sub"],
    ),
    
    # === Browser ===
    McpServerEntry(
        name="puppeteer",
        package="@modelcontextprotocol/server-puppeteer",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        description="Browser automation and web scraping",
        category="browser",
        use_cases=["web scraping", "form filling", "screenshots", "testing"],
    ),
    McpServerEntry(
        name="playwright",
        package="@playwright/mcp",
        command="npx",
        args=["-y", "@playwright/mcp"],
        description="Browser automation using Playwright",
        category="browser",
        use_cases=["web testing", "automation", "screenshots"],
    ),
    
    # === Development ===
    # NOTE: GitHub MCP requires a free personal access token from github.com
    McpServerEntry(
        name="github",
        package="@modelcontextprotocol/server-github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        description="GitHub repository management (requires free GitHub token)",
        category="development",
        env_vars={"GITHUB_PERSONAL_ACCESS_TOKEN": "{token}"},
        use_cases=["repo management", "issues", "PRs", "code search"],
    ),
    McpServerEntry(
        name="docker",
        package="mcp-server-docker",
        command="uvx",
        args=["mcp-server-docker"],
        description="Docker container management",
        category="development",
        use_cases=["container management", "image building", "compose"],
    ),
    
]


# All MCP servers
ALL_MCPS: list[McpServerEntry] = REFERENCE_MCPS + COMMUNITY_MCPS


def get_free_mcps(category: str | None = None) -> list[McpServerEntry]:
    """Get free MCP servers, optionally filtered by category."""
    if category:
        return [mcp for mcp in ALL_MCPS if mcp.category == category]
    return ALL_MCPS


def get_mcp_by_name(name: str) -> McpServerEntry | None:
    """Get an MCP server by name."""
    for mcp in ALL_MCPS:
        if mcp.name.lower() == name.lower():
            return mcp
    return None


def get_mcp_categories() -> list[str]:
    """Get all MCP categories."""
    return list(set(mcp.category for mcp in ALL_MCPS))


def search_mcps(query: str) -> list[McpServerEntry]:
    """Search MCP servers by query."""
    query_lower = query.lower()
    return [
        mcp for mcp in ALL_MCPS
        if query_lower in mcp.name.lower()
        or query_lower in mcp.description.lower()
        or query_lower in mcp.category.lower()
        or any(query_lower in uc.lower() for uc in mcp.use_cases)
    ]
