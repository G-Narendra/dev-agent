"""
Image and URL input support for chat.

Like Aider's image/web page support:
- Add images to chat for visual context
- Add web pages as context
- Screenshot analysis
"""
from __future__ import annotations
import os
import base64
import mimetypes
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class ImageInput:
    """An image input for chat."""
    path: str
    media_type: str = "image/png"
    base64_data: Optional[str] = None
    description: str = ""

    def load(self) -> bool:
        """Load image data from disk."""
        if not os.path.exists(self.path):
            return False
        try:
            with open(self.path, "rb") as f:
                self.base64_data = base64.b64encode(f.read()).decode()
            self.media_type = mimetypes.guess_type(self.path)[0] or "image/png"
            return True
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Convert to API-compatible dict."""
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{self.media_type};base64,{self.base64_data}",
            },
        }


@dataclass
class WebInput:
    """A web page input for chat."""
    url: str
    title: str = ""
    content: str = ""
    max_chars: int = 10000

    async def fetch(self) -> bool:
        """Fetch web page content."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.url, follow_redirects=True)
                resp.raise_for_status()
                self.content = resp.text[:self.max_chars]
                # Extract title from HTML
                if "<title>" in self.content:
                    start = self.content.index("<title>") + 7
                    end = self.content.index("</title>")
                    self.title = self.content[start:end].strip()
                return True
        except Exception:
            return False

    def to_message(self) -> str:
        """Convert to message content."""
        return f"[Web Page: {self.title or self.url}]\n{self.content[:5000]}"


class InputManager:
    """Manages image and URL inputs for chat."""
    
    def __init__(self):
        self.images: list[ImageInput] = []
        self.urls: list[WebInput] = []

    def add_image(self, path: str, description: str = "") -> bool:
        """Add an image file to the context."""
        img = ImageInput(path=os.path.abspath(path), description=description)
        if img.load():
            self.images.append(img)
            return True
        return False

    def add_url(self, url: str) -> bool:
        """Add a URL to the context."""
        web = WebInput(url=url)
        self.urls.append(web)
        return True

    def remove_image(self, path: str):
        """Remove an image from context."""
        self.images = [i for i in self.images if i.path != os.path.abspath(path)]

    def remove_url(self, url: str):
        """Remove a URL from context."""
        self.urls = [u for u in self.urls if u.url != url]

    def clear(self):
        """Clear all inputs."""
        self.images.clear()
        self.urls.clear()

    def get_message_parts(self) -> list[dict]:
        """Get message parts for API call (multimodal format)."""
        parts = []
        for img in self.images:
            parts.append(img.to_dict())
        return parts

    def get_text_context(self) -> str:
        """Get text context from URLs."""
        parts = []
        for web in self.urls:
            if web.content:
                parts.append(f"[Web Page: {web.title or web.url}]\n{web.content[:5000]}")
        return "\n\n".join(parts)

    def list_inputs(self) -> list[dict]:
        """List all current inputs."""
        result = []
        for img in self.images:
            result.append({"type": "image", "path": img.path, "description": img.description})
        for web in self.urls:
            result.append({"type": "url", "url": web.url, "title": web.title})
        return result

    @staticmethod
    def parse_image_refs(text: str) -> list[str]:
        """Extract image references from user text."""
        import re
        # Match @image /path/to/image.png
        refs = re.findall(r'@image\s+([^\s]+)', text)
        # Match common image extensions in text
        refs.extend(re.findall(r'([^\s]+\.(?:png|jpg|jpeg|gif|webp|bmp))', text))
        return refs

    @staticmethod
    def parse_url_refs(text: str) -> list[str]:
        """Extract URL references from user text."""
        import re
        urls = re.findall(r'@url\s+(https?://[^\s]+)', text)
        urls.extend(re.findall(r'(https?://[^\s]+)', text))
        return list(set(urls))
