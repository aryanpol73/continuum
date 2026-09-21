"""
Ingestion loader for Continuum:
Supports both the Akola Ramraksha Hospital OPD relational export files:
    - patients.csv
    - opd_visits.csv
    - clinical_notes.csv
    - prescriptions.csv
    - contacts_consent.csv
As well as monolithic/legacy clinic exports.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, Any, Union
from sqlalchemy.orm import Session

from src.continuum.models import Patient, Consent, Visit, Prescription, UploadedReport
from src.continuum.ingest.normalize import (
    normalize_phone, normalize_date, normalize_name, normalize_gender
)
from src.continuum.engine.cohort import classify_diabetes_diagnosis
from src.continuum.audit import log_action


def ingest_akola_dataset(data_dir: Union[str, Path], db: Session, user: str = "system") -> Dict[str, int]:
    """
    Ingests the modular Ramraksha Hospital OPD software export files into normalized tables.
    """
    path = Path(data_dir)
    stats = {
        "patients_ingested": 0,
        "visits_ingested": 0,
        "prescriptions_ingested": 0,
        "consents_ingested": 0
    }

    # 1. Ingest patients.csv
    pts_file = path / "patients.csv"
    if pts_file.exists():
        with open(pts_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uh_id = row.get("UH_ID", "").strip()
                if not uh_id:
                    continue

                existing = db.query(Patient).filter(Patient.uh_id == uh_id).first()
                if not existing:
                    # Construct full name from F, M, L
                    name_parts = [row.get("F", ""), row.get("M", ""), row.get("L", "")]
                    full_name = " ".join([p.strip() for p in name_parts if p and p.strip()])
                    phone_norm, _ = normalize_phone(row.get("Mobile1"))

                    try:
                        age = int(float(row.get("Age", 0)))
                    except (ValueError, TypeError):
                        age = None

                    patient = Patient(
                        uh_id=uh_id,
                        name=normalize_name(full_name),
                        phone=phone_norm or "+910000000000",
                        gender=normalize_gender(row.get("Sex")),
                        age=age,
                        city=row.get("CityPlace", "Akola")
                    )
                    db.add(patient)
                    stats["patients_ingested"] += 1
        db.commit()

    # 2. Ingest contacts_consent.csv
    contacts_file = path / "contacts_consent.csv"
    if contacts_file.exists():
        with open(contacts_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uh_id = row.get("UH_ID", "").strip()
                if not uh_id:
                    continue

                patient = db.query(Patient).filter(Patient.uh_id == uh_id).first()
                if patient:
                    kin_phone_norm, _ = normalize_phone(row.get("KinMobile"))
                    patient.kin_name = normalize_name(row.get("KinName")) if row.get("KinName") else None
                    patient.kin_relation = row.get("KinRelation") or None
                    patient.kin_phone = kin_phone_norm

                    opt_out = (row.get("OptOut", "NO").upper() == "YES")
                    escalation_consent = (row.get("EscalationConsent", "NO").upper() == "YES")
                    outreach_consent = not opt_out
                    lang_raw = row.get("PreferredLanguage", "Marathi")
                    lang_code = "mr" if "marathi" in lang_raw.lower() else ("hi" if "hindi" in lang_raw.lower() else "en")

                    existing_consent = db.query(Consent).filter(Consent.patient_id == patient.id).first()
                    if not existing_consent:
                        consent = Consent(
                            patient_id=patient.id,
                            opt_out=opt_out,
                            kin_consent=escalation_consent,
                            preferred_language=lang_code,
                            source="CLINIC_REGISTRATION"
                        )
                        db.add(consent)
                        stats["consents_ingested"] += 1
                    else:
                        existing_consent.opt_out = opt_out
                        existing_consent.kin_consent = escalation_consent
                        existing_consent.preferred_language = lang_code
        db.commit()

    # Build patient_id lookup cache
    patient_id_map = {p.uh_id: p.id for p in db.query(Patient.uh_id, Patient.id).all()}

    # 3. Read clinical_notes.csv into lookup dict
    notes_file = path / "clinical_notes.csv"
    notes_lookup = {}
    if notes_file.exists():
        with open(notes_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                opd_id = row.get("OPD_ID", "").strip()
                notes_lookup[opd_id] = {
                    "diagnosis": row.get("Diagnosis", ""),
                    "investigation_advice": row.get("InvestigationAdvice", "")
                }

    # 4. Ingest opd_visits.csv
    visits_file = path / "opd_visits.csv"
    opd_id_to_visit_id = {}
    seen_opd_ids = set()
    if visits_file.exists():
        with open(visits_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                opd_id = row.get("OPD_ID", "").strip()
                if not opd_id or opd_id in seen_opd_ids:
                    continue
                seen_opd_ids.add(opd_id)

                uh_id = row.get("UH_ID", "").strip()
                pid = patient_id_map.get(uh_id)
                if not pid:
                    continue

                v_date = normalize_date(row.get("OPDDate"))
                fu_date = normalize_date(row.get("FollowUpDate"))
                fu_after = int(row.get("FollowUpAfterDays")) if row.get("FollowUpAfterDays") and str(row.get("FollowUpAfterDays")).isdigit() else None
                note_info = notes_lookup.get(opd_id, {})
                dx_text = note_info.get("diagnosis", "") if isinstance(note_info, dict) else ""
                inv_advice = note_info.get("investigation_advice", "") if isinstance(note_info, dict) else ""
                is_dm, _, _ = classify_diabetes_diagnosis(dx_text)

                visit = Visit(
                    patient_id=pid,
                    opd_id=opd_id,
                    visit_date=v_date,
                    doctor_name=row.get("Consultant", "Dr. Ashwin Sadavarte"),
                    department="Diabetology & Medicine",
                    diagnosis_raw=dx_text,
                    investigation_advice=inv_advice or None,
                    is_diabetes_cohort=is_dm,
                    followup_after_days=fu_after,
                    next_visit_due_date=fu_date
                )
                db.add(visit)
                db.flush()
                opd_id_to_visit_id[opd_id] = visit.id
                stats["visits_ingested"] += 1
        db.commit()

    # 5. Ingest prescriptions.csv
    rx_file = path / "prescriptions.csv"
    seen_rx_line_ids = set()
    if rx_file.exists():
        with open(rx_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rx_line_id = row.get("RxLineID", "").strip()
                if rx_line_id and rx_line_id in seen_rx_line_ids:
                    continue
                if rx_line_id:
                    seen_rx_line_ids.add(rx_line_id)

                opd_id = row.get("OPD_ID", "").strip()
                uh_id = row.get("UH_ID", "").strip()
                vid = opd_id_to_visit_id.get(opd_id)
                pid = patient_id_map.get(uh_id)

                if not vid or not pid:
                    continue

                rx_date = normalize_date(row.get("RxDate"))
                med_name = row.get("DrugName", "").strip()
                raw_dose = row.get("Dose", "1-0-1").strip()
                qty_val = row.get("Qty", "")
                try:
                    qty = int(qty_val) if qty_val and str(qty_val).strip() else 0
                except ValueError:
                    qty = 0

                rx = Prescription(
                    visit_id=vid,
                    patient_id=pid,
                    rx_line_id=row.get("RxLineID"),
                    opd_id=opd_id,
                    medication_name=med_name,
                    raw_dose=raw_dose,
                    quantity=qty,
                    start_date=rx_date,
                    refill_due_date=rx_date
                )
                db.add(rx)
                stats["prescriptions_ingested"] += 1
        db.commit()

    # 6. Ingest uploaded_reports.csv
    reports_file = path / "uploaded_reports.csv"
    stats["reports_ingested"] = 0
    if reports_file.exists():
        with open(reports_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                u_date = normalize_date(row.get("UploadDate"))
                if not u_date:
                    continue
                rep = UploadedReport(
                    uh_id=row.get("UH_ID", "").strip() or None,
                    file_name=row.get("FileName", "").strip(),
                    upload_date=u_date,
                    labelled_as=row.get("LabelledAs", "").strip() or None,
                    source=row.get("Source", "In-house")
                )
                db.add(rep)
                stats["reports_ingested"] += 1
        db.commit()

    log_action(
        db,
        action="AKOLA_DATASET_INGESTED",
        entity_type="Directory",
        entity_id=str(data_dir),
        user=user,
        details=stats
    )

    return stats
