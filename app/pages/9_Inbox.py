"""
Messages — Coordinator Communication Hub & Triage Workbench.
Two-column threaded inbox for patient-clinic chat, attachments, and urgent symptom triage.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import Patient
from src.continuum.messaging.thread import get_thread_summaries, mark_thread_read
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
            # Set default selection if none
            current_sel = st.session_state.get("inbox_patient_id")
            valid_ids = [s["patient_id"] for s in filtered]
            if current_sel not in valid_ids:
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
                # Mark as read when thread is opened
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

                st.divider()
                render_chat(db, selected_id, viewer="clinic", key_prefix="inbox")
