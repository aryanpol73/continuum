"""
Caregiver / Kin escalation queue with strict consent hard gate.
Only patients who authorized caregiver outreach can have their relatives contacted.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from src.continuum.config import get_today, get_settings
from src.continuum.models import Episode, Patient, Consent
from src.continuum.workflow.states import EpisodeStatus
from src.continuum.workflow.consent import verify_kin_consent
from src.continuum.workflow.episodes import transition_episode
from src.continuum.audit import log_action


def get_kin_escalation_candidates(db: Session) -> List[Dict[str, Any]]:
    """
    Identifies overdue patients who have been contacted or remain unreachable.
    """
    settings = get_settings()
    threshold_days = settings.get("thresholds", {}).get("unresponsive_days_for_escalation", 7)
    today = get_today()

    episodes = db.query(Episode).filter(
        Episode.max_overdue_days >= threshold_days,
        Episode.status.in_([EpisodeStatus.CONTACTED.value, EpisodeStatus.UNREACHABLE.value])
    ).order_by(Episode.max_overdue_days.desc()).all()

    candidates = []
    for ep in episodes:
        patient = ep.patient
        kin_allowed, reason = verify_kin_consent(db, patient.id)

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
            "consent_reason": reason
        })

    return candidates


def escalate_episode_to_kin(
    db: Session, 
    episode_id: int, 
    user: str = "care_coordinator"
) -> Tuple[bool, str]:
    """
    Escalates an episode to the caregiver / kin queue, strictly enforcing the kin consent hard gate.
    """
    ep = db.query(Episode).filter(Episode.id == episode_id).first()
    if not ep:
        return False, f"Episode #{episode_id} does not exist."

    patient = ep.patient
    # Hard Gate Check: Never contact kin without consent record
    kin_allowed, reason = verify_kin_consent(db, patient.id)
    if not kin_allowed:
        log_action(
            db,
            action="KIN_ESCALATION_BLOCKED",
            entity_type="Episode",
            entity_id=episode_id,
            user=user,
            details={
                "patient_id": patient.id,
                "reason": reason
            }
        )
        return False, f"HARD GATE BLOCKED: {reason}"

    if not patient.kin_phone:
        return False, "CANNOT ESCALATE: No kin / caregiver contact number on file."

    # Perform transition
    transition_episode(
        db,
        episode_id=episode_id,
        new_status="contacted",
        user=user,
        reason="Dispatched outreach to registered caregiver"
    )

    return True, f"Successfully routed episode #{episode_id} to {patient.kin_name or 'caregiver'}."
