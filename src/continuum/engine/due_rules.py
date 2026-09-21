"""
Clinical due rules engine:
- Follow-up overdue evaluation with grace periods
- Medication refill gap detection with safety buffers
- Milestone screening checks
"""

from __future__ import annotations
from datetime import date
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from src.continuum.config import get_today, get_settings
from src.continuum.models import Visit, Prescription, Patient


def check_followup_overdue(
    visit: Visit, 
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> Tuple[bool, int]:
    """
    Evaluates whether a clinical consultation follow-up is overdue past the permissible grace period.
    
    Returns:
        (is_overdue, days_past_due_date)
    """
    if not visit.next_visit_due_date:
        return False, 0

    today = anchor_date or get_today()
    if grace_days is None:
        settings = get_settings()
        grace_days = settings.get("thresholds", {}).get("followup_grace_days", 14)

    days_past = (today - visit.next_visit_due_date).days
    
    # Overdue if today exceeds next_visit_due_date + grace_days
    is_overdue = days_past > grace_days
    return is_overdue, days_past


def check_refill_gap(
    rx: Prescription, 
    anchor_date: Optional[date] = None,
    buffer_days: Optional[int] = None
) -> Tuple[bool, int]:
    """
    Evaluates whether a medication is within the critical refill window (or already exhausted).
    
    Returns:
        (is_refill_needed, days_remaining_until_exhaustion)
        Note: If days_remaining is negative, the supply is already exhausted by that many days.
    """
    if not rx.refill_due_date:
        return False, 999

    today = anchor_date or get_today()
    if buffer_days is None:
        settings = get_settings()
        buffer_days = settings.get("thresholds", {}).get("refill_buffer_days", 7)

    days_remaining = (rx.refill_due_date - today).days

    # Refill gap triggered if remaining supply <= buffer days
    is_gap = days_remaining <= buffer_days
    return is_gap, days_remaining
