"""
dashboard/streamlit_app_new.py
--------------------------------------
Nzyme transcript-to-task dashboard — extended with a Visual Dashboard page and improved Submit Transcript flow.

Run:
    streamlit run dashboard/streamlit_app_new.py

Backend:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import base64
import csv
import json
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import io

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# =============================================================================
# Configuration
# =============================================================================

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "nzyme_logo.png"

NZ_BLUE       = "#2B5375"
NZ_BLUE_DARK  = "#1E3D58"
NZ_BLUE_LIGHT = "#EAF1F7"
NZ_BORDER     = "#D0D7E2"
NZ_TEXT       = "#1D2433"
NZ_MUTED      = "#667085"

# Chart colour palette — cohesive with the brand
CHART_PALETTE = [
    "#2B5375", "#4A8AB5", "#6CAED4", "#9ECAE1",
    "#C6DBEF", "#E84C3D", "#F4A261", "#2A9D8F",
    "#E9C46A", "#264653",
]
OVERDUE_RED   = "#E84C3D"
ON_TRACK_TEAL = "#2A9D8F"
DUE_SOON_AMBER = "#F4A261"


# =============================================================================
# Page setup and global CSS
# =============================================================================

st.set_page_config(
    page_title="Nzyme Team Tasks",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    :root {{
        --nzyme-blue: {NZ_BLUE};
        --nzyme-blue-dark: {NZ_BLUE_DARK};
        --nzyme-blue-light: {NZ_BLUE_LIGHT};
        --nzyme-border: {NZ_BORDER};
        --nzyme-text: {NZ_TEXT};
        --nzyme-muted: {NZ_MUTED};
    }}

    .block-container {{
        padding-top: 2.5rem;
        padding-bottom: 2.4rem;
        max-width: 1280px;
    }}

    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #F8FAFC 0%, #EEF4F8 100%);
        border-right: 1px solid var(--nzyme-border);
    }}

    section[data-testid="stSidebar"] .block-container {{
        padding-top: 2.2rem;
    }}

    .nzyme-logo-wrapper {{
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        margin-bottom: 1.1rem;
    }}

    .nzyme-logo {{
        border-radius: 0 !important;
        object-fit: contain !important;
        image-rendering: auto;
    }}

    section[data-testid="stSidebar"] .nzyme-logo-wrapper {{
        margin-top: 0.4rem;
        margin-bottom: 1.2rem;
    }}

    section[data-testid="stSidebar"] .nzyme-logo {{
        width: 250px !important;
        max-width: 92% !important;
        height: auto !important;
    }}

    .hero-subtitle {{
        font-size: 1.0rem;
        color: #5A6778;
        max-width: 860px;
        margin-bottom: 1.6rem;
        line-height: 1.65;
    }}

    .sidebar-caption {{
        color: #697586;
        font-size: 0.95rem;
        line-height: 1.45;
        margin-top: -0.25rem;
        margin-bottom: 1.6rem;
    }}

    .section-label {{
        font-size: 0.80rem;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: var(--nzyme-muted);
        font-weight: 800;
        margin-top: 0.7rem;
        margin-bottom: 0.45rem;
    }}

    .small-muted {{
        color: var(--nzyme-muted);
        font-size: 0.92rem;
        line-height: 1.45;
    }}

    .status-card {{
        border: 1px solid var(--nzyme-border);
        border-radius: 16px;
        padding: 1rem 1.1rem;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}

    .notion-link a {{
        color: var(--nzyme-blue);
        font-weight: 700;
        text-decoration: none;
    }}

    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid var(--nzyme-border);
        border-radius: 16px;
        padding: 1rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}

    /* ── Visual Dashboard KPI cards ── */
    .vd-kpi {{
        background: #FFFFFF;
        border: 1px solid var(--nzyme-border);
        border-radius: 20px;
        padding: 1.35rem 1.5rem 1.2rem 1.5rem;
        box-shadow: 0 2px 8px rgba(16, 24, 40, 0.06);
        position: relative;
        overflow: hidden;
    }}

    .vd-kpi::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        border-radius: 20px 20px 0 0;
    }}

    .vd-kpi.blue::before  {{ background: {NZ_BLUE}; }}
    .vd-kpi.teal::before  {{ background: {ON_TRACK_TEAL}; }}
    .vd-kpi.red::before   {{ background: {OVERDUE_RED}; }}
    .vd-kpi.amber::before {{ background: {DUE_SOON_AMBER}; }}

    .vd-kpi-label {{
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: var(--nzyme-muted);
        margin-bottom: 0.45rem;
    }}

    .vd-kpi-value {{
        font-size: 2.6rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: var(--nzyme-blue-dark);
        line-height: 1;
    }}

    .vd-kpi-sub {{
        font-size: 0.84rem;
        color: var(--nzyme-muted);
        margin-top: 0.35rem;
    }}

    /* ── Chart containers ── */
    .chart-card {{
        background: #FFFFFF;
        border: 1px solid var(--nzyme-border);
        border-radius: 20px;
        padding: 1.5rem 1.6rem 1.2rem 1.6rem;
        box-shadow: 0 2px 8px rgba(16, 24, 40, 0.06);
        margin-bottom: 1.4rem;
    }}

    .chart-title {{
        font-size: 1.0rem;
        font-weight: 800;
        color: var(--nzyme-blue-dark);
        letter-spacing: -0.01em;
        margin-bottom: 0.18rem;
    }}

    .chart-subtitle {{
        font-size: 0.84rem;
        color: var(--nzyme-muted);
        margin-bottom: 1.1rem;
        line-height: 1.4;
    }}

    /* ── Risk badge ── */
    .risk-badge {{
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }}

    .risk-badge.high   {{ background: #FEE2E2; color: #B91C1C; }}
    .risk-badge.medium {{ background: #FEF3C7; color: #92400E; }}
    .risk-badge.low    {{ background: #D1FAE5; color: #065F46; }}

    /* ── Buttons ── */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"],
    button[kind="primary"],
    default-participants[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stFormSubmitButton"] > button:focus,
    .stForm button[type="submit"] {{
        background: #2B5375 !important;
        background-color: #2B5375 !important;
        border-color: #2B5375 !important;
        border: 1px solid #2B5375 !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(43, 83, 117, 0.35) !important;
    }}

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] > button:hover,
    .stForm button[type="submit"]:hover {{
        background: #1E3D58 !important;
        background-color: #1E3D58 !important;
        border-color: #1E3D58 !important;
        border: 1px solid #1E3D58 !important;
        color: #FFFFFF !important;
    }}

    .stButton > button[kind="primary"]:active,
    div[data-testid="stFormSubmitButton"] > button:active {{
        background: #162C40 !important;
        background-color: #162C40 !important;
        border-color: #162C40 !important;
    }}

    .stButton > button {{
        border-radius: 10px !important;
    }}

    /* Radio / checkbox accent colour */
    input[type="radio"], input[type="checkbox"] {{
        accent-color: var(--nzyme-blue) !important;
    }}

    div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        border-color: var(--nzyme-blue) !important;
    }}

    div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div {{
        background-color: var(--nzyme-blue) !important;
        border-color: var(--nzyme-blue) !important;
    }}

    /* Chat bubbles and avatars */
    div[data-testid="stChatMessage"] {{
        border-radius: 16px;
    }}

    div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] {{
        background-color: var(--nzyme-blue) !important;
    }}

    div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {{
        background-color: var(--nzyme-blue-light) !important;
        color: var(--nzyme-blue) !important;
    }}

    /* ── Polished Chat Input ── */
    div[data-testid="stChatInput"] [data-baseweb="textarea"],
    div[data-testid="stChatInput"] [data-baseweb="textarea"]:focus-within,
    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] textarea:focus {{
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        background-color: #F0F2F6 !important;
        padding-left: 0.25rem !important;
        padding-right: 0.25rem !important;
        caret-color: var(--nzyme-blue) !important;
    }}

    div[data-testid="stChatInput"] > div {{
        border: 1px solid var(--nzyme-border) !important;
        border-radius: 14px !important;
        background-color: #F0F2F6 !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }}

    div[data-testid="stChatInput"] > div:focus-within {{
        border-color: var(--nzyme-blue) !important;
        box-shadow: 0 0 0 1px var(--nzyme-blue) !important;
    }}

    div[data-testid="stChatInput"] button {{
        background-color: var(--nzyme-blue) !important;
        border-color: var(--nzyme-blue) !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
    }}

    div[data-testid="stChatInput"] button:hover {{
        background-color: var(--nzyme-blue-dark) !important;
        border-color: var(--nzyme-blue-dark) !important;
    }}

    div[data-testid="stChatInput"] button svg {{
        fill: #FFFFFF !important;
        color: #FFFFFF !important;
    }}

    /* Sidebar feel */
    section[data-testid="stSidebar"] hr {{
        margin-top: 1.5rem;
        margin-bottom: 1.5rem;
    }}

    section[data-testid="stSidebar"] label {{
        font-size: 1.02rem;
    }}

    /* Chat cards */
    .nzyme-chat-card {{
        border: 1px solid var(--nzyme-border);
        border-left: 6px solid #B8C9D9;
        border-radius: 16px;
        padding: 1.15rem 1.35rem;
        margin: 1.05rem 0 1.45rem 0;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}

    .nzyme-chat-card.user {{
        background: #F3F7FB;
        border-left-color: var(--nzyme-blue);
    }}

    .nzyme-chat-card.assistant {{
        background: #FFFFFF;
        border-left-color: #B8C9D9;
    }}

    .nzyme-chat-label {{
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
        font-weight: 800;
        color: var(--nzyme-blue);
        margin-bottom: 0.65rem;
    }}

    .nzyme-chat-content {{
        color: #273142;
        font-size: 1.03rem;
        line-height: 1.65;
    }}

    .nzyme-stream-card {{
        border: 1px solid var(--nzyme-border);
        border-left: 6px solid #B8C9D9;
        border-radius: 16px;
        padding: 1.15rem 1.35rem;
        margin: 1.05rem 0 1.45rem 0;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}

    .source-pill {{
        display: inline-block;
        padding: 0.18rem 0.45rem;
        border-radius: 999px;
        background: var(--nzyme-blue-light);
        color: var(--nzyme-blue);
        font-size: 0.80rem;
        font-weight: 700;
        margin-right: 0.25rem;
    }}

    .suggestion-intro {{
        color: #475467;
        font-size: 0.95rem;
        margin: -0.2rem 0 0.85rem 0;
        line-height: 1.45;
    }}

    .suggestion-group-title {{
        color: var(--nzyme-blue);
        font-weight: 800;
        letter-spacing: 0.01em;
        font-size: 0.98rem;
        margin-bottom: 0.12rem;
    }}

    .suggestion-group-subtitle {{
        color: var(--nzyme-muted);
        font-size: 0.84rem;
        line-height: 1.35;
        min-height: 2.3rem;
        margin-bottom: 0.45rem;
    }}

    div[data-testid="stExpander"] div[data-testid="stButton"] button {{
        min-height: 3.05rem;
        white-space: normal;
        text-align: left;
        border-radius: 12px !important;
        border-color: #D8E2EA !important;
        background: #FFFFFF !important;
        color: #273142 !important;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
    }}

    div[data-testid="stExpander"] div[data-testid="stButton"] button:hover {{
        border-color: var(--nzyme-blue) !important;
        background: #F5F9FC !important;
        color: var(--nzyme-blue) !important;
    }}

    /* Brand-polished sidebar */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, var(--nzyme-blue) 0%, var(--nzyme-blue-dark) 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.12) !important;
    }}

    section[data-testid="stSidebar"] .nzyme-logo-wrapper {{
        background: rgba(255,255,255,0.96);
        border: 1px solid rgba(255,255,255,0.72);
        border-radius: 18px;
        padding: 1.05rem 1rem;
        box-shadow: 0 10px 30px rgba(8, 31, 48, 0.18);
        margin-bottom: 1rem;
    }}

    section[data-testid="stSidebar"] .sidebar-caption {{
        color: rgba(255,255,255,0.82) !important;
        font-size: 0.93rem;
        margin-bottom: 1.6rem;
    }}

    section[data-testid="stSidebar"] .section-label {{
        color: rgba(255,255,255,0.66) !important;
        letter-spacing: 0.12em;
    }}

    section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.18) !important;
    }}

    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {{
        color: rgba(255,255,255,0.92) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 0.55rem 0.75rem;
        margin: 0.35rem 0;
        transition: all 0.15s ease;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
        background: rgba(255,255,255,0.14);
        border-color: rgba(255,255,255,0.24);
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        border-color: rgba(255,255,255,0.78) !important;
        background: transparent !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div {{
        background-color: #FFFFFF !important;
        border-color: #FFFFFF !important;
    }}

    h1, h2, h3 {{
        color: var(--nzyme-blue-dark);
    }}

    /* ── Multiselect tags ── */
    span[data-baseweb="tag"],
    div[data-baseweb="tag"] {{
        background-color: #2B5375 !important;
        background: #2B5375 !important;
        border: 1px solid #1E3D58 !important;
        border-radius: 8px !important;
    }}

    span[data-baseweb="tag"] span,
    span[data-baseweb="tag"] div,
    span[data-baseweb="tag"] button,
    div[data-baseweb="tag"] span,
    div[data-baseweb="tag"] div,
    div[data-baseweb="tag"] button {{
        color: #FFFFFF !important;
        background-color: transparent !important;
        background: transparent !important;
    }}

    span[data-baseweb="tag"] svg,
    div[data-baseweb="tag"] svg {{
        fill: #FFFFFF !important;
        color: #FFFFFF !important;
        stroke: #FFFFFF !important;
        opacity: 0.85;
    }}

    span[data-baseweb="tag"] svg:hover,
    div[data-baseweb="tag"] svg:hover {{
        opacity: 1;
    }}

    [data-baseweb="tag"] [data-testid="stMarkdownContainer"],
    [data-baseweb="tag"] p,
    [data-baseweb="tag"] span:not([role]) {{
        color: #FFFFFF !important;
    }}

    /* ── File uploader adjusted to brand blue accent outlines ── */
    div[data-testid="stFileUploader"] {{
        border: 2px dashed var(--nzyme-blue) !important;
        border-radius: 16px !important;
        background: #FAFBFC !important;
        padding: 0.5rem !important;
        transition: border-color 0.2s ease !important;
    }}

    div[data-testid="stFileUploader"]:hover {{
        border-color: var(--nzyme-blue) !important;
        background: var(--nzyme-blue-light) !important;
    }}

    div[data-testid="stFileUploader"] label {{
        color: var(--nzyme-blue) !important;
        font-weight: 700 !important;
    }}

    div[data-testid="stFileUploader"] small {{
        color: var(--nzyme-muted) !important;
    }}

    div[data-testid="stFileDropzoneInstructions"] {{
        color: var(--nzyme-blue) !important;
    }}

    div[data-testid="stFileDropzoneInstructions"] svg {{
        fill: var(--nzyme-blue) !important;
        color: var(--nzyme-blue) !important;
    }}

    /* ── Submit form card ── */
    .submit-form-card {{
        background: #FFFFFF;
        border: 1px solid var(--nzyme-border);
        border-radius: 20px;
        padding: 2rem 2.2rem;
        box-shadow: 0 2px 8px rgba(16, 24, 40, 0.05);
        margin-bottom: 1.6rem;
    }}

    .submit-section-label {{
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: var(--nzyme-muted);
        margin-bottom: 0.85rem;
        margin-top: 1.4rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid var(--nzyme-border);
    }}

    .submit-section-label:first-child {{
        margin-top: 0;
    }}

    /* ── Demo buttons row ── */
    .demo-row-label {{
        font-size: 0.82rem;
        color: var(--nzyme-muted);
        margin-bottom: 0.5rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }}

    /* ── Result task cards ── */
    .task-result-card {{
        background: var(--nzyme-blue-light);
        border: 1px solid #C5D8E8;
        border-left: 4px solid var(--nzyme-blue);
        border-radius: 12px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        font-size: 0.94rem;
        color: var(--nzyme-text);
        line-height: 1.55;
    }}

    .task-result-meta {{
        font-size: 0.82rem;
        color: var(--nzyme-muted);
        margin-top: 0.25rem;
    }}

    /* ── Form focus states updated to Brand Blue outlines ── */
    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="select"]:focus-within,
    div[data-baseweb="textarea"]:focus-within,
    textarea:focus,
    input:focus {{
        border-color: #2B5375 !important;
        box-shadow: 0 0 0 1px #2B5375 !important;
        outline: none !important;
    }}

    /* BaseWeb overrides for multi-select component layout wrappers */
    div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
    div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div:focus-within,
    div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div:focus,
    div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div[aria-expanded="true"],
    div[data-testid="stMultiSelect"] [data-baseweb="base-input"],
    div[data-testid="stMultiSelect"] [data-baseweb="base-input"]:focus-within,
    [data-baseweb="select"] > div[class*="controlContainer"],
    [data-baseweb="select"] > div[class*="controlContainer"]:focus-within,
    [data-baseweb="select"] [class*="controlContainer"][aria-expanded="true"] {{
        border-color: #2B5375 !important;
        box-shadow: 0 0 0 1px #2B5375 !important;
        outline: none !important;
    }}

    div[data-testid="stMultiSelect"] * {{
        border-color: #2B5375 !important;
        outline-color: #2B5375 !important;
    }}

    div[data-testid="stMultiSelect"] div[data-baseweb="select"] {{
        box-shadow: none !important;
    }}

    /* ── Calendar overlay styles fixed to brand blue selection arcs ── */
    div[data-baseweb="calendar"] [class*="DaySelected"] {{
        background-color: #2B5375 !important;
        color: #FFFFFF !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] {{
        display: flex !important;
        align-items: center !important;
        gap: 0.55rem !important;
        width: 100% !important;
        min-height: 3.0rem !important;
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 16px !important;
        padding: 0.55rem 0.78rem !important;
        margin: 0.36rem 0 !important;
        transition: all 0.16s ease !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:hover {{
        background: rgba(255,255,255,0.15) !important;
        border-color: rgba(255,255,255,0.28) !important;
        transform: translateX(1px);
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
        background: rgba(255,255,255,0.18) !important;
        border-color: rgba(255,255,255,0.38) !important;
        box-shadow: inset 4px 0 0 #FFFFFF, 0 8px 24px rgba(10, 31, 48, 0.16) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] *,
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) * {{
        color: rgba(255,255,255,0.96) !important;
        background: transparent !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div,
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        background: transparent !important;
        border-color: rgba(255,255,255,0.88) !important;
        box-shadow: none !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div::after {{
        background: #FFFFFF !important;
    }}

    /* ── Streamlined executive sidebar navigation ── */
    section[data-testid="stSidebar"] .block-container {{
        padding: 1.9rem 1.55rem 1.4rem 1.55rem !important;
    }}

    section[data-testid="stSidebar"] .nzyme-logo-wrapper {{
        margin-top: 0.2rem !important;
        margin-bottom: 1.65rem !important;
        padding: 1.05rem 1rem !important;
        border-radius: 22px !important;
        box-shadow: 0 18px 38px rgba(8, 31, 48, 0.23) !important;
    }}

    section[data-testid="stSidebar"] .section-label {{
        margin-top: 0.35rem !important;
        margin-bottom: 0.85rem !important;
        padding-left: 0.1rem !important;
        font-size: 0.78rem !important;
        color: rgba(255,255,255,0.58) !important;
    }}

    section[data-testid="stSidebar"] hr {{
        margin-top: 0.25rem !important;
        margin-bottom: 1.45rem !important;
        border-color: rgba(255,255,255,0.14) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        display: none !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] {{
        position: relative !important;
        min-height: 3.35rem !important;
        padding: 0.72rem 1rem 0.72rem 1.05rem !important;
        margin: 0.46rem 0 !important;
        border-radius: 18px !important;
        background: rgba(255,255,255,0.075) !important;
        border: 1px solid rgba(255,255,255,0.13) !important;
        box-shadow: none !important;
        cursor: pointer !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:hover {{
        background: rgba(255,255,255,0.135) !important;
        border-color: rgba(255,255,255,0.26) !important;
        transform: translateX(2px) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
        background: linear-gradient(135deg, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0.14) 100%) !important;
        border-color: rgba(255,255,255,0.45) !important;
        box-shadow: inset 4px 0 0 #FFFFFF, 0 12px 28px rgba(5, 24, 38, 0.22) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] span,
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] p {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        font-weight: 400 !important;
        font-size: 1.02rem !important;
        line-height: 1.25 !important;
        color: rgba(255,255,255,0.92) !important;
    }}

    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) span,
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) p {{
        color: #FFFFFF !important;
    }}

    .sidebar-end-spacer {{
        height: 1.2rem;
    }}

    /* ── Elegant page header bar ── */
    .page-header-bar {{
        display: flex;
        flex-direction: column;
        gap: 0.18rem;
        margin-bottom: 0.6rem;
        padding-bottom: 0.85rem;
        border-bottom: 1px solid var(--nzyme-border);
    }}

    .page-header-inline {{
        display: flex;
        align-items: center;
        gap: 0.65rem;
    }}

    .page-header-wordmark {{
        font-size: 0.68rem;
        font-weight: 900;
        letter-spacing: 0.25em;
        color: var(--nzyme-blue);
        text-transform: uppercase;
    }}

    .page-header-pipe {{
        color: #C5CFDB;
        font-weight: 300;
        font-size: 1.3rem;
        line-height: 1;
    }}

    .page-header-title {{
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.022em;
        color: var(--nzyme-blue-dark);
        line-height: 1.2;
    }}

    /* ── Plotly chart overrides ── */
    .js-plotly-plot .plotly .modebar {{
        opacity: 0.4;
    }}

    .js-plotly-plot .plotly .modebar:hover {{
        opacity: 1;
    }}

    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Plotly chart theme helper
# =============================================================================

def _base_layout(**overrides) -> dict:
    """Shared Plotly layout settings that keep all charts on-brand."""
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial", color=NZ_TEXT, size=13),
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=12),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor=NZ_BORDER,
            font=dict(color=NZ_TEXT, size=13),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showline=False),
        yaxis=dict(showgrid=True, gridcolor="#EEF2F6", zeroline=False, showline=False),
    )
    base.update(overrides)
    return base


def _chart_card(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="chart-title">{title}</div>
        <div class="chart-subtitle">{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


def _kpi(label: str, value: str, sub: str, colour: str) -> None:
    st.markdown(
        f"""
        <div class="vd-kpi {colour}">
            <div class="vd-kpi-label">{label}</div>
            <div class="vd-kpi-value">{value}</div>
            <div class="vd-kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Helpers
# =============================================================================

def render_logo(width: int = 300) -> None:
    if LOGO_PATH.exists():
        encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
        st.markdown(
            f"""
            <div class="nzyme-logo-wrapper">
                <img
                    src="data:image/png;base64,{encoded}"
                    class="nzyme-logo"
                    style="
                        width: {width}px;
                        max-width: 100%;
                        height: auto;
                        object-fit: contain;
                        border-radius: 0;
                        display: block;
                    "
                />
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='font-size:2.4rem;font-weight:800;color:{NZ_BLUE};letter-spacing:0.03em;'>NZYME</div>",
            unsafe_allow_html=True,
        )


def render_page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="page-header-bar">
            <div class="page-header-inline">
                <span class="page-header-wordmark">NZYME</span>
                <span class="page-header-pipe">|</span>
                <span class="page-header-title">{title}</span>
            </div>
        </div>
        <div class='hero-subtitle'>{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_employees() -> Dict[str, Dict[str, str]]:
    path = DATA_DIR / "organization.csv"
    employees: Dict[str, Dict[str, str]] = {}
    if not path.exists():
        return employees
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            employees[row["employee_id"]] = dict(row)
    return employees


@st.cache_data(ttl=60, show_spinner=False)
def load_projects() -> Dict[str, Dict[str, str]]:
    path = DATA_DIR / "projects.csv"
    projects: Dict[str, Dict[str, str]] = {}
    if not path.exists():
        return projects
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            projects[row["project_id"]] = dict(row)
    return projects


def normalise_task(task: Dict[str, Any]) -> Dict[str, Any]:
    assignee = task.get("assignee") or {}
    if isinstance(assignee, dict):
        assignee_name = assignee.get("name") or task.get("assignee_name") or "Unresolved"
        employee_id = assignee.get("employee_id") or task.get("employee_id") or ""
    else:
        assignee_name = str(assignee) if assignee else task.get("assignee_name", "Unresolved")
        employee_id = task.get("employee_id", "")
    return {
        "Task": task.get("description") or task.get("Task") or "",
        "Assignee": assignee_name,
        "Employee ID": employee_id,
        "Deadline": task.get("deadline") or task.get("Deadline") or "",
        "Project ID": task.get("project_id") or task.get("Project ID") or "",
        "Project": task.get("project_name") or task.get("Project") or "",
        "Topic": task.get("topic") or task.get("Topic") or "",
        "Transcript": task.get("transcript_id") or task.get("Transcript") or "",
        "Notion URL": task.get("notion_url") or task.get("notion_page_url") or task.get("Notion URL") or "",
        "Open": task.get("open", task.get("Open", True)),
    }


@st.cache_data(ttl=60, show_spinner=False)
def fetch_tasks_from_api() -> List[Dict[str, Any]]:
    try:
        response = httpx.get(f"{API_BASE}/bonus/tasks", timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    if isinstance(payload, dict):
        tasks = payload.get("tasks", [])
    elif isinstance(payload, list):
        tasks = payload
    else:
        tasks = []
    return [normalise_task(t) for t in tasks]


def get_tasks_cached() -> List[Dict[str, Any]]:
    if "tasks_cache" not in st.session_state:
        st.session_state.tasks_cache = fetch_tasks_from_api()
    return st.session_state.tasks_cache


def refresh_tasks() -> None:
    fetch_tasks_from_api.clear()
    st.session_state.tasks_cache = fetch_tasks_from_api()


def tasks_to_dataframe(tasks: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for task in tasks:
        rows.append({
            "Task": task.get("Task", ""),
            "Assignee": task.get("Assignee", "Unresolved"),
            "Employee ID": task.get("Employee ID", ""),
            "Deadline": task.get("Deadline", ""),
            "Project ID": task.get("Project ID", ""),
            "Project": task.get("Project", ""),
        })
    return pd.DataFrame(rows)


def call_api_post(path: str, payload: Dict[str, Any], timeout: int = 120) -> Optional[Dict[str, Any]]:
    try:
        response = httpx.post(f"{API_BASE}{path}", json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"API error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        st.error(f"Request failed: {exc}")
    return None


def load_sample_request(transcript_id: str) -> Optional[Dict[str, Any]]:
    suffix = "001" if transcript_id.endswith("001") else "002"
    request_path = ROOT_DIR / f"request_{suffix}.json"
    if request_path.exists():
        return json.loads(request_path.read_text(encoding="utf-8"))
    metadata_path = DATA_DIR / "metadata.json"
    transcript_path = DATA_DIR / "transcripts" / f"transcript_{suffix}.txt"
    if not metadata_path.exists() or not transcript_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    transcript_meta = next(
        (m for m in metadata.get("transcripts", []) if m.get("transcript_id") == f"transcript_{suffix}"),
        None,
    )
    if not transcript_meta:
        return None
    return {
        "transcript_id": transcript_meta["transcript_id"],
        "transcript": transcript_path.read_text(encoding="utf-8"),
        "metadata": {
            "meeting_title": transcript_meta["meeting_title"],
            "date": transcript_meta["date"],
            "participants": transcript_meta["participants"],
        },
    }


def parse_deadline(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def deadline_label(deadline: str) -> str:
    dl = parse_deadline(deadline)
    if not dl:
        return "No deadline"
    today = date.today()
    if dl < today:
        return f"{deadline} · overdue"
    if (dl - today).days <= 3:
        return f"{deadline} · due soon"
    return deadline


def apply_filters(
    tasks: List[Dict[str, Any]], member: str, project: str, stale_only: bool
) -> List[Dict[str, Any]]:
    filtered = list(tasks)
    if member != "All":
        filtered = [t for t in filtered if t["Assignee"] == member]
    if project != "All":
        filtered = [t for t in filtered if t["Project ID"] == project or t["Project"] == project]
    if stale_only:
        today = date.today()
        filtered = [t for t in filtered if parse_deadline(t["Deadline"]) and parse_deadline(t["Deadline"]) < today]
    return filtered


# =============================================================================
# Grounded chatbot helpers
# =============================================================================

OUT_OF_SCOPE_PATTERNS = [
    r"\bweather\b", r"\btemperature\b", r"\bforecast\b", r"\bstock\b",
    r"\bshare price\b", r"\bcrypto\b", r"\bbitcoin\b", r"\bnews\b",
    r"\bsports\b", r"\brestaurant\b", r"\bhotel\b", r"\bflight\b",
    r"\btravel\b", r"\bwho won\b",
]

REFUSAL_MESSAGE = (
    "I am an AI assistant trained only on your team's meeting tasks and project documents. "
    "I cannot answer external questions like weather queries. How can I help you with your tasks today?"
)


def is_out_of_scope_question(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in OUT_OF_SCOPE_PATTERNS)


def build_context_for_legacy_chatbot(
    employees: Dict[str, Dict[str, str]],
    projects: Dict[str, Dict[str, str]],
    tasks: List[Dict[str, Any]],
) -> str:
    lines = ["=== EMPLOYEES ==="]
    for emp in employees.values():
        lines.append(f"- {emp.get('name')} ({emp.get('employee_id')}), {emp.get('role')} in {emp.get('department')}, email {emp.get('email')}")
    lines.append("\n=== PROJECTS ===")
    for project in projects.values():
        lines.append(f"- {project.get('name')} ({project.get('project_id')}), status {project.get('status')}: {project.get('description')}")
    lines.append("\n=== TASKS ===")
    for task in tasks:
        lines.append(
            f"- {task['Task']} | assignee={task['Assignee']} | employee_id={task['Employee ID']} "
            f"| deadline={task['Deadline'] or 'N/A'} | project={task['Project ID'] or 'N/A'} | project_name={task['Project'] or 'N/A'}"
        )
    return "\n".join(lines)


def ask_chatbot(
    question: str,
    tasks: List[Dict[str, Any]],
    employees: Dict[str, Dict[str, str]],
    projects: Dict[str, Dict[str, str]],
) -> str:
    if is_out_of_scope_question(question):
        return REFUSAL_MESSAGE
    try:
        response = httpx.post(f"{API_BASE}/bonus/chat", json={"question": question}, timeout=60)
        if response.status_code != 404:
            response.raise_for_status()
            payload = response.json()
            return payload.get("answer") or payload.get("response") or str(payload)
    except Exception as exc:
        first_error = str(exc)
    else:
        first_error = ""
    try:
        context = build_context_for_legacy_chatbot(employees, projects, tasks)
        response = httpx.post(f"{API_BASE}/chatbot", json={"question": question, "context": context}, timeout=60)
        response.raise_for_status()
        return response.json().get("answer", "No answer returned.")
    except Exception as exc:
        return f"I could not reach the grounded chatbot endpoint. First error: {first_error}. Fallback error: {exc}"


def stream_response_text(text: str):
    for token in re.split(r"(\s+)", text):
        if token:
            yield token
            time.sleep(0.014)


def find_employee_matches(question: str, employees: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    q = question.lower()
    matches = []
    for emp in employees.values():
        name = emp.get("name", "")
        employee_id = emp.get("employee_id", "")
        first_name = name.split()[0].lower() if name else ""
        full_name = name.lower()
        if employee_id.lower() in q or full_name in q or (first_name and re.search(rf"\b{re.escape(first_name)}\b", q)):
            matches.append(emp)
    return matches


def find_project_matches(question: str, projects: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    q = question.lower()
    matches = []
    for project in projects.values():
        project_id = project.get("project_id", "")
        name = project.get("name", "")
        if project_id.lower() in q or (name and name.lower() in q):
            matches.append(project)
    return matches


def task_matches_question(
    task: Dict[str, Any],
    question: str,
    employees: Dict[str, Dict[str, str]],
    projects: Dict[str, Dict[str, str]],
) -> bool:
    q = question.lower()
    emp_matches = find_employee_matches(question, employees)
    proj_matches = find_project_matches(question, projects)
    if emp_matches and task.get("Employee ID") in {emp.get("employee_id") for emp in emp_matches}:
        return True
    if proj_matches and task.get("Project ID") in {proj.get("project_id") for proj in proj_matches}:
        return True
    if "deadline" in q or "due" in q or "overdue" in q or "stale" in q:
        return bool(task.get("Deadline"))
    if "most tasks" in q or "workload" in q or "on their plate" in q or "team" in q:
        return True
    return False


def build_sources(
    question: str,
    answer: str,
    tasks: List[Dict[str, Any]],
    employees: Dict[str, Dict[str, str]],
    projects: Dict[str, Dict[str, str]],
) -> List[Dict[str, str]]:
    sources: List[Dict[str, str]] = []
    if answer == REFUSAL_MESSAGE:
        return [{"Source": "Scope guardrail", "Evidence": "Question was classified as outside organization.csv, projects.csv and Notion task data."}]
    for emp in find_employee_matches(question, employees):
        sources.append({"Source": f"organization.csv -> {emp.get('employee_id')}", "Evidence": f"{emp.get('name')} | {emp.get('role')} | {emp.get('department')} | {emp.get('email')}"})
    for project in find_project_matches(question, projects):
        sources.append({"Source": f"projects.csv -> {project.get('project_id')}", "Evidence": f"{project.get('name')} | status={project.get('status')} | {project.get('description')}"})
    matched_tasks = [task for task in tasks if task_matches_question(task, question, employees, projects)]
    for task in matched_tasks[:8]:
        task_source = "Notion task repository" + (" -> transcript page" if task.get("Notion URL") else "")
        sources.append({"Source": task_source, "Evidence": f"{task.get('Task')} | assignee={task.get('Assignee')} | deadline={task.get('Deadline') or 'No deadline'} | project={task.get('Project ID') or 'No project'}"})
    q = question.lower()
    if ("project" in q or "projects" in q) and not find_project_matches(question, projects):
        sources.append({"Source": "projects.csv", "Evidence": "Project catalogue used to restrict project answers to known project IDs and names."})
    if ("employee" in q or "member" in q or "team" in q) and not find_employee_matches(question, employees):
        sources.append({"Source": "organization.csv", "Evidence": "Organization database used to restrict people answers to known employees."})
    if not sources:
        sources.append({"Source": "Notion task repository + organization.csv + projects.csv", "Evidence": "Answer was routed through the grounded task assistant using only local task, employee and project records."})
    seen = set()
    unique_sources = []
    for item in sources:
        key = (item["Source"], item["Evidence"])
        if key not in seen:
            unique_sources.append(item)
            seen.add(key)
    return unique_sources


def render_sources(sources: List[Dict[str, str]]) -> None:
    with st.expander("Sources and grounding data", expanded=False):
        for item in sources:
            st.markdown(f"<span class='source-pill'>{item['Source']}</span><br>{item['Evidence']}", unsafe_allow_html=True)
            st.divider()


def _html_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _markdown_to_card_html(text: str) -> str:
    safe = _html_escape(text or "")
    lines = safe.splitlines()
    out: List[str] = []
    in_ul = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<br>")
            continue
        if stripped.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<div>{stripped}</div>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def render_streaming_chat_card(content: str) -> str:
    placeholder = st.empty()
    streamed = ""
    for chunk in stream_response_text(content):
        streamed += chunk
        placeholder.markdown(
            f'<div class="nzyme-chat-card assistant"><div class="nzyme-chat-label">Nzyme Assistant</div><div class="nzyme-chat-content">{_markdown_to_card_html(streamed)}</div></div>',
            unsafe_allow_html=True,
        )
    placeholder.markdown(
        f'<div class="nzyme-chat-card assistant"><div class="nzyme-chat-label">Nzyme Assistant</div><div class="nzyme-chat-content">{_markdown_to_card_html(streamed)}</div></div>',
        unsafe_allow_html=True,
    )
    return streamed


def render_chat_card(role: str, content: str) -> None:
    role_class = "user" if role == "user" else "assistant"
    label = "You" if role == "user" else "Nzyme Assistant"
    st.markdown(
        f'<div class="nzyme-chat-card {role_class}"><div class="nzyme-chat-label">{label}</div><div class="nzyme-chat-content">{_markdown_to_card_html(content)}</div></div>',
        unsafe_allow_html=True,
    )


# =============================================================================
# Visual Dashboard helpers
# =============================================================================

def _classify_deadline(deadline_str: str) -> str:
    dl = parse_deadline(deadline_str)
    if not dl:
        return "No deadline"
    today = date.today()
    if dl < today:
        return "Overdue"
    if (dl - today).days <= 7:
        return "Due this week"
    return "On track"


def build_visual_data(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = date.today()

    proj_counter: Dict[str, int] = defaultdict(int)
    for t in tasks:
        label = t.get("Project") or t.get("Project ID") or "No project"
        proj_counter[label] += 1
    df_proj = (
        pd.DataFrame(list(proj_counter.items()), columns=["Project", "Tasks"])
        .sort_values("Tasks", ascending=True)
        .reset_index(drop=True)
    )

    health_counter: Dict[str, int] = defaultdict(int)
    for t in tasks:
        health_counter[_classify_deadline(t.get("Deadline", ""))] += 1
    df_health = pd.DataFrame(list(health_counter.items()), columns=["Status", "Count"])

    person_counter: Dict[str, int] = defaultdict(int)
    for t in tasks:
        person_counter[t.get("Assignee") or "Unresolved"] += 1
    df_person = (
        pd.DataFrame(list(person_counter.items()), columns=["Person", "Tasks"])
        .sort_values("Tasks", ascending=True)
        .reset_index(drop=True)
    )

    rows = []
    for t in tasks:
        dl = parse_deadline(t.get("Deadline", ""))
        if dl:
            rows.append({
                "Assignee": t.get("Assignee") or "Unresolved",
                "Deadline": dl,
                "Task": t.get("Task", ""),
                "Project": t.get("Project") or t.get("Project ID") or "—",
                "Status": _classify_deadline(t.get("Deadline", "")),
                "Days": (dl - today).days,
            })
    df_timeline = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Assignee", "Deadline", "Task", "Project", "Status", "Days"])

    topic_counter: Dict[str, int] = defaultdict(int)
    for t in tasks:
        topic_counter[t.get("Topic") or "Untagged"] += 1
    df_topic = (
        pd.DataFrame(list(topic_counter.items()), columns=["Topic", "Tasks"])
        .sort_values("Tasks", ascending=False)
        .reset_index(drop=True)
    )

    overdue   = health_counter.get("Overdue", 0)
    due_soon  = health_counter.get("Due this week", 0)
    on_track  = health_counter.get("On track", 0)
    no_dl     = health_counter.get("No deadline", 0)

    return {
        "df_proj": df_proj,
        "df_health": df_health,
        "df_person": df_person,
        "df_timeline": df_timeline,
        "df_topic": df_topic,
        "overdue": overdue,
        "due_soon": due_soon,
        "on_track": on_track,
        "no_deadline": no_dl,
        "total": len(tasks),
    }


def render_visual_dashboard(tasks: List[Dict[str, Any]]) -> None:
    if not tasks:
        st.info("No tasks available. Process at least one transcript and refresh.")
        return

    d = build_visual_data(tasks)

    rc1, _ = st.columns([1, 7])
    with rc1:
        if st.button("↺  Refresh", key="vd_refresh"):
            refresh_tasks()
            st.rerun()

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        _kpi("Total tasks", str(d["total"]), "open across all projects", "blue")
    with k2:
        _kpi("On track", str(d["on_track"]), "deadline > 7 days away", "teal")
    with k3:
        _kpi("Overdue", str(d["overdue"]), "past deadline today", "red")
    with k4:
        _kpi("Due this week", str(d["due_soon"]), "deadline within 7 days", "amber")
    with k5:
        _kpi("No deadline", str(d["no_deadline"]), "tasks without a due date", "blue")

    st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1.55], gap="large")

    with col_left:
        _chart_card(
            "Deadline Health Overview",
            "At-a-glance split of tasks by urgency — helps managers triage risk instantly.",
        )
        health_colours = {
            "Overdue":       OVERDUE_RED,
            "Due this week": DUE_SOON_AMBER,
            "On track":      ON_TRACK_TEAL,
            "No deadline":   "#B8C9D9",
        }
        df_h = d["df_health"]
        fig_donut = go.Figure(go.Pie(
            labels=df_h["Status"],
            values=df_h["Count"],
            hole=0.62,
            marker=dict(
                colors=[health_colours.get(s, NZ_BLUE) for s in df_h["Status"]],
                line=dict(color="#FFFFFF", width=3),
            ),
            textinfo="label+percent",
            textfont=dict(size=13, color=NZ_TEXT),
            hovertemplate="<b>%{label}</b><br>%{value} tasks (%{percent})<extra></extra>",
            sort=False,
        ))
        fig_donut.add_annotation(
            text=f"<b>{d['total']}</b><br><span style='font-size:11px;color:{NZ_MUTED}'>tasks</span>",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=22, color=NZ_BLUE_DARK),
            align="center",
        )
        fig_donut.update_layout(
            **_base_layout(
                height=300,
                showlegend=False,
                margin=dict(l=0, r=0, t=10, b=0),
            )
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

    with col_right:
        _chart_card(
            "Team Workload Distribution",
            "Number of open tasks per person — surface capacity imbalances before they become blockers.",
        )
        df_p = d["df_person"]
        max_tasks = df_p["Tasks"].max() if len(df_p) else 1
        bar_colours = [
            OVERDUE_RED if v >= max_tasks * 0.8 else (DUE_SOON_AMBER if v >= max_tasks * 0.5 else ON_TRACK_TEAL)
            for v in df_p["Tasks"]
        ]
        fig_workload = go.Figure(go.Bar(
            x=df_p["Tasks"],
            y=df_p["Person"],
            orientation="h",
            marker=dict(color=bar_colours, line=dict(width=0)),
            text=df_p["Tasks"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} tasks<extra></extra>",
        ))
        fig_workload.update_layout(
            **_base_layout(
                height=300,
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=13)),
                margin=dict(l=0, r=40, t=10, b=0),
                bargap=0.35,
            )
        )
        st.plotly_chart(fig_workload, use_container_width=True, config={"displayModeBar": False})

    col_proj, col_topic = st.columns([1.4, 1], gap="large")

    with col_proj:
        _chart_card(
            "Tasks by Project",
            "Horizontal bar showing how work is distributed across active projects.",
        )
        df_proj = d["df_proj"]
        proj_colours = [CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(df_proj))]
        fig_proj = go.Figure(go.Bar(
            x=df_proj["Tasks"],
            y=df_proj["Project"],
            orientation="h",
            marker=dict(color=proj_colours, line=dict(width=0)),
            text=df_proj["Tasks"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} tasks<extra></extra>",
        ))
        fig_proj.update_layout(
            **_base_layout(
                height=max(260, len(df_proj) * 38),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=12)),
                margin=dict(l=0, r=40, t=10, b=0),
                bargap=0.35,
            )
        )
        st.plotly_chart(fig_proj, use_container_width=True, config={"displayModeBar": False})

    with col_topic:
        _chart_card(
            "Task Topics",
            "What themes dominate the backlog — useful for spotting areas of concentrated effort.",
        )
        df_t = d["df_topic"].nlargest(10, "Tasks").sort_values("Tasks", ascending=True)
        fig_topic = go.Figure(go.Bar(
            x=df_t["Tasks"],
            y=df_t["Topic"],
            orientation="h",
            marker=dict(
                color=df_t["Tasks"],
                colorscale=[[0, NZ_BLUE_LIGHT], [1, NZ_BLUE_DARK]],
                line=dict(width=0),
            ),
            text=df_t["Tasks"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} tasks<extra></extra>",
        ))
        fig_topic.update_layout(
            **_base_layout(
                height=max(260, len(df_t) * 38),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(
                    showgrid=False, zeroline=False, showline=False,
                    tickfont=dict(size=12),
                    categoryorder="array",
                    categoryarray=df_t["Topic"].tolist(),
                ),
                margin=dict(l=0, r=40, t=10, b=0),
                bargap=0.35,
            )
        )
        st.plotly_chart(fig_topic, use_container_width=True, config={"displayModeBar": False})


# =============================================================================
# Data load and sidebar
# =============================================================================

employees = load_employees()
projects = load_projects()

with st.sidebar:
    render_logo(width=260)
    st.divider()
    st.markdown("<div class='section-label'>Navigation</div>", unsafe_allow_html=True)
    nav_options = {
        "Submit Transcript": "⏏  Submit Transcript",
        "Task Dashboard":    "▦  Task Dashboard",
        "Visual Dashboard":  "◧  Visual Dashboard",
        "Chatbot":           "◌  Chatbot",
    }
    selected_nav = st.radio(
        "Navigation",
        list(nav_options.values()),
        label_visibility="collapsed",
    )
    page = next(key for key, value in nav_options.items() if value == selected_nav)
    st.markdown("<div class='sidebar-end-spacer'></div>", unsafe_allow_html=True)


# =============================================================================
# Page 1: Submit Transcript
# =============================================================================

if page == "Submit Transcript":
    render_page_header(
        "Submit Meeting Transcript",
        "Upload or paste a transcript, fill in the meeting details, then process it through the full pipeline: extraction, assignee resolution, topic grouping, project linking and Notion persistence.",
    )

    if "loaded_request" not in st.session_state:
        st.session_state.loaded_request = {}
    if "transcript_text_override" not in st.session_state:
        st.session_state.transcript_text_override = None
    if "auto_participants" not in st.session_state:
        st.session_state.auto_participants = []      
    if "auto_meeting_title" not in st.session_state:
        st.session_state.auto_meeting_title = ""

    def _detect_from_transcript(text: str, emp_map: Dict[str, Dict[str, str]]) -> tuple:
        import re as _re
        first_name_map: Dict[str, str] = {}
        for eid, emp in emp_map.items():
            first = emp.get("name", "").split()[0].lower()
            if first:
                first_name_map[first] = eid

        speaker_tokens = _re.findall(
            r"(?:^\[\d{2}:\d{2}:\d{2}\]\s+)?([A-Za-záéíóúñüÁÉÍÓÚÑÜ][A-Za-záéíóúñüÁÉÍÓÚÑÜ]{1,20}):",
            text,
            _re.MULTILINE,
        )
        matched_ids: List[str] = []
        seen_ids: set = set()
        for token in speaker_tokens:
            key = token.strip().lower()
            eid = first_name_map.get(key)
            if eid and eid not in seen_ids:
                matched_ids.append(eid)
                seen_ids.add(eid)

        first_three = [emp_map[i].get("name", i).split()[0] for i in matched_ids[:3]]
        title = ""

        for line in text.splitlines()[:10]:
            stripped = line.strip()
            if (
                4 < len(stripped) < 90
                and not _re.match(r"^\[?\d", stripped)
                and not _re.match(r"^[A-Za-záéíóúñü]+\s*:", stripped)
                and stripped[0].isupper()
            ):
                title = stripped
                break

        if not title:
            m = _re.search(
                r"(?:meeting|agenda|subject|title|re:)\s*[:\-]\s*([A-Za-z][^\n]{4,80})",
                text[:400],
                _re.IGNORECASE,
            )
            if m:
                title = m.group(1).strip().rstrip(".")

        if not title and first_three:
            title = ", ".join(first_three) + " Sync"

        return matched_ids, title


    def _read_uploaded_file(uploaded_file) -> Optional[str]:
        name = uploaded_file.name.lower()
        raw = uploaded_file.read()
        if name.endswith(".txt") or name.endswith(".srt"):
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode("utf-8", errors="replace")
        if name.endswith(".docx"):
            try:
                import zipfile, xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                paragraphs = []
                for para in root.iter(f"{ns}p"):
                    texts = [node.text for node in para.iter(f"{ns}t") if node.text]
                    if texts:
                        paragraphs.append("".join(texts))
                return "\n\n".join(paragraphs)
            except Exception as exc:
                st.error(f"Could not read .docx file: {exc}")
                return None
        return None

    st.markdown("<div class='demo-row-label'>Load a sample transcript for demo or testing</div>", unsafe_allow_html=True)
    demo_col1, demo_col2, _ = st.columns([1, 1, 4])
    with demo_col1:
        if st.button("▶  Sample 001", use_container_width=True):
            st.session_state.loaded_request = load_sample_request("transcript_001") or {}
            st.session_state.transcript_text_override = None
            st.session_state.auto_participants = []
            st.session_state.auto_meeting_title = ""
            st.rerun()
    with demo_col2:
        if st.button("▶  Sample 002", use_container_width=True):
            st.session_state.loaded_request = load_sample_request("transcript_002") or {}
            st.session_state.transcript_text_override = None
            st.session_state.auto_participants = []
            st.session_state.auto_meeting_title = ""
            st.rerun()

    loaded = st.session_state.loaded_request or {}
    loaded_meta = loaded.get("metadata", {})

    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)

    st.markdown("<div class='submit-section-label'>Upload transcript file</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Drag and drop or click to browse — accepts .txt, .docx, .srt",
        type=["txt", "docx", "srt"],
        label_visibility="collapsed",
        help="Upload a plain-text transcript, Word document, or subtitle file. The content will populate the transcript field below.",
    )
    if uploaded_file is not None:
        parsed_text = _read_uploaded_file(uploaded_file)
        if parsed_text:
            st.session_state.transcript_text_override = parsed_text
            detected_ids, detected_title = _detect_from_transcript(parsed_text, employees)
            _emp_opts = {f"{emp.get('name', eid)} ({eid})": eid for eid, emp in employees.items()}
            _rev = {eid: label for label, eid in _emp_opts.items()}
            st.session_state.auto_participants = [
                _rev[eid] for eid in detected_ids if eid in _rev
            ]
            st.session_state.auto_meeting_title = detected_title
            n_found = len(detected_ids)
            participant_names = ", ".join(
                employees[eid].get("name", eid) for eid in detected_ids
            ) if detected_ids else "none detected"
            st.success(
                f"✓  **{uploaded_file.name}** loaded — {len(parsed_text):,} characters.  "
                f"Auto-detected **{n_found} participant{'s' if n_found != 1 else ''}**: {participant_names}."
            )

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    employee_options = {f"{emp.get('name', eid)} ({eid})": eid for eid, emp in employees.items()}
    reverse_labels = {eid: label for label, eid in employee_options.items()}

    if st.session_state.auto_participants:
        default_participants = st.session_state.auto_participants
    else:
        default_participants = [
            reverse_labels[eid]
            for eid in loaded_meta.get("participants", [])
            if eid in reverse_labels
        ]

    default_meeting_title = (
        st.session_state.auto_meeting_title
        if st.session_state.auto_meeting_title
        else loaded_meta.get("meeting_title", "")
    )

    initial_transcript = (
        st.session_state.transcript_text_override
        if st.session_state.transcript_text_override is not None
        else loaded.get("transcript", "")
    )

    st.markdown("<div class='submit-section-label'>Meeting details</div>", unsafe_allow_html=True)

    with st.form("submit_transcript_form"):
        col1, col2 = st.columns(2)
        with col1:
            transcript_id = st.text_input(
                "Transcript ID",
                value=loaded.get("transcript_id", "transcript_001"),
                help="Unique identifier for this transcript, used for de-duplication in Notion.",
            )
            meeting_title = st.text_input(
                "Meeting Title",
                value=default_meeting_title,
                placeholder="e.g. EU Pricing Decision — Cross-functional Sync",
            )
        with col2:
            default_date = date.today()
            if loaded_meta.get("date"):
                try:
                    default_date = datetime.strptime(loaded_meta["date"], "%Y-%m-%d").date()
                except Exception:
                    pass
            meeting_date = st.date_input("Meeting Date", value=default_date)
            participant_labels = st.multiselect(
                "Participants",
                options=list(employee_options.keys()),
                default=default_participants,
                help="Select all team members present in the meeting.",
            )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        transcript = st.text_area(
            "Transcript",
            value=initial_transcript,
            height=300,
            placeholder="Paste the meeting transcript here, or upload a file above to auto-populate this field...",
            help="Plain text of the meeting. Speaker labels (e.g. 'Liam:') are recognised automatically.",
        )

        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("⏏  Process Transcript", type="primary", use_container_width=False)

    if submitted:
        if not transcript.strip():
            st.warning("Please paste a transcript or upload a file before processing.")
        elif not participant_labels:
            st.warning("Please select at least one participant.")
        else:
            payload = {
                "transcript_id": transcript_id,
                "transcript": transcript,
                "metadata": {
                    "meeting_title": meeting_title,
                    "date": meeting_date.isoformat(),
                    "participants": [employee_options[label] for label in participant_labels],
                },
            }
            with st.spinner("Processing transcript and writing tasks to Notion..."):
                result = call_api_post("/process-transcript", payload)
            if result:
                st.success("Transcript processed successfully.")
                notion_url = result.get("notion_page_url")
                if notion_url:
                    st.markdown(
                        f"<div class='notion-link'><a href='{notion_url}' target='_blank'>↗ Open in Notion</a></div>",
                        unsafe_allow_html=True,
                    )
                topics = result.get("topics", [])
                if topics:
                    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
                    st.subheader(f"Extracted tasks — {sum(len(t.get('tasks', [])) for t in topics)} total")
                    for topic in topics:
                        task_list = topic.get("tasks", [])
                        with st.expander(f"{topic.get('topic')} — {len(task_list)} task(s)", expanded=True):
                            for task in task_list:
                                assignee = task.get("assignee") or {}
                                st.markdown(
                                    f"<div class='task-result-card'>"
                                    f"<strong>{task.get('description', '')}</strong>"
                                    f"<div class='task-result-meta'>"
                                    f"Assignee: {assignee.get('name', 'Unresolved')} &nbsp;·&nbsp; "
                                    f"Deadline: {task.get('deadline') or 'No deadline'} &nbsp;·&nbsp; "
                                    f"Project: {task.get('project_id') or 'No project'}"
                                    f"</div></div>",
                                    unsafe_allow_html=True,
                                )
                refresh_tasks()


# =============================================================================
# Page 2: Task Dashboard
# =============================================================================

elif page == "Task Dashboard":
    render_page_header(
        "Team Task Dashboard",
        "Manager view of open tasks retrieved from the task repository, with filters by member, project and stale or overdue deadlines.",
    )

    top_col1, top_col2 = st.columns([1, 5])
    with top_col1:
        if st.button("Refresh tasks"):
            refresh_tasks()
            st.rerun()

    tasks = get_tasks_cached()
    if not tasks:
        st.warning("No tasks were retrieved from the API. Make sure Uvicorn is running and that you have processed at least one transcript into Notion.")

    total_tasks = len(tasks)
    assignee_count = len({task["Assignee"] for task in tasks if task["Assignee"]})
    overdue_count = sum(1 for task in tasks if parse_deadline(task["Deadline"]) and parse_deadline(task["Deadline"]) < date.today())
    project_count = len({task["Project ID"] for task in tasks if task["Project ID"]})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open tasks", total_tasks)
    m2.metric("People with tasks", assignee_count)
    m3.metric("Stale or overdue", overdue_count)
    m4.metric("Linked projects", project_count)

    st.subheader("Filters")
    col1, col2, col3 = st.columns([1.15, 1.15, 1.25])
    members = ["All"] + sorted({task["Assignee"] for task in tasks if task["Assignee"]})
    project_labels = ["All"] + sorted({task["Project"] if task["Project"] else task["Project ID"] for task in tasks if task["Project"] or task["Project ID"]})

    with col1:
        member_filter = st.selectbox("Filter by member", members)
    with col2:
        project_filter = st.selectbox("Filter by project", project_labels)
    with col3:
        stale_only = st.checkbox("Show stale or overdue tasks only")

    filtered = apply_filters(tasks, member_filter, project_filter, stale_only)
    st.markdown(f"**{len(filtered)} task(s) shown**")

    if filtered:
        with st.expander("Table view", expanded=False):
            st.dataframe(tasks_to_dataframe(filtered), use_container_width=True, hide_index=True)

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for task in filtered:
            grouped[task["Assignee"] or "Unresolved"].append(task)

        for assignee in sorted(grouped):
            member_tasks = grouped[assignee]
            with st.expander(f"{assignee} — {len(member_tasks)} task(s)", expanded=True):
                for task in member_tasks:
                    project_value = task["Project"] or task["Project ID"] or "No project"
                    st.markdown(
                        f"- **{task['Task']}** \n"
                        f"  Topic: {task.get('Topic') or 'No topic'} | Deadline: {deadline_label(task['Deadline'])} | Project: {project_value}"
                    )
    else:
        st.info("No tasks match the selected filters.")


# =============================================================================
# Page 3: Visual Dashboard
# =============================================================================

elif page == "Visual Dashboard":
    render_page_header(
        "Visual Dashboard",
        "Executive analytics view: deadline health, team workload, project distribution, burn-down timeline and a risk register, all driven by live task data.",
    )
    tasks = get_tasks_cached()
    render_visual_dashboard(tasks)


# =============================================================================
# Page 4: Chatbot
# =============================================================================

elif page == "Chatbot":
    render_page_header(
        "Team Task Chatbot",
        "Ask about team workload, members, projects, deadlines or stale tasks. Answers are grounded exclusively on the task repository plus organization and project data.",
    )

    tasks = get_tasks_cached()

    suggested_question_groups = {
        "Resource and workload management": {
            "subtitle": "For team leads checking capacity and ownership.",
            "questions": [
                "What does Liam have on his plate?",
                "What tasks does Hugo need to do?",
                "Who has the most tasks right now?",
            ],
        },
        "Deadline and risk tracking": {
            "subtitle": "For managers identifying overdue work and delivery risk.",
            "questions": [
                "Which tasks are overdue?",
                "Show me tasks due by the end of this week.",
                "Are there any stale tasks with no updates?",
            ],
        },
        "Project summaries": {
            "subtitle": "For drilling into specific project commitments.",
            "questions": [
                "Show tasks for PRJ007.",
                "What is the status of the North Star Pricing project?",
                "Who owns the tasks for PRJ007?",
            ],
        },
    }

    with st.expander("Try one of these questions", expanded=False):
        st.markdown(
            "<div class='suggestion-intro'>Choose a question by business objective. These examples show the kinds of grounded workload, deadline and project queries the assistant can answer.</div>",
            unsafe_allow_html=True,
        )
        group_cols = st.columns(3)
        for col, (group_name, group_data) in zip(group_cols, suggested_question_groups.items()):
            with col:
                st.markdown(f"<div class='suggestion-group-title'>{group_name}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='suggestion-group-subtitle'>{group_data['subtitle']}</div>", unsafe_allow_html=True)
                for question in group_data["questions"]:
                    if st.button(question, use_container_width=True, key=f"starter_{group_name}_{question}"):
                        st.session_state.pending_question = question
                        st.rerun()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for message in st.session_state.chat_history:
        render_chat_card(message["role"], message["content"])
        if message["role"] == "assistant" and message.get("sources"):
            render_sources(message["sources"])

    typed_question = st.chat_input("Ask about tasks, team members, or projects...")
    pending_question = st.session_state.pop("pending_question", None)
    user_question = pending_question or typed_question

    if user_question:
        st.session_state.chat_history.append({"role": "user", "content": user_question})
        render_chat_card("user", user_question)

        with st.spinner("Retrieving grounded records..."):
            answer = ask_chatbot(user_question, tasks, employees, projects)
            sources = build_sources(user_question, answer, tasks, employees, projects)

        streamed_answer = render_streaming_chat_card(answer)
        render_sources(sources)

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": streamed_answer or answer,
            "sources": sources,
        })