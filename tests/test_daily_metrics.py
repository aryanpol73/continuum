"""
Unit tests for daily activity snapshot and series queries.
"""

from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import Patient, Visit, Episode, OutreachLog
from src.continuum.metrics.daily import get_daily_snapshot, get_daily_series


def test_daily_snapshot_and_series():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    target_day = date(2026, 9, 19)

    with Session() as db:
        # Create a patient
        patient = Patient(
            uh_id="DAILY-001",
            name="Test Daily Patient",
            phone="919876543210",
            gender="Female",
            age=52,
        )
        db.add(patient)
        db.flush()

        # 1. Expected visit today (next_visit_due_date = target_day)
        v_expected = Visit(
            patient_id=patient.id,
            visit_date=date(2026, 8, 19),
            doctor_name="Dr. Patni",
            next_visit_due_date=target_day,
        )
        db.add(v_expected)

        # 2. Attended visit today (visit_date = target_day)
        v_attended = Visit(
            patient_id=patient.id,
            visit_date=target_day,
            doctor_name="Dr. Patni",
            is_diabetes_cohort=True,
            next_visit_due_date=date(2026, 10, 19),
        )
        db.add(v_attended)

        # 3. Lapsed episode due today (is_refill_only = True)
        ep = Episode(
            patient_id=patient.id,
            reason="REFILL_GAP",
            status="detected",
            due_date=target_day,
            opened_date=target_day,
            max_overdue_days=7,
            is_refill_only=True,
        )
        db.add(ep)
        db.flush()

        # 4. Outreach log today
        log = OutreachLog(
            episode_id=ep.id,
            patient_id=patient.id,
            recipient_phone="919876543210",
            channel="WHATSAPP",
            message_body="Reminder message",
            status="SENT",
            timestamp=datetime(2026, 9, 19, 10, 30, 0),
        )
        db.add(log)
        db.commit()

        # Test snapshot
        snap = get_daily_snapshot(db, target_day)
        assert snap["date"] == target_day
        assert snap["expected_today"] == 1
        assert snap["attended_today"] == 1
        assert snap["no_show_today"] == 0
        assert snap["lapsed_today"] == 1
        assert snap["refill_lapsed_today"] == 1
        assert snap["outreach_today"] == 1
        assert snap["closed_today"] == 0

        # Test empty day snapshot
        empty_snap = get_daily_snapshot(db, date(2026, 1, 1))
        assert empty_snap["expected_today"] == 0
        assert empty_snap["attended_today"] == 0
        assert empty_snap["no_show_today"] == 0
        assert empty_snap["lapsed_today"] == 0
        assert empty_snap["refill_lapsed_today"] == 0
        assert empty_snap["outreach_today"] == 0
        assert empty_snap["closed_today"] == 0

        # Test series
        series = get_daily_series(db, end_day=target_day, days=7)
        assert len(series) == 7
        last_item = series[-1]
        assert last_item["date"] == target_day
        assert last_item["Lapsed"] == 1
        assert last_item["Refill-only"] == 1
        assert last_item["Attended"] == 1
