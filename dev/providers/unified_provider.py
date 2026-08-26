"""
Unified Multi-Provider System — Bytez + NVIDIA NIM + OpenRouter

All three providers use OpenAI-compatible API format.
This provider chains them with intelligent routing and fallback.

Provider strengths:
- Bytez: 175K+ models, $0/month, text/image/video/audio
- NVIDIA NIM: 80+ top models, fastest inference, 40 RPM free
- OpenRouter: 28+ free models, DeepSeek R1, Qwen3 Coder 480B
"""

from __future__ import annotations

import asyncio
import time
import os
import json
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator, Callable
from collections import deque

import httpx
from pydantic import BaseModel


# ============================================================================
# Provider Configurations
# ============================================================================

PROVIDER_CONFIGS = {
    "nvidia": {
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "env_key": "NVIDIA_API_KEY",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "rpm": 40,
        "tpm": 400_000,
        "strengths": ["speed", "fast inference", "40 RPM", "tool calling"],
        "best_models": {
            "coding": "nvidia/nemotron-3-super-120b-a12b",
            "fast": "nvidia/nemotron-3-nano-30b-a3b",
            "reasoning": "nvidia/nemotron-3-super-120b-a12b",
            "vision": "meta/llama-3.2-11b-vision-instruct",
            "default": "nvidia/nemotron-3-super-120b-a12b",
            "tool": "nvidia/nemotron-3-super-120b-a12b",
        },
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "rpm": 20,
        "tpm": 200_000,
        "strengths": ["550B model", "1M context", "best free coding"],
        "best_models": {
            "coding": "poolside/laguna-s-2.1:free",
            "fast": "cohere/north-mini-code:free",
            "reasoning": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "vision": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "default": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "tool": "cohere/north-mini-code:free",
        },
    },
    "bytez": {
        "name": "Bytez",
        "base_url": "https://api.bytez.com/models/v2/openai/v1",
        "env_key": "BYTEZ_API_KEY",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "rpm": 60,
        "tpm": 200_000,
        "strengths": ["scale", "175K+ models"],
        "best_models": {
            "coding": "Qwen/Qwen3-Coder-32B-Instruct",
            "fast": "Qwen/Qwen3-4B",
            "reasoning": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
            "vision": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "default": "meta-llama/Llama-3.3-70B-Instruct",
            "tool": "meta-llama/Llama-3.3-70B-Instruct",
        },
    },
}


# ============================================================================
# Per-Key Rate Limit State
# ============================================================================

class ProviderKey(BaseModel):
    """A single API key for any provider with its own rate limit state."""
    provider: str  # "bytez", "nvidia", "openrouter"
    key: str
    name: str = ""
    requests_this_minute: int = 0
    last_request_time: float = 0
    total_requests: int = 0
    total_tokens: int = 0
    is_exhausted: bool = False
    exhausted_until: float = 0


# ============================================================================
# Unified Provider
# ============================================================================

class UnifiedProvider:
    """
    Multi-provider LLM API with intelligent routing and fallback.
    
    Chains Bytez + NVIDIA NIM + OpenRouter with:
    - Automatic key rotation across all providers
    - Model-aware routing (coding tasks → best coding model)
    - Health tracking and auto-fallback
    - Rate limit management per key
    - Graceful degradation when providers are exhausted
    """
    
    def __init__(
        self,
        keys: dict[str, list[str]] | None = None,  # {"bytez": [...], "nvidia": [...], "openrouter": [...]}
        provider_order: list[str] | None = None,  # Priority order
    ):
        """
        Args:
            keys: Dict mapping provider name to list of API keys.
                  Example: {"nvidia": ["key1"], "openrouter": ["sk-or-..."]}
            provider_order: Priority order for provider selection.
                          Default: ["nvidia", "openrouter", "bytez"]
        """
        self.provider_order = provider_order or ["nvidia", "openrouter", "bytez"]
        
        # Build flat key list from dict
        self.keys: list[ProviderKey] = []
        if keys:
            for provider_name in self.provider_order:
                if provider_name in keys:
                    for i, key in enumerate(keys[provider_name]):
                        self.keys.append(ProviderKey(
                            provider=provider_name,
                            key=key,
                            name=f"{provider_name}-{i}",
                        ))
        
        # Rate limit config per provider
        self._rate_configs: dict[str, dict] = {}
        for pname, pconfig in PROVIDER_CONFIGS.items():
            self._rate_configs[pname] = {
                "rpm": pconfig["rpm"],
                "tpm": pconfig["tpm"],
                "cooldown_seconds": 60.0,
            }
        
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        
        # Model routing preferences
        self._model_overrides: dict[str, str] = {}  # task_type -> provider/model
        
        # Health tracking
        self._provider_health: dict[str, dict] = {}
        self._provider_failures: dict[str, int] = {}
        
        # Stats
        self._total_requests = 0
        self._total_tokens = 0
        self._provider_usage: dict[str, int] = {p: 0 for p in self.provider_order}
        
        self._verbose = False
    
    def _log(self, msg: str):
        if self._verbose:
            try:
                import sys
                print(f"[unified] {msg}", file=sys.stderr)
            except Exception:
                pass
    
    async def initialize(self):
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=120.0,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
        )
    
    async def close(self):
        if self._client:
            await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # -----------------------------------------------------------------------
    # Key Management
    # -----------------------------------------------------------------------
    
    def _get_available_key(self, provider: str | None = None) -> Optional[ProviderKey]:
        """Get next available key, optionally filtered by provider."""
        now = time.time()
        
        for key in self.keys:
            if provider and key.provider != provider:
                continue
            
            # Reset exhausted state if cooldown passed
            if key.is_exhausted and now > key.exhausted_until:
                key.is_exhausted = False
                key.requests_this_minute = 0
            
            if not key.is_exhausted:
                rate_config = self._rate_configs.get(key.provider, {})
                rpm = rate_config.get("rpm", 40)
                
                # Reset counter if more than a minute passed
                if now - key.last_request_time > 60:
                    key.requests_this_minute = 0
                
                if key.requests_this_minute < rpm:
                    return key
        
        return None
    
    async def _wait_for_key(
        self,
        provider: str | None = None,
        timeout: float = 30.0,
        patient: bool = False,
    ) -> ProviderKey:
        """Wait for an available key with timeout.

        patient=True: when all keys are exhausted, wait for the nearest
        RPM-window reset (up to 90s) instead of raising immediately.
        Daily-limit keys (exhausted_until > 3600s) are never waited for.
        """
        deadline = time.time() + timeout

        while True:
            key = self._get_available_key(provider)
            if key:
                return key

            if time.time() >= deadline:
                # Patient mode: if the earliest RPM reset is imminent, wait for it
                if patient:
                    earliest = self._earliest_rpm_reset(provider)
                    if earliest is not None and earliest <= 90:
                        self._log(f"Patient wait: sleeping {earliest:.0f}s for RPM window reset")
                        await asyncio.sleep(earliest + 1.0)
                        # Re-check after sleeping
                        key = self._get_available_key(provider)
                        if key:
                            return key

                exhausted = sum(1 for k in self.keys if k.is_exhausted)
                raise TimeoutError(
                    f"All API keys exhausted for {timeout}s "
                    f"({exhausted}/{len(self.keys)} rate-limited)"
                )

            await asyncio.sleep(min(1.0, deadline - time.time()))

    def _earliest_rpm_reset(self, provider: str | None = None) -> float | None:
        """Return seconds until the earliest non-daily RPM reset, or None."""
        now = time.time()
        earliest = None
        for k in self.keys:
            if provider and k.provider != provider:
                continue
            if k.is_exhausted and k.exhausted_until > now:
                wait = k.exhausted_until - now
                if wait <= 120:  # RPM resets within 2 minutes — worth waiting
                    if earliest is None or wait < earliest:
                        earliest = wait
        return earliest
    
    def _record_request(self, key: ProviderKey, tokens: int = 0):
        """Record a request against a key."""
        now = time.time()
        
        if now - key.last_request_time > 60:
            key.requests_this_minute = 0
        
        key.requests_this_minute += 1
        key.last_request_time = now
        key.total_requests += 1
        key.total_tokens += tokens
        self._total_requests += 1
        self._total_tokens += tokens
        self._provider_usage[key.provider] = self._provider_usage.get(key.provider, 0) + 1
        
        rate_config = self._rate_configs.get(key.provider, {})
        if key.requests_this_minute >= rate_config.get("rpm", 40):
            key.is_exhausted = True
            key.exhausted_until = now + rate_config.get("cooldown_seconds", 60)
    
    # -----------------------------------------------------------------------
    # Model Routing
    # -----------------------------------------------------------------------
    
    def resolve_model(
        self,
        task_type: str = "default",
        preferred_provider: str | None = None,
        has_tools: bool = False,
    ) -> tuple[str, str]:
        """
        Resolve the best model for a task type.
        
        Returns: (provider_name, model_id)
        """
        # Check overrides first
        if task_type in self._model_overrides:
            override = self._model_overrides[task_type]
            if "/" in override:
                provider, model = override.split("/", 1)
                return provider, model
        
        # Try each provider in priority order
        for provider_name in self.provider_order:
            if preferred_provider and provider_name != preferred_provider:
                continue
            
            config = PROVIDER_CONFIGS.get(provider_name, {})
            models = config.get("best_models", {})
            
            model = models.get(task_type) or models.get("default")
            if model:
                return provider_name, model
        
        # Fallback to first provider's default
        first_provider = self.provider_order[0]
        config = PROVIDER_CONFIGS.get(first_provider, {})
        model = config.get("best_models", {}).get("default", "meta/llama-3.1-70b-instruct")
        return first_provider, model
    
    def set_model_override(self, task_type: str, provider_model: str):
        """Override the model for a task type. Format: 'provider/model'."""
        self._model_overrides[task_type] = provider_model
    
    # -----------------------------------------------------------------------
    # Health Tracking
    # -----------------------------------------------------------------------
    
    def _record_provider_success(self, provider: str, latency: float = 0.0):
        if provider not in self._provider_health:
            self._provider_health[provider] = {"success": 0, "failure": 0, "latency_avg": 0.0}
        self._provider_health[provider]["success"] += 1
        if latency > 0:
            h = self._provider_health[provider]
            h["latency_avg"] = h["latency_avg"] * 0.9 + latency * 0.1
        self._provider_failures[provider] = 0
    
    def _record_provider_failure(self, provider: str):
        if provider not in self._provider_health:
            self._provider_health[provider] = {"success": 0, "failure": 0, "latency_avg": 0.0}
        self._provider_health[provider]["failure"] += 1
        self._provider_failures[provider] = self._provider_failures.get(provider, 0) + 1
    
    def _is_provider_healthy(self, provider: str) -> bool:
        return self._provider_failures.get(provider, 0) < 3
    
    def _get_fallback_provider(self, current: str) -> str | None:
        """Get next healthy provider in the chain."""
        idx = self.provider_order.index(current) if current in self.provider_order else -1
        for i in range(idx + 1, len(self.provider_order)):
            p = self.provider_order[i]
            if self._is_provider_healthy(p):
                return p
        # Wrap around
        for i in range(0, idx):
            p = self.provider_order[i]
            if self._is_provider_healthy(p):
                return p
        return None
    
    # -----------------------------------------------------------------------
    # Chat Completion (Non-Streaming)
    # -----------------------------------------------------------------------
    
    async def chat_completion(
        self,
        messages: list[dict],
        task_type: str = "default",
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        stream: bool = False,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request with intelligent provider routing.
        
        Automatically selects the best provider and model for the task type.
        Falls back to other providers on failure.
        """
        if not self._client:
            await self.initialize()
        
        user_specified_model = model is not None
        if not model:
            provider_name, model = self.resolve_model(task_type, has_tools=bool(tools))
        else:
            # User specified a model — detect which provider it belongs to
            provider_name = None
            for pname in self.provider_order:
                if model.startswith(pname + "/") or model in PROVIDER_CONFIGS.get(pname, {}).get("best_models", {}).values():
                    provider_name = pname
                    break
            if not provider_name:
                provider_name = self.provider_order[0] if self.provider_order else 'nvidia'
        
        # Try each provider in order
        providers_to_try = [provider_name]
        fallback = self._get_fallback_provider(provider_name)
        while fallback and fallback not in providers_to_try:
            providers_to_try.append(fallback)
            fallback = self._get_fallback_provider(fallback)
        
        last_error = None
        for prov in providers_to_try:
            try:
                key = await self._wait_for_key(provider=prov, timeout=3.0, patient=True)
                config = PROVIDER_CONFIGS[prov]
                
                # Resolve model for this provider (only if user didn't specify one)
                if not user_specified_model:
                    _, model = self.resolve_model(task_type, preferred_provider=prov, has_tools=bool(tools))
                # else: keep the user-specified model
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream,
                    **kwargs,
                }
                if tools:
                    payload["tools"] = tools
                
                headers = {
                    config["auth_header"]: f"{config['auth_prefix']}{key.key}",
                    "Content-Type": "application/json",
                }
                
                start = time.time()
                response = await self._client.post(
                    f"{config['base_url']}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                latency = time.time() - start
                
                response.raise_for_status()
                result = response.json()
                
                usage = result.get("usage", {})
                tokens = usage.get("total_tokens", 0)
                self._record_request(key, tokens)
                self._record_provider_success(prov, latency)
                
                self._log(f"[{prov}] {model} → {tokens} tokens in {latency:.1f}s")
                
                return result
                
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    key.is_exhausted = True
                    # Check if it's a daily limit (longer cooldown) or per-minute (short cooldown)
                    error_body = str(e.response.text)
                    if 'daily' in error_body.lower() or 'per-day' in error_body.lower():
                        key.exhausted_until = time.time() + 3600  # 1 hour for daily limits
                    else:
                        key.exhausted_until = time.time() + 60  # 1 min for per-minute limits
                    self._log(f"[{prov}] Rate limited ({e.response.status_code}), trying next provider")
                    continue
                self._record_provider_failure(prov)
                continue
            except Exception as e:
                last_error = e
                self._record_provider_failure(prov)
                self._log(f"[{prov}] Error: {e}, trying next provider")
                continue
        
        raise last_error or RuntimeError("All providers exhausted")
    
    # -----------------------------------------------------------------------
    # Streaming with Events
    # -----------------------------------------------------------------------
    
    async def chat_completion_stream_events(
        self,
        messages: list[dict],
        task_type: str = "default",
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        tools: list[dict] | None = None,
        on_text: Callable[[str], None] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Stream a chat completion as structured events.
        
        Yields:
            {"type": "text", "content": "..."}
            {"type": "tool_call", "tool_call": {...}}
            {"type": "usage", "usage": {...}}
            {"type": "finish", "reason": "..."}
        """
        if not self._client:
            await self.initialize()
        
        user_specified_model = model is not None
        if not model:
            provider_name, model = self.resolve_model(task_type, has_tools=bool(tools))
        else:
            provider_name = None
            for pname in self.provider_order:
                if model.startswith(pname + "/") or model in PROVIDER_CONFIGS.get(pname, {}).get("best_models", {}).values():
                    provider_name = pname
                    break
            if not provider_name:
                provider_name = self.provider_order[0] if self.provider_order else 'nvidia'
        
        # Try providers in order
        providers_to_try = [provider_name]
        fallback = self._get_fallback_provider(provider_name)
        while fallback and fallback not in providers_to_try:
            providers_to_try.append(fallback)
            fallback = self._get_fallback_provider(fallback)
        
        last_error = None
        for prov in providers_to_try:
            try:
                # Resolve model for this specific provider
                if not user_specified_model:
                    _, resolved = self.resolve_model(task_type, preferred_provider=prov, has_tools=bool(tools))
                else:
                    resolved = model
                async for event in self._stream_provider(
                    prov, messages, resolved, temperature, max_tokens, tools, on_text, **kwargs
                ):
                    yield event
                return  # Success
            except Exception as e:
                last_error = e
                self._record_provider_failure(prov)
                # Mark keys as exhausted on rate limit
                if '429' in str(e) or 'rate' in str(e).lower():
                    for pk in self.keys:
                        if pk.provider == prov and not pk.is_exhausted:
                            pk.is_exhausted = True
                            if 'daily' in str(e).lower():
                                pk.exhausted_until = time.time() + 3600
                            else:
                                pk.exhausted_until = time.time() + 60
                self._log(f"[{prov}] Stream failed: {e}, trying next provider")
                continue
        
        # All providers failed — try non-streaming fallback
        if tools:
            self._log("All streaming failed, trying non-streaming with tools")
            try:
                result = await self.chat_completion(
                    messages=messages,
                    task_type=task_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
                choice = result.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])
                
                if content:
                    yield {"type": "text", "content": content}
                for tc in tool_calls:
                    yield {"type": "tool_call", "tool_call": tc}
                yield {"type": "finish", "reason": choice.get("finish_reason", "stop")}
                return
            except Exception:
                pass
        
        raise last_error or RuntimeError("All providers failed")
    
    async def _stream_provider(
        self,
        provider_name: str,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None,
        on_text: Callable[[str], None] | None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """Stream from a specific provider."""
        key = await self._wait_for_key(provider=provider_name, timeout=3.0, patient=True)
        config = PROVIDER_CONFIGS[provider_name]
        
        # Use the provided model or resolve one
        resolved_model = model
        if not resolved_model:
            _, resolved_model = self.resolve_model(
                "coding" if "code" in str(messages).lower() else "default",
                preferred_provider=provider_name,
                has_tools=bool(tools),
            )
        
        # Build payload
        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if tools:
            payload["tools"] = self._sanitize_tools(tools)
        
        headers = {
            config["auth_header"]: f"{config['auth_prefix']}{key.key}",
            "Content-Type": "application/json",
        }
        
        # Add OpenRouter-specific headers
        if provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/G-Narendra/dev-agent"
            headers["X-Title"] = "Dev Agent"
        
        # Track tool call deltas (for streaming tool calls)
        tool_call_deltas: dict[int, dict] = {}
        has_content = False
        has_tool_calls = False
        
        start = time.time()
        
        async with self._client.stream(
            "POST",
            f"{config['base_url']}/chat/completions",
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
                    has_content = True
                    if on_text:
                        on_text(content)
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
                    # Flush tool calls before finish
                    for idx in sorted(tool_call_deltas.keys()):
                        tc = tool_call_deltas[idx]
                        if tc.get("function", {}).get("name"):
                            has_tool_calls = True
                            yield {"type": "tool_call", "tool_call": tc}
                    tool_call_deltas.clear()
                    
                    latency = time.time() - start
                    self._record_request(key)
                    self._record_provider_success(provider_name, latency)
                    self._log(f"[{provider_name}] Done in {latency:.1f}s")
                    
                    yield {"type": "finish", "reason": finish_reason}
                    return
        
        # If we got here, no finish_reason was received
        latency = time.time() - start
        self._record_request(key)
        self._record_provider_success(provider_name, latency)
        
        if not has_content and not has_tool_calls:
            raise RuntimeError(f"[{provider_name}] Stream returned no content")
    
    # -----------------------------------------------------------------------
    # Tool Sanitization
    # -----------------------------------------------------------------------
    
    def _sanitize_tools(self, tools: list[dict]) -> list[dict]:
        """Sanitize tool definitions to minimize token usage."""
        if not tools:
            return tools
        sanitized = []
        for tool in tools:
            t = dict(tool)
            if "function" in t:
                func = dict(t["function"])
                if "description" in func and len(func["description"]) > 100:
                    func["description"] = func["description"][:97] + "..."
                if "parameters" in func:
                    params = dict(func["parameters"])
                    props = params.get("properties", {})
                    for pname, pval in props.items():
                        if isinstance(pval, dict):
                            if pval.get("default") in (None, "", []):
                                pval = {k: v for k, v in pval.items() if k != "default"}
                            if "description" in pval and len(pval["description"]) > 80:
                                pval["description"] = pval["description"][:77] + "..."
                            props[pname] = pval
                    func["parameters"] = params
                t["function"] = func
            sanitized.append(t)
        return sanitized
    
    # -----------------------------------------------------------------------
    # Stats & Diagnostics
    # -----------------------------------------------------------------------
    
    def get_stats(self) -> dict:
        """Get comprehensive usage statistics."""
        return {
            "providers": {
                prov: {
                    "requests": self._provider_usage.get(prov, 0),
                    "health": self._provider_health.get(prov, {}),
                    "consecutive_failures": self._provider_failures.get(prov, 0),
                    "keys_available": sum(
                        1 for k in self.keys
                        if k.provider == prov and not k.is_exhausted
                    ),
                    "keys_total": sum(1 for k in self.keys if k.provider == prov),
                }
                for prov in self.provider_order
            },
            "keys": [
                {
                    "name": k.name,
                    "provider": k.provider,
                    "requests_this_minute": k.requests_this_minute,
                    "total_requests": k.total_requests,
                    "total_tokens": k.total_tokens,
                    "is_exhausted": k.is_exhausted,
                }
                for k in self.keys
            ],
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
        }
    
    def get_available_models(self) -> list[dict]:
        """List all available models across all configured providers."""
        models = []
        for prov_name in self.provider_order:
            config = PROVIDER_CONFIGS.get(prov_name, {})
            for task_type, model_id in config.get("best_models", {}).items():
                has_key = any(k.provider == prov_name for k in self.keys)
                models.append({
                    "provider": prov_name,
                    "model": model_id,
                    "task_type": task_type,
                    "has_key": has_key,
                    "strengths": config.get("strengths", []),
                })
        return models


# ============================================================================
# Backward-compatible NimProvider alias
# ============================================================================

class NimProvider(UnifiedProvider):
    """
    Backward-compatible wrapper that behaves like the old NimProvider
    but internally uses the unified multi-provider system.
    """
    
    # Keep old MODELS dict for compatibility
    MODELS = {
        "coding": "nvidia/nemotron-3-super-120b-a12b",
        "reasoning": "nvidia/nemotron-3-super-120b-a12b",
        "fast": "nvidia/nemotron-3-nano-30b-a3b",
        "vision": "meta/llama-3.2-11b-vision-instruct",
        "default": "nvidia/nemotron-3-super-120b-a12b",
        "tool": "nvidia/nemotron-3-super-120b-a12b",
    }
    
    TOOL_CAPABLE_MODELS = {
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "meta/llama-3.2-11b-vision-instruct",
    }
    
    BASE_URL = "https://integrate.api.nvidia.com/v1"
    
    def __init__(
        self,
        keys: list[str] | None = None,
        config: "RateLimitConfig" | None = None,
    ):
        """
        Initialize with NVIDIA NIM keys (backward compatible).
        
        Also checks for Bytez and OpenRouter keys in env vars.
        """
        provider_keys = {}
        
        # NVIDIA keys from constructor
        if keys:
            provider_keys["nvidia"] = keys
        
        # Auto-detect keys from environment
        bytez_key = os.environ.get("BYTEZ_API_KEY", "")
        if bytez_key:
            provider_keys["bytez"] = [bytez_key]
        
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if openrouter_key:
            provider_keys["openrouter"] = [openrouter_key]
        
        # Also check NVIDIA env var
        nvidia_env_key = os.environ.get("NVIDIA_API_KEY", "")
        if nvidia_env_key and "nvidia" not in provider_keys:
            provider_keys["nvidia"] = [nvidia_env_key]
        
        # If no keys from any source, use NVIDIA keys from constructor
        if not provider_keys and keys:
            provider_keys["nvidia"] = keys
        
        super().__init__(
            keys=provider_keys or {"nvidia": keys or []},
            provider_order=["nvidia", "openrouter", "bytez"],
        )
        
        # Rate limit config for backward compatibility
        if config:
            for pname in self._rate_configs:
                self._rate_configs[pname]["rpm"] = config.rpm
                self._rate_configs[pname]["tpm"] = config.tpm
    
    def _resolve_model(self, model: str, has_tools: bool = False) -> str:
        """Resolve model name (backward compatible)."""
        resolved = self.MODELS.get(model, model)
        if has_tools and resolved not in self.TOOL_CAPABLE_MODELS:
            resolved = self.MODELS["tool"]
        return resolved
    
    def _sanitize_tools_for_nim(self, tools: list[dict]) -> list[dict]:
        """Sanitize tools (backward compatible)."""
        return self._sanitize_tools(tools)
