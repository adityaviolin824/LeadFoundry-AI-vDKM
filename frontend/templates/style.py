import base64
from pathlib import Path
import streamlit as st


def apply_lf_styles():
    """Inject LeadFoundry CSS with a clean engineering-themed background."""
    img_path = Path(__file__).parent / "background.png"
    bg_url = ""

    if img_path.exists():
        try:
            with img_path.open("rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            bg_url = f"data:image/png;base64,{b64}"
        except Exception:
            bg_url = ""

    st.markdown(
        f"""
<style>

/* --------------------------------------------------
   GLOBAL LAYOUT
-------------------------------------------------- */

body, .stApp {{
    background-color: #0E1318; /* steel fallback */
}}

/* --------------------------------------------------
   BACKGROUND IMAGE LAYER (NO BLUR, NO DARKENING)
-------------------------------------------------- */

body::before, .stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;

    background-image: url("{bg_url}");
    background-position: center;
    background-size: cover;
    background-repeat: no-repeat;
}}

/* --------------------------------------------------
   ENSURE CONTENT FLOATS ABOVE BACKGROUND
-------------------------------------------------- */

.stApp > * {{
    position: relative;
    z-index: 1;
}}

/* --------------------------------------------------
   TYPOGRAPHY BASE
-------------------------------------------------- */

html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, Oxygen, Ubuntu,
                 Cantarell, "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    color: #E6E8EB;
}}

/* --------------------------------------------------
   HERO
-------------------------------------------------- */

.lf-hero-title {{
    font-size: 2.6rem;
    font-weight: 800;
    background: linear-gradient(
        90deg,
        #DCE7F3 0%,
        #7FA9D6 45%,
        #F3A15F 100%
    );
    -webkit-background-clip: text;
    color: transparent;
}}

.lf-hero-tagline {{
    font-size: 1.15rem;
    color: #B9C0C8;
}}

/* --------------------------------------------------
   INPUTS (DARK, EYE-SAFE)
-------------------------------------------------- */

.stTextInput input,
.stNumberInput input,
textarea {{
    border-radius: 8px !important;
    background: #0F141A !important;
    border: 1px solid #2E3A46 !important;
    color: #E6E8EB !important;
}}

.stSelectbox div[data-baseweb="select"] div {{
    border-radius: 8px !important;
    background: #121923 !important;
    border: 1px solid #2E3A46 !important;
    color: #E6E8EB !important;
}}

/* Focus: engineering blue */
.stTextInput input:focus,
.stNumberInput input:focus,
textarea:focus {{
    border-color: #4A84C6 !important;
    box-shadow: 0 0 0 1px rgba(74, 132, 198, 0.4) !important;
}}

/* --------------------------------------------------
   BUTTONS
-------------------------------------------------- */

.stButton > button {{
    border-radius: 10px !important;
    padding: 0.55rem 1.2rem !important;
    font-weight: 600 !important;
    background: linear-gradient(
        90deg,
        #4A84C6 0%,
        #6FA3DA 100%
    ) !important;
    color: #0E1318 !important;
    border: none !important;
}}

.stButton > button:hover {{
    background: linear-gradient(
        90deg,
        #4A84C6 0%,
        #F0A15A 100%
    ) !important;
}}

</style>
""",
        unsafe_allow_html=True,
    )
