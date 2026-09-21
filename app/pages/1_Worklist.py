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
from src.continuum.config import get_today, get_rules
from src.continuum.engine.worklist import get_overdue_worklist
from src.continuum.engine.investigations import get_all_missing_investigations_summary
from src.continuum.workflow.episodes import transition_episode
from app.components.message_editor import render_message_editor

st.set_page_config(page_title="Overdue Worklist | Continuum", page_icon="📋", layout="wide")

st.title("📋 Care Coordinator Overdue Worklist")
st.caption("Ambulatory chronic care outreach queue ranked strictly by days overdue (descending). Zero clinical severity scoring.")

Session = get_session_factory()
today = get_today()
rules = get_rules()
actionable_limit = rules.get("actionable_window", {}).get("actionable_window_days", 540)

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


def render_worklist_row(db, row, idx, inv_summary, key_prefix):
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

            # Missing investigation administrative signal
            pending_tests = inv_summary.get(row["uh_id"], [])
            if pending_tests:
                st.markdown(
                    f"""
                    <div style="margin-top: 6px; padding: 4px 8px; background: #fef3c7; border-left: 3px solid #f59e0b; border-radius: 4px; font-size: 0.85rem;">
                        🔬 <b>Pending Advised Labs (>45d):</b> {', '.join(pending_tests)}
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
                key_prefix=f"{key_prefix}_{row['episode_id']}"
            )

        st.markdown("---")
        # Workflow Lifecycle Transition Buttons
        st.markdown("**Update Closed-Loop Status:**")
        qa1, qa2, qa3, qa4, qa5 = st.columns(5)

        with qa1:
            if st.button("Mark 'Contacted'", key=f"{key_prefix}_contacted_{row['episode_id']}"):
                try:
                    transition_episode(db, row['episode_id'], "contacted", user="care_coordinator", reason="Outreach dispatched")
                    st.success("Updated to contacted!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with qa2:
            if st.button("Mark 'Promised'", key=f"{key_prefix}_promised_{row['episode_id']}"):
                try:
                    transition_episode(db, row['episode_id'], "promised", user="care_coordinator", reason="Patient promised to attend follow-up")
                    st.success("Updated to promised!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with qa3:
            if st.button("Mark 'Returned'", key=f"{key_prefix}_ret_{row['episode_id']}"):
                try:
                    transition_episode(db, row['episode_id'], "returned", user="care_coordinator", reason="Attended clinic consultation")
                    st.success("Episode successfully closed — Returned to Care!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with qa4:
            if st.button("Unreachable", key=f"{key_prefix}_unreach_{row['episode_id']}"):
                try:
                    transition_episode(db, row['episode_id'], "unreachable", user="care_coordinator", reason="Call unanswered")
                    st.info("Marked as unreachable.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with qa5:
            if st.button("Opted Out", key=f"{key_prefix}_optout_{row['episode_id']}"):
                try:
                    transition_episode(db, row['episode_id'], "opted_out", user="care_coordinator", reason="Patient requested no further contact")
                    st.info("Marked as opted_out.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


with Session() as db:
    worklist = get_overdue_worklist(
        db=db,
        reason=reason_filter,
        status=status_filter,
        search_query=search_q
    )

    if refill_only_toggle:
        worklist = [item for item in worklist if item["is_refill_only"]]

    # Load administrative missing investigation summary
    inv_summary = get_all_missing_investigations_summary(db, anchor_date=today)

    active_items = [w for w in worklist if w["max_overdue_days"] <= actionable_limit]
    dormant_items = [w for w in worklist if w["max_overdue_days"] > actionable_limit]

    tab_active, tab_dormant = st.tabs([
        f"📞 Active Actionable Queue (≤ {actionable_limit} Days) [{len(active_items)}]",
        f"📁 Dormant / Archive (> {actionable_limit} Days) [{len(dormant_items)}]"
    ])

    with tab_active:
        col_sub1, col_sub2 = st.columns([3, 1])
        with col_sub1:
            st.markdown(f"**Showing {len(active_items)} actionable overdue patients (Simulated Today: `{today}`)**")
        with col_sub2:
            window_subfilter = st.selectbox(
                "Actionable Horizon",
                options=["ALL_ACTIONABLE", "UNDER_90", "91_180", "181_540"],
                format_func=lambda x: {
                    "ALL_ACTIONABLE": f"All Actionable (≤{actionable_limit}d)",
                    "UNDER_90": "High Urgency (≤ 90d)",
                    "91_180": "Moderate (91 - 180d)",
                    "181_540": "Extended Lapsed (181 - 540d)"
                }[x],
                key="sub_horizon_filter"
            )

        filtered_active = active_items
        if window_subfilter == "UNDER_90":
            filtered_active = [w for w in active_items if w["max_overdue_days"] <= 90]
        elif window_subfilter == "91_180":
            filtered_active = [w for w in active_items if 91 <= w["max_overdue_days"] <= 180]
        elif window_subfilter == "181_540":
            filtered_active = [w for w in active_items if 181 <= w["max_overdue_days"] <= 540]

        if not filtered_active:
            st.info("No active queue records match the selected horizon.")
        else:
            for idx, row in enumerate(filtered_active):
                render_worklist_row(db, row, idx, inv_summary, key_prefix="act")

    with tab_dormant:
        st.markdown(
            f"""
            <div style="padding: 10px 14px; background: #f3f4f6; border-radius: 6px; margin-bottom: 12px; font-size: 0.9rem;">
                ℹ️ <b>Dormant / Archived Cases (> {actionable_limit} days):</b> 
                These patients have been lapsed for over ~18 months. Routed to this archive queue so day-to-day coordinators 
                focus calls strictly on actionable, responsive patients.
            </div>
            """,
            unsafe_allow_html=True
        )
        if not dormant_items:
            st.info("No dormant records in this view.")
        else:
            for idx, row in enumerate(dormant_items):
                render_worklist_row(db, row, idx, inv_summary, key_prefix="dorm")

