"""
Image Analysis — Analyze images and screenshots

Provides basic image analysis using built-in Python libraries.
"""
import os
import base64
from typing import Optional


class ImageAnalyzer:
    """
    Analyze images for the agent.
    
    Features:
    1. Read image files
    2. Get image dimensions
    3. Convert to base64 for LLM vision
    4. Basic color analysis
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
    
    def read_image(self, path: str) -> Optional[dict]:
        """Read an image file."""
        abs_path = os.path.join(self.project_path, path) if not os.path.isabs(path) else path
        
        if not os.path.exists(abs_path):
            return {"error": f"File not found: {path}"}
        
        try:
            # Get file info
            size = os.path.getsize(abs_path)
            
            # Try to get dimensions
            width, height = self._get_dimensions(abs_path)
            
            # Get mime type
            mime = self._get_mime_type(abs_path)
            
            # Read as base64
            with open(abs_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode()
            
            return {
                "path": path,
                "size": size,
                "width": width,
                "height": height,
                "mime_type": mime,
                "base64": data[:100] + "...",  # Truncate for display
                "full_base64": data,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_dimensions(self, path: str) -> tuple:
        """Get image dimensions without PIL."""
        try:
            import struct
            
            with open(path, 'rb') as f:
                header = f.read(32)
            
            # PNG
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                width = struct.unpack('>I', header[16:20])[0]
                height = struct.unpack('>I', header[20:24])[0]
                return width, height
            
            # JPEG
            if header[:2] == b'\xff\xd8':
                f = open(path, 'rb')
                f.read(2)
                while True:
                    marker = f.read(2)
                    if not marker or len(marker) < 2:
                        break
                    if marker[0] != 0xFF:
                        break
                    if marker[1] in (0xC0, 0xC1, 0xC2):
                        f.read(3)
                        height = struct.unpack('>H', f.read(2))[0]
                        width = struct.unpack('>H', f.read(2))[0]
                        f.close()
                        return width, height
                    else:
                        length = struct.unpack('>H', f.read(2))[0]
                        f.read(length - 2)
                f.close()
            
            return 0, 0
        except Exception:
            return 0, 0
    
    def _get_mime_type(self, path: str) -> str:
        """Get MIME type from extension."""
        ext = os.path.splitext(path)[1].lower()
        mime_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
        }
        return mime_map.get(ext, 'application/octet-stream')
    
    def analyze_colors(self, path: str) -> dict:
        """Basic color analysis."""
        try:
            from PIL import Image
            
            abs_path = os.path.join(self.project_path, path) if not os.path.isabs(path) else path
            img = Image.open(abs_path)
            img = img.convert('RGB')
            
            # Get dominant colors
            colors = img.getcolors(maxcolors=10000)
            if colors:
                colors.sort(reverse=True)
                dominant = [c[1] for c in colors[:5]]
                return {"dominant_colors": dominant}
            
            return {"dominant_colors": []}
        except ImportError:
            return {"error": "PIL not installed"}
        except Exception as e:
            return {"error": str(e)}
