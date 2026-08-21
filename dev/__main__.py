"""Allow running dev as a Python module: python -m dev"""

import sys

# Fix for module execution
if __name__ == "__main__" or "__main__" in sys.modules:
    from dev.cli.main import app
    app()
