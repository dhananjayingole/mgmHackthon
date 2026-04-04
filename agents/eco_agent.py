
import re
from typing import Dict, Any, List
from agents.base import BaseAgent
from agents.state import AgentState


class EcoAgent(BaseAgent):
    """Calculates eco score and waste reduction metrics."""

    # CO₂ kg per 100g of ingredient
    CO2_MAP = {
        "beef": 2.5, "lamb": 2.0, "pork": 0.7, "chicken": 0.4,
        "fish": 0.3, "egg": 0.2, "milk": 0.15, "cheese": 0.5,
        "paneer": 0.4, "butter": 0.6, "ghee": 0.5,
        "rice": 0.12, "wheat": 0.08, "lentil": 0.05, "dal": 0.05,
        "chickpea": 0.06, "tofu": 0.1, "soy": 0.07,
        "spinach": 0.03, "tomato": 0.04, "onion": 0.03,
        "potato": 0.03, "carrot": 0.03, "oil": 0.15,
    }

    def __init__(self):
        super().__init__("🌱 Eco Agent")

    def run(self, state: AgentState, db=None, **kwargs) -> AgentState:
        ingredients = state.get("recipe_ingredients_structured", [])
        profile = state.get("user_profile", {})

        if not ingredients:
            return state

        score = 50  # Base score
        co2_total = 0.0
        tips = []

        # 1. Carbon from ingredients
        for ing in ingredients:
            name = ing.get("name", "").lower()
            grams = self._to_grams(ing.get("quantity", 100), ing.get("unit", "grams"))
            co2_per_100 = next((v for k, v in self.CO2_MAP.items() if k in name), 0.05)
            co2_total += co2_per_100 * grams / 100

        # Lower CO₂ = higher score
        if co2_total < 0.2:
            score += 20
        elif co2_total < 0.5:
            score += 10
        elif co2_total > 1.5:
            score -= 15

        # 2. Diet bonus
        diet = profile.get("diet_type", "")
        if diet in ("vegan",):
            score += 15
            tips.append("Vegan meal = 60% less carbon than meat-based")
        elif diet in ("vegetarian",):
            score += 10
            tips.append("Vegetarian meal saves ~1.5kg CO₂ vs beef")

        # 3. Expiring items used
        expiring_used = 0
        if db:
            expiring = db.get_expiring_soon(days=3)
            expiring_names = [e["item_name"].lower() for e in expiring]
            for ing in ingredients:
                if any(e in ing.get("name", "").lower() for e in expiring_names):
                    expiring_used += 1
        if expiring_used > 0:
            score += expiring_used * 10
            tips.append(f"Used {expiring_used} expiring item(s) — great waste reduction! 🎉")

        # 4. Local/seasonal
        local_items = ["spinach", "tomato", "onion", "dal", "rice", "potato", "carrot"]
        local_count = sum(
            1 for ing in ingredients
            if any(l in ing.get("name", "").lower() for l in local_items)
        )
        if local_count >= 3:
            score += 8
            tips.append("Using locally-available ingredients")

        score = max(0, min(100, score))

        # Grade
        if score >= 85:
            grade = "A+"
        elif score >= 75:
            grade = "A"
        elif score >= 65:
            grade = "B"
        elif score >= 50:
            grade = "C"
        else:
            grade = "D"

        co2_saved = max(0, 2.0 - co2_total)  # vs average meal

        state["eco_score"] = {
            "score": round(score, 1),
            "grade": grade,
            "co2_kg": round(co2_total, 2),
            "co2_saved_kg": round(co2_saved, 2),
            "tip": tips[0] if tips else "Add more vegetables to improve eco score",
            "all_tips": tips,
            "expiring_used": expiring_used,
        }
        self.log(state, f"Eco score: {score:.0f} (Grade {grade})", "success")
        return state

    def _to_grams(self, qty: float, unit: str) -> float:
        unit = str(unit).lower().strip()
        return qty * {
            "g": 1, "gram": 1, "grams": 1,
            "kg": 1000, "kilogram": 1000,
            "ml": 1, "l": 1000, "liter": 1000,
            "cup": 240, "cups": 240,
            "tbsp": 15, "tsp": 5,
            "piece": 100, "pieces": 100,
        }.get(unit, 100)


def eco_agent(state: AgentState, db=None, **kwargs) -> AgentState:
    return EcoAgent().run(state, db=db)
