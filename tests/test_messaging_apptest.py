"""
Integration tests for Streamlit pages and chat messaging handlers via AppTest.
Exercises patient message posting, clinic replies, urgent red-flag triage,
and cleans up test records to preserve demo database state.
"""

from __future__ import annotations
from streamlit.testing.v1 import AppTest
from src.continuum.config import get_base_dir
from src.continuum.db import get_session_factory
from src.continuum.models import Patient, PatientMessage, AuditLog, PatientAccessToken, issue_patient_token


def test_apptest_pages_and_handlers():
    base_dir = get_base_dir()
    Session = get_session_factory()
    created_msg_ids = []
    created_audit_ids = []
    created_token_ids = []

    pages = [
        "app/Home.py",
        "app/pages/0_Clinic_Setup.py",
        "app/pages/1_Worklist.py",
        "app/pages/2_Patient_Detail.py",
        "app/pages/3_Duplicate_Review.py",
        "app/pages/4_Document_Verify.py",
        "app/pages/5_Escalation_Queue.py",
        "app/pages/6_Consent.py",
        "app/pages/7_Metrics.py",
        "app/pages/8_Audit_Log.py",
        "app/pages/9_Inbox.py",
        "app/pages/90_My_Care.py",
    ]

    try:
        with Session() as db:
            patient = db.query(Patient).first()
            if not patient:
                return
            patient_id = patient.id
            uh_id = patient.uh_id
            tok = issue_patient_token(db, patient_id=patient_id, days_valid=1)
            created_token_ids.append(tok.id)
            token_str = tok.token

        # Render all 12 pages
        for p in pages:
            at = AppTest.from_file(str(base_dir / p), default_timeout=30)
            if "90_My_Care.py" in p:
                at.query_params["t"] = token_str
            at.run()
            assert len(at.exception) == 0, f"Exception rendering {p}: {at.exception}"

        # Exercise Patient Side post message (urgent red flag)
        at_pt = AppTest.from_file(str(base_dir / "app/pages/90_My_Care.py"), default_timeout=30)
        at_pt.query_params["t"] = token_str
        at_pt.run()
        assert len(at_pt.chat_input) > 0
        at_pt.chat_input[0].set_value("Severe chest pain and breathless").run()
        assert len(at_pt.exception) == 0

        with Session() as db:
            in_msg = (
                db.query(PatientMessage)
                .filter(PatientMessage.patient_id == patient_id, PatientMessage.direction == "IN")
                .order_by(PatientMessage.id.desc())
                .first()
            )
            assert in_msg is not None
            created_msg_ids.append(in_msg.id)
            assert in_msg.urgent_flagged is True
            pt_audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "PATIENT_CHAT_MESSAGE_RECEIVED", AuditLog.entity_id == str(in_msg.id))
                .first()
            )
            assert pt_audit is not None
            created_audit_ids.append(pt_audit.id)

        # Exercise Clinic Side reply
        at_clinic = AppTest.from_file(str(base_dir / "app/pages/9_Inbox.py"), default_timeout=30)
        at_clinic.session_state["inbox_patient_id"] = patient_id
        at_clinic.run()
        assert len(at_clinic.chat_input) > 0
        at_clinic.chat_input[0].set_value("Call 108 immediately").run()
        assert len(at_clinic.exception) == 0

        with Session() as db:
            out_msg = (
                db.query(PatientMessage)
                .filter(PatientMessage.patient_id == patient_id, PatientMessage.direction == "OUT")
                .order_by(PatientMessage.id.desc())
                .first()
            )
            assert out_msg is not None
            created_msg_ids.append(out_msg.id)
            assert out_msg.urgent_flagged is False
            clinic_audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "CLINIC_CHAT_MESSAGE_SENT", AuditLog.entity_id == str(out_msg.id))
                .first()
            )
            assert clinic_audit is not None
            created_audit_ids.append(clinic_audit.id)

            read_audits = (
                db.query(AuditLog)
                .filter(AuditLog.action == "PATIENT_THREAD_READ", AuditLog.entity_id == str(patient_id))
                .all()
            )
            for ra in read_audits:
                created_audit_ids.append(ra.id)

    finally:
        with Session() as db:
            if created_msg_ids:
                db.query(PatientMessage).filter(PatientMessage.id.in_(created_msg_ids)).delete(synchronize_session=False)
            if created_audit_ids:
                db.query(AuditLog).filter(AuditLog.id.in_(created_audit_ids)).delete(synchronize_session=False)
            if created_token_ids:
                db.query(PatientAccessToken).filter(PatientAccessToken.id.in_(created_token_ids)).delete(synchronize_session=False)
            db.commit()
