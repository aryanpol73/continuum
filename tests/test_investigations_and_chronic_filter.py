"""
Unit tests for chronic medication refill filtering and administrative investigation turnaround.
Verifies that:
1. Acute medications (MACBATE, NEXPRO) and courses < 14 days never contaminate the refill signal.
2. Missing investigation detection correctly identifies advised tests pending after 45 days.
"""

from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import Patient, Visit, Prescription, Episode, Consent, UploadedReport
from src.continuum.config import get_rules
from src.continuum.workflow.episodes import generate_episodes_from_rules
from src.continuum.engine.investigations import (
    parse_advised_tests,
    get_patient_missing_investigations,
    get_all_missing_investigations_summary
)


def get_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_acute_medication_refill_exclusion():
    """Verifies acute syrups and short courses do not trigger refill gaps."""
    db = get_test_db()
    anchor = date(2026, 9, 19)

    # Diabetic patient
    p = Patient(uh_id="UH_TEST_01", name="Test Acute", phone="9876543210")
    db.add(p)
    db.flush()

    c = Consent(patient_id=p.id, opt_out=False, kin_consent=False)
    db.add(c)

    # Visit 30 days ago with next review 60 days in future (follow-up NOT overdue)
    v = Visit(
        patient_id=p.id,
        opd_id="OPD_TEST_01",
        visit_date=anchor - timedelta(days=30),
        doctor_name="Dr. Ashwin Sadavarte",
        diagnosis_raw="T2DM DM-2",
        is_diabetes_cohort=True,
        followup_after_days=90,
        next_visit_due_date=anchor + timedelta(days=60)
    )
    db.add(v)
    db.flush()

    # Prescriptions:
    # 1. MACBATE 10 ML - acute liquid (qty 10, dose 1-1-1 = 3 days, would exhaust 27 days ago)
    # 2. NEXPRO RD 40 - acute PPI short course (qty 10, dose 1-0-0 = 10 days < 14 days min_supply)
    # 3. WALAPHAGE G2 - chronic diabetes (qty 60, dose 1-0-1 = 30 days supply, exhausts exactly today)
    rx1 = Prescription(
        visit_id=v.id, patient_id=p.id,
        medication_name="MACBATE 10 ML", raw_dose="1-1-1",
        quantity=10, start_date=v.visit_date, refill_due_date=v.visit_date
    )
    rx2 = Prescription(
        visit_id=v.id, patient_id=p.id,
        medication_name="NEXPRO RD 40", raw_dose="1-0-0",
        quantity=10, start_date=v.visit_date, refill_due_date=v.visit_date
    )
    rx3 = Prescription(
        visit_id=v.id, patient_id=p.id,
        medication_name="WALAPHAGE G2", raw_dose="1-0-1",
        quantity=60, start_date=v.visit_date, refill_due_date=v.visit_date
    )
    db.add_all([rx1, rx2, rx3])
    db.commit()

    stats = generate_episodes_from_rules(db, anchor_date=anchor)

    # Since WALAPHAGE had 30 days supply and grace period is 7 days, it is not yet overdue
    # (today - end_date = 0 <= 7 grace). MACBATE & NEXPRO must NOT cause an episode!
    ep = db.query(Episode).filter(Episode.patient_id == p.id).first()
    assert ep is None, "Acute drugs must not trigger an early false-positive refill gap"

    # Now simulate 10 days later: WALAPHAGE is now 3 days past 7-day grace period
    stats_later = generate_episodes_from_rules(db, anchor_date=anchor + timedelta(days=10))
    ep_later = db.query(Episode).filter(Episode.patient_id == p.id).first()
    assert ep_later is not None, "Chronic medication gap should now open an episode"
    assert ep_later.first_drug_exhausted == "WALAPHAGE G2", "First drug exhausted must be the chronic drug, never MACBATE"
    assert "MACBATE" not in ep_later.first_drug_exhausted
    assert "NEXPRO" not in ep_later.first_drug_exhausted


def test_administrative_missing_investigation():
    """Verifies tracking of advised investigations pending report after 45 days."""
    db = get_test_db()
    anchor = date(2026, 9, 19)

    p = Patient(uh_id="UH_INV_01", name="Test Inv", phone="9876543211")
    db.add(p)
    db.flush()

    # Visit 50 days ago with HbA1c and Serum Creatinine advised
    v = Visit(
        patient_id=p.id,
        opd_id="OPD_INV_01",
        visit_date=anchor - timedelta(days=50),
        doctor_name="Dr. Ashwin Sadavarte",
        diagnosis_raw="T2DM",
        investigation_advice="HbA1c S.CREAT",
        is_diabetes_cohort=True
    )
    db.add(v)
    db.commit()

    # Check parse_advised_tests
    parsed = parse_advised_tests("HbA1c S.CREAT")
    assert "HbA1c" in parsed
    assert "Serum Creatinine" in parsed

    # Initially, both are missing (>45 days, no uploaded report)
    missing = get_patient_missing_investigations(db, "UH_INV_01", anchor_date=anchor)
    assert len(missing) == 2
    missing_test_names = [m["test_name"] for m in missing]
    assert "HbA1c" in missing_test_names
    assert "Serum Creatinine" in missing_test_names

    # Upload only HbA1c report
    rep = UploadedReport(
        uh_id="UH_INV_01",
        file_name="UH_INV_01_HbA1c.jpg",
        upload_date=anchor - timedelta(days=40),
        labelled_as="HbA1c",
        source="In-house"
    )
    db.add(rep)
    db.commit()

    # Now only Serum Creatinine should be pending
    missing_after = get_patient_missing_investigations(db, "UH_INV_01", anchor_date=anchor)
    assert len(missing_after) == 1
    assert missing_after[0]["test_name"] == "Serum Creatinine"
