"""
Unit tests for token-authenticated patient portal and coordinator inbox messaging.
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import (
    Patient,
    PatientAccessToken,
    PatientMessage,
    issue_patient_token,
    resolve_patient_token,
)


def test_patient_token_lifecycle():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        # Create test patient
        patient = Patient(
            uh_id="PORTAL-001",
            name="Rajendra Deshmukh",
            phone="919822112233",
            gender="Male",
            age=61,
        )
        db.add(patient)
        db.commit()

        # 1. Issue valid token
        tok = issue_patient_token(db, patient.id, days_valid=30)
        assert tok.token is not None
        assert len(tok.token) >= 24

        # Resolve valid token
        resolved = resolve_patient_token(db, tok.token)
        assert resolved is not None
        assert resolved.id == patient.id
        assert resolved.uh_id == "PORTAL-001"

        # 2. Non-existent token
        assert resolve_patient_token(db, "non_existent_token_xyz") is None

        # 3. Revoked token
        tok.revoked = True
        db.commit()
        assert resolve_patient_token(db, tok.token) is None

        # 4. Expired token
        tok_expired = PatientAccessToken(
            patient_id=patient.id,
            token="expired_token_123",
            expires_at=datetime.utcnow() - timedelta(days=1),
            revoked=False,
        )
        db.add(tok_expired)
        db.commit()
        assert resolve_patient_token(db, "expired_token_123") is None


def test_patient_message_handling():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        patient = Patient(
            uh_id="PORTAL-002",
            name="Sunita Patil",
            phone="919822445566",
            gender="Female",
            age=55,
        )
        db.add(patient)
        db.commit()

        # 1. Patient sends reply
        msg = PatientMessage(
            patient_id=patient.id,
            direction="IN",
            category="APPOINTMENT_REPLY",
            body="I will come for my check-up — I can come on Saturday morning",
        )
        db.add(msg)
        db.commit()

        # Query unread inbox
        unread = (
            db.query(PatientMessage)
            .filter(PatientMessage.direction == "IN", PatientMessage.read_at.is_(None))
            .all()
        )
        assert len(unread) == 1
        assert unread[0].body == "I will come for my check-up — I can come on Saturday morning"

        # 2. Coordinator marks handled
        unread[0].read_at = datetime.utcnow()
        unread[0].handled_by = "care_coordinator"
        db.commit()

        # Verify no unread remaining
        remaining = (
            db.query(PatientMessage)
            .filter(PatientMessage.direction == "IN", PatientMessage.read_at.is_(None))
            .all()
        )
        assert len(remaining) == 0


def test_patient_portal_and_inbox_audit():
    from src.continuum.audit import log_action
    from src.continuum.models import AuditLog

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        patient = Patient(
            uh_id="PORTAL-003",
            name="Vikas Shinde",
            phone="919822778899",
            gender="Male",
            age=49,
        )
        db.add(patient)
        db.commit()

        # 1. Patient reply audit
        log_action(
            db,
            action="PATIENT_PORTAL_REPLY",
            entity_type="Patient",
            entity_id=str(patient.id),
            user=f"patient:{patient.uh_id}",
            details={"category": "APPOINTMENT_REPLY"},
        )
        # 2. Patient upload audit
        log_action(
            db,
            action="PATIENT_PORTAL_UPLOAD",
            entity_type="Patient",
            entity_id=str(patient.id),
            user=f"patient:{patient.uh_id}",
            details={"category": "REFILL_PROOF", "filename": "rx.jpg"},
        )
        # 3. Coordinator handled audit
        log_action(
            db,
            action="PATIENT_MESSAGE_HANDLED",
            entity_type="PatientMessage",
            entity_id="1",
            user="care_coordinator",
            details={"patient_id": patient.id, "category": "APPOINTMENT_REPLY"},
        )
        # 4. Patient link issued audit with masked suffix
        log_action(
            db,
            action="PATIENT_LINK_ISSUED",
            entity_type="Patient",
            entity_id=str(patient.id),
            user="care_coordinator",
            details={"token_suffix": "abcdef"},
        )
        db.commit()

        logs = db.query(AuditLog).all()
        assert len(logs) == 4
        actions = [l.action for l in logs]
        assert "PATIENT_PORTAL_REPLY" in actions
        assert "PATIENT_PORTAL_UPLOAD" in actions
        assert "PATIENT_MESSAGE_HANDLED" in actions
        assert "PATIENT_LINK_ISSUED" in actions
        users = [l.user_or_system for l in logs]
        assert f"patient:{patient.uh_id}" in users
        assert "care_coordinator" in users

