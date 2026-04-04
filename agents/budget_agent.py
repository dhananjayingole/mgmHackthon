
import re
from agents.base import BaseAgent
from agents.state import AgentState
from agents.user_profile import _currency


class BudgetAgent(BaseAgent):
    """Calculates recipe costs with database-backed pricing."""
    
    def __init__(self):
        super().__init__("💰 Budget Agent")
    
    def run(self, state: AgentState, **kwargs) -> AgentState:
        profile = state.get("user_profile", {})
        currency = "₹"  # Always INR for Indian users
        
        # Try to get price service
        try:
            from services.price_service import get_price_service
            price_service = get_price_service()
        except ImportError:
            # Fallback to local price dict
            price_service = None
        
        ingredients = state.get("recipe_ingredients_structured") or []
        total_inr = 0
        ingredient_breakdown = []
        
        for item in ingredients:
            name = item.get("name", "").lower()
            qty = float(item.get("quantity", 1) or 1)
            unit = item.get("unit", "grams")
            
            # Convert to kg
            grams = self._to_grams(qty, unit)
            kg = grams / 1000
            
            if price_service:
                cost = price_service.get_price(name, kg)
            else:
                cost = self._get_fallback_price(name, kg)
            
            total_inr += cost
            ingredient_breakdown.append({
                "name": name.title(),
                "cost": round(cost, 0)
            })
        
        total_inr = round(total_inr, 0)
        
        # Get budget from profile
        budget_limit = 500
        if isinstance(profile.get("budget_preference"), dict):
            budget_limit = profile["budget_preference"].get("amount", 500)
        elif state.get("budget_limit"):
            budget_limit = state.get("budget_limit", 500)
        
        servings = max(state.get("servings", 2), 1)
        per_serving = total_inr / servings
        within = total_inr <= budget_limit
        
        state["budget_analysis"] = {
            "total_cost": total_inr,
            "per_serving": round(per_serving, 0),
            "budget_limit": budget_limit,
            "within_budget": within,
            "status": "✅ Within Budget" if within else f"⚠️ Over Budget by ₹{total_inr - budget_limit}",
            "currency": currency,
            "ingredient_breakdown": ingredient_breakdown
        }
        
        return state
    
    def _to_grams(self, qty: float, unit: str) -> float:
        unit = unit.lower().strip()
        conversions = {
            "g": 1, "gram": 1, "grams": 1,
            "kg": 1000, "kilogram": 1000,
            "ml": 1, "l": 1000, "liter": 1000,
            "cup": 200, "cups": 200,  # Indian katori size
            "tbsp": 15, "tsp": 5,
            "piece": 75, "pieces": 75,
            "bunch": 250,
        }
        return qty * conversions.get(unit, 100)
    
    def _get_fallback_price(self, name: str, kg: float) -> float:
        """Fallback prices when price service unavailable."""
        fallbacks = {
            "onion": 40, "tomato": 30, "potato": 25, "spinach": 30,
            "paneer": 280, "dal": 100, "lentil": 100, "rice": 60,
            "milk": 60, "curd": 50, "ghee": 600, "oil": 110,
            "garlic": 200, "ginger": 150, "cumin": 300, "turmeric": 200,
        }
        price_per_kg = fallbacks.get(name, 50)
        return price_per_kg * kg
    
    def get_cheapest_protein(self, profile: dict) -> dict:
        """Get cheapest protein source for user's diet."""
        diet_type = profile.get("diet_type", "").lower()
        
        try:
            from services.price_service import get_price_service
            price_service = get_price_service()
            return price_service.get_cheapest_protein(diet_type)
        except Exception:
            # Fallback
            if "vegetarian" in diet_type:
                return {
                    "name": "Soy Chunks",
                    "price_per_kg": 120,
                    "protein_per_100g": 52,
                    "cost_per_10g_protein": 2.31,
                    "currency": "₹"
                }
            else:
                return {
                    "name": "Eggs",
                    "price_per_kg": 70,
                    "protein_per_100g": 13,
                    "cost_per_10g_protein": 5.38,
                    "currency": "₹"
                }


def budget_agent(state: AgentState, client=None) -> AgentState:
    return BudgetAgent().run(state)
