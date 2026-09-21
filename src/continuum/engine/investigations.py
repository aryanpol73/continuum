"""
Administrative test turnaround & missing investigation tracker for Continuum.
Tracks whether advised lab tests/investigations have an uploaded report within
the configured turnaround window (default 45 days).
Administrative care continuity tracking only: no interpretation or scoring of lab values.
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.continuum.config import get_today, get_rules
from src.continuum.models import Visit, Patient, UploadedReport

# Standard test token aliases mapping advice tokens to report labels
TEST_MAPPINGS = {
    "HBA1C": ["HBA1C"],
    "FBS": ["FBS-PPBS", "FBS", "PPBS", "GLUCOSE"],
    "PPBS": ["FBS-PPBS", "FBS", "PPBS", "GLUCOSE"],
    "S.CREAT": ["SERUM CREATININE", "CREATININE", "S.CREAT"],
    "LIPID": ["LIPID PROFILE", "LIPID", "CHOLESTEROL"],
    "THYROID": ["THYROID PROFILE", "THYROID", "TSH"],
    "URINE": ["URINE ROUTINE", "URINE"],
    "ECG": ["ECG"],
    "ECHO": ["2D ECHO", "ECHO"],
    "USG": ["USG ABDOMEN", "USG", "SONOGRAPHY"],
}


def parse_advised_tests(advice_str: Optional[str]) -> List[str]:
    """Extracts standardized test tokens from free-text doctor investigation advice."""
    if not advice_str:
        return []
    
    advice_upper = advice_str.upper()
    found = []
    
    if "HBA1C" in advice_upper:
        found.append("HbA1c")
    if "FBS" in advice_upper or "PPBS" in advice_upper:
        found.append("FBS-PPBS")
    if "CREAT" in advice_upper:
        found.append("Serum Creatinine")
    if "LIPID" in advice_upper:
        found.append("Lipid Profile")
    if "THYROID" in advice_upper:
        found.append("Thyroid Profile")
    if "URINE" in advice_upper:
        found.append("Urine Routine")
    if "ECG" in advice_upper:
        found.append("ECG")
    if "ECHO" in advice_upper:
        found.append("2D Echo")
    if "USG" in advice_upper:
        found.append("USG Abdomen")

    return list(dict.fromkeys(found))


def get_patient_missing_investigations(
    db: Session,
    patient_uh_id: str,
    anchor_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Identifies investigations advised for a patient where no matching uploaded report
    was received within the allowed turnaround window.
    """
    today = anchor_date or get_today()
    rules = get_rules()
    turnaround_days = rules.get("investigation_rules", {}).get("report_turnaround_days", 45)

    patient = db.query(Patient).filter(Patient.uh_id == patient_uh_id).first()
    if not patient:
        return []

    # Get patient's visits with investigation advice
    visits = (
        db.query(Visit)
        .filter(Visit.patient_id == patient.id, Visit.investigation_advice.isnot(None))
        .order_by(Visit.visit_date.asc())
        .all()
    )

    if not visits:
        return []

    # Get patient's uploaded reports
    reports = (
        db.query(UploadedReport)
        .filter(UploadedReport.uh_id == patient_uh_id)
        .all()
    )

    missing = []
    for v in visits:
        advised_tests = parse_advised_tests(v.investigation_advice)
        days_pending = (today - v.visit_date).days

        if days_pending <= turnaround_days:
            continue

        for test_name in advised_tests:
            # Check if there is an uploaded report matching this test
            test_key = test_name.upper().replace(" ", "").replace("-", "")
            aliases = [a.replace(" ", "").replace("-", "") for a in TEST_MAPPINGS.get(test_key, [test_key])]

            has_report = False
            for r in reports:
                if not r.labelled_as:
                    continue
                rep_lbl = r.labelled_as.upper().replace(" ", "").replace("-", "")
                if any(alias in rep_lbl or rep_lbl in alias for alias in aliases):
                    if (r.upload_date - v.visit_date).days >= 0:
                        has_report = True
                        break

            if not has_report:
                missing.append({
                    "uh_id": patient_uh_id,
                    "visit_id": v.id,
                    "test_name": test_name,
                    "advised_date": v.visit_date,
                    "days_pending": days_pending,
                    "turnaround_threshold_days": turnaround_days,
                    "is_overdue": True
                })

    return missing


def get_all_missing_investigations_summary(
    db: Session,
    anchor_date: Optional[date] = None
) -> Dict[str, List[str]]:
    """
    Returns a lookup mapping {uh_id: [missing_test_names]} for all patients with pending overdue tests.
    """
    today = anchor_date or get_today()
    rules = get_rules()
    turnaround_days = rules.get("investigation_rules", {}).get("report_turnaround_days", 45)

    visits_with_advice = (
        db.query(Visit)
        .join(Patient)
        .filter(Visit.investigation_advice.isnot(None))
        .all()
    )

    reports = db.query(UploadedReport).filter(UploadedReport.uh_id.isnot(None)).all()
    rep_map: Dict[str, List[UploadedReport]] = {}
    for r in reports:
        if r.uh_id:
            rep_map.setdefault(r.uh_id, []).append(r)

    summary: Dict[str, List[str]] = {}

    for v in visits_with_advice:
        days_pending = (today - v.visit_date).days
        if days_pending <= turnaround_days:
            continue

        uh_id = v.patient.uh_id
        advised_tests = parse_advised_tests(v.investigation_advice)
        patient_reps = rep_map.get(uh_id, [])

        for test_name in advised_tests:
            test_key = test_name.upper().replace(" ", "").replace("-", "")
            aliases = [a.replace(" ", "").replace("-", "") for a in TEST_MAPPINGS.get(test_key, [test_key])]

            has_report = False
            for r in patient_reps:
                if not r.labelled_as:
                    continue
                rep_lbl = r.labelled_as.upper().replace(" ", "").replace("-", "")
                if any(alias in rep_lbl or rep_lbl in alias for alias in aliases):
                    if (r.upload_date - v.visit_date).days >= 0:
                        has_report = True
                        break

            if not has_report:
                if uh_id not in summary:
                    summary[uh_id] = []
                if test_name not in summary[uh_id]:
                    summary[uh_id].append(test_name)

    return summary
