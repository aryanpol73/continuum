"""
Page 5: Caregiver / Kin Escalation Queue.
Manage outreach to primary family contacts when chronic patients remain unresponsive, with strict consent gating.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.config import get_today
from src.continuum.workflow.escalation import get_kin_escalation_candidates, escalate_episode_to_kin
from app.components.message_editor import render_message_editor
from app.components.style import apply_theme

st.set_page_config(page_title="Kin Escalation | Continuum", page_icon="🚨", layout="wide")
apply_theme()
from app.components.nav import render_sidebar, render_context_bar
render_sidebar()

st.title("Caregiver / Kin Escalation Queue")
st.caption("Outreach center for patients overdue past the escalation threshold. Strictly gated by patient's recorded kin consent.")
render_context_bar()

Session = get_session_factory()
today = get_today()

with Session() as db:
    candidates = get_kin_escalation_candidates(db)
    
    st.markdown(f"**Identified {len(candidates)} escalation candidates (Anchor Date: `{today}`)**")

    if not candidates:
        st.info("No patients currently require kin escalation. All overdue patients have responded or are within initial grace periods.")
    else:
        for idx, row in enumerate(candidates):
            kin_status_color = "#16a34a" if row["kin_consent_allowed"] else "#dc2626"
            kin_badge = "✓ KIN OUTREACH AUTHORIZED" if row["kin_consent_allowed"] else "🚫 KIN CONTACT UNAUTHORIZED"

            with st.expander(
                f"[{row['status'].upper()}] {row['name']} ({row['uh_id']}) — Overdue by {row['max_overdue_days']} days | Caregiver: {row['kin_name']}",
                expanded=(idx == 0)
            ):
                col_left, col_right = st.columns([1, 1])

                with col_left:
                    st.markdown(f"**Patient Name:** {row['name']} (`{row['uh_id']}`)")
                    st.markdown(f"**Patient Mobile:** `{row['phone']}`")
                    st.markdown(f"**Registered Kin:** {row['kin_name']} ({row['kin_relation']})")
                    st.markdown(f"**Kin Mobile:** `{row['kin_phone']}`")
                    st.markdown(f"**Flag Reason:** {row['reason']} &bull; **Due Date:** {row['due_date']}")
                    st.markdown(f"**Days Overdue:** `{row['max_overdue_days']}` days")
                    st.markdown(f"**Last Patient Outreach:** `{row.get('last_patient_attempt', 'N/A')}` ({row.get('days_since_patient_attempt', 0)} days ago)")
                    
                    st.markdown(
                        f"""
                        <div style="margin-top: 10px;">
                            <span style="background: {kin_status_color}22; color: {kin_status_color}; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 0.85rem;">
                                {kin_badge}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                with col_right:
                    st.markdown("#### 💬 Caregiver WhatsApp Dispatch")
                    render_message_editor(
                        db=db,
                        episode_id=row["episode_id"],
                        recipient_type="KIN",
                        key_prefix=f"kin_{row['episode_id']}"
                    )

                    if not row["kin_consent_allowed"]:
                        st.error(f"⚠️ {row['consent_reason']}\n\nReaching out to a relative without explicit consent violates clinical privacy. To enable, update consent in the Consent Registry.")
                    else:
                        if st.button("Dispatch Kin Outreach (Mark Kin Escalated)", key=f"btn_move_esc_{row['episode_id']}", type="primary"):
                            ok, msg = escalate_episode_to_kin(db, row["episode_id"], user="care_coordinator")
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
