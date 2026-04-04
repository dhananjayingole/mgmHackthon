"""agents/health_agent.py — Health and nutrition advice with constraint enforcement."""

import re
import json
from typing import Dict, Any, List
from datetime import datetime
from agents.base import BaseAgent
from agents.state import AgentState
from agents.user_profile import get_profile_context_string, get_diet_constraints_string


class HealthAgent(BaseAgent):
    """Enforces health constraints and provides nutrition advice."""
    
    def __init__(self):
        super().__init__("🏥 Health Agent")
    
    def run(self, state: AgentState, client=None, **kwargs) -> AgentState:
        """Process health-related queries and validate recipes."""
        intent = state.get("intent", "")
        profile = state.get("user_profile", {})
        
        if intent == "health_advice":
            return self._provide_health_advice(state, client, profile)
        else:
            return self._validate_recipe_health(state, client, profile)
    
    def _provide_health_advice(self, state: AgentState, client, profile) -> AgentState:
        """Provide personalized health advice."""
        query = state.get("user_query", "")
        health_conditions = profile.get("health_conditions", [])
        diet_type = profile.get("diet_type", "")
        fitness_goal = profile.get("fitness_goal", "")
        
        # Build condition-specific advice prompt
        conditions_str = ", ".join(health_conditions) if health_conditions else "None"
        
        prompt = f"""You are a certified nutritionist providing personalized health advice.

USER PROFILE:
- Diet: {diet_type or 'Not specified'}
- Health conditions: {conditions_str}
- Fitness goal: {fitness_goal or 'Not specified'}

USER QUESTION: "{query}"

Provide:
1. Evidence-based answer with specific numbers where applicable
2. Practical dietary advice considering their profile
3. Food recommendations from Indian cuisine (if relevant)
4. Important cautions or things to avoid
5. Suggested portion sizes or timing

Keep response under 300 words. Be warm but professional."""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            state["assistant_message"] = response.choices[0].message.content.strip()
            state["final_output"] = "complete"
            self.log(state, "Health advice provided", "success")
        except Exception as e:
            state["assistant_message"] = "I couldn't generate health advice right now. Please try again."
            self.log(state, f"Error: {e}", "error")
        
        return state
    
    def _validate_recipe_health(self, state: AgentState, client, profile) -> AgentState:
        """Validate recipe against health constraints."""
        ingredients = state.get("available_ingredients", [])
        recipe_ings = state.get("recipe_ingredients_structured", [])
        calorie_limit = profile.get("calorie_goal", state.get("calorie_limit", 600))
        
        health_conditions = profile.get("health_conditions", [])
        allergies = profile.get("allergies", [])
        diet_type = profile.get("diet_type", "")
        
        # Check for allergens
        allergen_violations = []
        for allergen in allergies:
            if any(allergen.lower() in ing.lower() for ing in ingredients):
                allergen_violations.append(allergen)
        
        # Check for diet violations (basic)
        diet_violations = []
        if diet_type == "vegetarian":
            meat_items = ["chicken", "beef", "pork", "fish", "mutton", "lamb"]
            for item in meat_items:
                if any(item in ing.lower() for ing in ingredients):
                    diet_violations.append(item)
        elif diet_type == "vegan":
            animal_items = ["chicken", "beef", "fish", "milk", "cheese", "egg", "butter", "ghee", "honey"]
            for item in animal_items:
                if any(item in ing.lower() for ing in ingredients):
                    diet_violations.append(item)
        
        # Build validation response
        validation = []
        
        if allergen_violations:
            validation.append(f"⚠️ **Allergen Alert:** Contains {', '.join(allergen_violations)}")
        
        if diet_violations:
            validation.append(f"⚠️ **Diet Violation:** Contains {', '.join(diet_violations)} (not allowed for {diet_type})")
        
        # Nutrition analysis prompt
        if recipe_ings and client:
            prompt = f"""Analyze the nutritional profile of this recipe for health conditions.

HEALTH CONDITIONS: {', '.join(health_conditions) if health_conditions else 'None'}
DIET TYPE: {diet_type}
CALORIE LIMIT: {calorie_limit} kcal per serving

INGREDIENTS: {', '.join([i.get('name', '') for i in recipe_ings[:15]])}

Provide:
1. Is this recipe suitable for their health conditions? (yes/no with reasoning)
2. Estimated nutritional strengths (protein, fiber, etc.)
3. Suggested modifications to make it healthier
4. Compliance rating (1-10)
5. 2-3 tips for this meal

Keep response concise, under 200 words."""

            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=350
                )
                nutrition_analysis = response.choices[0].message.content.strip()
                validation.append(nutrition_analysis)
            except Exception as e:
                validation.append("Nutrition analysis temporarily unavailable.")
        
        state["health_recommendations"] = "\n\n".join(validation) if validation else "✅ Recipe appears compatible with your health profile."
        
        if allergen_violations or diet_violations:
            self.log(state, f"Violations: {allergen_violations + diet_violations}", "warning")
        
        return state
    
    def check_diabetes_compatibility(self, ingredients: List[str], client) -> Dict:
        """Check if recipe is diabetes-friendly."""
        prompt = f"""Analyze these ingredients for diabetes compatibility.

INGREDIENTS: {', '.join(ingredients[:20])}

Return JSON:
{{
    "compatible": true/false,
    "reason": "brief explanation",
    "carbs_estimate": "low/medium/high",
    "suggestions": ["tip1", "tip2"]
}}"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            return {
                "compatible": True,
                "reason": "Analysis unavailable",
                "carbs_estimate": "medium",
                "suggestions": ["Add more fiber", "Include protein"]
            }
    
    def check_hypertension_compatibility(self, ingredients: List[str], client) -> Dict:
        """Check if recipe is hypertension-friendly (low sodium)."""
        prompt = f"""Analyze these ingredients for hypertension compatibility (low sodium).

INGREDIENTS: {', '.join(ingredients[:20])}

Return JSON:
{{
    "compatible": true/false,
    "reason": "brief explanation",
    "sodium_estimate": "low/medium/high",
    "suggestions": ["tip1", "tip2"]
}}"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            return {
                "compatible": True,
                "reason": "Analysis unavailable",
                "sodium_estimate": "medium",
                "suggestions": ["Use herbs instead of salt", "Avoid processed ingredients"]
            }


def health_agent(state: AgentState, client=None) -> AgentState:
    """Wrapper function for health agent."""
    agent = HealthAgent()
    return agent.run(state, client=client)
