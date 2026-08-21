"""
First-Run Setup Wizard for Dev Agent.

When the user runs `narendra` for the first time with no API keys configured,
this wizard:
1. Detects no keys are configured
2. Asks how many NVIDIA NIM API keys they have
3. Prompts for each key one by one
4. Verifies each key works by making a test API call
5. Shows which models are available
6. Saves the keys to ~/.dev/config.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

CONFIG_DIR = Path.home() / ".dev"
CONFIG_FILE = CONFIG_DIR / "config.json"

# NVIDIA NIMs free-tier models
FREE_MODELS = {
    "nvidia/llama-3.1-nemotron-70b-instruct": "Coding & reasoning (128K context)",
    "nvidia/llama-3.1-8b-instruct": "Fast responses (128K context)",
    "nvidia/llama-3.3-70b-instruct": "Advanced reasoning (128K context)",
    "deepseek-ai/deepseek-r1": "Deep reasoning & math (128K context)",
    "qwen/qwen2.5-coder-32b-instruct": "Code generation (128K context)",
    "qwen/qwen2.5-72b-instruct": "General purpose (128K context)",
    "meta/llama-3.1-405b-instruct": "Largest free model (128K context)",
    "google/gemma-2-27b-it": "Google's free model (8K context)",
}

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


def is_configured() -> bool:
    """Check if API keys are already configured."""
    if not CONFIG_FILE.exists():
        return False
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        keys = config.get("api_keys", [])
        return len(keys) > 0
    except (json.JSONDecodeError, OSError):
        return False


async def verify_key(api_key: str) -> dict:
    """
    Verify an API key by making a test request.
    Returns {"valid": bool, "models": list, "error": str|None}
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test with a simple chat completion
            response = await client.post(
                f"{NIM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "nvidia/llama-3.1-8b-instruct",
                    "messages": [{"role": "user", "content": "Say OK"}],
                    "max_tokens": 5,
                    "temperature": 0.1,
                },
            )

            if response.status_code == 200:
                data = response.json()
                # Try to get available models (endpoint may not exist on all tiers)
                models = []
                try:
                    models_response = await client.get(
                        f"{NIM_BASE_URL}/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=10.0,
                    )
                    if models_response.status_code == 200:
                        models_data = models_response.json()
                        models = [
                            m["id"]
                            for m in models_data.get("data", [])
                            if m.get("owned_by") == "nvidia"
                        ]
                except Exception:
                    pass  # Models endpoint not available, but key is valid
                return {"valid": True, "models": models, "error": None}
            elif response.status_code == 401:
                return {"valid": False, "models": [], "error": "Invalid API key"}
            elif response.status_code == 429:
                return {"valid": True, "models": [], "error": "Key valid but rate limited"}
            else:
                return {
                    "valid": False,
                    "models": [],
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                }
    except httpx.TimeoutException:
        return {"valid": False, "models": [], "error": "Connection timeout"}
    except Exception as e:
        return {"valid": False, "models": [], "error": str(e)}


def save_keys(keys: list[str]):
    """Save API keys to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    config["api_keys"] = keys
    config["rpm"] = len(keys) * 40  # Each key gives ~40 RPM
    config["setup_complete"] = True

    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Restrict permissions (contains API keys)
    try:
        import stat
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, AttributeError):
        pass  # Windows


async def run_wizard() -> bool:
    """
    Run the first-time setup wizard.
    Returns True if setup completed successfully.
    """
    console.print()
    console.print(
        Panel(
            "[bold green]Welcome to Dev Agent![/bold green]\n\n"
            "Free 24/7 AI coding agent powered by NVIDIA NIMs.\n"
            "No local GPU required. No API costs.\n\n"
            "Let's set up your API keys.",
            title="🚀 First-Time Setup",
            border_style="green",
        )
    )

    console.print()
    console.print("[dim]Get free API keys at: https://build.nvidia.com[/dim]")
    console.print("[dim]Each key gives 40 requests/minute (free tier)[/dim]")
    console.print("[dim]You can use up to 3 keys for 120 RPM total[/dim]")
    console.print()

    # Ask how many keys
    while True:
        try:
            raw = input("How many NVIDIA NIM API keys do you have? (1): ").strip()
            num_keys = int(raw) if raw else 1
            if 1 <= num_keys <= 10:
                break
            console.print("[red]Please enter a number between 1 and 10[/red]")
        except (ValueError, KeyboardInterrupt, EOFError):
            console.print("[dim]Using 1 key[/dim]")
            num_keys = 1

    console.print()
    keys = []
    verified_keys = []

    for i in range(num_keys):
        console.print(f"[bold]Key {i + 1}/{num_keys}:[/bold]")
        while True:
            try:
                # Use input() instead of Rich Prompt so Ctrl+V paste works in cmd.exe
                key = input(f"  Paste your API key #{i + 1}: ")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Skipping remaining keys[/dim]")
                break

            if not key.strip():
                console.print("[red]Key cannot be empty. Try again.[/red]")
                continue

            key = key.strip()

            # Verify the key
            console.print(f"  [dim]Verifying key...[/dim]", end="")
            result = await verify_key(key)

            if result["valid"]:
                console.print(f"  [green]✓ Valid[/green]")
                keys.append(key)
                verified_keys.append(result)
                if result["models"]:
                    console.print(
                        f"  [dim]  Found {len(result['models'])} models[/dim]"
                    )
                break
            else:
                console.print(f"  [red]✗ {result['error']}[/red]")
                try:
                    retry = input("  Try again? (y/n): ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    retry = "n"
                if retry in ("n", "no"):
                    break

        if len(keys) > 0 and i < num_keys - 1:
            console.print()

    if not keys:
        console.print("[red]No keys configured. You can run `dev setup --key <key>` later.[/red]")
        return False

    # Save keys
    save_keys(keys)

    # Show summary
    console.print()
    console.print(
        Panel(
            f"[bold green]Setup Complete![/bold green]\n\n"
            f"  Keys configured: {len(keys)}\n"
            f"  Total RPM: {len(keys) * 40}\n"
            f"  Config saved: {CONFIG_FILE}",
            title="✅ Ready to Go",
            border_style="green",
        )
    )

    # Show available models
    console.print()
    console.print("[bold]Available Models:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Model", style="green")
    table.add_column("Best For")
    table.add_column("Status")

    # Merge all verified models
    all_models = set()
    for v in verified_keys:
        all_models.update(v.get("models", []))

    for model_id, description in FREE_MODELS.items():
        status = "✅ Available" if model_id in all_models else "⚠️  Check key"
        table.add_row(model_id, description, status)

    console.print(table)

    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print("  narendra chat                    # Interactive chat")
    console.print('  narendra run "build a REST API"   # Single task')
    console.print("  narendra --help                  # All commands")
    console.print()

    return True


def ensure_setup() -> bool:
    """
    Synchronous wrapper. Returns True if configured (or was just configured).
    """
    if is_configured():
        return True

    # Check if we're already inside an event loop (e.g., from chat command)
    try:
        loop = asyncio.get_running_loop()
        # Already in a loop — can't use asyncio.run().
        # Print message and return False so the caller can handle it.
        console.print("[yellow]No API keys configured. Run `dev setup` first.[/yellow]")
        return False
    except RuntimeError:
        pass  # No running loop — safe to use asyncio.run()

    # Run the async wizard
    try:
        return asyncio.run(run_wizard())
    except KeyboardInterrupt:
        console.print("\n[dim]Setup cancelled. Run `dev setup` to configure later.[/dim]")
        return False
