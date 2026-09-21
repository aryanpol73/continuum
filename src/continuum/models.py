"""
SQLAlchemy relational models for the Continuum platform.
Implements clean separation of episode reason (why flagged) vs status (workflow lifecycle).
"""

from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import relationship
from src.continuum.db import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uh_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False, index=True)
    phone = Column(String(32), nullable=False, index=True)
    gender = Column(String(16), nullable=True)
    age = Column(Integer, nullable=True)
    city = Column(String(64), nullable=True)
    
    # Primary kin / caregiver information
    kin_name = Column(String(128), nullable=True)
    kin_phone = Column(String(32), nullable=True)
    kin_relation = Column(String(64), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    consent = relationship("Consent", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    visits = relationship("Visit", back_populates="patient", cascade="all, delete-orphan", order_by="desc(Visit.visit_date)")
    prescriptions = relationship("Prescription", back_populates="patient", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="patient", cascade="all, delete-orphan")


class Consent(Base):
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Patient outreach is ordinary clinical communication; permitted unless opt_out is True
    opt_out = Column(Boolean, default=False, nullable=False, index=True)
    
    # Hard gate applies strictly to kin escalation (disclosing to a third party)
    kin_consent = Column(Boolean, default=False, nullable=False, index=True)
    consented_kin_name = Column(String(128), nullable=True)
    consented_kin_phone = Column(String(32), nullable=True)
    
    preferred_language = Column(String(16), default="mr", nullable=False)  # 'mr', 'hi', 'en'
    source = Column(String(64), default="REGISTRATION_MASTER", nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="consent")


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    opd_id = Column(String(64), nullable=True, index=True)
    visit_date = Column(Date, nullable=False, index=True)
    doctor_name = Column(String(128), nullable=False)
    department = Column(String(64), default="General Medicine")
    diagnosis_raw = Column(Text, nullable=True)
    investigation_advice = Column(String(128), nullable=True)
    is_diabetes_cohort = Column(Boolean, default=False, index=True)
    followup_after_days = Column(Integer, nullable=True)
    next_visit_due_date = Column(Date, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="visits")
    prescriptions = relationship("Prescription", back_populates="visit", cascade="all, delete-orphan")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    visit_id = Column(Integer, ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    rx_line_id = Column(String(64), nullable=True, index=True)
    opd_id = Column(String(64), nullable=True, index=True)
    
    medication_name = Column(String(128), nullable=False)
    raw_dose = Column(String(64), nullable=False)
    frequency_per_day = Column(Float, default=1.0)
    quantity = Column(Integer, default=30)
    days_supply = Column(Integer, default=30)
    start_date = Column(Date, nullable=False)
    refill_due_date = Column(Date, nullable=False, index=True)
    is_chronic_diabetes_drug = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    visit = relationship("Visit", back_populates="prescriptions")
    patient = relationship("Patient", back_populates="prescriptions")


class Episode(Base):
    """
    Care continuum episode:
    - reason: why patient was flagged (FOLLOWUP_OVERDUE, REFILL_GAP, COMBINED)
    - status: workflow lifecycle state (detected -> contacted -> promised -> returned / unreachable / opted_out)
    - max_overdue_days: ranking key (strictly days overdue, never clinical severity scoring)
    """
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_id = Column(Integer, ForeignKey("visits.id", ondelete="SET NULL"), nullable=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True)
    
    # Reason why flagged (NOT a lifecycle state)
    reason = Column(String(32), nullable=False, index=True)  # FOLLOWUP_OVERDUE, REFILL_GAP, COMBINED
    
    # Workflow status: detected -> contacted -> promised -> returned / unreachable / opted_out
    status = Column(String(32), nullable=False, default="detected", index=True)
    
    due_date = Column(Date, nullable=False, index=True)
    opened_date = Column(Date, nullable=False)
    closed_date = Column(Date, nullable=True)
    closure_reason = Column(String(128), nullable=True)

    # Ranking key: strictly days overdue
    max_overdue_days = Column(Integer, default=0, index=True)
    
    # Signals
    first_drug_exhausted = Column(String(128), nullable=True)
    followup_overdue_days = Column(Integer, default=0)
    refill_overdue_days = Column(Integer, default=0)
    is_refill_only = Column(Boolean, default=False, index=True)
    
    # Closed-loop tracking
    promised_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="episodes")
    outreach_logs = relationship("OutreachLog", back_populates="episode", cascade="all, delete-orphan")


class OutreachLog(Base):
    __tablename__ = "outreach_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    recipient_type = Column(String(16), default="PATIENT", nullable=False)  # PATIENT, KIN
    recipient_phone = Column(String(32), nullable=False)
    channel = Column(String(16), default="WHATSAPP", nullable=False)       # WHATSAPP, CALL, SMS
    message_body = Column(Text, nullable=False)
    status = Column(String(32), default="DRAFTED", nullable=False)         # DRAFTED, SENT, BLOCKED_NO_KIN_CONSENT
    click_to_chat_url = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    episode = relationship("Episode", back_populates="outreach_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    user_or_system = Column(String(64), default="system", nullable=False)
    action = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=True)


class DuplicateCluster(Base):
    __tablename__ = "duplicate_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    candidate_patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    match_reason = Column(String(128), nullable=False)
    confidence_score = Column(Float, nullable=False)
    status = Column(String(32), default="PENDING", nullable=False)  # PENDING, RESOLVED_MERGED, RESOLVED_DISTINCT
    created_at = Column(DateTime, default=datetime.utcnow)


class UploadedReport(Base):
    __tablename__ = "uploaded_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uh_id = Column(String(64), nullable=True, index=True)
    file_name = Column(String(256), nullable=False)
    upload_date = Column(Date, nullable=False, index=True)
    labelled_as = Column(String(64), nullable=True, index=True)
    source = Column(String(64), default="In-house")


class ClinicProfile(Base):
    __tablename__ = "clinic_profile"

    id = Column(Integer, primary_key=True, default=1)
    clinic_name = Column(String(200), default="Continuum Demo Clinic")
    doctor_name = Column(String(200), default="Dr. [Name]")
    clinic_phone = Column(String(20), default="+91 90000 00000")
    clinic_city = Column(String(100), default="Akola")
    default_language = Column(String(5), default="mr")
    is_configured = Column(Boolean, default=False)


def get_clinic_profile(db) -> ClinicProfile:
    p = db.query(ClinicProfile).first()
    if not p:
        p = ClinicProfile(
            id=1,
            clinic_name="Continuum Demo Clinic",
            doctor_name="Dr. [Name]",
            clinic_phone="+91 90000 00000",
            clinic_city="Akola",
            default_language="mr",
            is_configured=False
        )
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


