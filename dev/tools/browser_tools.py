"""
Browser Automation and Docker Execution for Dev.

Uses Playwright for browser automation (with httpx fallback),
and Docker for sandboxed execution.
"""

from __future__ import annotations

import asyncio
import os
import json
import re
from typing import Any, Optional
from .base import Tool


def _html_to_text(html: str) -> str:
    """Convert HTML to readable text (no dependencies)."""
    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Decode common entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return text


def _extract_links(html: str) -> list[dict]:
    """Extract links from HTML."""
    links = []
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
        href = match.group(1)
        link_text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if href and link_text:
            links.append({"url": href, "text": link_text[:100]})
    return links[:50]


class BrowserScreenshotTool(Tool):
    """Take screenshots of web pages."""
    name = "browser_screenshot"
    description = "Take a screenshot of a web page."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to screenshot"},
            "full_page": {"type": "boolean", "description": "Capture full page", "default": False},
        },
        "required": ["url"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "")
        full_page = input_data.get("full_page", False)
        
        # Try Playwright first
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                screenshot_path = os.path.join(project_path, ".dev", "screenshot.png")
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                
                await page.screenshot(path=screenshot_path, full_page=full_page)
                title = await page.title()
                await browser.close()
                
                return {
                    "success": True,
                    "path": screenshot_path,
                    "url": url,
                    "title": title,
                }
        except ImportError:
            pass
        except Exception as e:
            pass
        
        # Fallback: fetch page content instead of screenshot
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Dev-Agent/1.0"})
                text = _html_to_text(resp.text[:50000])
                return {
                    "success": True,
                    "url": url,
                    "status_code": resp.status_code,
                    "content_preview": text[:2000],
                    "note": "Playwright not available — returned text content instead of screenshot",
                }
        except ImportError:
            pass
        except Exception:
            pass
        
        # Last fallback: urllib
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Dev-Agent/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                text = _html_to_text(html[:50000])
                return {
                    "success": True,
                    "url": url,
                    "content_preview": text[:2000],
                    "note": "Playwright not available — returned text content instead of screenshot",
                }
        except Exception as e:
            return {"error": f"Failed to fetch URL: {e}"}


class BrowserNavigateTool(Tool):
    """Navigate and interact with web pages."""
    name = "browser_navigate"
    description = "Navigate to a URL and extract content (text, links, or HTML)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "extract": {"type": "string", "description": "What to extract: text, links, html", "default": "text"},
            "selector": {"type": "string", "description": "CSS selector to extract (Playwright only)"},
        },
        "required": ["url"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "")
        extract = input_data.get("extract", "text")
        selector = input_data.get("selector", "")
        
        # Try Playwright first (for CSS selector support)
        if selector:
            try:
                from playwright.async_api import async_playwright
                
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    title = await page.title()
                    elements = await page.query_selector_all(selector)
                    content = []
                    for el in elements[:20]:
                        text = await el.text_content()
                        if text:
                            content.append(text.strip())
                    await browser.close()
                    
                    return {
                        "url": url,
                        "title": title,
                        "content": "\n".join(content),
                        "count": len(content),
                    }
            except ImportError:
                pass
            except Exception:
                pass
        
        # Try Playwright for general navigation
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                title = await page.title()
                
                if extract == "links":
                    links = await page.query_selector_all("a[href]")
                    result_links = []
                    for link in links[:50]:
                        href = await link.get_attribute("href")
                        text = await link.text_content()
                        if href and text:
                            result_links.append({"url": href, "text": text.strip()[:100]})
                    await browser.close()
                    return {"url": url, "title": title, "links": result_links}
                
                elif extract == "html":
                    content = await page.content()
                    await browser.close()
                    return {"url": url, "title": title, "html": content[:50000]}
                
                else:  # text
                    content = await page.inner_text("body")
                    await browser.close()
                    return {"url": url, "title": title, "text": content[:50000]}
        except ImportError:
            pass
        except Exception:
            pass
        
        # Fallback: httpx
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Dev-Agent/1.0"})
                html = resp.text[:100000]
                
                # Extract title
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""
                
                if extract == "links":
                    links = _extract_links(html)
                    return {"url": url, "title": title, "links": links}
                elif extract == "html":
                    return {"url": url, "title": title, "html": html[:50000]}
                else:
                    text = _html_to_text(html)
                    return {"url": url, "title": title, "text": text[:50000]}
        except ImportError:
            pass
        except Exception:
            pass
        
        # Last fallback: urllib
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Dev-Agent/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")[:100000]
                
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""
                
                if extract == "links":
                    links = _extract_links(html)
                    return {"url": url, "title": title, "links": links}
                elif extract == "html":
                    return {"url": url, "title": title, "html": html[:50000]}
                else:
                    text = _html_to_text(html)
                    return {"url": url, "title": title, "text": text[:50000]}
        except Exception as e:
            return {"error": f"Failed to navigate: {e}"}


class BrowserClickTool(Tool):
    """Click elements on web pages."""
    name = "browser_click"
    description = "Click an element on a web page (requires Playwright)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "selector": {"type": "string", "description": "CSS selector to click"},
            "wait_after": {"type": "number", "description": "Seconds to wait after click", "default": 1},
        },
        "required": ["url", "selector"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "")
        selector = input_data.get("selector", "")
        wait_after = input_data.get("wait_after", 1)
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                element = await page.query_selector(selector)
                if not element:
                    await browser.close()
                    return {"error": f"Element not found: {selector}"}
                
                await element.click()
                await asyncio.sleep(wait_after)
                
                # Get page content after click
                content = await page.inner_text("body")
                new_url = page.url
                
                await browser.close()
                
                return {
                    "url": new_url,
                    "clicked": selector,
                    "content_after": content[:5000],
                }
        except ImportError:
            return {
                "error": "Playwright required for click operations. Install: pip install playwright && playwright install",
                "fallback": "Use browser_navigate tool instead for reading page content",
            }
        except Exception as e:
            return {"error": str(e)}


class DockerRunTool(Tool):
    """Run commands in Docker containers."""
    name = "docker_run"
    description = "Run a command inside a Docker container."
    parameters = {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Docker image to use"},
            "command": {"type": "string", "description": "Command to run"},
            "volumes": {"type": "array", "items": {"type": "string"}, "description": "Volume mounts (host:container)"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 60},
        },
        "required": ["image", "command"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        image = input_data.get("image", "")
        command = input_data.get("command", "")
        volumes = input_data.get("volumes", [])
        timeout = input_data.get("timeout", 60)
        
        # Build docker command
        cmd = ["docker", "run", "--rm"]
        
        # Add volume mounts
        for vol in volumes:
            cmd.extend(["-v", vol])
        
        # Mount project directory
        cmd.extend(["-v", f"{project_path}:/workspace", "-w", "/workspace"])
        
        cmd.extend([image, "sh", "-c", command])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[-10000:],
                "stderr": stderr.decode(errors="replace")[-5000:],
            }
        except FileNotFoundError:
            return {"error": "Docker not installed. Install Docker to use sandboxed execution."}
        except asyncio.TimeoutError:
            return {"error": f"Docker command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}


class DockerBuildTool(Tool):
    """Build Docker images."""
    name = "docker_build"
    description = "Build a Docker image from a Dockerfile."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to Dockerfile directory", "default": "."},
            "tag": {"type": "string", "description": "Image tag"},
            "dockerfile": {"type": "string", "description": "Dockerfile name", "default": "Dockerfile"},
        },
        "required": ["tag"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        build_path = input_data.get("path", project_path)
        tag = input_data.get("tag", "dev-build")
        dockerfile = input_data.get("dockerfile", "Dockerfile")
        
        cmd = ["docker", "build", "-t", tag, "-f", dockerfile, build_path]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            
            return {
                "exit_code": proc.returncode,
                "tag": tag,
                "output": stdout.decode(errors="replace")[-5000:],
                "errors": stderr.decode(errors="replace")[-3000:],
            }
        except FileNotFoundError:
            return {"error": "Docker not installed."}
        except asyncio.TimeoutError:
            return {"error": "Docker build timed out after 120s"}
        except Exception as e:
            return {"error": str(e)}
