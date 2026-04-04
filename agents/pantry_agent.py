"""agents/pantry_agent.py — Complete pantry management: add, view, remove."""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from agents.base import BaseAgent
from agents.state import AgentState

# ---------------------------------------------------------------------------
# Canonical name normalisation
# ---------------------------------------------------------------------------
CANONICAL = {
    "panner": "paneer", "panear": "paneer", "panneer": "paneer",
    "spinch": "spinach", "spinnach": "spinach",
    "tomatoes": "tomato", "tomatoe": "tomato",
    "onions": "onion", "potatoes": "potato",
    "basmati rice": "rice", "basmati": "rice",
    "curd": "yogurt", "dahi": "yogurt",
    "dals": "dal", "lentils": "dal",
    "chillies": "chilli", "chilies": "chilli", "chili": "chilli",
    "capsicums": "capsicum", "bell pepper": "capsicum",
    "ladies finger": "okra", "bhindi": "okra",
    "brinjal": "eggplant", "baingan": "eggplant",
    "methi": "fenugreek", "dhania": "coriander",
    "jeera": "cumin", "haldi": "turmeric",
    "atta": "wheat flour", "maida": "all-purpose flour",
    "sarson": "mustard", "rai": "mustard seeds",
}

# ---------------------------------------------------------------------------
# Diet restrictions
# ---------------------------------------------------------------------------
DIET_RESTRICTIONS = {
    "vegetarian": {
        "forbidden": [
            "chicken", "fish", "shrimp", "prawn", "meat", "beef", "pork",
            "lamb", "mutton", "turkey", "duck", "seafood", "salmon", "tuna",
            "bacon", "sausage", "anchovy", "lard",
        ],
        "warning": "Not allowed in a vegetarian diet",
    },
    "vegan": {
        "forbidden": [
            "chicken", "fish", "shrimp", "meat", "beef", "pork", "egg", "eggs",
            "milk", "cheese", "paneer", "curd", "yogurt", "ghee", "butter",
            "honey", "cream", "whey", "casein", "lactose",
        ],
        "warning": "Not allowed in a vegan diet",
    },
}

# Category → expiry days (sensible defaults)
CATEGORY_EXPIRY = {
    "vegetables": 5,
    "fruits": 5,
    "dairy": 4,
    "proteins": 3,
    "grains": 180,
    "spices": 365,
    "oils": 180,
    "other": 7,
}


def _canonical(name: str) -> str:
    n = name.lower().strip()
    return CANONICAL.get(n, n)


def _is_allowed_for_diet(item_name: str, profile: dict) -> Tuple[bool, str]:
    diet_type = profile.get("diet_type", "").lower()
    if not diet_type or diet_type not in DIET_RESTRICTIONS:
        return True, ""
    restrictions = DIET_RESTRICTIONS[diet_type]
    item_lower = item_name.lower()
    for forbidden in restrictions["forbidden"]:
        if forbidden in item_lower:
            return False, restrictions["warning"]
    return True, ""


# ---------------------------------------------------------------------------
# BUY-KEYWORD intent guard (fixes misrouting from general intent)
# ---------------------------------------------------------------------------
BUY_KEYWORDS = [
    "i bought", "i got", "purchased", "i have", "picked up",
    "i picked", "just bought", "bought some", "got some",
    "brought", "i added", "add to pantry", "add to my pantry",
]
VIEW_KEYWORDS = [
    "show pantry", "show my pantry", "view pantry", "what's in my pantry",
    "what do i have", "check pantry", "my pantry", "list pantry",
    "pantry status", "show inventory", "view inventory",
]
REMOVE_KEYWORDS = [
    "remove", "delete", "used up", "ran out", "finished", "consumed",
    "take out", "clear", "empty",
]


def detect_pantry_intent(query: str) -> Optional[str]:
    """
    Detect pantry intent from raw query text.
    Returns 'add_inventory', 'view_inventory', 'remove_inventory',
    'remove_all_inventory', or None.
    """
    q = query.lower()
    if any(kw in q for kw in BUY_KEYWORDS):
        return "add_inventory"
    if any(kw in q for kw in VIEW_KEYWORDS):
        return "view_inventory"
    if "clear pantry" in q or "empty pantry" in q or "remove all" in q:
        return "remove_all_inventory"
    if any(kw in q for kw in REMOVE_KEYWORDS):
        return "remove_inventory"
    return None


# ---------------------------------------------------------------------------
# PantryAgent
# ---------------------------------------------------------------------------
class PantryAgent(BaseAgent):
    """Manages pantry inventory: add, view, remove."""

    def __init__(self):
        super().__init__("📦 Pantry Agent")

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------
    def run(self, state: AgentState, db=None, client=None, **kwargs) -> AgentState:
        intent = state.get("intent", "")

        # Safety-net: re-detect intent if misclassified as "general"
        if intent == "general":
            detected = detect_pantry_intent(state.get("user_query", ""))
            if detected:
                intent = detected
                state["intent"] = detected

        if intent == "add_inventory":
            return self._add_items(state, client, db)
        elif intent == "remove_inventory":
            return self._remove_items(state, client, db)
        elif intent == "remove_all_inventory":
            return self._clear_pantry(state, db)
        elif intent == "view_inventory":
            return self._view_pantry(state, db)
        return state

    # ------------------------------------------------------------------
    # ADD
    # ------------------------------------------------------------------
    def _add_items(self, state: AgentState, client, db) -> AgentState:
        query = state.get("user_query", "")
        profile = state.get("user_profile", {})

        # --- LLM parse ---
        prompt = f"""Parse grocery items from this message: "{query}"

Return a JSON array ONLY — no markdown, no extra text:
[
  {{
    "name": "singular lowercase name",
    "quantity": 1.0,
    "unit": "kg|g|pieces|ml|l|cups|bunch",
    "category": "vegetables|fruits|dairy|proteins|grains|spices|oils|other",
    "is_perishable": true
  }}
]

Rules:
- Singular names: "tomato" not "tomatoes", "onion" not "onions"
- Vegetables/dairy/proteins/fruits → is_perishable: true
- Grains/spices/oils → is_perishable: false
- Detect quantity+unit from text (e.g. "500g" → quantity:500, unit:"g")
- If quantity not mentioned, default to 1 piece
- Return ONLY the JSON array, nothing else."""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=600,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            # Extract JSON array even if wrapped in extra text
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON array found in LLM response")
            items = json.loads(match.group())
        except Exception as e:
            state["assistant_message"] = (
                f"❌ Could not parse your groceries. Try: 'I bought 500g paneer and 1kg onions'\n\n"
                f"*Error: {e}*"
            )
            return state

        added, rejected, skipped = [], [], []

        for item in items:
            raw_name = item.get("name", "").lower().strip()
            name = _canonical(raw_name)
            if not name or len(name) < 2:
                continue

            # Diet check
            allowed, reason = _is_allowed_for_diet(name, profile)
            if not allowed:
                diet = profile.get("diet_type", "your diet")
                rejected.append(f"**{name.title()}** — {reason} ({diet})")
                continue

            qty    = float(item.get("quantity", 1))
            unit   = item.get("unit", "pieces")
            cat    = item.get("category", "other")
            is_per = bool(item.get("is_perishable", False))
            days   = CATEGORY_EXPIRY.get(cat, 7) if is_per else None

            success = db.add_grocery(
                item_name=name,
                quantity=qty,
                unit=unit,
                category=cat,
                is_perishable=is_per,
                days_until_expiry=days,
            )
            if success:
                added.append(f"{qty} {unit} **{name.title()}**")
            else:
                skipped.append(name.title())

        # Build response
        parts = []
        if added:
            parts.append("✅ **Added to pantry:**\n" + "\n".join(f"  • {a}" for a in added))

        if rejected:
            parts.append(
                "❌ **Rejected (diet restriction):**\n"
                + "\n".join(f"  • {r}" for r in rejected)
            )

        if skipped:
            parts.append(
                "⚠️ **Could not save:**\n"
                + "\n".join(f"  • {s}" for s in skipped)
            )

        if not added and not rejected and not skipped:
            parts.append(
                "❌ Could not parse any groceries.\n"
                "Try: *'I bought 500g paneer, 1kg spinach and 3 tomatoes'*"
            )

        # Expiry warning
        expiring = db.get_expiring_soon(days=3) if db else []
        if expiring:
            names = [e["item_name"].title() for e in expiring[:3]]
            parts.append(f"\n⚠️ **Use soon (≤3 days):** {', '.join(names)}")

        state["assistant_message"] = "\n\n".join(parts)
        return state

    # ------------------------------------------------------------------
    # VIEW
    # ------------------------------------------------------------------
    def _view_pantry(self, state: AgentState, db) -> AgentState:
        groceries = db.get_all_groceries() if db else []

        if not groceries:
            state["assistant_message"] = (
                "📦 **Your pantry is empty.**\n\n"
                "Tell me what you bought and I'll track everything!\n"
                "_Example: 'I bought 500g paneer, 1kg spinach and 3 tomatoes'_"
            )
            return state

        # Group by category
        CAT_ORDER = [
            ("🥬 Vegetables", "vegetables"),
            ("🍎 Fruits",     "fruits"),
            ("🧀 Dairy",      "dairy"),
            ("🥩 Proteins",   "proteins"),
            ("🌾 Grains",     "grains"),
            ("🧂 Spices & Oils", "spices"),
            ("🧂 Spices & Oils", "oils"),
            ("📦 Other",      "other"),
        ]
        # Build deduplicated ordered mapping
        seen_cats = {}
        for label, key in CAT_ORDER:
            if key not in seen_cats:
                seen_cats[key] = label

        buckets: Dict[str, list] = {label: [] for label in seen_cats.values()}

        now = datetime.now()
        total_items = len(groceries)
        expiring_count = 0

        for g in groceries:
            raw_cat = (g.get("category") or "other").lower()
            label = seen_cats.get(raw_cat, "📦 Other")

            name = g["item_name"].title()
            qty  = g["quantity"]
            unit = g["unit"]

            # Expiry badge
            badge = "•"
            suffix = ""
            if g.get("expiry_date"):
                try:
                    expiry = datetime.fromisoformat(str(g["expiry_date"]))
                    days_left = (expiry - now).days
                    if days_left < 0:
                        badge, suffix = "🔴", " *(expired!)*"
                        expiring_count += 1
                    elif days_left == 0:
                        badge, suffix = "🔴", " *(expires today!)*"
                        expiring_count += 1
                    elif days_left <= 3:
                        badge, suffix = "🟡", f" *({days_left}d left)*"
                        expiring_count += 1
                    else:
                        badge, suffix = "🟢", ""
                except Exception:
                    pass

            buckets[label].append(f"{badge} {name} — {qty} {unit}{suffix}")

        lines = [f"## 📦 Your Pantry  ·  {total_items} items"]
        if expiring_count:
            lines.append(f"⚠️ *{expiring_count} item(s) need attention*\n")
        else:
            lines.append("")

        for label, items in buckets.items():
            if items:
                lines.append(f"**{label}**")
                lines.extend(f"  {row}" for row in items)
                lines.append("")

        lines.append(
            "_🟢 Fresh  🟡 Use soon  🔴 Urgent/Expired_\n\n"
            "_Say 'remove spinach' to delete an item, or 'clear pantry' to reset._"
        )

        state["assistant_message"] = "\n".join(lines)
        return state

    # ------------------------------------------------------------------
    # REMOVE (specific items)
    # ------------------------------------------------------------------
    def _remove_items(self, state: AgentState, client, db) -> AgentState:
        query = state.get("user_query", "")
        pantry = [g["item_name"] for g in (db.get_all_groceries() if db else [])]

        if not pantry:
            state["assistant_message"] = "📦 Your pantry is already empty — nothing to remove."
            return state

        prompt = f"""Extract item names to remove from this message: "{query}"
Known pantry items: {pantry}

Match the user's items to the known pantry items (handle plurals and typos).
Return ONLY a JSON array of item names to remove, e.g.: ["spinach", "tomato"]
Return [] if nothing matches."""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            to_remove = json.loads(match.group()) if match else []
        except Exception as e:
            state["assistant_message"] = f"❌ Could not parse removal request: {e}"
            return state

        if not to_remove:
            state["assistant_message"] = (
                "❌ Couldn't find matching items in your pantry.\n\n"
                f"Your pantry has: {', '.join(p.title() for p in pantry[:8])}"
                + (" ..." if len(pantry) > 8 else "")
            )
            return state

        removed, not_found = [], []

        for item in to_remove:
            canonical = _canonical(item.lower().strip())
            if db.delete_grocery(canonical):
                removed.append(canonical.title())
            elif db.delete_grocery(item.lower()):
                removed.append(item.title())
            else:
                not_found.append(item.title())

        parts = []
        if removed:
            parts.append(f"✅ **Removed:** {', '.join(removed)}")
        if not_found:
            parts.append(f"⚠️ **Not found:** {', '.join(not_found)}")

        remaining = db.get_all_groceries() if db else []
        parts.append(f"_📦 {len(remaining)} item(s) remaining in pantry._")

        state["assistant_message"] = "\n\n".join(parts)
        return state

    # ------------------------------------------------------------------
    # CLEAR ALL
    # ------------------------------------------------------------------
    def _clear_pantry(self, state: AgentState, db) -> AgentState:
        if db:
            count = len(db.get_all_groceries())
            db.clear_inventory()
            state["assistant_message"] = (
                f"🗑️ **Pantry cleared!** {count} item(s) removed.\n\n"
                "_Tell me what you buy next and I'll start tracking again._"
            )
        else:
            state["assistant_message"] = "❌ Database not available."
        return state
