"""
Patient Care Portal — Token-Authenticated Administrative Reply & Prescription Upload.
Zero clinical medical advice channel. Not monitored 24/7.
Emergency directs to clinic desk and 108.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import (
    Prescription,
    get_clinic_profile,
    resolve_patient_token,
)
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
    st.subheader("Chat with the clinic")
    topic_choice = st.selectbox(
        "Topic",
        ["Appointment", "Medicines", "Reports", "Other"],
        key="pt_topic_select",
    )
    render_chat(db, patient.id, viewer="patient", key_prefix="pt", topic=topic_choice.upper())


