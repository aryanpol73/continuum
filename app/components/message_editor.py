"""
Interactive message composer component for Streamlit:
Allows selecting language, previewing rendered message, launching WhatsApp click-to-chat, and logging outreach.
"""

from __future__ import annotations
import streamlit as st
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from src.continuum.outreach.render import render_outreach_draft
from src.continuum.workflow.episodes import transition_episode


def render_message_editor(
    db: Session,
    episode_id: int,
    recipient_type: str = "PATIENT",
    key_prefix: str = "msg"
):
    """
    Renders an interactive message composer and WhatsApp dispatcher for a given episode.
    """
    col1, col2 = st.columns([1, 2])
    with col1:
        lang_choice = st.selectbox(
            "Select Language",
            options=["en", "hi", "mr"],
            format_func=lambda x: {"en": "English", "hi": "हिंदी (Hindi)", "mr": "मराठी (Marathi)"}[x],
            key=f"{key_prefix}_lang_{episode_id}"
        )

    # Render draft
    ok, msg, payload = render_outreach_draft(
        db=db,
        episode_id=episode_id,
        recipient_type=recipient_type,
        override_language=lang_choice,
        user="ui_coordinator"
    )

    if not ok:
        st.error(f"⚠️ {msg}")
        return

    st.markdown(f"**Subject:** `{payload['subject']}`")
    
    # Message preview box
    st.text_area(
        "Message Draft",
        value=payload["body"],
        height=140,
        disabled=True,
        key=f"{key_prefix}_body_{episode_id}"
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        wa_url = payload["whatsapp_url"]
        st.markdown(
            f"""
            <a href="{wa_url}" target="_blank" style="text-decoration: none;">
                <button style="width: 100%; background-color: #25D366; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer;">
                    💬 Open in WhatsApp Web / App
                </button>
            </a>
            """,
            unsafe_allow_html=True
        )
    with col_b:
        if st.button("Mark Episode as 'Contacted'", key=f"{key_prefix}_mark_contacted_{episode_id}"):
            try:
                transition_episode(db, episode_id, new_status="CONTACTED", user="ui_coordinator", reason="Outreach dispatched via WhatsApp")
                st.success("Episode updated to CONTACTED!")
                st.rerun()
            except Exception as e:
                st.error(str(e))
