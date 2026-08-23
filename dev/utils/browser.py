"""
Browser Automation — Screenshot, Click, Navigate

Provides basic browser automation using subprocess calls.
Uses system tools (open/chromium) for lightweight automation.
"""
import os
import subprocess
import json
from typing import Optional


class BrowserAutomation:
    """
    Basic browser automation for the agent.
    
    Features:
    1. Open URLs in browser
    2. Take screenshots (if chromium available)
    3. Get page content via curl
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def open_url(self, url: str) -> dict:
        """Open a URL in the default browser."""
        try:
            if os.name == 'nt':  # Windows
                subprocess.Popen(['start', url], shell=True)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.Popen(['open', url])
            
            return {"success": True, "url": url}
        except Exception as e:
            return {"error": str(e)}
    
    def get_page_content(self, url: str, max_chars: int = 10000) -> str:
        """Get page content via curl."""
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '10', url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            
            content = result.stdout
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... [truncated]"
            
            return content
        except Exception as e:
            return f"Error fetching URL: {e}"
    
    def take_screenshot(self, url: str, output_path: str = "screenshot.png") -> dict:
        """Take a screenshot using chromium headless."""
        try:
            result = subprocess.run(
                [
                    'chromium', '--headless', '--disable-gpu',
                    '--screenshot=' + output_path,
                    '--window-size=1280,720',
                    '--no-sandbox',
                    url
                ],
                capture_output=True,
                timeout=30,
            )
            
            if os.path.exists(output_path):
                return {"success": True, "path": output_path}
            return {"error": "Screenshot failed"}
        except FileNotFoundError:
            return {"error": "Chromium not installed"}
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_page(self, url: str) -> dict:
        """Analyze a web page."""
        content = self.get_page_content(url, max_chars=50000)
        
        # Extract basic info
        import re
        
        title = ""
        m = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if m:
            title = m.group(1).strip()
        
        # Count elements
        headings = len(re.findall(r'<h[1-6][^>]*>', content, re.IGNORECASE))
        links = len(re.findall(r'<a\s', content, re.IGNORECASE))
        images = len(re.findall(r'<img\s', content, re.IGNORECASE))
        forms = len(re.findall(r'<form\s', content, re.IGNORECASE))
        
        return {
            "url": url,
            "title": title,
            "headings": headings,
            "links": links,
            "images": images,
            "forms": forms,
            "content_length": len(content),
        }
