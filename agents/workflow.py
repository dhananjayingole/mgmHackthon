"""agents/workflow.py — Fixed: conversation history threading, context persistence."""

import functools
from langgraph.graph import StateGraph, END
from agents.recipe_agent import RecipeAgent
from agents.state import AgentState
from agents.memory_agent import MemoryAgent
from agents.pantry_agent import PantryAgent
from agents.intent_router import intelligent_router_agent
from agents.budget_agent import budget_agent
from agents.user_profile import UserProfileDB


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "general")
    routes = {
        "generate_recipe":       "recipe_agent",
        "modify_recipe":         "recipe_agent",
        "view_inventory":        "pantry_agent",
        "add_inventory":         "pantry_agent",
        "remove_inventory":      "pantry_agent",
        "remove_all_inventory":  "pantry_agent",
        "general":               "end",
        "greeting":              "end",
        "memory_recall":         "end",
        "health_advice":         "end",
        "meal_plan":             "end",
        "shopping_list":         "end",
        "daily_nutrition":       "end",
        "save_meal":             "end",
        "view_calendar":         "end",
        "rate_recipe":           "end",
        "eco_tips":              "end",
        "budget_analysis":       "end",
        "cooking_tips":          "end",
        "start_cooking_mode":    "end",
        "invalid_input":         "end",
        "context_followup":      "end",
    }
    return routes.get(intent, "end")


def create_workflow(client, db, recipe_kb, profile_db: UserProfileDB = None, feedback_db=None):
    memory_agent = MemoryAgent()
    pantry_agent = PantryAgent()
    recipe_agent = RecipeAgent()

    memory_node = functools.partial(memory_agent.run, profile_db=profile_db, client=client)
    intent_node = functools.partial(intelligent_router_agent, client=client)
    pantry_node = functools.partial(pantry_agent.run, db=db, client=client)
    recipe_node = functools.partial(recipe_agent.run, client=client)
    budget_node = functools.partial(budget_agent)

    graph = StateGraph(AgentState)

    graph.add_node("memory_agent", memory_node)
    graph.add_node("intent_agent", intent_node)
    graph.add_node("pantry_agent", pantry_node)
    graph.add_node("recipe_agent", recipe_node)
    graph.add_node("budget_agent", budget_node)

    graph.set_entry_point("memory_agent")
    graph.add_edge("memory_agent", "intent_agent")
    graph.add_conditional_edges("intent_agent", route_by_intent, {
        "recipe_agent": "recipe_agent",
        "pantry_agent": "pantry_agent",
        "end": END,
    })
    graph.add_edge("recipe_agent", "budget_agent")
    graph.add_edge("budget_agent", END)
    graph.add_edge("pantry_agent", END)

    return graph.compile()


def build_initial_state(
    user_query: str,
    user_id: str = "default",
    dietary_restrictions: list = None,
    health_conditions: list = None,
    calorie_limit: int = 600,
    budget_limit: float = 500.0,
    servings: int = 2,
    cuisine_preference: str = "Indian",
    extra_ingredients: list = None,
    conversation_history: list = None,
) -> AgentState:
    """
    Build the initial AgentState for a pipeline run.
    
    CRITICAL: conversation_history is passed in so agents have full context
    of what was discussed before — enabling recipe modification, follow-ups, etc.
    """
    state = AgentState(
        user_query            = user_query,
        available_ingredients = extra_ingredients or [],
        dietary_restrictions  = dietary_restrictions or [],
        health_conditions     = health_conditions or [],
        calorie_limit         = calorie_limit,
        budget_limit          = budget_limit,
        servings              = servings,
        cuisine_preference    = cuisine_preference,
        conversation_history  = conversation_history or [],  # ← FULL HISTORY passed in
        conversation_summary  = "",
        user_profile          = {},
        intent                = "general",
        intent_confidence     = 0.0,
        needs_clarification   = False,
        clarification_question = "",
        ingredient_analysis   = "",
        health_recommendations = "",
        rag_results           = "",
        generated_recipe      = "",          # Will be restored from history by MemoryAgent
        recipe_ingredients_structured = [],
        budget_analysis       = {},
        waste_score           = {},
        shopping_list         = "",
        nutrition_data        = {},
        total_nutrition       = {},
        final_output          = "",
        assistant_message     = "",
        errors                = [],
        agent_logs            = [],
        processing_time       = {},
        retry_count           = 0,
    )

    state["user_id"] = user_id
    return state