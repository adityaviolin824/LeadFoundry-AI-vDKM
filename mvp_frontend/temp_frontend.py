import streamlit as st
import requests
import time
from pathlib import Path
from templates.spinner import render_spinning_status
from templates.style import LF_STYLE
import pandas as pd
from io import BytesIO

# -------------------------------------------------------------
# Config
# -------------------------------------------------------------
# API_URL = "https://leadfoundry-ai-vdkm.onrender.com"
# API_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 1200

st.set_page_config(page_title="LeadFoundry AI", page_icon="🧲", layout="wide")

# Load inline CSS AFTER page config
st.markdown(f"<style>{LF_STYLE}</style>", unsafe_allow_html=True)

# -------------------------------------------------------------
# Session State
# -------------------------------------------------------------
def init():
    st.session_state.setdefault("run_id", None)
    st.session_state.setdefault("view", "create_profile")
    st.session_state.setdefault("finalize_response", None)
    st.session_state.setdefault("email_sent", False)

init()


# -------------------------------------------------------------
# API helpers
# -------------------------------------------------------------
def api_request(method, path, **kwargs):
    url = f"{API_URL}{path}"
    try:
        r = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        try:
            return r.status_code, r.json()
        except:
            return r.status_code, {"raw": r.text}
    except Exception as e:
        return 500, {"error": str(e)}

api_post = lambda p, json=None: api_request("post", p, json=json)
api_get = lambda p: api_request("get", p)
api_delete = lambda p: api_request("delete", p)

# -------------------------------------------------------------
# Status helpers
# -------------------------------------------------------------
STATUS_LABELS = {
    "created": "🆕 Run created",
    "intake_queued": "📥 Intake queued",
    "intake_running": "📥 Intake running",
    "intake_completed": "✅ Intake complete",
    "research_queued": "Research queued",
    "research_running": "Research running",
    "research_completed": "🎉 Research complete",
    "finalize_queued": "Finalize queued",
    "finalize_running": "Finalize running",
    "finalize_completed": "🎉 Complete",
    "intake_failed": "❌ Intake failed",
    "research_failed": "❌ Research failed",
    "finalize_failed": "❌ Finalize failed",
    "cancelled": "⚠️ Cancelled"
}

interpret = lambda s: STATUS_LABELS.get(s, s)

# -------------------------------------------------------------
# Polling loop - UPDATED TO HANDLE MULTIPLE END STATES
# -------------------------------------------------------------
def poll_until_multi(run_id, target_statuses, fail_statuses, stage_name):
    """
    Poll until any of the target_statuses or fail_statuses is reached.
    target_statuses and fail_statuses should be lists.
    """
    TIMEOUT = 1500
    INTERVAL = 2.5

    status_box = st.empty()
    spinner_box = st.empty()

    last_status = None
    start = time.time()

    while True:
        code, data = api_get(f"/runs/{run_id}/status")
        status = data.get("status", "")

        if status != last_status:
            if not status.endswith("_running") and not status.endswith("_queued"):
                status_box.markdown(
                    f"<div class='status-bar'>{interpret(status)}</div>",
                    unsafe_allow_html=True,
                )
            last_status = status

        # Check if we've reached a target status
        if status in target_statuses:
            spinner_box.empty()
            return data

        # Check if we've reached a failure status
        if status in fail_statuses:
            spinner_box.empty()
            st.error(f"{interpret(status)}")
            return data

        # Show spinner for active statuses (FIX 1: This already handles finalize_running correctly)
        if status.endswith("_running") or status.endswith("_queued"):
            spinner_box.empty()
            render_spinning_status(status_box, spinner_box, stage_name, 0.5)

        if time.time() - start > TIMEOUT:
            st.error("Timeout waiting for pipeline stage.")
            return None

        time.sleep(INTERVAL)


# Keep the original for backward compatibility
def poll_until(run_id, target_status, fail_status, stage_name):
    return poll_until_multi(run_id, [target_status], [fail_status], stage_name)


# -------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------
st.sidebar.markdown("### 🧲 LeadFoundry AI")
st.sidebar.caption("Agentic lead generation pipeline")
st.sidebar.divider()

PIPELINE = ["Profile Intake", "Lead Search", "Optimize", "Download"]
view_map = {
    "create_profile": 0,
    "intake_processing": 1,
    "research_processing": 2,
    "finalize_processing": 3,
    "results": 4,
}

active = view_map.get(st.session_state.view, 0)

for idx, label in enumerate(PIPELINE):
    if idx == active:
        css = "lf-step-chip lf-step-active"
        icon = "🟢"
    elif idx < active:
        css = "lf-step-chip lf-step-done"
        icon = "✅"
    else:
        css = "lf-step-chip lf-step-upcoming"
        icon = "⚪"

    st.sidebar.markdown(
        f'<div class="{css}">{icon} <span>{label}</span></div>',
        unsafe_allow_html=True,
    )

# -------------------------------------------------------------
# HERO
# -------------------------------------------------------------
st.markdown('<div class="lf-hero-title">🧲 LeadFoundry AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="lf-hero-tagline">Find qualified leads using intelligent agent teams.</div>',
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

# -------------------------------------------------------------
# VIEW: CREATE PROFILE
# -------------------------------------------------------------
if st.session_state.view == "create_profile":

    st.markdown('<div class="lf-section-title">Create Lead Search Profile</div>', unsafe_allow_html=True)

    with st.form("form"):
        col1, col2 = st.columns(2)
        with col1:
            project = st.text_input("Project Name", "college workshops")
            entity_type = st.text_input("Entity Type", "college")
            entity_subtype = st.text_input("Entity Subtype", "technical college")
        with col2:
            locations = st.text_input("Locations", "odisha, west bengal")
            keywords = st.text_input("Keywords", "engineering workshop, technical training")
            industries = st.text_input("Industries", "education")

        col1, col2 = st.columns(2)
        with col1:
            roles = st.text_input("Roles", "principal, director")
        with col2:
            seniority = st.text_input("Seniority", "senior")

        col1, col2 = st.columns(2)
        with col1:
            lead_limit = st.number_input("Lead Limit", 10, 1000, 100)
        with col2:
            required_fields = st.text_input("Required Fields", "email, phone")

        # -------------------------
        # OPTIONAL EMAIL INPUT
        # -------------------------
        email = st.text_input(
            "Email (optional)",
            placeholder="Enter your email to receive leads automatically"
        )

        submit = st.form_submit_button("Launch Lead Intake", use_container_width=True)

    if submit:
        # -------------------------
        # BASIC REQUIRED FIELD CHECKS
        # -------------------------
        if not entity_type.strip():
            st.warning("Entity Type is required.")
            st.stop()

        if not locations.strip():
            st.warning("At least one location is required.")
            st.stop()

        if not industries.strip():
            st.warning("At least one industry is required.")
            st.stop()

        payload = {
            "project": project,
            "entity_type": entity_type,
            "targets": {
                "entity_subtype": entity_subtype,
                "locations": [x.strip() for x in locations.split(",")],
                "industries": [x.strip() for x in industries.split(",") if x.strip()],
                "keywords": [x.strip() for x in keywords.split(",")],
                "company_sizes": [],
            },
            "personas": {
                "roles": [x.strip() for x in roles.split(",")],
                "seniority": [x.strip() for x in seniority.split(",")],
            },
            "constraints": {
                "lead_limit": int(lead_limit),
                "required_fields": [x.strip() for x in required_fields.split(",")],
                "exclusions": [],
            },
            "verification": {"level": "strict", "require_official_domain": True},
            "seeds": {"seed_websites": [], "seed_company_names": []},
        }

        # attach email only if provided
        if email and email.strip():
            payload["email"] = email.strip()

        code, data = api_post("/runs/full", json=payload)
        if code == 201:
            st.session_state.run_id = data["run_id"]
            st.session_state.view = "intake_processing"
            st.rerun()
        else:
            st.error(f"Failed to create run: {data}")


# -------------------------------------------------------------
# VIEW: INTAKE PROCESSING
# -------------------------------------------------------------
elif st.session_state.view == "intake_processing":

    run_id = st.session_state.run_id

    poll_until(run_id, "intake_completed", "intake_failed", "intake")
    st.success("Intake completed.")

    if st.button("Start Lead Research", type="primary", use_container_width=True):
        api_post(f"/runs/{run_id}/research")
        st.session_state.view = "research_processing"
        st.rerun()


# -------------------------------------------------------------
# VIEW: RESEARCH PROCESSING - UPDATED WITH BOTH FIXES
# -------------------------------------------------------------
elif st.session_state.view == "research_processing":

    run_id = st.session_state.run_id
    status_msg = st.empty()

    # Get initial status to check if email delivery is enabled
    code, initial_data = api_get(f"/runs/{run_id}/status")
    email_enabled = initial_data.get("email_delivery_enabled", False)

    if email_enabled:
        # Wait for finalize_completed since email triggers auto-finalization
        # FIX 1: Using stage_name="research & finalization" (already correct)
        result = poll_until_multi(
            run_id,
            target_statuses=["finalize_completed"],
            fail_statuses=["research_failed", "finalize_failed"],
            stage_name="research & finalization"
        )
        
        if result:
            final_status = result.get("status")
            
            if final_status == "finalize_completed":
                # Fetch finalize metadata so UI has excel_available
                _, finalize_data = api_post(f"/runs/{run_id}/finalize_full")

                if result.get("email_sent"):
                    # Email success path
                    st.session_state.finalize_response = finalize_data
                    st.session_state.email_sent = True
                    st.session_state.view = "email_success"
                    st.rerun()
                else:
                    # Email failed but finalize succeeded
                    email_error = result.get("email_error", "Unknown error")
                    st.warning(f"Finalization completed, but email failed: {email_error}")
                    st.info("You can still download the results manually below.")

                    st.session_state.finalize_response = finalize_data
                    st.session_state.view = "results"
                    st.rerun()
            else:
                st.error(f"Pipeline failed at {final_status}")

                            
    else:
        # No email - just wait for research_completed
        result = poll_until(run_id, "research_completed", "research_failed", "research")
        
        if result and result.get("status") == "research_completed":
            status_msg.success("Research completed.")
            
            if st.button("De-duplicate Sort & Generate Excel", type="primary", use_container_width=True):
                code, data = api_post(f"/runs/{run_id}/finalize_full")
                if code in (200, 202):
                    st.session_state.finalize_response = data
                    st.session_state.view = "results"
                    st.rerun()
                else:
                    st.error("Finalize failed.")


# -------------------------------------------------------------
# VIEW: EMAIL SUCCESSFUL
# -------------------------------------------------------------
elif st.session_state.view == "email_success":

    st.markdown(
        """
        <div style="text-align:center; margin-top:60px;">
            <h1>🧲 Hot leads. Fresh cast.</h1>
            <h2>Inbox delivery.</h2>
            <br/>
            <p style="font-size:18px;">
                Your leads have been forged in the LeadFoundry<br/>
                and delivered straight to your inbox.
            </p>
            <p style="opacity:0.7;">
                Check spam if you don't see it. Even great leads get lost sometimes.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    if st.button("🔁 Start New Search", type="primary", use_container_width=True):
        st.session_state.clear()
        st.session_state.view = "create_profile"
        st.rerun()


# -------------------------------------------------------------
# VIEW: RESULTS
# -------------------------------------------------------------
elif st.session_state.view == "results":

    st.markdown('<div class="lf-section-title">Results & Download</div>', unsafe_allow_html=True)

    run_id = st.session_state.run_id
    data = st.session_state.finalize_response or {}

    st.markdown("### Preview of Leads (first 20 rows)")

    excel_url = f"{API_URL}/runs/{run_id}/finalize_full/download_excel"
    excel_available = data.get("excel_available", False)

    if excel_available:
        r = requests.get(excel_url)

        if r.status_code == 200:
            st.success("Excel ready for preview and download!")

            try:
                excel_bytes = BytesIO(r.content)
                df = pd.read_excel(excel_bytes)

                if isinstance(df, pd.DataFrame) and len(df) > 0:
                    max_rows = min(20, len(df))
                    st.dataframe(df.head(max_rows), use_container_width=True)
                    st.caption(f"Showing {max_rows} of {len(df)} rows")
                else:
                    st.info("Excel file is empty.")

            except Exception as e:
                st.warning(f"Could not preview Excel: {e}")

            st.download_button(
                "Download Excel",
                data=r.content,
                file_name="leadfoundry_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
        else:
            st.error("Excel not found or not accessible.")
    else:
        st.warning("Excel not ready yet.")

    if st.button("Start New Search", use_container_width=True):
        st.session_state.clear()
        st.session_state.view = "create_profile"
        st.rerun()

# -------------------------------------------------------------
# Danger zone
# -------------------------------------------------------------
if st.session_state.view != "create_profile" and st.session_state.run_id:
    with st.expander("Danger Zone"):
        if st.button("Cancel Run & Reset Pipeline", use_container_width=True):
            api_delete(f"/runs/{st.session_state.run_id}")
            st.session_state.clear()
            st.session_state.view = "create_profile"
            st.rerun()