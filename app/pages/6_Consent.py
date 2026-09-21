"""
Page 6: Patient Opt-Out & Kin Escalation Consent Registry.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import Patient, Consent, AuditLog
from src.continuum.workflow.consent import set_patient_opt_out, set_kin_consent

st.set_page_config(page_title="Consent Registry | Continuum", page_icon="🔒", layout="wide")

st.title("🔒 Patient Opt-Out & Kin Consent Registry")
st.caption("Patient outreach is routine clinical care (permitted unless opted out). Kin contact is strictly gated by affirmative consent.")

Session = get_session_factory()

with Session() as db:
    patients = db.query(Patient).order_by(Patient.name).all()
    if not patients:
        st.warning("No patients in database.")
        st.stop()

    search_term = st.text_input("🔍 Search Patient to Update Preferences", placeholder="Search by name, UHID, or mobile...")
    
    filtered_patients = patients
    if search_term:
        st_clean = search_term.strip().lower()
        filtered_patients = [
            p for p in patients 
            if st_clean in p.name.lower() or st_clean in p.uh_id.lower() or st_clean in p.phone.lower()
        ]

    if not filtered_patients:
        st.info("No matching patients found.")
        st.stop()

    patient_select_map = {f"{p.name} ({p.uh_id}) - {p.phone}": p for p in filtered_patients}
    selected_label = st.selectbox("Select Patient", options=list(patient_select_map.keys()))
    patient = patient_select_map[selected_label]

    consent = patient.consent
    if not consent:
        consent = Consent(patient_id=patient.id, opt_out=False, kin_consent=False)

    st.markdown("---")
    st.subheader(f"Communication Preferences: {patient.name} ({patient.uh_id})")

    with st.form("consent_update_form"):
        col1, col2 = st.columns(2)

        with col1:
            opt_out_val = st.checkbox(
                "Patient Opt-Out (Do Not Contact Patient)",
                value=consent.opt_out,
                help="If checked, the patient has requested not to receive routine follow-up reminders."
            )
            kin_val = st.checkbox(
                "Affirmative Caregiver / Kin Consent Granted",
                value=consent.kin_consent,
                help="Authorizes clinic staff to contact primary relative if patient is unresponsive."
            )
            if patient.kin_name or patient.kin_phone:
                st.caption(f"Registered Kin: **{patient.kin_name or 'N/A'}** ({patient.kin_relation or 'Relative'}) &bull; `{patient.kin_phone or 'No phone'}`")
            if consent.kin_consent and consent.consented_kin_phone:
                st.caption(f"🔒 Bound Contact: **{consent.consented_kin_name or patient.kin_name}** (`{consent.consented_kin_phone}`)")

        with col2:
            lang_options = ["mr", "hi", "en"]
            curr_lang = consent.preferred_language if consent.preferred_language in lang_options else "mr"
            lang = st.selectbox(
                "Preferred Language",
                options=lang_options,
                index=lang_options.index(curr_lang),
                format_func=lambda x: {"mr": "मराठी (Marathi)", "hi": "हिंदी (Hindi)", "en": "English"}[x]
            )
            user_name = st.text_input("Coordinator / Staff ID", value="Dr. Ashwin Sadavarte / Desk")

        save_btn = st.form_submit_button("Save Preferences", type="primary")

        if save_btn:
            try:
                set_patient_opt_out(db, patient.id, opt_out=opt_out_val, user=user_name)
                set_kin_consent(
                    db,
                    patient.id,
                    kin_consent=kin_val,
                    user=user_name,
                    consented_kin_name=patient.kin_name if kin_val else None,
                    consented_kin_phone=patient.kin_phone if kin_val else None
                )
                db.refresh(patient)  # pick up the row consent helpers created
                if patient.consent:
                    patient.consent.preferred_language = lang
                db.commit()
                st.success("Communication preferences updated and logged in audit trail!")
                st.rerun()
            except Exception as e:
                st.error(f"Error updating preferences: {e}")

    st.markdown("---")
    st.subheader("Recent Preference Audit Trail")
    recent_logs = db.query(AuditLog).filter(
        AuditLog.action.in_(["PATIENT_OPT_OUT_CHANGED", "KIN_CONSENT_CHANGED"])
    ).order_by(AuditLog.timestamp.desc()).limit(10).all()

    if recent_logs:
        logs_table = []
        for l in recent_logs:
            logs_table.append({
                "Timestamp": l.timestamp,
                "Staff": l.user_or_system,
                "Action": l.action,
                "Details": l.details_json
            })
        st.dataframe(logs_table, use_container_width=True)
