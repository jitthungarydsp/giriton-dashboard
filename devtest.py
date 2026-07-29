import html
import json
import re
import traceback
import unicodedata
import uuid
from datetime import date, timedelta
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
from resources.settlement_pdf import build_settlement_pdf
from resources.courier_master_db import update_courier_master_profile
from page.settlement_parameter_catalog import render_parameter_catalog

try:
    from resources.dsp_route_explanations import (
        read_order_details_for_routes,
        read_route_stories,
    )
except Exception:
    read_order_details_for_routes = None
    read_route_stories = None

RESERVE_TARGET_HUF = 350_000
RESERVE_RATE = 0.10
INSURANCE_FEE_HUF = 10_000
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
def load_latest_excel_jit_session_id() -> str | None:
    """Find the latest non-API JIT session for Excel calculation mode."""
    try:
        rows = (
            get_db()
            .schema("settlement")
            .table("jit_row")
            .select("session_id,source_sheet,created_at")
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
        "Raktár", "Státusz", "Nettó bevétel", "Bónusz",
        "Borravaló", "Levonás", "Kifizetendő", "Előző havi összeg",
        "KPI", "Munkakezdés",
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
    if "Munkakezdés" not in df.columns:
        df["Munkakezdés"] = ""

    # Ideiglenes designer státuszok. Később ezt valódi üzleti logika váltja fel.
    workflow_statuses = [
        "Elszámolásra vár",
        "TIG-re vár",
        "Bejelentések",
        "Kifizetésre vár",
    ]
    df["Státusz"] = [
        workflow_statuses[index % len(workflow_statuses)]
        for index in range(len(df))
    ]

    for column in [
        "Nettó bevétel", "Bónusz", "Borravaló", "Levonás",
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
def load_target_reserve_status(courier_id: str, courier_name: str) -> dict[str, object]:
    """Return insurance only from the insurance_active flag of a matching reserve row."""
    try:
        rows = (get_db().schema("public").table("courier_target_reserve")
                .select("*").limit(10000).execute().data or [])
    except BaseException:
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


def calculate_target_reserve_month(
    reserve_status: dict[str, object],
    payable_before_insurance: float,
) -> dict[str, object]:
    reserve_row = reserve_status.get("row") or {}
    insurance_active_before = bool(reserve_status.get("insurance_active"))
    reserve_before = reserve_row_amount(reserve_row, "current_reserve_huf")
    if reserve_before == 0:
        reserve_before = reserve_row_amount(reserve_row, "CT_Z_FT")

    should_charge = insurance_active_before and reserve_before < RESERVE_TARGET_HUF
    reserve_addition = round(max(float(payable_before_insurance), 0.0) * RESERVE_RATE) if should_charge else 0
    insurance_fee = INSURANCE_FEE_HUF if should_charge else 0
    reserve_after = reserve_before + reserve_addition
    insurance_active_after = bool(insurance_active_before and reserve_after < RESERVE_TARGET_HUF)
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


def format_bank_account_4(value: object) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    return " ".join(digits[index:index + 4] for index in range(0, len(digits), 4))


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
) -> None:
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
    calculation = calculate_target_reserve_month(reserve_status, payable_before_insurance)
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
    save_target_reserve_monthly(session_id, courier_id, period_start, period_end, calculation)
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
        "Rendszerbónusz", "Kiemelt túrák", "Normál túrák", "Számolt túrák", "Nem számolt túrák",
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
                "Rendszerbónusz", "Számolt túrák", "Nem számolt túrák",
            ]
        ]
        .sum()
    )
    calculated_by_id = calculated[calculated["_courier_id_lookup"] != ""].groupby("_courier_id_lookup", as_index=False)[
        [
            "Nettó bevétel", "Vállalkozói alapdíj", "Borravaló",
            "Rendszerbónusz", "Számolt túrák", "Nem számolt túrák",
        ]
    ].sum()
    amount_by_id = calculated_by_id.set_index("_courier_id_lookup")["Nettó bevétel"] if not calculated_by_id.empty else pd.Series(dtype=float)
    company_amount_by_id = calculated_by_id.set_index("_courier_id_lookup")["Vállalkozói alapdíj"] if not calculated_by_id.empty else pd.Series(dtype=float)
    tip_by_id = calculated_by_id.set_index("_courier_id_lookup")["Borravaló"] if not calculated_by_id.empty else pd.Series(dtype=float)
    system_bonus_by_id = calculated_by_id.set_index("_courier_id_lookup")["Rendszerbónusz"] if not calculated_by_id.empty else pd.Series(dtype=float)
    matched_routes_by_id = calculated_by_id.set_index("_courier_id_lookup")["Számolt túrák"] if not calculated_by_id.empty else pd.Series(dtype=float)
    unmatched_routes_by_id = calculated_by_id.set_index("_courier_id_lookup")["Nem számolt túrák"] if not calculated_by_id.empty else pd.Series(dtype=float)
    amount_by_courier = calculated_by_name.set_index("_courier_lookup")["Nettó bevétel"]
    company_amount_by_courier = calculated_by_name.set_index("_courier_lookup")["Vállalkozói alapdíj"]
    tip_by_courier = calculated_by_name.set_index("_courier_lookup")["Borravaló"]
    system_bonus_by_courier = calculated_by_name.set_index("_courier_lookup")["Rendszerbónusz"]
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
    result["Számolt túrák"] = result["_courier_id_lookup"].map(matched_routes_by_id).fillna(resolved_lookup.map(matched_routes)).fillna(0).astype(int)
    result["Nem számolt túrák"] = result["_courier_id_lookup"].map(unmatched_routes_by_id).fillna(resolved_lookup.map(unmatched_routes)).fillna(0).astype(int)
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + _numeric_series(result, "Bónusz")
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


def _api_route_other_bonus(route: dict[str, object]) -> float:
    excluded = {"fixed_base", "delay_performance", "dataport_delay_performance", "compliance"}
    total = 0.0
    for item in route.get("ruleBreakdown") or []:
        if not isinstance(item, dict):
            continue
        fee_type = str(item.get("feeType") or "").casefold()
        if fee_type and fee_type not in excluded:
            total += _money_amount(item.get("amount"))
    return total


@st.cache_data(show_spinner=False, ttl=60)
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


def api_financial_routes_to_detail(rows: pd.DataFrame, courier_id: str | None = None) -> pd.DataFrame:
    columns = [
        "Route ID", "Excel dátum", "Hét napja", "Túratípus", "Naptípus",
        "Rendelések", "Alapdíj", "Borravaló", "Késedelmi díj",
        "Túramegfelelés", "Egyéb bónusz", "Bónuszok", "DB státusz",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
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
            parsed.append({
                "_courier_id": _courier_id_key(source.get("courier_id")),
                "Route ID": str(route.get("routeId") or "–"),
                "Excel dátum": delivery_date or "–",
                "Hét napja": weekday_names.get(int(parsed_date.dayofweek) + 1, "–") if pd.notna(parsed_date) else "–",
                "Túratípus": route_type,
                "Naptípus": "Nincs besorolás",
                "Rendelések": parse_huf_value(route.get("orderCount")),
                "Alapdíj": 0.0,
                "Borravaló": _money_amount(route.get("customerTipsTotal")),
                "Késedelmi díj": 0.0,
                "Túramegfelelés": 0.0,
                "Egyéb bónusz": 0.0,
                "Bónuszok": 0.0,
                "DB státusz": "API nyers adat - paraméterezés szükséges",
            })
    if not parsed:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(parsed).sort_values(["Excel dátum", "Route ID"])


def apply_api_base_rates(data: pd.DataFrame, period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    """API mode must keep the same output contract as the Excel pipeline."""
    result = data.copy()
    result["Számítás módja"] = "API"
    api_session_id = load_latest_api_jit_session_id(period_start, warehouse_label)
    if not api_session_id:
        return result
    return apply_excel_base_rates(result, api_session_id)


def build_settlement_working_data(calculation_mode: str, session_id: str | None, period_start: date, warehouse_label: str | None = None) -> pd.DataFrame:
    """Build the main settlement table without changing its shape per source."""
    normalized_mode = str(calculation_mode or "API").strip().casefold()
    if normalized_mode == "excel":
        data = load_courier_master("Excel")
        return apply_excel_base_rates(data, session_id)
    return apply_api_base_rates(load_courier_master("API"), period_start, warehouse_label)


def recompute_payable_total(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + _numeric_series(result, "Bónusz")
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


def apply_loyalty_bonus(data: pd.DataFrame, period_start: date, period_end: date, session_id: str | None) -> pd.DataFrame:
    result = data.copy()
    rules = load_loyalty_bonus_rules_for_month(period_start, period_end)
    counts = load_loyalty_route_counts(session_id)
    if rules.empty or counts.empty:
        if "Lojalitás" not in result.columns:
            result["Lojalitás"] = 0.0
        return result

    counts_by_driver = {
        driver_key: group.copy()
        for driver_key, group in counts.groupby("driver_key")
    }
    loyalty_amounts: list[float] = []
    for _, row in result.iterrows():
        driver_key = _courier_match_key(row.get("Futár"))
        months_worked = completed_months_between(row.get("Munkakezdés"), period_end)
        if months_worked < 0:
            loyalty_amounts.append(0.0)
            continue
        driver_counts = counts_by_driver.get(driver_key)
        if driver_counts is None or driver_counts.empty:
            loyalty_amounts.append(0.0)
            continue
        total = 0.0
        for _, rule in rules.iterrows():
            required_months = int(parse_huf_value(rule.get("loyalty_months_required")))
            if months_worked < required_months:
                continue
            route_type = str(rule.get("route_type") or "normal")
            unit = str(rule.get("calculation_unit") or "per_route")
            amount = parse_huf_value(rule.get("bonus_amount_huf"))
            matched_counts = driver_counts if route_type == "any" else driver_counts.loc[driver_counts["route_type"] == normalize_customer_rating_route_type(route_type)]
            if matched_counts.empty:
                continue
            quantity_column = "orders" if unit == "per_order" else "routes"
            total += float(matched_counts[quantity_column].sum()) * amount
        loyalty_amounts.append(total)

    loyalty_bonus = pd.Series(loyalty_amounts, index=result.index)
    result["Lojalitás"] = loyalty_bonus
    result["Bónusz"] = _numeric_series(result, "Bónusz") + loyalty_bonus
    result["Kifizetendő"] = (
        _numeric_series(result, "Nettó bevétel")
        + _numeric_series(result, "Borravaló")
        + _numeric_series(result, "Bónusz")
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
        result["Bónusz"] = _numeric_series(result, "Bónusz") + courier_ids.map(pivot.get("bonus", pd.Series(dtype=float))).fillna(0.0)
        deductions = (pivot.get("malus", pd.Series(dtype=float)) + pivot.get("atm_deduction", pd.Series(dtype=float)) + pivot.get("other_expense", pd.Series(dtype=float)))
        result["Levonás"] = _numeric_series(result, "Levonás") + courier_ids.map(deductions).fillna(0.0)
        result["Bónusz"] += courier_ids.map(pivot.get("customer_rating", pd.Series(dtype=float))).fillna(0.0)
    result["Kifizetendő"] = _numeric_series(result, "Nettó bevétel") + _numeric_series(result, "Borravaló") + _numeric_series(result, "Bónusz") - _numeric_series(result, "Levonás")
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
        + _numeric_series(result, "Bónusz")
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
    ]
    if not session_id:
        return pd.DataFrame(columns=columns)
    definitions = {
        "bonus_route_row": ("Importált bónusz", ("bonus", "bonusz", "amount", "osszeg", "total"), False),
        "penalty_row": ("Importált málusz", ("penalty", "malus", "levonas", "amount", "osszeg"), True),
        "atm_balance_row": ("Importált ATM levonás", ("balance", "egyenleg", "atm", "cash", "amount", "osszeg"), True),
    }
    records: list[dict[str, object]] = []
    for table_name, (output_column, amount_tokens, use_absolute) in definitions.items():
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
            amount_value = next(
                (value for key, value in normalized_payload.items()
                 if any(token in key for token in amount_tokens)),
                None,
            )
            amount = parse_huf_value(amount_value)
            if (courier_id is None and courier_name is None) or amount == 0:
                continue
            records.append({
                "courier_id_key": _courier_id_key(courier_id),
                "courier_name_key": _courier_match_key(courier_name),
                output_column: abs(amount) if use_absolute else amount,
            })
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records).fillna(0.0)
    for column in columns[1:]:
        if column not in result:
            result[column] = 0.0
    return result.groupby(columns[:2], as_index=False, dropna=False)[columns[2:]].sum()


def apply_imported_balance_components(data: pd.DataFrame, session_id: str | None) -> pd.DataFrame:
    result = data.copy()
    components = load_imported_balance_components(session_id)
    component_columns = ("Importált bónusz", "Importált málusz", "Importált ATM levonás")
    for column in component_columns:
        result[column] = 0.0
    if components.empty:
        return result
    component_by_id = (
        components[components["courier_id_key"] != ""]
        .groupby("courier_id_key")[list(component_columns)].sum()
    )
    component_by_name = (
        components[components["courier_name_key"] != ""]
        .groupby("courier_name_key")[list(component_columns)].sum()
    )
    result["_courier_id_component_key"] = result["Courier ID"].map(_courier_id_key)
    result["_courier_name_component_key"] = result["Futár"].map(_courier_match_key)
    for column in component_columns:
        empty_values = pd.Series(float("nan"), index=result.index, dtype="float64")
        by_id = result["_courier_id_component_key"].map(component_by_id[column]) if column in component_by_id else empty_values
        by_name = result["_courier_name_component_key"].map(component_by_name[column]) if column in component_by_name else empty_values
        result[column] = by_id.fillna(by_name).fillna(0.0)
    result["Bónusz"] = _numeric_series(result, "Bónusz") + result["Importált bónusz"]
    result["Levonás"] = _numeric_series(result, "Levonás") + result["Importált málusz"] + result["Importált ATM levonás"]
    return result.drop(columns=["_courier_id_component_key", "_courier_name_component_key"])


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


def status_meta(status: str) -> tuple[str,str]:
    mapping={
        "Előkészítve":("status-red","led-red"),
        "Ellenőrzés alatt":("status-yellow","led-yellow"),
        "Jóváhagyva":("status-green","led-green"),
        "Elszámolásra vár":("status-blue","led-blue"),
        "TIG-re vár":("status-purple","led-purple"),
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


@st.cache_data(show_spinner=False, ttl=60)
def load_courier_route_detail(
    courier_id: str,
    courier_name: str,
    session_id: str | None,
    calculation_mode: str = "Excel",
    period_start: date | None = None,
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
        "Túramegfelelés", "Egyéb bónusz", "Bónuszok", "DB státusz",
    ]
    if not session_id or not courier_id:
        if str(calculation_mode).casefold() != "api" or period_start is None:
            return pd.DataFrame(columns=columns)
    if str(calculation_mode).casefold() == "api" and period_start is not None:
        api_session_id = load_latest_api_jit_session_id(period_start)
        if api_session_id:
            session_id = api_session_id
        else:
            api_rows = load_api_financial_overview_rows(period_start.year, period_start.month)
            api_detail = api_financial_routes_to_detail(api_rows, courier_id)
            return api_detail.drop(columns=["_courier_id"], errors="ignore")
    try:
        rows = (
            get_db().schema("settlement").table("jit_row")
            .select(
                "normalized_data,route_unique_id,route_date,weekday_iso,calculated_day_type,"
                "courier_base_rate_huf,courier_tip_huf,courier_delay_bonus_huf,"
                "courier_compliance_bonus_huf,courier_other_bonus_huf,"
                "courier_bonus_total_huf,is_route_primary,base_rate_status"
            )
            .eq("session_id", session_id).execute().data or []
        )
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
        is_matching_courier = (
            _courier_id_key(source_id) == target_id
            if has_source_id
            else (is_exact_name or is_extended_full_name)
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
        other_bonus = parse_huf_value(source.get("courier_other_bonus_huf"))
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
            "Egyéb bónusz": other_bonus,
            "Bónuszok": parse_huf_value(source.get("courier_bonus_total_huf")),
            "DB státusz": str(source.get("base_rate_status") or "ismeretlen"),
        })
    if not parsed:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(parsed).sort_values(["Excel dátum", "Route ID"])


def summarize_courier_route_detail(route_detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only the auditable Route ID rows displayed to the user."""
    columns = [
        "Túratípus", "Naptípus", "Túrák", "Alapdíj", "Borravaló",
        "Késedelmi díj", "Túramegfelelés", "Egyéb bónusz", "Bónuszok",
    ]
    if route_detail.empty:
        return pd.DataFrame(columns=columns)
    detail = route_detail.copy()
    detail["Túrák"] = 1
    return detail.groupby(["Túratípus", "Naptípus"], as_index=False)[columns[2:]].sum()


def build_amount_drilldown(route_detail: pd.DataFrame, amount_column: str) -> pd.DataFrame:
    columns = ["Túratípus", "Naptípus", "Túrák", "Egységösszeg", "Összeg", "Számítás"]
    if route_detail.empty or amount_column not in route_detail.columns:
        return pd.DataFrame(columns=columns)
    detail = route_detail.copy()
    detail["_amount"] = pd.to_numeric(detail[amount_column], errors="coerce").fillna(0.0)
    detail = detail[detail["_amount"].ne(0)].copy()
    if detail.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        detail.groupby(["Túratípus", "Naptípus", "_amount"], dropna=False)
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
) -> pd.DataFrame:
    columns = [
        "issue_key", "Route ID", "Order ID", "Dátum", "Probléma", "Eltérés perc",
        "Rendelések", "Késedelmi díj", "Túramegfelelés", "Story", "Státusz", "Megjegyzés",
    ]
    if route_detail.empty and stories.empty and order_details.empty:
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
                "Story": str(story_row.get("story_text") or ""),
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


@st.dialog("Futár részletei", width="large")
def show_courier_dialog() -> None:
    courier_id = str(st.session_state.get("selected_courier_id") or "")
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
        data = apply_imported_balance_components(data, dialog_session_id)
        data = apply_manual_balance_adjustments(data, dialog_start, dialog_end)
        data = apply_salary_advance_deduction(data, dialog_start, dialog_end)
        data = recompute_payable_total(data)
    match = data[data["Courier ID"].astype(str) == courier_id]

    if match.empty:
        st.warning("A futár nem található.")
        return

    row = match.iloc[0]
    courier_name = str(row.get("Futár") or "Ismeretlen futár")
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
    period_label = (
        f"{period_start:%Y. %m. %d.} - {period_end:%Y. %m. %d.}"
        if period_start and period_end
        else "Aktuális hónap"
    )
    month_label = f"{period_end:%Y. %B}" if period_end else "Aktuális hónap"
    last_settlement_label = f"{period_end:%Y. %m. %d.}" if period_end else "-"

    route_detail = load_courier_route_detail(courier_id, courier_name, session_id, active_calculation_mode, period_start)
    route_breakdown = summarize_courier_route_detail(route_detail)
    reserve_status = load_target_reserve_status(courier_id, courier_name)
    profile = load_courier_profile(courier_id)
    persisted_summary = load_courier_settlement_summary(session_id)
    summary_row: dict[str, object] = {}
    if not persisted_summary.empty:
        summary_match = persisted_summary[
            persisted_summary.get("courier_id", pd.Series("", index=persisted_summary.index))
            .map(_courier_id_key).eq(_courier_id_key(courier_id))
        ]
        if summary_match.empty and "driver_name" in persisted_summary:
            summary_match = persisted_summary[
                persisted_summary["driver_name"].map(_courier_match_key).eq(_courier_match_key(courier_name))
            ]
        if not summary_match.empty:
            summary_row = summary_match.iloc[0].to_dict()
    profile_adjustments = load_courier_adjustments(courier_id, period_start, period_end)
    profile_adjustment_totals = (
        profile_adjustments.groupby("adjustment_type")["amount_huf"].sum().to_dict()
        if not profile_adjustments.empty else {}
    )

    def settlement_amount(summary_column: str, fallback_column: str | None = None) -> float:
        if summary_column in summary_row:
            return parse_huf_value(summary_row.get(summary_column))
        if fallback_column:
            return parse_huf_value(row.get(fallback_column))
        return 0.0

    base_total = settlement_amount("courier_base_rate_huf", "Nettó bevétel")
    tip_total = settlement_amount("tip_huf", "Borravaló")
    delay_total = settlement_amount("delay_bonus_huf")
    compliance_total = settlement_amount("compliance_bonus_huf")
    other_route_bonus_total = settlement_amount("other_route_bonus_huf")
    imported_bonus_total = settlement_amount("imported_bonus_huf", "Importált bónusz")
    imported_malus_total = abs(parse_huf_value(row.get("Importált málusz")))
    imported_atm_total = abs(parse_huf_value(row.get("Importált ATM levonás")))
    manual_bonus_total = float(profile_adjustment_totals.get("bonus", 0.0))
    loyalty_total = parse_huf_value(row.get("Lojalitás"))
    imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
    customer_rating_total = imported_customer_rating_total + float(profile_adjustment_totals.get("customer_rating", 0.0))
    manual_malus_total = float(profile_adjustment_totals.get("malus", 0.0))
    manual_atm_total = float(profile_adjustment_totals.get("atm_deduction", 0.0))
    other_expense_total = float(profile_adjustment_totals.get("other_expense", 0.0))
    malus_total = imported_malus_total + manual_malus_total
    atm_deduction_total = imported_atm_total + manual_atm_total
    total_income = (
        base_total + tip_total + delay_total + compliance_total + other_route_bonus_total
        + imported_bonus_total + manual_bonus_total + loyalty_total + customer_rating_total
    )
    salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
    total_deduction = malus_total + atm_deduction_total + other_expense_total + salary_advance_total
    payable_before_insurance = total_income - total_deduction
    reserve_month = resolve_target_reserve_month(
        session_id, courier_id, period_start, period_end, reserve_status, payable_before_insurance
    )
    reserve_addition_total = parse_huf_value(reserve_month.get("reserve_addition_huf"))
    insurance_fee_total = parse_huf_value(reserve_month.get("insurance_fee_huf"))
    total_deduction += reserve_addition_total + insurance_fee_total
    payable_total = parse_huf_value(reserve_month.get("payable_after_insurance_huf"))
    monthly_closure = load_courier_monthly_closure(courier_id, period_start, period_end)
    closure_done = str(monthly_closure.get("status") or "").casefold() == "done"
    paid_badge = '<span class="settlement-chip">✓ Kifizetve</span>' if closure_done else ''
    order_total = int(settlement_amount("order_count") or route_detail.get("Rendelések", pd.Series(dtype=float)).sum())
    route_total = int(settlement_amount("route_count") or len(route_detail))
    data_source_label = "DB összesítő" if summary_row else "Főoldali adat"
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
              <div class="settlement-kpi-card"><div class="settlement-kpi-icon blue">Σ</div><div><div class="settlement-kpi-label">Összes bevétel</div><div class="settlement-kpi-value">{format_huf(total_income)}</div><div class="settlement-kpi-note">{html.escape(month_label)}</div></div></div>
              <div class="settlement-kpi-card"><div class="settlement-kpi-icon red">−</div><div><div class="settlement-kpi-label">Összes levonás</div><div class="settlement-kpi-value">{format_huf(total_deduction)}</div><div class="settlement-kpi-note">{html.escape(month_label)}</div></div></div>
              <div class="settlement-kpi-card"><div class="settlement-kpi-icon purple">✓</div><div><div class="settlement-kpi-label">Utolsó elszámolás</div><div class="settlement-kpi-value">{html.escape(last_settlement_label)}</div><div class="settlement-kpi-note">Fizetve</div></div></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    menu_key = f"courier_menu_{courier_id}"
    menu_target_key = f"courier_menu_target_{courier_id}"
    menu_target = st.session_state.pop(menu_target_key, None)
    if menu_target:
        st.session_state[menu_key] = menu_target

    selected_menu = st.radio(
        "Futármenü", ["Áttekintés", "Pénzügy", "Fizetés előleg", "Útvonalak", "Dokumentumok", "Reklamációk", "Profil"],
        horizontal=True, label_visibility="collapsed", key=menu_key,
    )

    def keep_courier_menu(menu_name: str) -> None:
        st.session_state[menu_target_key] = menu_name

    if selected_menu == "Áttekintés":
        missing_data_count = 0
        if not summary_row:
            missing_data_count += 1
        if route_detail.empty:
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
                      <div class="settlement-ledger-row"><span>Alapdíj</span><strong>{format_huf(base_total)}</strong></div>
                      <div class="settlement-ledger-row"><span>Borravaló</span><strong>{format_huf(tip_total)}</strong></div>
                      <div class="settlement-ledger-row"><span>Késedelmi bónusz</span><strong>{format_huf(delay_total)}</strong></div>
                      <div class="settlement-ledger-row"><span>Túramegfelelés / egyéb bónusz</span><strong>{format_huf(compliance_total + other_route_bonus_total + imported_bonus_total + manual_bonus_total + loyalty_total + customer_rating_total)}</strong></div>
                      <div class="settlement-ledger-row total"><span>Összesen</span><strong>{format_huf(total_income)}</strong></div>
                    </div>
                    <div class="settlement-ledger outcome">
                      <div class="settlement-ledger-head">↓ Levonások</div>
                      <div class="settlement-ledger-row"><span>Málusz</span><strong>-{format_huf(malus_total)}</strong></div>
                      <div class="settlement-ledger-row"><span>ATM levonás</span><strong>-{format_huf(atm_deduction_total)}</strong></div>
                      <div class="settlement-ledger-row"><span>Egyéb kiadás</span><strong>-{format_huf(other_expense_total)}</strong></div>
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
                st.session_state["settlement_import_session_id"] = (
                    st.session_state.get("settlement_excel_session_id")
                    or load_latest_excel_jit_session_id()
                )
            else:
                st.session_state["settlement_import_session_id"] = load_latest_api_jit_session_id(
                    period_start,
                    st.session_state.get("new_warehouse", "Összes"),
                )
            st.rerun()
        st.markdown("#### Útvonalak (legutóbbi 5)")
        if route_detail.empty:
            st.info("Nincs megjeleníthető útvonal az aktuális sessionben.")
        else:
            route_preview = route_detail.head(5).copy()
            route_preview["Kör"] = 1
            route_preview["Bevétel"] = route_preview.apply(
                lambda route: sum(
                    parse_huf_value(route.get(column))
                    for column in ["Alapdíj", "Borravaló", "Késedelmi díj", "Túramegfelelés", "Egyéb bónusz"]
                ),
                axis=1,
            )
            route_preview["Bevétel"] = route_preview["Bevétel"].map(format_huf)
            route_preview["Státusz"] = "Elszámolva"
            route_preview = route_preview.rename(
                columns={
                    "Route ID": "Útvonal azonosító",
                    "Excel dátum": "Dátum",
                }
            )
            st.dataframe(
                route_preview[["Útvonal azonosító", "Dátum", "Kör", "Rendelések", "Bevétel", "Státusz"]],
                use_container_width=True,
                hide_index=True,
            )

    if selected_menu == "Pénzügy":
        session_id = st.session_state.get("settlement_import_session_id") or load_latest_jit_session_id()
        period_start, period_end = load_settlement_month(session_id)
        route_detail = load_courier_route_detail(courier_id, str(row["Futár"]), session_id, active_calculation_mode, period_start)
        route_breakdown = summarize_courier_route_detail(route_detail)
        adjustments = load_courier_adjustments(courier_id, period_start, period_end)
        adjustment_totals = adjustments.groupby("adjustment_type")["amount_huf"].sum().to_dict() if not adjustments.empty else {}
        # These two totals are calculated and persisted by the DB view.  The
        # Route ID table below is an audit drill-down, not a second calculator.
        base_total = float(row.get("Nettó bevétel", 0.0))
        tip_total = float(row.get("Borravaló", 0.0))
        delay_total = float(route_breakdown.get("Késedelmi díj", pd.Series(dtype=float)).sum())
        compliance_total = float(route_breakdown.get("Túramegfelelés", pd.Series(dtype=float)).sum())
        route_other_bonus_total = float(route_breakdown.get("Egyéb bónusz", pd.Series(dtype=float)).sum())
        bonus_total = route_other_bonus_total + float(adjustment_totals.get("bonus", 0))
        loyalty_total = parse_huf_value(row.get("Lojalitás"))
        imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
        customer_rating_total = imported_customer_rating_total + float(adjustment_totals.get("customer_rating", 0))
        malus_total = float(adjustment_totals.get("malus", 0))
        atm_deduction_total = float(adjustment_totals.get("atm_deduction", 0))
        other_expense_total = float(adjustment_totals.get("other_expense", 0))
        salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
        imported_bonus_total = parse_huf_value(row.get("Importált bónusz"))
        imported_malus_total = abs(parse_huf_value(row.get("Importált málusz")))
        imported_atm_total = abs(parse_huf_value(row.get("Importált ATM levonás")))
        bonus_total += imported_bonus_total
        malus_total += imported_malus_total
        atm_deduction_total += imported_atm_total
        payable_total = (
            base_total + tip_total + delay_total + compliance_total + bonus_total
            + loyalty_total + customer_rating_total - malus_total - atm_deduction_total - other_expense_total - salary_advance_total
        )
        order_total = int(route_detail.get("Rendelések", pd.Series(dtype=float)).sum())
        route_total = int(len(route_detail))
        monthly_bonus_malus_effect = (
            imported_bonus_total + float(adjustment_totals.get("bonus", 0)) + loyalty_total
            - imported_malus_total - float(adjustment_totals.get("malus", 0))
        )
        manual_other_total = float(adjustment_totals.get("other_expense", 0))

        # The profile cards are a direct projection of the persisted central
        # settlement row.  Route detail is drill-down only and must never
        # overwrite the authoritative summary amounts.
        persisted_summary = load_courier_settlement_summary(session_id)
        if not persisted_summary.empty:
            summary_match = persisted_summary[
                persisted_summary.get("courier_id", pd.Series("", index=persisted_summary.index))
                .map(_courier_id_key).eq(_courier_id_key(courier_id))
            ]
            if summary_match.empty and "driver_name" in persisted_summary:
                summary_match = persisted_summary[
                    persisted_summary["driver_name"].map(_courier_match_key).eq(_courier_match_key(row["Futár"]))
                ]
            if not summary_match.empty:
                persisted = summary_match.iloc[0]
                amount = lambda field: parse_huf_value(persisted.get(field))
                base_total = amount("courier_base_rate_huf")
                tip_total = amount("tip_huf")
                delay_total = amount("delay_bonus_huf")
                compliance_total = amount("compliance_bonus_huf")
                route_other_bonus_total = amount("other_route_bonus_huf")
                imported_bonus_total = amount("imported_bonus_huf")
                order_total = int(amount("order_count"))
                route_total = int(amount("route_count"))

        manual_bonus_total = float(adjustment_totals.get("bonus", 0.0))
        manual_customer_rating_total = float(adjustment_totals.get("customer_rating", 0.0))
        loyalty_total = parse_huf_value(row.get("Lojalitás"))
        imported_customer_rating_total = parse_huf_value(row.get("Ügyfélértékelés"))
        manual_malus_total = float(adjustment_totals.get("malus", 0.0))
        manual_atm_total = float(adjustment_totals.get("atm_deduction", 0.0))
        manual_other_total = float(adjustment_totals.get("other_expense", 0.0))
        bonus_total = route_other_bonus_total + imported_bonus_total + manual_bonus_total
        customer_rating_total = imported_customer_rating_total + manual_customer_rating_total
        malus_total = imported_malus_total + manual_malus_total
        atm_deduction_total = imported_atm_total + manual_atm_total
        other_expense_total = manual_other_total
        salary_advance_total = parse_huf_value(row.get("Fizetés előleg"))
        payable_total = (
            base_total + tip_total + delay_total + compliance_total + bonus_total
            + loyalty_total + customer_rating_total - malus_total - atm_deduction_total - other_expense_total - salary_advance_total
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
        payable_total = parse_huf_value(reserve_month.get("payable_after_insurance_huf"))
        monthly_closure = load_courier_monthly_closure(courier_id, period_start, period_end)
        closure_done = str(monthly_closure.get("status") or "").casefold() == "done"
        monthly_bonus_malus_effect = (
            imported_bonus_total + manual_bonus_total + loyalty_total + imported_customer_rating_total + manual_customer_rating_total
            - imported_malus_total - manual_malus_total
        )

        pdf_bytes = build_settlement_pdf(
            {"name": row["Futár"], "id": courier_id, "branch": row["Branch"], "warehouse": row["Raktár"], "status": row["Státusz"]},
            route_breakdown.to_dict("records"),
            {"base": base_total, "tip": tip_total, "bonus": bonus_total + loyalty_total, "malus": malus_total, "atm": atm_deduction_total, "other": other_expense_total + salary_advance_total, "customer_rating": customer_rating_total, "payable": payable_total},
        )
        tig_bytes = build_demo_preview_pdf(
            f"TIG - {row['Futár']}",
            f"Courier ID: {courier_id} | Időszak: {period_start} - {period_end} | Fizetendő: {format_huf(payable_total)}",
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
        doc_a, doc_b = st.columns([0.18, 0.18])
        doc_a.download_button("Elszámolás PDF", data=pdf_bytes, file_name=f"jitt_elszamolas_{courier_id}.pdf", mime="application/pdf", use_container_width=True, key=f"finance_top_settlement_pdf_{courier_id}")
        doc_b.download_button("TIG PDF", data=tig_bytes, file_name=f"tig_{courier_id}.pdf", mime="application/pdf", use_container_width=True, key=f"finance_top_tig_pdf_{courier_id}")

        kpi_items = [
            ("Rendelés", f"{order_total:,}".replace(",", " "), ""),
            ("Kör", str(route_total), ""),
            ("Késedelmi díj", format_huf(delay_total), ""),
            ("Túramegfelelés", format_huf(compliance_total), ""),
            ("Lojalitás", format_huf(loyalty_total), ""),
            ("Ügyfélértékelési bónusz", format_huf(customer_rating_total), ""),
            ("Fizetendő", format_huf(payable_total), "payable"),
            ("Levonás / plusz", format_huf(-other_expense_total), ""),
            ("Havi bónusz/málusz", format_huf(monthly_bonus_malus_effect), ""),
            ("ATM hatás", format_huf(-atm_deduction_total), ""),
            ("Fizetés előleg", format_huf(-salary_advance_total), ""),
            ("Céltartalék 10%", format_huf(-reserve_addition_total), ""),
            ("Biztosítási díj", format_huf(-insurance_fee_total), ""),
            ("CT státusz", "Done" if reserve_month_status == "done" else "In progress", ""),
        ]

        def finance_detail_frame(detail_label: str) -> pd.DataFrame:
            if detail_label == "Késedelmi díj":
                return build_amount_drilldown(route_detail, "Késedelmi díj")
            if detail_label == "Túramegfelelés":
                return build_amount_drilldown(route_detail, "Túramegfelelés")
            if detail_label == "Lojalitás":
                unit_amount = loyalty_total / route_total if route_total else 0
                return pd.DataFrame([{
                    "Tétel": "Lojalitás",
                    "Darab": route_total,
                    "Egységösszeg": unit_amount,
                    "Összeg": loyalty_total,
                    "Számítás": f"{route_total} x {format_huf(unit_amount)}" if unit_amount else format_huf(loyalty_total),
                }])
            if detail_label == "Ügyfélértékelési bónusz":
                unit_amount = customer_rating_total / route_total if route_total else 0
                return pd.DataFrame([{
                    "Tétel": "Ügyfélértékelési bónusz",
                    "Darab": route_total,
                    "Egységösszeg": unit_amount,
                    "Összeg": customer_rating_total,
                    "Számítás": f"{route_total} x {format_huf(unit_amount)}" if unit_amount else format_huf(customer_rating_total),
                }])
            if detail_label == "Havi bónusz/málusz":
                return pd.DataFrame([
                    {"Tétel": "Importált bónusz", "Összeg": imported_bonus_total},
                    {"Tétel": "Manuális bónusz", "Összeg": manual_bonus_total},
                    {"Tétel": "Lojalitás", "Összeg": loyalty_total},
                    {"Tétel": "Ügyfélértékelés", "Összeg": customer_rating_total},
                    {"Tétel": "Importált málusz", "Összeg": -imported_malus_total},
                    {"Tétel": "Manuális málusz", "Összeg": -manual_malus_total},
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
            "Késedelmi díj", "Túramegfelelés", "Lojalitás", "Ügyfélértékelési bónusz",
            "Havi bónusz/málusz", "ATM hatás", "Fizetés előleg", "Céltartalék 10%",
        }

        def render_finance_kpi(label: str, value: str, css_class: str) -> str:
            card = (
                f'<div class="finance-kpi {css_class}">'
                f'<div class="finance-kpi-label">{html.escape(label)}</div>'
                f'<div class="finance-kpi-value">{html.escape(value)}</div>'
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
                render_finance_kpi(label, value, css_class)
                for label, value, css_class in kpi_items
            )
            + "</div></div>",
            unsafe_allow_html=True,
        )

        payable_sources = pd.DataFrame([
            {"Művelet": "+", "Tétel": "Alapdíj", "Összeg": base_total},
            {"Művelet": "+", "Tétel": "Borravaló", "Összeg": tip_total},
            {"Művelet": "+", "Tétel": "Késedelmi díj", "Összeg": delay_total},
            {"Művelet": "+", "Tétel": "Túramegfelelés", "Összeg": compliance_total},
            {"Művelet": "+", "Tétel": "Bónuszok", "Összeg": bonus_total},
            {"Művelet": "+", "Tétel": "Lojalitás", "Összeg": loyalty_total},
            {"Művelet": "+", "Tétel": "Ügyfélértékelés", "Összeg": customer_rating_total},
            {"Művelet": "-", "Tétel": "Máluszok", "Összeg": malus_total},
            {"Művelet": "-", "Tétel": "ATM levonás", "Összeg": atm_deduction_total},
            {"Művelet": "-", "Tétel": "Egyéb kiadás", "Összeg": other_expense_total},
            {"Művelet": "-", "Tétel": "Fizetés előleg", "Összeg": salary_advance_total},
            {"Művelet": "-", "Tétel": "Céltartalék 10%", "Összeg": reserve_addition_total},
            {"Művelet": "-", "Tétel": "Biztosítási díj", "Összeg": insurance_fee_total},
            {"Művelet": "=", "Tétel": "Kifizetendő", "Összeg": payable_total},
        ])
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
            "malus": "Málusz",
            "atm_deduction": "ATM levonás",
            "other_expense": "Egyéb kiadás",
            "customer_rating": "Ügyfélértékelés",
        }
        adjustment_type_values = {label: key for key, label in adjustment_type_labels.items()}
        editor_columns = ["id", "Típus", "Összeg", "Megjegyzés", "Érvényes ettől", "Érvényes eddig", "Törlés"]
        if adjustments.empty:
            editor_df = pd.DataFrame(
                [
                    {"id": "", "Típus": "Bónusz", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Ügyfélértékelés", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
                    {"id": "", "Típus": "Málusz", "Összeg": 0, "Megjegyzés": "", "Érvényes ettől": period_start, "Érvényes eddig": period_end, "Törlés": False},
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
                    st.success(f"{saved_changes} módosítás mentve és naplózva.")
                    st.rerun()
                else:
                    st.info("Nem volt mentendő változás.")
            except Exception as exc:
                st.error(f"A tételek nem menthetők. Futtasd le az adjustment edit migrációt. Részlet: {exc}")

        if reset_clicked:
            try:
                reset_courier_adjustments(session_id, courier_id, period_start, period_end)
                st.rerun()
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
                requested_amount = st.number_input("Igényelt összeg (Ft)", min_value=0, step=1000, value=0, key=f"salary_advance_amount_{courier_id}")
                installment_months = st.number_input("Havi bontás (hónap)", min_value=1, max_value=60, step=1, value=1, key=f"salary_advance_months_{courier_id}")
                start_date = st.date_input("Kezdő dátum", value=period_start, key=f"salary_advance_start_{courier_id}")
                note = st.text_area("Megjegyzés", key=f"salary_advance_note_{courier_id}")
                preview_amounts = salary_advance_installment_amounts(requested_amount, int(installment_months))
                preview_monthly = preview_amounts[0] if preview_amounts else 0
                st.info(f"Havi levonás: {format_huf(preview_monthly)}")
                save_advance = st.form_submit_button("Fizetés előleg mentése", type="primary", use_container_width=True)
            if save_advance:
                if requested_amount <= 0:
                    st.error("Az igényelt összegnek pozitívnak kell lennie.")
                else:
                    try:
                        create_salary_advance_plan(courier_id, courier_name, requested_amount, int(installment_months), start_date, note)
                        st.success("A fizetés előleg havi részletei létrejöttek.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"A fizetés előleg nem menthető. Futtasd le az előleg DB migrációt. Részlet: {exc}")

        with form_right:
            history = load_courier_salary_advance_history(courier_id)
            st.markdown('<div class="settlement-profile-shell"><div class="finance-panel-title">Részletek</div></div>', unsafe_allow_html=True)
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

    if selected_menu == "Útvonalak":
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
        issue_rows = build_route_issue_rows(route_detail, stories, order_details, reviews, courier_id)

        open_count = 0 if reviews.empty or "status" not in reviews.columns else int(reviews["status"].isin(["Vizsgálat", "Elfogadva"]).sum())
        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Problémás sor", int(len(issue_rows)))
        metric2.metric("Késő rendelés", int((issue_rows.get("Probléma", pd.Series(dtype=str)) == "Késő rendelés").sum()))
        metric3.metric("Sorba állási gond", int(issue_rows.get("Probléma", pd.Series(dtype=str)).astype(str).str.contains("sorba", case=False, na=False).sum()))
        metric4.metric("Aktív reklamáció", open_count)

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
                    "Rendelések", "Késedelmi díj", "Túramegfelelés", "Story",
                ],
                column_order=[
                    "Dátum", "Route ID", "Order ID", "Probléma", "Eltérés perc",
                    "Rendelések", "Késedelmi díj", "Túramegfelelés", "Státusz", "Megjegyzés", "Story",
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
                "Naptípus", "Rendelések", "Alapdíj", "Borravaló",
                "Késedelmi díj", "Túramegfelelés", "DB státusz",
            ]
            display_columns = [column for column in display_columns if column in route_view.columns]
            for amount_column in ["Alapdíj", "Borravaló", "Késedelmi díj", "Túramegfelelés", "Egyéb bónusz"]:
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
        docs = pd.DataFrame(
            [
                {"Típus": "Elszámolás", "Fájl": "elszamolas_2026_07.pdf", "Feltöltve": "2026-07-10 09:12", "Státusz": "Aktív"},
                {"Típus": "TIG", "Fájl": "tig_2026_07.pdf", "Feltöltve": "2026-07-11 10:35", "Státusz": "Aktív"},
                {"Típus": "Számla", "Fájl": "szamla_2026_07.pdf", "Feltöltve": "2026-07-12 14:02", "Státusz": "Ellenőrzés alatt"},
                {"Típus": "Szerződés", "Fájl": "szerzodes.pdf", "Feltöltve": "2026-01-15 08:20", "Státusz": "Aktív"},
            ]
        )
        st.dataframe(docs, use_container_width=True, hide_index=True)

        doc1, doc2, doc3 = st.columns(3)
        doc1.button("Megnyitás", use_container_width=True, key=f"ui_doc_open_{courier_id}")
        doc2.button("Letöltés", use_container_width=True, key=f"ui_doc_download_{courier_id}")
        doc3.file_uploader(
            "Új dokumentum feltöltése",
            type=["pdf", "png", "jpg", "jpeg"],
            key=f"ui_doc_upload_{courier_id}",
        )

    if selected_menu == "Reklamációk":
        st.markdown("#### Reklamációk")
        complaint_list, complaint_editor = st.columns([1.35, 0.65])

        with complaint_list:
            complaint_demo = pd.DataFrame(
                [
                    {"Dátum": "2026-07-05", "Típus": "Elszámolás", "Tárgy": "Bónusz eltérés", "Státusz": "Nyitott"},
                    {"Dátum": "2026-06-18", "Típus": "TIG", "Tárgy": "Cím javítás", "Státusz": "Lezárt"},
                ]
            )
            st.dataframe(complaint_demo, use_container_width=True, hide_index=True)

        with complaint_editor:
            st.markdown("##### Új reklamáció")
            st.selectbox(
                "Típus",
                ["Elszámolás", "TIG", "Számla", "Egyéb"],
                key=f"ui_complaint_type_{courier_id}",
            )
            st.text_input("Tárgy", key=f"ui_complaint_subject_{courier_id}")
            st.text_area("Leírás", key=f"ui_complaint_text_{courier_id}")
            st.button(
                "Reklamáció mentése",
                use_container_width=True,
                key=f"ui_complaint_save_{courier_id}",
                help="Csak dizájn, még nem ment adatot.",
            )

    if selected_menu == "Profil":
        profile = load_courier_profile(courier_id)
        reserve_status = load_target_reserve_status(courier_id, str(row["Futár"]))
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
            current_work_start = pd.to_datetime(profile.get("work_start_date"), errors="coerce")
            work_start_date = st.date_input(
                "Munkakezdés dátuma",
                value=current_work_start.date() if pd.notna(current_work_start) else date.today(),
                disabled=not is_editing,
                key=f"ui_profile_work_start_{courier_id}",
            )

        with profile2:
            st.text_input("Számítás módja", value=str(row["Számítás módja"]), disabled=True, key=f"ui_profile_calc_{courier_id}")
            company_name = st.text_input("Vállalkozás neve", value=str(profile.get("company_name") or ""), disabled=not is_editing, key=f"ui_profile_company_{courier_id}")
            company_address = st.text_input("Vállalkozás címe", value=str(profile.get("company_address") or ""), disabled=not is_editing, key=f"ui_profile_company_address_{courier_id}")
            tax_number = st.text_input("Adószám", value=str(profile.get("tax_number") or ""), disabled=not is_editing, key=f"ui_profile_tax_{courier_id}")
            bank_account_number = st.text_input("Bankszámlaszám", value=str(profile.get("bank_account_number") or ""), disabled=not is_editing, key=f"ui_profile_bank_{courier_id}")
            vat_status = st.text_input("ÁFA státusz", value=str(profile.get("vat_status") or ""), disabled=not is_editing, key=f"ui_profile_vat_status_{courier_id}")
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
            new_fields = {"courier_name": courier_name, "phone_number": phone_number, "email": email, "warehouse_name": warehouse_name, "billing_email": billing_email, "work_start_date": work_start_date.isoformat() if work_start_date else "", "company_name": company_name, "company_address": company_address, "tax_number": tax_number, "bank_account_number": bank_account_number, "vat_status": vat_status}
            changes = {field: {"old": str(profile.get(field) or ""), "new": str(value or "")} for field, value in new_fields.items() if str(profile.get(field) or "") != str(value or "")}
            try:
                if changes:
                    update_courier_master_profile(courier_id, new_fields)
                    log_profile_change(courier_id, changes)
                st.session_state[edit_key] = False
                keep_courier_menu("Profil")
                load_courier_profile.clear()
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


def build_demo_preview_pdf(title: str, subtitle: str) -> bytes:
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
            f"{title}\n\n{subtitle}\n\nDesigner előnézet."
        ).encode("utf-8")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, height - 70, title)

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, height - 100, subtitle)
    pdf.drawString(50, height - 130, "Designer előnézet – nincs mögötte üzleti logika.")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, height - 180, "Minta dokumentum")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, height - 210, "Futár: Kiss Péter")
    pdf.drawString(50, height - 230, "Courier ID: 7486")
    pdf.drawString(50, height - 250, "Branch: Kifli")
    pdf.drawString(50, height - 270, "Összeg: 468 500 Ft")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_excel_export(df: pd.DataFrame) -> bytes:
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Elszámolások")
    return output.getvalue()

def show_new_settlement_page() -> None:
    apply_design()
    requested_calculation_mode = st.session_state.pop("courier_requested_calculation_mode", None)
    if requested_calculation_mode in {"API", "Excel"}:
        st.session_state["new_calculation_mode"] = requested_calculation_mode
    selected_calculation_mode = st.session_state.get("new_calculation_mode", "API")
    selected_month_label = st.session_state.get("new_month") or month_options()[0]
    selected_warehouse_label = st.session_state.get("new_warehouse", "Összes")
    selected_period_start = parse_month_option(selected_month_label)
    if str(selected_calculation_mode or "API").strip().casefold() == "excel":
        import_session_id = (
            st.session_state.get("settlement_excel_session_id")
            or load_latest_excel_jit_session_id()
        )
        balance_period_start, balance_period_end = load_settlement_month(import_session_id)
    else:
        balance_period_start = selected_period_start
        _, balance_period_end = month_bounds(balance_period_start)
        api_session_id = load_latest_api_jit_session_id(balance_period_start, selected_warehouse_label)
        import_session_id = api_session_id
        if api_session_id:
            import_session_id = api_session_id
    data = build_settlement_working_data(selected_calculation_mode, import_session_id, balance_period_start, selected_warehouse_label)
    data = apply_imported_balance_components(data, import_session_id)
    data = apply_loyalty_bonus(data, balance_period_start, balance_period_end, import_session_id)
    data = apply_customer_rating_bonus(data, balance_period_start, balance_period_end)
    data = apply_manual_balance_adjustments(data, balance_period_start, balance_period_end)
    data = apply_salary_advance_deduction(data, balance_period_start, balance_period_end)
    data = recompute_payable_total(data)
    data = apply_monthly_closure_status(data, balance_period_start, balance_period_end)

    with st.sidebar:
        st.markdown("## Elszámolás")
        st.caption("Szűrés és műveletek")
        selected_month=st.selectbox("Elszámolási hónap",month_options(),key="new_month")
        branch=st.selectbox("Branch",["Összes"]+sorted(data["Branch"].unique().tolist()),key="new_branch")
        calculation_mode=st.selectbox("Számítás módja",["API","Excel","Összes"],key="new_calculation_mode")
        warehouse=st.selectbox("Raktár",["Összes"]+sorted(data["Raktár"].unique().tolist()),key="new_warehouse")
        status=st.selectbox("Elszámolás állapota",["Összes","Előkészítve","Ellenőrzés alatt","Jóváhagyva"],key="new_status")
        search=st.text_input("Futár keresése",placeholder="Név vagy azonosító",key="new_search")
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

        import_session_id = st.session_state.get("settlement_import_session_id")
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
                    try:
                        recalculate_excel_base_rates(get_db(), result["session_id"])
                        st.session_state["settlement_base_rate_summary"] = load_excel_courier_base_rates(
                            result["session_id"],
                            parameter_revision,
                        )
                    except BaseException:
                        st.session_state["settlement_base_rate_summary"] = pd.DataFrame()

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

        import_session_id = st.session_state.get("settlement_import_session_id")

        if excel_action_check.button(
            "SQL ellenőrzés",
            use_container_width=True,
            disabled=not import_session_id,
            key="check_excel_import_sql",
            help="A settlement.vw_excel_preview nézetből olvassa vissza az importot.",
        ):
            try:
                preview_df = get_import_preview(
                    get_db(),
                    import_session_id,
                    limit=200,
                )
                st.session_state["settlement_import_preview"] = preview_df

                if preview_df.empty:
                    st.warning("A SQL ellenőrzés lefutott, de nincs visszaolvasott sor.")
                else:
                    st.success(f"SQL ellenőrzés OK: {len(preview_df)} sor visszaolvasva.")

            except Exception as exc:
                st.error(f"SQL ellenőrzés sikertelen: {exc}")

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
        rating_preview = pd.DataFrame()
        if uploaded_rating_excel is not None:
            try:
                rating_preview = parse_customer_rating_excel(
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
        query=search.strip()
        base_filtered=base_filtered[
            base_filtered["Futár"].str.contains(query,case=False,na=False)
            | base_filtered["Courier ID"].astype(str).str.contains(query,case=False,na=False)
        ]

    active_workflow_filter = st.session_state.get("dashboard_status_filter")
    filtered = base_filtered.copy()
    if active_workflow_filter:
        filtered = filtered[filtered["Státusz"] == active_workflow_filter]

    st.session_state["current_filtered_data"]=filtered.copy()

    total_gross=int(filtered["Nettó bevétel"].sum()) if not filtered.empty else 0
    total_deduction=int(filtered["Levonás"].sum()) if not filtered.empty else 0
    total_payable=int(filtered["Kifizetendő"].sum()) if not filtered.empty else 0

    st.markdown(
        f"""
        <div class="premium-hero">
          <div class="hero-left"><div class="badge">ÚJ MODUL</div><h1>Új Elszámolási oldal</h1><p>Gyors, átlátható és biztonságos futárelszámolási felület.</p></div>
          <div class="month-pill"><div class="label">Elszámolási hónap</div><div class="value">{html.escape(selected_month)}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    total_bonus = int(filtered["Bónusz"].sum()) if not filtered.empty else 0
    total_tip = int(filtered["Borravaló"].sum()) if not filtered.empty else 0

    st.markdown(
        f"""
        <div class="summary-donut-grid">
          <div class="summary-donut-card">
            <div>
              <div class="summary-donut-title">Bónuszok összesen</div>
              <div class="summary-donut-value">{format_huf(total_bonus)}</div>
              <div class="summary-donut-note">{html.escape(selected_month)}</div>
            </div>
            <div class="summary-donut summary-donut-primary">
              <div class="summary-donut-center"><strong>{total_bonus / 1_000_000:.1f} M</strong><span>Ft</span></div>
            </div>
          </div>

          <div class="summary-donut-card">
            <div>
              <div class="summary-donut-title">Borravaló összesen</div>
              <div class="summary-donut-value">{format_huf(total_tip)}</div>
              <div class="summary-donut-note">{html.escape(selected_month)}</div>
            </div>
            <div class="summary-donut summary-donut-secondary">
              <div class="summary-donut-center"><strong>{total_tip / 1_000_000:.1f} M</strong><span>Ft</span></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Áttekintés</div>',unsafe_allow_html=True)

    workflow_cards = [
        ("Elszámolásra vár", "Még nem készült elszámolás", "🔵"),
        ("TIG-re vár", "Még nem készült TIG", "🟣"),
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
    show_new_settlement_page()
