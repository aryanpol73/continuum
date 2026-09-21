"""
Continuum — Seed Demo State for Kin Escalation Queue.

Picks 4 episodes from the actionable window (<= 540 days overdue),
writes a PATIENT OutreachLog backdated 12 days, sets episode status to 'contacted',
and for 2 of them sets affirmative kin consent with matching consented contact details.
Safe to re-run (idempotent).
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.config import get_today
from src.continuum.db import get_session_factory
from src.continuum.models import Episode, Patient, OutreachLog
from src.continuum.workflow.states import EpisodeStatus
from src.continuum.workflow.consent import set_kin_consent, set_patient_opt_out
from src.continuum.audit import log_action


def seed_demo_state():
    Session = get_session_factory()
    today = get_today()
    backdated_dt = datetime.combine(today - timedelta(days=12), datetime.min.time().replace(hour=10, minute=30))

    with Session() as db:
        print("=" * 65)
        print(" CONTINUUM DEMO STATE SEEDING — KIN ESCALATION QUEUE ")
        print("=" * 65)

        # Target 4 actionable episodes with registered kin details
        # 2 with consent (20240002, 20240014) and 2 without consent (20240007, 20240030)
        target_uhids_with_consent = ["20240002", "20240014"]
        target_uhids_no_consent = ["20240007", "20240030"]
        all_target_uhids = target_uhids_with_consent + target_uhids_no_consent

        episodes = (
            db.query(Episode)
            .join(Patient)
            .filter(
                Patient.uh_id.in_(all_target_uhids),
                Episode.max_overdue_days <= 540
            )
            .all()
        )

        # If any target UHIDs not found in DB, fallback to first 4 actionable episodes with kin
        if len(episodes) < 4:
            fallback_eps = (
                db.query(Episode)
                .join(Patient)
                .filter(
                    Episode.max_overdue_days <= 540,
                    Patient.kin_phone.isnot(None)
                )
                .order_by(Episode.id)
                .limit(4)
                .all()
            )
            episodes = fallback_eps

        if len(episodes) < 4:
            print(f"[WARN] Found only {len(episodes)} episodes for seeding.")

        print(f"[*] Found {len(episodes)} target episodes for demo seeding.")

        for i, ep in enumerate(episodes):
            patient = ep.patient
            give_consent = (patient.uh_id in target_uhids_with_consent)

            # 1. Update episode status to 'contacted'
            ep.status = EpisodeStatus.CONTACTED.value

            # Ensure patient has kin info populated
            if not patient.kin_name:
                patient.kin_name = f"Family Caregiver {i+1}"
            if not patient.kin_phone:
                patient.kin_phone = f"+9198220{i+1:05d}"
            if not patient.kin_relation:
                patient.kin_relation = "Spouse" if i % 2 == 0 else "Son"

            # 2. Add or update backdated PATIENT OutreachLog
            existing_log = (
                db.query(OutreachLog)
                .filter(
                    OutreachLog.episode_id == ep.id,
                    OutreachLog.recipient_type == "PATIENT"
                )
                .first()
            )

            if not existing_log:
                outreach_log = OutreachLog(
                    episode_id=ep.id,
                    patient_id=patient.id,
                    recipient_type="PATIENT",
                    recipient_phone=patient.phone,
                    channel="WHATSAPP",
                    message_body=(
                        f"Namaste {patient.name}, this is a follow-up reminder from the clinic "
                        f"regarding your overdue consultation."
                    ),
                    status="SENT",
                    timestamp=backdated_dt
                )
                db.add(outreach_log)
            else:
                existing_log.timestamp = backdated_dt

            # 3. Configure consent and bind contact details
            set_patient_opt_out(db, patient.id, opt_out=False, user="demo_seeder")
            if give_consent:
                set_kin_consent(
                    db,
                    patient.id,
                    kin_consent=True,
                    user="demo_seeder",
                    consented_kin_name=patient.kin_name,
                    consented_kin_phone=patient.kin_phone
                )
                consent_tag = f"[OK] KIN CONSENT GRANTED & BOUND ({patient.kin_name}: {patient.kin_phone})"
            else:
                set_kin_consent(
                    db,
                    patient.id,
                    kin_consent=False,
                    user="demo_seeder",
                    consented_kin_name=None,
                    consented_kin_phone=None
                )
                consent_tag = "[LOCKED] NO KIN CONSENT (STRICTLY HARD GATED)"

            log_action(
                db,
                action="DEMO_STATE_SEEDED",
                entity_type="Episode",
                entity_id=str(ep.id),
                user="demo_seeder",
                details={
                    "patient_id": patient.id,
                    "uh_id": patient.uh_id,
                    "attempt_days_ago": 12,
                    "kin_consent": give_consent
                }
            )

            print(f"    - Patient: {patient.name} ({patient.uh_id})")
            print(f"      Status: contacted | Backdated Attempt: {backdated_dt.date()} (12 days ago)")
            print(f"      Kin: {patient.kin_name} ({patient.kin_phone}) -> {consent_tag}")

        db.commit()
        print("=" * 65)
        print("[SUCCESS] Demo state successfully seeded! Kin escalation queue is now primed.")
        print("=" * 65)


if __name__ == "__main__":
    seed_demo_state()
