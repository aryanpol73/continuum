"""
Patient Care Portal — Token-Authenticated Administrative Reply & Prescription Upload.
Zero clinical medical advice channel. Not monitored 24/7.
Emergency directs to clinic desk and 108.
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
from src.continuum.config import get_base_dir
from src.continuum.models import (
    PatientMessage,
    Prescription,
    get_clinic_profile,
    resolve_patient_token,
)
from src.continuum.audit import log_action
from app.components.chat import render_chat

st.set_page_config(
    page_title="My Care",
    page_icon="🩺",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """<style>
 [data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="stToolbar"] {display:none;}
 .block-container {max-width:440px; padding-top:1.1rem;}
 .stButton button {width:100%;}
</style>""",
    unsafe_allow_html=True,
)

Session = get_session_factory()
token = st.query_params.get("t")

with Session() as db:
    patient = resolve_patient_token(db, token) if token else None
    if not patient:
        st.error("This link is invalid or has expired. Please contact the clinic.")
        st.stop()

    profile = get_clinic_profile(db)
    st.markdown(f"**{profile.clinic_name}**")
    st.caption(f"Namaste, {patient.name.split()[0]}")

    st.warning(
        f"This page is for appointments and prescription uploads only. "
        f"It is not checked at all hours and is not for medical advice. "
        f"For anything urgent, call {profile.clinic_phone} or 108."
    )

    st.subheader("My current medicines")
    rxs = (
        db.query(Prescription)
        .filter(Prescription.patient_id == patient.id)
        .order_by(Prescription.id.desc())
        .limit(6)
        .all()
    )
    if not rxs:
        st.caption("No prescription on record yet.")
    for r in rxs:
        st.markdown(f"- **{r.medication_name}** — {r.raw_dose or ''}  ·  qty {r.quantity or '—'}")

    st.divider()
    st.subheader("Reply to the clinic")
    choice = st.radio(
        "Message",
        [
            "I will come for my check-up",
            "I need a new appointment date",
            "I have stopped taking my medicines",
            "I have already visited another doctor",
        ],
        label_visibility="collapsed",
    )
    note = st.text_input(
        "Anything to add (optional)",
        max_chars=140,
        placeholder="e.g. I can come on Saturday morning",
    )
    if st.button("Send to clinic", type="primary"):
        msg_body = f"{choice}" + (f" — {note}" if note else "")
        msg = PatientMessage(
            patient_id=patient.id,
            direction="IN",
            category="APPOINTMENT_REPLY",
            body=msg_body,
        )
        db.add(msg)
        log_action(
            db,
            action="PATIENT_PORTAL_REPLY",
            entity_type="Patient",
            entity_id=str(patient.id),
            user=f"patient:{patient.uh_id}",
            details={"category": "APPOINTMENT_REPLY", "body": msg_body},
        )
        db.commit()
        st.success("Sent. The clinic desk will see this.")

    st.divider()
    st.subheader("Upload a pharmacy bill or prescription")
    up = st.file_uploader(
        "Photo or PDF",
        type=["png", "jpg", "jpeg", "pdf"],
        label_visibility="collapsed",
    )
    if up and st.button("Upload"):
        dest = get_base_dir() / "data" / "uploads" / "patient"
        dest.mkdir(parents=True, exist_ok=True)
        fp = dest / f"{patient.uh_id}_{int(datetime.utcnow().timestamp())}_{up.name}"
        fp.write_bytes(up.getbuffer())
        msg = PatientMessage(
            patient_id=patient.id,
            direction="IN",
            category="REFILL_PROOF",
            body=f"Uploaded {up.name}",
            attachment_path=str(fp),
        )
        db.add(msg)
        log_action(
            db,
            action="PATIENT_PORTAL_UPLOAD",
            entity_type="Patient",
            entity_id=str(patient.id),
            user=f"patient:{patient.uh_id}",
            details={"category": "REFILL_PROOF", "filename": up.name},
        )
        db.commit()
        st.success("Received. The desk will confirm your refill.")

    st.divider()
    st.subheader("Chat with the clinic")
    topic_choice = st.selectbox(
        "Message Topic",
        ["Medicines", "Appointment", "Reports", "Other"],
        key="pt_topic_select",
    )
    render_chat(db, patient.id, viewer="patient", key_prefix="pt", topic=topic_choice.upper())

