"""agents/planner_agent.py — Meal planning agent with strict diet constraints."""

import re
from agents.base import BaseAgent
from agents.state import AgentState
from agents.user_profile import get_profile_context_string


class MealPlannerAgent(BaseAgent):
    """Generates multi-day meal plans with strict diet constraints."""
    
    def __init__(self):
        super().__init__("📅 Meal Planner")
    
    def run(self, state: AgentState, client=None, db=None, **kwargs) -> AgentState:
        profile = state.get("user_profile", {})
        query = state.get("user_query", "")
        
        days_match = re.search(r"(\d+)\s*day", query, re.IGNORECASE)
        num_days = int(days_match.group(1)) if days_match else 3
        
        diet_type = profile.get("diet_type", "any").lower()
        cuisine = profile.get("cuisine_preferences", ["Indian"])[0]
        calorie_goal = profile.get("calorie_goal", 500)
        
        # FIXED: Add strict dietary constraints to prompt
        diet_restrictions = ""
        if "vegetarian" in diet_type:
            diet_restrictions = """⚠️ **CRITICAL: User is VEGETARIAN**
            - NEVER include chicken, fish, shrimp, turkey, beef, pork, or any meat
            - NEVER include eggs (strict vegetarian = no eggs)
            - Only use: paneer, tofu, lentils, beans, chickpeas, dairy
            - All recipes must be 100% vegetarian"""
        elif "vegan" in diet_type:
            diet_restrictions = """⚠️ **CRITICAL: User is VEGAN**
            - NO animal products: no dairy, no eggs, no honey, no ghee
            - Use plant-based proteins only: tofu, tempeh, lentils, beans, chickpeas
            - Use plant milk, coconut oil, or vegetable oil"""
        
        prompt = f"""Create a {num_days}-day meal plan for a {diet_type} user.

{diet_restrictions}

User Profile: {get_profile_context_string(profile)}
Cuisine Preference: {cuisine}
Target Calories per meal: {calorie_goal} kcal

For each day, provide:
- **Breakfast**, **Lunch**, **Dinner**
- Calories and protein per meal
- Brief description of key ingredients

**IMPORTANT FORMATTING RULES:**
- Use markdown headings: Day 1, Day 2, etc.
- Each meal: bold name, then calories/protein on next line
- Keep it concise but informative
- Max 1000 words total

**CRITICAL: Respect the diet restrictions above 100%. If user is vegetarian, DO NOT include any meat, fish, or poultry in ANY meal.**"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=1500
            )
            state["assistant_message"] = response.choices[0].message.content.strip()
            state["final_output"] = "complete"
        except Exception as e:
            state["assistant_message"] = f"Could not generate meal plan: {e}"
        
        return state


def meal_plan_agent(state: AgentState, client=None, db=None) -> AgentState:
    return MealPlannerAgent().run(state, client=client, db=db)