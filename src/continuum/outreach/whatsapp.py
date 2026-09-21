"""
WhatsApp click-to-chat link builder and phone cleaner.
Constructs valid 'https://wa.me/91XXXXXXXXXX?text=...' URLs for 1-click clinical coordinator outreach.
Strictly strips leading plus sign, hyphens, and whitespace.
"""

from __future__ import annotations
import re
import urllib.parse
from typing import Optional


def sanitize_phone_for_whatsapp(phone: str) -> Optional[str]:
    """
    Strips non-digit characters and ensures country code 91 is included with NO plus sign.
    Example: '+91 98220-12345' -> '919822012345'
             '9822012345'       -> '919822012345'
             '09822012345'      -> '919822012345'
    """
    if not phone:
        return None
        
    digits = re.sub(r"[^\d]", "", str(phone))
    if not digits:
        return None

    # 10 digits Indian mobile -> prepend 91
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    elif len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    elif len(digits) == 12 and digits.startswith("91"):
        return digits

    return digits


def build_whatsapp_link(phone: str, message: str) -> str:
    """
    Constructs an official WhatsApp click-to-chat URL: https://wa.me/91XXXXXXXXXX?text=...
    """
    clean_phone = sanitize_phone_for_whatsapp(phone)
    if not clean_phone:
        return ""
        
    encoded_message = urllib.parse.quote(message.strip())
    return f"https://wa.me/{clean_phone}?text={encoded_message}"
