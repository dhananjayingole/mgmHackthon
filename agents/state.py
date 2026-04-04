"""agents/state.py — AgentState with user_id for multi-user isolation."""

from typing import TypedDict, List, Optional, Dict, Any


class AgentState(TypedDict, total=False):
    # ── Multi-user identity ────────────────────────────────────────────────
    user_id: str                     # CRITICAL: identifies which user this run belongs to

    # ── Core Input ────────────────────────────────────────────────────────
    user_query: str
    available_ingredients: List[str]
    dietary_restrictions: List[str]
    health_conditions: List[str]
    calorie_limit: int
    budget_limit: float
    servings: int
    cuisine_preference: str

    # ── Multimodal ────────────────────────────────────────────────────────
    voice_audio_bytes: Optional[bytes]
    image_bytes: Optional[bytes]
    image_base64: Optional[str]
    image_detected_items: List[str]
    input_mode: str

    # ── User Profile ──────────────────────────────────────────────────────
    user_profile: Dict[str, Any]
    skill_level: str
    cooking_time_available: int

    # ── Memory ────────────────────────────────────────────────────────────
    conversation_history: List[Dict[str, str]]
    conversation_summary: str
    session_id: str

    # ── Intent ────────────────────────────────────────────────────────────
    intent: str
    intent_confidence: float
    needs_clarification: bool
    clarification_question: str

    # ── Agent Outputs ─────────────────────────────────────────────────────
    ingredient_analysis: str
    health_recommendations: str
    rag_results: str
    generated_recipe: str
    recipe_ingredients_structured: List[Dict[str, Any]]
    budget_analysis: Dict[str, Any]
    waste_score: Dict[str, Any]
    shopping_list: str
    nutrition_data: Dict[str, Any]
    total_nutrition: Dict[str, float]
    eco_score: Dict[str, Any]
    time_analysis: Dict[str, Any]
    skill_assessment: Dict[str, Any]
    cuisine_diversity: Dict[str, Any]
    taste_profile: Dict[str, Any]
    meal_plan_data: Dict[str, Any]
    daily_nutrition_summary: Dict[str, Any]

    # ── Cooking Mode ──────────────────────────────────────────────────────
    cooking_steps: List[Dict[str, Any]]
    current_step_index: int
    cooking_mode_active: bool

    # ── Final ─────────────────────────────────────────────────────────────
    final_output: str
    assistant_message: str

    # ── Feedback ──────────────────────────────────────────────────────────
    recipe_rating: Optional[int]
    recipe_feedback: Optional[str]
    recipe_id: Optional[str]

    # ── Metadata ──────────────────────────────────────────────────────────
    errors: List[str]
    agent_logs: List[Dict[str, Any]]
    processing_time: Dict[str, float]
    retry_count: int
    last_error: Optional[str]

    # ── Internal ──────────────────────────────────────────────────────────
    _last_violations: List[str]
    _diet_warning: bool
    last_generated_nutrition: Dict[str, Any]
