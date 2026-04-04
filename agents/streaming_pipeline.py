"""
agents/streaming_pipeline.py — Fixed: conversational invalid input, greeting, context followup.
"""

import time
import re
from typing import Generator
from agents.state import AgentState
from agents.pantry_agent import detect_pantry_intent


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe(fn, state, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        return (result if result is not None else state), None
    except Exception as e:
        return state, str(e)


def _stream(text: str, delay: float = 0.004) -> Generator:
    for ch in str(text):
        yield {"type": "token", "text": ch}
        time.sleep(delay)


def _phase(agent: str, status: str, **extra):
    return {"type": "phase", "agent": agent, "status": status, **extra}


def _guard_intent(state: AgentState) -> AgentState:
    if state.get("intent", "general") != "general":
        return state
    detected = detect_pantry_intent(state.get("user_query", ""))
    if detected:
        state["intent"] = detected
    return state


def _resolve_user_services(state: AgentState, db, profile_db, feedback_db):
    user_id = state.get("user_id")
    if user_id:
        try:
            from services.user_services import get_user_services
            svc = get_user_services(user_id)
            db          = svc["db"]
            profile_db  = svc["profile_db"]
            feedback_db = svc["feedback_db"]
        except Exception:
            pass
    return db, profile_db, feedback_db


# ── Main streaming pipeline ───────────────────────────────────────────────────

def run_streaming_pipeline(
    state: AgentState,
    client,
    db,
    recipe_kb,
    profile_db=None,
    feedback_db=None,
) -> Generator:

    # ── ISOLATION GATE ────────────────────────────────────────────────────
    db, profile_db, feedback_db = _resolve_user_services(
        state, db, profile_db, feedback_db
    )

    # ── Phase 1: Memory ───────────────────────────────────────────────────
    yield _phase("🧠 Memory Agent", "running")
    t0 = time.time()
    try:
        from agents.memory_agent import MemoryAgent
        ma = MemoryAgent()
        state, err = _safe(ma.run, state, state, profile_db=profile_db, client=client)
    except Exception as e:
        err = str(e)
    yield _phase("🧠 Memory Agent", "done" if not err else "error",
                 time=round(time.time() - t0, 2))

    # ── Phase 2: Intent ───────────────────────────────────────────────────
    yield _phase("🎯 Intent Agent", "running")
    t0 = time.time()
    try:
        from agents.intent_router import intelligent_router_agent
        state, _ = _safe(intelligent_router_agent, state, state, client=client)
    except Exception:
        pass
    state  = _guard_intent(state)
    intent = state.get("intent", "general")
    yield _phase("🎯 Intent Agent", "done", time=round(time.time() - t0, 2), intent=intent)

    # ════════════════════════════════════════════════════════════════════════
    # INVALID INPUT — conversational, warm response
    # ════════════════════════════════════════════════════════════════════════
    if intent == "invalid_input":
        msg = _invalid_input_response(state, client)
        state["assistant_message"] = msg
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # GREETING
    # ════════════════════════════════════════════════════════════════════════
    if intent == "greeting":
        profile = state.get("user_profile", {})
        msg = _build_greeting(profile)
        state["assistant_message"] = msg
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # MEMORY RECALL
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "memory_recall":
        yield _phase("🧠 Memory Agent", "running")
        t0 = time.time()
        try:
            state, err = _safe(ma.recall, state, state, client)
        except Exception as e:
            err = str(e)
        yield _phase("🧠 Memory Agent", "done" if not err else "error",
                     time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", "No profile found."))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # CONTEXT FOLLOWUP — answer questions about the last recipe
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "context_followup":
        yield _phase("🍳 Recipe Agent", "running")
        t0 = time.time()
        msg = _context_followup_response(state, client)
        state["assistant_message"] = msg
        yield _phase("🍳 Recipe Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # PANTRY: ADD
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "add_inventory":
        yield _phase("📦 Pantry Agent", "running")
        t0 = time.time()
        from agents.pantry_agent import PantryAgent
        state = PantryAgent()._add_items(state, client, db)
        yield _phase("📦 Pantry Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", "❌ Could not add items."))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # PANTRY: VIEW
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "view_inventory":
        yield _phase("📦 Pantry Agent", "running")
        t0 = time.time()
        from agents.pantry_agent import PantryAgent
        state = PantryAgent()._view_pantry(state, db)
        yield _phase("📦 Pantry Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", "Pantry is empty."))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # PANTRY: REMOVE / CLEAR
    # ════════════════════════════════════════════════════════════════════════
    elif intent in ("remove_inventory", "remove_all_inventory"):
        yield _phase("📦 Pantry Agent", "running")
        t0 = time.time()
        from agents.pantry_agent import PantryAgent
        pa = PantryAgent()
        if intent == "remove_all_inventory":
            state = pa._clear_pantry(state, db)
        else:
            state = pa._remove_items(state, client, db)
        yield _phase("📦 Pantry Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", "Done."))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # RECIPE / RECOMMENDATION / MODIFY
    # ════════════════════════════════════════════════════════════════════════
    elif intent in ("generate_recipe", "smart_recommendation", "modify_recipe"):
        yield from _run_recipe_pipeline(state, client, db, recipe_kb)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # MEAL PLAN
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "meal_plan":
        yield _phase("📅 Meal Planner", "running")
        t0 = time.time()
        try:
            from agents.planner_agent import meal_plan_agent
            state = meal_plan_agent(state, client=client, db=db)
        except Exception as e:
            state["assistant_message"] = f"Could not generate meal plan: {e}"
        yield _phase("📅 Meal Planner", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # SHOPPING LIST
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "shopping_list":
        yield _phase("🛒 Shopping Agent", "running")
        t0 = time.time()
        try:
            from agents.shopping_agent import shopping_agent
            state = shopping_agent(state, db=db, client=client)
        except Exception as e:
            state["assistant_message"] = f"Could not generate shopping list: {e}"
        yield _phase("🛒 Shopping Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # DAILY NUTRITION
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "daily_nutrition":
        yield _phase("📊 Nutrition Agent", "running")
        t0 = time.time()
        try:
            from agents.nutrition_tracker import get_daily_nutrition_summary
            state = get_daily_nutrition_summary(state, db, client)
        except Exception as e:
            state["assistant_message"] = f"Could not load nutrition data: {e}"
        yield _phase("📊 Nutrition Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # SAVE MEAL
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "save_meal":
        yield _phase("📅 Meal Planner", "running")
        t0 = time.time()
        try:
            from agents.nutrition_tracker import save_meal_to_calendar
            if not state.get("generated_recipe"):
                last = _find_last_recipe(state)
                if last:
                    state["generated_recipe"] = last
            q_lower   = state.get("user_query", "").lower()
            meal_type = "dinner"
            for mt in ["breakfast", "lunch", "snack"]:
                if mt in q_lower:
                    meal_type = mt
                    break
            state = save_meal_to_calendar(state, db, meal_type)
        except Exception as e:
            state["assistant_message"] = f"Could not save meal: {e}"
        yield _phase("📅 Meal Planner", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # HEALTH ADVICE
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "health_advice":
        yield _phase("🏥 Health Agent", "running")
        t0 = time.time()
        try:
            from agents.health_agent import health_agent
            state = health_agent(state, client=client)
        except Exception as e:
            state["assistant_message"] = _health_fallback(state, client)
        yield _phase("🏥 Health Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # ECO TIPS
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "eco_tips":
        yield _phase("🌱 Eco Agent", "running")
        t0 = time.time()
        msg = _eco_response(state, db)
        state["assistant_message"] = msg
        yield _phase("🌱 Eco Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # BUDGET ANALYSIS
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "budget_analysis":
        yield _phase("💰 Budget Agent", "running")
        t0 = time.time()
        msg = _build_budget_response(state, client)
        state["assistant_message"] = msg
        yield _phase("💰 Budget Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # COOKING TIPS
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "cooking_tips":
        yield _phase("🍳 Recipe Agent", "running")
        t0 = time.time()
        try:
            profile = state.get("user_profile", {})
            query   = state.get("user_query", "")
            prompt  = (
                f'You are an expert Indian chef. Answer precisely:\n\n"{query}"\n\n'
                f'User: {profile.get("diet_type","vegetarian")}, '
                f'{profile.get("skill_level","intermediate")} cook.\n\n'
                "Give: direct answer, exact times/temps, common mistakes, one pro tip.\n"
                "Under 200 words. Use bullet points."
            )
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4, max_tokens=400,
            )
            msg = resp.choices[0].message.content.strip()
        except Exception as e:
            msg = f"Cooking tips unavailable: {e}"
        state["assistant_message"] = msg
        yield _phase("🍳 Recipe Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # RATE RECIPE
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "rate_recipe":
        yield _phase("⭐ Taste Agent", "running")
        t0 = time.time()
        state = _handle_rating(state, feedback_db)
        yield _phase("⭐ Taste Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # VIEW CALENDAR
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "view_calendar":
        yield _phase("📅 Meal Planner", "running")
        t0 = time.time()
        try:
            from datetime import date
            from collections import defaultdict
            meals = db.get_meal_plans(days=7) if db else []
            if meals:
                by_date = defaultdict(list)
                for m in meals:
                    by_date[m.get("plan_date", "?")].append(m)
                lines = ["## 📅 Meal Calendar — Last 7 Days\n"]
                for d in sorted(by_date.keys(), reverse=True):
                    label = "**Today**" if d == date.today().isoformat() else f"**{d}**"
                    total_cal = 0
                    lines.append(label)
                    for m in by_date[d]:
                        cal = m.get("calories", 0)
                        total_cal += cal
                        lines.append(f"  • {m.get('meal_type','').title()}: {m.get('recipe_name','')} ({cal} kcal)")
                    lines.append(f"  *Total: {total_cal} kcal*\n")
                msg = "\n".join(lines)
            else:
                msg = (
                    "📅 **No meals logged yet.**\n\n"
                    "After generating a recipe, say *'save this as dinner'* to start tracking."
                )
            state["assistant_message"] = msg
        except Exception as e:
            state["assistant_message"] = f"Could not load calendar: {e}"
        yield _phase("📅 Meal Planner", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # START COOKING MODE
    # ════════════════════════════════════════════════════════════════════════
    elif intent == "start_cooking_mode":
        yield _phase("🍳 Recipe Agent", "running")
        t0 = time.time()
        recipe = state.get("generated_recipe", "") or _find_last_recipe(state)
        if recipe:
            state["assistant_message"] = (
                "🍳 **Cooking Mode Ready!**\n\n"
                "Click **'🍳 Start Cooking Mode'** button to begin step-by-step guidance.\n\n"
                "I'll walk you through each step with timers. 👨‍🍳"
            )
        else:
            state["assistant_message"] = (
                "❌ No recipe found yet. Please generate a recipe first, then say 'start cooking mode'!"
            )
        yield _phase("🍳 Recipe Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(state.get("assistant_message", ""))
        yield {"type": "complete", "state": state}
        return

    # ════════════════════════════════════════════════════════════════════════
    # GENERAL FALLBACK — conversational LLM response
    # ════════════════════════════════════════════════════════════════════════
    else:
        yield _phase("🧠 Memory Agent", "running")
        t0 = time.time()
        msg = _general_response(state, client)
        state["assistant_message"] = msg
        yield _phase("🧠 Memory Agent", "done", time=round(time.time() - t0, 2))
        yield from _stream(msg)
        yield {"type": "complete", "state": state}
        return


# ── Recipe sub-pipeline ───────────────────────────────────────────────────────

def _run_recipe_pipeline(state, client, db, recipe_kb) -> Generator:
    from agents.budget_agent import budget_agent
    from agents.nutrition_agent import _calculate_nutrition

    # Pantry context
    yield _phase("🥕 Pantry Agent", "running")
    t0        = time.time()
    groceries = db.get_all_groceries() if db else []
    expiring  = db.get_expiring_soon(days=3) if db else []
    state["available_ingredients"] = [g["item_name"] for g in groceries]
    if expiring:
        exp_names = [e["item_name"] for e in expiring[:3]]
        state["user_query"] = (
            state.get("user_query", "")
            + f" (prioritise using: {', '.join(exp_names)} which are expiring soon)"
        )
    yield _phase("🥕 Pantry Agent", "done", time=round(time.time() - t0, 2))

    # Recipe generation
    yield _phase("🍳 Recipe Agent", "running")
    t0 = time.time()
    try:
        from agents.recipe_agent import RecipeAgent
        ra = RecipeAgent()
        state, err = _safe(ra.run, state, state, client=client)
    except Exception as e:
        state["generated_recipe"] = f"Recipe generation failed: {e}"
    recipe = state.get("generated_recipe", "")
    yield from _stream(recipe)
    yield _phase("🍳 Recipe Agent", "done", time=round(time.time() - t0, 2))

    _extract_ingredients(state, recipe)

    # Nutrition
    yield _phase("📊 Nutrition Agent", "running")
    t0 = time.time()
    try:
        ings     = state.get("recipe_ingredients_structured", [])
        servings = state.get("servings", 2)
        if ings:
            state = _calculate_nutrition(state, ings, servings, client)
    except Exception:
        pass
    yield _phase("📊 Nutrition Agent", "done", time=round(time.time() - t0, 2))
    if state.get("nutrition_data"):
        yield {"type": "section", "title": "📊 Nutrition", "content": state["nutrition_data"]}

    # Budget
    yield _phase("💰 Budget Agent", "running")
    t0 = time.time()
    try:
        state = budget_agent(state)
    except Exception:
        pass
    yield _phase("💰 Budget Agent", "done", time=round(time.time() - t0, 2))
    if state.get("budget_analysis"):
        yield {"type": "section", "title": "💰 Budget", "content": state["budget_analysis"]}

    # Eco
    yield _phase("🌱 Eco Agent", "running")
    t0 = time.time()
    try:
        from agents.eco_agent import eco_agent
        state = eco_agent(state, db=db)
    except Exception:
        pass
    yield _phase("🌱 Eco Agent", "done", time=round(time.time() - t0, 2))
    if state.get("eco_score"):
        yield {"type": "section", "title": "🌱 Eco", "content": state["eco_score"]}

    # Health
    yield _phase("🏥 Health Agent", "running")
    t0 = time.time()
    try:
        from agents.health_agent import health_agent
        state = health_agent(state, client=client)
    except Exception:
        pass
    yield _phase("🏥 Health Agent", "done", time=round(time.time() - t0, 2))
    rec = state.get("health_recommendations", "")
    if rec and "✅" not in rec and len(rec) > 10:
        yield {"type": "section", "title": "🏥 Health", "content": rec}


# ── Ingredient extraction ─────────────────────────────────────────────────────

def _extract_ingredients(state: AgentState, recipe_text: str):
    if not recipe_text:
        return
    pattern = re.compile(
        r"[-•]\s*([0-9½¼¾]+(?:[./][0-9]+)?)\s*"
        r"(kg|g|grams?|ml|l|liters?|cups?|tbsp|tsp|pieces?|bunch|cloves?|pinch|medium|large|small)?\s*"
        r"([a-zA-Z][a-zA-Z\s\-]+?)(?:\s*[,\(~\n]|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    ing_section = re.search(
        r"###\s*📋\s*Ingredients\s*\n(.*?)(?=\n###|\n##|$)",
        recipe_text, re.DOTALL | re.IGNORECASE,
    )
    search_text = ing_section.group(1) if ing_section else recipe_text
    ingredients = []
    for m in pattern.finditer(search_text):
        qs   = m.group(1).replace("½","0.5").replace("¼","0.25").replace("¾","0.75")
        unit = m.group(2) or "grams"
        name = m.group(3).strip().rstrip("(~, ")
        try:
            qty = float(qs)
        except ValueError:
            qty = 1.0
        if 2 < len(name) < 40:
            ingredients.append({"name": name.lower(), "quantity": qty, "unit": unit.lower()})
    if ingredients:
        state["recipe_ingredients_structured"] = ingredients


# ── Rating handler ────────────────────────────────────────────────────────────

def _handle_rating(state: AgentState, feedback_db) -> AgentState:
    query = state.get("user_query", "")
    star_match = re.search(r"(\d)\s*(?:star|/5|out of)", query.lower())
    if star_match:
        rating = int(star_match.group(1))
    elif any(w in query.lower() for w in ["loved","amazing","delicious","excellent"]):
        rating = 5
    elif any(w in query.lower() for w in ["good","liked","nice","great"]):
        rating = 4
    elif any(w in query.lower() for w in ["okay","average","alright"]):
        rating = 3
    elif any(w in query.lower() for w in ["bad","disliked","not great"]):
        rating = 2
    else:
        rating = 4

    last_recipe = _find_last_recipe(state)
    recipe_name = "Previous Recipe"
    if last_recipe:
        nm = re.search(r"##\s*🍽️\s*(.+)", last_recipe)
        if nm:
            recipe_name = nm.group(1).strip()

    if feedback_db:
        try:
            profile     = state.get("user_profile", {})
            nutrition   = state.get("total_nutrition", {})
            ingredients = [i.get("name","") for i in state.get("recipe_ingredients_structured",[])]
            cp          = profile.get("cuisine_preferences", ["Indian"])
            cuisine     = cp[0] if isinstance(cp, list) and cp else "Indian"
            feedback_db.save_rating(
                recipe_name    = recipe_name,
                rating         = rating,
                recipe_content = last_recipe[:500],
                cuisine        = cuisine,
                diet_type      = profile.get("diet_type",""),
                calories       = nutrition.get("calories", 0),
                ingredients    = ingredients,
                session_id     = state.get("session_id",""),
            )
        except Exception:
            pass

    stars     = "⭐" * rating + "☆" * (5 - rating)
    reactions = {
        5: "Wonderful! That makes me so happy to hear! 🎉 I'll suggest similar recipes more often.",
        4: "Great to know! I'll remember what you enjoyed for next time. 😊",
        3: "Thanks for the feedback — I'll work on improving! What could be better?",
        2: "Sorry it wasn't great. I'll suggest something different next time. 🙏",
        1: "I apologise — I'll completely change my approach for you!",
    }
    state["assistant_message"] = (
        f"## {stars} Rating Saved!\n\n"
        f"**{recipe_name}** — {rating}/5 stars\n\n"
        f"{reactions.get(rating,'Thanks!')}\n\n"
        f"*Your taste profile is now smarter — better recommendations coming!* 🧠"
    )
    return state


def _find_last_recipe(state: AgentState) -> str:
    # First check state directly
    recipe = state.get("generated_recipe", "")
    if recipe and "## 🍽️" in recipe:
        return recipe

    # Then check conversation history
    history = state.get("conversation_history", [])
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if "## 🍽️" in content and "### 📋 Ingredients" in content:
                return content
    return ""


# ── CONVERSATIONAL RESPONSE BUILDERS ─────────────────────────────────────────

def _invalid_input_response(state: AgentState, client) -> str:
    """Generate a warm, conversational response for invalid/gibberish input."""
    query = state.get("user_query", "")
    profile = state.get("user_profile", {})
    name = profile.get("name", "")
    name_part = f", {name}" if name else ""

    # Try LLM for a natural response
    if client:
        try:
            history = state.get("conversation_history", [])
            recent_ctx = ""
            if history:
                last_few = history[-4:]
                recent_ctx = "\n".join(
                    f"{m['role'].upper()}: {m['content'][:100]}" for m in last_few
                )

            prompt = f"""You are NutriBot, a warm and friendly AI meal assistant.
The user sent a message that doesn't seem to be a valid cooking/food query.

User message: "{query}"
{f'Recent context: {recent_ctx}' if recent_ctx else ''}
User profile: {profile.get('diet_type', 'not set')} diet, {profile.get('fitness_goal', 'no specific goal')}

Respond in a warm, conversational way. Possibilities:
- If it looks like a typo or incomplete message, guess what they might have meant and offer to help
- If it's clearly gibberish/keyboard mashing, gently let them know you didn't understand and offer helpful suggestions
- Suggest 2-3 specific things you CAN help with, personalised to their profile if known
- Keep it short (3-4 sentences max), friendly, and helpful
- Do NOT say "I cannot understand" or be robotic — be warm like a friend

Do not use bullet points for suggestions — write naturally."""

            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass

    # Fallback static responses
    diet = profile.get("diet_type", "")
    diet_hint = f" Since you're {diet}, I can suggest some great {diet} recipes!" if diet else ""

    return (
        f"Hmm, I didn't quite catch that{name_part}! 😊{diet_hint}\n\n"
        "Here are some things I can help you with — just try one:\n"
        "• *\"Make me palak paneer\"* — for a recipe\n"
        "• *\"I bought 500g paneer\"* — to track groceries\n"
        "• *\"Plan my meals for 3 days\"* — for a meal plan"
    )


def _build_greeting(profile: dict) -> str:
    """Build a personalized, warm greeting."""
    name = profile.get("name", "")
    diet = profile.get("diet_type", "")
    goal = profile.get("fitness_goal", "")
    conditions = profile.get("health_conditions", [])

    # Returning user with profile
    if profile:
        name_part  = f" {name}!" if name else "!"
        diet_part  = f" I know you're **{diet}**." if diet else ""
        goal_part  = f" Working towards **{goal.replace('_', ' ')}** — great!" if goal else ""
        cond_part  = ""
        if conditions:
            conds = conditions if isinstance(conditions, list) else [conditions]
            cond_part = f" I'll keep your **{', '.join(conds)}** in mind for all recipes."

        return (
            f"Hey there{name_part} Welcome back to **NutriBot**! 🥗{diet_part}{goal_part}{cond_part}\n\n"
            "What can I help you with today?\n\n"
            "• 🍳 Generate a recipe\n"
            "• 📦 Track pantry items\n"
            "• 📅 Plan your weekly meals\n"
            "• 📊 Check today's nutrition\n"
            "• 💰 Budget-friendly ideas\n\n"
            "*Just tell me what you need in plain English!*"
        )
    else:
        # First-time user
        return (
            "👋 Hey there! I'm **NutriBot**, your personal AI meal assistant!\n\n"
            "I can help you:\n"
            "• 🍳 **Generate recipes** personalised to your diet & health\n"
            "• 📦 **Track your pantry** and reduce food waste\n"
            "• 📅 **Plan weekly meals** within your budget\n"
            "• 📊 **Monitor nutrition** — calories, protein, carbs\n"
            "• 💰 **Save money** with smart ingredient choices\n"
            "• 🌱 **Reduce carbon footprint** with eco scores\n\n"
            "To get started, tell me a bit about yourself! For example:\n"
            "*\"I'm vegetarian, trying to lose weight, and love Indian food\"*\n\n"
            "Or just ask me anything — I'm here to help! 😊"
        )


def _context_followup_response(state: AgentState, client) -> str:
    """Answer a follow-up question about the last recipe."""
    query = state.get("user_query", "")
    profile = state.get("user_profile", {})
    last_recipe = _find_last_recipe(state)

    if not last_recipe:
        return (
            "I don't have a recipe in context right now. "
            "Generate one first and then ask me follow-up questions! 🍳"
        )

    if client:
        try:
            prompt = f"""You are NutriBot, a helpful cooking assistant.
The user is asking a follow-up question about a recipe we just discussed.

RECIPE CONTEXT (first 1500 chars):
{last_recipe[:1500]}

USER'S FOLLOW-UP QUESTION: "{query}"

Answer the question directly and helpfully, referencing the specific recipe.
Keep it conversational and concise (under 150 words).
User profile: {profile.get('diet_type', 'not set')} diet."""

            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"I had trouble answering that. Could you rephrase? ({e})"

    return "Could you clarify your question? I want to make sure I help you correctly! 😊"


# ── Budget response ───────────────────────────────────────────────────────────

def _build_budget_response(state: AgentState, client) -> str:
    profile = state.get("user_profile", {})
    try:
        from services.price_service import PriceService
        from agents.user_profile import _currency
        ps           = PriceService()
        cur          = _currency(profile)
        diet         = profile.get("diet_type", "vegetarian")
        cheapest     = ps.get_cheapest_protein(diet)
        bp           = profile.get("budget_preference", {})
        budget_amt   = bp.get("amount", 500) if isinstance(bp, dict) else 500
        protein_name  = cheapest.get("name",            "lentil (dal)")
        protein_price = cheapest.get("price_per_kg",    80)
        protein_g     = cheapest.get("protein_per_100g",24)
        return (
            f"## 💰 Budget Analysis\n\n"
            f"**Your weekly budget:** {cur}{budget_amt}\n\n"
            f"**Best value protein:** **{protein_name.title()}** — "
            f"{cur}{protein_price}/kg | {protein_g}g protein/100g\n\n"
            f"**₹500/week staples:**\n"
            f"| Item | Cost |\n|------|------|\n"
            f"| 1kg Dal | ₹80-120 |\n| 2kg Rice | ₹120 |\n"
            f"| 1kg Onion | ₹40 |\n| 500g Tomato | ₹30 |\n"
            f"| 500g Paneer | ₹140 |\n| 1kg Spinach | ₹40 |\n"
            f"| Spices | ₹30 |\n| **Total** | **~₹480** ✅ |"
        )
    except Exception:
        return (
            "## 💰 Budget Tips (₹500/week)\n\n"
            "• Soy chunks: ₹120/kg — 52g protein/100g ⭐\n"
            "• Dal: ₹80-120/kg — 24g protein/100g\n"
            "• Chickpeas: ₹80/kg — 19g protein/100g\n"
            "• Paneer: ₹280/kg — use sparingly"
        )


# ── Eco response ──────────────────────────────────────────────────────────────

def _eco_response(state: AgentState, db) -> str:
    eco      = state.get("eco_score", {})
    expiring = db.get_expiring_soon(days=3) if db else []
    lines    = ["## 🌱 Eco Score & Carbon Tips\n"]
    if eco:
        score = eco.get("score", 0)
        grade = eco.get("grade", "?")
        co2   = eco.get("co2_kg", 0)
        saved = eco.get("co2_saved_kg", 0)
        tips  = eco.get("all_tips", [])
        color = {"A+":"🟢","A":"🟢","B":"🟡","C":"🟡","D":"🔴"}.get(grade,"🟡")
        lines += [
            f"**Last recipe:** {color} {score:.0f}/100 — Grade **{grade}**",
            f"• CO₂ used: {co2:.2f} kg  |  CO₂ saved: {saved:.2f} kg",
        ]
        if tips:
            lines.append("\n**Why:**")
            lines.extend(f"• {t}" for t in tips)
    else:
        lines.append("*Generate a recipe to see your eco score!*\n")
    if expiring:
        lines += ["", "**⚠️ Use before expiry (+10 eco pts each):**"]
        for e in expiring[:5]:
            lines.append(f"• 🔴 {e['item_name'].title()}")
    lines += [
        "",
        "**🌍 General eco tips:**",
        "• Vegetarian meals → 60% less CO₂ than beef",
        "• Seasonal local veg → 70% lower carbon footprint",
        "• Lentils/dal → most sustainable protein available",
    ]
    return "\n".join(lines)


# ── General fallback — CONVERSATIONAL ────────────────────────────────────────

def _general_response(state: AgentState, client) -> str:
    """Fully conversational general response using LLM with full context."""
    try:
        profile  = state.get("user_profile", {})
        history  = state.get("conversation_history", [])
        query    = state.get("user_query", "")
        last_recipe = _find_last_recipe(state)

        # Build rich context
        hist_txt = ""
        if history:
            hist_txt = "\n".join(
                f"{m['role'].upper()}: {m['content'][:200]}" for m in history[-8:]
            )

        recipe_ctx = ""
        if last_recipe:
            # Extract just the name
            nm = re.search(r"##\s*🍽️\s*(.+)", last_recipe)
            if nm:
                recipe_ctx = f"\nLast recipe discussed: {nm.group(1).strip()}"

        from agents.user_profile import get_profile_context_string
        prompt = (
            f"You are NutriBot, a warm, friendly AI meal assistant specialising in Indian nutrition.\n"
            f"Respond conversationally — like a knowledgeable friend, not a robot.\n\n"
            f"{get_profile_context_string(profile)}\n"
            f"{recipe_ctx}\n\n"
            + (f"RECENT CONVERSATION:\n{hist_txt}\n\n" if hist_txt else "")
            + f"USER: {query}\n\n"
            "Be helpful, warm, and specific. If you can connect to their food/health goals, do so. "
            "Under 200 words. No bullet lists unless the question specifically calls for them."
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6, max_tokens=350,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return (
            "I'm here to help! Here are some things you can try:\n"
            "• 📦 *'I bought 500g paneer'* — track groceries\n"
            "• 🍳 *'Make me palak paneer'* — get a recipe\n"
            "• 📅 *'Plan my meals for 3 days'* — meal planning\n"
            "• 📊 *'Show my daily nutrition'* — track intake\n\n"
            "Just ask in plain English! 😊"
        )


def _health_fallback(state: AgentState, client) -> str:
    try:
        profile = state.get("user_profile", {})
        query   = state.get("user_query", "")
        conds   = profile.get("health_conditions", [])
        prompt  = (
            f'You are a certified nutritionist. Answer this question warmly and helpfully:\n\n"{query}"\n\n'
            f'Patient profile: {profile.get("diet_type","vegetarian")} diet, conditions: {conds}\n\n'
            "Evidence-based, practical, under 250 words. Be conversational and supportive."
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=450,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "Health advice is temporarily unavailable. Please try again in a moment! 🙏"