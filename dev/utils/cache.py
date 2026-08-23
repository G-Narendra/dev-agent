"""
Token Cache — Cache LLM Responses for Faster Repeated Calls

Provides caching for LLM responses to avoid redundant API calls.
"""
import os
import json
import hashlib
import time
from typing import Optional


class TokenCache:
    """
    Cache LLM responses.
    
    Features:
    1. Hash-based cache keys
    2. TTL-based expiration
    3. Persistent disk storage
    4. Size-limited cache
    """
    
    def __init__(self, project_path: str = ".", max_size: int = 1000,
                 ttl: int = 3600):
        self.project_path = os.path.abspath(project_path)
        self.cache_dir = os.path.join(self.project_path, ".dev", "cache")
        self.max_size = max_size
        self.ttl = ttl  # seconds
        self._cache = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        cache_file = os.path.join(self.cache_dir, "llm_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        os.makedirs(self.cache_dir, exist_ok=True)
        cache_file = os.path.join(self.cache_dir, "llm_cache.json")
        
        # Limit size
        if len(self._cache) > self.max_size:
            # Remove oldest entries
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1].get("time", 0))
            self._cache = dict(sorted_items[-self.max_size:])
        
        with open(cache_file, 'w') as f:
            json.dump(self._cache, f, indent=2)
    
    def _make_key(self, messages: list, model: str) -> str:
        """Generate cache key from messages and model."""
        content = json.dumps({"messages": messages, "model": model}, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, messages: list, model: str) -> Optional[dict]:
        """Get cached response."""
        key = self._make_key(messages, model)
        
        if key in self._cache:
            entry = self._cache[key]
            # Check TTL
            if time.time() - entry.get("time", 0) < self.ttl:
                return entry.get("response")
            else:
                # Expired
                del self._cache[key]
        
        return None
    
    def set(self, messages: list, model: str, response: dict):
        """Cache a response."""
        key = self._make_key(messages, model)
        self._cache[key] = {
            "response": response,
            "time": time.time(),
        }
        self._save_cache()
    
    def clear(self):
        """Clear the cache."""
        self._cache = {}
        self._save_cache()
    
    def size(self) -> int:
        """Get cache size."""
        return len(self._cache)
