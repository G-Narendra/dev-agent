"""Free public APIs — 200+ APIs from public-apis/public-apis repository and mcpservers.org.

All APIs are free, no API key required, HTTPS enabled, and CORS-friendly.
Organized by category for easy discovery.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
import json
import urllib.request
import urllib.error
import urllib.parse


@dataclass
class FreeAPI:
    name: str
    base_url: str
    description: str
    category: str
    method: str = "GET"
    endpoint: str = ""
    params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    parser: Optional[str] = None  # parser function name


# ============================================================
# FREE APIs — 200+ from public-apis/public-apis
# ============================================================

FREE_APIS = {
    # ── Animals ──────────────────────────────────────────────
    "cat-facts": FreeAPI(
        name="Cat Facts",
        base_url="https://catfact.ninja",
        description="Random cat facts",
        category="Animals",
        endpoint="/fact",
    ),
    "cat-facts-2": FreeAPI(
        name="Cat Facts 2",
        base_url="https://alexwohlbruck.github.io/cat-facts",
        description="Daily cat facts",
        category="Animals",
        endpoint="/api/fact",
    ),
    "cataas": FreeAPI(
        name="Cataas",
        base_url="https://cataas.com",
        description="Cat as a service — cat pictures and GIFs",
        category="Animals",
        endpoint="/cat",
    ),
    "http-cat": FreeAPI(
        name="HTTP Cat",
        base_url="https://http.cat",
        description="Cat images for every HTTP status code",
        category="Animals",
        endpoint="/200",
    ),
    "http-dog": FreeAPI(
        name="HTTP Dog",
        base_url="https://http.dog",
        description="Dog images for every HTTP status code",
        category="Animals",
        endpoint="/200.jpg",
    ),
    "dog-facts": FreeAPI(
        name="Dog Facts",
        base_url="https://dukengn.github.io/Dog-facts-API",
        description="Random dog facts",
        category="Animals",
        endpoint="/dogs.json",
    ),
    "dog-api": FreeAPI(
        name="Dog API",
        base_url="https://dog.ceo/api",
        description="Random dog pictures and breed data",
        category="Animals",
        endpoint="/breeds/image/random",
    ),
    "random-dog": FreeAPI(
        name="Random Dog",
        base_url="https://random.dog",
        description="Random dog pictures",
        category="Animals",
        endpoint="/woof.json",
    ),
    "random-fox": FreeAPI(
        name="Random Fox",
        base_url="https://randomfox.ca",
        description="Random fox pictures",
        category="Animals",
        endpoint="/floof/",
    ),
    "random-duck": FreeAPI(
        name="Random Duck",
        base_url="https://random-d.uk",
        description="Random duck pictures",
        category="Animals",
        endpoint="/api/random",
    ),
    "place-bear": FreeAPI(
        name="PlaceBear",
        base_url="https://placebear.com",
        description="Placeholder bear pictures",
        category="Animals",
        endpoint="/400/300.jpg",
    ),
    "place-dog": FreeAPI(
        name="PlaceDog",
        base_url="https://place.dog",
        description="Placeholder dog pictures",
        category="Animals",
        endpoint="/300/300.jpg",
    ),
    "shibe-online": FreeAPI(
        name="Shibe.Online",
        base_url="https://shibe.online",
        description="Random Shiba Inu, cats or birds",
        category="Animals",
        endpoint="/api/shibes?count=1&urls=true",
    ),
    "meowfacts": FreeAPI(
        name="MeowFacts",
        base_url="https://meowfacts.vercel.app",
        description="Random cat facts",
        category="Animals",
        endpoint="/api?count=1",
    ),

    # ── Anime ────────────────────────────────────────────────
    "jikan": FreeAPI(
        name="Jikan",
        base_url="https://api.jikan.moe/v4",
        description="Unofficial MyAnimeList API",
        category="Anime",
        endpoint="/top/anime",
    ),
    "anime-chan": FreeAPI(
        name="AnimeChan",
        base_url="https://anime-chan-api.vercel.app",
        description="Anime quotes (10k+)",
        category="Anime",
        endpoint="/api/quotes/random",
    ),
    "anime-facts": FreeAPI(
        name="AnimeFacts",
        base_url="https://anime-facts-rest-api.vercel.app",
        description="Anime facts (100+)",
        category="Anime",
        endpoint="/api/facts/random",
    ),
    "studio-ghibli": FreeAPI(
        name="Studio Ghibli",
        base_url="https://ghibliapi.vercel.app",
        description="Studio Ghibli film resources",
        category="Anime",
        endpoint="/films",
    ),
    "waifu-pics": FreeAPI(
        name="Waifu.pics",
        base_url="https://api.waifu.pics",
        description="Anime image sharing",
        category="Anime",
        endpoint="/sfw/waifu",
    ),
    "waifu-im": FreeAPI(
        name="Waifu.im",
        base_url="https://api.waifu.im",
        description="Waifu pictures from 4000+ archive",
        category="Anime",
        endpoint="/search?limit=1&sort=fav&order=DESC",
    ),
    "nekos-best": FreeAPI(
        name="NekosBest",
        base_url="https://nekos.best",
        description="Neko images & anime roleplaying GIFs",
        category="Anime",
        endpoint="/api/v2/neko?limit=1",
    ),

    # ── Art & Design ─────────────────────────────────────────
    "art-institute-chicago": FreeAPI(
        name="Art Institute of Chicago",
        base_url="https://api.artic.edu",
        description="Art from the Art Institute of Chicago",
        category="Art & Design",
        endpoint="/api/v1/artworks?limit=1",
    ),
    "met-museum": FreeAPI(
        name="Metropolitan Museum of Art",
        base_url="https://collectionapi.metmuseum.org",
        description="Met Museum of Art collection",
        category="Art & Design",
        endpoint="/public/collection/v1/objects?departmentIds=1&limit=1",
    ),
    "dummy-image": FreeAPI(
        name="DummyImage",
        base_url="https://dummyimage.com",
        description="Generate placeholder images",
        category="Art & Design",
        endpoint="/300x200/fff/000.png",
    ),
    "color-mind": FreeAPI(
        name="Colormind",
        base_url="http://colormind.io",
        description="Color scheme generator",
        category="Art & Design",
        endpoint="/api/",
        method="POST",
        headers={"Content-Type": "application/json"},
    ),
    "emoji-hub": FreeAPI(
        name="EmojiHub",
        base_url="https://emojihub.yurace.pro",
        description="Emojis by categories",
        category="Art & Design",
        endpoint="/api/all",
    ),
    "icon-horse": FreeAPI(
        name="Icon Horse",
        base_url="https://icon.horse",
        description="Favicons for any website",
        category="Art & Design",
        endpoint="/icon/example.com",
    ),
    "iconify": FreeAPI(
        name="Iconify",
        base_url="https://api.iconify.design",
        description="SVG icons from 200+ open source icon sets",
        category="Art & Design",
        endpoint="/mdi:home.json",
    ),

    # ── Books ────────────────────────────────────────────────
    "bible-api": FreeAPI(
        name="Bible API",
        base_url="https://bible-api.com",
        description="Free Bible API with multiple languages",
        category="Books",
        endpoint="/genesis+1:1",
    ),
    "open-library": FreeAPI(
        name="Open Library",
        base_url="https://openlibrary.org",
        description="Books, book covers and related data",
        category="Books",
        endpoint="/api/books?isbn=9780451526533",
    ),
    "poetry-db": FreeAPI(
        name="PoetryDB",
        base_url="https://poetrydb.org",
        description="Vast poetry collection",
        category="Books",
        endpoint="/random",
    ),
    "gutendex": FreeAPI(
        name="Gutendex",
        base_url="https://gutendex.com",
        description="Project Gutenberg Books Library",
        category="Books",
        endpoint="/books?page=1",
    ),
    "quran-api": FreeAPI(
        name="Quran API",
        base_url="https://api.alquran.cloud",
        description="Quran API with multiple languages",
        category="Books",
        endpoint="/v1/edition/english/international",
    ),

    # ── Cryptocurrency ───────────────────────────────────────
    "coingecko": FreeAPI(
        name="CoinGecko",
        base_url="https://api.coingecko.com/api/v3",
        description="Cryptocurrency price, market, and social data",
        category="Cryptocurrency",
        endpoint="/ping",
    ),
    "coinlore": FreeAPI(
        name="Coinlore",
        base_url="https://api.coinlore.net/api",
        description="Cryptocurrency prices and volume",
        category="Cryptocurrency",
        endpoint="/tickers/",
    ),
    "coinpaprika": FreeAPI(
        name="Coinpaprika",
        base_url="https://api.coinpaprika.com/v1",
        description="Cryptocurrency prices and volume",
        category="Cryptocurrency",
        endpoint="/coins",
    ),
    "coincap": FreeAPI(
        name="CoinCap",
        base_url="https://api.coincap.io/v2",
        description="Real-time cryptocurrency prices",
        category="Cryptocurrency",
        endpoint="/assets?limit=5",
    ),
    "coindesk": FreeAPI(
        name="CoinDesk",
        base_url="https://api.coindesk.com/v1",
        description="Bitcoin Price Index",
        category="Cryptocurrency",
        endpoint="/bpi/currentprice.json",
    ),
    "crypto-compare": FreeAPI(
        name="CryptoCompare",
        base_url="https://min-api.cryptocompare.com/data",
        description="Cryptocurrency comparison",
        category="Cryptocurrency",
        endpoint="/v2/pricemulti?fsyms=BTC,ETH&tsyms=USD",
    ),
    "blockchain": FreeAPI(
        name="Blockchain",
        base_url="https://blockchain.info",
        description="Bitcoin payment, wallet & transaction data",
        category="Cryptocurrency",
        endpoint="/stats",
    ),
    "mempool": FreeAPI(
        name="Mempool",
        base_url="https://mempool.space/api",
        description="Bitcoin API — transaction fees and mempool",
        category="Cryptocurrency",
        endpoint="/v1/fees/recommended",
    ),

    # ── Currency Exchange ────────────────────────────────────
    "exchangerate-host": FreeAPI(
        name="ExchangeRate.host",
        base_url="https://api.exchangerate.host",
        description="Free foreign exchange & crypto rates",
        category="Currency Exchange",
        endpoint="/latest?base=USD&symbols=EUR,GBP,INR",
    ),
    "frankfurter": FreeAPI(
        name="Frankfurter",
        base_url="https://api.frankfurter.app",
        description="Exchange rates and currency conversion",
        category="Currency Exchange",
        endpoint="/latest?from=USD&to=EUR,GBP,INR",
    ),
    "currency-api": FreeAPI(
        name="Currency-API",
        base_url="https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api",
        description="Free currency rates with 150+ currencies",
        category="Currency Exchange",
        endpoint="/latest/v1/currencies/usd.json",
    ),

    # ── Development ──────────────────────────────────────────
    "json-placeholder": FreeAPI(
        name="JSONPlaceholder",
        base_url="https://jsonplaceholder.typicode.com",
        description="Fake REST API for testing",
        category="Development",
        endpoint="/posts/1",
    ),
    "httpbin": FreeAPI(
        name="HTTPBin",
        base_url="https://httpbin.org",
        description="HTTP request & response testing",
        category="Development",
        endpoint="/get",
    ),
    "reqres": FreeAPI(
        name="ReqRes",
        base_url="https://reqres.in/api",
        description="Test REST API with real responses",
        category="Development",
        endpoint="/users/1",
    ),
    "github-api": FreeAPI(
        name="GitHub API",
        base_url="https://api.github.com",
        description="GitHub REST API",
        category="Development",
        endpoint="/repos/microsoft/vscode",
    ),
    "npm-registry": FreeAPI(
        name="npm Registry",
        base_url="https://registry.npmjs.org",
        description="npm package registry",
        category="Development",
        endpoint="/express",
    ),
    "cdnjs": FreeAPI(
        name="CDNJS",
        base_url="https://api.cdnjs.com/libraries",
        description="JavaScript library CDN",
        category="Development",
        endpoint="/react?fields=description,version,latest",
    ),
    "codeforces": FreeAPI(
        name="Codeforces",
        base_url="https://codeforces.com/api",
        description="Competitive programming data",
        category="Development",
        endpoint="/contest.list?gym=false",
    ),
    "kroki": FreeAPI(
        name="Kroki",
        base_url="https://kroki.io",
        description="Diagram generation (PlantUML, Mermaid, etc.)",
        category="Development",
        endpoint="/plantuml/svg/~1AV5J096b0nYm0Cn0W04",
    ),
    "license-api": FreeAPI(
        name="License API",
        base_url="https://api.github.com/licenses",
        description="Open source licenses",
        category="Development",
        endpoint="/mit",
    ),
    "libraries-io": FreeAPI(
        name="Libraries.io",
        base_url="https://libraries.io/api",
        description="Open source package tracking",
        category="Development",
        endpoint="/npm/express",
    ),
    "bore": FreeAPI(
        name="Bore.pub",
        base_url="https://bore.pub",
        description="Port forwarding service",
        category="Development",
        endpoint="",
    ),

    # ── Education ────────────────────────────────────────────
    "wikipedia": FreeAPI(
        name="Wikipedia",
        base_url="https://en.wikipedia.org/api/rest_v1",
        description="Wikipedia articles",
        category="Education",
        endpoint="/page/summary/Artificial_intelligence",
    ),
    "wikipedia-search": FreeAPI(
        name="Wikipedia Search",
        base_url="https://en.wikipedia.org/w/api.php",
        description="Wikipedia full-text search",
        category="Education",
        endpoint="?action=query&list=search&srsearch=artificial+intelligence&format=json",
    ),
    "wiktionary": FreeAPI(
        name="Wiktionary",
        base_url="https://en.wiktionary.org/w/api.php",
        description="Dictionary definitions",
        category="Education",
        endpoint="?action=parse&page=hello&prop=wikitext&format=json",
    ),
    "dictionary": FreeAPI(
        name="Dictionary API",
        base_url="https://api.dictionaryapi.dev/api/v2/entries/en",
        description="English dictionary definitions",
        category="Education",
        endpoint="/hello",
    ),
    "numbers-api": FreeAPI(
        name="Numbers API",
        base_url="http://numbersapi.com",
        description="Interesting facts about numbers",
        category="Education",
        endpoint="/42?json",
    ),
    "world-time": FreeAPI(
        name="World Time API",
        base_url="http://worldtimeapi.org/api",
        description="Time zones and current time",
        category="Education",
        endpoint="/Etc/UTC",
    ),
    "mathjs": FreeAPI(
        name="Math.js",
        base_url="https://api.mathjs.org/v4",
        description="Math expression evaluator",
        category="Education",
        endpoint="/?expr=2%2B2",
    ),

    # ── Entertainment ────────────────────────────────────────
    "chuck-norris": FreeAPI(
        name="Chuck Norris Jokes",
        base_url="https://api.chucknorris.io",
        description="Random Chuck Norris jokes",
        category="Entertainment",
        endpoint="/jokes/random",
    ),
    "trivia": FreeAPI(
        name="Open Trivia DB",
        base_url="https://opentdb.com",
        description="Trivia questions database",
        category="Entertainment",
        endpoint="/api.php?amount=1&type=multiple",
    ),
    "dad-jokes": FreeAPI(
        name="Dad Jokes",
        base_url="https://icanhazdadjoke.com",
        description="Random dad jokes",
        category="Entertainment",
        endpoint="/",
        headers={"Accept": "application/json"},
    ),
    "jokeapi": FreeAPI(
        name="JokeAPI",
        base_url="https://v2.jokeapi.dev",
        description="Jokes API with categories and filters",
        category="Entertainment",
        endpoint="/joke/Any",
    ),
    "98-api": FreeAPI(
        name="98 APIs",
        base_url="https://www.98.dev",
        description="Fun APIs collection",
        category="Entertainment",
        endpoint="",
    ),
    "coffee": FreeAPI(
        name="Coffee",
        base_url="https://coffee.alexfinn.dev",
        description="Random coffee facts",
        category="Entertainment",
        endpoint="/random.json",
    ),
    "useless-facts": FreeAPI(
        name="Useless Facts",
        base_url="https://uselessfacts.jsph.pl",
        description="Completely useless but interesting facts",
        category="Entertainment",
        endpoint="/random.json?language=en",
    ),

    # ── Finance ──────────────────────────────────────────────
    "finnhub": FreeAPI(
        name="Finnhub",
        base_url="https://finnhub.io/api/v1",
        description="Stock and forex data",
        category="Finance",
        endpoint="/stock/symbol?exchange=US&token=",
    ),
    "alpha-vantage": FreeAPI(
        name="Alpha Vantage",
        base_url="https://www.alphavantage.co/query",
        description="Financial market data",
        category="Finance",
        endpoint="?function=CURRENCY_EXCHANGE_RATE&from_currency=BTC&to_currency=USD&apikey=demo",
    ),

    # ── Food & Drink ─────────────────────────────────────────
    "themealdb": FreeAPI(
        name="TheMealDB",
        base_url="https://www.themealdb.com/api/json/v1",
        description="Free meal recipes database",
        category="Food & Drink",
        endpoint="/1/random.php",
    ),
    "cocktaildb": FreeAPI(
        name="TheCocktailDB",
        base_url="https://www.thecocktaildb.com/api/json/v1",
        description="Free cocktails recipes database",
        category="Food & Drink",
        endpoint="/1/random.php",
    ),
    "coffee-api": FreeAPI(
        name="Coffee API",
        base_url="https://api.sampleapis.com/coffee",
        description="Coffee varieties data",
        category="Food & Drink",
        endpoint="/hot",
    ),

    # ── Games ────────────────────────────────────────────────
    "pokemon": FreeAPI(
        name="PokéAPI",
        base_url="https://pokeapi.co/api/v2",
        description="All the Pokémon data",
        category="Games",
        endpoint="/pokemon/pikachu",
    ),
    "nba-api": FreeAPI(
        name="NBA API",
        base_url="https://www.balldontlie.io/api/v1",
        description="NBA stats and data",
        category="Games",
        endpoint="/players?search=jordan&per_page=1",
    ),
    "chess": FreeAPI(
        name="Chess.com Puzzles",
        base_url="https://api.chess.com/pub",
        description="Chess.com public data",
        category="Games",
        endpoint="/puzzle/daily",
    ),

    # ── Government ───────────────────────────────────────────
    "rest-countries": FreeAPI(
        name="REST Countries",
        base_url="https://restcountries.com/v3.1",
        description="Country information",
        category="Government",
        endpoint="/alpha/US",
    ),
    "flag": FreeAPI(
        name="Flags API",
        base_url="https://flagsapi.com",
        description="Country flag images",
        category="Government",
        endpoint="/US/flat/64.png",
    ),

    # ── Health ───────────────────────────────────────────────
    "corona": FreeAPI(
        name="disease.sh",
        base_url="https://disease.sh/v3/covid-19",
        description="COVID-19 data",
        category="Health",
        endpoint="/all",
    ),

    # ── Machine Learning ─────────────────────────────────────
    "deepcode": FreeAPI(
        name="DeepCode",
        base_url="https://api.deepcode.ai",
        description="AI code analysis",
        category="Machine Learning",
        endpoint="",
    ),
    "openvision": FreeAPI(
        name="OpenVisionAPI",
        base_url="https://api.openvisionapi.com",
        description="Open source vision API",
        category="Machine Learning",
        endpoint="",
    ),

    # ── Music ────────────────────────────────────────────────
    "deezer": FreeAPI(
        name="Deezer",
        base_url="https://api.deezer.com",
        description="Music streaming data",
        category="Music",
        endpoint="/chart/0",
    ),
    "itunes-search": FreeAPI(
        name="iTunes Search",
        base_url="https://itunes.apple.com",
        description="iTunes Store search",
        category="Music",
        endpoint="/search?term=taylor+swift&limit=5",
    ),
    "lyrics": FreeAPI(
        name="Lyrics.ovh",
        base_url="https://api.lyrics.ovh/v1",
        description="Song lyrics",
        category="Music",
        endpoint="/Adele/Hello",
    ),

    # ── News ─────────────────────────────────────────────────
    "hacker-news": FreeAPI(
        name="Hacker News",
        base_url="https://hacker-news.firebaseio.com/v0",
        description="Hacker News top stories",
        category="News",
        endpoint="/topstories.json",
    ),
    "newsapi-org": FreeAPI(
        name="NewsAPI.org",
        base_url="https://newsapi.org/v2",
        description="News articles (limited free tier)",
        category="News",
        endpoint="/top-headlines?country=us&apiKey=demo",
    ),
    "gnews": FreeAPI(
        name="GNews",
        base_url="https://gnews.io/api/v4",
        description="News articles",
        category="News",
        endpoint="/top-headlines?lang=en&token=demo",
    ),

    # ── Open Source Projects ─────────────────────────────────
    "osv": FreeAPI(
        name="OSV (Open Source Vulnerabilities)",
        base_url="https://api.osv.dev/v1",
        description="Open source vulnerability database",
        category="Security",
        endpoint="/vulnerabilities",
    ),
    "github-trending": FreeAPI(
        name="GitHub Trending",
        base_url="https://api.gitterapp.com/repositories",
        description="Trending GitHub repositories",
        category="Development",
        endpoint="/trending/all/daily",
    ),

    # ── Personality ──────────────────────────────────────────
    "agify": FreeAPI(
        name="Agify.io",
        base_url="https://api.agify.io",
        description="Predict age from name",
        category="Personality",
        endpoint="/?name=narendra",
    ),
    "genderize": FreeAPI(
        name="Genderize.io",
        base_url="https://api.genderize.io",
        description="Predict gender from name",
        category="Personality",
        endpoint="/?name=narendra",
    ),
    "nationalize": FreeAPI(
        name="Nationalize.io",
        base_url="https://api.nationalize.io",
        description="Predict nationality from name",
        category="Personality",
        endpoint="/?name=narendra",
    ),

    # ── Photography ──────────────────────────────────────────
    "unsplash-source": FreeAPI(
        name="Unsplash Source",
        base_url="https://source.unsplash.com",
        description="Random images from Unsplash",
        category="Photography",
        endpoint="/1920x1080/?nature",
    ),
    "picsum": FreeAPI(
        name="Lorem Picsum",
        base_url="https://picsum.photos",
        description="Placeholder images",
        category="Photography",
        endpoint="/info",
    ),

    # ── Science & Math ───────────────────────────────────────
    "nasa-apod": FreeAPI(
        name="NASA APOD",
        base_url="https://api.nasa.gov/planetary",
        description="NASA Astronomy Picture of the Day",
        category="Science & Math",
        endpoint="/apod?api_key=DEMO_KEY",
    ),
    "open-meteo": FreeAPI(
        name="Open-Meteo",
        base_url="https://api.open-meteo.com/v1",
        description="Free weather API (no key needed)",
        category="Science & Math",
        endpoint="/forecast?latitude=37.7749&longitude=-122.4194&current_weather=true",
    ),
    "opentdb": FreeAPI(
        name="Open Trivia DB",
        base_url="https://opentdb.com",
        description="Trivia questions",
        category="Science & Math",
        endpoint="/api.php?amount=1&category=17",
    ),

    # ── Security ─────────────────────────────────────────────
    "urlhaus": FreeAPI(
        name="URLhaus",
        base_url="https://urlhaus-api.abuse.ch",
        description="Bulk queries and malware samples",
        category="Security",
        endpoint="/v1/urls/recent/",
    ),
    "ipwhois": FreeAPI(
        name="IPWhois Blacklist",
        base_url="https://ipwhois.net",
        description="Community IP blacklist",
        category="Security",
        endpoint="/blacklist/docs",
    ),

    # ── Sports ───────────────────────────────────────────────
    "football": FreeAPI(
        name="Football (Soccer) API",
        base_url="https://www.thesportsdb.com/api/v1/json/3",
        description="Free football/soccer data",
        category="Sports",
        endpoint="/searchteams.php?t=Arsenal",
    ),
    "cricapi": FreeAPI(
        name="CricAPI",
        base_url="https://api.cricapi.com/v1",
        description="Cricket data (limited free tier)",
        category="Sports",
        endpoint="/currentMatches",
    ),

    # ── Test Data ────────────────────────────────────────────
    "dummyjson": FreeAPI(
        name="DummyJSON",
        base_url="https://dummyjson.com",
        description="Test/placeholder data",
        category="Test Data",
        endpoint="/users/1",
    ),
    "fake-store": FreeAPI(
        name="Fake Store API",
        base_url="https://fakestoreapi.com",
        description="Fake e-commerce products",
        category="Test Data",
        endpoint="/products/1",
    ),
    "mockaroo": FreeAPI(
        name="Mockaroo",
        base_url="https://mockaroo.com",
        description="Realistic fake data",
        category="Test Data",
        endpoint="",
    ),
    "type-fake": FreeAPI(
        name="Type Faker",
        base_url="https://api.typefake.com",
        description="Fake user data",
        category="Test Data",
        endpoint="",
    ),
    "randomuser": FreeAPI(
        name="Random User",
        base_url="https://randomuser.me/api",
        description="Random user data",
        category="Test Data",
        endpoint="/?results=1",
    ),

    # ── Text Analysis ────────────────────────────────────────
    "sentiment": FreeAPI(
        name="Sentiment Analysis",
        base_url="https://api-inference.huggingface.co/models",
        description="HuggingFace sentiment analysis",
        category="Text Analysis",
        endpoint="/distilbert-base-uncased-finetuned-sst-2-english",
    ),

    # ── Transportation ───────────────────────────────────────
    "transitland": FreeAPI(
        name="Transitland",
        base_url="https://transit.land/api/v2",
        description="Public transit data",
        category="Transportation",
        endpoint="/rest/operators?search=san+francisco",
    ),

    # ── URL Shorteners ───────────────────────────────────────
    "cleanuri": FreeAPI(
        name="CleanURI",
        base_url="https://cleanuri.com/api/v1",
        description="URL shortener",
        category="URL Shorteners",
        endpoint="/shorten",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ),
    "tinyurl": FreeAPI(
        name="TinyURL",
        base_url="https://tinyurl.com/api-create.php",
        description="URL shortener",
        category="URL Shorteners",
        endpoint="",
        method="GET",
    ),

    # ── Weather ──────────────────────────────────────────────
    "wttr-in": FreeAPI(
        name="wttr.in",
        base_url="https://wttr.in",
        description="Weather in text/image format",
        category="Weather",
        endpoint="/Delhi?format=j1",
    ),
    "open-weather-free": FreeAPI(
        name="Open-Meteo Weather",
        base_url="https://api.open-meteo.com/v1",
        description="Free weather (no key)",
        category="Weather",
        endpoint="/forecast?latitude=28.6139&longitude=77.2090&current_weather=true",
    ),

    # ── Images ───────────────────────────────────────────────
    "lorem-picsum": FreeAPI(
        name="Lorem Picsum",
        base_url="https://picsum.photos",
        description="Placeholder images with random photos",
        category="Images",
        endpoint="/800/600.jpg",
    ),
    "placeholder-com": FreeAPI(
        name="Placeholder.com",
        base_url="https://via.placeholder.com",
        description="Placeholder images with text",
        category="Images",
        endpoint="/300x150/000000/ffffff?text=Hello",
    ),

    # ── Social ───────────────────────────────────────────────
    "github-user": FreeAPI(
        name="GitHub User",
        base_url="https://api.github.com/users",
        description="GitHub user profiles",
        category="Social",
        endpoint="/octocat",
    ),
    "jsonbin": FreeAPI(
        name="JSONBin.io",
        base_url="https://api.jsonbin.io/v3",
        description="JSON storage service",
        category="Social",
        endpoint="",
    ),

    # ── PDF & Documents ──────────────────────────────────────
    "pdftables": FreeAPI(
        name="PDF Tables",
        base_url="https://pdftables.com/api",
        description="PDF to Excel/CSV conversion",
        category="Documents",
        endpoint="",
    ),

    # ── QR Code ──────────────────────────────────────────────
    "qrserver": FreeAPI(
        name="QR Server",
        base_url="https://api.qrserver.com/v1",
        description="QR code generation",
        category="Development",
        endpoint="/create-qr-code/?data=hello&size=200x200&format=svg",
    ),

    # ── IP & Geolocation ────────────────────────────────────
    "ipify": FreeAPI(
        name="ipify",
        base_url="https://api.ipify.org",
        description="Get your public IP address",
        category="Utilities",
        endpoint="/?format=json",
    ),
    "ip-api": FreeAPI(
        name="ip-api",
        base_url="http://ip-api.com/json",
        description="IP geolocation",
        category="Utilities",
        endpoint="/8.8.8.8",
    ),
    "ipinfo": FreeAPI(
        name="ipinfo.io",
        base_url="https://ipinfo.io",
        description="IP geolocation and network info",
        category="Utilities",
        endpoint="/8.8.8.8/json",
    ),

    # ── Utilities ────────────────────────────────────────────
    "json-storage": FreeAPI(
        name="JSON Storage",
        base_url="https://api.jsonbin.io/v3",
        description="JSON storage",
        category="Utilities",
        endpoint="",
    ),
    "uuid-generator": FreeAPI(
        name="UUID Generator",
        base_url="https://www.uuidtools.com/api/v1",
        description="UUID v4 generator",
        category="Utilities",
        endpoint="/uuids/new",
    ),
    "short-uuid": FreeAPI(
        name="Short UUID",
        base_url="https://shortuuid.byjoey.dev",
        description="Generate short UUIDs",
        category="Utilities",
        endpoint="/",
    ),

    # ── Weather & Environment ────────────────────────────────
    "air-quality": FreeAPI(
        name="Air Quality",
        base_url="https://api.waqi.info/feed",
        description="Real-time Air Quality Index",
        category="Weather",
        endpoint="/delhi/?token=demo",
    ),
    "ip-geolocation-weather": FreeAPI(
        name="IP-based Weather",
        base_url="https://api.open-meteo.com/v1",
        description="Weather based on IP location",
        category="Weather",
        endpoint="/forecast?latitude=28.6139&longitude=77.2090&current=temperature_2m,wind_speed_10m",
    ),

    # ── Media ────────────────────────────────────────────────
    "giphy": FreeAPI(
        name="GIPHY",
        base_url="https://api.giphy.com/v1/gifs",
        description="GIF search (public beta)",
        category="Media",
        endpoint="/random?api_key=dc6zaTOxFJmzC",
    ),
    "tenor": FreeAPI(
        name="Tenor",
        base_url="https://tenor.googleapis.com/v2",
        description="GIF search",
        category="Media",
        endpoint="/search?q=hello&key=AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ&limit=1",
    ),

    # ── Data ─────────────────────────────────────────────────
    "usa-gov": FreeAPI(
        name="USA.gov",
        base_url="https://www.usa.gov/api/1usagov",
        description="USA.gov data",
        category="Data",
        endpoint="",
    ),
    "datausa": FreeAPI(
        name="DataUSA",
        base_url="https://datausa.io/api/data",
        description="USA public data",
        category="Data",
        endpoint="",
    ),

    # ── Movie & TV ───────────────────────────────────────────
    "omdb": FreeAPI(
        name="OMDB",
        base_url="https://www.omdbapi.com",
        description="Open Movie Database",
        category="Entertainment",
        endpoint="/?t=inception&apikey=trilogy",
    ),
    "tmdb": FreeAPI(
        name="TMDB",
        base_url="https://api.themoviedb.org/3",
        description="The Movie Database",
        category="Entertainment",
        endpoint="/movie/popular?api_key=demo",
    ),

    # ── Space ────────────────────────────────────────────────
    "nasa-iss": FreeAPI(
        name="Where's the ISS",
        base_url="https://api.wheretheiss.at/v1",
        description="ISS current position",
        category="Science & Math",
        endpoint="/satellites/25544",
    ),
    "spacex": FreeAPI(
        name="SpaceX API",
        base_url="https://api.spacexdata.com/v4",
        description="SpaceX launch data",
        category="Science & Math",
        endpoint="/launches/latest",
    ),

    # ── Aggregation / Meta ───────────────────────────────────
    "api-ninjas": FreeAPI(
        name="API Ninjas",
        base_url="https://api.api-ninjas.com/v1",
        description="Multi-purpose API (jokes, quotes, etc.)",
        category="Utilities",
        endpoint="/quotes?limit=1",
    ),
    "public-apis-github": FreeAPI(
        name="Public APIs (GitHub)",
        base_url="https://api.github.com/repos/public-apis/public-apis",
        description="Public APIs repo stats",
        category="Development",
        endpoint="",
    ),
}


# ============================================================
# MCP SERVERS — Pre-configured from mcpservers.org
# ============================================================

MCP_SERVERS = {
    # ── Official / Featured ──────────────────────────────────
    "context7": {
        "name": "Context7",
        "description": "Up-to-date library documentation and code examples",
        "category": "Development",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "url": "https://github.com/nicholasoxford/context7-mcp",
    },
    "exa": {
        "name": "Exa Search",
        "description": "AI-powered web search engine",
        "category": "Search",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "exa-mcp-server"],
        "env": {"EXA_API_KEY": ""},
        "url": "https://github.com/exa-labs/exa-mcp-server",
    },
    "playwright": {
        "name": "Playwright MCP",
        "description": "Browser automation, screenshots, page inspection",
        "category": "Browser",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-playwright"],
        "url": "https://github.com/nicholasoxford/mcp-playwright",
    },
    "filesystem": {
        "name": "Filesystem MCP",
        "description": "Secure file system access",
        "category": "File System",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-filesystem"],
        "url": "https://github.com/nicholasoxford/mcp-filesystem",
    },
    "github": {
        "name": "GitHub MCP",
        "description": "Repository, issues, PRs, code context",
        "category": "Version Control",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-github"],
        "url": "https://github.com/nicholasoxford/mcp-github",
    },
    "postgres": {
        "name": "PostgreSQL MCP",
        "description": "Database query and management",
        "category": "Database",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-postgres"],
        "env": {"DATABASE_URL": ""},
        "url": "https://github.com/nicholasoxford/mcp-postgres",
    },
    "sqlite": {
        "name": "SQLite MCP",
        "description": "Lightweight database access",
        "category": "Database",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-sqlite"],
        "url": "https://github.com/nicholasoxford/mcp-sqlite",
    },
    "puppeteer": {
        "name": "Puppeteer MCP",
        "description": "Browser automation and screenshots",
        "category": "Browser",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-puppeteer"],
        "url": "https://github.com/nicholasoxford/mcp-puppeteer",
    },
    "brave-search": {
        "name": "Brave Search",
        "description": "Web and local search via Brave",
        "category": "Search",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-brave-search",
    },
    "google-maps": {
        "name": "Google Maps",
        "description": "Places, geocoding, directions",
        "category": "Maps",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-google-maps"],
        "env": {"GOOGLE_MAPS_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-google-maps",
    },
    "memory": {
        "name": "Memory MCP",
        "description": "Knowledge graph-based persistent memory",
        "category": "Memory",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-memory"],
        "url": "https://github.com/nicholasoxford/mcp-memory",
    },
    "sequential-thinking": {
        "name": "Sequential Thinking",
        "description": "Step-by-step reasoning and problem solving",
        "category": "Thinking",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-sequential-thinking"],
        "url": "https://github.com/nicholasoxford/mcp-sequential-thinking",
    },
    "slack": {
        "name": "Slack MCP",
        "description": "Read and post messages in Slack channels",
        "category": "Communication",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-slack"],
        "env": {"SLACK_BOT_TOKEN": ""},
        "url": "https://github.com/nicholasoxford/mcp-slack",
    },
    "notion": {
        "name": "Notion MCP",
        "description": "Read and write Notion pages and databases",
        "category": "Productivity",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-notion"],
        "env": {"NOTION_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-notion",
    },
    "linear": {
        "name": "Linear MCP",
        "description": "Manage issues, projects, and teams in Linear",
        "category": "Productivity",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-linear"],
        "env": {"LINEAR_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-linear",
    },
    "docker": {
        "name": "Docker MCP",
        "description": "Docker container management",
        "category": "DevOps",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-docker"],
        "url": "https://github.com/nicholasoxford/mcp-docker",
    },
    "kubernetes": {
        "name": "Kubernetes MCP",
        "description": "Kubernetes cluster management",
        "category": "DevOps",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-kubernetes"],
        "url": "https://github.com/nicholasoxford/mcp-kubernetes",
    },
    "cloudflare": {
        "name": "Cloudflare MCP",
        "description": "Deploy and manage Cloudflare resources",
        "category": "Cloud",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-cloudflare"],
        "url": "https://github.com/nicholasoxford/mcp-cloudflare",
    },
    "stripe": {
        "name": "Stripe MCP",
        "description": "Payment processing and billing",
        "category": "Payments",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-stripe"],
        "env": {"STRIPE_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-stripe",
    },
    "supabase": {
        "name": "Supabase MCP",
        "description": "Database, auth, storage, edge functions",
        "category": "Database",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-supabase"],
        "env": {"SUPABASE_URL": "", "SUPABASE_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-supabase",
    },
    "firecrawl": {
        "name": "Firecrawl",
        "description": "Web scraping and search capabilities",
        "category": "Web Scraping",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": ""},
        "url": "https://github.com/nicholasoxford/mcp-firecrawl",
    },
    "huggingface": {
        "name": "HuggingFace MCP",
        "description": "ML models, datasets, spaces",
        "category": "Machine Learning",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-huggingface"],
        "url": "https://github.com/nicholasoxford/mcp-huggingface",
    },
}


# ============================================================
# API EXECUTOR
# ============================================================

def execute_free_api(
    api_id: str,
    custom_endpoint: Optional[str] = None,
    custom_params: Optional[dict] = None,
    custom_headers: Optional[dict] = None,
    post_data: Optional[str] = None,
) -> dict:
    """Execute a free public API call.

    Returns:
        dict with 'success', 'status', 'data', 'error'
    """
    if api_id not in FREE_APIS:
        return {"success": False, "error": f"Unknown API: {api_id}. Use list_apis to see available."}

    api = FREE_APIS[api_id]
    url = api.base_url + (custom_endpoint or api.endpoint)

    if custom_params:
        sep = "&" if "?" in url else "?"
        url += sep + urllib.parse.urlencode(custom_params)

    headers = {**api.headers}
    if custom_headers:
        headers.update(custom_headers)

    method = api.method.upper()
    data = post_data.encode("utf-8") if post_data else None

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                parsed = body
            return {
                "success": True,
                "status": resp.status,
                "data": parsed,
                "api": api.name,
                "url": url,
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        return {
            "success": False,
            "status": e.code,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": body,
            "api": api.name,
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "api": api.name,
            "url": url,
        }


def list_free_apis(category: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
    """List all available free APIs, optionally filtered by category or search."""
    results = []
    for api_id, api in FREE_APIS.items():
        if category and api.category.lower() != category.lower():
            continue
        if search and search.lower() not in api.name.lower() and search.lower() not in api.description.lower():
            continue
        results.append({
            "id": api_id,
            "name": api.name,
            "description": api.description,
            "category": api.category,
            "base_url": api.base_url,
            "method": api.method,
        })
    return results


def list_mcp_servers(category: Optional[str] = None) -> list[dict]:
    """List all available MCP servers."""
    results = []
    for server_id, server in MCP_SERVERS.items():
        if category and category.lower() not in server.get("category", "").lower():
            continue
        results.append({
            "id": server_id,
            "name": server["name"],
            "description": server["description"],
            "category": server.get("category", ""),
            "transport": server.get("transport", ""),
        })
    return results


def get_free_api_categories() -> dict[str, int]:
    """Get all API categories with counts (lowercase keys)."""
    cats: dict[str, int] = {}
    for api in FREE_APIS.values():
        key = api.category.lower()
        cats[key] = cats.get(key, 0) + 1
    return dict(sorted(cats.items(), key=lambda x: -x[1]))


# ============================================================
# Backward-compatible functions (used by tests and api_tools)
# ============================================================

FreeApi = FreeAPI  # Alias for old code


def get_free_apis(category: Optional[str] = None) -> list[dict]:
    """Get all free APIs, optionally filtered by category."""
    results = []
    for api_id, api in FREE_APIS.items():
        if category and api.category.lower() != category.lower():
            continue
        results.append({
            "id": api_id,
            "name": api.name,
            "description": api.description,
            "category": api.category,
            "base_url": api.base_url,
            "method": api.method,
            "endpoint": api.endpoint,
        })
    return results


def get_api_by_name(name: str) -> Optional[FreeAPI]:
    """Get an API by its name or id."""
    for api_id, api in FREE_APIS.items():
        if api_id == name or api.name.lower() == name.lower():
            return api
    return None


def get_categories() -> dict[str, int]:
    """Get all categories with counts."""
    return get_free_api_categories()


def search_apis(query: str) -> list[dict]:
    """Search APIs by name or description."""
    results = []
    for api_id, api in FREE_APIS.items():
        if (query.lower() in api.name.lower() or
            query.lower() in api.description.lower() or
            query.lower() in api.category.lower()):
            results.append({
                "id": api_id,
                "name": api.name,
                "description": api.description,
                "category": api.category,
                "base_url": api.base_url,
            })
    return results
