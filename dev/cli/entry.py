"""Entry point for the dev CLI — defaults to chat when no args given."""

import sys
import os


def main():
    """CLI entry point. Defaults to 'chat' when no arguments are provided."""
    # Fix Windows encoding for emoji
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if len(sys.argv) <= 1:
        # Check first-run
        try:
            from dev.utils.first_run import is_configured
            if not is_configured():
                print("[First-Time Setup] No NVIDIA NIM API keys found.")
                print("Let's set up your keys.\n")
                import asyncio
                from dev.utils.first_run import run_wizard
                asyncio.run(run_wizard())
                print("\nStarting chat...\n")
        except Exception:
            pass
        sys.argv = ["dev", "chat"]

    from dev.cli.main import app
    app()
