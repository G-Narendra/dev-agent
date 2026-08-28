"""
Deployment Helper Tool for Dev.

Detects the project type and generates deployment configuration:
- Dockerfile for containerized deployment
- docker-compose.yml for multi-service apps
- .dockerignore
- Procfile for Heroku/Railway
- Vercel/Netlify config for serverless
- GitHub Actions CI/CD workflow
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import Tool



__all__ = ["DeployTool"]

class DeployTool(Tool):
    """Detect project type and generate deployment configurations: Dockerfile, docker-compose.yml, GitHub Actions CI/CD, Vercel config, Heroku Procfile."""

    name = "deploy"
    description = (
        "Detect project type and generate deployment files. "
        "Creates Dockerfile, docker-compose.yml, CI/CD workflows, etc. "
        "Write all generated files to the project."
    )

    parameters = {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": (
                    "Target platform: 'docker' (default), 'vercel', 'netlify', "
                    "'railway', 'heroku', 'github-actions'. Omit for auto-detect."
                ),
            },
            "port": {
                "type": "integer",
                "description": "Port the app listens on (default: auto-detect from code)",
            },
        },
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        platform = input_data.get("platform", "docker")
        port = input_data.get("port", 0)

        # Detect project type
        detection = self._detect_project(project_path, port)

        files = {}

        if platform in ("docker", "all"):
            files.update(self._generate_docker(project_path, detection))
        if platform in ("github-actions", "all"):
            files.update(self._generate_github_actions(project_path, detection))
        if platform in ("vercel", "all"):
            files.update(self._generate_vercel(project_path, detection))
        if platform in ("railway", "heroku", "all"):
            files.update(self._generate_procfile(project_path, detection))

        # Write all files
        written = []
        for path, content in files.items():
            abs_path = os.path.join(project_path, path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(path)

        return {
            "success": True,
            "files_written": written,
            "project_type": detection["type"],
            "platform": platform,
            "message": f"Generated {len(written)} deployment files for {detection['type']} project",
        }

    def _detect_project(self, project_path: str, port: int) -> dict:
        """Detect project type from files."""
        detection = {"type": "unknown", "port": port, "cmd": "", "install": ""}

        # Node.js
        if os.path.isfile(os.path.join(project_path, "package.json")):
            detection["type"] = "node"
            detection["port"] = port or 3000
            detection["cmd"] = "node server.js"
            detection["install"] = "npm install"
            # Detect framework
            try:
                with open(os.path.join(project_path, "package.json")) as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    detection["type"] = "nextjs"
                    detection["cmd"] = "npm run build && npm start"
                elif "react" in deps:
                    detection["type"] = "react"
                    detection["cmd"] = "npm run build"
                elif "express" in deps:
                    detection["type"] = "express"
                    detection["cmd"] = "node server.js"
                elif "vite" in deps:
                    detection["type"] = "vite"
                    detection["cmd"] = "npm run build"
            except Exception:
                pass

        # Python
        elif os.path.isfile(os.path.join(project_path, "requirements.txt")):
            detection["type"] = "python"
            detection["port"] = port or 8000
            detection["cmd"] = "python app.py"
            detection["install"] = "pip install -r requirements.txt"
            # Check for Flask/FastAPI/Django
            try:
                with open(os.path.join(project_path, "requirements.txt")) as f:
                    reqs = f.read().lower()
                if "flask" in reqs:
                    detection["type"] = "flask"
                    detection["cmd"] = "flask run"
                elif "fastapi" in reqs:
                    detection["type"] = "fastapi"
                    detection["cmd"] = "uvicorn app:app --host 0.0.0.0"
                elif "django" in reqs:
                    detection["type"] = "django"
                    detection["cmd"] = "python manage.py runserver 0.0.0.0:8000"
            except Exception:
                pass

        # Go
        elif os.path.isfile(os.path.join(project_path, "go.mod")):
            detection["type"] = "go"
            detection["port"] = port or 8080
            detection["cmd"] = "./app"
            detection["install"] = "go build -o app ."

        # Rust
        elif os.path.isfile(os.path.join(project_path, "Cargo.toml")):
            detection["type"] = "rust"
            detection["port"] = port or 8080
            detection["cmd"] = "./target/release/app"
            detection["install"] = "cargo build --release"

        return detection

    def _generate_docker(self, project_path: str, detection: dict) -> dict:
        """Generate Dockerfile and docker-compose.yml."""
        files = {}

        ptype = detection["type"]
        port = detection["port"]
        cmd = detection["cmd"]

        if ptype in ("node", "express", "react", "nextjs", "vite"):
            files["Dockerfile"] = f"""FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
{'RUN npm run build' if ptype in ('react', 'nextjs', 'vite') else ''}

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app .
EXPOSE {port}
CMD {cmd}
"""
            files[".dockerignore"] = """node_modules
.git
.env
*.log
dist
build
.next
"""
        elif ptype in ("python", "flask", "fastapi", "django"):
            files["Dockerfile"] = f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port}
CMD {cmd}
"""
            files[".dockerignore"] = """__pycache__
*.pyc
.env
.venv
venv
.git
*.egg-info
"""
        elif ptype == "go":
            files["Dockerfile"] = f"""FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o app .

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/app .
EXPOSE {port}
CMD ["./app"]
"""
        else:
            files["Dockerfile"] = f"""FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE {port}
CMD ["{cmd or 'echo No command configured'}"]
"""

        files["docker-compose.yml"] = f"""version: "3.8"
services:
  app:
    build: .
    ports:
      - "{port}:{port}"
    environment:
      - NODE_ENV=production
    restart: unless-stopped
"""

        return files

    def _generate_github_actions(self, project_path: str, detection: dict) -> dict:
        """Generate GitHub Actions CI/CD workflow."""
        files = {}
        ptype = detection["type"]

        if ptype in ("node", "express", "react", "nextjs", "vite"):
            files[".github/workflows/ci.yml"] = """name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test
      - run: npm run build
"""
        elif ptype in ("python", "flask", "fastapi", "django"):
            files[".github/workflows/ci.yml"] = """name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest
"""

        return files

    def _generate_vercel(self, project_path: str, detection: dict) -> dict:
        """Generate Vercel configuration."""
        files = {}

        if detection["type"] in ("react", "nextjs", "vite"):
            files["vercel.json"] = json.dumps({
                "buildCommand": "npm run build",
                "outputDirectory": "dist" if detection["type"] == "vite" else ".next",
                "framework": detection["type"],
            }, indent=2) + "\n"

        return files

    def _generate_procfile(self, project_path: str, detection: dict) -> dict:
        """Generate Procfile for Heroku/Railway."""
        files = {}

        cmd = detection["cmd"] or "echo 'No command'"
        files["Procfile"] = f"web: {cmd}\n"

        return files
