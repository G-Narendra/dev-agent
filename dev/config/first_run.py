"""
First-Run Setup Wizard — guides users through setting up all 3 free API providers.

Providers:
1. NVIDIA NIM — 80+ models, fastest, 40 RPM free
2. OpenRouter — 28+ free models, DeepSeek R1, Qwen3 Coder
3. Bytez — 175K+ models, $0/month, text/image/video

All three are 100% free with no credit card required.
"""

import asyncio
import sys
import os

import httpx

from .provider_config import (
    save_api_keys,
    get_api_keys,
    has_any_key,
    validate_key,
    load_config,
    save_config,
    get_config_summary,
)


# Provider details for the wizard
PROVIDERS = {
    "nvidia": {
        "name": "NVIDIA NIM",
        "url": "https://build.nvidia.com",
        "url_note": "build.nvidia.com",
        "description": "80+ top AI models, fastest inference, 40 RPM free",
        "strength": "Speed",
        "signup_steps": [
            "Go to build.nvidia.com",
            "Sign up with email (free)",
            "Go to Settings → API Keys",
            "Click 'Generate Key'",
            "Copy the key (starts with nvapi-)",
        ],
        "key_format": "nvapi-...",
        "verify_url": "https://integrate.api.nvidia.com/v1/models",
        "models_count": "80+",
        "models_list": [
            "meta/llama-3.1-70b-instruct (coding)",
            "meta/llama-3.1-8b-instruct (fast)",
            "nvidia/llama-3.1-nemotron-ultra-253b-v1 (reasoning)",
            "meta/llama-3.2-11b-vision-instruct (vision)",
            "deepseek-ai/deepseek-v4-flash-0731 (DeepSeek V4)",
            "mistralai/codestral-22b-instruct-v0.1 (code)",
            "google/gemma-2-27b-it (Google)",
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "url": "https://openrouter.ai",
        "url_note": "openrouter.ai",
        "description": "28+ free models including DeepSeek R1, Qwen3 Coder 480B",
        "strength": "Variety",
        "signup_steps": [
            "Go to openrouter.ai",
            "Sign up with email or GitHub (free)",
            "Go to Settings → Keys",
            "Click 'Create Key'",
            "Copy the key (starts with sk-or-)",
        ],
        "key_format": "sk-or-...",
        "verify_url": "https://openrouter.ai/api/v1/models",
        "models_count": "28+ free",
        "models_list": [
            "nvidia/nemotron-3-ultra-550b-a55b:free (1M context, reasoning)",
            "poolside/laguna-s-2.1:free (coding agent)",
            "cohere/north-mini-code:free (code generation)",
            "nvidia/nemotron-3-super-120b-a12b:free (general agent)",
            "google/gemma-4-26b-a4b-it:free (multimodal)",
        ],
    },
    "bytez": {
        "name": "Bytez",
        "url": "https://bytez.com",
        "url_note": "bytez.com",
        "description": "175K+ models, text/image/video/audio, $0/month",
        "strength": "Scale",
        "signup_steps": [
            "Go to bytez.com",
            "Sign up (free)",
            "Go to API settings",
            "Generate an API key",
            "Copy the key",
        ],
        "key_format": "...",
        "verify_url": "https://api.bytez.com/models/v2/openai/v1/models",
        "models_count": "175K+",
        "models_list": [
            "Qwen/Qwen3-Coder-32B-Instruct (coding)",
            "meta-llama/Llama-3.3-70B-Instruct (general)",
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B (reasoning)",
        ],
    },
}


def print_header():
    """Print the setup header."""
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + " 🚀 Dev Agent — First-Time Setup ".center(70) + "║")
    print("╠" + "═" * 70 + "╣")
    print("║" + " Free 24/7 AI coding agent powered by 3 providers ".center(70) + "║")
    print("║" + " No credit card. No local GPU. No API costs. ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")
    print()


def print_provider_info(provider_key: str):
    """Print info about a provider."""
    info = PROVIDERS[provider_key]
    print(f"\n{'─' * 60}")
    print(f"  📦 {info['name']} ({info['strength']})")
    print(f"{'─' * 60}")
    print(f"  {info['description']}")
    print(f"  Models: {info['models_count']}")
    print(f"  Sign up: {info['url']}")
    print()
    print("  Sign up steps:")
    for i, step in enumerate(info["signup_steps"], 1):
        print(f"    {i}. {step}")
    print()


def verify_key(provider: str, key: str) -> tuple[bool, str]:
    """Verify an API key by making a test request."""
    try:
        config = PROVIDERS[provider]
        
        if provider == "nvidia":
            url = "https://integrate.api.nvidia.com/v1/models"
            headers = {"Authorization": f"Bearer {key}"}
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Authorization": f"Bearer {key}"}
        elif provider == "bytez":
            url = "https://api.bytez.com/models/v2/openai/v1/models"
            headers = {"Authorization": f"Bearer {key}"}
        else:
            return False, "Unknown provider"
        
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                return True, f"Found {model_count} models"
            elif response.status_code == 401:
                return False, "Invalid key"
            elif response.status_code == 403:
                return False, "Key not authorized"
            else:
                return False, f"HTTP {response.status_code}"
    
    except httpx.TimeoutException:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)


def prompt_key(provider: str) -> str | None:
    """Prompt user for an API key."""
    info = PROVIDERS[provider]
    
    print(f"\n  Enter your {info['name']} API key:")
    print(f"  (format: {info['key_format']})")
    print(f"  Get one free at: {info['url']}")
    print()
    
    try:
        key = input("  API Key: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    
    if not key:
        return None
    
    return key


def setup_provider(provider: str) -> list[str]:
    """Set up keys for a single provider. Returns list of valid keys."""
    info = PROVIDERS[provider]
    keys = []
    
    print(f"\n  Setting up {info['name']}...")
    
    # Ask how many keys
    try:
        count_str = input(f"  How many {info['name']} API keys? (0 to skip): ").strip()
        count = int(count_str) if count_str else 0
    except (ValueError, EOFError, KeyboardInterrupt):
        return []
    
    if count <= 0:
        return []
    
    for i in range(count):
        print(f"\n  Key {i + 1}/{count}:")
        
        max_attempts = 3
        for attempt in range(max_attempts):
            key = prompt_key(provider)
            if not key:
                break
            
            print("  Verifying...", end=" ", flush=True)
            valid, message = verify_key(provider, key)
            
            if valid:
                print(f"✓ {message}")
                keys.append(key)
                break
            else:
                print(f"✗ {message}")
                if attempt < max_attempts - 1:
                    try:
                        retry = input("  Try again? (y/n): ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        return keys
                    if retry != "y" and retry != "yes":
                        break
    
    return keys


def run_first_run_wizard() -> dict[str, list[str]]:
    """
    Run the interactive first-run setup wizard.
    
    Returns dict of provider -> list of API keys.
    """
    print_header()
    
    # Check if already configured
    existing_keys = get_api_keys()
    if existing_keys:
        total = sum(len(v) for v in existing_keys.values())
        print(f"  ⚠️  Already have {total} key(s) configured.")
        try:
            reconfigure = input("  Reconfigure? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return existing_keys
        if reconfigure != "y" and reconfigure != "yes":
            return existing_keys
    
    # Show available providers
    print("  Available free API providers:")
    print()
    for key, info in PROVIDERS.items():
        print(f"    {'●' if key == 'nvidia' else '○'} {info['name']:15s} — {info['description']}")
    print()
    print("  💡 Recommended: Get keys from all 3 for maximum power")
    print("  💡 Each gives different strengths: Speed + Variety + Scale")
    print()
    
    all_keys = {}
    
    # Set up each provider
    for provider_key in ["nvidia", "openrouter", "bytez"]:
        print_provider_info(provider_key)
        keys = setup_provider(provider_key)
        if keys:
            all_keys[provider_key] = keys
            save_api_keys(provider_key, keys)
            print(f"\n  ✅ {len(keys)} {PROVIDERS[provider_key]['name']} key(s) saved")
    
    # Summary
    total = sum(len(v) for v in all_keys.values())
    if total == 0:
        print("\n  ⚠️  No API keys configured. You can run 'dev setup' later.")
        print("  Without API keys, Dev cannot make AI requests.")
    else:
        print(f"\n  🎉 Setup complete! {total} key(s) configured:")
        for prov, keys in all_keys.items():
            print(f"    {PROVIDERS[prov]['name']}: {len(keys)} key(s)")
        
        print(f"\n  Total free RPM: {sum(len(v) * PROVIDERS[p].get('rpm', 40) for p, v in all_keys.items())}")
        print()
        print("  Quick Start:")
        print("    narendra chat                    # Interactive chat")
        print("    narendra run 'build a REST API'  # Single task")
        print("    narendra --help                  # All commands")
    
    return all_keys


def check_and_setup() -> dict[str, list[str]]:
    """Check if setup is needed and run wizard if so."""
    if has_any_key():
        return get_api_keys()
    
    return run_first_run_wizard()
