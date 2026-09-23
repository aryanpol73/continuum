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
