import html
import json
import re
import traceback
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from streamlit_autorefresh import st_autorefresh

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from resources.settlement_excel_import import (
    delete_all_settlement_data,
    get_import_preview,
    get_supabase_client,
    save_excel_to_supabase,
)
from resources.settlement_processor import (
    process_settlement_session,
    report_as_dict,
)
from resources.settlement_parameters import recalculate_excel_base_rates
from resources.settlement_pdf import build_settlement_pdf, build_tig_breakdown, build_tig_pdf
from resources.courier_master_db import update_courier_master_profile
from resources.peopleforce_documents import (
    create_peopleforce_complaint,
    delete_peopleforce_complaint,
    delete_peopleforce_document,
    decode_document_content,
    read_peopleforce_document_content,
    read_peopleforce_documents_for_courier,
    read_peopleforce_documents_for_month,
    read_peopleforce_card_statuses,
    read_peopleforce_card_statuses_for_month,
    read_peopleforce_complaints_for_month,
    respond_to_peopleforce_complaint,
    update_peopleforce_complaints_status_for_process,
    update_peopleforce_complaint_status,
    upsert_peopleforce_card_status,
    upload_peopleforce_document,
    upload_peopleforce_document_bytes,
)
from resources.profile_route_metrics import resolve_profile_route_metrics
from page.settlement_parameter_catalog import render_parameter_catalog

try:
    from resources.dsp_route_explanations import (
        read_order_details_for_routes,
        read_route_stories,
    )
except Exception:
    read_order_details_for_routes = None
    read_route_stories = None

RESERVE_TARGET_HUF = 50_000
RESERVE_RATE = 0.10
INSURANCE_FEE_HUF = 10_000
DEFAULT_LOYALTY_MONTHS_REQUIRED = 6
ROUTE_ISSUE_STATUSES = ["Nincs reklamáció", "Vizsgálat", "Elfogadva", "Elutasítva", "Lezárva"]
CUSTOMER_RATING_UPLOAD_TABLE = "bill_jitt_invoice_customer_rating_bonus"

st.set_page_config(
    page_title="Új Elszámolási oldal",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

from resources.auth import (
    login_screen,
    logout_button,
)

login_screen()

@st.cache_resource
def get_db():
    return get_supabase_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"],
    )


supabase = get_db()


if "user" not in st.session_state:
    st.stop()

user = st.session_state["user"]

st.sidebar.success(f"Felhasználó: {user['username']}")
st.sidebar.info(f"Jogosultság: {user['role']}")
logout_button()
devtest_page = st.sidebar.radio(
    "Devtest oldal",
    ["Elszamolas", "PDF minta"],
    key="devtest_page",
)

def apply_design() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg:#f5f7fb; --surface:#ffffff; --text:#17351F; --muted:#5E7464;
            --border:#e4e9f2; --primary:#2f6fed; --primary-dark:#2459bf;
            --green:#1f9d74; --yellow:#f0b429; --red:#e05260;
            --shadow:0 10px 30px rgba(20,40,80,.07);
        }
        .stApp { background:var(--bg); }
        .block-container { max-width:1540px; padding-top:1.1rem; padding-bottom:3rem; }
        [data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--border); }
        .premium-hero {
            display:flex; justify-content:space-between; align-items:center; gap:24px;
            background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%);
            border:1px solid var(--border); border-radius:22px; padding:24px 28px;
            box-shadow:var(--shadow); margin-bottom:18px;
        }
        .hero-left .badge {
            display:inline-block; background:#dfeaff; color:var(--primary-dark);
            border-radius:999px; padding:6px 11px; font-size:12px; font-weight:800;
            letter-spacing:.04em; margin-bottom:10px;
        }
        .hero-left h1 { margin:0; color:var(--text); font-size:32px; line-height:1.12; }
        .hero-left p { margin:8px 0 0; color:var(--muted); font-size:15px; }
        .month-pill {
            min-width:210px; text-align:center; background:#fff; border:1px solid var(--border);
            border-radius:16px; padding:14px 18px; box-shadow:0 6px 18px rgba(20,40,80,.05);
        }
        .month-pill .label { color:var(--muted); font-size:12px; margin-bottom:5px; }
        .month-pill .value { color:var(--text); font-size:18px; font-weight:800; }
        .section-title { color:var(--text); font-size:18px; font-weight:800; margin:12px 0; }
        .kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:18px; }
        .kpi {
            background:#fff; border:1px solid var(--border); border-radius:18px; padding:17px 18px;
            box-shadow:0 6px 20px rgba(20,40,80,.045); position:relative; overflow:hidden;
        }
        .kpi:before { content:""; position:absolute; inset:0 auto 0 0; width:5px; background:var(--accent); }
        .kpi .k-label { color:var(--muted); font-size:13px; margin-bottom:8px; }
        .kpi .k-value { color:var(--text); font-size:25px; font-weight:850; line-height:1.1; }
        .kpi .k-note { color:var(--muted); font-size:12px; margin-top:8px; }
        .table-card {
            background:#fff; border:1px solid var(--border); border-radius:20px;
            box-shadow:var(--shadow); overflow:hidden; margin-top:4px;
        }
        .table-card-head {
            display:flex; align-items:center; justify-content:space-between; gap:16px;
            padding:18px 20px; border-bottom:1px solid var(--border); background:#fff;
        }
        .table-card-head h3 { margin:0; color:var(--text); font-size:18px; }
        .table-card-head span { color:var(--muted); font-size:12px; }
        .premium-table { width:100%; border-collapse:separate; border-spacing:0; }
        .premium-table th {
            background:#f8fafc; color:#657084; font-size:12px; text-transform:uppercase;
            letter-spacing:.035em; text-align:left; padding:13px 16px; border-bottom:1px solid var(--border);
        }
        .premium-table td {
            padding:15px 16px; border-bottom:1px solid #edf1f6; color:#274630; font-size:14px;
            vertical-align:middle;
        }
        .premium-table tbody tr:hover { background:#fbfdff; }
        .premium-table tbody tr:last-child td { border-bottom:none; }
        .courier-name { font-weight:800; color:var(--text); }
        .courier-sub { color:var(--muted); font-size:12px; margin-top:2px; }
        .money { font-variant-numeric:tabular-nums; white-space:nowrap; }
        .payable { font-weight:850; color:#1d2b44; }
        .status-badge {
            display:inline-flex; align-items:center; gap:7px; border-radius:999px;
            padding:6px 10px; font-size:12px; font-weight:800; white-space:nowrap;
        }
        .status-red { background:#fff0f2; color:#b42334; }
        .status-yellow { background:#fff8e7; color:#9a6700; }
        .status-green { background:#eaf8f2; color:#157254; }
        .status-blue { background:#eaf2ff; color:#1f5fbf; }
        .status-purple { background:#f2eaff; color:#6b21c9; }
        .status-orange { background:#fff2e5; color:#c85b00; }
        .led {
            display:inline-block; width:14px; height:14px; border-radius:50%;
            box-shadow:inset 0 1px 1px rgba(255,255,255,.7), 0 0 0 3px rgba(0,0,0,.03), 0 2px 6px rgba(0,0,0,.18);
        }
        .led-red { background:radial-gradient(circle at 35% 30%,#ffb3bd 0 18%,#f05a6b 35%,#c92f43 75%); }
        .led-yellow { background:radial-gradient(circle at 35% 30%,#fff0a6 0 18%,#f4c542 35%,#d69900 75%); }
        .led-green { background:radial-gradient(circle at 35% 30%,#a8f0d6 0 18%,#29b784 35%,#15775a 75%); }
        .led-blue { background:radial-gradient(circle at 35% 30%,#b8d7ff 0 18%,#3b82f6 35%,#1d4ed8 75%); }
        .led-purple { background:radial-gradient(circle at 35% 30%,#dfc5ff 0 18%,#8b5cf6 35%,#6d28d9 75%); }
        .led-orange { background:radial-gradient(circle at 35% 30%,#ffd2a8 0 18%,#f59e0b 35%,#c65b00 75%); }
        .table-footer {
            display:flex; justify-content:space-between; align-items:center; padding:14px 18px;
            border-top:1px solid var(--border); background:#fbfcfe; color:var(--muted); font-size:12px;
        }
        .pager { display:flex; gap:6px; }
        .pager span { width:28px; height:28px; display:grid; place-items:center; border:1px solid var(--border); border-radius:8px; background:#fff; }
        .pager .active { background:var(--primary); color:#fff; border-color:var(--primary); }
        .stButton > button, .stDownloadButton > button { min-height:42px; border-radius:11px; font-weight:750; }
        .stButton > button[kind="primary"] { background:var(--primary); border-color:var(--primary); }
        div[data-baseweb="select"] > div, div[data-testid="stTextInputRootElement"] { border-radius:11px; }
        .side-note { color:var(--muted); font-size:12px; line-height:1.45; }
        @media (max-width:1000px) {
            .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .premium-hero { align-items:flex-start; flex-direction:column; }
            .month-pill { width:100%; }
            .table-card { overflow-x:auto; }
            .premium-table { min-width:950px; }
        }
        
/* --- Egységes zöld arculat --- */
div.stButton > button[kind="primary"],
div.stDownloadButton > button {
    background: #1FA64A !important;
    border-color: #1FA64A !important;
    color: white !important;
}

div.stButton > button[kind="primary"]:hover,
div.stDownloadButton > button:hover {
    background: #17853B !important;
    border-color: #17853B !important;
}

div.stButton > button:not([kind="primary"]) {
    border-color: #BDE9C9 !important;
}

div.stButton > button:not([kind="primary"]):hover {
    border-color: #1FA64A !important;
    color: #17853B !important;
    background: #F4FBF5 !important;
}

div[data-baseweb="tab-list"] button[aria-selected="true"] {
    color: #17853B !important;
    border-bottom-color: #1FA64A !important;
}

div[data-baseweb="tab-highlight"] {
    background-color: #1FA64A !important;
}

div[data-testid="stCheckbox"] svg,
div[data-testid="stRadio"] svg {
    color: #1FA64A !important;
}

div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within,
textarea:focus {
    border-color: #1FA64A !important;
    box-shadow: 0 0 0 1px #1FA64A !important;
}

div[data-testid="stMetricValue"] {
    color: #17351F !important;
}

.green-accent-card {
    background: linear-gradient(135deg, #F4FBF5 0%, #FFFFFF 100%);
    border: 1px solid #DDF5E4;
    border-left: 5px solid #1FA64A;
}

.workload-kpi-card {
    border: 1px solid #DCE8DE;
    border-radius: 8px;
    padding: 14px 16px;
    min-height: 94px;
    background: #FFFFFF;
}
.workload-kpi-card.is-good {
    background: #EAF8EF;
    border-color: #8AD39F;
}
.workload-kpi-label {
    color: #52655A;
    font-size: 13px;
    font-weight: 800;
    margin-bottom: 10px;
}
.workload-kpi-value {
    color: #17351F;
    font-size: 30px;
    font-weight: 850;
    line-height: 1.1;
}
.workload-kpi-card.is-good .workload-kpi-value {
    color: #17853B;
}


.summary-donut-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin: 18px 0 22px 0;
}
.summary-donut-card {
    background: #ffffff;
    border: 1px solid #DDF5E4;
    border-radius: 20px;
    padding: 18px 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 165px;
    box-shadow: 0 10px 28px rgba(23, 133, 59, 0.08);
}
.summary-donut-title {
    color: #5E7464;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 8px;
}
.summary-donut-value {
    color: #17351F;
    font-size: 28px;
    line-height: 1.1;
    font-weight: 850;
}
.summary-donut-note {
    color: #7A8F7F;
    font-size: 12px;
    margin-top: 8px;
}
.summary-donut {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    position: relative;
    flex: 0 0 120px;
    display: grid;
    place-items: center;
}
.summary-donut-primary {
    background: conic-gradient(#1FA64A 0 72%, #DDF5E4 72% 100%);
}
.summary-donut-secondary {
    background: conic-gradient(#17853B 0 66%, #DDF5E4 66% 100%);
}
.summary-donut::after {
    content: "";
    position: absolute;
    width: 76px;
    height: 76px;
    border-radius: 50%;
    background: #ffffff;
}
.summary-donut-center {
    position: relative;
    z-index: 1;
    text-align: center;
    color: #17351F;
    line-height: 1.05;
}
.summary-donut-center strong {
    display: block;
    font-size: 16px;
    font-weight: 850;
}
.summary-donut-center span {
    display: block;
    margin-top: 4px;
    font-size: 12px;
    color: #5E7464;
}
@media (max-width: 900px) {
    .summary-donut-grid {
        grid-template-columns: 1fr;
    }
}

/* --- Lekerekített futárlista --- */
.courier-list-header {
    display:grid;
    grid-template-columns:1.45fr .75fr .85fr 1fr 1fr 1fr .9fr;
    gap:1rem;
    align-items:center;
    padding:0 18px 8px 18px;
    color:#314235;
    font-size:13px;
    font-weight:800;
}
[class*="st-key-courier_row_"] {
    background:#ffffff;
    border:1px solid #DDE9E0 !important;
    border-radius:18px !important;
    padding:10px 14px 10px 14px !important;
    margin:0 0 10px 0 !important;
    box-shadow:0 5px 16px rgba(23,53,31,.045);
    transition:transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}
[class*="st-key-courier_row_"]:hover {
    transform:translateY(-1px);
    border-color:#A9DEB8 !important;
    box-shadow:0 10px 24px rgba(23,133,59,.09);
}
[class*="st-key-courier_row_"] div.stButton > button {
    justify-content:flex-start !important;
    min-height:42px;
    border-radius:12px !important;
    border:1px solid #BDE9C9 !important;
    background:linear-gradient(135deg,#FFFFFF 0%,#F7FCF8 100%) !important;
    color:#17351F !important;
    font-weight:800 !important;
    padding-left:14px !important;
}
[class*="st-key-courier_row_"] div.stButton > button:hover {
    background:#F0FAF3 !important;
    border-color:#1FA64A !important;
    color:#17853B !important;
}
[class*="st-key-courier_row_"] [data-testid="stCaptionContainer"] {
    color:#6D7F71;
    font-size:13px;
}
.courier-list-footer {
    color:#6D7F71;
    font-size:12px;
    padding:4px 4px 0 4px;
}
@media (max-width: 1000px) {
    .courier-list-header { display:none; }
    [class*="st-key-courier_row_"] { overflow-x:auto; }
}


/* --- Prémium futárprofil --- */
.detail-card {
    background:#ffffff;
    border:1px solid #DDE9E0;
    border-radius:20px;
    box-shadow:0 10px 28px rgba(23,53,31,.07);
}
.courier-profile-hero {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:24px;
    padding:24px;
    margin-bottom:16px;
    background:linear-gradient(135deg,#F4FBF5 0%,#FFFFFF 58%,#F0F7FF 100%);
    border:1px solid #DDE9E0;
    border-radius:22px;
    box-shadow:0 12px 32px rgba(23,53,31,.08);
}
.courier-profile-main { display:flex;align-items:center;gap:16px;min-width:0; }
.courier-avatar {
    width:66px;height:66px;border-radius:18px;display:grid;place-items:center;
    flex:0 0 66px;background:linear-gradient(145deg,#1FA64A,#17853B);
    color:#fff;font-size:25px;font-weight:900;box-shadow:0 8px 20px rgba(31,166,74,.23);
}
.courier-profile-name { font-size:25px;font-weight:900;color:#17351F;line-height:1.15; }
.courier-profile-meta { color:#66796B;font-size:13px;margin-top:7px; }
.courier-profile-badges { display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end; }
.profile-stat-grid {
    display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:4px 0 18px;
}
.profile-stat-card {
    background:#fff;border:1px solid #DDE9E0;border-radius:17px;padding:16px 17px;
    box-shadow:0 6px 18px rgba(23,53,31,.045);
}
.profile-stat-label { color:#718176;font-size:12px;font-weight:700;margin-bottom:7px; }
.profile-stat-value { color:#17351F;font-size:23px;font-weight:900;line-height:1.1; }
.profile-stat-note { color:#8A978D;font-size:11px;margin-top:7px; }
.profile-panel-title { font-size:16px;font-weight:900;color:#17351F;margin-bottom:12px; }
.profile-mini-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px; }
.profile-mini-card { background:#F8FBF8;border:1px solid #E0ECE3;border-radius:14px;padding:14px; }
.profile-mini-label { color:#718176;font-size:12px;margin-bottom:6px; }
.profile-mini-value { color:#17351F;font-size:18px;font-weight:850; }
.profile-alert { border-radius:14px;padding:13px 15px;margin-top:10px;font-size:13px;font-weight:750; }
.profile-alert-ok { background:#EAF8F0;color:#157254;border:1px solid #CDEEDB; }
.profile-alert-warn { background:#FFF8E7;color:#946200;border:1px solid #F5E1A8; }
div[data-testid="stDialog"] div[data-baseweb="radio"] > div {
    gap:4px;background:#F5F8F6;border:1px solid #DDE9E0;border-radius:14px;padding:5px;
    overflow-x:auto;flex-wrap:nowrap;
}
div[data-testid="stDialog"] div[data-baseweb="radio"] label {
    background:transparent;border-radius:10px;padding:7px 11px;white-space:nowrap;
}
div[data-testid="stDialog"] div[data-baseweb="radio"] label:has(input:checked) {
    background:#ffffff;box-shadow:0 3px 10px rgba(23,53,31,.08);
}
@media (max-width:900px) {
    .courier-profile-hero { align-items:flex-start;flex-direction:column; }
    .courier-profile-badges { justify-content:flex-start; }
    .profile-stat-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .profile-mini-grid { grid-template-columns:1fr; }
}

/* --- Futárprofil modal v2: elszámolási cockpit --- */
div[data-testid="stDialog"] [role="dialog"] {
    width:min(1280px, 96vw) !important;
}
.settlement-profile-shell {
    --sp-ink:#17251d;
    --sp-muted:#64736b;
    --sp-soft:#f7faf8;
    --sp-border:#dfe7e2;
    --sp-green:#137a3a;
    --sp-green-soft:#eaf7ee;
    --sp-red:#e03b3b;
    --sp-red-soft:#fff0ef;
    --sp-blue:#2f6fed;
    --sp-blue-soft:#edf4ff;
    color:var(--sp-ink);
}
.settlement-profile-top {
    display:grid;
    grid-template-columns:minmax(340px, 1fr) minmax(520px, 1.6fr);
    gap:22px;
    align-items:center;
    padding:10px 2px 18px;
    border-bottom:1px solid var(--sp-border);
}
.settlement-driver {
    display:grid;
    grid-template-columns:82px 1fr;
    gap:18px;
    align-items:center;
    min-width:0;
}
.settlement-avatar {
    width:76px;
    height:76px;
    border-radius:50%;
    display:grid;
    place-items:center;
    background:linear-gradient(145deg,#dff4e5,#bfe8ca);
    color:#10391e;
    font-size:27px;
    font-weight:900;
}
.settlement-name {
    font-size:24px;
    line-height:1.1;
    font-weight:900;
    margin-bottom:14px;
}
.settlement-meta-grid {
    display:grid;
    grid-template-columns:repeat(4,minmax(74px, 1fr));
    gap:12px;
}
.settlement-meta-item {
    min-width:0;
}
.settlement-meta-label {
    color:var(--sp-muted);
    font-size:11px;
    font-weight:750;
    margin-bottom:4px;
}
.settlement-meta-value {
    color:#26362d;
    font-size:12px;
    font-weight:800;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
}
.settlement-top-kpis {
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:14px;
}
.settlement-kpi-card {
    display:grid;
    grid-template-columns:38px 1fr;
    gap:11px;
    align-items:center;
    min-height:76px;
    padding:14px;
    background:#fff;
    border:1px solid var(--sp-border);
    border-radius:8px;
    box-shadow:0 7px 18px rgba(23,37,29,.045);
}
.settlement-kpi-icon {
    width:32px;
    height:32px;
    border-radius:8px;
    display:grid;
    place-items:center;
    color:var(--sp-green);
    background:var(--sp-green-soft);
    font-weight:900;
}
.settlement-kpi-icon.blue { color:var(--sp-blue); background:var(--sp-blue-soft); }
.settlement-kpi-icon.red { color:var(--sp-red); background:var(--sp-red-soft); }
.settlement-kpi-icon.purple { color:#7657d8; background:#f1edff; }
.settlement-kpi-label {
    color:var(--sp-muted);
    font-size:11px;
    font-weight:750;
}
.settlement-kpi-value {
    color:var(--sp-ink);
    font-size:17px;
    font-weight:950;
    line-height:1.15;
    margin-top:2px;
}
.settlement-kpi-note {
    color:#77867e;
    font-size:10px;
    margin-top:4px;
}
.settlement-chip {
    display:inline-flex;
    align-items:center;
    width:max-content;
    padding:4px 8px;
    border-radius:6px;
    background:var(--sp-green-soft);
    color:var(--sp-green);
    font-size:11px;
    font-weight:850;
}
.settlement-overview-grid {
    display:grid;
    grid-template-columns:minmax(0, 1.35fr) minmax(340px, .9fr);
    gap:14px;
    margin-top:14px;
}
.settlement-card {
    background:#fff;
    border:1px solid var(--sp-border);
    border-radius:8px;
    box-shadow:0 8px 22px rgba(23,37,29,.04);
    padding:16px;
}
.settlement-card-title {
    font-size:18px;
    font-weight:900;
    color:var(--sp-ink);
    margin-bottom:14px;
}
.settlement-card-subtitle {
    display:inline-flex;
    margin-left:8px;
    color:var(--sp-green);
    font-size:12px;
    font-weight:800;
}
.settlement-summary-line {
    display:grid;
    grid-template-columns:1fr 1fr 1.45fr;
    gap:18px;
    align-items:end;
    margin-bottom:18px;
}
.settlement-summary-item {
    min-height:58px;
}
.settlement-summary-item.payable {
    border-left:1px solid var(--sp-border);
    padding-left:28px;
}
.settlement-summary-label {
    color:var(--sp-muted);
    font-size:12px;
    font-weight:750;
    margin-bottom:8px;
}
.settlement-summary-value {
    color:var(--sp-ink);
    font-size:19px;
    font-weight:950;
}
.settlement-summary-value.red { color:var(--sp-red); }
.settlement-summary-value.big {
    color:var(--sp-green);
    font-size:34px;
    letter-spacing:0;
}
.settlement-ledger-grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:18px;
}
.settlement-ledger {
    border:1px solid var(--sp-border);
    border-radius:8px;
    overflow:hidden;
}
.settlement-ledger.income { border-color:#d6ecdd; }
.settlement-ledger.outcome { border-color:#f3d8d6; }
.settlement-ledger-head {
    display:flex;
    align-items:center;
    gap:9px;
    padding:13px 14px;
    font-size:14px;
    font-weight:900;
    background:linear-gradient(90deg,#eef8f1,#fff);
}
.settlement-ledger.outcome .settlement-ledger-head {
    background:linear-gradient(90deg,#fff1f0,#fff);
}
.settlement-ledger-row {
    display:grid;
    grid-template-columns:1fr auto;
    gap:14px;
    padding:10px 14px;
    border-top:1px solid #edf2ef;
    font-size:12px;
}
.settlement-ledger-row strong {
    font-variant-numeric:tabular-nums;
}
.settlement-ledger-row.total {
    font-weight:900;
    color:var(--sp-ink);
}
.settlement-side-stack {
    display:grid;
    gap:8px;
}
.settlement-mini-kpis {
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:14px;
}
.settlement-mini-kpi {
    border:1px solid var(--sp-border);
    border-radius:8px;
    padding:14px;
    min-height:88px;
}
.settlement-mini-value {
    color:var(--sp-ink);
    font-size:20px;
    font-weight:950;
    margin-top:7px;
}
.settlement-mini-note {
    color:var(--sp-green);
    font-size:11px;
    font-weight:800;
    margin-top:10px;
}
.settlement-source-row {
    display:grid;
    grid-template-columns:1fr auto 24px;
    gap:12px;
    align-items:center;
    padding:9px 0;
    border-top:1px solid #edf2ef;
    color:#526259;
    font-size:13px;
}
.settlement-source-row:first-of-type {
    border-top:none;
}
.settlement-source-row strong {
    color:#34443b;
}
.settlement-ok {
    color:var(--sp-green);
    font-weight:900;
}
.settlement-info {
    color:var(--sp-blue);
    font-weight:900;
}
.settlement-route-card {
    margin-top:8px;
}
.settlement-route-head,
.settlement-route-row {
    display:grid;
    grid-template-columns:1.3fr .9fr .55fr .65fr .9fr .7fr 20px;
    gap:12px;
    align-items:center;
}
.settlement-route-head {
    color:var(--sp-muted);
    font-size:12px;
    font-weight:850;
    padding:4px 0 9px;
    border-bottom:1px solid var(--sp-border);
}
.settlement-route-row {
    min-height:36px;
    border-bottom:1px solid #edf2ef;
    color:#26362d;
    font-size:12px;
}
.settlement-route-row:last-child {
    border-bottom:none;
}
.settlement-route-link {
    float:right;
    color:#2668cf;
    font-size:12px;
    font-weight:850;
}
.finance-toolbar {
    display:grid;
    grid-template-columns:minmax(170px,.9fr) minmax(150px,.7fr) 1fr;
    gap:16px;
    align-items:center;
    padding:14px 16px;
    margin:14px 0 16px;
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fff;
    box-shadow:0 8px 20px rgba(23,37,29,.035);
}
.finance-toolbar-label {
    color:var(--sp-muted);
    font-size:12px;
    font-weight:800;
    margin-bottom:6px;
}
.finance-toolbar-value {
    display:inline-flex;
    align-items:center;
    min-height:36px;
    padding:0 12px;
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fbfcfb;
    color:var(--sp-ink);
    font-size:14px;
    font-weight:850;
}
.finance-toolbar-actions {
    display:flex;
    justify-content:flex-end;
    color:var(--sp-muted);
    font-size:12px;
}
.finance-status {
    display:inline-flex;
    align-items:center;
    min-height:34px;
    padding:0 12px;
    border-radius:999px;
    background:var(--sp-green-soft);
    color:var(--sp-green);
    font-weight:900;
}
.finance-kpi-grid {
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    gap:14px;
    margin:10px 0 16px;
}
.finance-kpi {
    min-height:96px;
    padding:16px;
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fff;
    box-shadow:0 7px 18px rgba(23,37,29,.035);
}
details.finance-kpi-detail-card {
    min-height:96px;
    padding:0;
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fff;
    box-shadow:0 7px 18px rgba(23,37,29,.035);
    overflow:hidden;
}
details.finance-kpi-detail-card > summary {
    list-style:none;
    cursor:pointer;
}
details.finance-kpi-detail-card > summary::-webkit-details-marker { display:none; }
details.finance-kpi-detail-card .finance-kpi {
    min-height:96px;
    border:0;
    box-shadow:none;
}
details.finance-kpi-detail-card[open] {
    grid-column:span 2;
}
.finance-kpi-detail-body {
    padding:0 14px 14px;
}
.finance-kpi-detail-table {
    width:100%;
    border-collapse:collapse;
    font-size:12px;
}
.finance-kpi-detail-table th {
    color:var(--sp-muted);
    text-align:left;
    font-weight:850;
    border-bottom:1px solid var(--sp-border);
    padding:8px 4px;
}
.finance-kpi-detail-table td {
    border-bottom:1px solid #eef3ef;
    padding:8px 4px;
    color:var(--sp-ink);
}
.finance-kpi-detail-empty {
    color:var(--sp-muted);
    font-size:12px;
    padding:10px 4px 2px;
}
.finance-kpi.payable {
    background:linear-gradient(135deg,#19a64d,#108138);
    border-color:#19a64d;
    color:#fff;
}
.finance-kpi-label {
    color:var(--sp-muted);
    font-size:12px;
    font-weight:800;
}
.finance-kpi.payable .finance-kpi-label { color:rgba(255,255,255,.84); }
.finance-kpi-value {
    margin-top:12px;
    color:var(--sp-ink);
    font-size:22px;
    font-weight:950;
    letter-spacing:0;
}
.finance-kpi.payable .finance-kpi-value { color:#fff; }
.finance-kpi-note {
    margin-top:8px;
    color:var(--sp-muted);
    font-size:12px;
    font-weight:800;
}
.finance-kpi.payable .finance-kpi-note { color:rgba(255,255,255,.8); }
.finance-work-grid {
    display:grid;
    grid-template-columns:minmax(360px,.55fr) minmax(560px,1fr);
    gap:14px;
    align-items:start;
    margin-top:4px;
}
.finance-panel {
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fff;
    padding:14px;
    box-shadow:0 8px 22px rgba(23,37,29,.035);
}
.finance-panel-head {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin-bottom:12px;
}
.finance-panel-title {
    color:var(--sp-ink);
    font-size:17px;
    font-weight:950;
}
.finance-table {
    border:1px solid #e5ebe7;
    border-radius:8px;
    overflow:hidden;
}
.finance-row {
    display:grid;
    grid-template-columns:72px 1fr 120px;
    min-height:36px;
    align-items:center;
    border-top:1px solid #edf2ef;
    font-size:13px;
}
.finance-row:first-child { border-top:none; }
.finance-row.header {
    color:var(--sp-muted);
    background:#f8faf9;
    font-size:12px;
    font-weight:850;
}
.finance-row > div {
    padding:8px 10px;
    border-left:1px solid #edf2ef;
}
.finance-row > div:first-child { border-left:none; }
.finance-op {
    display:inline-grid;
    place-items:center;
    min-width:46px;
    height:22px;
    border-radius:999px;
    font-weight:950;
}
.finance-op.plus { background:#dcf9e3;color:var(--sp-green); }
.finance-op.minus { background:#ffe2e0;color:var(--sp-red); }
.finance-op.equals { background:#f0f2f3;color:var(--sp-ink); }
.finance-amount {
    text-align:right;
    font-variant-numeric:tabular-nums;
    font-weight:850;
}
.finance-row.total {
    font-weight:950;
    background:#fbfcfb;
}
.finance-note {
    color:var(--sp-muted);
    font-size:12px;
    margin-top:10px;
}
.finance-log-panel {
    margin-top:14px;
    border:1px solid var(--sp-border);
    border-radius:8px;
    background:#fff;
    padding:14px;
}
@media (max-width:1100px) {
    .finance-toolbar,
    .finance-work-grid {
        grid-template-columns:1fr;
    }
    .finance-kpi-grid {
        grid-template-columns:repeat(2,minmax(0,1fr));
    }
}
@media (max-width:1100px) {
    .settlement-profile-top,
    .settlement-overview-grid,
    .settlement-summary-line,
    .settlement-ledger-grid {
        grid-template-columns:1fr;
    }
    .settlement-summary-item.payable {
        border-left:none;
        padding-left:0;
    }
    .settlement-top-kpis,
    .settlement-mini-kpis {
        grid-template-columns:repeat(2,minmax(0,1fr));
    }
}

</style>
        """,
        unsafe_allow_html=True,
    )


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _courier_match_key(value: object) -> str:
    """Stable match key for DB and Excel courier names.

    Names can differ only by accents, whitespace, word order, or a copied
    numeric identifier. These differences must not hide a DB-calculated row.
    """
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [token for token in tokens if not (token.isdigit() and 3 <= len(token) <= 6)]
    return " ".join(sorted(tokens))


def _courier_id_key(value: object) -> str:
    """Normalize Courier ID values such as ``7056`` and ``7056.0``."""
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    try:
        numeric = float(text.replace(" ", "").replace(",", "."))
        return str(int(numeric)) if numeric.is_integer() else str(numeric)
    except ValueError:
        return text


def _normalized_field_key(value: object) -> str:
    """Normalize Excel/JSON field names, including Hungarian accents."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]", "", text)


def _search_text_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text).strip()


def filter_couriers_by_search(data: pd.DataFrame, query: str) -> pd.DataFrame:
    clean_query = _search_text_key(query)
    if data.empty or not clean_query:
        return data
    name_series = data.get("Futár", pd.Series("", index=data.index)).map(_search_text_key)
    id_series = data.get("Courier ID", pd.Series("", index=data.index)).astype(str).map(_search_text_key)
    mask = name_series.str.contains(clean_query, regex=False, na=False) | id_series.str.contains(clean_query, regex=False, na=False)
    return data[mask]


@st.cache_data(show_spinner=False, ttl=60)
def load_active_excel_bonus_rules(table_name: str) -> pd.DataFrame:
    """Read configured Excel-mode performance rules; missing tables pay nothing."""
    try:
        rows = (
            get_db().schema("settlement").table(table_name).select("*")
            .eq("is_active", True).is_("deleted_at", "null").execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    rules = pd.DataFrame(rows)
    if rules.empty or "calculation_mode" not in rules:
        return pd.DataFrame()
    return rules[rules["calculation_mode"].fillna("").str.casefold() == "excel"].copy()


@st.cache_data(show_spinner=False, ttl=60)
def load_active_bonus_level_rules(table_name: str) -> pd.DataFrame:
    """Read active performance level rules for UI drilldowns."""
    try:
        rows = (
            get_db().schema("settlement").table(table_name).select("*")
            .eq("is_active", True).is_("deleted_at", "null").execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=60)
def load_active_periodic_fee_rules(period_start: date, period_end: date) -> pd.DataFrame:
    """Read JITT periodic fees that overlap the selected settlement month."""
    try:
        rows = (
            get_db().schema("settlement").table("cfg_jitt_periodic_fees").select("*")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", period_end.isoformat())
            .order("priority")
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    rules = pd.DataFrame(rows)
    if rules.empty:
        return rules
    valid_to = pd.to_datetime(rules.get("valid_to"), errors="coerce")
    return rules.loc[valid_to.isna() | (valid_to >= pd.Timestamp(period_start))].copy()


@st.cache_data(show_spinner=False, ttl=60)
def load_dsp_monthly_company_quality_bonus(courier_id: str, period_start: date) -> dict[str, float]:
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return {}
    try:
        rows = (
            get_db().schema("public").table("dsp_courier_quality_monthly")
            .select("company_delay_bonus_huf,company_compliance_bonus_huf,company_quality_bonus_total_huf")
            .eq("courier_id", int(clean_id))
            .eq("period_month", period_start.replace(day=1).isoformat())
            .limit(1)
            .execute().data or []
        )
    except BaseException:
        return {}
    return rows[0] if rows else {}


@st.cache_data(show_spinner=False, ttl=60)
def load_jitt_day_definitions_for_period(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("cfg_jitt_day_definitions").select("*")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", period_end.isoformat())
            .order("priority")
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    rules = pd.DataFrame(rows)
    if rules.empty:
        return rules
    valid_to = pd.to_datetime(rules.get("valid_to"), errors="coerce")
    return rules.loc[valid_to.isna() | (valid_to >= pd.Timestamp(period_start))].copy()


def resolve_jitt_day_type_label(work_date: object, rules: pd.DataFrame) -> str:
    parsed = pd.to_datetime(work_date, errors="coerce")
    if pd.isna(parsed):
        return "Nincs besorolás"
    route_date = parsed.date()
    weekday_iso = int(parsed.dayofweek) + 1
    if not rules.empty:
        for _, rule in rules.sort_values("priority", kind="stable").iterrows():
            try:
                valid_from = date.fromisoformat(str(rule.get("valid_from"))[:10])
                valid_to_value = rule.get("valid_to")
                valid_to = date.fromisoformat(str(valid_to_value)[:10]) if pd.notna(valid_to_value) else None
            except ValueError:
                continue
            if route_date < valid_from or (valid_to and route_date > valid_to):
                continue
            weekdays = rule.get("weekdays") or []
            if isinstance(weekdays, str):
                weekdays = [int(item) for item in re.findall(r"\d+", weekdays)]
            if weekday_iso not in set(int(item) for item in weekdays):
                continue
            return {"highlighted": "Kiemelt nap", "normal": "Normál nap"}.get(
                str(rule.get("day_type") or "").casefold(),
                "Nincs besorolás",
            )
    return "Normál nap"


def _performance_rule_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    match = re.search(r"(?:level|szint)[_\-\s]*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}. szint"
    return text.replace("_", " ").replace("-", " ").strip()


def _performance_key_from_label(value: object, kind: str) -> str:
    text = str(value or "").strip().casefold()
    if kind == "day":
        if "kiemelt" in text or "highlight" in text:
            return "highlighted"
        if "norm" in text:
            return "normal"
        return "any"
    if "express" in text:
        return "express"
    if "region" in text:
        return "regional"
    if "norm" in text or "city" in text:
        return "normal"
    return "any"


def performance_level_for_amount(
    amount: object,
    rules: pd.DataFrame,
    route_type: object = None,
    day_type: object = None,
    route_date: object = None,
) -> str:
    if rules.empty:
        return "-"
    amount_value = parse_huf_value(amount)
    if amount_value == 0:
        return "-"
    route_type_key = _performance_key_from_label(route_type, "route")
    day_type_key = _performance_key_from_label(day_type, "day")
    try:
        work_date = date.fromisoformat(str(route_date)[:10])
    except ValueError:
        work_date = None
    for _, rule in rules.sort_values("priority", kind="stable").iterrows():
        if parse_huf_value(rule.get("courier_amount_huf")) != amount_value:
            continue
        if str(rule.get("day_type") or "any").casefold() not in {"any", day_type_key}:
            continue
        if str(rule.get("route_type") or "any").casefold() not in {"any", route_type_key}:
            continue
        if work_date:
            try:
                valid_from = date.fromisoformat(str(rule.get("valid_from"))[:10])
                valid_to_value = rule.get("valid_to")
                valid_to = date.fromisoformat(str(valid_to_value)[:10]) if pd.notna(valid_to_value) else None
            except ValueError:
                continue
            if work_date < valid_from or (valid_to and work_date > valid_to):
                continue
        return _performance_rule_label(rule.get("level_code"))
    return "-"


def _configured_excel_bonus_for_route(
    rules: pd.DataFrame,
    source_field: str,
    route_date: object,
    day_type: str,
    route_type: str,
    warehouse_code: object,
    normalized_fields: dict[str, object],
) -> float:
    """Use an Excel amount only when an explicit matching parameter rule exists."""
    field_key = _normalized_field_key(source_field)
    if rules.empty or field_key not in normalized_fields:
        return 0.0
    try:
        work_date = date.fromisoformat(str(route_date)[:10])
    except ValueError:
        return 0.0
    warehouse_key = str(warehouse_code or "").strip().casefold()
    for _, rule in rules.sort_values("priority", kind="stable").iterrows():
        if _normalized_field_key(rule.get("excel_source_field")) != field_key:
            continue
        try:
            valid_from = date.fromisoformat(str(rule.get("valid_from"))[:10])
            valid_to_value = rule.get("valid_to")
            valid_to = date.fromisoformat(str(valid_to_value)[:10]) if pd.notna(valid_to_value) else None
        except ValueError:
            continue
        if work_date < valid_from or (valid_to and work_date > valid_to):
            continue
        if str(rule.get("day_type") or "any").casefold() not in {"any", day_type}:
            continue
        if str(rule.get("route_type") or "any").casefold() not in {"any", route_type}:
            continue
        rule_warehouse = str(rule.get("warehouse_code") or "").strip().casefold()
        if rule_warehouse and rule_warehouse != warehouse_key:
            continue
        return parse_huf_value(normalized_fields[field_key])
    return 0.0


def _resolve_courier_lookup_key(courier_key: str, available_keys: set[str]) -> str:
    """Resolve one unambiguous shortened or extended courier name."""
    if courier_key in available_keys:
        return courier_key
    tokens = set(courier_key.split())
    if not tokens:
        return courier_key
    candidates = [
        key for key in available_keys
        if tokens <= set(key.split()) or set(key.split()) <= tokens
    ]
    return candidates[0] if len(candidates) == 1 else courier_key


@st.cache_data(show_spinner=False, ttl=60)
def load_latest_jit_session_id() -> str | None:
    """Use existing DB data even after an app refresh; no Excel re-upload needed."""
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("session_id,created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return str(rows[0]["session_id"]) if rows else None
    except BaseException:
        return None


@st.cache_data(show_spinner=False, ttl=60)
def load_latest_excel_jit_session_id(period_start: date | None = None) -> str | None:
    """Find the latest non-API JIT session for Excel calculation mode."""
    try:
        query = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("session_id,source_sheet,created_at")
        )
        if period_start:
            _, period_end = month_bounds(period_start)
            query = query.gte("route_date", period_start.isoformat()).lte("route_date", period_end.isoformat())
        rows = query.order("created_at", desc=True).limit(10000).execute().data or []
        for row in rows:
            source_sheet = str(row.get("source_sheet") or "")
            if not source_sheet.lower().startswith("api financial overview"):
                return str(row["session_id"])
        return None
    except BaseException:
        return None


@st.cache_data(show_spinner=False, ttl=60)
def jit_session_has_rows_in_month(session_id: str | None, period_start: date) -> bool:
    if not session_id:
        return False
    try:
        _, period_end = month_bounds(period_start)
        rows = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("session_id")
            .eq("session_id", session_id)
            .gte("route_date", period_start.isoformat())
            .lte("route_date", period_end.isoformat())
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(rows)
    except BaseException:
        return False


@st.cache_data(show_spinner=False, ttl=60)
def load_latest_api_jit_session_id(period_start: date, warehouse_label: str | None = None) -> str | None:
    """Find the latest API-imported JIT session for the selected month."""
    try:
        _, period_end = month_bounds(period_start)
        rows = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("session_id,source_sheet,created_at")
            .ilike("source_sheet", "API financial overview%")
            .gte("route_date", period_start.isoformat())
            .lte("route_date", period_end.isoformat())
            .order("created_at", desc=True)
            .limit(10000)
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        data = pd.DataFrame(rows)
        warehouse_id = settlement_warehouse_id(warehouse_label)
        if warehouse_id is not None:
            needle = f"WH{warehouse_id}"
            data = data.loc[data["source_sheet"].astype(str).str.contains(needle, case=False, na=False)]
            if data.empty:
                return None
            grouped = (
                data.groupby("session_id", as_index=False)
                .agg(latest_created_at=("created_at", "max"))
                .sort_values("latest_created_at", ascending=False)
            )
            return str(grouped.iloc[0]["session_id"]) if not grouped.empty else None
        grouped = (
            data.groupby("session_id", as_index=False)
            .agg(
                warehouse_count=("source_sheet", "nunique"),
                latest_created_at=("created_at", "max"),
            )
            .sort_values(["warehouse_count", "latest_created_at"], ascending=[False, False])
        )
        return str(grouped.iloc[0]["session_id"]) if not grouped.empty else None
    except BaseException:
        return None


def settlement_mobile_session_for_mode(calculation_mode: str, period_start: date, warehouse_label: str | None) -> str | None:
    normalized_mode = str(calculation_mode or "API").strip().casefold()
    if normalized_mode == "excel":
        _, period_end = month_bounds(period_start)
        try:
            rows = (
                get_db()
                .schema("settlement")
                .table("jit_row")
                .select("session_id,source_sheet,created_at")
                .gte("route_date", period_start.isoformat())
                .lte("route_date", period_end.isoformat())
                .order("created_at", desc=True)
                .limit(10000)
                .execute()
                .data
                or []
            )
            for row in rows:
                source_sheet = str(row.get("source_sheet") or "")
                if not source_sheet.lower().startswith("api financial overview"):
                    return str(row["session_id"])
            return None
        except BaseException:
            return None
    if normalized_mode == "api":
        return load_latest_api_jit_session_id(period_start, warehouse_label)
    return None


def save_mobile_settlement_period_config(
    period_start: date,
    calculation_mode: str,
    warehouse_label: str | None,
    session_id: str | None,
    updated_by: str,
) -> bool:
    normalized_mode = "Excel" if str(calculation_mode or "").strip().casefold() == "excel" else "API"
    if str(calculation_mode or "").strip() not in {"API", "Excel"}:
        return False
    try:
        get_db().schema("settlement").table("mobile_settlement_period_config").upsert(
            {
                "period_start": period_start.replace(day=1).isoformat(),
                "calculation_mode": normalized_mode,
                "warehouse_label": str(warehouse_label or "Összes"),
                "session_id": str(session_id or ""),
                "source_note": f"{normalized_mode} elszámolási forrás publikálva mobilra.",
                "updated_by": updated_by,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="period_start",
        ).execute()
        return True
    except BaseException:
        return False


def clear_mobile_settlement_period_config(period_start: date) -> bool:
    try:
        get_db().schema("settlement").table("mobile_settlement_period_config").delete() \
            .eq("period_start", period_start.replace(day=1).isoformat()).execute()
        return True
    except BaseException:
        return False


def load_mobile_breakdown_overrides(courier_id: str, period_start: date) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("mobile_settlement_breakdown_overrides")
            .select("item_key,item_label,amount_value,amount_kind,note")
            .eq("courier_id", str(courier_id))
            .eq("period_start", period_start.replace(day=1).isoformat())
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame(columns=["item_key", "item_label", "amount_value", "amount_kind", "note"])
    return pd.DataFrame(rows)


def save_mobile_breakdown_overrides(
    courier_id: str,
    period_start: date,
    rows: list[dict[str, object]],
    updated_by: str,
) -> bool:
    clean_courier_id = _courier_id_key(courier_id)
    payloads = []
    for row in rows:
        item_key = str(row.get("item_key") or row.get("Kulcs") or "").strip()
        if not item_key:
            continue
        amount_kind = str(row.get("amount_kind") or row.get("Típus") or "huf").strip()
        if amount_kind not in {"huf", "count"}:
            amount_kind = "huf"
        payloads.append({
            "period_start": period_start.replace(day=1).isoformat(),
            "courier_id": clean_courier_id,
            "item_key": item_key,
            "item_label": str(row.get("item_label") or row.get("Megnevezés") or item_key),
            "amount_value": parse_huf_value(row.get("amount_value") if "amount_value" in row else row.get("Érték")),
            "amount_kind": amount_kind,
            "note": str(row.get("note") or row.get("Megjegyzés") or "").strip() or "Admin felülírás",
            "updated_by": updated_by,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    if not payloads:
        return False
    try:
        get_db().schema("settlement").table("mobile_settlement_breakdown_overrides").upsert(
            payloads,
            on_conflict="period_start,courier_id,item_key",
        ).execute()
        return True
    except BaseException:
        return False


def mobile_breakdown_rows_from_settlement_row(row: dict[str, object]) -> list[dict[str, object]]:
    base = parse_huf_value(row.get("Nettó bevétel"))
    tip = parse_huf_value(row.get("Borravaló"))
    imported_bonus = parse_huf_value(row.get("Importált bónusz"))
    imported_malus = abs(parse_huf_value(row.get("Importált málusz")))
    imported_atm = abs(parse_huf_value(row.get("Importált ATM levonás")))
    deduction = parse_huf_value(row.get("Levonás"))
    payable = parse_huf_value(row.get("Kifizetendő"))
    orders = parse_huf_value(row.get("Rendelések"))
    routes = parse_huf_value(row.get("Útvonalak") or row.get("Számolt túrák"))
    highlighted = parse_huf_value(row.get("Kiemelt túrák"))
    normal = parse_huf_value(row.get("Normál túrák"))
    if routes > 0 and highlighted + normal == 0:
        normal = routes
    delay = parse_huf_value(row.get("Késedelmi díj"))
    compliance = parse_huf_value(row.get("Túramegfelelés"))
    loyalty = parse_huf_value(row.get("Lojalitás"))
    customer_rating = parse_huf_value(row.get("Ügyfélértékelés"))
    correction = parse_huf_value(
        row.get("Korrekció")
        or row.get("Korrekciók")
        or row.get("Időszakos díjak / korrekció")
        or row.get("Időszakos díj")
    )
    salary_advance = parse_huf_value(row.get("Fizetés előleg"))
    manual_bonus = parse_huf_value(row.get("JITT bónusz"))
    manual_malus = abs(parse_huf_value(row.get("JITT malus")))
    correction_income = max(correction, 0.0)
    correction_deduction = abs(min(correction, 0.0))
    known_deductions = imported_malus + manual_malus + imported_atm + salary_advance + correction_deduction
    remaining_deduction = max(abs(deduction) - known_deductions, 0.0)
    income = base + tip + imported_bonus + manual_bonus + delay + compliance + loyalty + customer_rating + correction_income
    return [
        {"item_key": "payable", "item_label": "Teljes összeg", "amount_kind": "huf", "amount_value": payable, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "income", "item_label": "Jóváírások", "amount_kind": "huf", "amount_value": income, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "deductions", "item_label": "Levonások összesen", "amount_kind": "huf", "amount_value": -abs(deduction), "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "performance", "item_label": "Teljesítmény", "amount_kind": "count", "amount_value": orders, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "base", "item_label": "Alapdíj", "amount_kind": "huf", "amount_value": base, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "tip", "item_label": "Borravaló", "amount_kind": "huf", "amount_value": tip, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "delay_bonus", "item_label": "Késedelmi díj", "amount_kind": "huf", "amount_value": delay, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "compliance_bonus", "item_label": "Túramegfelelés", "amount_kind": "huf", "amount_value": compliance, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "loyalty_bonus", "item_label": "Lojalitási bónusz", "amount_kind": "huf", "amount_value": loyalty, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "customer_rating", "item_label": "Ügyfélértékelési bónusz", "amount_kind": "huf", "amount_value": customer_rating, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "correction", "item_label": "Korrekciók összesen", "amount_kind": "huf", "amount_value": correction, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "correction_income", "item_label": "Korrekció +", "amount_kind": "huf", "amount_value": correction_income, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "correction_deduction", "item_label": "Korrekció -", "amount_kind": "huf", "amount_value": -correction_deduction, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "kiflis_bonus_malus", "item_label": "Kiflis levonások / bónuszok", "amount_kind": "huf", "amount_value": imported_bonus - imported_malus, "note": "Excel import tételek összesen"},
        {"item_key": "monthly_bonus", "item_label": "Kiflis bónusz", "amount_kind": "huf", "amount_value": imported_bonus, "note": str(row.get("Importált bónusz megjegyzés") or "").strip() or "Havi nyitáskor publikált snapshot"},
        {"item_key": "monthly_malus", "item_label": "Kiflis malus", "amount_kind": "huf", "amount_value": -imported_malus, "note": str(row.get("Importált málusz megjegyzés") or "").strip() or "Havi nyitáskor publikált snapshot"},
        {"item_key": "atm_effect", "item_label": "ATM hatás", "amount_kind": "huf", "amount_value": -imported_atm, "note": str(row.get("Importált ATM megjegyzés") or "").strip() or "Havi nyitáskor publikált snapshot"},
        {"item_key": "salary_advance", "item_label": "Fizetés előleg", "amount_kind": "huf", "amount_value": -abs(salary_advance), "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "other_expense", "item_label": "Egyéb levonás", "amount_kind": "huf", "amount_value": -remaining_deduction, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "orders", "item_label": "Cím", "amount_kind": "count", "amount_value": orders, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "routes", "item_label": "Kör", "amount_kind": "count", "amount_value": routes, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "highlighted_routes", "item_label": "Kiemelt kör", "amount_kind": "count", "amount_value": highlighted, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "normal_routes", "item_label": "Normál kör", "amount_kind": "count", "amount_value": normal, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "shift_count", "item_label": "Műszak", "amount_kind": "count", "amount_value": 0, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "late_count", "item_label": "Késések száma", "amount_kind": "count", "amount_value": 0, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "delayed_orders", "item_label": "Késéses cím", "amount_kind": "count", "amount_value": 0, "note": "Havi nyitáskor publikált snapshot"},
        {"item_key": "no_show_count", "item_label": "Nem jelent meg műszakban", "amount_kind": "count", "amount_value": 0, "note": "Havi nyitáskor publikált snapshot"},
    ]


def _set_mobile_breakdown_row_amount(
    rows: list[dict[str, object]],
    item_key: str,
    amount_value: float,
    *,
    item_label: str | None = None,
    amount_kind: str = "huf",
    note: str | None = None,
) -> None:
    for item in rows:
        if str(item.get("item_key") or "") == item_key:
            item["amount_value"] = amount_value
            if item_label is not None:
                item["item_label"] = item_label
            if amount_kind:
                item["amount_kind"] = amount_kind
            if note is not None:
                item["note"] = note
            return
    rows.append({
        "item_key": item_key,
        "item_label": item_label or item_key,
        "amount_kind": amount_kind,
        "amount_value": amount_value,
        "note": note or "Valós elszámolási adat",
    })


def _mobile_breakdown_amount(rows: list[dict[str, object]], item_key: str) -> float:
    for item in rows:
        if str(item.get("item_key") or "") == item_key:
            return parse_huf_value(item.get("amount_value"))
    return 0.0


def recalculate_mobile_breakdown_totals(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    monthly_bonus = _mobile_breakdown_amount(rows, "monthly_bonus")
    monthly_malus = abs(_mobile_breakdown_amount(rows, "monthly_malus"))
    manual_bonus = _mobile_breakdown_amount(rows, "manual_bonus")
    manual_malus = abs(_mobile_breakdown_amount(rows, "manual_malus"))
    correction = _mobile_breakdown_amount(rows, "correction")
    correction_income = max(correction, 0.0)
    correction_deduction = abs(min(correction, 0.0))
    _set_mobile_breakdown_row_amount(rows, "correction_income", correction_income, item_label="Korrekció +")
    _set_mobile_breakdown_row_amount(rows, "correction_deduction", -correction_deduction, item_label="Korrekció -")
    _set_mobile_breakdown_row_amount(
        rows,
        "kiflis_bonus_malus",
        monthly_bonus - monthly_malus,
        item_label="Kiflis levonások / bónuszok",
        note="Excel import tételek összesen",
    )
    _set_mobile_breakdown_row_amount(
        rows,
        "bonus_malus",
        manual_bonus - manual_malus,
        item_label="JITT bónusz / malus",
        note="Sheet/DB tételek összesen",
    )
    income = (
        _mobile_breakdown_amount(rows, "base")
        + _mobile_breakdown_amount(rows, "tip")
        + _mobile_breakdown_amount(rows, "delay_bonus")
        + _mobile_breakdown_amount(rows, "compliance_bonus")
        + _mobile_breakdown_amount(rows, "loyalty_bonus")
        + _mobile_breakdown_amount(rows, "customer_rating")
        + monthly_bonus
        + manual_bonus
        + correction_income
    )
    deductions = -(
        monthly_malus
        + manual_malus
        + abs(_mobile_breakdown_amount(rows, "atm_effect"))
        + abs(_mobile_breakdown_amount(rows, "salary_advance"))
        + abs(_mobile_breakdown_amount(rows, "reserve"))
        + abs(_mobile_breakdown_amount(rows, "insurance_fee"))
        + abs(_mobile_breakdown_amount(rows, "other_expense"))
        + correction_deduction
    )
    _set_mobile_breakdown_row_amount(rows, "income", income, item_label="Jóváírások")
    _set_mobile_breakdown_row_amount(rows, "deductions", deductions, item_label="Levonások összesen")
    _set_mobile_breakdown_row_amount(rows, "payable", income + deductions, item_label="Teljes összeg")
    return rows


def enrich_mobile_settlement_row_for_snapshot(
    row: dict[str, object],
    *,
    courier_id: str,
    courier_name: str,
    session_id: str | None,
    calculation_mode: str,
    period_start: date,
    period_end: date,
    warehouse_label: str | None,
) -> tuple[dict[str, object], pd.DataFrame]:
    enriched = dict(row)
    route_detail = pd.DataFrame()
    try:
        route_detail = load_courier_route_detail(
            courier_id,
            courier_name,
            session_id,
            calculation_mode,
            period_start,
            warehouse_label,
        )
    except Exception:
        route_detail = pd.DataFrame()
    if not route_detail.empty:
        for target_column in ["Rendelések", "Késedelmi díj", "Túramegfelelés"]:
            if target_column in route_detail.columns:
                enriched[target_column] = float(pd.to_numeric(route_detail[target_column], errors="coerce").fillna(0.0).sum())
        route_count = int(len(route_detail))
        enriched["Útvonalak"] = route_count
        enriched["Számolt túrák"] = route_count
        day_type = route_detail.get("Naptípus", pd.Series(dtype=str)).astype(str).str.casefold()
        highlighted = int(day_type.str.contains("kiemelt", na=False).sum())
        normal = int(day_type.str.contains("norm", na=False).sum())
        if highlighted + normal == 0:
            normal = route_count
        enriched["Kiemelt túrák"] = highlighted
        enriched["Normál túrák"] = normal
        if parse_huf_value(enriched.get("Nettó bevétel")) == 0 and "Alapdíj" in route_detail.columns:
            enriched["Nettó bevétel"] = float(pd.to_numeric(route_detail["Alapdíj"], errors="coerce").fillna(0.0).sum())
        if parse_huf_value(enriched.get("Borravaló")) == 0 and "Borravaló" in route_detail.columns:
            enriched["Borravaló"] = float(pd.to_numeric(route_detail["Borravaló"], errors="coerce").fillna(0.0).sum())
    summary_row = load_courier_settlement_summary_row(session_id, courier_id, courier_name, period_start)
    if summary_row:
        summary_map = {
            "Rendelések": "order_count",
            "Útvonalak": "route_count",
            "Számolt túrák": "route_count",
            "Késedelmi díj": "delay_bonus_huf",
            "Túramegfelelés": "compliance_bonus_huf",
            "Kiemelt túrák": "highlighted_routes",
            "Normál túrák": "normal_routes",
        }
        for target_column, summary_column in summary_map.items():
            summary_value = parse_huf_value(summary_row.get(summary_column))
            if summary_value and parse_huf_value(enriched.get(target_column)) == 0:
                enriched[target_column] = summary_value
        if parse_huf_value(enriched.get("Nettó bevétel")) == 0:
            enriched["Nettó bevétel"] = parse_huf_value(summary_row.get("courier_base_rate_huf"))
        if parse_huf_value(enriched.get("Borravaló")) == 0:
            enriched["Borravaló"] = parse_huf_value(summary_row.get("tip_huf"))
    if parse_huf_value(enriched.get("Korrekció")) == 0:
        try:
            correction_totals = load_periodic_fee_correction_totals(
                session_id,
                calculation_mode,
                period_start,
                period_end,
                warehouse_label,
            )
        except Exception:
            correction_totals = pd.DataFrame()
        if not correction_totals.empty:
            id_key = _courier_id_key(courier_id)
            name_key = _courier_match_key(courier_name)
            selected = correction_totals.loc[correction_totals["_courier_id_lookup"].eq(id_key)]
            if selected.empty and name_key:
                selected = correction_totals.loc[correction_totals["_courier_name_lookup"].eq(name_key)]
            if not selected.empty:
                enriched["Korrekció"] = float(pd.to_numeric(selected["Korrekció"], errors="coerce").fillna(0.0).sum())
    try:
        adjustments = load_courier_adjustments(courier_id, period_start, period_end)
    except Exception:
        adjustments = pd.DataFrame()
    if not adjustments.empty and "adjustment_type" in adjustments.columns:
        adjustment_totals = adjustments.groupby("adjustment_type")["amount_huf"].sum().to_dict()
        enriched["JITT bónusz"] = float(adjustment_totals.get("bonus", 0.0))
        enriched["JITT malus"] = float(adjustment_totals.get("malus", 0.0))
    return enriched, route_detail


def append_jitt_bonus_malus_mobile_rows(
    rows: list[dict[str, object]],
    row: dict[str, object],
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict[str, object]]:
    courier_id = _courier_id_key(row.get("Courier ID"))
    manual_bonus = parse_huf_value(row.get("JITT bónusz"))
    manual_malus = abs(parse_huf_value(row.get("JITT malus")))
    adjustment_details: list[dict[str, object]] = []
    adjustment_bonus = 0.0
    adjustment_malus = 0.0
    if courier_id and period_start and period_end:
        adjustments = load_courier_adjustments(courier_id, period_start, period_end)
        if not adjustments.empty:
            detail_index = 1
            for _, adjustment in adjustments.reset_index(drop=True).iterrows():
                adjustment_type = str(adjustment.get("adjustment_type") or "").strip()
                if adjustment_type not in {"bonus", "malus"}:
                    continue
                amount = abs(parse_huf_value(adjustment.get("amount_huf")))
                if not amount:
                    continue
                is_bonus = adjustment_type == "bonus"
                if is_bonus:
                    adjustment_bonus += amount
                else:
                    adjustment_malus += amount
                adjustment_details.append({
                    "item_key": f"{'jitt_bonus' if is_bonus else 'jitt_malus'}_{detail_index}",
                    "item_label": "JITT bónusz" if is_bonus else "JITT malus",
                    "amount_kind": "huf",
                    "amount_value": amount if is_bonus else -amount,
                    "note": str(adjustment.get("note") or "").strip() or "Sheet/DB tétel",
                })
                detail_index += 1
    if adjustment_bonus:
        manual_bonus = adjustment_bonus
    if adjustment_malus:
        manual_malus = adjustment_malus
    if not manual_bonus and not manual_malus and not adjustment_details:
        return rows
    rows.extend([
        {
            "item_key": "bonus_malus",
            "item_label": "JITT bónusz / malus",
            "amount_kind": "huf",
            "amount_value": manual_bonus - manual_malus,
            "note": "Sheet/DB tételek összesen",
        },
        {
            "item_key": "manual_bonus",
            "item_label": "JITT bónusz",
            "amount_kind": "huf",
            "amount_value": manual_bonus,
            "note": "Sheet/DB tételek",
        },
        {
            "item_key": "manual_malus",
            "item_label": "JITT malus",
            "amount_kind": "huf",
            "amount_value": -manual_malus,
            "note": "Sheet/DB tételek",
        },
    ])
    rows.extend(adjustment_details)
    return rows


def append_kiflis_bonus_malus_mobile_rows(
    rows: list[dict[str, object]],
    row: dict[str, object],
    session_id: str | None,
) -> list[dict[str, object]]:
    courier_id = _courier_id_key(row.get("Courier ID"))
    courier_name = str(row.get("Futár") or "")
    details = load_imported_balance_component_items(session_id, courier_id, courier_name)
    if details.empty:
        imported_bonus = parse_huf_value(row.get("Importált bónusz"))
        imported_malus = abs(parse_huf_value(row.get("Importált málusz")))
        if imported_bonus:
            rows.append({
                "item_key": "kiflis_bonus_1",
                "item_label": "Kiflis bónusz",
                "amount_kind": "huf",
                "amount_value": imported_bonus,
                "note": str(row.get("Importált bónusz megjegyzés") or "").strip() or "Excel import tétel",
            })
        if imported_malus:
            rows.append({
                "item_key": "kiflis_malus_1",
                "item_label": "Kiflis malus",
                "amount_kind": "huf",
                "amount_value": -imported_malus,
                "note": str(row.get("Importált málusz megjegyzés") or "").strip() or "Excel import tétel",
            })
        return rows
    for index, detail_row in details.reset_index(drop=True).iterrows():
        label = str(detail_row.iloc[0] if len(detail_row) > 0 else "").strip()
        amount = parse_huf_value(detail_row.iloc[1] if len(detail_row) > 1 else 0)
        note = str(detail_row.iloc[2] if len(detail_row) > 2 else "").strip()
        if not amount:
            continue
        key_prefix = "kiflis_bonus" if amount > 0 else "kiflis_malus"
        rows.append({
            "item_key": f"{key_prefix}_{index + 1}",
            "item_label": label or ("Kiflis bónusz" if amount > 0 else "Kiflis malus"),
            "amount_kind": "huf",
            "amount_value": amount,
            "note": note or "Excel import tétel",
        })
    return rows


def append_periodic_correction_mobile_rows(
    rows: list[dict[str, object]],
    *,
    row: dict[str, object],
    route_detail: pd.DataFrame,
    period_start: date,
    period_end: date,
) -> list[dict[str, object]]:
    periodic_total, periodic_detail = calculate_periodic_fee_corrections(
        route_detail,
        period_start,
        period_end,
        row.get("Raktár"),
    )
    manual_correction_total = 0
    for item in rows:
        if str(item.get("item_key") or "") == "correction":
            manual_correction_total = parse_huf_value(item.get("amount_value"))
            item["amount_value"] = manual_correction_total + periodic_total
            break
    else:
        rows.append({
            "item_key": "correction",
            "item_label": "Időszakos díjak / korrekció",
            "amount_kind": "huf",
            "amount_value": periodic_total,
            "note": "Havi nyitáskor publikált snapshot",
        })
    detail_rows = []
    if manual_correction_total:
        detail_rows.append({
            "item_key": "correction_manual_snapshot",
            "item_label": "Kézi korrekciók",
            "amount_kind": "huf",
            "amount_value": manual_correction_total,
            "note": "Havi nyitáskor publikált snapshot",
        })
    if not periodic_detail.empty:
        for correction_index, correction_row in periodic_detail.reset_index(drop=True).iterrows():
            correction_amount = parse_huf_value(correction_row.get("Összeg"))
            if not correction_amount:
                continue
            correction_note_parts = [
                str(correction_row.get("Napok") or "").strip(),
                str(correction_row.get("Túratípus") or "").strip(),
                str(correction_row.get("Feltétel") or "").strip(),
                str(correction_row.get("Számítás") or "").strip(),
            ]
            detail_rows.append({
                "item_key": f"correction_periodic_{correction_index + 1}",
                "item_label": str(correction_row.get("Tétel") or "Időszakos díj"),
                "amount_kind": "huf",
                "amount_value": correction_amount,
                "note": " | ".join(part for part in correction_note_parts if part) or "Időszakos díj szabály alapján",
            })
    if detail_rows:
        existing_keys = {str(item.get("item_key") or "") for item in rows}
        rows.extend(item for item in detail_rows if str(item.get("item_key") or "") not in existing_keys)
    return recalculate_mobile_breakdown_totals(rows)


def tig_editor_rows_from_breakdown(tig_breakdown: dict[str, object], overrides: pd.DataFrame | None = None) -> pd.DataFrame:
    rows = []
    override_map = {}
    if isinstance(overrides, pd.DataFrame) and not overrides.empty:
        override_map = {
            str(item.get("item_key") or ""): item
            for item in overrides.to_dict("records")
            if str(item.get("item_key") or "").startswith("tig_")
        }
    for item in tig_breakdown.get("rows") or []:
        item_key = f"tig_{item.get('key') or ''}"
        override = override_map.get(item_key, {})
        item_label = str(override.get("item_label") or item.get("label") or item_key)
        if item_key == "tig_transfer_service":
            item_label = "Szállítási díj (494107) - átutalás"
        elif item_key == "tig_cash_service":
            item_label = "Szállítási díj (494107) - készpénz"
        rows.append({
            "Kulcs": item_key,
            "MegnevezĂ©s": item_label,
            "TĂ­pus": "huf",
            "Ă‰rtĂ©k": parse_huf_value(override.get("amount_value") if override else item.get("grossHuf")),
            "MegjegyzĂ©s": str(override.get("note") or item.get("note") or ""),
        })
    final_override = override_map.get("tig_final_total", {})
    rows.append({
        "Kulcs": "tig_final_total",
        "MegnevezĂ©s": str(final_override.get("item_label") or "TIG vĂ©gĂ¶sszeg"),
        "TĂ­pus": "huf",
        "Ă‰rtĂ©k": parse_huf_value(final_override.get("amount_value") if final_override else tig_breakdown.get("finalTotalHuf")),
        "MegjegyzĂ©s": str(final_override.get("note") or "TIG elfogadĂˇsnĂˇl lĂˇthatĂł vĂ©gĂ¶sszeg"),
    })
    return pd.DataFrame(rows, columns=["Kulcs", "MegnevezĂ©s", "TĂ­pus", "Ă‰rtĂ©k", "MegjegyzĂ©s"])


def publish_mobile_settlement_snapshot(
    data: pd.DataFrame,
    period_start: date,
    calculation_mode: str,
    warehouse_label: str | None,
    session_id: str | None,
    updated_by: str,
) -> tuple[int, int]:
    if str(calculation_mode or "") not in {"API", "Excel"}:
        return 0, 0
    config_saved = save_mobile_settlement_period_config(
        period_start,
        calculation_mode,
        warehouse_label,
        session_id,
        updated_by,
    )
    if not config_saved:
        return 0, 0
    courier_count = 0
    row_count = 0
    for item in data.to_dict("records"):
        courier_id = _courier_id_key(item.get("Courier ID"))
        if not courier_id:
            continue
        period_end = month_bounds(period_start)[1]
        item, route_detail = enrich_mobile_settlement_row_for_snapshot(
            item,
            courier_id=courier_id,
            courier_name=str(item.get("Futár") or ""),
            session_id=session_id,
            calculation_mode=calculation_mode,
            period_start=period_start,
            period_end=period_end,
            warehouse_label=warehouse_label,
        )
        component_session_id = balance_component_session_id(calculation_mode, period_start, session_id)
        item = enrich_mobile_row_with_imported_balance_components(item, component_session_id)
        rows = append_jitt_bonus_malus_mobile_rows(
            mobile_breakdown_rows_from_settlement_row(item),
            item,
            period_start,
            period_end,
        )
        rows = append_kiflis_bonus_malus_mobile_rows(rows, item, component_session_id)
        try:
            rows = append_periodic_correction_mobile_rows(
                rows,
                row=item,
                route_detail=route_detail,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception:
            pass
        rows = recalculate_mobile_breakdown_totals(rows)
        if save_mobile_breakdown_overrides(courier_id, period_start, rows, updated_by):
            courier_count += 1
            row_count += len(rows)
    return courier_count, row_count


def refresh_mobile_settlement_breakdown_snapshot(
    data: pd.DataFrame,
    period_start: date,
    calculation_mode: str,
    warehouse_label: str | None,
    session_id: str | None,
    updated_by: str,
) -> tuple[int, int]:
    if str(calculation_mode or "") not in {"API", "Excel"}:
        return 0, 0
    courier_count = 0
    row_count = 0
    for item in data.to_dict("records"):
        courier_id = _courier_id_key(item.get("Courier ID"))
        if not courier_id:
            continue
        period_end = month_bounds(period_start)[1]
        item, route_detail = enrich_mobile_settlement_row_for_snapshot(
            item,
            courier_id=courier_id,
            courier_name=str(item.get("Futár") or item.get("FutĂˇr") or ""),
            session_id=session_id,
            calculation_mode=calculation_mode,
            period_start=period_start,
            period_end=period_end,
            warehouse_label=warehouse_label,
        )
        component_session_id = balance_component_session_id(calculation_mode, period_start, session_id)
        item = enrich_mobile_row_with_imported_balance_components(item, component_session_id)
        rows = append_jitt_bonus_malus_mobile_rows(
            mobile_breakdown_rows_from_settlement_row(item),
            item,
            period_start,
            period_end,
        )
        rows = append_kiflis_bonus_malus_mobile_rows(rows, item, component_session_id)
        try:
            rows = append_periodic_correction_mobile_rows(
                rows,
                row=item,
                route_detail=route_detail,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception:
            pass
        rows = recalculate_mobile_breakdown_totals(rows)
        if save_mobile_breakdown_overrides(courier_id, period_start, rows, updated_by):
            courier_count += 1
            row_count += len(rows)
    return courier_count, row_count


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_master(calculation_mode: str = "Excel") -> pd.DataFrame:
    response = (
        get_db()
        .schema("public")
        .table("courier_master")
        .select("*")
        .order("courier_name")
        .execute()
    )

    rows = response.data or []
    columns = [
        "Courier ID", "Futár", "Branch", "Számítás módja",
        "Raktár", "Vállalkozás", "Státusz", "Nettó bevétel", "Bónusz",
        "Borravaló", "Alvállalkozói összeg", "Levonás", "Kifizetendő",
        "Előző havi összeg", "KPI", "Munkakezdés",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows).rename(columns={
        "courier_id": "Courier ID",
        "courier_name": "Futár",
        "warehouse_name": "Raktár",
        "work_start_date": "Munkakezdés",
    })

    df["Courier ID"] = df["Courier ID"].astype(str)
    df["Futár"] = df["Futár"].fillna("Ismeretlen futár")
    df["Branch"] = "JIT"
    df["Számítás módja"] = "API" if str(calculation_mode).casefold() == "api" else "Excel"
    df["Raktár"] = df["Raktár"].fillna("BUD1")
    if "Vállalkozás" not in df.columns:
        df["Vállalkozás"] = ""
    df["Vállalkozás"] = df["Vállalkozás"].fillna("")
    if "Munkakezdés" not in df.columns:
        df["Munkakezdés"] = ""

    df["Státusz"] = "Elszámolásra vár"

    for column in [
        "Nettó bevétel", "Bónusz", "Borravaló", "Alvállalkozói összeg", "Levonás",
        "Kifizetendő", "Előző havi összeg", "KPI",
    ]:
        df[column] = 0.0

    return df[columns]


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_profile(courier_id: str) -> dict[str, object]:
    try:
        rows = (get_db().schema("public").table("courier_master").select("*")
                .eq("courier_id", courier_id).limit(1).execute().data or [])
        return rows[0] if rows else {}
    except BaseException:
        return {}


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_profile_lookup() -> dict[str, dict[str, object]]:
    try:
        rows = (
            get_db().schema("public").table("courier_master")
            .select("courier_id,courier_name,work_start_date,active")
            .limit(20000)
            .execute().data or []
        )
    except BaseException:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for row in rows:
        courier_key = _courier_id_key(row.get("courier_id"))
        if courier_key:
            lookup[courier_key] = row
    return lookup


EMPLOYMENT_TYPE_LABELS = {
    "efo": "EFO",
    "egyeni_vallalkozo": "Egyéni vállalkozó",
    "bejelentett": "Bejelentett",
}


@st.cache_data(show_spinner=False, ttl=60)
def load_active_efo_assignment(courier_id: str, as_of: date) -> dict[str, object]:
    try:
        rows = (
            get_db().schema("settlement").table("courier_efo_assignment")
            .select("*")
            .eq("courier_id", str(courier_id or "").strip())
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", as_of.isoformat())
            .order("valid_from", desc=True)
            .limit(20)
            .execute().data or []
        )
    except BaseException:
        return {}
    for row in rows:
        valid_to = pd.to_datetime(row.get("valid_to"), errors="coerce")
        if pd.isna(valid_to) or valid_to.date() >= as_of:
            return row
    return {}


@st.cache_data(show_spinner=False, ttl=60)
def load_loyalty_month_requirement_for_date(as_of: date) -> int:
    try:
        rows = (
            get_db().schema("settlement").table("cfg_jitt_loyalty_bonus_rules")
            .select("loyalty_months_required,valid_from,valid_to,is_active,deleted_at,priority")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", as_of.isoformat())
            .order("priority")
            .limit(20)
            .execute().data or []
        )
    except BaseException:
        return DEFAULT_LOYALTY_MONTHS_REQUIRED
    valid_requirements: list[int] = []
    for row in rows:
        valid_to = pd.to_datetime(row.get("valid_to"), errors="coerce")
        if pd.isna(valid_to) or valid_to.date() >= as_of:
            required_months = int(parse_huf_value(row.get("loyalty_months_required")))
            valid_requirements.append(required_months if required_months > 0 else DEFAULT_LOYALTY_MONTHS_REQUIRED)
    return min(valid_requirements) if valid_requirements else DEFAULT_LOYALTY_MONTHS_REQUIRED


def _parse_booking_timestamp_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%Y.%m.%d. %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        parsed = pd.to_datetime(text, format=date_format, errors="coerce")
        if pd.notna(parsed):
            return parsed.date()
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _booking_operation_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _is_booking_change_operation(value: object) -> bool:
    operation = _booking_operation_key(value)
    if not operation:
        return False
    return any(
        marker in operation
        for marker in [
            "modosit",
            "modositas",
            "torol",
            "torles",
            "lemond",
            "lemondas",
            "cancel",
            "delete",
            "modify",
            "change",
        ]
    )


def _is_clean_booking_operation(value: object) -> bool:
    operation = _booking_operation_key(value)
    if not operation:
        return False
    if _is_booking_change_operation(value):
        return False
    return any(marker in operation for marker in ["foglal", "book"])


def _booked_by_period_cutoff(value: object, cutoff_date: date) -> bool:
    booked_at = pd.to_datetime(value, errors="coerce")
    return bool(pd.notna(booked_at) and booked_at.date() <= cutoff_date)


def _booking_proxy_email(value: object) -> str:
    match = re.search(r"Proxy:\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", str(value or ""), flags=re.IGNORECASE)
    return match.group(1).strip().casefold() if match else ""


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_identity_by_email() -> dict[str, dict[str, str]]:
    try:
        rows = (
            get_db().schema("public").table("courier_master")
            .select("courier_id,courier_name,email,billing_email")
            .limit(20000)
            .execute().data or []
        )
    except BaseException:
        return {}
    lookup: dict[str, dict[str, str]] = {}
    for row in rows:
        payload = {
            "courier_id": str(row.get("courier_id") or "").strip(),
            "courier_name": str(row.get("courier_name") or "").strip(),
        }
        for email in [row.get("email"), row.get("billing_email")]:
            email_key = str(email or "").strip().casefold()
            if email_key:
                lookup[email_key] = payload
    return lookup


def _loyalty_booking_effective_identity(row: dict[str, object]) -> dict[str, str]:
    proxy_email = _booking_proxy_email(row.get("raw_shift_data"))
    if proxy_email:
        match = load_courier_identity_by_email().get(proxy_email, {})
        return {
            "courier_id": str(match.get("courier_id") or "").strip(),
            "courier_name": str(match.get("courier_name") or "").strip(),
            "user_email": proxy_email,
        }
    return {
        "courier_id": str(row.get("courier_id") or "").strip(),
        "courier_name": str(row.get("courier_name") or "").strip(),
        "user_email": str(row.get("user_email") or "").strip(),
    }


def _loyalty_booking_shift_key(row: dict[str, object], *, include_driver: bool = False) -> tuple[str, ...]:
    identity = _loyalty_booking_effective_identity(row)
    driver_key = _courier_id_key(identity.get("courier_id")) or _courier_match_key(
        identity.get("courier_name") or identity.get("user_email")
    )
    shift_date = str(row.get("shift_date") or "").strip()[:10]
    shift_time = str(row.get("shift_time") or "").strip()
    warehouse = str(row.get("warehouse") or "").strip().casefold()
    raw_shift_data = str(row.get("raw_shift_data") or "").strip()
    base_key = (shift_date, shift_time, warehouse, raw_shift_data)
    return (driver_key, *base_key) if include_driver else base_key


def _summarize_loyalty_booking_log_rows(
    rows: list[dict[str, object]],
    previous_month_end: date,
) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    changed_keys = {
        _loyalty_booking_shift_key(row)
        for row in rows
        if _is_booking_change_operation(row.get("operation"))
    }
    clean_booking_keys = set()
    advance_booking_keys = set()
    for row in rows:
        shift_key = _loyalty_booking_shift_key(row)
        if not all(shift_key[:2]) or shift_key in changed_keys:
            continue
        if not _is_clean_booking_operation(row.get("operation")):
            continue
        clean_booking_keys.add(shift_key)
        if _booked_by_period_cutoff(row.get("booked_at"), previous_month_end):
            advance_booking_keys.add(shift_key)
    return clean_booking_keys, advance_booking_keys


@st.cache_data(show_spinner=False, ttl=60)
def load_muszakpro_booking_summary(courier_id: str, period_start: date, period_end: date) -> dict[str, object]:
    clean_courier_id = str(courier_id or "").strip()
    if not clean_courier_id:
        return {"booked_shift_count": 0, "advance_booked_shift_count": 0, "source": ""}

    previous_month_end = period_start - timedelta(days=1)
    try:
        log_rows = (
            get_db().schema("settlement").table("courier_loyalty_booking_log")
            .select("courier_id,courier_name,user_email,operation,booked_at,shift_date,shift_time,warehouse,raw_shift_data,source_key")
            .gte("shift_date", period_start.isoformat())
            .lte("shift_date", period_end.isoformat())
            .limit(50000)
            .execute().data or []
        )
    except BaseException:
        log_rows = []
    log_rows = [
        row for row in log_rows
        if _courier_id_key(_loyalty_booking_effective_identity(row).get("courier_id")) == _courier_id_key(clean_courier_id)
    ]
    if log_rows:
        clean_keys, advance_keys = _summarize_loyalty_booking_log_rows(log_rows, previous_month_end)
        return {
            "booked_shift_count": len(clean_keys),
            "advance_booked_shift_count": len(advance_keys),
            "source": "courier_loyalty_booking_log",
        }

    rows: list[dict[str, object]] = []
    source_table = ""
    for table_name in ["raw_muszakpro_bookings", "foglalasok_raw"]:
        try:
            rows = (
                get_db().schema("public").table(table_name)
                .select("work_date,timestamp_text,shift_text,booking_code,serial,courier_id")
                .eq("courier_id", clean_courier_id)
                .gte("work_date", period_start.isoformat())
                .lte("work_date", period_end.isoformat())
                .limit(1000)
                .execute().data or []
            )
            source_table = table_name
            break
        except BaseException:
            rows = []

    if not rows:
        return {"booked_shift_count": 0, "advance_booked_shift_count": 0, "source": ""}

    unique_keys = set()
    advance_keys = set()
    for row in rows:
        key = (
            str(row.get("work_date") or ""),
            str(row.get("shift_text") or ""),
            str(row.get("booking_code") or row.get("serial") or ""),
        )
        unique_keys.add(key)
        booking_date = _parse_booking_timestamp_date(row.get("timestamp_text"))
        if booking_date and booking_date <= previous_month_end:
            advance_keys.add(key)

    return {
        "booked_shift_count": len(unique_keys),
        "advance_booked_shift_count": len(advance_keys),
        "source": source_table,
    }


@st.cache_data(show_spinner=False, ttl=60)
def load_giriton_shift_summary(courier_id: str, period_start: date, period_end: date) -> dict[str, object]:
    clean_courier_id = str(courier_id or "").strip()
    if not clean_courier_id:
        return {"giriton_shift_count": 0, "source": ""}

    def valid_status(value: object) -> bool:
        text = str(value or "").strip().casefold()
        return bool(text) and text not in {"-", "nincs", "missing", "missing_giriton"}

    for table_name, select_columns in [
        ("ops_shift_comparison", "work_date,shift_start,giriton_status,courier_id"),
        ("giriton_shifts_raw", "work_date,start_time,status,courier_id,serial"),
        ("raw_giriton_shifts", "work_date,start_time,status,courier_id,serial"),
    ]:
        try:
            rows = (
                get_db().schema("public").table(table_name)
                .select(select_columns)
                .eq("courier_id", clean_courier_id)
                .gte("work_date", period_start.isoformat())
                .lte("work_date", period_end.isoformat())
                .limit(2000)
                .execute().data or []
            )
        except BaseException:
            rows = []
        if not rows:
            continue
        unique_keys = set()
        for row in rows:
            status_value = row.get("giriton_status") if table_name == "ops_shift_comparison" else row.get("status")
            if not valid_status(status_value):
                continue
            unique_keys.add((
                str(row.get("work_date") or ""),
                str(row.get("shift_start") or row.get("start_time") or ""),
                str(row.get("serial") or ""),
            ))
        return {"giriton_shift_count": len(unique_keys), "source": table_name}

    return {"giriton_shift_count": 0, "source": ""}


def save_monthly_workload_summary(
    *,
    courier_id: str,
    courier_name: str,
    period_start: date,
    period_end: date,
    booked_shift_count: int,
    advance_booked_shift_count: int,
    giriton_shift_count: int,
    completed_route_count: int,
    order_count: int,
    muszakpro_source: str,
    route_source: str,
) -> None:
    try:
        get_db().schema("settlement").table("courier_monthly_workload_summary").upsert(
            {
                "courier_id": str(courier_id or "").strip(),
                "courier_name": str(courier_name or "").strip(),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "booked_shift_count": max(int(booked_shift_count or 0), 0),
                "advance_booked_shift_count": max(int(advance_booked_shift_count or 0), 0),
                "giriton_shift_count": max(int(giriton_shift_count or 0), 0),
                "completed_route_count": max(int(completed_route_count or 0), 0),
                "order_count": max(int(order_count or 0), 0),
                "muszakpro_source": str(muszakpro_source or ""),
                "route_source": str(route_source or ""),
                "updated_by": str(st.session_state.get("user", {}).get("username") or "unknown"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="courier_id,period_start",
        ).execute()
    except BaseException:
        # The finance UI remains usable even before the DB migration is deployed.
        pass


@st.cache_data(show_spinner=False, ttl=60)
def load_target_reserve_status(courier_id: str, courier_name: str) -> dict[str, object]:
    """Return insurance only from the insurance_active flag of a matching reserve row."""
    clean_courier_id = str(courier_id or "").strip()
    try:
        query = get_db().schema("public").table("courier_target_reserve").select("*").limit(1)
        rows = query.eq("courier_ID", clean_courier_id).execute().data or []
    except BaseException:
        return {"insurance_active": False, "row": {}}
    if not rows:
        return {"insurance_active": False, "row": {}}
    def id_key(value: object) -> str:
        text = str(value or "").strip().casefold()
        if not text:
            return ""
        try:
            numeric = float(text.replace(" ", "").replace(",", "."))
            return str(int(numeric)) if numeric.is_integer() else str(numeric)
        except ValueError:
            return text

    def normalized_column_name(value: object) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

    target_id = id_key(courier_id)
    for reserve_row in rows:
        id_columns = {"courierid", "couriernumber", "usernumber", "userid", "driverid"}
        id_values = [value for column, value in reserve_row.items() if normalized_column_name(column) in id_columns]
        matches_id = target_id and any(id_key(value) == target_id for value in id_values if value is not None)
        if matches_id:
            active_value = next((value for column, value in reserve_row.items() if normalized_column_name(column) == "insuranceactive"), None)
            active = str(active_value).strip().casefold() in {"true", "t", "1", "yes", "igen"}
            return {"insurance_active": active, "row": reserve_row}
    return {"insurance_active": False, "row": {}}


def reserve_row_amount(reserve_row: dict[str, object], column: str) -> float:
    if not reserve_row:
        return 0.0
    value = reserve_row.get(column)
    if value in (None, "") and column == "current_reserve_huf":
        value = reserve_row.get("CT_Z_FT")
    return parse_huf_value(value)


@st.cache_data(show_spinner=False, ttl=60)
def load_active_reserve_insurance_rule(period_start: date) -> dict[str, object]:
    try:
        rows = (
            get_db().schema("settlement").table("cfg_jitt_reserve_insurance_rules")
            .select("*")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", period_start.isoformat())
            .order("priority", desc=False)
            .order("valid_from", desc=True)
            .limit(20)
            .execute().data or []
        )
    except BaseException:
        return {}
    for row in rows:
        valid_to = str(row.get("valid_to") or "").strip()
        if not valid_to or valid_to[:10] >= period_start.isoformat():
            return row
    return {}


def calculate_target_reserve_month(
    reserve_status: dict[str, object],
    payable_before_insurance: float,
    period_start: date | None = None,
) -> dict[str, object]:
    reserve_row = reserve_status.get("row") or {}
    insurance_active_before = bool(reserve_status.get("insurance_active"))
    rule = load_active_reserve_insurance_rule(period_start or date.today().replace(day=1))
    reserve_target = parse_huf_value(rule.get("reserve_target_huf")) or RESERVE_TARGET_HUF
    reserve_rate = (parse_huf_value(rule.get("deduction_percent")) / 100.0) if rule else RESERVE_RATE
    insurance_fee_rule = parse_huf_value(rule.get("insurance_fee_huf")) if rule else INSURANCE_FEE_HUF
    reserve_before = reserve_row_amount(reserve_row, "current_reserve_huf")
    if reserve_before == 0:
        reserve_before = reserve_row_amount(reserve_row, "CT_Z_FT")

    should_charge = insurance_active_before and reserve_before < reserve_target
    calculated_addition = round(max(float(payable_before_insurance), 0.0) * reserve_rate) if should_charge else 0
    reserve_addition = min(calculated_addition, max(0, int(round(reserve_target - reserve_before)))) if should_charge else 0
    insurance_fee = insurance_fee_rule if should_charge else 0
    reserve_after = reserve_before + reserve_addition
    insurance_active_after = bool(insurance_active_before and reserve_after < reserve_target)
    payable_after = float(payable_before_insurance) - reserve_addition - insurance_fee
    return {
        "payable_before_insurance_huf": float(payable_before_insurance),
        "reserve_before_huf": reserve_before,
        "reserve_addition_huf": reserve_addition,
        "insurance_fee_huf": insurance_fee,
        "reserve_after_huf": reserve_after,
        "payable_after_insurance_huf": payable_after,
        "insurance_active_before": insurance_active_before,
        "insurance_active_after": insurance_active_after,
    }


@st.cache_data(show_spinner=False, ttl=30)
def load_target_reserve_monthly(courier_id: str, period_start: date, period_end: date) -> dict[str, object]:
    try:
        rows = (get_db().schema("settlement").table("courier_target_reserve_monthly")
                .select("*").eq("courier_id", courier_id)
                .eq("period_start", period_start.isoformat())
                .eq("period_end", period_end.isoformat())
                .limit(1).execute().data or [])
        return rows[0] if rows else {}
    except BaseException:
        return {}


def save_target_reserve_monthly(
    session_id: str | None,
    courier_id: str,
    period_start: date,
    period_end: date,
    calculation: dict[str, object],
) -> None:
    existing = load_target_reserve_monthly(courier_id, period_start, period_end)
    if existing.get("status") == "done":
        return
    payload = {
        "courier_id": courier_id,
        "session_id": session_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "status": "in_progress",
        "calculated_at": pd.Timestamp.utcnow().isoformat(),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
        **calculation,
    }
    try:
        get_db().schema("settlement").table("courier_target_reserve_monthly").upsert(
            payload,
            on_conflict="courier_id,period_start,period_end",
        ).execute()
        load_target_reserve_monthly.clear()
    except BaseException:
        pass


def close_target_reserve_month(
    session_id: str | None,
    courier_id: str,
    period_start: date,
    period_end: date,
    calculation: dict[str, object],
) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    payload = {
        "courier_id": courier_id,
        "session_id": session_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "status": "done",
        "closed_at": pd.Timestamp.utcnow().isoformat(),
        "closed_by": actor,
        "calculated_at": pd.Timestamp.utcnow().isoformat(),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
        **calculation,
    }
    get_db().schema("settlement").table("courier_target_reserve_monthly").upsert(
        payload,
        on_conflict="courier_id,period_start,period_end",
    ).execute()
    get_db().schema("public").table("courier_target_reserve").update({
        "CT_Z_FT": str(int(round(parse_huf_value(calculation.get("reserve_after_huf"))))),
        "CT_NY_FT": str(int(round(parse_huf_value(calculation.get("reserve_addition_huf"))))),
        "current_reserve_huf": int(round(parse_huf_value(calculation.get("reserve_after_huf")))),
        "reserve_deduction_huf": int(round(parse_huf_value(calculation.get("reserve_addition_huf")))),
        "insurance_active": bool(calculation.get("insurance_active_after")),
        "reserve_status": "done",
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("courier_ID", courier_id).execute()
    load_target_reserve_status.clear()
    load_target_reserve_monthly.clear()


@st.cache_data(show_spinner=False, ttl=30)
def load_courier_monthly_closure(courier_id: str, period_start: date, period_end: date) -> dict[str, object]:
    try:
        rows = (
            get_db().schema("settlement").table("courier_monthly_closure")
            .select("*")
            .eq("courier_id", courier_id)
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .limit(1)
            .execute().data or []
        )
        return rows[0] if rows else {}
    except BaseException:
        return {}


@st.cache_data(show_spinner=False, ttl=30)
def load_monthly_closure_statuses(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("courier_monthly_closure")
            .select("courier_id,status")
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .eq("status", "done")
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def apply_monthly_closure_status(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    result = data.copy()
    closures = load_monthly_closure_statuses(period_start, period_end)
    if closures.empty or "Courier ID" not in result.columns:
        if "Kifizetve" not in result.columns:
            result["Kifizetve"] = False
        return result
    paid_ids = set(closures.get("courier_id", pd.Series(dtype=str)).map(_courier_id_key))
    courier_ids = result["Courier ID"].map(_courier_id_key)
    result["Kifizetve"] = courier_ids.isin(paid_ids)
    result.loc[result["Kifizetve"], "Státusz"] = "Kifizetve"
    return result


def apply_peopleforce_workflow_status(data: pd.DataFrame, document_month: date) -> pd.DataFrame:
    result = data.copy()
    if result.empty or "Courier ID" not in result.columns:
        return result

    month_start = document_month.replace(day=1)
    courier_ids = result["Courier ID"].map(_courier_id_key)
    result["Státusz"] = "Elszámolásra vár"

    try:
        documents = read_peopleforce_documents_for_month(month_start)
    except Exception:
        documents = pd.DataFrame()
    try:
        statuses = read_peopleforce_card_statuses_for_month(month_start)
    except Exception:
        statuses = pd.DataFrame()
    try:
        complaints = read_peopleforce_complaints_for_month(month_start)
    except Exception:
        complaints = pd.DataFrame()

    document_types_by_courier: dict[str, set[str]] = {}
    if not documents.empty:
        for item in documents.to_dict("records"):
            if process_id_from_note(item.get("note")):
                continue
            courier_key = _courier_id_key(item.get("courier_id"))
            document_type = str(item.get("document_type") or "").strip()
            if courier_key and document_type:
                document_types_by_courier.setdefault(courier_key, set()).add(document_type)

    status_by_courier: dict[str, dict[str, str]] = {}
    if not statuses.empty:
        for item in statuses.sort_values("updated_at", ascending=False, na_position="last").to_dict("records"):
            courier_key = _courier_id_key(item.get("courier_id"))
            action_key = str(item.get("action_key") or "").strip()
            if process_id_from_action_key(action_key):
                continue
            if courier_key and action_key:
                status_by_courier.setdefault(courier_key, {}).setdefault(
                    action_key,
                    str(item.get("status") or "").strip().casefold(),
                )

    complaint_couriers: set[str] = set()
    if not complaints.empty:
        for item in complaints.to_dict("records"):
            status = str(item.get("status") or "").strip().casefold()
            has_admin_answer = bool(str(item.get("admin_response") or "").strip() or str(item.get("responded_at") or "").strip())
            if status in {"resolved", "closed"} or has_admin_answer:
                continue
            courier_key = _courier_id_key(item.get("courier_id"))
            if courier_key:
                complaint_couriers.add(courier_key)

    def workflow_status(courier_key: str) -> str:
        if courier_key in complaint_couriers:
            return "Bejelentések"
        document_types = document_types_by_courier.get(courier_key, set())
        action_statuses = status_by_courier.get(courier_key, {})
        if "settlement" not in document_types:
            return "Elszámolásra vár"
        if action_statuses.get("settlement") != "done":
            return "Elszámolás elfogadásra vár"
        if action_statuses.get("invoice_payment") == "done":
            return "Kifizetve"
        if "tig" not in document_types:
            return "TIG-re vár"
        if action_statuses.get("tig") != "done":
            return "TIG elfogadásra vár"
        if (
            action_statuses.get("tig") == "done"
            or action_statuses.get("invoice_check") == "done"
            or action_statuses.get("invoice_submit") == "done"
            or "invoice" in document_types
        ):
            return "Kifizetésre vár"
        return "TIG-re vár"

    result["Státusz"] = courier_ids.map(workflow_status)
    return result


def format_bank_account_4(value: object) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    return " ".join(digits[index:index + 4] for index in range(0, len(digits), 4))


def slugify_filename(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "dokumentum"


def make_document_reference(courier_id: str, document_type: str, document_month: date) -> str:
    month_text = document_month.replace(day=1).strftime("%Y%m")
    doc_type = re.sub(r"[^A-Z0-9]+", "", str(document_type or "DOC").upper()) or "DOC"
    return f"{courier_id}-{month_text}-{doc_type}-{uuid.uuid4().hex[:8].upper()}"


def normalize_process_id(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    if text in {"", "havi", "monthly", "alap"}:
        return ""
    return text[:80]


def process_action_key(action: str, process_id: object = "") -> str:
    clean_process = normalize_process_id(process_id)
    return f"process:{clean_process}:{action}" if clean_process else action


def base_action_key(action_key: object) -> str:
    match = re.fullmatch(r"process:([a-z0-9_-]+):(.+)", str(action_key or "").strip())
    return match.group(2) if match else str(action_key or "").strip()


def process_id_from_action_key(action_key: object) -> str:
    match = re.fullmatch(r"process:([a-z0-9_-]+):(.+)", str(action_key or "").strip())
    return match.group(1) if match else ""


def process_id_from_note(note: object) -> str:
    match = re.search(r"Folyamat azonos[íi]t[óo]:\s*([a-z0-9_-]+)", str(note or ""), flags=re.IGNORECASE)
    return normalize_process_id(match.group(1)) if match else ""


def delete_peopleforce_process_statuses(courier_id: str, document_month: date, process_id: object) -> int:
    clean_process = normalize_process_id(process_id)
    if not clean_process:
        return 0
    deleted = 0
    for action in ["settlement", "tig", "invoice_submit", "invoice_check", "invoice_payment"]:
        get_db().schema("public").table("peopleforce_card_statuses").delete() \
            .eq("courier_id", str(courier_id or "").strip()) \
            .eq("document_month", document_month.replace(day=1).isoformat()) \
            .eq("action_key", process_action_key(action, clean_process)) \
            .execute()
        deleted += 1
    read_peopleforce_card_statuses.clear()
    read_peopleforce_card_statuses_for_month.clear()
    return deleted


@st.cache_data(show_spinner=False, ttl=60)
def load_latest_invoice_number(courier_id: str, period_start: date) -> str:
    month_text = period_start.strftime("%Y-%m")
    try:
        rows = (
            get_db().schema("public").table("peopleforce_documents")
            .select("document_type,document_month,title,file_name,note,uploaded_at")
            .eq("courier_id", courier_id)
            .eq("document_month", month_text)
            .order("uploaded_at", desc=True)
            .limit(20)
            .execute().data or []
        )
    except BaseException:
        return ""
    invoice_rows = [
        row for row in rows
        if "számla" in str(row.get("document_type") or row.get("title") or row.get("file_name") or "").casefold()
        or "szamla" in str(row.get("document_type") or row.get("title") or row.get("file_name") or "").casefold()
    ]
    for row in invoice_rows or rows:
        haystack = " ".join(str(row.get(column) or "") for column in ["note", "title", "file_name"])
        for pattern in [
            r"(?:számlaszám|szamlaszam|sorszám|sorszam)\s*:?\s*([A-Za-z0-9/_-]{3,})",
            r"\b([A-Z]{1,5}[-_/]?\d{3,})\b",
        ]:
            match = re.search(pattern, haystack, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def invoice_number_from_document(document: dict[str, object]) -> str:
    haystack = " ".join(str(document.get(column) or "") for column in ["note", "title", "file_name"])
    for pattern in [
        r"(?:számlaszám|szamlaszam|sorszám|sorszam)\s*:?\s*([A-Za-z0-9/_-]{3,})",
        r"\b([A-Z]{1,5}[-_/]?\d{3,})\b",
    ]:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def invoice_amount_from_document(document: dict[str, object]) -> float:
    note = str(document.get("note") or "")
    for pattern in [
        r"brutt[óo]\s+[öo]sszesen\s*:?\s*([0-9\s.,]+)\s*Ft",
        r"[öo]sszeg\s*:?\s*([0-9\s.,]+)\s*Ft",
    ]:
        match = re.search(pattern, note, flags=re.IGNORECASE)
        if match:
            return parse_huf_value(match.group(1))
    return 0.0


WORKFLOW_BACKSTEP_TARGETS = {
    "settlement": {"label": "Elszamolas elfogadasara", "done": [], "open": ["settlement", "tig", "invoice_submit", "invoice_check", "invoice_payment"]},
    "tig": {"label": "TIG elfogadasara", "done": ["settlement"], "open": ["tig", "invoice_submit", "invoice_check", "invoice_payment"]},
    "invoice_submit": {"label": "Szamlafeltoltesre", "done": ["settlement", "tig"], "open": ["invoice_submit", "invoice_check", "invoice_payment"]},
    "invoice_check": {"label": "Szamlaellenorzesre", "done": ["settlement", "tig", "invoice_submit"], "open": ["invoice_check", "invoice_payment"]},
    "invoice_payment": {"label": "Kifizetesre", "done": ["settlement", "tig", "invoice_submit", "invoice_check"], "open": ["invoice_payment"]},
}


def backstep_peopleforce_workflow(*, courier_id: str, courier_name: str, document_month: date, target_action: str, updated_by: str, note: str = "") -> int:
    target = WORKFLOW_BACKSTEP_TARGETS.get(str(target_action or ""))
    if not target:
        return 0
    clean_note = str(note or "").strip() or f"Admin visszaleptette: {target['label']}."
    saved = 0
    for action_key in ["manual_invoice_skip", "invoice_validation_override"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="open", status_note=clean_note, updated_by=updated_by)
        saved += 1
    for action_key in target["done"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="done", status_note=clean_note, updated_by=updated_by)
        saved += 1
    for action_key in target["open"]:
        upsert_peopleforce_card_status(courier_id=courier_id, courier_name=courier_name, action_key=action_key, document_month=document_month, status="open", status_note=clean_note, updated_by=updated_by)
        saved += 1
    read_peopleforce_card_statuses.clear()
    read_peopleforce_card_statuses_for_month.clear()
    return saved


def load_courier_payment_documents(courier_id: str, period_start: date) -> pd.DataFrame:
    try:
        documents = read_peopleforce_documents_for_month(period_start.replace(day=1), "invoice")
    except Exception:
        return pd.DataFrame()
    if documents.empty:
        return documents
    return documents[
        documents.get("courier_id", pd.Series("", index=documents.index))
        .astype(str).map(_courier_id_key).eq(_courier_id_key(courier_id))
    ].copy()


def copy_cards_html(items: list[tuple[str, str]]) -> None:
    payload = json.dumps([{"label": label, "value": value} for label, value in items])
    components.html(
        f"""
        <div id="copy-grid" style="display:grid;gap:10px;font-family:Inter,Arial,sans-serif;">
        </div>
        <script>
        const items = {payload};
        const root = document.getElementById("copy-grid");
        items.forEach((item) => {{
        const button = document.createElement("button");
        button.type = "button";
        button.style.cssText = "width:100%;text-align:left;border:1px solid #dfe7e2;border-radius:8px;background:#fff;padding:10px 12px;cursor:pointer;color:#15251d;";
        button.innerHTML = `<div style="font-size:11px;color:#6c7971;margin-bottom:4px;">${{item.label}}</div><div style="font-size:15px;font-weight:700;">${{item.value || '-'}}</div>`;
        button.onclick = async () => {{
            await navigator.clipboard.writeText(item.value || "");
            const old = button.innerHTML;
            button.innerHTML = `<div style="font-size:11px;color:#16803a;margin-bottom:4px;">Másolva</div><div style="font-size:15px;font-weight:700;">${{item.value || '-'}}</div>`;
            setTimeout(() => button.innerHTML = old, 1100);
        }};
        root.appendChild(button);
        }});
        </script>
        """,
        height=max(120, len(items) * 72),
    )


def save_courier_monthly_closure(
    session_id: str | None,
    courier_id: str,
    courier_name: str,
    period_start: date,
    period_end: date,
    transfer_data: dict[str, object],
    snapshot: dict[str, object],
) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    payload = {
        "courier_id": courier_id,
        "courier_name": courier_name,
        "session_id": session_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "bank_account_number": str(transfer_data.get("bank_account_number") or ""),
        "recipient_name": str(transfer_data.get("recipient_name") or ""),
        "payment_note": str(transfer_data.get("payment_note") or ""),
        "invoice_number": str(transfer_data.get("invoice_number") or ""),
        "payable_huf": parse_huf_value(transfer_data.get("payable_huf")),
        "status": "done",
        "closed_at": pd.Timestamp.utcnow().isoformat(),
        "closed_by": actor,
        "snapshot": snapshot,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    get_db().schema("settlement").table("courier_monthly_closure").upsert(
        payload,
        on_conflict="courier_id,period_start,period_end",
    ).execute()
    load_courier_monthly_closure.clear()


def reopen_courier_monthly_closure(courier_id: str, period_start: date, period_end: date) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    try:
        get_db().schema("settlement").table("courier_monthly_closure").update({
            "status": "reopened",
            "reopened_at": pd.Timestamp.utcnow().isoformat(),
            "reopened_by": actor,
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        }).eq("courier_id", courier_id).eq("period_start", period_start.isoformat()).eq("period_end", period_end.isoformat()).execute()
    except Exception as exc:
        message = str(exc)
        if "reopened_at" not in message and "courier_monthly_closure_status_check" not in message:
            raise
        # Backward-compatible fallback for environments where the reopen
        # migration has not run yet: removing the closure row makes the month
        # editable again and avoids counting it as paid.
        get_db().schema("settlement").table("courier_monthly_closure").delete() \
            .eq("courier_id", courier_id) \
            .eq("period_start", period_start.isoformat()) \
            .eq("period_end", period_end.isoformat()) \
            .execute()
    load_courier_monthly_closure.clear()
    load_monthly_closure_statuses.clear()


def reopen_target_reserve_month(courier_id: str, period_start: date, period_end: date) -> None:
    saved = load_target_reserve_monthly(courier_id, period_start, period_end)
    if not saved or str(saved.get("status") or "").casefold() != "done":
        return
    reserve_before = int(round(parse_huf_value(saved.get("reserve_before_huf"))))
    reserve_addition = int(round(parse_huf_value(saved.get("reserve_addition_huf"))))
    get_db().schema("settlement").table("courier_target_reserve_monthly").update({
        "status": "in_progress",
        "closed_at": None,
        "closed_by": None,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("courier_id", courier_id).eq("period_start", period_start.isoformat()).eq("period_end", period_end.isoformat()).execute()
    get_db().schema("public").table("courier_target_reserve").update({
        "CT_Z_FT": str(reserve_before),
        "CT_NY_FT": str(reserve_addition),
        "current_reserve_huf": reserve_before,
        "reserve_deduction_huf": reserve_addition,
        "insurance_active": bool(saved.get("insurance_active_before")),
        "reserve_status": "in_progress",
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("courier_ID", courier_id).execute()
    load_target_reserve_status.clear()
    load_target_reserve_monthly.clear()


def month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    next_month = (pd.Timestamp(start) + pd.DateOffset(months=1)).date()
    return start, next_month - timedelta(days=1)


def add_months(value: date, months: int) -> date:
    return (pd.Timestamp(value.replace(day=1)) + pd.DateOffset(months=months)).date()


def previous_month_delta_note(current_total: float, previous_total: float) -> str:
    current_value = parse_huf_value(current_total)
    previous_value = parse_huf_value(previous_total)
    if previous_value <= 0:
        return "Előző hónap: nincs adat"
    difference = current_value - previous_value
    if difference >= 0:
        return f"{format_huf(difference)} túlteljesítés az előző hónaphoz képest"
    return f"{format_huf(abs(difference))} hiányzik az előző hónaphoz"


def donut_percent(current_total: float, previous_total: float) -> int:
    previous_value = parse_huf_value(previous_total)
    if previous_value <= 0:
        return 100 if parse_huf_value(current_total) > 0 else 0
    return max(0, min(100, int(round(parse_huf_value(current_total) / previous_value * 100))))


def salary_advance_installment_amounts(total_huf: float, months: int) -> list[int]:
    total = int(round(parse_huf_value(total_huf)))
    count = max(1, int(months or 1))
    base_amount = total // count
    amounts = [base_amount for _ in range(count)]
    amounts[-1] += total - sum(amounts)
    return amounts


@st.cache_data(show_spinner=False, ttl=30)
def load_salary_advance_installments_for_month(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("courier_salary_advance_installment")
            .select("*")
            .eq("status", "open")
            .gte("period_end", period_start.isoformat())
            .lte("period_start", period_end.isoformat())
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=30)
def load_courier_salary_advance_history(courier_id: str) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("courier_salary_advance_installment")
            .select("*, courier_salary_advance_plan(requested_amount_huf,installment_months,start_date,note,status)")
            .eq("courier_id", courier_id)
            .order("period_start", desc=False)
            .order("installment_no", desc=False)
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def load_courier_salary_advance_current(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    installments = load_salary_advance_installments_for_month(period_start, period_end)
    if installments.empty or "courier_id" not in installments.columns:
        return pd.DataFrame()
    return installments[installments["courier_id"].map(_courier_id_key).eq(_courier_id_key(courier_id))].copy()


def apply_salary_advance_deduction(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    result = data.copy()
    result["Fizetés előleg"] = 0.0
    installments = load_salary_advance_installments_for_month(period_start, period_end)
    if installments.empty or "Courier ID" not in result.columns:
        return result
    amounts = (
        installments.assign(
            courier_key=installments.get("courier_id", pd.Series(dtype=str)).map(_courier_id_key),
            amount=pd.to_numeric(installments.get("amount_huf"), errors="coerce").fillna(0.0),
        )
        .groupby("courier_key")["amount"].sum()
        .to_dict()
    )
    result["Fizetés előleg"] = result["Courier ID"].map(lambda value: float(amounts.get(_courier_id_key(value), 0.0)))
    if "Levonás" not in result.columns:
        result["Levonás"] = 0.0
    result["Levonás"] = pd.to_numeric(result["Levonás"], errors="coerce").fillna(0.0) + result["Fizetés előleg"]
    if "Kifizetendő" in result.columns:
        result["Kifizetendő"] = pd.to_numeric(result["Kifizetendő"], errors="coerce").fillna(0.0) - result["Fizetés előleg"]
    return result


def create_salary_advance_plan(
    courier_id: str,
    courier_name: str,
    requested_amount_huf: float,
    installment_months: int,
    start_date: date,
    note: str,
) -> str:
    plan_id = str(uuid.uuid4())
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    start_month, _ = month_bounds(start_date)
    amounts = salary_advance_installment_amounts(requested_amount_huf, installment_months)
    monthly_amount = amounts[0] if amounts else 0
    plan_payload = {
        "id": plan_id,
        "courier_id": courier_id,
        "courier_name": courier_name,
        "requested_amount_huf": int(round(parse_huf_value(requested_amount_huf))),
        "installment_months": len(amounts),
        "monthly_amount_huf": monthly_amount,
        "start_date": start_month.isoformat(),
        "status": "open",
        "note": note,
        "created_by": actor,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    installment_payloads = []
    for index, amount in enumerate(amounts):
        period_start, period_end = month_bounds(add_months(start_month, index))
        installment_payloads.append({
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "courier_id": courier_id,
            "courier_name": courier_name,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "installment_no": index + 1,
            "installment_count": len(amounts),
            "amount_huf": amount,
            "status": "open",
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        })
    get_db().schema("settlement").table("courier_salary_advance_plan").insert(plan_payload).execute()
    if installment_payloads:
        get_db().schema("settlement").table("courier_salary_advance_installment").insert(installment_payloads).execute()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return plan_id


@st.cache_data(show_spinner=False, ttl=30)
def load_courier_salary_advance_requests(courier_id: str) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("courier_salary_advance_request")
            .select("*")
            .eq("courier_id", str(courier_id or "").strip())
            .order("requested_at", desc=True)
            .limit(100)
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def create_salary_advance_request(
    courier_id: str,
    courier_name: str,
    requested_amount_huf: float,
    installment_months: int,
    start_date: date,
    note: str,
) -> None:
    start_month, _ = month_bounds(start_date)
    amounts = salary_advance_installment_amounts(requested_amount_huf, installment_months)
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    get_db().schema("settlement").table("courier_salary_advance_request").insert({
        "courier_id": str(courier_id or "").strip(),
        "courier_name": str(courier_name or "").strip(),
        "requested_amount_huf": int(round(parse_huf_value(requested_amount_huf))),
        "installment_months": len(amounts),
        "monthly_amount_huf": amounts[0] if amounts else 0,
        "start_date": start_month.isoformat(),
        "status": "requested",
        "note": str(note or "").strip(),
        "requested_by": actor,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).execute()
    load_courier_salary_advance_requests.clear()


def update_salary_advance_schedule(
    request_row: dict,
    courier_name: str,
    new_start_date: date,
    new_installment_months: int,
    change_note: str = "",
) -> str:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    request_id = str(request_row.get("id") or "").strip()
    courier_id = str(request_row.get("courier_id") or "").strip()
    requested_amount = int(round(parse_huf_value(request_row.get("requested_amount_huf"))))
    start_month, _ = month_bounds(new_start_date)
    requested_months = max(1, int(new_installment_months or 1))
    request_amounts = salary_advance_installment_amounts(requested_amount, requested_months)
    existing_note = str(request_row.get("note") or "").strip()
    response = str(change_note or "").strip()
    updated_note = "\n\n".join(
        part for part in [
            existing_note,
            f"Ütemezés módosítva ({actor}): kezdés {start_month:%Y-%m}, {requested_months} hónap. {response}".strip(),
        ]
        if part
    )
    get_db().schema("settlement").table("courier_salary_advance_request").update({
        "installment_months": requested_months,
        "monthly_amount_huf": request_amounts[0] if request_amounts else 0,
        "start_date": start_month.isoformat(),
        "note": updated_note,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", request_id).execute()

    plan_id = str(request_row.get("plan_id") or "").strip()
    if not plan_id:
        load_courier_salary_advance_requests.clear()
        return "Az igény ütemezése módosítva. Részlet-terv még nem jött létre."

    existing_installments = (
        get_db().schema("settlement").table("courier_salary_advance_installment")
        .select("*")
        .eq("plan_id", plan_id)
        .order("installment_no", desc=False)
        .execute().data or []
    )
    done_rows = [
        row for row in existing_installments
        if str(row.get("status") or "").casefold() == "done"
    ]
    done_amount = sum(parse_huf_value(row.get("amount_huf")) for row in done_rows)
    remaining_amount = max(0, requested_amount - int(round(done_amount)))
    remaining_months = max(1, requested_months - len(done_rows))
    if done_rows:
        done_starts = [
            parsed.date()
            for parsed in (pd.to_datetime(row.get("period_start"), errors="coerce") for row in done_rows)
            if not pd.isna(parsed)
        ]
        if done_starts:
            latest_done_start = max(done_starts)
            min_next_month, _ = month_bounds(add_months(latest_done_start, 1))
            if start_month < min_next_month:
                start_month = min_next_month
    open_ids = [
        str(row.get("id")) for row in existing_installments
        if row.get("id") and str(row.get("status") or "").casefold() != "done"
    ]
    if open_ids:
        get_db().schema("settlement").table("courier_salary_advance_installment").delete().in_("id", open_ids).execute()

    new_amounts = salary_advance_installment_amounts(remaining_amount, remaining_months) if remaining_amount else []
    get_db().schema("settlement").table("courier_salary_advance_request").update({
        "installment_months": len(done_rows) + len(new_amounts),
        "monthly_amount_huf": new_amounts[0] if new_amounts else 0,
        "start_date": start_month.isoformat(),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", request_id).execute()
    insert_rows = []
    for index, amount in enumerate(new_amounts):
        period_start, period_end = month_bounds(add_months(start_month, index))
        insert_rows.append({
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "courier_id": courier_id,
            "courier_name": courier_name,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "installment_no": len(done_rows) + index + 1,
            "installment_count": len(done_rows) + len(new_amounts),
            "amount_huf": amount,
            "status": "open",
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        })
    if insert_rows:
        get_db().schema("settlement").table("courier_salary_advance_installment").insert(insert_rows).execute()

    get_db().schema("settlement").table("courier_salary_advance_plan").update({
        "installment_months": len(done_rows) + len(new_amounts),
        "monthly_amount_huf": new_amounts[0] if new_amounts else 0,
        "start_date": start_month.isoformat(),
        "status": "done" if not new_amounts else "open",
        "note": updated_note,
        "closed_at": pd.Timestamp.utcnow().isoformat() if not new_amounts else None,
        "closed_by": actor if not new_amounts else None,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", plan_id).execute()
    load_courier_salary_advance_requests.clear()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return f"Az ütemezés módosítva. Lezárt részletek: {len(done_rows)}, új nyitott részletek: {len(new_amounts)}."


def salary_advance_process_id(request_id: str, courier_id: str, start_date: date) -> str:
    short_id = re.sub(r"[^a-zA-Z0-9]+", "", str(request_id or ""))[:8].lower()
    return f"eloleg-{_courier_id_key(courier_id)}-{start_date:%Y%m}-{short_id or uuid.uuid4().hex[:8]}"


def approve_salary_advance_request(request_row: dict, courier_name: str) -> str:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    request_id = str(request_row.get("id") or "").strip()
    courier_id = str(request_row.get("courier_id") or "").strip()
    start_date = pd.to_datetime(request_row.get("start_date"), errors="coerce").date()
    process_id = salary_advance_process_id(request_id, courier_id, start_date)
    requested_amount = int(round(parse_huf_value(request_row.get("requested_amount_huf"))))
    months = int(round(parse_huf_value(request_row.get("installment_months"))))
    monthly_amount = int(round(parse_huf_value(request_row.get("monthly_amount_huf"))))
    document_month = start_date.replace(day=1)
    for action in ["settlement", "tig"]:
        upsert_peopleforce_card_status(
            courier_id=courier_id,
            courier_name=courier_name,
            action_key=process_action_key(action, process_id),
            document_month=document_month,
            status="done",
            status_note=(
                f"Fizetés előleg jóváhagyva, számlafeltöltésre vár. "
                f"Összeg: {format_huf(requested_amount)}; havi bontás: {months} hónap; "
                f"havi levonás: {format_huf(monthly_amount)}"
            ),
            updated_by=actor,
        )
    get_db().schema("settlement").table("courier_salary_advance_request").update({
        "status": "approved",
        "process_id": process_id,
        "approved_by": actor,
        "approved_at": pd.Timestamp.utcnow().isoformat(),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", request_id).execute()
    load_courier_salary_advance_requests.clear()
    return process_id


def mark_salary_advance_request_paid(request_row: dict, courier_name: str) -> str:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    request_id = str(request_row.get("id") or "").strip()
    courier_id = str(request_row.get("courier_id") or "").strip()
    start_date = pd.to_datetime(request_row.get("start_date"), errors="coerce").date()
    document_month = start_date.replace(day=1)
    plan_id = str(request_row.get("plan_id") or "").strip()
    if not plan_id:
        plan_id = create_salary_advance_plan(
            courier_id,
            courier_name,
            parse_huf_value(request_row.get("requested_amount_huf")),
            int(round(parse_huf_value(request_row.get("installment_months")))),
            start_date,
            str(request_row.get("note") or ""),
        )
    process_id = str(request_row.get("process_id") or "") or salary_advance_process_id(request_id, courier_id, start_date)
    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key=f"process:{process_id}:invoice_payment",
        document_month=document_month,
        status="done",
        status_note="Fizetés előleg kifizetve és lezárva.",
        updated_by=actor,
    )
    get_db().schema("settlement").table("courier_salary_advance_request").update({
        "status": "closed",
        "process_id": process_id,
        "plan_id": plan_id,
        "paid_by": actor,
        "paid_at": pd.Timestamp.utcnow().isoformat(),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", request_id).execute()
    load_courier_salary_advance_requests.clear()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return plan_id


def cancel_salary_advance_plan_for_request(request_row: dict, response_message: str = "") -> int:
    plan_id = str(request_row.get("plan_id") or "").strip()
    if not plan_id:
        return 0
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    response = str(response_message or "").strip()
    existing_note = str(request_row.get("note") or "").strip()
    updated_note = "\n\n".join(
        part for part in [
            existing_note,
            f"Visszavonva ({actor}): {response}" if response else f"Visszavonva: {actor}",
        ]
        if part
    )
    rows = (
        get_db().schema("settlement").table("courier_salary_advance_installment")
        .select("id")
        .eq("plan_id", plan_id)
        .execute().data or []
    )
    installment_ids = [str(row.get("id")) for row in rows if row.get("id")]
    if installment_ids:
        get_db().schema("settlement").table("courier_salary_advance_installment").update({
            "status": "cancelled",
            "closed_at": pd.Timestamp.utcnow().isoformat(),
            "closed_by": actor,
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        }).in_("id", installment_ids).execute()
    get_db().schema("settlement").table("courier_salary_advance_plan").update({
        "status": "cancelled",
        "note": updated_note,
        "closed_at": pd.Timestamp.utcnow().isoformat(),
        "closed_by": actor,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", plan_id).execute()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return len(installment_ids)


def reject_salary_advance_request(request_row: dict, courier_name: str, response_message: str) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    request_id = str(request_row.get("id") or "").strip()
    courier_id = str(request_row.get("courier_id") or "").strip()
    start_date = pd.to_datetime(request_row.get("start_date"), errors="coerce").date()
    document_month = start_date.replace(day=1)
    process_id = normalize_process_id(
        str(request_row.get("process_id") or "")
        or salary_advance_process_id(request_id, courier_id, start_date)
    )
    response = str(response_message or "").strip()
    existing_note = str(request_row.get("note") or "").strip()
    updated_note = "\n\n".join(
        part for part in [
            existing_note,
            f"Elutasítás válasz ({actor}): {response}" if response else f"Elutasítva: {actor}",
        ]
        if part
    )
    get_db().schema("settlement").table("courier_salary_advance_request").update({
        "status": "rejected",
        "process_id": process_id,
        "note": updated_note,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", request_id).execute()
    cancel_salary_advance_plan_for_request(request_row, response)
    if process_id:
        delete_peopleforce_process_statuses(courier_id, document_month, process_id)
    load_courier_salary_advance_requests.clear()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    read_peopleforce_card_statuses.clear()
    read_peopleforce_card_statuses_for_month.clear()


def close_salary_advance_installments(courier_id: str, period_start: date, period_end: date) -> int:
    current = load_courier_salary_advance_current(courier_id, period_start, period_end)
    if current.empty:
        return 0
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    installment_ids = current.get("id", pd.Series(dtype=str)).dropna().astype(str).tolist()
    plan_ids = current.get("plan_id", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
    if installment_ids:
        get_db().schema("settlement").table("courier_salary_advance_installment").update({
            "status": "done",
            "closed_at": pd.Timestamp.utcnow().isoformat(),
            "closed_by": actor,
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        }).in_("id", installment_ids).execute()
    for plan_id in plan_ids:
        open_rows = (
            get_db().schema("settlement").table("courier_salary_advance_installment")
            .select("id")
            .eq("plan_id", plan_id)
            .eq("status", "open")
            .limit(1)
            .execute().data or []
        )
        if not open_rows:
            get_db().schema("settlement").table("courier_salary_advance_plan").update({
                "status": "done",
                "closed_at": pd.Timestamp.utcnow().isoformat(),
                "closed_by": actor,
                "updated_at": pd.Timestamp.utcnow().isoformat(),
            }).eq("id", plan_id).execute()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return len(installment_ids)


def reopen_salary_advance_installments(courier_id: str, period_start: date, period_end: date) -> int:
    try:
        rows = (
            get_db().schema("settlement").table("courier_salary_advance_installment")
            .select("id,plan_id")
            .eq("courier_id", courier_id)
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .eq("status", "done")
            .execute().data or []
        )
    except BaseException:
        return 0
    if not rows:
        return 0
    installment_ids = [str(row.get("id")) for row in rows if row.get("id")]
    plan_ids = sorted({str(row.get("plan_id")) for row in rows if row.get("plan_id")})
    if installment_ids:
        get_db().schema("settlement").table("courier_salary_advance_installment").update({
            "status": "open",
            "closed_at": None,
            "closed_by": None,
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        }).in_("id", installment_ids).execute()
    for plan_id in plan_ids:
        get_db().schema("settlement").table("courier_salary_advance_plan").update({
            "status": "open",
            "closed_at": None,
            "closed_by": None,
            "updated_at": pd.Timestamp.utcnow().isoformat(),
        }).eq("id", plan_id).execute()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    return len(installment_ids)


def resolve_target_reserve_month(
    session_id: str | None,
    courier_id: str,
    period_start: date,
    period_end: date,
    reserve_status: dict[str, object],
    payable_before_insurance: float,
) -> dict[str, object]:
    calculation = calculate_target_reserve_month(reserve_status, payable_before_insurance, period_start)
    saved = load_target_reserve_monthly(courier_id, period_start, period_end)
    if saved.get("status") == "done":
        return {
            "payable_before_insurance_huf": parse_huf_value(saved.get("payable_before_insurance_huf")),
            "reserve_before_huf": parse_huf_value(saved.get("reserve_before_huf")),
            "reserve_addition_huf": parse_huf_value(saved.get("reserve_addition_huf")),
            "insurance_fee_huf": parse_huf_value(saved.get("insurance_fee_huf")),
            "reserve_after_huf": parse_huf_value(saved.get("reserve_after_huf")),
            "payable_after_insurance_huf": parse_huf_value(saved.get("payable_after_insurance_huf")),
            "insurance_active_before": bool(saved.get("insurance_active_before")),
            "insurance_active_after": bool(saved.get("insurance_active_after")),
            "status": "done",
        }
    return {**calculation, "status": "in_progress"}


@st.cache_data(show_spinner=False, ttl=60)
def load_profile_change_log(courier_id: str) -> pd.DataFrame:
    try:
        rows = (get_db().schema("settlement").table("courier_profile_change_log")
                .select("changed_fields,changed_by,created_at").eq("courier_id", courier_id)
                .order("created_at", desc=True).limit(100).execute().data or [])
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def log_profile_change(courier_id: str, changes: dict[str, dict[str, str]]) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    get_db().schema("settlement").table("courier_profile_change_log").insert({
        "courier_id": courier_id, "changed_fields": changes, "changed_by": actor,
    }).execute()
    load_profile_change_log.clear()


@st.cache_data(show_spinner=False, ttl=60)
def load_driver_dashboard(session_id: str | None = None, calculation_mode: str = "Excel") -> pd.DataFrame:
    query = (
        get_db()
        .schema("settlement")
        .table("vw_driver_dashboard")
        .select("*")
    )

    if session_id:
        query = query.eq("session_id", session_id)

    response = query.order("driver_name").execute()
    rows = response.data or []
    if not rows:
        return pd.DataFrame(columns=[
            "Courier ID", "Futár", "Raktár", "Branch", "Számítás módja",
            "Nettó bevétel", "Bónusz", "Borravaló", "Levonás",
            "Kifizetendő", "Előző havi összeg", "KPI", "Státusz",
        ])

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "courier_id": "Courier ID",
        "driver_name": "Futár",
        "warehouse_name": "Raktár",
        "company_name": "Vállalkozás",
        "tax_number": "Adószám",
        "vat_status": "ÁFA státusz",
        "fixed_rate_total": "Alap díj",
        "tip_total": "Borravaló",
        "extra_bonus_total": "Extra bónusz",
        "penalty_total": "Levonás",
        "atm_balance": "ATM Balance",
        "calculated_total": "Kifizetendő",
        "total_orders": "Rendelések",
        "total_routes": "Útvonalak",
        "work_days": "Munkanapok",
        "average_performance": "KPI",
    })

    for col in [
        "Alap díj", "Borravaló", "Extra bónusz", "Levonás",
        "ATM Balance", "Kifizetendő", "Rendelések", "Útvonalak",
        "Munkanapok", "KPI",
    ]:
        df[col] = _numeric_series(df, col)

    bonus_source_columns = [
        "delay_bonus_total",
        "compliance_bonus_total",
        "fuel_bonus_total",
        "car_fridge_bonus_total",
        "fill_rate_bonus_total",
        "branding_total",
    ]
    df["Bónusz"] = df["Extra bónusz"]
    for col in bonus_source_columns:
        df["Bónusz"] += _numeric_series(df, col)

    df["Levonás"] = df["Levonás"].abs()
    df["Nettó bevétel"] = (
        df["Alap díj"]
        + df["Borravaló"]
        + df["Bónusz"]
        + df["ATM Balance"]
    )

    df["Courier ID"] = df.get("Courier ID", pd.Series(index=df.index, dtype="object")).fillna("").astype(str)
    df["Futár"] = df.get("Futár", pd.Series(index=df.index, dtype="object")).fillna("Ismeretlen futár")
    if "Raktár" not in df.columns:
        df["Raktár"] = df.get("location", pd.Series("", index=df.index))
    else:
        df["Raktár"] = df["Raktár"].fillna(df.get("location", pd.Series("", index=df.index)))
    df["Raktár"] = df["Raktár"].fillna("")

    df["Branch"] = "JIT"
    df["Számítás módja"] = "API" if str(calculation_mode).casefold() == "api" else "Excel"
    df["Státusz"] = "Előkészítve"
    df["Előző havi összeg"] = 0.0

    return df


@st.cache_data(show_spinner=False, ttl=60)
def load_excel_courier_base_rates(session_id: str, parameter_revision: int = 0) -> pd.DataFrame:
    """Read persisted database-calculated courier base fees."""
    columns = [
        "Courier ID", "Futár", "Vállalkozói alapdíj", "Nettó bevétel", "Borravaló",
        "Rendszerbónusz", "Késedelmi díj", "Túramegfelelés",
        "Kiemelt túrák", "Normál túrák", "Számolt túrák", "Nem számolt túrák",
    ]
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("courier_settlement_summary")
            .select("*")
            .eq("session_id", session_id)
            .execute()
            .data
            or []
        )
    # Some deployed PostgREST versions expose APIError outside the regular
    # Exception hierarchy. This boundary must never make an Excel import fail.
    except BaseException:
        result = pd.DataFrame(columns=columns)
        try:
            rows = (
                get_db()
                .schema("settlement")
                .table("vw_parameterized_courier_settlement_summary")
                .select("*")
                .eq("session_id", session_id)
                .execute()
                .data
                or []
            )
        except BaseException:
            try:
                rows = (
                    get_db().schema("settlement").table("vw_parameterized_courier_base_summary")
                    .select("*").eq("session_id", session_id).execute().data or []
                )
            except BaseException:
                result = pd.DataFrame(columns=columns)
                result.attrs["configuration_error"] = (
                    "A settlement paramétertáblák még nem érhetők el. Futtasd le a teljes "
                    "settlement-paraméter és courier-settlement-summary migrációt."
                )
                return result
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows).rename(columns={
        "courier_id": "Courier ID",
        "driver_name": "Futár",
        "company_base_rate_huf": "Vállalkozói alapdíj",
        "courier_base_rate_huf": "Nettó bevétel",
        "tip_huf": "Borravaló",
        "route_bonus_huf": "Rendszerbónusz",
        "route_bonus_total_huf": "Rendszerbónusz",
        "delay_bonus_huf": "Késedelmi díj",
        "compliance_bonus_huf": "Túramegfelelés",
        "highlighted_routes": "Kiemelt túrák",
        "normal_routes": "Normál túrák",
        "calculated_routes": "Számolt túrák",
        "uncalculated_routes": "Nem számolt túrák",
    })
    if "Courier ID" not in result.columns:
        result["Courier ID"] = ""
    result["Courier ID"] = result["Courier ID"].fillna("").astype(str)
    for column in columns[2:]:
        result[column] = _numeric_series(result, column)
    return result[columns]


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_settlement_summary(session_id: str | None) -> pd.DataFrame:
    """Read the persisted, authoritative courier settlement rows for one Excel session."""
    if not session_id:
        return pd.DataFrame()
    try:
        rows = (
            get_db().schema("settlement").table("courier_settlement_summary")
            .select("*").eq("session_id", session_id).execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_settlement_summary_row(
    session_id: str | None,
    courier_id: str,
    courier_name: str,
    period_start: date | None = None,
) -> dict[str, object]:
    """Read one persisted settlement summary row; avoid loading the whole session in a profile."""
    if not session_id:
        return {}
    clean_courier_id = str(courier_id or "").strip()
    clean_courier_name = str(courier_name or "").strip()
    try:
        if clean_courier_id and period_start:
            try:
                rows = (
                    get_db().schema("settlement").table("vw_courier_month_profile_snapshot")
                    .select("*")
                    .eq("session_id", session_id)
                    .eq("courier_id", clean_courier_id)
                    .eq("period_month", period_start.replace(day=1).isoformat())
                    .limit(1)
                    .execute().data or []
                )
                if rows:
                    return rows[0]
            except BaseException:
                pass
        if clean_courier_id:
            rows = (
                get_db().schema("settlement").table("courier_settlement_summary")
                .select("*")
                .eq("session_id", session_id)
                .eq("courier_id", clean_courier_id)
                .limit(1)
                .execute().data or []
            )
            if rows:
                return rows[0]
        if clean_courier_name:
            rows = (
                get_db().schema("settlement").table("courier_settlement_summary")
                .select("*")
                .eq("session_id", session_id)
                .eq("driver_name", clean_courier_name)
                .limit(1)
                .execute().data or []
            )
            if rows:
                return rows[0]
    except BaseException:
        return {}
    return {}


@st.cache_data(show_spinner=False, ttl=60)
def load_excel_base_rate_diagnostics(session_id: str, parameter_revision: int = 0) -> pd.DataFrame:
    """Show DB-stored matching outcomes; no amount is calculated in the UI."""
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("route_unique_id,route_date,weekday_iso,calculated_day_type,base_rate_status,is_route_primary")
            .eq("session_id", session_id)
            .eq("is_route_primary", True)
            .execute()
            .data
            or []
        )
    except BaseException:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    data = pd.DataFrame(rows)
    data["Excel dátum"] = data["route_date"].fillna("-")
    data["Hét napja (DB)"] = data["weekday_iso"].map(
        {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
    ).fillna("Nincs dátum")
    data["Naptípus"] = data["calculated_day_type"].map(
        {"highlighted": "Kiemelt", "normal": "Normál"}
    ).fillna("Nincs besorolás")
    data["DB státusz"] = data["base_rate_status"].map(
        {
            "calculated": "Alapdíj kiszámolva",
            "missing_base_rate": "Nincs érvényes alapdíj-szabály",
            "missing_excel_date": "Hiányzó vagy nem olvasható Excel-dátum",
            "unsupported_unit": "Nem támogatott elszámolási egység",
            "duplicate_route_id": "Ismétlődő Route ID",
        }
    ).fillna(data["base_rate_status"].fillna("Ismeretlen"))
    return (
        data.groupby(["Excel dátum", "Hét napja (DB)", "Naptípus", "DB státusz"], dropna=False)
        .size()
        .reset_index(name="Route ID db")
        .sort_values(["Excel dátum", "Naptípus"])
    )


def apply_excel_base_rates(data: pd.DataFrame, session_id: str | None) -> pd.DataFrame:
    """Overlay the safe Excel base-fee calculation onto the main courier list."""
    parameter_revision = int(st.session_state.get("settlement_parameter_revision", 0))
    if not session_id:
        return data
    calculated = load_excel_courier_base_rates(session_id, parameter_revision)
    configuration_error = calculated.attrs.get("configuration_error")
    if configuration_error:
        st.warning(configuration_error)
        return data
    if calculated.empty:
        return data

    result = data.copy()
    result["_courier_id_lookup"] = result["Courier ID"].map(_courier_id_key)
    result["_courier_lookup"] = result["Futár"].map(_courier_match_key)
    calculated = calculated.copy()
    calculated["_courier_id_lookup"] = calculated["Courier ID"].map(_courier_id_key)
    calculated["_courier_lookup"] = calculated["Futár"].map(_courier_match_key)
    calculated_by_name = (
        calculated.groupby("_courier_lookup", as_index=False)[
            [
                "Nettó bevétel", "Vállalkozói alapdíj", "Borravaló",
                "Rendszerbónusz", "Késedelmi díj", "Túramegfelelés",
                "Számolt túrák", "Nem számolt túrák",
            ]
        ]
        .sum()
    )
    calculated_by_id = calculated[calculated["_courier_id_lookup"] != ""].groupby("_courier_id_lookup", as_index=False)[
        [
            "Nettó bevétel", "Vállalkozói alapdíj", "Borravaló",
            "Rendszerbónusz", "Késedelmi díj", "Túramegfelelés",
            "Számolt túrák", "Nem számolt túrák",
        ]
    ].sum()
    amount_by_id = calculated_by_id.set_index("_courier_id_lookup")["Nettó bevétel"] if not calculated_by_id.empty else pd.Series(dtype=float)
    company_amount_by_id = calculated_by_id.set_index("_courier_id_lookup")["Vállalkozói alapdíj"] if not calculated_by_id.empty else pd.Series(dtype=float)
    tip_by_id = calculated_by_id.set_index("_courier_id_lookup")["Borravaló"] if not calculated_by_id.empty else pd.Series(dtype=float)
    system_bonus_by_id = calculated_by_id.set_index("_courier_id_lookup")["Rendszerbónusz"] if not calculated_by_id.empty else pd.Series(dtype=float)
    delay_bonus_by_id = calculated_by_id.set_index("_courier_id_lookup")["Késedelmi díj"] if not calculated_by_id.empty else pd.Series(dtype=float)
    compliance_bonus_by_id = calculated_by_id.set_index("_courier_id_lookup")["Túramegfelelés"] if not calculated_by_id.empty else pd.Series(dtype=float)
    matched_routes_by_id = calculated_by_id.set_index("_courier_id_lookup")["Számolt túrák"] if not calculated_by_id.empty else pd.Series(dtype=float)
    unmatched_routes_by_id = calculated_by_id.set_index("_courier_id_lookup")["Nem számolt túrák"] if not calculated_by_id.empty else pd.Series(dtype=float)
    amount_by_courier = calculated_by_name.set_index("_courier_lookup")["Nettó bevétel"]
    company_amount_by_courier = calculated_by_name.set_index("_courier_lookup")["Vállalkozói alapdíj"]
    tip_by_courier = calculated_by_name.set_index("_courier_lookup")["Borravaló"]
    system_bonus_by_courier = calculated_by_name.set_index("_courier_lookup")["Rendszerbónusz"]
    delay_bonus_by_courier = calculated_by_name.set_index("_courier_lookup")["Késedelmi díj"]
    compliance_bonus_by_courier = calculated_by_name.set_index("_courier_lookup")["Túramegfelelés"]
    matched_routes = calculated_by_name.set_index("_courier_lookup")["Számolt túrák"]
    unmatched_routes = calculated_by_name.set_index("_courier_lookup")["Nem számolt túrák"]
    calculated_keys = set(amount_by_courier.index)
    resolved_lookup = result["_courier_lookup"].map(
        lambda key: _resolve_courier_lookup_key(key, calculated_keys)
    )
    result["Nettó bevétel"] = result["_courier_id_lookup"].map(amount_by_id).fillna(resolved_lookup.map(amount_by_courier)).fillna(0.0)
    result["Vállalkozói alapdíj"] = result["_courier_id_lookup"].map(company_amount_by_id).fillna(resolved_lookup.map(company_amount_by_courier)).fillna(0.0)
    result["Borravaló"] = result["_courier_id_lookup"].map(tip_by_id).fillna(resolved_lookup.map(tip_by_courier)).fillna(0.0)
    result["Bónusz"] = result["_courier_id_lookup"].map(system_bonus_by_id).fillna(resolved_lookup.map(system_bonus_by_courier)).fillna(0.0)
    result["Késedelmi díj"] = result["_courier_id_lookup"].map(delay_bonus_by_id).fillna(resolved_lookup.map(delay_bonus_by_courier)).fillna(0.0)
    result["Túramegfelelés"] = result["_courier_id_lookup"].map(compliance_bonus_by_id).fillna(resolved_lookup.map(compliance_bonus_by_courier)).fillna(0.0)
    result["Számolt túrák"] = result["_courier_id_lookup"].map(matched_routes_by_id).fillna(resolved_lookup.map(matched_routes)).fillna(0).astype(int)
    result["Nem számolt túrák"] = result["_courier_id_lookup"].map(unmatched_routes_by_id).fillna(resolved_lookup.map(unmatched_routes)).fillna(0).astype(int)
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + payable_bonus_total(result)
        + _numeric_series(result, "Korrekció")
        - _numeric_series(result, "Levonás")
    )
    return result.drop(columns=["_courier_id_lookup", "_courier_lookup"])


def _money_amount(value: object) -> float:
    if isinstance(value, dict):
        return parse_huf_value(value.get("amount"))
    return parse_huf_value(value)


def _api_route_fee(route: dict[str, object], *fee_types: str) -> float:
    wanted = {fee_type.casefold() for fee_type in fee_types}
    total = 0.0
    for item in route.get("ruleBreakdown") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("feeType") or "").casefold() in wanted:
            total += _money_amount(item.get("amount"))
    return total


def _api_route_courier_fee_from_rules(
    route: dict[str, object],
    raw_amount: object,
    rules: pd.DataFrame,
    route_date: object,
    day_type: object,
    route_type: object,
) -> float:
    raw_value = parse_huf_value(raw_amount)
    if raw_value == 0 or rules.empty:
        return raw_value

    try:
        work_date = date.fromisoformat(str(route_date)[:10])
    except ValueError:
        work_date = None

    route_type_key = _performance_key_from_label(route_type, "route")
    day_type_key = _performance_key_from_label(day_type, "day")
    orders = parse_huf_value(route.get("orderCount"))

    for _, rule in rules.sort_values("priority", kind="stable").iterrows():
        if str(rule.get("day_type") or "any").casefold() not in {"any", day_type_key}:
            continue
        if str(rule.get("route_type") or "any").casefold() not in {"any", route_type_key}:
            continue
        if work_date:
            try:
                valid_from = date.fromisoformat(str(rule.get("valid_from"))[:10])
                valid_to_value = rule.get("valid_to")
                valid_to = date.fromisoformat(str(valid_to_value)[:10]) if pd.notna(valid_to_value) else None
            except ValueError:
                continue
            if work_date < valid_from or (valid_to and work_date > valid_to):
                continue

        company_amount = parse_huf_value(rule.get("company_amount_huf"))
        courier_amount = parse_huf_value(rule.get("courier_amount_huf"))
        calculation_unit = str(rule.get("calculation_unit") or "per_route").casefold()
        expected_company_amount = company_amount
        if calculation_unit == "per_order":
            expected_company_amount = company_amount * orders

        if abs(expected_company_amount - raw_value) > 0.5 and abs(company_amount - raw_value) > 0.5:
            continue
        if calculation_unit == "per_order":
            return courier_amount * orders
        return courier_amount

    return raw_value

API_REVENUE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "Fix alap": ("fixed_base",),
    "Megfelelés": ("compliance",),
    "Kitöltési arány": ("fill_rate", "fill_rate_bonus"),
    "Üzemanyag-felár": ("fuel_surcharge", "fuel_bonus", "fuel"),
    "Hűtő mérete": ("car_fridge", "fridge", "car_fridge_bonus"),
    "Branding": ("branding", "branding_bonus"),
    "Késési teljesítmény (Dataport)": ("delay_performance", "dataport_delay_performance"),
}


def _api_route_revenue_components(route: dict[str, object]) -> dict[str, float]:
    return {
        component_name: _api_route_fee(route, *fee_types)
        for component_name, fee_types in API_REVENUE_COMPONENTS.items()
    }


def _api_payload_routes(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if not isinstance(payload, dict):
        return []
    return [route for route in payload.get("routes") or [] if isinstance(route, dict)]


def _api_revenue_master_lookup() -> dict[str, dict[str, object]]:
    master = load_courier_master("API")
    if master.empty:
        return {}
    return {
        _courier_id_key(row.get("Courier ID")): row
        for row in master.to_dict("records")
        if _courier_id_key(row.get("Courier ID"))
    }


@st.cache_data(show_spinner=False, ttl=300)
def load_api_financial_overview_rows(year: int, month: int) -> pd.DataFrame:
    target_tables = [
        "courier_financial_overview_raw_bud1",
        "courier_financial_overview_raw_bud2",
    ]
    frames = []
    for table_name in target_tables:
        try:
            rows = (
                get_db().schema("public").table(table_name)
                .select("courier_id,courier_name,warehouse_id,year,month,response_json,fetched_at")
                .eq("year", int(year))
                .eq("month", int(month))
                .eq("status_code", 200)
                .execute().data or []
            )
            if rows:
                frames.append(pd.DataFrame(rows))
        except BaseException:
            continue
    if frames:
        return pd.concat(frames, ignore_index=True)

    try:
        rows = (
            get_db().schema("public").table("courier_financial_overview_raw")
            .select("courier_id,courier_name,warehouse_id,year,month,response_json,fetched_at")
            .eq("year", int(year))
            .eq("month", int(month))
            .eq("status_code", 200)
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_api_financial_overview_rows_for_courier(year: int, month: int, courier_id: str) -> pd.DataFrame:
    courier_key = _courier_id_key(courier_id)
    if not courier_key:
        return pd.DataFrame()
    target_tables = [
        "courier_financial_overview_raw_bud1",
        "courier_financial_overview_raw_bud2",
    ]
    frames = []
    for table_name in target_tables:
        try:
            rows = (
                get_db().schema("public").table(table_name)
                .select("courier_id,courier_name,warehouse_id,year,month,response_json,fetched_at")
                .eq("year", int(year))
                .eq("month", int(month))
                .eq("status_code", 200)
                .eq("courier_id", courier_key)
                .execute().data or []
            )
            if rows:
                frames.append(pd.DataFrame(rows))
        except BaseException:
            continue
    if frames:
        return pd.concat(frames, ignore_index=True)

    try:
        rows = (
            get_db().schema("public").table("courier_financial_overview_raw")
            .select("courier_id,courier_name,warehouse_id,year,month,response_json,fetched_at")
            .eq("year", int(year))
            .eq("month", int(month))
            .eq("status_code", 200)
            .eq("courier_id", courier_key)
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def api_raw_overview_stats(period_start: date, warehouse_label: str | None) -> dict[str, int]:
    warehouse_id = settlement_warehouse_id(warehouse_label)
    rows = load_api_financial_overview_rows(period_start.year, period_start.month)
    if rows.empty:
        return {"couriers": 0, "routes": 0}
    if warehouse_id is not None and "warehouse_id" in rows.columns:
        rows = rows.loc[pd.to_numeric(rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id]
    route_count = 0
    for payload in rows.get("response_json", pd.Series(dtype=object)):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if isinstance(payload, dict):
            route_count += len(payload.get("routes") or [])
    return {"couriers": int(len(rows)), "routes": int(route_count)}


def api_raw_overview_breakdown(period_start: date) -> pd.DataFrame:
    rows = load_api_financial_overview_rows(period_start.year, period_start.month)
    if rows.empty:
        return pd.DataFrame(columns=["Raktár", "Futár", "Útvonal"])
    records = []
    for warehouse_id, group in rows.groupby("warehouse_id", dropna=False):
        route_count = 0
        for payload in group.get("response_json", pd.Series(dtype=object)):
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            if isinstance(payload, dict):
                route_count += len(payload.get("routes") or [])
        records.append({
            "Raktár": "BUD2" if int(warehouse_id or 0) == 2 else "BUD1",
            "Futár": int(len(group)),
            "Útvonal": int(route_count),
        })
    return pd.DataFrame(records).sort_values("Raktár")


@st.cache_data(show_spinner=False, ttl=30)
def load_api_import_diagnostics(session_id: str | None) -> dict[str, object]:
    if not session_id:
        return {"session_id": "", "jit_rows": 0, "summary_rows": 0, "calculated": 0, "missing_base_rate": 0}
    try:
        jit_rows = (
            get_db().schema("settlement").table("jit_row")
            .select("base_rate_status", count="exact")
            .eq("session_id", session_id)
            .execute()
        )
        summary_rows = (
            get_db().schema("settlement").table("courier_settlement_summary")
            .select("courier_id", count="exact")
            .eq("session_id", session_id)
            .execute()
        )
        statuses = pd.DataFrame(jit_rows.data or [])
        status_counts = statuses["base_rate_status"].value_counts().to_dict() if not statuses.empty and "base_rate_status" in statuses else {}
        return {
            "session_id": session_id,
            "jit_rows": int(jit_rows.count or 0),
            "summary_rows": int(summary_rows.count or 0),
            "calculated": int(status_counts.get("calculated", 0)),
            "missing_base_rate": int(status_counts.get("missing_base_rate", 0)),
        }
    except BaseException as exc:
        return {"session_id": session_id, "error": str(exc)}


def api_financial_routes_to_detail(
    rows: pd.DataFrame,
    courier_id: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> pd.DataFrame:
    columns = [
        "Route ID", "Excel dátum", "Hét napja", "Túratípus", "Naptípus",
        "Rendelések", "Alapdíj", "Kapott összeg", "Borravaló", "Késedelmi díj",
        "Túramegfelelés", "Bónuszok", "DB státusz",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    if period_start is None or period_end is None:
        period_start = period_start or date.today().replace(day=1)
        _, period_end = month_bounds(period_start)
    day_rules = load_jitt_day_definitions_for_period(period_start, period_end)
    delay_level_rules = load_active_bonus_level_rules("cfg_jitt_delay_bonus_rules")
    compliance_level_rules = load_active_bonus_level_rules("cfg_jitt_compliance_bonus_rules")
    target_id = _courier_id_key(courier_id)
    weekday_names = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
    parsed: list[dict[str, object]] = []
    for source in rows.to_dict("records"):
        if target_id and _courier_id_key(source.get("courier_id")) != target_id:
            continue
        payload = source.get("response_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            continue
        for route in payload.get("routes") or []:
            if not isinstance(route, dict):
                continue
            delivery_date = str(route.get("deliveryDate") or "")
            parsed_date = pd.to_datetime(delivery_date, errors="coerce")
            route_layer = str(route.get("routeLayer") or "NORMAL").strip().upper()
            route_type = {"NORMAL": "Normál", "EXPRESS": "Expressz", "REGIONAL": "Regionális"}.get(route_layer, route_layer.title())
            day_type = resolve_jitt_day_type_label(parsed_date, day_rules)
            delay_fee = _api_route_courier_fee_from_rules(
                route,
                _api_route_fee(route, "delay_performance", "dataport_delay_performance"),
                delay_level_rules,
                delivery_date,
                day_type,
                route_type,
            )
            compliance_fee = _api_route_courier_fee_from_rules(
                route,
                _api_route_fee(route, "compliance"),
                compliance_level_rules,
                delivery_date,
                day_type,
                route_type,
            )
            parsed.append({
                "_courier_id": _courier_id_key(source.get("courier_id")),
                "Route ID": str(route.get("routeId") or "–"),
                "Excel dátum": delivery_date or "–",
                "Hét napja": weekday_names.get(int(parsed_date.dayofweek) + 1, "–") if pd.notna(parsed_date) else "–",
                "Túratípus": route_type,
                "Naptípus": day_type,
                "Rendelések": parse_huf_value(route.get("orderCount")),
                "Alapdíj": _api_route_fee(route, "fixed_base"),
                "Kapott összeg": _money_amount(route.get("totalAmount")),
                "Borravaló": _money_amount(route.get("customerTipsTotal")),
                "Késedelmi díj": delay_fee,
                "Túramegfelelés": compliance_fee,
                "Bónuszok": delay_fee + compliance_fee,
                "DB státusz": "API nyers adat",
            })
    if not parsed:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(parsed).sort_values(["Excel dátum", "Route ID"])


@st.cache_data(show_spinner=False, ttl=300)
def load_api_received_amounts(period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    columns = ["Courier ID", "Alvállalkozói összeg"]
    summary = load_api_monthly_courier_revenue_summary(period_start, warehouse_label)
    if summary.empty:
        return pd.DataFrame(columns=columns)
    result = summary.rename(columns={"Nyers beérkezett összeg": "Alvállalkozói összeg"})
    return result.groupby("Courier ID", as_index=False)["Alvállalkozói összeg"].sum()


@st.cache_data(show_spinner=False, ttl=300)
def load_contractor_totals_for_session(session_id: str | None, period_start: date | None = None) -> pd.DataFrame:
    columns = ["Courier ID", "Futár", "Alvállalkozói összeg"]
    if not session_id:
        return pd.DataFrame(columns=columns)
    try:
        query = (
            get_db().schema("settlement").table("vw_courier_month_profile_snapshot")
            .select("courier_id,driver_name,contractor_total_huf,company_base_rate_huf,company_quality_bonus_total_huf,period_month")
            .eq("session_id", session_id)
        )
        if period_start:
            query = query.eq("period_month", period_start.replace(day=1).isoformat())
        rows = query.execute().data or []
    except BaseException:
        rows = []
    if not rows:
        try:
            rows = (
                get_db().schema("settlement").table("courier_settlement_summary")
                .select("courier_id,driver_name,contractor_total_huf,company_base_rate_huf,company_quality_bonus_total_huf")
                .eq("session_id", session_id)
                .execute().data or []
            )
        except BaseException:
            rows = []
    if not rows:
        return pd.DataFrame(columns=columns)
    data = pd.DataFrame(rows)
    contractor_total = (
        data.get("contractor_total_huf", pd.Series(0.0, index=data.index)).map(parse_huf_value)
        if "contractor_total_huf" in data else pd.Series(0.0, index=data.index)
    )
    fallback_total = (
        data.get("company_base_rate_huf", pd.Series(0.0, index=data.index)).map(parse_huf_value)
        + data.get("company_quality_bonus_total_huf", pd.Series(0.0, index=data.index)).map(parse_huf_value)
    )
    return pd.DataFrame({
        "Courier ID": data.get("courier_id", pd.Series("", index=data.index)).astype(str),
        "Futár": data.get("driver_name", pd.Series("", index=data.index)).astype(str),
        "Alvállalkozói összeg": contractor_total.where(contractor_total.ne(0), fallback_total),
    })


@st.cache_data(show_spinner=False, ttl=300)
def load_api_monthly_revenue_detail(period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    component_columns = list(API_REVENUE_COMPONENTS.keys())
    columns = [
        "Hónap", "Raktár", "Courier ID", "Futár", "Vállalkozás", "Route ID",
        "Dátum", "Túratípus", "Rendelések", "Nyers beérkezett összeg",
        "Borravaló", "Komponensek összesen", *component_columns,
    ]
    rows = load_api_financial_overview_rows(period_start.year, period_start.month)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    warehouse_id = settlement_warehouse_id(warehouse_label)
    if warehouse_id is not None and "warehouse_id" in rows.columns:
        rows = rows.loc[
            pd.to_numeric(rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id
        ]
    master_lookup = _api_revenue_master_lookup()
    records: list[dict[str, object]] = []
    for source in rows.to_dict("records"):
        courier_id = str(source.get("courier_id") or "")
        courier_key = _courier_id_key(courier_id)
        master_row = master_lookup.get(courier_key, {})
        warehouse_code = "BUD2" if int(source.get("warehouse_id") or 0) == 2 else "BUD1"
        for route in _api_payload_routes(source.get("response_json") or {}):
            components = _api_route_revenue_components(route)
            delivery_date = str(route.get("deliveryDate") or "")
            route_layer = str(route.get("routeLayer") or "NORMAL").strip().upper()
            route_type = {"NORMAL": "Normál", "EXPRESS": "Expressz", "REGIONAL": "Regionális"}.get(route_layer, route_layer.title())
            records.append({
                "Hónap": period_start.replace(day=1),
                "Raktár": warehouse_code,
                "Courier ID": courier_id,
                "Futár": str(source.get("courier_name") or master_row.get("Futár") or "Ismeretlen futár"),
                "Vállalkozás": str(master_row.get("Vállalkozás") or ""),
                "Route ID": str(route.get("routeId") or "–"),
                "Dátum": delivery_date,
                "Túratípus": route_type,
                "Rendelések": parse_huf_value(route.get("orderCount")),
                "Nyers beérkezett összeg": _money_amount(route.get("totalAmount")),
                "Borravaló": _money_amount(route.get("customerTipsTotal")),
                "Komponensek összesen": sum(components.values()),
                **components,
            })
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records)
    for column in ["Rendelések", "Nyers beérkezett összeg", "Borravaló", "Komponensek összesen", *component_columns]:
        result[column] = _numeric_series(result, column)
    return result[columns].sort_values(["Raktár", "Futár", "Dátum", "Route ID"])


@st.cache_data(show_spinner=False, ttl=300)
def load_api_monthly_courier_payload_totals(period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    columns = ["Hónap", "Raktár", "Courier ID", "Futár", "Vállalkozás", "Nyers beérkezett összeg"]
    rows = load_api_financial_overview_rows(period_start.year, period_start.month)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    warehouse_id = settlement_warehouse_id(warehouse_label)
    if warehouse_id is not None and "warehouse_id" in rows.columns:
        rows = rows.loc[
            pd.to_numeric(rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id
        ]
    master_lookup = _api_revenue_master_lookup()
    records: list[dict[str, object]] = []
    for source in rows.to_dict("records"):
        courier_id = str(source.get("courier_id") or "")
        courier_key = _courier_id_key(courier_id)
        master_row = master_lookup.get(courier_key, {})
        payload = source.get("response_json") or {}
        payload_total = 0.0
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if isinstance(payload, dict):
            payload_total = _money_amount(payload.get("totalCost"))
            if not payload_total:
                payload_total = sum(_money_amount(route.get("totalAmount")) for route in _api_payload_routes(payload))
        records.append({
            "Hónap": period_start.replace(day=1),
            "Raktár": "BUD2" if int(source.get("warehouse_id") or 0) == 2 else "BUD1",
            "Courier ID": courier_id,
            "Futár": str(source.get("courier_name") or master_row.get("Futár") or "Ismeretlen futár"),
            "Vállalkozás": str(master_row.get("Vállalkozás") or ""),
            "Nyers beérkezett összeg": payload_total,
        })
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records)
    result["Nyers beérkezett összeg"] = _numeric_series(result, "Nyers beérkezett összeg")
    return (
        result.groupby(["Hónap", "Raktár", "Courier ID", "Futár", "Vállalkozás"], dropna=False)["Nyers beérkezett összeg"]
        .sum()
        .reset_index()
        .sort_values(["Raktár", "Futár"])
    )


@st.cache_data(show_spinner=False, ttl=300)
def load_api_monthly_courier_revenue_summary(period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    component_columns = list(API_REVENUE_COMPONENTS.keys())
    columns = [
        "Hónap", "Raktár", "Courier ID", "Futár", "Vállalkozás", "Útvonalak",
        "Rendelések", "Nyers beérkezett összeg", "Borravaló",
        "Komponensek összesen", *component_columns,
    ]
    rows = load_api_financial_overview_rows(period_start.year, period_start.month)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    warehouse_id = settlement_warehouse_id(warehouse_label)
    if warehouse_id is not None and "warehouse_id" in rows.columns:
        rows = rows.loc[
            pd.to_numeric(rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id
        ]
    master_lookup = _api_revenue_master_lookup()
    records: list[dict[str, object]] = []
    for source in rows.to_dict("records"):
        courier_id = str(source.get("courier_id") or "")
        courier_key = _courier_id_key(courier_id)
        master_row = master_lookup.get(courier_key, {})
        payload = source.get("response_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        routes = _api_payload_routes(payload)
        components_total = {column: 0.0 for column in component_columns}
        raw_total = _money_amount(payload.get("totalCost")) if isinstance(payload, dict) else 0.0
        orders_total = 0.0
        tip_total = 0.0
        if not raw_total:
            raw_total = sum(_money_amount(route.get("totalAmount")) for route in routes)
        for route in routes:
            orders_total += parse_huf_value(route.get("orderCount"))
            tip_total += _money_amount(route.get("customerTipsTotal"))
            components = _api_route_revenue_components(route)
            for component_name, amount in components.items():
                components_total[component_name] = components_total.get(component_name, 0.0) + amount
        records.append({
            "Hónap": period_start.replace(day=1),
            "Raktár": "BUD2" if int(source.get("warehouse_id") or 0) == 2 else "BUD1",
            "Courier ID": courier_id,
            "Futár": str(source.get("courier_name") or master_row.get("Futár") or "Ismeretlen futár"),
            "Vállalkozás": str(master_row.get("Vállalkozás") or ""),
            "Útvonalak": len(routes),
            "Rendelések": orders_total,
            "Nyers beérkezett összeg": raw_total,
            "Borravaló": tip_total,
            "Komponensek összesen": sum(components_total.values()),
            **components_total,
        })
    if not records:
        return pd.DataFrame(columns=columns)
    summary = pd.DataFrame(records)
    value_columns = ["Útvonalak", "Rendelések", "Nyers beérkezett összeg", "Borravaló", "Komponensek összesen", *component_columns]
    for column in value_columns:
        summary[column] = _numeric_series(summary, column)
    summary = (
        summary.groupby(["Hónap", "Raktár", "Courier ID", "Futár", "Vállalkozás"], dropna=False)[value_columns]
        .sum()
        .reset_index()
    )
    return summary[columns].sort_values(["Raktár", "Futár"])


@st.cache_data(show_spinner=False, ttl=300)
def load_api_monthly_subcontractor_revenue_summary(period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    courier_summary = load_api_monthly_courier_revenue_summary(period_start, warehouse_label)
    component_columns = list(API_REVENUE_COMPONENTS.keys())
    columns = [
        "Hónap", "Vállalkozás", "Futárok", "Útvonalak", "Rendelések",
        "Nyers beérkezett összeg", "Borravaló", "Komponensek összesen",
        *component_columns,
    ]
    if courier_summary.empty:
        return pd.DataFrame(columns=columns)
    summary_source = courier_summary.copy()
    summary_source["Vállalkozás"] = summary_source["Vállalkozás"].replace("", "Nincs vállalkozás megadva")
    summary = (
        summary_source.groupby(["Hónap", "Vállalkozás"], dropna=False)
        .agg(
            Futárok=("Courier ID", "nunique"),
            Útvonalak=("Útvonalak", "sum"),
            Rendelések=("Rendelések", "sum"),
            **{
                column: (column, "sum")
                for column in ["Nyers beérkezett összeg", "Borravaló", "Komponensek összesen", *component_columns]
            },
        )
        .reset_index()
    )
    return summary[columns].sort_values("Vállalkozás")


def api_monthly_growth(current: pd.DataFrame, previous: pd.DataFrame, key_columns: list[str]) -> pd.DataFrame:
    value_columns = [
        "Nyers beérkezett összeg", "Borravaló", "Komponensek összesen",
        *API_REVENUE_COMPONENTS.keys(),
    ]
    current_values = current[key_columns + [column for column in value_columns if column in current.columns]].copy()
    previous_values = previous[key_columns + [column for column in value_columns if column in previous.columns]].copy()
    merged = current_values.merge(previous_values, on=key_columns, how="outer", suffixes=("", " előző hónap")).fillna(0)
    for column in value_columns:
        if column in merged.columns and f"{column} előző hónap" in merged.columns:
            merged[f"{column} növekedés"] = merged[column] - merged[f"{column} előző hónap"]
    return merged


def api_monthly_profit_projection(courier_summary: pd.DataFrame, settlement_data: pd.DataFrame) -> pd.DataFrame:
    if courier_summary.empty:
        return courier_summary.copy()
    result = courier_summary.copy()
    payouts = settlement_data.copy() if isinstance(settlement_data, pd.DataFrame) else pd.DataFrame()
    if payouts.empty:
        result["Kifizetendő"] = 0.0
    else:
        payouts["_courier_id_lookup"] = payouts["Courier ID"].map(_courier_id_key)
        payout_by_id = payouts.set_index("_courier_id_lookup")["Kifizetendő"]
        result["_courier_id_lookup"] = result["Courier ID"].map(_courier_id_key)
        result["Kifizetendő"] = result["_courier_id_lookup"].map(payout_by_id).fillna(0.0)
        result = result.drop(columns=["_courier_id_lookup"])
    result["Nyereség"] = _numeric_series(result, "Nyers beérkezett összeg") - _numeric_series(result, "Kifizetendő")
    return result


def apply_received_amounts(
    data: pd.DataFrame,
    calculation_mode: str,
    period_start: date,
    warehouse_label: str | None = None,
    session_id: str | None = None,
) -> pd.DataFrame:
    result = data.copy()
    normalized_mode = str(calculation_mode or "API").strip().casefold()
    result["Alvállalkozói összeg"] = _numeric_series(result, "Vállalkozói alapdíj")
    contractor_totals = load_contractor_totals_for_session(session_id, period_start)
    if not contractor_totals.empty:
        result["_courier_id_lookup"] = result["Courier ID"].map(_courier_id_key)
        result["_courier_name_lookup"] = result["Futár"].map(_courier_match_key)
        contractor_totals["_courier_id_lookup"] = contractor_totals["Courier ID"].map(_courier_id_key)
        contractor_totals["_courier_name_lookup"] = contractor_totals["Futár"].map(_courier_match_key)
        by_id = contractor_totals.loc[
            contractor_totals["_courier_id_lookup"].ne("")
        ].groupby("_courier_id_lookup")["Alvállalkozói összeg"].sum()
        by_name = contractor_totals.loc[
            contractor_totals["_courier_name_lookup"].ne("")
        ].groupby("_courier_name_lookup")["Alvállalkozói összeg"].sum()
        contractor_amounts = result["_courier_id_lookup"].map(by_id).fillna(result["_courier_name_lookup"].map(by_name))
        current_amounts = _numeric_series(result, "Alvállalkozói összeg")
        if normalized_mode == "excel":
            result["Alvállalkozói összeg"] = contractor_amounts.where(
                contractor_amounts.fillna(0.0).ne(0.0),
                current_amounts,
            ).fillna(current_amounts)
        else:
            result["Alvállalkozói összeg"] = contractor_amounts.fillna(current_amounts)
        result = result.drop(columns=["_courier_id_lookup", "_courier_name_lookup"])
    if normalized_mode != "api":
        return result
    received = load_api_received_amounts(period_start, warehouse_label)
    if received.empty:
        return result
    result["_courier_id_lookup"] = result["Courier ID"].map(_courier_id_key)
    received["_courier_id_lookup"] = received["Courier ID"].map(_courier_id_key)
    amount_by_id = received.set_index("_courier_id_lookup")["Alvállalkozói összeg"]
    api_amounts = result["_courier_id_lookup"].map(amount_by_id)
    current_amounts = _numeric_series(result, "Alvállalkozói összeg")
    result["Alvállalkozói összeg"] = api_amounts.where(api_amounts.fillna(0).ne(0), current_amounts)
    return result.drop(columns=["_courier_id_lookup"])


def apply_api_base_rates(
    data: pd.DataFrame,
    period_start: date,
    warehouse_label: str | None = None,
    session_id: str | None = None,
) -> pd.DataFrame:
    """API mode must keep the same output contract as the Excel pipeline."""
    result = data.copy()
    result["Számítás módja"] = "API"
    api_session_id = session_id or load_latest_api_jit_session_id(period_start, warehouse_label)
    if not api_session_id:
        return result
    return apply_excel_base_rates(result, api_session_id)


def build_settlement_working_data(calculation_mode: str, session_id: str | None, period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    """Build the main settlement table without changing its shape per source."""
    normalized_mode = str(calculation_mode or "API").strip().casefold()
    if normalized_mode == "excel":
        data = load_courier_master("Excel")
        return apply_excel_base_rates(data, session_id)
    return apply_api_base_rates(load_courier_master("API"), period_start, warehouse_label, session_id)


def payable_bonus_total(data: pd.DataFrame) -> pd.Series:
    itemized_columns = [
        "Késedelmi díj",
        "Túramegfelelés",
        "Importált bónusz",
        "JITT bónusz",
        "Lojalitás",
        "Ügyfélértékelés",
    ]
    available_columns = [column for column in itemized_columns if column in data.columns]
    if not available_columns:
        return _numeric_series(data, "Bónusz")
    total = pd.Series(0.0, index=data.index, dtype="float64")
    for column in available_columns:
        total = total + _numeric_series(data, column)
    return total


def recompute_payable_total(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + payable_bonus_total(result)
        + _numeric_series(result, "Korrekció")
        - _numeric_series(result, "Levonás")
    )
    return result


@st.cache_data(show_spinner=False, ttl=60)
def load_loyalty_bonus_rules_for_month(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("cfg_jitt_loyalty_bonus_rules")
            .select("*")
            .eq("is_active", True)
            .is_("deleted_at", "null")
            .lte("valid_from", period_end.isoformat())
            .order("priority")
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame()
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    valid_to = pd.to_datetime(data.get("valid_to"), errors="coerce")
    return data.loc[valid_to.isna() | (valid_to >= pd.Timestamp(period_start))].copy()


def completed_months_between(start_value: object, as_of: date) -> int:
    start = pd.to_datetime(start_value, errors="coerce")
    if pd.isna(start):
        return -1
    start_date = start.date()
    months = (as_of.year - start_date.year) * 12 + (as_of.month - start_date.month)
    if as_of.day < start_date.day:
        months -= 1
    return max(months, 0)


@st.cache_data(show_spinner=False, ttl=60)
def load_loyalty_route_counts(session_id: str | None) -> pd.DataFrame:
    if not session_id:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    try:
        rows = (
            get_db().schema("settlement").table("jit_row")
            .select("normalized_data,is_route_primary")
            .eq("session_id", session_id)
            .eq("is_route_primary", True)
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    records: list[dict[str, object]] = []
    for row in rows:
        payload = row.get("normalized_data") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        driver_name = payload.get("Driver") or payload.get("driver_name") or payload.get("Futár") or payload.get("courier_name") or ""
        route_type = payload.get("Route Type") or payload.get("route_type") or payload.get("Túratípus") or payload.get("Tipus") or "normal"
        orders = next(
            (payload.get(key) for key in ["Orders", "orders", "Rendelések", "order_count"] if payload.get(key) not in (None, "")),
            0,
        )
        records.append({
            "driver_key": _courier_match_key(driver_name),
            "route_type": normalize_customer_rating_route_type(route_type),
            "routes": 1,
            "orders": parse_huf_value(orders),
        })
    if not records:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    return pd.DataFrame(records).groupby(["driver_key", "route_type"], as_index=False)[["routes", "orders"]].sum()


def _loyalty_route_counts_from_settlement_rows(data: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for _, row in data.iterrows():
        driver_key = _courier_match_key(row.get("Futár"))
        if not driver_key:
            continue
        total_routes = int(parse_huf_value(row.get("Számolt túrák") or row.get("Útvonalak") or row.get("Kör")))
        normal_routes = int(parse_huf_value(row.get("Normál túrák") or row.get("Normál túra") or row.get("Normál kör")))
        highlighted_routes = int(parse_huf_value(row.get("Kiemelt túrák") or row.get("Kiemelt túra") or row.get("Kiemelt kör")))
        express_normal = int(parse_huf_value(row.get("Express normál")))
        express_highlighted = int(parse_huf_value(row.get("Express kiemelt")))
        normal_total = normal_routes + highlighted_routes
        express_total = express_normal + express_highlighted
        if total_routes > 0 and normal_total + express_total == 0:
            normal_total = total_routes
        elif total_routes > normal_total + express_total:
            normal_total += total_routes - normal_total - express_total
        orders = int(parse_huf_value(row.get("Cím") or row.get("Rendelés") or row.get("Cím / rendelés")))
        if normal_total > 0:
            records.append({
                "driver_key": driver_key,
                "route_type": "normal",
                "routes": normal_total,
                "orders": orders,
            })
        if express_total > 0:
            records.append({
                "driver_key": driver_key,
                "route_type": "express",
                "routes": express_total,
                "orders": 0,
            })
    if not records:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    return pd.DataFrame(records).groupby(["driver_key", "route_type"], as_index=False)[["routes", "orders"]].sum()


def _loyalty_count_record(payload: object) -> dict[str, object] | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    driver_name = payload.get("Driver") or payload.get("driver_name") or payload.get("Futár") or payload.get("courier_name") or ""
    if not str(driver_name or "").strip():
        return None
    route_type = payload.get("Route Type") or payload.get("route_type") or payload.get("Túratípus") or payload.get("Tipus") or "normal"
    orders = next(
        (payload.get(key) for key in ["Orders", "orders", "Rendelések", "order_count"] if payload.get(key) not in (None, "")),
        0,
    )
    return {
        "driver_key": _courier_match_key(driver_name),
        "route_type": normalize_customer_rating_route_type(route_type),
        "routes": 1,
        "orders": parse_huf_value(orders),
    }


@st.cache_data(show_spinner=False, ttl=300)
def load_loyalty_route_counts_for_period(period_start: date, period_end: date, source_mode: str = "") -> pd.DataFrame:
    try:
        rows = (
            get_db().schema("settlement").table("jit_row")
            .select("normalized_data,is_route_primary,route_date,source_sheet")
            .eq("is_route_primary", True)
            .gte("route_date", period_start.isoformat())
            .lte("route_date", period_end.isoformat())
            .limit(50000)
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    records = []
    source_key = str(source_mode or "").strip().casefold()
    for row in rows:
        source_sheet = str(row.get("source_sheet") or "").strip().casefold()
        is_api_source = source_sheet.startswith("api financial overview")
        if source_key == "api" and not is_api_source:
            continue
        if source_key == "excel" and is_api_source:
            continue
        record = _loyalty_count_record(row.get("normalized_data"))
        if record:
            records.append(record)
    if not records:
        return pd.DataFrame(columns=["driver_key", "route_type", "routes", "orders"])
    return pd.DataFrame(records).groupby(["driver_key", "route_type"], as_index=False)[["routes", "orders"]].sum()


@st.cache_data(show_spinner=False, ttl=300)
def load_loyalty_advance_booking_days(period_start: date, period_end: date) -> pd.DataFrame:
    previous_month_end = period_start - timedelta(days=1)
    try:
        rows = (
            get_db().schema("settlement").table("courier_loyalty_booking_log")
            .select("courier_id,courier_name,user_email,operation,booked_at,shift_date,shift_time,warehouse,raw_shift_data,source_key")
            .gte("shift_date", period_start.isoformat())
            .lte("shift_date", period_end.isoformat())
            .limit(50000)
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame(columns=["driver_key", "advance_booking_days"])
    changed_keys = {
        _loyalty_booking_shift_key(row, include_driver=True)
        for row in rows
        if _is_booking_change_operation(row.get("operation"))
    }
    records = []
    for row in rows:
        shift_key = _loyalty_booking_shift_key(row, include_driver=True)
        if not all(shift_key[:3]) or shift_key in changed_keys:
            continue
        if not _is_clean_booking_operation(row.get("operation")):
            continue
        if not _booked_by_period_cutoff(row.get("booked_at"), previous_month_end):
            continue
        identity = _loyalty_booking_effective_identity(row)
        driver_key = _courier_match_key(
            identity.get("courier_name") or identity.get("user_email") or identity.get("courier_id")
        )
        if driver_key:
            records.append({"driver_key": driver_key, "shift_key": "|".join(shift_key)})
    if not records:
        return pd.DataFrame(columns=["driver_key", "advance_booking_days"])
    return (
        pd.DataFrame(records)
        .drop_duplicates(["driver_key", "shift_key"])
        .groupby("driver_key", as_index=False)["shift_key"]
        .nunique()
        .rename(columns={"shift_key": "advance_booking_days"})
    )


@st.cache_data(show_spinner=False, ttl=900)
def load_loyalty_profile_lookup() -> dict[str, dict[str, object]]:
    try:
        from resources.loyalty_bonus import read_loyalty_profiles

        profiles = read_loyalty_profiles()
    except BaseException:
        return {}
    if profiles.empty:
        return {}
    lookup: dict[str, dict[str, object]] = {}
    for _, profile in profiles.iterrows():
        driver_key = _courier_match_key(profile.get("driver_name"))
        if driver_key:
            lookup[driver_key] = profile.to_dict()
    return lookup


def resolve_loyalty_work_start(profile: dict[str, object], courier_name: str) -> tuple[object, str, dict[str, object]]:
    db_value = profile.get("work_start_date")
    db_start = pd.to_datetime(db_value, errors="coerce")
    if pd.notna(db_start):
        return db_start.date(), "DB profil", {}
    sheet_profile = load_loyalty_profile_lookup().get(_courier_match_key(courier_name), {})
    sheet_start = pd.to_datetime(sheet_profile.get("start_date"), errors="coerce")
    if pd.notna(sheet_start):
        return sheet_start.date(), "Lojalitási Google Sheet", sheet_profile
    return None, "Nincs adat", sheet_profile


def _loyalty_rule_bool(rule: pd.Series, column: str, default: bool) -> bool:
    if column not in rule or pd.isna(rule.get(column)):
        return default
    value = rule.get(column)
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "t", "yes", "y", "igen"}
    return bool(value)


def apply_loyalty_bonus(data: pd.DataFrame, period_start: date, period_end: date, session_id: str | None, source_mode: str = "") -> pd.DataFrame:
    result = data.copy()
    rules = load_loyalty_bonus_rules_for_month(period_start, period_end)
    current_counts = load_loyalty_route_counts(session_id)
    if current_counts.empty:
        current_counts = _loyalty_route_counts_from_settlement_rows(result)
    previous_month_end = period_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    previous_counts = load_loyalty_route_counts_for_period(previous_month_start, previous_month_end, source_mode)
    booking_days = load_loyalty_advance_booking_days(period_start, period_end)
    profile_lookup = load_loyalty_profile_lookup()
    db_profile_by_id = load_courier_profile_lookup()

    for column, default in [
        ("Lojalitás", 0.0),
        ("Lojalitás előző havi normál kör", 0),
        ("Lojalitás aktuális normál kör", 0),
        ("Lojalitás Ft/kör", 0.0),
        ("Lojalitás előre foglalt nap", 0),
        ("Lojalitás státusz", ""),
    ]:
        if column not in result.columns:
            result[column] = default

    if rules.empty or current_counts.empty:
        if "Lojalitás" not in result.columns:
            result["Lojalitás"] = 0.0
        return result

    current_by_driver = {
        driver_key: group.copy()
        for driver_key, group in current_counts.groupby("driver_key")
    }
    previous_normal = (
        previous_counts.loc[previous_counts["route_type"] == "normal"]
        .groupby("driver_key")["routes"]
        .sum()
        .to_dict()
        if not previous_counts.empty
        else {}
    )
    booking_by_driver = dict(zip(booking_days.get("driver_key", []), booking_days.get("advance_booking_days", [])))
    rules = rules.copy()
    if "previous_normal_routes_min" not in rules.columns:
        rules["previous_normal_routes_min"] = 0
    rules["previous_normal_routes_min"] = pd.to_numeric(rules["previous_normal_routes_min"], errors="coerce").fillna(0).astype(int)
    rules = rules.sort_values(["previous_normal_routes_min", "priority"], ascending=[False, True], kind="stable")

    loyalty_amounts: list[float] = []
    previous_route_values: list[int] = []
    current_route_values: list[int] = []
    rate_values: list[float] = []
    booking_day_values: list[int] = []
    status_values: list[str] = []

    for _, row in result.iterrows():
        driver_key = _courier_match_key(row.get("Futár"))
        profile = profile_lookup.get(driver_key, {})
        courier_id = str(row.get("Courier ID") or "").strip()
        db_profile = db_profile_by_id.get(_courier_id_key(courier_id), {}) if courier_id else {}
        if db_profile:
            profile = {**profile, **db_profile}
        if profile.get("work_start_date"):
            profile["start_date"] = profile.get("work_start_date")
        start_value = row.get("Munkakezdés") or profile.get("start_date")
        months_worked = completed_months_between(start_value, period_start)
        driver_counts = current_by_driver.get(driver_key)
        settlement_route_count = int(parse_huf_value(row.get("Számolt túrák") or row.get("Útvonalak") or row.get("Kör")))
        settlement_order_count = int(parse_huf_value(row.get("Cím") or row.get("Rendelés") or row.get("Cím / rendelés")))
        source_route_count = int(float(driver_counts["routes"].sum())) if driver_counts is not None and not driver_counts.empty else 0
        source_order_count = int(float(driver_counts["orders"].sum())) if driver_counts is not None and not driver_counts.empty else 0
        current_route_count = max(source_route_count, settlement_route_count)
        current_order_count = max(source_order_count, settlement_order_count)
        previous_normal_routes = int(float(previous_normal.get(driver_key, 0) or 0))
        advance_booking_days = int(float(booking_by_driver.get(driver_key, 0) or 0))
        previous_route_values.append(previous_normal_routes)
        current_route_values.append(current_route_count)
        booking_day_values.append(advance_booking_days)

        if months_worked < 0:
            loyalty_amounts.append(0.0)
            rate_values.append(0.0)
            status_values.append("Hiányzik: munkakezdés")
            continue
        if current_route_count <= 0 and current_order_count <= 0:
            loyalty_amounts.append(0.0)
            rate_values.append(0.0)
            status_values.append("Nincs aktuális kör")
            continue

        selected_rule = None
        selected_missing: list[str] = []
        for _, rule in rules.iterrows():
            missing: list[str] = []
            configured_required_months = int(parse_huf_value(rule.get("loyalty_months_required")))
            required_months = configured_required_months if configured_required_months > 0 else DEFAULT_LOYALTY_MONTHS_REQUIRED
            if months_worked < required_months:
                missing.append(f"{required_months}. hónap")
            booked_shift_min = int(parse_huf_value(rule.get("previous_normal_routes_min")))
            if advance_booking_days < booked_shift_min:
                missing.append(f"előre foglalt műszak < {booked_shift_min}")
            if _loyalty_rule_bool(rule, "require_active_relationship", True):
                is_active = bool(profile.get("is_active", True))
                is_notice_period = bool(profile.get("is_notice_period", False))
                if not is_active or is_notice_period:
                    missing.append("aktív jogviszony")
            if _loyalty_rule_bool(rule, "require_advance_booking", True) and advance_booking_days <= 0:
                missing.append("előfoglalás")
            if not missing:
                selected_rule = rule
                selected_missing = []
                break
            if not selected_missing:
                selected_missing = missing

        if selected_rule is None:
            loyalty_amounts.append(0.0)
            rate_values.append(0.0)
            status_values.append("Hiányzik: " + ", ".join(selected_missing or ["feltétel"]))
            continue

        unit = str(selected_rule.get("calculation_unit") or "per_route")
        amount = parse_huf_value(selected_rule.get("bonus_amount_huf"))
        quantity = float(current_order_count if unit == "per_order" else current_route_count)
        total = quantity * amount
        loyalty_amounts.append(total)
        rate_values.append(amount)
        status_values.append("Jogosult")

    loyalty_bonus = pd.Series(loyalty_amounts, index=result.index)
    result["Lojalitás"] = loyalty_bonus
    result["Lojalitás előző havi normál kör"] = previous_route_values
    result["Lojalitás aktuális normál kör"] = current_route_values
    result["Lojalitás Ft/kör"] = rate_values
    result["Lojalitás előre foglalt nap"] = booking_day_values
    result["Lojalitás státusz"] = status_values
    result["Bónusz"] = _numeric_series(result, "Bónusz") + loyalty_bonus
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + payable_bonus_total(result)
        - _numeric_series(result, "Levonás")
    )
    return result


@st.cache_data(show_spinner=False, ttl=60)
def load_monthly_adjustment_totals(period_start: date, period_end: date) -> pd.DataFrame:
    """Manual courier balances are available even when no Excel session exists."""
    try:
        rows = (get_db().schema("settlement").table("courier_settlement_adjustment")
                .select("courier_id,adjustment_type,amount_huf,valid_from,valid_to,effective_date")
                .eq("is_active", True).is_("deleted_at", "null").execute().data or [])
    except BaseException:
        return pd.DataFrame(columns=["courier_id", "adjustment_type", "amount_huf"])
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    from_values = data["valid_from"] if "valid_from" in data else data.get("effective_date")
    to_values = data["valid_to"] if "valid_to" in data else pd.Series(pd.NaT, index=data.index)
    valid_from = pd.to_datetime(from_values, errors="coerce").fillna(pd.to_datetime(data.get("effective_date"), errors="coerce"))
    valid_to = pd.to_datetime(to_values, errors="coerce")
    mask = (valid_from <= pd.Timestamp(period_end)) & (valid_to.isna() | (valid_to >= pd.Timestamp(period_start)))
    return data.loc[mask, ["courier_id", "adjustment_type", "amount_huf"]].copy()


def apply_manual_balance_adjustments(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    """Add bonuses and subtract maluses on the main courier balance list."""
    result = data.copy()
    adjustments = load_monthly_adjustment_totals(period_start, period_end)
    if not adjustments.empty:
        adjustments["courier_id"] = adjustments["courier_id"].map(lambda value: str(value).strip().removesuffix(".0"))
        adjustments["amount_huf"] = pd.to_numeric(adjustments["amount_huf"], errors="coerce").fillna(0.0)
        pivot = adjustments.pivot_table(index="courier_id", columns="adjustment_type", values="amount_huf", aggfunc="sum", fill_value=0.0)
        courier_ids = result["Courier ID"].map(lambda value: str(value).strip().removesuffix(".0"))
        zero_adjustments = pd.Series(0.0, index=pivot.index)
        manual_bonus = courier_ids.map(pivot.get("bonus", zero_adjustments)).fillna(0.0)
        manual_malus = courier_ids.map(pivot.get("malus", zero_adjustments)).fillna(0.0)
        result["JITT bónusz"] = manual_bonus
        result["JITT malus"] = manual_malus
        correction_income = (
            pivot.get("correction", zero_adjustments)
            + pivot.get("manual_correction", zero_adjustments)
            + pivot.get("correction_income", zero_adjustments)
        )
        correction_deduction = (
            pivot.get("correction_deduction", zero_adjustments)
            + pivot.get("manual_correction_deduction", zero_adjustments)
        )
        result["Bónusz"] = (
            _numeric_series(result, "Bónusz")
            + manual_bonus
        )
        result["Korrekció"] = (
            _numeric_series(result, "Korrekció")
            + courier_ids.map(correction_income - correction_deduction).fillna(0.0)
        )
        deductions = (
            pivot.get("malus", zero_adjustments)
            + pivot.get("atm_deduction", zero_adjustments)
            + pivot.get("other_expense", zero_adjustments)
        )
        result["Levonás"] = _numeric_series(result, "Levonás") + courier_ids.map(deductions).fillna(0.0)
        result["Bónusz"] += courier_ids.map(pivot.get("customer_rating", zero_adjustments)).fillna(0.0)
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + payable_bonus_total(result)
        + _numeric_series(result, "Korrekció")
        - _numeric_series(result, "Levonás")
    )
    return result


def apply_periodic_fee_corrections(
    data: pd.DataFrame,
    session_id: str | None,
    calculation_mode: str,
    period_start: date,
    period_end: date,
    warehouse_label: str | None = None,
) -> pd.DataFrame:
    result = data.copy()
    if result.empty:
        return result
    if "Korrekció" not in result.columns:
        result["Korrekció"] = 0.0
    periodic_totals = load_periodic_fee_correction_totals(
        session_id,
        calculation_mode,
        period_start,
        period_end,
        warehouse_label,
    )
    if periodic_totals.empty:
        return result
    result["_courier_id_lookup"] = result["Courier ID"].map(_courier_id_key)
    result["_courier_name_lookup"] = result["Futár"].map(_courier_match_key)
    by_id = periodic_totals.loc[
        periodic_totals["_courier_id_lookup"].ne("")
    ].groupby("_courier_id_lookup")["Korrekció"].sum()
    by_name = periodic_totals.loc[
        periodic_totals["_courier_name_lookup"].ne("")
    ].groupby("_courier_name_lookup")["Korrekció"].sum()
    result["Korrekció"] = (
        _numeric_series(result, "Korrekció")
        + result["_courier_id_lookup"].map(by_id).fillna(result["_courier_name_lookup"].map(by_name)).fillna(0.0)
    )
    result = result.drop(columns=["_courier_id_lookup", "_courier_name_lookup"])
    return result


@st.cache_data(show_spinner=False, ttl=60)
def load_customer_rating_bonus_rows(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (get_db().schema("public").table(CUSTOMER_RATING_UPLOAD_TABLE)
                .select("billing_month,worksheet_name,courier_id,driver_name,route_type,rating_count,average_rating,bonus_per_route_huf,completed_routes,bonus_total_huf,source_row_number")
                .eq("billing_month", period_start.replace(day=1).isoformat())
                .order("driver_name").execute().data or [])
        return pd.DataFrame(rows)
    except BaseException:
        try:
            rows = (get_db().schema("public").table(CUSTOMER_RATING_UPLOAD_TABLE)
                    .select("billing_month,worksheet_name,courier_id,driver_name,rating_count,average_rating,bonus_per_route_huf,completed_routes,bonus_total_huf,source_row_number")
                    .eq("billing_month", period_start.replace(day=1).isoformat())
                    .order("driver_name").execute().data or [])
            return pd.DataFrame(rows)
        except BaseException:
            return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def load_customer_rating_rules_for_month(period_start: date, period_end: date) -> pd.DataFrame:
    try:
        rows = (get_db().schema("settlement").table("cfg_jitt_customer_rating_rules")
                .select("*").eq("is_active", True).is_("deleted_at", "null")
                .lte("valid_from", period_end.isoformat())
                .order("priority").execute().data or [])
    except BaseException:
        return pd.DataFrame()
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    valid_to = pd.to_datetime(data.get("valid_to"), errors="coerce")
    result = data.loc[valid_to.isna() | (valid_to >= pd.Timestamp(period_start))].copy()
    return result


def normalize_customer_rating_route_type(value: object) -> str:
    text = _normalized_field_key(value)
    if "express" in text:
        return "express"
    if "regional" in text or "region" in text:
        return "regional"
    return "normal"


def customer_rating_rule_amount(average_rating: float, rules: pd.DataFrame, route_type: str = "normal") -> float:
    if rules.empty:
        return 0.0
    rating_5 = float(average_rating or 0.0)
    route_type = normalize_customer_rating_route_type(route_type)
    for _, rule in rules.iterrows():
        try:
            min_value = float(rule["rating_min_percent"]) if pd.notna(rule.get("rating_min_percent")) else None
            max_value = float(rule["rating_max_percent"]) if pd.notna(rule.get("rating_max_percent")) else None
        except (TypeError, ValueError):
            continue
        rule_route_type = normalize_customer_rating_route_type(rule.get("route_type") or "normal")
        if rule_route_type not in {route_type, "any"}:
            continue
        if min_value is not None and rating_5 < min_value:
            continue
        if max_value is not None and rating_5 > max_value:
            continue
        return parse_huf_value(rule.get("courier_amount_huf"))
    return 0.0


@st.cache_data(show_spinner=False, ttl=60)
def load_customer_rating_route_type_counts(session_id: str | None) -> pd.DataFrame:
    if not session_id:
        return pd.DataFrame(columns=["driver_key", "route_type", "completed_routes"])
    try:
        rows = (
            get_db().schema("settlement").table("jit_row")
            .select("normalized_data,is_route_primary")
            .eq("session_id", session_id)
            .eq("is_route_primary", True)
            .execute().data or []
        )
    except BaseException:
        return pd.DataFrame(columns=["driver_key", "route_type", "completed_routes"])
    records: list[dict[str, object]] = []
    for row in rows:
        payload = row.get("normalized_data") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        driver_name = (
            payload.get("Driver")
            or payload.get("driver_name")
            or payload.get("Futár")
            or payload.get("courier_name")
            or ""
        )
        route_type = (
            payload.get("Route Type")
            or payload.get("route_type")
            or payload.get("Túratípus")
            or payload.get("Tipus")
            or "normal"
        )
        records.append({
            "driver_key": _courier_match_key(driver_name),
            "route_type": normalize_customer_rating_route_type(route_type),
            "completed_routes": 1,
        })
    if not records:
        return pd.DataFrame(columns=["driver_key", "route_type", "completed_routes"])
    return pd.DataFrame(records).groupby(["driver_key", "route_type"], as_index=False)["completed_routes"].sum()


def apply_customer_rating_bonus(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    result = data.copy()
    rating_rows = load_customer_rating_bonus_rows(period_start, period_end)
    if rating_rows.empty:
        if "Ügyfélértékelés" not in result.columns:
            result["Ügyfélértékelés"] = 0.0
        return result
    rating_rows["courier_id"] = rating_rows.get("courier_id", pd.Series(dtype=str)).map(_courier_id_key)
    rating_rows["driver_key"] = rating_rows.get("driver_name", pd.Series(dtype=str)).map(_courier_match_key)
    rating_rows["bonus_total_huf"] = pd.to_numeric(rating_rows.get("bonus_total_huf", 0), errors="coerce").fillna(0.0)
    by_id = rating_rows.groupby("courier_id")["bonus_total_huf"].sum()
    by_name = rating_rows.groupby("driver_key")["bonus_total_huf"].sum()
    courier_ids = result["Courier ID"].map(_courier_id_key)
    courier_names = result["Futár"].map(_courier_match_key)
    rating_bonus = courier_ids.map(by_id).fillna(courier_names.map(by_name)).fillna(0.0)
    result["Ügyfélértékelés"] = rating_bonus
    result["Bónusz"] = _numeric_series(result, "Bónusz") + rating_bonus
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + payable_bonus_total(result)
        - _numeric_series(result, "Levonás")
    )
    return result


def parse_customer_rating_excel(uploaded_file, billing_month: date, dashboard_data: pd.DataFrame) -> pd.DataFrame:
    raw = pd.read_excel(uploaded_file)
    normalized_columns = {_normalized_field_key(column): column for column in raw.columns}
    required = {
        "courier_id": ["courierid", "futarid", "driverid"],
        "courier_name": ["couriername", "futarneve", "futarnev", "drivername"],
        "courier_rating": ["courierrating", "rating", "ertekeles", "ugyfelertekeles"],
        "deliver_at": ["deliverat", "deliverydate", "datum", "date"],
    }
    resolved: dict[str, str] = {}
    for output_name, aliases in required.items():
        source_column = next((normalized_columns[alias] for alias in aliases if alias in normalized_columns), "")
        if not source_column:
            raise ValueError(f"Hiányzó oszlop az ügyfélértékelés Excelben: {output_name}")
        resolved[output_name] = source_column
    warehouse_column = next((normalized_columns[alias] for alias in ["warehousename", "raktar", "warehouse"] if alias in normalized_columns), "")

    data = raw.copy()
    data["courier_id"] = data[resolved["courier_id"]].map(_courier_id_key)
    data["driver_name"] = data[resolved["courier_name"]].astype(str).str.strip()
    data["courier_rating"] = pd.to_numeric(data[resolved["courier_rating"]], errors="coerce")
    data["deliver_at"] = pd.to_datetime(data[resolved["deliver_at"]], errors="coerce")
    data = data.dropna(subset=["courier_rating"])
    if data.empty:
        raise ValueError("Nem található feldolgozható ügyfélértékelés sor.")
    month_start = billing_month.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    data = data.loc[(data["deliver_at"].dt.date >= month_start) & (data["deliver_at"].dt.date < next_month)].copy()
    if data.empty:
        raise ValueError("A feltöltött Excelben nincs sor a kiválasztott hónapra.")

    routes_by_id = pd.Series(dtype=float)
    routes_by_name = pd.Series(dtype=float)
    if not dashboard_data.empty:
        dash = dashboard_data.copy()
        dash["id_key"] = dash["Courier ID"].map(_courier_id_key)
        dash["name_key"] = dash["Futár"].map(_courier_match_key)
        route_source = _numeric_series(dash, "Útvonalak")
        if route_source.eq(0).all() and "Számolt túrák" in dash.columns:
            route_source = _numeric_series(dash, "Számolt túrák")
        dash["_routes"] = route_source
        routes_by_id = dash.groupby("id_key")["_routes"].sum()
        routes_by_name = dash.groupby("name_key")["_routes"].sum()

    rules = load_customer_rating_rules_for_month(month_start, next_month - timedelta(days=1))
    grouped = (
        data.groupby(["courier_id", "driver_name"], dropna=False)
        .agg(rating_count=("courier_rating", "count"), average_rating=("courier_rating", "mean"))
        .reset_index()
    )
    grouped["name_key"] = grouped["driver_name"].map(_courier_match_key)
    grouped["completed_routes"] = grouped["courier_id"].map(routes_by_id).fillna(grouped["name_key"].map(routes_by_name)).fillna(0).astype(int)
    route_type_counts = load_customer_rating_route_type_counts(
        str(st.session_state.get("settlement_import_session_id") or "").strip()
    )
    route_records: list[dict[str, object]] = []
    for _, row in grouped.iterrows():
        route_counts: dict[str, int] = {}
        if not route_type_counts.empty:
            matches = route_type_counts.loc[route_type_counts["driver_key"] == row["name_key"]]
            route_counts = {
                str(match["route_type"]): int(match["completed_routes"] or 0)
                for _, match in matches.iterrows()
            }
        if not route_counts:
            route_counts = {"normal": int(row["completed_routes"] or 0)}
        for route_type, completed_routes in route_counts.items():
            if completed_routes <= 0:
                continue
            bonus_per_route = customer_rating_rule_amount(row["average_rating"], rules, route_type)
            route_records.append({
                **row.to_dict(),
                "route_type": route_type,
                "completed_routes": completed_routes,
                "bonus_per_route_huf": bonus_per_route,
                "bonus_total_huf": bonus_per_route * completed_routes,
            })
    grouped = pd.DataFrame(route_records)
    if grouped.empty:
        raise ValueError("Nem található számolható Normál vagy Express túra az ügyfélértékeléshez.")
    grouped["billing_month"] = month_start.isoformat()
    grouped["worksheet_name"] = data[warehouse_column].astype(str).str.strip().mode().iloc[0] if warehouse_column else "Ügyfélértékelés"
    grouped["source_row_number"] = range(2, len(grouped) + 2)
    grouped["source_spreadsheet_id"] = f"customer_rating_upload_{month_start:%Y_%m}"
    grouped["row_data"] = grouped.apply(
        lambda row: {
            "rating_count": int(row["rating_count"]),
            "average_rating": float(row["average_rating"]),
            "route_type": str(row["route_type"]),
            "source_file": getattr(uploaded_file, "name", "uploaded.xlsx"),
        },
        axis=1,
    )
    now = pd.Timestamp.utcnow().isoformat()
    grouped["imported_at"] = now
    grouped["updated_at"] = now
    return grouped[[
        "source_spreadsheet_id", "worksheet_name", "source_row_number", "billing_month",
        "courier_id", "driver_name", "route_type", "rating_count", "average_rating",
        "bonus_per_route_huf", "completed_routes", "bonus_total_huf", "row_data",
        "imported_at", "updated_at",
    ]]


def _customer_rating_dashboard_routes(dashboard_data: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    routes_by_id = pd.Series(dtype=float)
    routes_by_name = pd.Series(dtype=float)
    if dashboard_data.empty:
        return routes_by_id, routes_by_name

    dash = dashboard_data.copy()
    dash["id_key"] = dash["Courier ID"].map(_courier_id_key)
    dash["name_key"] = dash["Futár"].map(_courier_match_key)
    route_source = _numeric_series(dash, "Útvonalak")
    if route_source.eq(0).all() and "Számolt túrák" in dash.columns:
        route_source = _numeric_series(dash, "Számolt túrák")
    dash["_routes"] = route_source
    routes_by_id = dash.groupby("id_key")["_routes"].sum()
    routes_by_name = dash.groupby("name_key")["_routes"].sum()
    return routes_by_id, routes_by_name


def _finalize_customer_rating_monthly_rows(
    grouped: pd.DataFrame,
    uploaded_file,
    billing_month: date,
    dashboard_data: pd.DataFrame,
    worksheet_name: str,
) -> pd.DataFrame:
    month_start = billing_month.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    rules = load_customer_rating_rules_for_month(month_start, next_month - timedelta(days=1))
    routes_by_id, routes_by_name = _customer_rating_dashboard_routes(dashboard_data)

    grouped = grouped.copy()
    grouped["courier_id"] = grouped.get("courier_id", pd.Series(dtype=str)).map(_courier_id_key)
    grouped["driver_name"] = grouped.get("driver_name", pd.Series(dtype=str)).astype(str).str.strip()
    grouped["rating_count"] = pd.to_numeric(grouped.get("rating_count"), errors="coerce").fillna(0).astype(int)
    grouped["average_rating"] = pd.to_numeric(grouped.get("average_rating"), errors="coerce")
    grouped = grouped.dropna(subset=["average_rating"])
    if grouped.empty:
        raise ValueError("Nem talĂˇlhatĂł feldolgozhatĂł havi ĂĽgyfĂ©lĂ©rtĂ©kelĂ©s sor.")

    grouped["name_key"] = grouped["driver_name"].map(_courier_match_key)
    grouped["completed_routes"] = (
        grouped["courier_id"].map(routes_by_id)
        .fillna(grouped["name_key"].map(routes_by_name))
        .fillna(0)
        .astype(int)
    )

    route_type_counts = load_customer_rating_route_type_counts(
        str(st.session_state.get("settlement_import_session_id") or "").strip()
    )
    route_records: list[dict[str, object]] = []
    for _, row in grouped.iterrows():
        route_counts: dict[str, int] = {}
        if not route_type_counts.empty:
            matches = route_type_counts.loc[route_type_counts["driver_key"] == row["name_key"]]
            route_counts = {
                str(match["route_type"]): int(match["completed_routes"] or 0)
                for _, match in matches.iterrows()
            }
        if not route_counts:
            route_counts = {"normal": int(row["completed_routes"] or 0)}
        for route_type, completed_routes in route_counts.items():
            if completed_routes <= 0:
                continue
            bonus_per_route = customer_rating_rule_amount(row["average_rating"], rules, route_type)
            route_records.append({
                **row.to_dict(),
                "route_type": route_type,
                "completed_routes": completed_routes,
                "bonus_per_route_huf": bonus_per_route,
                "bonus_total_huf": bonus_per_route * completed_routes,
            })

    result = pd.DataFrame(route_records)
    if result.empty:
        raise ValueError("Nem talĂˇlhatĂł szĂˇmolhatĂł NormĂˇl vagy Express tĂşra az ĂĽgyfĂ©lĂ©rtĂ©kelĂ©shez.")

    result["billing_month"] = month_start.isoformat()
    result["worksheet_name"] = worksheet_name or "Feltoltes_havi"
    result["source_row_number"] = range(2, len(result) + 2)
    result["source_spreadsheet_id"] = f"customer_rating_monthly_upload_{month_start:%Y_%m}"
    result["row_data"] = result.apply(
        lambda row: {
            "rating_count": int(row["rating_count"]),
            "average_rating": float(row["average_rating"]),
            "route_type": str(row["route_type"]),
            "source_file": getattr(uploaded_file, "name", "uploaded.xlsx"),
            "source_format": "monthly_upload",
        },
        axis=1,
    )
    now = pd.Timestamp.utcnow().isoformat()
    result["imported_at"] = now
    result["updated_at"] = now
    return result[[
        "source_spreadsheet_id", "worksheet_name", "source_row_number", "billing_month",
        "courier_id", "driver_name", "route_type", "rating_count", "average_rating",
        "bonus_per_route_huf", "completed_routes", "bonus_total_huf", "row_data",
        "imported_at", "updated_at",
    ]]


def parse_customer_rating_excel_v2(uploaded_file, billing_month: date, dashboard_data: pd.DataFrame) -> pd.DataFrame:
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    excel_file = pd.ExcelFile(uploaded_file)

    simple_aliases = {
        "billing_month": ["datum", "date", "honap", "month", "elszamolasihonap", "billingmonth"],
        "courier_id": ["id", "futarid", "courierid", "driverid"],
        "driver_name": ["nev", "futarnev", "futarneve", "couriername", "drivername"],
        "average_rating": ["ertek", "ertekszam", "ugyfelertekeles", "ertekeles", "averagerating", "atlag", "rating"],
        "rating_count": ["ertekelesdb", "ratingcount", "darab", "count"],
    }
    for simple_sheet in excel_file.sheet_names:
        simple_raw = pd.read_excel(excel_file, sheet_name=simple_sheet)
        simple_columns = {_normalized_field_key(column): column for column in simple_raw.columns}
        simple_resolved: dict[str, str] = {}
        for output_name, names in simple_aliases.items():
            source_column = next((simple_columns[name] for name in names if name in simple_columns), "")
            if source_column:
                simple_resolved[output_name] = source_column
        required_simple = {"billing_month", "courier_id", "driver_name", "average_rating"}
        if not required_simple.issubset(simple_resolved):
            continue

        month_start = billing_month.replace(day=1)
        simple_data = simple_raw.copy()
        month_text = simple_data[simple_resolved["billing_month"]].astype(str).str.strip()
        parsed_months = pd.to_datetime(
            month_text.where(month_text.str.len() > 7, month_text + "-01"),
            errors="coerce",
        ).dt.date
        simple_data["billing_month"] = parsed_months.map(lambda value: value.replace(day=1) if pd.notna(value) else None)
        simple_data = simple_data.loc[simple_data["billing_month"] == month_start].copy()
        if simple_data.empty:
            continue

        grouped = pd.DataFrame({
            "courier_id": simple_data[simple_resolved["courier_id"]],
            "driver_name": simple_data[simple_resolved["driver_name"]],
            "rating_count": (
                simple_data[simple_resolved["rating_count"]]
                if simple_resolved.get("rating_count")
                else pd.Series(1, index=simple_data.index)
            ),
            "average_rating": simple_data[simple_resolved["average_rating"]],
        })
        return _finalize_customer_rating_monthly_rows(
            grouped,
            uploaded_file,
            billing_month,
            dashboard_data,
            simple_sheet,
        )

    monthly_sheet = next(
        (
            sheet_name
            for sheet_name in excel_file.sheet_names
            if _normalized_field_key(sheet_name) in {"feltolteshavi", "havisablon", "forrasmindenhonap"}
        ),
        "",
    )
    if not monthly_sheet:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return parse_customer_rating_excel(uploaded_file, billing_month, dashboard_data)

    raw = pd.read_excel(excel_file, sheet_name=monthly_sheet)
    normalized_columns = {_normalized_field_key(column): column for column in raw.columns}
    aliases = {
        "billing_month": ["elszamolasihonap", "billingmonth", "honap", "month"],
        "courier_id": ["futarid", "courierid", "driverid"],
        "driver_name": ["futarnev", "futarneve", "couriername", "drivername"],
        "average_rating": ["ugyfelertekeleshaviatlag", "ugyfelertekeles", "averagerating", "atlag", "rating"],
        "rating_count": ["ertekelesdb", "ratingcount", "darab", "count"],
    }
    resolved: dict[str, str] = {}
    for output_name, names in aliases.items():
        source_column = next((normalized_columns[name] for name in names if name in normalized_columns), "")
        if not source_column:
            raise ValueError(f"HiĂˇnyzĂł oszlop a havi ĂĽgyfĂ©lĂ©rtĂ©kelĂ©s sablonban: {output_name}")
        resolved[output_name] = source_column

    data = raw.copy()
    month_text = data[resolved["billing_month"]].astype(str).str.strip()
    parsed_months = pd.to_datetime(month_text.where(month_text.str.len() > 7, month_text + "-01"), errors="coerce").dt.date
    data["billing_month"] = parsed_months
    month_start = billing_month.replace(day=1)
    matching_month = data.loc[data["billing_month"] == month_start].copy()
    if matching_month.empty:
        for candidate_sheet in excel_file.sheet_names:
            if candidate_sheet == monthly_sheet:
                continue
            if _normalized_field_key(candidate_sheet) not in {"feltolteshavi", "havisablon", "forrasmindenhonap"}:
                continue
            candidate_raw = pd.read_excel(excel_file, sheet_name=candidate_sheet)
            candidate_columns = {_normalized_field_key(column): column for column in candidate_raw.columns}
            candidate_resolved: dict[str, str] = {}
            for output_name, names in aliases.items():
                source_column = next((candidate_columns[name] for name in names if name in candidate_columns), "")
                if not source_column:
                    candidate_resolved = {}
                    break
                candidate_resolved[output_name] = source_column
            if not candidate_resolved:
                continue
            candidate_data = candidate_raw.copy()
            candidate_month_text = candidate_data[candidate_resolved["billing_month"]].astype(str).str.strip()
            candidate_months = pd.to_datetime(
                candidate_month_text.where(candidate_month_text.str.len() > 7, candidate_month_text + "-01"),
                errors="coerce",
            ).dt.date
            candidate_data["billing_month"] = candidate_months
            candidate_matching = candidate_data.loc[candidate_data["billing_month"] == month_start].copy()
            if candidate_matching.empty:
                continue
            monthly_sheet = candidate_sheet
            resolved = candidate_resolved
            data = candidate_data
            matching_month = candidate_matching
            break
    if not matching_month.empty:
        data = matching_month
    else:
        data = data.loc[data["billing_month"].notna()].copy()
    if data.empty:
        raise ValueError("A havi ugyfelertekeles sablonban nincs felismerheto elszamolasi_honap.")

    grouped = pd.DataFrame({
        "courier_id": data[resolved["courier_id"]],
        "driver_name": data[resolved["driver_name"]],
        "rating_count": data[resolved["rating_count"]],
        "average_rating": data[resolved["average_rating"]],
    })
    return _finalize_customer_rating_monthly_rows(
        grouped,
        uploaded_file,
        billing_month,
        dashboard_data,
        monthly_sheet,
    )


def save_customer_rating_upload(rows: pd.DataFrame, billing_month: date) -> None:
    month_text = billing_month.replace(day=1).isoformat()
    get_db().schema("public").table(CUSTOMER_RATING_UPLOAD_TABLE).delete().eq("billing_month", month_text).execute()
    payload = rows.copy()
    for column in ["average_rating", "bonus_per_route_huf", "bonus_total_huf"]:
        payload[column] = pd.to_numeric(payload[column], errors="coerce").fillna(0).astype(float)
    if "route_type" in payload.columns:
        payload["route_type"] = payload["route_type"].map(normalize_customer_rating_route_type)
    payload["rating_count"] = pd.to_numeric(payload["rating_count"], errors="coerce").fillna(0).astype(int)
    payload["completed_routes"] = pd.to_numeric(payload["completed_routes"], errors="coerce").fillna(0).astype(int)
    records = payload.to_dict("records")
    for start in range(0, len(records), 500):
        get_db().schema("public").table(CUSTOMER_RATING_UPLOAD_TABLE).insert(records[start:start + 500]).execute()
    load_customer_rating_bonus_rows.clear()


@st.cache_data(show_spinner=False, ttl=60)
def load_imported_balance_components(session_id: str | None) -> pd.DataFrame:
    """Read the separate Excel bonus, penalty and ATM sheets for one session."""
    columns = [
        "courier_id_key", "courier_name_key", "Importált bónusz",
        "Importált málusz", "Importált ATM levonás",
        "Importált bónusz megjegyzés", "Importált málusz megjegyzés",
        "Importált ATM megjegyzés",
    ]
    if not session_id:
        return pd.DataFrame(columns=columns)
    definitions = {
        "bonus_route_row": (
            "Importált bónusz",
            ("bonus", "bonusz", "amount", "osszeg", "total"),
            ("bonus", "bonusz", "amount", "osszeg", "total"),
            False,
        ),
        "penalty_row": (
            "Importált málusz",
            ("value", "amount", "osszeg", "penalty", "malus", "levonas"),
            ("value", "amount", "osszeg", "penalty", "malus", "levonas"),
            True,
        ),
        "atm_balance_row": (
            "Importált ATM levonás",
            ("walletdeductions", "balance", "egyenleg", "atm", "cash", "amount", "osszeg"),
            ("wallet", "deduction", "balance", "egyenleg", "atm", "cash", "amount", "osszeg"),
            True,
        ),
    }
    records: list[dict[str, object]] = []
    for table_name, (output_column, exact_amount_keys, amount_tokens, use_absolute) in definitions.items():
        try:
            rows = (get_db().schema("settlement").table(table_name).select("normalized_data")
                    .eq("session_id", session_id).execute().data or [])
        except BaseException:
            continue
        for row in rows:
            payload = row.get("normalized_data") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            if not isinstance(payload, dict):
                continue
            normalized_payload = {
                _normalized_field_key(key): value
                for key, value in payload.items()
            }
            courier_id = next(
                (value for key, value in normalized_payload.items()
                if key in {"courierid", "couriernumber", "driverid", "usernumber", "userid"}),
                None,
            )
            courier_name = next(
                (value for key, value in normalized_payload.items()
                if key in {"driver", "drivername", "courier", "couriername", "futar", "futarnev", "name", "nev"}),
                None,
            )
            amount_value = next((normalized_payload.get(key) for key in exact_amount_keys if key in normalized_payload), None)
            if amount_value is None:
                amount_value = next(
                    (value for key, value in normalized_payload.items()
                    if any(token in key for token in amount_tokens)),
                    None,
                )
            note_value = next(
                (
                    value for key, value in normalized_payload.items()
                    if key in {"note", "notes", "comment", "comment2", "megjegyzes", "leiras", "description"}
                    or "comment" in key
                    or "note" in key
                    or "megjegyzes" in key
                ),
                "",
            )
            amount = parse_huf_value(amount_value)
            if (courier_id is None and courier_name is None) or amount == 0:
                continue
            note_column = {
                "Importált bónusz": "Importált bónusz megjegyzés",
                "Importált málusz": "Importált málusz megjegyzés",
                "Importált ATM levonás": "Importált ATM megjegyzés",
            }.get(output_column)
            records.append({
                "courier_id_key": _courier_id_key(courier_id),
                "courier_name_key": _courier_match_key(courier_name),
                output_column: abs(amount) if use_absolute else amount,
                **({note_column: str(note_value or "").strip()} if note_column else {}),
            })
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records).fillna(0.0)
    for column in columns[1:]:
        if column not in result:
            result[column] = "" if "megjegyzés" in column else 0.0
    amount_columns = ["Importált bónusz", "Importált málusz", "Importált ATM levonás"]
    note_columns = ["Importált bónusz megjegyzés", "Importált málusz megjegyzés", "Importált ATM megjegyzés"]
    for note_column in note_columns:
        result[note_column] = result[note_column].fillna("").astype(str)

    def join_notes(series: pd.Series) -> str:
        values = [str(value).strip() for value in series.tolist() if str(value).strip()]
        return " | ".join(dict.fromkeys(values))

    return (
        result.groupby(columns[:2], as_index=False, dropna=False)
        .agg({
            **{column: "sum" for column in amount_columns},
            **{column: join_notes for column in note_columns},
        })
    )


@st.cache_data(show_spinner=False, ttl=60)
def load_imported_balance_component_items(session_id: str | None, courier_id: str, courier_name: str) -> pd.DataFrame:
    columns = ["Tétel", "Összeg", "Megjegyzés"]
    if not session_id:
        return pd.DataFrame(columns=columns)
    definitions = {
        "bonus_route_row": ("Kiflis bónusz", 1, ("bonus", "bonusz", "amount", "osszeg", "total")),
        "penalty_row": ("Kiflis malus", -1, ("value", "amount", "osszeg", "penalty", "malus", "levonas")),
    }
    rows_out: list[dict[str, object]] = []
    target_id = _courier_id_key(courier_id)
    target_name = _courier_match_key(courier_name)
    for table_name, (label, sign, amount_keys) in definitions.items():
        try:
            rows = (
                get_db().schema("settlement").table(table_name)
                .select("normalized_data")
                .eq("session_id", session_id)
                .execute().data or []
            )
        except BaseException:
            continue
        for source_row in rows:
            payload = source_row.get("normalized_data") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            if not isinstance(payload, dict):
                continue
            normalized_payload = {_normalized_field_key(key): value for key, value in payload.items()}
            row_id = _courier_id_key(next(
                (value for key, value in normalized_payload.items()
                 if key in {"courierid", "couriernumber", "driverid", "usernumber", "userid"}),
                "",
            ))
            row_name = _courier_match_key(next(
                (value for key, value in normalized_payload.items()
                 if key in {"driver", "drivername", "courier", "couriername", "futar", "futarnev", "name", "nev"}),
                "",
            ))
            if target_id and row_id and row_id != target_id:
                continue
            if (not row_id or not target_id) and target_name and row_name != target_name:
                continue
            amount_value = next((normalized_payload.get(key) for key in amount_keys if key in normalized_payload), None)
            if amount_value is None:
                amount_value = next(
                    (value for key, value in normalized_payload.items() if any(token in key for token in amount_keys)),
                    None,
                )
            amount = abs(parse_huf_value(amount_value))
            if not amount:
                continue
            note_parts = []
            for key in ("malusname", "bonusname", "tetel", "reason", "category", "comment", "comment2", "note", "megjegyzes", "description"):
                value = str(normalized_payload.get(key) or "").strip()
                if value and value.casefold() != "nan":
                    note_parts.append(value)
            rows_out.append({
                "Tétel": label,
                "Összeg": sign * amount,
                "Megjegyzés": " | ".join(dict.fromkeys(note_parts)),
            })
    return pd.DataFrame(rows_out, columns=columns)


def apply_imported_balance_components(data: pd.DataFrame, session_id: str | None) -> pd.DataFrame:
    result = data.copy()
    components = load_imported_balance_components(session_id)
    component_columns = ("Importált bónusz", "Importált málusz", "Importált ATM levonás")
    component_note_columns = ("Importált bónusz megjegyzés", "Importált málusz megjegyzés", "Importált ATM megjegyzés")
    for column in component_columns:
        result[column] = 0.0
    for column in component_note_columns:
        result[column] = ""
    if components.empty:
        return result
    component_by_id = (
        components[components["courier_id_key"] != ""]
        .groupby("courier_id_key", dropna=False)
        .agg({
            **{column: "sum" for column in component_columns},
            **{column: "first" for column in component_note_columns},
        })
    )
    component_by_name = (
        components[components["courier_name_key"] != ""]
        .groupby("courier_name_key", dropna=False)
        .agg({
            **{column: "sum" for column in component_columns},
            **{column: "first" for column in component_note_columns},
        })
    )
    result["_courier_id_component_key"] = result["Courier ID"].map(_courier_id_key)
    result["_courier_name_component_key"] = result["Futár"].map(_courier_match_key)
    for column in component_columns:
        empty_values = pd.Series(float("nan"), index=result.index, dtype="float64")
        by_id = result["_courier_id_component_key"].map(component_by_id[column]) if column in component_by_id else empty_values
        by_name = result["_courier_name_component_key"].map(component_by_name[column]) if column in component_by_name else empty_values
        result[column] = by_id.fillna(by_name).fillna(0.0)
    for column in component_note_columns:
        empty_values = pd.Series("", index=result.index, dtype="object")
        by_id = result["_courier_id_component_key"].map(component_by_id[column]) if column in component_by_id else empty_values
        by_name = result["_courier_name_component_key"].map(component_by_name[column]) if column in component_by_name else empty_values
        result[column] = by_id.fillna(by_name).fillna("").astype(str)
    result["Bónusz"] = _numeric_series(result, "Bónusz") + result["Importált bónusz"]
    result["Levonás"] = _numeric_series(result, "Levonás") + result["Importált málusz"] + result["Importált ATM levonás"]
    return result.drop(columns=["_courier_id_component_key", "_courier_name_component_key"])


def balance_component_session_id(calculation_mode: str, period_start: date, session_id: str | None) -> str | None:
    """Kiflis bonus/malus/ATM sheets are Excel-side data even when the main settlement mode is API."""
    if str(calculation_mode or "").strip().casefold() == "excel":
        return session_id
    return load_latest_excel_jit_session_id(period_start) or session_id


def enrich_mobile_row_with_imported_balance_components(
    row: dict[str, object],
    component_session_id: str | None,
) -> dict[str, object]:
    """Overlay the latest Excel-side Kiflis bonus/malus/ATM values before publishing to PWA."""
    if not component_session_id:
        return row
    try:
        components = load_imported_balance_components(component_session_id)
    except Exception:
        return row
    if components.empty:
        return row
    courier_id = _courier_id_key(row.get("Courier ID"))
    courier_name = _courier_match_key(row.get("Futár") or row.get("FutĂˇr"))
    selected = pd.DataFrame()
    if courier_id and "courier_id_key" in components.columns:
        selected = components.loc[components["courier_id_key"].astype(str).eq(courier_id)]
    if selected.empty and courier_name and "courier_name_key" in components.columns:
        selected = components.loc[components["courier_name_key"].astype(str).eq(courier_name)]
    if selected.empty:
        return row

    enriched = dict(row)
    amount_columns = ("Importált bónusz", "Importált málusz", "Importált ATM levonás")
    note_columns = (
        "Importált bónusz megjegyzés",
        "Importált málusz megjegyzés",
        "Importált ATM megjegyzés",
    )
    for column in amount_columns:
        if column in selected.columns:
            enriched[column] = float(pd.to_numeric(selected[column], errors="coerce").fillna(0.0).sum())
    for column in note_columns:
        if column in selected.columns:
            notes = [
                str(value).strip()
                for value in selected[column].fillna("").tolist()
                if str(value).strip()
            ]
            enriched[column] = " | ".join(dict.fromkeys(notes))
    return enriched


def format_huf(value: float | int) -> str:
    try:
        if pd.isna(value):
            value = 0
    except (TypeError, ValueError):
        value = 0
    return f"{value:,.0f} Ft".replace(",", " ")


def parse_huf_value(value: object) -> float:
    """Accept numeric DB values and formatted Hungarian money strings."""
    if value is None or value == "":
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("−", "-").replace("Ft", "").replace("ft", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9,.-]", "", text)
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def month_options(count: int = 24) -> list[str]:
    names = ["január","február","március","április","május","június","július","augusztus","szeptember","október","november","december"]
    today = date.today()
    items=[]
    y,m=today.year,today.month
    for _ in range(count):
        items.append(f"{y}. {names[m-1]}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return items


def parse_month_option(value: str | None) -> date:
    names = {
        "január": 1, "február": 2, "március": 3, "április": 4,
        "május": 5, "június": 6, "július": 7, "augusztus": 8,
        "szeptember": 9, "október": 10, "november": 11, "december": 12,
    }
    text = str(value or "").strip().lower()
    match = re.match(r"^(\d{4})\.\s*(.+)$", text)
    if not match:
        today = date.today()
        return date(today.year, today.month, 1)
    year = int(match.group(1))
    month = names.get(match.group(2).strip(), date.today().month)
    return date(year, month, 1)


def settlement_warehouse_id(value: str | None) -> int | None:
    normalized = str(value or "").strip().upper().replace("-", "").replace("_", "").replace(" ", "")
    if normalized in {"", "ÖSSZES", "OSSZES"}:
        return None
    if "BUD2" in normalized:
        return 2
    if "BUD1" in normalized or normalized in {"BUD", "BUDAPEST"}:
        return 1
    return None


def import_api_financial_overview_to_jit(period_start: date, warehouse_label: str | None) -> str:
    warehouse_id = settlement_warehouse_id(warehouse_label)
    response = (
        get_db()
        .schema("settlement")
        .rpc(
            "import_api_financial_overview_to_jit",
            {
                "p_year": period_start.year,
                "p_month": period_start.month,
                "p_warehouse_id": warehouse_id,
            },
        )
        .execute()
    )
    if isinstance(response.data, str):
        return response.data
    return str(response.data or "")


def refresh_excel_route_coverage_audit(session_id: str | None, period_start: date, period_end: date) -> int:
    if not session_id:
        return 0
    response = (
        get_db()
        .schema("settlement")
        .rpc(
            "refresh_excel_route_coverage_audit",
            {
                "p_session_id": str(session_id),
                "p_period_start": period_start.isoformat(),
                "p_period_end": period_end.isoformat(),
            },
        )
        .execute()
    )
    try:
        return int(response.data or 0)
    except (TypeError, ValueError):
        return 0


def refresh_dsp_route_delay_audit(period_start: date, period_end: date) -> dict[str, int]:
    response = (
        get_db()
        .schema("settlement")
        .rpc(
            "refresh_dsp_route_delay_audit",
            {
                "p_period_start": period_start.isoformat(),
                "p_period_end": period_end.isoformat(),
            },
        )
        .execute()
    )
    data = response.data or {}
    if not isinstance(data, dict):
        return {"detail_rows": 0, "daily_rows": 0, "monthly_compare_rows": 0}
    return {
        "detail_rows": int(data.get("detail_rows") or 0),
        "daily_rows": int(data.get("daily_rows") or 0),
        "monthly_compare_rows": int(data.get("monthly_compare_rows") or 0),
    }


def refresh_dsp_shift_attendance_audit(period_start: date, period_end: date) -> dict[str, int]:
    response = (
        get_db()
        .schema("settlement")
        .rpc(
            "refresh_dsp_shift_attendance_audit",
            {
                "p_period_start": period_start.isoformat(),
                "p_period_end": period_end.isoformat(),
            },
        )
        .execute()
    )
    data = response.data or {}
    if not isinstance(data, dict):
        return {"monthly_compare_rows": 0}
    return {
        "monthly_compare_rows": int(data.get("monthly_compare_rows") or 0),
    }


@st.cache_data(show_spinner=False, ttl=60)
def load_dsp_time_window_delay_audit(period_start: date, period_end: date) -> pd.DataFrame:
    columns = [
        "period_start",
        "period_end",
        "courier_id",
        "courier_name",
        "api_delayed_order_count",
        "mart_time_window_late_count",
        "difference_count",
        "delay_match_ok",
        "refreshed_at",
    ]
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("dsp_time_window_delay_audit_monthly")
            .select(",".join(columns))
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .execute()
            .data
            or []
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=60)
def load_dsp_shift_attendance_audit(period_start: date, period_end: date) -> pd.DataFrame:
    columns = [
        "period_start",
        "period_end",
        "courier_id",
        "courier_name",
        "api_shift_count",
        "mart_shift_count",
        "api_late_shift_count",
        "mart_late_shift_count",
        "late_difference_count",
        "late_match_ok",
        "api_no_show_count",
        "mart_no_show_count",
        "no_show_difference_count",
        "no_show_match_ok",
        "refreshed_at",
    ]
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("dsp_shift_attendance_audit_monthly")
            .select(",".join(columns))
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .execute()
            .data
            or []
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def apply_dsp_route_delay_audit(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    if data.empty:
        return data
    audit = load_dsp_time_window_delay_audit(period_start, period_end)
    result = data.copy()
    result["Delay audit has result"] = False
    result["Delay audit ok"] = pd.NA
    result["Delay audit text"] = ""
    if audit.empty:
        return result

    audit = audit.copy()
    audit["_courier_id_lookup"] = audit.get("courier_id", pd.Series(dtype=object)).map(_courier_id_key)
    audit["_courier_name_lookup"] = audit.get("courier_name", pd.Series(dtype=object)).map(_courier_match_key)
    numeric_columns = ["api_delayed_order_count", "mart_time_window_late_count", "difference_count"]
    for column in numeric_columns:
        audit[column] = pd.to_numeric(audit.get(column, 0), errors="coerce").fillna(0)
    audit["delay_match_ok"] = audit.get("delay_match_ok", False).astype(bool)
    by_id = (
        audit[audit["_courier_id_lookup"] != ""]
        .drop_duplicates("_courier_id_lookup", keep="first")
        .set_index("_courier_id_lookup")
        .to_dict("index")
    )
    by_name = (
        audit[audit["_courier_name_lookup"] != ""]
        .drop_duplicates("_courier_name_lookup", keep="first")
        .set_index("_courier_name_lookup")
        .to_dict("index")
    )

    has_results: list[bool] = []
    oks: list[object] = []
    texts: list[str] = []
    for _, row in result.iterrows():
        audit_row = by_id.get(_courier_id_key(row.get("Courier ID"))) or by_name.get(_courier_match_key(row.get("Futár")))
        if not audit_row:
            has_results.append(False)
            oks.append(pd.NA)
            texts.append("")
            continue
        api_count = int(audit_row.get("api_delayed_order_count") or 0)
        mart_count = int(audit_row.get("mart_time_window_late_count") or 0)
        is_ok = bool(audit_row.get("delay_match_ok"))
        has_results.append(True)
        oks.append(is_ok)
        if is_ok:
            texts.append(f"Késés OK: {api_count}")
        else:
            texts.append(f"Késés eltérés: API {api_count} / mart {mart_count}")

    result["Delay audit has result"] = has_results
    result["Delay audit ok"] = oks
    result["Delay audit text"] = texts
    return result


def apply_dsp_shift_attendance_audit(data: pd.DataFrame, period_start: date, period_end: date) -> pd.DataFrame:
    if data.empty:
        return data
    audit = load_dsp_shift_attendance_audit(period_start, period_end)
    result = data.copy()
    result["Shift late audit has result"] = False
    result["Shift late audit ok"] = pd.NA
    result["Shift late audit text"] = ""
    result["No show audit has result"] = False
    result["No show audit ok"] = pd.NA
    result["No show audit text"] = ""
    if audit.empty:
        return result

    audit = audit.copy()
    audit["_courier_id_lookup"] = audit.get("courier_id", pd.Series(dtype=object)).map(_courier_id_key)
    audit["_courier_name_lookup"] = audit.get("courier_name", pd.Series(dtype=object)).map(_courier_match_key)
    numeric_columns = [
        "api_late_shift_count",
        "mart_late_shift_count",
        "late_difference_count",
        "api_no_show_count",
        "mart_no_show_count",
        "no_show_difference_count",
    ]
    for column in numeric_columns:
        audit[column] = pd.to_numeric(audit.get(column, 0), errors="coerce").fillna(0)
    audit["late_match_ok"] = audit.get("late_match_ok", False).astype(bool)
    audit["no_show_match_ok"] = audit.get("no_show_match_ok", False).astype(bool)
    by_id = (
        audit[audit["_courier_id_lookup"] != ""]
        .drop_duplicates("_courier_id_lookup", keep="first")
        .set_index("_courier_id_lookup")
        .to_dict("index")
    )
    by_name = (
        audit[audit["_courier_name_lookup"] != ""]
        .drop_duplicates("_courier_name_lookup", keep="first")
        .set_index("_courier_name_lookup")
        .to_dict("index")
    )

    late_has_results: list[bool] = []
    late_oks: list[object] = []
    late_texts: list[str] = []
    no_show_has_results: list[bool] = []
    no_show_oks: list[object] = []
    no_show_texts: list[str] = []
    for _, row in result.iterrows():
        audit_row = by_id.get(_courier_id_key(row.get("Courier ID"))) or by_name.get(_courier_match_key(row.get("Futár")))
        if not audit_row:
            late_has_results.append(False)
            late_oks.append(pd.NA)
            late_texts.append("")
            no_show_has_results.append(False)
            no_show_oks.append(pd.NA)
            no_show_texts.append("")
            continue

        api_late = int(audit_row.get("api_late_shift_count") or 0)
        mart_late = int(audit_row.get("mart_late_shift_count") or 0)
        late_ok = bool(audit_row.get("late_match_ok"))
        late_has_results.append(True)
        late_oks.append(late_ok)
        late_texts.append(f"Műszak késés OK: {api_late}" if late_ok else f"Műszak késés eltérés: API {api_late} / mart {mart_late}")

        api_no_show = int(audit_row.get("api_no_show_count") or 0)
        mart_no_show = int(audit_row.get("mart_no_show_count") or 0)
        no_show_ok = bool(audit_row.get("no_show_match_ok"))
        no_show_has_results.append(True)
        no_show_oks.append(no_show_ok)
        no_show_texts.append(f"No-show OK: {api_no_show}" if no_show_ok else f"No-show eltérés: API {api_no_show} / mart {mart_no_show}")

    result["Shift late audit has result"] = late_has_results
    result["Shift late audit ok"] = late_oks
    result["Shift late audit text"] = late_texts
    result["No show audit has result"] = no_show_has_results
    result["No show audit ok"] = no_show_oks
    result["No show audit text"] = no_show_texts
    return result


@st.cache_data(show_spinner=False, ttl=60)
def load_excel_route_coverage_audit(session_id: str | None) -> pd.DataFrame:
    columns = [
        "session_id",
        "courier_id",
        "courier_name",
        "courier_key",
        "coverage_status",
        "is_ok",
        "excel_route_count",
        "dsp_route_count",
        "matched_route_count",
        "missing_route_count",
        "extra_excel_route_count",
        "missing_route_ids",
        "extra_excel_route_ids",
        "updated_at",
    ]
    if not session_id:
        return pd.DataFrame(columns=columns)
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("excel_route_coverage_audit")
            .select(",".join(columns))
            .eq("session_id", str(session_id))
            .execute()
            .data
            or []
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def apply_excel_route_coverage_audit(data: pd.DataFrame, session_id: str | None) -> pd.DataFrame:
    if data.empty or not session_id:
        return data
    audit = load_excel_route_coverage_audit(session_id)
    result = data.copy()
    result["Route audit status"] = ""
    result["Route audit ok"] = pd.NA
    result["Route audit text"] = ""
    if audit.empty:
        return result

    audit = audit.copy()
    audit["_courier_id_lookup"] = audit.get("courier_id", pd.Series(dtype=object)).map(_courier_id_key)
    audit["_courier_name_lookup"] = audit.get("courier_name", pd.Series(dtype=object)).map(_courier_match_key)
    for sort_column in ["is_ok", "matched_route_count", "updated_at"]:
        if sort_column not in audit.columns:
            audit[sort_column] = None
    audit_sorted = audit.sort_values(
        ["is_ok", "matched_route_count", "updated_at"],
        ascending=[False, False, False],
        na_position="last",
    )
    by_id = (
        audit_sorted[audit_sorted["_courier_id_lookup"] != ""]
        .drop_duplicates("_courier_id_lookup", keep="first")
        .set_index("_courier_id_lookup")
        .to_dict("index")
    )
    by_name = (
        audit_sorted[audit_sorted["_courier_name_lookup"] != ""]
        .drop_duplicates("_courier_name_lookup", keep="first")
        .set_index("_courier_name_lookup")
        .to_dict("index")
    )

    def resolve(row: pd.Series) -> dict[str, object] | None:
        courier_id_key = _courier_id_key(row.get("Courier ID"))
        courier_name_key = _courier_match_key(row.get("Futár"))
        return by_id.get(courier_id_key) or by_name.get(courier_name_key)

    statuses: list[str] = []
    oks: list[object] = []
    texts: list[str] = []
    for _, row in result.iterrows():
        audit_row = resolve(row)
        if not audit_row:
            statuses.append("")
            oks.append(pd.NA)
            texts.append("")
            continue
        status = str(audit_row.get("coverage_status") or "")
        is_ok = bool(audit_row.get("is_ok"))
        missing_count = int(audit_row.get("missing_route_count") or 0)
        dsp_count = int(audit_row.get("dsp_route_count") or 0)
        matched_count = int(audit_row.get("matched_route_count") or 0)
        if is_ok:
            text = f"Route ID OK: {matched_count}/{dsp_count}"
        elif status:
            text = f"Route ID eltérés: {missing_count} hiányzik az Excelből"
        else:
            text = ""
        statuses.append(status)
        oks.append(is_ok)
        texts.append(text)

    result["Route audit status"] = statuses
    result["Route audit ok"] = oks
    result["Route audit text"] = texts
    return result


def status_meta(status: str) -> tuple[str,str]:
    mapping={
        "Előkészítve":("status-red","led-red"),
        "Ellenőrzés alatt":("status-yellow","led-yellow"),
        "Jóváhagyva":("status-green","led-green"),
        "Elszámolásra vár":("status-blue","led-blue"),
        "Elszámolás elfogadásra vár":("status-blue","led-blue"),
        "TIG-re vár":("status-purple","led-purple"),
        "TIG elfogadásra vár":("status-purple","led-purple"),
        "Bejelentések":("status-orange","led-orange"),
        "Kifizetésre vár":("status-yellow","led-yellow"),
        "Kifizetve":("status-green","led-green"),
    }
    return mapping.get(status,("status-yellow","led-yellow"))


def get_demo_documents() -> pd.DataFrame:
    return pd.DataFrame([
        {"Courier ID":"7486","Típus":"Elszámolás","Fájl":"elszamolas_2026_06.pdf","Feltöltve":"2026-07-03 09:12"},
        {"Courier ID":"7486","Típus":"TIG","Fájl":"tig_2026_06.pdf","Feltöltve":"2026-07-04 10:35"},
        {"Courier ID":"7612","Típus":"Elszámolás","Fájl":"elszamolas_2026_06.pdf","Feltöltve":"2026-07-03 09:30"},
    ])


def get_demo_complaints() -> pd.DataFrame:
    return pd.DataFrame([
        {"Courier ID":"7486","Típus":"Elszámolás","Státusz":"Nyitott","Dátum":"2026-07-05","Üzenet":"A bónusz összege eltér."},
        {"Courier ID":"7612","Típus":"TIG","Státusz":"Lezárt","Dátum":"2026-07-02","Üzenet":"A vállalkozási cím javítva lett."},
    ])


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_route_detail(
    courier_id: str,
    courier_name: str,
    session_id: str | None,
    calculation_mode: str = "Excel",
    period_start: date | None = None,
    warehouse_label: str | None = None,
) -> pd.DataFrame:
    """Return auditable, unique Route ID rows for one courier.

    The JITT upload does not always contain a Courier ID.  In that case only a
    *full normalized name match* is accepted.  When the upload contains a
    legal-form suffix (for example ``E.V.``), the complete personal name may
    be extended only by that suffix; arbitrary partial name matching is not
    used.
    """
    columns = [
        "Route ID", "Excel dátum", "Hét napja", "Túratípus", "Naptípus",
        "Rendelések", "Alapdíj", "Borravaló", "Késedelmi díj",
        "Túramegfelelés", "Bónuszok", "DB státusz",
    ]
    if not session_id or not courier_id:
        if str(calculation_mode).casefold() != "api" or period_start is None:
            return pd.DataFrame(columns=columns)
    if str(calculation_mode).casefold() == "api" and period_start is not None:
        _, api_period_end = month_bounds(period_start)
        api_rows = load_api_financial_overview_rows_for_courier(period_start.year, period_start.month, courier_id)
        warehouse_id = settlement_warehouse_id(warehouse_label)
        if warehouse_id is not None and not api_rows.empty and "warehouse_id" in api_rows.columns:
            api_rows = api_rows.loc[
                pd.to_numeric(api_rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id
            ]
        api_detail = api_financial_routes_to_detail(api_rows, courier_id, period_start, api_period_end)
        if not api_detail.empty:
            return api_detail.drop(columns=["_courier_id"], errors="ignore")
        if not session_id:
            session_id = load_latest_api_jit_session_id(period_start, warehouse_label)
    try:
        rows: list[dict[str, object]] = []
        page_size = 1000
        offset = 0

        while True:
            query = (
                get_db()
                .schema("settlement")
                .table("jit_row")
                .select(
                    "normalized_data,route_unique_id,route_date,weekday_iso,"
                    "calculated_day_type,courier_base_rate_huf,courier_tip_huf,"
                    "courier_delay_bonus_huf,courier_compliance_bonus_huf,"
                    "courier_bonus_total_huf,"
                    "is_route_primary,base_rate_status"
                )
                .eq("session_id", session_id)
                .eq("is_route_primary", True)
            )
            if period_start is not None:
                _, detail_period_end = month_bounds(period_start)
                query = query.gte("route_date", period_start.isoformat()).lte("route_date", detail_period_end.isoformat())
            page = (
                query
                .range(offset, offset + page_size - 1)
                .execute()
                .data
                or []
            )

            rows.extend(page)

            if len(page) < page_size:
                break

            offset += page_size

    except BaseException:
        return pd.DataFrame(columns=columns)
    parsed: list[dict[str, object]] = []
    target_id = _courier_id_key(courier_id)
    target_name = _courier_match_key(courier_name)
    weekday_names = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
    for source in rows:
        normalized = source.get("normalized_data") or {}
        if isinstance(normalized, str):
            try:
                normalized = json.loads(normalized)
            except json.JSONDecodeError:
                normalized = {}
        if not isinstance(normalized, dict):
            continue
        normalized_fields = {_normalized_field_key(key): value for key, value in normalized.items()}
        source_id = next(
            (value for key, value in normalized_fields.items()
            if key in {"courierid", "couriernumber", "driverid", "usernumber", "userid"}),
            None,
        )
        source_name = next(
            (value for key, value in normalized_fields.items()
            if key in {"driver", "drivername", "courier", "couriername", "futar", "futarnev"}),
            None,
        )
        has_source_id = source_id is not None and _courier_id_key(source_id) != ""
        source_name_key = _courier_match_key(source_name)
        source_tokens, target_tokens = set(source_name_key.split()), set(target_name.split())
        is_exact_name = source_name_key == target_name
        is_extended_full_name = (
            len(source_tokens) >= 2 and len(target_tokens) >= 2
            and (source_tokens <= target_tokens or target_tokens <= source_tokens)
        )
        id_matches = (
            has_source_id
            and _courier_id_key(source_id) == target_id
        )

        is_matching_courier = (
            id_matches
            or is_exact_name
            or (not has_source_id and is_extended_full_name)
        )
        if not is_matching_courier:
            continue
        if source.get("is_route_primary") is not True:
            continue
        route_value = str(normalized.get("Route Type") or normalized.get("route_type") or "NORMAL").strip().upper()
        route_type_key = {"NORMAL": "normal", "CITY": "normal", "EXPRESS": "express", "REGIONAL": "regional"}.get(route_value, "normal")
        route_type = {"normal": "Normál", "express": "Expressz", "regional": "Regionális"}[route_type_key]
        day_type_key = str(source.get("calculated_day_type") or "").casefold()
        day_type = {"highlighted": "Kiemelt nap", "normal": "Normál nap"}.get(day_type_key, "Nincs besorolás")
        delay_bonus = parse_huf_value(source.get("courier_delay_bonus_huf"))
        compliance_bonus = parse_huf_value(source.get("courier_compliance_bonus_huf"))
        parsed.append({
            "Route ID": str(source.get("route_unique_id") or "–"),
            "Excel dátum": str(source.get("route_date") or "–"),
            "Hét napja": weekday_names.get(source.get("weekday_iso"), "–"),
            "Túratípus": route_type,
            "Naptípus": day_type,
            "Rendelések": parse_huf_value(normalized.get("Orders") or normalized.get("orders")),
            "Alapdíj": parse_huf_value(source.get("courier_base_rate_huf")),
            "Borravaló": parse_huf_value(source.get("courier_tip_huf")),
            "Késedelmi díj": delay_bonus,
            "Túramegfelelés": compliance_bonus,
            "Bónuszok": delay_bonus + compliance_bonus,
            "DB státusz": str(source.get("base_rate_status") or "ismeretlen"),
        })
    if not parsed:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(parsed).sort_values(["Excel dátum", "Route ID"])


def summarize_courier_route_detail(route_detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only the auditable Route ID rows displayed to the user."""
    columns = [
        "Túratípus", "Naptípus", "Túrák", "Alapdíj", "Borravaló",
        "Késedelmi díj", "Túramegfelelés", "Bónuszok",
    ]
    if route_detail.empty:
        return pd.DataFrame(columns=columns)
    detail = route_detail.copy()
    detail["Túrák"] = 1
    return detail.groupby(["Túratípus", "Naptípus"], as_index=False)[columns[2:]].sum()


def build_amount_drilldown(
    route_detail: pd.DataFrame,
    amount_column: str,
    level_rules: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = ["Túratípus", "Naptípus", "Szint", "Túrák", "Egységösszeg", "Összeg", "Számítás"]
    if route_detail.empty or amount_column not in route_detail.columns:
        return pd.DataFrame(columns=columns)
    detail = route_detail.copy()
    detail["_amount"] = pd.to_numeric(detail[amount_column], errors="coerce").fillna(0.0)
    detail = detail[detail["_amount"].ne(0)].copy()
    if detail.empty:
        return pd.DataFrame(columns=columns)
    if level_rules is not None and not level_rules.empty:
        detail["Szint"] = detail.apply(
            lambda item: performance_level_for_amount(
                item["_amount"],
                level_rules,
                item.get("Túratípus"),
                item.get("Naptípus"),
                item.get("Excel dátum"),
            ),
            axis=1,
        )
    else:
        detail["Szint"] = "-"
    grouped = (
        detail.groupby(["Túratípus", "Naptípus", "Szint", "_amount"], dropna=False)
        .size()
        .reset_index(name="Túrák")
    )
    grouped["Egységösszeg"] = grouped["_amount"]
    grouped["Összeg"] = grouped["Túrák"] * grouped["Egységösszeg"]
    grouped["Számítás"] = grouped.apply(
        lambda item: f"{int(item['Túrák'])} x {format_huf(item['Egységösszeg'])}",
        axis=1,
    )
    return grouped[columns].sort_values(["Túratípus", "Naptípus", "Egységösszeg"])


def _detail_column(data: pd.DataFrame, *names: str) -> str | None:
    if data.empty:
        return None
    normalized = {_normalized_field_key(column): column for column in data.columns}
    for name in names:
        column = normalized.get(_normalized_field_key(name))
        if column:
            return column
    return None


def _weekdays_from_rule(value: object) -> set[int]:
    if value in (None, ""):
        return set()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = re.findall(r"\d+", value)
    try:
        return {int(item) for item in value if int(item) in range(1, 8)}
    except TypeError:
        return set()


def _rule_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def calculate_periodic_fee_corrections(
    route_detail: pd.DataFrame,
    period_start: date,
    period_end: date,
    warehouse_code: object = None,
) -> tuple[float, pd.DataFrame]:
    columns = ["Tétel", "Napok", "Túratípus", "Feltétel", "Darab", "Egységösszeg", "Összeg", "Számítás"]
    rules = load_active_periodic_fee_rules(period_start, period_end)
    if route_detail.empty or rules.empty:
        return 0.0, pd.DataFrame(columns=columns)

    date_column = _detail_column(route_detail, "Excel dátum", "work_date", "delivery_date", "date")
    route_type_column = _detail_column(route_detail, "Túratípus", "route_type", "routeLayer")
    day_type_column = _detail_column(route_detail, "Naptípus", "day_type")
    order_column = _detail_column(route_detail, "Rendelések", "order_count", "orders")
    warehouse_column = _detail_column(route_detail, "Raktár", "warehouse", "warehouse_code")
    if not date_column:
        return 0.0, pd.DataFrame(columns=columns)

    detail = route_detail.copy()
    detail["_periodic_date"] = pd.to_datetime(detail[date_column], errors="coerce").dt.date
    detail = detail[detail["_periodic_date"].notna()].copy()
    if detail.empty:
        return 0.0, pd.DataFrame(columns=columns)
    detail["_periodic_route_type"] = detail[route_type_column].map(lambda value: _performance_key_from_label(value, "route")) if route_type_column else "any"
    detail["_periodic_day_type"] = detail[day_type_column].map(lambda value: _performance_key_from_label(value, "day")) if day_type_column else "any"
    detail["_periodic_orders"] = pd.to_numeric(detail[order_column], errors="coerce").fillna(0.0) if order_column else 0.0
    if warehouse_column:
        detail["_periodic_warehouse"] = detail[warehouse_column].astype(str).str.strip().str.casefold()
    else:
        detail["_periodic_warehouse"] = str(warehouse_code or "").strip().casefold()

    rows: list[dict[str, object]] = []
    for _, rule in rules.sort_values("priority", kind="stable").iterrows():
        valid_from = _rule_date(rule.get("valid_from")) or period_start
        valid_to = _rule_date(rule.get("valid_to")) or period_end
        selected = detail[
            (detail["_periodic_date"] >= valid_from)
            & (detail["_periodic_date"] <= valid_to)
        ].copy()
        if selected.empty:
            continue

        weekdays = _weekdays_from_rule(rule.get("weekdays"))
        if weekdays:
            selected = selected[selected["_periodic_date"].map(lambda item: item.isoweekday() in weekdays)].copy()
        rule_route_type = str(rule.get("route_type") or "any").casefold()
        if rule_route_type != "any":
            selected = selected[selected["_periodic_route_type"] == rule_route_type].copy()
        rule_day_type = str(rule.get("day_type") or "any").casefold()
        if rule_day_type != "any":
            selected = selected[selected["_periodic_day_type"] == rule_day_type].copy()
        rule_warehouse = str(rule.get("warehouse_code") or "").strip().casefold()
        if rule_warehouse:
            selected = selected[selected["_periodic_warehouse"] == rule_warehouse].copy()
        if selected.empty:
            continue

        condition = str(rule.get("condition_metric") or "none").casefold()
        minimum = parse_huf_value(rule.get("condition_min"))
        maximum_value = rule.get("condition_max")
        maximum = parse_huf_value(maximum_value) if pd.notna(maximum_value) else None
        unit = str(rule.get("calculation_unit") or "per_route").casefold()
        unit_amount = parse_huf_value(rule.get("courier_amount_huf"))
        route_count = len(selected)
        order_count = float(selected["_periodic_orders"].sum())
        payable_units = 0.0
        metric_count = route_count

        if condition == "orders_per_route":
            filtered = selected[selected["_periodic_orders"] >= minimum].copy()
            if maximum is not None:
                filtered = filtered[filtered["_periodic_orders"] <= maximum].copy()
            route_count = len(filtered)
            order_count = float(filtered["_periodic_orders"].sum())
            payable_units = route_count if unit in {"fixed", "per_route"} else order_count
            metric_count = route_count
        elif condition == "routes_per_day":
            day_counts = selected.groupby("_periodic_date").size()
            if maximum is None:
                eligible_days = day_counts[day_counts >= minimum]
            else:
                eligible_days = day_counts[(day_counts >= minimum) & (day_counts <= maximum)]
            metric_count = int(eligible_days.sum())
            payable_units = len(eligible_days) if unit == "fixed" else metric_count
            if unit == "per_order":
                payable_units = order_count
        elif condition == "routes_in_period":
            ok = route_count >= minimum and (maximum is None or route_count <= maximum)
            metric_count = route_count
            payable_units = route_count if ok else 0
            if ok and unit == "fixed":
                payable_units = 1
            if ok and unit == "per_order":
                payable_units = order_count
        elif condition == "orders_in_period":
            ok = order_count >= minimum and (maximum is None or order_count <= maximum)
            metric_count = order_count
            payable_units = order_count if ok and unit == "per_order" else (1 if ok and unit == "fixed" else route_count if ok else 0)
        elif condition == "every_n_routes_per_day":
            n_value = max(int(minimum), 1)
            blocks = int(selected.groupby("_periodic_date").size().map(lambda count: int(count) // n_value).sum())
            metric_count = blocks
            payable_units = blocks
        elif condition == "every_n_routes_in_period":
            n_value = max(int(minimum), 1)
            blocks = route_count // n_value
            metric_count = blocks
            payable_units = blocks
        elif condition == "orders_over_threshold_every_n_per_route":
            threshold = max(float(minimum or 0), 0.0)
            step_value = max(int(maximum or 1), 1)
            extra_orders = selected["_periodic_orders"].sub(threshold).clip(lower=0)
            route_blocks = extra_orders.map(lambda value: int(value) // step_value)
            blocks = int(route_blocks.sum())
            order_count = float(selected["_periodic_orders"].sum())
            metric_count = blocks
            payable_units = blocks
        else:
            payable_units = order_count if unit == "per_order" else route_count
            metric_count = route_count

        if unit == "per_hour":
            amount = 0.0
        else:
            amount = payable_units * unit_amount
        if not amount:
            continue

        day_names = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
        weekday_label = ", ".join(day_names.get(day, str(day)) for day in sorted(weekdays)) if weekdays else "Minden nap"
        condition_label = {
            "none": "Nincs feltétel",
            "orders_per_route": "Cím / túra",
            "routes_per_day": "Túra / nap",
            "routes_in_period": "Túra / időszak",
            "orders_in_period": "Cím / időszak",
            "every_n_routes_per_day": f"Minden {int(minimum)}. kifutott túra naponta",
            "every_n_routes_in_period": f"Minden {int(minimum)}. kifutott túra az időszakban",
            "orders_over_threshold_every_n_per_route": f"{int(minimum)} felett minden {int(maximum or 1)} cím túránként",
        }.get(condition, condition)
        rows.append({
            "Tétel": str(rule.get("fee_name") or "Időszakos díj"),
            "Napok": weekday_label,
            "Túratípus": {"normal": "Normál", "express": "Expressz", "regional": "Regionális", "any": "Bármely"}.get(rule_route_type, rule_route_type),
            "Feltétel": condition_label,
            "Darab": int(metric_count) if float(metric_count).is_integer() else metric_count,
            "Egységösszeg": unit_amount,
            "Összeg": amount,
            "Számítás": f"{int(payable_units) if float(payable_units).is_integer() else payable_units} x {format_huf(unit_amount)}",
        })

    detail_rows = pd.DataFrame(rows, columns=columns)
    total = float(detail_rows["Összeg"].sum()) if not detail_rows.empty else 0.0
    return total, detail_rows


@st.cache_data(show_spinner=False, ttl=300)
def load_periodic_fee_correction_totals(
    session_id: str | None,
    calculation_mode: str,
    period_start: date,
    period_end: date,
    warehouse_label: str | None = None,
) -> pd.DataFrame:
    columns = ["_courier_id_lookup", "_courier_name_lookup", "Korrekció"]
    if load_active_periodic_fee_rules(period_start, period_end).empty:
        return pd.DataFrame(columns=columns)

    detail = pd.DataFrame()
    normalized_mode = str(calculation_mode or "Excel").strip().casefold()
    if normalized_mode == "api":
        rows = load_api_financial_overview_rows(period_start.year, period_start.month)
        warehouse_id = settlement_warehouse_id(warehouse_label)
        if warehouse_id is not None and not rows.empty and "warehouse_id" in rows.columns:
            rows = rows.loc[
                pd.to_numeric(rows["warehouse_id"], errors="coerce").fillna(0).astype(int) == warehouse_id
            ]
        detail = api_financial_routes_to_detail(rows, None, period_start, period_end)
    elif session_id:
        try:
            rows = (
                get_db()
                .schema("settlement")
                .table("jit_row")
                .select(
                    "normalized_data,route_unique_id,route_date,weekday_iso,"
                    "calculated_day_type,courier_base_rate_huf,courier_tip_huf,"
                    "courier_delay_bonus_huf,courier_compliance_bonus_huf,"
                    "courier_bonus_total_huf,"
                    "is_route_primary,base_rate_status"
                )
                .eq("session_id", session_id)
                .eq("is_route_primary", True)
                .gte("route_date", period_start.isoformat())
                .lte("route_date", period_end.isoformat())
                .execute()
                .data
                or []
            )
        except BaseException:
            rows = []
        parsed: list[dict[str, object]] = []
        weekday_names = {1: "Hétfő", 2: "Kedd", 3: "Szerda", 4: "Csütörtök", 5: "Péntek", 6: "Szombat", 7: "Vasárnap"}
        for source in rows:
            normalized = source.get("normalized_data") or {}
            if isinstance(normalized, str):
                try:
                    normalized = json.loads(normalized)
                except json.JSONDecodeError:
                    normalized = {}
            if not isinstance(normalized, dict):
                normalized = {}
            normalized_fields = {_normalized_field_key(key): value for key, value in normalized.items()}
            source_id = next(
                (value for key, value in normalized_fields.items()
                 if key in {"courierid", "couriernumber", "driverid", "usernumber", "userid"}),
                None,
            )
            source_name = next(
                (value for key, value in normalized_fields.items()
                 if key in {"driver", "drivername", "courier", "couriername", "futar", "futarnev"}),
                None,
            )
            route_value = str(normalized.get("Route Type") or normalized.get("route_type") or "NORMAL").strip().upper()
            route_type_key = {"NORMAL": "normal", "CITY": "normal", "EXPRESS": "express", "REGIONAL": "regional"}.get(route_value, "normal")
            day_type_key = str(source.get("calculated_day_type") or "").casefold()
            parsed.append({
                "_courier_id_lookup": _courier_id_key(source_id),
                "_courier_name_lookup": _courier_match_key(source_name),
                "Route ID": str(source.get("route_unique_id") or "-"),
                "Excel dátum": str(source.get("route_date") or "-"),
                "Hét napja": weekday_names.get(source.get("weekday_iso"), "-"),
                "Túratípus": {"normal": "Normál", "express": "Expressz", "regional": "Regionális"}[route_type_key],
                "Naptípus": {"highlighted": "Kiemelt nap", "normal": "Normál nap"}.get(day_type_key, "Nincs besorolás"),
                "Rendelések": parse_huf_value(normalized.get("Orders") or normalized.get("orders")),
            })
        detail = pd.DataFrame(parsed)

    if detail.empty:
        return pd.DataFrame(columns=columns)
    if "_courier_id" in detail.columns and "_courier_id_lookup" not in detail.columns:
        detail["_courier_id_lookup"] = detail["_courier_id"].map(_courier_id_key)
    if "_courier_id_lookup" not in detail.columns:
        detail["_courier_id_lookup"] = ""
    if "_courier_name_lookup" not in detail.columns:
        detail["_courier_name_lookup"] = ""

    totals: list[dict[str, object]] = []
    group_columns = ["_courier_id_lookup", "_courier_name_lookup"]
    for (courier_id_key, courier_name_key), courier_detail in detail.groupby(group_columns, dropna=False):
        correction_total, _ = calculate_periodic_fee_corrections(
            courier_detail,
            period_start,
            period_end,
            warehouse_label,
        )
        if correction_total:
            totals.append({
                "_courier_id_lookup": str(courier_id_key or ""),
                "_courier_name_lookup": str(courier_name_key or ""),
                "Korrekció": correction_total,
            })
    if not totals:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(totals, columns=columns)


def normalize_route_key(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def route_issue_key(courier_id: str, route_id: object, order_id: object, issue_type: object) -> str:
    return "|".join([
        str(courier_id or "").strip(),
        normalize_route_key(route_id),
        str(order_id or "").strip(),
        str(issue_type or "").strip(),
    ])


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_route_stories(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    if not courier_id:
        return pd.DataFrame()
    if read_route_stories is not None:
        try:
            stories = read_route_stories(period_start, period_end, courier_id=courier_id)
            if not stories.empty:
                stories["route_id_key"] = stories["route_id"].map(normalize_route_key)
                return stories
        except BaseException:
            pass
    try:
        rows = (get_db().schema("public").table("mart_dsp_route_stories")
                .select("*").eq("courier_id", courier_id)
                .gte("work_date", period_start.isoformat())
                .lte("work_date", period_end.isoformat())
                .order("work_date").execute().data or [])
        stories = pd.DataFrame(rows)
        if not stories.empty:
            stories["route_id_key"] = stories["route_id"].map(normalize_route_key)
        return stories
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_route_issue_reviews(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    if not courier_id:
        return pd.DataFrame()
    try:
        rows = (get_db().schema("settlement").table("courier_route_issue_review")
                .select("*").eq("courier_id", courier_id)
                .gte("period_end", period_start.isoformat())
                .lte("period_start", period_end.isoformat())
                .order("updated_at", desc=True).execute().data or [])
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_route_alerts(courier_id: str, limit: int = 20) -> pd.DataFrame:
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return pd.DataFrame()
    try:
        rows = (
            get_db().schema("public").table("courier_route_alerts")
            .select("id,courier_id,courier_name,route_id,alert_type,message,status,created_at")
            .eq("courier_id", int(clean_id))
            .order("created_at", desc=True)
            .limit(int(limit))
            .execute().data or []
        )
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_route_alerts_for_period(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return pd.DataFrame()
    try:
        rows = (
            get_db().schema("public").table("courier_route_alerts")
            .select("id,courier_id,courier_name,route_id,order_id,alert_type,message,status,created_at")
            .eq("courier_id", int(clean_id))
            .gte("created_at", period_start.isoformat())
            .lt("created_at", (period_end + timedelta(days=1)).isoformat())
            .order("created_at", desc=True)
            .limit(1000)
            .execute().data or []
        )
        data = pd.DataFrame(rows)
        if not data.empty:
            data["route_id_key"] = data["route_id"].map(normalize_route_key)
        return data
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_financial_delay_rows(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return pd.DataFrame()
    try:
        rows = (
            get_db().schema("public").table("courier_financial_overview_delay")
            .select("delivery_date,route_id,warehouse_id,route_order_count,stops_count,delayed_stops_count,total_delay_minutes,max_delay_minutes,slot_miss_projected_count,rejected_stops_count")
            .eq("courier_id", int(clean_id))
            .gte("delivery_date", period_start.isoformat())
            .lte("delivery_date", period_end.isoformat())
            .or_("total_delay_minutes.gt.0,delayed_stops_count.gt.0")
            .order("delivery_date")
            .limit(1000)
            .execute().data or []
        )
        data = pd.DataFrame(rows)
        if not data.empty:
            data["route_id_key"] = data["route_id"].map(normalize_route_key)
        return data
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_financial_compliance_rows(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return pd.DataFrame()
    try:
        rows = (
            get_db().schema("public").table("courier_financial_overview_compliance")
            .select("shift_date,route_id,warehouse_id,planned_start_at,actual_start_at,route_assigned_at,shift_available_at,planned_departure_at,departed_at,warehouse_arrived_at,vehicle_plate,planned_start_delay_minutes,departure_delay_minutes,return_delay_minutes")
            .eq("courier_id", int(clean_id))
            .gte("shift_date", period_start.isoformat())
            .lte("shift_date", period_end.isoformat())
            .or_("planned_start_delay_minutes.gt.0,departure_delay_minutes.gt.0,actual_start_at.is.null,shift_available_at.is.null")
            .order("shift_date")
            .limit(1000)
            .execute().data or []
        )
        data = pd.DataFrame(rows)
        if not data.empty:
            data["route_id_key"] = data["route_id"].map(normalize_route_key)
        return data
    except BaseException:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def load_courier_api_route_statistics_rows(
    courier_id: str,
    period_start: date,
    period_end: date,
    warehouse_label: str | None = None,
) -> pd.DataFrame:
    """Load and safely combine Courier Hub route statistics rows.

    Each source is prefixed before merging, so columns with the same name from
    history, delay and compliance cannot collide during repeated merges.
    """
    clean_id = _courier_id_key(courier_id)
    if not clean_id:
        return pd.DataFrame()

    warehouse_id = settlement_warehouse_id(warehouse_label)

    def fetch_table(table_name: str, select_fields: str, date_field: str) -> pd.DataFrame:
        try:
            query = (
                get_db().schema("public").table(table_name)
                .select(select_fields)
                .eq("courier_id", int(clean_id))
                .gte(date_field, period_start.isoformat())
                .lte(date_field, period_end.isoformat())
                .order(date_field)
                .limit(5000)
            )
            if warehouse_id is not None:
                query = query.eq("warehouse_id", int(warehouse_id))
            return pd.DataFrame(query.execute().data or [])
        except BaseException:
            return pd.DataFrame()

    source_specs = [
        (
            "history",
            fetch_table(
                "courier_daily_route_history",
                "work_date,route_id,warehouse_id,order_count,stops_count,planned_start_at,actual_start_at,route_assigned_at,shift_available_at,planned_departure_at,departed_at,last_order_finished_at,warehouse_arrived_at,vehicle_plate,mileage_km,updated_at",
                "work_date",
            ),
            "work_date",
        ),
        (
            "delay",
            fetch_table(
                "courier_financial_overview_delay",
                "delivery_date,route_id,warehouse_id,route_order_count,stops_count,delayed_stops_count,total_delay_minutes,max_delay_minutes,slot_miss_projected_count,rejected_stops_count,updated_at",
                "delivery_date",
            ),
            "delivery_date",
        ),
        (
            "compliance",
            fetch_table(
                "courier_financial_overview_compliance",
                "shift_date,route_id,warehouse_id,planned_start_at,actual_start_at,route_assigned_at,shift_available_at,planned_departure_at,departed_at,last_order_finished_at,warehouse_arrived_at,vehicle_plate,mileage_km,planned_start_delay_minutes,departure_delay_minutes,return_delay_minutes,updated_at",
                "shift_date",
            ),
            "shift_date",
        ),
    ]

    prepared: list[pd.DataFrame] = []
    for source_name, frame, date_column in source_specs:
        if frame.empty:
            continue
        frame = frame.copy()
        frame["route_id_key"] = frame["route_id"].map(normalize_route_key)
        frame["warehouse_id_key"] = (
            pd.to_numeric(frame["warehouse_id"], errors="coerce").fillna(0).astype(int)
        )
        frame[f"{source_name}__stat_date"] = pd.to_datetime(
            frame[date_column], errors="coerce"
        ).dt.date

        rename_map = {
            column: f"{source_name}__{column}"
            for column in frame.columns
            if column not in {"route_id_key", "warehouse_id_key"}
        }
        prepared.append(frame.rename(columns=rename_map))

    if not prepared:
        return pd.DataFrame()

    result = prepared[0]
    for next_frame in prepared[1:]:
        result = result.merge(
            next_frame,
            on=["route_id_key", "warehouse_id_key"],
            how="outer",
            validate="one_to_one",
        )

    def coalesce(target: str, candidates: list[str]) -> None:
        existing = [column for column in candidates if column in result.columns]
        if not existing:
            return
        combined = result[existing[0]]
        for column in existing[1:]:
            combined = combined.combine_first(result[column])
        result[target] = combined

    coalesce("stat_date", [
        "history__stat_date", "delay__stat_date", "compliance__stat_date"
    ])
    coalesce("work_date", ["history__work_date", "delay__delivery_date", "compliance__shift_date"])

    shared_columns = [
        "planned_start_at", "actual_start_at", "route_assigned_at",
        "shift_available_at", "planned_departure_at", "departed_at",
        "last_order_finished_at", "warehouse_arrived_at", "vehicle_plate",
        "mileage_km", "stops_count", "updated_at",
    ]
    for column in shared_columns:
        coalesce(column, [
            f"history__{column}", f"delay__{column}", f"compliance__{column}"
        ])

    coalesce("order_count", ["history__order_count", "delay__route_order_count"])

    delay_columns = [
        "delayed_stops_count", "total_delay_minutes", "max_delay_minutes",
        "slot_miss_projected_count", "rejected_stops_count",
    ]
    for column in delay_columns:
        coalesce(column, [f"delay__{column}"])

    compliance_columns = [
        "planned_start_delay_minutes", "departure_delay_minutes",
        "return_delay_minutes",
    ]
    for column in compliance_columns:
        coalesce(column, [f"compliance__{column}"])

    result["route_id"] = result["route_id_key"]
    result["warehouse_id"] = result["warehouse_id_key"]

    sort_columns = [column for column in ["stat_date", "route_id"] if column in result.columns]
    return result.sort_values(sort_columns, kind="stable") if sort_columns else result


def render_courier_api_statistics(
    courier_id: str,
    period_start: date,
    period_end: date,
    warehouse_label: str | None,
) -> None:
    rows = load_courier_api_route_statistics_rows(
        courier_id, period_start, period_end, warehouse_label
    )

    st.markdown("#### Statisztika")
    st.caption("Forrás: Courier Hub API · a bal oldali Számítás módja: API")

    if rows.empty:
        st.info(
            "Ehhez a futárhoz és időszakhoz még nincs route performance detail adat. "
            "Futtasd le a sync_courier_route_performance_details.py szinkront."
        )
        return

    def numeric(column: str) -> pd.Series:
        if column not in rows.columns:
            return pd.Series(0.0, index=rows.index, dtype="float64")
        return pd.to_numeric(rows[column], errors="coerce").fillna(0.0)

    route_count = int(rows["route_id"].astype(str).replace("", pd.NA).dropna().nunique())
    stop_count = int(max(numeric("stops_count").sum(), numeric("order_count").sum()))
    delayed_count = int(numeric("delayed_stops_count").sum())
    delay_percent = (delayed_count / stop_count * 100.0) if stop_count else 0.0
    total_delay_minutes = int(numeric("total_delay_minutes").sum())
    max_delay_minutes = int(numeric("max_delay_minutes").max()) if len(rows) else 0

    actual_start_missing = rows.get("actual_start_at", pd.Series(index=rows.index, dtype=object)).isna()
    available_missing = rows.get("shift_available_at", pd.Series(index=rows.index, dtype=object)).isna()
    no_show_count = int((actual_start_missing | available_missing).sum())
    no_show_percent = (no_show_count / route_count * 100.0) if route_count else 0.0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Route", route_count)
    kpi2.metric("Cím / stop", stop_count)
    kpi3.metric("Késő cím", delayed_count, f"{delay_percent:.2f}%")
    kpi4.metric("No-show", no_show_count, f"{no_show_percent:.2f}%")

    kpi5, kpi6, kpi7, kpi8 = st.columns(4)
    kpi5.metric("Összes delay", f"{total_delay_minutes} perc")
    kpi6.metric("Legnagyobb delay", f"{max_delay_minutes} perc")
    kpi7.metric("Slot miss", int(numeric("slot_miss_projected_count").sum()))
    kpi8.metric("Kilométer", f"{numeric('mileage_km').sum():.1f} km")

    def display_time(value: object) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return "-"
        return parsed.strftime("%Y.%m.%d. %H:%M")

    stat_date_series = (
        rows["stat_date"]
        if "stat_date" in rows.columns
        else pd.Series(pd.NaT, index=rows.index, dtype="datetime64[ns]")
    )

    table = pd.DataFrame({
        "Dátum": pd.to_datetime(stat_date_series, errors="coerce").dt.strftime("%Y.%m.%d."),
        "Route ID": rows.get("route_id", pd.Series("", index=rows.index, dtype=str)).astype(str),
        "Raktár": rows.get("warehouse_id", pd.Series(dtype=object)).map(lambda value: f"WH{int(value)}" if pd.notna(value) and str(value) not in {"", "0"} else "-"),
        "Sorba állt": rows.get("actual_start_at", pd.Series(index=rows.index, dtype=object)).map(display_time),
        "Elérhető": rows.get("shift_available_at", pd.Series(index=rows.index, dtype=object)).map(display_time),
        "Route kiosztva": rows.get("route_assigned_at", pd.Series(index=rows.index, dtype=object)).map(display_time),
        "Indult": rows.get("departed_at", pd.Series(index=rows.index, dtype=object)).map(display_time),
        "Visszaért": rows.get("warehouse_arrived_at", pd.Series(index=rows.index, dtype=object)).map(display_time),
        "Cím": numeric("stops_count").astype(int),
        "Késő cím": numeric("delayed_stops_count").astype(int),
        "Delay perc": numeric("total_delay_minutes").astype(int),
        "Max delay": numeric("max_delay_minutes").astype(int),
        "No-show": (actual_start_missing | available_missing).map({True: "Igen", False: "Nem"}),
        "KM": numeric("mileage_km").round(1),
    })
    st.dataframe(table, use_container_width=True, hide_index=True, height=420)

    previous_month_end = period_start.replace(day=1) - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    previous_rows = load_courier_api_route_statistics_rows(
        courier_id, previous_month_start, previous_month_end, warehouse_label
    )

    st.markdown("##### Előző havi teljesítés")
    st.caption(
        f"Időszak: {previous_month_start:%Y.%m.%d.} – {previous_month_end:%Y.%m.%d.}"
    )

    if previous_rows.empty:
        st.info("Az előző hónaphoz még nincs megjeleníthető Courier Hub route statisztika.")
    else:
        previous_stops = pd.to_numeric(
            previous_rows.get(
                "stops_count",
                pd.Series(0, index=previous_rows.index, dtype="float64"),
            ),
            errors="coerce",
        ).fillna(0.0)
        previous_orders = pd.to_numeric(
            previous_rows.get(
                "order_count",
                pd.Series(0, index=previous_rows.index, dtype="float64"),
            ),
            errors="coerce",
        ).fillna(0.0)
        previous_delayed = pd.to_numeric(
            previous_rows.get(
                "delayed_stops_count",
                pd.Series(0, index=previous_rows.index, dtype="float64"),
            ),
            errors="coerce",
        ).fillna(0.0)

        previous_stop_count = int(max(previous_stops.sum(), previous_orders.sum()))
        previous_delayed_count = min(int(previous_delayed.sum()), previous_stop_count)
        previous_on_time_count = max(previous_stop_count - previous_delayed_count, 0)

        if previous_stop_count <= 0:
            st.info("Az előző hónap route-jaihoz nincs cím/stop darabszám.")
        else:
            chart_col, metric_col = st.columns([0.58, 0.42], gap="large")
            with chart_col:
                chart_data = pd.DataFrame(
                    {
                        "Állapot": ["Időben", "Késő"],
                        "Darabszám": [previous_on_time_count, previous_delayed_count],
                    }
                )
                st.vega_lite_chart(
                    chart_data,
                    {
                        "title": "Előző havi időablakos teljesítés",
                        "mark": {"type": "arc", "innerRadius": 70},
                        "encoding": {
                            "theta": {"field": "Darabszám", "type": "quantitative"},
                            "color": {
                                "field": "Állapot",
                                "type": "nominal",
                                "legend": {"orient": "bottom"},
                            },
                            "tooltip": [
                                {"field": "Állapot", "type": "nominal"},
                                {"field": "Darabszám", "type": "quantitative"},
                            ],
                        },
                        "view": {"stroke": None},
                    },
                    use_container_width=True,
                )
                st.caption(f"Összesen: {previous_stop_count} cím / stop")

            with metric_col:
                previous_delay_percent = (
                    previous_delayed_count / previous_stop_count * 100.0
                )
                st.metric("Előző havi cím / stop", previous_stop_count)
                st.metric(
                    "Előző havi késő cím",
                    previous_delayed_count,
                    f"{previous_delay_percent:.2f}%",
                )
                st.metric("Előző havi időben teljesített", previous_on_time_count)


def save_route_issue_review(
    session_id: str | None,
    courier_id: str,
    period_start: date,
    period_end: date,
    issue_row: dict[str, object],
    status: str,
    note: str,
) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    payload = {
        "issue_key": issue_row["issue_key"],
        "session_id": session_id,
        "courier_id": courier_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "route_id": normalize_route_key(issue_row.get("Route ID")),
        "order_id": str(issue_row.get("Order ID") or "").strip() or None,
        "issue_type": str(issue_row.get("Probléma") or ""),
        "status": status,
        "note": note.strip() or None,
        "updated_by": actor,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    get_db().schema("settlement").table("courier_route_issue_review").upsert(
        payload,
        on_conflict="issue_key",
    ).execute()
    get_db().schema("settlement").table("courier_route_issue_review_event").insert({
        "issue_key": issue_row["issue_key"],
        "session_id": session_id,
        "courier_id": courier_id,
        "route_id": payload["route_id"],
        "order_id": payload["order_id"],
        "issue_type": payload["issue_type"],
        "status": status,
        "note": payload["note"],
        "performed_by": actor,
    }).execute()
    load_route_issue_reviews.clear()


def build_route_issue_rows(
    route_detail: pd.DataFrame,
    stories: pd.DataFrame,
    order_details: pd.DataFrame,
    reviews: pd.DataFrame,
    courier_id: str,
    delay_rows: pd.DataFrame | None = None,
    compliance_rows: pd.DataFrame | None = None,
    route_alerts: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "issue_key", "Route ID", "Order ID", "Dátum", "Probléma", "Eltérés perc",
        "Rendelések", "Késedelmi díj", "Túramegfelelés", "Futár jelzett",
        "Bejelentés", "Story", "Státusz", "Megjegyzés",
    ]
    delay_rows = delay_rows if delay_rows is not None else pd.DataFrame()
    compliance_rows = compliance_rows if compliance_rows is not None else pd.DataFrame()
    route_alerts = route_alerts if route_alerts is not None else pd.DataFrame()
    if route_detail.empty and stories.empty and order_details.empty and delay_rows.empty and compliance_rows.empty and route_alerts.empty:
        return pd.DataFrame(columns=columns)

    route_lookup: dict[str, dict[str, object]] = {}
    if not route_detail.empty:
        detail = route_detail.copy()
        detail["route_id_key"] = detail["Route ID"].map(normalize_route_key)
        route_lookup = {
            row["route_id_key"]: row.to_dict()
            for _, row in detail.iterrows()
        }

    story_lookup: dict[str, dict[str, object]] = {}
    if not stories.empty:
        story_lookup = {
            normalize_route_key(row.get("route_id")): row
            for row in stories.to_dict("records")
        }

    alert_lookup: dict[str, list[dict[str, object]]] = {}
    if not route_alerts.empty:
        for alert in route_alerts.to_dict("records"):
            alert_lookup.setdefault(normalize_route_key(alert.get("route_id")), []).append(alert)

    def alert_summary(route_id: object) -> tuple[str, str]:
        alerts = alert_lookup.get(normalize_route_key(route_id), [])
        if not alerts:
            return "Nem", ""
        type_labels = {"delay": "Késés", "problem": "Probléma", "bag_missing": "Táska hiány"}
        parts = []
        for alert in alerts[:3]:
            label = type_labels.get(str(alert.get("alert_type") or ""), str(alert.get("alert_type") or "Bejelentés"))
            message = str(alert.get("message") or "").strip()
            created = str(alert.get("created_at") or "")[:16]
            parts.append(f"{created} {label}: {message}" if message else f"{created} {label}")
        return "Igen", " | ".join(parts)

    rows: list[dict[str, object]] = []

    if not order_details.empty:
        order_data = order_details.copy()
        order_data["route_id_key"] = order_data["route_id"].map(normalize_route_key)
        for _, order in order_data.iterrows():
            window_delta = parse_huf_value(order.get("time_window_delta_minutes"))
            if window_delta <= 0:
                continue
            route_id = normalize_route_key(order.get("route_id"))
            route_row = route_lookup.get(route_id, {})
            story_row = story_lookup.get(route_id, {})
            issue_type = "Késő rendelés"
            order_id = str(order.get("order_id") or order.get("checkpoint_id") or "").strip()
            rows.append({
                "issue_key": route_issue_key(courier_id, route_id, order_id, issue_type),
                "Route ID": route_id,
                "Order ID": order_id,
                "Dátum": str(order.get("work_date") or route_row.get("Excel dátum") or story_row.get("work_date") or ""),
                "Probléma": issue_type,
                "Eltérés perc": int(window_delta),
                "Rendelések": parse_huf_value(route_row.get("Rendelések")),
                "Késedelmi díj": parse_huf_value(route_row.get("Késedelmi díj")),
                "Túramegfelelés": parse_huf_value(route_row.get("Túramegfelelés")),
                "Futár jelzett": alert_summary(route_id)[0],
                "Bejelentés": alert_summary(route_id)[1],
                "Story": str(story_row.get("story_text") or order.get("time_window_status") or ""),
                "Státusz": "Nincs reklamáció",
                "Megjegyzés": "",
            })

    route_ids = set(route_lookup) | set(story_lookup)
    for route_id in sorted(route_ids):
        route_row = route_lookup.get(route_id, {})
        story_row = story_lookup.get(route_id, {})
        queue_delta = parse_huf_value(story_row.get("queue_entry_delta_minutes"))
        next_shift_delta = parse_huf_value(story_row.get("next_shift_delay_minutes"))
        late_count = parse_huf_value(story_row.get("time_window_late_count"))
        delay_fee = parse_huf_value(route_row.get("Késedelmi díj"))
        compliance_fee = parse_huf_value(route_row.get("Túramegfelelés"))
        assignment_mode = str(story_row.get("assignment_mode") or "").casefold()
        route_problems: list[tuple[str, float]] = []
        if queue_delta > 0:
            route_problems.append(("Késő sorba állás", queue_delta))
        if "manual" in assignment_mode or "manualis" in assignment_mode:
            route_problems.append(("Nem látszik sorba állás", 0))
        if next_shift_delta > 0:
            route_problems.append(("Következő műszak késés", next_shift_delta))
        if late_count > 0 and not any(row["Route ID"] == route_id and row["Probléma"] == "Késő rendelés" for row in rows):
            route_problems.append(("Késő rendelés", late_count))
        for issue_type, delta in route_problems:
            rows.append({
                "issue_key": route_issue_key(courier_id, route_id, "", issue_type),
                "Route ID": route_id,
                "Order ID": "",
                "Dátum": str(route_row.get("Excel dátum") or story_row.get("work_date") or ""),
                "Probléma": issue_type,
                "Eltérés perc": int(delta),
                "Rendelések": parse_huf_value(route_row.get("Rendelések") or story_row.get("address_count")),
                "Késedelmi díj": delay_fee,
                "Túramegfelelés": compliance_fee,
                "Futár jelzett": alert_summary(route_id)[0],
                "Bejelentés": alert_summary(route_id)[1],
                "Story": str(story_row.get("story_text") or ""),
                "Státusz": "Nincs reklamáció",
                "Megjegyzés": "",
            })

    for _, delay_row in delay_rows.iterrows():
        route_id = normalize_route_key(delay_row.get("route_id"))
        route_row = route_lookup.get(route_id, {})
        alerted, alert_text = alert_summary(route_id)
        rows.append({
            "issue_key": route_issue_key(courier_id, route_id, "", "API késés"),
            "Route ID": route_id,
            "Order ID": "",
            "Dátum": str(delay_row.get("delivery_date") or route_row.get("Excel dátum") or ""),
            "Probléma": "API késés",
            "Eltérés perc": int(parse_huf_value(delay_row.get("total_delay_minutes"))),
            "Rendelések": parse_huf_value(delay_row.get("route_order_count") or route_row.get("Rendelések")),
            "Késedelmi díj": parse_huf_value(route_row.get("Késedelmi díj")),
            "Túramegfelelés": parse_huf_value(route_row.get("Túramegfelelés")),
            "Futár jelzett": alerted,
            "Bejelentés": alert_text,
            "Story": f"{int(parse_huf_value(delay_row.get('delayed_stops_count')))} késéses cím, max {int(parse_huf_value(delay_row.get('max_delay_minutes')))} perc",
            "Státusz": "Nincs reklamáció",
            "Megjegyzés": "",
        })

    for _, compliance_row in compliance_rows.iterrows():
        route_id = normalize_route_key(compliance_row.get("route_id"))
        route_row = route_lookup.get(route_id, {})
        start_delay = parse_huf_value(compliance_row.get("planned_start_delay_minutes"))
        departure_delay = parse_huf_value(compliance_row.get("departure_delay_minutes"))
        has_checkin = str(compliance_row.get("actual_start_at") or compliance_row.get("shift_available_at") or "").strip()
        issue_type = "No-show / nincs bejelentkezés" if not has_checkin else "Késő bejelentkezés"
        alerted, alert_text = alert_summary(route_id)
        rows.append({
            "issue_key": route_issue_key(courier_id, route_id, "", issue_type),
            "Route ID": route_id,
            "Order ID": "",
            "Dátum": str(compliance_row.get("shift_date") or route_row.get("Excel dátum") or ""),
            "Probléma": issue_type,
            "Eltérés perc": int(max(start_delay, departure_delay, 0)),
            "Rendelések": parse_huf_value(route_row.get("Rendelések")),
            "Késedelmi díj": parse_huf_value(route_row.get("Késedelmi díj")),
            "Túramegfelelés": parse_huf_value(route_row.get("Túramegfelelés")),
            "Futár jelzett": alerted,
            "Bejelentés": alert_text,
            "Story": f"Tervezett kezdés: {compliance_row.get('planned_start_at') or '-'} | Elérhető: {compliance_row.get('shift_available_at') or compliance_row.get('actual_start_at') or '-'} | Indulás eltérés: {int(departure_delay)} perc",
            "Státusz": "Nincs reklamáció",
            "Megjegyzés": "",
        })

    result = pd.DataFrame(rows, columns=columns).drop_duplicates("issue_key")
    if result.empty:
        return result
    if not reviews.empty:
        review_lookup = {
            str(row.get("issue_key")): row
            for row in reviews.to_dict("records")
        }
        result["Státusz"] = result.apply(
            lambda row: review_lookup.get(row["issue_key"], {}).get("status") or row["Státusz"],
            axis=1,
        )
        result["Megjegyzés"] = result.apply(
            lambda row: review_lookup.get(row["issue_key"], {}).get("note") or row["Megjegyzés"],
            axis=1,
        )
    return result.sort_values(["Dátum", "Route ID", "Order ID", "Probléma"])


@st.cache_data(show_spinner=False, ttl=60)
def load_settlement_month(session_id: str | None) -> tuple[date, date]:
    if session_id:
        try:
            rows = (get_db().schema("settlement").table("jit_row").select("route_date")
                    .eq("session_id", session_id).not_.is_("route_date", "null")
                    .order("route_date").limit(1).execute().data or [])
            if rows and rows[0].get("route_date"):
                route_date = date.fromisoformat(str(rows[0]["route_date"])[:10])
                start = route_date.replace(day=1)
                next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                return start, next_month - timedelta(days=1)
        except BaseException:
            pass
    start = date.today().replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(days=1)


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_adjustments(courier_id: str, period_start: date, period_end: date) -> pd.DataFrame:
    if not courier_id:
        return pd.DataFrame(columns=["adjustment_type", "amount_huf", "effective_date", "note"])
    try:
        rows = (get_db().schema("settlement").table("courier_settlement_adjustment")
                .select("id,adjustment_type,amount_huf,effective_date,valid_from,valid_to,note,created_by,created_at")
                .eq("courier_id", courier_id)
                .eq("is_active", True).is_("deleted_at", "null").execute().data or [])
    except BaseException:
        return pd.DataFrame(columns=["adjustment_type", "amount_huf", "effective_date", "note"])
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    try:
        from_values = data["valid_from"] if "valid_from" in data.columns else pd.Series(pd.NaT, index=data.index)
        effective_values = data["effective_date"] if "effective_date" in data.columns else pd.Series(pd.NaT, index=data.index)
        to_values = data["valid_to"] if "valid_to" in data.columns else pd.Series(pd.NaT, index=data.index)
        valid_from = pd.to_datetime(from_values, errors="coerce").fillna(pd.to_datetime(effective_values, errors="coerce"))
        valid_to = pd.to_datetime(to_values, errors="coerce")
        period_start_ts, period_end_ts = pd.Timestamp(period_start), pd.Timestamp(period_end)
        data = data.loc[(valid_from <= period_end_ts) & (valid_to.isna() | (valid_to >= period_start_ts))].copy()
        data["valid_from"] = valid_from.loc[data.index].dt.date
        data["valid_to"] = valid_to.loc[data.index].dt.date
        return data
    except (TypeError, ValueError, KeyError):
        return pd.DataFrame(columns=["id", "adjustment_type", "amount_huf", "effective_date", "valid_from", "valid_to", "note"])


def save_courier_adjustment(session_id: str | None, courier_id: str, adjustment_type: str, amount_huf: float, note: str, valid_from: date, valid_to: date | None) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    existing = load_courier_adjustments(courier_id, valid_from, valid_to or valid_from)
    same_end = existing["valid_to"].isna() if valid_to is None else existing["valid_to"] == valid_to
    duplicate = existing.loc[(existing["adjustment_type"] == adjustment_type) & (existing["amount_huf"].astype(float) == float(amount_huf)) & (existing["note"].fillna("") == (note.strip() or "")) & (existing["valid_from"] == valid_from) & same_end]
    if not duplicate.empty:
        return
    get_db().schema("settlement").table("courier_settlement_adjustment").insert({
        "session_id": session_id, "courier_id": courier_id, "adjustment_type": adjustment_type,
        "amount_huf": float(amount_huf), "note": note.strip() or None, "effective_date": valid_from.isoformat(),
        "valid_from": valid_from.isoformat(), "valid_to": valid_to.isoformat() if valid_to else None,
        "created_by": actor,
    }).execute()
    get_db().schema("settlement").table("courier_settlement_adjustment_event").insert({
        "session_id": session_id, "courier_id": courier_id, "event_type": "created",
        "adjustment_type": adjustment_type, "amount_huf": float(amount_huf),
        "note": note.strip() or None, "performed_by": actor,
    }).execute()
    load_courier_adjustments.clear()
    load_courier_adjustment_log.clear()


def update_courier_adjustment(
    session_id: str | None,
    courier_id: str,
    adjustment_id: str,
    adjustment_type: str,
    amount_huf: float,
    note: str,
    valid_from: date,
    valid_to: date | None,
    old_values: dict[str, object],
) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    get_db().schema("settlement").table("courier_settlement_adjustment").update({
        "adjustment_type": adjustment_type,
        "amount_huf": float(amount_huf),
        "note": note.strip() or None,
        "effective_date": valid_from.isoformat(),
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat() if valid_to else None,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", adjustment_id).execute()
    change_note = (
        f"Módosítva: {old_values.get('adjustment_type')} {format_huf(parse_huf_value(old_values.get('amount_huf')))} "
        f"-> {adjustment_type} {format_huf(amount_huf)}; megjegyzés: {note.strip() or '-'}"
    )
    get_db().schema("settlement").table("courier_settlement_adjustment_event").insert({
        "session_id": session_id, "courier_id": courier_id, "event_type": "updated",
        "adjustment_type": adjustment_type, "amount_huf": float(amount_huf),
        "note": change_note, "performed_by": actor,
    }).execute()
    load_courier_adjustments.clear()
    load_courier_adjustment_log.clear()


def delete_courier_adjustment(session_id: str | None, courier_id: str, adjustment_id: str, adjustment_type: str, amount_huf: float, note: str) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    get_db().schema("settlement").table("courier_settlement_adjustment").update({
        "is_active": False,
        "deleted_at": pd.Timestamp.utcnow().isoformat(),
        "deleted_by": actor,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }).eq("id", adjustment_id).execute()
    get_db().schema("settlement").table("courier_settlement_adjustment_event").insert({
        "session_id": session_id, "courier_id": courier_id, "event_type": "deleted",
        "adjustment_type": adjustment_type, "amount_huf": float(amount_huf),
        "note": note.strip() or "Korrekciós sor törölve", "performed_by": actor,
    }).execute()
    load_courier_adjustments.clear()
    load_courier_adjustment_log.clear()


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_adjustment_log(courier_id: str) -> pd.DataFrame:
    if not courier_id:
        return pd.DataFrame()
    try:
        rows = (get_db().schema("settlement").table("courier_settlement_adjustment_event")
                .select("event_type,adjustment_type,amount_huf,note,performed_by,created_at")
                .eq("courier_id", courier_id)
                .order("created_at", desc=True).execute().data or [])
        return pd.DataFrame(rows)
    except BaseException:
        return pd.DataFrame()


def reset_courier_adjustments(session_id: str | None, courier_id: str, period_start: date, period_end: date) -> None:
    actor = str(st.session_state.get("user", {}).get("username") or "unknown")
    adjustments = load_courier_adjustments(courier_id, period_start, period_end)
    for adjustment_id in adjustments.get("id", pd.Series(dtype=str)):
        get_db().schema("settlement").table("courier_settlement_adjustment").update({
            "is_active": False, "deleted_at": pd.Timestamp.utcnow().isoformat(), "deleted_by": actor,
        }).eq("id", adjustment_id).execute()
    get_db().schema("settlement").table("courier_settlement_adjustment_event").insert({
        "session_id": session_id, "courier_id": courier_id, "event_type": "reset",
        "note": "Kézi havi korrekciók visszaállítása", "performed_by": actor,
    }).execute()
    load_courier_adjustments.clear()
    load_courier_adjustment_log.clear()


def refresh_settlement_profile_data() -> None:
    load_api_financial_overview_rows.clear()
    load_latest_api_jit_session_id.clear()
    load_excel_courier_base_rates.clear()
    load_excel_base_rate_diagnostics.clear()
    load_active_bonus_level_rules.clear()
    load_courier_route_detail.clear()
    load_imported_balance_components.clear()
    load_courier_settlement_summary.clear()
    load_courier_settlement_summary_row.clear()
    load_courier_adjustments.clear()
    load_courier_adjustment_log.clear()
    load_target_reserve_monthly.clear()
    load_courier_monthly_closure.clear()
    load_salary_advance_installments_for_month.clear()
    load_courier_salary_advance_history.clear()
    load_customer_rating_bonus_rows.clear()
    load_courier_master.clear()


def render_bonus_malus_manager(courier_id: str, adjustment_type: str) -> None:
    """The Bonus and Malus menus use the same persistent, period-aware rows."""
    title = "Bónuszok" if adjustment_type == "bonus" else "Máluszok"
    singular = "Bónusz" if adjustment_type == "bonus" else "Málusz"
    session_id = st.session_state.get("settlement_import_session_id") or load_latest_jit_session_id()
    period_start, period_end = load_settlement_month(session_id)
    rows = load_courier_adjustments(courier_id, period_start, period_end)
    rows = rows.loc[rows.get("adjustment_type", pd.Series(index=rows.index, dtype=str)) == adjustment_type].copy()
    st.markdown(f"#### {title}")
    left, right = st.columns([1.35, 0.65])
    with left:
        if rows.empty:
            st.info(f"Nincs rögzített {singular.lower()} az aktuális elszámolási hónapra.")
        elif selected_component in {"loyalty", "instructor", "manual"}:
            st.info("Ehhez a tételhez az aktuális elszámolási időszakban nincs rögzített, kifizethető DB-adat.")
        else:
            view = rows.rename(columns={"effective_date": "Kezdete", "valid_to": "Vége", "amount_huf": "Összeg", "note": "Megjegyzés", "created_by": "Létrehozta", "created_at": "Létrehozva"}).copy()
            view["Összeg"] = view["Összeg"].map(format_huf)
            st.dataframe(view[["Kezdete", "Vége", "Összeg", "Megjegyzés", "Létrehozta", "Létrehozva"]], use_container_width=True, hide_index=True)
    with right:
        with st.form(f"{adjustment_type}_form_{courier_id}"):
            st.text_input("Megnevezés / megjegyzés", key=f"{adjustment_type}_note_{courier_id}")
            amount = st.number_input("Összeg (Ft)", min_value=0, step=100, key=f"{adjustment_type}_amount_{courier_id}")
            valid_from = st.date_input("Érvényes ettől", value=period_start, key=f"{adjustment_type}_from_{courier_id}")
            has_end = st.checkbox("Van záródátum", value=True, key=f"{adjustment_type}_has_end_{courier_id}")
            valid_to = st.date_input("Érvényes eddig", value=period_end, key=f"{adjustment_type}_to_{courier_id}")
            saved = st.form_submit_button(f"{singular} mentése", type="primary")
        if saved:
            if has_end and valid_to < valid_from:
                st.error("A záródátum nem lehet korábbi a kezdő dátumnál.")
            else:
                try:
                    save_courier_adjustment(session_id, courier_id, adjustment_type, amount, st.session_state[f"{adjustment_type}_note_{courier_id}"], valid_from, valid_to if has_end else None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"A mentés nem sikerült: {exc}")


def render_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nincs találat a megadott szűrőkkel.")
        return

    st.markdown(
        """
        <div class="courier-list-header">
        <div>Futár</div><div>Branch</div><div>Számítás</div>
        <div>Nettó</div><div>Borravaló</div><div>Kifizetendő</div><div>Státusz</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for i, row in df.reset_index(drop=True).iterrows():
        audit_status = str(row.get("Route audit status") or "").strip().casefold()
        audit_ok_raw = row.get("Route audit ok")
        audit_has_result = audit_status != "" and not pd.isna(audit_ok_raw)
        shift_late_audit_ok_raw = row.get("Shift late audit ok")
        shift_late_audit_has_result = bool(row.get("Shift late audit has result")) and not pd.isna(shift_late_audit_ok_raw)
        delay_audit_ok_raw = row.get("Delay audit ok")
        delay_audit_has_result = bool(row.get("Delay audit has result")) and not pd.isna(delay_audit_ok_raw)
        no_show_audit_ok_raw = row.get("No show audit ok")
        no_show_audit_has_result = bool(row.get("No show audit has result")) and not pd.isna(no_show_audit_ok_raw)

        left_audit_has_result = shift_late_audit_has_result or audit_has_result
        left_audit_ok = False
        if shift_late_audit_has_result:
            left_audit_ok = bool(shift_late_audit_ok_raw)
        elif audit_has_result:
            left_audit_ok = bool(audit_ok_raw)
        if left_audit_has_result:
            audit_color = "#16A34A" if left_audit_ok else "#DC2626"
            audit_bg = "rgba(22, 163, 74, 0.08)" if left_audit_ok else "rgba(220, 38, 38, 0.08)"
            st.markdown(
                f"""
                <style>
                [class*="st-key-courier_row_{i}"] {{
                    border-left: 7px solid {audit_color} !important;
                    border-color: {audit_color}66 !important;
                    box-shadow: inset 7px 0 0 {audit_bg};
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
        right_audit_has_result = no_show_audit_has_result or delay_audit_has_result
        right_audit_ok = False
        if no_show_audit_has_result:
            right_audit_ok = bool(no_show_audit_ok_raw)
        elif delay_audit_has_result:
            right_audit_ok = bool(delay_audit_ok_raw)
        if right_audit_has_result:
            delay_audit_color = "#16A34A" if right_audit_ok else "#DC2626"
            delay_audit_bg = "rgba(22, 163, 74, 0.08)" if right_audit_ok else "rgba(220, 38, 38, 0.08)"
            st.markdown(
                f"""
                <style>
                [class*="st-key-courier_row_{i}"] {{
                    border-right: 7px solid {delay_audit_color} !important;
                    box-shadow: inset -7px 0 0 {delay_audit_bg};
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
        with st.container(border=True, key=f"courier_row_{i}"):
            cols = st.columns(
                [1.45, 0.75, 0.85, 1, 1, 1, 0.9],
                vertical_alignment="center",
            )

            courier_label = f"{row['Futár']} · {row['Courier ID']}"
            if cols[0].button(
                courier_label,
                key=f"courier_{row['Courier ID']}_{i}",
                use_container_width=True,
                help=f"Raktár: {row['Raktár'] or 'BUD1'}",
            ):
                st.session_state["selected_courier_id"] = str(row["Courier ID"])
                show_courier_dialog()
            audit_text = str(row.get("Route audit text") or "").strip()
            if audit_text:
                cols[0].caption(audit_text)
            shift_late_audit_text = str(row.get("Shift late audit text") or "").strip()
            if shift_late_audit_text:
                cols[0].caption(shift_late_audit_text)
            delay_audit_text = str(row.get("Delay audit text") or "").strip()
            if delay_audit_text:
                cols[0].caption(delay_audit_text)
            no_show_audit_text = str(row.get("No show audit text") or "").strip()
            if no_show_audit_text:
                cols[0].caption(no_show_audit_text)

            cols[1].caption(str(row["Branch"]))
            cols[2].caption(str(row["Számítás módja"]))
            cols[3].caption(format_huf(row["Nettó bevétel"]))
            cols[4].caption(format_huf(row["Borravaló"]))
            cols[5].markdown(f"**{format_huf(row['Kifizetendő'])}**")

            badge, led = status_meta(str(row["Státusz"]))
            cols[6].markdown(
                f'<span class="status-badge {badge}"><span class="led {led}"></span>{html.escape(str(row["Státusz"]))}</span>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<div class="courier-list-footer">{len(df)} megjelenített futár</div>',
        unsafe_allow_html=True,
    )


def render_fast_courier_profile(
    *,
    courier_id: str,
    courier_name: str,
    row: pd.Series,
    period_start: date,
    menu_key: str,
    menu_target_key: str,
) -> None:
    profile = load_courier_profile(courier_id)
    reserve_status = load_target_reserve_status(courier_id, courier_name)
    efo_assignment = load_active_efo_assignment(courier_id, date.today())
    loyalty_required_months = load_loyalty_month_requirement_for_date(period_start)
    resolved_work_start, work_start_source, _loyalty_profile = resolve_loyalty_work_start(profile, courier_name)
    work_months = completed_months_between(resolved_work_start, period_start)
    employment_type = str(profile.get("employment_type") or "egyeni_vallalkozo").strip()
    if employment_type not in EMPLOYMENT_TYPE_LABELS:
        employment_type = "egyeni_vallalkozo"
    if work_months < 0:
        loyalty_status = "Hiányzik a munkakezdés"
    elif work_months >= loyalty_required_months:
        loyalty_status = "Beleszámít"
    else:
        loyalty_status = f"Még nem jogosult ({work_months}/{loyalty_required_months} hónap)"

    initials = "".join(part[:1].upper() for part in courier_name.split()[:2]) or "F"
    st.markdown(
        f"""
        <div class="settlement-profile-shell">
        <div class="settlement-profile-top">
            <div class="settlement-driver">
            <div class="settlement-avatar">{html.escape(initials)}</div>
            <div>
                <div class="settlement-name">{html.escape(courier_name)}</div>
                <div class="settlement-meta-grid">
                <div class="settlement-meta-item"><div class="settlement-meta-label">Futár azonosító</div><div class="settlement-meta-value">{html.escape(courier_id)}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Raktár</div><div class="settlement-meta-value">{html.escape(str(row.get('Raktár') or profile.get('warehouse_name') or '-'))}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Jogviszony</div><div class="settlement-chip">{html.escape(EMPLOYMENT_TYPE_LABELS.get(employment_type, employment_type))}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Biztosítás</div><div class="settlement-meta-value">{'Van' if reserve_status.get('insurance_active') else 'Nincs'}</div></div>
                </div>
            </div>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    profile_menu_items = ["Áttekintés", "Pénzügy", "Kifizetés", "Fizetés előleg", "Útvonalak"]
    if str(st.session_state.get("new_calculation_mode", "API")).strip().casefold() == "api":
        profile_menu_items.append("Statisztika")
    profile_menu_items.extend(["Dokumentumok", "Egyedi dokumentum", "Reklamációk", "Profil"])
    selected_menu = st.radio(
        "Futármenü",
        profile_menu_items,
        horizontal=True,
        label_visibility="collapsed",
        key=menu_key,
    )
    if selected_menu != "Profil":
        st.session_state[menu_target_key] = selected_menu
        st.rerun()

    st.markdown("#### Profil")
    st.caption("Gyors profilnézet: csak a profilhoz szükséges DB adatok töltődnek be.")
    edit_key = f"profile_edit_mode_{courier_id}"
    is_editing = bool(st.session_state.get(edit_key, False))

    def enable_profile_edit() -> None:
        st.session_state[edit_key] = True
        st.session_state[menu_target_key] = "Profil"

    def cancel_profile_edit() -> None:
        st.session_state[edit_key] = False
        st.session_state[menu_target_key] = "Profil"

    profile1, profile2 = st.columns(2)
    with profile1:
        profile_courier_name = st.text_input("Név", value=str(profile.get("courier_name") or courier_name), disabled=not is_editing, key=f"fast_profile_name_{courier_id}")
        st.text_input("Courier ID", value=courier_id, disabled=True, key=f"fast_profile_id_{courier_id}")
        phone_number = st.text_input("Telefonszám", value=str(profile.get("phone_number") or ""), disabled=not is_editing, key=f"fast_profile_phone_{courier_id}")
        email = st.text_input("E-mail", value=str(profile.get("email") or ""), disabled=not is_editing, key=f"fast_profile_email_{courier_id}")
        warehouse_name = st.text_input("Raktár", value=str(profile.get("warehouse_name") or row.get("Raktár") or ""), disabled=not is_editing, key=f"fast_profile_warehouse_{courier_id}")
        billing_email = st.text_input("Számlázási e-mail", value=str(profile.get("billing_email") or ""), disabled=not is_editing, key=f"fast_profile_billing_email_{courier_id}")
        work_start_date = st.date_input(
            "Munkakezdés dátuma",
            value=resolved_work_start or date.today(),
            disabled=not is_editing,
            key=f"fast_profile_work_start_{courier_id}",
        )
        st.caption(f"ForrĂˇs: {work_start_source}")
        employment_options = list(EMPLOYMENT_TYPE_LABELS)
        employment_type = st.selectbox(
            "Jogviszony",
            employment_options,
            index=employment_options.index(employment_type),
            format_func=lambda value: EMPLOYMENT_TYPE_LABELS.get(value, value),
            disabled=not is_editing,
            key=f"fast_profile_employment_type_{courier_id}",
        )
        employment_note = st.text_input("Jogviszony megjegyzés", value=str(profile.get("employment_note") or ""), disabled=not is_editing, key=f"fast_profile_employment_note_{courier_id}")
        st.text_input("Lojalitási bónusz", value=loyalty_status, disabled=True, key=f"fast_profile_loyalty_status_{courier_id}")

    with profile2:
        st.text_input("Számítás módja", value=str(row.get("Számítás módja") or ""), disabled=True, key=f"fast_profile_calc_{courier_id}")
        company_name = st.text_input("Vállalkozás neve", value=str(profile.get("company_name") or ""), disabled=not is_editing, key=f"fast_profile_company_{courier_id}")
        company_address = st.text_input("Vállalkozás címe", value=str(profile.get("company_address") or ""), disabled=not is_editing, key=f"fast_profile_company_address_{courier_id}")
        tax_number = st.text_input("Adószám", value=str(profile.get("tax_number") or ""), disabled=not is_editing, key=f"fast_profile_tax_{courier_id}")
        bank_account_number = st.text_input("Bankszámlaszám", value=str(profile.get("bank_account_number") or ""), disabled=not is_editing, key=f"fast_profile_bank_{courier_id}")
        vat_status = st.text_input("ÁFA státusz", value=str(profile.get("vat_status") or ""), disabled=not is_editing, key=f"fast_profile_vat_status_{courier_id}")
        efo_status = "Nincs aktuális EFO bejelentés"
        if efo_assignment:
            efo_end = str(efo_assignment.get("valid_to") or "folyamatos")
            efo_status = f"Bejelentve: {efo_assignment.get('valid_from')} - {efo_end}, napi levonás {format_huf(parse_huf_value(efo_assignment.get('daily_deduction_huf')))}"
        st.text_input("EFO státusz", value=efo_status, disabled=True, key=f"fast_profile_efo_status_{courier_id}")
        st.text_input("Biztosítás", value="Van" if reserve_status.get("insurance_active") else "Nincs", disabled=True, key=f"fast_profile_insurance_{courier_id}")
        st.text_input("Profil státusz", value="Aktív" if bool(profile.get("active", True)) else "Inaktív", disabled=True, key=f"fast_profile_status_{courier_id}")

    profile_actions = st.columns(3)
    if not is_editing:
        profile_actions[0].button("Profil szerkesztése", type="primary", use_container_width=True, key=f"fast_profile_edit_{courier_id}", on_click=enable_profile_edit)
    if is_editing and profile_actions[0].button("Profil mentése", type="primary", use_container_width=True, key=f"fast_profile_save_{courier_id}"):
        new_fields = {
            "courier_name": profile_courier_name,
            "phone_number": phone_number,
            "email": email,
            "warehouse_name": warehouse_name,
            "billing_email": billing_email,
            "work_start_date": work_start_date.isoformat() if work_start_date else "",
            "employment_type": employment_type,
            "employment_note": employment_note,
            "company_name": company_name,
            "company_address": company_address,
            "tax_number": tax_number,
            "bank_account_number": bank_account_number,
            "vat_status": vat_status,
        }
        changes = {field: {"old": str(profile.get(field) or ""), "new": str(value or "")} for field, value in new_fields.items() if str(profile.get(field) or "") != str(value or "")}
        try:
            if changes:
                update_courier_master_profile(courier_id, new_fields)
                log_profile_change(courier_id, changes)
            st.session_state[edit_key] = False
            st.session_state[menu_target_key] = "Profil"
            load_courier_profile.clear()
            load_active_efo_assignment.clear()
            load_muszakpro_booking_summary.clear()
            load_loyalty_profile_lookup.clear()
            load_loyalty_month_requirement_for_date.clear()
            load_courier_master.clear()
            st.success("A profil mentve, a változás naplózva.")
            st.rerun()
        except Exception as exc:
            st.error(f"A profil nem menthető: {exc}")
    if is_editing:
        profile_actions[1].button("Mégse", use_container_width=True, key=f"fast_profile_cancel_{courier_id}", on_click=cancel_profile_edit)
    if profile_actions[2].button("Profiladatok újratöltése", use_container_width=True, key=f"fast_profile_refresh_{courier_id}"):
        st.session_state[menu_target_key] = "Profil"
        load_courier_profile.clear()
        load_active_efo_assignment.clear()
        load_muszakpro_booking_summary.clear()
        load_loyalty_profile_lookup.clear()
        load_loyalty_month_requirement_for_date.clear()
        load_target_reserve_status.clear()
        st.rerun()

    if st.checkbox("Profil módosítási napló megjelenítése", key=f"fast_profile_log_toggle_{courier_id}"):
        profile_log = load_profile_change_log(courier_id)
        if profile_log.empty:
            st.info("Nincs profil módosítási napló.")
        else:
            st.dataframe(profile_log.rename(columns={"changed_fields": "Változások", "changed_by": "Módosította", "created_at": "Időpont"}), use_container_width=True, hide_index=True)


@st.dialog("Futár részletei", width="large")
def show_courier_dialog() -> None:
    courier_id = str(st.session_state.get("selected_courier_id") or "")
    def rerun_courier_profile(menu_name: str | None = None) -> None:
        st.session_state["selected_courier_id"] = courier_id
        st.session_state["reopen_courier_dialog"] = True
        if menu_name:
            st.session_state[f"courier_menu_target_{courier_id}"] = menu_name
        st.rerun()

    data = st.session_state.get("current_filtered_data")
    if not isinstance(data, pd.DataFrame) or data.empty:
        dialog_session_id = st.session_state.get("settlement_import_session_id") or load_latest_jit_session_id()
        dialog_calculation_mode = st.session_state.get("new_calculation_mode", "API")
        if str(dialog_calculation_mode or "API").strip().casefold() == "excel":
            dialog_start, dialog_end = load_settlement_month(dialog_session_id)
        else:
            dialog_start = parse_month_option(st.session_state.get("new_month") or month_options()[0])
            _, dialog_end = month_bounds(dialog_start)
            dialog_api_session_id = load_latest_api_jit_session_id(dialog_start, st.session_state.get("new_warehouse", "Összes"))
            if dialog_api_session_id:
                dialog_session_id = dialog_api_session_id
        data = build_settlement_working_data(dialog_calculation_mode, dialog_session_id, dialog_start, st.session_state.get("new_warehouse", "Összes"))
        data = apply_received_amounts(
            data,
            dialog_calculation_mode,
            dialog_start,
            st.session_state.get("new_warehouse", "Összes"),
            dialog_session_id,
        )
        data = apply_imported_balance_components(
            data,
            balance_component_session_id(dialog_calculation_mode, dialog_start, dialog_session_id),
        )
        data = apply_manual_balance_adjustments(data, dialog_start, dialog_end)
        data = apply_salary_advance_deduction(data, dialog_start, dialog_end)
        data = recompute_payable_total(data)
    match = data[data["Courier ID"].astype(str) == courier_id]

    if match.empty:
        st.warning("A futár nem található.")
        return

    row = match.iloc[0]
    courier_name = str(
        row.get("Futár")
        or row.get("name")
        or row.get("courier_name")
        or row.get("driver_name")
        or "Ismeretlen futár"
    )
    if "Futár" not in row or not str(row.get("Futár") or "").strip():
        row = row.copy()
        row["Futár"] = courier_name
    initials = "".join(part[:1].upper() for part in courier_name.split()[:2]) or "F"
    session_id = st.session_state.get("settlement_import_session_id") or load_latest_jit_session_id()
    active_calculation_mode = st.session_state.get("new_calculation_mode", "API")
    if str(active_calculation_mode or "API").strip().casefold() == "excel":
        period_start, period_end = load_settlement_month(session_id)
    else:
        period_start = parse_month_option(st.session_state.get("new_month") or month_options()[0])
        _, period_end = month_bounds(period_start)
        api_session_id = load_latest_api_jit_session_id(period_start, st.session_state.get("new_warehouse", "Összes"))
        if api_session_id:
            session_id = api_session_id
    imported_balance_session_id = balance_component_session_id(active_calculation_mode, period_start, session_id)
    period_label = (
        f"{period_start:%Y. %m. %d.} - {period_end:%Y. %m. %d.}"
        if period_start and period_end
        else "Aktuális hónap"
    )
    month_label = f"{period_end:%Y. %B}" if period_end else "Aktuális hónap"
    last_settlement_label = f"{period_end:%Y. %m. %d.}" if period_end else "-"

    menu_key = f"courier_menu_{courier_id}"
    menu_target_key = f"courier_menu_target_{courier_id}"
    menu_target = st.session_state.pop(menu_target_key, None)
    if menu_target:
        st.session_state[menu_key] = menu_target
    selected_menu_hint = str(st.session_state.get(menu_key) or "Áttekintés")
    if selected_menu_hint == "Profil":
        render_fast_courier_profile(
            courier_id=courier_id,
            courier_name=courier_name,
            row=row,
            period_start=period_start,
            menu_key=menu_key,
            menu_target_key=menu_target_key,
        )
        return
    route_detail = pd.DataFrame()
    if selected_menu_hint in {"Áttekintés", "Pénzügy", "Útvonalak"}:
        route_detail = load_courier_route_detail(
            courier_id,
            courier_name,
            session_id,
            active_calculation_mode,
            period_start,
            st.session_state.get("new_warehouse", "Összes"),
        )
    route_breakdown = summarize_courier_route_detail(route_detail)
    reserve_status = load_target_reserve_status(courier_id, courier_name)
    profile = load_courier_profile(courier_id)
    summary_row = load_courier_settlement_summary_row(session_id, courier_id, courier_name, period_start)
    summary_available = not summary_row.empty if isinstance(summary_row, pd.Series) else bool(summary_row)
    profile_adjustments = load_courier_adjustments(courier_id, period_start, period_end)
    profile_adjustment_totals = (
        profile_adjustments.groupby("adjustment_type")["amount_huf"].sum().to_dict()
        if not profile_adjustments.empty else {}
    )
    correction_income_total = (
        float(profile_adjustment_totals.get("correction", 0.0))
        + float(profile_adjustment_totals.get("manual_correction", 0.0))
        + float(profile_adjustment_totals.get("correction_income", 0.0))
    )
    correction_deduction_total = (
        float(profile_adjustment_totals.get("correction_deduction", 0.0))
        + float(profile_adjustment_totals.get("manual_correction_deduction", 0.0))
    )
    periodic_correction_total, _overview_periodic_correction_detail = calculate_periodic_fee_corrections(
        route_detail,
        period_start,
        period_end,
        row.get("Raktár"),
    )
    correction_income_total += periodic_correction_total

    def settlement_amount(summary_column: str, fallback_column: str | None = None) -> float:
        if summary_column in summary_row:
            return parse_huf_value(summary_row.get(summary_column))
        if fallback_column:
            return parse_huf_value(row.get(fallback_column))
        return 0.0

    def imported_settlement_amount(summary_column: str, fallback_column: str, *, absolute: bool = False) -> float:
        summary_value = parse_huf_value(summary_row.get(summary_column)) if summary_column in summary_row else 0.0
        fallback_value = parse_huf_value(row.get(fallback_column))
        value = fallback_value if fallback_value else summary_value
        return abs(value) if absolute else value

    base_total = settlement_amount("courier_base_rate_huf", "Nettó bevétel")
    tip_total = settlement_amount("tip_huf", "Borravaló")
    contractor_base_total = settlement_amount("company_base_rate_huf", "Alvállalkozói összeg")
    contractor_received_total = parse_huf_value(row.get("Alvállalkozói összeg")) or settlement_amount("contractor_total_huf")
    if not contractor_received_total:
        contractor_quality_total = settlement_amount("company_quality_bonus_total_huf")
        if not contractor_quality_total:
            contractor_quality_bonus = load_dsp_monthly_company_quality_bonus(courier_id, period_start)
            contractor_quality_total = parse_huf_value(contractor_quality_bonus.get("company_quality_bonus_total_huf"))
        contractor_received_total = contractor_base_total + contractor_quality_total
    if (
        str(active_calculation_mode or "").strip().casefold() == "api"
        and (not summary_available or contractor_base_total == 0)
        and contractor_received_total == 0
    ):
        api_received = load_api_received_amounts(period_start, st.session_state.get("new_warehouse", "Összes")).copy()
        if not api_received.empty:
            api_received["_courier_id_lookup"] = api_received["Courier ID"].map(_courier_id_key)
            api_match = api_received.loc[api_received["_courier_id_lookup"].eq(_courier_id_key(courier_id))]
            if not api_match.empty:
                contractor_received_total = float(_numeric_series(api_match, "Alvállalkozói összeg").sum())
    delay_total = settlement_amount("delay_bonus_huf")
    compliance_total = settlement_amount("compliance_bonus_huf")
    other_route_bonus_total = 0.0
    display_base_total = base_total
    imported_bonus_total = imported_settlement_amount("imported_bonus_huf", "Importált bónusz")
    imported_malus_total = imported_settlement_amount("imported_malus_huf", "Importált málusz", absolute=True)
    imported_atm_total = imported_settlement_amount("imported_atm_deduction_huf", "Importált ATM levonás", absolute=True)
    manual_bonus_total = float(profile_adjustment_totals.get("bonus", 0.0))
    loyalty_total = parse_huf_value(row.get("Lojalitás"))
    imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
    customer_rating_total = imported_customer_rating_total + float(profile_adjustment_totals.get("customer_rating", 0.0))
    manual_malus_total = float(profile_adjustment_totals.get("malus", 0.0))
    manual_atm_total = float(profile_adjustment_totals.get("atm_deduction", 0.0))
    other_expense_total = float(profile_adjustment_totals.get("other_expense", 0.0))
    malus_total = imported_malus_total + manual_malus_total
    atm_deduction_total = imported_atm_total + manual_atm_total
    correction_total = correction_income_total - correction_deduction_total
    total_income = (
        base_total + tip_total + delay_total + compliance_total
        + imported_bonus_total + manual_bonus_total + loyalty_total + customer_rating_total
        + correction_income_total
    )
    salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
    total_deduction = (
        malus_total + atm_deduction_total + other_expense_total
        + correction_deduction_total + salary_advance_total
    )
    payable_before_insurance = total_income - total_deduction
    reserve_month = resolve_target_reserve_month(
        session_id, courier_id, period_start, period_end, reserve_status, payable_before_insurance
    )
    reserve_addition_total = parse_huf_value(reserve_month.get("reserve_addition_huf"))
    insurance_fee_total = parse_huf_value(reserve_month.get("insurance_fee_huf"))
    total_deduction += reserve_addition_total + insurance_fee_total
    reserve_payable_total = parse_huf_value(reserve_month.get("payable_after_insurance_huf"))
    payable_total = (
        reserve_payable_total
        if str(reserve_month.get("status") or "").casefold() == "done"
        else payable_before_insurance - reserve_addition_total - insurance_fee_total
    )
    if str(reserve_month.get("status") or "").casefold() != "done":
        itemized_deduction_total = (
            malus_total + atm_deduction_total + other_expense_total
            + correction_deduction_total + salary_advance_total
            + reserve_addition_total + insurance_fee_total
        )
        if itemized_deduction_total:
            total_deduction = itemized_deduction_total
    overview_payable_total = payable_total
    monthly_closure = load_courier_monthly_closure(courier_id, period_start, period_end)
    closure_done = str(monthly_closure.get("status") or "").casefold() == "done"
    paid_badge = '<span class="settlement-chip">✓ Kifizetve</span>' if closure_done else ''
    profile_metrics = resolve_profile_route_metrics(route_detail, summary_row, row)
    order_total = profile_metrics["order_total"]
    route_total = profile_metrics["route_total"]
    if summary_available:
        order_total = max(order_total, int(parse_huf_value(summary_row.get("order_count"))))
        route_total = max(route_total, int(parse_huf_value(summary_row.get("route_count"))))
    if not route_detail.empty:
        route_day_type = route_detail.get("Naptípus", pd.Series(dtype=str)).astype(str).str.casefold()
        route_type = route_detail.get("Túratípus", pd.Series(dtype=str)).astype(str).str.casefold()
        highlighted_route_total = int(route_day_type.str.contains("kiemelt", na=False).sum())
        normal_route_total = int(route_day_type.str.contains("norm", na=False).sum())
        express_highlighted_total = int((route_type.str.contains("express", na=False) & route_day_type.str.contains("kiemelt", na=False)).sum())
        express_normal_total = int((route_type.str.contains("express", na=False) & route_day_type.str.contains("norm", na=False)).sum())
    else:
        highlighted_route_total = int(parse_huf_value(summary_row.get("highlighted_routes")))
        normal_route_total = int(parse_huf_value(summary_row.get("normal_routes")))
        express_highlighted_total = int(parse_huf_value(summary_row.get("express_highlighted_routes")))
        express_normal_total = int(parse_huf_value(summary_row.get("express_normal_routes")))
    if summary_available:
        highlighted_route_total = max(highlighted_route_total, int(parse_huf_value(summary_row.get("highlighted_routes"))))
        normal_route_total = max(normal_route_total, int(parse_huf_value(summary_row.get("normal_routes"))))
        express_highlighted_total = max(express_highlighted_total, int(parse_huf_value(summary_row.get("express_highlighted_routes"))))
        express_normal_total = max(express_normal_total, int(parse_huf_value(summary_row.get("express_normal_routes"))))
    if route_total > 0 and highlighted_route_total + normal_route_total == 0:
        normal_route_total = route_total
    data_source_label = "DB összesítő" if summary_available else "Főoldali adat"
    insurance_label = "Aktív" if reserve_status.get("insurance_active") else "Nincs"
    vat_status_label = str(profile.get("vat_status") or "Nincs megadva")

    st.markdown(
        f"""
        <div class="settlement-profile-shell">
        <div class="settlement-profile-top">
            <div class="settlement-driver">
            <div class="settlement-avatar">{html.escape(initials)}</div>
            <div>
                <div class="settlement-name">{html.escape(courier_name)}</div>
                <div class="settlement-meta-grid">
                <div class="settlement-meta-item"><div class="settlement-meta-label">Futár azonosító</div><div class="settlement-meta-value">{html.escape(courier_id)}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Raktár</div><div class="settlement-meta-value">{html.escape(str(row.get('Raktár') or profile.get('warehouse_name') or '-'))}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Státusz</div><div class="settlement-chip">{html.escape(str(row.get('Státusz') or 'Aktív'))}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">Biztosítás</div><div class="settlement-meta-value">{html.escape(insurance_label)}</div></div>
                <div class="settlement-meta-item"><div class="settlement-meta-label">ÁFA státusz</div><div class="settlement-meta-value">{html.escape(vat_status_label)}</div></div>
                </div>
            </div>
            </div>
            <div class="settlement-top-kpis">
            <div class="settlement-kpi-card"><div class="settlement-kpi-icon">Ft</div><div><div class="settlement-kpi-label">Havi fizetendő {paid_badge}</div><div class="settlement-kpi-value">{format_huf(payable_total)}</div><div class="settlement-kpi-note">{html.escape(month_label)}</div></div></div>
            <div class="settlement-kpi-card"><div class="settlement-kpi-icon blue">Σ</div><div><div class="settlement-kpi-label">Vállalkozói díj</div><div class="settlement-kpi-value">{format_huf(contractor_received_total)}</div><div class="settlement-kpi-note">{html.escape(month_label)}</div></div></div>
            <div class="settlement-kpi-card"><div class="settlement-kpi-icon red">−</div><div><div class="settlement-kpi-label">Összes levonás</div><div class="settlement-kpi-value">{format_huf(total_deduction)}</div><div class="settlement-kpi-note">{html.escape(month_label)}</div></div></div>
            <div class="settlement-kpi-card"><div class="settlement-kpi-icon purple">✓</div><div><div class="settlement-kpi-label">Utolsó elszámolás</div><div class="settlement-kpi-value">{html.escape(last_settlement_label)}</div><div class="settlement-kpi-note">Fizetve</div></div></div>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    courier_menu_items = ["Áttekintés", "Pénzügy", "Kifizetés", "Fizetés előleg", "Útvonalak"]
    if str(active_calculation_mode or "API").strip().casefold() == "api":
        courier_menu_items.append("Statisztika")
    courier_menu_items.extend(["Dokumentumok", "Egyedi dokumentum", "Reklamációk", "Profil"])
    selected_menu = st.radio(
        "Futármenü", courier_menu_items,
        horizontal=True, label_visibility="collapsed", key=menu_key,
    )

    def keep_courier_menu(menu_name: str) -> None:
        st.session_state[menu_target_key] = menu_name

    if selected_menu == "Áttekintés":
        missing_data_count = 0
        if not summary_available:
            missing_data_count += 1

        st.markdown(
            f"""
            <div class="settlement-profile-shell">
            <div class="settlement-overview-grid">
                <div class="settlement-card">
                <div class="settlement-card-title">Havi elszámolás <span class="settlement-card-subtitle">{html.escape(month_label)}</span></div>
                <div class="settlement-summary-line">
                    <div class="settlement-summary-item"><div class="settlement-summary-label">Összes bevétel</div><div class="settlement-summary-value">{format_huf(total_income)}</div></div>
                    <div class="settlement-summary-item"><div class="settlement-summary-label">Összes levonás</div><div class="settlement-summary-value red">{format_huf(total_deduction)}</div></div>
                    <div class="settlement-summary-item payable"><div class="settlement-summary-label">Fizetendő összeg</div><div class="settlement-summary-value big">{format_huf(payable_total)}</div></div>
                </div>
                <div class="settlement-ledger-grid">
                    <div class="settlement-ledger income">
                    <div class="settlement-ledger-head">↗ Bevételek</div>
                    <div class="settlement-ledger-row"><span>Alapdíj</span><strong>{format_huf(display_base_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Borravaló</span><strong>{format_huf(tip_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Késedelmi bónusz</span><strong>{format_huf(delay_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Túramegfelelés</span><strong>{format_huf(compliance_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Kiflis bónusz</span><strong>{format_huf(imported_bonus_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>JITT bónusz</span><strong>{format_huf(manual_bonus_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Lojalitás</span><strong>{format_huf(loyalty_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Ügyfélértékelés</span><strong>{format_huf(customer_rating_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Korrekció +</span><strong>{format_huf(correction_income_total)}</strong></div>
                    <div class="settlement-ledger-row total"><span>Összesen</span><strong>{format_huf(total_income)}</strong></div>
                    </div>
                    <div class="settlement-ledger outcome">
                    <div class="settlement-ledger-head">↓ Levonások</div>
                    <div class="settlement-ledger-row"><span>Kiflis malus</span><strong>-{format_huf(imported_malus_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>JITT malus</span><strong>-{format_huf(manual_malus_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>ATM levonás</span><strong>-{format_huf(atm_deduction_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Egyéb kiadás</span><strong>-{format_huf(other_expense_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Korrekció -</span><strong>-{format_huf(correction_deduction_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Fizetés előleg</span><strong>-{format_huf(salary_advance_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Céltartalék 10%</span><strong>-{format_huf(reserve_addition_total)}</strong></div>
                    <div class="settlement-ledger-row"><span>Biztosítási díj</span><strong>-{format_huf(insurance_fee_total)}</strong></div>
                    <div class="settlement-ledger-row total"><span>Összesen</span><strong>-{format_huf(total_deduction)}</strong></div>
                    </div>
                </div>
                </div>
                <div class="settlement-side-stack">
                <div class="settlement-card">
                    <div class="settlement-card-title">Elszámolási mutatók</div>
                    <div class="settlement-mini-kpis">
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon">□</div><div class="settlement-kpi-label">Rendelés</div><div class="settlement-mini-value">{order_total}</div><div class="settlement-mini-note">aktuális hónap</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon blue">↔</div><div class="settlement-kpi-label">Kör</div><div class="settlement-mini-value">{route_total}</div><div class="settlement-mini-note">route detail</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon">Ft</div><div class="settlement-kpi-label">Bevétel</div><div class="settlement-mini-value">{format_huf(total_income)}</div><div class="settlement-mini-note">jóváírások</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon blue">N</div><div class="settlement-kpi-label">Normál</div><div class="settlement-mini-value">{normal_route_total}</div><div class="settlement-mini-note">túra</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon">K</div><div class="settlement-kpi-label">Kiemelt</div><div class="settlement-mini-value">{highlighted_route_total}</div><div class="settlement-mini-note">túra</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon blue">E</div><div class="settlement-kpi-label">Express normál</div><div class="settlement-mini-value">{express_normal_total}</div><div class="settlement-mini-note">túra</div></div>
                    <div class="settlement-mini-kpi"><div class="settlement-kpi-icon">E</div><div class="settlement-kpi-label">Express kiemelt</div><div class="settlement-mini-value">{express_highlighted_total}</div><div class="settlement-mini-note">túra</div></div>
                    </div>
                </div>
                <div class="settlement-card">
                    <div class="settlement-card-title">Adatforrás</div>
                    <div class="settlement-source-row"><span>Elsődleges forrás</span><strong>{html.escape(data_source_label)}</strong><span class="settlement-ok">✓</span></div>
                    <div class="settlement-source-row"><span>Elszámolási időszak</span><strong>{html.escape(period_label)}</strong><span class="settlement-info">i</span></div>
                    <div class="settlement-source-row"><span>Adatminőség</span><strong>{'Megbízható' if missing_data_count == 0 else 'Ellenőrizendő'}</strong><span class="settlement-ok">✓</span></div>
                    <div class="settlement-source-row"><span>Hiányzó adatok</span><strong>{missing_data_count}</strong><span class="settlement-info">i</span></div>
                </div>
                </div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        source_options = ["API", "Excel"]
        current_source = "Excel" if str(active_calculation_mode or "").strip().casefold() == "excel" else "API"
        source_choice = st.radio(
            "Adatforrás módosítása",
            source_options,
            index=source_options.index(current_source),
            horizontal=True,
            key=f"courier_data_source_choice_{courier_id}",
            help="A futár részletező adatai API vagy Excel alapú elszámolásból olvashatók.",
        )
        if source_choice != current_source:
            st.session_state["courier_requested_calculation_mode"] = source_choice
            if source_choice == "Excel":
                state_excel_session_id = st.session_state.get("settlement_excel_session_id")
                if jit_session_has_rows_in_month(state_excel_session_id, period_start):
                    st.session_state["settlement_import_session_id"] = state_excel_session_id
                else:
                    st.session_state["settlement_import_session_id"] = load_latest_excel_jit_session_id(period_start)
            else:
                st.session_state["settlement_import_session_id"] = load_latest_api_jit_session_id(
                    period_start,
                    st.session_state.get("new_warehouse", "Összes"),
                )
            st.rerun()
        st.markdown("#### Bejelentések (public.courier_route_alerts)")
        st.caption("Ellenőrző táblák: settlement.excel_route_coverage_audit, settlement.dsp_time_window_delay_audit_monthly, settlement.dsp_shift_attendance_audit_monthly.")
        route_alerts = load_courier_route_alerts(courier_id, limit=5)
        if route_alerts.empty:
            st.info("Nincs bejelentés ennél a futárnál.")
        else:
            alert_type_labels = {
                "problem": "Probléma",
                "delay": "Késés",
                "bag_missing": "Táska hiány",
            }
            alert_view = route_alerts.copy()
            alert_view["Dátum"] = pd.to_datetime(alert_view.get("created_at"), errors="coerce").dt.strftime("%Y. %m. %d. %H:%M")
            alert_view["Route ID"] = alert_view.get("route_id", pd.Series(dtype=str)).astype(str)
            alert_view["Típus"] = alert_view.get("alert_type", pd.Series(dtype=str)).map(alert_type_labels).fillna(alert_view.get("alert_type", "-"))
            alert_view["Státusz"] = alert_view.get("status", pd.Series(dtype=str)).fillna("-")
            st.dataframe(
                alert_view[["Dátum", "Route ID", "Típus", "Státusz"]],
                use_container_width=True,
                hide_index=True,
            )

    if selected_menu == "Pénzügy":
        if route_detail.empty:
            route_detail = load_courier_route_detail(
                courier_id,
                courier_name,
                session_id,
                active_calculation_mode,
                period_start,
                st.session_state.get("new_warehouse", "Összes"),
            )
        route_breakdown = summarize_courier_route_detail(route_detail)
        adjustments = load_courier_adjustments(courier_id, period_start, period_end)
        adjustment_totals = adjustments.groupby("adjustment_type")["amount_huf"].sum().to_dict() if not adjustments.empty else {}
        # These two totals are calculated and persisted by the DB view.  The
        # Route ID table below is an audit drill-down, not a second calculator.
        base_total = float(row.get("Nettó bevétel", 0.0))
        tip_total = float(row.get("Borravaló", 0.0))
        delay_total = float(route_breakdown.get("Késedelmi díj", pd.Series(dtype=float)).sum())
        compliance_total = float(route_breakdown.get("Túramegfelelés", pd.Series(dtype=float)).sum())
        route_other_bonus_total = 0.0
        bonus_total = float(adjustment_totals.get("bonus", 0))
        loyalty_total = parse_huf_value(row.get("Lojalitás"))
        imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
        customer_rating_total = imported_customer_rating_total + float(adjustment_totals.get("customer_rating", 0))
        malus_total = float(adjustment_totals.get("malus", 0))
        atm_deduction_total = float(adjustment_totals.get("atm_deduction", 0))
        other_expense_total = float(adjustment_totals.get("other_expense", 0))
        correction_income_total = (
            float(adjustment_totals.get("correction", 0))
            + float(adjustment_totals.get("manual_correction", 0))
            + float(adjustment_totals.get("correction_income", 0))
        )
        correction_deduction_total = (
            float(adjustment_totals.get("correction_deduction", 0))
            + float(adjustment_totals.get("manual_correction_deduction", 0))
        )
        periodic_correction_total, periodic_correction_detail = calculate_periodic_fee_corrections(
            route_detail,
            period_start,
            period_end,
            row.get("Raktár"),
        )
        correction_income_total += periodic_correction_total
        correction_total = correction_income_total - correction_deduction_total
        salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
        imported_bonus_total = imported_settlement_amount("imported_bonus_huf", "Importált bónusz")
        imported_malus_total = imported_settlement_amount("imported_malus_huf", "Importált málusz", absolute=True)
        imported_atm_total = imported_settlement_amount("imported_atm_deduction_huf", "Importált ATM levonás", absolute=True)
        imported_bonus_note = str(row.get("Importált bónusz megjegyzés") or "").strip()
        imported_malus_note = str(row.get("Importált málusz megjegyzés") or "").strip()
        bonus_total += imported_bonus_total
        malus_total += imported_malus_total
        atm_deduction_total += imported_atm_total
        route_other_bonus_total = 0.0
        payable_total = (
            base_total + tip_total + delay_total + compliance_total + bonus_total
            + loyalty_total + customer_rating_total + correction_income_total
            - malus_total - atm_deduction_total - other_expense_total - correction_deduction_total - salary_advance_total
        )
        profile_metrics = resolve_profile_route_metrics(route_detail, summary_row, row)
        order_total = profile_metrics["order_total"]
        route_total = profile_metrics["route_total"]
        monthly_bonus_malus_effect = (
            imported_bonus_total + float(adjustment_totals.get("bonus", 0)) + loyalty_total
            - imported_malus_total - float(adjustment_totals.get("malus", 0))
        )
        manual_other_total = float(adjustment_totals.get("other_expense", 0))

        # The profile cards are a direct projection of the persisted central
        # settlement row for money amounts. For counts, keep the larger central
        # monthly value when the route detail drill-down is incomplete.
        if summary_available and route_detail.empty:
            amount = lambda field: parse_huf_value(summary_row.get(field))
            base_total = amount("courier_base_rate_huf")
            tip_total = amount("tip_huf")
            delay_total = amount("delay_bonus_huf")
            compliance_total = amount("compliance_bonus_huf")
            route_other_bonus_total = 0.0
            imported_bonus_total = imported_settlement_amount("imported_bonus_huf", "Importált bónusz")
            imported_malus_total = imported_settlement_amount("imported_malus_huf", "Importált málusz", absolute=True)
            imported_atm_total = imported_settlement_amount("imported_atm_deduction_huf", "Importált ATM levonás", absolute=True)
            order_total = int(amount("order_count"))
            route_total = int(amount("route_count"))
        elif summary_available:
            base_total = parse_huf_value(summary_row.get("courier_base_rate_huf"))
            tip_total = parse_huf_value(summary_row.get("tip_huf"))
            delay_total = parse_huf_value(summary_row.get("delay_bonus_huf"))
            compliance_total = parse_huf_value(summary_row.get("compliance_bonus_huf"))
            route_other_bonus_total = 0.0
            imported_bonus_total = imported_settlement_amount("imported_bonus_huf", "Importált bónusz")
            imported_malus_total = imported_settlement_amount("imported_malus_huf", "Importált málusz", absolute=True)
            imported_atm_total = imported_settlement_amount("imported_atm_deduction_huf", "Importált ATM levonás", absolute=True)
            order_total = max(order_total, int(parse_huf_value(summary_row.get("order_count"))))
            route_total = max(route_total, int(parse_huf_value(summary_row.get("route_count"))))

        manual_bonus_total = float(adjustment_totals.get("bonus", 0.0))
        manual_customer_rating_total = float(adjustment_totals.get("customer_rating", 0.0))
        loyalty_total = parse_huf_value(row.get("Lojalitás"))
        imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
        manual_malus_total = float(adjustment_totals.get("malus", 0.0))
        manual_atm_total = float(adjustment_totals.get("atm_deduction", 0.0))
        manual_other_total = float(adjustment_totals.get("other_expense", 0.0))
        bonus_total = imported_bonus_total + manual_bonus_total
        customer_rating_total = imported_customer_rating_total + manual_customer_rating_total
        malus_total = imported_malus_total + manual_malus_total
        loyalty_previous_routes = int(parse_huf_value(row.get("Lojalitás előző havi normál kör")))
        loyalty_current_routes = int(parse_huf_value(row.get("Lojalitás aktuális normál kör")))
        loyalty_rate = parse_huf_value(row.get("Lojalitás Ft/kör"))
        loyalty_advance_booking_days = int(parse_huf_value(row.get("Lojalitás előre foglalt nap")))
        loyalty_status = str(row.get("Lojalitás státusz") or "").strip()
        atm_deduction_total = imported_atm_total + manual_atm_total
        other_expense_total = manual_other_total
        salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
        route_other_bonus_total = 0.0
        display_base_total = base_total
        payable_total = (
            base_total + tip_total + delay_total + compliance_total + bonus_total
            + loyalty_total + customer_rating_total + correction_income_total
            - malus_total - atm_deduction_total - other_expense_total - correction_deduction_total - salary_advance_total
        )
        payable_before_insurance = payable_total
        reserve_month = resolve_target_reserve_month(
            session_id, courier_id, period_start, period_end, reserve_status, payable_before_insurance
        )
        reserve_addition_total = parse_huf_value(reserve_month.get("reserve_addition_huf"))
        insurance_fee_total = parse_huf_value(reserve_month.get("insurance_fee_huf"))
        reserve_before_total = parse_huf_value(reserve_month.get("reserve_before_huf"))
        reserve_after_total = parse_huf_value(reserve_month.get("reserve_after_huf"))
        reserve_month_status = str(reserve_month.get("status") or "in_progress")
        payable_total = overview_payable_total
        monthly_closure = load_courier_monthly_closure(courier_id, period_start, period_end)
        closure_done = str(monthly_closure.get("status") or "").casefold() == "done"
        monthly_bonus_malus_effect = (
            imported_bonus_total + manual_bonus_total + loyalty_total + imported_customer_rating_total + manual_customer_rating_total
            - imported_malus_total - manual_malus_total
        )
        kiflis_bonus_malus_effect = imported_bonus_total - imported_malus_total
        jitt_bonus_malus_effect = manual_bonus_total - manual_malus_total
        snapshot_has_workload = "booked_shift_count" in summary_row or "giriton_shift_count" in summary_row
        if snapshot_has_workload:
            booking_summary = {"source": "vw_courier_month_profile_snapshot"}
            booked_shift_count = int(parse_huf_value(summary_row.get("booked_shift_count")))
            advance_booked_shift_count = int(parse_huf_value(summary_row.get("advance_booked_shift_count")))
            giriton_shift_summary = {"source": "vw_courier_month_profile_snapshot"}
            giriton_shift_count = int(parse_huf_value(summary_row.get("giriton_shift_count")))
        else:
            booking_summary = load_muszakpro_booking_summary(courier_id, period_start, period_end)
            booked_shift_count = int(booking_summary.get("booked_shift_count") or 0)
            advance_booked_shift_count = int(booking_summary.get("advance_booked_shift_count") or 0)
            giriton_shift_summary = load_giriton_shift_summary(courier_id, period_start, period_end)
            giriton_shift_count = int(giriton_shift_summary.get("giriton_shift_count") or 0)
        save_monthly_workload_summary(
            courier_id=courier_id,
            courier_name=courier_name,
            period_start=period_start,
            period_end=period_end,
            booked_shift_count=booked_shift_count,
            advance_booked_shift_count=advance_booked_shift_count,
            giriton_shift_count=giriton_shift_count,
            completed_route_count=route_total,
            order_count=order_total,
            muszakpro_source=str(booking_summary.get("source") or ""),
            route_source="courier_settlement_summary" if summary_available else "route_detail",
        )

        settlement_document_reference = make_document_reference(courier_id, "settlement", period_start)
        tig_document_reference = make_document_reference(courier_id, "tig", period_start)
        pdf_bytes = build_settlement_pdf(
            {
                "name": courier_name,
                "id": courier_id,
                "branch": row["Branch"],
                "warehouse": row["Raktár"],
                "status": row["Státusz"],
                "document_reference": settlement_document_reference,
                "document_month": period_start,
                "email": profile.get("email") or "",
            },
            route_breakdown.to_dict("records"),
            {
                "base": base_total,
                "tip": tip_total,
                "bonus": bonus_total + loyalty_total,
                "malus": malus_total,
                "atm": atm_deduction_total,
                "other": other_expense_total,
                "salary_advance": salary_advance_total,
                "customer_rating": customer_rating_total,
                "reserve": reserve_addition_total,
                "reserve_before": reserve_before_total,
                "reserve_after": reserve_after_total,
                "insurance": insurance_fee_total,
                "payable": payable_total,
            },
        )
        tig_bytes = build_tig_pdf(
            {
                "name": courier_name,
                "company_name": profile.get("company_name") or courier_name,
                "address": profile.get("address") or "",
                "tax_number": profile.get("tax_number") or profile.get("tax_id") or "",
                "tig_type": profile.get("tig_type") or profile.get("tig_mode") or profile.get("invoice_type") or profile.get("invoice_vat_type") or profile.get("vat_status") or "",
                "vat_status": profile.get("vat_status") or "",
                "email": profile.get("email") or "",
                "id": courier_id,
                "document_reference": tig_document_reference,
                "document_month": period_start,
            },
            {
                "payable": payable_total,
                "cash": abs(atm_deduction_total),
                "tip": tip_total,
            },
        )
        st.markdown(
            f"""
            <div class="settlement-profile-shell">
            <div class="finance-toolbar">
                <div><div class="finance-toolbar-label">Elszámolási hónap</div><div class="finance-toolbar-value">{period_end:%Y. %B}</div></div>
                <div><div class="finance-toolbar-label">Státusz</div><div class="finance-status">Szerkeszthető</div></div>
                <div class="finance-toolbar-actions">A havi tételek mentése lent, a szerkeszthető táblánál történik.</div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        workload_cols = st.columns(5)
        workload_cols[0].metric("MűszakPro foglalt műszak", booked_shift_count)
        workload_cols[1].metric("Előre foglalt műszak", advance_booked_shift_count)
        workload_cols[2].markdown(
            f"""
            <div class="workload-kpi-card {'is-good' if giriton_shift_count > 30 else ''}">
                <div class="workload-kpi-label">Giriton műszak</div>
                <div class="workload-kpi-value">{giriton_shift_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        workload_cols[3].metric("Kifutott túra", route_total)
        workload_cols[4].metric("Cím / rendelés", order_total)
        doc_a, doc_b = st.columns([0.18, 0.18])
        settlement_file_name = f"jitt_elszamolas_{courier_id}_{slugify_filename(courier_name)}_{period_start:%Y-%m}_{settlement_document_reference}.pdf"
        tig_file_name = f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_{period_start:%Y-%m}_{tig_document_reference}.pdf"
        doc_a.download_button("Elszámolás PDF", data=pdf_bytes, file_name=settlement_file_name, mime="application/pdf", use_container_width=True, key=f"finance_top_settlement_pdf_{courier_id}")
        doc_b.download_button("TIG PDF", data=tig_bytes, file_name=tig_file_name, mime="application/pdf", use_container_width=True, key=f"finance_top_tig_pdf_{courier_id}")
        upload_a, upload_b, open_month_col, refresh_col = st.columns([0.18, 0.18, 0.28, 0.18])
        if closure_done:
            st.warning("A havi folyamat le van zárva, új elszámolás/TIG nem tölthető fel erre a hónapra.")
        try:
            individual_statuses = read_peopleforce_card_statuses(courier_id, period_start.replace(day=1))
        except Exception:
            individual_statuses = pd.DataFrame()
        individual_status_by_action = {
            str(item.get("action_key") or ""): item
            for item in individual_statuses.to_dict("records")
        } if not individual_statuses.empty else {}
        individual_monthly_billing_open = str(
            (individual_status_by_action.get("individual_monthly_billing") or {}).get("status") or ""
        ).casefold() in {"open", "done"}
        if upload_a.button("Elszámolás feltöltése profilba", use_container_width=True, disabled=closure_done, key=f"finance_upload_settlement_pdf_{courier_id}"):
            try:
                upload_peopleforce_document_bytes(
                    courier_id=courier_id,
                    courier_name=courier_name,
                    document_type="settlement",
                    document_month=period_start.replace(day=1),
                    title=f"Elszámolás - {period_start:%Y-%m}",
                    note=f"Dokumentum azonosító: {settlement_document_reference}",
                    file_name=settlement_file_name,
                    mime_type="application/pdf",
                    file_bytes=pdf_bytes,
                    uploaded_by=str(st.session_state.get("user", {}).get("username") or "unknown"),
                )
                st.success("Elszámolás PDF feltöltve a futár profiljába.")
                rerun_courier_profile("Pénzügy")
            except Exception as exc:
                st.error(f"Az elszámolás feltöltése sikertelen: {exc}")
        if upload_b.button("TIG feltöltése profilba", use_container_width=True, disabled=closure_done, key=f"finance_upload_tig_pdf_{courier_id}"):
            try:
                upload_peopleforce_document_bytes(
                    courier_id=courier_id,
                    courier_name=courier_name,
                    document_type="tig",
                    document_month=period_start.replace(day=1),
                    title=f"TIG - {period_start:%Y-%m}",
                    note=f"Dokumentum azonosító: {tig_document_reference}",
                    file_name=tig_file_name,
                    mime_type="application/pdf",
                    file_bytes=tig_bytes,
                    uploaded_by=str(st.session_state.get("user", {}).get("username") or "unknown"),
                )
                st.success("TIG PDF feltöltve a futár profiljába.")
                rerun_courier_profile("Pénzügy")
            except Exception as exc:
                st.error(f"A TIG feltöltése sikertelen: {exc}")
        if open_month_col.button(
            "Egyedi havi számlázás zárása" if individual_monthly_billing_open else "Egyedi havi számlázás nyitása",
            type="secondary" if individual_monthly_billing_open else "primary",
            use_container_width=True,
            disabled=closure_done or active_calculation_mode not in {"API", "Excel"},
            key=f"finance_open_individual_month_{courier_id}",
            help="Nyitáskor publikálja a havi elszámolást. Záráskor leveszi az egyedi mobil nyitást és törli az így feltöltött tesztdokumentumokat.",
        ):
            try:
                actor = str(st.session_state.get("user", {}).get("username") or "unknown")
                if individual_monthly_billing_open:
                    deleted_count = close_individual_monthly_billing(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        period_start=period_start,
                        actor=actor,
                    )
                    st.success(f"Egyedi havi számlázás lezárva. Törölt tesztdokumentum: {deleted_count}.")
                    rerun_courier_profile("Pénzügy")
                else:
                    deleted_count, uploaded_count, courier_count = open_individual_monthly_billing(
                        row.to_dict(),
                        period_start,
                        period_end,
                        active_calculation_mode,
                        st.session_state.get("new_warehouse", "Összes"),
                        session_id,
                        actor,
                    )
                    if courier_count:
                        st.success(
                            "Egyedi havi számlázás megnyitva: "
                            f"{uploaded_count} dokumentum feltöltve"
                            + (f", {deleted_count} korábbi tesztdokumentum cserélve." if deleted_count else ".")
                        )
                        rerun_courier_profile("Dokumentumok")
                    else:
                        st.error("Az egyedi havi nyitás nem sikerült. Ellenőrizd a mobil SQL táblákat és a kiválasztott API/Excel sessiont.")
            except Exception as exc:
                st.error(f"Az egyedi havi számlázás módosítása sikertelen: {exc}")
        if refresh_col.button("Adatok frissítése", use_container_width=True, key=f"finance_refresh_data_{courier_id}"):
            refresh_settlement_profile_data()
            st.toast("Futárprofil adatok frissítve.", icon="✅")
            rerun_courier_profile("Pénzügy")

        delay_level_rules = load_active_bonus_level_rules("cfg_jitt_delay_bonus_rules")
        compliance_level_rules = load_active_bonus_level_rules("cfg_jitt_compliance_bonus_rules")

        def finance_detail_frame(detail_label: str) -> pd.DataFrame:
            if detail_label == "Kör":
                return pd.DataFrame([
                    {"Tétel": "MűszakPro foglalt műszak", "Darab": booked_shift_count, "Forrás": str(booking_summary.get("source") or "-")},
                    {"Tétel": "Giriton műszak", "Darab": giriton_shift_count, "Forrás": str(giriton_shift_summary.get("source") or "-")},
                    {"Tétel": "Kifutott túra", "Darab": route_total, "Forrás": "courier_settlement_summary" if summary_available else "route_detail"},
                    {"Tétel": "Cím / rendelés", "Darab": order_total, "Forrás": "courier_settlement_summary" if summary_available else "route_detail"},
                ])
            if detail_label == "Késedelmi díj":
                return build_amount_drilldown(route_detail, "Késedelmi díj", delay_level_rules)
            if detail_label == "Túramegfelelés":
                return build_amount_drilldown(route_detail, "Túramegfelelés", compliance_level_rules)
            if detail_label == "Lojalitás":
                unit_amount = loyalty_rate or (loyalty_total / loyalty_current_routes if loyalty_current_routes else 0)
                return pd.DataFrame([
                    {
                        "Tétel": "Lojalitás",
                        "Darab": loyalty_current_routes,
                        "Egységösszeg": unit_amount,
                        "Összeg": loyalty_total,
                        "Számítás": f"{loyalty_current_routes} x {format_huf(unit_amount)}" if unit_amount else format_huf(loyalty_total),
                    },
                    {"Tétel": "Kifutott kör", "Darab": loyalty_current_routes, "Egységösszeg": 0, "Összeg": 0, "Számítás": str(loyalty_current_routes)},
                    {"Tétel": "Előre foglalt műszak", "Darab": loyalty_advance_booking_days, "Egységösszeg": 0, "Összeg": 0, "Számítás": str(loyalty_advance_booking_days)},
                    {"Tétel": "Státusz", "Darab": 0, "Egységösszeg": 0, "Összeg": 0, "Számítás": loyalty_status or "-"},
                ])
            if detail_label == "Ügyfélértékelési bónusz":
                unit_amount = customer_rating_total / route_total if route_total else 0
                return pd.DataFrame([{
                    "Tétel": "Ügyfélértékelési bónusz",
                    "Darab": route_total,
                    "Egységösszeg": unit_amount,
                    "Összeg": customer_rating_total,
                    "Számítás": f"{route_total} x {format_huf(unit_amount)}" if unit_amount else format_huf(customer_rating_total),
                }])
            if detail_label == "Korrekció":
                detail_parts = []
                if not periodic_correction_detail.empty:
                    detail_parts.append(periodic_correction_detail)
                correction_labels = {
                    "correction": "Korrekció",
                    "manual_correction": "Kézi korrekció +",
                    "correction_income": "Korrekció +",
                    "correction_deduction": "Korrekció -",
                    "manual_correction_deduction": "Kézi korrekció -",
                }
                if not adjustments.empty:
                    manual_corrections = adjustments[
                        adjustments["adjustment_type"].astype(str).isin(correction_labels)
                    ].copy()
                    if not manual_corrections.empty:
                        manual_corrections["Összeg"] = pd.to_numeric(manual_corrections["amount_huf"], errors="coerce").fillna(0.0)
                        deduction_mask = manual_corrections["adjustment_type"].isin({"correction_deduction", "manual_correction_deduction"})
                        manual_corrections.loc[deduction_mask, "Összeg"] = -manual_corrections.loc[deduction_mask, "Összeg"].abs()
                        manual_corrections["Tétel"] = manual_corrections["adjustment_type"].map(correction_labels).fillna("Korrekció")
                        manual_corrections["Számítás"] = manual_corrections.get("note", pd.Series("", index=manual_corrections.index)).fillna("")
                        detail_parts.append(manual_corrections[["Tétel", "Összeg", "Számítás"]])
                return pd.concat(detail_parts, ignore_index=True, sort=False) if detail_parts else pd.DataFrame()
            if detail_label == "Kiflis levonások / bónuszok":
                itemized_imports = load_imported_balance_component_items(imported_balance_session_id, courier_id, courier_name)
                if not itemized_imports.empty:
                    return itemized_imports
                return pd.DataFrame([
                    {"Tétel": "Kiflis bónusz", "Összeg": imported_bonus_total, "Megjegyzés": imported_bonus_note},
                    {"Tétel": "Kiflis malus", "Összeg": -imported_malus_total, "Megjegyzés": imported_malus_note},
                ])
            if detail_label in {"Havi bónusz/malus", "JITT bónusz / malus"}:
                manual_bonus_notes = " | ".join(
                    dict.fromkeys(
                        adjustments.loc[
                            adjustments["adjustment_type"].astype(str).eq("bonus"),
                            "note",
                        ].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().tolist()
                    )
                ) if not adjustments.empty and "note" in adjustments.columns else ""
                manual_malus_notes = " | ".join(
                    dict.fromkeys(
                        adjustments.loc[
                            adjustments["adjustment_type"].astype(str).eq("malus"),
                            "note",
                        ].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().tolist()
                    )
                ) if not adjustments.empty and "note" in adjustments.columns else ""
                return pd.DataFrame([
                    {"Tétel": "JITT bónusz", "Összeg": manual_bonus_total, "Megjegyzés": manual_bonus_notes},
                    {"Tétel": "JITT malus", "Összeg": -manual_malus_total, "Megjegyzés": manual_malus_notes},
                ])
            if detail_label == "ATM hatás":
                return pd.DataFrame([
                    {"Tétel": "Importált ATM levonás", "Összeg": -imported_atm_total},
                    {"Tétel": "Manuális ATM levonás", "Összeg": -manual_atm_total},
                ])
            if detail_label == "Fizetés előleg":
                return pd.DataFrame([{"Tétel": "Aktuális havi fizetés előleg", "Összeg": -salary_advance_total}])
            if detail_label == "Céltartalék 10%":
                return pd.DataFrame([
                    {"Tétel": "Céltartalék feltöltés", "Összeg": -reserve_addition_total},
                    {"Tétel": "Nyitó céltartalék", "Összeg": reserve_before_total},
                    {"Tétel": "Záró céltartalék", "Összeg": reserve_after_total},
                ])
            return pd.DataFrame()

        def finance_level_note(detail_label: str) -> str:
            detail_df = finance_detail_frame(detail_label)
            if detail_df.empty or "Szint" not in detail_df.columns:
                return ""
            levels = [
                str(level).strip()
                for level in detail_df["Szint"].dropna().unique().tolist()
                if str(level).strip() and str(level).strip() != "-"
            ]
            if not levels:
                return ""
            levels = sorted(levels)
            if len(levels) == 1:
                return f"Szint: {levels[0]}"
            return f"Szintek: {', '.join(levels[:3])}" + ("..." if len(levels) > 3 else "")

        kpi_items = [
            ("Rendelés", f"{order_total:,}".replace(",", " "), "", ""),
            ("Kör", str(route_total), "", ""),
            ("Normál túra", str(normal_route_total), "", ""),
            ("Kiemelt túra", str(highlighted_route_total), "", ""),
            ("Express normál", str(express_normal_total), "", ""),
            ("Express kiemelt", str(express_highlighted_total), "", ""),
            ("Késedelmi díj", format_huf(delay_total), "", finance_level_note("Késedelmi díj")),
            ("Túramegfelelés", format_huf(compliance_total), "", finance_level_note("Túramegfelelés")),
            ("Lojalitás", format_huf(loyalty_total), "", ""),
            ("Ügyfélértékelési bónusz", format_huf(customer_rating_total), "", ""),
            ("Fizetendő", format_huf(payable_total), "payable", ""),
            ("Korrekció", format_huf(correction_total), "", ""),
            ("Kiflis levonások / bónuszok", format_huf(kiflis_bonus_malus_effect), "", ""),
            ("JITT bónusz / malus", format_huf(jitt_bonus_malus_effect), "", ""),
            ("ATM hatás", format_huf(-atm_deduction_total), "", ""),
            ("Fizetés előleg", format_huf(-salary_advance_total), "", ""),
            ("Céltartalék 10%", format_huf(-reserve_addition_total), "", ""),
            ("Biztosítási díj", format_huf(-insurance_fee_total), "", ""),
            ("CT státusz", "Done" if reserve_month_status == "done" else "In progress", "", ""),
        ]

        def finance_detail_html(detail_label: str) -> str:
            detail_df = finance_detail_frame(detail_label)
            if detail_df.empty:
                return '<div class="finance-kpi-detail-empty">Nincs bontott adat.</div>'
            display_detail = detail_df.copy()
            for amount_column in ["Egységösszeg", "Összeg"]:
                if amount_column in display_detail.columns:
                    display_detail[amount_column] = display_detail[amount_column].map(format_huf)
            headers = "".join(f"<th>{html.escape(str(column))}</th>" for column in display_detail.columns)
            rows_html = []
            for _, detail_row in display_detail.iterrows():
                rows_html.append(
                    "<tr>"
                    + "".join(f"<td>{html.escape(str(detail_row.get(column, '')))}</td>" for column in display_detail.columns)
                    + "</tr>"
                )
            return (
                '<div class="finance-kpi-detail-body">'
                '<table class="finance-kpi-detail-table">'
                f"<thead><tr>{headers}</tr></thead><tbody>{''.join(rows_html)}</tbody>"
                "</table></div>"
            )

        detail_labels = {
            "Kör", "Késedelmi díj", "Túramegfelelés", "Lojalitás", "Ügyfélértékelési bónusz",
            "Korrekció", "Kiflis levonások / bónuszok", "JITT bónusz / malus", "ATM hatás", "Fizetés előleg", "Céltartalék 10%",
        }

        def render_finance_kpi(label: str, value: str, css_class: str, note: str = "") -> str:
            note_html = f'<div class="finance-kpi-note">{html.escape(note)}</div>' if note else ""
            card = (
                f'<div class="finance-kpi {css_class}">'
                f'<div class="finance-kpi-label">{html.escape(label)}</div>'
                f'<div class="finance-kpi-value">{html.escape(value)}</div>'
                f"{note_html}"
                "</div>"
            )
            if label not in detail_labels:
                return card
            return (
                f'<details class="finance-kpi-detail-card {css_class}">'
                f"<summary>{card}</summary>"
                f"{finance_detail_html(label)}"
                "</details>"
            )

        st.markdown(
            '<div class="settlement-profile-shell"><div class="finance-kpi-grid">'
            + "".join(
                render_finance_kpi(label, value, css_class, note)
                for label, value, css_class, note in kpi_items
            )
            + "</div></div>",
            unsafe_allow_html=True,
        )
        with st.expander("Kör részletei - műszakok és kifutott túrák", expanded=False):
            route_source_label = "courier_settlement_summary" if summary_available else "route_detail"
            st.dataframe(
                pd.DataFrame([
                    {
                        "Mutató": "MűszakPro foglalt műszak",
                        "Darab": booked_shift_count,
                        "Forrás": str(booking_summary.get("source") or "-"),
                    },
                    {
                        "Mutató": "Giriton műszak",
                        "Darab": giriton_shift_count,
                        "Forrás": str(giriton_shift_summary.get("source") or "-"),
                    },
                    {
                        "Mutató": "Kifutott túra",
                        "Darab": route_total,
                        "Forrás": route_source_label,
                    },
                    {
                        "Mutató": "Cím / rendelés",
                        "Darab": order_total,
                        "Forrás": route_source_label,
                    },
                ]),
                hide_index=True,
                use_container_width=True,
            )

        kiflis_bonus_malus_effect = imported_bonus_total - imported_malus_total
        jitt_bonus_malus_effect = manual_bonus_total - manual_malus_total
        mobile_monthly_bonus = imported_bonus_total + manual_bonus_total
        mobile_monthly_malus = imported_malus_total + manual_malus_total
        mobile_income_total = (
            base_total + tip_total + delay_total + compliance_total
            + imported_bonus_total + manual_bonus_total + loyalty_total + customer_rating_total
            + correction_income_total
        )
        mobile_deduction_total = -(
            mobile_monthly_malus + atm_deduction_total + other_expense_total
            + correction_deduction_total + salary_advance_total + reserve_addition_total + insurance_fee_total
        )
        mobile_default_rows = pd.DataFrame([
            {"item_key": "payable", "item_label": "Teljes összeg", "amount_kind": "huf", "amount_value": payable_total, "note": "Valós elszámolási adat"},
            {"item_key": "income", "item_label": "Jóváírások", "amount_kind": "huf", "amount_value": mobile_income_total, "note": "Valós elszámolási adat"},
            {"item_key": "deductions", "item_label": "Levonások összesen", "amount_kind": "huf", "amount_value": mobile_deduction_total, "note": "Valós elszámolási adat"},
            {"item_key": "performance", "item_label": "Teljesítmény", "amount_kind": "count", "amount_value": order_total, "note": "Valós elszámolási adat"},
            {"item_key": "base", "item_label": "Alapdíj", "amount_kind": "huf", "amount_value": base_total, "note": "Valós elszámolási adat"},
            {"item_key": "tip", "item_label": "Borravaló", "amount_kind": "huf", "amount_value": tip_total, "note": "Valós elszámolási adat"},
            {"item_key": "delay_bonus", "item_label": "Késedelmi díj", "amount_kind": "huf", "amount_value": delay_total, "note": "Valós elszámolási adat"},
            {"item_key": "compliance_bonus", "item_label": "Túramegfelelés", "amount_kind": "huf", "amount_value": compliance_total, "note": "Valós elszámolási adat"},
            {"item_key": "loyalty_bonus", "item_label": "Lojalitási bónusz", "amount_kind": "huf", "amount_value": loyalty_total, "note": "Valós elszámolási adat"},
            {"item_key": "customer_rating", "item_label": "Ügyfélértékelési bónusz", "amount_kind": "huf", "amount_value": customer_rating_total, "note": "Valós elszámolási adat"},
            {"item_key": "correction", "item_label": "Korrekciók összesen", "amount_kind": "huf", "amount_value": correction_total, "note": "Valós elszámolási adat"},
            {"item_key": "correction_income", "item_label": "Korrekció +", "amount_kind": "huf", "amount_value": correction_income_total, "note": "Valós elszámolási adat"},
            {"item_key": "correction_deduction", "item_label": "Korrekció -", "amount_kind": "huf", "amount_value": -correction_deduction_total, "note": "Valós elszámolási adat"},
            {"item_key": "kiflis_bonus_malus", "item_label": "Kiflis levonások / bónuszok", "amount_kind": "huf", "amount_value": kiflis_bonus_malus_effect, "note": "Excel import tételek összesen"},
            {"item_key": "monthly_bonus", "item_label": "Kiflis bónusz", "amount_kind": "huf", "amount_value": imported_bonus_total, "note": imported_bonus_note or "Valós elszámolási adat"},
            {"item_key": "monthly_malus", "item_label": "Kiflis malus", "amount_kind": "huf", "amount_value": -imported_malus_total, "note": imported_malus_note or "Valós elszámolási adat"},
            {"item_key": "bonus_malus", "item_label": "JITT bónusz / malus", "amount_kind": "huf", "amount_value": jitt_bonus_malus_effect, "note": "Sheet/DB tételek összesen"},
            {"item_key": "manual_bonus", "item_label": "JITT bónusz", "amount_kind": "huf", "amount_value": manual_bonus_total, "note": "Sheet/DB tételek"},
            {"item_key": "manual_malus", "item_label": "JITT malus", "amount_kind": "huf", "amount_value": -manual_malus_total, "note": "Sheet/DB tételek"},
            {"item_key": "atm_effect", "item_label": "ATM hatás", "amount_kind": "huf", "amount_value": -atm_deduction_total, "note": "Valós elszámolási adat"},
            {"item_key": "salary_advance", "item_label": "Fizetés előleg", "amount_kind": "huf", "amount_value": -salary_advance_total, "note": "Valós elszámolási adat"},
            {"item_key": "reserve", "item_label": "Céltartalék", "amount_kind": "huf", "amount_value": -reserve_addition_total, "note": "Valós elszámolási adat"},
            {"item_key": "insurance_fee", "item_label": "Biztosítási díj", "amount_kind": "huf", "amount_value": -insurance_fee_total, "note": "Valós elszámolási adat"},
            {"item_key": "orders", "item_label": "Cím", "amount_kind": "count", "amount_value": order_total, "note": "Valós elszámolási adat"},
            {"item_key": "routes", "item_label": "Kör", "amount_kind": "count", "amount_value": route_total, "note": "Valós elszámolási adat"},
            {"item_key": "highlighted_routes", "item_label": "Kiemelt kör", "amount_kind": "count", "amount_value": highlighted_route_total, "note": "Valós elszámolási adat"},
            {"item_key": "normal_routes", "item_label": "Normál kör", "amount_kind": "count", "amount_value": normal_route_total, "note": "Valós elszámolási adat"},
            {"item_key": "loyalty_previous_normal_routes", "item_label": "Lojalitás: előző havi normál kör", "amount_kind": "count", "amount_value": loyalty_previous_routes, "note": "Valós elszámolási adat"},
            {"item_key": "loyalty_current_normal_routes", "item_label": "Lojalitás: aktuális normál kör", "amount_kind": "count", "amount_value": loyalty_current_routes, "note": "Valós elszámolási adat"},
            {"item_key": "loyalty_advance_booking_days", "item_label": "Lojalitás: előre foglalt műszak", "amount_kind": "count", "amount_value": loyalty_advance_booking_days, "note": "Valós elszámolási adat"},
            {"item_key": "shift_count", "item_label": "Műszak", "amount_kind": "count", "amount_value": 0, "note": "Valós elszámolási adat"},
            {"item_key": "late_count", "item_label": "Késések száma", "amount_kind": "count", "amount_value": 0, "note": "Valós elszámolási adat"},
            {"item_key": "delayed_orders", "item_label": "Késéses cím", "amount_kind": "count", "amount_value": 0, "note": "Valós elszámolási adat"},
            {"item_key": "no_show_count", "item_label": "Nem jelent meg műszakban", "amount_kind": "count", "amount_value": 0, "note": "Valós elszámolási adat"},
        ])
        kiflis_detail_rows = append_kiflis_bonus_malus_mobile_rows(
            [],
            {"Courier ID": courier_id, "Futár": courier_name},
            session_id,
        )
        if kiflis_detail_rows:
            mobile_default_rows = pd.concat(
                [mobile_default_rows, pd.DataFrame(kiflis_detail_rows)],
                ignore_index=True,
            )
        if not periodic_correction_detail.empty:
            periodic_mobile_rows = []
            for correction_index, correction_row in periodic_correction_detail.reset_index(drop=True).iterrows():
                correction_amount = parse_huf_value(correction_row.get("Összeg"))
                if not correction_amount:
                    continue
                correction_note_parts = [
                    str(correction_row.get("Napok") or "").strip(),
                    str(correction_row.get("Túratípus") or "").strip(),
                    str(correction_row.get("Feltétel") or "").strip(),
                    str(correction_row.get("Számítás") or "").strip(),
                ]
                correction_note = " | ".join(part for part in correction_note_parts if part)
                periodic_mobile_rows.append({
                    "item_key": f"correction_periodic_{correction_index + 1}",
                    "item_label": str(correction_row.get("Tétel") or "Időszakos díj"),
                    "amount_kind": "huf",
                    "amount_value": correction_amount,
                    "note": correction_note or "Időszakos díj szabály alapján",
                })
            if periodic_mobile_rows:
                mobile_default_rows = pd.concat(
                    [mobile_default_rows, pd.DataFrame(periodic_mobile_rows)],
                    ignore_index=True,
                )
        mobile_overrides = load_mobile_breakdown_overrides(courier_id, period_start)
        if not mobile_overrides.empty:
            mobile_default_rows = mobile_default_rows.set_index("item_key")
            for _, override_row in mobile_overrides.iterrows():
                override_note_key = _normalized_field_key(override_row.get("note"))
                if (
                    not override_note_key
                    or "snapshot" in override_note_key
                    or "publikalt" in override_note_key
                    or "valos elszamolasi adat" in override_note_key
                ):
                    continue
                item_key = str(override_row.get("item_key") or "")
                if item_key in mobile_default_rows.index:
                    for column in ["item_label", "amount_value", "amount_kind", "note"]:
                        mobile_default_rows.loc[item_key, column] = override_row.get(column)
            mobile_default_rows = mobile_default_rows.reset_index()
        mobile_editor = mobile_default_rows.rename(columns={
            "item_key": "Kulcs",
            "item_label": "Megnevezés",
            "amount_kind": "Típus",
            "amount_value": "Érték",
            "note": "Megjegyzés",
        })
        st.markdown("#### Mobilon látható értékek")
        edited_mobile = st.data_editor(
            mobile_editor,
            hide_index=True,
            use_container_width=True,
            key=f"mobile_breakdown_editor_{courier_id}_{period_start:%Y%m}",
            disabled=["Kulcs"],
            column_config={
                "Kulcs": st.column_config.TextColumn("Kulcs"),
                "Megnevezés": st.column_config.TextColumn("Megnevezés"),
                "Típus": st.column_config.SelectboxColumn("Típus", options=["huf", "count"], required=True),
                "Érték": st.column_config.NumberColumn("Érték", step=1, format="%d"),
                "Megjegyzés": st.column_config.TextColumn("Megjegyzés"),
            },
        )
        if st.button("Mobil értékek mentése", type="primary", use_container_width=True, key=f"save_mobile_breakdown_{courier_id}_{period_start:%Y%m}"):
            saved = save_mobile_breakdown_overrides(
                courier_id,
                period_start,
                edited_mobile.to_dict("records"),
                str(st.session_state.get("user", {}).get("username") or "unknown"),
            )
            if saved:
                st.success("Mobilon látható értékek mentve.")
                st.rerun()
            else:
                st.error("A mobil értékek mentése sikertelen. Futtasd a mobile_settlement_breakdown_overrides SQL-t.")

        tig_breakdown = build_tig_breakdown(
            {
                "name": courier_name,
                "company_name": profile.get("company_name") or courier_name,
                "address": profile.get("address") or profile.get("company_address") or "",
                "tax_number": profile.get("tax_number") or profile.get("tax_id") or "",
                "tig_type": profile.get("tig_type") or profile.get("tig_mode") or profile.get("invoice_type") or profile.get("invoice_vat_type") or profile.get("vat_status") or "",
                "vat_status": profile.get("vat_status") or "",
                "id": courier_id,
                "document_month": period_start,
            },
            {
                "payable": payable_total,
                "cash": abs(atm_deduction_total),
                "tip": tip_total,
            },
        )
        st.markdown("#### Mobilon lĂˇthatĂł TIG")
        st.caption("A TIG is az oldalon jelenik meg. A KP kĂĽlĂ¶n sor, a KP levonĂˇsa kĂĽlĂ¶n sor.")
        edited_tig_mobile = st.data_editor(
            tig_editor_rows_from_breakdown(tig_breakdown, mobile_overrides),
            hide_index=True,
            use_container_width=True,
            key=f"mobile_tig_breakdown_editor_{courier_id}_{period_start:%Y%m}",
            disabled=["Kulcs", "TĂ­pus"],
            column_config={
                "Kulcs": st.column_config.TextColumn("Kulcs"),
                "MegnevezĂ©s": st.column_config.TextColumn("MegnevezĂ©s"),
                "TĂ­pus": st.column_config.SelectboxColumn("TĂ­pus", options=["huf", "count"], required=True),
                "Ă‰rtĂ©k": st.column_config.NumberColumn("Ă‰rtĂ©k", step=1, format="%d"),
                "MegjegyzĂ©s": st.column_config.TextColumn("MegjegyzĂ©s"),
            },
        )
        if st.button("TIG mobil Ă©rtĂ©kek mentĂ©se", type="primary", use_container_width=True, key=f"save_mobile_tig_breakdown_{courier_id}_{period_start:%Y%m}"):
            saved = save_mobile_breakdown_overrides(
                courier_id,
                period_start,
                edited_tig_mobile.to_dict("records"),
                str(st.session_state.get("user", {}).get("username") or "unknown"),
            )
            if saved:
                st.success("Mobilon lĂˇthatĂł TIG mentve.")
                st.rerun()
            else:
                st.error("A TIG mobil Ă©rtĂ©kek mentĂ©se sikertelen. Futtasd a mobile_settlement_breakdown_overrides SQL-t.")

        payable_sources = pd.DataFrame([
            {"Művelet": "+", "Tétel": "Alapdíj", "Összeg": display_base_total},
            {"Művelet": "+", "Tétel": "Borravaló", "Összeg": tip_total},
            {"Művelet": "+", "Tétel": "Késedelmi díj", "Összeg": delay_total},
            {"Művelet": "+", "Tétel": "Túramegfelelés", "Összeg": compliance_total},
            {"Művelet": "+", "Tétel": "Kiflis bónusz", "Összeg": imported_bonus_total},
            {"Művelet": "+", "Tétel": "JITT bónusz", "Összeg": manual_bonus_total},
            {"Művelet": "+", "Tétel": "Lojalitás", "Összeg": loyalty_total},
            {"Művelet": "+", "Tétel": "Ügyfélértékelés", "Összeg": customer_rating_total},
            {"Művelet": "+", "Tétel": "Korrekció +", "Összeg": correction_income_total},
            {"Művelet": "-", "Tétel": "Kiflis malus", "Összeg": imported_malus_total},
            {"Művelet": "-", "Tétel": "JITT malus", "Összeg": manual_malus_total},
            {"Művelet": "-", "Tétel": "ATM levonás", "Összeg": atm_deduction_total},
            {"Művelet": "-", "Tétel": "Egyéb kiadás", "Összeg": other_expense_total},
            {"Művelet": "-", "Tétel": "Korrekció -", "Összeg": correction_deduction_total},
            {"Művelet": "-", "Tétel": "Fizetés előleg", "Összeg": salary_advance_total},
            {"Művelet": "-", "Tétel": "Céltartalék 10%", "Összeg": reserve_addition_total},
            {"Művelet": "-", "Tétel": "Biztosítási díj", "Összeg": insurance_fee_total},
            {"Művelet": "=", "Tétel": "Kifizetendő", "Összeg": payable_total},
        ])
        payable_sources = payable_sources.loc[
            payable_sources["Összeg"].ne(0) | payable_sources["Művelet"].eq("=")
        ].copy()
        payable_sources["Összeg"] = payable_sources["Összeg"].map(format_huf)

        finance_left, finance_right = st.columns([0.38, 0.62], gap="medium")
        with finance_left:
            st.markdown(
                '<div class="settlement-profile-shell"><div class="finance-panel-head"><div class="finance-panel-title">Kifizetendő levezetése</div><span class="settlement-info">i</span></div></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(
                payable_sources,
                use_container_width=True,
                hide_index=True,
            )

        with finance_right:
            st.markdown('<div class="settlement-profile-shell"><div class="finance-panel-title">Aktuális hónap szerkeszthető tételei</div></div>', unsafe_allow_html=True)
            ct_a, ct_b, ct_c = st.columns(3)
            ct_a.metric("CT nyitó", format_huf(reserve_before_total))
            ct_b.metric("CT_NY_FT", format_huf(reserve_addition_total))
            ct_c.metric("CT záró", format_huf(reserve_after_total))
            if closure_done:
                st.success("✓ Havi zárás megtörtént.")

            with st.popover("✓ Havi zárás" if closure_done else "Havi zárás", use_container_width=True):
                invoice_default = str(monthly_closure.get("invoice_number") or load_latest_invoice_number(courier_id, period_start) or "")
                invoice_number = st.text_input("Feltöltött számla sorszáma", value=invoice_default, key=f"monthly_close_invoice_{courier_id}")
                recipient_name = str(monthly_closure.get("recipient_name") or profile.get("company_name") or row["Futár"] or "")
                bank_account = format_bank_account_4(monthly_closure.get("bank_account_number") or profile.get("bank_account_number") or "")
                payment_note = str(monthly_closure.get("payment_note") or f"{courier_id}-{invoice_number}".strip("-"))
                st.text_input(
                    "Közlemény",
                    value=payment_note,
                    disabled=True,
                    key=f"monthly_close_note_{courier_id}_{invoice_number}",
                )
                st.caption("Kattints bármelyik mezőre, és az érték a vágólapra kerül.")
                copy_cards_html([
                    ("Számlaszám", bank_account),
                    ("Név", recipient_name),
                    ("Közlemény", payment_note),
                    ("Fizetendő összeg", format_huf(payable_total)),
                ])
                close_disabled = closure_done
                if st.button("Zárás", type="primary", use_container_width=True, disabled=close_disabled, key=f"monthly_close_{courier_id}"):
                    try:
                        close_target_reserve_month(session_id, courier_id, period_start, period_end, reserve_month)
                        close_salary_advance_installments(courier_id, period_start, period_end)
                        save_courier_monthly_closure(
                            session_id,
                            courier_id,
                            str(row["Futár"]),
                            period_start,
                            period_end,
                            {
                                "bank_account_number": bank_account,
                                "recipient_name": recipient_name,
                                "payment_note": payment_note,
                                "invoice_number": invoice_number,
                                "payable_huf": payable_total,
                            },
                            {
                                "base_huf": base_total,
                                "tip_huf": tip_total,
                                "delay_bonus_huf": delay_total,
                                "compliance_bonus_huf": compliance_total,
                                "bonus_huf": bonus_total,
                                "loyalty_huf": loyalty_total,
                                "customer_rating_huf": customer_rating_total,
                                "malus_huf": malus_total,
                                "atm_deduction_huf": atm_deduction_total,
                                "other_expense_huf": other_expense_total,
                                "salary_advance_huf": salary_advance_total,
                                "reserve_addition_huf": reserve_addition_total,
                                "insurance_fee_huf": insurance_fee_total,
                                "reserve_before_huf": reserve_before_total,
                                "reserve_after_huf": reserve_after_total,
                                "payable_huf": payable_total,
                            },
                        )
                        st.success("A futár havi elszámolása lezárva.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A havi zárás sikertelen. Futtasd le a havi zárás migrációkat. Részlet: {exc}")
                if closure_done:
                    st.warning("A visszanyitás visszaállítja a céltartalékot a zárás előtti értékre, és az aktuális havi előleg részletet újra nyitottra állítja.")
                    if st.button("Havi zárás visszanyitása", use_container_width=True, key=f"monthly_reopen_{courier_id}"):
                        try:
                            reopen_courier_monthly_closure(courier_id, period_start, period_end)
                            reopen_target_reserve_month(courier_id, period_start, period_end)
                            reopen_salary_advance_installments(courier_id, period_start, period_end)
                            st.success("A futár havi elszámolása visszanyitva.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"A havi zárás visszanyitása sikertelen. Futtasd le a visszanyitás migrációt. Részlet: {exc}")

        adjustment_type_labels = {
            "bonus": "Bónusz",
            "malus": "Malus",
            "atm_deduction": "ATM levonás",
            "other_expense": "Egyéb kiadás",
            "customer_rating": "Ügyfélértékelés",
            "correction_income": "Korrekció +",
            "correction_deduction": "Korrekció -",
            "manual_correction": "Kézi korrekció +",
            "manual_correction_deduction": "Kézi korrekció -",
        }
        adjustment_type_values = {label: key for key, label in adjustment_type_labels.items()}
        editor_columns = ["id", "Típus", "Összeg", "Megjegyzés", "Érvényes ettől", "Érvényes eddig", "Törlés"]
        if adjustments.empty:
            editor_df = pd.DataFrame(
                [
                    {"id": "", "Típus": "Bónusz", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Ügyfélértékelés", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Málusz", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Korrekció +", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Korrekció -", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "ATM levonás", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Egyéb kiadás", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                ],
                columns=editor_columns,
            )
        else:
            editor_df = adjustments.copy()
            editor_df["Típus"] = editor_df["adjustment_type"].map(adjustment_type_labels).fillna(editor_df["adjustment_type"])
            editor_df["Összeg"] = pd.to_numeric(editor_df["amount_huf"], errors="coerce").fillna(0.0)
            editor_df["Megjegyzés"] = editor_df.get("note", pd.Series("", index=editor_df.index)).fillna("")
            editor_df["Érvényes ettől"] = pd.to_datetime(editor_df.get("valid_from"), errors="coerce").dt.date
            editor_df["Érvényes eddig"] = pd.to_datetime(editor_df.get("valid_to"), errors="coerce").dt.date
            editor_df["Törlés"] = False
            editor_df = editor_df[editor_columns]

        with finance_right:
            edited_adjustments = st.data_editor(
                editor_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=f"finance_adjustment_editor_{courier_id}",
                disabled=["id"],
                column_order=["Típus", "Összeg", "Megjegyzés", "Érvényes ettől", "Érvényes eddig", "Törlés"],
                column_config={
                    "id": st.column_config.TextColumn("ID", help="Belső azonosító", width="small"),
                    "Típus": st.column_config.SelectboxColumn("Típus", options=list(adjustment_type_values.keys()), required=True),
                    "Összeg": st.column_config.NumberColumn("Összeg (Ft)", min_value=0, step=100, format="%d"),
                    "Megjegyzés": st.column_config.TextColumn("Megjegyzés"),
                    "Érvényes ettől": st.column_config.DateColumn("Érvényes ettől"),
                    "Érvényes eddig": st.column_config.DateColumn("Érvényes eddig"),
                    "Törlés": st.column_config.CheckboxColumn("Törlés"),
                },
            )
            st.markdown('<div class="finance-note">A pozitív összeg növeli, a levonás típusú sor csökkenti a kifizetendő összeget.</div>', unsafe_allow_html=True)
            save_col, reset_col = st.columns([0.46, 0.54])
            save_clicked = save_col.button("Változások mentése", type="primary", use_container_width=True, key=f"finance_save_adjustments_{courier_id}")
            reset_clicked = reset_col.button("Havi kézi tételek visszaállítása", use_container_width=True, key=f"reset_adjustments_{courier_id}", help="A kézi korrekciók inaktiválódnak, az alap DB-értékek maradnak.")

        def editor_date(value: object, fallback: date | None = None) -> date | None:
            if value is None or value == "":
                return fallback
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.isna(parsed):
                return fallback
            return parsed.date()

        if save_clicked:
            try:
                original_by_id = {str(item.get("id")): item for _, item in adjustments.iterrows()} if not adjustments.empty else {}
                saved_changes = 0
                for _, edited in edited_adjustments.iterrows():
                    adjustment_id = str(edited.get("id") or "").strip()
                    label = str(edited.get("Típus") or "").strip()
                    adjustment_type = adjustment_type_values.get(label)
                    amount = parse_huf_value(edited.get("Összeg"))
                    note = str(edited.get("Megjegyzés") or "").strip()
                    valid_from = editor_date(edited.get("Érvényes ettől"), period_start) or period_start
                    valid_to = editor_date(edited.get("Érvényes eddig"), None)
                    marked_for_delete = bool(edited.get("Törlés"))

                    if not adjustment_type:
                        continue
                    if valid_to and valid_to < valid_from:
                        st.error("A záródátum nem lehet korábbi a kezdődátumnál.")
                        return

                    if adjustment_id:
                        original = original_by_id.get(adjustment_id)
                        if original is None:
                            continue
                        if marked_for_delete:
                            delete_courier_adjustment(session_id, courier_id, adjustment_id, str(original.get("adjustment_type")), parse_huf_value(original.get("amount_huf")), note)
                            saved_changes += 1
                            continue
                        original_from = editor_date(original.get("valid_from"), period_start)
                        original_to = editor_date(original.get("valid_to"), None)
                        changed = (
                            str(original.get("adjustment_type")) != adjustment_type
                            or parse_huf_value(original.get("amount_huf")) != amount
                            or str(original.get("note") or "") != note
                            or original_from != valid_from
                            or original_to != valid_to
                        )
                        if changed:
                            update_courier_adjustment(session_id, courier_id, adjustment_id, adjustment_type, amount, note, valid_from, valid_to, original.to_dict())
                            saved_changes += 1
                    elif amount > 0 and not marked_for_delete:
                        save_courier_adjustment(session_id, courier_id, adjustment_type, amount, note, valid_from, valid_to)
                        saved_changes += 1
                if saved_changes:
                    refresh_settlement_profile_data()
                    st.success(f"{saved_changes} módosítás mentve és naplózva.")
                    rerun_courier_profile("Pénzügy")
                else:
                    st.info("Nem volt mentendő változás.")
            except Exception as exc:
                st.error(f"A tételek nem menthetők. Futtasd le az adjustment edit migrációt. Részlet: {exc}")

        if reset_clicked:
            try:
                reset_courier_adjustments(session_id, courier_id, period_start, period_end)
                refresh_settlement_profile_data()
                rerun_courier_profile("Pénzügy")
            except Exception as exc:
                st.error(f"A visszaállítás nem menthető. Részlet: {exc}")

        adjustment_log = load_courier_adjustment_log(courier_id)
        st.markdown('<div class="settlement-profile-shell"><div class="finance-log-panel"><div class="finance-panel-title">Módosítási napló</div></div></div>', unsafe_allow_html=True)
        if adjustment_log.empty:
            st.info("Még nincs naplózott módosítás ennél a futárnál.")
        else:
            log_view = adjustment_log.rename(columns={"event_type": "Művelet", "adjustment_type": "Típus", "amount_huf": "Összeg", "note": "Megjegyzés", "performed_by": "Felhasználó", "created_at": "Időpont"}).copy()
            log_view["Művelet"] = log_view["Művelet"].map({"created": "Létrehozva", "updated": "Módosítva", "deleted": "Törölve", "reset": "Visszaállítás"}).fillna(log_view["Művelet"])
            log_view["Típus"] = log_view["Típus"].map(adjustment_type_labels).fillna("-")
            log_view["Összeg"] = log_view["Összeg"].map(lambda value: format_huf(value) if pd.notna(value) else "-")
            st.dataframe(log_view, use_container_width=True, hide_index=True)

    if selected_menu == "Kifizetés":
        st.markdown("#### Kifizetés")
        payment_month = period_start.replace(day=1)
        actor = str(st.session_state.get("user", {}).get("username") or "unknown")
        try:
            workflow_statuses = read_peopleforce_card_statuses(courier_id, payment_month)
        except Exception as exc:
            st.warning(f"A mobilos folyamat státuszok nem tölthetők be: {exc}")
            workflow_statuses = pd.DataFrame()
        invoice_documents = load_courier_payment_documents(courier_id, payment_month)
        advance_requests = load_courier_salary_advance_requests(courier_id)

        process_ids = {""}
        if not workflow_statuses.empty:
            process_ids.update(
                process_id_from_action_key(item.get("action_key"))
                for item in workflow_statuses.to_dict("records")
            )
        if not invoice_documents.empty:
            process_ids.update(
                process_id_from_note(item.get("note"))
                for item in invoice_documents.to_dict("records")
            )
        if not advance_requests.empty:
            current_requests = advance_requests[
                pd.to_datetime(advance_requests.get("start_date"), errors="coerce").dt.date.eq(payment_month)
            ].copy()
            process_ids.update(
                normalize_process_id(item.get("process_id"))
                for item in current_requests.to_dict("records")
                if (
                    normalize_process_id(item.get("process_id"))
                    and str(item.get("status") or "").strip().casefold()
                    not in {"rejected", "cancelled", "closed"}
                )
            )

        status_by_key = {
            str(item.get("action_key") or ""): item
            for item in workflow_statuses.to_dict("records")
        } if not workflow_statuses.empty else {}
        invoice_rows_by_process: dict[str, list[dict[str, object]]] = {}
        if not invoice_documents.empty:
            for item in invoice_documents.to_dict("records"):
                invoice_rows_by_process.setdefault(process_id_from_note(item.get("note")), []).append(item)
        rejected_advance_process_ids = {
            normalize_process_id(item.get("process_id"))
            for item in advance_requests.to_dict("records")
            if (
                normalize_process_id(item.get("process_id"))
                and str(item.get("status") or "").strip().casefold()
                in {"rejected", "cancelled", "closed"}
            )
        } if not advance_requests.empty else set()
        request_by_process = {
            normalize_process_id(item.get("process_id")): item
            for item in advance_requests.to_dict("records")
            if (
                normalize_process_id(item.get("process_id"))
                and str(item.get("status") or "").strip().casefold()
                not in {"rejected", "cancelled", "closed"}
            )
} if not advance_requests.empty else {}

        process_options = []
        for process_id in sorted(
            process_ids,
            key=lambda value: (bool(value), value),
        ):
            if process_id and process_id in rejected_advance_process_ids:
                continue
            request_item = request_by_process.get(process_id, {})

            if process_id:
                request_status = str(
                    request_item.get("status") or ""
                ).strip().casefold()

                if not request_item or request_status in {
                    "rejected",
                    "cancelled",
                    "closed",
                }:
                    continue

            invoice_rows = invoice_rows_by_process.get(process_id, [])
            latest_invoice = invoice_rows[0] if invoice_rows else {}
            invoice_number = (
                invoice_number_from_document(latest_invoice)
                if latest_invoice
                else ""
            )
            invoice_amount = sum(
                invoice_amount_from_document(item)
                for item in invoice_rows
            )
            request_amount = (
                parse_huf_value(request_item.get("requested_amount_huf"))
                if request_item
                else 0
            )

            action_key = process_action_key(
                "invoice_payment",
                process_id,
            )
            payment_status = str(
                (status_by_key.get(action_key) or {}).get("status") or ""
            ).casefold()

            process_options.append({
                "process_id": process_id,
                "label": (
                    "Havi folyamat"
                    if not process_id
                    else f"Egyéb folyamat: {process_id}"
                ),
                "invoice_number": invoice_number,
                "invoice_file": str(latest_invoice.get("file_name") or ""),
                "invoice_title": str(latest_invoice.get("title") or ""),
                "amount": (
                    request_amount
                    if request_item
                    else invoice_amount or (
                        payable_total if not process_id else 0
                    )
                ),
                "status": (
                    "Lezárva"
                    if payment_status == "done"
                    or (not process_id and closure_done)
                    else "Nyitott"
                ),
                "request": request_item,
            })

        if not process_options:
            st.info("Nincs kifizethető folyamat az aktuális hónapban.")
        else:
            option_labels = [item["label"] for item in process_options]
            selected_payment_label = st.selectbox(
                "Folyamat",
                option_labels,
                key=f"payment_process_{courier_id}_{payment_month:%Y%m}",
            )
            payment_item = process_options[option_labels.index(selected_payment_label)]
            process_id = str(payment_item["process_id"])
            invoice_number_default = str(payment_item.get("invoice_number") or "")
            if not invoice_number_default and not process_id:
                invoice_number_default = str(monthly_closure.get("invoice_number") or load_latest_invoice_number(courier_id, period_start) or "")
            invoice_number = st.text_input(
                "Feltöltött számla sorszáma",
                value=invoice_number_default,
                key=f"payment_invoice_{courier_id}_{process_id or 'monthly'}",
            )
            recipient_name = str(monthly_closure.get("recipient_name") or profile.get("company_name") or row["Futár"] or "")
            bank_account = format_bank_account_4(monthly_closure.get("bank_account_number") or profile.get("bank_account_number") or "")
            amount_huf = parse_huf_value(payment_item.get("amount"))
            payment_note = f"{courier_id}-{invoice_number}".strip("-")

            st.markdown(
                f"""
                <div class="settlement-profile-shell">
                <div class="finance-kpi-grid">
                    <div class="finance-kpi"><div class="finance-kpi-label">Folyamat</div><div class="finance-kpi-value">{html.escape(str(payment_item['label']))}</div></div>
                    <div class="finance-kpi"><div class="finance-kpi-label">Státusz</div><div class="finance-kpi-value">{html.escape(str(payment_item['status']))}</div></div>
                    <div class="finance-kpi payable"><div class="finance-kpi-label">Összeg</div><div class="finance-kpi-value">{format_huf(amount_huf)}</div></div>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            copy_cards_html([
                ("Bankszámlaszám", bank_account),
                ("Közlemény", payment_note),
                ("Név", recipient_name),
                ("Összeg", format_huf(amount_huf)),
            ])
            if payment_item.get("invoice_file"):
                st.caption(f"Feltöltött számla: {payment_item.get('invoice_title') or payment_item.get('invoice_file')}")

            reject_note = st.text_area(
                "Elutasítás megjegyzés",
                key=f"payment_reject_note_{courier_id}_{process_id or 'monthly'}",
                placeholder="Röviden írd le, miért utasítjuk el / vonjuk vissza.",
            )
            close_disabled = str(payment_item.get("status")) == "Lezárva"
            close_col, reject_col = st.columns(2)
            if close_col.button("Havi zárás" if not process_id else "Folyamat lezárása", type="primary", use_container_width=True, disabled=close_disabled, key=f"payment_close_{courier_id}_{process_id or 'monthly'}"):
                try:
                    if process_id:
                        request_item = payment_item.get("request") or {}
                        if str(request_item.get("status") or "").casefold() == "approved":
                            mark_salary_advance_request_paid(request_item, courier_name)
                        upsert_peopleforce_card_status(
                            courier_id=courier_id,
                            courier_name=str(row["Futár"]),
                            action_key=process_action_key("invoice_payment", process_id),
                            document_month=payment_month,
                            status="done",
                            status_note=f"Kifizetve: {format_huf(amount_huf)}; közlemény: {payment_note}",
                            updated_by=actor,
                        )
                    else:
                        close_target_reserve_month(session_id, courier_id, period_start, period_end, reserve_month)
                        close_salary_advance_installments(courier_id, period_start, period_end)
                        save_courier_monthly_closure(
                            session_id,
                            courier_id,
                            str(row["Futár"]),
                            period_start,
                            period_end,
                            {
                                "bank_account_number": bank_account,
                                "recipient_name": recipient_name,
                                "payment_note": payment_note,
                                "invoice_number": invoice_number,
                                "payable_huf": amount_huf,
                            },
                            {
                                "base_huf": base_total,
                                "tip_huf": tip_total,
                                "bonus_huf": imported_bonus_total + manual_bonus_total + loyalty_total + customer_rating_total,
                                "malus_huf": malus_total,
                                "atm_deduction_huf": atm_deduction_total,
                                "other_expense_huf": other_expense_total,
                                "salary_advance_huf": salary_advance_total,
                                "reserve_addition_huf": reserve_addition_total,
                                "insurance_fee_huf": insurance_fee_total,
                                "payable_huf": amount_huf,
                            },
                        )
                        upsert_peopleforce_card_status(
                            courier_id=courier_id,
                            courier_name=str(row["Futár"]),
                            action_key="invoice_payment",
                            document_month=payment_month,
                            status="done",
                            status_note=f"Havi zárás és kifizetés megtörtént: {format_huf(amount_huf)}",
                            updated_by=actor,
                        )
                    st.success("Kifizetés lezárva.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"A kifizetés lezárása sikertelen: {exc}")
            reject_label = "Havi kifizetés elutasítása / visszanyitás" if not process_id else "Elutasítás / folyamat visszavonása"
            if reject_col.button(reject_label, use_container_width=True, key=f"payment_reject_{courier_id}_{process_id or 'monthly'}"):
                try:
                    response = str(reject_note or "").strip()
                    if process_id:
                        request_item = payment_item.get("request") or {}
                        if request_item:
                            reject_salary_advance_request(request_item, courier_name, response)
                        else:
                            delete_peopleforce_process_statuses(courier_id, payment_month, process_id)
                    else:
                        reopen_courier_monthly_closure(courier_id, period_start, period_end)
                        reopen_target_reserve_month(courier_id, period_start, period_end)
                        reopen_salary_advance_installments(courier_id, period_start, period_end)
                        upsert_peopleforce_card_status(
                            courier_id=courier_id,
                            courier_name=str(row["Futár"]),
                            action_key="invoice_payment",
                            document_month=payment_month,
                            status="open",
                            status_note=f"Havi kifizetés elutasítva / visszanyitva. {response}".strip(),
                            updated_by=actor,
                        )
                    st.success("A kifizetés elutasítva, a kapcsolódó folyamat visszavonva.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"A kifizetés elutasítása sikertelen: {exc}")

    if selected_menu == "Fizetés előleg":
        st.markdown("#### Fizetés előleg")
        current_installments = load_courier_salary_advance_current(courier_id, period_start, period_end)
        current_amount = (
            pd.to_numeric(current_installments.get("amount_huf"), errors="coerce").fillna(0.0).sum()
            if not current_installments.empty else 0.0
        )
        status_text = "Van aktuális nyitott részlet" if current_amount else "Nincs aktuális nyitott részlet"
        st.markdown(
            f"""
            <div class="settlement-profile-shell">
            <div class="finance-kpi-grid">
                <div class="finance-kpi"><div class="finance-kpi-label">Aktuális havi levonás</div><div class="finance-kpi-value">{format_huf(current_amount)}</div></div>
                <div class="finance-kpi"><div class="finance-kpi-label">Státusz</div><div class="finance-kpi-value">{html.escape(status_text)}</div></div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        form_left, form_right = st.columns([0.42, 0.58], gap="medium")
        with form_left:
            with st.form(f"salary_advance_form_{courier_id}", clear_on_submit=False):
                requested_amount = st.number_input("Igényelt összeg (Ft)", min_value=0, max_value=10_000_000, step=1000, value=0, key=f"salary_advance_amount_{courier_id}")
                installment_months = st.number_input("Havi bontás (hónap)", min_value=1, max_value=60, step=1, value=1, key=f"salary_advance_months_{courier_id}")
                start_date = st.date_input("Kezdő dátum", value=period_start, key=f"salary_advance_start_{courier_id}")
                note = st.text_area("Megjegyzés", key=f"salary_advance_note_{courier_id}")
                preview_amounts = salary_advance_installment_amounts(requested_amount, int(installment_months))
                preview_monthly = preview_amounts[0] if preview_amounts else 0
                st.info(f"Havi levonás: {format_huf(preview_monthly)}")
                save_advance = st.form_submit_button("Admin előleg igény indítása", type="primary", use_container_width=True)
            if save_advance:
                if requested_amount <= 0:
                    st.error("Az igényelt összegnek pozitívnak kell lennie.")
                else:
                    try:
                        create_salary_advance_request(courier_id, courier_name, requested_amount, int(installment_months), start_date, note)
                        st.success("A fizetés előleg igény rögzítve. Jóváhagyás után indul a folyamat.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A fizetés előleg nem menthető. Futtasd le az előleg DB migrációt. Részlet: {exc}")

        with form_right:
            requests = load_courier_salary_advance_requests(courier_id)
            st.markdown('<div class="settlement-profile-shell"><div class="finance-panel-title">Előleg igények</div></div>', unsafe_allow_html=True)
            if requests.empty:
                st.info("Nincs nyitott vagy korábbi előleg igény ennél a futárnál.")
            else:
                status_labels = {
                    "requested": "Jóváhagyásra vár",
                    "approved": "Jóváhagyva",
                    "paid": "Kifizetve",
                    "closed": "Lezárva",
                    "rejected": "Elutasítva",
                }
                for request_item in requests.to_dict("records"):
                    request_status = str(request_item.get("status") or "requested").strip().lower()
                    request_id = str(request_item.get("id") or "")
                    process_id = str(request_item.get("process_id") or "")
                    amount = parse_huf_value(request_item.get("requested_amount_huf"))
                    months = int(round(parse_huf_value(request_item.get("installment_months"))))
                    monthly = parse_huf_value(request_item.get("monthly_amount_huf"))
                    request_start = pd.to_datetime(request_item.get("start_date"), errors="coerce")
                    start_text = request_start.strftime("%Y. %m.") if not pd.isna(request_start) else "-"
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([0.28, 0.2, 0.22, 0.3])
                        c1.markdown(f"**{status_labels.get(request_status, request_status)}**")
                        c1.caption(f"Kezdés: {start_text}")
                        c2.metric("Összeg", format_huf(amount))
                        c3.metric("Havi levonás", format_huf(monthly), f"{months} hó")
                        c4.caption(f"Folyamat: {process_id or '-'}")
                        if request_status != "rejected":
                            default_start = request_start.date() if not pd.isna(request_start) else period_start
                            with st.form(f"salary_advance_schedule_form_{request_id}", clear_on_submit=False):
                                st.caption("Ütemezés módosítása")
                                schedule_cols = st.columns([0.34, 0.22, 0.44])
                                new_start_date = schedule_cols[0].date_input(
                                    "Új kezdés",
                                    value=default_start,
                                    key=f"salary_advance_schedule_start_{request_id}",
                                )
                                new_months = schedule_cols[1].number_input(
                                    "Hónap",
                                    min_value=1,
                                    max_value=60,
                                    step=1,
                                    value=max(1, months),
                                    key=f"salary_advance_schedule_months_{request_id}",
                                )
                                schedule_note = schedule_cols[2].text_input(
                                    "Módosítás oka",
                                    key=f"salary_advance_schedule_note_{request_id}",
                                    placeholder="Pl. +1 hónapot kér",
                                )
                                preview_schedule = salary_advance_installment_amounts(amount, int(new_months))
                                st.caption(f"Új tervezett havi levonás: {format_huf(preview_schedule[0] if preview_schedule else 0)}")
                                save_schedule = st.form_submit_button("Ütemezés mentése", use_container_width=True)
                            if save_schedule:
                                try:
                                    result_message = update_salary_advance_schedule(
                                        request_item,
                                        courier_name,
                                        new_start_date,
                                        int(new_months),
                                        schedule_note,
                                    )
                                    st.success(result_message)
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Az előleg ütemezés módosítása sikertelen. Részlet: {exc}")
                        reject_response = ""
                        if request_status in {"requested", "approved"}:
                            reject_response = st.text_area(
                                "Elutasítás szöveges válasz",
                                key=f"salary_advance_reject_note_{request_id}",
                                placeholder="Írd le röviden, miért lett elutasítva.",
                            )
                        if request_status == "requested":
                            approve_col, reject_col = st.columns(2)
                            if approve_col.button("Jóváhagyás és folyamat indítása", type="primary", use_container_width=True, key=f"salary_advance_approve_{request_id}"):
                                try:
                                    approved_process = approve_salary_advance_request(request_item, courier_name)
                                    st.success(f"Előleg folyamat elindítva: {approved_process}")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Az előleg igény jóváhagyása sikertelen. Részlet: {exc}")
                            if reject_col.button("Elutasítás", use_container_width=True, key=f"salary_advance_reject_{request_id}"):
                                try:
                                    reject_salary_advance_request(request_item, courier_name, reject_response)
                                    st.success("Az előleg igény elutasítva.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Az előleg igény elutasítása sikertelen. Részlet: {exc}")
                        elif request_status == "approved":
                            paid_col, reject_col = st.columns(2)
                            if paid_col.button("Kifizetve / lezárás", type="primary", use_container_width=True, key=f"salary_advance_paid_{request_id}"):
                                try:
                                    mark_salary_advance_request_paid(request_item, courier_name)
                                    st.success("Az előleg lezárva, a részletek bekerültek az aktuális előleg táblába.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Az előleg lezárása sikertelen. Részlet: {exc}")
                            if reject_col.button("Elutasítás és folyamat lezárása", use_container_width=True, key=f"salary_advance_reject_approved_{request_id}"):
                                try:
                                    reject_salary_advance_request(request_item, courier_name, reject_response)
                                    st.success("Az előleg elutasítva, a kapcsolódó folyamat lezárva.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Az előleg elutasítása sikertelen. Részlet: {exc}")

            history = load_courier_salary_advance_history(courier_id)
            st.markdown('<div class="settlement-profile-shell"><div class="finance-panel-title">Levonási részletek</div></div>', unsafe_allow_html=True)
            if history.empty:
                st.info("Még nincs rögzített fizetés előleg ennél a futárnál.")
            else:
                history_view = history.copy()
                history_view["Időszak"] = pd.to_datetime(history_view.get("period_start"), errors="coerce").dt.strftime("%Y. %m.")
                history_view["Részlet"] = history_view.apply(
                    lambda item: f"{int(parse_huf_value(item.get('installment_no')))} / {int(parse_huf_value(item.get('installment_count')))}",
                    axis=1,
                )
                history_view["Összeg"] = history_view.get("amount_huf", pd.Series(dtype=float)).map(format_huf)
                history_view["Státusz"] = history_view.get("status", pd.Series(dtype=str)).map({"open": "Open", "done": "Done", "cancelled": "Törölve"}).fillna(history_view.get("status", "-"))
                st.dataframe(
                    history_view[["Időszak", "Részlet", "Összeg", "Státusz"]],
                    use_container_width=True,
                    hide_index=True,
                )

    if selected_menu == "Statisztika":
        if str(active_calculation_mode or "API").strip().casefold() == "api":
            render_courier_api_statistics(
                courier_id=courier_id,
                period_start=period_start,
                period_end=period_end,
                warehouse_label=st.session_state.get("new_warehouse", "Összes"),
            )

    if selected_menu == "Útvonalak":
        if route_detail.empty:
            route_detail = load_courier_route_detail(
                courier_id,
                courier_name,
                session_id,
                active_calculation_mode,
                period_start,
                st.session_state.get("new_warehouse", "Összes"),
            )
            route_breakdown = summarize_courier_route_detail(route_detail)
        st.markdown("#### Problémás útvonalak és rendelések")
        stories = load_courier_route_stories(courier_id, period_start, period_end)
        route_ids = route_detail.get("Route ID", pd.Series(dtype=str)).dropna().astype(str).map(normalize_route_key).tolist()
        story_route_ids = stories.get("route_id", pd.Series(dtype=str)).dropna().astype(str).map(normalize_route_key).tolist() if not stories.empty else []
        all_route_ids = sorted({route_id for route_id in [*route_ids, *story_route_ids] if route_id})
        if read_order_details_for_routes is not None and all_route_ids:
            try:
                order_details = read_order_details_for_routes(period_start, period_end, courier_id, all_route_ids)
            except BaseException:
                order_details = pd.DataFrame()
        else:
            order_details = pd.DataFrame()
        reviews = load_route_issue_reviews(courier_id, period_start, period_end)
        delay_issue_rows = load_courier_financial_delay_rows(courier_id, period_start, period_end)
        compliance_issue_rows = load_courier_financial_compliance_rows(courier_id, period_start, period_end)
        route_alert_rows = load_courier_route_alerts_for_period(courier_id, period_start, period_end)
        issue_rows = build_route_issue_rows(
            route_detail,
            stories,
            order_details,
            reviews,
            courier_id,
            delay_issue_rows,
            compliance_issue_rows,
            route_alert_rows,
        )

        open_count = 0 if reviews.empty or "status" not in reviews.columns else int(reviews["status"].isin(["Vizsgálat", "Elfogadva"]).sum())
        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Problémás sor", int(len(issue_rows)))
        metric2.metric("Késő rendelés", int((issue_rows.get("Probléma", pd.Series(dtype=str)) == "Késő rendelés").sum()))
        metric3.metric("Sorba állási gond", int(issue_rows.get("Probléma", pd.Series(dtype=str)).astype(str).str.contains("sorba", case=False, na=False).sum()))
        metric4.metric("Aktív reklamáció", open_count)
        extra1, extra2, extra3 = st.columns(3)
        extra1.metric("API késés", int((issue_rows.get("Probléma", pd.Series(dtype=str)) == "API késés").sum()))
        extra2.metric("Bejelentkezési gond", int(issue_rows.get("Probléma", pd.Series(dtype=str)).astype(str).str.contains("bejelentkezés|No-show", case=False, na=False).sum()))
        extra3.metric("Futár jelzett", int((issue_rows.get("Futár jelzett", pd.Series(dtype=str)) == "Igen").sum()))

        if issue_rows.empty:
            st.success("Az aktuális hónapban nincs késésből vagy sorba állásból látható probléma ennél a futárnál.")
        else:
            editor_key = f"route_issue_editor_{courier_id}_{period_start}_{period_end}"
            edited_issues = st.data_editor(
                issue_rows,
                use_container_width=True,
                hide_index=True,
                key=editor_key,
                disabled=[
                    "issue_key", "Route ID", "Order ID", "Dátum", "Probléma", "Eltérés perc",
                    "Rendelések", "Késedelmi díj", "Túramegfelelés", "Futár jelzett", "Bejelentés", "Story",
                ],
                column_order=[
                    "Dátum", "Route ID", "Order ID", "Probléma", "Eltérés perc",
                    "Rendelések", "Késedelmi díj", "Túramegfelelés", "Futár jelzett", "Státusz", "Megjegyzés", "Bejelentés", "Story",
                ],
                column_config={
                    "Dátum": st.column_config.TextColumn("Dátum", width="small"),
                    "Route ID": st.column_config.TextColumn("Route ID", width="small"),
                    "Order ID": st.column_config.TextColumn("Order ID", width="small"),
                    "Probléma": st.column_config.TextColumn("Probléma", width="medium"),
                    "Eltérés perc": st.column_config.NumberColumn("Eltérés perc", step=1, format="%d"),
                    "Rendelések": st.column_config.NumberColumn("Rendelések", step=1, format="%d"),
                    "Késedelmi díj": st.column_config.NumberColumn("Késedelmi díj", step=100, format="%d Ft"),
                    "Túramegfelelés": st.column_config.NumberColumn("Túramegfelelés", step=100, format="%d Ft"),
                    "Futár jelzett": st.column_config.TextColumn("Futár jelzett", width="small"),
                    "Bejelentés": st.column_config.TextColumn("Futár bejelentése", width="large"),
                    "Státusz": st.column_config.SelectboxColumn("Reklamáció státusz", options=ROUTE_ISSUE_STATUSES, required=True),
                    "Megjegyzés": st.column_config.TextColumn("Megjegyzés"),
                    "Story": st.column_config.TextColumn("DSP magyarázat", width="large"),
                },
            )
            save_route_issues = st.button("Reklamációk mentése", type="primary", use_container_width=True, key=f"save_route_issues_{courier_id}")
            if save_route_issues:
                original_by_key = {row["issue_key"]: row for row in issue_rows.to_dict("records")}
                saved = 0
                try:
                    for edited_row in edited_issues.to_dict("records"):
                        issue_key = str(edited_row.get("issue_key") or "")
                        original = original_by_key.get(issue_key, {})
                        status = str(edited_row.get("Státusz") or "Nincs reklamáció")
                        note = str(edited_row.get("Megjegyzés") or "")
                        original_status = str(original.get("Státusz") or "Nincs reklamáció")
                        original_note = str(original.get("Megjegyzés") or "")
                        should_save = (
                            (status != original_status or note.strip() != original_note.strip())
                            and (
                                status != "Nincs reklamáció"
                                or bool(note.strip())
                                or original_status != "Nincs reklamáció"
                                or bool(original_note.strip())
                            )
                        )
                        if should_save:
                            save_route_issue_review(session_id, courier_id, period_start, period_end, edited_row, status, note)
                            saved += 1
                    if saved:
                        st.success(f"{saved} útvonal reklamáció mentve és naplózva.")
                        st.rerun()
                    else:
                        st.info("Nem volt mentendő reklamációs változás.")
                except Exception as exc:
                    st.error(f"A reklamációk nem menthetők. Futtasd le az útvonal reklamáció migrációt. Részlet: {exc}")

        st.markdown("#### Teljes útvonal lista")
        route_view = route_detail.copy()
        if route_view.empty:
            st.info("Ehhez a futárhoz nem található route részlet az aktuális sessionben.")
        else:
            display_columns = [
                "Route ID", "Excel dátum", "Hét napja", "Túratípus",
                "Naptípus", "Rendelések", "Alapdíj", "Kapott összeg", "Borravaló",
                "Késedelmi díj", "Túramegfelelés", "DB státusz",
            ]
            display_columns = [column for column in display_columns if column in route_view.columns]
            for amount_column in ["Alapdíj", "Kapott összeg", "Borravaló", "Késedelmi díj", "Túramegfelelés"]:
                if amount_column in route_view.columns:
                    route_view[amount_column] = route_view[amount_column].map(format_huf)
            st.dataframe(route_view[display_columns], use_container_width=True, hide_index=True)

        st.markdown("#### Túratípus és naptípus szerinti összesítés")
        if route_breakdown.empty:
            st.info("Nincs összesíthető útvonaladat.")
        else:
            breakdown_view = route_breakdown.copy()
            for amount_column in ["Alapdíj", "Borravaló", "Késedelmi díj", "Túramegfelelés", "Bónuszok"]:
                if amount_column in breakdown_view.columns:
                    breakdown_view[amount_column] = breakdown_view[amount_column].map(format_huf)
            st.dataframe(breakdown_view, use_container_width=True, hide_index=True)

    if selected_menu == "Bónusz":
        render_bonus_malus_manager(courier_id, "bonus")

    if selected_menu == "Málusz":
        render_bonus_malus_manager(courier_id, "malus")

    if selected_menu == "Céltartalék":
        reserve_status = load_target_reserve_status(courier_id, str(row["Futár"]))
        reserve_row = reserve_status.get("row") or {}
        reserve_value = next(
            (value for column, value in reserve_row.items() if "ctzft" in re.sub(r"[^a-z0-9]", "", str(column).casefold())),
            None,
        )
        reserve_amount = parse_huf_value(reserve_value)
        st.markdown("#### Céltartalék és biztosítás")

        reserve1, reserve2 = st.columns(2)
        with reserve1:
            st.metric("Biztosítási státusz", "Van biztosítása" if reserve_status["insurance_active"] else "Nincs biztosítása")
            st.caption("Forrás: courier_target_reserve.insurance_active")

        with reserve2:
            st.metric("Aktuális céltartalék", format_huf(reserve_amount))
            st.caption("Forrás: courier_target_reserve.CT_Z_FT")
            if reserve_value is not None:
                st.caption(f"Nyers DB-érték: {reserve_value}")
            if reserve_row and reserve_value is None:
                st.warning("A Courier ID-hoz tartozó sor megvan, de nem található benne CT_Z_FT mező.")
            elif not reserve_row:
                st.warning(f"A {courier_id} Courier ID-hoz nem található courier_target_reserve sor.")

    if selected_menu == "Dokumentumok":
        st.markdown("#### Dokumentumok")
        type_labels = {
            "settlement": "Elszámolás",
            "tig": "TIG",
            "invoice": "Számla",
            "contract": "Szerződés",
            "complaint_response": "Reklamáció válasz",
        }
        workflow_action_labels = {
            "individual_monthly_billing": "Egyedi havi számlázás nyitva",
            "manual_invoice_skip": "Számlázás kihagyása kézzel",
            "settlement": "Elszámolás elfogadása",
            "tig": "TIG elfogadása",
            "invoice_check": "Számlaellenőrzés",
            "invoice_submit": "Számlafeltöltés",
            "invoice_payment": "Számla elfogadva / kifizetés",
            "ignore_complaints_for_billing": "Reklamációk figyelmen kívül hagyása",
            "invoice_validation_override": "Számlaellenőrzés felülbírálása",
        }
        workflow_month = period_start.replace(day=1)
        actor = str(st.session_state.get("user", {}).get("username") or "unknown")
        st.markdown("##### Folyamat státuszok")
        try:
            workflow_statuses = read_peopleforce_card_statuses(courier_id, workflow_month)
        except Exception as exc:
            st.warning(f"A mobilos folyamat státuszok nem tölthetők be: {exc}")
            workflow_statuses = pd.DataFrame()
        status_by_action = {
            str(item.get("action_key") or ""): item
            for item in workflow_statuses.to_dict("records")
        } if not workflow_statuses.empty else {}
        manual_invoice_skip_active = str(
            (status_by_action.get("manual_invoice_skip") or {}).get("status") or ""
        ).casefold() == "done"
        individual_monthly_billing_open = str(
            (status_by_action.get("individual_monthly_billing") or {}).get("status") or ""
        ).casefold() in {"open", "done"}
        skip_col, reset_skip_col, open_billing_col = st.columns(3)
        if skip_col.button(
            "Számlázás kihagyása kézzel",
            type="primary",
            use_container_width=True,
            disabled=manual_invoice_skip_active,
            key=f"manual_invoice_skip_open_{courier_id}_{workflow_month:%Y%m}",
        ):
            try:
                upsert_peopleforce_card_status(
                    courier_id=courier_id,
                    courier_name=str(row["Futár"]),
                    action_key="manual_invoice_skip",
                    document_month=workflow_month,
                    status="done",
                    status_note="Admin kézzel kihagyta a számlafeltöltést ehhez a havi folyamathoz.",
                    updated_by=actor,
                )
                for skipped_action, skipped_status, skipped_note in [
                    ("tig", "done", "TIG kézzel kihagyva."),
                    ("invoice_submit", "done", "Számlafeltöltés kézzel kihagyva."),
                    ("invoice_check", "done", "Számlaellenőrzés kézzel kihagyva."),
                    ("invoice_payment", "open", "Számlázás kézzel kihagyva, admin kifizetésre vár."),
                ]:
                    upsert_peopleforce_card_status(
                        courier_id=courier_id,
                        courier_name=str(row["Futár"]),
                        action_key=skipped_action,
                        document_month=workflow_month,
                        status=skipped_status,
                        status_note=skipped_note,
                        updated_by=actor,
                    )
                st.success("A számlázás kézi kihagyása beállítva.")
                st.rerun()
            except Exception as exc:
                st.error(f"A számlázás kézi kihagyása sikertelen: {exc}")
        if reset_skip_col.button(
            "Normál számlázás visszaállítása",
            use_container_width=True,
            disabled=not manual_invoice_skip_active,
            key=f"manual_invoice_skip_reset_{courier_id}_{workflow_month:%Y%m}",
        ):
            try:
                upsert_peopleforce_card_status(
                    courier_id=courier_id,
                    courier_name=str(row["Futár"]),
                    action_key="manual_invoice_skip",
                    document_month=workflow_month,
                    status="open",
                    status_note="Admin visszaállította a normál számlázási folyamatot.",
                    updated_by=actor,
                )
                for reopened_action in ["tig", "invoice_submit", "invoice_check", "invoice_payment"]:
                    upsert_peopleforce_card_status(
                        courier_id=courier_id,
                        courier_name=str(row["Futár"]),
                        action_key=reopened_action,
                        document_month=workflow_month,
                        status="open",
                        status_note="Normál számlázási folyamat visszaállítva.",
                        updated_by=actor,
                    )
                st.success("A normál számlázási folyamat visszaállítva.")
                st.rerun()
            except Exception as exc:
                st.error(f"A normál számlázás visszaállítása sikertelen: {exc}")
        if open_billing_col.button(
            "Egyedi havi számlázás zárása" if individual_monthly_billing_open else "Egyedi havi számlázás nyitása",
            type="secondary" if individual_monthly_billing_open else "primary",
            use_container_width=True,
            disabled=closure_done,
            key=f"docs_open_individual_month_{courier_id}_{workflow_month:%Y%m}",
            help="Nyitáskor publikálja az adott futár havi elszámolását. Záráskor leveszi az egyedi mobil nyitást és törli az így feltöltött tesztdokumentumokat.",
        ):
            try:
                if individual_monthly_billing_open:
                    deleted_count = close_individual_monthly_billing(
                        courier_id=courier_id,
                        courier_name=str(row["Futár"]),
                        period_start=workflow_month,
                        actor=actor,
                    )
                    st.success(f"Egyedi havi számlázás lezárva. Törölt tesztdokumentum: {deleted_count}.")
                    st.rerun()
                else:
                    deleted_count, uploaded_count, courier_count = open_individual_monthly_billing(
                        row.to_dict() if hasattr(row, "to_dict") else dict(row),
                        period_start,
                        period_end,
                        active_calculation_mode,
                        st.session_state.get("new_warehouse", "Összes"),
                        session_id,
                        actor,
                    )
                    if courier_count:
                        st.success(
                            "Egyedi havi számlázás megnyitva: "
                            f"{uploaded_count} dokumentum feltöltve"
                            + (f", {deleted_count} korábbi tesztdokumentum cserélve." if deleted_count else ".")
                        )
                        st.rerun()
                    else:
                        st.error("Az egyedi havi nyitás nem sikerült. Ellenőrizd a kiválasztott API/Excel sessiont.")
            except Exception as exc:
                st.error(f"Az egyedi havi számlázás módosítása sikertelen: {exc}")
        with st.expander("Folyamat visszaleptetese", expanded=False):
            backstep_options = list(WORKFLOW_BACKSTEP_TARGETS.keys())
            backstep_target = st.selectbox(
                "Melyik lepesre keruljon vissza?",
                backstep_options,
                format_func=lambda key: WORKFLOW_BACKSTEP_TARGETS[key]["label"],
                index=backstep_options.index("tig"),
                key=f"workflow_backstep_target_{courier_id}_{workflow_month:%Y%m}",
            )
            backstep_note = st.text_input(
                "Megjegyzes",
                value=f"Admin visszaleptetes: {WORKFLOW_BACKSTEP_TARGETS[backstep_target]['label']}.",
                key=f"workflow_backstep_note_{courier_id}_{workflow_month:%Y%m}",
            )
            if st.button(
                "Visszaleptetes mentese",
                type="primary",
                use_container_width=True,
                disabled=closure_done,
                key=f"workflow_backstep_save_{courier_id}_{workflow_month:%Y%m}",
            ):
                try:
                    saved_count = backstep_peopleforce_workflow(
                        courier_id=courier_id,
                        courier_name=courier_name,
                        document_month=workflow_month,
                        target_action=backstep_target,
                        updated_by=actor,
                        note=backstep_note,
                    )
                    st.success(f"Folyamat visszaleptetve. Modositott statuszok: {saved_count}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"A folyamat visszaleptetese sikertelen: {exc}")
        status_rows = []
        for action_key, action_label in workflow_action_labels.items():
            saved_status = status_by_action.get(action_key, {})
            status_rows.append({
                "Kulcs": action_key,
                "Lépés": action_label,
                "Kész": str(saved_status.get("status") or "").casefold() == "done",
                "Megjegyzés": str(saved_status.get("status_note") or ""),
                "Frissítette": str(saved_status.get("updated_by") or ""),
            })
        workflow_editor = st.data_editor(
            pd.DataFrame(status_rows),
            use_container_width=True,
            hide_index=True,
            disabled=["Kulcs", "Lépés", "Frissítette"],
            key=f"workflow_status_editor_{courier_id}_{workflow_month:%Y%m}",
            column_config={
                "Kész": st.column_config.CheckboxColumn("Kész"),
                "Megjegyzés": st.column_config.TextColumn("Megjegyzés"),
            },
        )
        if st.button("Folyamat státuszok mentése", type="primary", use_container_width=True, key=f"workflow_status_save_{courier_id}"):
            try:
                saved_count = 0
                for status_row in workflow_editor.to_dict("records"):
                    action_key = str(status_row.get("Kulcs") or "")
                    if not action_key:
                        continue
                    is_done = bool(status_row.get("Kész"))
                    upsert_peopleforce_card_status(
                        courier_id=courier_id,
                        courier_name=str(row["Futár"]),
                        action_key=action_key,
                        document_month=workflow_month,
                        status="done" if is_done else "open",
                        status_note=str(status_row.get("Megjegyzés") or ""),
                        updated_by=actor,
                    )
                    if action_key == "settlement" and not is_done:
                        delete_generated_monthly_billing_documents(courier_id, workflow_month, {"tig"})
                    saved_count += 1
                st.success(f"{saved_count} folyamat státusz mentve. A mobilos felület is ezt olvassa.")
                st.rerun()
            except Exception as exc:
                st.error(f"A folyamat státuszok mentése sikertelen: {exc}")
        st.divider()
        try:
            documents = read_peopleforce_documents_for_courier(courier_id)
        except Exception as exc:
            st.error(f"A régi dokumentumtár nem tölthető be: {exc}")
            documents = pd.DataFrame()

        if documents.empty:
            st.info("Ehhez a futárhoz még nincs feltöltött dokumentum a régi dokumentumtárban.")
        else:
            document_view = documents.copy()
            document_view["Típus"] = document_view.get("document_type", pd.Series("", index=document_view.index)).map(
                lambda value: type_labels.get(str(value or "").strip().lower(), str(value or ""))
            )
            document_view["Elszámolási időszak"] = pd.to_datetime(
                document_view.get("document_month"), errors="coerce"
            ).dt.strftime("%Y-%m").fillna(document_view.get("document_month", ""))
            document_view["Fájl"] = document_view.get("file_name", pd.Series("", index=document_view.index)).fillna("")
            document_view["Megnevezés"] = document_view.get("title", pd.Series("", index=document_view.index)).fillna("")
            document_view["Feltöltve"] = pd.to_datetime(
                document_view.get("uploaded_at"), errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M").fillna(document_view.get("uploaded_at", ""))
            document_view["Feltöltötte"] = document_view.get("uploaded_by", pd.Series("", index=document_view.index)).fillna("")
            document_view["Megjegyzés"] = document_view.get("note", pd.Series("", index=document_view.index)).fillna("")
            st.dataframe(
                document_view[[
                    "Elszámolási időszak", "Típus", "Megnevezés", "Fájl",
                    "Feltöltve", "Feltöltötte", "Megjegyzés",
                ]],
                use_container_width=True,
                hide_index=True,
            )

            rows_by_id = {str(item.get("id")): item for item in documents.to_dict("records") if item.get("id")}
            selected_document_id = st.selectbox(
                "Letöltendő dokumentum",
                list(rows_by_id),
                format_func=lambda value: (
                    f"{pd.to_datetime(rows_by_id[value].get('document_month'), errors='coerce').strftime('%Y-%m')} · "
                    f"{type_labels.get(str(rows_by_id[value].get('document_type') or '').lower(), rows_by_id[value].get('document_type') or '')} · "
                    f"{rows_by_id[value].get('file_name') or rows_by_id[value].get('title') or 'dokumentum'}"
                ),
                key=f"new_doc_select_{courier_id}",
            )
            if selected_document_id:
                try:
                    content_row = read_peopleforce_document_content(selected_document_id)
                    file_bytes = decode_document_content(content_row.get("file_content_base64"))
                    st.download_button(
                        "Dokumentum letöltése",
                        data=file_bytes,
                        file_name=str(content_row.get("file_name") or rows_by_id[selected_document_id].get("file_name") or "dokumentum"),
                        mime=str(content_row.get("mime_type") or rows_by_id[selected_document_id].get("mime_type") or "application/octet-stream"),
                        use_container_width=True,
                        key=f"new_doc_download_{selected_document_id}",
                    )
                except Exception as exc:
                    st.warning(f"A dokumentum tartalma nem tölthető le: {exc}")

        st.markdown("##### Új dokumentum feltöltése")
        upload_columns = st.columns([0.22, 0.22, 0.28, 0.28])
        doc_type_label = upload_columns[0].selectbox(
            "Típus",
            ["Elszámolás", "TIG", "Számla", "Szerződés"],
            key=f"new_doc_type_{courier_id}",
        )
        doc_period = upload_columns[1].date_input(
            "Elszámolási időszak",
            value=period_start.replace(day=1),
            key=f"new_doc_period_{courier_id}",
        )
        doc_title = upload_columns[2].text_input(
            "Megnevezés",
            value=f"{doc_type_label} - {doc_period:%Y-%m}",
            key=f"new_doc_title_{courier_id}",
        )
        uploaded_file = upload_columns[3].file_uploader(
            "Fájl",
            type=["pdf", "png", "jpg", "jpeg"],
            key=f"new_doc_upload_{courier_id}",
        )
        doc_note = st.text_input("Megjegyzés", key=f"new_doc_note_{courier_id}")
        reverse_type_labels = {"Elszámolás": "settlement", "TIG": "tig", "Számla": "invoice", "Szerződés": "contract"}
        selected_upload_type = reverse_type_labels.get(doc_type_label, "settlement")
        upload_month_closed = (
            closure_done
            and doc_period.replace(day=1) == period_start.replace(day=1)
            and selected_upload_type in {"settlement", "tig", "invoice"}
        )
        if upload_month_closed:
            st.warning("Ez a havi folyamat már le van zárva, új elszámolás/TIG/számla nem tölthető fel rá.")
        if st.button("Dokumentum feltöltése", type="primary", use_container_width=True, disabled=uploaded_file is None or upload_month_closed, key=f"new_doc_save_{courier_id}"):
            try:
                upload_peopleforce_document(
                    courier_id=courier_id,
                    courier_name=str(row["Futár"]),
                    document_type=selected_upload_type,
                    document_month=doc_period.replace(day=1),
                    title=doc_title,
                    note=doc_note,
                    uploaded_file=uploaded_file,
                    uploaded_by=str(st.session_state.get("user", {}).get("username") or "unknown"),
                )
                st.success("Dokumentum feltöltve a régi dokumentumtárba, az új rendszerben is látszik.")
                st.rerun()
            except Exception as exc:
                st.error(f"A dokumentum feltöltése sikertelen: {exc}")

    if selected_menu == "Egyedi dokumentum":
        st.markdown("#### Egyedi TIG / részletező összeállítása")
        st.caption("Nulláról készíthető PDF a futárnak, majd egy kattintással feltölthető a profiljába.")
        custom_left, custom_right = st.columns([0.45, 0.55], gap="medium")
        with custom_left:
            custom_doc_label = st.selectbox(
                "Dokumentum típusa",
                ["TIG", "Részletező / elszámolás"],
                key=f"custom_doc_type_{courier_id}",
            )
            custom_period = st.date_input(
                "Elszámolási időszak",
                value=period_start.replace(day=1),
                key=f"custom_doc_period_{courier_id}",
            )
            custom_is_other_process = st.checkbox(
                "Egyéb folyamat indítása",
                value=False,
                key=f"custom_doc_other_process_{courier_id}",
                help="Hónap közepi vagy egyedi elszámolási/TIG folyamat. A PWA-n külön választható lesz.",
            )
            process_default = f"eloleg-{custom_period:%Y-%m-%d}" if custom_is_other_process else ""
            custom_process_label = st.text_input(
                "Folyamat azonosító",
                value=process_default,
                disabled=not custom_is_other_process,
                key=f"custom_doc_process_label_{courier_id}",
            )
            custom_title_default = (
                f"TIG - {row['Futár']} - {custom_period:%Y-%m}"
                if custom_doc_label == "TIG"
                else f"Elszámolási részletező - {row['Futár']} - {custom_period:%Y-%m}"
            )
            custom_title = st.text_input(
                "Cím",
                value=custom_title_default,
                key=f"custom_doc_title_{courier_id}",
            )
            custom_payable = st.number_input(
                "Fizetendő összeg (Ft)",
                value=float(payable_total or 0),
                step=1000.0,
                key=f"custom_doc_payable_{courier_id}",
            )
            custom_note = st.text_area(
                "Megjegyzés / tartalom",
                value=(
                    f"Courier ID: {courier_id}\n"
                    f"Futár: {row['Futár']}\n"
                    f"Időszak: {custom_period:%Y-%m}\n"
                    f"Fizetendő: {format_huf(custom_payable)}"
                ),
                key=f"custom_doc_note_{courier_id}",
            )
            default_items = pd.DataFrame([
                {"Kulcs": "Courier ID", "Érték": courier_id, "Törlés": False},
                {"Kulcs": "Futár", "Érték": str(row["Futár"]), "Törlés": False},
                {"Kulcs": "Időszak", "Érték": f"{custom_period:%Y-%m}", "Törlés": False},
                {"Kulcs": "Fizetendő", "Érték": format_huf(custom_payable), "Törlés": False},
            ])
            custom_items = st.data_editor(
                default_items,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key=f"custom_doc_items_{courier_id}",
                column_config={
                    "Kulcs": st.column_config.TextColumn("Kulcs"),
                    "Érték": st.column_config.TextColumn("Érték"),
                    "Törlés": st.column_config.CheckboxColumn("Törlés"),
                },
            )

        custom_type = "tig" if custom_doc_label == "TIG" else "settlement"
        custom_process_id = ""
        if custom_is_other_process:
            custom_process_id = unicodedata.normalize("NFKD", str(custom_process_label or "")).encode("ascii", "ignore").decode("ascii")
            custom_process_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", custom_process_id).strip("-").lower()[:80]
            if not custom_process_id:
                custom_process_id = f"egyeb-{custom_period:%Y%m%d}"
        custom_month_closed = closure_done and custom_period.replace(day=1) == period_start.replace(day=1)
        if custom_month_closed:
            st.warning("Ez a havi folyamat már le van zárva, új egyedi TIG/elszámolási folyamat nem indítható rá.")
        reference_state_key = f"custom_doc_reference_{courier_id}_{custom_type}_{custom_period:%Y%m}"
        if reference_state_key not in st.session_state:
            st.session_state[reference_state_key] = make_document_reference(courier_id, custom_type, custom_period)
        custom_reference = st.session_state[reference_state_key]
        custom_file_name = (
            f"jitt_{custom_type}_{courier_id}_{slugify_filename(row['Futár'])}_"
            f"{custom_period:%Y-%m}_{custom_reference}.pdf"
        )
        custom_subtitle = (
            f"Courier ID: {courier_id} | Dokumentum ID: {custom_reference} | "
            f"Időszak: {custom_period:%Y-%m} | Fizetendő: {format_huf(custom_payable)}"
        )
        custom_item_rows = []
        if isinstance(custom_items, pd.DataFrame):
            for item in custom_items.to_dict("records"):
                if bool(item.get("Törlés")):
                    continue
                key = str(item.get("Kulcs") or "").strip()
                value = str(item.get("Érték") or "").strip()
                if key or value:
                    custom_item_rows.append((key or "-", value))
        custom_item_rows = [
            ("Dokumentum ID", custom_reference),
            *custom_item_rows,
        ]
        custom_note_with_items = "\n".join(
            [
                f"Dokumentum azonosító: {custom_reference}",
                f"Folyamat azonosító: {custom_process_id}" if custom_process_id else "",
                custom_note.strip(),
                "Tételek:",
            ]
            + [f"{key}: {value}" for key, value in custom_item_rows if key != "Dokumentum ID"]
        ).strip()
        custom_pdf_bytes = build_demo_preview_pdf(custom_title, custom_subtitle, custom_item_rows)
        with custom_right:
            st.markdown("##### Dokumentum adatai")
            st.code(
                f"Dokumentum ID: {custom_reference}\n"
                f"Courier ID: {courier_id}\n"
                f"Fájl: {custom_file_name}",
                language="text",
            )
            st.download_button(
                "Egyedi PDF letöltése",
                data=custom_pdf_bytes,
                file_name=custom_file_name,
                mime="application/pdf",
                use_container_width=True,
                key=f"custom_doc_download_{courier_id}",
            )
            if st.button("Egyedi dokumentum feltöltése profilba", type="primary", use_container_width=True, disabled=custom_month_closed, key=f"custom_doc_upload_{courier_id}"):
                try:
                    upload_peopleforce_document_bytes(
                        courier_id=courier_id,
                        courier_name=str(row["Futár"]),
                        document_type=custom_type,
                        document_month=custom_period.replace(day=1),
                        title=custom_title,
                        note=custom_note_with_items,
                        file_name=custom_file_name,
                        mime_type="application/pdf",
                        file_bytes=custom_pdf_bytes,
                        uploaded_by=str(st.session_state.get("user", {}).get("username") or "unknown"),
                    )
                    if custom_process_id:
                        custom_action_key = f"process:{custom_process_id}:{custom_type}"
                        upsert_peopleforce_card_status(
                            courier_id=courier_id,
                            courier_name=str(row["Futár"]),
                            action_key=custom_action_key,
                            document_month=custom_period.replace(day=1),
                            status="open",
                            status_note=f"Egyéb folyamat indítva: {custom_process_id}",
                            updated_by=str(st.session_state.get("user", {}).get("username") or "unknown"),
                        )
                    st.success("Egyedi dokumentum feltöltve a futár profiljába.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Az egyedi dokumentum feltöltése sikertelen: {exc}")

    if selected_menu == "Reklamációk":
        st.markdown("#### Reklamációk")
        complaint_type_labels = {
            "settlement": "Elszámolás",
            "tig": "TIG",
            "invoice": "Számla",
            "invoice_check": "Számlaellenőrzés",
            "invoice_submit": "Számlafeltöltés",
            "other": "Egyéb",
        }
        reverse_complaint_type_labels = {
            label: key for key, label in complaint_type_labels.items()
        }
        complaint_status_labels = {
            "new": "Új",
            "open": "Nyitott",
            "in_progress": "Folyamatban",
            "resolved": "Megválaszolva",
            "closed": "Lezárt",
        }
        reverse_complaint_status_labels = {
            label: key for key, label in complaint_status_labels.items()
        }
        def complaint_type_label(value: object) -> str:
            action_key = str(value or "").strip()
            base_key = base_action_key(action_key)
            label = complaint_type_labels.get(base_key, base_key or action_key)
            process_id = process_id_from_action_key(action_key)
            return f"{label} ({process_id})" if process_id else label

        actor = str(st.session_state.get("user", {}).get("username") or "unknown")
        try:
            complaints = read_peopleforce_complaints_for_month(period_start.replace(day=1))
            if not complaints.empty:
                complaints = complaints[
                    complaints.get("courier_id", pd.Series("", index=complaints.index))
                    .astype(str).map(_courier_id_key).eq(_courier_id_key(courier_id))
                ].copy()
        except Exception as exc:
            st.error(f"A reklamációk nem tölthetők be: {exc}")
            complaints = pd.DataFrame()

        complaint_list, complaint_editor = st.columns([1.35, 0.65])

        with complaint_list:
            if complaints.empty:
                st.info("Ehhez a futárhoz nincs reklamáció az aktuális hónapban.")
            else:
                complaint_view = complaints.copy()
                complaint_view["Dátum"] = pd.to_datetime(
                    complaint_view.get("created_at"), errors="coerce"
                ).dt.strftime("%Y-%m-%d %H:%M").fillna(complaint_view.get("created_at", ""))
                complaint_view["Típus"] = complaint_view.get("document_type", pd.Series("", index=complaint_view.index)).map(complaint_type_label)
                complaint_view["Státusz"] = complaint_view.get("status", pd.Series("", index=complaint_view.index)).map(
                    lambda value: complaint_status_labels.get(str(value or "").strip(), str(value or ""))
                )
                complaint_view["Üzenet"] = complaint_view.get("message", pd.Series("", index=complaint_view.index)).fillna("")
                complaint_view["Admin válasz"] = complaint_view.get("admin_response", pd.Series("", index=complaint_view.index)).fillna("")
                complaint_view["Válaszolta"] = complaint_view.get("responded_by", pd.Series("", index=complaint_view.index)).fillna("")
                st.dataframe(
                    complaint_view[["Dátum", "Típus", "Státusz", "Üzenet", "Admin válasz", "Válaszolta"]],
                    use_container_width=True,
                    hide_index=True,
                )

        with complaint_editor:
            st.markdown("##### Új reklamáció")
            new_complaint_type_label = st.selectbox(
                "Típus",
                ["Elszámolás", "TIG", "Számlaellenőrzés", "Számlafeltöltés", "Számla", "Egyéb"],
                key=f"ui_complaint_type_{courier_id}",
            )
            new_complaint_subject = st.text_input("Tárgy", key=f"ui_complaint_subject_{courier_id}")
            new_complaint_text = st.text_area("Leírás", key=f"ui_complaint_text_{courier_id}")
            if st.button("Reklamáció mentése", type="primary", use_container_width=True, key=f"ui_complaint_save_{courier_id}"):
                message_parts = [new_complaint_subject.strip(), new_complaint_text.strip()]
                message = "\n\n".join([part for part in message_parts if part])
                if not message:
                    st.error("A reklamációhoz adj meg tárgyat vagy leírást.")
                else:
                    try:
                        create_peopleforce_complaint(
                            courier_id=courier_id,
                            courier_name=str(row["Futár"]),
                            document_type=reverse_complaint_type_labels.get(new_complaint_type_label, "other"),
                            document_month=period_start.replace(day=1),
                            message=message,
                            created_by=actor,
                        )
                        st.success("Reklamáció mentve. A mobilos felületen is megjelenik.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A reklamáció mentése sikertelen: {exc}")

            st.markdown("##### Válasz / státusz")
            if complaints.empty:
                st.caption("Nincs kiválasztható reklamáció.")
            else:
                complaint_rows_by_id = {
                    str(item.get("id")): item
                    for item in complaints.to_dict("records")
                    if item.get("id")
                }
                complaint_ids = list(complaint_rows_by_id)
                selected_index = 0
                for index, complaint_id in enumerate(complaint_ids):
                    status = str(complaint_rows_by_id[complaint_id].get("status") or "").strip().lower()
                    if status not in {"resolved", "closed"}:
                        selected_index = index
                        break
                selected_complaint_id = st.selectbox(
                    "Reklamáció",
                    complaint_ids,
                    format_func=lambda value: (
                        f"{complaint_type_label(complaint_rows_by_id[value].get('document_type'))} · "
                        f"{str(complaint_rows_by_id[value].get('message') or '')[:48]}"
                    ),
                    index=selected_index,
                    key=f"ui_complaint_select_{courier_id}",
                )
                selected_complaint = complaint_rows_by_id.get(selected_complaint_id, {})
                current_status_label = complaint_status_labels.get(
                    str(selected_complaint.get("status") or "new"),
                    str(selected_complaint.get("status") or "Új"),
                )
                response_status_label = st.selectbox(
                    "Státusz",
                    list(complaint_status_labels.values()),
                    index=list(complaint_status_labels.values()).index(current_status_label)
                    if current_status_label in complaint_status_labels.values() else 0,
                    key=f"ui_complaint_status_{courier_id}_{selected_complaint_id}",
                )
                response_message = st.text_area(
                    "Admin válasz",
                    value=str(selected_complaint.get("admin_response") or ""),
                    key=f"ui_complaint_response_{courier_id}_{selected_complaint_id}",
                )
                response_actions = st.columns(3)
                if response_actions[2].button("Lezaras", type="primary", use_container_width=True, key=f"ui_complaint_close_top_{courier_id}_{selected_complaint_id}"):
                    try:
                        update_peopleforce_complaints_status_for_process(
                            courier_id,
                            period_start.replace(day=1),
                            str(selected_complaint.get("document_type") or ""),
                            "closed",
                        )
                        st.success("Reklamacio lezarva.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A reklamacio lezarasa sikertelen: {exc}")
                if st.button("Reklamáció elrejtése", use_container_width=True, key=f"ui_complaint_delete_{courier_id}_{selected_complaint_id}"):
                    try:
                        delete_peopleforce_complaint(selected_complaint_id)
                        st.success("Reklamáció elrejtve. DB-ből visszanyitható.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A reklamáció elrejtése sikertelen: {exc}")
                if response_actions[0].button("Válasz küldése", type="primary", use_container_width=True, key=f"ui_complaint_response_save_{courier_id}"):
                    if not response_message.strip():
                        st.error("A válasz szövege nem lehet üres.")
                    else:
                        try:
                            respond_to_peopleforce_complaint(
                                selected_complaint_id,
                                response_message,
                                actor,
                                courier_id=courier_id,
                                courier_name=str(row["Futár"]),
                                document_type=str(selected_complaint.get("document_type") or "other"),
                                document_month=period_start.replace(day=1),
                            )
                            st.success("Válasz elküldve. A futár mobilon is látni fogja.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"A válasz mentése sikertelen: {exc}")
                if response_actions[1].button("Státusz mentése", use_container_width=True, key=f"ui_complaint_status_save_{courier_id}"):
                    try:
                        next_status = reverse_complaint_status_labels.get(response_status_label, "open")
                        if next_status == "closed":
                            update_peopleforce_complaints_status_for_process(
                                courier_id,
                                period_start.replace(day=1),
                                str(selected_complaint.get("document_type") or ""),
                                "closed",
                            )
                        else:
                            update_peopleforce_complaint_status(
                                selected_complaint_id,
                                next_status,
                            )
                        st.success("Reklamáció státusz frissítve.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A státusz mentése sikertelen: {exc}")
                if st.button("Reklamáció lezárása", type="primary", use_container_width=True, key=f"ui_complaint_close_{courier_id}_{selected_complaint_id}"):
                    try:
                        update_peopleforce_complaints_status_for_process(
                            courier_id,
                            period_start.replace(day=1),
                            str(selected_complaint.get("document_type") or ""),
                            "closed",
                        )
                        st.success("Reklamáció lezárva.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A reklamáció lezárása sikertelen: {exc}")

    if selected_menu == "Profil":
        profile = load_courier_profile(courier_id)
        reserve_status = load_target_reserve_status(courier_id, str(row["Futár"]))
        efo_assignment = load_active_efo_assignment(courier_id, date.today())
        loyalty_required_months = load_loyalty_month_requirement_for_date(period_start)
        resolved_work_start, work_start_source, _loyalty_profile = resolve_loyalty_work_start(profile, courier_name)
        work_months = completed_months_between(resolved_work_start, period_start)
        employment_type = str(profile.get("employment_type") or "egyeni_vallalkozo").strip()
        if employment_type not in EMPLOYMENT_TYPE_LABELS:
            employment_type = "egyeni_vallalkozo"
        if work_months < 0:
            loyalty_status = "Hiányzik a munkakezdés"
        elif work_months >= loyalty_required_months:
            loyalty_status = "Beleszámít"
        else:
            loyalty_status = f"Még nem jogosult ({work_months}/{loyalty_required_months} hónap)"
        st.markdown("#### Profil")
        st.caption("Forrás: public.courier_master. A biztosítási tagság forrása: public.courier_target_reserve.")
        edit_key = f"profile_edit_mode_{courier_id}"
        is_editing = bool(st.session_state.get(edit_key, False))

        def enable_profile_edit() -> None:
            st.session_state[edit_key] = True
            keep_courier_menu("Profil")

        def cancel_profile_edit() -> None:
            st.session_state[edit_key] = False
            keep_courier_menu("Profil")

        profile1, profile2 = st.columns(2)

        with profile1:
            courier_name = st.text_input("Név", value=str(profile.get("courier_name") or row["Futár"]), disabled=not is_editing, key=f"ui_profile_name_{courier_id}")
            st.text_input("Courier ID", value=courier_id, disabled=True, key=f"ui_profile_id_{courier_id}")
            phone_number = st.text_input("Telefonszám", value=str(profile.get("phone_number") or ""), disabled=not is_editing, key=f"ui_profile_phone_{courier_id}")
            email = st.text_input("E-mail", value=str(profile.get("email") or ""), disabled=not is_editing, key=f"ui_profile_email_{courier_id}")
            warehouse_name = st.text_input("Raktár", value=str(profile.get("warehouse_name") or row["Raktár"] or ""), disabled=not is_editing, key=f"ui_profile_warehouse_{courier_id}")
            billing_email = st.text_input("Számlázási e-mail", value=str(profile.get("billing_email") or ""), disabled=not is_editing, key=f"ui_profile_billing_email_{courier_id}")
            work_start_date = st.date_input(
                "Munkakezdés dátuma",
            value=resolved_work_start or date.today(),
                disabled=not is_editing,
                key=f"ui_profile_work_start_{courier_id}",
            )
            st.caption(f"ForrĂˇs: {work_start_source}")
            employment_options = list(EMPLOYMENT_TYPE_LABELS)
            employment_type = st.selectbox(
                "Jogviszony",
                employment_options,
                index=employment_options.index(employment_type),
                format_func=lambda value: EMPLOYMENT_TYPE_LABELS.get(value, value),
                disabled=not is_editing,
                key=f"ui_profile_employment_type_{courier_id}",
            )
            employment_note = st.text_input("Jogviszony megjegyzés", value=str(profile.get("employment_note") or ""), disabled=not is_editing, key=f"ui_profile_employment_note_{courier_id}")
            st.text_input("Lojalitási bónusz", value=loyalty_status, disabled=True, key=f"ui_profile_loyalty_status_{courier_id}")

        with profile2:
            st.text_input("Számítás módja", value=str(row["Számítás módja"]), disabled=True, key=f"ui_profile_calc_{courier_id}")
            company_name = st.text_input("Vállalkozás neve", value=str(profile.get("company_name") or ""), disabled=not is_editing, key=f"ui_profile_company_{courier_id}")
            company_address = st.text_input("Vállalkozás címe", value=str(profile.get("company_address") or ""), disabled=not is_editing, key=f"ui_profile_company_address_{courier_id}")
            tax_number = st.text_input("Adószám", value=str(profile.get("tax_number") or ""), disabled=not is_editing, key=f"ui_profile_tax_{courier_id}")
            bank_account_number = st.text_input("Bankszámlaszám", value=str(profile.get("bank_account_number") or ""), disabled=not is_editing, key=f"ui_profile_bank_{courier_id}")
            vat_status = st.text_input("ÁFA státusz", value=str(profile.get("vat_status") or ""), disabled=not is_editing, key=f"ui_profile_vat_status_{courier_id}")
            efo_status = "Bejelentve" if efo_assignment else "Nincs aktuális EFO bejelentés"
            if efo_assignment:
                efo_end = str(efo_assignment.get("valid_to") or "folyamatos")
                efo_status = f"Bejelentve: {efo_assignment.get('valid_from')} - {efo_end}, napi levonás {format_huf(parse_huf_value(efo_assignment.get('daily_deduction_huf')))}"
            st.text_input("EFO státusz", value=efo_status, disabled=True, key=f"ui_profile_efo_status_{courier_id}")
            st.text_input("Biztosítás", value="Van" if reserve_status["insurance_active"] else "Nincs", disabled=True, key=f"ui_profile_insurance_{courier_id}")
            st.text_input("Profil státusz", value="Aktív" if bool(profile.get("active", True)) else "Inaktív", disabled=True, key=f"ui_profile_status_{courier_id}")

        profile_actions = st.columns(3)
        if not is_editing:
            profile_actions[0].button(
                "Profil szerkesztése",
                type="primary",
                use_container_width=True,
                key=f"ui_profile_edit_{courier_id}",
                on_click=enable_profile_edit,
            )
        if is_editing and profile_actions[0].button("Profil mentése", type="primary", use_container_width=True, key=f"ui_profile_save_{courier_id}"):
            new_fields = {
                "courier_name": courier_name,
                "phone_number": phone_number,
                "email": email,
                "warehouse_name": warehouse_name,
                "billing_email": billing_email,
                "work_start_date": work_start_date.isoformat() if work_start_date else "",
                "employment_type": employment_type,
                "employment_note": employment_note,
                "company_name": company_name,
                "company_address": company_address,
                "tax_number": tax_number,
                "bank_account_number": bank_account_number,
                "vat_status": vat_status,
            }
            changes = {field: {"old": str(profile.get(field) or ""), "new": str(value or "")} for field, value in new_fields.items() if str(profile.get(field) or "") != str(value or "")}
            try:
                if changes:
                    update_courier_master_profile(courier_id, new_fields)
                    log_profile_change(courier_id, changes)
                st.session_state[edit_key] = False
                keep_courier_menu("Profil")
                load_courier_profile.clear()
                load_active_efo_assignment.clear()
                load_loyalty_profile_lookup.clear()
                load_loyalty_month_requirement_for_date.clear()
                load_courier_master.clear()
                st.success("A profil mentve, a változás naplózva.")
                st.rerun()
            except Exception as exc:
                st.error(f"A profil nem menthető: {exc}")
        if is_editing:
            profile_actions[1].button(
                "Mégse",
                use_container_width=True,
                key=f"ui_profile_cancel_{courier_id}",
                on_click=cancel_profile_edit,
            )
        if profile_actions[2].button("↻ Profiladatok újratöltése", use_container_width=True, key=f"ui_profile_refresh_{courier_id}"):
            keep_courier_menu("Profil")
            load_courier_profile.clear()
            load_active_efo_assignment.clear()
            load_loyalty_month_requirement_for_date.clear()
            load_target_reserve_status.clear()
            st.rerun()
        profile_log = load_profile_change_log(courier_id)
        if not profile_log.empty:
            with st.expander("Profil módosítási napló", expanded=False):
                st.dataframe(profile_log.rename(columns={"changed_fields": "Változások", "changed_by": "Módosította", "created_at": "Időpont"}), use_container_width=True, hide_index=True)


@st.dialog("Tömeges elszámolás", width="large")
def show_bulk_settlement_dialog() -> None:
    df = st.session_state.get("current_filtered_data", load_courier_master())

    st.subheader("Tömeges elszámolás")
    st.caption("Az aktuális szűrés alapján kiválasztott futárok.")

    if df.empty:
        st.info("Nincs feldolgozható futár.")
        return

    preview_df = df[
        ["Courier ID", "Futár", "Branch", "Számítás módja", "Kifizetendő", "Státusz"]
    ].copy()
    preview_df["Kifizetendő"] = preview_df["Kifizetendő"].map(format_huf)

    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    precheck = st.checkbox(
        "Előellenőrzés megtörtént",
        key="bulk_settlement_precheck",
        help="A tömeges gyártás csak ennek bepipálása után indítható.",
    )

    generate_key = "bulk_settlement_preview_ready"

    if st.button(
        "Tömeges elszámolás gyártása",
        type="primary",
        use_container_width=True,
        disabled=not precheck,
        key="bulk_settlement_generate",
    ):
        st.session_state[generate_key] = True

    if st.session_state.get(generate_key):
        st.success("A tömeges gyártás designer állapota elkészült.")
        st.markdown("#### 1 darab minta PDF")

        pdf_bytes = build_demo_preview_pdf(
            "Tömeges elszámolás – minta",
            f"Szűrésben szereplő futárok: {len(df)}",
        )

        st.download_button(
            "Minta elszámolás PDF megnyitása / letöltése",
            data=pdf_bytes,
            file_name="tomeges_elszamolas_minta.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="bulk_settlement_preview_pdf",
        )

        action1, action2 = st.columns(2)

        if action1.button(
            "Elfogadás",
            type="primary",
            use_container_width=True,
            key="bulk_settlement_accept",
            help="Csak designer gomb.",
        ):
            st.session_state["bulk_settlement_accepted"] = True
            st.success("A minta elszámolás elfogadott állapotot kapna.")

        if action2.button(
            "Feltöltés profilba",
            use_container_width=True,
            disabled=not st.session_state.get("bulk_settlement_accepted", False),
            key="bulk_settlement_upload",
            help="Csak designer gomb.",
        ):
            st.success("A tömeges elszámolások profilba feltöltése indulna.")


@st.dialog("Tömeges TIG", width="large")
def show_bulk_tig_dialog() -> None:
    df = st.session_state.get("current_filtered_data", load_courier_master())

    st.subheader("Tömeges TIG")
    st.caption("Az aktuális szűrés alapján kiválasztott futárok.")

    if df.empty:
        st.info("Nincs feldolgozható futár.")
        return

    preview_df = df[
        ["Courier ID", "Futár", "Branch", "Számítás módja", "Kifizetendő"]
    ].copy()
    preview_df["Kifizetendő"] = preview_df["Kifizetendő"].map(format_huf)

    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    precheck = st.checkbox(
        "Előellenőrzés megtörtént",
        key="bulk_tig_precheck",
        help="A tömeges gyártás csak ennek bepipálása után indítható.",
    )

    generate_key = "bulk_tig_preview_ready"

    if st.button(
        "Tömeges TIG gyártása",
        type="primary",
        use_container_width=True,
        disabled=not precheck,
        key="bulk_tig_generate",
    ):
        st.session_state[generate_key] = True

    if st.session_state.get(generate_key):
        st.success("A tömeges TIG gyártás designer állapota elkészült.")
        st.markdown("#### 1 darab minta PDF")

        pdf_bytes = build_demo_preview_pdf(
            "Tömeges TIG – minta",
            f"Szűrésben szereplő futárok: {len(df)}",
        )

        st.download_button(
            "Minta TIG PDF megnyitása / letöltése",
            data=pdf_bytes,
            file_name="tomeges_tig_minta.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="bulk_tig_preview_pdf",
        )

        action1, action2 = st.columns(2)

        if action1.button(
            "Elfogadás",
            type="primary",
            use_container_width=True,
            key="bulk_tig_accept",
            help="Csak designer gomb.",
        ):
            st.session_state["bulk_tig_accepted"] = True
            st.success("A minta TIG elfogadott állapotot kapna.")

        if action2.button(
            "Feltöltés profilba",
            use_container_width=True,
            disabled=not st.session_state.get("bulk_tig_accepted", False),
            key="bulk_tig_upload",
            help="Csak designer gomb.",
        ):
            st.success("A tömeges TIG-ek profilba feltöltése indulna.")



@st.dialog("Paraméterértékek", width="large")
def show_parameter_catalog_dialog() -> None:
    render_parameter_catalog(get_db())

@st.dialog("Bejelentések", width="large")
def show_reports_dialog() -> None:
    df = st.session_state.get("current_filtered_data", load_courier_master())
    ids = set(df["Courier ID"].astype(str))

    complaints = get_demo_complaints()
    complaints = complaints[
        complaints["Courier ID"].astype(str).isin(ids)
    ].copy()

    if complaints.empty:
        st.success("Nincs bejelentés a szűrésben.")
        return

    merged = complaints.merge(
        df[["Courier ID", "Futár", "Branch"]],
        on="Courier ID",
        how="left",
    ).reset_index(drop=True)

    st.subheader("Bejelentések")
    st.caption("Kattints a futár nevére a részletes bejelentés megnyitásához.")

    header = st.columns([1.35, 0.8, 0.8, 0.8, 1.8])
    for col, label in zip(
        header,
        ["Futár", "Típus", "Státusz", "Dátum", "Üzenet"],
    ):
        col.markdown(f"**{label}**")

    for index, report in merged.iterrows():
        cols = st.columns(
            [1.35, 0.8, 0.8, 0.8, 1.8],
            vertical_alignment="center",
        )

        if cols[0].button(
            f"{report['Futár']} · {report['Courier ID']}",
            use_container_width=True,
            key=f"open_report_{report['Courier ID']}_{index}",
        ):
            st.session_state["selected_report"] = report.to_dict()
            show_report_detail_dialog()

        cols[1].caption(str(report["Típus"]))
        cols[2].caption(str(report["Státusz"]))
        cols[3].caption(str(report["Dátum"]))
        cols[4].caption(str(report["Üzenet"]))


@st.dialog("Bejelentés részletei", width="large")
def show_report_detail_dialog() -> None:
    report = st.session_state.get("selected_report")

    if not isinstance(report, dict):
        st.warning("A kiválasztott bejelentés nem található.")
        return

    courier_name = str(report.get("Futár") or "Ismeretlen futár")
    courier_id = str(report.get("Courier ID") or "")
    report_type = str(report.get("Típus") or "Egyéb")
    report_status = str(report.get("Státusz") or "Nyitott")
    report_date = str(report.get("Dátum") or "-")
    report_message = str(report.get("Üzenet") or "Nincs megadott üzenet.")

    st.subheader(f"{courier_name} · {courier_id}")
    st.caption(f"{report.get('Branch', '-')} · {report_type}")

    detail1, detail2, detail3 = st.columns(3)
    detail1.metric("Típus", report_type)
    detail2.metric("Státusz", report_status)
    detail3.metric("Dátum", report_date)

    st.markdown("#### Bejelentés szövege")
    st.markdown(
        f"""
        <div class="detail-card">
        <div style="font-size:15px;line-height:1.6;color:#274630;">
            {html.escape(report_message)}
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Válasz a futárnak")
    response_text = st.text_area(
        "Szöveges válasz",
        placeholder="Írd le az admin válaszát, a döntést vagy a szükséges teendőt.",
        height=150,
        key=f"ui_report_response_{courier_id}_{report_date}_{report_type}",
    )

    action1, action2 = st.columns(2)

    if action1.button(
        "Elfogadás",
        type="primary",
        use_container_width=True,
        key=f"ui_report_accept_{courier_id}_{report_date}_{report_type}",
        help="Csak designer gomb, még nincs mögötte mentési logika.",
    ):
        if not response_text.strip():
            st.info("A designer nézetben a válasz mező üresen is hagyható.")
        st.success("A bejelentés elfogadott állapotot kapna.")

    if action2.button(
        "Lezárás",
        use_container_width=True,
        key=f"ui_report_close_{courier_id}_{report_date}_{report_type}",
        help="Csak designer gomb, még nincs mögötte mentési logika.",
    ):
        if not response_text.strip():
            st.info("A designer nézetben a válasz mező üresen is hagyható.")
        st.success("A bejelentés lezárt állapotot kapna.")


def build_demo_preview_pdf(title: str, subtitle: str, detail_lines: list[tuple[str, str]] | None = None) -> bytes:
    """
    Csak designer előnézeti PDF.
    Nincs mögötte üzleti logika vagy valódi elszámolási számítás.
    """
    from io import BytesIO

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return (
            f"{title}\n\n{subtitle}\n\n"
            + "\n".join(f"{key}: {value}" for key, value in (detail_lines or []))
        ).encode("utf-8")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, height - 70, title)

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, height - 100, subtitle)
    pdf.drawString(50, height - 130, "Egyedi dokumentum")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, height - 180, "Dokumentum adatok")

    pdf.setFont("Helvetica", 10)
    y = height - 210
    for key, value in detail_lines or []:
        pdf.drawString(50, y, f"{key}: {value}")
        y -= 20
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - 60

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_settlement_detail_sample_pdf(
    courier: dict[str, object],
    summary_rows: list[tuple[str, int]],
    rule_rows: list[dict[str, object]],
    source_rows: list[tuple[str, str]],
) -> bytes:
    """Designer minta PDF a reszletes elszamolasi bontashoz."""
    from io import BytesIO

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        lines = [
            "Elszamolasi reszletezo minta",
            "",
            *(f"{key}: {value}" for key, value in courier.items()),
            "",
            "Osszesito",
            *(f"{label}: {format_huf(value)}" for label, value in summary_rows),
            "",
            "Szabaly szerinti bontas",
            *(
                f"{row['tetel']} | {row['szabaly']} | {row['keplet']} | {format_huf(row['osszeg'])}"
                for row in rule_rows
            ),
        ]
        return "\n".join(lines).encode("utf-8")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "SettlementSampleTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#17351F"),
    )
    section = ParagraphStyle(
        "SettlementSampleSection",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#17351F"),
    )
    body = ParagraphStyle(
        "SettlementSampleBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    )

    story = [
        Paragraph("Elszamolasi reszletezo minta", title),
        Spacer(1, 3 * mm),
        Paragraph("Designer elonezet az uj devtest elszamolasi modulhoz.", body),
        Spacer(1, 5 * mm),
    ]

    header_rows = [
        ["Futar", str(courier.get("name", "")), "Courier ID", str(courier.get("courier_id", ""))],
        ["Raktar", str(courier.get("warehouse", "")), "Idoszak", str(courier.get("period", ""))],
        ["Dokumentum ID", str(courier.get("document_id", "")), "Adatforras", str(courier.get("source", ""))],
    ]
    header_table = Table(header_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 58 * mm])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F7F3")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D8CC")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [header_table, Spacer(1, 6 * mm), Paragraph("Havi osszesito", section), Spacer(1, 2 * mm)]

    summary_table = Table(
        [["Tetel", "Osszeg"]] + [[label, format_huf(value)] for label, value in summary_rows],
        colWidths=[118 * mm, 58 * mm],
    )
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17351F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DFF1E4")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CF")),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [summary_table, Spacer(1, 6 * mm), Paragraph("Szabaly szerinti reszletezo", section), Spacer(1, 2 * mm)]

    rule_table_rows = [["Tetel", "Szabaly", "Keplet", "Osszeg"]]
    for row in rule_rows:
        rule_table_rows.append([
            str(row["tetel"]),
            str(row["szabaly"]),
            str(row["keplet"]),
            format_huf(row["osszeg"]),
        ])
    rule_table = Table(rule_table_rows, colWidths=[42 * mm, 48 * mm, 50 * mm, 36 * mm])
    rule_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF8F0")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CF")),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [rule_table, Spacer(1, 6 * mm), Paragraph("Adatforras", section), Spacer(1, 2 * mm)]

    source_table = Table(
        [["Mezo", "Ertek"]] + [[label, value] for label, value in source_rows],
        colWidths=[70 * mm, 106 * mm],
    )
    source_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F8FA")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CF")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [source_table]

    doc.build(story)
    return buffer.getvalue()


def show_settlement_pdf_sample_page() -> None:
    apply_design()
    st.markdown(
        """
        <div class="premium-hero">
        <div class="hero-left">
            <div class="badge">PDF MINTA</div>
            <h1>Elszamolasi reszletezo PDF</h1>
            <p>Designer elonezet: igy latszik majd a futarnak, mibol all ossze a havi fizetendo osszeg.</p>
        </div>
        <div class="month-pill"><div class="label">Modul</div><div class="value">Devtest</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    input_left, input_right = st.columns([1, 1])
    with input_left:
        st.markdown("#### Futar es idoszak")
        courier_name = st.text_input("Futar neve", value="Gurzo Balazs", key="sample_pdf_courier_name")
        courier_id = st.text_input("Courier ID", value="7644", key="sample_pdf_courier_id")
        warehouse = st.selectbox("Raktar", ["BUD1", "BUD2"], index=1, key="sample_pdf_warehouse")
        period = st.selectbox("Elszamolasi honap", month_options(), key="sample_pdf_month")
        source = st.radio("Adatforras", ["API", "Excel"], horizontal=True, key="sample_pdf_source")

    with input_right:
        st.markdown("#### Szabaly parameterek")
        level_code = st.selectbox("Szint", ["LEVEL-1", "LEVEL-2", "LEVEL-3"], key="sample_pdf_level")
        express_days = st.number_input("Expressz napok / korok", min_value=0, value=15, step=1, key="sample_pdf_express_days")
        express_rate = st.number_input("Expressz egységdíj (Ft)", min_value=0, value=3000, step=100, key="sample_pdf_express_rate")
        normal_days = st.number_input("Normal napok / korok", min_value=0, value=10, step=1, key="sample_pdf_normal_days")
        normal_rate = st.number_input("Normal egységdíj (Ft)", min_value=0, value=3000, step=100, key="sample_pdf_normal_rate")

    extra_cols = st.columns(4)
    tip_amount = extra_cols[0].number_input("Borravalo (Ft)", min_value=0, value=102750, step=500, key="sample_pdf_tip")
    delay_bonus = extra_cols[1].number_input("Késedelmi díj / bonusz (Ft)", min_value=0, value=75000, step=500, key="sample_pdf_delay")
    compliance_bonus = extra_cols[2].number_input("Turamegfeleles (Ft)", min_value=0, value=12500, step=500, key="sample_pdf_compliance")
    customer_bonus = extra_cols[3].number_input("Ugyfelertekelesi bonusz (Ft)", min_value=0, value=7500, step=500, key="sample_pdf_rating")

    deduction_cols = st.columns(4)
    monthly_bonus = deduction_cols[0].number_input("Havi bonusz / malusz (Ft)", value=7500, step=500, key="sample_pdf_monthly_bonus")
    atm_impact = deduction_cols[1].number_input("ATM hatas (Ft)", value=-18789, step=500, key="sample_pdf_atm")
    salary_advance = deduction_cols[2].number_input("Fizetes eloleg (Ft)", value=0, step=500, key="sample_pdf_advance")
    reserve = deduction_cols[3].number_input("Celtartalek 10% (Ft)", value=0, step=500, key="sample_pdf_reserve")

    express_total = int(express_days) * int(express_rate)
    normal_total = int(normal_days) * int(normal_rate)
    base_fee = express_total + normal_total
    total_revenue = base_fee + int(tip_amount) + int(delay_bonus) + int(compliance_bonus) + int(customer_bonus) + int(monthly_bonus)
    total_deductions = abs(min(int(atm_impact), 0)) + abs(min(int(salary_advance), 0)) + abs(min(int(reserve), 0))
    payable = total_revenue + int(atm_impact) + int(salary_advance) + int(reserve)

    st.markdown('<div class="section-title">Elonezet</div>', unsafe_allow_html=True)
    metric_cols = st.columns(5)
    metric_cols[0].metric("Alapdij", format_huf(base_fee))
    metric_cols[1].metric("Bonuszok", format_huf(delay_bonus + compliance_bonus + customer_bonus + monthly_bonus))
    metric_cols[2].metric("Borravalo", format_huf(tip_amount))
    metric_cols[3].metric("Levonas / hatas", format_huf(atm_impact + salary_advance + reserve))
    metric_cols[4].metric("Fizetendo", format_huf(payable))

    rule_rows = [
        {
            "tetel": "Expressz alapdij",
            "szabaly": f"{level_code} + Expressz",
            "darab": int(express_days),
            "egysegar": int(express_rate),
            "keplet": f"{int(express_days)} x {format_huf(express_rate)}",
            "osszeg": express_total,
        },
        {
            "tetel": "Normal alapdij",
            "szabaly": f"{level_code} + Normal",
            "darab": int(normal_days),
            "egysegar": int(normal_rate),
            "keplet": f"{int(normal_days)} x {format_huf(normal_rate)}",
            "osszeg": normal_total,
        },
        {
            "tetel": "Kesedelmi dij",
            "szabaly": f"{level_code} + API/Excel delay",
            "darab": 1,
            "egysegar": int(delay_bonus),
            "keplet": f"szabaly szerinti havi osszeg",
            "osszeg": int(delay_bonus),
        },
        {
            "tetel": "Turamegfeleles",
            "szabaly": f"{level_code} + Compliance",
            "darab": 1,
            "egysegar": int(compliance_bonus),
            "keplet": f"szabaly szerinti havi osszeg",
            "osszeg": int(compliance_bonus),
        },
        {
            "tetel": "Ugyfelertekeles",
            "szabaly": "Rating bonusz",
            "darab": 1,
            "egysegar": int(customer_bonus),
            "keplet": "ertekelesi sav alapjan",
            "osszeg": int(customer_bonus),
        },
    ]
    rule_df = pd.DataFrame(rule_rows).rename(columns={
        "tetel": "Tétel",
        "szabaly": "Szabály kulcs",
        "darab": "Darab",
        "egysegar": "Egységár",
        "keplet": "Számítás",
        "osszeg": "Összeg",
    })
    rule_view = rule_df.copy()
    for column in ["Egységár", "Összeg"]:
        rule_view[column] = rule_view[column].map(format_huf)
    st.dataframe(rule_view, use_container_width=True, hide_index=True)

    summary_rows = [
        ("Alapdij", base_fee),
        ("Borravalo", int(tip_amount)),
        ("Kesedelmi dij / bonusz", int(delay_bonus)),
        ("Turamegfeleles", int(compliance_bonus)),
        ("Ugyfelertekelesi bonusz", int(customer_bonus)),
        ("Havi bonusz / malusz", int(monthly_bonus)),
        ("ATM hatas", int(atm_impact)),
        ("Fizetes eloleg", int(salary_advance)),
        ("Celtartalek 10%", int(reserve)),
        ("Fizetendo", payable),
    ]
    source_rows = [
        ("Elsodleges forras", source),
        ("Szabaly kulcs", f"{level_code} + turatipus"),
        ("Raktar", warehouse),
        ("Adatminoseg", "Minta: megbizhato"),
        ("Hianyzo adatok", "0"),
    ]
    document_id = f"{courier_id}-{parse_month_option(period):%Y%m}-DETAIL-SAMPLE"
    courier = {
        "name": courier_name,
        "courier_id": courier_id,
        "warehouse": warehouse,
        "period": period,
        "source": source,
        "document_id": document_id,
    }
    pdf_bytes = build_settlement_detail_sample_pdf(
        courier,
        summary_rows,
        rule_rows,
        source_rows,
    )

    action_cols = st.columns([1, 1])
    action_cols[0].download_button(
        "Reszletezo PDF minta letoltese",
        data=pdf_bytes,
        file_name=f"elszamolasi_reszletezo_minta_{courier_id}_{parse_month_option(period):%Y_%m}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    action_cols[1].code(
        f"Dokumentum ID: {document_id}\nCourier ID: {courier_id}\nSzabaly: {level_code} + turatipus",
        language="text",
    )


def build_excel_export(df: pd.DataFrame) -> bytes:
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Elszámolások")
    return output.getvalue()

def build_monthly_period_document_plan(data: pd.DataFrame, period_start: date, period_end: date) -> list[dict[str, object]]:
    if data.empty:
        return []
    planned: list[dict[str, object]] = []
    for item in data.to_dict("records"):
        courier_id = str(item.get("Courier ID") or "").strip()
        courier_name = str(item.get("Futár") or "").strip()
        if not courier_id or not courier_name:
            continue
        amount_huf = parse_huf_value(item.get("Kifizetendő"))
        reference_base = make_document_reference(courier_id, "monthly", period_start)
        planned.append({
            "courier_id": courier_id,
            "courier_name": courier_name,
            "period_start": period_start,
            "period_end": period_end,
            "settlement_reference": f"{reference_base}-SETTLEMENT",
            "tig_reference": f"{reference_base}-TIG",
            "settlement_file": f"jitt_elszamolas_{courier_id}_{slugify_filename(courier_name)}_{period_start:%Y-%m}.pdf",
            "tig_file": f"jitt_tig_{courier_id}_{slugify_filename(courier_name)}_{period_start:%Y-%m}.pdf",
            "payable_huf": amount_huf,
        })
    return planned


def monthly_period_start_already_clicked(period_start: date) -> bool:
    if st.session_state.get(f"monthly_period_start_clicked_{period_start:%Y%m}"):
        return True
    try:
        rows = (
            get_db().schema("settlement").table("mobile_settlement_period_config")
            .select("period_start")
            .eq("period_start", period_start.replace(day=1).isoformat())
            .limit(1)
            .execute().data or []
        )
        return bool(rows)
    except BaseException:
        return False


def build_monthly_period_documents(data: pd.DataFrame, period_start: date, period_end: date) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for plan in build_monthly_period_document_plan(data, period_start, period_end):
        courier_id = str(plan["courier_id"])
        courier_name = str(plan["courier_name"])
        matching = data[data["Courier ID"].astype(str).eq(courier_id)]
        row = matching.iloc[0].to_dict() if not matching.empty else {}
        payable = parse_huf_value(plan.get("payable_huf"))
        base = parse_huf_value(row.get("Nettó bevétel"))
        tip = parse_huf_value(row.get("Borravaló"))
        bonus = parse_huf_value(row.get("Bónusz"))
        malus = parse_huf_value(row.get("Levonás"))
        routes = [{
            "Túratípus": "Havi összesen",
            "Naptípus": "Összes nap",
            "Túrák": parse_huf_value(row.get("Számolt túrák")),
            "Rendelések": parse_huf_value(row.get("Rendelések")),
        }]
        courier_payload = {
            "name": courier_name,
            "company_name": str(row.get("Vállalkozás neve") or row.get("Futár") or courier_name),
            "address": str(row.get("Cím") or ""),
            "tax_number": str(row.get("Adószám") or ""),
            "tig_type": str(row.get("TIG típus") or row.get("TIG tipus") or row.get("Számla típus") or row.get("ÁFA státusz") or row.get("vat_status") or ""),
            "vat_status": str(row.get("ÁFA státusz") or row.get("vat_status") or ""),
            "email": str(row.get("Email") or ""),
            "id": courier_id,
            "branch": str(row.get("Branch") or ""),
            "warehouse": str(row.get("Raktár") or ""),
            "status": str(row.get("Státusz") or ""),
            "document_month": period_start,
        }
        settlement_bytes = build_settlement_pdf(
            {**courier_payload, "document_reference": plan["settlement_reference"]},
            routes,
            {
                "base": base,
                "tip": tip,
                "bonus": bonus,
                "malus": malus,
                "payable": payable,
            },
        )
        tig_bytes = build_tig_pdf(
            {**courier_payload, "document_reference": plan["tig_reference"]},
            {
                "payable": payable,
                "cash": abs(parse_huf_value(row.get("ATM hatás"))),
                "tip": tip,
            },
        )
        documents.extend([
            {**plan, "document_type": "settlement", "file_name": plan["settlement_file"], "file_bytes": settlement_bytes},
            {**plan, "document_type": "tig", "file_name": plan["tig_file"], "file_bytes": tig_bytes},
        ])
    return documents


def delete_generated_monthly_billing_documents(
    courier_id: str,
    period_start: date,
    document_types: set[str] | None = None,
) -> int:
    document_types = document_types or {"settlement", "tig"}
    try:
        documents = read_peopleforce_documents_for_courier(courier_id)
    except Exception:
        return 0
    if documents.empty:
        return 0
    month_text = period_start.replace(day=1).isoformat()
    deleted = 0
    marker = "Egyedi havi számlázás nyitása"
    for item in documents.to_dict("records"):
        document_type = str(item.get("document_type") or "").strip().lower()
        document_month = str(item.get("document_month") or "")[:10]
        note = str(item.get("note") or "")
        if (
            document_type in document_types
            and document_month == month_text
            and marker in note
            and item.get("id")
        ):
            delete_peopleforce_document(str(item["id"]))
            deleted += 1
    return deleted


def open_individual_monthly_billing(
    row: dict[str, object],
    period_start: date,
    period_end: date,
    calculation_mode: str,
    warehouse_label: str,
    session_id: str | None,
    actor: str,
) -> tuple[int, int, int]:
    courier_id = str(row.get("Courier ID") or "").strip()
    courier_name = str(row.get("Futár") or "").strip()
    if not courier_id or not courier_name:
        return 0, 0, 0

    single_row = pd.DataFrame([row])
    deleted = delete_generated_monthly_billing_documents(courier_id, period_start)
    courier_count, _row_count = publish_mobile_settlement_snapshot(
        single_row,
        period_start,
        calculation_mode,
        warehouse_label,
        session_id,
        actor,
    )
    if not courier_count:
        return deleted, 0, 0

    documents = build_monthly_period_documents(single_row, period_start, period_end)
    uploaded = 0
    for document in documents:
        document_type = str(document.get("document_type") or "").strip()
        title = (
            f"Elszámolás - {period_start:%Y-%m}"
            if document_type == "settlement"
            else f"TIG - {period_start:%Y-%m}"
        )
        note = (
            "Egyedi havi számlázás nyitása. "
            f"Dokumentum azonosító: {document.get(f'{document_type}_reference') or document.get('settlement_reference') or document.get('tig_reference') or ''}"
        ).strip()
        upload_peopleforce_document_bytes(
            courier_id=courier_id,
            courier_name=courier_name,
            document_type=document_type,
            document_month=period_start.replace(day=1),
            title=title,
            note=note,
            file_name=str(document.get("file_name") or "dokumentum.pdf"),
            mime_type="application/pdf",
            file_bytes=document.get("file_bytes") or b"",
            uploaded_by=actor,
        )
        uploaded += 1

    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key="individual_monthly_billing",
        document_month=period_start.replace(day=1),
        status="done",
        status_note="Egyedi havi számlázás megnyitva teszteléshez.",
        updated_by=actor,
    )
    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key="settlement",
        document_month=period_start.replace(day=1),
        status="open",
        status_note="Egyedi havi számlázás megnyitva teszteléshez.",
        updated_by=actor,
    )
    upsert_peopleforce_card_status(
        courier_id=courier_id,
        courier_name=courier_name,
        action_key="tig",
        document_month=period_start.replace(day=1),
        status="open",
        status_note="Admin előnézeti TIG elkészült; futárnak elszámolás elfogadása után aktív.",
        updated_by=actor,
    )
    return deleted, uploaded, courier_count


def close_individual_monthly_billing(
    *,
    courier_id: str,
    courier_name: str,
    period_start: date,
    actor: str,
) -> int:
    deleted = delete_generated_monthly_billing_documents(courier_id, period_start)
    get_db().schema("public").table("peopleforce_card_statuses").delete() \
        .eq("courier_id", str(courier_id or "").strip()) \
        .eq("document_month", period_start.replace(day=1).isoformat()) \
        .eq("action_key", "individual_monthly_billing") \
        .execute()
    read_peopleforce_card_statuses.clear()
    read_peopleforce_card_statuses_for_month.clear()
    return deleted


def show_new_settlement_page() -> None:
    apply_design()
    requested_calculation_mode = st.session_state.pop("courier_requested_calculation_mode", None)
    if requested_calculation_mode in {"API", "Excel"}:
        st.session_state["new_calculation_mode"] = requested_calculation_mode
    selected_calculation_mode = st.session_state.get("new_calculation_mode", "API")
    selected_month_label = st.session_state.get("new_month") or month_options()[0]
    selected_warehouse_label = st.session_state.get("new_warehouse", "Összes")
    selected_period_start = parse_month_option(selected_month_label)
    balance_period_start = selected_period_start
    _, balance_period_end = month_bounds(balance_period_start)
    if str(selected_calculation_mode or "API").strip().casefold() == "excel":
        state_excel_session_id = st.session_state.get("settlement_excel_session_id")
        if state_excel_session_id:
            import_session_id = state_excel_session_id
        else:
            import_session_id = load_latest_excel_jit_session_id(balance_period_start)
            if import_session_id:
                st.session_state["settlement_excel_session_id"] = import_session_id
    else:
        api_session_id = st.session_state.get("settlement_api_session_id") or load_latest_api_jit_session_id(balance_period_start, selected_warehouse_label)
        import_session_id = api_session_id
        if api_session_id:
            st.session_state["settlement_api_session_id"] = api_session_id
            import_session_id = api_session_id
    if str(selected_calculation_mode or "").strip() in {"API", "Excel"} and import_session_id:
        st.session_state["settlement_import_session_id"] = import_session_id
    data = build_settlement_working_data(selected_calculation_mode, import_session_id, balance_period_start, selected_warehouse_label)
    data = apply_received_amounts(
        data,
        selected_calculation_mode,
        balance_period_start,
        selected_warehouse_label,
        import_session_id,
    )
    data = apply_imported_balance_components(
        data,
        balance_component_session_id(selected_calculation_mode, balance_period_start, import_session_id),
    )
    data = apply_loyalty_bonus(data, balance_period_start, balance_period_end, import_session_id, selected_calculation_mode)
    data = apply_customer_rating_bonus(data, balance_period_start, balance_period_end)
    data = apply_manual_balance_adjustments(data, balance_period_start, balance_period_end)
    data = apply_periodic_fee_corrections(
        data,
        import_session_id,
        selected_calculation_mode,
        balance_period_start,
        balance_period_end,
        selected_warehouse_label,
    )
    data = apply_salary_advance_deduction(data, balance_period_start, balance_period_end)
    data = recompute_payable_total(data)
    data = apply_peopleforce_workflow_status(data, balance_period_start)
    data = apply_monthly_closure_status(data, balance_period_start, balance_period_end)
    if str(selected_calculation_mode or "").strip().casefold() == "excel":
        data = apply_excel_route_coverage_audit(data, import_session_id)
    data = apply_dsp_route_delay_audit(data, balance_period_start, balance_period_end)
    data = apply_dsp_shift_attendance_audit(data, balance_period_start, balance_period_end)

    with st.sidebar:
        st.markdown("## Elszámolás")
        st.caption("Szűrés és műveletek")
        selected_month=st.selectbox("Elszámolási hónap",month_options(),key="new_month")
        branch=st.selectbox("Branch",["Összes"]+sorted(data["Branch"].unique().tolist()),key="new_branch")
        calculation_mode=st.selectbox("Számítás módja",["API","Excel","Összes"],key="new_calculation_mode")
        warehouse=st.selectbox("Raktár",["Összes"]+sorted(data["Raktár"].unique().tolist()),key="new_warehouse")
        status=st.selectbox(
            "Elszámolás állapota",
            [
                "Összes",
                "Elszámolásra vár",
                "Elszámolás elfogadásra vár",
                "TIG-re vár",
                "TIG elfogadásra vár",
                "Bejelentések",
                "Kifizetésre vár",
                "Kifizetve",
            ],
            key="new_status",
        )
        search=st.text_input("Futár keresése",placeholder="Név vagy azonosító",key="new_search")
        mobile_period_start = parse_month_option(selected_month)
        if str(calculation_mode or "").strip().casefold() == "excel":
            mobile_source_session_id = st.session_state.get("settlement_excel_session_id") or load_latest_excel_jit_session_id(mobile_period_start)
        else:
            mobile_source_session_id = settlement_mobile_session_for_mode(calculation_mode, mobile_period_start, warehouse)
        if calculation_mode in {"API", "Excel"}:
            st.caption(f"Kiválasztott mobil forrás: {calculation_mode} | session={str(mobile_source_session_id or '-')[:8]}")
        else:
            st.caption("Kiválasztott mobil forrás: nincs, mert a Számítás módja Összes.")
        st.divider()
        if str(calculation_mode or "API").strip().casefold() != "excel":
            api_stats = api_raw_overview_stats(parse_month_option(selected_month), warehouse)
            st.caption(f"API raw adat: {api_stats['couriers']} futár, {api_stats['routes']} útvonal")
            api_breakdown = api_raw_overview_breakdown(parse_month_option(selected_month))
            if not api_breakdown.empty:
                st.dataframe(api_breakdown, hide_index=True, use_container_width=True, height=120)
            selected_api_session_id = load_latest_api_jit_session_id(parse_month_option(selected_month), warehouse)
            api_diagnostics = load_api_import_diagnostics(selected_api_session_id)
            if api_diagnostics.get("error"):
                st.caption(f"API számítás ellenőrzés hiba: {api_diagnostics['error']}")
            else:
                st.caption(
                    "API számítás: "
                    f"session={str(api_diagnostics.get('session_id') or '-')[:8]} | "
                    f"jit_row={api_diagnostics.get('jit_rows', 0)} | "
                    f"summary={api_diagnostics.get('summary_rows', 0)} | "
                    f"számolt={api_diagnostics.get('calculated', 0)} | "
                    f"hiányzó szabály={api_diagnostics.get('missing_base_rate', 0)}"
                )
        if st.button("Adatok betöltése",type="primary",use_container_width=True):
            if str(calculation_mode or "API").strip().casefold() == "excel":
                current_excel_session_id = st.session_state.get("settlement_excel_session_id") or load_latest_excel_jit_session_id(parse_month_option(selected_month))
                if current_excel_session_id:
                    try:
                        current_period_start = parse_month_option(selected_month)
                        _, current_period_end = month_bounds(current_period_start)
                        load_excel_route_coverage_audit.clear()
                        audited = refresh_excel_route_coverage_audit(
                            current_excel_session_id,
                            current_period_start,
                            current_period_end,
                        )
                        st.toast(f"Route ID ellenőrzés frissítve: {audited} futár", icon="✅")
                    except Exception as exc:
                        st.warning(f"Route ID ellenőrzés nem futott le: {exc}")
                st.toast(f"Betöltve: {selected_month}",icon="✅")
            else:
                try:
                    load_api_financial_overview_rows.clear()
                    api_period_start = parse_month_option(selected_month)
                    api_stats = api_raw_overview_stats(api_period_start, warehouse)
                    if api_stats["routes"] == 0:
                        st.error(
                            "Nincs raw API adat erre a hónapra/raktárra. "
                            "Előbb futtasd a Courier Hub API szinkront erre az időszakra."
                        )
                        st.stop()
                    api_session_id = import_api_financial_overview_to_jit(api_period_start, warehouse)
                    if settlement_warehouse_id(warehouse) is not None:
                        import_api_financial_overview_to_jit(api_period_start, "Összes")
                    st.session_state["settlement_api_session_id"] = api_session_id
                    st.session_state["settlement_import_session_id"] = api_session_id
                    load_latest_api_jit_session_id.clear()
                    load_excel_courier_base_rates.clear()
                    load_excel_base_rate_diagnostics.clear()
                    load_courier_route_detail.clear()
                    load_imported_balance_components.clear()
                    load_courier_settlement_summary.clear()
                    load_courier_master.clear()
                    load_api_import_diagnostics.clear()
                    st.toast(f"API adatok betöltve és újraszámolva: {selected_month}", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"API adatok betöltése sikertelen: {exc}")
        if st.button("Szűrők törlése",use_container_width=True):
            st.session_state["new_branch"]="Összes"
            st.session_state["new_calculation_mode"]="API"
            st.session_state["new_warehouse"]="Összes"
            st.session_state["new_status"]="Összes"
            st.session_state["new_search"]=""
            st.session_state.pop("dashboard_status_filter", None)
            st.rerun()

        st.divider()
        st.markdown("### Excel számítás")
        st.caption("A szűrőktől független feltöltési terület.")

        if "excel_upload_version" not in st.session_state:
            st.session_state["excel_upload_version"] = 0

        uploaded_excel = st.file_uploader(
            "Excel feltöltése",
            type=["xlsx", "xls"],
            key=f"calculation_excel_upload_{st.session_state['excel_upload_version']}",
            help="Designer elem, az Excel tartalma még nem kerül feldolgozásra.",
        )

        if uploaded_excel is not None:
            st.success(f"Kiválasztva: {uploaded_excel.name}")

        excel_import_session_id = (
            st.session_state.get("settlement_excel_session_id")
            or load_latest_excel_jit_session_id(parse_month_option(selected_month))
        )
        excel_action1, excel_action_check, excel_action2 = st.columns(3)

        if excel_action1.button(
            "Számítás betöltése",
            type="primary",
            use_container_width=True,
            disabled=uploaded_excel is None,
            key="load_excel_calculation",
            help="Importálja az Excelt, majd a paraméterezett Fixed Rate szabályokkal kiszámítja a futár alapdíját.",
        ):
            try:
                result = save_excel_to_supabase(
                    uploaded_excel,
                    get_db(),
                )
                st.session_state["excel_calculation_loaded"] = True
                st.session_state["settlement_excel_session_id"] = result["session_id"]
                st.session_state["settlement_import_session_id"] = result["session_id"]
                st.session_state["settlement_import_result"] = result
                st.session_state.pop("settlement_import_preview", None)
                st.session_state.pop("settlement_processing_report", None)

                processing_report = process_settlement_session(
                    get_db(),
                    result["session_id"],
                )
                processing_result = report_as_dict(processing_report)
                st.session_state["settlement_processing_report"] = processing_result

                if processing_result.get("status") in {"completed", "completed_with_warnings"}:
                    load_driver_dashboard.clear()
                    load_courier_master.clear()
                    load_latest_jit_session_id.clear()
                    load_latest_excel_jit_session_id.clear()
                    load_excel_courier_base_rates.clear()
                    load_excel_base_rate_diagnostics.clear()
                    load_courier_route_detail.clear()
                    load_imported_balance_components.clear()
                    load_courier_settlement_summary.clear()
                    parameter_revision = int(st.session_state.get("settlement_parameter_revision", 0))
                    recalculate_excel_base_rates(get_db(), result["session_id"])
                    try:
                        load_excel_route_coverage_audit.clear()
                        refresh_excel_route_coverage_audit(
                            result["session_id"],
                            balance_period_start,
                            balance_period_end,
                        )
                    except Exception as exc:
                        st.warning(f"Route ID ellenőrzés nem futott le: {exc}")
                    st.session_state["settlement_base_rate_summary"] = load_excel_courier_base_rates(
                        result["session_id"],
                        parameter_revision,
                    )

                if processing_result.get("status") == "failed":
                    error_messages = [
                        f"{error.get('error_code', 'HIBA')}: "
                        f"{error.get('message', 'Ismeretlen feldolgozási hiba')}"
                        for error in processing_result.get("errors", [])
                    ]
                    raise RuntimeError(
                        "A normalizált feldolgozás sikertelen. "
                        + (" | ".join(error_messages) if error_messages else "Nincs részletes hibaüzenet.")
                    )

                st.success(
                    f"Excel import kész: {result['sheet_count']} sheet, "
                    f"{result['inserted_rows']} sor."
                )
                st.rerun()

            except Exception as exc:
                st.session_state["excel_calculation_loaded"] = False
                error_details = "".join(
                    traceback.format_exception(
                        type(exc),
                        exc,
                        exc.__traceback__,
                    )
                )

                st.error(
                    f"Excel import sikertelen: {type(exc).__name__}: {exc!r}"
                )
                with st.expander("Technikai hiba részletei", expanded=True):
                    st.code(error_details, language="text")

        excel_import_session_id = (
            st.session_state.get("settlement_excel_session_id")
            or load_latest_excel_jit_session_id(parse_month_option(selected_month))
        )

        if excel_action_check.button(
            "SQL ellenőrzés",
            use_container_width=True,
            disabled=not excel_import_session_id,
            key="check_excel_import_sql",
            help="A settlement.vw_excel_preview nézetből olvassa vissza az importot.",
        ):
            try:
                preview_df = get_import_preview(
                    get_db(),
                    excel_import_session_id,
                    limit=200,
                )
                st.session_state["settlement_import_preview"] = preview_df

                if preview_df.empty:
                    st.warning("A SQL ellenőrzés lefutott, de nincs visszaolvasott sor.")
                else:
                    st.success(f"SQL ellenőrzés OK: {len(preview_df)} sor visszaolvasva.")

            except Exception as exc:
                st.error(f"SQL ellenőrzés sikertelen: {exc}")

        if excel_import_session_id and st.button(
            "Route ID ellenőrzés frissítése",
            use_container_width=True,
            key="refresh_excel_route_audit",
            help="Összeveti a DSP route ID-kat az Excelben szereplő route ID-kkal, és DB-be menti az eredményt.",
        ):
            try:
                route_audit_period_start = parse_month_option(selected_month)
                _, route_audit_period_end = month_bounds(route_audit_period_start)
                load_excel_route_coverage_audit.clear()
                audited = refresh_excel_route_coverage_audit(
                    excel_import_session_id,
                    route_audit_period_start,
                    route_audit_period_end,
                )
                st.success(f"Route ID ellenőrzés kész: {audited} futár.")
                st.rerun()
            except Exception as exc:
                st.error(f"Route ID ellenőrzés sikertelen: {exc}")

        if st.button(
            "Késés ellenőrzés frissítése",
            use_container_width=True,
            key="refresh_dsp_route_delay_audit",
            help="Az API havi késés darabszámát hasonlítja a mart időablakon belüli késéseihez.",
        ):
            try:
                delay_audit_period_start = parse_month_option(selected_month)
                _, delay_audit_period_end = month_bounds(delay_audit_period_start)
                load_dsp_time_window_delay_audit.clear()
                delay_audit_result = refresh_dsp_route_delay_audit(
                    delay_audit_period_start,
                    delay_audit_period_end,
                )
                load_dsp_time_window_delay_audit.clear()
                st.success(
                    "Késés ellenőrzés kész: "
                    f"{delay_audit_result['monthly_compare_rows']} havi futár összevetés."
                )
            except Exception as exc:
                st.error(f"Késés ellenőrzés sikertelen: {exc}")

        if st.button(
            "No-show ellenőrzés frissítése",
            use_container_width=True,
            key="refresh_dsp_shift_attendance_audit",
            help="Az API műszak-késés és no-show darabszámait hasonlítja a saját műszak riporthoz.",
        ):
            try:
                attendance_audit_period_start = parse_month_option(selected_month)
                _, attendance_audit_period_end = month_bounds(attendance_audit_period_start)
                load_dsp_shift_attendance_audit.clear()
                attendance_audit_result = refresh_dsp_shift_attendance_audit(
                    attendance_audit_period_start,
                    attendance_audit_period_end,
                )
                load_dsp_shift_attendance_audit.clear()
                st.success(
                    "No-show ellenőrzés kész: "
                    f"{attendance_audit_result['monthly_compare_rows']} havi futár összevetés."
                )
            except Exception as exc:
                st.error(f"No-show ellenőrzés sikertelen: {exc}")

        if excel_action2.button(
            "Törlés",
            use_container_width=True,
            disabled=False,
            key="delete_excel_calculation",
            help="Kiüríti az importhoz és feldolgozáshoz tartozó settlement táblákat.",
        ):
            try:
                deleted_by_table = delete_all_settlement_data(get_db())
                deleted_total = sum(deleted_by_table.values())

                st.session_state["excel_upload_version"] += 1
                st.session_state["excel_calculation_loaded"] = False
                st.session_state.pop("settlement_import_session_id", None)
                st.session_state.pop("settlement_excel_session_id", None)
                st.session_state.pop("settlement_api_session_id", None)
                st.session_state.pop("settlement_import_result", None)
                st.session_state.pop("settlement_import_preview", None)
                st.session_state.pop("settlement_processing_report", None)
                st.session_state.pop("settlement_base_rate_summary", None)
                load_driver_dashboard.clear()
                load_courier_master.clear()
                load_latest_jit_session_id.clear()
                load_latest_excel_jit_session_id.clear()
                load_excel_courier_base_rates.clear()
                load_excel_base_rate_diagnostics.clear()
                load_courier_route_detail.clear()
                load_imported_balance_components.clear()
                load_courier_settlement_summary.clear()
                load_excel_route_coverage_audit.clear()

                st.toast(f"Settlement adatok törölve: {deleted_total} sor.")
                st.rerun()

            except Exception as exc:
                error_details = "".join(
                    traceback.format_exception(
                        type(exc),
                        exc,
                        exc.__traceback__,
                    )
                )
                st.error(f"A settlement adatok törlése sikertelen: {exc}")
                with st.expander("Törlési hiba részletei", expanded=True):
                    st.code(error_details, language="text")

        st.divider()
        st.markdown("### Ügyfélértékelés feltöltése")
        st.caption("Havi order rating Excel. A bónusz a futár profil Pénzügy fülén is megjelenik.")
        rating_month = st.date_input(
            "Értékelési hónap",
            value=balance_period_start,
            key="customer_rating_upload_month",
        ).replace(day=1)
        uploaded_rating_excel = st.file_uploader(
            "Ügyfélértékelés Excel",
            type=["xlsx", "xls"],
            key="customer_rating_excel_upload",
            help="Elvárt oszlopok: order_id, courier_name, courier_id, courier_rating, deliver_at, warehouse_name.",
        )
        st.caption("Uj havi sablon is feltoltheto: Feltoltes_havi ful, elszamolasi_honap, futar_id, futar_nev, ugyfelertekeles_havi_atlag, ertekeles_db.")
        rating_preview = pd.DataFrame()
        if uploaded_rating_excel is not None:
            try:
                rating_preview = parse_customer_rating_excel_v2(
                    uploaded_rating_excel,
                    rating_month,
                    data,
                )
                st.success(f"Előnézet kész: {len(rating_preview)} futár.")
                rating_rules = load_customer_rating_rules_for_month(
                    rating_month,
                    (rating_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1),
                )
                if rating_rules.empty:
                    st.warning("Nincs érvényes Ügyfélértékelés paraméter erre a hónapra. A bónusz 0 Ft lesz, amíg a Paraméterértékekben nincs rögzített sáv.")
                preview_view = rating_preview.rename(columns={
                    "courier_id": "Courier ID",
                    "driver_name": "Futár",
                    "route_type": "Túratípus",
                    "rating_count": "Értékelés db",
                    "average_rating": "Átlag",
                    "bonus_per_route_huf": "Bónusz / kör",
                    "completed_routes": "Teljesített kör",
                    "bonus_total_huf": "Ügyfélértékelési bónusz",
                })[[
                    "Courier ID", "Futár", "Túratípus", "Értékelés db", "Átlag",
                    "Bónusz / kör", "Teljesített kör", "Ügyfélértékelési bónusz",
                ]].head(20)
                st.dataframe(preview_view, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Az ügyfélértékelés Excel nem olvasható: {exc}")

        if st.button(
            "Ügyfélértékelés mentése",
            type="primary",
            use_container_width=True,
            disabled=uploaded_rating_excel is None or rating_preview.empty,
            key="save_customer_rating_upload",
        ):
            try:
                save_customer_rating_upload(rating_preview, rating_month)
                load_customer_rating_bonus_rows.clear()
                load_driver_dashboard.clear()
                st.success(f"Ügyfélértékelés mentve: {len(rating_preview)} futár, hónap: {rating_month:%Y-%m}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Az ügyfélértékelés mentése sikertelen: {exc}")

        import_result = st.session_state.get("settlement_import_result")
        if import_result:
            st.info(
                f"Utolsó import: {import_result['sheet_count']} sheet, "
                f"{import_result['inserted_rows']} sor. Session: "
                f"{import_result['session_id']}"
            )
            for sheet_name, row_count in import_result["sheet_row_counts"].items():
                st.write(f"- {sheet_name}: {row_count} sor")

        base_rate_summary = st.session_state.get("settlement_base_rate_summary")
        if isinstance(base_rate_summary, pd.DataFrame) and not base_rate_summary.empty:
            st.markdown("#### Paraméterezett alapdíj-számítás")
            st.caption("Az Excel Fixed Rate helyett a Kiemelt/Normál nap és Alap díj szabályok szerinti eredmény.")
            summary_net = int(base_rate_summary["Nettó bevétel"].sum())
            summary_tip = int(base_rate_summary["Borravaló"].sum())
            summary_routes = int(base_rate_summary["Számolt túrák"].sum())
            c_net, c_tip, c_routes = st.columns(3)
            c_net.metric("Futár nettó alapdíj", format_huf(summary_net))
            c_tip.metric("Borravaló", format_huf(summary_tip))
            c_routes.metric("Számolt Route ID", summary_routes)
            st.dataframe(
                base_rate_summary[
                    ["Futár", "Nettó bevétel", "Borravaló", "Kiemelt túrák", "Normál túrák", "Számolt túrák", "Nem számolt túrák"]
                ],
                use_container_width=True,
                hide_index=True,
            )
            diagnostics = load_excel_base_rate_diagnostics(
                import_result["session_id"],
                int(st.session_state.get("settlement_parameter_revision", 0)),
            )
            if not diagnostics.empty and (diagnostics["DB státusz"] != "Alapdíj kiszámolva").any():
                st.markdown("##### Alapdíj-egyezés ellenőrzése (DB)")
                st.caption("Ez a settlement.jit_row táblában tárolt eredmény; a főoldal nem számol újra.")
                st.dataframe(diagnostics, use_container_width=True, hide_index=True)

        processing_result = st.session_state.get(
            "settlement_processing_report"
        )
        if processing_result:
            st.markdown("#### Normalizált feldolgozás")

            processing_status = processing_result.get("status", "unknown")
            processing_message = (
                f"{processing_result.get('recognized_sheets', 0)}/"
                f"{processing_result.get('total_sheets', 0)} felismert sheet, "
                f"{processing_result.get('accepted_rows', 0)} elfogadott és "
                f"{processing_result.get('rejected_rows', 0)} elutasított sor."
            )

            if processing_status == "failed":
                st.error(f"Feldolgozás sikertelen: {processing_message}")
            elif processing_status == "completed_with_warnings":
                st.warning(f"Feldolgozás figyelmeztetésekkel kész: {processing_message}")
            elif processing_status == "completed":
                st.success(f"Feldolgozás kész: {processing_message}")
            else:
                st.info(f"Feldolgozás állapota: {processing_status}. {processing_message}")

            st.caption(
                f"Állapot: {processing_status} | "
                f"Run: {processing_result.get('processing_run_id', '-')}"
            )

            sheet_rows = [
                {
                    "Sheet": sheet["sheet_name"],
                    "Típus": sheet["detected_type"] or "ismeretlen",
                    "Állapot": sheet["status"],
                    "Összes sor": sheet["total_rows"],
                    "Elfogadott": sheet["accepted_rows"],
                    "Elutasított": sheet["rejected_rows"],
                    "Confidence": sheet["confidence"],
                }
                for sheet in processing_result.get("sheets", [])
            ]
            if sheet_rows:
                st.dataframe(
                    pd.DataFrame(sheet_rows),
                    use_container_width=True,
                    hide_index=True,
                )

            processing_errors = processing_result.get("errors", [])
            if processing_errors:
                with st.expander(
                    f"Validációs jelzések ({len(processing_errors)})"
                ):
                    error_rows = [
                        {
                            "Súlyosság": error["severity"],
                            "Kód": error["error_code"],
                            "Sheet": error.get("sheet_name"),
                            "Forrássor": error.get("source_row_no"),
                            "Üzenet": error["message"],
                        }
                        for error in processing_errors
                    ]
                    st.dataframe(
                        pd.DataFrame(error_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

        preview_df = st.session_state.get("settlement_import_preview")
        if isinstance(preview_df, pd.DataFrame) and not preview_df.empty:
            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
            )
        elif st.session_state.get("excel_calculation_loaded", False):
            st.info("A számítás betöltve. Futtasd az SQL ellenőrzést a visszaolvasáshoz.")

        st.markdown('<p class="side-note">Könnyű, külső UI-csomag nélküli felület. A régi elszámolási oldalt nem módosítja.</p>',unsafe_allow_html=True)

    # Alapszűrés: ha nincs kijelölt felső státuszkártya, minden futár látszik
    # az aktuálisan kiválasztott raktárban és a többi oldalsávos szűrő szerint.
    base_filtered=data.copy()
    if branch!="Összes":
        base_filtered=base_filtered[base_filtered["Branch"]==branch]
    if calculation_mode!="Összes":
        base_filtered=base_filtered[base_filtered["Számítás módja"]==calculation_mode]
    if warehouse!="Összes":
        base_filtered=base_filtered[base_filtered["Raktár"]==warehouse]
    if status!="Összes":
        base_filtered=base_filtered[base_filtered["Státusz"]==status]
    if search.strip():
        base_filtered = filter_couriers_by_search(base_filtered, search)

    active_workflow_filter = st.session_state.get("dashboard_status_filter")
    filtered = base_filtered.copy()
    if active_workflow_filter:
        filtered = filtered[filtered["Státusz"] == active_workflow_filter]

    st.session_state["current_filtered_data"]=filtered.copy()

    total_gross=int(filtered["Nettó bevétel"].sum()) if not filtered.empty else 0
    total_deduction=int(filtered["Levonás"].sum()) if not filtered.empty else 0
    total_payable=int(filtered["Kifizetendő"].sum()) if not filtered.empty else 0
    previous_period_start = add_months(balance_period_start, -1)
    previous_period_start, previous_period_end = month_bounds(previous_period_start)
    previous_filtered = pd.DataFrame(columns=filtered.columns)
    try:
        previous_session_id = None
        if str(selected_calculation_mode or "API").strip().casefold() == "excel":
            previous_session_id = load_latest_excel_jit_session_id(previous_period_start)
        if str(selected_calculation_mode or "API").strip().casefold() == "api":
            previous_session_id = load_latest_api_jit_session_id(previous_period_start, selected_warehouse_label)
            if not previous_session_id:
                raise RuntimeError("Nincs előző havi API session")
        previous_data = build_settlement_working_data(
            selected_calculation_mode,
            previous_session_id,
            previous_period_start,
            selected_warehouse_label,
        )
        previous_data = apply_received_amounts(
            previous_data,
            selected_calculation_mode,
            previous_period_start,
            selected_warehouse_label,
            previous_session_id,
        )
        previous_data = apply_imported_balance_components(
            previous_data,
            balance_component_session_id(selected_calculation_mode, previous_period_start, previous_session_id),
        )
        previous_data = apply_loyalty_bonus(previous_data, previous_period_start, previous_period_end, previous_session_id, selected_calculation_mode)
        previous_data = apply_customer_rating_bonus(previous_data, previous_period_start, previous_period_end)
        previous_data = apply_manual_balance_adjustments(previous_data, previous_period_start, previous_period_end)
        previous_data = apply_salary_advance_deduction(previous_data, previous_period_start, previous_period_end)
        previous_data = recompute_payable_total(previous_data)
        previous_data = apply_peopleforce_workflow_status(previous_data, previous_period_start)
        previous_data = apply_monthly_closure_status(previous_data, previous_period_start, previous_period_end)
        previous_filtered = previous_data.copy()
        if branch!="Összes":
            previous_filtered=previous_filtered[previous_filtered["Branch"]==branch]
        if calculation_mode!="Összes":
            previous_filtered=previous_filtered[previous_filtered["Számítás módja"]==calculation_mode]
        if warehouse!="Összes":
            previous_filtered=previous_filtered[previous_filtered["Raktár"]==warehouse]
        if status!="Összes":
            previous_filtered=previous_filtered[previous_filtered["Státusz"]==status]
        if search.strip():
            previous_filtered = filter_couriers_by_search(previous_filtered, search)
        if active_workflow_filter:
            previous_filtered = previous_filtered[previous_filtered["Státusz"] == active_workflow_filter]
    except BaseException:
        previous_filtered = pd.DataFrame(columns=filtered.columns)

    st.markdown(
        f"""
        <div class="premium-hero">
        <div class="hero-left"><div class="badge">ÚJ MODUL</div><h1>Új Elszámolási oldal</h1><p>Gyors, átlátható és biztonságos futárelszámolási felület.</p></div>
        <div class="month-pill"><div class="label">Havi indítás</div><div class="value">{html.escape(selected_month)}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    monthly_document_plan = build_monthly_period_document_plan(filtered, balance_period_start, balance_period_end)
    period_start_clicked = monthly_period_start_already_clicked(balance_period_start)
    start_label = (
        f"Havi elszámolási időszak indítása - {selected_month} "
        f"({len(monthly_document_plan)} futár)"
    )
    if st.button(
        start_label,
        disabled=period_start_clicked or selected_calculation_mode not in {"API", "Excel"},
        use_container_width=True,
        key=f"monthly_period_start_{balance_period_start:%Y%m}",
        help="Egyszeri inditas: a futar PWA-ban megkapja az elszamolasi idoszakot. TIG csak elszamolas elfogadasa utan keszul.",
    ):
        snapshot_session_id = settlement_mobile_session_for_mode(
            selected_calculation_mode,
            balance_period_start,
            selected_warehouse_label,
        )
        courier_count, row_count = publish_mobile_settlement_snapshot(
            filtered,
            balance_period_start,
            selected_calculation_mode,
            selected_warehouse_label,
            snapshot_session_id,
            str(st.session_state.get("user", {}).get("username") or "unknown"),
        )
        if courier_count:
            st.session_state[f"monthly_period_start_clicked_{balance_period_start:%Y%m}"] = True
            st.success(f"Havi elszámolási időszak elindítva: {courier_count} futár, {row_count} mobil érték publikálva.")
            st.rerun()
        else:
            st.error("A havi nyitás nem sikerült. Ellenőrizd a mobil SQL táblákat és a kiválasztott API/Excel sessiont.")
    if period_start_clicked:
        st.info("Ez a havi elszámolási időszak már el lett indítva.")
    else:
        st.caption("A havi nyitás a kiválasztott API/Excel forrásból publikálja ugyanazokat az értékeket az admin és futár mobil nézetbe.")

    total_received = int(_numeric_series(filtered, "Alvállalkozói összeg").sum()) if not filtered.empty else 0
    if st.button(
        f"Mobil értékek tömeges frissítése ellenőrzéshez - {selected_month} ({len(filtered)} futár)",
        disabled=selected_calculation_mode not in {"API", "Excel"} or filtered.empty,
        use_container_width=True,
        key=f"mobile_breakdown_bulk_refresh_{balance_period_start:%Y%m}",
        help="Csak a PWA megjelenítési bontást frissíti a DB-ben. Nem indít havi folyamatot és nem nyitja meg a futároknak.",
    ):
        snapshot_session_id = settlement_mobile_session_for_mode(
            selected_calculation_mode,
            balance_period_start,
            selected_warehouse_label,
        )
        courier_count, row_count = refresh_mobile_settlement_breakdown_snapshot(
            filtered,
            balance_period_start,
            selected_calculation_mode,
            selected_warehouse_label,
            snapshot_session_id,
            str(st.session_state.get("user", {}).get("username") or "unknown"),
        )
        if courier_count:
            st.success(f"Mobil ellenőrzési értékek frissítve: {courier_count} futár, {row_count} sor.")
            st.rerun()
        else:
            st.error("A mobil ellenőrzési frissítés nem sikerült. Ellenőrizd a kiválasztott API/Excel sessiont és a szűrést.")

    previous_total_payable = int(_numeric_series(previous_filtered, "Kifizetendő").sum()) if not previous_filtered.empty else 0
    previous_total_received = int(_numeric_series(previous_filtered, "Alvállalkozói összeg").sum()) if not previous_filtered.empty else 0
    payable_note = previous_month_delta_note(total_payable, previous_total_payable)
    received_note = previous_month_delta_note(total_received, previous_total_received)
    payable_percent = donut_percent(total_payable, previous_total_payable)
    received_percent = donut_percent(total_received, previous_total_received)

    st.markdown(
        f"""
        <div class="summary-donut-grid">
        <div class="summary-donut-card">
            <div>
            <div class="summary-donut-title">Kifizetés összesen</div>
            <div class="summary-donut-value">{format_huf(total_payable)}</div>
            <div class="summary-donut-note">{html.escape(payable_note)}</div>
            </div>
            <div class="summary-donut summary-donut-primary" style="background: conic-gradient(#1FA64A 0 {payable_percent}%, #DDF5E4 {payable_percent}% 100%);">
            <div class="summary-donut-center"><strong>{total_payable / 1_000_000:.1f} M</strong><span>Ft</span></div>
            </div>
        </div>

        <div class="summary-donut-card">
            <div>
            <div class="summary-donut-title">Alvállalkozói összeg</div>
            <div class="summary-donut-value">{format_huf(total_received)}</div>
            <div class="summary-donut-note">{html.escape(received_note)}</div>
            </div>
            <div class="summary-donut summary-donut-secondary" style="background: conic-gradient(#17853B 0 {received_percent}%, #DDF5E4 {received_percent}% 100%);">
            <div class="summary-donut-center"><strong>{total_received / 1_000_000:.1f} M</strong><span>Ft</span></div>
            </div>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Áttekintés</div>',unsafe_allow_html=True)

    workflow_cards = [
        ("Elszámolásra vár", "Még nem készült elszámolás", "🔵"),
        ("Elszámolás elfogadásra vár", "Futár elfogadására vár", "🔵"),
        ("TIG-re vár", "Még nem készült TIG", "🟣"),
        ("TIG elfogadásra vár", "Futár TIG elfogadására vár", "🟣"),
        ("Bejelentések", "Nyitott ügyek", "🟠"),
        ("Kifizetésre vár", "Jóváhagyás után", "🟡"),
        ("Kifizetve", "Havi zárás kész", "🟢"),
    ]
    card_columns = st.columns(len(workflow_cards))
    active_workflow_filter = st.session_state.get("dashboard_status_filter")

    for card_column, (card_status, card_note, card_icon) in zip(card_columns, workflow_cards):
        card_count = int((base_filtered["Státusz"] == card_status).sum())
        is_active = active_workflow_filter == card_status
        checkmark = "  ✅" if is_active else ""
        button_label = f"{card_icon} {card_status}\n\n{card_count} db{checkmark}\n\n{card_note}"

        if card_column.button(
            button_label,
            key=f"workflow_card_{card_status}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if is_active:
                st.session_state.pop("dashboard_status_filter", None)
            else:
                st.session_state["dashboard_status_filter"] = card_status
            st.rerun()

    if active_workflow_filter:
        st.caption(
            f"Aktív szűrés: {active_workflow_filter}. "
            "A kijelölt kártyára ismét kattintva a szűrés kikapcsol."
        )
    else:
        selected_warehouse_label = warehouse if warehouse != "Összes" else "összes raktár"
        st.caption(f"Nincs felső státuszszűrés: minden futár megjelenik ({selected_warehouse_label}).")

    render_table(filtered)
    if st.session_state.pop("reopen_courier_dialog", False) and st.session_state.get("selected_courier_id"):
        show_courier_dialog()

    st.markdown('<div class="section-title" style="margin-top:18px">Gyors műveletek</div>',unsafe_allow_html=True)
    a,b,c,d,e=st.columns(5)
    if a.button("Tömeges elszámolás",use_container_width=True):
        show_bulk_settlement_dialog()
    if b.button("Tömeges TIG",use_container_width=True):
        show_bulk_tig_dialog()
    if c.button("Bejelentések",use_container_width=True):
        show_reports_dialog()
    if d.button("Paraméterértékek",use_container_width=True):
        show_parameter_catalog_dialog()
    e.download_button(
        "Export Excel",
        data=build_excel_export(filtered),
        file_name="elszamolas_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


if __name__ == "__main__":
    if devtest_page == "PDF minta":
        show_settlement_pdf_sample_page()
    else:
        show_new_settlement_page()
