"""
Care continuum retention metrics and physician engagement scorecards.
Tracks the closed-loop story: detected -> contacted -> promised -> returned.
"""

from __future__ import annotations
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from src.continuum.models import Patient, Visit, Prescription, Episode, OutreachLog, Consent
from src.continuum.workflow.states import EpisodeReason, EpisodeStatus


def get_retention_funnel_metrics(db: Session) -> Dict[str, Any]:
    """
    Computes overall care continuum closed-loop metrics.
    """
    total_patients = db.query(Patient).count()

    # Diabetic cohort: unique patients who have at least one diabetic visit
    diabetic_patient_ids = db.query(Visit.patient_id).filter(
        Visit.is_diabetes_cohort == True
    ).distinct().all()
    diabetic_cohort_count = len(diabetic_patient_ids)

    # Episodes breakdown by reason
    total_episodes = db.query(Episode).count()
    followup_episodes = db.query(Episode).filter(Episode.reason == EpisodeReason.FOLLOWUP_OVERDUE.value).count()
    refill_episodes = db.query(Episode).filter(Episode.reason == EpisodeReason.REFILL_GAP.value).count()
    combined_episodes = db.query(Episode).filter(Episode.reason == EpisodeReason.COMBINED.value).count()
    refill_only_episodes = db.query(Episode).filter(Episode.is_refill_only == True).count()

    # Closed-loop status breakdown
    detected = db.query(Episode).filter(Episode.status == EpisodeStatus.DETECTED.value).count()
    contacted = db.query(Episode).filter(Episode.status == EpisodeStatus.CONTACTED.value).count()
    promised = db.query(Episode).filter(Episode.status == EpisodeStatus.PROMISED.value).count()
    returned = db.query(Episode).filter(Episode.status == EpisodeStatus.RETURNED.value).count()
    unreachable = db.query(Episode).filter(Episode.status == EpisodeStatus.UNREACHABLE.value).count()
    opted_out = db.query(Episode).filter(Episode.status == EpisodeStatus.OPTED_OUT.value).count()
    kin_escalated = db.query(Episode).filter(Episode.status == EpisodeStatus.KIN_ESCALATED.value).count()

    # Outreached includes contacted, kin_escalated, promised, returned
    total_engaged = contacted + kin_escalated + promised + returned
    return_to_care_rate = round(returned / max(1, total_engaged) * 100, 1)

    # Consent summary
    opted_out_count = db.query(Consent).filter(Consent.opt_out == True).count()
    kin_consented_count = db.query(Consent).filter(Consent.kin_consent == True).count()

    return {
        "total_patients": total_patients,
        "diabetic_cohort_count": diabetic_cohort_count,
        "opted_out_patients": opted_out_count,
        "kin_consented_patients": kin_consented_count,
        "total_episodes": total_episodes,
        "followup_episodes": followup_episodes,
        "refill_episodes": refill_episodes,
        "combined_episodes": combined_episodes,
        "refill_only_episodes": refill_only_episodes,
        "status_counts": {
            "detected": detected,
            "contacted": contacted,
            "promised": promised,
            "returned": returned,
            "unreachable": unreachable,
            "opted_out": opted_out,
            "kin_escalated": kin_escalated
        },
        "return_to_care_rate_percent": return_to_care_rate
    }


def get_doctor_retention_scorecard(db: Session) -> List[Dict[str, Any]]:
    """
    Computes doctor-specific patient retention and follow-up metrics.
    """
    doctors = db.query(Visit.doctor_name).distinct().all()
    scorecards = []

    for (doc_name,) in doctors:
        if not doc_name:
            continue

        doc_visits = db.query(Visit.id).filter(Visit.doctor_name == doc_name).subquery()
        
        total_episodes = db.query(Episode).filter(Episode.visit_id.in_(doc_visits)).count()
        returned_count = db.query(Episode).filter(
            Episode.visit_id.in_(doc_visits),
            Episode.status == EpisodeStatus.RETURNED.value
        ).count()
        active_overdue = db.query(Episode).filter(
            Episode.visit_id.in_(doc_visits),
            Episode.status.in_([EpisodeStatus.DETECTED.value, EpisodeStatus.CONTACTED.value, EpisodeStatus.PROMISED.value])
        ).count()

        retention_rate = round(returned_count / max(1, total_episodes) * 100, 1)

        scorecards.append({
            "doctor_name": doc_name,
            "total_episodes_flagged": total_episodes,
            "active_overdue": active_overdue,
            "returned_to_care": returned_count,
            "retention_rate_pct": retention_rate
        })

    return sorted(scorecards, key=lambda x: x["total_episodes_flagged"], reverse=True)
