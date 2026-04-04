"""agents/nutrition_agent.py — Fixed with accurate calorie calculation."""

import json
import re
import os
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from agents.state import AgentState

USDA_API_KEY = os.getenv("USDA_API_KEY", "DEMO_KEY")
USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

NUTRIENT_IDS = {
    "calories": 1008, "protein": 1003, "fat": 1004,
    "carbs": 1005, "fiber": 1079, "sugar": 2000,
    "sodium": 1093, "calcium": 1087, "iron": 1089,
}

_nutrition_cache: Dict[str, Dict] = {}

# FIXED: Accurate unit conversions for Indian cooking
UNIT_TO_GRAMS = {
    "g": 1, "gram": 1, "grams": 1, "kg": 1000, "kilogram": 1000,
    "oz": 28.35, "ounce": 28.35, "ounces": 28.35,
    "lb": 453.6, "pound": 453.6, "pounds": 453.6,
    "ml": 1, "milliliter": 1, "l": 1000, "liter": 1000,
    "cup": 200, "cups": 200,  # Indian katori (not 240ml)
    "tbsp": 15, "tablespoon": 15,
    "tsp": 5, "teaspoon": 5,
    "piece": 75, "pieces": 75,
    "bunch": 250, "medium": 75, "large": 100, "small": 40,
}


def to_grams(quantity: float, unit: str) -> float:
    unit_lower = unit.lower().strip()
    return quantity * UNIT_TO_GRAMS.get(unit_lower, 100)


def search_usda_food(ingredient_name: str) -> Optional[Dict]:
    cache_key = ingredient_name.lower()
    if cache_key in _nutrition_cache:
        return _nutrition_cache[cache_key]
    
    try:
        query = urllib.parse.urlencode({
            "query": ingredient_name,
            "dataType": "Foundation,SR Legacy",
            "pageSize": 1,
            "api_key": USDA_API_KEY,
        })
        url = f"{USDA_BASE_URL}/foods/search?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "NutriBot/5.0"})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
        
        if not data.get("foods"):
            return None
        
        food = data["foods"][0]
        nutrients = {n["nutrientId"]: n["value"] for n in food.get("foodNutrients", [])}
        
        result = {
            "name": food.get("description", ingredient_name),
            "per_100g": {
                "calories": nutrients.get(NUTRIENT_IDS["calories"], 0),
                "protein": nutrients.get(NUTRIENT_IDS["protein"], 0),
                "fat": nutrients.get(NUTRIENT_IDS["fat"], 0),
                "carbs": nutrients.get(NUTRIENT_IDS["carbs"], 0),
                "fiber": nutrients.get(NUTRIENT_IDS["fiber"], 0),
                "sodium": nutrients.get(NUTRIENT_IDS["sodium"], 0),
            }
        }
        _nutrition_cache[cache_key] = result
        return result
    except Exception:
        return None


def _estimate_calories(name: str) -> float:
    """Realistic calorie estimation for Indian ingredients (per 100g)."""
    n = name.lower()
    
    # FIXED: Realistic values
    if any(x in n for x in ["oil", "butter", "ghee", "cream"]):
        return 884
    if any(x in n for x in ["sugar", "honey", "jaggery"]):
        return 387
    if "rice" in n:
        return 130  # cooked rice
    if any(x in n for x in ["pasta", "bread", "roti", "naan"]):
        return 250
    if "paneer" in n:
        return 265
    if "tofu" in n:
        return 145
    if "chicken" in n:
        return 165
    if "fish" in n:
        return 150
    if "egg" in n:
        return 155
    if any(x in n for x in ["milk", "yogurt", "curd"]):
        return 60
    if any(x in n for x in ["spinach", "lettuce", "cabbage"]):
        return 23
    if "broccoli" in n:
        return 34
    if "tomato" in n:
        return 18
    if "onion" in n:
        return 40
    if "carrot" in n:
        return 41
    if "potato" in n:
        return 77
    if any(x in n for x in ["lentil", "chickpea", "bean", "dal"]):
        return 116  # cooked dal
    if "dal" in n:
        return 116
    return 100


def _calculate_nutrition(state: AgentState, ingredients: List[Dict], servings: int, client) -> AgentState:
    per_ingredient = {}
    total = {"calories": 0, "protein_g": 0, "fat_g": 0,
             "carbs_g": 0, "fiber_g": 0, "sodium_mg": 0}
    usda_used = 0
    
    for item in ingredients:
        name = item.get("name", "")
        qty = float(item.get("quantity", 1) or 1)
        unit = item.get("unit", "grams")
        grams = to_grams(qty, unit)
        
        usda_data = search_usda_food(name)
        
        if usda_data:
            usda_used += 1
            factor = grams / 100.0
            p = usda_data["per_100g"]
            item_nutrition = {
                "calories": round(p.get("calories", 0) * factor, 1),
                "protein_g": round(p.get("protein", 0) * factor, 1),
                "fat_g": round(p.get("fat", 0) * factor, 1),
                "carbs_g": round(p.get("carbs", 0) * factor, 1),
                "fiber_g": round(p.get("fiber", 0) * factor, 1),
                "sodium_mg": round(p.get("sodium", 0) * factor, 1),
                "source": "USDA",
            }
        else:
            cal_per_100g = _estimate_calories(name)
            factor = grams / 100.0
            item_nutrition = {
                "calories": round(cal_per_100g * factor, 1),
                "protein_g": round(cal_per_100g * 0.08 * factor, 1),
                "fat_g": round(cal_per_100g * 0.05 * factor, 1),
                "carbs_g": round(cal_per_100g * 0.12 * factor, 1),
                "fiber_g": round(grams * 0.015, 1),
                "sodium_mg": round(grams * 0.04, 1),
                "source": "estimated",
            }
        
        per_ingredient[name] = item_nutrition
        for key in total:
            total[key] += item_nutrition.get(key, 0)
    
    per_serving = {k: round(v / max(servings, 1), 1) for k, v in total.items()}
    accuracy = (usda_used / max(len(ingredients), 1)) * 100
    
    state["nutrition_data"] = {
        "per_ingredient": per_ingredient,
        "total": {k: round(v, 1) for k, v in total.items()},
        "per_serving": per_serving,
        "usda_matched": usda_used,
        "total_ingredients": len(ingredients),
        "servings": servings,
        "accuracy_pct": round(accuracy, 1),
    }
    state["total_nutrition"] = per_serving
    return state


def render_nutrition_card(nutrition_data: Dict, show_detail: bool = True) -> str:
    # Keep your existing render function
    if not nutrition_data:
        return ""
    
    ps = nutrition_data.get("per_serving", {})
    usda = nutrition_data.get("usda_matched", 0)
    total_ings = nutrition_data.get("total_ingredients", 1)
    accuracy = (usda / max(total_ings, 1)) * 100
    
    cal = ps.get("calories", 0)
    protein = ps.get("protein_g", 0)
    fat = ps.get("fat_g", 0)
    carbs = ps.get("carbs_g", 0)
    fiber = ps.get("fiber_g", 0)
    sodium = ps.get("sodium_mg", 0)
    
    acc_color = "#10b981" if accuracy > 70 else "#f97316" if accuracy > 40 else "#ef4444"
    acc_badge = f"🏛️ {accuracy:.0f}% USDA verified" if accuracy > 0 else "📊 Estimated"
    
    return f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:1.2rem;margin:0.8rem 0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
            <span style="font-family:monospace;font-size:0.7rem;color:#64748b;text-transform:uppercase;font-weight:600">
                📊 Nutrition Per Serving
            </span>
            <span style="font-size:0.65rem;padding:3px 10px;border-radius:20px;
                background:{'#d1fae5' if accuracy > 70 else '#fef3c7'};
                color:{acc_color};font-weight:600">
                {acc_badge}
            </span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-bottom:0.5rem">
            <div style="text-align:center;background:white;border-radius:10px;padding:0.6rem;border:1px solid #e2e8f0">
                <div style="font-size:1.4rem;font-weight:700;color:#f97316">{cal:.0f}</div>
                <div style="font-size:0.6rem;color:#94a3b8">kcal</div>
            </div>
            <div style="text-align:center;background:white;border-radius:10px;padding:0.6rem;border:1px solid #e2e8f0">
                <div style="font-size:1.4rem;font-weight:700;color:#3b82f6">{protein:.0f}g</div>
                <div style="font-size:0.6rem;color:#94a3b8">protein</div>
            </div>
            <div style="text-align:center;background:white;border-radius:10px;padding:0.6rem;border:1px solid #e2e8f0">
                <div style="font-size:1.4rem;font-weight:700;color:#10b981">{carbs:.0f}g</div>
                <div style="font-size:0.6rem;color:#94a3b8">carbs</div>
            </div>
            <div style="text-align:center;background:white;border-radius:10px;padding:0.6rem;border:1px solid #e2e8f0">
                <div style="font-size:1.4rem;font-weight:700;color:#8b5cf6">{fat:.0f}g</div>
                <div style="font-size:0.6rem;color:#94a3b8">fat</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem">
            <div style="text-align:center;background:#f0fdf4;border-radius:8px;padding:0.4rem">
                <div style="font-size:1.1rem;font-weight:600;color:#059669">{fiber:.0f}g</div>
                <div style="font-size:0.6rem;color:#64748b">Fiber</div>
            </div>
            <div style="text-align:center;background:#fff7ed;border-radius:8px;padding:0.4rem">
                <div style="font-size:1.1rem;font-weight:600;color:#c2410c">{sodium:.0f}mg</div>
                <div style="font-size:0.6rem;color:#64748b">Sodium</div>
            </div>
            <div style="text-align:center;background:#eff6ff;border-radius:8px;padding:0.4rem">
                <div style="font-size:1.1rem;font-weight:600;color:#2563eb">{nutrition_data.get('accuracy_pct', 0):.0f}%</div>
                <div style="font-size:0.6rem;color:#64748b">Accuracy</div>
            </div>
        </div>
    </div>
    """
