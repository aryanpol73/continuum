"""
Care Coordinator Portal — Patient Replies & Proof of Refill Inbox.
Administrative response triage. Zero medical advice channel.
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import PatientMessage
from src.continuum.audit import log_action
from app.components.style import apply_theme
from app.components.nav import render_sidebar, render_context_bar

st.set_page_config(page_title="Inbox | Continuum", page_icon="📥", layout="wide")
apply_theme()
render_sidebar()

st.title("Patient Replies")
st.caption("Administrative replies and uploads from patients. Not a medical advice channel.")
render_context_bar()

Session = get_session_factory()
with Session() as db:
    unread = (
        db.query(PatientMessage)
        .filter(PatientMessage.direction == "IN", PatientMessage.read_at.is_(None))
        .order_by(PatientMessage.created_at.desc())
        .all()
    )

    st.metric("Unread replies", len(unread))
    st.markdown("<br>", unsafe_allow_html=True)

    if not unread:
        st.info("No unread replies from patients. All administrative responses are up to date.")
    else:
        for m in unread:
            with st.container(border=True):
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"**{m.patient.name}** · `{m.patient.uh_id}` · {m.created_at:%d %b %H:%M}"
                    )
                    st.markdown(
                        f"**{m.category.replace('_', ' ').title()}** — {m.body or 'No message body'}"
                    )
                    if m.attachment_path and Path(m.attachment_path).exists():
                        ext = Path(m.attachment_path).suffix.lower()
                        if ext in [".png", ".jpg", ".jpeg"]:
                            st.image(m.attachment_path, width=280)
                        else:
                            st.caption(f"📎 Attachment: `{Path(m.attachment_path).name}`")
                with col_btn:
                    if st.button("Mark handled", key=f"h_{m.id}"):
                        m.read_at = datetime.utcnow()
                        m.handled_by = "care_coordinator"
                        log_action(
                            db,
                            action="PATIENT_MESSAGE_HANDLED",
                            entity_type="patient_message",
                            entity_id=str(m.id),
                            user_or_system="care_coordinator",
                            details={"patient_id": m.patient_id, "category": m.category},
                        )
                        db.commit()
                        st.success("Handled.")
                        st.rerun()
