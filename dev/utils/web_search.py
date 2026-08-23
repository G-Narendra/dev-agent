"""
Web Search — Research best practices and documentation

Provides web search and scraping for the agent.
Uses free APIs and urllib for HTTP requests.
"""
import json
import urllib.request
import urllib.parse
from typing import Optional


class WebSearch:
    """
    Search the web for information.
    
    Uses free search APIs and web scraping.
    """
    
    def __init__(self):
        self._cache = {}
    
    def search(self, query: str, num_results: int = 5) -> list[dict]:
        """
        Search the web for a query.
        
        Returns list of {title, url, snippet}
        """
        # Try DuckDuckGo Instant Answer API (free)
        results = self._search_duckduckgo(query, num_results)
        
        if not results:
            # Fallback: try Wikipedia API
            results = self._search_wikipedia(query)
        
        return results
    
    def _search_duckduckgo(self, query: str, num_results: int) -> list[dict]:
        """Search using DuckDuckGo API."""
        try:
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
            req = urllib.request.Request(url, headers={"User-Agent": "DevAgent/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
            
            results = []
            
            # Abstract
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("Abstract", "")[:500],
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "")[:500],
                    })
            
            return results[:num_results]
        except Exception:
            return []
    
    def _search_wikipedia(self, query: str) -> list[dict]:
        """Search using Wikipedia API."""
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "DevAgent/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
            
            return [{
                "title": data.get("title", query),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "snippet": data.get("extract", "")[:500],
            }]
        except Exception:
            return []
    
    def fetch_url(self, url: str, max_chars: int = 10000) -> str:
        """
        Fetch content from a URL.
        
        Returns text content (simplified).
        """
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DevAgent/1.0"})
            
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode('utf-8', errors='replace')
            
            # Simple HTML to text conversion
            text = self._html_to_text(content)
            
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... [truncated]"
            
            return text
        except Exception as e:
            return f"Error fetching URL: {e}"
    
    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion."""
        import re
        
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        
        # Remove tags
        html = re.sub(r'<[^>]+>', ' ', html)
        
        # Clean up whitespace
        html = re.sub(r'\s+', ' ', html).strip()
        
        return html
    
    def search_code_examples(self, query: str) -> list[dict]:
        """Search for code examples."""
        results = self.search(f"{query} code example", num_results=3)
        
        # Also search Stack Overflow
        so_results = self._search_stackoverflow(query)
        
        return results + so_results
    
    def _search_stackoverflow(self, query: str) -> list[dict]:
        """Search Stack Overflow."""
        try:
            url = f"https://api.stackexchange.com/2.3/search?order=desc&sort=relevance&intitle={urllib.parse.quote(query)}&site=stackoverflow"
            req = urllib.request.Request(url, headers={"User-Agent": "DevAgent/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())
            
            results = []
            for item in data.get("items", [])[:3]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": f"Score: {item.get('score', 0)} | Answers: {item.get('answer_count', 0)}",
                })
            
            return results
        except Exception:
            return []
