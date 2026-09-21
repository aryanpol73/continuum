# Continuum — Ambulatory Chronic Care Follow-Up & Retention Engine

Continuum is a clinical workflow, medication refill tracking, and ambulatory care retention platform engineered for Indian outpatient clinics (specifically modeled on Ramraksha Hospital, Station Road, Akola, Maharashtra).

Chronic diseases such as **Type 2 Diabetes Mellitus (T2DM)** require ongoing monitoring, timely medication renewals, and scheduled quarterly/biannual physician reviews. In high-volume district outpatient departments, chronic patients frequently lapse when prescriptions expire weeks ahead of their scheduled consultation, presenting only when acute complications emerge.

Continuum bridges this gap by transforming raw, messy clinic exports (CSV/Excel) and scanned prescriptions into proactive, priority-ranked care coordinator worklists with WhatsApp click-to-chat engagement, strict consent governance, and automated validation against ground truth.

---

## 🌟 Key Features

1. **Clinic EMR Ingestion & Phone Normalization**:
   - Robust normalization of Indian phone numbers (`91XXXXXXXXXX` for `wa.me` links) and heterogeneous date formats (`DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`).
   - Deduplication engine identifying duplicate UHIDs and fuzzy match candidates (Name + Phone + Age).

2. **Earliest-Exhausting Drug Refill & Follow-Up Engine**:
   - Real-world dosing pattern parser: `1-0-1`, `1-1-1`, `0-0-1`, `1-0-0`, `1/2-0-1/2`, `OD`, `BD`, `TDS`, `QID`.
   - Computes earliest-exhausting drug across all lines of a prescription (`Qty / doses_per_day`).
   - Unmasks "refill-only gaps": patients whose follow-up appointment is still weeks away, but whose vital diabetes medicines ran out >7 days ago.

3. **Care Continuum Episode Management**:
   - Clear architectural split: **reason** (`FOLLOWUP_OVERDUE`, `REFILL_GAP`, `COMBINED`) and workflow **status** (`detected` → `contacted` → `promised` → `returned` / `unreachable` / `opted_out`).
   - **Pure Days-Overdue Ranking**: Ranked strictly by `max_overdue_days` (descending). Zero clinical severity or diagnostic scoring.
   - Closed-loop return auto-closure: automatically closes open episodes when a returning patient attends an in-person OPD consultation.
   - Escalation queue for unreachable patients.

4. **Proportional Consent Gating & Medico-Legal Safeguards**:
   - **Routine Patient Outreach Permitted**: Ordinary clinical communication for pending care is allowed unless `opt_out = YES`.
   - **Kin Escalation Hard Gate**: Strictly blocks disclosure to third parties/kin unless affirmative consent is on record (`kin_consent = YES`).
   - **Never Block Drafting**: The care coordinator can always draft and review call scripts/messages regardless of outreach status.
   - **Immutable Audit Log**: Every state change and action is recorded with timestamps, coordinator ID, and payload diffs.

5. **WhatsApp Click-to-Chat & Multilingual Outreach**:
   - 1-click `wa.me/91XXXXXXXXXX` links populated with doctor-approved, empathetic outreach messages.
   - Multi-lingual templates in **English**, **Hindi (हिंदी)**, and **Marathi (मराठी)**.
   - Template-only placeholder injection: never improvises free-form medical advice.

6. **Streamlit Care Coordinator Console**:
   - Multi-page clinical dashboard with KPIs, time-travel simulation date controller, 360° patient timelines, prescription OCR verification workbench, and compliance audit logs.

7. **Ground-Truth Scoring Harness**:
   - Evaluates engine output against calibrated synthetic answer keys across 137 overdue diabetes cases (including 47 refill-only gaps).
   - Reconciled with chronic medication filter (skipping acute syrups/short-course PPIs) and `actionable_window_days: 540`.
   - Validates exact arithmetic day count parity (100.0%) and 100% consent gate compliance.

---

## 🚀 Quick Start

### 1. Installation
```bash
# Clone the repository
cd continuum

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Synthetic Clinic Data & Ground Truth
```bash
python scripts/generate_clinic_data.py
```
This generates 515 patients in `data/` along with calibrated `_expected_overdue.csv` (137 overdue diabetes patients, 47 refill-only gaps).

### 3. Initialize Database & Run Ingest
```bash
python scripts/init_db.py --drop
python scripts/run_ingest.py
```

### 4. Run the Clinical Engine
```bash
python scripts/run_engine.py
```
This classifies the diabetes cohort, parses dosing patterns, computes supply exhaustion dates, and generates active episodes.

### 5. Verify Against Ground Truth
```bash
python scripts/score_against_truth.py
```
Verifies that engine output matches the labelled synthetic answer key exactly across all 137 cases.

### 6. Launch the Streamlit Care Coordinator Portal
```bash
streamlit run app/Home.py
```

---

## 📁 Repository Structure

```
continuum/
├── AGENTS.md                    # Agent guardrails, clinical boundaries & conventions
├── README.md                    # Project overview & guide
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment configuration
├── .gitignore                   # Git ignore specifications
│
├── config/
│   ├── settings.yaml            # TODAY override, paths, thresholds
│   ├── mapping_ramraksha.yaml   # Clinic column → canonical schema map
│   ├── rules.yaml               # Dosing patterns, grace periods, cohort keywords
│   └── templates/
│       ├── followup_overdue.yaml
│       ├── refill_gap.yaml
│       └── kin_escalation.yaml
│
├── data/
│   ├── synthetic/               # Generated clinic exports & ground_truth.json
│   ├── raw/                     # Real clinic exports (GITIGNORED)
│   └── uploads/                 # Scanned prescriptions/docs (GITIGNORED)
│
├── src/continuum/
│   ├── config.py                # YAML configuration & dynamic TODAY resolution
│   ├── db.py                    # SQLAlchemy session & engine
│   ├── models.py                # Relational schema (Patient, Visit, Rx, Episode, etc.)
│   ├── audit.py                 # log_action() audit trail
│   │
│   ├── ingest/
│   │   ├── mapper.py            # Header normalization using YAML aliases
│   │   ├── loader.py            # CSV / Excel ingestion pipeline
│   │   ├── normalize.py         # Phone (+91), name, and date parsing
│   │   └── dedupe.py            # UHID collision & fuzzy match detection
│   │
│   ├── engine/
│   │   ├── dosing.py            # Indian dosing parser ("1-0-1" → 2/day; days supply)
│   │   ├── due_rules.py         # Follow-up overdue & refill gap evaluation
│   │   ├── cohort.py            # Diabetes cohort selection from free-text dx
│   │   └── worklist.py          # Priority scoring & ranked worklist assembly
│   │
│   ├── workflow/
│   │   ├── states.py            # Episode finite state machine
│   │   ├── episodes.py          # Episode lifecycle transitions
│   │   ├── consent.py           # Hard gate consent verifier
│   │   └── escalation.py        # Caregiver / kin escalation queue
│   │
│   ├── ai/
│   │   ├── schemas.py           # Pydantic extraction schemas
│   │   ├── extract.py           # Multimodal vision document extractor
│   │   └── message.py           # Personalized outreach generation
│   │
│   ├── outreach/
│   │   ├── render.py            # Template renderer with variable injection
│   │   └── whatsapp.py          # wa.me click-to-chat URL builder
│   │
│   └── metrics/
│       └── report.py            # Care continuum retention & conversion metrics
│
├── app/
│   ├── Home.py                  # Dashboard overview & time-travel controller
│   ├── pages/
│   │   ├── 1_Worklist.py        # Care coordinator priority worklist
│   │   ├── 2_Patient_Detail.py  # 360° longitudinal patient view
│   │   ├── 3_Duplicate_Review.py# Deduplication resolution workbench
│   │   ├── 4_Document_Verify.py # Prescription upload & vision OCR review
│   │   ├── 5_Escalation_Queue.py# Caregiver escalation center
│   │   ├── 6_Consent.py         # Patient consent & preferences registry
│   │   ├── 7_Metrics.py         # Retention funnels & doctor scorecards
│   │   └── 8_Audit_Log.py       # Compliance & audit trail viewer
│   └── components/
│       ├── patient_card.py      # Reusable patient summary card
│       └── message_editor.py    # Multilingual WhatsApp message composer
│
├── scripts/
│   ├── generate_clinic_data.py  # Synthetic generator with ground truth
│   ├── init_db.py               # Database table initializer
│   ├── run_ingest.py            # CLI ingest runner
│   ├── run_engine.py            # CLI rules & episode generator
│   └── score_against_truth.py   # Ground-truth evaluation harness
│
├── tests/
│   ├── test_dosing.py           # Dosing regex & days supply unit tests
│   ├── test_due_rules.py        # Follow-up & refill threshold unit tests
│   ├── test_consent_gate.py     # Hard consent gate security tests
│   └── test_golden.py           # End-to-end golden flow regression test
│
└── docs/
    ├── scope.md                 # Clinical boundaries & doctor sign-off
    ├── data_dictionary.md       # Canonical schema & field specifications
    └── demo_script.md           # Clinical demonstration walkthrough
```
