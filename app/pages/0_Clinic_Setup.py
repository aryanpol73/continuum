"""
Page 0: Clinic Profile & OPD Configuration.
Allows deploying Continuum to any hospital or outpatient department by configuring
the clinic name, treating clinician, desk phone, city, and default regional language.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import get_clinic_profile
from src.continuum.audit import log_action
from app.components.style import apply_theme

st.set_page_config(page_title="Clinic Setup | Continuum", page_icon="🏥", layout="wide")
apply_theme()

st.title("Clinic Profile & OPD Configuration")
st.caption("Configure hospital identity, treating diabetologist, and contact numbers. Seamless zero-code deployment to any OPD.")

Session = get_session_factory()

with Session() as db:
    profile = get_clinic_profile(db)

    if not profile.is_configured:
        st.warning(
            "⚠️ **Clinic profile is currently unconfigured.** "
            "Continuum is using neutral demo placeholders. Save your clinic details below to activate."
        )
    else:
        st.success(f"✓ **Active Clinic Profile:** {profile.clinic_name} ({profile.clinic_city}) &bull; Consultant: {profile.doctor_name}")

    st.markdown("---")

    col_form, col_preview = st.columns([3, 2])

    with col_form:
        st.subheader("Hospital & Clinician Credentials")

        with st.form("clinic_setup_form"):
            c_name = st.text_input(
                "Hospital / Clinic Name",
                value=profile.clinic_name if profile.clinic_name != "Continuum Demo Clinic" else "",
                placeholder="e.g. Ramraksha Hospital, City Care Clinic"
            )

            d_name = st.text_input(
                "Consultant / Treating Diabetologist",
                value=profile.doctor_name if profile.doctor_name != "Dr. [Name]" else "",
                placeholder="e.g. Dr. Ashwin Sadavarte"
            )

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                c_phone = st.text_input(
                    "Clinic / OPD Desk Mobile (for call-backs)",
                    value=profile.clinic_phone if profile.clinic_phone != "+91 90000 00000" else "",
                    placeholder="e.g. +91 98765 43210"
                )
            with col_p2:
                c_city = st.text_input(
                    "City / District",
                    value=profile.clinic_city,
                    placeholder="e.g. Akola, Maharashtra"
                )

            lang_options = ["mr", "hi", "en"]
            curr_lang = profile.default_language if profile.default_language in lang_options else "mr"
            d_lang = st.selectbox(
                "Default Regional Outreach Language",
                options=lang_options,
                index=lang_options.index(curr_lang),
                format_func=lambda x: {"mr": "मराठी (Marathi)", "hi": "हिंदी (Hindi)", "en": "English"}[x]
            )

            c_staff = st.text_input("Configured By (Staff Name / ID)", value="Administrator / Desk")

            submit_btn = st.form_submit_button("Save & Activate Clinic Profile", type="primary")

            if submit_btn:
                profile.clinic_name = c_name.strip() or "Continuum Demo Clinic"
                profile.doctor_name = d_name.strip() or "Dr. [Name]"
                profile.clinic_phone = c_phone.strip() or "+91 90000 00000"
                profile.clinic_city = c_city.strip() or "Akola"
                profile.default_language = d_lang
                profile.is_configured = bool(c_name.strip() and d_name.strip())

                log_action(
                    db,
                    action="CLINIC_PROFILE_CONFIGURED",
                    entity_type="ClinicProfile",
                    entity_id=str(profile.id),
                    user=c_staff,
                    details={
                        "clinic_name": profile.clinic_name,
                        "doctor_name": profile.doctor_name,
                        "clinic_phone": profile.clinic_phone,
                        "is_configured": profile.is_configured
                    }
                )
                db.commit()
                st.success("Clinic Profile saved! All outreach drafts and templates have been dynamically updated.")
                st.rerun()

        # Reset button
        if profile.is_configured:
            if st.button("Reset to Neutral Demo Placeholders"):
                profile.clinic_name = "Continuum Demo Clinic"
                profile.doctor_name = "Dr. [Name]"
                profile.clinic_phone = "+91 90000 00000"
                profile.clinic_city = "Akola"
                profile.is_configured = False
                db.commit()
                st.info("Reset to neutral demo profile.")
                st.rerun()

    with col_preview:
        st.subheader("Live Dynamic Outreach Preview")
        st.caption("How your clinic identity appears inside WhatsApp messages and call scripts:")

        st.markdown(
            f"""
            <div style="background: #eef2ff; border-left: 4px solid #6366f1; padding: 16px; border-radius: 6px;">
                <div style="font-weight: bold; color: #3730a3; margin-bottom: 8px;">
                    WhatsApp Notice Header:
                </div>
                <div style="font-family: monospace; font-size: 0.9rem; background: white; padding: 12px; border-radius: 4px; color: #1e1b4b;">
                    "सस्नेह नमस्कार श्री. गजानन जी. आम्ही <b>{profile.clinic_name}</b> तर्फे संपर्क साधत आहोत. आपले <b>{profile.doctor_name}</b> यांच्याकडील नियमित मधुमेह फॉलो-अप प्रलंबित आहे... संपर्क: <b>{profile.clinic_phone}</b>"
                </div>
                <div style="margin-top: 12px; font-size: 0.85rem; color: #4338ca;">
                    ✓ Status: <b>{'Configured (Production Mode)' if profile.is_configured else 'Demo / Placeholder Mode'}</b><br>
                    ✓ City: <b>{profile.clinic_city}</b><br>
                    ✓ Default Language: <b>{profile.default_language.upper()}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
