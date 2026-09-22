"""
Page 4: Prescription & Clinical Document Verification Workbench.
Upload scanned prescriptions, review AI vision extraction fields side-by-side, and commit verified records.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.config import get_base_dir
from src.continuum.ai.extract import extract_prescription_document
from src.continuum.models import Patient, Visit, Prescription, Consent
from src.continuum.ingest.normalize import normalize_date, normalize_name, normalize_phone
from src.continuum.engine.dosing import process_prescription_dosing
from src.continuum.engine.cohort import classify_diabetes_diagnosis
from src.continuum.audit import log_action
from app.components.style import apply_theme

st.set_page_config(page_title="Document Verify | Continuum", page_icon="📄", layout="wide")
apply_theme()
from app.components.nav import render_sidebar, render_context_bar
render_sidebar()

st.title("Clinical Document & Prescription Verification")
st.caption("Multimodal vision extraction with human-in-the-loop verification before committing to clinical records.")
render_context_bar()

uploads_dir = get_base_dir() / "data" / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

uploaded_file = st.file_uploader(
    "Upload Prescription Scan or Discharge Summary",
    type=["png", "jpg", "jpeg"],
    help="Supports handwritten or printed clinical prescriptions."
)

if uploaded_file is not None:
    # Save temp file
    save_path = uploads_dir / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    col_img, col_form = st.columns([1, 1])

    with col_img:
        st.subheader("Original Document")
        image = Image.open(save_path)
        st.image(image, use_container_width=True, caption=uploaded_file.name)

    with col_form:
        st.subheader("AI Vision Extracted Fields")
        
        with st.spinner("Analyzing document with clinical OCR vision model..."):
            extracted = extract_prescription_document(save_path)

        if extracted.overall_confidence == 0.0:
            st.warning("⚠️ No vision API key configured — displaying offline sample extraction.")

        st.markdown(
            f"""
            <span style="background: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.8rem;">
                Confidence Score: {int(extracted.overall_confidence * 100)}%
            </span>
            """,
            unsafe_allow_html=True
        )

        # Verification form
        with st.form("verify_prescription_form"):
            c1, c2 = st.columns(2)
            with c1:
                p_name = st.text_input("Patient Name", value=extracted.patient_name or "")
                p_uhid = st.text_input("Patient UHID", value=extracted.patient_uhid or "RAM-2024-NEW")
            with c2:
                doc_name = st.text_input("Doctor Name", value=extracted.doctor_name or "Dr. Vinayak Joshi")
                v_date = st.text_input("Consultation Date (YYYY-MM-DD)", value=extracted.visit_date or "2026-08-10")

            diagnosis = st.text_input("Impression / Diagnosis", value=extracted.diagnosis or "")
            next_review = st.text_input("Next Review Due Date (YYYY-MM-DD)", value=extracted.next_review_date or "2026-09-10")

            st.markdown("##### Prescribed Medications")
            med_rows = []
            for i, med in enumerate(extracted.medications):
                st.markdown(f"**Medicine {i+1}:** `{med.medication_name}` (Confidence: {int(med.confidence*100)}%)")
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    m_name = st.text_input(f"Name #{i+1}", value=med.medication_name, key=f"mname_{i}")
                with mc2:
                    m_dose = st.text_input(f"Dose Pattern #{i+1}", value=med.dosage_pattern, key=f"mdose_{i}")
                with mc3:
                    m_qty = st.number_input(f"Dispensed Qty #{i+1}", value=med.quantity, step=1, key=f"mqty_{i}")

                med_rows.append({"name": m_name, "dose": m_dose, "qty": m_qty})

            submit_commit = st.form_submit_button("Approve & Commit to Database", type="primary")

            if submit_commit:
                Session = get_session_factory()
                with Session() as db:
                    # 1. Upsert Patient
                    patient = db.query(Patient).filter(Patient.uh_id == p_uhid.strip()).first()
                    if not patient:
                        patient = Patient(
                            uh_id=p_uhid.strip(),
                            name=normalize_name(p_name),
                            phone="+919800000000",
                            gender="Unknown"
                        )
                        db.add(patient)
                        db.flush()
                        # Default consent
                        db.add(Consent(patient_id=patient.id, opt_out=False, kin_consent=False))

                    # 2. Add Visit
                    visit_d = normalize_date(v_date)
                    next_d = normalize_date(next_review)
                    is_dm, _, _ = classify_diabetes_diagnosis(diagnosis)

                    visit = Visit(
                        patient_id=patient.id,
                        visit_date=visit_d,
                        doctor_name=doc_name,
                        diagnosis_raw=diagnosis,
                        next_visit_due_date=next_d,
                        is_diabetes_cohort=is_dm
                    )
                    db.add(visit)
                    db.flush()

                    # 3. Add Prescriptions
                    for m in med_rows:
                        rx = Prescription(
                            visit_id=visit.id,
                            patient_id=patient.id,
                            medication_name=m["name"],
                            raw_dose=m["dose"],
                            quantity=int(m["qty"]),
                            start_date=visit_d,
                            refill_due_date=visit_d
                        )
                        process_prescription_dosing(rx)
                        db.add(rx)

                    db.commit()

                    log_action(
                        db,
                        action="PRESCRIPTION_DOC_VERIFIED",
                        entity_type="Visit",
                        entity_id=visit.id,
                        user="care_coordinator",
                        details={"file_name": uploaded_file.name, "uhid": p_uhid}
                    )

                    st.success(f"Prescription successfully committed for {patient.name} ({patient.uh_id})!")
else:
    st.info("Please upload a prescription image to start OCR verification.")
