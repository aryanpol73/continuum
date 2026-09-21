"""
Unit tests for clinical due rules: follow-up overdue with grace periods and refill gap evaluation.
Uses 7-day grace period after follow-up date and 7-day grace period after supply exhaustion.
"""

from datetime import date
from unittest.mock import MagicMock
from src.continuum.engine.due_rules import (
    calculate_followup_overdue_days, calculate_refill_overdue_days,
    check_followup_overdue, check_refill_gap, is_followup_overdue, is_refill_overdue
)


def test_followup_overdue_within_grace():
    # Due 5 days ago, grace period is 7 days -> NOT overdue yet (0 overdue days)
    visit = MagicMock()
    visit.next_visit_due_date = date(2026, 9, 14)
    today = date(2026, 9, 19)

    is_overdue, days_past = check_followup_overdue(visit, anchor_date=today, grace_days=7)
    assert is_overdue is False
    assert days_past == 5
    assert calculate_followup_overdue_days(visit.next_visit_due_date, today, grace_days=7) == 0


def test_followup_overdue_exceeding_grace():
    # Due 15 days ago, grace period is 7 days -> OVERDUE (15 - 7 = 8 days past grace)
    visit = MagicMock()
    visit.next_visit_due_date = date(2026, 9, 4)
    today = date(2026, 9, 19)

    is_overdue, days_past = check_followup_overdue(visit, anchor_date=today, grace_days=7)
    assert is_overdue is True
    assert days_past == 15
    assert calculate_followup_overdue_days(visit.next_visit_due_date, today, grace_days=7) == 8


def test_refill_exhaustion_within_grace():
    # Supply ended 4 days ago, refill grace is 7 days -> Within grace (0 overdue days)
    rx = MagicMock()
    rx.refill_due_date = date(2026, 9, 15)
    today = date(2026, 9, 19)

    is_overdue, days_since = check_refill_gap(rx, anchor_date=today, buffer_days=7)
    assert is_overdue is False
    assert days_since == 4
    assert calculate_refill_overdue_days(rx.refill_due_date, today, grace_days=7) == 0


def test_refill_overdue_past_grace():
    # Supply ended 20 days ago, refill grace is 7 days -> OVERDUE by 13 days
    rx = MagicMock()
    rx.refill_due_date = date(2026, 8, 30)
    today = date(2026, 9, 19)

    is_overdue, days_since = check_refill_gap(rx, anchor_date=today, buffer_days=7)
    assert is_overdue is True
    assert days_since == 20
    assert calculate_refill_overdue_days(rx.refill_due_date, today, grace_days=7) == 13

