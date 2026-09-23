"""
Threaded patient-clinic messaging services.
Manages persistent conversation history, file attachment persistence,
and urgent triage tagging.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.continuum.config import get_base_dir
from src.continuum.models import Patient, PatientMessage
from src.continuum.messaging.triage import is_urgent
from src.continuum.audit import log_action


def get_thread(db: Session, patient_id: int, limit: int = 100) -> List[PatientMessage]:
    """Returns chronological conversation history between patient and clinic."""
    return (
        db.query(PatientMessage)
        .filter(PatientMessage.patient_id == patient_id)
        .order_by(PatientMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def post_message(
    db: Session,
    patient_id: int,
    direction: str,
    body: Optional[str] = None,
    topic: Optional[str] = None,
    uploaded_file: Any = None,
    author: str = "patient",
) -> PatientMessage:
    """Persists message, processes attachments, flags urgent symptoms, and logs audit."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError(f"Patient ID {patient_id} not found")

    attachment_path, attachment_name, attachment_mime = None, None, None

    if uploaded_file is not None:
        attachment_name = getattr(uploaded_file, "name", "attachment")
        attachment_mime = getattr(uploaded_file, "type", "application/octet-stream")
        dest_dir = get_base_dir() / "data" / "uploads" / "messages"
        dest_dir.mkdir(parents=True, exist_ok=True)
        clean_name = Path(attachment_name).name.replace(" ", "_")
        ts = int(datetime.utcnow().timestamp())
        file_path = dest_dir / f"{patient.uh_id}_{ts}_{clean_name}"

        if hasattr(uploaded_file, "getbuffer"):
            file_path.write_bytes(uploaded_file.getbuffer())
        elif hasattr(uploaded_file, "read"):
            content = uploaded_file.read()
            if isinstance(content, str):
                content = content.encode("utf-8")
            file_path.write_bytes(content)
        elif isinstance(uploaded_file, bytes):
            file_path.write_bytes(uploaded_file)
        attachment_path = str(file_path)

    urgent_flag = False
    if direction == "IN" and body:
        urgent_flag = is_urgent(body)

    msg = PatientMessage(
        patient_id=patient_id,
        direction=direction,
        category="CHAT_MESSAGE",
        topic=topic,
        body=body or "",
        attachment_path=attachment_path,
        attachment_name=attachment_name,
        attachment_mime=attachment_mime,
        urgent_flagged=urgent_flag,
        created_at=datetime.utcnow(),
    )
    db.add(msg)

    # When clinic replies, mark prior unread inbound messages as read
    if direction == "OUT":
        now = datetime.utcnow()
        for prev in (
            db.query(PatientMessage)
            .filter(
                PatientMessage.patient_id == patient_id,
                PatientMessage.direction == "IN",
                PatientMessage.read_at.is_(None),
            )
            .all()
        ):
            prev.read_at = now
            prev.handled_by = author

    db.flush()

    action = "PATIENT_CHAT_MESSAGE_RECEIVED" if direction == "IN" else "CLINIC_CHAT_MESSAGE_SENT"
    log_action(
        db,
        action=action,
        entity_type="PatientMessage",
        entity_id=str(msg.id),
        user=author,
        details={
            "patient_id": patient_id,
            "direction": direction,
            "topic": topic,
            "urgent": urgent_flag,
            "has_attachment": bool(attachment_path),
        },
    )
    db.commit()
    db.refresh(msg)
    return msg


def mark_thread_read(db: Session, patient_id: int, reader: str = "care_coordinator") -> int:
    """Marks all unread inbound messages for a patient as handled/read."""
    unread_messages = (
        db.query(PatientMessage)
        .filter(
            PatientMessage.patient_id == patient_id,
            PatientMessage.direction == "IN",
            PatientMessage.read_at.is_(None),
        )
        .all()
    )
    if not unread_messages:
        return 0

    now = datetime.utcnow()
    for m in unread_messages:
        m.read_at = now
        m.handled_by = reader

    log_action(
        db,
        action="PATIENT_THREAD_READ",
        entity_type="Patient",
        entity_id=str(patient_id),
        user=reader,
        details={"read_count": len(unread_messages)},
    )
    db.commit()
    return len(unread_messages)


def get_thread_summaries(db: Session) -> List[Dict[str, Any]]:
    """Returns thread summary for every patient who has at least one message."""
    msgs = db.query(PatientMessage).order_by(PatientMessage.created_at.desc()).all()
    if not msgs:
        return []

    by_patient: Dict[int, List[PatientMessage]] = {}
    for m in msgs:
        by_patient.setdefault(m.patient_id, []).append(m)

    summaries = []
    for pid, p_msgs in by_patient.items():
        patient = p_msgs[0].patient or db.query(Patient).filter(Patient.id == pid).first()
        if not patient:
            continue

        last_m = p_msgs[0]
        unread_in = sum(1 for m in p_msgs if m.direction == "IN" and m.read_at is None)
        has_urgent = any(m.urgent_flagged for m in p_msgs if m.direction == "IN" and m.read_at is None)

        preview_body = last_m.body
        if not preview_body and last_m.attachment_name:
            preview_body = f"📎 {last_m.attachment_name}"
        elif not preview_body:
            preview_body = "Empty message"

        summaries.append({
            "patient_id": patient.id,
            "name": patient.name,
            "uh_id": patient.uh_id,
            "phone": patient.phone or "",
            "last_message_body": preview_body,
            "last_message_at": last_m.created_at,
            "unread_in_count": unread_in,
            "has_urgent": has_urgent,
        })

    summaries.sort(
        key=lambda s: (1 if s["has_urgent"] else 0, s["last_message_at"] or datetime.min),
        reverse=True,
    )
    return summaries
