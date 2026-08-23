"""
NVIDIA NIMs API Provider with multi-key rotation and rate limiting.

Adapted from Freebuff's model-provider pattern and Aider's litellm integration,
but using direct OpenAI-compatible API calls to NVIDIA NIMs.
"""

import asyncio
import time
import os
import json
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator
from collections import deque

import httpx
from pydantic import BaseModel


class NimKey(BaseModel):
    """A single NVIDIA NIM API key with its own rate limit state."""
    key: str
    name: str = ""
    requests_this_minute: int = 0
    last_request_time: float = 0
    total_requests: int = 0
    total_tokens: int = 0
    is_exhausted: bool = False
    exhausted_until: float = 0


@dataclass
class RateLimitConfig:
    """Rate limit configuration per key."""
    rpm: int = 40  # Requests per minute
    tpm: int = 400_000  # Tokens per minute (estimated)
    burst: int = 5  # Max burst requests
    cooldown_seconds: float = 60  # Cooldown when exhausted


class NimProvider:
    """
    NVIDIA NIMs API provider with intelligent multi-key rotation.
    
    Rotates across multiple API keys to maximize throughput within
    rate limits. Uses token bucket algorithm per key.
    
    Adapted from:
    - Freebuff's model-provider.ts (provider routing)
    - Aider's litellm integration (OpenAI-compatible API)
    """
    
    BASE_URL = "https://integrate.api.nvidia.com/v1"
    
    # Available models on NVIDIA NIMs free tier (verified working)
    MODELS = {
        "coding": "meta/llama-3.1-70b-instruct",
        "reasoning": "meta/llama-3.1-70b-instruct",
        "fast": "meta/llama-3.1-8b-instruct",
        "vision": "meta/llama-3.2-11b-vision-instruct",
        "default": "meta/llama-3.1-70b-instruct",
        "tool": "meta/llama-3.1-70b-instruct",  # Always use 70B for tool calls
    }
    
    # Models that support reliable tool calling
    TOOL_CAPABLE_MODELS = {
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct",
    }
    
    def __init__(
        self,
        keys: list[str],
        config: Optional[RateLimitConfig] = None,
    ):
        self.config = config or RateLimitConfig()
        self.keys = [
            NimKey(key=k, name=f"key-{i}")
            for i, k in enumerate(keys)
        ]
        self._client: Optional[httpx.AsyncClient] = None
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize the HTTP client with generous pool limits."""
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Content-Type": "application/json"},
            timeout=120.0,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
        )
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    def _get_available_key(self) -> Optional[NimKey]:
        """Get the next available key using round-robin with rate limit awareness."""
        now = time.time()
        
        for key in self.keys:
            # Reset exhausted state if cooldown has passed
            if key.is_exhausted and now > key.exhausted_until:
                key.is_exhausted = False
                key.requests_this_minute = 0
            
            if not key.is_exhausted:
                # Check if we can make a request this minute
                if key.requests_this_minute < self.config.rpm:
                    return key
        
        return None
    
    async def _wait_for_available_key(self, timeout: float = 60.0) -> NimKey:
        """Wait until a key becomes available, with a global timeout.
        
        Raises TimeoutError if no key becomes available within `timeout` seconds.
        """
        deadline = time.time() + timeout
        while True:
            key = self._get_available_key()
            if key:
                return key
            
            if time.time() >= deadline:
                exhausted_count = sum(1 for k in self.keys if k.is_exhausted)
                raise TimeoutError(
                    f"All {len(self.keys)} API keys exhausted for {timeout}s. "
                    f"{exhausted_count}/{len(self.keys)} keys rate-limited. "
                    f"Wait and try again."
                )
            
            # Calculate shortest wait time
            now = time.time()
            min_wait = float('inf')
            for k in self.keys:
                if k.is_exhausted:
                    wait = k.exhausted_until - now
                    min_wait = min(min_wait, wait)
                else:
                    # Wait until next minute resets
                    min_wait = min(min_wait, 1.0)
            
            await asyncio.sleep(min(min_wait + 0.1, 5.0))
    
    def _record_request(self, key: NimKey, tokens_used: int = 0):
        """Record a request against a key."""
        now = time.time()
        
        # Reset counter if more than a minute has passed
        if now - key.last_request_time > 60:
            key.requests_this_minute = 0
        
        key.requests_this_minute += 1
        key.last_request_time = now
        key.total_requests += 1
        key.total_tokens += tokens_used
        
        # Mark as exhausted if at limit
        if key.requests_this_minute >= self.config.rpm:
            key.is_exhausted = True
            key.exhausted_until = now + self.config.cooldown_seconds
    
    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request using the best available key.
        
        Returns the raw API response dict.
        """
        if not self._client:
            await self.initialize()
        
        resolved_model = self.MODELS.get(model, model)
        key = await self._wait_for_available_key()
        
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        
        headers = {
            "Authorization": f"Bearer {key.key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
            
            # Track usage
            usage = result.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            self._record_request(key, tokens)
            
            return result
            
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, httpx.PoolTimeout) as e:
            if hasattr(e, 'request') and 'Authorization' in e.request.headers:
                e.request.headers['Authorization'] = 'Bearer ***'
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                # Rate limited - respect Retry-After header
                retry_after = int(e.response.headers.get("Retry-After", self.config.cooldown_seconds))
                key.is_exhausted = True
                key.exhausted_until = time.time() + retry_after
                raise
            raise
    
    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion response.
        
        Yields content chunks as they arrive.
        """
        if not self._client:
            await self.initialize()
        
        resolved_model = self.MODELS.get(model, model)
        key = await self._wait_for_available_key()
        
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        
        headers = {
            "Authorization": f"Bearer {key.key}",
            "Content-Type": "application/json",
        }
        
        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                
                try:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
                except (httpx.ReadError, httpx.RemoteProtocolError) as e:
                    self._log(f"Stream interrupted: {e}")
                
                self._record_request(key)
                
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, httpx.PoolTimeout) as e:
            if hasattr(e, 'request') and 'Authorization' in e.request.headers:
                e.request.headers['Authorization'] = 'Bearer ***'
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                key.is_exhausted = True
                key.exhausted_until = time.time() + self.config.cooldown_seconds
                async for chunk in self.chat_completion_stream(
                    messages, model, temperature, max_tokens, **kwargs
                ):
                    yield chunk
                return  # Success after retry — do NOT re-raise
            raise
    
    def _resolve_model(self, model: str, has_tools: bool = False) -> str:
        """Resolve model name, forcing 70B for tool calls."""
        resolved = self.MODELS.get(model, model)
        # Force 70B for tool calling to avoid truncation
        if has_tools and resolved not in self.TOOL_CAPABLE_MODELS:
            resolved = self.MODELS["tool"]
        return resolved
    
    async def _call_with_retry(
        self,
        messages: list[dict],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        max_retries: int = 3,
        **kwargs,
    ) -> dict:
        """Call LLM with retry and exponential backoff."""
        import random
        
        for attempt in range(max_retries):
            try:
                result = await self.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                # Exponential backoff with jitter
                delay = min(0.5 * (2 ** attempt) + random.uniform(0, 0.5), 30.0)
                await asyncio.sleep(delay)
        
        return {}
    
    async def chat_completion_stream_events(
        self,
        messages: list[dict],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Stream a chat completion as structured events.
        
        Yields dicts with:
        - {"type": "text", "content": "..."}  
        - {"type": "tool_call", "tool_call": {...}}
        - {"type": "usage", "usage": {...}}
        - {"type": "finish", "reason": "..."}
        
        Supports tool calling when tools are provided.
        Falls back to non-streaming if tool streaming fails.
        """
        if not self._client:
            await self.initialize()
        
        resolved_model = self.MODELS.get(model, model)
        key = await self._wait_for_available_key()
        
        # Force 70B model for tool calls to avoid truncation
        if tools:
            resolved_model = self._resolve_model(model, has_tools=True)
        
        # Use non-streaming when tools are present (more reliable with smaller models)
        # Streaming tool calls are unreliable on many NIM models
        if tools:
            payload = {
                "model": resolved_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
                **kwargs,
            }
            headers = {
                "Authorization": f"Bearer {key.key}",
                "Content-Type": "application/json",
            }
            try:
                response = await self._client.post("/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                usage = result.get("usage", {})
                if usage:
                    self._record_request(key, usage.get("total_tokens", 0))
                    yield {"type": "usage", "usage": usage}
                choice = result.get("choices", [{}])[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "stop")
                content = message.get("content") or ""
                tool_calls = message.get("tool_calls", [])
                
                # Detect truncation: if tool call arguments are too short
                truncated = False
                for tc in tool_calls:
                    args = tc.get("function", {}).get("arguments", "")
                    if len(args) < 10:  # Truncated if args < 10 chars
                        truncated = True
                        break
                
                if truncated and content:
                    # Model truncated tool calls — retry without tools
                    # Parse text output for code blocks instead
                    yield {"type": "text", "content": content}
                    yield {"type": "finish", "reason": "truncation_recovery"}
                    return
                elif truncated and not content:
                    # Truncated with no content — retry without tools
                    try:
                        # Remove tools and retry
                        retry_result = await self.chat_completion(
                            messages=messages,
                            model="default",
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        retry_choice = retry_result.get("choices", [{}])[0]
                        retry_message = retry_choice.get("message", {})
                        retry_content = retry_message.get("content", "")
                        if retry_content:
                            chunk_size = 20
                            for i in range(0, len(retry_content), chunk_size):
                                yield {"type": "text", "content": retry_content[i:i+chunk_size]}
                        yield {"type": "finish", "reason": "truncation_recovery"}
                        return
                    except Exception:
                        pass
                
                # If no tool calls, simulate streaming by chunking text
                if content and not tool_calls:
                    chunk_size = 20
                    for i in range(0, len(content), chunk_size):
                        yield {"type": "text", "content": content[i:i+chunk_size]}
                elif content:
                    yield {"type": "text", "content": content}
                for tc in tool_calls:
                    yield {"type": "tool_call", "tool_call": tc}
                yield {"type": "finish", "reason": finish_reason}
                return
            except Exception:
                pass  # Fall through to streaming without tools
        
        # Fallback: non-streaming call (works reliably)
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools
        
        headers = {
            "Authorization": f"Bearer {key.key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            
            # Track usage
            usage = result.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            self._record_request(key, tokens)
            
            # Yield usage
            if usage:
                yield {"type": "usage", "usage": usage}
            
            # Parse response
            choice = result.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")
            
            # Yield text content
            content = message.get("content", "")
            if content:
                yield {"type": "text", "content": content}
            
            # Yield tool calls
            tool_calls = message.get("tool_calls", [])
            for tc in tool_calls:
                yield {"type": "tool_call", "tool_call": tc}
            
            # Yield finish
            yield {"type": "finish", "reason": finish_reason}
            
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, httpx.PoolTimeout) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                key.is_exhausted = True
                key.exhausted_until = time.time() + self.config.cooldown_seconds
                async for event in self.chat_completion_stream_events(
                    messages, model, temperature, max_tokens, tools, **kwargs
                ):
                    yield event
            else:
                raise
    
    async def _stream_with_tools(
        self,
        messages: list[dict],
        resolved_model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict],
        key: NimKey,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Stream with tool calling support.
        
        Some NIMs models support tool calling in streaming mode.
        This method tries streaming first, falls back to non-streaming.
        """
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "tools": tools,
            **kwargs,
        }
        
        headers = {
            "Authorization": f"Bearer {key.key}",
            "Content-Type": "application/json",
        }
        
        # Track tool call deltas
        tool_call_deltas: dict[int, dict] = {}
        has_content = False
        has_tool_calls = False
        
        async with self._client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                
                data = line[6:]
                if data == "[DONE]":
                    # Flush remaining tool calls
                    for idx in sorted(tool_call_deltas.keys()):
                        tc = tool_call_deltas[idx]
                        if tc.get("function", {}).get("name"):
                            has_tool_calls = True
                            yield {"type": "tool_call", "tool_call": tc}
                    break
                
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                
                # Usage
                usage = chunk.get("usage")
                if usage:
                    yield {"type": "usage", "usage": usage}
                
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")
                
                # Text content
                content = delta.get("content", "")
                if content:
                    has_content = True
                    yield {"type": "text", "content": content}
                
                # Tool call deltas
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_call_deltas:
                            tool_call_deltas[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        tc = tool_call_deltas[idx]
                        
                        if tc_delta.get("id"):
                            tc["id"] = tc_delta["id"]
                        func = tc_delta.get("function", {})
                        if func.get("name"):
                            tc["function"]["name"] += func["name"]
                        if func.get("arguments"):
                            tc["function"]["arguments"] += func["arguments"]
                
                # Finish
                if finish_reason:
                    for idx in sorted(tool_call_deltas.keys()):
                        tc = tool_call_deltas[idx]
                        if tc.get("function", {}).get("name"):
                            has_tool_calls = True
                            yield {"type": "tool_call", "tool_call": tc}
                    tool_call_deltas.clear()
                    yield {"type": "finish", "reason": finish_reason}
            
            self._record_request(key)
            
            # If we got neither text nor tool calls, something went wrong
            if not has_content and not has_tool_calls:
                raise RuntimeError("Streaming returned no content")
    
    def get_stats(self) -> dict:
        """Get usage statistics for all keys."""
        return {
            "keys": [
                {
                    "name": k.name,
                    "requests_this_minute": k.requests_this_minute,
                    "total_requests": k.total_requests,
                    "total_tokens": k.total_tokens,
                    "is_exhausted": k.is_exhausted,
                }
                for k in self.keys
            ],
            "total_requests": sum(k.total_requests for k in self.keys),
            "total_tokens": sum(k.total_tokens for k in self.keys),
        }
