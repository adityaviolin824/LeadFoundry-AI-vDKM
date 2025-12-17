"""
LeadFoundry spinner messages – Engineering / Construction Theme
Blue-first, orange-accented, dark UI safe
"""

_SPINNER_MESSAGES = {
    "intake": (
        "📥 Preparing Search Blueprints",
        "Extracting parameters, shaping targets and generating high-precision lead-search queries."
    ),
    "research": (
        "🔍 Surveying Lead Sources",
        "Scanning signals, collecting data and identifying high-value leads."
    ),
    "finalize": (
        "🧹 Finalizing Structured Lead Output",
        "Cleaning, ranking, sorting and exporting your finished Excel output."
    ),
}


def _normalize_step(step: str) -> str:
    step = step.lower()

    if "intake" in step:
        return "intake"
    if "research" in step:
        return "research"
    if "final" in step or "optimize" in step:
        return "finalize"

    return step


def render_spinning_status(html_placeholder, progress_placeholder, step, progress_fraction):
    """Render step-specific engineering-style spinner using HTML/CSS for LeadFoundry."""

    normalized_step = _normalize_step(step)

    if normalized_step in _SPINNER_MESSAGES:
        title, subtitle = _SPINNER_MESSAGES[normalized_step]
    else:
        title, subtitle = "⏳ Working…", "Processing your request."

    # --------------------------------------------------
    # ENGINEERING COLOR PALETTE
    # --------------------------------------------------
    panel_bg        = "rgba(15,20,26,0.92)"     # near-black / charcoal
    panel_shadow    = "rgba(0,0,0,0.6)"
    border_blue     = "rgba(74,132,198,0.35)"

    primary_blue    = "#4A84C6"                # engineering blue
    accent_orange   = "#F0A15A"                # restrained construction orange

    text_primary    = "#E6E8EB"                # cool off-white
    text_secondary  = "rgba(230,232,235,0.75)"

    html = f"""
    <style>
    .spinner-container {{
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        padding:2rem;
        background:{panel_bg};
        border-radius:14px;
        box-shadow:0 12px 30px {panel_shadow};
        margin:1.2rem 0;
        border:1px solid {border_blue};
    }}

    .spinner {{
        border:4px solid rgba(255,255,255,0.08);
        border-top:4px solid {primary_blue};
        border-right:4px solid {accent_orange};
        border-radius:50%;
        width:54px;
        height:54px;
        animation:spin 1s linear infinite;
        margin-bottom:1rem;
        box-shadow:0 0 10px rgba(74,132,198,0.45);
    }}

    @keyframes spin {{
        0% {{transform:rotate(0deg);}}
        100% {{transform:rotate(360deg);}}
    }}

    .spinner-title {{
        font-size:1.35rem;
        font-weight:700;
        color:{text_primary};
        margin-bottom:0.35rem;
        text-align:center;
        letter-spacing:0.3px;
    }}

    .spinner-subtitle {{
        font-size:0.98rem;
        color:{text_secondary};
        text-align:center;
        line-height:1.5;
        max-width:520px;
        letter-spacing:0.2px;
    }}
    </style>

    <div class="spinner-container">
        <div class="spinner"></div>
        <div class="spinner-title">{title}</div>
        <div class="spinner-subtitle">{subtitle}</div>
    </div>
    """

    html_placeholder.markdown(html, unsafe_allow_html=True)

    try:
        progress_placeholder.progress(progress_fraction)
    except:
        pass
