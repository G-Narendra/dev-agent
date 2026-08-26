"""
Design Fetcher — Fetches real DESIGN.md files from brands and teaches the agent.

This tool fetches DESIGN.md files from the VoltAgent/awesome-design-md repo
and injects real design patterns (Stripe, Linear, Apple, GitHub, etc.) into
the agent's context. The agent learns from actual brand design systems,
not manual patterns.

Sources:
- https://github.com/VoltAgent/awesome-design-md
- https://www.shadcn.io/design
- https://getdesign.md
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Optional
from .base import Tool


# Available DESIGN.md files from the awesome-design-md repo
AVAILABLE_DESIGNS = {
    # AI & LLM Platforms
    "claude": "Anthropic's AI assistant — warm terracotta accent, clean editorial layout",
    "cohere": "Enterprise AI platform — vibrant gradients, data-rich dashboard aesthetic",
    "elevenlabs": "AI voice platform — dark cinematic UI, audio-waveform aesthetics",
    "mistral": "French-engineered minimalism, purple-toned",
    "ollama": "Terminal-first, monochrome simplicity",
    "together": "Technical, blueprint-style design",
    "xai": "Stark monochrome, futuristic minimalism",
    
    # Developer Tools
    "cursor": "Sleek dark interface, gradient accents",
    "expo": "Dark theme, tight letter-spacing, code-centric",
    "lovable": "Playful gradients, friendly dev aesthetic",
    "raycast": "Sleek dark chrome, vibrant gradient accents",
    "superhuman": "Premium dark UI, keyboard-first, purple glow",
    "vercel": "Black and white precision, Geist font",
    "warp": "Dark IDE-like interface, block-based command UI",
    
    # Backend & DevOps
    "clickhouse": "Yellow-accented, technical documentation style",
    "hashicorp": "Enterprise-clean, black and white",
    "mongodb": "Green leaf branding, developer documentation focus",
    "sentry": "Dark dashboard, data-dense, pink-purple accent",
    "supabase": "Dark emerald theme, code-first",
    
    # Productivity & SaaS
    "linear": "Ultra-minimal, precise, purple accent",
    "notion": "Warm minimalism, serif headings, soft surfaces",
    "resend": "Minimal dark theme, monospace accents",
    "zapier": "Warm orange, friendly illustration-driven",
    
    # Design & Creative
    "figma": "Vibrant multi-color, playful yet professional",
    "framer": "Bold black and blue, motion-first, design-forward",
    "webflow": "Blue-accented, polished marketing site aesthetic",
    
    # Fintech
    "stripe": "Signature purple gradients, weight-300 elegance",
    "revolut": "Sleek dark interface, gradient cards, fintech precision",
    "wise": "Bright green accent, friendly and clear",
    
    # E-commerce
    "airbnb": "Warm coral accent, photography-driven, rounded UI",
    "nike": "Monochrome UI, massive uppercase, full-bleed photography",
    "shopify": "Dark-first cinematic, neon green accent",
    
    # Media & Tech
    "apple": "Premium white space, SF Pro, cinematic imagery",
    "nvidia": "Green-black energy, technical power aesthetic",
    "spotify": "Vibrant green on dark, bold type, album-art-driven",
    "uber": "Bold black and white, tight type, urban energy",
    
    # Automotive
    "tesla": "Radical subtraction, cinematic full-viewport photography",
    "bmw": "Dark premium surfaces, precise German engineering aesthetic",
    "ferrari": "Chiaroscuro black-white editorial, Ferrari Red",
}

# GitHub raw URL template
GITHUB_RAW_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-design-md/main/design-md/{brand}/DESIGN.md"


class DesignFetcherTool(Tool):
    """Fetch real DESIGN.md files from brands and inject design patterns."""
    
    name = "design_fetch"
    description = (
        "Fetch a real brand's DESIGN.md file (Stripe, Linear, Apple, etc.) "
        "and inject its design patterns into your context. "
        "Use this BEFORE building a website to learn the design system. "
        "Available brands: stripe, linear, apple, github, vercel, notion, figma, nike, tesla, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "brand": {
                "type": "string",
                "description": "Brand to fetch design from (e.g., 'stripe', 'linear', 'apple')",
            },
            "save_to_project": {
                "type": "boolean",
                "description": "Save the DESIGN.md to the project root",
                "default": True,
            },
        },
        "required": ["brand"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        brand = input_data.get("brand", "").lower().strip()
        save_to_project = input_data.get("save_to_project", True)
        
        # Validate brand
        if brand not in AVAILABLE_DESIGNS:
            available = ", ".join(sorted(AVAILABLE_DESIGNS.keys())[:20])
            return {
                "error": f"Unknown brand: '{brand}'",
                "available_brands": available,
                "hint": f"Use one of: {available}",
            }
        
        # Fetch the DESIGN.md
        url = GITHUB_RAW_URL.format(brand=brand)
        content = await self._fetch_design_md(url)
        
        if not content:
            return {"error": f"Failed to fetch DESIGN.md for {brand}"}
        
        # Save to project if requested
        saved_path = None
        if save_to_project:
            design_path = os.path.join(project_path, "DESIGN.md")
            with open(design_path, "w", encoding="utf-8") as f:
                f.write(content)
            saved_path = design_path
        
        # Extract key tokens for the agent
        tokens = self._extract_tokens(content)
        
        return {
            "success": True,
            "brand": brand,
            "description": AVAILABLE_DESIGNS[brand],
            "saved_to": saved_path,
            "content_length": len(content),
            "tokens": tokens,
            "content_preview": content[:2000],
        }
    
    async def _fetch_design_md(self, url: str) -> Optional[str]:
        """Fetch DESIGN.md from GitHub."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
        except Exception:
            pass
        return None
    
    def _extract_tokens(self, content: str) -> dict:
        """Extract key design tokens from DESIGN.md."""
        tokens = {}
        
        # Extract colors
        color_matches = re.findall(r'(\w[\w-]*):\s*["\']?(#[0-9a-fA-F]{6})["\']?', content)
        if color_matches:
            tokens["colors"] = {name: hex_val for name, hex_val in color_matches[:15]}
        
        # Extract font family
        font_match = re.search(r'fontFamily:\s*["\']([^"\']+)', content)
        if font_match:
            tokens["font_family"] = font_match.group(1)
        
        # Extract border radius
        radius_matches = re.findall(r'(\w+):\s*(\d+px)', content)
        if radius_matches:
            tokens["radii"] = {name: val for name, val in radius_matches[:8]}
        
        # Extract spacing
        spacing_matches = re.findall(r'(\w+):\s*(\d+px)', content)
        if spacing_matches:
            tokens["spacing"] = {name: val for name, val in spacing_matches[:8]}
        
        return tokens


class DesignListTool(Tool):
    """List available brand DESIGN.md files."""
    
    name = "design_list"
    description = "List all available brand DESIGN.md files you can fetch."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        categories = {}
        for brand, desc in sorted(AVAILABLE_DESIGNS.items()):
            # Simple categorization
            if brand in ("stripe", "revolut", "wise"):
                cat = "Fintech"
            elif brand in ("apple", "nvidia", "spotify", "uber"):
                cat = "Media & Tech"
            elif brand in ("nike", "airbnb", "shopify"):
                cat = "E-commerce"
            elif brand in ("cursor", "expo", "vercel", "warp", "raycast"):
                cat = "Developer Tools"
            elif brand in ("linear", "notion", "resend", "zapier"):
                cat = "Productivity"
            elif brand in ("figma", "framer", "webflow"):
                cat = "Design Tools"
            elif brand in ("tesla", "bmw", "ferrari"):
                cat = "Automotive"
            else:
                cat = "AI & Platforms"
            
            if cat not in categories:
                categories[cat] = []
            categories[cat].append({"brand": brand, "description": desc})
        
        return {
            "total": len(AVAILABLE_DESIGNS),
            "categories": categories,
            "usage": "Use design_fetch with brand='stripe' to fetch a DESIGN.md file",
        }
