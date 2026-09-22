"""
Outreach message rendering engine:
Fills placeholders in doctor-approved templates. Never composes free-form health advice.
Drafting is NEVER blocked so coordinators can always prepare scripts.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from src.continuum.config import get_template, get_settings, get_today
from src.continuum.models import Patient, Episode, Visit, Prescription, OutreachLog, get_clinic_profile
from src.continuum.workflow.consent import is_patient_outreach_permitted, verify_kin_consent
from src.continuum.outreach.whatsapp import build_whatsapp_link
from src.continuum.audit import log_action


def render_outreach_draft(
    db: Session,
    episode_id: int,
    recipient_type: str = "PATIENT",
    override_language: Optional[str] = None,
    user: str = "care_coordinator",
    persist: bool = False
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Renders a doctor-approved outreach message draft.
    Drafting is never blocked. Permission status is returned in the payload.
    """
    ep = db.query(Episode).filter(Episode.id == episode_id).first()
    if not ep:
        return False, f"Episode #{episode_id} does not exist.", None

    patient = ep.patient
    settings = get_settings()
    clinic_info = settings.get("clinic", {})
    today = get_today()

    # Determine recipient phone and authorization
    is_dispatch_allowed = True
    dispatch_warning = ""

    if recipient_type == "KIN":
        allowed, reason = verify_kin_consent(db, patient.id)
        if not allowed:
            is_dispatch_allowed = False
            dispatch_warning = "Caregiver contact is NOT authorized by patient on record."
        recipient_phone = patient.kin_phone or ""
    else:
        allowed, reason = is_patient_outreach_permitted(db, patient.id)
        if not allowed:
            is_dispatch_allowed = False
            dispatch_warning = "Patient has requested to opt out of routine reminders."
        recipient_phone = patient.phone

    # Determine template
    if recipient_type == "KIN":
        template_id = "kin_escalation"
    elif ep.reason == "REFILL_GAP":
        template_id = "refill_gap"
    else:
        template_id = "followup_overdue"

    template_data = get_template(template_id)
    if not template_data:
        return False, f"Template '{template_id}' not found.", None

    # Language resolution (default Marathi for Akola context)
    pref_lang = override_language or (patient.consent.preferred_language if patient.consent else "mr")
    lang_dict = template_data.get("languages", {})
    lang_data = lang_dict.get(pref_lang) or lang_dict.get("mr") or lang_dict.get("en", {})

    profile = get_clinic_profile(db)
    clinic_name = profile.clinic_name or "Continuum Demo Clinic"
    doctor_name = profile.doctor_name or "Dr. [Name]"
    clinic_phone = profile.clinic_phone or "+91 90000 00000"

    if ep.visit_id:
        v = db.query(Visit).filter(Visit.id == ep.visit_id).first()
        if v and v.doctor_name and v.doctor_name.strip():
            doctor_name = v.doctor_name

    med_name = ep.first_drug_exhausted or "your regular diabetes medications"
    refill_date_str = str(ep.due_date) if ep.due_date else ""

    params = {
        "patient_name": patient.name,
        "kin_name": patient.kin_name or "Caregiver",
        "relation": patient.kin_relation or "relative",
        "clinic_name": clinic_name,
        "doctor_name": doctor_name,
        "due_date": str(ep.due_date),
        "refill_due_date": refill_date_str,
        "days_overdue": str(ep.max_overdue_days),
        "medication_name": med_name,
        "clinic_phone": clinic_phone,
        "appointment_link": clinic_info.get("appointment_link", "https://clinic.example.com/book")
    }

    body = lang_data.get("body", "")
    subject = lang_data.get("subject", "")

    # Clean placeholder substitution
    for k, v in params.items():
        body = body.replace(f"{{{k}}}", str(v))
        subject = subject.replace(f"{{{k}}}", str(v))

    wa_url = build_whatsapp_link(recipient_phone, body) if recipient_phone else ""

    log_id = None
    if persist:
        # Record drafted message only when explicitly requested
        log_entry = OutreachLog(
            episode_id=ep.id,
            patient_id=patient.id,
            recipient_type=recipient_type,
            recipient_phone=recipient_phone,
            channel="WHATSAPP",
            message_body=body,
            status="DRAFTED",
            click_to_chat_url=wa_url if is_dispatch_allowed else None
        )
        db.add(log_entry)
        db.commit()

        log_action(
            db,
            action="OUTREACH_DRAFT_PREPARED",
            entity_type="OutreachLog",
            entity_id=log_entry.id,
            user=user,
            details={
                "episode_id": ep.id,
                "recipient_type": recipient_type,
                "language": pref_lang,
                "is_dispatch_allowed": is_dispatch_allowed
            }
        )
        log_id = log_entry.id

    return True, "Draft prepared.", {
        "outreach_log_id": log_id,
        "recipient_phone": recipient_phone,
        "recipient_type": recipient_type,
        "language": pref_lang,
        "subject": subject,
        "body": body,
        "whatsapp_url": wa_url,
        "is_dispatch_allowed": is_dispatch_allowed,
        "dispatch_warning": dispatch_warning
    }
