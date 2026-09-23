"""Daily activity snapshot anchored to the simulation date."""
from __future__ import annotations
from datetime import date, timedelta, datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from src.continuum.models import Episode, Visit, OutreachLog


def get_daily_snapshot(db: Session, day: date) -> Dict[str, Any]:
    lapsed = db.query(Episode).filter(Episode.due_date == day).count()
    refill_lapsed = db.query(Episode).filter(
        Episode.due_date == day, Episode.is_refill_only.is_(True)
    ).count()
    expected = db.query(Visit).filter(Visit.next_visit_due_date == day).count()
    attended = db.query(Visit).filter(
        Visit.visit_date == day, Visit.is_diabetes_cohort.is_(True)
    ).count()
    closed = db.query(Episode).filter(Episode.closed_date == day).count()
    outreach = db.query(OutreachLog).filter(
        OutreachLog.timestamp >= datetime.combine(day, datetime.min.time()),
        OutreachLog.timestamp < datetime.combine(day + timedelta(days=1), datetime.min.time()),
    ).count()
    return {
        "date": day,
        "expected_today": expected,
        "attended_today": attended,
        "no_show_today": max(0, expected - attended),
        "lapsed_today": lapsed,
        "refill_lapsed_today": refill_lapsed,
        "outreach_today": outreach,
        "closed_today": closed,
    }


def get_daily_series(db: Session, end_day: date, days: int = 30) -> List[Dict[str, Any]]:
    start = end_day - timedelta(days=days - 1)
    eps = db.query(Episode.due_date, Episode.is_refill_only).filter(
        Episode.due_date >= start, Episode.due_date <= end_day
    ).all()
    vis = db.query(Visit.visit_date).filter(
        Visit.visit_date >= start,
        Visit.visit_date <= end_day,
        Visit.is_diabetes_cohort.is_(True),
    ).all()

    lapsed, refill, attended = {}, {}, {}
    for d, ro in eps:
        lapsed[d] = lapsed.get(d, 0) + 1
        if ro:
            refill[d] = refill.get(d, 0) + 1
    for (d,) in vis:
        attended[d] = attended.get(d, 0) + 1

    return [
        {
            "date": start + timedelta(days=i),
            "Lapsed": lapsed.get(start + timedelta(days=i), 0),
            "Refill-only": refill.get(start + timedelta(days=i), 0),
            "Attended": attended.get(start + timedelta(days=i), 0),
        }
        for i in range(days)
    ]
