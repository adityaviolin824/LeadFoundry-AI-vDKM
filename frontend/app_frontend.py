import streamlit as st
import requests
import time
from pathlib import Path
from templates.spinner import render_spinning_status
from templates.style import LF_STYLE
import pandas as pd
from io import BytesIO

# API_URL = "https://leadfoundry-ai-vdkm.onrender.com"
# API_URL = "https://leadfoundry-ai-vdkm-846645990850.asia-south1.run.app"
API_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 1200

INTAKE_TIMEOUT = 120
RESEARCH_TIMEOUT = 1800
FINALIZE_TIMEOUT = 120
POLL_INTERVAL = 2.5


def get_phase_timeout(phase, status):
    if phase == "intake" or status.startswith("intake"):
        return INTAKE_TIMEOUT
    if phase == "research" or status.startswith("research"):
        return RESEARCH_TIMEOUT
    if phase == "finalize" or status.startswith("finalize"):
        return FINALIZE_TIMEOUT
    return RESEARCH_TIMEOUT


st.set_page_config(page_title="LeadFoundry AI", page_icon="🧲", layout="wide")

st.markdown(f"<style>{LF_STYLE}</style>", unsafe_allow_html=True)


def init():
    st.session_state.setdefault("run_id", None)
    st.session_state.setdefault("view", "create_profile")
    st.session_state.setdefault("email_mode", False)


init()


def api_request(method, path, **kwargs):
    url = f"{API_URL}{path}"
    try:
        r = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text}
    except Exception as e:
        return 500, {"error": str(e)}


api_post = lambda p, json=None: api_request("post", p, json=json)
api_get = lambda p: api_request("get", p)
api_delete = lambda p: api_request("delete", p)


def get_stage_label(status, phase):
    if phase == "intake" or status.startswith("intake"):
        return "intake"
    if phase == "research" or status.startswith("research"):
        return "research"
    if phase == "finalize" or status.startswith("finalize"):
        return "finalization"
    if phase == "done":
        return "complete"
    return "processing"


def poll_until_multi(run_id, target_statuses, fail_statuses):
    status_box = st.empty()
    spinner_box = st.empty()
    debug_box = st.empty()

    current_phase = None
    phase_start_time = None

    while True:
        code, data = api_get(f"/runs/{run_id}/status")

        if code != 200:
            spinner_box.empty()
            status_box.empty()
            debug_box.empty()
            st.error(f"Failed to fetch status: {data}")
            return None

        status = data.get("status", "")
        phase = data.get("phase")

        debug_box.caption(f"🔍 Status: {status} | Phase: {phase}")

        if status in target_statuses:
            spinner_box.empty()
            status_box.empty()
            debug_box.empty()
            return data

        if status in fail_statuses:
            spinner_box.empty()
            status_box.empty()
            debug_box.empty()
            st.error(f"Pipeline failed: {data.get('error', status)}")
            return data

        if phase != current_phase:
            current_phase = phase
            phase_start_time = time.time()

        if status.endswith("_queued") or status.endswith("_running"):
            spinner_box.empty()
            render_spinning_status(
                status_box,
                spinner_box,
                get_stage_label(status, phase),
                0.5,
            )

        if phase:
            timeout = get_phase_timeout(phase, status)
            if phase_start_time and (time.time() - phase_start_time > timeout):
                spinner_box.empty()
                status_box.empty()
                debug_box.empty()
                st.error(f"Timeout during {phase} phase (> {timeout}s)")
                return None

        time.sleep(POLL_INTERVAL)


def poll_until(run_id, target_status, fail_status):
    return poll_until_multi(run_id, [target_status], [fail_status])


def is_probably_valid_email(email: str) -> bool:
    email = email.strip().lower()

    if " " in email:
        return False
    if email.count("@") != 1:
        return False

    local, domain = email.split("@")
    if not local or not domain:
        return False
    if "." not in domain:
        return False

    junk_locals = {"test", "email", "admin", "asdf", "example"}
    if local in junk_locals:
        return False

    return True


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
    "email_success": 4,
}

active = view_map.get(st.session_state.view, 0)

for idx, label in enumerate(PIPELINE):
    if idx == active:
        css, icon = "lf-step-chip lf-step-active", "🟢"
    elif idx < active:
        css, icon = "lf-step-chip lf-step-done", "✅"
    else:
        css, icon = "lf-step-chip lf-step-upcoming", "⚪"

    st.sidebar.markdown(
        f'<div class="{css}">{icon} <span>{label}</span></div>',
        unsafe_allow_html=True,
    )


st.markdown('<div class="lf-hero-title">🧲 LeadFoundry AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="lf-hero-tagline">Find qualified leads using intelligent agent teams.</div>',
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)


if st.session_state.view == "create_profile":

    st.markdown('<div class="lf-section-title">Create Lead Search Profile</div>', unsafe_allow_html=True)

    with st.form("form"):
        col1, col2 = st.columns(2)

        with col1:
            project = st.text_input(
                "Project Name (optional)",
                placeholder="e.g. University outreach, SaaS partnerships",
            )

            entity_type = st.selectbox(
                "Entity Type",
                options=[
                    "Corporate / Enterprise",
                    "Small & Medium Business (SMB)",
                    "Startup",
                    "Academic Institution",
                    "Government / Public Sector",
                    "Research Organization",
                    "Non-profit / NGO",
                    "Healthcare Organization",
                    "Financial Institution",
                    "Manufacturing / Industrial",
                    "Others",
                ],
            )

            entity_subtype = st.text_input(
                "Entity Subtype",
                placeholder="e.g. SaaS company, technical university, hospital network",
            )

        with col2:
            locations = st.text_input(
                "Locations",
                "Odisha, West Bengal",
            )

            industries = st.text_input(
                "Industries",
                "Education",
            )

            industry_keywords = st.text_input(
                "Industry Keywords",
                "engineering workshop, technical training",
            )

        col1, col2 = st.columns(2)

        with col1:
            roles = st.multiselect(
                "Target Roles",
                options=[
                    "Founder",
                    "Co-founder",
                    "CEO",
                    "CTO",
                    "CIO",
                    "COO",
                    "Chief Data Officer",
                    "President",
                    "Vice President",
                    "Director",
                    "Associate Director",
                    "Principal",
                    "Chancellor",
                    "Dean",
                    "Head of Department",
                    "Engineering Manager",
                    "Product Manager",
                    "Operations Head",
                    "Procurement Head",
                    "Program Manager",
                    "Research Lead",
                    "Others",
                ],
                default=["Director", "Principal"],
            )

        with col2:
            seniority = st.multiselect(
                "Seniority Level",
                options=[
                    "Founder",
                    "C-Level",
                    "Executive",
                    "Senior Management",
                    "Mid Management",
                    "Junior Management",
                    "Individual Contributor",
                    "Advisor / Board Member",
                    "Others",
                ],
                default=["Senior Management"],
            )

        col1, col2 = st.columns(2)

        with col1:
            lead_limit = st.number_input(
                "Lead Limit",
                min_value=10,
                max_value=1000,
                value=100,
            )

        with col2:
            required_fields = st.text_input(
                "Required Fields",
                "email, phone",
            )

        email = st.text_input(
            "Email (optional)",
            placeholder="Enter your email to receive leads automatically",
        )

        lead_target = st.selectbox(
            "What should we prioritize?",
            options=[
                "Companies",
                "People",
                "Both",
            ],
            index=2,
        )

        submit = st.form_submit_button("Launch Lead Intake", use_container_width=True)

    if submit:
        if not locations.strip() or not industries.strip():
            st.warning("Locations and Industries are required.")
            st.stop()

        if email.strip() and not is_probably_valid_email(email):
            st.error("Please enter a valid, real email address.")
            st.stop()

        payload = {
            "project": project.strip() or None,
            "lead_target": lead_target.lower(),
            "entity_type": entity_type,
            "targets": {
                "entity_subtype": entity_subtype.strip(),
                "locations": [x.strip() for x in locations.split(",") if x.strip()],
                "industries": [x.strip() for x in industries.split(",") if x.strip()],
                "keywords": [x.strip() for x in industry_keywords.split(",") if x.strip()],
                "company_sizes": [],
            },
            "personas": {
                "roles": roles,
                "seniority": seniority,
            },
            "constraints": {
                "lead_limit": int(lead_limit),
                "required_fields": [x.strip() for x in required_fields.split(",") if x.strip()],
                "exclusions": [],
            },
            "verification": {
                "level": "strict",
                "require_official_domain": True,
            },
            "seeds": {
                "seed_websites": [],
                "seed_company_names": [],
            },
        }

        if email.strip():
            payload["email"] = email.strip()
            st.session_state.email_mode = True
        else:
            st.session_state.email_mode = False

        code, data = api_post("/runs/full", json=payload)
        if code == 201:
            st.session_state.run_id = data["run_id"]
            st.session_state.view = "intake_processing"
            st.rerun()
        else:
            st.error(f"Failed to create run: {data}")


elif st.session_state.view == "intake_processing":

    run_id = st.session_state.run_id

    result = poll_until(run_id, "intake_completed", "intake_failed")
    
    if result:
        status = result.get("status")
        
        if status == "intake_completed":
            st.success("Intake completed successfully")
            
            if st.button("Start Lead Research", type="primary", use_container_width=True):
                code, data = api_post(f"/runs/{run_id}/research")
                if code == 202:
                    st.session_state.view = "research_processing"
                    st.rerun()
                else:
                    st.error(f"Failed to start research: {data}")
        else:
            error = result.get("error", "Unknown error")
            st.error(f"Intake failed: {error}")


elif st.session_state.view == "research_processing":

    run_id = st.session_state.run_id
    email_mode = st.session_state.email_mode

    if email_mode:
        result = poll_until_multi(
            run_id,
            target_statuses=["finalize_completed"],
            fail_statuses=["research_failed", "finalize_failed"]
        )
        
        if result:
            final_status = result.get("status")
            
            if final_status == "finalize_completed":
                if result.get("email_sent"):
                    st.session_state.view = "email_success"
                    st.rerun()
                else:
                    email_error = result.get("email_error", "Unknown error")
                    st.warning("Pipeline completed successfully")
                    st.warning(f"❌ Email delivery failed: {email_error}")
                    st.info("📥 You can download the results manually below")
                    
                    time.sleep(1)
                    st.session_state.view = "results"
                    st.rerun()
            else:
                error = result.get("error", "Unknown error")
                st.error(f"Pipeline failed: {error}")
    else:
        result = poll_until(run_id, "research_completed", "research_failed")
        
        if result:
            status = result.get("status")
            
            if status == "research_completed":
                st.success("Research completed successfully")
                
                if st.button("De-duplicate, Enrich, Sort & Generate Excel", type="primary", use_container_width=True):
                    code, data = api_post(f"/runs/{run_id}/finalize_full")
                    
                    if code in (200, 202):
                        st.session_state.view = "finalize_processing"
                        st.rerun()
                    else:
                        st.error(f"Failed to start finalization: {data}")
            else:
                error = result.get("error", "Unknown error")
                st.error(f"Research failed: {error}")


elif st.session_state.view == "finalize_processing":

    run_id = st.session_state.run_id

    result = poll_until(run_id, "finalize_completed", "finalize_failed")
    
    if result:
        status = result.get("status")
        
        if status == "finalize_completed":
            st.success("Finalization completed successfully")
            time.sleep(0.5)
            st.session_state.view = "results"
            st.rerun()
        else:
            error = result.get("error", "Unknown error")
            st.error(f"Finalization failed: {error}")


elif st.session_state.view == "email_success":

    st.markdown(
        """
        <div style="text-align:center; margin-top:60px;">
            <h1>Hot leads. Fresh cast.</h1>
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
        init()
        st.rerun()


elif st.session_state.view == "results":

    st.markdown('<div class="lf-section-title">Results & Download</div>', unsafe_allow_html=True)

    run_id = st.session_state.run_id

    code, status_data = api_get(f"/runs/{run_id}/status")
    
    if code != 200:
        st.error("Failed to fetch run status from API")
        st.stop()

    current_status = status_data.get("status")
    current_phase = status_data.get("phase")

    st.markdown("### Preview of Leads (first 20 rows)")

    excel_url = f"{API_URL}/runs/{run_id}/finalize_full/download_excel"

    try:
        r = requests.get(excel_url, timeout=30)
    except Exception as e:
        st.error(f"Failed to fetch Excel file: {e}")
        st.stop()

    if r.status_code == 200:
        st.success("Excel file ready for preview and download")

        try:
            excel_bytes = BytesIO(r.content)
            df = pd.read_excel(excel_bytes)

            if isinstance(df, pd.DataFrame) and len(df) > 0:
                max_rows = min(20, len(df))
                st.dataframe(df.head(max_rows), use_container_width=True)
                st.caption(f"Showing {max_rows} of {len(df)} total rows")
            else:
                st.info("Excel file is empty (no leads found)")

        except Exception as e:
            st.warning(f"Could not preview Excel: {e}")

        st.download_button(
            "📥 Download Excel",
            data=r.content,
            file_name="leadfoundry_leads.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )
    else:
        st.error("❌ Excel file not found")
        st.info(f"Current status: {current_status} | Phase: {current_phase}")
        
        if current_status != "finalize_completed":
            st.warning("Finalization may not have completed successfully")

    st.divider()

    if st.button("🔁 Start New Search", use_container_width=True):
        st.session_state.clear()
        init()
        st.rerun()


if st.session_state.view != "create_profile" and st.session_state.run_id:
    with st.expander("⚠️ Danger Zone"):
        if st.button("Cancel Run & Reset Pipeline", use_container_width=True):
            run_id = st.session_state.run_id
            
            code, data = api_delete(f"/runs/{run_id}")
            
            if code == 200:
                st.info(f"Cancellation signal sent: {data.get('status')}")
            else:
                st.warning(f"Failed to cancel: {data}")
            
            time.sleep(0.5)
            
            st.session_state.clear()
            init()
            st.rerun()