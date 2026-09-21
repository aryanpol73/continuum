"""
Data normalization utilities for Indian clinical records:
- Indian phone number cleaning (+91 E.164 standard)
- Date format normalization (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, Excel serials)
- Name cleaning (title stripping, spacing, casing)
- Gender normalization
"""

from __future__ import annotations
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple


def normalize_phone(raw_phone: Any) -> Tuple[Optional[str], bool]:
    """
    Normalizes Indian phone numbers to E.164 (+91XXXXXXXXXX).
    Valid Indian mobile numbers consist of 10 digits starting with 6, 7, 8, or 9.
    
    Returns:
        (normalized_e164_phone, is_valid)
    """
    if raw_phone is None:
        return None, False
    
    phone_str = str(raw_phone).strip()
    # Handle floating point strings like '9822012345.0' from Excel
    if phone_str.endswith(".0"):
        phone_str = phone_str[:-2]
        
    # Remove non-digit characters except leading plus
    digits = re.sub(r"[^\d]", "", phone_str)
    
    if not digits:
        return None, False

    # Check various standard Indian formats
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}", True
    elif len(digits) == 11 and digits[0] == "0" and digits[1] in "6789":
        return f"+91{digits[1:]}", True
    elif len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return f"+{digits}", True
    elif len(digits) == 13 and digits.startswith("091") and digits[3] in "6789":
        return f"+{digits[1:]}", True

    # If already formatted with +91
    if phone_str.startswith("+91") and len(digits) == 12 and digits[2] in "6789":
        return f"+{digits}", True

    # Invalid mobile format
    return phone_str, False


def normalize_date(raw_date: Any) -> Optional[date]:
    """
    Parses heterogeneous date representations into datetime.date.
    Supports DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, Excel serial days, and timestamps.
    """
    if raw_date is None:
        return None
        
    if isinstance(raw_date, date):
        if isinstance(raw_date, datetime):
            return raw_date.date()
        return raw_date
        
    # Excel serial number handling (e.g. 45180 -> approx 2023)
    if isinstance(raw_date, (int, float)):
        try:
            if 30000 <= raw_date <= 60000:
                excel_base = datetime(1899, 12, 30)
                return (excel_base + timedelta(days=raw_date)).date()
        except Exception:
            pass

    date_str = str(raw_date).strip()
    if not date_str or date_str.lower() in ("nat", "nan", "none", "null", ""):
        return None

    # Try common formats in Indian clinical systems
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d/%m/%y",
        "%d-%m-%y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Fallback to dateutil if installed
    try:
        from dateutil import parser
        parsed = parser.parse(date_str, dayfirst=True)
        return parsed.date()
    except Exception:
        pass

    return None


def normalize_name(raw_name: Any) -> str:
    """
    Cleans names by stripping prefixes, excessive whitespace, and standardizing to Title Case.
    """
    if not raw_name:
        return "Unknown"
    
    name = str(raw_name).strip()
    
    # Strip common prefixes
    prefix_pattern = r"^(Dr\.|Dr|Mr\.|Mr|Mrs\.|Mrs|Ms\.|Ms|Shri|Smt\.|Smt|Master)\s+"
    name = re.sub(prefix_pattern, "", name, flags=re.IGNORECASE)
    
    # Collapse multiple whitespaces
    name = re.sub(r"\s+", " ", name)
    return name.title()


def normalize_gender(raw_gender: Any) -> str:
    """
    Normalizes gender strings to 'Male', 'Female', or 'Other'.
    """
    if not raw_gender:
        return "Unknown"
    g = str(raw_gender).strip().upper()
    if g in ("M", "MALE", "PURUSH"):
        return "Male"
    elif g in ("F", "FEMALE", "STREE"):
        return "Female"
    elif g in ("O", "OTHER", "TRANSGENDER"):
        return "Other"
    return "Unknown"
