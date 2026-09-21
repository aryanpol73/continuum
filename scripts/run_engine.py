"""
CLI Engine runner: runs cohort classifier, dosing parser, due rules evaluator, and deduplication scanner.
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.continuum.db import get_session_factory
from src.continuum.config import get_today
from src.continuum.engine.cohort import update_all_visits_cohort
from src.continuum.engine.dosing import update_all_prescriptions_dosing
from src.continuum.workflow.episodes import generate_episodes_from_rules
from src.continuum.ingest.dedupe import detect_duplicates


def main():
    today = get_today()
    print(f"[ENGINE] Running Continuum Clinical Engine (Anchor Date: {today})...")
    
    Session = get_session_factory()
    with Session() as db:
        # 1. Cohort Classification
        print("  -> Classifying Diabetes Mellitus cohort...")
        diabetic_visits = update_all_visits_cohort(db)
        print(f"     Identified {diabetic_visits} diabetic consultation records.")

        # 2. Dosing & Refill Calculation
        print("  -> Calculating prescription dosing rates and refill exhaustion dates...")
        rxs_processed = update_all_prescriptions_dosing(db)
        print(f"     Processed {rxs_processed} prescription lines.")

        # 3. Episode Generation
        print("  -> Evaluating due rules and generating care continuum episodes...")
        ep_stats = generate_episodes_from_rules(db, anchor_date=today, user="cli_engine")
        print(f"     Total Episodes Generated: {ep_stats['episodes_created']}")
        print(f"     - Refill-Only Gaps (Appointment-blind) : {ep_stats['refill_only_episodes']}")
        print(f"     - Follow-up Overdue Only              : {ep_stats['followup_only_episodes']}")
        print(f"     - Combined Overdue                    : {ep_stats['combined_episodes']}")

        # 4. Deduplication Scan
        print("  -> Scanning patient database for duplicate registrations...")
        duplicates = detect_duplicates(db)
        print(f"     Flagged {len(duplicates)} candidate duplicate clusters.")

    print("[SUCCESS] Engine execution finished.")


if __name__ == "__main__":
    main()
