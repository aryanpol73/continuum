# Continuum — Agent Instructions & Guardrails

## What this is
Overdue follow-up worklist for diabetes patients at a district OPD.
Detects lapsed patients from clinic records. Coordinator acts; system never does.

## HARD RULES — never violate
- **No diagnosis, treatment advice, risk scoring, or interpretation of lab values.**
- **Banned word:** The word **"risk"** is strictly forbidden in all identifiers, functions, columns, docstrings, and UI strings.
- **Rank ONLY by days overdue.** Never by clinical severity, disease stage, or risk.
- **Lab values:** HbA1c/FBS values may be STORED and DISPLAYED. Never scored, never compared to reference ranges, never used to rank patients.
- **Outreach & Drafting:**
  - Never auto-send any message. Coordinator presses send.
  - Patient outreach is permitted unless `opt_out = YES`. (Ordinary clinical communication between clinic and patient).
  - Never block drafting — the coordinator must be able to prepare a call script/message regardless.
- **Kin Escalation:**
  - Never contact kin without consent record (`kin_consent = YES`). Hard block in code, not a warning.
- **Terminology:**
  - Never write "non-adherent". Write "no refill recorded".
- **Message Generation:**
  - The message generator may only translate and fill placeholders in doctor-approved templates. It must NEVER compose free-form health content.
- **WhatsApp Links:**
  - `wa.me` links require format `91XXXXXXXXXX` (digits only, no `+` sign or spaces).

## Conventions
- **All clinical intervals live in `config/rules.yaml`.** Never hardcode.
- **Time Anchor:** `TODAY` comes from `src.continuum.config.get_today()`. Never `date.today()` in logic.
- **Audit Logging:** Every DB write that changes state calls `audit.log_action()`.
- **File modularity:** Files stay under ~200 lines. Split rather than grow.
- **Clean Architecture:** `src/` has no Streamlit imports. `app/` has no business logic.

## Verification
After changing `engine/` or `ingest/`, run:
```bash
python scripts/score_against_truth.py
```
It compares output to `data/_expected_overdue.csv`.
Day counts must match exactly. If they don't, the change is wrong.
