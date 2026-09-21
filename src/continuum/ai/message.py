"""
AI message personalization module.
Enhances outreach messages with empathy and culturally tailored tone while strictly enforcing medical non-advice guardrails.
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
    Polishes an outreach message while respecting strict medical safety guardrails.
    """
    settings = get_settings()
    api_key = settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            prompt = f"""
            You are a polite, compassionate care coordinator at Ramraksha Clinic in Pune, India.
            Rewrite the following outreach reminder in {language} (language code) to make it warm, respectful, and clear.
            
            STRICT GUARDRAILS:
            1. DO NOT give any clinical diagnoses or medication adjustments.
            2. ONLY remind about appointment review or medication supply stock.
            3. Address the patient respectfully as {patient_name} ji.
            
            Original Message:
            {base_text}
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PersonalizedMessageDraft,
                ),
            )
            if response.parsed:
                return response.parsed
        except Exception:
            pass

    # Fallback to standard base text
    subjects = {
        "en": "Health Review & Refill Reminder - Ramraksha Clinic",
        "hi": "स्वास्थ्य परामर्श एवं दवाई स्मरणपत्र - रामरक्षा क्लिनिक",
        "mr": "आरोग्य तपासणी स्मरणपत्र - रामरक्षा क्लिनिक"
    }

    ctas = {
        "en": "Book Consultation",
        "hi": "परामर्श बुक करें",
        "mr": "तपासणी निश्चित करा"
    }

    return PersonalizedMessageDraft(
        language=language,
        subject=subjects.get(language, subjects["en"]),
        body=base_text,
        call_to_action=ctas.get(language, ctas["en"])
    )
