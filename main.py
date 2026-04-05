"""
backend/main.py — NutriBot Backend API v6.0
Full per-user data isolation. Every endpoint receives a user_id and
routes to that user's private database files.

LLM Strategy:
  - Groq  → all chat, recipe, nutrition, health, planning agents (fast, free)
  - Gemini → ONLY /fridge/scan and /vision/analyze (vision capability)
"""

import os
import sys
import uuid
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from agents.recipe_agent import RecipeAgent

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv()

# ── Global services ───────────────────────────────────────────────────────────
_global_client       = None   # Groq  — used by ALL non-vision endpoints
_global_recipe_kb    = None   # recipe knowledge base (shared/read-only)
_global_gemini_model = None   # Gemini — used ONLY by /fridge/scan and /vision/analyze


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _global_client, _global_recipe_kb, _global_gemini_model

    print("🚀 Starting NutriBot Backend API v6.0 (per-user isolation)...")

    # ── Groq (all agents) ─────────────────────────────────────────────────
    from groq import Groq
    from tools.tools import load_recipe_dataset, build_recipe_knowledge_base

    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        _global_client = Groq(api_key=groq_key)
        print("✅ Groq client ready")
    else:
        print("⚠️  GROQ_API_KEY not set — LLM features disabled")

    dataset = load_recipe_dataset()
    _global_recipe_kb = build_recipe_knowledge_base(dataset)
    print("✅ Recipe knowledge base ready")

    # ── Gemini (vision only) ──────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            _global_gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")
            print("✅ Gemini Vision ready (fridge scanner active)")
        except Exception as e:
            print(f"⚠️  Gemini init failed: {e} — fridge scanner disabled")
    else:
        print("⚠️  GEMINI_API_KEY not set — fridge scanner disabled")

    print("✅ All global services ready")
    yield
    print("🛑 Shutting down...")


app = FastAPI(
    title="NutriBot API",
    description="Smart Meal Assistant — per-user data isolation",
    version="6.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class UserMessage(BaseModel):
    query:    str
    session_id: Optional[str]  = None
    user_id:    Optional[str]  = "default"
    input_mode: str            = "text"
    dietary_restrictions: Optional[List[str]] = None
    health_conditions:    Optional[List[str]] = None
    calorie_limit:  Optional[int]   = 500
    budget_limit:   Optional[float] = 500.0
    servings:       Optional[int]   = 2
    cuisine_preference: Optional[str] = "Indian"


class UserProfileUpdate(BaseModel):
    name:                Optional[str]       = None
    diet_type:           Optional[str]       = None
    fitness_goal:        Optional[str]       = None
    cuisine_preferences: Optional[List[str]] = None
    allergies:           Optional[List[str]] = None
    health_conditions:   Optional[List[str]] = None
    calorie_goal:        Optional[int]       = None
    budget_preference:   Optional[Dict[str, Any]] = None
    cooking_time_preference: Optional[str]   = None
    skill_level:         Optional[str]       = None


class GroceryItemAdd(BaseModel):
    item_name:         str
    quantity:          float = 1.0
    unit:              str   = "pieces"
    category:          Optional[str] = None
    is_perishable:     bool  = False
    days_until_expiry: Optional[int] = None


class GroceryItemRemove(BaseModel):
    item_name: str


class MealPlanSave(BaseModel):
    plan_date:   str
    meal_type:   str
    recipe_name: str
    calories:    int   = 0
    protein_g:   float = 0
    carbs_g:     float = 0
    fat_g:       float = 0
    notes:       Optional[str] = None


class RecipeRating(BaseModel):
    recipe_name:    str
    rating:         int
    feedback:       Optional[str] = None
    cuisine:        Optional[str] = None
    recipe_content: Optional[str] = None


class APIResponse(BaseModel):
    success: bool
    message: str
    data:    Optional[Any] = None
    error:   Optional[str] = None


class ParseStepsRequest(BaseModel):
    recipe_text: str


class HealthAdviceRequest(BaseModel):
    query:   str
    user_id: Optional[str] = None


class ShoppingListRequest(BaseModel):
    query:   str
    user_id: Optional[str] = None


class WeeklyPlanRequest(BaseModel):
    query:   str
    user_id: Optional[str] = None


class EcoScoreRequest(BaseModel):
    ingredients: List[Dict[str, Any]]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_svc(user_id: Optional[str]):
    """Return per-user service objects (Groq-based)."""
    from services.user_services import get_user_services
    return get_user_services(user_id or "default")


def _get_state(msg: UserMessage):
    """Build AgentState from a UserMessage, with user_id threaded through."""
    from agents.workflow import build_initial_state
    svc   = _get_svc(msg.user_id)
    state = build_initial_state(
        user_query           = msg.query,
        user_id              = msg.user_id or "default",
        dietary_restrictions = msg.dietary_restrictions or [],
        health_conditions    = msg.health_conditions   or [],
        calorie_limit        = msg.calorie_limit or 500,
        budget_limit         = float(msg.budget_limit or 500),
        servings             = msg.servings or 2,
        cuisine_preference   = msg.cuisine_preference or "Indian",
        extra_ingredients    = [],
        conversation_history = [],
    )
    state["session_id"]   = msg.session_id or str(uuid.uuid4())[:8]
    state["user_profile"] = svc["profile_db"].get_full_profile()
    return state, svc


# ── System ────────────────────────────────────────────────────────────────────

@app.get("/", response_model=APIResponse, tags=["System"])
async def root():
    return APIResponse(
        success=True, message="NutriBot API v6.0",
        data={
            "version":         "6.0.0",
            "groq_available":  bool(_global_client),
            "gemini_available": bool(_global_gemini_model),
        }
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status":  "healthy",
        "groq":    bool(_global_client),
        "gemini":  bool(_global_gemini_model),
    }


# ── Chat (Groq) ───────────────────────────────────────────────────────────────

@app.post("/chat", response_model=APIResponse, tags=["Chat"])
async def chat(message: UserMessage):
    from agents.streaming_pipeline import run_streaming_pipeline

    state, svc = _get_state(message)
    final_state = state

    for event in run_streaming_pipeline(
        state, _global_client,          # ← Groq
        svc["db"], _global_recipe_kb,
        profile_db  = svc["profile_db"],
        feedback_db = svc["feedback_db"],
    ):
        if event.get("type") == "complete":
            final_state = event.get("state", state)

    intent       = final_state.get("intent", "general")
    message_text = (
        final_state.get("assistant_message") or
        final_state.get("generated_recipe")  or
        "Request processed."
    )

    return APIResponse(
        success=True, message="OK",
        data={
            "response":         message_text,
            "intent":           intent,
            "session_id":       final_state.get("session_id"),
            "nutrition":        final_state.get("nutrition_data"),
            "budget":           final_state.get("budget_analysis"),
            "eco":              final_state.get("eco_score"),
            "generated_recipe": final_state.get("generated_recipe"),
        }
    )


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(message: UserMessage):
    from agents.streaming_pipeline import run_streaming_pipeline

    async def generate():
        state, svc = _get_state(message)
        for event in run_streaming_pipeline(
            state, _global_client,      # ← Groq
            svc["db"], _global_recipe_kb,
            profile_db  = svc["profile_db"],
            feedback_db = svc["feedback_db"],
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── Profile (Groq) ────────────────────────────────────────────────────────────

@app.get("/profile/{user_id}", response_model=APIResponse, tags=["Profile"])
async def get_profile(user_id: str):
    svc     = _get_svc(user_id)
    profile = svc["profile_db"].get_full_profile()
    profile["user_id"] = user_id
    return APIResponse(success=True, message="Profile retrieved", data=profile)


@app.put("/profile/{user_id}", response_model=APIResponse, tags=["Profile"])
async def update_profile(user_id: str, profile_update: UserProfileUpdate):
    svc = _get_svc(user_id)
    for key, value in profile_update.model_dump(exclude_none=True).items():
        svc["profile_db"].set(key, value)
    updated = svc["profile_db"].get_full_profile()
    updated["user_id"] = user_id
    return APIResponse(success=True, message="Profile updated", data=updated)


@app.delete("/profile/{user_id}", response_model=APIResponse, tags=["Profile"])
async def reset_profile(user_id: str):
    from services.user_services import evict_user_cache
    svc = _get_svc(user_id)
    svc["profile_db"].clear()
    evict_user_cache(user_id)
    return APIResponse(success=True, message="Profile reset", data={"user_id": user_id})


# ── Pantry ────────────────────────────────────────────────────────────────────

@app.get("/pantry", response_model=APIResponse, tags=["Pantry"])
async def get_pantry(user_id: str = Query("default")):
    svc   = _get_svc(user_id)
    items = svc["db"].get_all_groceries()
    return APIResponse(
        success=True, message="Pantry retrieved",
        data={"items": items, "count": len(items),
              "expiring_soon": svc["db"].get_expiring_soon(3)},
    )


@app.post("/pantry", response_model=APIResponse, tags=["Pantry"])
async def add_to_pantry(item: GroceryItemAdd, user_id: str = Query("default")):
    svc = _get_svc(user_id)
    ok  = svc["db"].add_grocery(
        item_name         = item.item_name,
        quantity          = item.quantity,
        unit              = item.unit,
        category          = item.category,
        is_perishable     = item.is_perishable,
        days_until_expiry = item.days_until_expiry,
    )
    if ok:
        return APIResponse(success=True, message=f"Added {item.item_name}", data=item.model_dump())
    return APIResponse(success=False, message="Failed", error="DB error")


@app.delete("/pantry", response_model=APIResponse, tags=["Pantry"])
async def remove_from_pantry(item: GroceryItemRemove, user_id: str = Query("default")):
    svc = _get_svc(user_id)
    ok  = svc["db"].delete_grocery(item.item_name)
    if ok:
        return APIResponse(success=True, message=f"Removed {item.item_name}",
                           data={"removed": item.item_name})
    return APIResponse(success=False, message=f"{item.item_name} not found", error="Not found")


@app.delete("/pantry/all", response_model=APIResponse, tags=["Pantry"])
async def clear_pantry(user_id: str = Query("default")):
    svc = _get_svc(user_id)
    svc["db"].clear_inventory()
    return APIResponse(success=True, message="Pantry cleared", data={})


@app.get("/pantry/expiring", response_model=APIResponse, tags=["Pantry"])
async def get_expiring(user_id: str = Query("default"), days: int = 3):
    svc      = _get_svc(user_id)
    expiring = svc["db"].get_expiring_soon(days)
    return APIResponse(success=True, message=f"Expiring in {days} days",
                       data={"items": expiring, "count": len(expiring)})


# ── Recipes (Groq) ────────────────────────────────────────────────────────────

@app.post("/recipe/generate", response_model=APIResponse, tags=["Recipes"])
async def generate_recipe(message: UserMessage):

    state, svc = _get_state(message)
    state["available_ingredients"] = [g["item_name"] for g in svc["db"].get_all_groceries()]
    state = RecipeAgent().run(state, client=_global_client)   # ← Groq
    return APIResponse(
        success=True, message="Recipe generated",
        data={
            "recipe":      state.get("generated_recipe", ""),
            "ingredients": state.get("recipe_ingredients_structured", []),
            "nutrition":   state.get("nutrition_data"),
            "budget":      state.get("budget_analysis"),
            "eco_score":   state.get("eco_score"),
        },
    )


@app.post("/recipe/rate", response_model=APIResponse, tags=["Recipes"])
async def rate_recipe(rating: RecipeRating, user_id: str = Query("default")):
    svc = _get_svc(user_id)
    rid = svc["feedback_db"].save_rating(
        recipe_name    = rating.recipe_name,
        rating         = rating.rating,
        recipe_content = rating.recipe_content or "",
        feedback_text  = rating.feedback or "",
        cuisine        = rating.cuisine or "",
    )
    return APIResponse(success=True, message=f"Rated {rating.rating}/5",
                       data={"recipe_name": rating.recipe_name, "rating": rating.rating, "id": rid})


# ── Meal plans (Groq) ─────────────────────────────────────────────────────────

@app.get("/mealplan", response_model=APIResponse, tags=["Meal Plans"])
async def get_meal_plans(user_id: str = Query("default"), days: int = 7):
    svc   = _get_svc(user_id)
    meals = svc["db"].get_meal_plans(days)
    return APIResponse(success=True, message=f"{len(meals)} meals",
                       data={"meals": meals, "count": len(meals)})


@app.get("/mealplan/today", response_model=APIResponse, tags=["Meal Plans"])
async def get_today_meals(user_id: str = Query("default")):
    svc   = _get_svc(user_id)
    meals = svc["db"].get_meal_plans_today()
    grouped: Dict[str, list] = {}
    for m in meals:
        grouped.setdefault(m.get("meal_type", "other"), []).append(m)
    return APIResponse(success=True, message="Today's meals",
                       data={"meals": meals, "grouped": grouped,
                             "date": date.today().isoformat()})


@app.post("/mealplan", response_model=APIResponse, tags=["Meal Plans"])
async def save_meal_plan(meal: MealPlanSave, user_id: str = Query("default")):
    svc = _get_svc(user_id)
    ok  = svc["db"].save_meal_plan(
        plan_date   = meal.plan_date,
        meal_type   = meal.meal_type,
        recipe_name = meal.recipe_name,
        calories    = meal.calories,
        protein_g   = meal.protein_g,
        carbs_g     = meal.carbs_g,
        fat_g       = meal.fat_g,
        notes       = meal.notes or "",
    )
    if ok:
        return APIResponse(success=True, message=f"Saved {meal.meal_type}", data=meal.model_dump())
    return APIResponse(success=False, message="Failed to save", error="DB error")


@app.post("/mealplan/week", response_model=APIResponse, tags=["Meal Plans"])
async def weekly_plan(req: WeeklyPlanRequest):
    from agents.planner_agent import meal_plan_agent
    from agents.workflow import build_initial_state

    uid   = req.user_id or "default"
    svc   = _get_svc(uid)
    state = build_initial_state(user_query=req.query, user_id=uid)
    state["user_profile"] = svc["profile_db"].get_full_profile()
    state = meal_plan_agent(state, client=_global_client, db=svc["db"])  # ← Groq
    return APIResponse(success=True, message="Weekly plan generated",
                       data={"plan": state.get("assistant_message", "")})


# ── Nutrition (Groq) ──────────────────────────────────────────────────────────

@app.get("/nutrition/today", response_model=APIResponse, tags=["Nutrition"])
async def today_nutrition(user_id: str = Query("default")):
    from agents.nutrition_tracker import get_daily_nutrition_summary
    from agents.workflow import build_initial_state

    svc   = _get_svc(user_id)
    state = build_initial_state(user_query="", user_id=user_id)
    state["user_profile"] = svc["profile_db"].get_full_profile()
    state = get_daily_nutrition_summary(state, svc["db"], _global_client)  # ← Groq
    return APIResponse(success=True, message="Today's nutrition",
                       data={"summary": state.get("daily_nutrition_summary", {}),
                             "message": state.get("assistant_message", ""),
                             "date":    date.today().isoformat()})


@app.get("/nutrition/week", response_model=APIResponse, tags=["Nutrition"])
async def weekly_nutrition(user_id: str = Query("default")):
    svc   = _get_svc(user_id)
    meals = svc["db"].get_meal_plans(7)
    daily: Dict[str, dict] = {}
    for m in meals:
        day = m.get("plan_date", "")
        if day not in daily:
            daily[day] = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
        daily[day]["calories"]  += m.get("calories",  0)
        daily[day]["protein_g"] += m.get("protein_g", 0)
        daily[day]["carbs_g"]   += m.get("carbs_g",   0)
        daily[day]["fat_g"]     += m.get("fat_g",     0)
    return APIResponse(success=True, message="Weekly nutrition",
                       data={"daily_totals": daily, "meals": meals})


# ── Budget ────────────────────────────────────────────────────────────────────

@app.get("/budget/cheapest-protein", response_model=APIResponse, tags=["Budget"])
async def cheapest_protein(user_id: str = Query("default"), diet_type: str = "vegetarian"):
    svc  = _get_svc(user_id)
    data = svc["price_service"].get_cheapest_protein(diet_type)
    return APIResponse(success=True, message="Cheapest protein", data=data)


@app.get("/budget/prices", response_model=APIResponse, tags=["Budget"])
async def all_prices(user_id: str = Query("default")):
    svc    = _get_svc(user_id)
    prices = svc["price_service"].get_all_prices()
    return APIResponse(success=True, message="All prices", data={"prices": prices})


@app.get("/budget/price/{ingredient}", response_model=APIResponse, tags=["Budget"])
async def ingredient_price(ingredient: str, user_id: str = Query("default"),
                            quantity_kg: float = 1.0):
    svc   = _get_svc(user_id)
    price = svc["price_service"].get_price(ingredient, quantity_kg)
    return APIResponse(success=True, message=f"Price for {ingredient}",
                       data={"ingredient": ingredient, "price_inr": price})


# ── Shopping (Groq) ───────────────────────────────────────────────────────────

@app.post("/shopping/generate", response_model=APIResponse, tags=["Shopping"])
async def shopping_list(req: ShoppingListRequest):
    from agents.shopping_agent import shopping_agent
    from agents.workflow import build_initial_state

    uid   = req.user_id or "default"
    svc   = _get_svc(uid)
    state = build_initial_state(user_query=req.query, user_id=uid)
    state["user_profile"] = svc["profile_db"].get_full_profile()
    state = shopping_agent(state, db=svc["db"], client=_global_client)  # ← Groq
    return APIResponse(success=True, message="Shopping list",
                       data={"shopping_list": state.get("assistant_message", "")})


# ── Cooking (Groq) ────────────────────────────────────────────────────────────

@app.post("/cooking/parse", response_model=APIResponse, tags=["Cooking"])
async def parse_steps(req: ParseStepsRequest):
    from agents.cooking_agent import CookingAgent
    steps = CookingAgent().parse_recipe_steps(req.recipe_text)
    return APIResponse(success=True, message=f"{len(steps)} steps",
                       data={"steps": steps, "total_steps": len(steps)})


# ── Health advice (Groq) ──────────────────────────────────────────────────────

@app.post("/health/advice", response_model=APIResponse, tags=["Health"])
async def health_advice(req: HealthAdviceRequest):
    from agents.health_agent import health_agent
    from agents.workflow import build_initial_state

    uid   = req.user_id or "default"
    svc   = _get_svc(uid)
    state = build_initial_state(user_query=req.query, user_id=uid)
    state["user_profile"] = svc["profile_db"].get_full_profile()
    state["intent"]       = "health_advice"
    state = health_agent(state, client=_global_client)  # ← Groq
    return APIResponse(success=True, message="Health advice",
                       data={"advice":          state.get("assistant_message", ""),
                             "recommendations": state.get("health_recommendations", "")})


# ── Eco score (Groq) ──────────────────────────────────────────────────────────

@app.post("/eco/calculate", response_model=APIResponse, tags=["Eco"])
async def eco_score(req: EcoScoreRequest, user_id: str = Query("default")):
    from agents.eco_agent import eco_agent
    from agents.workflow import build_initial_state

    svc   = _get_svc(user_id)
    state = build_initial_state(user_query="", user_id=user_id)
    state["recipe_ingredients_structured"] = req.ingredients
    state["user_profile"] = svc["profile_db"].get_full_profile()
    state = eco_agent(state, db=svc["db"])
    return APIResponse(success=True, message="Eco score", data=state.get("eco_score", {}))


# ── Feedback ──────────────────────────────────────────────────────────────────

@app.get("/feedback/stats", response_model=APIResponse, tags=["Feedback"])
async def feedback_stats(user_id: str = Query("default")):
    svc   = _get_svc(user_id)
    stats = svc["feedback_db"].get_preference_summary()
    return APIResponse(success=True, message="Feedback stats", data=stats)


@app.get("/feedback/top-cuisines", response_model=APIResponse, tags=["Feedback"])
async def top_cuisines(user_id: str = Query("default"), min_ratings: int = 1):
    svc = _get_svc(user_id)
    top = svc["feedback_db"].get_top_cuisines(min_ratings)
    return APIResponse(success=True, message="Top cuisines", data={"cuisines": top})


@app.get("/feedback/liked-ingredients", response_model=APIResponse, tags=["Feedback"])
async def liked_ingredients(user_id: str = Query("default"), min_likes: int = 2):
    svc   = _get_svc(user_id)
    liked = svc["feedback_db"].get_liked_ingredients(min_likes)
    return APIResponse(success=True, message="Liked ingredients", data={"ingredients": liked})


# ── Vision — image-based pantry add (Gemini) ──────────────────────────────────
#
# NOTE: Both /vision/analyze and /fridge/scan use Gemini (_global_gemini_model).
#       All other endpoints above use Groq (_global_client). Nothing else changed.

@app.post("/vision/analyze", response_model=APIResponse, tags=["Vision"])
async def analyze_image(
    file:    UploadFile = File(...),
    context: str        = Form("fridge"),
    user_id: str        = Form("default"),
):
    if not _global_client:
        return APIResponse(
            success=False,
            message="Vision unavailable",
            error="GROQ_API_KEY is not configured."
        )

    from vision.fridge_scanner import fridge_scan_pipeline

    raw_bytes    = await file.read()
    svc          = _get_svc(user_id)
    user_profile = svc["profile_db"].get_full_profile()

    scan_result, summary = fridge_scan_pipeline(
        image_bytes  = raw_bytes,
        db           = svc["db"],
        groq_client  = _global_client,   # ← groq_client, NOT gemini_model
        user_profile = user_profile,
    )
    scan_result["inventory_summary"] = summary
    return APIResponse(success=True, message="Image analyzed", data=scan_result)


@app.post("/fridge/scan", response_model=APIResponse, tags=["Vision"])
async def scan_fridge(
    file:    UploadFile = File(...),
    user_id: str        = Form(...),
):
    # ← FIXED: Check Groq, not Gemini
    if not _global_client:
        return APIResponse(
            success=False,
            message="Fridge scanner unavailable",
            error="GROQ_API_KEY is not configured."
        )

    try:
        from vision.fridge_scanner import fridge_scan_pipeline

        image_bytes  = await file.read()
        svc          = _get_svc(user_id)
        user_profile = svc["profile_db"].get_full_profile()

        scan_result, summary = fridge_scan_pipeline(
            image_bytes  = image_bytes,
            db           = svc["db"],
            groq_client  = _global_client,   # ← FIXED: groq_client, not gemini_model
            user_profile = user_profile,
        )

        return APIResponse(
            success=True,
            message="Fridge scanned successfully",
            data={
                "total_detected":    len(scan_result.get("detected_items", [])),
                "allowed_items":     scan_result.get("allowed_items", []),
                "blocked_items":     scan_result.get("blocked_items", []),
                "scene_description": scan_result.get("scene_description", ""),
                "suggested_recipes": scan_result.get("suggested_recipes", []),
                "nutrition_tips":    scan_result.get("nutrition_tips", []),
                "confidence":        scan_result.get("confidence", 0.0),
                "summary":           summary,
            },
        )

    except Exception as e:
        return APIResponse(success=False, message="Fridge scan failed", error=str(e))

# ── Voice (Groq Whisper) ──────────────────────────────────────────────────────

@app.post("/voice/transcribe", response_model=APIResponse, tags=["Voice"])
async def transcribe(file: UploadFile = File(...)):
    from voice.voice_agent import transcribe_audio_groq
    audio = await file.read()
    text  = transcribe_audio_groq(audio, _global_client, file.filename)  # ← Groq
    return APIResponse(success=True, message="Transcribed", data={"text": text})


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/users", tags=["Admin"])
async def list_users():
    from database.user_db_manager import list_all_users
    return {"users": list_all_users()}


@app.delete("/admin/users/{user_id}", tags=["Admin"])
async def purge_user(user_id: str):
    """Delete all data for a user (GDPR / admin use only)."""
    from services.user_services import evict_user_cache
    from database.user_db_manager import get_user_data_dir
    import shutil

    evict_user_cache(user_id)
    user_dir = get_user_data_dir(user_id)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
        return {"deleted": True, "user_id": user_id}
    return {"deleted": False, "reason": "User directory not found"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
