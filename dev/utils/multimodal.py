"""
Multimodal support for Dev.

From Freebuff's image handling and Codex's image support.
Supports:
- Image input (screenshots, diagrams)
- Image generation (via APIs)
- Image analysis
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ImageContent:
    """An image to send to the LLM."""
    data: str  # base64 encoded
    media_type: str  # "image/png", "image/jpeg", etc.
    path: str = ""


class ImageHandler:
    """
    Handles image input/output.
    
    From Freebuff's image-processor.ts.
    """
    
    SUPPORTED_FORMATS = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    
    MAX_SIZE_MB = 20
    
    def load_image(self, path: str) -> ImageContent | None:
        """Load an image from file."""
        ext = Path(path).suffix.lower()
        
        if ext not in self.SUPPORTED_FORMATS:
            return None
        
        try:
            file_size = os.path.getsize(path) / (1024 * 1024)
            if file_size > self.MAX_SIZE_MB:
                return None
            
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            
            return ImageContent(
                data=data,
                media_type=self.SUPPORTED_FORMATS[ext],
                path=path,
            )
        except Exception:
            return None
    
    def load_images(self, paths: list[str]) -> list[ImageContent]:
        """Load multiple images."""
        images = []
        for path in paths:
            img = self.load_image(path)
            if img:
                images.append(img)
        return images
    
    def image_to_message(self, image: ImageContent) -> dict:
        """Convert image to message format for LLM."""
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image.media_type};base64,{image.data}",
            },
        }
    
    def images_to_content(self, images: list[ImageContent], text: str = "") -> list[dict]:
        """Convert images to content array for LLM message."""
        content = []
        
        if text:
            content.append({"type": "text", "text": text})
        
        for image in images:
            content.append(self.image_to_message(image))
        
        return content
    
    def resize_image(
        self,
        path: str,
        max_width: int = 1024,
        max_height: int = 1024,
        output_path: str | None = None,
    ) -> str | None:
        """Resize an image (requires Pillow)."""
        try:
            from PIL import Image
            
            img = Image.open(path)
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            save_path = output_path or path
            img.save(save_path)
            
            return save_path
        except ImportError:
            return None
        except Exception:
            return None
    
    def get_image_info(self, path: str) -> dict:
        """Get image metadata."""
        try:
            from PIL import Image
            
            img = Image.open(path)
            return {
                "path": path,
                "format": img.format,
                "mode": img.mode,
                "size": img.size,
                "width": img.width,
                "height": img.height,
            }
        except ImportError:
            return {"path": path, "error": "Pillow not installed"}
        except Exception as e:
            return {"path": path, "error": str(e)}


class ScreenshotTool:
    """
    Take screenshots of web pages.
    
    Uses the free ApiFlash or screenshot API.
    """
    
    def __init__(self):
        self._handler = ImageHandler()
    
    async def take_screenshot(
        self,
        url: str,
        output_path: str | None = None,
        width: int = 1280,
        height: int = 720,
    ) -> dict:
        """Take a screenshot of a URL."""
        import httpx
        
        # Use free screenshot API
        api_url = "https://api.screenshotone.com/take"
        params = {
            "url": url,
            "format": "png",
            "width": width,
            "height": height,
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(api_url, params=params)
                
                if resp.status_code == 200:
                    if output_path:
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        return {"success": True, "path": output_path}
                    else:
                        data = base64.b64encode(resp.content).decode()
                        return {"success": True, "data": data[:100] + "..."}
                else:
                    return {"error": f"Screenshot failed: {resp.status_code}"}
                    
        except Exception as e:
            return {"error": str(e)}
