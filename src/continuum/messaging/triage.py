"""
Urgent symptom triage classifier for inbound patient messages.
Flags red-flag keywords indicating emergent or severe symptoms.
"""

from __future__ import annotations
from typing import Optional

RED_FLAGS = [
    "chest pain",
    "chest",
    "breathless",
    "breathing",
    "unconscious",
    "fainted",
    "faint",
    "seizure",
    "fits",
    "bleeding",
    "vomiting blood",
    "sugar very low",
    "sugar very high",
    "chhati",
    "shwas",
    "behosh",
    "rakt",
]


def is_urgent(text: Optional[str]) -> bool:
    """
    Returns True if the text contains any red-flag symptom substring.
    Case-insensitive and safe against None or empty input.
    """
    if not text:
        return False
    lower_text = text.lower()
    return any(flag in lower_text for flag in RED_FLAGS)
