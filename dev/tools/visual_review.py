"""
Visual Review Tool — Screenshot + Vision Analysis for Self-Correction

This tool enables the agent to:
1. Take a screenshot of a web page using Playwright
2. Send the screenshot to a vision model for design analysis
3. Return structured feedback on visual quality
4. Enable the agent to fix ugly code based on feedback

This is the "eyes" of the agent — without it, the agent writes code blind.
"""

from __future__ import annotations

import asyncio
import base64
import os
import json
import time
from typing import Any, Optional
from .base import Tool


DESIGN_CRITIQUE_PROMPT = """You are a senior UI/UX designer reviewing a website screenshot. 
Analyze this screenshot and provide a detailed design critique.

Score the design on these criteria (1-10 each):
1. **Visual Hierarchy** — Is the most important content prominent? Are headings, body text, and CTAs clearly differentiated?
2. **Color Palette** — Are colors harmonious? Is there proper contrast? Does it look professional?
3. **Typography** — Is the font choice appropriate? Are sizes and weights used well? Is there good readability?
4. **Spacing & Layout** — Is there enough whitespace? Are elements properly aligned? Does the layout feel balanced?
5. **Modern Design** — Does it look like a 2026 website? Does it use modern patterns (glassmorphism, gradients, cards)?
6. **Responsiveness** — Does it look like it would work on mobile? Are elements appropriately sized?
7. **Overall Polish** — Does it feel production-ready or like a prototype?

For each criterion, provide:
- Score (1-10)
- What's good
- What needs improvement

Then provide a prioritized list of specific CSS/HTML changes to make it look stunning.
Be specific — mention exact CSS properties, colors, spacing values, and layout changes.

Format your response as JSON:
{
  "scores": {
    "visual_hierarchy": {"score": N, "good": "...", "improve": "..."},
    "color_palette": {"score": N, "good": "...", "improve": "..."},
    "typography": {"score": N, "good": "...", "improve": "..."},
    "spacing_layout": {"score": N, "good": "...", "improve": "..."},
    "modern_design": {"score": N, "good": "...", "improve": "..."},
    "responsiveness": {"score": N, "good": "...", "improve": "..."},
    "overall_polish": {"score": N, "good": "...", "improve": "..."}
  },
  "overall_score": N,
  "verdict": "ugly" | "decent" | "good" | "stunning",
  "critical_fixes": ["fix 1", "fix 2", ...],
  "css_changes": [
    {"selector": "...", "property": "...", "value": "...", "reason": "..."},
    ...
  ],
  "html_changes": ["change 1", "change 2", ...]
}
"""


class VisualReviewTool(Tool):
    """Review code changes by taking a screenshot and analyzing visual output for quality."""
    
    name = "visual_review"
    description = (
        "Take a screenshot of a webpage and get AI design feedback. "
        "Use this AFTER creating a website to check if it looks good. "
        "Returns scores, critique, and specific CSS/HTML fixes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to screenshot (e.g., http://localhost:3000)",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page (default: true)",
                "default": True,
            },
            "focus": {
                "type": "string",
                "description": "Specific area to focus on (e.g., 'hero section', 'navigation', 'contact form')",
                "default": "full page",
            },
        },
        "required": ["url"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "http://localhost:3000")
        full_page = input_data.get("full_page", True)
        focus = input_data.get("focus", "full page")
        
        # Step 1: Take screenshot
        screenshot_path = await self._take_screenshot(url, full_page, project_path)
        if not screenshot_path:
            return {"error": "Failed to take screenshot. Is the server running?"}
        
        # Step 2: Send to vision model
        feedback = await self._analyze_design(screenshot_path, focus, project_path)
        
        return {
            "success": True,
            "screenshot": screenshot_path,
            "url": url,
            "feedback": feedback,
        }
    
    async def _take_screenshot(self, url: str, full_page: bool, project_path: str) -> Optional[str]:
        """Take a screenshot using Playwright."""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                
                # Navigate with timeout
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(1)  # Wait for animations
                
                # Take screenshot
                screenshot_dir = os.path.join(project_path, ".dev")
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshot_dir, "review_screenshot.png")
                
                await page.screenshot(path=screenshot_path, full_page=full_page)
                await browser.close()
                
                return screenshot_path
                
        except ImportError:
            return None
        except Exception as e:
            print(f"[visual_review] Screenshot error: {e}")
            return None
    
    async def _analyze_design(self, screenshot_path: str, focus: str, project_path: str) -> dict:
        """Send screenshot to vision model for design analysis."""
        try:
            import httpx
            from dev.config.provider_config import get_api_keys
            
            keys = get_api_keys()
            
            # Read and encode screenshot
            with open(screenshot_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Build vision request
            prompt = DESIGN_CRITIQUE_PROMPT
            if focus != "full page":
                prompt += f"\n\nFocus especially on the: {focus}"
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_data}",
                            },
                        },
                    ],
                }
            ]
            
            # Try NVIDIA NIM vision model first
            nvidia_keys = keys.get("nvidia", [])
            if nvidia_keys:
                try:
                    result = await self._call_vision_model(
                        provider="nvidia",
                        key=nvidia_keys[0],
                        model="meta/llama-3.2-11b-vision-instruct",
                        messages=messages,
                    )
                    if result:
                        return result
                except Exception as e:
                    print(f"[visual_review] NVIDIA vision failed: {e}")
            
            # Fallback: OpenRouter vision model
            openrouter_keys = keys.get("openrouter", [])
            if openrouter_keys:
                try:
                    result = await self._call_vision_model(
                        provider="openrouter",
                        key=openrouter_keys[0],
                        model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                        messages=messages,
                    )
                    if result:
                        return result
                except Exception as e:
                    print(f"[visual_review] OpenRouter vision failed: {e}")
            
            # Fallback: text-only analysis (no vision)
            return {
                "overall_score": 5,
                "verdict": "unknown",
                "note": "Vision model unavailable — cannot analyze screenshot visually",
                "screenshot_saved": screenshot_path,
                "hint": "Review the screenshot manually at: " + screenshot_path,
            }
            
        except Exception as e:
            return {"error": f"Vision analysis failed: {e}"}
    
    async def _call_vision_model(
        self,
        provider: str,
        key: str,
        model: str,
        messages: list,
    ) -> Optional[dict]:
        """Call a vision model via API."""
        import httpx
        
        base_urls = {
            "nvidia": "https://integrate.api.nvidia.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 2000,
            "temperature": 0.3,
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{base_urls[provider]}/chat/completions",
                json=payload,
                headers=headers,
            )
            
            if response.status_code != 200:
                return None
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            try:
                # Try to extract JSON from the response
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(content[json_start:json_end])
            except json.JSONDecodeError:
                pass
            
            # Return raw text if JSON parsing fails
            return {
                "overall_score": 5,
                "verdict": "unknown",
                "raw_feedback": content,
                "note": "Could not parse structured feedback",
            }


class AutoVisualReviewTool(Tool):
    """Automatically review all recent file changes with visual screenshot comparison."""
    
    name = "auto_visual_review"
    description = (
        "Automatically screenshot a webpage, analyze the design, and apply fixes. "
        "This is the self-correction loop — it screenshots, critiques, and fixes in one call. "
        "Use after creating a website to make it look stunning."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to review (e.g., http://localhost:3000)",
            },
            "css_file": {
                "type": "string",
                "description": "Path to the CSS file to fix",
            },
            "html_file": {
                "type": "string",
                "description": "Path to the HTML file to fix (optional)",
            },
            "max_fix_rounds": {
                "type": "integer",
                "description": "Maximum number of fix rounds (default: 3)",
                "default": 3,
            },
        },
        "required": ["url", "css_file"],
    }
    
    async def execute(self, input_data: dict, state: Any, project_path: str) -> dict:
        url = input_data.get("url", "http://localhost:3000")
        css_file = input_data.get("css_file", "")
        html_file = input_data.get("html_file", "")
        max_rounds = input_data.get("max_fix_rounds", 3)
        
        results = []
        
        for round_num in range(max_rounds):
            # Step 1: Screenshot and analyze
            review_tool = VisualReviewTool()
            review_result = await review_tool.execute(
                {"url": url, "full_page": True},
                state,
                project_path,
            )
            
            if not review_result.get("success"):
                results.append({"round": round_num + 1, "error": review_result.get("error")})
                break
            
            feedback = review_result.get("feedback", {})
            score = feedback.get("overall_score", 5)
            verdict = feedback.get("verdict", "unknown")
            
            results.append({
                "round": round_num + 1,
                "score": score,
                "verdict": verdict,
                "screenshot": review_result.get("screenshot"),
            })
            
            # If score is good enough, stop
            if score >= 7 or verdict in ("stunning", "good"):
                break
            
            # Step 2: Apply CSS fixes
            css_changes = feedback.get("css_changes", [])
            if css_changes and css_file:
                await self._apply_css_fixes(css_file, css_changes, project_path)
            
            # Step 3: Apply HTML fixes
            html_changes = feedback.get("html_changes", [])
            if html_changes and html_file:
                await self._apply_html_fixes(html_file, html_changes, project_path)
        
        return {
            "success": True,
            "rounds": len(results),
            "results": results,
            "final_score": results[-1].get("score") if results else 0,
            "final_verdict": results[-1].get("verdict") if results else "unknown",
        }
    
    async def _apply_css_fixes(self, css_file: str, changes: list, project_path: str):
        """Apply CSS changes from vision feedback."""
        css_path = os.path.join(project_path, css_file)
        if not os.path.exists(css_path):
            return
        
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                css_content = f.read()
            
            for change in changes:
                selector = change.get("selector", "")
                property_name = change.get("property", "")
                value = change.get("value", "")
                
                if selector and property_name and value:
                    # Simple CSS injection — add or update property
                    import re
                    pattern = re.compile(
                        f"({re.escape(selector)}\\s*{{[^}}]*?){re.escape(property_name)}\\s*:[^;]+;",
                        re.DOTALL,
                    )
                    replacement = f"\\1{property_name}: {value};"
                    new_css = pattern.sub(replacement, css_content)
                    
                    if new_css != css_content:
                        css_content = new_css
                    else:
                        # Property doesn't exist — append to selector
                        selector_pattern = re.compile(
                            f"({re.escape(selector)}\\s*{{[^}}]*}})",
                            re.DOTALL,
                        )
                        new_rule = f"\\1\n    {property_name}: {value};"
                        css_content = selector_pattern.sub(new_rule, css_content, count=1)
            
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(css_content)
                
        except Exception as e:
            print(f"[visual_review] CSS fix error: {e}")
    
    async def _apply_html_fixes(self, html_file: str, changes: list, project_path: str):
        """Apply HTML changes from vision feedback."""
        # HTML fixes are more complex — log them for the agent to apply
        pass
__all__ = ["VisualReviewTool", "AutoVisualReviewTool"]
