# Continuum — Clinical Demonstration Walkthrough Script
**Target Audience:** Clinical Directors, Diabetologists, and Clinic Operations Teams  
**Setting:** Ramraksha Clinic & Chronic Care Center  

---

## Act 1: The Outpatient Reality & Cohort Selection
1. **The Challenge**:
   - Outpatient clinics manage hundreds of chronic diabetes patients who disappear after a consultation.
   - Without proactive reminders, over 40% of patients experience medication gaps or unmonitored HbA1c elevation.
2. **The Solution**:
   - Ingest raw clinic files: `python scripts/run_ingest.py`.
   - Run the engine: `python scripts/run_engine.py`.
   - Show how Continuum parses messy doctor notes (e.g. `"T2DM c HTN"`) to accurately select the Diabetic Cohort without manual tagging.

---

## Act 2: Dosing Intelligence & Refill Forecasting
1. Open **Streamlit Console** (`streamlit run app/Home.py`).
2. Show the **Executive Dashboard**:
   - Highlight the **Simulated Today Date** (`2026-09-21`) and KPI counters.
3. Navigate to **Patient 360° View** (`pages/2_Patient_Detail.py`):
   - Select a patient on `Glycomet GP 1` with dose `1-0-1` and quantity `60`.
   - Point out that Continuum parsed `1-0-1` as **2 tablets/day**, calculated **30 days of supply**, and identified the exact refill exhaustion date.

---

## Act 3: Care Coordinator Priority Worklist & WhatsApp Outreach
1. Navigate to **Priority Worklist** (`pages/1_Worklist.py`):
   - Show how patients are ranked strictly by days overdue (descending order, never by clinical severity).
   - Point out the distinction between `reason` (why flagged: Followup Overdue, Refill Gap, Combined) and `status` (lifecycle: detected -> contacted -> promised -> returned).
2. Click on an **Overdue Episode**:
   - Expand the drawer.
   - Show the **Language Selector**: toggle between **English**, **Hindi (हिंदी)**, and **Marathi (मराठी)**.
   - Notice that the message fills placeholders in a doctor-approved template (never improvises free-form medical advice), and includes the treating physician's name, missed date, and clinic phone number.
3. Click the **"Open in WhatsApp"** button:
   - Demonstrates the official `wa.me/91XXXXXXXXXX` link opening WhatsApp Web/App ready to send with 1 click.
4. Click **"Mark as Contacted"**:
   - Watch the episode state advance cleanly on the FSM to `contacted`.

---

## Act 4: Proportional Consent Gating & Medico-Legal Protection
1. In the Worklist, find a patient who has **Opted Out of Outreach** (`opt_out = YES`):
   - Show that direct patient dispatch is **BLOCKED** with a badge because the patient explicitly opted out.
   - Note that **drafting call scripts remains permitted** so the coordinator can review records or prepare clinical communication.
   - Explain: *Routine follow-up for a clinic's own patient is ordinary care, allowed unless opted out. Autonomy is protected by code.*
2. Navigate to **Consent Registry** (`pages/6_Consent.py`):
   - Search for the patient.
   - Record an updated consent preference.
   - Return to the Worklist: notice the patient is now unblocked and ready for communication.

---

## Act 5: Caregiver / Kin Escalation Hard Gate
1. Navigate to **Kin Escalation Queue** (`pages/5_Escalation_Queue.py`):
   - Explain: *When an overdue patient is unreachable, contacting a third party (kin/caregiver) discloses health status.*
   - Show the **Kin Consent Hard Gate**: kin messaging is strictly blocked unless `kin_consent = YES` is explicitly on record.
   - Demonstrate that unconsented kin entries cannot be messaged, preventing HIPAA/DISHA data protection breaches.

---

## Act 6: Prescription OCR Verification Workbench
1. Navigate to **Document Verification** (`pages/4_Document_Verify.py`):
   - Upload a scanned paper prescription or discharge summary.
   - Watch the multimodal AI vision model parse doctor handwriting, extracting medication names, `1-0-1` patterns, and quantities.
   - Demonstrate the human-in-the-loop review before committing to the database.

---

## Act 7: Automated Truth Verification Harness
1. In terminal, run:
   ```bash
   python scripts/score_against_truth.py
   ```
2. Review the output scorecard:
   - Cohort Selection F1: `>95%`
   - Dosing Precision: `100%`
   - Consent Hard Gate Breaches: `0 (100% Compliance)`
3. Conclude: *Continuum provides clinical safety, mathematical precision, and scalable patient retention for chronic care.*
