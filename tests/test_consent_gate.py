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


def test_kin_escalation_candidates_only_after_direct_attempt(memory_db):
    """Verifies that newly detected episodes do NOT appear in the kin escalation queue."""
    from src.continuum.workflow.escalation import get_kin_escalation_candidates

    p = Patient(
        uh_id="TEST-004",
        name="Laxman Test",
        phone="+919822055555",
        kin_name="Archana Test",
        kin_phone="+919822066666",
        kin_relation="Spouse"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester")

    # Newly detected episode: patient has NOT been contacted yet
    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="detected",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_ep_ids = [c["episode_id"] for c in candidates]
    assert ep.id not in cand_ep_ids, "Newly detected episodes must not jump to kin escalation before direct contact is attempted"

    # Once coordinator marks them unreachable after trying to call:
    ep.status = "unreachable"
    memory_db.commit()

    candidates_after = get_kin_escalation_candidates(memory_db)
    cand_after_ids = [c["episode_id"] for c in candidates_after]
    assert ep.id in cand_after_ids, "Unreachable patient must now appear in the kin escalation queue"


def test_kin_escalation_template_sanitized():
    """Verifies that kin escalation template never reveals diabetes diagnosis to a relative."""
    from src.continuum.config import get_template

    tmpl = get_template("kin_escalation")
    for lang in ["en", "hi", "mr"]:
        lang_data = tmpl["languages"][lang]
        body = lang_data["body"]
        assert "diabetes" not in body.lower(), f"Kin escalation body in {lang} must not disclose diabetes diagnosis"
        assert "मधुमेह" not in body, f"Kin escalation body in {lang} must not disclose diabetes diagnosis"


def test_clinic_profile_configuration(memory_db):
    """Verifies that ClinicProfile dynamically updates outreach rendering."""
    from src.continuum.models import get_clinic_profile

    p = Patient(uh_id="TEST-005", name="Kavita Test", phone="+919822077777")
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

    # Initial profile is demo placeholder
    profile = get_clinic_profile(memory_db)
    assert profile.is_configured is False
    assert profile.clinic_name == "Continuum Demo Clinic"

    ok, _, payload = render_outreach_draft(memory_db, ep.id, recipient_type="PATIENT", override_language="en")
    assert ok is True
    assert "Continuum Demo Clinic" in payload["body"]

    # Configure custom hospital live
    profile.clinic_name = "Akola Specialty Diabetes Center"
    profile.doctor_name = "Dr. Ashwin Sadavarte"
    profile.clinic_phone = "+91 99887 76655"
    profile.is_configured = True
    memory_db.commit()

    ok2, _, payload2 = render_outreach_draft(memory_db, ep.id, recipient_type="PATIENT", override_language="en")
    assert ok2 is True
    assert "Akola Specialty Diabetes Center" in payload2["body"]
    assert "+91 99887 76655" in payload2["body"]

