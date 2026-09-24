"""
AppTest verification script for Continuum:
1. Loops over all 12 pages and confirms zero unhandled exceptions.
2. Exercises handlers:
   - Patient side (90_My_Care.py): posts an urgent message ("Chest pain and breathlessness").
   - Clinic side (9_Inbox.py): coordinator replies ("Please call 108 immediately").
3. Asserts:
   - Both rows exist in patient_messages with correct directions (IN, OUT).
   - Urgent keyword sets urgent_flagged=True for patient message.
   - An audit row was written for each action.
4. Cleans up any test rows so demo database remains pristine.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from streamlit.testing.v1 import AppTest
from src.continuum.db import get_session_factory
from src.continuum.models import Patient, PatientMessage, AuditLog, PatientAccessToken, issue_patient_token

PAGES = [
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

def verify_all_pages_render(valid_token: str):
    print("=" * 60)
    print("STEP 8.1: Verifying AppTest rendering across all 12 pages...")
    print("=" * 60)
    for p in PAGES:
        at = AppTest.from_file(str(ROOT_DIR / p), default_timeout=30)
        if "90_My_Care.py" in p:
            at.query_params["t"] = valid_token
        at.run()
        exceptions = [e for e in at.exception]
        if exceptions:
            print(f"FAILED on page: {p}")
            for e in exceptions:
                print(f"  Exception: {e.value} (message: {e.message})")
            raise RuntimeError(f"Rendering failed on {p}")
        print(f"  [PASS] {p}")
    print("[SUCCESS] All 12 pages rendered without error.")

def verify_handlers():
    print("=" * 60)
    print("STEP 8.2: Exercising messaging handlers via AppTest...")
    print("=" * 60)
    Session = get_session_factory()
    created_msg_ids = []
    created_audit_ids = []
    created_token_ids = []

    try:
        with Session() as db:
            patient = db.query(Patient).first()
            assert patient is not None, "No patient found in database"
            patient_id = patient.id
            uh_id = patient.uh_id

            # Issue temporary token
            tok = issue_patient_token(db, patient_id=patient_id, days_valid=1)
            created_token_ids.append(tok.id)
            token_str = tok.token
            print(f"Using patient: {patient.name} ({uh_id}), token: {tok.token[-6:]}")

        # 1. Render all pages
        verify_all_pages_render(token_str)

        # 2. Patient side: post urgent message via AppTest
        print("\nExercising Patient Side (90_My_Care.py)...")
        at_pt = AppTest.from_file(str(ROOT_DIR / "app/pages/90_My_Care.py"), default_timeout=30)
        at_pt.query_params["t"] = token_str
        at_pt.run()
        assert len(at_pt.exception) == 0, f"Exceptions on patient page: {at_pt.exception}"
        
        # Verify chat_input exists and send urgent message
        assert len(at_pt.chat_input) > 0, "No chat_input found on patient page"
        urgent_text = "I am having severe chest pain and breathless since morning"
        at_pt.chat_input[0].set_value(urgent_text).run()
        assert len(at_pt.exception) == 0, f"Exceptions after patient chat_input: {at_pt.exception}"

        # Check DB for patient message
        with Session() as db:
            in_msg = (
                db.query(PatientMessage)
                .filter(PatientMessage.patient_id == patient_id, PatientMessage.direction == "IN")
                .order_by(PatientMessage.id.desc())
                .first()
            )
            assert in_msg is not None, "Patient message not saved to database!"
            created_msg_ids.append(in_msg.id)
            assert in_msg.body == urgent_text
            assert in_msg.urgent_flagged is True, "urgent_flagged should be True for 'chest pain'!"
            print(f"  [PASS] Inbound message saved: ID={in_msg.id}, urgent_flagged={in_msg.urgent_flagged}")

            # Check audit row
            pt_audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "PATIENT_CHAT_MESSAGE_RECEIVED", AuditLog.entity_id == str(in_msg.id))
                .first()
            )
            assert pt_audit is not None, "Audit row for patient message not found!"
            created_audit_ids.append(pt_audit.id)
            assert pt_audit.user_or_system == f"patient:{uh_id}"
            print(f"  [PASS] Audit row verified: action={pt_audit.action}, user={pt_audit.user_or_system}")

        # 3. Clinic side: reply via 9_Inbox.py
        print("\nExercising Clinic Side (9_Inbox.py)...")
        at_clinic = AppTest.from_file(str(ROOT_DIR / "app/pages/9_Inbox.py"), default_timeout=30)
        at_clinic.session_state["inbox_patient_id"] = patient_id
        at_clinic.run()
        assert len(at_clinic.exception) == 0, f"Exceptions on inbox page: {at_clinic.exception}"

        assert len(at_clinic.chat_input) > 0, "No chat_input found on clinic inbox page"
        reply_text = "Please call 108 immediately or visit the emergency room."
        at_clinic.chat_input[0].set_value(reply_text).run()
        assert len(at_clinic.exception) == 0, f"Exceptions after clinic reply: {at_clinic.exception}"

        # Check DB for clinic reply
        with Session() as db:
            out_msg = (
                db.query(PatientMessage)
                .filter(PatientMessage.patient_id == patient_id, PatientMessage.direction == "OUT")
                .order_by(PatientMessage.id.desc())
                .first()
            )
            assert out_msg is not None, "Clinic reply not saved to database!"
            created_msg_ids.append(out_msg.id)
            assert out_msg.body == reply_text
            assert out_msg.urgent_flagged is False
            print(f"  [PASS] Outbound reply saved: ID={out_msg.id}, urgent_flagged={out_msg.urgent_flagged}")

            # Check clinic audit row
            clinic_audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "CLINIC_CHAT_MESSAGE_SENT", AuditLog.entity_id == str(out_msg.id))
                .first()
            )
            assert clinic_audit is not None, "Audit row for clinic message not found!"
            created_audit_ids.append(clinic_audit.id)
            assert clinic_audit.user_or_system == "care_coordinator"
            print(f"  [PASS] Audit row verified: action={clinic_audit.action}, user={clinic_audit.user_or_system}")

            # Also check mark_thread_read audit if generated
            read_audits = (
                db.query(AuditLog)
                .filter(AuditLog.action == "PATIENT_THREAD_READ", AuditLog.entity_id == str(patient_id))
                .all()
            )
            for ra in read_audits:
                created_audit_ids.append(ra.id)

    finally:
        print("\nCleaning up test rows from database...")
        with Session() as db:
            if created_msg_ids:
                db.query(PatientMessage).filter(PatientMessage.id.in_(created_msg_ids)).delete(synchronize_session=False)
            if created_audit_ids:
                db.query(AuditLog).filter(AuditLog.id.in_(created_audit_ids)).delete(synchronize_session=False)
            if created_token_ids:
                db.query(PatientAccessToken).filter(PatientAccessToken.id.in_(created_token_ids)).delete(synchronize_session=False)
            db.commit()
        print(f"Cleaned up {len(created_msg_ids)} messages, {len(created_audit_ids)} audits, {len(created_token_ids)} tokens.")

    print("\n" + "=" * 60)
    print("ALL APPTEST VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    verify_handlers()

