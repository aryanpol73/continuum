# Continuum — Clinical Scope & Medico-Legal Boundaries
**Clinic Context:** Ramraksha Hospital, Station Road, Akola, Maharashtra  
**Supervising Diabetologist:** Dr. Ashwin Sadavarte, MBBS, MD (Medicine), Diabetologist  
**Document Version:** 1.1.0 (Doctor-Approved & Aligned)

---

## 1. Clinical Purpose & Operational Scope

Continuum is an ambulatory chronic care coordination, appointment retention, and prescription refill tracking platform designed for outpatient clinics managing chronic non-communicable diseases (specifically **Type 2 Diabetes Mellitus** and associated comorbidities).

### IN SCOPE:
1. **Longitudinal Care Gap Identification**:
   - Flagging patients whose scheduled review consultations have elapsed past clinical grace periods (>7 days).
   - Forecasting medication stock exhaustion across all prescription lines (`Qty / doses_per_day`) to identify the earliest-exhausting drug (>7 days past supply exhaustion).
   - Catching "refill-only gaps": patients whose follow-up appointment is still weeks away, but whose vital diabetes medicines ran out >7 days ago.
2. **Care Coordinator Worklist Prioritization**:
   - Ranking overdue episodes strictly by days overdue (`max_overdue_days`, descending). Never by clinical severity, disease stage, or diagnostic interpretation.
3. **Multi-lingual Patient Engagement**:
   - Populating doctor-approved templates with administrative facts in English, Hindi, and Marathi.
   - Formatting official WhatsApp click-to-chat links (`wa.me/91XXXXXXXXXX`) for care coordinator dispatch.
4. **Caregiver Escalation Hard Gate**:
   - Providing secondary outreach paths to registered family members when chronic patients become unreachable, strictly gated by express patient consent (`kin_consent = YES`).
5. **Human-in-the-Loop Document Verification**:
   - Extracting structured data from paper prescriptions and lab reports for staff review prior to database ingestion.
6. **Closed-Loop Attendance Verification**:
   - Automatically verifying and closing episodes when the patient attends an in-person OPD consultation.

### STRICTLY OUT OF SCOPE:
1. **Autonomous Medical Diagnosing & Advice**:
   - Continuum must NEVER issue diagnoses, clinical claims about physiological consequences, or autonomous advice.
2. **Autonomous Medication Modification**:
   - Continuum must NEVER advise a patient to titrate doses, start new medications, or stop existing drugs.
3. **Emergency Medical Services**:
   - Continuum is NOT an emergency triage system.
4. **Unconsented Kin Disclosure**:
   - Continuum must NEVER disclose patient status to third parties/kin without affirmative recorded consent (`kin_consent = YES`).

---

## 2. Medico-Legal Safeguards & Consent Governance

1. **Proportional Consent Gating**:
   - Routine clinic-to-patient follow-up is ordinary clinical care, permitted unless `opt_out = YES`.
   - Kin escalation is hard-gated: third-party contact is blocked in code without affirmative authorization.
   - Drafting call scripts and messages is never blocked.
2. **Append-Only Immutable Audit Log**:
   - Every system interaction, data import, duplicate patient merge, rule evaluation, message draft, and status change is logged with UTC timestamp, actor ID, and JSON payload.
3. **Data Privacy & PII Protection**:
   - Raw patient exports and uploaded images are strictly isolated in local directories excluded from version control (`.gitignore`).

---

## 3. Physician Sign-off & Clinical Validation

I have reviewed the clinical rules, dosing parsing patterns, due date thresholds (7-day follow-up grace, 7-day refill grace after supply exhaustion), and multilingual message templates. They accurately reflect outpatient diabetology practices at Ramraksha Hospital (Akola) and ensure patient safety.

**Dr. Ashwin Sadavarte, MBBS, MD**  
*Consulting Physician & Diabetologist*  
*Ramraksha Hospital, Akola, Maharashtra*

