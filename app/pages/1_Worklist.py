"""
Continuum - Overdue Follow-up & Refill Worklist
Ranked STRICTLY by days overdue (descending). Zero clinical severity scoring.
Tracks closed-loop lifecycle: detected -> contacted -> promised -> returned.
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.config import get_today
from src.continuum.engine.worklist import get_overdue_worklist
from src.continuum.workflow.episodes import transition_episode
from app.components.message_editor import render_message_editor

st.set_page_config(page_title="Overdue Worklist | Continuum", page_icon="📋", layout="wide")

st.title("📋 Care Coordinator Overdue Worklist")
st.caption("Ambulatory chronic care outreach queue ranked strictly by days overdue (descending).")

Session = get_session_factory()
today = get_today()

# Filter Bar
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 3])

with col_f1:
    reason_filter = st.selectbox(
        "Flag Reason",
        options=["ALL", "REFILL_GAP", "FOLLOWUP_OVERDUE", "COMBINED"],
        format_func=lambda x: {
            "ALL": "All Reasons",
            "REFILL_GAP": "Medication Refill Gap",
            "FOLLOWUP_OVERDUE": "Follow-up Review Overdue",
            "COMBINED": "Combined Overdue"
        }[x]
    )

with col_f2:
    status_filter = st.selectbox(
        "Workflow Status",
        options=["ALL", "detected", "contacted", "promised", "returned", "unreachable", "opted_out"],
        index=0
    )

with col_f3:
    refill_only_toggle = st.checkbox("Refill-Only Gaps (Appointment-blind)", value=False)

with col_f4:
    search_q = st.text_input("🔍 Search Patient", placeholder="Name, UHID, or Mobile...")

with Session() as db:
    worklist = get_overdue_worklist(
        db=db,
        reason=reason_filter,
        status=status_filter,
        search_query=search_q
    )

    if refill_only_toggle:
        worklist = [item for item in worklist if item["is_refill_only"]]

    st.markdown(f"**Showing {len(worklist)} overdue patient records (Simulated Today: `{today}`)**")

    if not worklist:
        st.info("No overdue records match the current filter.")
    else:
        for idx, row in enumerate(worklist):
            is_refill_only = row["is_refill_only"]
            badge_color = "#ea580c" if is_refill_only else "#0284c7"
            badge_label = "REFILL ONLY" if is_refill_only else row["reason"].replace("_", " ")

            expander_title = (
                f"[{row['status'].upper()}] {row['name']} ({row['uh_id']}) — "
                f"{row['max_overdue_days']} DAYS OVERDUE | {badge_label}"
            )

            with st.expander(expander_title, expanded=(idx < 2)):
                c_info1, c_info2 = st.columns([1, 1])

                with c_info1:
                    st.markdown(f"**Patient Name:** {row['name']}")
                    st.markdown(f"**UHID:** `{row['uh_id']}` &nbsp;|&nbsp; **Mobile:** `{row['phone']}`")
                    st.markdown(f"**Age / Gender:** {row['age']} yrs / {row['gender']}")
                    st.markdown(f"**Consultant:** {row['doctor_name']}")
                    if row["first_drug_exhausted"]:
                        st.markdown(f"**Earliest Drug Exhausted:** `{row['first_drug_exhausted']}`")
                    
                    st.markdown(f"**Follow-up Overdue Days:** `{row['followup_overdue_days']}`")
                    st.markdown(f"**Refill Overdue Days:** `{row['refill_overdue_days']}`")
                    
                    st.markdown(
                        f"""
                        <div style="margin-top: 8px;">
                            <span style="background: {badge_color}22; color: {badge_color}; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem;">
                                {row['max_overdue_days']} DAYS OVERDUE (RANK KEY)
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    if row["opt_out"]:
                        st.warning("⚠️ Patient has requested to opt out of routine reminders.")

                with c_info2:
                    st.markdown("#### 💬 Outreach Message & Call Script")
                    render_message_editor(
                        db=db,
                        episode_id=row["episode_id"],
                        recipient_type="PATIENT",
                        key_prefix=f"wl_{row['episode_id']}"
                    )

                st.markdown("---")
                # Workflow Lifecycle Transition Buttons
                st.markdown("**Update Closed-Loop Status:**")
                qa1, qa2, qa3, qa4, qa5 = st.columns(5)

                with qa1:
                    if st.button("Mark 'Contacted'", key=f"btn_contacted_{row['episode_id']}"):
                        try:
                            transition_episode(db, row['episode_id'], "contacted", user="care_coordinator", reason="Outreach dispatched")
                            st.success("Updated to contacted!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with qa2:
                    if st.button("Mark 'Promised'", key=f"btn_promised_{row['episode_id']}"):
                        try:
                            transition_episode(db, row['episode_id'], "promised", user="care_coordinator", reason="Patient promised to attend follow-up")
                            st.success("Updated to promised!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with qa3:
                    if st.button("Mark 'Returned'", key=f"btn_ret_{row['episode_id']}"):
                        try:
                            transition_episode(db, row['episode_id'], "returned", user="care_coordinator", reason="Attended clinic consultation")
                            st.success("Episode successfully closed — Returned to Care!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with qa4:
                    if st.button("Unreachable", key=f"btn_unreach_{row['episode_id']}"):
                        try:
                            transition_episode(db, row['episode_id'], "unreachable", user="care_coordinator", reason="Call unanswered")
                            st.info("Marked as unreachable.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with qa5:
                    if st.button("Opted Out", key=f"btn_optout_{row['episode_id']}"):
                        try:
                            transition_episode(db, row['episode_id'], "opted_out", user="care_coordinator", reason="Patient requested no further contact")
                            st.info("Marked as opted_out.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
