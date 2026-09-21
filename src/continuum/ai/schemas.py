"""
Pydantic data contracts for AI document extraction and message generation.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedMedication(BaseModel):
    medication_name: str = Field(..., description="Brand or generic medication name")
    dosage_pattern: str = Field(..., description="Prescription frequency, e.g. '1-0-1' or 'OD'")
    quantity: int = Field(default=30, description="Total number of units/tablets prescribed")
    duration_days: Optional[int] = Field(default=None, description="Duration in days if specified")
    instructions: Optional[str] = Field(default=None, description="Special instructions, e.g. 'After food'")
    confidence: float = Field(default=0.9, description="Extraction confidence score from 0.0 to 1.0")


class ExtractedPrescriptionDoc(BaseModel):
    clinic_name: Optional[str] = Field(default=None, description="Detected clinic or hospital name")
    doctor_name: Optional[str] = Field(default=None, description="Detected doctor or consultant name")
    patient_name: Optional[str] = Field(default=None, description="Detected patient full name")
    patient_uhid: Optional[str] = Field(default=None, description="Detected hospital registration number / UHID")
    visit_date: Optional[str] = Field(default=None, description="Date of prescription in YYYY-MM-DD")
    diagnosis: Optional[str] = Field(default=None, description="Detected diagnosis or clinical impression")
    next_review_date: Optional[str] = Field(default=None, description="Next suggested follow-up date")
    medications: List[ExtractedMedication] = Field(default_factory=list, description="List of prescribed medicines")
    overall_confidence: float = Field(default=0.85, description="Overall document extraction confidence score")


class PersonalizedMessageDraft(BaseModel):
    language: str = Field(default="en", description="Target language code: 'en', 'hi', or 'mr'")
    subject: str = Field(..., description="Short message subject or header")
    body: str = Field(..., description="Full message body text")
    call_to_action: str = Field(..., description="Button or action label")
