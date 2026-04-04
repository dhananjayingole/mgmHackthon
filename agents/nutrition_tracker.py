"""agents/nutrition_tracker.py — Daily nutrition tracking with goals and progress."""

import json
import re
from datetime import datetime, date
from typing import Dict, Any, List
from agents.state import AgentState


def get_daily_nutrition_summary(state: AgentState, db, client) -> AgentState:
    """Compute today's nutrition from saved meal plans and return formatted dashboard."""
    today = date.today().isoformat()
    
    try:
        meals_today = db.get_meal_plans_today()
    except Exception:
        meals_today = []
    
    profile = state.get("user_profile", {})
    
    # Goals based on profile
    calorie_goal = profile.get("calorie_goal", 1500)
    if calorie_goal < 500:  # per-meal goal stored → convert to daily
        calorie_goal = calorie_goal * 3
    
    protein_goal = profile.get("protein_goal", 60)
    carbs_goal = profile.get("carbs_goal", 150)
    fat_goal = profile.get("fat_goal", 50)
    
    # Adjust goals based on fitness goal
    fitness_goal = profile.get("fitness_goal", "")
    if fitness_goal == "weight_loss":
        calorie_goal = min(calorie_goal, 1500)
        protein_goal = max(protein_goal, 70)
    elif fitness_goal == "muscle_gain":
        calorie_goal = max(calorie_goal, 2000)
        protein_goal = max(protein_goal, 100)
    
    # Sum today's meals
    total = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    meals_list = []
    
    for meal in meals_today:
        calories = meal.get("calories", 0)
        protein = meal.get("protein_g", 0)
        carbs = meal.get("carbs_g", 0)
        fat = meal.get("fat_g", 0)
        
        total["calories"] += calories
        total["protein_g"] += protein
        total["carbs_g"] += carbs
        total["fat_g"] += fat
        
        meals_list.append(
            f"• {meal.get('meal_type', '').title()}: {meal.get('recipe_name', '')} "
            f"({calories} kcal, {protein:.0f}g protein, {carbs:.0f}g carbs)"
        )
    
    remaining_cal = max(0, calorie_goal - total["calories"])
    remaining_protein = max(0, protein_goal - total["protein_g"])
    
    def pct_bar(current, goal, width=20):
        p = min(1.0, current / max(goal, 1))
        filled = int(p * width)
        return "█" * filled + "░" * (width - filled) + f" {p*100:.0f}%"
    
    # Build message
    lines = [
        "## 📊 Today's Nutrition Dashboard",
        f"*{datetime.now().strftime('%A, %d %B %Y')}*\n",
    ]
    
    if meals_list:
        lines.append("### 🍽️ Meals Logged Today")
        lines.extend(meals_list)
        lines.append("")
    else:
        lines.append("*No meals logged today yet. Generate a recipe and save it to track nutrition!*\n")
    
    lines += [
        "### 📈 Progress",
        f"**🔥 Calories:** {total['calories']:.0f} / {calorie_goal} kcal",
        f"`{pct_bar(total['calories'], calorie_goal)}`",
        "",
        f"**💪 Protein:** {total['protein_g']:.0f}g / {protein_goal}g",
        f"`{pct_bar(total['protein_g'], protein_goal)}`",
        "",
        f"**🌾 Carbs:** {total['carbs_g']:.0f}g / {carbs_goal}g",
        f"`{pct_bar(total['carbs_g'], carbs_goal)}`",
        "",
        f"**🥑 Fat:** {total['fat_g']:.0f}g / {fat_goal}g",
        f"`{pct_bar(total['fat_g'], fat_goal)}`",
        "",
        "### 🎯 Remaining",
        f"- 🍽️ **{remaining_cal:.0f} kcal** left today",
        f"- 💪 **{remaining_protein:.0f}g protein** still needed",
        f"- 🌾 **{max(0, carbs_goal - total['carbs_g']):.0f}g carbs** available",
        "",
    ]
    
    # Suggestions based on remaining
    if remaining_protein > 20 and remaining_cal > 200:
        lines += [
            "### 💡 Next Meal Suggestion",
            "You need more protein. Consider:",
            "- Paneer Tikka (~25g protein, ~300 kcal)",
            "- Dal with Roti (~18g protein, ~350 kcal)",
            "- Chickpea Salad (~15g protein, ~250 kcal)",
        ]
    elif remaining_cal < 100:
        lines.append("### ✅ You've hit your calorie goal for today!")
    elif remaining_cal > 0:
        lines += [
            "### 💡 Light snack ideas:",
            "- Fruit (~80 kcal)",
            "- Curd with cumin (~60 kcal)",
            "- A handful of nuts (~150 kcal)",
        ]
    
    state["assistant_message"] = "\n".join(lines)
    state["daily_nutrition_summary"] = total
    return state


def save_meal_to_calendar(state: AgentState, db, meal_type: str = "dinner") -> AgentState:
    """Save the last generated recipe to meal calendar with correct nutrition."""
    recipe = state.get("generated_recipe", "")
    
    # Try multiple sources for nutrition data
    nutrition = state.get("total_nutrition") or {}
    if not nutrition:
        nutrition = state.get("last_generated_nutrition") or {}
    if not nutrition:
        nutrition = state.get("nutrition_data", {}).get("per_serving", {})
    
    if not recipe:
        state["assistant_message"] = "❌ No recipe to save. Generate a recipe first!"
        return state
    
    # Extract recipe name
    name_match = re.search(r"##\s*🍽️\s*(.+)", recipe)
    recipe_name = name_match.group(1).strip() if name_match else "Today's Recipe"
    
    # Extract nutrition from recipe if not available in state
    if not nutrition or nutrition.get("calories", 0) == 0:
        nutrition = _extract_nutrition_from_recipe(recipe)
    
    servings = state.get("servings", 2)
    
    try:
        db.save_meal_plan(
            plan_date=date.today().isoformat(),
            meal_type=meal_type,
            recipe_name=recipe_name,
            calories=int(nutrition.get("calories", 0)),
            protein_g=float(nutrition.get("protein_g", 0)),
            carbs_g=float(nutrition.get("carbs_g", 0)),
            fat_g=float(nutrition.get("fat_g", 0)),
            notes=f"Saved from NutriBot. Serves {servings}",
        )
        
        calories = int(nutrition.get("calories", 0))
        protein = nutrition.get("protein_g", 0)
        carbs = nutrition.get("carbs_g", 0)
        
        state["assistant_message"] = (
            f"✅ **Saved to calendar!**\n\n"
            f"📅 **{meal_type.title()}:** {recipe_name}\n"
            f"🔥 **{calories} kcal** • "
            f"💪 **{protein:.0f}g** protein • "
            f"🌾 **{carbs:.0f}g** carbs\n\n"
            f"*Ask 'show my daily nutrition' to see today's total.*"
        )
        
        # Update daily summary in state
        daily = state.get("daily_nutrition_summary", {})
        daily["calories"] = daily.get("calories", 0) + calories
        daily["protein_g"] = daily.get("protein_g", 0) + protein
        daily["carbs_g"] = daily.get("carbs_g", 0) + carbs
        state["daily_nutrition_summary"] = daily
        
    except Exception as e:
        state["assistant_message"] = f"❌ Could not save: {e}"
    
    return state


def _extract_nutrition_from_recipe(recipe: str) -> dict:
    """Extract nutrition values from recipe text."""
    nutrition = {}
    
    # Try to find nutrition table
    cal_match = re.search(r'Calories\s*\|\s*(\d+)\s*kcal', recipe, re.IGNORECASE)
    if cal_match:
        nutrition["calories"] = int(cal_match.group(1))
    
    protein_match = re.search(r'Protein\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
    if protein_match:
        nutrition["protein_g"] = float(protein_match.group(1))
    
    carbs_match = re.search(r'Carbs\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
    if carbs_match:
        nutrition["carbs_g"] = float(carbs_match.group(1))
    
    fat_match = re.search(r'Fat\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
    if fat_match:
        nutrition["fat_g"] = float(fat_match.group(1))
    
    fiber_match = re.search(r'Fiber\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
    if fiber_match:
        nutrition["fiber_g"] = float(fiber_match.group(1))
    
    return nutrition
