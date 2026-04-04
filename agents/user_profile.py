"""
agents/user_profile.py — Per-user persistent profile with incremental learning.
Each user_id gets their own profile.db under data/users/<user_id>/
"""

import json
import sqlite3
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from database.user_db_manager import get_user_connection


class UserProfileDB:
    """Per-user profile store. Pass user_id for full isolation."""

    def __init__(self, user_id: str = "default", db_path: str = None):
        self.user_id = user_id
        if db_path:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
        else:
            self.conn = get_user_connection(user_id, "user_profile.db")
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS interaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent TEXT,
                cuisine TEXT,
                rating INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def get(self, key: str, default=None):
        row = self.conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (key,)
        ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return row[0]
        return default

    def set(self, key: str, value, confidence: float = 1.0):
        self.conn.execute(
            "INSERT OR REPLACE INTO user_profile (key, value, confidence, updated_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), confidence, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_full_profile(self) -> Dict[str, Any]:
        rows = self.conn.execute("SELECT key, value FROM user_profile").fetchall()
        profile = {}
        for key, value in rows:
            try:
                profile[key] = json.loads(value)
            except Exception:
                profile[key] = value
        return profile

    def log_interaction(self, intent: str, cuisine: str = "", rating: int = 0):
        self.conn.execute(
            "INSERT INTO interaction_log (intent, cuisine, rating) VALUES (?, ?, ?)",
            (intent, cuisine, rating)
        )
        self.conn.commit()

    def get_cuisine_history(self, limit: int = 20) -> List[str]:
        rows = self.conn.execute(
            "SELECT cuisine FROM interaction_log WHERE cuisine != '' ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [r[0] for r in rows]

    def clear(self):
        self.conn.execute("DELETE FROM user_profile")
        self.conn.commit()

    def close(self):
        pass


# ── Regex fast-pass ──────────────────────────────────────────────────────────

def _regex_extract_profile(message: str) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    m = message.lower().strip()

    if re.search(r"\bi'?m\s+(a\s+)?vegan\b|i\s+eat\s+vegan|vegan\s+diet|strictly\s+vegan", m):
        updates["diet_type"] = "vegan"
    elif re.search(r"\bi'?m\s+(a\s+)?vegetarian\b|i\s+eat\s+vegetarian|vegetarian\s+diet|no\s+meat", m):
        updates["diet_type"] = "vegetarian"
    elif re.search(r"\bi'?m\s+(on\s+)?keto\b|keto\s+diet|ketogenic", m):
        updates["diet_type"] = "keto"
    elif re.search(r"\bnon[\s-]?veg(etarian)?\b|i\s+eat\s+meat|i\s+eat\s+non[\s-]?veg", m):
        updates["diet_type"] = "non-vegetarian"

    if re.search(r"(goal|trying|want)\s+(is\s+)?(to\s+)?(lose|losing)\s+weight|weight\s+loss", m):
        updates["fitness_goal"] = "weight_loss"
    elif re.search(r"(build|gain|grow)\s+muscle|muscle\s+gain|bulking", m):
        updates["fitness_goal"] = "muscle_gain"

    cuisine_map = {
        "indian": "Indian", "italian": "Italian", "chinese": "Chinese",
        "mexican": "Mexican", "mediterranean": "Mediterranean",
        "thai": "Thai", "japanese": "Japanese", "korean": "Korean",
    }
    for key, val in cuisine_map.items():
        if re.search(rf"prefer\s+{key}|like\s+{key}\s+(food|cuisine|recipes?)", m):
            updates.setdefault("cuisine_preferences", [])
            if val not in updates["cuisine_preferences"]:
                updates["cuisine_preferences"].append(val)

    inr_pattern = r"(₹|inr|rupees?|set\s+currency\s+(to\s+)?(inr|₹|rupees?))"
    if re.search(inr_pattern, m):
        budget_match = re.search(r"budget\s+(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(rupees?|₹|inr)", m)
        amount = float(budget_match.group(1) or budget_match.group(2)) if budget_match else None
        bp: Dict[str, Any] = {"currency": "INR", "level": "medium"}
        if amount:
            bp["amount"] = amount
        updates["budget_preference"] = bp

    allergen_match = re.findall(
        r"allerg(ic|y)\s+to\s+([\w\s,]+?)(?:\.|,|and|$)|"
        r"can'?t\s+eat\s+([\w\s,]+?)(?:\.|,|and|$)",
        m
    )
    if allergen_match:
        allergens = []
        for groups in allergen_match:
            raw = " ".join(g for g in groups if g).strip()
            for token in re.split(r"[,\s]+", raw):
                token = token.strip()
                if token and len(token) > 2:
                    allergens.append(token)
        if allergens:
            updates["allergies"] = allergens

    conditions = []
    if re.search(r"\bdiabetes\b|\bdiabetic\b", m):
        conditions.append("diabetes")
    if re.search(r"\bhypertension\b|\bhigh\s+blood\s+pressure\b", m):
        conditions.append("hypertension")
    if conditions:
        updates["health_conditions"] = conditions

    cal_match = re.search(
        r"(\d{3,4})\s*(kcal|calories?)\s*(per\s+meal|a\s+meal)?|"
        r"(under|below)\s+(\d{3,4})\s*(kcal|calories?)", m
    )
    if cal_match:
        raw_val = cal_match.group(1) or cal_match.group(5)
        if raw_val:
            updates["calorie_goal"] = int(raw_val)

    return updates


def profile_extraction_agent(
    user_message: str,
    conversation_history: list,
    profile_db: UserProfileDB,
    client,
) -> Dict[str, Any]:
    current_profile = profile_db.get_full_profile()

    regex_updates = _regex_extract_profile(user_message)
    for key, value in regex_updates.items():
        if value is not None and value != "" and value != [] and value != {}:
            if key in ("cuisine_preferences", "allergies", "health_conditions", "avoid_ingredients"):
                existing = current_profile.get(key, [])
                if isinstance(existing, list) and isinstance(value, list):
                    merged = list(dict.fromkeys(existing + value))
                    profile_db.set(key, merged)
                else:
                    profile_db.set(key, value)
            else:
                profile_db.set(key, value)

    current_profile = profile_db.get_full_profile()

    recent = conversation_history[-6:] if conversation_history else []
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}" for m in recent
    ) if recent else "No history."

    prompt = f"""Extract user preferences from this message for a cooking assistant.

Current profile: {json.dumps(current_profile, indent=2) if current_profile else "Empty"}
User message: "{user_message}"
Recent conversation: {history_text}

Extract ONLY explicitly stated NEW preferences NOT already in the current profile:
- diet_type: vegetarian/vegan/non-vegetarian/pescatarian/keto/paleo
- fitness_goal: weight_loss/muscle_gain/maintenance/endurance
- cuisine_preferences: list of cuisines
- allergies: list of allergens
- health_conditions: list
- protein_focus: true/false
- avoid_ingredients: list
- cooking_time_preference: quick/medium/any
- budget_preference: dict with level and currency (INR/USD) and optional amount
- calorie_goal: number per meal
- servings_preference: number
- skill_level: beginner/intermediate/advanced

Return ONLY JSON with NEW/CHANGED values. Empty {{}} if nothing new."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
        updates = json.loads(raw)
        for key, value in updates.items():
            if value is not None and value != "" and value != [] and value != {}:
                if key in regex_updates:
                    continue
                if key in ("cuisine_preferences", "allergies", "health_conditions", "avoid_ingredients"):
                    existing = current_profile.get(key, [])
                    if isinstance(existing, list) and isinstance(value, list):
                        merged = list(dict.fromkeys(existing + value))
                        profile_db.set(key, merged)
                    else:
                        profile_db.set(key, value)
                else:
                    profile_db.set(key, value)
    except Exception:
        pass

    return profile_db.get_full_profile()


def get_profile_context_string(profile: Dict[str, Any]) -> str:
    if not profile:
        return "No preferences stored yet."
    lines = ["📋 USER PROFILE:"]
    mapping = {
        "diet_type":               ("Diet",         lambda v: v),
        "fitness_goal":            ("Goal",         lambda v: v.replace("_", " ")),
        "cuisine_preferences":     ("Cuisines",     lambda v: ", ".join(v) if isinstance(v, list) else v),
        "allergies":               ("Allergies",    lambda v: ", ".join(v) if isinstance(v, list) else v),
        "health_conditions":       ("Health",       lambda v: ", ".join(v) if isinstance(v, list) else v),
        "protein_focus":           ("High Protein", lambda v: "Yes" if v else "No"),
        "avoid_ingredients":       ("Avoid",        lambda v: ", ".join(v) if isinstance(v, list) else v),
        "cooking_time_preference": ("Cook Time",    lambda v: v),
        "budget_preference":       ("Budget",       lambda v: (
            f"{v.get('level', v)} ({v.get('currency', 'USD')})"
            + (f" — {v.get('currency','$')}{v.get('amount','')}" if v.get('amount') else "")
            if isinstance(v, dict) else str(v)
        )),
        "calorie_goal":            ("Calorie Goal", lambda v: f"{v} kcal/meal"),
        "servings_preference":     ("Servings",     lambda v: f"{v} people"),
        "skill_level":             ("Skill Level",  lambda v: v),
    }
    for key, (label, fmt) in mapping.items():
        val = profile.get(key)
        if val is not None and val != "" and val != [] and val != {}:
            try:
                lines.append(f"  • {label}: {fmt(val)}")
            except Exception:
                lines.append(f"  • {label}: {val}")
    return "\n".join(lines) if len(lines) > 1 else "No preferences stored yet."


def get_diet_constraints_string(profile: Dict[str, Any]) -> str:
    constraints = []
    diet = profile.get("diet_type", "")
    if diet:
        diet_l = diet.lower()
        if diet_l == "vegan":
            constraints.append("VEGAN — NO meat, dairy, eggs, honey, or any animal products")
        elif "vegetarian" in diet_l and "non" not in diet_l:
            constraints.append("VEGETARIAN — NO meat, chicken, fish, seafood, or any animal flesh")
        elif diet_l == "keto":
            constraints.append("KETO — Under 20g net carbs, high fat, moderate protein")
        else:
            constraints.append(f"Diet: {diet}")

    allergies = profile.get("allergies", [])
    if allergies:
        constraints.append(f"ALLERGIES (NEVER USE): {', '.join(allergies if isinstance(allergies, list) else [allergies])}")

    avoid = profile.get("avoid_ingredients", [])
    if avoid:
        constraints.append(f"AVOID: {', '.join(avoid if isinstance(avoid, list) else [avoid])}")

    health = profile.get("health_conditions", [])
    if health:
        hl = [h.lower() for h in (health if isinstance(health, list) else [health])]
        if "diabetes" in hl:
            constraints.append("DIABETIC — Low GI, limit sugar and refined carbs, max 45g carbs/meal")
        if "hypertension" in hl:
            constraints.append("HYPERTENSION — Low sodium (<1500mg/day)")

    if profile.get("protein_focus"):
        constraints.append("HIGH PROTEIN — 30g+ protein per serving")

    goal = profile.get("fitness_goal", "")
    if goal == "weight_loss":
        constraints.append("WEIGHT LOSS — Keep calories ≤500/meal, high fiber")
    elif goal == "muscle_gain":
        constraints.append("MUSCLE GAIN — High protein, sufficient complex carbs")

    budget = profile.get("budget_preference", {})
    if isinstance(budget, dict) and budget.get("currency") == "INR":
        constraints.append("CURRENCY: Indian Rupees (₹)")

    return "\n".join(f"  ⚠️ {c}" for c in constraints) if constraints else "None"


def _currency(profile: dict) -> str:
    b = profile.get("budget_preference", {})
    if isinstance(b, dict) and b.get("currency") == "INR":
        return "₹"
    if isinstance(b, str) and "INR" in b.upper():
        return "₹"
    return "₹"  # Default to INR for Indian app
