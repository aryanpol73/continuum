# Continuum — Clinical Data Dictionary & Canonical Schema
**Setting:** Ramraksha Hospital OPD Software (Akola, Maharashtra)

---

## 1. Table: `patients`

| Column | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key | Autoincrement |
| `uh_id` | String(64) | Unique Hospital ID | Indexed, Unique (e.g. `20240001`) |
| `name` | String(128) | Full Name | Title-cased from F, M, L |
| `phone` | String(32) | Mobile Number | Normalized to E.164: `+91XXXXXXXXXX` |
| `gender` | String(16) | Sex | `Male`, `Female` |
| `age` | Integer | Age in years | 0 to 120 |
| `city` | String(64) | Place / Town | E.g. `Akola`, `Telhara`, `Akot` |
| `kin_name` | String(128) | Registered Relative | Caregiver name |
| `kin_phone` | String(32) | Caregiver Mobile | E.164 format: `+91XXXXXXXXXX` |
| `kin_relation` | String(64) | Relation | E.g. `Son`, `Daughter`, `Spouse` |

---

## 2. Table: `consents`

| Column | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key | Autoincrement |
| `patient_id` | Integer | Foreign Key -> `patients.id` | Unique, Cascade |
| `opt_out` | Boolean | Routine Outreach Opt-Out | Default `False` (Outreach permitted unless True) |
| `kin_consent` | Boolean | Caregiver Escalation Consent | Default `False` (**Hard Gate**: Kin contact blocked unless True) |
| `preferred_language` | String(16) | Communication Language | `mr` (Marathi), `hi` (Hindi), `en` (English) |

---

## 3. Table: `visits`

| Column | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key | Autoincrement |
| `patient_id` | Integer | Foreign Key -> `patients.id` | Cascade |
| `opd_id` | String(64) | OPD Consultation Register ID | E.g. `10001` |
| `visit_date` | Date | Date of OPD Consultation | `YYYY-MM-DD` |
| `doctor_name` | String(128) | Treating Consultant | E.g. `Dr. Ashwin Sadavarte` |
| `diagnosis_raw` | Text | Clinical Notes & History | Free text (e.g. `T2DM c HTN`) |
| `is_diabetes_cohort` | Boolean | Chronic Diabetes Mellitus Tag | Tagged by regex classifier |
| `followup_after_days` | Integer | Doctor's review interval | E.g. 15, 30, 60, 90 days |
| `next_visit_due_date` | Date | Next Review Due Date | `visit_date + followup_after_days` |

---

## 4. Table: `prescriptions`

| Column | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key | Autoincrement |
| `visit_id` | Integer | Foreign Key -> `visits.id` | Cascade |
| `patient_id` | Integer | Foreign Key -> `patients.id` | Cascade |
| `rx_line_id` | String(64) | Prescription Line ID | E.g. `X000001` |
| `opd_id` | String(64) | Associated OPD Visit ID | E.g. `10001` |
| `medication_name` | String(128) | Brand / Drug Name | E.g. `WALAPHAGE G2` |
| `raw_dose` | String(64) | Dosing Pattern | E.g. `1-0-1`, `1-0-0`, `0-0-1` |
| `frequency_per_day` | Float | Calculated Daily Frequency | `2.0`, `1.0`, `3.0` |
| `quantity` | Integer | Dispensed Quantity (Tablets) | E.g. 30, 60, 90 |
| `days_supply` | Integer | Supply Days | `floor(quantity / frequency_per_day)` |
| `refill_due_date` | Date | Supply Exhaustion Date | `start_date + days_supply` |

---

## 5. Table: `episodes`

| Column | Type | Description | Constraints |
| :--- | :--- | :--- | :--- |
| `id` | Integer | Primary Key | Autoincrement |
| `patient_id` | Integer | Foreign Key -> `patients.id` | Cascade |
| `reason` | String(32) | Reason Flagged (NOT status) | `FOLLOWUP_OVERDUE`, `REFILL_GAP`, `COMBINED` |
| `status` | String(32) | Closed-Loop Lifecycle State | `detected` → `contacted` → `promised` → `returned` / `unreachable` / `opted_out` |
| `due_date` | Date | Exhaustion or Review Date | `YYYY-MM-DD` |
| `max_overdue_days` | Integer | **Ranking Key** (Strictly Days Overdue) | Descending order (Never clinical severity scoring) |
| `first_drug_exhausted` | String(128) | Earliest-Exhausting Drug | E.g. `WALAPHAGE G2` |
| `followup_overdue_days`| Integer | Days past review grace period | `max(0, (TODAY - FollowUpDate) - 7)` |
| `refill_overdue_days` | Integer | Days past supply exhaustion grace | `max(0, (TODAY - first_end) - 7)` |
| `is_refill_only` | Boolean | Refill Gap with Valid Follow-up Date | Headline Finding |
| `promised_date` | Date | Patient's Promised Return Date | For closed-loop scheduling |
