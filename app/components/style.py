import streamlit as st

def apply_theme():
    st.markdown("""
    <style>
      #MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden;}
      [data-testid="stDecoration"] {display: none;}
      .block-container {padding-top: 2rem; max-width: 1400px;}
      h1 {font-size: 1.6rem !important; font-weight: 600 !important;
          letter-spacing: -0.02em; color: #111827;}
      h2 {font-size: 1.2rem !important; font-weight: 600 !important;}
      [data-testid="stMetric"] {
          background: #FFFFFF; border: 1px solid #E5E7EB;
          border-radius: 8px; padding: 16px 18px;
      }
      [data-testid="stMetricLabel"] {
          font-size: 0.75rem; text-transform: uppercase;
          letter-spacing: 0.05em; color: #6B7280;
      }
      section[data-testid="stSidebar"] {background: #F9FAFB;
          border-right: 1px solid #E5E7EB;}
      .stButton button {border-radius: 6px; font-weight: 500;}
    </style>
    """, unsafe_allow_html=True)
