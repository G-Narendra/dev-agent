"""
Docker Sandbox — Safe Code Execution in Containers

Provides Docker-based sandboxing for running untrusted code.
"""
import os
import subprocess
import json
from typing import Optional


class DockerSandbox:
    """
    Execute commands in Docker containers for safety.
    
    Features:
    1. Run commands in isolated containers
    2. File system isolation
    3. Network restrictions
    4. Resource limits
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self._docker_available = None
    
    def is_available(self) -> bool:
        """Check if Docker is available."""
        if self._docker_available is not None:
            return self._docker_available
        
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                timeout=5,
            )
            self._docker_available = result.returncode == 0
        except Exception:
            self._docker_available = False
        
        return self._docker_available
    
    def run_command(self, command: str, image: str = "python:3.11-slim",
                    timeout: int = 60) -> dict:
        """Run a command in a Docker container."""
        if not self.is_available():
            return {"error": "Docker not available"}
        
        try:
            result = subprocess.run(
                [
                    'docker', 'run', '--rm',
                    '--network', 'none',  # No network access
                    '--memory', '256m',  # Memory limit
                    '--cpus', '1',  # CPU limit
                    '-v', f'{self.project_path}:/workspace',
                    '-w', '/workspace',
                    image,
                    'sh', '-c', command
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_python(self, code: str, timeout: int = 30) -> dict:
        """Run Python code in a sandbox."""
        # Escape the code for shell
        escaped = code.replace("'", "'\\''")
        return self.run_command(
            f"python3 -c '{escaped}'",
            image="python:3.11-slim",
            timeout=timeout,
        )
    
    def run_node(self, code: str, timeout: int = 30) -> dict:
        """Run Node.js code in a sandbox."""
        escaped = code.replace("'", "'\\''")
        return self.run_command(
            f"node -e '{escaped}'",
            image="node:20-slim",
            timeout=timeout,
        )
    
    def setup_sandbox(self, name: str = "dev-sandbox") -> dict:
        """Set up a persistent sandbox container."""
        if not self.is_available():
            return {"error": "Docker not available"}
        
        try:
            # Create volume for persistence
            subprocess.run(
                ['docker', 'volume', 'create', name],
                capture_output=True,
                timeout=10,
            )
            
            return {"success": True, "volume": name}
        except Exception as e:
            return {"error": str(e)}
    
    def cleanup(self):
        """Clean up Docker resources."""
        try:
            subprocess.run(
                ['docker', 'system', 'prune', '-f'],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass  # Intentional: non-critical: best-effort operation
