"""
Consent governance security tests:
- Routine patient outreach is permitted by default (ordinary care communication) unless opt_out = YES.
- Kin escalation is strictly hard-blocked without explicit patient consent.
- Drafting is never blocked.
"""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import Patient, Consent, Episode, Visit
from src.continuum.workflow.consent import (
    is_patient_outreach_permitted, verify_kin_consent, set_patient_opt_out, set_kin_consent
)
from src.continuum.outreach.render import render_outreach_draft
from src.continuum.workflow.escalation import escalate_episode_to_kin


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_patient_outreach_permitted_by_default(memory_db):
    # Patient with NO prior consent record (day-one clinic ingestion)
    p = Patient(uh_id="TEST-001", name="Gajanan Test", phone="+919822011111")
    memory_db.add(p)
    memory_db.flush()

    ep = Episode(
        patient_id=p.id,
        reason="REFILL_GAP",
        status="detected",
        due_date=date(2026, 8, 15),
        opened_date=date(2026, 9, 19),
        max_overdue_days=30
    )
    memory_db.add(ep)
    memory_db.commit()

    # Routine outreach to patient is permitted
    allowed, reason = is_patient_outreach_permitted(memory_db, p.id)
    assert allowed is True

    # Drafting succeeds and dispatch is allowed
    ok, msg, payload = render_outreach_draft(memory_db, ep.id, recipient_type="PATIENT", user="tester")
    assert ok is True
    assert payload["is_dispatch_allowed"] is True


def test_patient_opt_out_enforcement(memory_db):
    p = Patient(uh_id="TEST-002", name="Sunil Test", phone="+919822022222")
    memory_db.add(p)
    memory_db.flush()

    # Patient explicitly opted out
    set_patient_opt_out(memory_db, p.id, opt_out=True, user="tester")

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="detected",
        due_date=date(2026, 8, 15),
        opened_date=date(2026, 9, 19),
        max_overdue_days=25
    )
    memory_db.add(ep)
    memory_db.commit()

    # Gate check reflects opt-out
    allowed, reason = is_patient_outreach_permitted(memory_db, p.id)
    assert allowed is False
    assert "OPT_OUT" in reason

    # Drafting is NOT blocked (coordinator can prepare script), but dispatch is disallowed
    ok, msg, payload = render_outreach_draft(memory_db, ep.id, recipient_type="PATIENT", user="tester")
    assert ok is True
    assert payload["is_dispatch_allowed"] is False
    assert "opt out" in payload["dispatch_warning"]


def test_kin_consent_hard_gate(memory_db):
    # Patient without kin consent
    p = Patient(
        uh_id="TEST-003",
        name="Ramesh Test",
        phone="+919822033333",
        kin_name="Vinod Test",
        kin_phone="+919822044444",
        kin_relation="Brother"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=False, user="tester")

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="contacted",
        due_date=date(2026, 8, 15),
        opened_date=date(2026, 9, 19),
        max_overdue_days=35
    )
    memory_db.add(ep)
    memory_db.commit()

    # Kin gate must return False
    kin_allowed, reason = verify_kin_consent(memory_db, p.id)
    assert kin_allowed is False
    assert "KIN_ESCALATION_UNAUTHORIZED" in reason

    # Kin escalation transition must be strictly blocked
    escalate_ok, msg = escalate_episode_to_kin(memory_db, ep.id, user="tester")
    assert escalate_ok is False
    assert "HARD GATE BLOCKED" in msg
    assert ep.status == "contacted"  # unchanged

    # Granting kin consent unblocks escalation
    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester")
    assert verify_kin_consent(memory_db, p.id)[0] is True
    
    escalate_ok2, _ = escalate_episode_to_kin(memory_db, ep.id, user="tester")
    assert escalate_ok2 is True
