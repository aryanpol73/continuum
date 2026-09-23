"""
Page 8: Compliance & Immutable Audit Log Inspector.
"""

from __future__ import annotations
import sys
import json
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.continuum.db import get_session_factory
from src.continuum.models import AuditLog
from app.components.style import apply_theme

st.set_page_config(page_title="Audit Trail | Continuum", page_icon="📜", layout="wide")
apply_theme()
from app.components.nav import render_sidebar, render_context_bar, require_clinic_setup
render_sidebar()
require_clinic_setup()

st.title("Compliance & Immutable Audit Trail")
st.caption("Complete append-only audit records of every clinical decision, outreach draft, consent change, and system action.")
render_context_bar()

Session = get_session_factory()

with Session() as db:
    actions = [a[0] for a in db.query(AuditLog.action).distinct().all()]
    users = [u[0] for u in db.query(AuditLog.user_or_system).distinct().all()]

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        selected_action = st.selectbox("Filter by Action Type", options=["ALL"] + actions)
    with col2:
        selected_user = st.selectbox("Filter by Actor / User", options=["ALL"] + users)
    with col3:
        limit_count = st.selectbox("Records Limit", options=[50, 100, 200, 500], index=0)

    query = db.query(AuditLog)
    if selected_action != "ALL":
        query = query.filter(AuditLog.action == selected_action)
    if selected_user != "ALL":
        query = query.filter(AuditLog.user_or_system == selected_user)

    total_logs = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit_count).all()

    st.markdown(f"**Showing {len(logs)} of {total_logs} logged events**")

    if not logs:
        st.info("No audit logs matching current filter.")
    else:
        for entry in logs:
            action_color = "#dc2626" if "BLOCKED" in entry.action else ("#16a34a" if "COMPLETED" in entry.action or "VERIFIED" in entry.action else "#0284c7")
            
            with st.expander(
                f"[{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.action} by {entry.user_or_system} (Target: {entry.entity_type} #{entry.entity_id})"
            ):
                st.markdown(f"**Entity Type:** `{entry.entity_type}` &bull; **Entity ID:** `{entry.entity_id}`")
                st.markdown(f"**Actor:** `{entry.user_or_system}` &bull; **Action:** `{entry.action}`")
                
                if entry.details_json:
                    try:
                        parsed = json.loads(entry.details_json)
                        st.json(parsed)
                    except Exception:
                        st.code(entry.details_json)
                else:
                    st.text("No additional payload details recorded.")
