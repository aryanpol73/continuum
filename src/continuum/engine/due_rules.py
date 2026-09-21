"""
Clinical due rules engine:
- Follow-up overdue evaluation with 7-day grace period
- Medication refill gap detection with 7-day grace period after supply exhaustion
Standardized against config/rules.yaml and used across engine, workflow, and verification.
"""

from __future__ import annotations
from datetime import date
from typing import Tuple, Optional

from src.continuum.config import get_today, get_rules, get_settings
from src.continuum.models import Visit, Prescription


def calculate_followup_overdue_days(
    next_visit_due_date: Optional[date],
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> int:
    """
    Computes days past the follow-up review grace period.
    Returns 0 if not due or within grace period.
    """
    if not next_visit_due_date:
        return 0

    today = anchor_date or get_today()
    if grace_days is None:
        rules = get_rules()
        grace_days = rules.get("grace_periods", {}).get("followup_grace_days", 7)

    days_past = (today - next_visit_due_date).days
    return max(0, days_past - grace_days)


def is_followup_overdue(
    next_visit_due_date: Optional[date],
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> bool:
    """
    Returns True if consultation is overdue past the grace period.
    """
    return calculate_followup_overdue_days(next_visit_due_date, anchor_date, grace_days) > 0


def calculate_refill_overdue_days(
    supply_end_date: Optional[date],
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> int:
    """
    Computes days past medication supply exhaustion grace period.
    Returns 0 if supply is still active or within grace period.
    """
    if not supply_end_date:
        return 0

    today = anchor_date or get_today()
    if grace_days is None:
        rules = get_rules()
        grace_days = rules.get("grace_periods", {}).get("refill_grace_days", 7)

    days_past_exhaustion = (today - supply_end_date).days
    return max(0, days_past_exhaustion - grace_days)


def is_refill_overdue(
    supply_end_date: Optional[date],
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> bool:
    """
    Returns True if medication supply exhaustion exceeds the grace period.
    """
    return calculate_refill_overdue_days(supply_end_date, anchor_date, grace_days) > 0


def check_followup_overdue(
    visit: Visit, 
    anchor_date: Optional[date] = None,
    grace_days: Optional[int] = None
) -> Tuple[bool, int]:
    """
    Backward-compatible evaluator for visit objects.
    Returns:
        (is_overdue, total_days_since_due_date)
    """
    if not visit.next_visit_due_date:
        return False, 0

    today = anchor_date or get_today()
    days_past = (today - visit.next_visit_due_date).days
    overdue_days = calculate_followup_overdue_days(visit.next_visit_due_date, today, grace_days)
    return overdue_days > 0, days_past


def check_refill_gap(
    rx: Prescription, 
    anchor_date: Optional[date] = None,
    buffer_days: Optional[int] = None
) -> Tuple[bool, int]:
    """
    Evaluator for prescription refill overdue past supply exhaustion.
    Returns:
        (is_overdue, days_since_exhaustion)
    """
    if not rx.refill_due_date:
        return False, 0

    today = anchor_date or get_today()
    days_since_exhaustion = (today - rx.refill_due_date).days
    overdue_days = calculate_refill_overdue_days(rx.refill_due_date, today, buffer_days)
    return overdue_days > 0, days_since_exhaustion

