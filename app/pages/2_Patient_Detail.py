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
from src.continuum.models import (
    Patient, Visit, Prescription, Episode, OutreachLog, AuditLog, UploadedReport,
    issue_patient_token
)
from src.continuum.config import get_portal_base_url
from src.continuum.audit import log_action
from src.continuum.engine.investigations import get_patient_missing_investigations
from app.components.patient_card import render_patient_card
from app.components.chat import render_chat
from app.components.style import apply_theme

st.set_page_config(page_title="Patient 360 | Continuum", page_icon="👤", layout="wide")
apply_theme()
from app.components.nav import render_sidebar, render_context_bar, require_clinic_setup
render_sidebar()
require_clinic_setup()

st.title("Patient 360° Longitudinal View")
st.caption("Complete clinical consultation timeline, prescription forecasts, continuum episodes, and communication logs.")
render_context_bar()

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

    col_link1, col_link2 = st.columns([1, 2])
    with col_link1:
        if st.button("🔗 Generate Patient Link", key=f"btn_gen_link_{patient.id}"):
            tok = issue_patient_token(db, patient.id)
            log_action(
                db,
                action="PATIENT_LINK_ISSUED",
                entity_type="Patient",
                entity_id=str(patient.id),
                user="care_coordinator",
                details={"token_suffix": tok.token[-6:]},
            )
            st.session_state[f"pat_token_{patient.id}"] = tok.token

    cur_tok = st.session_state.get(f"pat_token_{patient.id}")
    if cur_tok:
        portal_url = f"{get_portal_base_url()}/My_Care?t={cur_tok}"
        st.caption("Patient Portal Link (valid 30 days):")
        st.code(portal_url, language="text")

    # Tabs for comprehensive view
    t_visits, t_rxs, t_reports, t_episodes, t_outreach, t_messages, t_audit = st.tabs([
        "🩺 Consultation Visits",
        "💊 Prescriptions & Refills",
        "🔬 Investigations & Reports",
        "⚡ Care Continuum Episodes",
        "📢 Outreach History",
        "💬 Messages",
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
                    inv_markup = f"<div style='margin-top: 4px; color: #b45309;'><strong>Advised Investigations:</strong> {v.investigation_advice}</div>" if v.investigation_advice else ""
                    st.markdown(
                        f"""
                        <div style="background: white; border-left: 4px solid #0284c7; padding: 12px; margin-bottom: 10px; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                            <div style="display: flex; justify-content: space-between;">
                                <strong>Consultation Date: {v.visit_date} (OPD #{v.opd_id or 'N/A'})</strong>
                                <span style="color: #64748b;">{v.doctor_name} ({v.department})</span>
                            </div>
                            <div style="margin-top: 6px;"><strong>Clinical Impression:</strong> {v.diagnosis_raw or 'None recorded'}</div>
                            {inv_markup}
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

    with t_reports:
        st.subheader("Laboratory Investigations & Scanned Reports")
        
        # 1. Missing / Overdue Advised Tests
        missing_invs = get_patient_missing_investigations(db, patient.uh_id)
        if missing_invs:
            st.warning(f"⚠️ **{len(missing_invs)} Advised Investigations Missing Report (>45d Turnaround)**")
            missing_data = []
            for m in missing_invs:
                missing_data.append({
                    "Advised Test": m["test_name"],
                    "Date Advised": m["advised_date"],
                    "Days Pending": m["days_pending"],
                    "Turnaround Threshold": f"{m['turnaround_threshold_days']} days",
                    "Administrative Status": "REPORT PENDING"
                })
            st.dataframe(missing_data, use_container_width=True)
        else:
            st.success("✓ No overdue missing investigation reports for this patient.")

        st.markdown("---")
        # 2. Uploaded / Linked Reports
        st.markdown("#### Uploaded Diagnostic Reports & Documents")
        uploaded = db.query(UploadedReport).filter(UploadedReport.uh_id == patient.uh_id).order_by(UploadedReport.upload_date.desc()).all()
        if not uploaded:
            st.info("No scanned reports or lab PDFs uploaded for this UH_ID.")
        else:
            rep_data = []
            for r in uploaded:
                rep_data.append({
                    "Document File": r.file_name,
                    "Upload Date": r.upload_date,
                    "Label / Test": r.labelled_as or "Unlabelled Scan",
                    "Origin Lab": r.source
                })
            st.dataframe(rep_data, use_container_width=True)

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

    with t_messages:
        st.subheader("Patient Conversation Thread")
        render_chat(db, patient.id, viewer="clinic", key_prefix="pd")

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
