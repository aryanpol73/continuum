from pathlib import Path
import streamlit as st
from src.continuum.db import get_session_factory
from src.continuum.config import get_today
from src.continuum.models import AuditLog, ClinicProfile, get_clinic_profile
from app.components.pwa import render_pwa_sidebar_badge, inject_pwa_client_bridge

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

NAV = [
    ("Daily Work", [
        ("app/pages/1_Worklist.py",         "Overdue Worklist"),
        ("app/pages/9_Inbox.py",            "Patient Replies"),
        ("app/pages/5_Escalation_Queue.py", "Escalation Queue"),
        ("app/pages/2_Patient_Detail.py",   "Patient Detail"),
    ]),
    ("Data Quality", [
        ("app/pages/3_Duplicate_Review.py", "Duplicate Review"),
        ("app/pages/4_Document_Verify.py",  "Document Intake"),
    ]),
    ("Governance", [
        ("app/pages/6_Consent.py",   "Consent Registry"),
        ("app/pages/8_Audit_Log.py", "Audit Trail"),
    ]),
    ("Insight", [
        ("app/pages/7_Metrics.py", "Retention Metrics"),
    ]),
    ("Settings", [
        ("app/pages/0_Clinic_Setup.py", "Clinic Profile"),
    ]),
]

def _safe_page_link(path: str, label: str):
    candidates = [path]
    if path.startswith("app/"):
        candidates.append(path[4:])
    for p in candidates:
        try:
            st.page_link(p, label=label)
            return
        except Exception:
            continue
    try:
        st.page_link(path, label=label)
    except Exception:
        pass

def render_sidebar():
    if LOGO_PATH.exists():
        try:
            st.logo(str(LOGO_PATH))
        except Exception:
            pass
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=175)
            st.markdown(
                "<div style='font-size:0.75rem;color:#6B7280;margin-top:-6px;margin-bottom:14px;text-align:center;'>"
                "Follow-up &amp; Refill Engine</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:1.05rem;font-weight:600;color:#0F766E;'>"
                "Continuum</div>"
                "<div style='font-size:0.75rem;color:#6B7280;margin-bottom:14px;'>"
                "Follow-up &amp; Refill Engine</div>",
                unsafe_allow_html=True,
            )
        _safe_page_link("app/Home.py", label="Overview")
        for section, pages in NAV:
            st.markdown(
                f"<div style='font-size:0.68rem;text-transform:uppercase;"
                f"letter-spacing:0.08em;color:#9CA3AF;margin:14px 0 4px;'>"
                f"{section}</div>",
                unsafe_allow_html=True,
            )
            for path, label in pages:
                _safe_page_link(path, label=label)
        render_pwa_sidebar_badge()
    inject_pwa_client_bridge()

def render_context_bar():
    Session = get_session_factory()
    with Session() as db:
        profile = db.query(ClinicProfile).first()
        last_run = (
            db.query(AuditLog)
            .filter(AuditLog.action == "EPISODE_GENERATION_RUN")
            .order_by(AuditLog.timestamp.desc())
            .first()
        )
    clinic = (profile.clinic_name if profile and profile.clinic_name
              else "Clinic not configured")
    run_txt = (last_run.timestamp.strftime("%d %b %Y, %H:%M")
               if last_run else "never")
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;
             align-items:center;padding:8px 14px;background:#F6F8FA;
             border:1px solid #E5E7EB;border-radius:6px;
             font-size:0.78rem;color:#4B5563;margin-bottom:18px;">
          <span><b style="color:#111827;">{clinic}</b></span>
          <span>Evaluation date: {get_today()}
                &nbsp;&nbsp;|&nbsp;&nbsp; Engine last run: {run_txt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_clinic_setup():
    """Bounce to Clinic Setup until the profile is configured."""
    Session = get_session_factory()
    with Session() as db:
        profile = get_clinic_profile(db)
        configured = profile.is_configured
    if configured:
        return
    st.warning("Configure your clinic profile to activate Continuum.")
    _safe_page_link("app/pages/0_Clinic_Setup.py", label="Go to Clinic Setup →")
    st.stop()

