"""
Page 7: Care Continuum Retention & Performance Metrics.
Closed-loop lifecycle tracking and physician engagement scorecards.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.metrics.report import get_retention_funnel_metrics, get_doctor_retention_scorecard

st.set_page_config(page_title="Metrics & Retention | Continuum", page_icon="📈", layout="wide")

st.title("📈 Care Retention & Closed-Loop Analytics")
st.caption("Tracking patient return rates, refill gap closures, and consultant scorecards.")

Session = get_session_factory()

with Session() as db:
    metrics = get_retention_funnel_metrics(db)
    scorecards = get_doctor_retention_scorecard(db)
    status_counts = metrics["status_counts"]

    # Top KPI summary
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total Flagged Gaps", metrics["total_episodes"])
    with k2:
        st.metric("Refill-Only Gaps", metrics["refill_only_episodes"])
    with k3:
        st.metric("Patients Contacted / Promised", status_counts["contacted"] + status_counts["promised"])
    with k4:
        st.metric("Confirmed Returns", status_counts["returned"])

    st.markdown("---")

    col_chart, col_funnel = st.columns([1, 1])

    with col_chart:
        st.subheader("Closed-Loop Status Distribution")
        df_funnel = pd.DataFrame([
            {"Stage": "1. Detected", "Count": status_counts["detected"]},
            {"Stage": "2. Contacted", "Count": status_counts["contacted"]},
            {"Stage": "3. Promised Visit", "Count": status_counts["promised"]},
            {"Stage": "4. Returned to Clinic", "Count": status_counts["returned"]},
            {"Stage": "5. Unreachable", "Count": status_counts["unreachable"]},
            {"Stage": "6. Opted Out", "Count": status_counts["opted_out"]}
        ])
        st.bar_chart(df_funnel.set_index("Stage"))

    with col_funnel:
        st.subheader("Episode Reason Breakdown")
        st.markdown(
            f"""
            - **Diabetic Cohort Size:** `{metrics['diabetic_cohort_count']}` patients
            - **Refill-Only Gaps (Appointment-Blind):** `{metrics['refill_only_episodes']}` episodes
            - **Review Overdue Only:** `{metrics['followup_episodes']}` episodes
            - **Combined Overdue (Review + Refill):** `{metrics['combined_episodes']}` episodes
            - **Return-to-Care Rate:** `{metrics['return_to_care_rate_percent']}%`
            - **Patient Opt-Outs:** `{metrics['opted_out_patients']}`
            - **Authorized Kin Contacts:** `{metrics['kin_consented_patients']}`
            """
        )
        st.info(f"The {metrics['refill_only_episodes']} refill-only patients represent chronic diabetic individuals who ran out of medication while their appointment was still weeks away.")

    st.markdown("---")
    st.subheader("👨‍⚕️ Consultant Retention Scorecard")
    st.caption("Monitoring follow-up return rates across treating consultants.")

    if not scorecards:
        st.info("No consultant records to summarize.")
    else:
        st.dataframe(scorecards, use_container_width=True)
