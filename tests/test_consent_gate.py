"""
Consent governance security tests:
- Routine patient outreach is permitted by default (ordinary care communication) unless opt_out = YES.
- Kin escalation is strictly hard-blocked without explicit patient consent.
- Drafting is never blocked.
"""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.config import get_today
from src.continuum.models import Patient, Consent, Episode, Visit, OutreachLog, AuditLog
from src.continuum.workflow.states import EpisodeStatus
from src.continuum.workflow.consent import (
    is_patient_outreach_permitted, verify_kin_consent, set_patient_opt_out, set_kin_consent
)
from src.continuum.outreach.render import render_outreach_draft
from src.continuum.workflow.escalation import escalate_episode_to_kin, get_kin_escalation_candidates


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
    assert ep.status == EpisodeStatus.KIN_ESCALATED.value


def test_no_outreach_log_means_no_escalation(memory_db):
    """Verifies that an episode with no patient outreach log cannot be escalated to kin."""
    p = Patient(
        uh_id="TEST-ESC-1",
        name="Sunil Patil",
        phone="+919822011111",
        kin_name="Savita Patil",
        kin_phone="+919822022222",
        kin_relation="Spouse"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester")

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="contacted",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_ids = [c["episode_id"] for c in candidates]
    assert ep.id not in cand_ids, "Episodes without a PATIENT outreach log must not qualify for kin escalation"


def test_attempt_5_days_ago_means_no_escalation(memory_db):
    """Verifies that an outreach attempt made 5 days ago (< 10 day threshold) is skipped."""
    today = get_today()
    p = Patient(
        uh_id="TEST-ESC-2",
        name="Ramesh Deshmukh",
        phone="+919822033333",
        kin_name="Anita Deshmukh",
        kin_phone="+919822044444",
        kin_relation="Spouse"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester")

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="contacted",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.flush()

    # Attempt logged 5 days ago (less than 10 day threshold)
    log = OutreachLog(
        episode_id=ep.id,
        patient_id=p.id,
        recipient_type="PATIENT",
        recipient_phone=p.phone,
        channel="WHATSAPP",
        message_body="Reminder",
        status="SENT",
        timestamp=datetime.combine(today - timedelta(days=5), datetime.min.time())
    )
    memory_db.add(log)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_ids = [c["episode_id"] for c in candidates]
    assert ep.id not in cand_ids, "Patient outreach 5 days ago is within the 10-day waiting threshold and must not escalate"


def test_attempt_12_days_ago_with_consent_means_escalation(memory_db):
    """Verifies that an outreach attempt made 12 days ago (>= 10 days) with affirmative consent escalates successfully."""
    today = get_today()
    p = Patient(
        uh_id="TEST-ESC-3",
        name="Gajanan Wankhede",
        phone="+919822055555",
        kin_name="Mira Wankhede",
        kin_phone="+919822066666",
        kin_relation="Spouse"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester", consented_kin_name=p.kin_name, consented_kin_phone=p.kin_phone)

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="contacted",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.flush()

    # Attempt logged 12 days ago (>= 10 day threshold)
    log = OutreachLog(
        episode_id=ep.id,
        patient_id=p.id,
        recipient_type="PATIENT",
        recipient_phone=p.phone,
        channel="WHATSAPP",
        message_body="Reminder",
        status="SENT",
        timestamp=datetime.combine(today - timedelta(days=12), datetime.min.time())
    )
    memory_db.add(log)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_map = {c["episode_id"]: c for c in candidates}
    assert ep.id in cand_map, "Patient outreach 12 days ago must qualify for kin escalation queue"
    assert cand_map[ep.id]["kin_consent_allowed"] is True
    assert cand_map[ep.id]["days_since_patient_attempt"] == 12

    # Transition to kin_escalated
    ok, msg = escalate_episode_to_kin(memory_db, ep.id, user="tester")
    assert ok is True
    assert ep.status == EpisodeStatus.KIN_ESCALATED.value


def test_mismatched_kin_phone_is_blocked(memory_db):
    """Verifies that if patient's kin phone differs from consented kin phone, escalation is strictly blocked."""
    today = get_today()
    p = Patient(
        uh_id="TEST-ESC-4",
        name="Vijay Joshi",
        phone="+919822077777",
        kin_name="Anand Joshi",
        kin_phone="+919822088888",
        kin_relation="Brother"
    )
    memory_db.add(p)
    memory_db.flush()

    # Consent granted for a DIFFERENT phone (+919822099999)
    set_kin_consent(
        memory_db,
        p.id,
        kin_consent=True,
        user="tester",
        consented_kin_name="Anand Joshi",
        consented_kin_phone="+919822099999"
    )

    ep = Episode(
        patient_id=p.id,
        reason="REFILL_GAP",
        status="contacted",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.flush()

    log = OutreachLog(
        episode_id=ep.id,
        patient_id=p.id,
        recipient_type="PATIENT",
        recipient_phone=p.phone,
        channel="WHATSAPP",
        message_body="Reminder",
        status="SENT",
        timestamp=datetime.combine(today - timedelta(days=12), datetime.min.time())
    )
    memory_db.add(log)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_map = {c["episode_id"]: c for c in candidates}
    assert ep.id in cand_map
    assert cand_map[ep.id]["kin_consent_allowed"] is False
    assert cand_map[ep.id]["consent_reason"] == "contact changed since consent"

    ok, msg = escalate_episode_to_kin(memory_db, ep.id, user="tester")
    assert ok is False
    assert "contact changed since consent" in msg

    # Audit log check
    audit = (
        memory_db.query(AuditLog)
        .filter(AuditLog.action == "KIN_ESCALATION_BLOCKED", AuditLog.entity_id == str(ep.id))
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert "contact changed since consent" in audit.details_json


def test_kin_escalated_episodes_do_not_reappear_in_queue(memory_db):
    """Verifies that an episode once escalated to kin (status=kin_escalated) does not reappear in the queue."""
    today = get_today()
    p = Patient(
        uh_id="TEST-ESC-5",
        name="Nitin Kale",
        phone="+919822012121",
        kin_name="Sneha Kale",
        kin_phone="+919822034343",
        kin_relation="Daughter"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester", consented_kin_name=p.kin_name, consented_kin_phone=p.kin_phone)

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status=EpisodeStatus.KIN_ESCALATED.value,  # Already escalated
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.flush()

    log = OutreachLog(
        episode_id=ep.id,
        patient_id=p.id,
        recipient_type="PATIENT",
        recipient_phone=p.phone,
        channel="WHATSAPP",
        message_body="Reminder",
        status="SENT",
        timestamp=datetime.combine(today - timedelta(days=15), datetime.min.time())
    )
    memory_db.add(log)
    memory_db.commit()

    candidates = get_kin_escalation_candidates(memory_db)
    cand_ids = [c["episode_id"] for c in candidates]
    assert ep.id not in cand_ids, "Kin escalated episodes must not reappear in the candidate queue"


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


def test_missing_kin_phone_logs_accurate_reason(memory_db):
    """Verifies that if patient has no kin phone, escalation refuses with 'no number on file'."""
    p = Patient(
        uh_id="TEST-ESC-6",
        name="Santosh Shinde",
        phone="+919822088888",
        kin_name="Archana Shinde",
        kin_phone=None,  # Null / missing kin phone
        kin_relation="Spouse"
    )
    memory_db.add(p)
    memory_db.flush()

    set_kin_consent(memory_db, p.id, kin_consent=True, user="tester")

    ep = Episode(
        patient_id=p.id,
        reason="FOLLOWUP_OVERDUE",
        status="contacted",
        due_date=date(2026, 8, 1),
        opened_date=date(2026, 9, 19),
        max_overdue_days=45
    )
    memory_db.add(ep)
    memory_db.commit()

    ok, msg = escalate_episode_to_kin(memory_db, ep.id, user="tester")
    assert ok is False
    assert "No kin / caregiver contact number on file" in msg

    audit = (
        memory_db.query(AuditLog)
        .filter(AuditLog.action == "KIN_ESCALATION_BLOCKED", AuditLog.entity_id == str(ep.id))
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert "no number on file" in audit.details_json
    assert "contact changed since consent" not in audit.details_json


