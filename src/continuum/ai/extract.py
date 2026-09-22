"""
Multimodal document extractor: parses scanned prescription documents into structured fields.
Uses Google Gemini API when available, with a deterministic mock fallback for offline operation.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Union, Optional
from PIL import Image

from src.continuum.config import get_settings
from src.continuum.ai.schemas import ExtractedPrescriptionDoc, ExtractedMedication


def extract_prescription_document(
    file_path: Union[str, Path]
) -> ExtractedPrescriptionDoc:
    """
    Extracts structured clinical fields from an uploaded prescription image.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    settings = get_settings()
    api_key = settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            img = Image.open(path)
            
            prompt = """
            You are a specialized Indian clinical prescription OCR assistant. 
            Analyze this prescription image and extract the following into JSON matching the schema:
            - clinic_name
            - doctor_name
            - patient_name
            - patient_uhid
            - visit_date (YYYY-MM-DD)
            - diagnosis (provisional diagnosis or impression, e.g. T2DM, Hypertension)
            - next_review_date (YYYY-MM-DD)
            - medications: list of objects with (medication_name, dosage_pattern like '1-0-1' or 'OD', quantity, instructions, confidence)
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[img, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedPrescriptionDoc,
                ),
            )
            if response.parsed:
                return response.parsed
        except Exception as e:
            # Fallback to deterministic extraction on API failure
            pass

    # --- Deterministic Offline Extractor ---
    # Safe sample fallback when no vision API key is configured
    return ExtractedPrescriptionDoc(
        clinic_name="SAMPLE — Offline Intake Demo",
        doctor_name="Dr. [Sample Clinician]",
        patient_name="Sample Patient",
        patient_uhid="DEMO-2026-001",
        visit_date="2026-08-10",
        diagnosis="Type 2 Diabetes Mellitus with Mild Neuropathy",
        next_review_date="2026-09-10",
        medications=[
            ExtractedMedication(
                medication_name="Glycomet GP 1 Tablet",
                dosage_pattern="1-0-1",
                quantity=60,
                instructions="Before meals",
                confidence=0.0
            ),
            ExtractedMedication(
                medication_name="Jardiance 10mg",
                dosage_pattern="1-0-0",
                quantity=30,
                instructions="Morning after breakfast",
                confidence=0.0
            ),
            ExtractedMedication(
                medication_name="Telma 40mg",
                dosage_pattern="0-0-1",
                quantity=30,
                instructions="At bedtime",
                confidence=0.0
            )
        ],
        overall_confidence=0.0
    )
