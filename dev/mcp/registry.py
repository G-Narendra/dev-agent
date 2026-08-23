"""
Free MCP Tools Registry for Dev.

All MCP servers listed here are FREE and open source.
From https://github.com/modelcontextprotocol/servers
And https://mcpservers.org/

Categories:
- Filesystem (secure file operations)
- Git (repository management)
- Web (fetching, search)
- Database (SQLite, PostgreSQL)
- Memory (persistent knowledge)
- Browser (automation)
- Development (code, packages)
- Search (web search)
- Communication (Slack, email)
- Productivity (Notion, calendar)
- DevOps (Docker, K8s)
- Cloud (Cloudflare, Vercel)
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
    url: str = ""


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


# ============================================================================
# EXTENDED MCP SERVERS (from mcpservers.org — top 100+ servers)
# ============================================================================

EXTENDED_MCPS: list[McpServerEntry] = [
    # ── Search ──────────────────────────────────────────────
    McpServerEntry(
        name="exa-search",
        package="exa-mcp-server",
        command="npx",
        args=["-y", "exa-mcp-server"],
        description="AI-powered web search engine by Exa",
        category="search",
        env_vars={"EXA_API_KEY": "{key}"},
        use_cases=["web search", "content discovery", "research"],
        url="https://github.com/exa-labs/exa-mcp-server",
    ),
    McpServerEntry(
        name="brave-search",
        package="@anthropic-ai/mcp-brave-search",
        command="npx",
        args=["-y", "@anthropic-ai/mcp-brave-search"],
        description="Web and local search via Brave Search API",
        category="search",
        env_vars={"BRAVE_API_KEY": "{key}"},
        use_cases=["web search", "local search", "news"],
    ),
    McpServerEntry(
        name="context7",
        package="@upstash/context7-mcp",
        command="npx",
        args=["-y", "@upstash/context7-mcp@latest"],
        description="Up-to-date library documentation and code examples",
        category="search",
        use_cases=["library docs", "code examples", "API reference"],
    ),
    McpServerEntry(
        name="deepwiki",
        package="deepwiki-mcp",
        command="npx",
        args=["-y", "deepwiki-mcp"],
        description="AI-powered codebase context and answers by Devin",
        category="search",
        use_cases=["codebase Q&A", "code context", "architecture"],
    ),
    McpServerEntry(
        name="firecrawl",
        package="firecrawl-mcp",
        command="npx",
        args=["-y", "firecrawl-mcp"],
        description="Web scraping and search capabilities",
        category="search",
        env_vars={"FIRECRAWL_API_KEY": "{key}"},
        use_cases=["web scraping", "crawling", "structured data"],
    ),

    # ── Browser Automation ──────────────────────────────────
    McpServerEntry(
        name="chrome-devtools",
        package="@anthropic-ai/mcp-chrome-devtools",
        command="npx",
        args=["-y", "@anthropic-ai/mcp-chrome-devtools"],
        description="Chrome DevTools MCP for browser control and inspection",
        category="browser",
        use_cases=["browser debugging", "DOM inspection", "performance"],
    ),
    McpServerEntry(
        name="browserbase",
        package="browserbase-mcp",
        command="npx",
        args=["-y", "browserbase-mcp"],
        description="Cloud browser automation",
        category="browser",
        env_vars={"BROWSERBASE_API_KEY": "{key}"},
        use_cases=["cloud browsing", "web automation", "form filling"],
    ),
    McpServerEntry(
        name="ego-lite-browser",
        package="ego-lite-browser",
        command="npx",
        args=["-y", "ego-lite-browser"],
        description="Fastest browser for AI agents — zero cost, zero config",
        category="browser",
        use_cases=["web automation", "shared login state", "screenshots"],
    ),

    # ── Productivity ────────────────────────────────────────
    McpServerEntry(
        name="notion",
        package="notion-mcp-server",
        command="npx",
        args=["-y", "notion-mcp-server"],
        description="Read and write Notion pages and databases",
        category="productivity",
        env_vars={"NOTION_API_KEY": "{key}"},
        use_cases=["read pages", "write pages", "query databases"],
    ),
    McpServerEntry(
        name="linear",
        package="linear-mcp-server",
        command="npx",
        args=["-y", "linear-mcp-server"],
        description="Manage issues, projects, and teams in Linear",
        category="productivity",
        env_vars={"LINEAR_API_KEY": "{key}"},
        use_cases=["issue tracking", "project management", "team ops"],
    ),
    McpServerEntry(
        name="atlassian",
        package="atlassian-mcp-server",
        command="npx",
        args=["-y", "atlassian-mcp-server"],
        description="Jira, Confluence, and Opsgenie integration",
        category="productivity",
        env_vars={"ATLASSIAN_API_KEY": "{key}", "ATLASSIAN_EMAIL": "{email}"},
        use_cases=["Jira issues", "Confluence docs", "Incidents"],
    ),
    McpServerEntry(
        name="cal-com",
        package="cal-com-mcp",
        command="npx",
        args=["-y", "cal-com-mcp"],
        description="Cal.com scheduling integration",
        category="productivity",
        use_cases=["scheduling", "booking", "calendar"],
    ),
    McpServerEntry(
        name="google-calendar",
        package="google-calendar-mcp",
        command="npx",
        args=["-y", "google-calendar-mcp"],
        description="Google Calendar integration",
        category="productivity",
        env_vars={"GOOGLE_CALENDAR_CREDENTIALS": "{json}"},
        use_cases=["calendar events", "scheduling", "reminders"],
    ),
    McpServerEntry(
        name="notebooklm",
        package="notebooklm-mcp",
        command="npx",
        args=["-y", "notebooklm-mcp"],
        description="Chat with NotebookLM for zero-hallucination answers",
        category="productivity",
        use_cases=["research", "document Q&A", "notebook queries"],
    ),

    # ── Communication ───────────────────────────────────────
    McpServerEntry(
        name="slack",
        package="@anthropic-ai/mcp-slack",
        command="npx",
        args=["-y", "@anthropic-ai/mcp-slack"],
        description="Read and post messages in Slack channels",
        category="communication",
        env_vars={"SLACK_BOT_TOKEN": "{key}"},
        use_cases=["read messages", "post messages", "channel management"],
    ),
    McpServerEntry(
        name="granola",
        package="granola-mcp",
        command="npx",
        args=["-y", "granola-mcp"],
        description="Query meeting notes and transcripts from Granola",
        category="communication",
        use_cases=["meeting notes", "transcripts", "meeting insights"],
    ),

    # ── Cloud Services ──────────────────────────────────────
    McpServerEntry(
        name="cloudflare",
        package="cloudflare-mcp",
        command="npx",
        args=["-y", "cloudflare-mcp"],
        description="Deploy and manage Cloudflare Workers, KV, R2, D1",
        category="cloud",
        env_vars={"CLOUDFLARE_API_TOKEN": "{key}"},
        use_cases=["Workers", "KV storage", "R2 storage", "D1 database"],
    ),
    McpServerEntry(
        name="vercel",
        package="vercel-mcp",
        command="npx",
        args=["-y", "vercel-mcp"],
        description="Vercel deployment and project management",
        category="cloud",
        env_vars={"VERCEL_TOKEN": "{key}"},
        use_cases=["deploy", "project management", "environment variables"],
    ),
    McpServerEntry(
        name="railway",
        package="railway-mcp",
        command="npx",
        args=["-y", "railway-mcp"],
        description="Railway project and infrastructure management",
        category="cloud",
        use_cases=["deploy", "manage projects", "environment variables"],
    ),

    # ── Database ────────────────────────────────────────────
    McpServerEntry(
        name="supabase",
        package="supabase-mcp",
        command="npx",
        args=["-y", "supabase-mcp"],
        description="Supabase database, auth, storage, edge functions",
        category="database",
        env_vars={"SUPABASE_URL": "{url}", "SUPABASE_KEY": "{key}"},
        use_cases=["SQL queries", "auth", "storage", "edge functions"],
    ),
    McpServerEntry(
        name="mongodb",
        package="mongodb-mcp",
        command="npx",
        args=["-y", "mongodb-mcp"],
        description="MongoDB database operations",
        category="database",
        env_vars={"MONGODB_URI": "{uri}"},
        use_cases=["queries", "aggregation", "schema management"],
    ),
    McpServerEntry(
        name="neo4j",
        package="neo4j-mcp",
        command="npx",
        args=["-y", "neo4j-mcp"],
        description="Neo4j graph database operations",
        category="database",
        env_vars={"NEO4J_URI": "{uri}", "NEO4J_USER": "{user}", "NEO4J_PASSWORD": "{pass}"},
        use_cases=["Cypher queries", "graph operations", "schema"],
    ),

    # ── Version Control ─────────────────────────────────────
    McpServerEntry(
        name="github-extended",
        package="@anthropic-ai/mcp-github",
        command="npx",
        args=["-y", "@anthropic-ai/mcp-github"],
        description="Extended GitHub: repos, issues, PRs, actions, code search",
        category="version-control",
        env_vars={"GITHUB_PERSONAL_ACCESS_TOKEN": "{token}"},
        use_cases=["repo management", "issues", "PRs", "CI/CD", "code search"],
    ),
    McpServerEntry(
        name="gitlab",
        package="gitlab-mcp",
        command="npx",
        args=["-y", "gitlab-mcp"],
        description="GitLab project and repository management",
        category="version-control",
        env_vars={"GITLAB_TOKEN": "{key}"},
        use_cases=["repos", "merge requests", "pipelines", "issues"],
    ),

    # ── DevOps ──────────────────────────────────────────────
    McpServerEntry(
        name="kubernetes",
        package="kubernetes-mcp",
        command="npx",
        args=["-y", "kubernetes-mcp"],
        description="Kubernetes cluster management",
        category="devops",
        use_cases=["pod management", "deployment", "service discovery"],
    ),
    McpServerEntry(
        name="terraform",
        package="terraform-mcp",
        command="npx",
        args=["-y", "terraform-mcp"],
        description="Terraform infrastructure as code management",
        category="devops",
        use_cases=["plan", "apply", "state management"],
    ),

    # ── Code Quality ────────────────────────────────────────
    McpServerEntry(
        name="next-devtools",
        package="next-devtools-mcp",
        command="npx",
        args=["-y", "next-devtools-mcp"],
        description="Next.js development tools and utilities",
        category="development",
        use_cases=["Next.js debugging", "route analysis", "performance"],
    ),
    McpServerEntry(
        name="proxyman",
        package="proxyman-mcp",
        command="npx",
        args=["-y", "proxyman-mcp"],
        description="HTTP traffic inspection and debugging",
        category="development",
        use_cases=["HTTP debugging", "traffic inspection", "rules"],
    ),

    # ── Design ──────────────────────────────────────────────
    McpServerEntry(
        name="blender",
        package="blender-mcp",
        command="npx",
        args=["-y", "blender-mcp"],
        description="Natural language interface with Blender's Python API",
        category="design",
        use_cases=["3D modeling", "scene management", "rendering"],
    ),
    McpServerEntry(
        name="figma",
        package="figma-mcp",
        command="npx",
        args=["-y", "figma-mcp"],
        description="Figma design file access and manipulation",
        category="design",
        env_vars={"FIGMA_TOKEN": "{key}"},
        use_cases=["read designs", "extract styles", "components"],
    ),

    # ── Finance ─────────────────────────────────────────────
    McpServerEntry(
        name="alpha-vantage",
        package="alpha-vantage-mcp",
        command="npx",
        args=["-y", "alpha-vantage-mcp"],
        description="Financial market data: stocks, ETFs, forex, crypto",
        category="finance",
        env_vars={"ALPHA_VANTAGE_API_KEY": "{key}"},
        use_cases=["stock prices", "forex rates", "technical indicators"],
    ),
    McpServerEntry(
        name="stripe",
        package="stripe-mcp",
        command="npx",
        args=["-y", "stripe-mcp"],
        description="Stripe payment processing and billing",
        category="finance",
        env_vars={"STRIPE_API_KEY": "{key}"},
        use_cases=["payments", "subscriptions", "invoices", "customers"],
    ),

    # ── Marketing ───────────────────────────────────────────
    McpServerEntry(
        name="google-analytics",
        package="google-analytics-mcp",
        command="npx",
        args=["-y", "google-analytics-mcp"],
        description="Google Analytics data access",
        category="marketing",
        env_vars={"GOOGLE_ANALYTICS_CREDENTIALS": "{json}"},
        use_cases=["traffic analysis", "user behavior", "conversions"],
    ),

    # ── Memory / Knowledge ──────────────────────────────────
    McpServerEntry(
        name="obsidian",
        package="obsidian-mcp",
        command="npx",
        args=["-y", "obsidian-mcp"],
        description="Read and search Obsidian vault notes",
        category="memory",
        use_cases=["note search", "knowledge base", "wiki"],
    ),

    # ── AI / ML ─────────────────────────────────────────────
    McpServerEntry(
        name="huggingface",
        package="huggingface-mcp",
        command="npx",
        args=["-y", "huggingface-mcp"],
        description="HuggingFace models, datasets, and spaces",
        category="ai",
        use_cases=["model search", "dataset access", "inference"],
    ),
    McpServerEntry(
        name="minimax",
        package="minimax-mcp",
        command="npx",
        args=["-y", "minimax-mcp"],
        description="Text-to-speech, image, and video generation",
        category="ai",
        env_vars={"MINIMAX_API_KEY": "{key}"},
        use_cases=["TTS", "image generation", "video generation"],
    ),

    # ── File Storage ────────────────────────────────────────
    McpServerEntry(
        name="google-drive",
        package="google-drive-mcp",
        command="npx",
        args=["-y", "google-drive-mcp"],
        description="Google Drive file access and management",
        category="storage",
        env_vars={"GOOGLE_DRIVE_CREDENTIALS": "{json}"},
        use_cases=["read files", "upload files", "search", "share"],
    ),
    McpServerEntry(
        name="s3",
        package="aws-s3-mcp",
        command="npx",
        args=["-y", "aws-s3-mcp"],
        description="AWS S3 bucket operations",
        category="storage",
        env_vars={"AWS_ACCESS_KEY_ID": "{key}", "AWS_SECRET_ACCESS_KEY": "{secret}"},
        use_cases=["upload", "download", "list objects", "manage buckets"],
    ),

    # ── Web Scraping ────────────────────────────────────────
    McpServerEntry(
        name="scrapingbee",
        package="scrapingbee-mcp",
        command="npx",
        args=["-y", "scrapingbee-mcp"],
        description="Web scraping with ScrapingBee",
        category="web-scraping",
        env_vars={"SCRAPINGBEE_API_KEY": "{key}"},
        use_cases=["web scraping", "screenshot", "search"],
    ),

    # ── Monitoring ──────────────────────────────────────────
    McpServerEntry(
        name="sentry",
        package="sentry-mcp",
        command="npx",
        args=["-y", "sentry-mcp"],
        description="Sentry error tracking and monitoring",
        category="monitoring",
        env_vars={"SENTRY_AUTH_TOKEN": "{key}"},
        use_cases=["error tracking", "performance monitoring", "releases"],
    ),
    McpServerEntry(
        name="datadog",
        package="datadog-mcp",
        command="npx",
        args=["-y", "datadog-mcp"],
        description="Datadog monitoring and observability",
        category="monitoring",
        env_vars={"DD_API_KEY": "{key}", "DD_APP_KEY": "{key}"},
        use_cases=["metrics", "logs", "traces", "dashboards"],
    ),

    # ── Testing ─────────────────────────────────────────────
    McpServerEntry(
        name="testrail",
        package="testrail-mcp",
        command="npx",
        args=["-y", "testrail-mcp"],
        description="TestRail test case management",
        category="testing",
        env_vars={"TESTRAIL_URL": "{url}", "TESTRAIL_USER": "{user}", "TESTRAIL_KEY": "{key}"},
        use_cases=["test cases", "test runs", "test results"],
    ),

    # ── Localization ────────────────────────────────────────
    McpServerEntry(
        name="crowdin",
        package="crowdin-mcp",
        command="npx",
        args=["-y", "crowdin-mcp"],
        description="Crowdin localization management",
        category="localization",
        env_vars={"CROWDIN_TOKEN": "{key}"},
        use_cases=["translations", "locale management", "strings"],
    ),

    # ── Typography / Fonts ──────────────────────────────────
    McpServerEntry(
        name="google-fonts",
        package="google-fonts-mcp",
        command="npx",
        args=["-y", "google-fonts-mcp"],
        description="Google Fonts API access",
        category="design",
        use_cases=["font search", "font families", "CSS generation"],
    ),
]


# All MCP servers combined
ALL_MCPS: list[McpServerEntry] = REFERENCE_MCPS + COMMUNITY_MCPS + EXTENDED_MCPS


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
    return sorted(set(mcp.category for mcp in ALL_MCPS))


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
