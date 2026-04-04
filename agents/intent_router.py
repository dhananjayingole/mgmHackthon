"""agents/intent_router.py — Fixed: invalid input detection, context-aware routing."""

import re
import json
from agents.base import BaseAgent
from agents.state import AgentState


class IntentRouter(BaseAgent):

    INTENTS = [
        "generate_recipe", "smart_recommendation", "modify_recipe",
        "view_inventory", "add_inventory", "remove_inventory", "remove_all_inventory",
        "health_advice", "greeting", "memory_recall",
        "meal_plan", "cooking_tips", "budget_analysis", "shopping_list",
        "daily_nutrition", "save_meal", "view_calendar",
        "rate_recipe", "eco_tips", "start_cooking_mode", "general",
        "invalid_input", "context_followup",
    ]

    def __init__(self):
        super().__init__("🎯 Intent Agent")

    def run(self, state: AgentState, client=None, **kwargs) -> AgentState:
        query = state.get("user_query", "").strip()
        q = query.lower()

        # ── Check for invalid / gibberish input first ─────────────────────
        if self._is_invalid_input(query):
            state["intent"] = "invalid_input"
            state["intent_confidence"] = 0.99
            self.log(state, "Intent → invalid_input (gibberish detected)", "warning")
            return state

        # ── Check if this is a follow-up / modification of previous context ─
        context_intent = self._check_context_followup(query, q, state)
        if context_intent:
            state["intent"] = context_intent
            state["intent_confidence"] = 0.95
            self.log(state, f"Intent → {context_intent} (context followup)", "success")
            return state

        # ── Rule-based classification ─────────────────────────────────────
        intent = self._classify_rules(q, query, state)
        if intent:
            state["intent"] = intent
            state["intent_confidence"] = 0.95
            self.log(state, f"Intent → {intent} (rule)", "success")
            return state

        # ── LLM classification ────────────────────────────────────────────
        if client:
            intent = self._classify_llm(query, state, client)
        else:
            intent = "general"

        state["intent"] = intent
        state["intent_confidence"] = 0.80
        self.log(state, f"Intent → {intent} (LLM)", "success")
        return state

    # ─────────────────────────────────────────────────────────────────────
    # INVALID INPUT DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _is_invalid_input(self, query: str) -> bool:
        """Detect gibberish, random characters, or meaningless input."""
        q = query.strip()

        if len(q) == 0:
            return True

        # Too short and not a meaningful word
        if len(q) <= 2 and not re.match(r'^(hi|ok|no|yes|yep|nah|bye)$', q.lower()):
            return True

        # Pure numbers (not a rating like "5 stars" or "2")
        if re.match(r'^\d+$', q) and len(q) > 3:
            return True

        # Gibberish: repeated characters like "ghhhhhh", "thsnsnnnn"
        if re.match(r'^(.)\1{3,}$', q.lower()):  # same char repeated 4+ times
            return True

        # Random consonant clusters (no vowels, long string)
        words = q.split()
        gibberish_count = 0
        for word in words:
            cleaned = re.sub(r'[^a-zA-Z]', '', word.lower())
            if len(cleaned) >= 4:
                vowels = sum(1 for c in cleaned if c in 'aeiou')
                # Less than 15% vowels in a word of 4+ chars = likely gibberish
                if vowels == 0 or (vowels / len(cleaned)) < 0.10:
                    gibberish_count += 1

        if gibberish_count > 0 and gibberish_count >= len([w for w in words if len(re.sub(r'[^a-zA-Z]', '', w)) >= 4]):
            return True

        # Keyboard mash patterns
        keyboard_mash = re.compile(
            r'^[qwrtypsdfghjklzxcvbnm]{5,}$|'  # all consonants
            r'^[asdfghjkl;]{4,}$|'             # home row
            r'^[qwertyuiop]{4,}$',              # top row
            re.IGNORECASE
        )
        if keyboard_mash.match(q.replace(' ', '')):
            return True

        return False

    # ─────────────────────────────────────────────────────────────────────
    # CONTEXT-AWARE FOLLOW-UP DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _check_context_followup(self, query: str, q: str, state: AgentState) -> str | None:
        """Detect if this message is modifying/referencing a previous recipe."""
        history = state.get("conversation_history", [])
        last_recipe = state.get("generated_recipe", "")

        # Check if there was a recent recipe in conversation
        has_recent_recipe = bool(last_recipe) or any(
            "## 🍽️" in m.get("content", "") for m in history[-6:]
            if m.get("role") == "assistant"
        )

        if not has_recent_recipe:
            return None

        # Recipe modification patterns
        modify_patterns = [
            r"(make it|change it to|convert to|make.*more|add|without|remove|less|more|instead|swap)",
            r"(korean|chinese|italian|indian|mexican|thai|japanese|fusion)\s*(style|version|way)?",
            r"(spicier|milder|healthier|vegan|vegetarian|keto|low carb|high protein)",
            r"(add (cheese|cream|butter|coconut|paneer)|with (cheese|sauce|gravy))",
            r"(same recipe|that recipe|this recipe|it|modify|adjust|tweak|alter)",
            r"(can you (make|change|adjust)|now (make|add|remove))",
            r"(more (spicy|sweet|sour|tangy|creamy|thick|thin))",
            r"(double|half|triple) (the|servings|recipe|portion)",
        ]

        for pattern in modify_patterns:
            if re.search(pattern, q, re.IGNORECASE):
                return "modify_recipe"

        # Follow-up cooking questions about the last recipe
        followup_cooking = [
            r"(how (long|much|many)|what temperature|when do i|how do i)",
            r"(can i (substitute|replace|use instead)|what if i don't have)",
            r"(step \d|next step|previous step|repeat that)",
        ]

        for pattern in followup_cooking:
            if re.search(pattern, q, re.IGNORECASE):
                return "context_followup"

        return None

    # ─────────────────────────────────────────────────────────────────────
    # RULE-BASED CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────────

    def _classify_rules(self, q: str, raw: str, state: AgentState = None) -> str:

        # ── Greeting ──────────────────────────────────────────────────────
        if re.match(r"^(hi|hello|hey|good\s+(morning|evening|afternoon|night)|namaste|hii+|yo\b|howdy|sup\b|greetings)\b", q):
            return "greeting"

        # ── Start cooking mode ────────────────────────────────────────────
        if re.search(r"(start|begin|open|enter).*(cooking mode|cook mode|step.by.step|guided cook)", q):
            return "start_cooking_mode"
        if re.search(r"cooking mode.*(for|palak|dal|paneer|biryani|recipe)", q):
            return "start_cooking_mode"

        # ── Memory recall ─────────────────────────────────────────────────
        if re.search(
            r"(what did i tell you|my (diet|preference|profile|goal|restriction|allerg)|"
            r"remind me|what do you know about me|what('s| is) my|do you remember|"
            r"what have i told|my saved|my stored)",
            q,
        ):
            return "memory_recall"

        # ── Profile setting ───────────────────────────────────────────────
        if re.search(
            r"^(my (calorie|budget|cuisine|diet|goal|preference|cook time)|"
            r"i prefer|i like|i love|i want|set my|update my|change my)",
            q,
        ):
            return "memory_recall"

        # ── FIX: Diabetes recipe request → generate_recipe ────────────────
        if re.search(
            r"(diabetes|diabetic).*(make me|generate|recipe|dinner|lunch|breakfast|cook|what can i eat)",
            q,
        ):
            return "generate_recipe"

        # ── Low carb / diabetic meal ──────────────────────────────────────
        if re.search(
            r"(low carb|low-carb|keto|diabetic friendly).*(dinner|meal|recipe|lunch|breakfast)",
            q,
        ):
            return "generate_recipe"

        # ── Daily nutrition ───────────────────────────────────────────────
        if re.search(
            r"(daily nutrition|today'?s? (nutrition|calories?|intake|macros?)|"
            r"how (much|many).*(eaten|calories|protein|carbs)|"
            r"nutrition (dashboard|tracker|summary)|"
            r"(calories?|macros?).*(today|so far|eaten)|show.*nutrition|"
            r"progress today|what.*(eaten|consumed) today)",
            q,
        ):
            return "daily_nutrition"

        # ── Save meal ─────────────────────────────────────────────────────
        if re.search(
            r"(save (this|last|that|the).*(recipe|meal|dinner|lunch|breakfast)|"
            r"log (this|that|the).*(meal|recipe|dinner)|"
            r"add.*(calendar|diary|log)|track this meal|save (as|for) (dinner|lunch|breakfast))",
            q,
        ):
            return "save_meal"

        # ── View calendar ─────────────────────────────────────────────────
        if re.search(
            r"(meal calendar|show.*calendar|my (meal|eating|food) history|"
            r"what did i eat|show.*logged meals|meal log)",
            q,
        ):
            return "view_calendar"

        # ── Shopping list ─────────────────────────────────────────────────
        if re.search(
            r"(shopping list|what (do i|should i) (buy|get|purchase)|"
            r"grocery list|what'?s? missing|what (to buy|to get)|"
            r"generate.*shopping|create.*list|items? (to buy|i need))",
            q,
        ):
            return "shopping_list"

        # ── Rate recipe ───────────────────────────────────────────────────
        if re.search(
            r"(rate (this|that|the) recipe|give.*(\d+)\s*star|(\d+)\s*(star|out of 5)|"
            r"i (loved|liked|hated|disliked) (this|that|it)|"
            r"was (delicious|awful|good|bad|amazing|terrible)|"
            r"feedback (for|on) (this|that|the) recipe|"
            r"rate \d|^\d\s*stars?$)",
            q,
        ):
            return "rate_recipe"

        # ── Eco tips ──────────────────────────────────────────────────────
        if re.search(
            r"(eco score|carbon footprint|co2|environmental impact|"
            r"sustainable (eating|food|meals?)|food waste|green (meal|recipe))",
            q,
        ):
            return "eco_tips"

        # ── Remove all ────────────────────────────────────────────────────
        if re.search(r"(clear|empty|delete|remove).*(pantry|inventory|all)", q):
            return "remove_all_inventory"

        # ── Remove specific item ──────────────────────────────────────────
        if re.search(
            r"(remove|delete|used up|finished|ran out of|no more|consumed|used all)\s+"
            r"(the\s+)?(paneer|spinach|tomato|rice|milk|onion|potato|egg|dal|lentil|"
            r"carrot|cauliflower|beans|curd|ghee|butter|oil|sugar|flour|basmati)",
            q,
        ):
            return "remove_inventory"

        # ── Add inventory ─────────────────────────────────────────────────
        if re.search(
            r"(i (bought|got|purchased|picked up)|just (bought|got)|"
            r"add.*(to.*)?(pantry|inventory|fridge))",
            q,
        ) and re.search(
            r"(\d+\s*(kg|g|ml|l|pieces?|cups?|bunch|liters?)|"
            r"paneer|spinach|tomato|rice|milk|onion|potato|egg|dal|lentil|"
            r"flour|sugar|oil|butter|ghee|yogurt|curd|beans|basmati|"
            r"carrot|cauliflower|capsicum)",
            q,
        ):
            return "add_inventory"

        if re.match(r"^i have\s+\d", q):
            return "add_inventory"

        # ── View inventory ────────────────────────────────────────────────
        if re.search(
            r"(show|view|list|check|what('s| is).*(in my|in the).*(pantry|fridge|inventory)|"
            r"what.*pantry|my (pantry|fridge|inventory)|pantry status)",
            q,
        ):
            return "view_inventory"

        if re.search(r"(what('s| is) expiring|expir(ing|ed)|use soon|going bad)", q):
            return "view_inventory"

        # ── Budget analysis ───────────────────────────────────────────────
        if re.search(
            r"(cheapest|most affordable|best value|budget friendly|economical|"
            r"cheapest.*protein|protein.*cheap|best protein.*(budget|cheap|affordable)|"
            r"budget|how much.*cost|cost of|price of|afford|save money)",
            q,
        ):
            return "budget_analysis"

        # ── Health advice (narrower) ──────────────────────────────────────
        if re.search(
            r"(diabetes|diabetic|hypertension|high blood pressure|cholesterol|celiac|"
            r"how many carbs|how much protein|recommended (intake|amount)|"
            r"should i eat|is.*good for (diabetic|health)|diet for (diabetes|weight)|"
            r"health (advice|tips?|recommendation)|nutrition (advice|tips?))",
            q,
        ):
            if not re.search(r"(make me|recipe|generate|cook)", q):
                return "health_advice"

        # ── Smart recommendation ──────────────────────────────────────────
        if re.search(
            r"(suggest|recommend|give me|what'?s? a good).*(breakfast|lunch|dinner|snack|meal|recipe)",
            q,
        ):
            return "smart_recommendation"

        # ── Meal plan ─────────────────────────────────────────────────────
        if re.search(
            r"(plan my (meals?|week|day)|meal plan|weekly plan|"
            r"(\d+[\s-]day|week(ly)?|daily).*plan|plan.*(\d+\s*day|week))",
            q,
        ):
            return "meal_plan"

        # ── Cooking tips ──────────────────────────────────────────────────
        if re.search(
            r"(how do i|how to (cook|make|prepare|fry|boil|bake|grill|roast)|tips? for|technique|"
            r"what temperature|how long.*cook|difference between|substitute for|"
            r"can i replace|what if i don't have)",
            q,
        ):
            return "cooking_tips"

        # ── Generate specific recipe ──────────────────────────────────────
        if re.search(
            r"(make me|recipe for|how to make|i want to (make|cook)|"
            r"generate.*recipe|create.*recipe|give me.*recipe|show me.*recipe)",
            q,
        ):
            return "generate_recipe"

        DISHES = [
            "palak paneer", "dal tadka", "aloo gobi", "chole", "biryani",
            "dosa", "idli", "sambar", "rajma", "kadai", "paneer tikka",
            "pulao", "khichdi", "upma", "poha", "butter chicken",
            "pasta", "pizza", "soup", "sandwich", "stir fry",
            "halwa", "kheer", "raita", "maggie", "noodles", "ramen",
            "curry", "sabzi", "rice", "rotis", "chapati",
        ]
        if any(dish in q for dish in DISHES):
            return "generate_recipe"

        return None

    # ─────────────────────────────────────────────────────────────────────
    # LLM CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────────

    def _classify_llm(self, query: str, state: AgentState, client) -> str:
        profile = state.get("user_profile", {})
        history = state.get("conversation_history", [])
        has_recipe = bool(state.get("generated_recipe")) or any(
            "## 🍽️" in m.get("content", "") for m in history[-4:]
            if m.get("role") == "assistant"
        )

        recent_ctx = ""
        if has_recipe:
            recent_ctx = "\n⚠️ User has a recently generated recipe in context."

        intents_str = ", ".join(self.INTENTS)
        prompt = f"""Classify this cooking assistant message into exactly one intent.

Available intents: {intents_str}

Critical rules:
- Gibberish / random characters / nonsense → invalid_input
- Modifications to a previously discussed recipe → modify_recipe
- "start cooking mode for X" → start_cooking_mode
- "suggest a high protein breakfast" → smart_recommendation
- "cheapest protein source" → budget_analysis
- "I have diabetes, make me a low carb dinner" → generate_recipe
- "how many carbs for diabetic" → health_advice
- "my calorie goal is X" or "I prefer quick" → memory_recall
- "save last recipe as dinner" → save_meal
- "I bought X" → add_inventory
- Single words or short phrases that don't make cooking sense → invalid_input
{recent_ctx}

User message: "{query}"
User profile: diet={profile.get('diet_type','?')}, goal={profile.get('fitness_goal','?')}

Return ONLY the intent name, nothing else."""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=25,
            )
            intent = response.choices[0].message.content.strip().lower().replace("-", "_")
            if intent in self.INTENTS:
                return intent
        except Exception:
            pass
        return "general"


intelligent_router_agent = IntentRouter().run