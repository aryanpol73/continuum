"""
Continuum - Overdue Follow-up & Refill Worklist
Ranked STRICTLY by days overdue (descending). Zero clinical severity scoring.
Tracks closed-loop lifecycle: detected -> contacted -> promised -> returned.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.config import get_today, get_rules
from src.continuum.models import Episode, Visit
from src.continuum.engine.worklist import get_overdue_worklist
from src.continuum.engine.investigations import get_all_missing_investigations_summary
from src.continuum.workflow.episodes import transition_episode
from src.continuum.workflow.states import is_valid_transition
from app.components.message_editor import render_message_editor
from app.components.style import apply_theme
from app.components.nav import render_sidebar, render_context_bar, require_clinic_setup

st.set_page_config(page_title="Overdue Worklist | Continuum", page_icon="📋", layout="wide")
apply_theme()
render_sidebar()
require_clinic_setup()

st.title("Overdue Worklist")
st.caption("Ranked strictly by days overdue. No clinical severity scoring.")
render_context_bar()

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


def render_patient_panel(db, row, inv_summary, key_prefix):
    """Renders the detailed patient panel and outreach action controls."""
    is_refill_only = row["is_refill_only"]
    badge_color = "#ea580c" if is_refill_only else "#0284c7"
    badge_label = "REFILL ONLY" if is_refill_only else row["reason"].replace("_", " ")

    st.subheader(f"{row['name']} ({row['uh_id']})")

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
                {row['max_overdue_days']} DAYS OVERDUE (RANK KEY) | {badge_label}
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

    st.markdown("---")
    st.markdown("#### 💬 Outreach Message & Call Script")
    render_message_editor(
        db=db,
        episode_id=row["episode_id"],
        recipient_type="PATIENT",
        key_prefix=f"{key_prefix}_{row['episode_id']}"
    )

    st.markdown("---")
    # Workflow Lifecycle Transition Buttons
    current_status = row.get("status", "detected")
    candidate_transitions = [
        ("contacted", "Mark 'Contacted'", "Outreach dispatched"),
        ("promised", "Mark 'Promised'", "Patient promised to attend follow-up"),
        ("returned", "Mark 'Returned'", "Attended clinic consultation"),
        ("unreachable", "Unreachable", "Call unanswered"),
        ("opted_out", "Opted Out", "Patient requested no further contact"),
    ]
    allowed_actions = [
        (s, label, r_reason) for (s, label, r_reason) in candidate_transitions
        if is_valid_transition(current_status, s) and (s != current_status or s == "contacted")
    ]

    if allowed_actions:
        st.markdown("**Update Closed-Loop Status:**")
        cols = st.columns(len(allowed_actions))
        for col, (target_status, label, default_reason) in zip(cols, allowed_actions):
            with col:
                if st.button(label, key=f"{key_prefix}_{target_status}_{row['episode_id']}", use_container_width=True):
                    try:
                        transition_episode(db, row['episode_id'], target_status, user="care_coordinator", reason=default_reason)
                        st.success(f"Updated to {target_status}!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def render_worklist_table_and_panel(db, rows, inv_summary, key_prefix, max_progress=540):
    """Renders the left table and right detail panel layout."""
    if not rows:
        st.info("No records match the current criteria.")
        return

    left, right = st.columns([5, 4], gap="large")

    records = []
    for r in rows:
        signal = "Refill only" if r.get("is_refill_only") else r.get("reason", "").replace("_", " ").title()
        last_v = r.get("last_visit")
        v_str = str(last_v) if last_v else "—"
        records.append({
            "Patient": r.get("name", ""),
            "UHID": r.get("uh_id", ""),
            "Days Overdue": r.get("max_overdue_days", 0),
            "Signal": signal,
            "Status": r.get("status", "").title(),
            "Last Visit": v_str
        })
    df = pd.DataFrame(records)

    selected_row = None
    with left:
        try:
            df_key = f"df_{key_prefix}"
            event = st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=620,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "Days Overdue": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=max_progress,
                        format="%d d"
                    )
                },
                key=df_key
            )
            selected_indices = []
            if df_key in st.session_state:
                ss_val = st.session_state[df_key]
                if hasattr(ss_val, "selection") and hasattr(ss_val.selection, "rows"):
                    selected_indices = ss_val.selection.rows
                elif isinstance(ss_val, dict) and "selection" in ss_val:
                    selected_indices = ss_val["selection"].get("rows", [])
            if not selected_indices and event:
                if hasattr(event, "selection") and hasattr(event.selection, "rows"):
                    selected_indices = event.selection.rows
                elif isinstance(event, dict) and "selection" in event:
                    selected_indices = event["selection"].get("rows", [])

            if selected_indices and 0 <= selected_indices[0] < len(rows):
                selected_row = rows[selected_indices[0]]
                st.session_state[f"last_selected_uhid_{key_prefix}"] = selected_row.get("uh_id")
            elif f"last_selected_uhid_{key_prefix}" in st.session_state:
                last_uhid = st.session_state[f"last_selected_uhid_{key_prefix}"]
                for r in rows:
                    if r.get("uh_id") == last_uhid:
                        selected_row = r
                        break
        except Exception:
            # Fallback to radio over patient labels in left column if st.dataframe selection fails
            st.dataframe(df, use_container_width=True, hide_index=True, height=400)
            patient_labels = [f"{r['name']} ({r['uh_id']}) — {r['max_overdue_days']}d" for r in rows]
            chosen_label = st.radio(
                "Select Patient for Details:",
                options=patient_labels,
                key=f"radio_{key_prefix}"
            )
            if chosen_label:
                chosen_idx = patient_labels.index(chosen_label)
                selected_row = rows[chosen_idx]

    with right:
        if selected_row:
            render_patient_panel(db, selected_row, inv_summary, key_prefix=f"{key_prefix}_panel")
        else:
            st.info("Select a patient to view details and prepare outreach.")


with Session() as db:
    worklist = get_overdue_worklist(
        db=db,
        reason=reason_filter,
        status=status_filter,
        search_query=search_q
    )

    if refill_only_toggle:
        worklist = [item for item in worklist if item["is_refill_only"]]

    # Fetch last visit dates for all episodes
    ep_ids = [w["episode_id"] for w in worklist]
    ep_visits = dict(
        db.query(Episode.id, Visit.visit_date)
        .outerjoin(Visit, Episode.visit_id == Visit.id)
        .filter(Episode.id.in_(ep_ids))
        .all()
    ) if ep_ids else {}

    for w in worklist:
        w["last_visit"] = ep_visits.get(w["episode_id"])

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
                    "UNDER_90": "Recently lapsed (≤ 90d)",
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

        render_worklist_table_and_panel(db, filtered_active, inv_summary, key_prefix="act", max_progress=540)

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
        max_dorm = max([w["max_overdue_days"] for w in dormant_items], default=1000)
        render_worklist_table_and_panel(db, dormant_items, inv_summary, key_prefix="dorm", max_progress=max(1000, max_dorm))
