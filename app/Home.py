"""
Continuum — Care Coordinator Portal & Executive Clinical Dashboard.
Ambulatory Follow-up & Refill Engine.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from src.continuum.config import get_today, set_today_override, get_settings
from src.continuum.db import get_session_factory, init_db
from src.continuum.models import get_clinic_profile
from src.continuum.metrics.report import get_retention_funnel_metrics
from src.continuum.metrics.daily import get_daily_snapshot, get_daily_series
from src.continuum.workflow.episodes import generate_episodes_from_rules
from src.continuum.engine.cohort import update_all_visits_cohort
from src.continuum.engine.dosing import update_all_prescriptions_dosing
from app.components.style import apply_theme
from app.components.nav import render_sidebar, render_context_bar

st.set_page_config(
    page_title="Continuum | Clinical Care Engine",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)
apply_theme()
render_sidebar()

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
render_context_bar()

with Session() as db:
    metrics = get_retention_funnel_metrics(db)
    snap = get_daily_snapshot(db, current_today)
    series = get_daily_series(db, current_today, days=30)

# Hero Metric Card (Refill-Only Gaps)
st.markdown(
    f"""
    <div style="border: 1px solid #E5E7EB; border-radius: 8px; padding: 22px; background: #FFFFFF; margin-bottom: 20px;">
        <div style="font-size: 0.85rem; font-weight: 600; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Refill-only gaps</div>
        <div style="font-size: 3.2rem; font-weight: 700; color: #C2410C; line-height: 1.1; margin: 4px 0 8px 0;">{metrics['refill_only_episodes']}</div>
        <div style="font-size: 0.95rem; color: #4B5563;">These patients ran out of medication while their appointment calendar showed nothing overdue.</div>
    </div>
    """,
    unsafe_allow_html=True
)

# Secondary KPI Metrics Row
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Registered Patients", metrics["total_patients"])
with m2:
    st.metric("Diabetic Cohort", metrics["diabetic_cohort_count"])
with m3:
    st.metric("Total Overdue", metrics["total_episodes"])
with m4:
    st.metric("Review Overdue", metrics["followup_episodes"])
with m5:
    st.metric("Returned to Care", metrics["status_counts"]["returned"])

st.markdown("<br>", unsafe_allow_html=True)

# Daily Activity Snapshot & 30-Day Trend
st.subheader(f"Activity on {current_today}")
d1, d2, d3, d4 = st.columns(4)
d1.metric("Expected in OPD", snap["expected_today"])
d2.metric("Attended", snap["attended_today"])
d3.metric("Did not attend", snap["no_show_today"])
d4.metric(
    "Care lapsed today",
    snap["lapsed_today"],
    help="Appointment date or medication supply ran out on this date.",
)

df_daily = pd.DataFrame(series).set_index("date")
st.caption("Last 30 days — patients lapsing vs. patients attending")
st.bar_chart(df_daily[["Lapsed", "Attended"]], height=220)

st.markdown("<br>", unsafe_allow_html=True)

# Quick Operations Bar
col_act1, col_act2, col_act3 = st.columns([1, 1, 1])

with col_act1:
    if st.button("Run Clinical Engine Now", use_container_width=True, type="primary"):
        with st.spinner("Recomputing overdue signals…"):
            with Session() as engine_db:
                generate_episodes_from_rules(engine_db, user="ui_coordinator")
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
    st.subheader("The Headline Finding: Refill-Only Gaps")
    st.markdown(
        f"""
        Traditional hospital OPD software only tracks the next appointment date.
        
        In {clinic_name_val}'s records:
        - **{metrics['refill_only_episodes']} patients** had medications prescribed for 30 days (e.g. `WALAPHAGE G2` 60 tablets @ 2/day), but their follow-up was scheduled after 60 or 90 days.
        - **Result:** These patients ran out of diabetes medications weeks ago, but appointment-based systems see nothing wrong!
        - Continuum catches every single one by evaluating supply days (`Qty / daily_dose`) across every line of the prescription.
        """
    )

with col_right:
    st.subheader("Hard Rules & Guardrails")
    st.markdown(
        """
        - **Pure Days-Overdue Ranking:** Ranked strictly by days overdue (descending). Never by clinical severity.
        - **No Autonomous Prescribing:** Coordinator presses send; system never acts autonomously.
        - **Consent First:** Kin contact strictly blocked without affirmative consent record.
        - **Template-Only Messages:** Messages only translate and fill placeholders in approved templates.
        """
    )
