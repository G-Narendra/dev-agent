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
        use_cases=["testing", "prototyping", "user management"],
    ),
    FreeApi(
        name="Bored API",
        base_url="https://bored-api.appbrewery.com",
        description="Random activities to fight boredom",
        category="entertainment",
        rate_limit="moderate",
        use_cases=["random activities", "fun suggestions"],
    ),
    FreeApi(
        name="Advice Slip",
        base_url="https://api.adviceslip.com",
        description="Random advice slips",
        category="utilities",
        rate_limit="generous",
        use_cases=["random advice", "inspiration"],
    ),
    FreeApi(
        name="Random Fox",
        base_url="https://randomfox.ca/floof",
        description="Random fox pictures",
        category="animals",
        rate_limit="generous",
        use_cases=["random images", "fun content"],
    ),
    FreeApi(
        name="Random Dog",
        base_url="https://random.dog/woof.json",
        description="Random dog pictures",
        category="animals",
        rate_limit="generous",
        use_cases=["random images", "fun content"],
    ),
    FreeApi(
        name="Random Cat",
        base_url="https://api.thecatapi.com/v1/images/search",
        description="Random cat pictures",
        category="animals",
        rate_limit="generous",
        use_cases=["random images", "fun content"],
    ),
    FreeApi(
        name="Cat Facts",
        base_url="https://catfact.ninja/fact",
        description="Random cat facts",
        category="animals",
        rate_limit="generous",
        use_cases=["random facts", "fun content"],
    ),
    FreeApi(
        name="Dog Facts",
        base_url="https://dog-api.kinduff.com/api/facts",
        description="Random dog facts",
        category="animals",
        rate_limit="generous",
        use_cases=["random facts", "fun content"],
    ),
    FreeApi(
        name="HTTP Cat",
        base_url="https://http.cat",
        description="Cat images for every HTTP status code",
        category="development",
        rate_limit="generous",
        use_cases=["HTTP status codes", "documentation"],
    ),
    FreeApi(
        name="HTTP Dog",
        base_url="https://http.dog",
        description="Dog images for every HTTP status code",
        category="development",
        rate_limit="generous",
        use_cases=["HTTP status codes", "documentation"],
    ),
    FreeApi(
        name="PoetryDB",
        base_url="https://poetrydb.org",
        description="Classic poetry database with 700+ poems",
        category="books",
        rate_limit="generous",
        use_cases=["poetry", "literature", "quotes"],
    ),
    FreeApi(
        name="Open Library",
        base_url="https://openlibrary.org/api",
        description="Free book database with 20M+ records",
        category="books",
        rate_limit="generous",
        use_cases=["book search", "ISBN lookup", "authors"],
    ),
    FreeApi(
        name="Gutendex",
        base_url="https://gutendex.com/books",
        description="Project Gutenberg public domain books",
        category="books",
        rate_limit="generous",
        use_cases=["free ebooks", "public domain books"],
    ),
    FreeApi(
        name="Bible API",
        base_url="https://bible-api.com",
        description="Free Bible API with multiple languages",
        category="books",
        rate_limit="generous",
        use_cases=["Bible text", "verses", "scripture"],
    ),
    FreeApi(
        name="Wizard World",
        base_url="https://wizard-world-api.herokuapp.com",
        description="Harry Potter universe data",
        category="entertainment",
        rate_limit="moderate",
        use_cases=["Harry Potter", "spells", "potions"],
    ),
    FreeApi(
        name="Jikan",
        base_url="https://api.jikan.moe/v4",
        description="Unofficial MyAnimeList API",
        category="entertainment",
        rate_limit="moderate",
        use_cases=["anime search", "manga search", "character info"],
    ),
    FreeApi(
        name="Studio Ghibli",
        base_url="https://ghibliapi.vercel.app",
        description="Studio Ghibli films data",
        category="entertainment",
        rate_limit="generous",
        use_cases=["movies", "films", "characters"],
    ),
    FreeApi(
        name="Art Institute of Chicago",
        base_url="https://api.artic.edu/api/v1",
        description="Art museum collection data",
        category="art",
        rate_limit="generous",
        use_cases=["art search", "images", "artists"],
    ),
    FreeApi(
        name="Metropolitan Museum",
        base_url="https://collectionapi.metmuseum.org/public/collection/v1",
        description="Met Museum of Art collection",
        category="art",
        rate_limit="generous",
        use_cases=["art search", "museum data"],
    ),
    FreeApi(
        name="DummyImage",
        base_url="https://dummyimage.com",
        description="Generate placeholder images",
        category="art",
        rate_limit="generous",
        use_cases=["placeholder images", "prototyping"],
    ),
    FreeApi(
        name="Icon Horse",
        base_url="https://icon.horse",
        description="Favicons for any website",
        category="art",
        rate_limit="generous",
        use_cases=["favicons", "icons"],
    ),
    FreeApi(
        name="EmojiHub",
        base_url="https://emojihub.yurace.pro/api/all",
        description="Emoji data by categories",
        category="utilities",
        rate_limit="generous",
        use_cases=["emojis", "symbols"],
    ),
    FreeApi(
        name="QR Code Generator",
        base_url="https://api.qrserver.com/v1/create-qr-code",
        description="Generate QR codes as images",
        category="utilities",
        rate_limit="generous",
        use_cases=["QR codes", "barcodes"],
    ),
    FreeApi(
        name="Open-Meteo",
        base_url="https://api.open-meteo.com/v1",
        description="Free weather API, no key needed",
        category="weather",
        rate_limit="generous",
        use_cases=["weather forecast", "temperature", "wind"],
    ),
    FreeApi(
        name="Open Zoo",
        base_url="https://zoo-animal-api.herokuapp.com/animals/rand",
        description="Random zoo animal data",
        category="animals",
        rate_limit="moderate",
        use_cases=["animal facts", "education"],
    ),
    FreeApi(
        name="Trivia DB",
        base_url="https://opentdb.com/api.php",
        description="Trivia questions database",
        category="entertainment",
        rate_limit="generous",
        use_cases=["trivia", "quiz games"],
    ),
    FreeApi(
        name="Numbers API",
        base_url="https://numbersapi.com",
        description="Interesting facts about numbers",
        category="education",
        rate_limit="generous",
        use_cases=["number facts", "math trivia"],
    ),
    FreeApi(
        name="REST Countries",
        base_url="https://restcountries.com/v3.1/all",
        description="Country data (name, capital, population, etc.)",
        category="data",
        rate_limit="generous",
        use_cases=["country info", "geography", "flags"],
    ),
    FreeApi(
        name="Flags API",
        base_url="https://flagsapi.com",
        description="Country flag images",
        category="data",
        rate_limit="generous",
        use_cases=["flag images", "country flags"],
    ),
    FreeApi(
        name="CoinGecko",
        base_url="https://api.coingecko.com/api/v3",
        description="Free cryptocurrency data",
        category="finance",
        rate_limit="moderate",
        use_cases=["crypto prices", "market data"],
    ),
    FreeApi(
        name="Faker API",
        base_url="https://fakerapi.it/api/v1",
        description="Generate fake data (names, addresses, etc.)",
        category="data",
        rate_limit="generous",
        use_cases=["test data", "prototyping", "mocking"],
    ),
    FreeApi(
        name="Open Food Facts",
        base_url="https://world.openfoodfacts.org/api/v2",
        description="Food product database",
        category="food",
        rate_limit="generous",
        use_cases=["food data", "nutrition", "barcodes"],
    ),
    FreeApi(
        name="TheMealDB",
        base_url="https://www.themealdb.com/api/json/v1/1",
        description="Meal recipes database",
        category="food",
        rate_limit="generous",
        use_cases=["recipes", "meal planning"],
    ),
    FreeApi(
        name="CocktailDB",
        base_url="https://www.thecocktaildb.com/api/json/v1/1",
        description="Cocktail recipes database",
        category="food",
        rate_limit="generous",
        use_cases=["cocktail recipes", "drink mixing"],
    ),
    FreeApi(
        name="Chuck Norris Jokes",
        base_url="https://api.chucknorris.io/jokes/random",
        description="Random Chuck Norris jokes",
        category="entertainment",
        rate_limit="generous",
        use_cases=["jokes", "fun content"],
    ),
    FreeApi(
        name="Official Joke API",
        base_url="https://official-joke-api.appspot.com/random_joke",
        description="Random jokes",
        category="entertainment",
        rate_limit="generous",
        use_cases=["jokes", "fun content"],
    ),
    FreeApi(
        name="Dad Jokes",
        base_url="https://icanhazdadjoke.com",
        description="Random dad jokes",
        category="entertainment",
        rate_limit="generous",
        use_cases=["jokes", "fun content"],
    ),
    FreeApi(
        name="Product Hunt",
        base_url="https://api.producthunt.com/v2/api/graphql",
        description="Product Hunt API (needs OAuth)",
        category="development",
        auth_required=True,
        auth_type="OAuth",
        use_cases=["product discovery", "tech trends"],
    ),
    FreeApi(
        name="Wikipedia",
        base_url="https://en.wikipedia.org/api/rest_v1",
        description="Wikipedia article data",
        category="education",
        rate_limit="generous",
        use_cases=["encyclopedia", "research", "summaries"],
    ),
    FreeApi(
        name="Wiktionary",
        base_url="https://en.wiktionary.org/api/rest_v1",
        description="Dictionary definitions",
        category="education",
        rate_limit="generous",
        use_cases=["definitions", "etymology", "translations"],
    ),
    FreeApi(
        name="Dictionary API",
        base_url="https://api.dictionaryapi.dev/api/v2/entries/en",
        description="English dictionary definitions",
        category="education",
        rate_limit="generous",
        use_cases=["definitions", "synonyms", "pronunciation"],
    ),
    FreeApi(
        name="Quotes API",
        base_url="https://dummyjson.com/quotes/random",
        description="Random quotes",
        category="utilities",
        rate_limit="generous",
        use_cases=["quotes", "inspiration"],
    ),
    FreeApi(
        name="DummyJSON",
        base_url="https://dummyjson.com",
        description="Generate fake data (users, posts, products)",
        category="data",
        rate_limit="generous",
        use_cases=["test data", "prototyping", "mocking"],
    ),
    FreeApi(
        name="JSONBin",
        base_url="https://api.jsonbin.io/v3",
        description="JSON storage service",
        category="development",
        rate_limit="generous",
        use_cases=["JSON storage", "persistent data"],
    ),
    FreeApi(
        name="ReqRes",
        base_url="https://reqres.in/api",
        description="Hosted REST API for testing",
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
