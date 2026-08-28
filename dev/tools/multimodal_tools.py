"""
Multimodal tools for Dev — image input and PDF reading.

Lets the agent:
- Read and analyze images (screenshots, diagrams, photos)
- Read PDF documents
"""

from __future__ import annotations

import base64
import os
from typing import Any

from .base import Tool


class ReadImageTool(Tool):
    """Read an image file and return its base64 content for analysis."""

    name = "read_image"
    description = "Read an image file (png, jpg, gif, webp) and return its base64 content. Use this when you need to see a screenshot, diagram, or any visual content."

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file",
            },
        },
        "required": ["path"],
    }

    SUPPORTED_FORMATS = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        file_path = input_data.get("path", "")
        if not file_path:
            return {"error": "No path provided"}

        abs_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path
        ext = os.path.splitext(abs_path)[1].lower()

        if ext not in self.SUPPORTED_FORMATS:
            return {"error": f"Unsupported image format: {ext}. Supported: {', '.join(self.SUPPORTED_FORMATS.keys())}"}

        if not os.path.isfile(abs_path):
            return {"error": f"Image not found: {file_path}"}

        file_size = os.path.getsize(abs_path)
        if file_size > 20 * 1024 * 1024:
            return {"error": f"Image too large: {file_size / 1024 / 1024:.1f}MB (max 20MB)"}

        try:
            with open(abs_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            media_type = self.SUPPORTED_FORMATS[ext]

            return {
                "success": True,
                "path": file_path,
                "media_type": media_type,
                "size_bytes": file_size,
                "base64": image_data[:100] + "...[truncated for display]",
                "hint": "Image loaded successfully. The LLM can analyze this image.",
            }
        except Exception as e:
            return {"error": f"Failed to read image: {e}"}


class ReadPdfTool(Tool):
    """Read a PDF document and extract text content."""

    name = "read_pdf"
    description = "Read a PDF file and extract its text content. Use this for reading documentation, papers, or any PDF document."

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the PDF file",
            },
            "max_pages": {
                "type": "integer",
                "description": "Maximum number of pages to read (default: 50)",
                "default": 50,
            },
        },
        "required": ["path"],
    }

    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        file_path = input_data.get("path", "")
        max_pages = input_data.get("max_pages", 50)

        if not file_path:
            return {"error": "No path provided"}

        abs_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path

        if not os.path.isfile(abs_path):
            return {"error": f"PDF not found: {file_path}"}

        if not abs_path.lower().endswith(".pdf"):
            return {"error": "File is not a PDF"}

        try:
            # Try PyMuPDF first (fastest)
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(abs_path)
                pages = []
                total_pages = len(doc)
                pages_to_read = min(total_pages, max_pages)

                for i in range(pages_to_read):
                    page = doc[i]
                    text = page.get_text()
                    pages.append({"page": i + 1, "text": text})

                doc.close()

                full_text = "\n\n".join(p["text"] for p in pages)

                return {
                    "success": True,
                    "path": file_path,
                    "total_pages": total_pages,
                    "pages_read": pages_to_read,
                    "text": full_text[:100000],  # Cap at 100K chars
                    "truncated": len(full_text) > 100000,
                }
            except ImportError:
                pass

            # Try pdfplumber
            try:
                import pdfplumber

                with pdfplumber.open(abs_path) as pdf:
                    total_pages = len(pdf.pages)
                    pages_to_read = min(total_pages, max_pages)
                    texts = []

                    for i in range(pages_to_read):
                        page = pdf.pages[i]
                        text = page.extract_text() or ""
                        texts.append(text)

                    full_text = "\n\n".join(texts)

                    return {
                        "success": True,
                        "path": file_path,
                        "total_pages": total_pages,
                        "pages_read": pages_to_read,
                        "text": full_text[:100000],
                        "truncated": len(full_text) > 100000,
                    }
            except ImportError:
                pass

            # Fallback: try basic text extraction
            try:
                with open(abs_path, "rb") as f:
                    content = f.read()

                # Look for text streams in PDF
                import re
                text_parts = []
                for match in re.finditer(rb'\(([^\)]+)\)', content[:1000000]):
                    try:
                        text = match.group(1).decode("latin-1")
                        if len(text) > 3:
                            text_parts.append(text)
                    except Exception:
                        pass

                if text_parts:
                    return {
                        "success": True,
                        "path": file_path,
                        "text": " ".join(text_parts)[:50000],
                        "note": "Basic text extraction (install pymupdf or pdfplumber for better results)",
                    }
            except Exception:
                pass

            return {
                "error": "No PDF library available. Install with: pip install pymupdf",
                "path": file_path,
            }

        except Exception as e:
            return {"error": f"Failed to read PDF: {e}"}
