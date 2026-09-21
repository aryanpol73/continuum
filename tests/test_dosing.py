"""
Unit tests for Indian prescription dosing patterns, daily rates, and days supply calculation.
"""

import pytest
from datetime import date
from src.continuum.engine.dosing import (
    parse_dosing_string, calculate_days_supply, calculate_refill_due_date, is_chronic_diabetes_medication
)


@pytest.mark.parametrize("dosing_str, expected_freq", [
    ("1-0-1", 2.0),
    ("1 - 0 - 1", 2.0),
    ("1-1-1", 3.0),
    ("1-0-0", 1.0),
    ("0-0-1", 1.0),
    ("0-1-0", 1.0),
    ("1/2-0-1/2", 1.0),
    ("1-0-1/2", 1.5),
    ("2-0-2", 4.0),
    ("OD", 1.0),
    ("Once Daily", 1.0),
    ("BD", 2.0),
    ("BID", 2.0),
    ("TDS", 3.0),
    ("TID", 3.0),
    ("QID", 4.0),
    ("HS", 1.0),
    ("SOS", 0.0),
    ("PRN", 0.0),
    ("1 tab BD after food", 2.0),
    ("10 Units at Bedtime", 1.0)
])
def test_parse_dosing_string(dosing_str, expected_freq):
    assert parse_dosing_string(dosing_str) == expected_freq


@pytest.mark.parametrize("quantity, freq, expected_days", [
    (60, 2.0, 30),
    (30, 1.0, 30),
    (90, 3.0, 30),
    (15, 0.5, 30),
    (60, 1.5, 40),
    (30, 0.0, 30),  # SOS fallback
    (0, 2.0, 0),
])
def test_calculate_days_supply(quantity, freq, expected_days):
    assert calculate_days_supply(quantity, freq) == expected_days


def test_calculate_refill_due_date():
    start = date(2026, 8, 1)
    refill_date = calculate_refill_due_date(start, 30)
    assert refill_date == date(2026, 8, 31)


@pytest.mark.parametrize("med_name, is_diabetic", [
    ("Glycomet GP 1", True),
    ("Janumet 50/500", True),
    ("Jardiance 10mg", True),
    ("Forxiga 10mg", True),
    ("Metformin 500", True),
    ("Lantus Solostar", True),
    ("Telma 40", False),
    ("Pan 40", False),
    ("Shelcal 500", False)
])
def test_is_chronic_diabetes_medication(med_name, is_diabetic):
    assert is_chronic_diabetes_medication(med_name) == is_diabetic
