"""vision/fridge_scanner.py — Groq Vision based Fridge Scanner"""

import json
import re
import io
import base64
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageEnhance

# ── Same DIET/HEALTH rules as before ──────────────────────────────────────

DIET_FORBIDDEN: Dict[str, List[str]] = {
    "vegetarian": [
        "chicken", "beef", "pork", "fish", "mutton", "lamb", "prawn",
        "shrimp", "bacon", "meat", "salmon", "tuna", "seafood", "turkey",
        "duck", "sausage", "pepperoni", "ham", "anchovies", "crab",
        "lobster", "octopus", "squid", "clams", "mussels", "oysters",
    ],
    "vegan": [
        "chicken", "beef", "pork", "fish", "mutton", "lamb", "prawn",
        "shrimp", "bacon", "meat", "salmon", "tuna", "seafood", "turkey",
        "egg", "eggs", "milk", "cheese", "paneer", "curd", "yogurt",
        "ghee", "butter", "honey", "cream", "whey", "casein",
        "mayonnaise", "ice cream", "gelato", "custard", "buttermilk",
    ],
    "keto": [
        "rice", "pasta", "bread", "sugar", "flour", "potato", "corn",
        "oats", "cereal", "juice", "soda", "beer", "noodles", "wheat",
        "sweet potato", "banana", "mango", "grapes", "apple", "orange",
        "pineapple", "dates", "honey", "maple syrup",
    ],
    "jain": [
        "chicken", "beef", "pork", "fish", "meat", "egg", "eggs",
        "onion", "garlic", "potato", "carrot", "beet", "radish",
        "turnip", "leek", "scallion", "shallot", "chive",
    ],
    "non_vegetarian": [],
}

HEALTH_FORBIDDEN: Dict[str, List[str]] = {
    "diabetes": [
        "sugar", "ice cream", "candy", "chocolate", "cake", "pastry",
        "cookies", "soda", "juice", "jam", "syrup", "honey",
        "condensed milk", "sweet", "dessert", "pudding", "donut",
        "white bread", "white rice", "corn syrup", "cola", "sprite",
        "sweetened yogurt", "milkshake", "brownie", "muffin",
    ],
    "hypertension": [
        "salt", "pickle", "soy sauce", "processed meat", "bacon",
        "salami", "sausage", "canned soup", "chips", "namkeen",
        "papad", "instant noodles", "ketchup", "hot sauce",
    ],
    "lactose_intolerance": [
        "milk", "cheese", "butter", "cream", "ghee", "paneer",
        "yogurt", "curd", "ice cream", "whey", "buttermilk",
    ],
    "gluten_intolerance": [
        "bread", "wheat", "flour", "pasta", "noodles", "beer",
        "soy sauce", "biscuit", "cookies", "cake", "cereal",
    ],
    "cholesterol": [
        "egg", "eggs", "butter", "ghee", "cream", "full fat milk",
        "red meat", "organ meat", "liver", "shrimp", "prawn",
    ],
    "uric_acid": [
        "red meat", "beef", "pork", "organ meat", "liver",
        "anchovies", "sardines", "beer", "mackerel",
    ],
}

CONDITION_KEY_MAP = {
    "diabetes": "diabetes", "diabetic": "diabetes",
    "blood_pressure": "hypertension", "high_blood_pressure": "hypertension",
    "hypertension": "hypertension", "bp": "hypertension",
    "lactose_intolerance": "lactose_intolerance", "lactose": "lactose_intolerance",
    "gluten_intolerance": "gluten_intolerance", "gluten": "gluten_intolerance",
    "celiac": "gluten_intolerance", "coeliac": "gluten_intolerance",
    "high_cholesterol": "cholesterol", "cholesterol": "cholesterol",
    "uric_acid": "uric_acid", "gout": "uric_acid",
}

CATEGORY_EXPIRY_DAYS: Dict[str, int] = {
    "vegetables": 5, "fruits": 5, "dairy": 4, "meat_seafood": 2,
    "proteins": 3, "beverages": 7, "condiments": 30, "grains": 180,
    "snacks": 14, "frozen": 60, "leftovers": 3, "other": 7,
}


# ── Dietary Filter ─────────────────────────────────────────────────────────

def check_item_against_profile(
    item_name: str,
    profile: Dict[str, Any],
) -> Tuple[bool, str, str]:
    name_lower = item_name.lower().strip()

    diet_type = str(profile.get("diet_type", "")).lower().strip()
    if diet_type and diet_type in DIET_FORBIDDEN:
        for forbidden in DIET_FORBIDDEN[diet_type]:
            if forbidden in name_lower:
                return False, f"Not suitable for your **{diet_type}** diet", "diet"

    health_conditions = profile.get("health_conditions", [])
    if isinstance(health_conditions, str):
        health_conditions = [h.strip() for h in health_conditions.split(",") if h.strip()]
    for condition in health_conditions:
        raw_key = condition.lower().replace(" ", "_").replace("-", "_")
        condition_key = CONDITION_KEY_MAP.get(raw_key, raw_key)
        if condition_key in HEALTH_FORBIDDEN:
            for forbidden in HEALTH_FORBIDDEN[condition_key]:
                if forbidden in name_lower:
                    return False, f"Not recommended for your **{condition}** condition", "health"

    allergies = profile.get("allergies", [])
    if isinstance(allergies, str):
        allergies = [a.strip().lower() for a in allergies.split(",") if a.strip()]
    for allergy in allergies:
        if allergy.lower() in name_lower:
            return False, f"You have an **allergy** to {allergy}", "allergy"

    return True, "", ""


# ── Groq Vision Scan ───────────────────────────────────────────────────────

def scan_fridge_image(
    image_bytes: bytes,
    groq_client,
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    profile = user_profile or {}
    diet_ctx = profile.get("diet_type", "")
    conditions = profile.get("health_conditions", [])
    if isinstance(conditions, str):
        conditions = [c.strip() for c in conditions.split(",") if c.strip()]
    allergies = profile.get("allergies", [])
    if isinstance(allergies, str):
        allergies = [a.strip() for a in allergies.split(",") if a.strip()]

    profile_hint = ""
    if diet_ctx:
        profile_hint += f" The user follows a {diet_ctx} diet."
    if conditions:
        profile_hint += f" They have: {', '.join(conditions)}."
    if allergies:
        profile_hint += f" Allergies: {', '.join(allergies)}."

    # Convert to base64
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    prompt = f"""You are an expert kitchen AI scanning a food/fridge image.{profile_hint}

Identify EVERY visible food and drink item. Be thorough:
- Vegetables, fruits, leftovers in containers
- Dairy (milk, yogurt, cheese, butter, paneer)
- Beverages (juice, soda, water, cold drinks)
- Condiments, sauces, jams, pickles
- Eggs, meat, fish, seafood
- Any packaged items you can identify

Return ONLY this JSON (no markdown, no explanation):

{{
    "detected_items": [
        {{
            "name": "item name lowercase singular",
            "quantity": 1.0,
            "unit": "pieces/kg/grams/liters/ml/bottles/cartons/cans",
            "category": "vegetables/fruits/dairy/meat_seafood/proteins/beverages/condiments/grains/snacks/frozen/leftovers/other",
            "freshness": "fresh/good/use-soon/expiring",
            "expiry_risk": 0.0
        }}
    ],
    "scene_description": "one sentence summary",
    "suggested_recipes": ["recipe1", "recipe2", "recipe3"],
    "nutrition_tips": ["tip1", "tip2"],
    "confidence": 0.90
}}

Rules:
- expiry_risk: 0.0=very fresh, 0.5=use this week, 1.0=use today
- Estimate quantities from what is visible
- Return ONLY valid JSON, nothing else."""

    try:
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw).strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        vision_result = json.loads(json_match.group() if json_match else raw)
        vision_result["model_used"] = "llama-4-scout (Groq)"

    except json.JSONDecodeError as e:
        return _empty_result(f"Could not parse response as JSON: {e}")
    except Exception as e:
        return _empty_result(f"Groq Vision API error: {e}")

    # Apply dietary filter
    allowed_items: List[Dict] = []
    blocked_items: List[Dict] = []

    for item in vision_result.get("detected_items", []):
        name = item.get("name", "").lower().strip()
        if not name:
            continue
        is_allowed, reason, restriction_type = check_item_against_profile(name, profile)
        if is_allowed:
            allowed_items.append(item)
        else:
            blocked_items.append({
                **item,
                "blocked_reason": reason,
                "restriction_type": restriction_type
            })

    return {
        "detected_items":    vision_result.get("detected_items", []),
        "allowed_items":     allowed_items,
        "blocked_items":     blocked_items,
        "scene_description": vision_result.get("scene_description", ""),
        "suggested_recipes": vision_result.get("suggested_recipes", []),
        "nutrition_tips":    vision_result.get("nutrition_tips", []),
        "confidence":        vision_result.get("confidence", 0.0),
        "model_used":        "llama-4-scout (Groq)",
    }


def _empty_result(error_msg: str) -> Dict[str, Any]:
    return {
        "detected_items": [], "allowed_items": [], "blocked_items": [],
        "scene_description": error_msg, "suggested_recipes": [],
        "nutrition_tips": [], "confidence": 0.0,
        "model_used": "llama-4-scout (Groq)", "error": error_msg,
    }


# ── Add to Pantry ──────────────────────────────────────────────────────────

def add_fridge_items_to_pantry(
    scan_result: Dict[str, Any],
    db,
) -> Tuple[List[str], List[str]]:
    days_map = {"fresh": 7, "good": 5, "use-soon": 2, "expiring": 1}
    perishable_categories = {"vegetables", "fruits", "dairy", "meat_seafood", "leftovers", "proteins"}
    added, failed = [], []

    for item in scan_result.get("allowed_items", []):
        name = item.get("name", "").lower().strip()
        if not name:
            continue
        try:
            qty = float(str(item.get("quantity", 1)))
        except (ValueError, TypeError):
            qty = 1.0

        category = item.get("category", "other")
        freshness = item.get("freshness", "good")
        is_perishable = category in perishable_categories
        days = days_map.get(freshness, 5) if is_perishable else None

        try:
            success = db.add_grocery(
                item_name=name,
                quantity=qty,
                unit=item.get("unit", "pieces"),
                category=category,
                is_perishable=is_perishable,
                days_until_expiry=days,
            )
            (added if success else failed).append(name)
        except Exception:
            failed.append(name)

    return added, failed


# ── Summary Builder ────────────────────────────────────────────────────────

def build_scan_summary(
    scan_result: Dict[str, Any],
    added: List[str],
    failed: List[str],
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    allowed = scan_result.get("allowed_items", [])
    blocked = scan_result.get("blocked_items", [])
    total_detected = len(scan_result.get("detected_items", []))
    confidence_pct = int(scan_result.get("confidence", 0) * 100)
    model = scan_result.get("model_used", "Llama 4 Scout")

    lines = [
        f"## 📸 Fridge Scan Complete",
        f"*{scan_result.get('scene_description', '')}*",
        f"",
        f"🤖 **{total_detected} items detected** via {model} · {confidence_pct}% confidence",
        f"",
    ]

    if added:
        lines.append(f"### ✅ Added to Pantry ({len(added)} items)")
        item_map = {i["name"]: i for i in allowed}
        for name in added:
            item = item_map.get(name, {})
            risk = item.get("expiry_risk", 0)
            badge = "🔴" if risk > 0.7 else "🟡" if risk > 0.3 else "🟢"
            lines.append(f"  {badge} **{name.title()}** — {item.get('quantity','?')} {item.get('unit','')}")

    if failed:
        lines.append(f"\n⚠️ *Could not save: {', '.join(f.title() for f in failed[:3])}*")

    if blocked:
        lines.append(f"\n### 🚫 Not Added — Dietary Restrictions ({len(blocked)} items)")
        by_type: Dict[str, list] = {}
        for b in blocked:
            by_type.setdefault(b.get("restriction_type", "other"), []).append(b)
        icons = {"diet": "🥗", "health": "🏥", "allergy": "⚠️"}
        for rtype, items in by_type.items():
            icon = icons.get(rtype, "🚫")
            lines.append(f"\n  **{icon} {rtype.title()} restriction:**")
            for b in items:
                lines.append(f"  • ~~{b.get('name','').title()}~~ — {b.get('blocked_reason','Restricted')}")

    recipes = scan_result.get("suggested_recipes", [])
    if recipes:
        lines.append(f"\n### 🍳 You can make with these items:")
        for r in recipes[:3]:
            lines.append(f"  • {r}")

    tips = scan_result.get("nutrition_tips", [])
    if tips:
        lines.append(f"\n### 💡 Nutrition Tips")
        for tip in tips[:2]:
            lines.append(f"  • {tip}")

    expiring = [i for i in allowed if i.get("expiry_risk", 0) > 0.5]
    if expiring:
        lines.append(f"\n### ⏰ Use Soon:")
        for i in expiring:
            lines.append(f"  🔴 **{i['name'].title()}** — use within 1-2 days")

    lines += ["", "---", "_🟢 Fresh  🟡 Use this week  🔴 Use today_"]
    return "\n".join(lines)


# ── Main Pipeline ──────────────────────────────────────────────────────────

def fridge_scan_pipeline(
    image_bytes: bytes,
    db,
    groq_client,
    user_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    processed = _preprocess_image(image_bytes)
    scan_result = scan_fridge_image(processed, groq_client, user_profile)

    if not scan_result.get("detected_items"):
        error = scan_result.get("error", "")
        hint = f"\n\n*Technical detail: {error}*" if error else ""
        return scan_result, (
            "## ⚠️ No Items Detected\n\n"
            "**Tips for a better scan:**\n"
            "1. Open the fridge door fully\n"
            "2. Ensure good lighting — turn on kitchen lights\n"
            "3. Shoot straight-on, not at an angle\n"
            "4. Include all shelves in the frame\n"
            "5. Use a clear, in-focus photo" + hint
        )

    added, failed = add_fridge_items_to_pantry(scan_result, db)
    summary = build_scan_summary(scan_result, added, failed, user_profile)
    return scan_result, summary


def _preprocess_image(image_bytes: bytes, max_size: int = 1568) -> bytes:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes