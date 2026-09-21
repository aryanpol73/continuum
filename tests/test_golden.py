"""
End-to-end golden flow regression test for the Continuum care platform.
"""

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.continuum.db import Base
from src.continuum.models import Patient, Consent, Visit, Prescription, Episode, AuditLog
from src.continuum.engine.cohort import update_all_visits_cohort
from src.continuum.engine.dosing import update_all_prescriptions_dosing
from src.continuum.workflow.episodes import generate_episodes_from_rules, transition_episode
from src.continuum.engine.worklist import get_overdue_worklist
from src.continuum.outreach.render import render_outreach_draft


def test_golden_e2e_flow():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    
    with Session() as db:
        # 1. Create Patient
        p = Patient(
            uh_id="GOLD-001",
            name="Vinod Kalamkar",
            phone="+919822099999",
            gender="Male",
            age=58,
            kin_name="Shobha Kalamkar",
            kin_phone="+919822088888",
            kin_relation="Spouse"
        )
        db.add(p)
        db.flush()

        # 2. Record Consent (opt_out=False, kin_consent=True)
        c = Consent(
            patient_id=p.id,
            opt_out=False,
            kin_consent=True,
            preferred_language="mr"
        )
        db.add(c)

        # 3. Create Visit with Diabetes impression and overdue next review
        v = Visit(
            patient_id=p.id,
            opd_id="OPD-101",
            visit_date=date(2026, 7, 10),
            doctor_name="Dr. Ashwin Sadavarte",
            department="Diabetology",
            diagnosis_raw="T2DM with Essential Hypertension",
            next_visit_due_date=date(2026, 8, 10)  # > 7 days overdue as of 2026-09-19
        )
        db.add(v)
        db.flush()

        # 4. Create Prescription: WALAPHAGE G2 (dose 1-0-1 = 2/day, qty 60 = 30 days)
        rx = Prescription(
            visit_id=v.id,
            patient_id=p.id,
            opd_id="OPD-101",
            medication_name="WALAPHAGE G2",
            raw_dose="1-0-1",
            quantity=60,
            start_date=date(2026, 7, 10),
            refill_due_date=date(2026, 7, 10)
        )
        db.add(rx)
        db.commit()

        # 5. Execute Clinical Engine
        diabetic_count = update_all_visits_cohort(db)
        assert diabetic_count == 1
        db.refresh(v)
        assert v.is_diabetes_cohort is True

        dosing_count = update_all_prescriptions_dosing(db)
        assert dosing_count == 1
        db.refresh(rx)
        assert rx.frequency_per_day == 2.0
        assert rx.days_supply == 30
        assert rx.refill_due_date == date(2026, 8, 9)

        # 6. Generate Episodes (Anchor date: 2026-09-19)
        sim_today = date(2026, 9, 19)
        stats = generate_episodes_from_rules(db, anchor_date=sim_today, user="test_runner")
        assert stats["episodes_created"] == 1

        # 7. Check Overdue Worklist
        worklist = get_overdue_worklist(db)
        assert len(worklist) == 1
        assert worklist[0]["uh_id"] == "GOLD-001"
        assert worklist[0]["max_overdue_days"] > 0
        assert worklist[0]["first_drug_exhausted"] == "WALAPHAGE G2"

        # 8. Render Outreach Draft
        ep = db.query(Episode).filter(Episode.patient_id == p.id).first()
        ok, msg, payload = render_outreach_draft(db, ep.id, recipient_type="PATIENT", user="test_runner")
        assert ok is True
        assert "Vinod Kalamkar" in payload["body"]
        assert "Dr. Ashwin Sadavarte" in payload["body"]
        assert payload["is_dispatch_allowed"] is True
        # Verify WhatsApp URL format: 91XXXXXXXXXX (no plus sign)
        assert "wa.me/919822099999" in payload["whatsapp_url"]

        # 9. Advance Workflow Status: detected -> contacted -> promised -> returned
        transition_episode(db, ep.id, new_status="contacted", user="test_runner")
        db.refresh(ep)
        assert ep.status == "contacted"

        transition_episode(db, ep.id, new_status="promised", user="test_runner", reason="Patient confirmed Thursday visit")
        db.refresh(ep)
        assert ep.status == "promised"

        transition_episode(db, ep.id, new_status="returned", user="test_runner", reason="Attended clinic consultation")
        db.refresh(ep)
        assert ep.status == "returned"
        assert ep.closed_date is not None

        # 10. Audit Log Verification
        logs = db.query(AuditLog).all()
        assert len(logs) >= 4
