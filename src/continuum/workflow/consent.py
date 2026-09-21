"""
Consent governance module:
- Patient outreach is ordinary clinical follow-up: PERMITTED unless patient has explicitly opted out (opt_out = YES).
- Kin escalation discloses health data to a third party: STRICT HARD GATE, blocked unless kin_consent = YES.
- Drafting is NEVER blocked: care coordinators can always draft scripts and prepare messages.
"""

from __future__ import annotations
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from src.continuum.models import Consent, Patient
from src.continuum.audit import log_action


def is_patient_outreach_permitted(db: Session, patient_id: int) -> Tuple[bool, str]:
    """
    Checks if routine clinical outreach to the patient themselves is permitted.
    Permitted by default unless the patient has explicitly opted out.
    """
    consent = db.query(Consent).filter(Consent.patient_id == patient_id).first()
    if consent and consent.opt_out:
        return False, "OPT_OUT: Patient has requested to opt out of routine clinic reminders."

    return True, "OUTREACH_PERMITTED"


def verify_kin_consent(db: Session, patient_id: int) -> Tuple[bool, str]:
    """
    Hard Gate: Disclosing patient health information to a relative or caregiver
    is strictly forbidden without affirmative patient authorization on record.
    
    Returns:
        (is_allowed, reason_message)
    """
    consent = db.query(Consent).filter(Consent.patient_id == patient_id).first()
    if not consent:
        return False, "KIN_ESCALATION_UNAUTHORIZED: No consent agreement found on file."

    if not consent.kin_consent:
        return False, "KIN_ESCALATION_UNAUTHORIZED: Patient has not authorized third-party caregiver contact."

    return True, "KIN_CONSENT_VERIFIED"


def set_patient_opt_out(
    db: Session,
    patient_id: int,
    opt_out: bool,
    user: str = "care_coordinator"
) -> Consent:
    """
    Records a patient's opt-out or opt-in decision.
    """
    consent = db.query(Consent).filter(Consent.patient_id == patient_id).first()
    if not consent:
        consent = Consent(patient_id=patient_id, opt_out=opt_out)
        db.add(consent)
    else:
        consent.opt_out = opt_out

    db.commit()
    log_action(
        db,
        action="PATIENT_OPT_OUT_CHANGED",
        entity_type="Consent",
        entity_id=consent.id,
        user=user,
        details={"patient_id": patient_id, "opt_out": opt_out}
    )
    return consent


def set_kin_consent(
    db: Session,
    patient_id: int,
    kin_consent: bool,
    user: str = "care_coordinator",
    consented_kin_name: Optional[str] = None,
    consented_kin_phone: Optional[str] = None,
) -> Consent:
    """
    Records affirmative patient authorization for caregiver escalation,
    binding consent specifically to the authorized contact details.
    """
    consent = db.query(Consent).filter(Consent.patient_id == patient_id).first()
    patient = db.query(Patient).filter(Patient.id == patient_id).first()

    if kin_consent:
        bound_name = consented_kin_name if consented_kin_name is not None else (patient.kin_name if patient else None)
        bound_phone = consented_kin_phone if consented_kin_phone is not None else (patient.kin_phone if patient else None)
    else:
        bound_name = None
        bound_phone = None

    if not consent:
        consent = Consent(
            patient_id=patient_id,
            kin_consent=kin_consent,
            consented_kin_name=bound_name,
            consented_kin_phone=bound_phone
        )
        db.add(consent)
    else:
        consent.kin_consent = kin_consent
        consent.consented_kin_name = bound_name
        consent.consented_kin_phone = bound_phone

    db.commit()
    log_action(
        db,
        action="KIN_CONSENT_CHANGED",
        entity_type="Consent",
        entity_id=str(consent.id),
        user=user,
        details={
            "patient_id": patient_id,
            "kin_consent": kin_consent,
            "consented_kin_name": bound_name,
            "consented_kin_phone": bound_phone
        }
    )
    return consent
