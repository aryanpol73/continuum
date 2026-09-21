"""
Reusable patient card component for Streamlit pages.
"""

from __future__ import annotations
import streamlit as st
from typing import Dict, Any


def render_patient_card(patient_info: Dict[str, Any]):
    """
    Renders a clinical patient card with demographics and consent badges.
    """
    with st.container():
        st.markdown(
            f"""
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h4 style="margin: 0; color: #0f172a; font-size: 1.15rem;">{patient_info.get('name', 'Unknown')}</h4>
                        <span style="color: #64748b; font-size: 0.85rem; font-family: monospace;">UHID: {patient_info.get('uh_id', 'N/A')}</span>
                    </div>
                    <div>
                        <span style="background: {'#dcfce7' if patient_info.get('outreach_consent') else '#fee2e2'}; 
                                     color: {'#166534' if patient_info.get('outreach_consent') else '#991b1b'}; 
                                     padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">
                            {'✓ OUTREACH CONSENTED' if patient_info.get('outreach_consent') else '✕ OUTREACH OPT-OUT'}
                        </span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 12px; font-size: 0.9rem;">
                    <div><strong>Age/Gender:</strong> {patient_info.get('age', 'N/A')} yrs / {patient_info.get('gender', 'N/A')}</div>
                    <div><strong>Mobile:</strong> {patient_info.get('phone', 'N/A')}</div>
                    <div><strong>Kin:</strong> {patient_info.get('kin_name', 'None')} ({patient_info.get('kin_relation', 'None')})</div>
                    <div><strong>Kin Contact:</strong> {patient_info.get('kin_phone', 'None')}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
