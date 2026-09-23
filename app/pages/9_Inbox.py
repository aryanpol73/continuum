"""
Messages — Coordinator Communication Hub & Triage Workbench.
Two-column threaded inbox for patient-clinic chat, attachments, and urgent symptom triage.
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
from src.continuum.models import Patient, PatientMessage, PatientAccessToken, issue_patient_token
from src.continuum.messaging.thread import get_thread_summaries, mark_thread_read
from src.continuum.audit import log_action
from app.components.chat import render_chat
from app.components.style import apply_theme
from app.components.nav import render_sidebar, render_context_bar, require_clinic_setup

st.set_page_config(page_title="Messages | Continuum", page_icon="💬", layout="wide")
apply_theme()
render_sidebar()
require_clinic_setup()

st.title("Patient Messages")
st.caption("Threaded patient-clinic chat, document exchanges, and red-flag symptom triage.")
render_context_bar()

Session = get_session_factory()
with Session() as db:
    all_summaries = get_thread_summaries(db)

    col_list, col_chat = st.columns([4, 6])

    with col_list:
        with st.container(border=True):
            st.markdown("**Start a conversation**")
            all_pts = db.query(Patient).order_by(Patient.name).all()
            pt_options = {"Select a patient...": None}
            for p in all_pts:
                pt_options[f"{p.name} ({p.uh_id}) - {p.phone or 'no phone'}"] = p.id

            chosen_label = st.selectbox(
                "Select a patient",
                options=list(pt_options.keys()),
                key="inbox_new_patient_select",
                label_visibility="collapsed",
            )
            if st.button("Open conversation", key="btn_open_conversation"):
                target_pid = pt_options.get(chosen_label)
                if target_pid is not None:
                    st.session_state["inbox_patient_id"] = target_pid
                    st.rerun()

        st.subheader("Conversations")
        col_f1, col_f2 = st.columns([3, 2])
        with col_f1:
            search_query = st.text_input("Search", placeholder="Name or UHID...", label_visibility="collapsed")
        with col_f2:
            filter_mode = st.selectbox("Filter", ["All", "Unread", "Urgent"], label_visibility="collapsed")

        # Apply search and filters
        filtered = all_summaries
        if search_query:
            sq = search_query.strip().lower()
            filtered = [s for s in filtered if sq in s["name"].lower() or sq in s["uh_id"].lower()]

        if filter_mode == "Unread":
            filtered = [s for s in filtered if s["unread_in_count"] > 0]
        elif filter_mode == "Urgent":
            filtered = [s for s in filtered if s["has_urgent"]]

        if not filtered:
            if not all_summaries:
                st.info("No patient conversations yet. Inbound messages from My Care will appear here.")
            else:
                st.caption("No conversations match this search filter.")
        else:
            # Fall back to first thread only when no patient is currently selected
            if st.session_state.get("inbox_patient_id") is None and filtered:
                st.session_state["inbox_patient_id"] = filtered[0]["patient_id"]

            for s in filtered:
                is_selected = (st.session_state.get("inbox_patient_id") == s["patient_id"])
                border_color = "#0F766E" if is_selected else "#E5E7EB"
                bg_color = "#F0FDF4" if is_selected else "#FFFFFF"

                with st.container(border=True):
                    c_info, c_btn = st.columns([4, 1])
                    with c_info:
                        urg_badge = "🔴 " if s["has_urgent"] else ""
                        time_lbl = s["last_message_at"].strftime("%d %b %H:%M") if s["last_message_at"] else ""
                        st.markdown(f"**{urg_badge}{s['name']}** · `{s['uh_id']}`")
                        st.caption(f"{s['last_message_body'][:50]}... · {time_lbl}")
                        if s["unread_in_count"] > 0:
                            st.markdown(
                                f"<span style='background:#0F766E;color:white;padding:2px 8px;border-radius:10px;font-size:0.75rem;'>"
                                f"{s['unread_in_count']} unread</span>",
                                unsafe_allow_html=True,
                            )
                    with c_btn:
                        btn_label = "Active" if is_selected else "Open"
                        if st.button(btn_label, key=f"sel_p_{s['patient_id']}", disabled=is_selected):
                            st.session_state["inbox_patient_id"] = s["patient_id"]
                            st.rerun()

    with col_chat:
        selected_id = st.session_state.get("inbox_patient_id")
        if not selected_id:
            st.info("Select a conversation on the left to read and reply.")
        else:
            sel_patient = db.query(Patient).filter(Patient.id == selected_id).first()
            if not sel_patient:
                st.warning("Selected patient record not found.")
            else:
                # Skip mark_thread_read when patient has no unread inbound messages
                has_inbound = (
                    db.query(PatientMessage)
                    .filter(
                        PatientMessage.patient_id == selected_id,
                        PatientMessage.direction == "IN",
                        PatientMessage.read_at.is_(None),
                    )
                    .first()
                ) is not None
                if has_inbound:
                    mark_thread_read(db, selected_id, reader="care_coordinator")

                # Header with details and link to Patient Detail
                c_h1, c_h2 = st.columns([4, 2])
                with c_h1:
                    st.markdown(f"### {sel_patient.name}")
                    st.caption(f"UHID: `{sel_patient.uh_id}` &bull; Phone: `{sel_patient.phone or 'None'}`")
                with c_h2:
                    if st.button("Open Full Patient 360° →", key=f"btn_p360_{sel_patient.id}"):
                        st.session_state["selected_patient_id"] = sel_patient.id
                        st.switch_page("pages/2_Patient_Detail.py")

                # Check for active portal link
                now_dt = datetime.utcnow()
                active_token = (
                    db.query(PatientAccessToken)
                    .filter(
                        PatientAccessToken.patient_id == sel_patient.id,
                        PatientAccessToken.revoked.is_(False),
                        (PatientAccessToken.expires_at.is_(None) | (PatientAccessToken.expires_at > now_dt)),
                    )
                    .order_by(PatientAccessToken.id.desc())
                    .first()
                )
                if not active_token:
                    st.warning("This patient has no active portal link. They will not see clinic replies until you issue one.")
                    if st.button("Generate patient link", key=f"btn_gen_link_inbox_{sel_patient.id}"):
                        tok = issue_patient_token(db, sel_patient.id, days_valid=30)
                        log_action(
                            db,
                            action="PATIENT_LINK_ISSUED",
                            entity_type="Patient",
                            entity_id=str(sel_patient.id),
                            user="care_coordinator",
                            details={"token_suffix": tok.token[-6:]},
                        )
                        st.session_state[f"inbox_token_{sel_patient.id}"] = tok.token
                        st.rerun()

                tok_str = st.session_state.get(f"inbox_token_{sel_patient.id}")
                if tok_str:
                    portal_url = f"http://localhost:8501/My_Care?t={tok_str}"
                    st.caption("Patient Portal Link (valid 30 days):")
                    st.code(portal_url, language="text")

                st.divider()
                render_chat(db, selected_id, viewer="clinic", key_prefix="inbox")
