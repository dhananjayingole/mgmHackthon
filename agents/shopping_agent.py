"""agents/shopping_agent.py — Smart shopping list with diet constraints."""

import re
import json
from typing import Dict, Any, List
from agents.base import BaseAgent
from agents.state import AgentState
from agents.user_profile import _currency


class ShoppingAgent(BaseAgent):
    """Generates smart shopping lists with diet constraints."""

    def __init__(self):
        super().__init__("🛒 Shopping Agent")

    def run(self, state: AgentState, db=None, client=None, **kwargs) -> AgentState:
        intent = state.get("intent", "")
        if intent == "shopping_list" or "shopping" in state.get("user_query", "").lower():
            return self._generate_shopping_list(state, db, client)
        return state

    def _generate_shopping_list(self, state: AgentState, db, client) -> AgentState:
        profile = state.get("user_profile", {})
        cur = _currency(profile)
        diet_type = profile.get("diet_type", "").lower()
        
        # FIXED: Add diet restrictions for shopping list generation
        diet_restrictions = ""
        if "vegetarian" in diet_type:
            diet_restrictions = "⚠️ CRITICAL: User is VEGETARIAN. NEVER include chicken, fish, shrimp, meat, poultry, or eggs in shopping list."
        elif "vegan" in diet_type:
            diet_restrictions = "⚠️ CRITICAL: User is VEGAN. NEVER include dairy, eggs, honey, ghee, or any animal products."

        # Get pantry
        pantry = {}
        if db:
            for item in db.get_all_groceries():
                pantry[item["item_name"].lower()] = item

        # Get recipe ingredients if available
        recipe_ings = state.get("recipe_ingredients_structured", [])

        # Price map (₹ per 100g or per piece)
        PRICES = {
            "onion": 4, "tomato": 3, "potato": 2.5, "spinach": 4, "garlic": 20,
            "ginger": 15, "paneer": 28, "milk": 6, "curd": 5, "butter": 45,
            "ghee": 60, "rice": 6, "dal": 10, "lentil": 10, "chickpea": 8,
            "flour": 4, "oil": 11, "cumin": 30, "turmeric": 20, "chili": 40,
            "coriander": 25, "salt": 1, "sugar": 4, "egg": 7, "bread": 3,
            "carrot": 3.5, "peas": 5, "capsicum": 6, "cauliflower": 4,
            "brinjal": 3.5, "tofu": 15, "soy": 12, "oats": 8, "pasta": 8,
        }

        if recipe_ings:
            needed = []
            have = []
            total_cost = 0

            # FIXED: Filter ingredients based on diet
            for ing in recipe_ings:
                name = ing.get("name", "").lower().strip()
                
                # Skip non-vegetarian items for vegetarian users
                if "vegetarian" in diet_type:
                    meat_keywords = ["chicken", "fish", "shrimp", "prawn", "meat", "beef", "pork", "turkey", "egg"]
                    if any(k in name for k in meat_keywords):
                        continue
                
                qty = ing.get("quantity", 100)
                unit = ing.get("unit", "grams")

                # Check if in pantry
                in_pantry = any(
                    name in p or p in name
                    for p in pantry.keys()
                )

                # Estimate cost
                price_per_100 = next(
                    (p for k, p in PRICES.items() if k in name), 6
                )
                grams = self._to_grams(qty, unit)
                cost = round(price_per_100 * grams / 100, 0)

                if in_pantry:
                    have.append(f"✅ {name.title()} ({qty} {unit})")
                else:
                    needed.append({
                        "name": name.title(),
                        "qty": qty,
                        "unit": unit,
                        "cost": cost,
                    })
                    total_cost += cost

            # Group needed by category
            lines = ["## 🛒 Shopping List\n"]

            if have:
                lines.append(f"**✅ Already in pantry ({len(have)} items):**")
                lines.extend(have[:6])
                lines.append("")

            if needed:
                lines.append(f"**🛍️ Need to buy ({len(needed)} items):**")
                for item in needed:
                    lines.append(
                        f"- [ ] {item['qty']} {item['unit']} **{item['name']}** "
                        f"(~{cur}{item['cost']:.0f})"
                    )
                lines.append("")
                lines.append(f"**💰 Estimated total: {cur}{total_cost:.0f}**")

                budget = profile.get("budget_preference", {})
                weekly_budget = budget.get("amount", 500) if isinstance(budget, dict) else 500
                if total_cost <= weekly_budget:
                    lines.append(f"✅ Within your {cur}{weekly_budget}/week budget")
                else:
                    over = total_cost - weekly_budget
                    lines.append(f"⚠️ {cur}{over:.0f} over your {cur}{weekly_budget}/week budget")
                    # Suggest substitutions
                    lines.append("\n**💡 Budget substitutions:**")
                    subs = self._get_substitutions(needed, cur)
                    lines.extend(subs)
            else:
                lines.append("🎉 **You have everything needed!** No shopping required.")

        elif client:
            # Generate from scratch using LLM with diet constraints
            pantry_list = list(pantry.keys())
            budget = profile.get("budget_preference", {})
            weekly_budget = budget.get("amount", 500) if isinstance(budget, dict) else 500
            query = state.get("user_query", "")

            prompt = f"""Generate a smart shopping list for this user.

{diet_restrictions}

Profile: {profile.get('diet_type', 'vegetarian')}, {profile.get('cuisine_preferences', ['Indian'])}
Weekly budget: {cur}{weekly_budget}
Request: "{query}"
Already in pantry: {pantry_list[:20]}

Create a 5-day meal plan shopping list. For each item:
- Only items NOT already in pantry
- ONLY include items that match the user's diet type
- Group by category (Vegetables, Dairy, Proteins, Grains, Spices)
- Include quantity and estimated ₹ cost
- Show total cost
- Stay under budget

Format clearly with markdown."""

            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=800,
                )
                lines = [response.choices[0].message.content.strip()]
            except Exception as e:
                lines = [f"❌ Could not generate shopping list: {e}"]
        else:
            lines = ["❌ No recipe or client available to generate shopping list."]

        state["assistant_message"] = "\n".join(lines) if isinstance(lines, list) else lines[0]
        return state

    def _to_grams(self, qty: float, unit: str) -> float:
        unit = unit.lower().strip()
        conversions = {
            "g": 1, "gram": 1, "grams": 1,
            "kg": 1000, "kilogram": 1000,
            "ml": 1, "l": 1000, "liter": 1000,
            "cup": 240, "cups": 240,
            "tbsp": 15, "tsp": 5,
            "piece": 100, "pieces": 100,
        }
        return qty * conversions.get(unit, 100)

    def _get_substitutions(self, needed: list, cur: str) -> list:
        SUBS = {
            "Paneer": ("Tofu", 0.6),
            "Ghee": ("Butter", 0.7),
            "Basmati Rice": ("Regular Rice", 0.5),
            "Saffron": ("Turmeric", 0.1),
            "Cream": ("Curd", 0.3),
            "Almonds": ("Peanuts", 0.2),
        }
        result = []
        for item in needed[:3]:
            name = item["name"]
            if name in SUBS:
                sub, cost = SUBS[name]
                result.append(f"  • Replace {name} with {sub} (save {cur}{cost*100:.0f})")
        return result if result else ["  • Buy in bulk to save 20-30%"]


def shopping_agent(state: AgentState, db=None, client=None) -> AgentState:
    return ShoppingAgent().run(state, db=db, client=client)
