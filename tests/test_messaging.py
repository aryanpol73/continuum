"""
Unit tests for threaded patient-clinic messaging and urgent symptom triage.
"""

import io
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import Patient, PatientMessage, AuditLog
from src.continuum.messaging.triage import is_urgent, RED_FLAGS
from src.continuum.messaging.thread import (
    get_thread,
    post_message,
    mark_thread_read,
    get_thread_summaries,
)


def test_triage_classifier():
    # Positive cases
    assert is_urgent("Doctor, I have severe chest pain since morning") is True
    assert is_urgent("Feeling very breathless while walking") is True
    assert is_urgent("Patient fainted in the hall") is True
    assert is_urgent("Maza chhati madhe dukhata ahe") is True
    assert is_urgent("Shwas ghyayla tras hoto") is True
    assert is_urgent("Blood sugar very low today, felt dizzy") is True
    assert is_urgent("Patient had seizure fits") is True
    assert is_urgent("Bleeding from gums") is True

    # Negative cases
    assert is_urgent("I will come on Saturday for my follow up") is False
    assert is_urgent("Need an appointment date change") is False
    assert is_urgent("Have already taken my morning Metformin dose") is False
    assert is_urgent("Please confirm my pharmacy prescription refill") is False
    assert is_urgent("") is False
    assert is_urgent(None) is False


def test_messaging_thread_lifecycle():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        patient1 = Patient(
            uh_id="MSG-001",
            name="Rameshwar Tayade",
            phone="919822111222",
            gender="Male",
            age=58,
        )
        patient2 = Patient(
            uh_id="MSG-002",
            name="Sumanbai More",
            phone="919822333444",
            gender="Female",
            age=62,
        )
        db.add_all([patient1, patient2])
        db.commit()

        # 1. Patient 1 sends routine message
        msg1 = post_message(
            db,
            patient_id=patient1.id,
            direction="IN",
            body="Can I visit the clinic on Monday instead of Saturday?",
            topic="APPOINTMENT",
            author=f"patient:{patient1.uh_id}",
        )
        assert msg1.urgent_flagged is False
        assert msg1.topic == "APPOINTMENT"

        # 2. Clinic replies
        reply1 = post_message(
            db,
            patient_id=patient1.id,
            direction="OUT",
            body="Yes Rameshwar ji, Dr. is available Monday 9 AM to 1 PM.",
            topic="APPOINTMENT",
            author="care_coordinator",
        )
        assert reply1.urgent_flagged is False

        # 3. Patient 2 sends urgent message with attachment
        fake_file = io.BytesIO(b"%PDF-1.4 test prescription file")
        fake_file.name = "sugar_report.pdf"
        fake_file.type = "application/pdf"

        msg2 = post_message(
            db,
            patient_id=patient2.id,
            direction="IN",
            body="Feeling severe chest pain and breathless after medicine",
            topic="MEDICINES",
            uploaded_file=fake_file,
            author=f"patient:{patient2.uh_id}",
        )
        assert msg2.urgent_flagged is True
        assert msg2.attachment_name == "sugar_report.pdf"
        assert msg2.attachment_mime == "application/pdf"
        if msg2.attachment_path:
            import os
            try:
                os.unlink(msg2.attachment_path)
            except OSError:
                pass

        # 4. Verify thread order
        thread1 = get_thread(db, patient1.id)
        assert len(thread1) == 2
        assert thread1[0].id == msg1.id
        assert thread1[1].id == reply1.id

        # 5. Verify thread summaries (urgent pinned first)
        summaries = get_thread_summaries(db)
        assert len(summaries) == 2
        # Patient 2 has unread urgent message -> must be index 0
        assert summaries[0]["patient_id"] == patient2.id
        assert summaries[0]["has_urgent"] is True
        assert summaries[0]["unread_in_count"] == 1
        assert summaries[1]["patient_id"] == patient1.id
        assert summaries[1]["unread_in_count"] == 0

        # 6. Mark Patient 2 thread read
        read_count = mark_thread_read(db, patient2.id, reader="care_coordinator")
        assert read_count == 1

        summaries_after = get_thread_summaries(db)
        p2_sum = next(s for s in summaries_after if s["patient_id"] == patient2.id)
        assert p2_sum["unread_in_count"] == 0
        assert p2_sum["has_urgent"] is False

        # 7. Audit log verification
        audit_rows = db.query(AuditLog).all()
        actions = [a.action for a in audit_rows]
        assert "PATIENT_CHAT_MESSAGE_RECEIVED" in actions
        assert "CLINIC_CHAT_MESSAGE_SENT" in actions
        assert "PATIENT_THREAD_READ" in actions
        users = [a.user_or_system for a in audit_rows]
        assert f"patient:{patient1.uh_id}" in users
        assert "care_coordinator" in users


