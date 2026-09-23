"""
Page 3: Deduplication Resolution Workbench.
Review potential duplicate patient records flagged by phone or name/age matching, and merge records safely.
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import DuplicateCluster, Patient, Visit, Prescription
from src.continuum.ingest.dedupe import detect_duplicates, merge_patients, dismiss_duplicate
from app.components.style import apply_theme

st.set_page_config(page_title="Duplicate Review | Continuum", page_icon="👥", layout="wide")
apply_theme()
from app.components.nav import render_sidebar, render_context_bar, require_clinic_setup
render_sidebar()
require_clinic_setup()

st.title("Duplicate Patient Resolution Workbench")
st.caption("Human-in-the-loop review for patients sharing identical phone numbers or high name/age similarity.")
render_context_bar()

Session = get_session_factory()

col_scan, _ = st.columns([1, 3])
with col_scan:
    if st.button("🔍 Run Duplicate Detection Scan"):
        with Session() as db:
            clusters = detect_duplicates(db)
            st.success(f"Scan complete. Flagged {len(clusters)} new clusters.")
            st.rerun()

st.markdown("---")

with Session() as db:
    pending_clusters = db.query(DuplicateCluster).filter(DuplicateCluster.status == "PENDING").all()
    resolved_clusters = db.query(DuplicateCluster).filter(DuplicateCluster.status != "PENDING").all()

    st.subheader(f"Pending Reviews ({len(pending_clusters)})")

    if not pending_clusters:
        st.info("No pending duplicate candidates! The patient database is currently clean and deduplicated.")
    else:
        for cluster in pending_clusters:
            p1 = db.query(Patient).filter(Patient.id == cluster.canonical_patient_id).first()
            p2 = db.query(Patient).filter(Patient.id == cluster.candidate_patient_id).first()

            if not p1 or not p2:
                continue

            v1_count = db.query(Visit).filter(Visit.patient_id == p1.id).count()
            v2_count = db.query(Visit).filter(Visit.patient_id == p2.id).count()
            rx1_count = db.query(Prescription).filter(Prescription.patient_id == p1.id).count()
            rx2_count = db.query(Prescription).filter(Prescription.patient_id == p2.id).count()

            with st.container():
                st.markdown(
                    f"""
                    <div style="background: #fffbeb; border: 1px solid #fef3c7; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                        <strong>Match Reason:</strong> {cluster.match_reason} 
                        <span style="background: #fef08a; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; font-weight: bold;">
                            Score: {int(cluster.confidence_score * 100)}%
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"#### Primary Record: {p1.name}")
                    st.markdown(f"- **UHID:** `{p1.uh_id}`")
                    st.markdown(f"- **Mobile:** `{p1.phone}`")
                    st.markdown(f"- **Age / Gender:** {p1.age} yrs / {p1.gender}")
                    st.markdown(f"- **Visits:** {v1_count} &nbsp;|&nbsp; **Prescriptions:** {rx1_count}")

                with col_b:
                    st.markdown(f"#### Duplicate Candidate: {p2.name}")
                    st.markdown(f"- **UHID:** `{p2.uh_id}`")
                    st.markdown(f"- **Mobile:** `{p2.phone}`")
                    st.markdown(f"- **Age / Gender:** {p2.age} yrs / {p2.gender}")
                    st.markdown(f"- **Visits:** {v2_count} &nbsp;|&nbsp; **Prescriptions:** {rx2_count}")

                col_btn1, col_btn2, _ = st.columns([1, 1, 2])
                with col_btn1:
                    if st.button(f"Merge {p2.uh_id} into {p1.uh_id}", key=f"merge_{cluster.id}", type="primary"):
                        try:
                            merge_patients(db, canonical_id=p1.id, duplicate_id=p2.id, cluster_id=cluster.id)
                            st.success(f"Successfully merged {p2.uh_id} into {p1.uh_id}!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

                with col_btn2:
                    if st.button("Mark as Distinct Patients", key=f"dismiss_{cluster.id}"):
                        dismiss_duplicate(db, cluster_id=cluster.id)
                        st.info("Marked as distinct.")
                        st.rerun()

                st.markdown("---")

    if resolved_clusters:
        with st.expander(f"View Resolved History ({len(resolved_clusters)})"):
            res_data = []
            for rc in resolved_clusters:
                res_data.append({
                    "Cluster ID": rc.id,
                    "Canonical ID": rc.canonical_patient_id,
                    "Candidate ID": rc.candidate_patient_id,
                    "Reason": rc.match_reason,
                    "Status": rc.status,
                    "Timestamp": rc.created_at
                })
            st.dataframe(res_data, use_container_width=True)
