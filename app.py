"""app.py — NutriBot v5.0 — Complete Multi-User Implementation with Fridge Scanner."""

import os
import sys
import uuid
import re
from datetime import datetime, timedelta, date

import streamlit as st
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

load_dotenv()

st.set_page_config(
    page_title="NutriBot · Smart Meal Assistant",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=DM+Sans:ital,wght@0,400;0,500;1,400&display=swap');

* { font-family: 'DM Sans', sans-serif; }
h1,h2,h3,.chef-wordmark { font-family: 'Sora', sans-serif !important; }

.chat-scroll { max-height: 65vh; overflow-y: auto; padding: 0 0.5rem; }

.user-bubble { display:flex; justify-content:flex-end; margin:0.6rem 0; }
.user-inner {
    background: linear-gradient(135deg, #e8541e 0%, #f97316 100%);
    color: white; padding: 0.7rem 1.1rem; border-radius: 20px 20px 4px 20px;
    max-width: 72%; font-size:0.93rem; line-height:1.55; font-weight:500;
    box-shadow: 0 4px 15px rgba(232,84,30,0.25);
}

.ai-bubble { display:flex; gap:10px; margin:0.6rem 0; align-items:flex-start; }
.ai-avatar {
    width:38px; height:38px; min-width:38px;
    background: linear-gradient(135deg, #fff7ed, #fef3c7);
    border: 1.5px solid #fed7aa; border-radius:50%;
    display:flex; align-items:center; justify-content:center; font-size:1.1rem;
    box-shadow: 0 2px 8px rgba(232,84,30,0.15);
}
.ai-inner {
    background: #fafaf8; border: 1px solid #e8e5e0;
    border-radius: 4px 20px 20px 20px; padding: 0.8rem 1.1rem;
    max-width: 88%; font-size:0.93rem; line-height:1.6;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}

.intent-tag {
    display:inline-block; font-size:0.6rem; padding:2px 9px;
    border-radius:20px; margin-bottom:6px; font-weight:700;
    text-transform:uppercase; letter-spacing:0.06em; font-family:'Sora',sans-serif;
}
.tag-generate-recipe,.tag-generate_recipe{background:#fef3c7;color:#b45309}
.tag-smart-recommendation,.tag-smart_recommendation{background:#ede9fe;color:#6d28d9}
.tag-add-inventory,.tag-add_inventory{background:#d1fae5;color:#065f46}
.tag-view-inventory,.tag-view_inventory{background:#dbeafe;color:#1e40af}
.tag-health-advice,.tag-health_advice{background:#fce7f3;color:#9d174d}
.tag-memory-recall,.tag-memory_recall{background:#e0f2fe;color:#075985}
.tag-meal-plan,.tag-meal_plan{background:#f0fdf4;color:#166534}
.tag-shopping-list,.tag-shopping_list{background:#fdf4ff;color:#7e22ce}
.tag-daily-nutrition,.tag-daily_nutrition{background:#fff7ed;color:#c2410c}
.tag-save-meal,.tag-save_meal{background:#f0fdf4;color:#15803d}
.tag-rate-recipe,.tag-rate_recipe{background:#fef9c3;color:#a16207}
.tag-eco-tips,.tag-eco_tips{background:#dcfce7;color:#15803d}
.tag-budget-analysis,.tag-budget_analysis{background:#fff7ed;color:#c2410c}
.tag-cooking-tips,.tag-cooking_tips{background:#faf5ff;color:#7e22ce}
.tag-greeting{background:#fef9c3;color:#92400e}
.tag-general{background:#f1f5f9;color:#475569}
.tag-fridge-scan,.tag-fridge_scan{background:#e0f2fe;color:#075985}

.agent-panel {
    background: #fafaf8; border: 1px solid #e8e5e0; border-radius:14px;
    padding: 0.85rem; font-size:0.72rem; position:sticky; top:1rem;
}
.agent-panel-title {
    font-weight:800; color:#1a1a18; margin-bottom:0.6rem;
    font-size:0.65rem; text-transform:uppercase; letter-spacing:0.08em;
    font-family:'Sora',sans-serif;
}
.agent-row { display:flex; align-items:center; gap:7px; padding:3px 0; }
.agent-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.dot-idle{background:#e2e8f0} .dot-running{background:#f97316;animation:pulse .7s infinite}
.dot-done{background:#10b981} .dot-error{background:#ef4444}
.agent-name-idle{color:#94a3b8} .agent-name-running{color:#f97316;font-weight:700}
.agent-name-done{color:#10b981;font-weight:600} .agent-name-error{color:#ef4444}
.agent-time{margin-left:auto;color:#cbd5e1;font-size:0.62rem}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.35}}

.stream-cursor::after{content:'▋';animation:blink 1s infinite;color:#e8541e;font-size:0.8rem}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

.card {
    background:white; border:1px solid #e8e5e0; border-radius:14px;
    padding:1rem 1.1rem; margin:0.5rem 0;
    box-shadow:0 2px 10px rgba(0,0,0,0.04);
}
.card-title {
    font-size:0.65rem; font-weight:800; color:#64748b; text-transform:uppercase;
    letter-spacing:0.08em; margin-bottom:0.7rem; font-family:'Sora',sans-serif;
}
.metric-grid { display:grid; gap:0.4rem; }
.metric-cell {
    text-align:center; background:#fafaf8; border-radius:10px;
    padding:0.5rem 0.3rem; border:1px solid #f0ede8;
}
.metric-val{font-size:1.15rem;font-weight:800;font-family:'Sora',sans-serif}
.metric-lbl{font-size:0.58rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em}

.welcome-card {
    background: linear-gradient(135deg, #fff7ed 0%, #fef3c7 50%, #fef9c3 100%);
    border: 1.5px solid #fed7aa; border-radius:20px; padding:1.8rem;
    margin:0.8rem 0; box-shadow:0 4px 20px rgba(232,84,30,0.1);
}
.welcome-title{font-size:1.5rem;font-weight:800;color:#c2410c;margin-bottom:0.4rem;font-family:'Sora',sans-serif}

.chef-wordmark{font-size:1.7rem;font-weight:800;color:#e8541e;line-height:1.1}
.chef-tagline{font-size:0.72rem;color:#94a3b8;font-weight:500;letter-spacing:0.03em}

.stButton button {
    border-radius:12px !important; font-weight:600 !important;
    font-family:'DM Sans',sans-serif !important;
}

/* Login page styles */
.login-card {
    max-width: 420px; margin: 3rem auto; padding: 2.5rem;
    background: white; border-radius: 24px;
    border: 1px solid #e8e5e0;
    box-shadow: 0 8px 40px rgba(232,84,30,0.12);
}
.login-logo { text-align:center; font-size:4rem; margin-bottom:0.5rem; }
.login-title { text-align:center; font-size:1.8rem; font-weight:800; color:#1a1a18; font-family:'Sora',sans-serif; }
.login-sub { text-align:center; color:#94a3b8; font-size:0.9rem; margin-bottom:1.5rem; }
.user-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:#fef3c7; border:1px solid #fed7aa; border-radius:20px;
    padding:4px 12px; font-size:0.72rem; color:#92400e; font-weight:600;
}

[data-testid="metric-container"] { background:#fafaf8; border-radius:10px; padding:0.5rem; }

/* Fridge Scanner specific styles */
.fridge-scan-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 20px;
    padding: 24px 28px;
    margin-bottom: 20px;
    border: 1px solid rgba(249, 115, 22, 0.3);
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI MODEL — module-level singleton (initialised once per session)
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _get_gemini_model():
    """
    Initialise and cache the Gemini Vision model for the lifetime of the
    Streamlit process.  Returns None if GEMINI_API_KEY is not set or if the
    google-generativeai package is unavailable.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        return model
    except Exception as e:
        print(f"[NutriBot] Gemini init failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-USER AUTHENTICATION LAYER
# ═══════════════════════════════════════════════════════════════════════════

def sanitize_user_id(raw: str) -> str:
    """Strip unsafe characters from a user ID."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", raw.strip().lower())[:32]


def login_gate():
    """
    Show a login form and block until the user identifies themselves.
    Supports three modes (pick one by setting LOGIN_MODE in .env):
      - 'url'    : ?user=alice  (great for demos / shared deployments)
      - 'form'   : simple username input, no password needed
      - 'auto'   : random UUID per session (fully anonymous, still isolated)
    """
    if "user_id" in st.session_state and st.session_state["user_id"]:
        return  # already logged in

    login_mode = os.getenv("LOGIN_MODE", "form").lower()

    # ── URL param mode ────────────────────────────────────────────────────
    if login_mode == "url":
        params = st.query_params
        raw = params.get("user", "").strip()
        if raw:
            st.session_state["user_id"] = sanitize_user_id(raw)
            st.session_state["display_name"] = raw
            return
        login_mode = "form"

    # ── Auto-anonymous mode ───────────────────────────────────────────────
    if login_mode == "auto":
        anon_id = f"anon_{str(uuid.uuid4())[:8]}"
        st.session_state["user_id"] = anon_id
        st.session_state["display_name"] = anon_id
        return

    # ── Form mode (default) ───────────────────────────────────────────────
    st.markdown("""
    <div class="login-card">
        <div class="login-logo">🥗</div>
        <div class="login-title">NutriBot</div>
        <div class="login-sub">Your personal AI meal assistant</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Welcome! Who are you?")
        name = st.text_input(
            "Your name",
            placeholder="e.g. Priya, Arjun, guest123...",
            key="login_name_input"
        )
        st.caption("Your pantry, recipes, and nutrition data will be saved just for you.")

        if st.button("🚀 Start Cooking", type="primary", use_container_width=True):
            if name.strip():
                uid = sanitize_user_id(name)
                st.session_state["user_id"] = uid
                st.session_state["display_name"] = name.strip()
                st.rerun()
            else:
                st.error("Please enter your name to continue.")

        st.markdown("---")
        if st.button("👤 Continue as Guest", use_container_width=True):
            anon_id = f"guest_{str(uuid.uuid4())[:6]}"
            st.session_state["user_id"] = anon_id
            st.session_state["display_name"] = "Guest"
            st.rerun()

    st.stop()


# ═══════════════════════════════════════════════════════════════════════════
# PER-USER SERVICE FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def get_user_services(user_id: str) -> dict:
    """
    Return a dict of services scoped to *this* user.
    Results are cached in st.session_state so they survive reruns
    but are NOT shared across browser sessions / users.
    """
    cache_key = f"__services_{user_id}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    from groq import Groq
    from tools.tools import load_recipe_dataset, build_recipe_knowledge_base
    from services.user_services import get_user_services as _build
    from agents.pantry_agent import PantryAgent
    from agents.cooking_agent import CookingAgent
    from agents.memory_agent import MemoryAgent

    groq_key = os.getenv("GROQ_API_KEY", "")
    client = Groq(api_key=groq_key) if groq_key else None

    svc = _build(user_id)
    svc["client"]  = client
    svc["user_id"] = user_id

    dataset = load_recipe_dataset()
    svc["recipe_kb"] = build_recipe_knowledge_base(dataset)

    svc["pantry_agent"]  = PantryAgent()
    svc["cooking_agent"] = CookingAgent()
    svc["memory_agent"]  = MemoryAgent()

    st.session_state[cache_key] = svc
    return svc


# ═══════════════════════════════════════════════════════════════════════════
# FRIDGE SCANNER UI COMPONENT
# ═══════════════════════════════════════════════════════════════════════════

def render_fridge_scanner_tab(db, gemini_model, user_profile=None):
    """
    Full Streamlit UI for the Fridge Scanner feature.

    Args:
        db:           GroceryDatabase instance
        gemini_model: Gemini model instance (from _get_gemini_model())
        user_profile: User's profile dict
    """
    from vision.fridge_scanner import fridge_scan_pipeline

    # ── Header card ───────────────────────────────────────────────────────
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 20px;
        padding: 24px 28px;
        margin-bottom: 20px;
        border: 1px solid rgba(249, 115, 22, 0.3);
    ">
        <div style="display: flex; align-items: center; gap: 14px;">
            <span style="font-size: 42px;">🧊</span>
            <div>
                <div style="
                    font-family: 'Sora', sans-serif;
                    font-size: 1.4rem;
                    font-weight: 800;
                    color: #f97316;
                    margin-bottom: 4px;
                ">Smart Fridge Scanner</div>
                <div style="color: #94a3b8; font-size: 0.85rem; line-height: 1.5;">
                    📸 Snap your fridge → AI detects all items → Filtered by your diet &amp; health profile → Added to pantry instantly
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Gemini availability check ─────────────────────────────────────────
    if gemini_model is None:
        st.error(
            "🔴 **Fridge Scanner is disabled** — `GROQ_API_KEY` is not set or invalid.\n\n"
            "Add `GROQ_API_KEY=your_key_here` to your `.env` file and restart the app.\n\n"
            "Get a free key at [Google AI Studio](https://aistudio.google.com/app/apikey)."
        )
        return

    # ── Profile summary banner ────────────────────────────────────────────
    if user_profile:
        _render_profile_banner(user_profile)

    # ── Upload section ────────────────────────────────────────────────────
    col_upload, col_tips = st.columns([3, 2])

    with col_upload:
        st.markdown("#### 📤 Upload Fridge Photo")
        uploaded_file = st.file_uploader(
            "Drag & drop or browse",
            type=["jpg", "jpeg", "png", "webp"],
            key="fridge_scan_upload",
            label_visibility="collapsed",
            help="Take a photo of your open fridge for best results",
        )

    with col_tips:
        st.markdown("#### 💡 Tips for Best Results")
        st.markdown("""
        <div style="background: #fafaf8; border-radius: 12px; padding: 14px; border: 1px solid #e8e5e0; font-size: 0.82rem; line-height: 1.7;">
        📷 Open fridge door <b>fully</b><br>
        💡 Good <b>lighting</b> is key<br>
        📐 Shoot from <b>front</b>, not angle<br>
        🧹 Remove any <b>obstructions</b><br>
        🎯 Include <b>all shelves</b> if possible
        </div>
        """, unsafe_allow_html=True)

    if not uploaded_file:
        _render_empty_state()
        return

    # ── Preview + scan ────────────────────────────────────────────────────
    st.markdown("---")
    col_img, col_action = st.columns([2, 1])

    with col_img:
        st.image(uploaded_file, caption="📸 Your fridge", use_container_width=True)

    with col_action:
        st.markdown("#### Ready to scan?")

        if user_profile:
            active_filters = _get_active_filters(user_profile)
            if active_filters:
                st.markdown("**Active filters:**")
                for f in active_filters:
                    st.markdown(f"  {f}")
            else:
                st.info("No dietary restrictions set. All items will be added.")
        else:
            st.warning("No profile found. All items will be added.")

        st.markdown("")

        scan_clicked = st.button(
            "🔍 Scan Fridge & Add to Pantry",
            use_container_width=True,
            type="primary",
            key="fridge_scan_btn",
        )

    # ── Run scan ──────────────────────────────────────────────────────────
    if scan_clicked:
        raw_bytes = uploaded_file.getvalue()

        progress_bar = st.progress(0)
        status_text  = st.empty()

        status_text.markdown("🤖 *Initialising vision model...*")
        progress_bar.progress(10)

        status_text.markdown("🔍 *Scanning fridge contents...*")
        progress_bar.progress(30)

        # ── KEY FIX: pass gemini_model, not groq_client ───────────────
        scan_result, summary = fridge_scan_pipeline(
            image_bytes  = raw_bytes,
            db           = db,
            groq_client  = gemini_model,
            user_profile = user_profile,
        )

        progress_bar.progress(70)
        status_text.markdown("🧪 *Applying dietary filters...*")

        progress_bar.progress(90)
        status_text.markdown("📦 *Adding to pantry...*")

        progress_bar.progress(100)
        status_text.empty()
        progress_bar.empty()

        st.markdown("---")
        _render_scan_results(scan_result, summary, user_profile)

        st.session_state["last_fridge_scan"] = scan_result


def _render_profile_banner(profile):
    """Show active dietary/health filters in a compact banner."""
    diet = profile.get("diet_type", "")
    conditions = profile.get("health_conditions", [])
    if isinstance(conditions, str):
        conditions = [conditions]
    allergies = profile.get("allergies", [])
    if isinstance(allergies, str):
        allergies = [a.strip() for a in allergies.split(",") if a.strip()]

    if not any([diet, conditions, allergies]):
        return

    tags_html = ""
    if diet:
        color_map = {
            "vegetarian": "#d1fae5", "vegan": "#bbf7d0",
            "keto": "#dbeafe", "jain": "#fef9c3",
        }
        bg = color_map.get(diet.lower(), "#f0fdf4")
        tags_html += (
            f'<span style="background:{bg};color:#065f46;padding:3px 10px;'
            f'border-radius:20px;font-size:0.72rem;font-weight:700;margin-right:6px;">'
            f'🥗 {diet.upper()}</span>'
        )

    for c in conditions:
        tags_html += (
            f'<span style="background:#fce7f3;color:#9d174d;padding:3px 10px;'
            f'border-radius:20px;font-size:0.72rem;font-weight:700;margin-right:6px;">'
            f'🏥 {c.upper()}</span>'
        )

    for a in allergies[:2]:
        tags_html += (
            f'<span style="background:#fff7ed;color:#c2410c;padding:3px 10px;'
            f'border-radius:20px;font-size:0.72rem;font-weight:700;margin-right:6px;">'
            f'⚠️ ALLERGIC: {a.upper()}</span>'
        )

    st.markdown(f"""
    <div style="background:#fafaf8;border:1px solid #e8e5e0;border-radius:12px;
                padding:10px 14px;margin-bottom:12px;">
        <span style="font-size:0.7rem;font-weight:800;color:#64748b;text-transform:uppercase;
                     letter-spacing:0.08em;margin-right:10px;">ACTIVE FILTERS</span>
        {tags_html}
    </div>
    """, unsafe_allow_html=True)


def _get_active_filters(profile):
    """Get human-readable list of active filters."""
    filters = []
    diet = profile.get("diet_type", "")
    if diet:
        filters.append(f"🥗 **{diet.title()}** diet")

    conditions = profile.get("health_conditions", [])
    if isinstance(conditions, str):
        conditions = [conditions]
    for c in conditions:
        filters.append(f"🏥 **{c.title()}** restriction")

    allergies = profile.get("allergies", [])
    if isinstance(allergies, str):
        allergies = [a.strip() for a in allergies.split(",") if a.strip()]
    for a in allergies:
        filters.append(f"⚠️ **{a.title()}** allergy")

    return filters


def _render_scan_results(scan_result, summary, user_profile):
    """Render the scan results with metrics + details."""
    allowed    = scan_result.get("allowed_items", [])
    blocked    = scan_result.get("blocked_items", [])
    total      = len(scan_result.get("detected_items", []))
    confidence = scan_result.get("confidence", 0)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("🔍 Detected", total)
    with m2:
        st.metric("✅ Added", len(allowed), delta=f"{len(allowed)} items")
    with m3:
        st.metric(
            "🚫 Blocked", len(blocked),
            delta=f"-{len(blocked)} filtered" if blocked else None,
            delta_color="inverse",
        )
    with m4:
        st.metric("🎯 Confidence", f"{int(confidence * 100)}%")

    st.markdown("")
    st.markdown(summary)

    if blocked:
        with st.expander(f"🚫 View {len(blocked)} blocked item(s) detail", expanded=False):
            for b in blocked:
                name   = b.get("name", "").title()
                reason = b.get("blocked_reason", "Restricted")
                rtype  = b.get("restriction_type", "")
                icon   = {"diet": "🥗", "health": "🏥", "allergy": "⚠️"}.get(rtype, "🚫")
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                            background:#fff5f5;border-radius:10px;margin:4px 0;
                            border-left:3px solid #ef4444;">
                    <span style="font-size:1.1rem;">{icon}</span>
                    <div>
                        <strong style="color:#1e293b;">{name}</strong><br>
                        <span style="font-size:0.78rem;color:#64748b;">{reason}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    if allowed:
        st.success(
            f"✅ **{len(allowed)} items added to your pantry!** "
            + (f"({len(blocked)} items filtered by your diet)" if blocked else "")
        )


def _render_empty_state():
    """Show placeholder when no image is uploaded."""
    st.markdown("""
    <div style="
        border: 2px dashed #e2e8f0;
        border-radius: 20px;
        padding: 48px 24px;
        text-align: center;
        margin: 20px 0;
        background: #fafaf8;
    ">
        <div style="font-size: 4rem; margin-bottom: 12px;">🧊📸</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: #1e293b; margin-bottom: 8px;">
            Upload a fridge photo to get started
        </div>
        <div style="font-size: 0.85rem; color: #94a3b8; max-width: 320px; margin: 0 auto;">
            The AI will scan all visible items, check them against your dietary profile,
            and automatically add safe items to your pantry.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION INITIALISATION
# ═══════════════════════════════════════════════════════════════════════════

def init_session():
    """Set all session-state defaults."""
    defaults = {
        "chat_history":     [],
        "turn_count":       0,
        "chip_query":       None,
        "input_mode":       "text",
        "session_id":       str(uuid.uuid4())[:8],
        "cooking_mode":     False,
        "current_recipe":   None,
        "current_step":     0,
        "last_recipe":      None,
        "last_nutrition":   None,
        "last_budget":      None,
        "last_eco":         None,
        "last_fridge_scan": None,
        "prefs": {
            "dietary":  [],
            "health":   [],
            "cuisine":  "Indian",
            "calories": 500,
            "budget":   500,
            "servings": 2,
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════════════════
# CARD RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def _cell(val, label, color, cols=4):
    return (
        f'<div class="metric-cell">'
        f'<div class="metric-val" style="color:{color}">{val}</div>'
        f'<div class="metric-lbl">{label}</div>'
        f'</div>'
    )


def render_nutrition_card(nutrition_data: dict) -> str:
    if not nutrition_data:
        return ""
    ps     = nutrition_data.get("per_serving", {})
    cal    = ps.get("calories",  0)
    prot   = ps.get("protein_g", 0)
    carbs  = ps.get("carbs_g",   0)
    fat    = ps.get("fat_g",     0)
    fiber  = ps.get("fiber_g",   0)
    sodium = ps.get("sodium_mg", 0)
    usda   = nutrition_data.get("usda_matched", 0)
    total_i = max(nutrition_data.get("total_ingredients", 1), 1)
    acc = round(usda / total_i * 100)
    acc_color = "#059669" if acc > 70 else "#d97706" if acc > 40 else "#dc2626"
    badge_bg  = "#d1fae5" if acc > 70 else "#fef3c7" if acc > 40 else "#fee2e2"

    return f"""
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.7rem">
    <span class="card-title">📊 Nutrition Per Serving</span>
    <span style="font-size:0.6rem;padding:2px 9px;border-radius:20px;background:{badge_bg};color:{acc_color};font-weight:700">{acc}% USDA</span>
  </div>
  <div class="metric-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:0.4rem">
    {_cell(f"{cal:.0f}",   "kcal",    "#f97316")}
    {_cell(f"{prot:.0f}g", "protein", "#3b82f6")}
    {_cell(f"{carbs:.0f}g","carbs",   "#10b981")}
    {_cell(f"{fat:.0f}g",  "fat",     "#8b5cf6")}
  </div>
  <div class="metric-grid" style="grid-template-columns:repeat(2,1fr)">
    {_cell(f"{fiber:.0f}g",   "fiber",  "#059669")}
    {_cell(f"{sodium:.0f}mg", "sodium", "#c2410c")}
  </div>
</div>"""


def render_budget_card(budget: dict) -> str:
    if not budget:
        return ""
    cur     = budget.get("currency",      "₹")
    total   = budget.get("total_cost",    0)
    per_srv = budget.get("per_serving",   0)
    within  = budget.get("within_budget", True)
    limit   = budget.get("budget_limit",  500)
    status_color = "#059669" if within else "#dc2626"
    status_text  = "✅ Within Budget" if within else "⚠️ Over Budget"
    bar_pct   = min(100, round(total / max(limit, 1) * 100))
    bar_color = "#10b981" if within else "#ef4444"

    return f"""
<div class="card">
  <span class="card-title">💰 Cost Estimate</span>
  <div class="metric-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:0.6rem">
    {_cell(f"{cur}{total:.0f}", "total", "#f97316")}
    {_cell(f"{cur}{per_srv:.0f}", "per serving", "#3b82f6")}
    <div class="metric-cell">
      <div class="metric-val" style="color:{status_color};font-size:0.75rem">{status_text}</div>
      <div class="metric-lbl">vs {cur}{limit:.0f} budget</div>
    </div>
  </div>
  <div style="background:#f1f5f9;border-radius:6px;height:6px;overflow:hidden">
    <div style="width:{bar_pct}%;height:100%;background:{bar_color};border-radius:6px"></div>
  </div>
  <div style="font-size:0.65rem;color:#94a3b8;margin-top:3px">{bar_pct}% of weekly budget used</div>
</div>"""


def render_eco_card(eco: dict) -> str:
    if not eco:
        return ""
    score     = eco.get("score",        0)
    grade     = eco.get("grade",        "C")
    co2       = eco.get("co2_kg",       0)
    co2_saved = eco.get("co2_saved_kg", 0)
    tip       = eco.get("tip",          "")
    used      = eco.get("expiring_used", 0)
    color     = "#059669" if score >= 75 else "#f97316" if score >= 50 else "#dc2626"
    grade_bg  = {"A+": "#d1fae5", "A": "#d1fae5", "B": "#fef3c7",
                 "C": "#fff7ed",  "D": "#fee2e2"}.get(grade, "#f1f5f9")

    return f"""
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <span class="card-title">🌱 Eco Score</span>
    <div style="text-align:right">
      <span style="font-size:1.5rem;font-weight:800;color:{color};font-family:'Sora',sans-serif">{score:.0f}</span>
      <span style="font-size:0.7rem;color:#94a3b8">/100</span>
      <span style="display:block;font-size:0.65rem;background:{grade_bg};color:{color};padding:1px 7px;border-radius:20px;font-weight:700">Grade {grade}</span>
    </div>
  </div>
  <div class="metric-grid" style="grid-template-columns:1fr 1fr;margin:0.5rem 0">
    {_cell(f"{co2:.2f}kg",       "CO₂ used",  "#64748b")}
    {_cell(f"{co2_saved:.2f}kg", "CO₂ saved", "#059669")}
  </div>
  {f'<div style="font-size:0.75rem;color:#059669;margin-top:0.3rem">🎉 Used {used} expiring item(s)</div>' if used else ''}
  <div style="font-size:0.75rem;color:#64748b;margin-top:0.3rem;font-style:italic">{tip}</div>
</div>"""


def render_pipeline_panel(agent_status: dict):
    AGENTS = [
        "🧠 Memory Agent", "🎯 Intent Agent", "🥕 Pantry Agent",
        "🍳 Recipe Agent", "📊 Nutrition Agent", "💰 Budget Agent",
        "🌱 Eco Agent", "🏥 Health Agent", "📅 Meal Planner",
        "🛒 Shopping Agent", "⭐ Taste Agent",
    ]
    lines = ['<div class="agent-panel">', '<div class="agent-panel-title">⚡ Live Pipeline</div>']
    for agent in AGENTS:
        info   = agent_status.get(agent, {})
        status = info.get("status", "idle")
        t      = info.get("time", 0)
        t_str  = f'<span class="agent-time">{t:.1f}s</span>' if t else ""
        dot = {"idle": "dot-idle", "running": "dot-running",
               "done": "dot-done", "error": "dot-error"}.get(status, "dot-idle")
        nm  = {"idle": "agent-name-idle", "running": "agent-name-running",
               "done": "agent-name-done", "error": "agent-name-error"}.get(status, "agent-name-idle")
        lines.append(
            f'<div class="agent-row">'
            f'<div class="agent-dot {dot}"></div>'
            f'<span class="{nm}">{agent}</span>{t_str}</div>'
        )
    lines.append("</div>")
    st.markdown("".join(lines), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════

def render_sidebar(services: dict):
    user_id      = services["user_id"]
    display_name = st.session_state.get("display_name", user_id)

    with st.sidebar:
        st.markdown(
            f'<div class="user-badge">👤 {display_name}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Session ID: `{user_id}`")

        if st.button("🚪 Switch User", use_container_width=True):
            for key in ["user_id", "display_name", "chat_history", "turn_count",
                        "last_recipe", "last_nutrition", "last_budget", "last_eco",
                        "cooking_mode", "current_recipe", "current_step",
                        "last_fridge_scan", f"__services_{user_id}"]:
                st.session_state.pop(key, None)
            st.rerun()

        st.divider()

        profile = services["profile_db"].get_full_profile()
        if profile:
            with st.expander("🧠 Your Profile", expanded=False):
                diet    = profile.get("diet_type", "—")
                goal    = (profile.get("fitness_goal") or "—").replace("_", " ").title()
                cp      = profile.get("cuisine_preferences", [])
                cuisine = cp[0] if isinstance(cp, list) and cp else "—"
                bp      = profile.get("budget_preference", {})
                cur     = "₹" if isinstance(bp, dict) and bp.get("currency") == "INR" else "₹"
                amt     = bp.get("amount", 500) if isinstance(bp, dict) else 500

                st.markdown(f"""
| Field | Value |
|-------|-------|
| 🥗 Diet | {diet} |
| 🎯 Goal | {goal} |
| 🍽️ Cuisine | {cuisine} |
| 💰 Budget | {cur}{amt}/week |
| 🔥 Calories | {profile.get("calorie_goal", "—")} kcal/meal |
                """)
                if profile.get("health_conditions"):
                    st.caption(f"🏥 Health: {', '.join(profile['health_conditions'])}")
                if profile.get("allergies"):
                    st.caption(f"⚠️ Allergies: {', '.join(profile['allergies'])}")
                if st.button("🗑️ Reset Profile", use_container_width=True):
                    services["profile_db"].clear()
                    from services.user_services import evict_user_cache
                    evict_user_cache(user_id)
                    st.session_state.pop(f"__services_{user_id}", None)
                    st.success("Profile cleared!")
                    st.rerun()
        else:
            st.info("💡 Tell me your diet & goals in chat to build your profile!")

        with st.expander("🥗 Dietary Preferences", expanded=True):
            p = st.session_state["prefs"]
            p["dietary"] = st.multiselect(
                "Diet", ["Vegetarian", "Vegan", "Non-Vegetarian", "Keto", "Paleo"],
                default=p["dietary"], label_visibility="collapsed"
            )
            p["health"] = st.multiselect(
                "Health", ["Diabetes", "Hypertension", "High Cholesterol", "Celiac"],
                default=p["health"], label_visibility="collapsed"
            )

        with st.expander("💰 Budget & Goals", expanded=True):
            p["cuisine"]  = st.selectbox(
                "Cuisine",
                ["Indian", "Italian", "Asian", "Mediterranean", "Mexican", "American"],
            )
            p["calories"] = st.slider("Calories per meal", 300, 800, p["calories"], 50)
            p["budget"]   = st.number_input("Weekly budget (₹)", 200, 3000, p["budget"], 50)
            p["servings"] = st.number_input("Servings", 1, 6, p["servings"])
        st.session_state["prefs"] = p

        st.divider()

        groceries = services["db"].get_all_groceries()
        expiring  = services["db"].get_expiring_soon(days=3)
        c1, c2 = st.columns(2)
        with c1: st.metric("🥬 Pantry",   len(groceries))
        with c2: st.metric("⚠️ Expiring", len(expiring))

        if expiring:
            with st.expander(f"🔔 Expiring ({len(expiring)})", expanded=True):
                for item in expiring[:5]:
                    exp = item.get("expiry_date", "")
                    try:
                        days_left = (datetime.fromisoformat(exp) - datetime.now()).days
                        badge = "🔴" if days_left <= 1 else "🟡"
                    except Exception:
                        badge = "🟡"
                        days_left = "?"
                    st.markdown(f"{badge} **{item['item_name'].title()}** — {days_left}d left")

        if st.session_state.get("last_recipe"):
            st.divider()
            st.markdown("**🍳 Last Recipe**")
            last = st.session_state["last_recipe"]
            name_match = re.search(r"##\s*🍽️\s*(.+)", last)
            recipe_name = name_match.group(1).strip() if name_match else "Last Recipe"
            st.caption(recipe_name)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🍳 Cook", use_container_width=True, key="sb_cook"):
                    st.session_state["cooking_mode"]   = True
                    st.session_state["current_recipe"] = last
                    st.session_state["current_step"]   = 0
                    st.rerun()
            with c2:
                if st.button("💾 Save", use_container_width=True, key="sb_save"):
                    st.session_state["chip_query"] = "save this as dinner"

        st.divider()

        try:
            stats = services["feedback_db"].get_preference_summary()
            if stats["total_rated"] > 0:
                st.metric("⭐ Avg Rating", f"{stats['avg_rating']}/5",
                          f"{stats['total_rated']} recipes rated")
        except Exception:
            pass

        st.divider()
        
        groq_ok   = bool(os.getenv("GROQ_API_KEY"))
        st.markdown(
        f"**API Status**  \n"
        f"{'✅' if groq_ok else '❌'} Groq (LLM + Voice + Fridge Scanner)"
        )

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.update({"chat_history": [], "turn_count": 0})
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# VOICE / IMAGE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def render_voice_section(client):
    from voice.voice_agent import render_voice_input_ui
    st.markdown("---")
    st.markdown("### 🎙️ Voice Assistant")
    return render_voice_input_ui(client)


def render_image_section(db, client):
    from vision.vision_agent import render_image_input_ui
    st.markdown("### 📸 Smart Scan")
    return render_image_input_ui(db, client)


def render_bill_processor(db, client):
    from vision.vision_agent import process_bill_image, preprocess_image
    st.markdown("### 🧾 Bill/Receipt Scanner")
    st.markdown("*Upload a grocery bill photo — I'll add all items to your pantry!*")
    bill_file = st.file_uploader(
        "Upload bill/receipt photo", type=["jpg", "jpeg", "png"], key="bill_upload"
    )
    if bill_file:
        st.image(bill_file, caption="Your receipt", width=200)
        if st.button("📝 Process Bill", type="primary"):
            raw_bytes = bill_file.read()
            img_bytes, _ = preprocess_image(raw_bytes)
            with st.spinner("📄 Reading bill..."):
                _, summary = process_bill_image(img_bytes, db, client)
            st.markdown(summary)
            return summary
    return None


# ═══════════════════════════════════════════════════════════════════════════
# CHAT HISTORY RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def render_history():
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            icon = {"voice": "🎙️ ", "image": "📸 "}.get(msg.get("mode", "text"), "")
            st.markdown(
                f'<div class="user-bubble"><div class="user-inner">{icon}{msg["content"]}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            intent  = msg.get("intent", "general")
            tag_cls = f"tag-{intent.replace('_', '-')}"
            st.markdown(
                f'<div class="ai-bubble"><div class="ai-avatar">🥗</div><div class="ai-inner">'
                f'<div class="intent-tag {tag_cls}">{intent.replace("_", " ").title()}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(msg["content"])
            if msg.get("nutrition_data"):
                st.markdown(render_nutrition_card(msg["nutrition_data"]), unsafe_allow_html=True)
            if msg.get("budget_data"):
                st.markdown(render_budget_card(msg["budget_data"]), unsafe_allow_html=True)
            if msg.get("eco_data"):
                st.markdown(render_eco_card(msg["eco_data"]), unsafe_allow_html=True)
            if msg.get("show_rating") and not msg.get("rated"):
                cols = st.columns(5)
                for i, col in enumerate(cols, 1):
                    with col:
                        if st.button("⭐" * i, key=f"rate_{msg.get('msg_id', '')}_star{i}"):
                            msg["rated"] = True
                            st.session_state["chip_query"] = f"rate {i} stars"
                            st.rerun()
            st.markdown("</div></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(prompt: str, services: dict) -> dict:
    """
    Fixed pipeline runner that properly threads conversation history
    and recipe context into every agent call.
    """
    from agents.streaming_pipeline import run_streaming_pipeline
    from agents.workflow import build_initial_state
    import streamlit as st
    import re

    user_id = services["user_id"]
    p = st.session_state["prefs"]

    # ── Build conversation history in the correct format ──────────────────
    # Convert chat_history (UI format) → conversation_history (agent format)
    conversation_history = []
    for msg in st.session_state.get("chat_history", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            conversation_history.append({
                "role": role,
                "content": content,
            })

    state = build_initial_state(
        user_query           = prompt,
        user_id              = user_id,
        dietary_restrictions = [d.lower() for d in p["dietary"]],
        health_conditions    = [h.lower() for h in p["health"]],
        calorie_limit        = p["calories"],
        budget_limit         = float(p["budget"]),
        servings             = p["servings"],
        cuisine_preference   = p["cuisine"],
        extra_ingredients    = [],
        conversation_history = conversation_history,  # ← FULL HISTORY
    )
    state["session_id"] = st.session_state["session_id"]

    # ── Also restore last recipe directly from session state ──────────────
    # This ensures modify_recipe works even if history search fails
    if st.session_state.get("last_recipe"):
        state["generated_recipe"] = st.session_state["last_recipe"]

    # ── Restore last nutrition for save operations ────────────────────────
    if st.session_state.get("last_nutrition"):
        state["nutrition_data"] = st.session_state["last_nutrition"]
        nutrition = st.session_state["last_nutrition"]
        per_serving = nutrition.get("per_serving", {})
        if per_serving:
            state["total_nutrition"] = per_serving

    left_col, right_col = st.columns([1, 2.5])

    agent_status = {}
    pipeline_ph  = left_col.empty()
    with pipeline_ph.container():
        render_pipeline_panel(agent_status)

    right_col.markdown(
        '<div class="ai-bubble"><div class="ai-avatar">🥗</div><div class="ai-inner">',
        unsafe_allow_html=True,
    )

    intent_ph   = right_col.empty()
    response_ph = right_col.empty()

    accumulated = ""
    final_state = state

    for event in run_streaming_pipeline(
        state,
        services["client"],
        services["db"],
        services["recipe_kb"],
        profile_db  = services["profile_db"],
        feedback_db = services["feedback_db"],
    ):
        etype = event.get("type")

        if etype == "phase":
            agent = event["agent"]
            agent_status[agent] = {"status": event["status"], "time": event.get("time", 0)}
            with pipeline_ph.container():
                render_pipeline_panel(agent_status)
            if agent == "🎯 Intent Agent" and event.get("intent"):
                intent = event["intent"]
                tc = f"tag-{intent.replace('_', '-')}"
                intent_ph.markdown(
                    f'<div class="intent-tag {tc}">{intent.replace("_", " ").title()}</div>',
                    unsafe_allow_html=True,
                )

        elif etype == "token":
            accumulated += event["text"]
            response_ph.markdown(
                accumulated + '<span class="stream-cursor"></span>',
                unsafe_allow_html=True,
            )

        elif etype == "section":
            title   = event["title"]
            content = event["content"]
            if "Budget" in title and isinstance(content, dict):
                right_col.markdown(render_budget_card(content), unsafe_allow_html=True)
            elif "Nutrition" in title and isinstance(content, dict):
                right_col.markdown(render_nutrition_card(content), unsafe_allow_html=True)
            elif "Eco" in title and isinstance(content, dict):
                right_col.markdown(render_eco_card(content), unsafe_allow_html=True)
            elif "Health" in title and content and "✅" not in str(content):
                right_col.warning(str(content)[:300])

        elif etype == "complete":
            final_state = event["state"]
            if accumulated:
                response_ph.markdown(accumulated, unsafe_allow_html=True)

    right_col.markdown("</div></div>", unsafe_allow_html=True)
    return final_state


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # 1. Authentication
    login_gate()

    # 2. Session defaults
    init_session()

    user_id  = st.session_state["user_id"]
    services = get_user_services(user_id)

    if not os.getenv("GROQ_API_KEY"):
        st.error("⚠️ Set `GROQ_API_KEY` in your `.env` file. Free at console.groq.com")
        st.stop()

    # 3. Sidebar
    render_sidebar(services)

    # ── Tabs ───────────────────────────────────────────────────────────────
    tab_chat, tab_fridge, tab_pantry = st.tabs(
        ["💬 Chat Assistant", "🧊 Smart Fridge Scanner", "📦 My Pantry"]
    )

    # ══════════════════════════════════════════════════════════════════════
    with tab_chat:
        c1, c2, c3, c4 = st.columns([2.5, 1, 1, 1])
        with c1:
            display_name = st.session_state.get("display_name", user_id)
            st.markdown(
                f'<div class="chef-wordmark">🥗 NutriBot</div>'
                f'<div class="chef-tagline">Smart Meal Assistant · {display_name} · Track · Cook · Save</div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.metric("💬 Turns", st.session_state["turn_count"])
        with c3:
            st.metric("📦 Pantry", len(services["db"].get_all_groceries()))
        with c4:
            exp   = services["db"].get_expiring_soon(3)
            color = "#ef4444" if exp else "#10b981"
            st.markdown(
                f'<div style="text-align:center;padding:0.4rem">'
                f'<div style="font-size:1.6rem;font-weight:800;color:{color};font-family:Sora,sans-serif">{len(exp)}</div>'
                f'<div style="font-size:0.68rem;color:#94a3b8">Expiring</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<hr style="border:none;border-top:1px solid #e8e5e0;margin:0.5rem 0">',
            unsafe_allow_html=True,
        )

        # ── Cooking mode ──────────────────────────────────────────────────
        if st.session_state.get("cooking_mode") and st.session_state.get("current_recipe"):
            try:
                from agents.cooking_agent import CookingAgent
                steps = CookingAgent().parse_recipe_steps(st.session_state["current_recipe"])
                if steps:
                    idx   = st.session_state.get("current_step", 0)
                    total = len(steps)
                    st.markdown("---")
                    st.markdown(f"### 🍳 Cooking Mode — Step {idx + 1} of {total}")
                    st.progress(idx / max(total, 1))
                    current = steps[idx]
                    st.markdown(
                        f'<div class="card" style="font-size:1.1rem;line-height:1.7">'
                        f'<div style="font-size:0.65rem;color:#e8541e;font-weight:800;text-transform:uppercase;margin-bottom:0.4rem">Step {idx+1}</div>'
                        f'{current["instruction"]}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if current.get("timer_seconds"):
                        mins = current["timer_seconds"] // 60
                        secs = current["timer_seconds"] % 60
                        timer_html = f"""
                        <div style="text-align:center;padding:1rem;background:#fff7ed;border-radius:12px;margin:0.5rem 0">
                            <div style="font-size:2.5rem;font-family:monospace;font-weight:800;color:#e8541e" id="timer-{idx}">{mins}:{secs:02d}</div>
                            <button onclick="startTimer_{idx}()" style="background:#e8541e;color:white;border:none;padding:8px 24px;border-radius:8px;cursor:pointer;font-weight:600;margin-top:0.5rem">▶ Start Timer</button>
                        </div>
                        <script>
                        function startTimer_{idx}(){{
                            let rem={current["timer_seconds"]};
                            const d=document.getElementById('timer-{idx}');
                            const t=setInterval(()=>{{rem--;const m=Math.floor(rem/60),s=rem%60;d.textContent=`${{m}}:${{String(s).padStart(2,'0')}}`;if(rem<=0){{clearInterval(t);d.textContent='Done! ✅';d.style.color='#059669';}}}},1000);
                        }}
                        </script>"""
                        st.components.v1.html(timer_html, height=130)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if idx > 0 and st.button("⏮ Previous", use_container_width=True):
                            st.session_state["current_step"] -= 1
                            st.rerun()
                    with col2:
                        if st.button("✕ Exit", use_container_width=True):
                            st.session_state["cooking_mode"] = False
                            st.rerun()
                    with col3:
                        if idx < total - 1:
                            if st.button("Next ⏭", use_container_width=True, type="primary"):
                                st.session_state["current_step"] += 1
                                st.rerun()
                        else:
                            if st.button("🎉 Complete!", use_container_width=True, type="primary"):
                                st.balloons()
                                st.session_state["cooking_mode"] = False
                                st.session_state["chip_query"]   = "rate the recipe I just cooked"
                                st.rerun()
                    st.markdown("---")
            except Exception as e:
                st.error(f"Cooking mode error: {e}")
                st.session_state["cooking_mode"] = False

        # ── Welcome screen ────────────────────────────────────────────────
        if not st.session_state["chat_history"]:
            display_name = st.session_state.get("display_name", user_id)
            st.markdown(f"""
            <div class="welcome-card">
                <div class="welcome-title">Welcome, {display_name}! 🥗</div>
                <p style="color:#78350f;margin:0.4rem 0">Your personal AI nutrition assistant that <strong>remembers you</strong>, tracks your pantry, plans meals, and guides you step-by-step while cooking.</p>
                <p style="color:#92400e;font-weight:600;margin-top:0.8rem">Try saying something like:</p>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-top:0.5rem">
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">📦 "I bought 500g paneer, 1kg spinach"</div>
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">🍳 "Make me palak paneer"</div>
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">💬 "Hi, I'm vegetarian, trying to lose weight"</div>
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">📅 "Plan my meals for 3 days"</div>
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">📊 "Show my daily nutrition"</div>
                    <div style="background:rgba(255,255,255,0.7);border-radius:10px;padding:0.5rem 0.7rem;font-size:0.85rem">💰 "What's the cheapest protein?"</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            CHIPS = [
                ("📦", "I bought groceries"),
                ("🍳", "What should I cook?"),
                ("📅", "Plan my week"),
                ("📊", "Today's nutrition"),
                ("🛒", "Build shopping list"),
                ("🌱", "Eco tips"),
            ]
            cols = st.columns(len(CHIPS))
            for i, (icon, text) in enumerate(CHIPS):
                with cols[i]:
                    if st.button(f"{icon} {text}", key=f"chip_{i}", use_container_width=True):
                        st.session_state["chip_query"] = text

        # ── Chat history ──────────────────────────────────────────────────
        render_history()

        # ── Input area ────────────────────────────────────────────────────
        st.markdown(
            '<hr style="border:none;border-top:1px solid #e8e5e0;margin:0.8rem 0">',
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if st.button("⌨️ Text", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "text" else "secondary"):
                st.session_state["input_mode"] = "text"; st.rerun()
        with col2:
            if st.button("🎙️ Voice", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "voice" else "secondary"):
                st.session_state["input_mode"] = "voice"; st.rerun()
        with col3:
            if st.button("📸 Photo", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "image" else "secondary"):
                st.session_state["input_mode"] = "image"; st.rerun()
        with col4:
            if st.button("🧾 Bill", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "bill" else "secondary"):
                st.session_state["input_mode"] = "bill"; st.rerun()
        with col5:
            if st.button("🎤 Assistant", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "assistant" else "secondary"):
                st.session_state["input_mode"] = "assistant"; st.rerun()

        # ── Gather prompt ─────────────────────────────────────────────────
        prompt = st.session_state.pop("chip_query", None)

        if st.session_state["input_mode"] == "text":
            typed  = st.chat_input("Ask about recipes, pantry, nutrition, meal plans...")
            prompt = typed or prompt

        elif st.session_state["input_mode"] == "voice":
            voice_result = render_voice_section(services["client"])
            prompt = voice_result or prompt

        elif st.session_state["input_mode"] == "image":
            image_result = render_image_section(services["db"], services["client"])
            if image_result:
                prompt = image_result

        elif st.session_state["input_mode"] == "bill":
            bill_result = render_bill_processor(services["db"], services["client"])
            if bill_result:
                prompt = bill_result

        elif st.session_state["input_mode"] == "assistant":
            with st.expander("🎙️ Voice Assistant Active", expanded=True):
                from voice.voice_agent import render_voice_input_ui
                voice_text = render_voice_input_ui(services["client"])
                if voice_text:
                    prompt = voice_text
                    st.session_state["input_mode"] = "text"

        # ── Process ───────────────────────────────────────────────────────
        if prompt and prompt.strip():
            mode_icon = {"voice": "🎙️ ", "image": "📸 "}.get(
                st.session_state["input_mode"], ""
            )
            st.markdown(
                f'<div class="user-bubble"><div class="user-inner">{mode_icon}{prompt}</div></div>',
                unsafe_allow_html=True,
            )
            st.session_state["chat_history"].append({
                "role":    "user",
                "content": prompt,
                "mode":    st.session_state["input_mode"],
            })

            final_state = run_pipeline(prompt, services)

            intent  = final_state.get("intent", "general")
            message = (
                final_state.get("assistant_message")
                or final_state.get("generated_recipe")
                or "I processed your request."
            )

            msg_id = str(uuid.uuid4())[:8]
            history_entry = {
                "role": "assistant", "content": message,
                "intent": intent, "msg_id": msg_id,
            }

            if final_state.get("nutrition_data"):
                history_entry["nutrition_data"] = final_state["nutrition_data"]
            if final_state.get("budget_analysis"):
                history_entry["budget_data"] = final_state["budget_analysis"]
            if final_state.get("eco_score"):
                history_entry["eco_data"] = final_state["eco_score"]

            is_recipe = intent in ("generate_recipe", "smart_recommendation")
            if is_recipe:
                history_entry["show_rating"] = True
                st.session_state["last_recipe"]    = final_state.get("generated_recipe", "")
                st.session_state["last_nutrition"] = final_state.get("nutrition_data")
                st.session_state["last_budget"]    = final_state.get("budget_analysis")
                st.session_state["last_eco"]       = final_state.get("eco_score")

            st.session_state["chat_history"].append(history_entry)
            st.session_state["turn_count"] += 1

            if is_recipe and final_state.get("generated_recipe"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("🍳 Start Cooking Mode", use_container_width=True, type="primary"):
                        st.session_state["cooking_mode"]   = True
                        st.session_state["current_recipe"] = final_state["generated_recipe"]
                        st.session_state["current_step"]   = 0
                        st.rerun()
                with c2:
                    if st.button("💾 Save as Dinner", use_container_width=True):
                        st.session_state["chip_query"] = "save this as dinner"
                        st.rerun()
                with c3:
                    if st.button("🛒 Shopping List", use_container_width=True):
                        st.session_state["chip_query"] = "shopping list for this recipe"
                        st.rerun()

            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    with tab_fridge:
        profile      = services["profile_db"].get_full_profile()

        render_fridge_scanner_tab(
            db           = services["db"],
            gemini_model = services["client"],     # ← FIX: was groq_client=services["client"]
            user_profile = profile,
        )

    # ══════════════════════════════════════════════════════════════════════
    with tab_pantry:
        st.markdown("### 📦 Your Pantry Inventory")

        groceries = services["db"].get_all_groceries()

        if not groceries:
            st.info("Your pantry is empty. Add items via chat, bill scan, or fridge scanner!")
        else:
            categorized: dict = {}
            for item in groceries:
                cat = item.get("category", "Other")
                categorized.setdefault(cat, []).append(item)

            for category, items in categorized.items():
                with st.expander(f"🥬 {category} ({len(items)})", expanded=True):
                    for item in items:
                        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                        with col1:
                            st.markdown(f"**{item['item_name'].title()}**")
                        with col2:
                            st.caption(f"Qty: {item.get('quantity', 1)} {item.get('unit', 'pcs')}")
                        with col3:
                            if item.get("expiry_date"):
                                st.caption(f"📅 Exp: {item['expiry_date']}")
                        with col4:
                            if st.button("❌", key=f"del_{item['id']}", help="Remove item"):
                                services["db"].remove_item(item["id"])
                                st.rerun()

            if st.button("🗑️ Clear All Pantry", type="secondary", use_container_width=True):
                services["db"].clear()
                st.rerun()


if __name__ == "__main__":
    main()
