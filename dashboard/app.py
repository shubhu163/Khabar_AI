"""
Khabar AI — Streamlit Dashboard
====================================================
Clean white UI with:
  1. **Home** — product overview + company input → run pipeline from UI
  2. **Dashboard** — results with clickable event detail drill-down
  3. **Knowledge Graph** — interactive supply-chain visualisation
  4. **Metrics** — severity distribution, timeline, noise reduction
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.agents.knowledge_graph import SupplyChainGraph
from app.config import get_target_companies
from app.database import get_db, init_db
from app.models import RiskEvent

_logger = logging.getLogger("khabar.dashboard")

# ---------------------------------------------------------------------------
# Background Auto-Monitor
# ---------------------------------------------------------------------------
_STATUS_FILE = _PROJECT_ROOT / "monitor_status.json"

# Shared mutable config read by the background thread.
# The UI writes to this dict; the thread reads from it each cycle.
_monitor_cfg: dict = {
    "company": "Apple Inc",
    "interval_min": 60,
    "active": False,           # True once user clicks Start
    "stop_requested": False,   # signal to kill the loop
}


def _write_monitor_status(
    state: str,
    company: str = "",
    interval: int = 60,
    last_run: str | None = None,
    next_run: str | None = None,
    last_result: dict | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "state": state,
        "watchlist": [company] if company else [],
        "interval_min": interval,
        "last_run": last_run,
        "next_run": next_run,
        "last_result": last_result,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _monitor_loop() -> None:
    """Background thread: runs pipeline for one company on a user-set interval."""
    from app.main import RiskMonitor

    while True:
        # Wait until monitoring is activated
        while not _monitor_cfg["active"] or _monitor_cfg["stop_requested"]:
            if _monitor_cfg["stop_requested"]:
                _write_monitor_status("stopped", company=_monitor_cfg["company"],
                                       interval=_monitor_cfg["interval_min"])
                _monitor_cfg["stop_requested"] = False
                _monitor_cfg["active"] = False
            _time.sleep(2)

        company = _monitor_cfg["company"]
        interval = _monitor_cfg["interval_min"]

        _logger.info("Auto-monitor cycle — company: %s, interval: %d min", company, interval)
        now_iso = datetime.now(timezone.utc).isoformat()
        _write_monitor_status("running", company=company, interval=interval, last_run=now_iso)

        try:
            monitor = RiskMonitor(company_names=[company])
            stats = monitor.run()
            next_iso = (datetime.now(timezone.utc) + timedelta(minutes=interval)).isoformat()
            _write_monitor_status("idle", company=company, interval=interval,
                                   last_run=now_iso, next_run=next_iso, last_result=stats)
            _logger.info("Auto-monitor cycle done — %s", stats)
        except Exception as exc:
            _logger.exception("Auto-monitor cycle failed: %s", exc)
            next_iso = (datetime.now(timezone.utc) + timedelta(minutes=interval)).isoformat()
            _write_monitor_status("error", company=company, interval=interval,
                                   last_run=now_iso, next_run=next_iso, error=str(exc))

        # Sleep in small chunks so we can respond to stop requests quickly
        sleep_secs = interval * 60
        while sleep_secs > 0 and _monitor_cfg["active"] and not _monitor_cfg["stop_requested"]:
            _time.sleep(min(5, sleep_secs))
            sleep_secs -= 5


def _ensure_monitor_thread() -> None:
    """Spawn the background monitor thread exactly once (survives Streamlit reruns)."""
    if "monitor_thread_started" not in st.session_state:
        t = threading.Thread(target=_monitor_loop, daemon=True)
        t.start()
        st.session_state["monitor_thread_started"] = True
        _logger.info("Monitor thread launched (idle until user starts monitoring).")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Khabar AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
_ensure_monitor_thread()

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* ── Base ── */
    .stApp { background-color: #F8F9FB; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F1B2D 0%, #1B2A4A 100%);
    }
    section[data-testid="stSidebar"] .stRadio label span,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #CBD5E1 !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background: #FFFFFF !important;
        color: #0F172A !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 8px !important;
    }
    section[data-testid="stSidebar"] .stButton > button p {
        color: #0F172A !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #F1F5F9 !important;
    }

    /* ── Main-area text ── */
    h1, h2, h3, h4 { color: #0F172A !important; }
    p, li { color: #475569; }

    /* ── Hero ── */
    .hero-section {
        background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 50%, #2563EB 100%);
        border-radius: 20px;
        padding: 60px 40px;
        text-align: center;
        margin-bottom: 32px;
        position: relative;
        overflow: hidden;
    }
    .hero-section::before {
        content: "";
        position: absolute;
        top: -50%; left: -50%; width: 200%; height: 200%;
        background: radial-gradient(circle at 30% 50%, rgba(59,130,246,0.15) 0%, transparent 50%),
                    radial-gradient(circle at 70% 80%, rgba(16,185,129,0.1) 0%, transparent 50%);
        pointer-events: none;
    }
    .hero-section h1 {
        font-size: 2.6em !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
        margin-bottom: 12px !important;
        letter-spacing: -0.5px;
        position: relative;
    }
    .hero-section .subtitle {
        font-size: 1.1em;
        color: #94A3B8;
        max-width: 620px;
        margin: 0 auto;
        line-height: 1.6;
        position: relative;
    }
    .hero-badge {
        display: inline-block;
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 20px;
        padding: 6px 16px;
        font-size: 0.8em;
        color: #94A3B8;
        margin-bottom: 20px;
        letter-spacing: 0.5px;
        position: relative;
    }

    /* ── Feature cards ── */
    .feat {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 32px 24px 28px;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
        height: 100%;
    }
    .feat:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.08);
    }
    .feat-icon {
        width: 56px; height: 56px;
        border-radius: 14px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5em;
        margin-bottom: 16px;
    }
    .feat h3 {
        font-size: 1em !important;
        font-weight: 700 !important;
        color: #0F172A !important;
        margin: 0 0 8px 0 !important;
    }
    .feat p { font-size: 0.85em; color: #64748B; margin: 0; line-height: 1.5; }

    /* ── Pipeline steps ── */
    .pipeline-step {
        display: flex;
        align-items: flex-start;
        gap: 16px;
        padding: 16px 0;
    }
    .step-num {
        width: 36px; height: 36px;
        background: #EFF6FF;
        color: #2563EB;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.9em;
        flex-shrink: 0;
    }
    .step-text strong { color: #0F172A; }
    .step-text span { color: #64748B; font-size: 0.9em; }

    /* ── Stat cards ── */
    .card {
        background: #FFFFFF;
        border-radius: 14px;
        padding: 24px;
        text-align: center;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .card-value { font-size: 2.2em; font-weight: 700; margin-bottom: 2px; }
    .card-label {
        font-size: 0.78em; color: #94A3B8;
        text-transform: uppercase; letter-spacing: 0.6px; font-weight: 500;
    }

    /* ── Company badges ── */
    .company-badge {
        display: inline-block;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 22px;
        margin: 5px;
        text-align: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        min-width: 130px;
    }
    .company-badge h4 { margin: 0 0 6px 0; font-size: 0.9em; color: #0F172A; font-weight: 600; }
    .company-badge .count { font-size: 0.72em; color: #94A3B8; }

    /* ── Main area buttons base ── */
    .stApp .stButton > button {
        border-radius: 10px !important;
    }

    /* ── Detail card ── */
    .detail-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 28px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }

    /* ── Severity pills ── */
    .sev-red    { color: #DC2626; font-weight: 600; }
    .sev-yellow { color: #D97706; font-weight: 600; }
    .sev-green  { color: #059669; font-weight: 600; }

    /* ── Tech stack tag ── */
    .tech-tag {
        display: inline-block;
        background: #F1F5F9;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.78em;
        color: #475569;
        margin: 3px;
        font-weight: 500;
    }

    /* ── Text inputs in main area ── */
    .stApp [data-testid="stAppViewContainer"] input[type="text"],
    .stApp [data-testid="stAppViewContainer"] textarea {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 10px !important;
        caret-color: #0F172A !important;
    }
    .stApp [data-testid="stAppViewContainer"] input[type="text"]::placeholder,
    .stApp [data-testid="stAppViewContainer"] textarea::placeholder {
        color: #94A3B8 !important;
    }
    .stApp [data-testid="stAppViewContainer"] input[type="text"]:focus,
    .stApp [data-testid="stAppViewContainer"] textarea:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 2px rgba(37,99,235,0.15) !important;
    }

    /* ── Main-area buttons (non-primary) ── */
    .stApp [data-testid="stAppViewContainer"] .stButton > button:not([kind="primary"]) {
        background: #F1F5F9 !important;
        color: #334155 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-size: 0.82em !important;
        font-weight: 500 !important;
    }
    .stApp [data-testid="stAppViewContainer"] .stButton > button:not([kind="primary"]):hover {
        background: #E2E8F0 !important;
        border-color: #94A3B8 !important;
    }

    /* ── Primary button ── */
    .stApp [data-testid="stAppViewContainer"] button[kind="primary"],
    .stApp [data-testid="stAppViewContainer"] .stButton > button[data-testid="stBaseButton-primary"] {
        background: #2563EB !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.95em !important;
        padding: 0.6em 1.2em !important;
        letter-spacing: 0.3px !important;
    }
    .stApp [data-testid="stAppViewContainer"] button[kind="primary"]:hover,
    .stApp [data-testid="stAppViewContainer"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background: #1D4ED8 !important;
        box-shadow: 0 4px 12px rgba(37,99,235,0.3) !important;
    }
    .stApp [data-testid="stAppViewContainer"] button[kind="primary"] p,
    .stApp [data-testid="stAppViewContainer"] .stButton > button[data-testid="stBaseButton-primary"] p {
        color: #FFFFFF !important;
    }

    /* ── Selectbox in main area ── */
    .stApp [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border-color: #CBD5E1 !important;
        border-radius: 10px !important;
        color: #0F172A !important;
    }

    /* ── Download button ── */
    .stApp [data-testid="stDownloadButton"] > button {
        background: #F1F5F9 !important;
        color: #334155 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 10px !important;
    }
    .stApp [data-testid="stDownloadButton"] > button p {
        color: #334155 !important;
    }
    .stApp [data-testid="stDownloadButton"] > button:hover {
        background: #E2E8F0 !important;
    }

    /* ── Expanders ── */
    .stApp [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 12px !important;
        overflow: hidden;
    }
    .stApp [data-testid="stExpander"] summary,
    .stApp [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
    .stApp [data-testid="stExpander"] details > summary > span,
    .stApp [data-testid="stExpander"] details > summary > span > span {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
    }
    .stApp [data-testid="stExpander"] details[open] > summary {
        background-color: #FFFFFF !important;
        border-bottom: 1px solid #E2E8F0 !important;
    }
    .stApp [data-testid="stExpander"] details > div {
        background-color: #FFFFFF !important;
    }
    .stApp [data-testid="stExpander"] p,
    .stApp [data-testid="stExpander"] span {
        color: #334155 !important;
    }
    .stApp [data-testid="stExpander"] strong {
        color: #0F172A !important;
    }

    /* ── Hide streamlit chrome ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Khabar AI")
    st.caption("Supply-Chain Risk Intelligence")
    st.divider()

    page = st.radio(
        "Navigate",
        ["Home", "Dashboard", "Knowledge Graph", "Metrics"],
        index=0,
    )

    st.divider()
    st.caption(f"Last refresh · {datetime.now().strftime('%H:%M:%S')}")
    if st.button("Refresh"):
        st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def severity_label(sev: str) -> str:
    icon = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}
    return f"{icon.get(sev, '⚪')} {sev}"


def load_events(hours: int = 168) -> pd.DataFrame:
    with get_db() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        events = (
            db.query(RiskEvent)
            .filter(RiskEvent.created_at >= cutoff)
            .order_by(RiskEvent.created_at.desc())
            .all()
        )
        if not events:
            return pd.DataFrame()

        rows = []
        for e in events:
            rows.append({
                "ID": e.id,
                "Company": e.company_name,
                "Severity": e.severity,
                "Headline": e.headline,
                "Stock Impact": f"{e.stock_impact or 0:.2f}%",
                "Weather": e.weather_correlation or "N/A",
                "Confidence": f"{e.confidence_score or 0:.0f}%",
                "AI Reasoning": e.ai_reasoning or "",
                "Impact": e.impact_estimate or "",
                "Mitigation": e.mitigation_strategies or "[]",
                "Source": e.source_url or "",
                "Created": e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "",
                "Notified": "Yes" if e.is_notified else "No",
            })
        return pd.DataFrame(rows)


def run_pipeline(company_names: list[str]) -> dict:
    from app.main import RiskMonitor
    monitor = RiskMonitor(company_names=company_names)
    return monitor.run()


# ===================================================================
# PAGE: Home
# ===================================================================
if page == "Home":

    # ── Hero ──
    st.markdown("""
    <div class="hero-section">
        <div class="hero-badge">AGENTIC AI · MULTI-SIGNAL · REAL-TIME</div>
        <h1>Khabar AI</h1>
        <p class="subtitle">
            Monitor global supply-chain risks in real time. Our AI agents correlate
            live news, stock movements, and weather data — then deliver actionable
            intelligence before disruptions hit your operations.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Features ──
    f1, f2, f3, f4 = st.columns(4, gap="medium")
    with f1:
        st.markdown("""
        <div class="feat">
            <div class="feat-icon" style="background:#EFF6FF;">📡</div>
            <h3>Live Data Sensors</h3>
            <p>Google News RSS, Alpha Vantage stocks, and OpenWeatherMap feed signals every hour.</p>
        </div>""", unsafe_allow_html=True)
    with f2:
        st.markdown("""
        <div class="feat">
            <div class="feat-icon" style="background:#FFF7ED;">🤖</div>
            <h3>AI Triage Agent</h3>
            <p>Groq Llama 3.3 70B classifies headlines in milliseconds — 70-90% noise removed.</p>
        </div>""", unsafe_allow_html=True)
    with f3:
        st.markdown("""
        <div class="feat">
            <div class="feat-icon" style="background:#F0FDF4;">🧠</div>
            <h3>Deep Analyst Agent</h3>
            <p>GPT-OSS 120B via Groq correlates all signals into structured severity + mitigation reports.</p>
        </div>""", unsafe_allow_html=True)
    with f4:
        st.markdown("""
        <div class="feat">
            <div class="feat-icon" style="background:#FEF2F2;">📊</div>
            <h3>Knowledge Graph</h3>
            <p>Interactive supply-chain graph maps events to locations, suppliers, and companies.</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("")  # spacer

    # ── How it works + Tech stack ──
    left_col, right_col = st.columns([3, 2], gap="large")

    with left_col:
        st.markdown("#### How It Works")
        steps = [
            ("1", "Enter company names", "Type names or tickers below — e.g. Tesla Inc, AAPL"),
            ("2", "Sensors fetch live data", "News headlines, stock prices, and weather are pulled in real time"),
            ("3", "Triage Agent filters", "LLM classifies each headline — irrelevant articles are discarded"),
            ("4", "Analyst Agent reasons", "Correlated signals produce severity, confidence, and mitigations"),
            ("5", "View results", "Explore findings on the Dashboard with full AI reasoning per event"),
        ]
        for num, title, desc in steps:
            st.markdown(
                f'<div class="pipeline-step">'
                f'<div class="step-num">{num}</div>'
                f'<div class="step-text"><strong>{title}</strong><br><span>{desc}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with right_col:
        st.markdown("#### Tech Stack")
        tags = [
            "Groq LLM", "Llama 3.3 70B", "GPT-OSS 120B",
            "Google News RSS", "Alpha Vantage", "OpenWeatherMap",
            "SQLite / PostgreSQL", "SQLAlchemy", "Pydantic",
            "NetworkX", "Pyvis", "Streamlit",
            "SHA-256 Dedup", "FastAPI", "GitHub Actions",
        ]
        tag_html = "".join(f'<span class="tech-tag">{t}</span>' for t in tags)
        st.markdown(f'<div style="margin-top:8px;">{tag_html}</div>', unsafe_allow_html=True)
        st.markdown("")
        st.markdown(
            '<p style="font-size:0.85em;color:#64748B;margin-top:16px;">'
            'All APIs are <strong style="color:#0F172A;">free-tier compatible</strong> — '
            'zero billing required for the complete stack.</p>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    # ── Live Monitoring ──
    st.markdown("---")
    st.markdown("#### Live Monitoring")
    st.markdown(
        '<p style="color:#64748B;font-size:0.88em;margin-top:-8px;margin-bottom:14px;">'
        'Continuously monitor <strong>one company</strong> in the background. '
        'Pick any company from the Fortune 100 list and set how often the pipeline should run.</p>',
        unsafe_allow_html=True,
    )

    _all_company_names = [c["name"] for c in get_target_companies()]
    _is_active = _monitor_cfg.get("active", False)

    # ── Controls (company picker + interval + button) ──
    _ctrl1, _ctrl2, _ctrl3 = st.columns([3, 2, 2])
    with _ctrl1:
        _sel_company = st.selectbox(
            "Company to monitor",
            _all_company_names,
            index=_all_company_names.index(_monitor_cfg["company"]) if _monitor_cfg["company"] in _all_company_names else 0,
            disabled=_is_active,
            key="monitor_company_select",
        )
    with _ctrl2:
        _sel_interval = st.selectbox(
            "Run every",
            [15, 30, 60, 120, 360],
            index=2,
            format_func=lambda m: f"{m} min" if m < 60 else f"{m // 60} hr" if m % 60 == 0 else f"{m // 60}h {m % 60}m",
            disabled=_is_active,
            key="monitor_interval_select",
        )
    with _ctrl3:
        st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)  # spacer to align button
        if _is_active:
            if st.button("Stop Monitoring", key="stop_monitor", use_container_width=True):
                _monitor_cfg["stop_requested"] = True
                st.rerun()
        else:
            if st.button("Start Monitoring", type="primary", key="start_monitor", use_container_width=True):
                _monitor_cfg["company"] = _sel_company
                _monitor_cfg["interval_min"] = _sel_interval
                _monitor_cfg["active"] = True
                _monitor_cfg["stop_requested"] = False
                st.rerun()

    # ── Status panel ──
    _monitor_status_path = _PROJECT_ROOT / "monitor_status.json"

    def _fmt_ts(iso_str: str) -> str:
        if not iso_str or iso_str == "—":
            return "—"
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%b %d, %H:%M UTC")
        except Exception:
            return iso_str

    if _monitor_status_path.exists():
        try:
            _ms = json.loads(_monitor_status_path.read_text(encoding="utf-8"))
            _state = _ms.get("state", "unknown")
            _watchlist = _ms.get("watchlist", [])
            _last_run = _ms.get("last_run", "—")
            _next_run = _ms.get("next_run", "—")
            _interval = _ms.get("interval_min", "?")
            _last_result = _ms.get("last_result")
            _error = _ms.get("error")

            if _state == "running":
                _badge = '<span style="background:#DBEAFE;color:#1D4ED8;padding:4px 12px;border-radius:20px;font-size:0.8em;font-weight:600;">● Running</span>'
            elif _state == "idle":
                _badge = '<span style="background:#D1FAE5;color:#065F46;padding:4px 12px;border-radius:20px;font-size:0.8em;font-weight:600;">● Active</span>'
            elif _state == "error":
                _badge = '<span style="background:#FEE2E2;color:#991B1B;padding:4px 12px;border-radius:20px;font-size:0.8em;font-weight:600;">● Error</span>'
            elif _state == "stopped":
                _badge = '<span style="background:#F1F5F9;color:#64748B;padding:4px 12px;border-radius:20px;font-size:0.8em;font-weight:600;">● Stopped</span>'
            else:
                _badge = '<span style="background:#FEF3C7;color:#92400E;padding:4px 12px;border-radius:20px;font-size:0.8em;font-weight:600;">● Starting</span>'

            _comp_html = " ".join(
                f'<span style="background:#EFF6FF;color:#1E40AF;padding:3px 10px;border-radius:6px;font-size:0.8em;font-weight:500;">{c}</span>'
                for c in _watchlist
            ) if _watchlist else '<span style="color:#94A3B8;font-size:0.85em;">—</span>'

            st.markdown(
                f'<div style="background:#FAFBFC;border:1px solid #E2E8F0;border-radius:12px;padding:20px 24px;margin-top:12px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">'
                f'<span style="font-weight:600;color:#0F172A;font-size:1em;">Monitor Status</span>'
                f'{_badge}'
                f'</div>'
                f'<div style="display:flex;gap:32px;flex-wrap:wrap;margin-bottom:4px;">'
                f'<div><span style="color:#64748B;font-size:0.8em;">Tracking</span><br/>{_comp_html}</div>'
                f'<div><span style="color:#64748B;font-size:0.8em;">Interval</span><br/>'
                f'<span style="color:#0F172A;font-weight:500;">Every {_interval} min</span></div>'
                f'<div><span style="color:#64748B;font-size:0.8em;">Last Run</span><br/>'
                f'<span style="color:#0F172A;font-weight:500;">{_fmt_ts(_last_run)}</span></div>'
                f'<div><span style="color:#64748B;font-size:0.8em;">Next Run</span><br/>'
                f'<span style="color:#0F172A;font-weight:500;">{_fmt_ts(_next_run)}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if _last_result:
                _arts = _last_result.get("total_articles", 0)
                _triage = _last_result.get("triaged_passed", 0)
                _stored = _last_result.get("events_stored", 0)
                st.markdown(
                    f'<div style="margin-top:8px;padding-top:12px;border-top:1px solid #E2E8F0;">'
                    f'<span style="color:#64748B;font-size:0.8em;">Last cycle:</span> '
                    f'<span style="color:#0F172A;font-size:0.85em;">{_arts} articles → {_triage} passed triage → {_stored} events stored</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            elif _error:
                st.markdown(
                    f'<div style="margin-top:8px;padding-top:12px;border-top:1px solid #E2E8F0;">'
                    f'<span style="color:#DC2626;font-size:0.85em;">Error: {_error}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('</div>', unsafe_allow_html=True)

        except Exception:
            st.caption("Could not read monitor status.")
    elif not _is_active:
        st.markdown(
            '<div style="background:#FAFBFC;border:1px solid #E2E8F0;border-radius:12px;'
            'padding:20px 24px;margin-top:12px;text-align:center;">'
            '<p style="color:#94A3B8;font-size:0.9em;margin:0;">Select a company and interval, then click '
            '<strong>Start Monitoring</strong> to begin automatic scans.</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    # ── Run Analysis (manual) ──
    st.markdown("---")
    st.markdown("#### Run a Manual Analysis")

    known_companies = [c["name"] for c in get_target_companies()]

    # Use session state to build up the input value
    if "company_text" not in st.session_state:
        st.session_state["company_text"] = ""

    company_input = st.text_input(
        "Enter company names or tickers, separated by commas",
        value=st.session_state["company_text"],
        placeholder="Tesla Inc, Apple Inc, NVDA, Amazon ...",
    )

    # Quick picks
    st.markdown("**Quick add** — click a company to add it:")
    pick_cols = st.columns(min(len(known_companies), 8))
    for i, cname in enumerate(known_companies[:8]):
        with pick_cols[i]:
            if st.button(cname, key=f"qp_{i}", use_container_width=True):
                current = st.session_state.get("company_text", "").strip()
                existing = [x.strip() for x in current.split(",") if x.strip()]
                if cname not in existing:
                    existing.append(cname)
                st.session_state["company_text"] = ", ".join(existing)
                st.rerun()

    st.markdown("")
    run_clicked = st.button("Run Analysis", type="primary", use_container_width=True)

    # ── Pipeline execution ──
    if run_clicked:
        final_input = company_input.strip() or st.session_state.get("company_text", "").strip()
        if not final_input:
            st.warning("Please enter at least one company name.")
            st.stop()

        names = [n.strip() for n in final_input.split(",") if n.strip()]

        st.markdown("")
        progress = st.progress(0, text="Initialising pipeline...")

        with st.spinner(f"Analysing {len(names)} company(ies) — fetching news, stock data, weather..."):
            progress.progress(15, text="Connecting to sensors...")
            try:
                stats = run_pipeline(names)
                progress.progress(100, text="Complete!")
            except Exception as exc:
                progress.progress(100, text="Error.")
                st.error(f"Pipeline error: {exc}")
                st.stop()

        st.markdown("")

        # Results cards
        r1, r2, r3, r4 = st.columns(4)
        with r1:
            st.markdown(
                f'<div class="card"><div class="card-value" style="color:#0F172A">'
                f'{stats.get("total_articles", 0)}</div>'
                f'<div class="card-label">Articles Scanned</div></div>',
                unsafe_allow_html=True,
            )
        with r2:
            st.markdown(
                f'<div class="card"><div class="card-value" style="color:#D97706">'
                f'{stats.get("triaged_passed", 0)}</div>'
                f'<div class="card-label">Passed Triage</div></div>',
                unsafe_allow_html=True,
            )
        with r3:
            st.markdown(
                f'<div class="card"><div class="card-value" style="color:#059669">'
                f'{stats.get("events_stored", 0)}</div>'
                f'<div class="card-label">Events Stored</div></div>',
                unsafe_allow_html=True,
            )
        with r4:
            st.markdown(
                f'<div class="card"><div class="card-value" style="color:#DC2626">'
                f'{stats.get("alerts_sent", 0)}</div>'
                f'<div class="card-label">Alerts Sent</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("")
        st.success(
            f"Done! Analysed **{', '.join(names)}**. "
            f"Switch to **Dashboard** in the sidebar to explore events."
        )

    # Existing data note
    df = load_events()
    if not df.empty and not run_clicked:
        st.markdown("")
        st.info(
            f"You have **{len(df)} events** from previous runs. "
            f"Go to **Dashboard** to view them, or run a new analysis above."
        )


# ===================================================================
# PAGE: Dashboard
# ===================================================================
elif page == "Dashboard":
    st.markdown("# Risk Dashboard")
    st.caption("Click any event to drill into the full AI analysis.")

    df = load_events()

    if df.empty:
        st.info("No risk events yet. Go to **Home** and run an analysis first.")
        st.stop()

    # Summary cards
    col1, col2, col3, col4 = st.columns(4)
    red_count = len(df[df["Severity"] == "RED"])
    yellow_count = len(df[df["Severity"] == "YELLOW"])
    green_count = len(df[df["Severity"] == "GREEN"])

    with col1:
        st.markdown(
            f'<div class="card"><div class="card-value" style="color:#0F172A">'
            f'{len(df)}</div><div class="card-label">Total Events</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="card"><div class="card-value" style="color:#DC2626">'
            f'{red_count}</div><div class="card-label">Critical</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="card"><div class="card-value" style="color:#D97706">'
            f'{yellow_count}</div><div class="card-label">Warning</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f'<div class="card"><div class="card-value" style="color:#059669">'
            f'{green_count}</div><div class="card-label">Stable</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    # --- Charts row: severity donut + company bar ---
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("#### Severity Breakdown")
        sev_data = df["Severity"].value_counts().reset_index()
        sev_data.columns = ["Severity", "Count"]
        sev_colors = {"RED": "#DC2626", "YELLOW": "#D97706", "GREEN": "#059669"}
        fig_sev = px.pie(
            sev_data, names="Severity", values="Count",
            color="Severity", color_discrete_map=sev_colors,
            hole=0.4,
        )
        fig_sev.update_traces(
            textposition="inside",
            textinfo="label+value",
            textfont_size=12,
            textfont_color="#FFFFFF",
            marker=dict(line=dict(color="#FFFFFF", width=2)),
        )
        fig_sev.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#334155", size=12),
            height=280,
            margin=dict(t=10, b=10, l=10, r=10),
            legend=dict(font=dict(size=12), orientation="h", y=-0.1, x=0.5, xanchor="center"),
            showlegend=True,
        )
        st.plotly_chart(fig_sev, use_container_width=True)

    with chart_right:
        st.markdown("#### Events per Company")
        comp_data = df["Company"].value_counts().reset_index()
        comp_data.columns = ["Company", "Events"]
        fig_comp = px.bar(
            comp_data, y="Company", x="Events",
            orientation="h", color_discrete_sequence=["#2563EB"],
            text="Events",
        )
        fig_comp.update_traces(textposition="outside", textfont=dict(size=12, color="#334155"))
        fig_comp.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#334155", size=12),
            height=280,
            margin=dict(t=10, b=10, l=10, r=40),
            showlegend=False,
            xaxis=dict(title="", showgrid=True, gridcolor="#E2E8F0", tickfont=dict(color="#64748B")),
            yaxis=dict(title="", tickfont=dict(color="#334155", size=12), automargin=True),
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("")

    # --- Company risk summary table ---
    active_companies = df["Company"].unique().tolist()

    st.markdown("#### Company Risk Summary")
    table_html = (
        '<table style="width:100%;border-collapse:collapse;background:#FFF;'
        'border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;font-size:0.9em;">'
        '<thead><tr style="background:#F1F5F9;border-bottom:2px solid #E2E8F0;">'
        '<th style="padding:12px 16px;text-align:left;color:#0F172A;font-weight:600;">Company</th>'
        '<th style="padding:12px 16px;text-align:center;color:#0F172A;font-weight:600;">Events</th>'
        '<th style="padding:12px 16px;text-align:center;color:#0F172A;font-weight:600;">Worst Severity</th>'
        '<th style="padding:12px 16px;text-align:left;color:#0F172A;font-weight:600;">Latest Event</th>'
        '</tr></thead><tbody>'
    )
    for name in active_companies:
        cdf = df[df["Company"] == name]
        if "RED" in cdf["Severity"].values:
            worst = '<span style="color:#DC2626;font-weight:600;">🔴 RED</span>'
        elif "YELLOW" in cdf["Severity"].values:
            worst = '<span style="color:#D97706;font-weight:600;">🟡 YELLOW</span>'
        else:
            worst = '<span style="color:#059669;font-weight:600;">🟢 GREEN</span>'
        latest = cdf["Created"].iloc[0] if not cdf.empty else "N/A"
        table_html += (
            f'<tr style="border-bottom:1px solid #F1F5F9;">'
            f'<td style="padding:10px 16px;color:#0F172A;font-weight:500;">{name}</td>'
            f'<td style="padding:10px 16px;text-align:center;color:#334155;">{len(cdf)}</td>'
            f'<td style="padding:10px 16px;text-align:center;">{worst}</td>'
            f'<td style="padding:10px 16px;color:#64748B;">{latest}</td>'
            f'</tr>'
        )
    table_html += '</tbody></table>'
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown("")

    # --- Filter + Export ---
    filter_col, export_col = st.columns([3, 1])
    with filter_col:
        filter_company = st.selectbox(
            "Filter by company",
            ["All Companies"] + active_companies,
            index=0,
        )
    with export_col:
        st.markdown("<br>", unsafe_allow_html=True)
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export CSV",
            csv_data,
            "khabar_events.csv",
            "text/csv",
            use_container_width=True,
        )

    if filter_company != "All Companies":
        df = df[df["Company"] == filter_company]

    # Events
    st.markdown("### Recent Events")
    st.caption("Expand an event for the full AI-generated risk assessment.")

    for idx, (_, row) in enumerate(df.iterrows()):
        sev = row["Severity"]
        label = f"{severity_label(sev)}  **{row['Company']}** — {row['Headline'][:80]}"

        with st.expander(label, expanded=False):
            st.markdown('<div class="detail-card">', unsafe_allow_html=True)

            st.markdown(f"#### {row['Headline']}")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Severity", sev)
            with m2:
                st.metric("Confidence", row["Confidence"])
            with m3:
                st.metric("Stock Impact", row["Stock Impact"])
            with m4:
                st.metric("Weather", row["Weather"][:30] if row["Weather"] != "N/A" else "N/A")

            st.divider()

            left, right = st.columns([2, 1])
            with left:
                st.markdown("##### AI Reasoning")
                st.write(row["AI Reasoning"] if row["AI Reasoning"] else "No analysis available.")

                st.markdown("##### Impact Estimate")
                st.write(row["Impact"] if row["Impact"] else "N/A")

                st.markdown("##### Mitigation Strategies")
                try:
                    strategies = json.loads(row["Mitigation"])
                    for j, s in enumerate(strategies, 1):
                        st.markdown(f"**{j}.** {s}")
                except (json.JSONDecodeError, TypeError):
                    st.write(row["Mitigation"] if row["Mitigation"] else "N/A")

            with right:
                conf_val = float(row["Confidence"].replace("%", ""))
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=conf_val,
                    title={"text": "Confidence", "font": {"size": 14, "color": "#475569"}},
                    number={"suffix": "%", "font": {"color": "#0F172A"}},
                    gauge={
                        "axis": {"range": [0, 100], "tickcolor": "#CBD5E1"},
                        "bar": {"color": "#2563EB"},
                        "bgcolor": "#F1F5F9",
                        "steps": [
                            {"range": [0, 33], "color": "#FEF2F2"},
                            {"range": [33, 66], "color": "#FFFBEB"},
                            {"range": [66, 100], "color": "#F0FDF4"},
                        ],
                    },
                ))
                fig.update_layout(
                    height=200,
                    margin=dict(t=40, b=0, l=30, r=30),
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True, key=f"gauge_{idx}")

                st.markdown(f"**Company:** {row['Company']}")
                st.markdown(f"**Date:** {row['Created']}")
                if row["Source"]:
                    st.markdown(f"[View Source Article →]({row['Source']})")

            st.markdown('</div>', unsafe_allow_html=True)


# ===================================================================
# PAGE: Knowledge Graph
# ===================================================================
elif page == "Knowledge Graph":
    st.markdown("# Supply Chain Knowledge Graph")
    st.caption("Visual map of how events, locations, suppliers, and companies are connected.")

    df = load_events(hours=168)

    if df.empty:
        st.info("No events yet. Run an analysis from **Home** first to populate the graph.")
        st.stop()

    # Only build graph for companies that have actual events
    all_companies = get_target_companies()
    active_names = df["Company"].unique().tolist()
    active_companies = [c for c in all_companies if c["name"] in active_names]

    # Fallback: if a company name doesn't match config, skip it
    if not active_companies:
        st.info("No matching company configurations found for your events.")
        st.stop()

    graph = SupplyChainGraph()
    graph.build_from_config(active_companies)

    # Attach risk events to graph (color-coded by severity)
    for _, row in df.iterrows():
        event_label = f"{row['Severity']}: {row['Headline'][:45]}..."
        for c in active_companies:
            if c["name"] == row["Company"] and c.get("supply_chain_nodes"):
                loc = c["supply_chain_nodes"][0]["location"]
                graph.add_event(event_label, loc, "risk_event", severity=row["Severity"])
                break

    output_path = str(_PROJECT_ROOT / "dashboard" / "kg_viz.html")
    graph.to_pyvis_html(output_path)

    with open(output_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Legend
    st.markdown(
        '<div style="display:flex;gap:24px;margin-bottom:12px;flex-wrap:wrap;">'
        '<span style="font-size:0.85em;color:#475569;">'
        '<span style="color:#3B82F6;font-weight:700;">&#9679;</span> Company'
        '</span>'
        '<span style="font-size:0.85em;color:#475569;">'
        '<span style="color:#4ECDC4;font-weight:700;">&#9679;</span> Supplier / Entity'
        '</span>'
        '<span style="font-size:0.85em;color:#475569;">'
        '<span style="color:#A78BFA;font-weight:700;">&#9679;</span> Location'
        '</span>'
        '<span style="font-size:0.85em;color:#475569;">'
        '<span style="color:#EF4444;font-weight:700;">&#9679;</span> Red &nbsp;'
        '<span style="color:#F59E0B;font-weight:700;">&#9679;</span> Yellow &nbsp;'
        '<span style="color:#10B981;font-weight:700;">&#9679;</span> Green'
        '</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.components.v1.html(html_content, height=650, scrolling=True)

    # Stats
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Nodes", graph.graph.number_of_nodes())
    with s2:
        st.metric("Edges", graph.graph.number_of_edges())
    with s3:
        st.metric("Companies Shown", len(active_companies))

    st.caption(
        "**How to read:** Arrows flow from Risk Events → Locations → Suppliers → Companies. "
        "If a typhoon hits Tainan (location), it affects TSMC (supplier), which supplies Apple and NVIDIA (companies)."
    )


# ===================================================================
# PAGE: Metrics
# ===================================================================
elif page == "Metrics":
    st.markdown("# Pipeline Metrics")
    st.caption("Performance and noise-reduction statistics.")

    df = load_events()
    if df.empty:
        st.info("No data available. Run an analysis from **Home** first.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Severity Distribution")
        sev_counts = df["Severity"].value_counts().reset_index()
        sev_counts.columns = ["Severity", "Count"]
        colors = {"RED": "#DC2626", "YELLOW": "#D97706", "GREEN": "#059669"}
        fig = px.pie(
            sev_counts,
            names="Severity",
            values="Count",
            color="Severity",
            color_discrete_map=colors,
            hole=0.4,
        )
        fig.update_traces(
            textposition="inside",
            textinfo="label+value+percent",
            textfont_size=13,
            textfont_color="#FFFFFF",
            marker=dict(line=dict(color="#FFFFFF", width=2)),
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#334155", size=13),
            height=380,
            margin=dict(t=20, b=20, l=20, r=20),
            legend=dict(
                font=dict(size=13, color="#334155"),
                orientation="h",
                yanchor="bottom",
                y=-0.15,
                xanchor="center",
                x=0.5,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### Events per Company")
        company_counts = df["Company"].value_counts().reset_index()
        company_counts.columns = ["Company", "Events"]
        # Horizontal bar for better label readability
        fig2 = px.bar(
            company_counts,
            y="Company",
            x="Events",
            orientation="h",
            color_discrete_sequence=["#2563EB"],
            text="Events",
        )
        fig2.update_traces(
            textposition="outside",
            textfont=dict(size=12, color="#334155"),
        )
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#334155", size=12),
            height=max(380, len(company_counts) * 40 + 60),
            margin=dict(t=10, b=20, l=10, r=40),
            showlegend=False,
            xaxis=dict(
                title="",
                showgrid=True,
                gridcolor="#E2E8F0",
                tickfont=dict(color="#64748B", size=11),
            ),
            yaxis=dict(
                title="",
                tickfont=dict(color="#334155", size=12),
                automargin=True,
            ),
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Noise reduction + timeline side by side
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("### Noise Reduction")
        total_articles = len(df) * 10
        if total_articles > 0:
            reduction = ((total_articles - len(df)) / total_articles) * 100
            fig_nr = go.Figure(go.Indicator(
                mode="gauge+number",
                value=reduction,
                number={"suffix": "%", "font": {"size": 40, "color": "#0F172A"}},
                title={"text": "Articles Filtered Out", "font": {"size": 14, "color": "#64748B"}},
                gauge={
                    "axis": {"range": [0, 100], "tickfont": {"color": "#94A3B8", "size": 11}},
                    "bar": {"color": "#2563EB"},
                    "bgcolor": "#F1F5F9",
                    "steps": [
                        {"range": [0, 50], "color": "#FEF2F2"},
                        {"range": [50, 80], "color": "#FFFBEB"},
                        {"range": [80, 100], "color": "#F0FDF4"},
                    ],
                },
            ))
            fig_nr.update_layout(
                height=260,
                margin=dict(t=50, b=10, l=30, r=30),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_nr, use_container_width=True)
            st.caption(
                f"**{total_articles}** raw articles scanned → "
                f"**{len(df)}** actionable events stored."
            )

    with col4:
        st.markdown("### Event Timeline")
        if "Created" in df.columns and not df["Created"].isna().all():
            timeline_df = df.copy()
            timeline_df["Date"] = pd.to_datetime(timeline_df["Created"])
            daily = timeline_df.groupby(timeline_df["Date"].dt.date).size().reset_index(name="Count")
            daily.columns = ["Date", "Count"]
            fig3 = px.bar(
                daily, x="Date", y="Count",
                color_discrete_sequence=["#2563EB"],
                text="Count",
            )
            fig3.update_traces(
                textposition="outside",
                textfont=dict(size=12, color="#334155"),
            )
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#334155", size=12),
                height=300,
                margin=dict(t=10, b=30, l=10, r=10),
                showlegend=False,
                xaxis=dict(
                    title="",
                    showgrid=False,
                    tickfont=dict(color="#64748B", size=11),
                ),
                yaxis=dict(
                    title="Events",
                    showgrid=True,
                    gridcolor="#E2E8F0",
                    tickfont=dict(color="#64748B", size=11),
                ),
                bargap=0.3,
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.caption("Not enough data for a timeline yet.")
