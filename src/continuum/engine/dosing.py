"""
Indian prescription dosing pattern parser, daily rate calculator,
days-of-supply forecast, and refill due date engine.
"""

from __future__ import annotations
import math
import re
from datetime import date, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from src.continuum.config import get_rules
from src.continuum.models import Prescription
from src.continuum.audit import log_action


def parse_fraction(s: str) -> float:
    s = s.strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2:
            try:
                return float(parts[0]) / float(parts[1])
            except (ValueError, ZeroDivisionError):
                pass
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_dosing_string(raw_dose: str) -> float:
    """
    Parses complex Indian prescription dosing strings into numeric daily units.
    
    Examples:
        '1-0-1' -> 2.0
        '1-1-1' -> 3.0
        '1/2-0-1/2' -> 1.0
        '1-0-1/2' -> 1.5
        'OD' -> 1.0
        'BD' -> 2.0
        'TDS' -> 3.0
        'SOS' -> 0.0
    """
    if not raw_dose:
        return 1.0  # Default safe assumption

    text = str(raw_dose).strip().upper()
    rules = get_rules().get("dosing_patterns", {})
    
    # 1. Exact abbreviation check
    abbrevs = rules.get("abbreviations", {})
    if text in abbrevs:
        return float(abbrevs[text])

    # Check if abbreviation is contained in text (e.g. "1 Tab BD After Food")
    for abbr, freq in abbrevs.items():
        if re.search(rf"\b{re.escape(abbr)}\b", text):
            return float(freq)

    # 2. Hyphenated pattern check (e.g. '1-0-1', '1 - 0 - 1', '1/2-0-1/2', '0.5-0-0.5')
    clean_hyphen = re.sub(r"\s*-\s*", "-", text)
    match_hyphen = re.search(r"(\d+(?:/\d+|\.\d+)?)-(\d+(?:/\d+|\.\d+)?)-(\d+(?:/\d+|\.\d+)?)", clean_hyphen)
    if match_hyphen:
        morning = parse_fraction(match_hyphen.group(1))
        afternoon = parse_fraction(match_hyphen.group(2))
        night = parse_fraction(match_hyphen.group(3))
        return round(morning + afternoon + night, 3)

    # Two-part hyphenated (e.g. '1-1')
    match_two = re.search(r"(\d+(?:/\d+|\.\d+)?)-(\d+(?:/\d+|\.\d+)?)", clean_hyphen)
    if match_two:
        d1 = parse_fraction(match_two.group(1))
        d2 = parse_fraction(match_two.group(2))
        return round(d1 + d2, 3)

    # 3. Numeric patterns dictionary lookup
    num_patterns = rules.get("numeric_patterns", {})
    if text in num_patterns:
        return float(num_patterns[text])

    # 4. Insulin units regex (e.g. "10 Units at Bedtime", "14U HS")
    insulin_match = re.search(r"(\d+)\s*(?:UNITS?|U)\b", text)
    if insulin_match:
        # For insulin, we treat 1 pen / cartridge as standard supply or default 1 unit per day equivalent
        return 1.0

    # 5. Standalone number (e.g. "1 Tablet daily", "2 times")
    single_num = re.search(r"\b(\d+)\s*(?:TAB|CAP|TIMES?|X)\b", text)
    if single_num:
        return float(single_num.group(1))

    return 1.0


def calculate_days_supply(quantity: int, frequency_per_day: float) -> int:
    """
    Computes days of supply given dispensed quantity and daily dosage.
    Safely handles zero or fractional daily frequencies.
    """
    if quantity <= 0:
        return 0
    if frequency_per_day <= 0:
        return 30  # Fallback for SOS or PRN medications

    return max(1, math.floor(quantity / frequency_per_day))


def calculate_refill_due_date(start_date: date, days_supply: int) -> date:
    """
    Computes the exact calendar date when current supply will be exhausted.
    """
    return start_date + timedelta(days=days_supply)


def is_chronic_diabetes_medication(med_name: str) -> bool:
    """
    Checks if a medication belongs to standard chronic diabetes management regimens.
    """
    if not med_name:
        return False
        
    rules = get_rules()
    chronic_list = rules.get("chronic_medications", {}).get("diabetes", [])
    
    name_upper = med_name.strip().upper()
    for drug in chronic_list:
        if drug.upper() in name_upper:
            return True
            
    return False


def process_prescription_dosing(rx: Prescription) -> None:
    """
    Computes frequency_per_day, days_supply, refill_due_date, and chronic flag on a Prescription model.
    """
    freq = parse_dosing_string(rx.raw_dose)
    rx.frequency_per_day = freq
    rx.days_supply = calculate_days_supply(rx.quantity, freq)
    rx.refill_due_date = calculate_refill_due_date(rx.start_date, rx.days_supply)
    rx.is_chronic_diabetes_drug = is_chronic_diabetes_medication(rx.medication_name)


def update_all_prescriptions_dosing(db: Session) -> int:
    """
    Batch processor to re-calculate all prescriptions in the database.
    """
    prescriptions = db.query(Prescription).all()
    count = 0
    for rx in prescriptions:
        process_prescription_dosing(rx)
        count += 1
    db.commit()
    
    log_action(
        db,
        action="DOSING_ENGINE_RUN",
        entity_type="Prescription",
        entity_id="ALL",
        details={"processed_prescriptions": count}
    )
    return count
