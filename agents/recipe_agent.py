"""agents/recipe_agent.py — Fixed: modification via context, diet enforcement with friendly warnings."""

import re
import json
from agents.base import BaseAgent
from agents.state import AgentState
from agents.user_profile import get_profile_context_string, get_diet_constraints_string, _currency

# Hard forbidden lists per diet
FORBIDDEN = {
    "vegetarian": ["chicken", "beef", "pork", "fish", "mutton", "lamb", "prawn",
                   "shrimp", "bacon", "meat", "salmon", "tuna", "seafood"],
    "vegan": ["chicken", "beef", "pork", "fish", "mutton", "lamb", "prawn",
              "shrimp", "bacon", "meat", "salmon", "milk", "cheese", "egg",
              "butter", "ghee", "honey", "cream", "paneer", "yogurt", "curd"],
    "keto": ["rice", "pasta", "bread", "sugar", "flour", "potato", "corn", "oats"],
}

INDIAN_VEG_EXCLUDE = ["egg", "eggs", "omelette", "omelet"]

# Non-veg dish mappings → vegetarian alternatives
NON_VEG_ALTERNATIVES = {
    "chicken": "paneer",
    "beef":    "jackfruit",
    "mutton":  "mushroom",
    "lamb":    "tofu",
    "fish":    "tofu",
    "prawn":   "paneer",
    "shrimp":  "tofu",
    "pork":    "soy chunks",
    "bacon":   "smoked tofu",
}


class RecipeAgent(BaseAgent):

    def __init__(self):
        super().__init__("🍳 Recipe Agent")

    def run(self, state: AgentState, client=None, **kwargs) -> AgentState:
        intent = state.get("intent", "generate_recipe")
        query = state.get("user_query", "").lower()
        profile = state.get("user_profile", {})
        diet_type = profile.get("diet_type", "").lower()

        # ── Diet restriction check with friendly warning ───────────────────
        diet_warning = self._check_diet_restriction(query, diet_type, profile)
        if diet_warning:
            state["_diet_warning_message"] = diet_warning["message"]
            # Modify query to use the safe alternative
            if diet_warning.get("substitute_query"):
                state["user_query"] = diet_warning["substitute_query"]

        # ── Handle recipe modification (context-aware) ────────────────────
        if intent == "modify_recipe":
            state = self._modify_existing_recipe(state, client)
            return state

        # ── Generate new recipe with retry ────────────────────────────────
        for attempt in range(3):
            try:
                recipe, ingredients = self._generate(state, client, intent, attempt)
                profile = state.get("user_profile", {})
                diet_type = profile.get("diet_type", "")
                allergies = profile.get("allergies", [])
                if isinstance(allergies, str):
                    allergies = [allergies]

                violations = self._check_violations(recipe, diet_type, allergies)
                ingredient_violations = self._check_ingredient_violations(ingredients, diet_type, allergies)
                all_violations = list(set(violations + ingredient_violations))

                if not all_violations or attempt == 2:
                    state["generated_recipe"] = recipe
                    state["recipe_ingredients_structured"] = ingredients
                    state["assistant_message"] = recipe

                    # Prepend diet warning if any
                    if state.get("_diet_warning_message"):
                        state["assistant_message"] = (
                            state["_diet_warning_message"] + "\n\n---\n\n" + recipe
                        )

                    nutrition = self._extract_nutrition_from_recipe(recipe)
                    if nutrition:
                        state["last_generated_nutrition"] = nutrition
                        state["total_nutrition"] = nutrition
                    if all_violations:
                        self.log(state, f"⚠️ Residual violations: {all_violations}", "warning")
                    break
                else:
                    self.log(state, f"Attempt {attempt+1}: violations {all_violations}, retrying", "warning")
                    state["_last_violations"] = all_violations
            except Exception as e:
                if attempt == 2:
                    state["generated_recipe"] = f"❌ Could not generate recipe: {e}"
                    state["assistant_message"] = state["generated_recipe"]
                    self.log(state, f"Error: {e}", "error")
        return state

    # ─────────────────────────────────────────────────────────────────────
    # DIET RESTRICTION CHECK
    # ─────────────────────────────────────────────────────────────────────

    def _check_diet_restriction(self, query: str, diet_type: str, profile: dict) -> dict | None:
        """Check if query violates diet and return friendly warning with alternative."""
        if not diet_type:
            return None

        if "vegetarian" in diet_type and "non" not in diet_type:
            for meat, alt in NON_VEG_ALTERNATIVES.items():
                if meat in query:
                    # Build alternative query
                    substitute_query = query
                    for m, a in NON_VEG_ALTERNATIVES.items():
                        substitute_query = substitute_query.replace(m, a)

                    return {
                        "message": (
                            f"⚠️ **Heads up!** You asked for **{meat}**, but your profile shows you're **vegetarian**.\n\n"
                            f"No worries — I'll make a delicious **{alt.title()}** version instead! "
                            f"It'll be just as flavourful, I promise. 🌿"
                        ),
                        "substitute_query": substitute_query,
                    }

        if "vegan" in diet_type:
            animal_items = ["milk", "cheese", "egg", "butter", "ghee", "honey", "cream", "paneer", "yogurt"]
            for item in animal_items:
                if item in query:
                    return {
                        "message": (
                            f"⚠️ **Just a note!** **{item.title()}** isn't vegan. "
                            f"I'll use a plant-based alternative to keep it 100% vegan for you! 🌱"
                        ),
                        "substitute_query": None,
                    }

        health_conditions = profile.get("health_conditions", [])
        if isinstance(health_conditions, str):
            health_conditions = [health_conditions]
        conditions_lower = [h.lower() for h in health_conditions]

        if "diabetes" in conditions_lower:
            high_sugar_items = ["halwa", "kheer", "gulab jamun", "jalebi", "ice cream", "cake", "sweet"]
            for item in high_sugar_items:
                if item in query:
                    return {
                        "message": (
                            f"⚠️ **Health alert!** **{item.title()}** is high in sugar, "
                            f"which isn't ideal for your **diabetic** diet. "
                            f"I'll make a low-sugar, diabetic-friendly version instead! 💙"
                        ),
                        "substitute_query": None,
                    }

        return None

    # ─────────────────────────────────────────────────────────────────────
    # RECIPE MODIFICATION (context-aware)
    # ─────────────────────────────────────────────────────────────────────

    def _modify_existing_recipe(self, state: AgentState, client) -> AgentState:
        """Modify the previously generated recipe based on user's new request."""
        original_recipe = state.get("generated_recipe", "")
        history = state.get("conversation_history", [])

        # Try to get recipe from history if not in state
        if not original_recipe:
            for msg in reversed(history):
                if msg.get("role") == "assistant" and "## 🍽️" in msg.get("content", ""):
                    original_recipe = msg["content"]
                    break

        if not original_recipe:
            # No recipe to modify — generate fresh
            state["intent"] = "generate_recipe"
            return self.run(state, client=client)

        profile = state.get("user_profile", {})
        diet_constraints = get_diet_constraints_string(profile)
        modification_request = state.get("user_query", "")
        cur = _currency(profile)

        prompt = f"""You are an expert chef. The user wants to MODIFY their existing recipe.

═══ ORIGINAL RECIPE ═══
{original_recipe[:3000]}

═══ MODIFICATION REQUEST ═══
"{modification_request}"

═══ ABSOLUTE CONSTRAINTS (NEVER VIOLATE) ═══
{diet_constraints}

Create the MODIFIED version of the recipe. Keep the same format as the original.
Clearly show what changed. Start with:
"## 🍽️ [Modified Recipe Name]"
Then add: "**✨ Modifications made:** [list what changed]"
Then provide the complete modified recipe.

Currency: {cur}"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.65,
                max_tokens=2200,
            )
            modified_recipe = response.choices[0].message.content.strip()

            # Check for violations
            diet_type = profile.get("diet_type", "")
            allergies = profile.get("allergies", [])
            if isinstance(allergies, str):
                allergies = [allergies]
            violations = self._check_violations(modified_recipe, diet_type, allergies)

            if violations:
                # Add warning but still return
                warning = f"\n\n⚠️ *Note: Please verify this modified recipe matches your {diet_type} requirements.*"
                modified_recipe += warning

            state["generated_recipe"] = modified_recipe
            state["assistant_message"] = modified_recipe

            ingredients = self._extract_ingredients(modified_recipe)
            state["recipe_ingredients_structured"] = ingredients

            nutrition = self._extract_nutrition_from_recipe(modified_recipe)
            if nutrition:
                state["last_generated_nutrition"] = nutrition
                state["total_nutrition"] = nutrition

            self.log(state, "Recipe modified successfully", "success")

        except Exception as e:
            state["assistant_message"] = f"❌ Could not modify recipe: {e}"
            self.log(state, f"Modification error: {e}", "error")

        return state

    # ─────────────────────────────────────────────────────────────────────
    # GENERATION
    # ─────────────────────────────────────────────────────────────────────

    def _generate(self, state: AgentState, client, intent: str, attempt: int) -> tuple:
        prompt = self._build_prompt(state, intent, attempt)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.65,
            max_tokens=2200,
        )
        recipe_text = response.choices[0].message.content.strip()
        ingredients = self._extract_ingredients(recipe_text)
        return recipe_text, ingredients

    def _build_prompt(self, state: AgentState, intent: str, attempt: int) -> str:
        profile = state.get("user_profile", {})
        cur = _currency(profile)
        diet_type = profile.get("diet_type", "")
        diet_constraints = get_diet_constraints_string(profile)
        allergies = profile.get("allergies", [])
        if isinstance(allergies, str):
            allergies = [allergies]
        health_conditions = profile.get("health_conditions", [])
        if isinstance(health_conditions, str):
            health_conditions = [health_conditions]

        allergy_block = ""
        if allergies:
            allergy_block = f"\n  ⚠️ ALLERGIES — NEVER USE: {', '.join(allergies)}"
            if any("nut" in a.lower() for a in allergies):
                allergy_block += (
                    "\n  ⚠️ NUT ALLERGY: also exclude almonds, cashews, "
                    "pistachios, walnuts, peanuts, nut oils, marzipan"
                )

        health_block = ""
        conds = [h.lower() for h in health_conditions]
        if "diabetes" in conds:
            health_block += "\n  ⚠️ DIABETES: keep carbs ≤45g/serving, low GI foods, no refined sugar or white rice"
        if "hypertension" in conds:
            health_block += "\n  ⚠️ HYPERTENSION: sodium <600mg/serving, no added salt beyond recipe minimum"

        egg_note = ""
        if diet_type and "vegetarian" in diet_type.lower() and "non" not in diet_type.lower():
            egg_note = "\n  ⚠️ INDIAN VEGETARIAN: do NOT use eggs, omelette, or egg-based dishes"

        retry_block = ""
        if attempt > 0 and state.get("_last_violations"):
            retry_block = (
                f"\n⚠️ PREVIOUS ATTEMPT VIOLATIONS for {diet_type}: "
                f"{', '.join(state['_last_violations'])} — ABSOLUTELY DO NOT include these.\n"
            )

        max_time = profile.get("cooking_time_preference", "any")
        time_constraint = ""
        if max_time == "quick":
            time_constraint = "Total prep + cook time MUST be under 30 minutes."
        elif isinstance(max_time, int) and max_time > 0:
            time_constraint = f"Total time must not exceed {max_time} minutes."

        calorie_target = profile.get("calorie_goal") or state.get("calorie_limit") or 400

        cuisine_prefs = profile.get("cuisine_preferences", [])
        cuisine = state.get("cuisine_preference") or (cuisine_prefs[0] if cuisine_prefs else "Indian")
        servings = state.get("servings", 2)
        pantry = ", ".join(state.get("available_ingredients", [])[:20]) or "Common staples"
        query = state.get("user_query", "")

        return f"""You are an expert Indian chef creating a personalised recipe.

═══ USER PROFILE ═══
{get_profile_context_string(profile)}

═══ ABSOLUTE CONSTRAINTS — NEVER VIOLATE ═══
{diet_constraints}{allergy_block}{egg_note}{health_block}
{retry_block}
═══ REQUEST ═══
"{query}"

═══ PANTRY ═══
{pantry}

═══ PARAMETERS ═══
Cuisine: {cuisine} | Target calories: ≤{calorie_target} kcal/serving | Serves: {servings}
{time_constraint}
Currency: {cur}

FORMAT YOUR RESPONSE EXACTLY AS:

## 🍽️ [Recipe Name]

**Description:** [2 sentences explaining why this suits the user's profile]

### 📋 Ingredients
- [quantity] [unit] [ingredient] (~{cur}X)

### 👨‍🍳 Instructions
1. [Step — include exact timings in parentheses e.g. (3 min)]

### 📊 Nutrition (per serving)
| Nutrient | Amount |
|----------|--------|
| Calories | X kcal |
| Protein | Xg |
| Carbs | Xg |
| Fat | Xg |
| Fiber | Xg |

### ⏱️ Time & Servings
- **Prep:** X min | **Cook:** X min | **Total:** X min | **Serves:** {servings}

### 💡 Chef's Tips
1. [Practical tip relevant to the user's health/diet]
2. [Second tip]

Make the recipe genuinely delicious and perfectly tailored to the profile above."""

    def _extract_ingredients(self, recipe: str) -> list:
        ingredients = []
        in_ingredients = False

        for line in recipe.split('\n'):
            line = line.strip()
            if '### 📋 Ingredients' in line:
                in_ingredients = True
                continue
            if in_ingredients:
                if line.startswith('###') or line.startswith('##'):
                    break
                match = re.match(r'[-•]\s*([\d.]+)\s*([a-zA-Z]+)\s+([a-zA-Z\s]+?)(?:\s*\(~[^)]+\))?$', line)
                if match:
                    qty = float(match.group(1))
                    unit = match.group(2)
                    name = match.group(3).strip()
                    ingredients.append({"name": name, "quantity": qty, "unit": unit})

        return ingredients

    def _extract_nutrition_from_recipe(self, recipe: str) -> dict:
        nutrition = {}
        cal_match    = re.search(r'Calories\s*\|\s*(\d+)\s*kcal', recipe, re.IGNORECASE)
        protein_match = re.search(r'Protein\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
        carbs_match   = re.search(r'Carbs\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
        fat_match     = re.search(r'Fat\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
        fiber_match   = re.search(r'Fiber\s*\|\s*(\d+)g', recipe, re.IGNORECASE)
        if cal_match:     nutrition["calories"]  = int(cal_match.group(1))
        if protein_match: nutrition["protein_g"] = float(protein_match.group(1))
        if carbs_match:   nutrition["carbs_g"]   = float(carbs_match.group(1))
        if fat_match:     nutrition["fat_g"]      = float(fat_match.group(1))
        if fiber_match:   nutrition["fiber_g"]    = float(fiber_match.group(1))
        return nutrition

    def _check_violations(self, recipe: str, diet_type: str, allergies: list) -> list:
        violations = []
        rl = recipe.lower()
        forbidden = FORBIDDEN.get(diet_type.lower(), [])
        for f in forbidden:
            if f in rl:
                if f == "chicken" and "chickpea" in rl:
                    continue
                violations.append(f)
        if diet_type and "vegetarian" in diet_type.lower() and "non" not in diet_type.lower():
            for e in INDIAN_VEG_EXCLUDE:
                if e in rl:
                    violations.append(e)
        for allergen in allergies:
            al = allergen.lower()
            if al in ("nuts", "nut"):
                for nw in ["almond", "cashew", "pistachio", "walnut", "peanut", "hazelnut"]:
                    if nw in rl:
                        violations.append(nw)
            elif al in rl:
                violations.append(al)
        return violations

    def _check_ingredient_violations(self, ingredients: list, diet_type: str, allergies: list) -> list:
        violations = []
        if not ingredients:
            return violations
        forbidden = FORBIDDEN.get(diet_type.lower(), [])
        for ing in ingredients:
            name = ing.get("name", "").lower()
            for f in forbidden:
                if f in name:
                    if f == "chicken" and "chickpea" in name:
                        continue
                    violations.append(f)
            if diet_type and "vegetarian" in diet_type.lower():
                for e in INDIAN_VEG_EXCLUDE:
                    if e in name:
                        violations.append(e)
            for allergen in allergies:
                al = allergen.lower()
                if al == "nuts" and any(n in name for n in ["almond", "cashew", "walnut", "peanut"]):
                    violations.append(name)
                elif al in name:
                    violations.append(name)
        return list(set(violations))


def recipe_agent(state: AgentState, client=None) -> AgentState:
    return RecipeAgent().run(state, client=client)