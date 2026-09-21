"""
Caregiver / Kin escalation queue with strict consent hard gate.
Only patients who authorized caregiver outreach can have their relatives contacted.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from src.continuum.config import get_today, get_settings
from src.continuum.models import Episode, Patient, Consent, OutreachLog
from src.continuum.workflow.states import EpisodeStatus
from src.continuum.workflow.consent import verify_kin_consent
from src.continuum.workflow.episodes import transition_episode
from src.continuum.audit import log_action


def get_kin_escalation_candidates(db: Session) -> List[Dict[str, Any]]:
    """
    Identifies overdue patients who have been contacted or remain unreachable,
    and have elapsed the unresponsive waiting threshold since the last patient outreach attempt.
    """
    settings = get_settings()
    threshold_days = settings.get("thresholds", {}).get("days_since_last_patient_attempt", 10)
    today = get_today()

    episodes = db.query(Episode).filter(
        Episode.status.in_([EpisodeStatus.CONTACTED.value, EpisodeStatus.UNREACHABLE.value])
    ).order_by(Episode.max_overdue_days.desc()).all()

    candidates = []
    for ep in episodes:
        # Check latest OutreachLog where recipient_type == 'PATIENT'
        latest_patient_log = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.episode_id == ep.id,
                OutreachLog.recipient_type == "PATIENT"
            )
            .order_by(OutreachLog.timestamp.desc())
            .first()
        )
        if not latest_patient_log:
            continue

        last_attempt = latest_patient_log.timestamp
        last_attempt_date = last_attempt.date() if isinstance(last_attempt, datetime) else last_attempt
        days_since_attempt = (today - last_attempt_date).days
        if days_since_attempt < threshold_days:
            continue

        patient = ep.patient
        kin_allowed, reason = verify_kin_consent(db, patient.id)
        if kin_allowed:
            if not patient.kin_phone:
                kin_allowed = False
                reason = "no number on file"
            else:
                consent = db.query(Consent).filter(Consent.patient_id == patient.id).first()
                if not consent or patient.kin_phone != consent.consented_kin_phone:
                    kin_allowed = False
                    reason = "contact changed since consent"

        candidates.append({
            "episode_id": ep.id,
            "patient_id": patient.id,
            "uh_id": patient.uh_id,
            "name": patient.name,
            "phone": patient.phone,
            "kin_name": patient.kin_name or "Not Specified",
            "kin_phone": patient.kin_phone or "Not Specified",
            "kin_relation": patient.kin_relation or "Caregiver",
            "reason": ep.reason,
            "status": ep.status,
            "due_date": ep.due_date,
            "max_overdue_days": ep.max_overdue_days,
            "first_drug_exhausted": ep.first_drug_exhausted or "",
            "kin_consent_allowed": kin_allowed,
            "consent_reason": reason,
            "days_since_patient_attempt": days_since_attempt,
            "last_patient_attempt": str(last_attempt_date)
        })

    return candidates


def escalate_episode_to_kin(
    db: Session, 
    episode_id: int, 
    user: str = "care_coordinator"
) -> Tuple[bool, str]:
    """
    Escalates an episode to the caregiver / kin queue, strictly enforcing the kin consent hard gate
    and binding consent to the verified kin contact number.
    """
    ep = db.query(Episode).filter(Episode.id == episode_id).first()
    if not ep:
        return False, f"Episode #{episode_id} does not exist."

    patient = ep.patient
    # Hard Gate Check 1: Never contact kin without consent record
    kin_allowed, reason = verify_kin_consent(db, patient.id)
    if not kin_allowed:
        log_action(
            db,
            action="KIN_ESCALATION_BLOCKED",
            entity_type="Episode",
            entity_id=str(episode_id),
            user=user,
            details={
                "patient_id": patient.id,
                "reason": reason
            }
        )
        return False, f"HARD GATE BLOCKED: {reason}"

    # Contact Check: Ensure a kin / caregiver contact number exists on file
    if not patient.kin_phone:
        reason = "no number on file"
        log_action(
            db,
            action="KIN_ESCALATION_BLOCKED",
            entity_type="Episode",
            entity_id=str(episode_id),
            user=user,
            details={
                "patient_id": patient.id,
                "reason": reason
            }
        )
        return False, "CANNOT ESCALATE: No kin / caregiver contact number on file."

    # Hard Gate Check 2: Bind consent to a specific contact
    consent = db.query(Consent).filter(Consent.patient_id == patient.id).first()
    if not consent or patient.kin_phone != consent.consented_kin_phone:
        mismatch_reason = "contact changed since consent"
        log_action(
            db,
            action="KIN_ESCALATION_BLOCKED",
            entity_type="Episode",
            entity_id=str(episode_id),
            user=user,
            details={
                "patient_id": patient.id,
                "reason": mismatch_reason,
                "patient_kin_phone": patient.kin_phone,
                "consented_kin_phone": consent.consented_kin_phone if consent else None
            }
        )
        return False, f"HARD GATE BLOCKED: {mismatch_reason}"

    # Perform transition to KIN_ESCALATED
    transition_episode(
        db,
        episode_id=episode_id,
        new_status=EpisodeStatus.KIN_ESCALATED.value,
        user=user,
        reason="Dispatched outreach to registered caregiver"
    )

    return True, f"Successfully routed episode #{episode_id} to {patient.kin_name or 'caregiver'}."
