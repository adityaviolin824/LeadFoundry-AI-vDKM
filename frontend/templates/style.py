LF_STYLE = """

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, Oxygen, Ubuntu,
                 Cantarell, "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}

body {
    background: linear-gradient(160deg, #2A2E33 0%, #3A3F45 50%, #2A2E33 100%);
    background-attachment: fixed;
    color: #F4F5F6;
}

/* Subtle metallic texture */
body::before {
    content: "";
    position: fixed;
    inset: 0;
    background: radial-gradient(circle at 30% 20%, rgba(255,138,61,0.13), transparent 60%),
                radial-gradient(circle at 70% 80%, rgba(255,179,65,0.10), transparent 70%);
    pointer-events: none;
    z-index: -1;
}


/* --------------------------------------------------
   HERO SECTION
-------------------------------------------------- */

.lf-hero-title {
    font-size: 2.6rem;
    font-weight: 800;
    background: linear-gradient(90deg, #FFE9C7 0%, #FFB341 40%, #FF8A3D 100%);
    background-clip: text;
    -webkit-background-clip: text;
    -moz-background-clip: text;
    color: transparent;
    margin-top: 0.2rem;
}

.lf-hero-tagline {
    font-size: 1.15rem;
    color: #D4D6D8;
    line-height: 1.5;
}

.lf-subtle {
    margin-top: 0.4rem;
    color: #A3A5A7;
    font-size: 0.9rem;
}


/* --------------------------------------------------
   SECTION TITLES
-------------------------------------------------- */

.lf-section-title {
    font-size: 1.45rem;
    font-weight: 700;
    padding-bottom: 0.4rem;
    margin-bottom: 0.9rem;
    border-bottom: 2px solid rgba(255,138,61,0.45);
    color: #FFE9C7;
}


/* --------------------------------------------------
   PIPELINE STEP CHIPS
-------------------------------------------------- */

.lf-step-chip {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.55rem 0.9rem;
    border-radius: 10px;
    margin-bottom: 0.4rem;
    font-size: 0.92rem;
    border: 1px solid transparent;
}

.lf-step-done {
    background-color: rgba(191,198,209,0.18);
    border-color: rgba(191,198,209,0.4);
    color: #D6D7DA;
}

.lf-step-active {
    background: linear-gradient(90deg, #FF8A3D 0%, #FFB341 100%);
    border-color: #FFB341;
    color: #2A2E33;
    font-weight: 700;
}

.lf-step-upcoming {
    background-color: rgba(255,255,255,0.05);
    border-color: rgba(255,255,255,0.12);
    color: #9A9DA0;
}


/* --------------------------------------------------
   FORMS / INPUTS
-------------------------------------------------- */

.stTextInput > div > input,
.stSelectbox div[data-baseweb="select"] div,
.stNumberInput input,
textarea,
input {
    border-radius: 8px !important;
    background: #3A3F45 !important;
    border: 1px solid #555B63 !important;
    color: #F4F5F6 !important;
}

.stTextInput > div > input:focus,
.stNumberInput input:focus,
textarea:focus {
    border-color: #FF8A3D !important;
    box-shadow: 0 0 0 2px rgba(255,138,61,0.35) !important;
}


/* --------------------------------------------------
   BUTTONS
-------------------------------------------------- */

.stButton > button,
button[kind="primary"] {
    border-radius: 10px !important;
    padding: 0.55rem 1.2rem !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    border: none !important;
    background: linear-gradient(90deg, #FF8A3D 0%, #FFB341 100%) !important;
    color: #2A2E33 !important;
    cursor: pointer !important;
    transition: filter 0.15s ease !important;
}

.stButton > button:hover {
    filter: brightness(0.92) !important;
}

.stButton > button:active {
    filter: brightness(0.85) !important;
}

button[kind="secondary"] {
    background: #3A3F45 !important;
    border: 1px solid #6A7077 !important;
    color: #DADCDD !important;
}

button[kind="secondary"]:hover {
    background: #4A5058 !important;
}


/* --------------------------------------------------
   SPINNERS / LOADERS
-------------------------------------------------- */

.spinner {
    animation: spin 1s linear infinite !important;
    border-top-color: #FF8A3D !important;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}


/* --------------------------------------------------
   PREVIEW BLOCKS
-------------------------------------------------- */

.lf-preview-block {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px;
    padding: 1rem;
    margin-top: 1rem;
    color: #F4F5F6;
}


/* --------------------------------------------------
   ALERTS / CALLOUTS
-------------------------------------------------- */

.stAlert {
    border-radius: 10px !important;
}

.stAlert > div {
    background-color: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
}


/* --------------------------------------------------
   SIDEBAR
-------------------------------------------------- */

section[data-testid="stSidebar"] {
    min-width: 265px !important;
    background: #1F2226 !important;
    border-right: 1px solid #2E3237 !important;
}

section[data-testid="stSidebar"] * {
    color: #E2E3E5 !important;
}


/* --------------------------------------------------
   SCROLLBARS
-------------------------------------------------- */

::-webkit-scrollbar {
    width: 7px;
    height: 7px;
}

::-webkit-scrollbar-thumb {
    background: rgba(255,138,61,0.45);
    border-radius: 5px;
}

::-webkit-scrollbar-thumb:hover {
    background: rgba(255,138,61,0.65);
}


/* --------------------------------------------------
   SPACERS
-------------------------------------------------- */

.lf-space-sm { margin-top: 0.4rem; }
.lf-space-md { margin-top: 0.8rem; }
.lf-space-lg { margin-top: 1.2rem; }
"""
