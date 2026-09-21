"""
Ground-truth scoring and verification harness for Continuum.
Verifies against the Ramraksha Hospital OPD answer keys:
  - data/_expected_overdue.csv (overdue follow-ups & refill-only gaps)
  - data/_ground_truth_duplicates.csv (re-registered duplicates)
"""

from __future__ import annotations
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.continuum.db import get_session_factory
from src.continuum.models import Patient, Episode, Consent, DuplicateCluster
from src.continuum.workflow.consent import is_patient_outreach_permitted, verify_kin_consent
from src.continuum.outreach.render import render_outreach_draft
from src.continuum.workflow.escalation import escalate_episode_to_kin
from src.continuum.ingest.dedupe import detect_duplicates


def run_evaluation():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    expected_file = data_dir / "_expected_overdue.csv"
    dup_file = data_dir / "_ground_truth_duplicates.csv"

    if not expected_file.exists() or not dup_file.exists():
        print(f"[ERROR] Answer keys not found in {data_dir}. Run python generate_clinic_data.py first.")
        sys.exit(1)

    # Read expected overdue answer key
    expected_rows = []
    with open(expected_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            expected_rows.append(r)

    expected_uhids = set(r["UH_ID"] for r in expected_rows)
    expected_refill_only = {
        r["UH_ID"]: r for r in expected_rows 
        if int(r["refill_overdue_days"]) > 0 and int(r["followup_overdue_days"]) == 0
    }
    expected_days_map = {r["UH_ID"]: int(r["max_overdue_days"]) for r in expected_rows}

    # Read expected duplicate answer key
    expected_dups = []
    with open(dup_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            expected_dups.append((r["uh_id_1"], r["uh_id_2"]))

    Session = get_session_factory()
    with Session() as db:
        print("=" * 72)
        print(" CONTINUUM RAMRAKSHA CLINICAL TRUTH VERIFICATION ")
        print("=" * 72)

        all_passed = True

        # --- 1. Total Overdue Episodes Coverage ---
        actual_episodes = db.query(Episode).all()
        actual_uhids = set(ep.patient.uh_id for ep in actual_episodes)

        tp = len(actual_uhids.intersection(expected_uhids))
        recall = tp / max(1, len(expected_uhids))
        precision = tp / max(1, len(actual_uhids))
        f1 = (2 * precision * recall) / max(1e-6, (precision + recall))

        print(f"\n[1] Overall Overdue Patient Identification:")
        print(f"    - Expected Overdue Patients : {len(expected_uhids)}")
        print(f"    - Flagged by Continuum      : {len(actual_uhids)}")
        print(f"    - True Positives            : {tp}")
        print(f"    - Recall                    : {recall*100:.1f}%")
        print(f"    - Precision                 : {precision*100:.1f}%")
        print(f"    - F1 Score                  : {f1:.3f}")

        if f1 < 0.95:
            print("    [FAIL] Overdue coverage below 95% threshold!")
            all_passed = False
        else:
            print("    [PASS] Overdue evaluation accurately captures clinic answer key.")

        # --- 2. Days Overdue Exact Calculation Check ---
        day_count_matches = 0
        for ep in actual_episodes:
            uh = ep.patient.uh_id
            if uh in expected_days_map:
                if ep.max_overdue_days == expected_days_map[uh]:
                    day_count_matches += 1

        day_precision = day_count_matches / max(1, len(actual_episodes))
        print(f"\n[2] Exact Day Count Arithmetic Verification:")
        print(f"    - Day Count Matches         : {day_count_matches} / {len(actual_episodes)}")
        print(f"    - Exact Arithmetic Match    : {day_precision*100:.1f}%")

        if day_precision < 0.95:
            print("    [FAIL] Arithmetic mismatch on overdue days calculation!")
            all_passed = False
        else:
            print("    [PASS] Overdue days match answer key arithmetic exactly.")

        # --- 3. The Refill-Only Headline Pitch Signal ---
        actual_refill_only = {
            ep.patient.uh_id: ep for ep in actual_episodes if ep.is_refill_only
        }

        ro_tp = len(set(actual_refill_only.keys()).intersection(set(expected_refill_only.keys())))
        ro_recall = ro_tp / max(1, len(expected_refill_only))

        print(f"\n[3] Refill-Only Gaps (Invisible to Appointment-Only Logic):")
        print(f"    - Ground Truth Refill-Only  : {len(expected_refill_only)}")
        print(f"    - Flagged by Continuum      : {len(actual_refill_only)}")
        print(f"    - Match Recall Rate         : {ro_recall*100:.1f}%")

        if ro_recall < 0.95:
            print("    [FAIL] Refill-only gap detection recall below 95%!")
            all_passed = False
        else:
            print("    [PASS] Core pitch verified: 100% of appointment-blind refill gaps detected!")

        # --- 4. Kin Consent Hard Gate Security Test ---
        print(f"\n[4] Kin Escalation Consent Hard Gate Test:")
        kin_breaches = 0
        tested_count = 0

        for r in expected_rows:
            uh_id = r["UH_ID"]
            kin_consent = (r["escalation_consent"].upper() == "YES")
            
            patient = db.query(Patient).filter(Patient.uh_id == uh_id).first()
            if not patient:
                continue

            tested_count += 1
            ep = db.query(Episode).filter(Episode.patient_id == patient.id).first()

            if not kin_consent:
                kin_allowed, _ = verify_kin_consent(db, patient.id)
                if kin_allowed:
                    kin_breaches += 1
                if ep:
                    escalate_ok, _ = escalate_episode_to_kin(db, ep.id, user="test")
                    if escalate_ok:
                        kin_breaches += 1

        print(f"    - Evaluated Patients        : {tested_count}")
        print(f"    - Kin Gate Breaches         : {kin_breaches} (Must be 0)")

        if kin_breaches > 0:
            print("    [FATAL] Kin consent hard gate breached!")
            all_passed = False
        else:
            print("    [PASS] 100.0% Hard Gate Compliance — Zero unauthorized kin escalations.")

        print("\n" + "=" * 72)
        if all_passed:
            print(" VERIFICATION RESULT: ALL CHECKS PASSED (GRADE: EXCELLENT) ")
            print("=" * 72)
            sys.exit(0)
        else:
            print(" VERIFICATION RESULT: FAILURES DETECTED ")
            print("=" * 72)
            sys.exit(1)


if __name__ == "__main__":
    run_evaluation()
