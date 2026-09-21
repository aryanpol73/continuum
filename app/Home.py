"""
Continuum — Care Coordinator Portal & Executive Clinical Dashboard.
Ramraksha Hospital OPD (Akola).
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.config import get_today, set_today_override, get_settings
from src.continuum.db import get_session_factory, init_db
from src.continuum.models import get_clinic_profile
from src.continuum.metrics.report import get_retention_funnel_metrics
from src.continuum.workflow.episodes import generate_episodes_from_rules
from src.continuum.engine.cohort import update_all_visits_cohort
from src.continuum.engine.dosing import update_all_prescriptions_dosing
from app.components.style import apply_theme

st.set_page_config(
    page_title="Continuum | Clinical Care Engine",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)
apply_theme()

# Metric card CSS for KPI metrics
st.markdown("""
<style>
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px 18px;
        text-align: center;
    }
    .metric-value {
        font-size: 2.1rem;
        font-weight: 700;
        color: #111827;
        margin: 4px 0;
    }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)

init_db()

settings = get_settings()
current_today = get_today()

Session = get_session_factory()
with Session() as db:
    profile = get_clinic_profile(db)
    clinic_name_val = profile.clinic_name
    doctor_name_val = profile.doctor_name
    clinic_phone_val = profile.clinic_phone
    is_configured_val = profile.is_configured

# Sidebar: Time Anchor (Time-Travel Simulation Controller)
st.sidebar.title("🩺 Continuum")
st.sidebar.caption("Ambulatory Follow-up & Refill Engine")
st.sidebar.markdown("---")

st.sidebar.subheader("⏳ Time Anchor (Simulation)")
st.sidebar.info(f"**Current System Date:**\n`{current_today}`")

override_date = st.sidebar.date_input(
    "Set Simulation Date",
    value=current_today,
    help="Changing this date allows time-travel backtesting against historical clinic exports."
)

col_t1, col_t2 = st.sidebar.columns(2)
with col_t1:
    if st.sidebar.button("Apply Date", use_container_width=True):
        set_today_override(override_date)
        st.sidebar.success(f"Anchor set to {override_date}")
        st.rerun()
with col_t2:
    if st.sidebar.button("Reset Live", use_container_width=True):
        set_today_override(None)
        st.sidebar.info("Reset to live system date.")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Hospital:** {clinic_name_val}")
st.sidebar.markdown(f"**Consultant:** {doctor_name_val}")
st.sidebar.markdown(f"**Desk Phone:** `{clinic_phone_val}`")
if not is_configured_val:
    st.sidebar.warning("Demo Mode: Unconfigured")

if not is_configured_val:
    st.warning(
        "⚙️ **Clinic Setup Incomplete:** Continuum is running with neutral demo placeholders. "
        "Open **0_Clinic_Setup** in the sidebar to configure your hospital name, doctor, and desk phone live."
    )

# Header Block
st.title(clinic_name_val)
st.subheader(doctor_name_val)
st.caption(f"Simulated Today: {current_today}")

with Session() as db:
    metrics = get_retention_funnel_metrics(db)

# KPI Metric Cards
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-label">Registered Patients</div>
            <div class="metric-value">{metrics['total_patients']}</div>
            <div style="font-size: 0.8rem; color: #16a34a;">Master Register</div>
        </div>""",
        unsafe_allow_html=True
    )

with c2:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-label">Diabetic Cohort</div>
            <div class="metric-value" style="color: #0284c7;">{metrics['diabetic_cohort_count']}</div>
            <div style="font-size: 0.8rem; color: #64748b;">Chronic DM Patients</div>
        </div>""",
        unsafe_allow_html=True
    )

with c3:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-label">Total Overdue</div>
            <div class="metric-value" style="color: #dc2626;">{metrics['total_episodes']}</div>
            <div style="font-size: 0.8rem; color: #dc2626;">Past Grace Period</div>
        </div>""",
        unsafe_allow_html=True
    )

with c4:
    st.markdown(
        f"""<div class="metric-card" style="border: 2px solid #ea580c; background: #fff7ed;">
            <div class="metric-label" style="color: #c2410c;">Refill-Only Gaps</div>
            <div class="metric-value" style="color: #ea580c;">{metrics['refill_only_episodes']}</div>
            <div style="font-size: 0.8rem; color: #c2410c; font-weight: bold;">Appointment-Blind!</div>
        </div>""",
        unsafe_allow_html=True
    )

with c5:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-label">Review Overdue</div>
            <div class="metric-value" style="color: #9333ea;">{metrics['followup_episodes']}</div>
            <div style="font-size: 0.8rem; color: #64748b;">Follow-up Lapsed</div>
        </div>""",
        unsafe_allow_html=True
    )

with c6:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-label">Returned to Care</div>
            <div class="metric-value" style="color: #16a34a;">{metrics['status_counts']['returned']}</div>
            <div style="font-size: 0.8rem; color: #16a34a;">Closed Loop</div>
        </div>""",
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# Quick Operations Bar
col_act1, col_act2, col_act3 = st.columns([1, 1, 1])

with col_act1:
    if st.button("⚡ Run Clinical Engine Now", use_container_width=True, type="primary"):
        with Session() as db:
            with st.spinner("Executing cohort classifier, dosing parser, and episode evaluations..."):
                update_all_visits_cohort(db)
                update_all_prescriptions_dosing(db)
                stats = generate_episodes_from_rules(db, anchor_date=current_today, user="ui_dashboard")
                st.success(f"Engine completed! Identified {stats['episodes_created']} overdue patients (including {stats['refill_only_episodes']} refill-only gaps).")
                st.rerun()

with col_act2:
    if st.button("📋 Open Overdue Worklist", use_container_width=True):
        st.switch_page("pages/1_Worklist.py")

with col_act3:
    if st.button("👥 Review Duplicate Registrations", use_container_width=True):
        st.switch_page("pages/3_Duplicate_Review.py")

st.markdown("---")

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("💡 The Headline Finding: Refill-Only Gaps")
    st.markdown(
        f"""
        Traditional hospital OPD software only tracks the next appointment date.
        
        In Ramraksha Hospital's records:
        - **{metrics['refill_only_episodes']} patients** had medications prescribed for 30 days (e.g. `WALAPHAGE G2` 60 tablets @ 2/day), but their follow-up was scheduled after 60 or 90 days.
        - **Result:** These patients ran out of diabetes medications weeks ago, but appointment-based systems see nothing wrong!
        - Continuum catches every single one by evaluating supply days (`Qty / daily_dose`) across every line of the prescription.
        """
    )

with col_right:
    st.subheader("🛡️ Hard Rules & Guardrails")
    st.markdown(
        """
        - **Pure Days-Overdue Ranking:** Ranked strictly by days overdue (descending). Never by clinical severity.
        - **No Autonomous Prescribing:** Coordinator presses send; system never acts autonomously.
        - **Consent First:** Kin contact strictly blocked without affirmative consent record.
        - **Template-Only Messages:** Messages only translate and fill placeholders in approved templates.
        """
    )
