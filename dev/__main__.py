"""Allow running dev as a Python module: python -m dev"""

import sys
import os

if __name__ == "__main__" or "__main__" in sys.modules:
    # Fix Windows encoding for emoji
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")  # Force UTF-8 for all Python I/O
        os.environ.setdefault("PYTHONLEGACYWINDOWSSTDIO", "0")
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:

            pass  # best-effort: non-critical operation
    # If no arguments given (just `python -m dev`), start interactive chat
    if len(sys.argv) <= 1:
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

            pass  # best-effort: non-critical operation
        # Default to chat
        sys.argv = ["dev", "chat"]

    from dev.cli.main import app
    app()
