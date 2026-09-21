"""
Message formatting and template interpolation module.
Strictly adheres to AGENTS.md guardrail:
"The message generator may only translate and fill placeholders in doctor-approved templates. It must NEVER compose free-form health content."
"""

from __future__ import annotations
import os
from typing import Optional
from src.continuum.config import get_settings
from src.continuum.ai.schemas import PersonalizedMessageDraft


def personalize_clinical_message(
    base_text: str,
    patient_name: str,
    language: str = "en",
    relationship_context: Optional[str] = None
) -> PersonalizedMessageDraft:
    """
    Renders doctor-approved outreach messages with strict medical non-advice guardrails.
    Never generates or rewrites free-form clinical advice.
    """
    subjects = {
        "en": "Health Review & Refill Reminder - Ramraksha Hospital (Akola)",
        "hi": "स्वास्थ्य परामर्श एवं दवाई स्मरणपत्र - रामरक्षा हॉस्पिटल (अकोला)",
        "mr": "आरोग्य तपासणी व औषध स्मरणपत्र - रामरक्षा हॉस्पिटल (अकोला)"
    }

    ctas = {
        "en": "Contact Clinic Desk",
        "hi": "क्लिनिक डेस्क से संपर्क करें",
        "mr": "क्लिनिक डेस्कशी संपर्क साधा"
    }

    # Template-governed text delivery: zero unauthorized free-form improvisation
    return PersonalizedMessageDraft(
        language=language,
        subject=subjects.get(language, subjects["en"]),
        body=base_text,
        call_to_action=ctas.get(language, ctas["en"])
    )

