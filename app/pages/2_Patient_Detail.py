"""
Page 2: Longitudinal 360-Degree Patient Detail & Clinical Timeline.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import Patient, Visit, Prescription, Episode, OutreachLog, AuditLog
from app.components.patient_card import render_patient_card

st.set_page_config(page_title="Patient 360 | Continuum", page_icon="👤", layout="wide")

st.title("👤 Patient 360° Longitudinal View")
st.caption("Complete clinical consultation timeline, prescription forecasts, continuum episodes, and communication logs.")

Session = get_session_factory()

with Session() as db:
    patients = db.query(Patient).order_by(Patient.name).all()
    if not patients:
        st.warning("No patients found in database. Ingest clinical records first.")
        st.stop()

    patient_options = {f"{p.name} ({p.uh_id}) - {p.phone}": p.id for p in patients}
    selected_label = st.selectbox("Select Patient to Inspect", options=list(patient_options.keys()))
    selected_patient_id = patient_options[selected_label]

    patient = db.query(Patient).filter(Patient.id == selected_patient_id).first()
    if not patient:
        st.error("Patient not found.")
        st.stop()

    consent = patient.consent
    patient_dict = {
        "name": patient.name,
        "uh_id": patient.uh_id,
        "phone": patient.phone,
        "gender": patient.gender,
        "age": patient.age,
        "kin_name": patient.kin_name,
        "kin_phone": patient.kin_phone,
        "kin_relation": patient.kin_relation,
        "outreach_consent": not consent.opt_out if consent else True
    }

    render_patient_card(patient_dict)

    # Tabs for comprehensive view
    t_visits, t_rxs, t_episodes, t_outreach, t_audit = st.tabs([
        "🩺 Consultation Visits",
        "💊 Prescriptions & Refills",
        "⚡ Care Continuum Episodes",
        "💬 Outreach History",
        "📜 Audit Trail"
    ])

    with t_visits:
        st.subheader("Consultation History")
        visits = db.query(Visit).filter(Visit.patient_id == patient.id).order_by(Visit.visit_date.desc()).all()
        if not visits:
            st.info("No consultation records found.")
        else:
            for v in visits:
                with st.container():
                    st.markdown(
                        f"""
                        <div style="background: white; border-left: 4px solid #0284c7; padding: 12px; margin-bottom: 10px; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                            <div style="display: flex; justify-content: space-between;">
                                <strong>Consultation Date: {v.visit_date} (OPD #{v.opd_id or 'N/A'})</strong>
                                <span style="color: #64748b;">{v.doctor_name} ({v.department})</span>
                            </div>
                            <div style="margin-top: 6px;"><strong>Clinical Impression:</strong> {v.diagnosis_raw or 'None recorded'}</div>
                            <div style="margin-top: 4px; color: #0369a1;"><strong>Scheduled Next Review:</strong> {v.next_visit_due_date or 'None Scheduled'}</div>
                            <div style="margin-top: 4px; font-size: 0.8rem; color: #059669;">
                                {'✓ Chronic Diabetes Mellitus' if v.is_diabetes_cohort else 'Non-diabetic consultation'}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

    with t_rxs:
        st.subheader("Prescriptions & Refill Exhaustion Dates")
        prescriptions = db.query(Prescription).filter(Prescription.patient_id == patient.id).order_by(Prescription.start_date.desc()).all()
        if not prescriptions:
            st.info("No prescriptions on file.")
        else:
            rx_table = []
            for rx in prescriptions:
                rx_table.append({
                    "Medication": rx.medication_name,
                    "Dose Pattern": rx.raw_dose,
                    "Daily Rate": rx.frequency_per_day,
                    "Dispensed Qty": rx.quantity,
                    "Supply Days": rx.days_supply,
                    "Prescription Date": rx.start_date,
                    "Refill Due Date": rx.refill_due_date
                })
            st.dataframe(rx_table, use_container_width=True)

    with t_episodes:
        st.subheader("Care Continuum Episodes")
        episodes = db.query(Episode).filter(Episode.patient_id == patient.id).order_by(Episode.opened_date.desc()).all()
        if not episodes:
            st.info("No continuum episodes opened for this patient.")
        else:
            ep_table = []
            for ep in episodes:
                ep_table.append({
                    "Episode ID": ep.id,
                    "Reason": ep.reason,
                    "Status": ep.status,
                    "Days Overdue": ep.max_overdue_days,
                    "Earliest Drug Exhausted": ep.first_drug_exhausted or "-",
                    "Follow-up Overdue Days": ep.followup_overdue_days,
                    "Refill Overdue Days": ep.refill_overdue_days,
                    "Refill Only?": "YES" if ep.is_refill_only else "NO",
                    "Promised Date": ep.promised_date or "-"
                })
            st.dataframe(ep_table, use_container_width=True)

    with t_outreach:
        st.subheader("Outreach Logs")
        logs = db.query(OutreachLog).filter(OutreachLog.patient_id == patient.id).order_by(OutreachLog.timestamp.desc()).all()
        if not logs:
            st.info("No messages drafted or sent yet.")
        else:
            for log in logs:
                st.markdown(
                    f"""
                    <div style="background: #f1f5f9; padding: 12px; border-radius: 8px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #475569;">
                            <span>{log.timestamp} &bull; Channel: {log.channel} &bull; To: {log.recipient_type} ({log.recipient_phone})</span>
                            <span style="font-weight: bold; color: {'#16a34a' if log.status == 'SENT' else '#0284c7'};">{log.status}</span>
                        </div>
                        <div style="margin-top: 8px; font-size: 0.9rem;">{log.message_body}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    with t_audit:
        st.subheader("Patient Audit History")
        audit_records = db.query(AuditLog).filter(
            AuditLog.entity_id == str(patient.id)
        ).order_by(AuditLog.timestamp.desc()).limit(20).all()
        
        if not audit_records:
            st.info("No audit logs specifically tagged for this patient ID.")
        else:
            audit_data = []
            for a in audit_records:
                audit_data.append({
                    "Timestamp": a.timestamp,
                    "Actor": a.user_or_system,
                    "Action": a.action,
                    "Details": a.details_json
                })
            st.dataframe(audit_data, use_container_width=True)
