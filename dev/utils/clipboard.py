"""
Clipboard Integration — Copy/Paste Support

Provides clipboard access for the agent.
"""
import os
import subprocess
from typing import Optional


class Clipboard:
    """
    Clipboard access for the agent.
    
    Features:
    1. Copy text to clipboard
    2. Paste text from clipboard
    3. Cross-platform support
    """
    
    def copy(self, text: str) -> bool:
        """Copy text to clipboard."""
        try:
            if os.name == 'nt':  # Windows
                process = subprocess.Popen(
                    ['clip'],
                    stdin=subprocess.PIPE,
                    close_fds=True,
                )
                process.communicate(text.encode('utf-16le'))
                return True
            elif os.name == 'posix':  # macOS/Linux
                # Try pbcopy (macOS), xclip, xsel
                for cmd in [['pbcopy'], ['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']]:
                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            close_fds=True,
                        )
                        process.communicate(text.encode())
                        return True
                    except FileNotFoundError:
                        continue
            return False
        except Exception:
            return False
    
    def paste(self) -> Optional[str]:
        """Paste text from clipboard."""
        try:
            if os.name == 'nt':  # Windows
                process = subprocess.Popen(
                    ['powershell', '-command', 'Get-Clipboard'],
                    stdout=subprocess.PIPE,
                    close_fds=True,
                )
                output, _ = process.communicate()
                return output.decode().strip()
            elif os.name == 'posix':  # macOS/Linux
                for cmd in [['pbpaste'], ['xclip', '-selection', 'clipboard', '-o'], ['xsel', '--clipboard', '--output']]:
                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            close_fds=True,
                        )
                        output, _ = process.communicate()
                        return output.decode().strip()
                    except FileNotFoundError:
                        continue
            return None
        except Exception:
            return None
