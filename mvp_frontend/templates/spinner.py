"""
LeadFoundry spinner messages – Molten Metal Theme
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
    )
}

def render_spinning_status(html_placeholder, progress_placeholder, step, progress_fraction):
    """Render step-specific forge-style spinner using HTML/CSS for LeadFoundry."""
    
    if step in _SPINNER_MESSAGES:
        title, subtitle = _SPINNER_MESSAGES[step]
    else:
        title, subtitle = "⏳ Working…", "Processing your request."
    
    # --- Molten Metal Theme Colors ---
    forge_bg       = "rgba(42,46,51,0.90)"          # Forged steel background
    forge_shadow   = "rgba(0,0,0,0.55)"             # Industrial soft shadow
    ember_orange   = "#FF8A3D"                      # Molten core orange
    ember_gold     = "#FFB341"                      # Hot gold tint
    metal_text     = "#FFE9C7"                      # Forged-metal light text
    metal_subtext  = "rgba(255,233,199,0.80)"       # Slightly dimmer subtitle
    
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
        border:1px solid rgba(255,138,61,0.25); /* molten highlight */
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
