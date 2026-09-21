"""
Episode lifecycle management: automated generation from clinical rules,
status advancement through the FSM, and closure upon patient return.
Mirrors the Ramraksha Hospital OPD clinical reality and answer keys.
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from src.continuum.config import get_today, get_settings
from src.continuum.models import Episode, Visit, Prescription, Patient
from src.continuum.workflow.states import EpisodeReason, EpisodeStatus, is_valid_transition
from src.continuum.engine.dosing import parse_dosing_string, calculate_days_supply
from src.continuum.engine.due_rules import calculate_followup_overdue_days, calculate_refill_overdue_days
from src.continuum.audit import log_action


def generate_episodes_from_rules(
    db: Session, 
    anchor_date: Optional[date] = None,
    user: str = "system"
) -> Dict[str, int]:
    """
    Evaluates clinical database records against due rules and generates or refreshes active episodes.
    Calculates both follow-up overdue days and earliest medication refill exhaustion days for the diabetes cohort.
    Auto-closes open episodes when a patient returns for an in-person OPD consultation.
    """
    today = anchor_date or get_today()
    settings = get_settings()
    fu_grace = settings.get("thresholds", {}).get("followup_grace_days", 7)
    rf_grace = settings.get("thresholds", {}).get("refill_buffer_days", 7)

    stats = {
        "episodes_created": 0,
        "refill_only_episodes": 0,
        "followup_only_episodes": 0,
        "combined_episodes": 0,
        "episodes_auto_closed": 0
    }

    # Filter strictly to the diabetes cohort
    patients = (
        db.query(Patient)
        .join(Visit, Visit.patient_id == Patient.id)
        .filter(Visit.is_diabetes_cohort.is_(True))
        .distinct()
        .all()
    )

    for patient in patients:
        visits = db.query(Visit).filter(Visit.patient_id == patient.id).order_by(Visit.visit_date.asc(), Visit.id.asc()).all()
        if not visits:
            continue

        # Get the latest consultation visit
        last_visit = visits[-1]
        last_date = last_visit.visit_date

        # 1. Follow-up signal via due_rules engine
        fu_overdue_days = calculate_followup_overdue_days(last_visit.next_visit_due_date, today, fu_grace)

        # 2. Refill signal: EARLIEST-exhausting drug on the last prescription
        prescriptions = db.query(Prescription).filter(
            Prescription.patient_id == patient.id,
            Prescription.visit_id == last_visit.id
        ).all()

        ends = []
        for rx in prescriptions:
            if not rx.quantity or rx.quantity <= 0:
                continue
            dpd = parse_dosing_string(rx.raw_dose)
            if not dpd or dpd <= 0:
                continue
            
            supply_days = calculate_days_supply(rx.quantity, dpd)
            if supply_days is None:
                continue
            end_date = last_date + timedelta(days=supply_days)
            ends.append((end_date, rx.medication_name, rx.id))

        if ends:
            first_end, first_drug, rx_id = min(ends, key=lambda x: x[0])
            refill_overdue_days = calculate_refill_overdue_days(first_end, today, rf_grace)
        else:
            first_end, first_drug, rx_id, refill_overdue_days = None, None, None, 0

        # Check if overdue on either signal or if patient returned
        if fu_overdue_days == 0 and refill_overdue_days == 0:
            # Closed-loop return auto-closure: patient attended in-person OPD after episode opened
            open_ep = (
                db.query(Episode)
                .filter(
                    Episode.patient_id == patient.id,
                    Episode.status.notin_([
                        EpisodeStatus.RETURNED.value,
                        EpisodeStatus.OPTED_OUT.value,
                    ]),
                )
                .first()
            )
            if open_ep and last_date > open_ep.opened_date:
                open_ep.status = EpisodeStatus.RETURNED.value
                open_ep.closed_date = today
                open_ep.closure_reason = f"Attended OPD on {last_date}"
                stats["episodes_auto_closed"] += 1
                log_action(
                    db,
                    action="EPISODE_AUTO_CLOSED_ON_RETURN",
                    entity_type="Episode",
                    entity_id=open_ep.id,
                    user=user,
                    details={"visit_date": str(last_date)}
                )
            continue

        is_refill_only = (refill_overdue_days > 0 and fu_overdue_days == 0)
        
        if is_refill_only:
            reason_type = EpisodeReason.REFILL_GAP.value
            stats["refill_only_episodes"] += 1
            due_d = first_end
        elif fu_overdue_days > 0 and refill_overdue_days == 0:
            reason_type = EpisodeReason.FOLLOWUP_OVERDUE.value
            stats["followup_only_episodes"] += 1
            due_d = last_visit.next_visit_due_date
        else:
            reason_type = EpisodeReason.COMBINED.value
            stats["combined_episodes"] += 1
            due_d = min(filter(None, [first_end, last_visit.next_visit_due_date]))

        max_days = max(fu_overdue_days, refill_overdue_days)

        # Find or create episode
        existing_ep = db.query(Episode).filter(
            Episode.patient_id == patient.id,
            Episode.status.notin_([EpisodeStatus.RETURNED.value, EpisodeStatus.OPTED_OUT.value])
        ).first()

        if not existing_ep:
            ep = Episode(
                patient_id=patient.id,
                visit_id=last_visit.id,
                prescription_id=rx_id,
                reason=reason_type,
                status=EpisodeStatus.DETECTED.value,
                due_date=due_d or today,
                opened_date=today,
                max_overdue_days=max_days,
                first_drug_exhausted=first_drug,
                followup_overdue_days=fu_overdue_days,
                refill_overdue_days=refill_overdue_days,
                is_refill_only=is_refill_only
            )
            db.add(ep)
            stats["episodes_created"] += 1
        else:
            existing_ep.max_overdue_days = max_days
            existing_ep.first_drug_exhausted = first_drug
            existing_ep.followup_overdue_days = fu_overdue_days
            existing_ep.refill_overdue_days = refill_overdue_days
            existing_ep.is_refill_only = is_refill_only
            existing_ep.reason = reason_type

    db.commit()

    log_action(
        db,
        action="EPISODE_GENERATION_RUN",
        entity_type="Episode",
        entity_id="ALL",
        user=user,
        details=stats
    )

    return stats


def transition_episode(
    db: Session,
    episode_id: int,
    new_status: str,
    user: str = "care_coordinator",
    reason: Optional[str] = None
) -> Episode:
    """
    Advances an episode along the finite state machine:
    detected -> contacted -> promised -> returned / unreachable / opted_out.
    """
    ep = db.query(Episode).filter(Episode.id == episode_id).first()
    if not ep:
        raise ValueError(f"Episode #{episode_id} not found.")

    if not is_valid_transition(ep.status, new_status):
        raise ValueError(f"Invalid transition from {ep.status} to {new_status}")

    old_status = ep.status
    ep.status = new_status
    today = get_today()

    if new_status in [EpisodeStatus.RETURNED.value, EpisodeStatus.OPTED_OUT.value]:
        ep.closed_date = today
        ep.closure_reason = reason or f"Transitioned to {new_status}"

    db.commit()
    db.refresh(ep)

    log_action(
        db,
        action="EPISODE_STATUS_CHANGED",
        entity_type="Episode",
        entity_id=ep.id,
        user=user,
        details={
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason
        }
    )

    return ep
