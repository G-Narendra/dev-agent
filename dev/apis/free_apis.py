"""
Free Public APIs Registry for Dev.

From https://github.com/public-apis/public-apis
All APIs listed here are FREE and require NO API KEY unless noted.

Categories useful for coding agents:
- Development (code execution, validation, package info)
- Machine Learning (text analysis, NLP)
- Data (JSON storage, validation)
- Web (URL shortening, screenshots)
- Utilities (time, IP, random data)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FreeApi:
    """A free public API."""
    name: str
    base_url: str
    description: str
    category: str
    auth_required: bool = False
    auth_type: str = ""  # "apiKey", "OAuth", etc.
    https: bool = True
    cors: bool = True
    rate_limit: str = "unknown"  # "generous", "moderate", "strict"
    use_cases: list[str] = field(default_factory=list)


# ============================================================================
# FREE APIs - NO AUTH REQUIRED
# ============================================================================

FREE_APIS: list[FreeApi] = [
    # === Development ===
    FreeApi(
        name="JSONPlaceholder",
        base_url="https://jsonplaceholder.typicode.com",
        description="Fake REST API for testing and prototyping",
        category="development",
        rate_limit="generous",
        use_cases=["testing", "prototyping", "demo data"],
    ),
    FreeApi(
        name="HTTPBin",
        base_url="https://httpbin.org",
        description="HTTP Request & Response Service for testing",
        category="development",
        rate_limit="generous",
        use_cases=["HTTP testing", "request inspection", "IP info"],
    ),
    FreeApi(
        name="reqres",
        base_url="https://reqres.in/api",
        description="Hosted REST API ready to respond to your AJAX requests",
        category="development",
        rate_limit="generous",
        use_cases=["testing", "prototyping", "CRUD operations"],
    ),
    FreeApi(
        name="CDNJS",
        base_url="https://api.cdnjs.com/libraries",
        description="Library info on CDNJS - find JS/CSS libraries",
        category="development",
        rate_limit="generous",
        use_cases=["find libraries", "version info", "CDN URLs"],
    ),
    FreeApi(
        name="npm Registry",
        base_url="https://registry.npmjs.org",
        description="Query information about Node.js packages",
        category="development",
        rate_limit="generous",
        use_cases=["package info", "versions", "dependencies"],
    ),
    FreeApi(
        name="GitHub API",
        base_url="https://api.github.com",
        description="GitHub repositories, code and user info (unauthenticated: 60 req/hour)",
        category="development",
        auth_required=False,
        rate_limit="moderate",
        use_cases=["repo info", "search code", "user data"],
    ),
    FreeApi(
        name="Kroki",
        base_url="https://kroki.io",
        description="Creates diagrams from textual descriptions (Mermaid, PlantUML, etc)",
        category="development",
        rate_limit="generous",
        use_cases=["diagrams", "architecture", "flowcharts"],
    ),
    FreeApi(
        name="CodeX",
        base_url="https://codex-api.jaagrav.in",
        description="Online Compiler for Various Languages",
        category="development",
        rate_limit="moderate",
        use_cases=["code execution", "testing", "compilation"],
    ),
    FreeApi(
        name="Hypersite",
        base_url="https://www.hipsum.co",
        description="Hipster lorem ipsum generator",
        category="development",
        rate_limit="generous",
        use_cases=["placeholder text", "testing"],
    ),
    FreeApi(
        name="License API",
        base_url="https://api.github.com/licenses",
        description="Choose a license info",
        category="development",
        rate_limit="moderate",
        use_cases=["license selection", "compliance"],
    ),
    
    # === Machine Learning / NLP (truly free, no auth) ===
    FreeApi(
        name="Excited",
        base_url="https://api.api-ninjas.com/v1",
        description="Collection of free APIs (no key required for some endpoints)",
        category="machine_learning",
        rate_limit="generous",
        use_cases=["various utilities"],
    ),

    FreeApi(
        name="DeepCode",
        base_url="https://api.deepcode.ai",
        description="AI for code review",
        category="machine_learning",
        rate_limit="moderate",
        use_cases=["code review", "bug detection"],
    ),
    FreeApi(
        name="OpenVisionAPI",
        base_url="https://api.openvisionapi.com",
        description="Open source computer vision API",
        category="machine_learning",
        rate_limit="moderate",
        use_cases=["image analysis", "object detection"],
    ),

    
    # === Data / Validation ===
    FreeApi(
        name="Validator",
        base_url="https://validator.ninja/api",
        description="Data validation API",
        category="data",
        rate_limit="generous",
        use_cases=["email validation", "URL validation", "data checks"],
    ),
    FreeApi(
        name="ExtendsClass JSON Storage",
        base_url="https://api.json-storage.com",
        description="Simple JSON store API",
        category="data",
        rate_limit="generous",
        use_cases=["JSON storage", "key-value store"],
    ),
    
    # === Web / Utilities ===
    FreeApi(
        name="ipify",
        base_url="https://api.ipify.org",
        description="Simple IP Address API",
        category="utilities",
        rate_limit="generous",
        use_cases=["get public IP"],
    ),
    FreeApi(
        name="icanhazip",
        base_url="https://icanhazip.com",
        description="IP Address API",
        category="utilities",
        rate_limit="generous",
        use_cases=["get public IP"],
    ),
    FreeApi(
        name="WorldTimeAPI",
        base_url="https://worldtimeapi.org/api",
        description="Timezone and world time API",
        category="utilities",
        rate_limit="generous",
        use_cases=["timezones", "world time", "UTC conversion"],
    ),
    FreeApi(
        name="Agify.io",
        base_url="https://api.agify.io",
        description="Estimates age from a first name",
        category="utilities",
        rate_limit="generous",
        use_cases=["name analysis"],
    ),
    FreeApi(
        name="Genderize.io",
        base_url="https://api.genderize.io",
        description="Estimates gender from a first name",
        category="utilities",
        rate_limit="generous",
        use_cases=["name analysis"],
    ),
    FreeApi(
        name="Nationalize.io",
        base_url="https://api.nationalize.io",
        description="Estimates nationality from a first name",
        category="utilities",
        rate_limit="generous",
        use_cases=["name analysis"],
    ),
    FreeApi(
        name="Random Data",
        base_url="https://random-data-api.com/api",
        description="Random user, address, company data",
        category="utilities",
        rate_limit="generous",
        use_cases=["test data", "prototyping"],
    ),
    FreeApi(
        name="Advice Slip",
        base_url="https://api.adviceslip.com",
        description="Random advice",
        category="utilities",
        rate_limit="generous",
        use_cases=["fun", "random advice"],
    ),
    FreeApi(
        name="Bored API",
        base_url="https://bored-api.appbrewery.com",
        description="Random activities to fight boredom",
        category="utilities",
        rate_limit="generous",
        use_cases=["random activities"],
    ),
    
    # === Open Source Projects ===
    FreeApi(
        name="Open Source Alternatives",
        base_url="https://api.opensource alternative.to",
        description="Find open source alternatives to proprietary software",
        category="development",
        rate_limit="generous",
        use_cases=["find alternatives", "open source discovery"],
    ),
    FreeApi(
        name="Libraries.io",
        base_url="https://api.libraries.io",
        description="Package dependency monitoring",
        category="development",
        rate_limit="moderate",
        use_cases=["dependency info", "versions", "security"],
    ),
    FreeApi(
        name="OSV",
        base_url="https://api.osv.dev",
        description="Open Source Vulnerabilities database",
        category="security",
        rate_limit="generous",
        use_cases=["security scanning", "vulnerability lookup"],
    ),
]


def get_free_apis(category: str | None = None) -> list[FreeApi]:
    """Get free APIs, optionally filtered by category."""
    if category:
        return [api for api in FREE_APIS if api.category == category]
    return FREE_APIS


def get_api_by_name(name: str) -> FreeApi | None:
    """Get a free API by name."""
    for api in FREE_APIS:
        if api.name.lower() == name.lower():
            return api
    return None


def get_categories() -> list[str]:
    """Get all API categories."""
    return list(set(api.category for api in FREE_APIS))


def search_apis(query: str) -> list[FreeApi]:
    """Search APIs by query."""
    query_lower = query.lower()
    return [
        api for api in FREE_APIS
        if query_lower in api.name.lower()
        or query_lower in api.description.lower()
        or query_lower in api.category.lower()
        or any(query_lower in uc.lower() for uc in api.use_cases)
    ]
