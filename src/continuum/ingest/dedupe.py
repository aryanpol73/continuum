"""
Deduplication engine: identifies duplicate UHIDs and fuzzy match candidates (Phone or Name + Age).
Supports human-in-the-loop review and patient merging.
"""

from __future__ import annotations
from typing import List, Tuple
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from src.continuum.models import Patient, DuplicateCluster, Visit, Prescription, Episode, OutreachLog
from src.continuum.audit import log_action


def string_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def detect_duplicates(db: Session) -> List[DuplicateCluster]:
    """
    Scans all patients in the database and generates DuplicateCluster entries for suspected duplicates.
    """
    patients = db.query(Patient).all()
    created_clusters = []

    existing_clusters = db.query(DuplicateCluster.canonical_patient_id, DuplicateCluster.candidate_patient_id).all()
    existing_set = set()
    for c1, c2 in existing_clusters:
        existing_set.add((c1, c2))
        existing_set.add((c2, c1))

    for i in range(len(patients)):
        p1 = patients[i]
        for j in range(i + 1, len(patients)):
            p2 = patients[j]

            if (p1.id, p2.id) in existing_set:
                continue

            match_reason = None
            score = 0.0

            # 1. Exact phone match with different UHID
            if p1.phone and p2.phone and p1.phone == p2.phone and p1.phone != "+910000000000" and p1.uh_id != p2.uh_id:
                name_sim = string_similarity(p1.name, p2.name)
                if name_sim > 0.4:
                    match_reason = f"Identical phone ({p1.phone}) and matching name ({int(name_sim*100)}%)"
                    score = 0.95
                else:
                    match_reason = f"Identical phone ({p1.phone}) with different names"
                    score = 0.80

            # 2. High name similarity + matching age
            elif p1.age is not None and p2.age is not None and abs(p1.age - p2.age) <= 1:
                name_sim = string_similarity(p1.name, p2.name)
                if name_sim >= 0.80:
                    match_reason = f"High name similarity ({int(name_sim*100)}%) and matching age ({p1.age} vs {p2.age})"
                    score = name_sim

            if match_reason and score >= 0.80:
                cluster = DuplicateCluster(
                    canonical_patient_id=p1.id,
                    candidate_patient_id=p2.id,
                    match_reason=match_reason,
                    confidence_score=score,
                    status="PENDING"
                )
                db.add(cluster)
                existing_set.add((p1.id, p2.id))
                existing_set.add((p2.id, p1.id))
                created_clusters.append(cluster)

    if created_clusters:
        db.commit()
        for c in created_clusters:
            log_action(
                db, 
                action="DUPLICATE_FLAGGED", 
                entity_type="DuplicateCluster", 
                entity_id=c.id, 
                details={"canonical_id": c.canonical_patient_id, "candidate_id": c.candidate_patient_id, "score": c.confidence_score}
            )

    return created_clusters


def merge_patients(
    db: Session, 
    canonical_id: int, 
    duplicate_id: int, 
    cluster_id: int | None = None,
    user: str = "care_coordinator"
) -> None:
    """
    Merges duplicate patient record into canonical patient record.
    Reassigns all clinical visits, prescriptions, and episodes.
    """
    p_canonical = db.query(Patient).filter(Patient.id == canonical_id).first()
    p_duplicate = db.query(Patient).filter(Patient.id == duplicate_id).first()

    if not p_canonical or not p_duplicate:
        raise ValueError("One or both patient records do not exist.")

    # Reassign visits
    db.query(Visit).filter(Visit.patient_id == duplicate_id).update({"patient_id": canonical_id})
    # Reassign prescriptions
    db.query(Prescription).filter(Prescription.patient_id == duplicate_id).update({"patient_id": canonical_id})
    # Reassign episodes
    db.query(Episode).filter(Episode.patient_id == duplicate_id).update({"patient_id": canonical_id})
    # Reassign outreach logs
    db.query(OutreachLog).filter(OutreachLog.patient_id == duplicate_id).update({"patient_id": canonical_id})

    # Update cluster status if provided
    if cluster_id:
        cluster = db.query(DuplicateCluster).filter(DuplicateCluster.id == cluster_id).first()
        if cluster:
            cluster.status = "RESOLVED_MERGED"

    # Log action
    log_action(
        db,
        action="PATIENT_MERGED",
        entity_type="Patient",
        entity_id=canonical_id,
        user=user,
        details={
            "canonical_uhid": p_canonical.uh_id,
            "duplicate_uhid": p_duplicate.uh_id,
            "merged_patient_id": duplicate_id
        }
    )

    # Delete the duplicate patient record
    db.delete(p_duplicate)
    db.commit()


def dismiss_duplicate(
    db: Session, 
    cluster_id: int, 
    user: str = "care_coordinator"
) -> None:
    """
    Marks a suspected duplicate cluster as distinct patients.
    """
    cluster = db.query(DuplicateCluster).filter(DuplicateCluster.id == cluster_id).first()
    if cluster:
        cluster.status = "RESOLVED_DISTINCT"
        db.commit()
        log_action(
            db,
            action="DUPLICATE_DISMISSED",
            entity_type="DuplicateCluster",
            entity_id=cluster_id,
            user=user,
            details={"status": "RESOLVED_DISTINCT"}
        )
