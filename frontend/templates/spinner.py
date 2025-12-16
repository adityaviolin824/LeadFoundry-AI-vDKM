"""
LeadFoundry spinner messages – Molten Metal Theme
Option 1: Normalize composite step names to known stages
"""

_SPINNER_MESSAGES = {
    "intake": (
        "📥 Forging Optimized Search Queries",
        "Extracting parameters, shaping targets and generating high-precision lead-search queries."
    ),
    "research": (
        "🔍 Scanning Lead Sources",
        "Collecting signals, scraping data and gathering potential high-value leads."
    ),
    "finalize": (
        "🧹 Refining and Casting Final Lead List",
        "Deduping, ranking, sorting and exporting your finished Excel output."
    ),
}

def _normalize_step(step: str) -> str:
    """
    Normalize composite or verbose step names to canonical stages.
    This prevents fallback to 'Working… Processing your request.'
    """
    step = step.lower()

    if "intake" in step:
        return "intake"
    if "research" in step:
        return "research"
    if "final" in step or "optimize" in step:
        return "finalize"

    return step


def render_spinning_status(html_placeholder, progress_placeholder, step, progress_fraction):
    """Render step-specific forge-style spinner using HTML/CSS for LeadFoundry."""
    
    normalized_step = _normalize_step(step)

    if normalized_step in _SPINNER_MESSAGES:
        title, subtitle = _SPINNER_MESSAGES[normalized_step]
    else:
        title, subtitle = "⏳ Working…", "Processing your request."
    
    forge_bg       = "rgba(42,46,51,0.90)"
    forge_shadow   = "rgba(0,0,0,0.55)"
    ember_orange   = "#FF8A3D"
    ember_gold     = "#FFB341"
    metal_text     = "#FFE9C7"
    metal_subtext  = "rgba(255,233,199,0.80)"
    
    html = f"""
    <style>
    .spinner-container {{
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        padding:2rem;
        background:{forge_bg};
        border-radius:14px;
        box-shadow:0 12px 30px {forge_shadow};
        margin:1.2rem 0;
        border:1px solid rgba(255,138,61,0.25);
    }}
    .spinner {{
        border:4px solid rgba(255,255,255,0.12);
        border-top:4px solid {ember_orange};
        border-right:4px solid {ember_gold};
        border-radius:50%;
        width:54px;
        height:54px;
        animation:spin 1s linear infinite;
        margin-bottom:1rem;
        box-shadow:0 0 12px {ember_orange};
    }}
    @keyframes spin {{
        0% {{transform:rotate(0deg);}}
        100% {{transform:rotate(360deg);}}
    }}
    .spinner-title {{
        font-size:1.35rem;
        font-weight:700;
        color:{metal_text};
        margin-bottom:0.35rem;
        text-align:center;
        letter-spacing:0.3px;
    }}
    .spinner-subtitle {{
        font-size:0.98rem;
        color:{metal_subtext};
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
