"""services/vision_service.py — Vision service for image analysis."""

import os
import base64
import json
import re
from typing import Dict, Any, List, Optional
import httpx
from PIL import Image
import io


class VisionService:
    """Vision service using Claude Vision API."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1/messages"
    
    def analyze_fridge_image(self, image_bytes: bytes, context: str = "fridge") -> Dict:
        """Analyze fridge/pantry image and detect ingredients."""
        if not self.api_key:
            return {"error": "Anthropic API key not configured", "detected_items": []}
        
        # Resize image if too large
        image_bytes = self._resize_image(image_bytes, max_size=1568)
        
        # Convert to base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        media_type = "image/jpeg"
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        
        prompt = f"""Analyze this {context} image. Identify ALL visible food items.

Return ONLY valid JSON:
{{
    "detected_items": [
        {{
            "name": "item name (lowercase)",
            "quantity": "estimated number",
            "unit": "pieces/kg/grams/bunch",
            "freshness": "fresh/good/use-soon/expiring",
            "expiry_risk": 0.0-1.0,
            "category": "vegetables/fruits/dairy/proteins/grains/condiments"
        }}
    ],
    "scene_description": "one sentence",
    "suggested_recipes": ["recipe1", "recipe2"],
    "expiring_concerns": ["item1"],
    "confidence": 0.95
}}

Expiry risk: 0.0=very fresh, 0.5=use this week, 1.0=use today"""

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 1500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Extract JSON from response
                content = data.get("content", [{}])[0].get("text", "")
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return {"detected_items": [], "scene_description": "Analysis failed", "confidence": 0}
                
        except Exception as e:
            return {"error": str(e), "detected_items": [], "scene_description": f"Error: {e}", "confidence": 0}
    
    def _resize_image(self, image_bytes: bytes, max_size: int = 1568) -> bytes:
        """Resize image to fit API limits."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert RGBA to RGB
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # Resize if too large
            w, h = img.size
            if max(w, h) > max_size:
                ratio = max_size / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            
            # Save to bytes
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            return buf.getvalue()
        except Exception:
            return image_bytes
    
    def detect_ingredients(self, image_bytes: bytes) -> List[Dict]:
        """Detect ingredients from image."""
        result = self.analyze_fridge_image(image_bytes)
        return result.get("detected_items", [])
    
    def get_recipe_suggestions(self, image_bytes: bytes) -> List[str]:
        """Get recipe suggestions based on image."""
        result = self.analyze_fridge_image(image_bytes)
        return result.get("suggested_recipes", [])
    
    def check_expiring_items(self, image_bytes: bytes) -> List[str]:
        """Check for expiring items in image."""
        result = self.analyze_fridge_image(image_bytes)
        return result.get("expiring_concerns", [])


# Singleton instance
_vision_service = None


def get_vision_service() -> VisionService:
    """Get or create vision service instance."""
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service


def analyze_image(image_bytes: bytes, context: str = "fridge") -> Dict:
    """Convenience function for image analysis."""
    service = get_vision_service()
    return service.analyze_fridge_image(image_bytes, context)
