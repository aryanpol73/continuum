"""
Care coordinator worklist builder:
Ranks patients STRICTLY by days overdue (descending).
Never calculates clinical severity, stages, or scores.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.continuum.config import get_today
from src.continuum.models import Episode, Patient, Visit, Prescription, Consent


def get_overdue_worklist(
    db: Session,
    reason: Optional[str] = None,
    status: Optional[str] = None,
    search_query: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetches, filters, and ranks actionable care coordinator worklist items.
    Ranking convention: strictly sorted by max_overdue_days in descending order.
    """
    today = get_today()
    query = db.query(Episode).join(Patient)

    if reason and reason != "ALL":
        query = query.filter(Episode.reason == reason)

    if status and status != "ALL":
        query = query.filter(Episode.status == status)

    # Order strictly by days overdue descending
    episodes = query.order_by(desc(Episode.max_overdue_days), Episode.due_date).all()
    worklist_items = []

    for ep in episodes:
        patient = ep.patient
        consent = patient.consent

        # Search query filter (Name, UHID, or Phone)
        if search_query and search_query.strip():
            sq = search_query.strip().lower()
            if sq not in patient.name.lower() and sq not in patient.uh_id.lower() and sq not in patient.phone.lower():
                continue

        # Doctor details from associated visit
        doc_name = "Dr. Ashwin Sadavarte"
        if ep.visit_id:
            visit = db.query(Visit).filter(Visit.id == ep.visit_id).first()
            if visit and visit.doctor_name:
                doc_name = visit.doctor_name

        worklist_items.append({
            "episode_id": ep.id,
            "patient_id": patient.id,
            "uh_id": patient.uh_id,
            "name": patient.name,
            "phone": patient.phone,
            "gender": patient.gender,
            "age": patient.age,
            "kin_name": patient.kin_name or "",
            "kin_phone": patient.kin_phone or "",
            "kin_relation": patient.kin_relation or "",
            "reason": ep.reason,
            "status": ep.status,
            "due_date": ep.due_date,
            "max_overdue_days": ep.max_overdue_days,
            "followup_overdue_days": ep.followup_overdue_days,
            "refill_overdue_days": ep.refill_overdue_days,
            "first_drug_exhausted": ep.first_drug_exhausted or "",
            "is_refill_only": ep.is_refill_only,
            "doctor_name": doc_name,
            "promised_date": ep.promised_date,
            "opt_out": consent.opt_out if consent else False,
            "kin_consent": consent.kin_consent if consent else False,
            "preferred_language": consent.preferred_language if consent else "mr"
        })

    return worklist_items
