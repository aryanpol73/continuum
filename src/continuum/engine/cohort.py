"""
Cohort identification engine: classifies outpatient consultation notes and free-text impressions
to isolate chronic Type 2 Diabetes Mellitus patients with high specificity.
"""

from __future__ import annotations
import re
from typing import Tuple
from sqlalchemy.orm import Session

from src.continuum.config import get_rules
from src.continuum.models import Visit
from src.continuum.audit import log_action


def classify_diabetes_diagnosis(raw_dx: str) -> Tuple[bool, str, float]:
    """
    Evaluates whether an unstructured clinical impression / diagnosis text signifies Diabetes Mellitus.
    
    Returns:
        (is_diabetes, matched_term_or_reason, confidence_score)
    """
    if not raw_dx:
        return False, "EMPTY_DIAGNOSIS", 0.0

    text = str(raw_dx).strip().upper()
    rules = get_rules().get("cohort_rules", {})
    
    # 1. Check exclusion patterns first
    exclude_patterns = rules.get("exclude_patterns", [])
    for pattern in exclude_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return False, f"EXCLUDED_BY_PATTERN: {pattern}", 0.0

    # 2. Check inclusion patterns
    include_patterns = rules.get("include_patterns", [])
    for pattern in include_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            matched_text = match.group(0)
            return True, f"MATCHED: {matched_text}", 0.98

    return False, "NO_DIABETES_MARKERS", 0.0


def update_all_visits_cohort(db: Session) -> int:
    """
    Processes all clinical visits to tag `is_diabetes_cohort`.
    """
    visits = db.query(Visit).all()
    count_diabetic = 0
    
    for v in visits:
        is_dm, reason, conf = classify_diabetes_diagnosis(v.diagnosis_raw)
        v.is_diabetes_cohort = is_dm
        if is_dm:
            count_diabetic += 1

    db.commit()

    log_action(
        db,
        action="COHORT_CLASSIFICATION_RUN",
        entity_type="Visit",
        entity_id="ALL",
        details={"total_visits": len(visits), "diabetic_visits": count_diabetic}
    )
    return count_diabetic
