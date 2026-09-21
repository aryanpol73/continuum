# Continuum — Clinical Scope & Medico-Legal Boundaries
**Clinic Context:** Ramraksha Clinic & Chronic Care Center, Pune, Maharashtra  
**Supervising Diabetologist:** Dr. Vinayak Joshi, MBBS, MD (Internal Medicine)  
**Document Version:** 1.0.0 (Doctor-Approved & Signed)

---

## 1. Clinical Purpose & Operational Scope

Continuum is an ambulatory chronic care coordination, appointment retention, and prescription adherence monitoring platform designed for outpatient clinics managing chronic non-communicable diseases (primarily **Type 2 Diabetes Mellitus** and associated comorbidities such as Essential Hypertension and Dyslipidemia).

### IN SCOPE:
1. **Longitudinal Care Gap Identification**:
   - Flagging patients whose scheduled review consultations have elapsed past clinical grace periods (>14 days).
   - Forecasting medication stock exhaustion based on prescribed daily frequency and dispensed quantities.
   - Identifying patients due for quarterly or biannual HbA1c screening.
2. **Care Coordinator Worklist Prioritization**:
   - Ranking overdue episodes based on clinical severity, chronic condition complexity, insulin usage, and adherence history.
3. **Multi-lingual Patient Engagement**:
   - Drafting culturally sensitive, polite follow-up and refill reminders in English, Hindi, and Marathi.
   - Formatting official WhatsApp click-to-chat links for care coordinator dispatch.
4. **Caregiver Escalation Queue**:
   - Providing secondary outreach paths to primary family members when chronic patients become unresponsive, strictly gated by express patient consent.
5. **Human-in-the-Loop Document Verification**:
   - Extracting structured data from paper prescriptions and discharge summaries for staff review prior to database ingestion.

### STRICTLY OUT OF SCOPE:
1. **Autonomous Medical Diagnosing**:
   - Continuum must NEVER issue diagnoses, interpret test results (e.g. telling a patient their blood sugar is dangerously high), or modify prescriptions autonomously.
2. **Autonomous Medication Modification**:
   - Continuum must NEVER advise a patient to titrate insulin doses, start new medications, stop existing drugs, or take alternative supplements.
3. **Emergency Medical Services**:
   - Continuum is NOT an emergency triage system. Any acute symptoms (e.g. chest pain, severe hypoglycemia, ketoacidosis, unconsciousness) must direct patients to an immediate emergency department.
4. **Unconsented Patient Contact**:
   - Continuum must NEVER dispatch messages or allow drafts to be created for patients or relatives who have opted out or not granted explicit consent.

---

## 2. Medico-Legal Safeguards & Consent Governance

1. **Hard Code-Level Consent Gates**:
   - The system architecture enforces a hard gate in `src.continuum.workflow.consent`. No outreach payload can be rendered without verified consent.
2. **Separation of Kin Consent**:
   - Patient consent to receive personal messages does NOT imply permission to contact relatives. Kin escalation requires a distinct, affirmative authorization.
3. **Append-Only Immutable Audit Log**:
   - Every system interaction, data import, duplicate patient merge, rule evaluation, message draft, and status change is logged with UTC timestamp, actor ID, and JSON payload.
4. **Data Privacy & PII Protection**:
   - Raw patient exports and uploaded images are strictly isolated in local directories excluded from version control (`.gitignore`).

---

## 3. Physician Sign-off & Clinical Validation

I have reviewed the clinical rules, dosing parsing regexes, due date thresholds (14-day follow-up grace, 7-day refill buffer), and multilingual message templates. They accurately reflect standard outpatient diabetology practices at Ramraksha Clinic and ensure patient safety.

**Dr. Vinayak Joshi, MBBS, MD**  
*Consulting Physician & Diabetologist*  
*Ramraksha Clinic & Chronic Care Center, Pune*
