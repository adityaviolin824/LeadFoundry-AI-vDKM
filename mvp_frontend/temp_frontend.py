import streamlit as st
import requests
import time
from pathlib import Path
from templates.spinner import render_spinning_status

# -------------------------------------------------------------
# Config
# -------------------------------------------------------------
API_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 600

st.set_page_config(page_title="LeadFoundry AI", page_icon="🧲", layout="wide")

# -------------------------------------------------------------
# Global CSS
# -------------------------------------------------------------
css_path = Path("templates/style.css")
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# -------------------------------------------------------------
# Session State
# -------------------------------------------------------------
def init():
    st.session_state.setdefault("run_id", None)
    st.session_state.setdefault("view", "create_profile")
    st.session_state.setdefault("finalize_response", None)

init()

# -------------------------------------------------------------
# API helpers
# -------------------------------------------------------------
def api_request(method, path, **kwargs):
    url = f"{API_URL}{path}"
    try:
        r = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        try: return r.status_code, r.json()
        except: return r.status_code, {"raw": r.text}
    except Exception as e:
        return 500, {"error": str(e)}

api_post   = lambda p, json=None: api_request("post", p, json=json)
api_get    = lambda p: api_request("get", p)
api_delete = lambda p: api_request("delete", p)

# -------------------------------------------------------------
# Status helpers
# -------------------------------------------------------------
STATUS_LABELS = {
    "created": "🆕 Run created",
    "intake_queued": "📥 Intake queued",
    "intake_running": "📥 Intake running",
    "research_queued": "🔍 Research queued",
    "research_running": "🔍 Research running",
    "finalize_queued": "🧹 Finalize queued",
    "finalize_running": "🧹 Finalize running",
    "intake_failed": "❌ Intake failed",
    "research_failed": "❌ Research failed",
    "finalize_failed": "❌ Finalize failed",
    "cancelled": "⚠️ Cancelled"
}

interpret = lambda s: STATUS_LABELS.get(s, s)

# -------------------------------------------------------------
# Polling loop (smooth version)
# -------------------------------------------------------------
def poll_until(run_id, target_status, fail_status, stage_name):
    TIMEOUT = 900
    INTERVAL = 2.5 ######

    status_box  = st.empty()
    spinner_box = st.empty()

    last_status = None

    start = time.time()

    while True:

        code, data = api_get(f"/runs/{run_id}/status")
        status = data.get("status", "")

        # Update only if changed to avoid flicker
        if status != last_status:
            status_box.markdown(f"<div class='status-bar'>{interpret(status)}</div>", unsafe_allow_html=True)
            last_status = status

        if status == target_status:
            spinner_box.empty()
            return data

        if status == fail_status:
            spinner_box.empty()
            st.error(f"❌ {interpret(status)}")
            return data

        if status.endswith("_running") or status.endswith("_queued"):
            spinner_box.empty()
            render_spinning_status(status_box, spinner_box, stage_name, 0.5)

        if time.time() - start > TIMEOUT:
            st.error("Timeout waiting for pipeline stage.")
            return None

        time.sleep(INTERVAL)

# -------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------
st.sidebar.markdown("### 🧲 LeadFoundry AI")
st.sidebar.caption("Agentic lead generation pipeline")
st.sidebar.markdown("---")

PIPELINE = ["Profile Intake", "Lead Search", "Optimize", "Download"]
view_map = {
    "create_profile": 0,
    "intake_processing": 1,
    "research_processing": 2,
    "finalize_processing": 3,
    "results": 4
}

active = view_map.get(st.session_state.view, 0)

for idx, label in enumerate(PIPELINE):
    if idx == active:
        css = "lf-step-chip lf-step-active"; icon = "🟢"
    elif idx < active:
        css = "lf-step-chip lf-step-done"; icon = "✅"
    else:
        css = "lf-step-chip lf-step-upcoming"; icon = "⚪"

    st.sidebar.markdown(
        f'<div class="{css}">{icon} <span>{label}</span></div>',
        unsafe_allow_html=True
    )

# -------------------------------------------------------------
# HERO
# -------------------------------------------------------------
st.markdown('<div class="lf-hero-title">🧲 LeadFoundry AI</div>', unsafe_allow_html=True)
st.markdown('<div class="lf-hero-tagline">Find qualified leads using intelligent agent teams.</div>', unsafe_allow_html=True)

# Add two blank lines here:
st.markdown("<br><br>", unsafe_allow_html=True)


# -------------------------------------------------------------
# VIEW: CREATE PROFILE
# -------------------------------------------------------------
if st.session_state.view == "create_profile":

    st.markdown('<div class="lf-section-title">📥 Create Lead Search Profile</div>', unsafe_allow_html=True)

    with st.form("form"):
        col1, col2 = st.columns(2)

        with col1:
            project = st.text_input("Project Name", "college workshops")
            entity_type = st.text_input("Entity Type", "college")
            entity_subtype = st.text_input("Entity Subtype", "technical college")

        with col2:
            locations = st.text_input("Locations", "odisha, west bengal")
            keywords = st.text_input("Keywords", "engineering workshop, technical training")
            industries = st.text_input("Industries", "")

        col1, col2 = st.columns(2)
        with col1: roles = st.text_input("Roles", "principal, director")
        with col2: seniority = st.text_input("Seniority", "senior")

        col1, col2 = st.columns(2)
        with col1: lead_limit = st.number_input("Lead Limit", 10, 1000, 100)
        with col2: required_fields = st.text_input("Required Fields", "email, phone")

        submit = st.form_submit_button("🚀 Launch Lead Intake", use_container_width=True)

    if submit:
        payload = {
            "project": project,
            "entity_type": entity_type,
            "targets": {
                "entity_subtype": entity_subtype,
                "locations": [x.strip() for x in locations.split(",")],
                "industries": [x.strip() for x in industries.split(",") if x.strip()],
                "keywords": [x.strip() for x in keywords.split(",")],
                "company_sizes": []
            },
            "personas": {
                "roles": [x.strip() for x in roles.split(",")],
                "seniority": [x.strip() for x in seniority.split(",")],
            },
            "constraints": {
                "lead_limit": int(lead_limit),
                "required_fields": [x.strip() for x in required_fields.split(",")],
                "exclusions": []
            },
            "verification": {"level": "strict", "require_official_domain": True},
            "seeds": {"seed_websites": [], "seed_company_names": []}
        }

        code, data = api_post("/runs/full", json=payload)
        if code == 201:
            st.session_state.run_id = data["run_id"]
            st.session_state.view = "intake_processing"
            st.rerun()
        else:
            st.error(f"❌ Failed to create run: {data}")

# -------------------------------------------------------------
# VIEW: INTAKE PROCESSING
# -------------------------------------------------------------
elif st.session_state.view == "intake_processing":

    run_id = st.session_state.run_id

    poll_until(run_id, "intake_completed", "intake_failed", "intake")

    st.success("Intake completed.")

    if st.button("🔍 Start Research", type="primary", use_container_width=True):
        api_post(f"/runs/{run_id}/research")
        st.session_state.view = "research_processing"
        st.rerun()

# -------------------------------------------------------------
# VIEW: RESEARCH PROCESSING
# -------------------------------------------------------------
elif st.session_state.view == "research_processing":

    run_id = st.session_state.run_id

    poll_until(run_id, "research_completed", "research_failed", "research")

    st.success("Research completed.")

    if st.button("🧹 Run Finalize & Generate Excel", type="primary", use_container_width=True):
        code, data = api_post(f"/runs/{run_id}/finalize_full")
        if code in (200, 202):
            st.session_state.finalize_response = data
            st.session_state.view = "results"
            st.rerun()
        else:
            st.error("Finalize failed.")

# -------------------------------------------------------------
# VIEW: RESULTS
# -------------------------------------------------------------
elif st.session_state.view == "results":

    st.markdown('<div class="lf-section-title">🎉 Results & Download</div>', unsafe_allow_html=True)

    run_id = st.session_state.run_id
    data = st.session_state.finalize_response or {}

    excel_available = data.get("excel_available", False)
    url = f"{API_URL}/runs/{run_id}/finalize_full/download_excel"

    if excel_available:
        r = requests.get(url)
        if r.status_code == 200:
            st.success("📥 Excel ready for download!")
            st.download_button(
                "Download Excel",
                data=r.content,
                file_name="leadfoundry_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        else:
            st.error("Excel not found.")
    else:
        st.warning("Excel not ready yet.")

    if st.button("🔄 Start New Search", use_container_width=True):
        st.session_state.run_id = None
        st.session_state.finalize_response = None
        st.session_state.view = "create_profile"
        st.rerun()

# -------------------------------------------------------------
# Danger zone
# -------------------------------------------------------------
if st.session_state.view != "create_profile" and st.session_state.run_id:
    with st.expander("⚠️ Danger Zone"):
        if st.button("❌ Cancel Run & Reset Pipeline", use_container_width=True):
            api_delete(f"/runs/{st.session_state.run_id}")
            st.session_state.run_id = None
            st.session_state.finalize_response = None
            st.session_state.view = "create_profile"
            st.rerun()
