"""
vision/vision_agent.py — Groq LLaMA Vision for fridge/pantry/bill photo analysis
Completely free - no Anthropic API key needed!
"""

import base64
import json
import re
import os
import io
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image


def analyse_grocery_image_groq(image_bytes: bytes, client, context: str = "fridge") -> Dict[str, Any]:
    """Analyse food/grocery/bill image using Groq LLaMA Vision - FREE"""
    try:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime = "image/jpeg"
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            mime = "image/png"
        elif image_bytes[:4] == b'RIFF':
            mime = "image/webp"

        # Different prompts based on context
        if context == "bill" or context == "receipt":
            prompt = """You are analysing a grocery bill/receipt. Extract ALL grocery items with their quantities and prices.

Return ONLY valid JSON:
{
    "detected_items": [
        {
            "name": "item name (lowercase)",
            "quantity": 1.0,
            "unit": "kg/g/pieces/liters",
            "price": 0.0,
            "category": "vegetables/fruits/dairy/proteins/grains"
        }
    ],
    "total_amount": 0.0,
    "store_name": "store name if visible",
    "date": "date if visible",
    "confidence": 0.95
}

Return ONLY the JSON, no explanation."""
        else:
            prompt = f"""Expert kitchen AI analysing a {context} image.
Identify ALL visible food items with expiry risk assessment.

Return ONLY valid JSON:
{{
    "detected_items": [
        {{
            "name": "item name (lowercase)",
            "quantity": 1.0,
            "unit": "pieces/kg/grams/liters/bunch",
            "freshness": "fresh/good/use-soon/expiring",
            "expiry_risk": 0.0,
            "category": "vegetables/fruits/dairy/proteins/grains/condiments"
        }}
    ],
    "scene_description": "one sentence",
    "suggested_recipes": ["recipe1", "recipe2"],
    "expiring_concerns": ["item that needs attention"],
    "confidence": 0.95
}}

Expiry risk: 0.0=very fresh, 0.5=use this week, 1.0=use today
Return ONLY the JSON, no explanation."""

        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=1500, 
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(raw)
            
        result["model_used"] = "llama-3.2-11b-vision-preview"
        return result
    except Exception as e:
        return {"detected_items": [], "scene_description": f"Vision error: {e}",
                "suggested_recipes": [], "expiring_concerns": [], "confidence": 0.0}


def analyse_food_image(image_bytes: bytes, groq_client, context: str = "fridge") -> Dict[str, Any]:
    """Analyse image using Groq Vision (free)."""
    if groq_client:
        return analyse_grocery_image_groq(image_bytes, groq_client, context)
    return {"detected_items": [], "scene_description": "No vision model available.",
            "suggested_recipes": [], "expiring_concerns": [], "confidence": 0.0, "model_used": "none"}


def process_bill_image(image_bytes: bytes, db, groq_client) -> Tuple[Dict, str]:
    """Process a grocery bill/receipt and add items to inventory."""
    result = analyse_grocery_image_groq(image_bytes, groq_client, context="bill")
    
    if not result.get("detected_items"):
        return result, "⚠️ No items detected on the bill. Try a clearer photo."
    
    added = []
    failed = []
    total_price = result.get("total_amount", 0)
    
    for item in result["detected_items"]:
        name = item.get("name", "").lower().strip()
        if not name:
            continue
        
        qty = float(item.get("quantity", 1))
        unit = item.get("unit", "pieces")
        category = item.get("category", "other")
        price = item.get("price", 0)
        
        # Determine if perishable
        is_perishable = category in ("vegetables", "fruits", "dairy", "proteins")
        
        try:
            success = db.add_grocery(
                item_name=name, quantity=qty, unit=unit,
                category=category, is_perishable=is_perishable,
                days_until_expiry=7 if is_perishable else None
            )
            if success:
                added.append(f"{name.title()} (₹{price:.0f})" if price else name.title())
            else:
                failed.append(name)
        except Exception:
            failed.append(name)
    
    lines = [
        f"📸 **Processed Bill** - {len(result['detected_items'])} items detected",
        "",
    ]
    
    if added:
        lines.append("✅ **Added to pantry:**")
        for item in added[:10]:
            lines.append(f"  • {item}")
    
    if failed:
        lines.append(f"\n❌ Failed to add: {', '.join(failed[:3])}")
    
    if total_price > 0:
        lines.append(f"\n💰 **Total Bill Amount:** ₹{total_price:.0f}")
    
    if result.get("store_name"):
        lines.append(f"🏪 **Store:** {result['store_name']}")
    
    return result, "\n".join(lines)


def image_to_inventory(image_bytes: bytes, db, groq_client, context: str = "fridge") -> Tuple[Dict, str]:
    """Full pipeline: photo → detect → inventory → summary."""
    if context == "bill" or context == "receipt":
        return process_bill_image(image_bytes, db, groq_client)
    
    result = analyse_food_image(image_bytes, groq_client, context)

    if not result["detected_items"]:
        return result, "⚠️ No items detected. Try a clearer, better-lit photo."

    days_map = {"fresh": 7, "good": 5, "use-soon": 2, "expiring": 1}
    added, failed = [], []

    for item in result["detected_items"]:
        name = item.get("name", "").lower().strip()
        if not name:
            continue
        try:
            qty = float(str(item.get("quantity", "1")))
        except ValueError:
            qty = 1.0
        category = item.get("category", "other")
        freshness = item.get("freshness", "good")
        is_perishable = category in ("vegetables", "fruits", "dairy", "proteins")
        try:
            success = db.add_grocery(
                item_name=name, quantity=qty, unit=item.get("unit", "pieces"),
                category=category, is_perishable=is_perishable,
                days_until_expiry=days_map.get(freshness, 5) if is_perishable else None
            )
            (added if success else failed).append(name)
        except Exception:
            failed.append(name)

    model = result.get("model_used", "AI")
    confidence_pct = result.get("confidence", 0) * 100

    lines = [
        f"📸 **Detected {len(result['detected_items'])} items** via {model} (confidence: {confidence_pct:.0f}%)",
        f"🔍 *{result['scene_description']}*",
        "",
    ]

    if added:
        # Sort by expiry risk
        expiry_items = [(i, i.get("expiry_risk", 0)) for i in result["detected_items"]
                        if i.get("name", "").lower() in added]
        expiry_items.sort(key=lambda x: x[1], reverse=True)

        lines.append("✅ **Added to pantry:**")
        for item, risk in expiry_items[:8]:
            badge = "🔴" if risk > 0.7 else "🟡" if risk > 0.3 else "🟢"
            lines.append(f"  {badge} {item['name'].title()} — {item.get('quantity', '?')} {item.get('unit', '')}")

    if result.get("expiring_concerns"):
        lines.append("\n⚠️ **Use soon:**")
        for e in result["expiring_concerns"]:
            lines.append(f"  🔴 {e}")

    if result.get("suggested_recipes"):
        lines.append("\n🍳 **You could make:**")
        for r in result["suggested_recipes"][:3]:
            lines.append(f"  • {r}")

    return result, "\n".join(lines)


def preprocess_image(image_bytes: bytes, max_size: int = 1568) -> Tuple[bytes, str]:
    """Resize image for API limits."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, "image/jpeg"


def render_image_input_ui(db, groq_client) -> Optional[str]:
    """Streamlit UI for photo input - supports fridge, pantry, and bill uploads."""
    import streamlit as st

    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                border-radius: 16px; padding: 2px; margin-bottom: 16px;">
        <div style="background: #0f172a; border-radius: 14px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <span style="font-size: 28px;">📸</span>
                <div>
                    <div style="font-weight: 700; color: #f97316;">Smart Scan</div>
                    <div style="font-size: 12px; color: #94a3b8;">Upload fridge photo or grocery bill</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    img_file = st.file_uploader(
        "Upload image", type=["jpg", "jpeg", "png", "webp"],
        key="food_image_upload", label_visibility="collapsed"
    )

    if img_file:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(img_file, caption="Your image", use_container_width=True)
        with col2:
            context = st.selectbox(
                "What type of image is this?",
                ["fridge", "pantry shelf", "ingredients on counter", "grocery bag", "bill/receipt", "cooked dish"],
                key="img_context"
            )
            
            if st.button("🔍 Scan & Add to Pantry", use_container_width=True, type="primary"):
                raw_bytes = img_file.read()
                img_bytes, _ = preprocess_image(raw_bytes)
                with st.spinner("🤖 Analysing with AI Vision..."):
                    result, summary = image_to_inventory(img_bytes, db, groq_client, context)
                st.markdown(summary)
                st.session_state["last_vision_result"] = result
                return summary
    return None
