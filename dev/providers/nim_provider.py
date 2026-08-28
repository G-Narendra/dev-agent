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
    
    # Available models on NVIDIA NIMs free tier (verified working 2026-08-27)
    # Llama 3.1 models are DEAD (HTTP 410 Gone) — use Nemotron 3.x instead
    MODELS = {
        "coding": "nvidia/nemotron-3-super-120b-a12b",
        "reasoning": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "fast": "nvidia/nemotron-3-nano-30b-a3b",
        "vision": "meta/llama-3.2-11b-vision-instruct",
        "default": "nvidia/nemotron-3-super-120b-a12b",
        "tool": "nvidia/nemotron-3-super-120b-a12b",
    }
    
    # Models that support reliable tool calling
    TOOL_CAPABLE_MODELS = {
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "meta/llama-3.2-11b-vision-instruct",
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
        # Cached tool definitions (avoid re-serializing each call)
        self._tool_cache: list[dict] = []
        # Connection pool stats
        self._pool_stats = {"reused": 0, "new": 0}
        # Model health tracking
        self._model_health: dict[str, dict] = {}  # model -> {success, failure, latency_avg}
        self._model_failures: dict[str, int] = {}  # model -> consecutive failures
        self._verbose = False
    
    def _log(self, msg: str):
        """Log a message if verbose mode is on."""
        if self._verbose:
            try:
                import sys
                print(f"[nim] {msg}", file=sys.stderr)
            except Exception:
                pass  # Intentional: non-critical: best-effort operation
    
    @staticmethod
    def _recover_truncated_json(text: str) -> dict | None:
        """Attempt to recover a truncated JSON object by closing open brackets.
        
        Nemotron sometimes truncates long tool call arguments mid-string.
        This tries to produce a usable partial result.
        """
        if not text or not text.strip().startswith('{'):
            return None
        
        text = text.strip()
        
        # First: try parsing as-is (might already be valid)
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Try progressively: close any open string, close any open object/array
        attempts = [
            text + '"}',           # Close string + object
            text + '"}}',          # Close nested object + object
            text + '"}]',         # Close nested object + array
            text + '"}]}}',       # Deep nesting
            text + '"}}}',         # Deep nesting variant
        ]
        
        for attempt in attempts:
            try:
                result = json.loads(attempt)
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                continue
        
        return None
    
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
            # http2=True,  # Enable if h2 package is installed: pip install httpx[http2]
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
            # Reset per-minute counter if 60s have passed since first request
            if key.last_request_time > 0 and (now - key.last_request_time) > 60:
                key.requests_this_minute = 0
            
            # Reset exhausted state if cooldown has passed
            if key.is_exhausted and now > key.exhausted_until:
                key.is_exhausted = False
                key.requests_this_minute = 0
            
            if not key.is_exhausted and key.requests_this_minute < self.config.rpm:
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
        
        # Sanitize tool definitions to minimize NIM token usage
        tools = kwargs.pop("tools", None)
        if tools:
            tools = self._sanitize_tools_for_nim(tools)
        
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
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
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
            
            # Track usage
            usage = result.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            self._record_request(key, tokens)
            
            # Detect and handle truncated tool calls in non-streaming response
            choice = result.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                valid_tcs = []
                for tc in tool_calls:
                    args_str = tc.get("function", {}).get("arguments", "")
                    try:
                        parsed = json.loads(args_str) if args_str else {}
                        if isinstance(parsed, dict):
                            valid_tcs.append(tc)
                    except (json.JSONDecodeError, TypeError):
                        # Truncated args — try to recover partial JSON
                        self._log(f"Truncated tool call args ({len(args_str)} chars), attempting recovery")
                        recovered = self._recover_truncated_json(args_str)
                        if recovered:
                            tc["function"]["arguments"] = json.dumps(recovered)
                            valid_tcs.append(tc)
                        # else: skip this broken tool call
                message["tool_calls"] = valid_tcs
            
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
    
    def _sanitize_tools_for_nim(self, tools: list[dict]) -> list[dict]:
        """Sanitize tool definitions to minimize token usage for NIM.
        
        Nemotron models truncate tool args aggressively. This method:
        - Truncates descriptions to 80 chars
        - Removes verbose property descriptions
        - Strips defaults, examples, and unnecessary fields
        - Removes 'additionalProperties' and 'enum' arrays where possible
        """
        if not tools:
            return tools
        sanitized = []
        for tool in tools:
            t = dict(tool)
            if "function" in t:
                func = dict(t["function"])
                # Truncate function description
                if "description" in func and len(func["description"]) > 80:
                    func["description"] = func["description"][:77] + "..."
                # Clean parameters
                if "parameters" in func:
                    params = dict(func["parameters"])
                    props = params.get("properties", {})
                    clean_props = {}
                    for pname, pval in props.items():
                        if isinstance(pval, dict):
                            # Keep only type and description (shortened)
                            clean = {"type": pval.get("type", "string")}
                            if "description" in pval:
                                desc = pval["description"]
                                if len(desc) > 60:
                                    desc = desc[:57] + "..."
                                clean["description"] = desc
                            # Keep 'required' in nested objects
                            if "items" in pval:
                                clean["items"] = {"type": pval["items"].get("type", "string")}
                            clean_props[pname] = clean
                        else:
                            clean_props[pname] = pval
                    params["properties"] = clean_props
                    # Remove additionalProperties (saves tokens)
                    params.pop("additionalProperties", None)
                    func["parameters"] = params
                t["function"] = func
            sanitized.append(t)
        return sanitized

    def _resolve_model(self, model: str, has_tools: bool = False) -> str:
        """Resolve model name, forcing tool-capable model when tools are needed."""
        resolved = self.MODELS.get(model, model)
        if has_tools and resolved not in self.TOOL_CAPABLE_MODELS:
            resolved = self.MODELS["tool"]
        return resolved
    
    def _record_model_success(self, model: str, latency: float = 0.0):
        """Record successful model call for health tracking."""
        if model not in self._model_health:
            self._model_health[model] = {"success": 0, "failure": 0, "latency_avg": 0.0}
        health = self._model_health[model]
        health["success"] += 1
        # Exponential moving average for latency
        if latency > 0:
            health["latency_avg"] = health["latency_avg"] * 0.9 + latency * 0.1
        self._model_failures[model] = 0  # Reset consecutive failures
    
    def _record_model_failure(self, model: str):
        """Record failed model call for health tracking."""
        if model not in self._model_health:
            self._model_health[model] = {"success": 0, "failure": 0, "latency_avg": 0.0}
        self._model_health[model]["failure"] += 1
        self._model_failures[model] = self._model_failures.get(model, 0) + 1
    
    def _is_model_healthy(self, model: str) -> bool:
        """Check if a model is healthy enough to use."""
        failures = self._model_failures.get(model, 0)
        if failures >= 3:
            return False  # 3+ consecutive failures = unhealthy
        return True
    
    def _get_fallback_model(self, model: str) -> str:
        """Get a fallback model when the primary is unhealthy.
        
        Fallback chain:
          120B super -> 30B nano -> 120B super (alternate)
        """
        if "120b" in model:
            return self.MODELS["fast"]  # Try 30B nano
        elif "30b" in model:
            return self.MODELS["default"]  # Try 120B super
        elif "vision" in model:
            return self.MODELS["default"]  # Vision -> coding
        return self.MODELS["default"]
    
    def get_model_health(self) -> dict:
        """Get health status of all models."""
        return {
            model: {
                **health,
                "consecutive_failures": self._model_failures.get(model, 0),
                "healthy": self._is_model_healthy(model),
            }
            for model, health in self._model_health.items()
        }
    
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
        """Call LLM with retry, fallback model, and exponential backoff."""
        import random
        
        current_model = model
        for attempt in range(max_retries):
            try:
                result = await self.chat_completion(
                    messages=messages,
                    model=current_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
                self._record_model_success(current_model)
                return result
            except Exception as e:
                self._record_model_failure(current_model)
                self._log(f"Call failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                # On second failure, try fallback model
                if attempt == 1 and self._is_model_healthy(current_model) is False:
                    current_model = self._get_fallback_model(current_model)
                    self._log(f"Switching to fallback model: {current_model}")
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
            # Sanitize tool definitions to minimize NIM token usage
            tools = self._sanitize_tools_for_nim(tools)
        
        # Try streaming with tools first (token-by-token display)
        # Falls back to non-streaming if streaming fails
        if tools:
            try:
                async for event in self._stream_with_tools(
                    messages, resolved_model, temperature, max_tokens, tools, key, **kwargs
                ):
                    yield event
                return
            except Exception as e:
                self._log(f"Streaming with tools failed: {e}, falling back to non-streaming")
            # Fallback: non-streaming with tools
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
                
                # Detect truncation: ONLY for truly broken tool calls
                truncated = False
                has_valid_tool_calls = False
                for tc in tool_calls:
                    args = tc.get("function", {}).get("arguments", "")
                    name = tc.get("function", {}).get("name", "")
                    # Only mark truncated if args are empty or not valid JSON at all
                    try:
                        parsed = json.loads(args) if args else {}
                        if isinstance(parsed, dict):
                            has_valid_tool_calls = True
                    except (json.JSONDecodeError, TypeError):
                        # Invalid JSON in args = likely truncated
                        truncated = True
                        break
                
                if truncated and content and not has_valid_tool_calls:
                    # Model truncated tool calls — use text output for code blocks
                    # Log the truncation for debugging
                    self._log(f"Tool call truncated — using text output ({len(content)} chars)")
                    # Yield text content (production loop will parse code blocks)
                    yield {"type": "text", "content": content}
                    # Also yield any valid tool calls that weren't truncated
                    for tc in tool_calls:
                        try:
                            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            if isinstance(args, dict) and len(json.dumps(args)) > 20:
                                yield {"type": "tool_call", "tool_call": tc}
                        except Exception:
                            pass  # Intentional: non-critical: best-effort operation
                    yield {"type": "finish", "reason": "truncation_recovery"}
                    return
                elif truncated and not content:
                    # Truncated with no content — retry without tools with bigger max_tokens
                    self._log("Truncated with no content — retrying without tools")
                    try:
                        retry_result = await self.chat_completion(
                            messages=messages,
                            model="default",
                            temperature=temperature,
                            max_tokens=min(max_tokens * 4, 16384),  # 4x the original to avoid re-truncation
                        )
                        retry_choice = retry_result.get("choices", [{}])[0]
                        retry_message = retry_choice.get("message", {})
                        retry_content = retry_message.get("content", "")
                        if retry_content:
                            yield {"type": "text", "content": retry_content}
                        yield {"type": "finish", "reason": "truncation_recovery"}
                        return
                    except Exception:
                        pass  # Intentional: non-critical: best-effort operation
                
                # Nemotron recovery: extract tool calls from content string
                if not tool_calls and content:
                    from dev.agents.production_loop import ProductionAgentLoop
                    content, tool_calls = ProductionAgentLoop._extract_json_tool_calls_from_content(content)

                # If no tool calls, yield text content
                if content and not tool_calls:
                    yield {"type": "text", "content": content}
                elif content:
                    yield {"type": "text", "content": content}
                for tc in tool_calls:
                    yield {"type": "tool_call", "tool_call": tc}
                yield {"type": "finish", "reason": finish_reason}
                return
            except Exception:
                pass  # Fall through to streaming without tools
        
        # Fallback: streaming call without tools (token-by-token SSE)
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
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        
                        # Usage
                        usage = chunk.get("usage")
                        if usage:
                            self._record_request(key, usage.get("total_tokens", 0))
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
                            yield {"type": "text", "content": content}
                        
                        # Tool call deltas (some models support this)
                        if "tool_calls" in delta:
                            for tc_delta in delta["tool_calls"]:
                                yield {"type": "tool_call", "tool_call": tc_delta}
                        
                        # Finish
                        if finish_reason:
                            yield {"type": "finish", "reason": finish_reason}
                except (httpx.ReadError, httpx.RemoteProtocolError) as e:
                    self._log(f"Stream interrupted: {e}")
                
                self._record_request(key)
                
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, httpx.PoolTimeout) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                key.is_exhausted = True
                key.exhausted_until = time.time() + self.config.cooldown_seconds
                # Retry with a different key after cooldown
                await asyncio.sleep(1.0)
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
        accumulated_text = ""  # Buffer for Nemotron recovery
        
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
                    accumulated_text += content
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
            
            # Nemotron recovery: if no tool calls but accumulated text has JSON tool calls
            if not has_tool_calls and accumulated_text and tools:
                from dev.agents.production_loop import ProductionAgentLoop
                remaining, extracted = ProductionAgentLoop._extract_json_tool_calls_from_content(accumulated_text)
                if extracted:
                    self._log(f"Streaming Nemotron recovery: extracted {len(extracted)} tool call(s) from text")
                    for tc in extracted:
                        yield {"type": "tool_call", "tool_call": tc}
                    has_tool_calls = True
            
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
