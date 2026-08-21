"""
Headless mode for Dev — CI/CD pipelines.

Features:
- stdin piping: cat file.py | dev -p "explain this"
- --json output for machine parsing
- --quiet for minimal output
- --output-format stream-json for streaming JSON
- Proper tool execution via ProductionAgentLoop
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    STREAM_JSON = "stream-json"


@dataclass
class HeadlessConfig:
    """Configuration for headless mode."""
    enabled: bool = True
    output_format: OutputFormat = OutputFormat.TEXT
    quiet: bool = False
    max_tokens: int = 4096
    model: str = "default"
    approval_mode: str = "full-auto"
    max_steps: int = 50


@dataclass
class HeadlessResult:
    """Result of a headless run."""
    success: bool = True
    prompt: str = ""
    response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    steps: int = 0
    tokens_sent: int = 0
    tokens_received: int = 0
    cost: float = 0.0
    error: str = ""
    duration_ms: int = 0

    def to_json(self, pretty: bool = False) -> str:
        """Serialize to JSON."""
        data = {
            "success": self.success,
            "prompt": self.prompt,
            "response": self.response,
            "tool_calls": self.tool_calls,
            "files_changed": self.files_changed,
            "steps": self.steps,
            "tokens": {
                "sent": self.tokens_sent,
                "received": self.tokens_received,
            },
            "cost": self.cost,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            data["error"] = self.error
        indent = 2 if pretty else None
        return json.dumps(data, indent=indent)


class HeadlessRunner:
    """Runs Dev in headless mode for CI/CD pipelines."""

    def __init__(self, config: Optional[HeadlessConfig] = None):
        self.config = config or HeadlessConfig()

    def read_stdin(self) -> str:
        """Read prompt from stdin (for piping)."""
        if sys.stdin.isatty():
            return ""
        return sys.stdin.read().strip()

    def run(self, prompt: str, provider=None, runtime=None) -> HeadlessResult:
        """Run a prompt in headless mode."""
        start_time = time.time()

        # If prompt is empty, try reading from stdin
        if not prompt:
            prompt = self.read_stdin()

        if not prompt:
            return HeadlessResult(
                success=False,
                prompt="",
                error="No prompt provided. Usage: dev headless 'prompt' or echo 'prompt' | dev headless",
            )

        if not provider:
            return HeadlessResult(
                success=False,
                prompt=prompt,
                error="No LLM provider configured. Run 'dev setup --key <key>' first.",
            )

        result = asyncio.run(self._run_async(prompt, provider, runtime))
        result.duration_ms = int((time.time() - start_time) * 1000)

        if self.config.output_format == OutputFormat.JSON:
            print(result.to_json(pretty=True))
        elif self.config.output_format == OutputFormat.STREAM_JSON:
            # Output as JSONL (one JSON object per line)
            print(json.dumps({"type": "prompt", "content": prompt}))
            print(json.dumps({"type": "response", "content": result.response}))
            if result.tool_calls:
                print(json.dumps({"type": "tool_calls", "calls": result.tool_calls}))
            print(json.dumps({"type": "done", "success": result.success}))
        elif not self.config.quiet:
            print(result.response)

        return result

    def run_batch(self, prompts: list[str], provider=None, runtime=None) -> list[HeadlessResult]:
        """Run multiple prompts in sequence."""
        results = []
        for prompt in prompts:
            result = self.run(prompt, provider, runtime)
            results.append(result)
        return results

    async def _run_async(self, prompt: str, provider, runtime) -> HeadlessResult:
        """Run asynchronously with full tool execution."""
        result = HeadlessResult(prompt=prompt)

        try:
            if runtime:
                # Use full agent loop with tools
                from ..agents.production_loop import ProductionAgentLoop, LoopConfig

                loop_config = LoopConfig(
                    model=self.config.model,
                    approval_mode=self.config.approval_mode,
                    auto_lint=True,
                    auto_commit=True,
                )
                agent_loop = ProductionAgentLoop(
                    provider=provider,
                    tool_registry=runtime.tools,
                    config=loop_config,
                    project_path=os.path.abspath("."),
                )

                agent_result = await agent_loop.run_streaming(
                    prompt=prompt,
                    system_prompt="You are Dev, an AI coding agent. Complete the task efficiently.",
                    max_steps=self.config.max_steps,
                )

                result.response = agent_result.get("content", "")
                result.tool_calls = agent_result.get("tool_calls", [])
                result.tool_results = agent_result.get("tool_results", [])
                result.steps = agent_result.get("steps", 0)
                result.tokens_sent = agent_result.get("tokens_sent", 0)
                result.tokens_received = agent_result.get("tokens_received", 0)
                result.cost = agent_result.get("cost", 0)
                result.files_changed = [
                    tc.get("args", {}).get("path", "")
                    for tc in result.tool_calls
                    if tc.get("name") in ("write_file", "str_replace", "apply_patch")
                ]
                result.success = agent_result.get("status") in ("completed", "max_steps")
            else:
                # Simple LLM call without tools
                response = await provider.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                )
                choice = response.get("choices", [{}])[0]
                result.response = choice.get("message", {}).get("content", "")
                usage = response.get("usage", {})
                result.tokens_sent = usage.get("prompt_tokens", 0)
                result.tokens_received = usage.get("completion_tokens", 0)
                result.success = True

        except Exception as e:
            result.success = False
            result.error = str(e)

        return result
