"""
Reusable WhatsApp-style threaded chat component for patient and clinic viewers.
Renders message bubbles, attachments, urgent red-flag alerts, and response guidelines.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
import streamlit as st

from src.continuum.models import Patient, get_clinic_profile
from src.continuum.messaging.thread import get_thread, post_message


def render_chat(
    db: Session,
    patient_id: int,
    viewer: str = "clinic",
    key_prefix: str = "chat",
    topic: Optional[str] = None,
) -> None:
    """
    Renders conversation history and composer.
    viewer: 'clinic' (coordinator side) or 'patient' (token-authenticated portal).
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        st.warning("Patient not found.")
        return

    profile = get_clinic_profile(db)
    clinic_phone = profile.clinic_phone if profile and profile.clinic_phone else "+91 90000 00000"

    thread = get_thread(db, patient_id, limit=100)

    # Render previous messages
    if not thread:
        st.caption("No messages in this conversation yet. Send a message below to start.")
    else:
        for m in thread:
            is_patient_message = (m.direction == "IN")
            role = "user" if is_patient_message else "assistant"

            if viewer == "patient":
                sender_label = "You" if is_patient_message else "Clinic Desk"
            else:
                sender_label = f"{patient.name.split()[0]} ({patient.uh_id})" if is_patient_message else "You (Clinic Desk)"

            time_str = m.created_at.strftime("%d %b, %H:%M") if m.created_at else ""

            with st.chat_message(role):
                header_html = f"<b>{sender_label}</b> &nbsp;<span style='color:#6B7280;font-size:0.78rem;'>{time_str}</span>"
                if m.urgent_flagged:
                    header_html += (
                        " &nbsp;<span style='background:#FEE2E2;color:#991B1B;"
                        "padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:bold;'>"
                        "⚠️ NEEDS ATTENTION</span>"
                    )
                st.markdown(header_html, unsafe_allow_html=True)

                if m.topic:
                    st.caption(f"Topic: {m.topic.replace('_', ' ').title()}")

                if m.body:
                    st.markdown(m.body)

                # Attachments
                if m.attachment_path and Path(m.attachment_path).exists():
                    fp = Path(m.attachment_path)
                    ext = fp.suffix.lower()
                    if ext in [".png", ".jpg", ".jpeg"] or (m.attachment_mime and "image" in m.attachment_mime):
                        st.image(str(fp), width=240)
                    else:
                        st.download_button(
                            label=f"📎 {m.attachment_name or fp.name}",
                            data=fp.read_bytes(),
                            file_name=m.attachment_name or fp.name,
                            mime=m.attachment_mime or "application/octet-stream",
                            key=f"{key_prefix}_dl_{m.id}",
                        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Show urgent banner if patient just triggered an urgent red flag
    if st.session_state.get(f"{key_prefix}_urgent_notice"):
        st.error(
            f"⚠️ Your message mentions something that may need urgent attention. "
            f"Please do not wait for a reply — call {clinic_phone} now, or 108 in an emergency."
        )
        st.session_state[f"{key_prefix}_urgent_notice"] = False

    # Patient side guidance caption
    if viewer == "patient":
        st.caption(
            f"The clinic desk reads messages on working days and usually replies within "
            f"2 working days. This is not monitored at night or on holidays. For anything "
            f"urgent call {clinic_phone} or 108."
        )

    # File attachment before chat input
    with st.expander("📎 Attach Document / Photo (Optional)", expanded=False):
        up_file = st.file_uploader(
            "Attachment",
            type=["png", "jpg", "jpeg", "pdf"],
            key=f"{key_prefix}_uploader",
            label_visibility="collapsed",
        )
        if up_file and st.button("Send Attachment Now", key=f"{key_prefix}_send_file_btn"):
            direction = "IN" if viewer == "patient" else "OUT"
            author = f"patient:{patient.uh_id}" if viewer == "patient" else "care_coordinator"
            msg = post_message(
                db,
                patient_id=patient_id,
                direction=direction,
                body=f"Sent attachment: {up_file.name}",
                topic=topic,
                uploaded_file=up_file,
                author=author,
            )
            if viewer == "patient" and msg.urgent_flagged:
                st.session_state[f"{key_prefix}_urgent_notice"] = True
            st.rerun()

    # Chat text input
    chat_prompt = "Type a message to the clinic desk..." if viewer == "patient" else f"Reply to {patient.name.split()[0]}..."
    user_input = st.chat_input(chat_prompt, key=f"{key_prefix}_input")

    if user_input:
        direction = "IN" if viewer == "patient" else "OUT"
        author = f"patient:{patient.uh_id}" if viewer == "patient" else "care_coordinator"
        msg = post_message(
            db,
            patient_id=patient_id,
            direction=direction,
            body=user_input,
            topic=topic,
            uploaded_file=up_file if 'up_file' in locals() and up_file else None,
            author=author,
        )
        if viewer == "patient" and msg.urgent_flagged:
            st.session_state[f"{key_prefix}_urgent_notice"] = True
        st.rerun()
