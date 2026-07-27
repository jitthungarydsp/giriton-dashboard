import traceback
import unicodedata
from datetime import date, timedelta
from streamlit_autorefresh import st_autorefresh

import pandas as pd
import streamlit as st
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


/* --- Premium futárprofil v1 (vizuális prototípus) --- */
.courier-shell {
    --cp-green:#1FA64A;
    --cp-green-dark:#157A37;
    --cp-ink:#17351F;
    --cp-muted:#6D7F71;
    --cp-border:#DDE9E0;
    --cp-soft:#F4FBF5;
    --cp-danger:#D64550;
    --cp-warning:#E59B16;
}
.courier-cover {
    position:relative;
    overflow:hidden;
    border-radius:26px;
    padding:26px 28px;
    margin-bottom:16px;
    background:
      radial-gradient(circle at 90% 10%, rgba(31,166,74,.22), transparent 32%),
      linear-gradient(135deg,#102A18 0%,#1B4A29 58%,#1FA64A 145%);
    color:white;
    box-shadow:0 22px 60px rgba(18,58,31,.20);
}
.courier-cover::after {
    content:"";
    position:absolute;
    width:230px;height:230px;border-radius:50%;
    right:-80px;bottom:-130px;
    border:1px solid rgba(255,255,255,.18);
    box-shadow:0 0 0 34px rgba(255,255,255,.05),0 0 0 70px rgba(255,255,255,.03);
}
.courier-cover-top {display:flex;justify-content:space-between;align-items:center;gap:20px;position:relative;z-index:1;}
.courier-identity {display:flex;align-items:center;gap:18px;min-width:0;}
.courier-avatar {
    width:78px;height:78px;border-radius:24px;display:grid;place-items:center;
    background:linear-gradient(145deg,#FFFFFF,#DFF5E6);color:#16713A;
    font-size:27px;font-weight:900;letter-spacing:.03em;
    border:4px solid rgba(255,255,255,.18);box-shadow:0 12px 30px rgba(0,0,0,.18);
}
.courier-name-xl {font-size:30px;font-weight:900;line-height:1.08;margin:0 0 7px;}
.courier-meta {display:flex;gap:8px;flex-wrap:wrap;color:rgba(255,255,255,.78);font-size:13px;}
.courier-meta span {padding-right:9px;border-right:1px solid rgba(255,255,255,.20);}
.courier-meta span:last-child {border-right:none;}
.courier-badges {display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;}
.courier-badge {display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border-radius:999px;font-size:12px;font-weight:800;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.16);backdrop-filter:blur(8px);}
.courier-badge.light {background:#fff;color:#174626;border-color:#fff;}
.courier-badge .dot {width:8px;height:8px;border-radius:50%;background:#58E887;box-shadow:0 0 0 4px rgba(88,232,135,.15);}
.courier-cover-bottom {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:22px;position:relative;z-index:1;}
.cover-stat {padding:13px 14px;border-radius:16px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);}
.cover-stat .label {font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:rgba(255,255,255,.64);font-weight:800;}
.cover-stat .value {font-size:20px;font-weight:900;margin-top:3px;}
.profile-nav-hint {font-size:12px;color:#77907E;margin:-4px 0 12px;}
.profile-grid {display:grid;grid-template-columns:1.35fr .65fr;gap:16px;align-items:start;}
.profile-card {background:#fff;border:1px solid var(--cp-border);border-radius:22px;padding:20px;box-shadow:0 10px 32px rgba(23,53,31,.06);}
.profile-card + .profile-card {margin-top:14px;}
.profile-card-head {display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:17px;}
.profile-card-title {font-size:17px;font-weight:900;color:var(--cp-ink);}
.profile-card-sub {font-size:12px;color:var(--cp-muted);margin-top:3px;}
.money-hero {padding:20px;border-radius:20px;background:linear-gradient(135deg,#F1FBF4,#FFFFFF);border:1px solid #D5F0DE;}
.money-hero .eyebrow {font-size:12px;color:var(--cp-muted);font-weight:800;text-transform:uppercase;letter-spacing:.05em;}
.money-hero .amount {font-size:38px;line-height:1.05;color:var(--cp-ink);font-weight:950;margin:7px 0 5px;}
.money-hero .delta {font-size:13px;color:#168343;font-weight:800;}
.finance-columns {display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px;}
.finance-block {border:1px solid var(--cp-border);border-radius:18px;padding:15px 16px;background:#fff;}
.finance-block.income {border-top:4px solid #1FA64A;}
.finance-block.outcome {border-top:4px solid #E45B64;}
.finance-title {font-size:13px;font-weight:900;color:var(--cp-ink);margin-bottom:10px;}
.ledger-row {display:flex;justify-content:space-between;gap:16px;padding:9px 0;border-bottom:1px dashed #E7EFE9;font-size:13px;}
.ledger-row:last-child {border-bottom:none;}
.ledger-row span:first-child {color:var(--cp-muted);}
.ledger-row strong {color:var(--cp-ink);font-variant-numeric:tabular-nums;}
.kpi-mini-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}
.kpi-mini {border:1px solid var(--cp-border);border-radius:17px;padding:15px;background:linear-gradient(180deg,#fff,#FBFDFC);}
.kpi-mini .icon {font-size:18px;margin-bottom:10px;}
.kpi-mini .value {font-size:20px;font-weight:950;color:var(--cp-ink);}
.kpi-mini .label {font-size:11px;color:var(--cp-muted);margin-top:4px;font-weight:700;}
.quick-grid {display:grid;grid-template-columns:1fr 1fr;gap:9px;}
.quick-action {border:1px solid var(--cp-border);border-radius:16px;padding:14px;background:#fff;min-height:92px;}
.quick-action .qa-icon {font-size:20px;}
.quick-action .qa-title {font-size:13px;font-weight:900;color:var(--cp-ink);margin-top:8px;}
.quick-action .qa-sub {font-size:11px;color:var(--cp-muted);margin-top:3px;}
.chart-wrap {padding-top:3px;}
.chart-bars {height:165px;display:flex;align-items:flex-end;gap:12px;padding:16px 4px 2px;border-bottom:1px solid var(--cp-border);}
.chart-col {flex:1;text-align:center;min-width:0;}
.chart-bar {width:100%;max-width:38px;margin:0 auto;border-radius:9px 9px 3px 3px;background:linear-gradient(180deg,#4FCB76,#1A9446);box-shadow:0 8px 18px rgba(31,166,74,.16);}
.chart-col.active .chart-bar {background:linear-gradient(180deg,#1B4A29,#102A18);}
.chart-label {font-size:10px;color:var(--cp-muted);margin-top:7px;white-space:nowrap;}
.chart-value {font-size:10px;color:var(--cp-ink);font-weight:800;margin-bottom:5px;}
.activity-item {display:flex;gap:12px;padding:12px 0;border-bottom:1px solid #EDF2EE;}
.activity-item:last-child {border-bottom:none;}
.activity-dot {width:10px;height:10px;border-radius:50%;background:#1FA64A;margin-top:5px;box-shadow:0 0 0 5px #E8F7ED;flex:0 0 auto;}
.activity-title {font-size:13px;font-weight:850;color:var(--cp-ink);}
.activity-meta {font-size:11px;color:var(--cp-muted);margin-top:3px;}
.route-card {display:grid;grid-template-columns:1.2fr .8fr .7fr .9fr auto;gap:12px;align-items:center;border:1px solid var(--cp-border);border-radius:17px;padding:14px 16px;margin-bottom:9px;background:#fff;}
.route-card:hover {border-color:#9DD8AF;box-shadow:0 10px 24px rgba(31,166,74,.08);}
.route-id {font-size:13px;font-weight:900;color:var(--cp-ink);}
.route-sub {font-size:11px;color:var(--cp-muted);margin-top:3px;}
.route-pill {display:inline-flex;padding:6px 9px;border-radius:999px;background:#EDF8F0;color:#16723A;font-size:11px;font-weight:800;}
.route-arrow {width:30px;height:30px;border-radius:10px;background:#F1F7F3;display:grid;place-items:center;color:#27623A;font-weight:900;}
.empty-design-note {border:1px dashed #B8D9C1;background:#F7FCF8;border-radius:18px;padding:16px;color:#496550;font-size:13px;}
@media (max-width:1050px) {
  .profile-grid {grid-template-columns:1fr;}
  .courier-cover-top {align-items:flex-start;flex-direction:column;}
  .courier-badges {justify-content:flex-start;}
}
@media (max-width:760px) {
  .courier-cover {padding:20px;border-radius:20px;}
  .courier-cover-bottom {grid-template-columns:1fr 1fr;}
  .finance-columns,.kpi-mini-grid {grid-template-columns:1fr;}
  .route-card {grid-template-columns:1fr 1fr;}
  .route-arrow {display:none;}
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
def load_courier_master() -> pd.DataFrame:
    response = (
        get_db()
        .schema("public")
        .table("courier_master")
        .select("courier_id,courier_name,warehouse_name")
        .order("courier_name")
        .execute()
    )

    rows = response.data or []
    columns = [
        "Courier ID", "Futár", "Branch", "Számítás módja",
        "Raktár", "Státusz", "Nettó bevétel", "Bónusz",
        "Borravaló", "Levonás", "Kifizetendő", "Előző havi összeg",
        "KPI",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows).rename(columns={
        "courier_id": "Courier ID",
        "courier_name": "Futár",
        "warehouse_name": "Raktár",
    })

    df["Courier ID"] = df["Courier ID"].astype(str)
    df["Futár"] = df["Futár"].fillna("Ismeretlen futár")
    df["Branch"] = "JIT"
    df["Számítás módja"] = "Excel"
    df["Raktár"] = df["Raktár"].fillna("BUD1")

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
def load_driver_dashboard(session_id: str | None = None) -> pd.DataFrame:
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
    df["Számítás módja"] = "Excel"
    df["Státusz"] = "Előkészítve"
    df["Előző havi összeg"] = 0.0

    return df


@st.cache_data(show_spinner=False, ttl=60)
def load_excel_courier_base_rates(session_id: str, parameter_revision: int = 0) -> pd.DataFrame:
    """Read persisted database-calculated courier base fees."""
    columns = [
        "Futár", "Vállalkozói alapdíj", "Nettó bevétel", "Borravaló",
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
    for column in columns[1:]:
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
    result["_courier_lookup"] = result["Futár"].map(_courier_match_key)
    calculated = calculated.copy()
    calculated["_courier_lookup"] = calculated["Futár"].map(_courier_match_key)
    calculated = (
        calculated.groupby("_courier_lookup", as_index=False)[
            [
                "Nettó bevétel", "Vállalkozói alapdíj", "Borravaló",
                "Rendszerbónusz", "Számolt túrák", "Nem számolt túrák",
            ]
        ]
        .sum()
    )
    amount_by_courier = calculated.set_index("_courier_lookup")["Nettó bevétel"]
    company_amount_by_courier = calculated.set_index("_courier_lookup")["Vállalkozói alapdíj"]
    tip_by_courier = calculated.set_index("_courier_lookup")["Borravaló"]
    system_bonus_by_courier = calculated.set_index("_courier_lookup")["Rendszerbónusz"]
    matched_routes = calculated.set_index("_courier_lookup")["Számolt túrák"]
    unmatched_routes = calculated.set_index("_courier_lookup")["Nem számolt túrák"]
    calculated_keys = set(amount_by_courier.index)
    resolved_lookup = result["_courier_lookup"].map(
        lambda key: _resolve_courier_lookup_key(key, calculated_keys)
    )
    result["Nettó bevétel"] = resolved_lookup.map(amount_by_courier).fillna(0.0)
    result["Vállalkozói alapdíj"] = resolved_lookup.map(company_amount_by_courier).fillna(0.0)
    result["Borravaló"] = resolved_lookup.map(tip_by_courier).fillna(0.0)
    result["Bónusz"] = resolved_lookup.map(system_bonus_by_courier).fillna(0.0)
    result["Számolt túrák"] = resolved_lookup.map(matched_routes).fillna(0).astype(int)
    result["Nem számolt túrák"] = resolved_lookup.map(unmatched_routes).fillna(0).astype(int)
    return result.drop(columns="_courier_lookup")


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
    return f"{value:,.0f} Ft".replace(",", " ")


def parse_huf_value(value: object) -> float:
    """Accept numeric DB values and formatted Hungarian money strings."""
    if value is None or value == "":
        return 0.0
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


def status_meta(status: str) -> tuple[str,str]:
    mapping={
        "Előkészítve":("status-red","led-red"),
        "Ellenőrzés alatt":("status-yellow","led-yellow"),
        "Jóváhagyva":("status-green","led-green"),
        "Elszámolásra vár":("status-blue","led-blue"),
        "TIG-re vár":("status-purple","led-purple"),
        "Bejelentések":("status-orange","led-orange"),
        "Kifizetésre vár":("status-green","led-green"),
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
def load_courier_route_detail(courier_id: str, courier_name: str, session_id: str | None) -> pd.DataFrame:
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
        return pd.DataFrame(columns=columns)
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
    """A futár aktuális elszámolási adatainak prémium nézete.

    Az elszámolási összegek elsődleges forrása a
    ``settlement.courier_settlement_summary`` tábla. A főoldal és az import
    működése változatlan marad.
    """
    courier_id = str(st.session_state.get("selected_courier_id") or "")
    data = st.session_state.get("current_filtered_data")
    if not isinstance(data, pd.DataFrame) or data.empty:
        data = load_courier_master()

    match = data[data["Courier ID"].astype(str).map(_courier_id_key) == _courier_id_key(courier_id)]
    if match.empty:
        st.warning("A futár nem található.")
        return

    row = match.iloc[0]
    courier_name = str(row.get("Futár") or "Ismeretlen futár")
    initials = "".join(part[0] for part in courier_name.split()[:2] if part).upper() or "FT"
    session_id = st.session_state.get("settlement_import_session_id") or load_latest_jit_session_id()

    summary_data = load_courier_settlement_summary(session_id)
    summary_row: dict[str, object] = {}
    if not summary_data.empty:
        by_id = summary_data[
            summary_data.get("courier_id", pd.Series("", index=summary_data.index))
            .map(_courier_id_key)
            .eq(_courier_id_key(courier_id))
        ]
        if by_id.empty and "driver_name" in summary_data.columns:
            by_name = summary_data[
                summary_data["driver_name"].map(_courier_match_key).eq(_courier_match_key(courier_name))
            ]
            if not by_name.empty:
                by_id = by_name
        if not by_id.empty:
            summary_row = by_id.iloc[0].to_dict()

    def summary_amount(column: str, fallback_column: str | None = None) -> float:
        if column in summary_row:
            return parse_huf_value(summary_row.get(column))
        if fallback_column:
            return parse_huf_value(row.get(fallback_column))
        return 0.0

    payable = summary_amount("payable_huf", "Kifizetendő")
    order_count = int(round(summary_amount("order_count", "Rendelések")))
    route_count = int(round(summary_amount("route_count", "Útvonalak")))
    courier_base_rate = summary_amount("courier_base_rate_huf", "Nettó bevétel")
    tip = summary_amount("tip_huf", "Borravaló")
    delay_bonus = summary_amount("delay_bonus_huf")
    compliance_bonus = summary_amount("compliance_bonus_huf")
    other_route_bonus = summary_amount("other_route_bonus_huf")
    route_bonus_total = summary_amount("route_bonus_total_huf")
    imported_bonus = summary_amount("imported_bonus_huf")
    manual_bonus = summary_amount("manual_bonus_huf")
    customer_rating_bonus = summary_amount("customer_rating_bonus_huf")
    malus = abs(summary_amount("malus_huf"))
    atm_deduction = abs(summary_amount("atm_deduction_huf"))
    other_expense = abs(summary_amount("other_expense_huf"))

    if not summary_row:
        imported_bonus = parse_huf_value(row.get("Importált bónusz"))
        malus = parse_huf_value(row.get("Importált málusz"))
        atm_deduction = parse_huf_value(row.get("Importált ATM levonás"))

    period_start = str(summary_row.get("period_start") or "")
    period_end = str(summary_row.get("period_end") or "")
    period_label = f"{period_start} – {period_end}" if period_start and period_end else "Aktuális elszámolás"

    reserve_status = load_target_reserve_status(courier_id, courier_name)
    insurance_active = bool(reserve_status.get("insurance_active"))
    insurance_label = "Biztosított" if insurance_active else "Nincs biztosítás"

    route_detail = load_courier_route_detail(courier_id, courier_name, session_id)
    if route_count == 0 and not route_detail.empty:
        route_count = len(route_detail)
    if order_count == 0 and not route_detail.empty:
        order_count = int(pd.to_numeric(route_detail["Rendelések"], errors="coerce").fillna(0).sum())

    total_credits = (
        courier_base_rate + tip + delay_bonus + compliance_bonus + other_route_bonus
        + imported_bonus + manual_bonus + customer_rating_bonus
    )
    total_deductions = malus + atm_deduction + other_expense

    st.markdown('<div class="courier-shell">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="courier-cover">
          <div class="courier-cover-top">
            <div class="courier-identity">
              <div class="courier-avatar">{html.escape(initials)}</div>
              <div>
                <div class="courier-name-xl">{html.escape(courier_name)}</div>
                <div class="courier-meta">
                  <span>Courier ID: {html.escape(courier_id)}</span>
                  <span>{html.escape(str(row.get('Branch') or 'JIT'))}</span>
                  <span>{html.escape(str(row.get('Raktár') or '–'))}</span>
                </div>
              </div>
            </div>
            <div class="courier-badges">
              <span class="courier-badge"><span class="dot"></span> Aktív</span>
              <span class="courier-badge">🛡️ {html.escape(insurance_label)}</span>
            </div>
          </div>
          <div class="courier-cover-bottom">
            <div class="cover-stat"><div class="label">Aktuális kifizetés</div><div class="value">{format_huf(payable)}</div></div>
            <div class="cover-stat"><div class="label">Rendelések</div><div class="value">{order_count}</div></div>
            <div class="cover-stat"><div class="label">Teljesített körök</div><div class="value">{route_count}</div></div>
            <div class="cover-stat"><div class="label">Elszámolási időszak</div><div class="value" style="font-size:15px">{html.escape(period_label)}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_view = st.radio(
        "Profilnézet",
        ["Áttekintés", "Pénzügy", "Útvonalak", "Dokumentumok", "Reklamációk", "Profil"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"premium_profile_nav_{courier_id}",
    )

    if selected_view == "Áttekintés":
        st.markdown(
            f"""
            <div class="profile-grid">
              <div>
                <div class="profile-card">
                  <div class="profile-card-head">
                    <div><div class="profile-card-title">Havi elszámolás</div><div class="profile-card-sub">{html.escape(period_label)}</div></div>
                    <span class="route-pill">Adatbázisból</span>
                  </div>
                  <div class="money-hero">
                    <div class="eyebrow">Kifizetendő összeg</div>
                    <div class="amount">{format_huf(payable)}</div>
                    <div class="delta">{route_count} kör · {order_count} rendelés</div>
                  </div>
                  <div class="finance-columns">
                    <div class="finance-block income">
                      <div class="finance-title">Bevételek</div>
                      <div class="ledger-row"><span>Futár alapdíj</span><strong>{format_huf(courier_base_rate)}</strong></div>
                      <div class="ledger-row"><span>Borravaló</span><strong>{format_huf(tip)}</strong></div>
                      <div class="ledger-row"><span>Késedelmi bónusz</span><strong>{format_huf(delay_bonus)}</strong></div>
                      <div class="ledger-row"><span>Túramegfelelési bónusz</span><strong>{format_huf(compliance_bonus)}</strong></div>
                      <div class="ledger-row"><span>Egyéb route bónusz</span><strong>{format_huf(other_route_bonus)}</strong></div>
                      <div class="ledger-row"><span>Importált bónusz</span><strong>{format_huf(imported_bonus)}</strong></div>
                      <div class="ledger-row"><span>Manuális bónusz</span><strong>{format_huf(manual_bonus)}</strong></div>
                      <div class="ledger-row"><span>Értékelési bónusz</span><strong>{format_huf(customer_rating_bonus)}</strong></div>
                    </div>
                    <div class="finance-block outcome">
                      <div class="finance-title">Levonások</div>
                      <div class="ledger-row"><span>Málusz</span><strong>{format_huf(malus)}</strong></div>
                      <div class="ledger-row"><span>ATM levonás</span><strong>{format_huf(atm_deduction)}</strong></div>
                      <div class="ledger-row"><span>Egyéb kiadás</span><strong>{format_huf(other_expense)}</strong></div>
                      <div class="ledger-row"><span>Levonások összesen</span><strong>{format_huf(total_deductions)}</strong></div>
                    </div>
                  </div>
                </div>
              </div>
              <div>
                <div class="profile-card">
                  <div class="profile-card-head"><div><div class="profile-card-title">Elszámolási mutatók</div><div class="profile-card-sub">Aktuális összesítés</div></div></div>
                  <div class="kpi-mini-grid">
                    <div class="kpi-mini"><div class="icon">📦</div><div class="value">{order_count}</div><div class="label">Rendelés</div></div>
                    <div class="kpi-mini"><div class="icon">🚚</div><div class="value">{route_count}</div><div class="label">Kör</div></div>
                    <div class="kpi-mini"><div class="icon">💰</div><div class="value" style="font-size:16px">{format_huf(total_credits)}</div><div class="label">Bevétel összesen</div></div>
                  </div>
                </div>
                <div class="profile-card">
                  <div class="profile-card-head"><div><div class="profile-card-title">Adatforrás</div><div class="profile-card-sub">A megjelenített elszámolás állapota</div></div></div>
                  <div class="ledger-row"><span>Session</span><strong>{html.escape(str(session_id or '–'))}</strong></div>
                  <div class="ledger-row"><span>Összesítő sor</span><strong>{'Megtalálva' if summary_row else 'Nincs, főoldali tartalékadat'}</strong></div>
                  <div class="ledger-row"><span>Biztosítás</span><strong>{html.escape(insurance_label)}</strong></div>
                  <div class="ledger-row"><span>Route részletek</span><strong>{len(route_detail)} db</strong></div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif selected_view == "Pénzügy":
        st.markdown(
            f"""
            <div class="profile-card">
              <div class="profile-card-head"><div><div class="profile-card-title">Pénzügyi levezetés</div><div class="profile-card-sub">{html.escape(period_label)}</div></div><span class="route-pill">DB összesítő</span></div>
              <div class="finance-columns">
                <div class="finance-block income"><div class="finance-title">Jóváírások</div>
                  <div class="ledger-row"><span>Futár alapdíj</span><strong>{format_huf(courier_base_rate)}</strong></div>
                  <div class="ledger-row"><span>Borravaló</span><strong>{format_huf(tip)}</strong></div>
                  <div class="ledger-row"><span>Késedelmi bónusz</span><strong>{format_huf(delay_bonus)}</strong></div>
                  <div class="ledger-row"><span>Túramegfelelési bónusz</span><strong>{format_huf(compliance_bonus)}</strong></div>
                  <div class="ledger-row"><span>Egyéb route bónusz</span><strong>{format_huf(other_route_bonus)}</strong></div>
                  <div class="ledger-row"><span>Route bónusz összesen</span><strong>{format_huf(route_bonus_total)}</strong></div>
                  <div class="ledger-row"><span>Importált bónusz</span><strong>{format_huf(imported_bonus)}</strong></div>
                  <div class="ledger-row"><span>Manuális bónusz</span><strong>{format_huf(manual_bonus)}</strong></div>
                  <div class="ledger-row"><span>Értékelési bónusz</span><strong>{format_huf(customer_rating_bonus)}</strong></div>
                </div>
                <div class="finance-block outcome"><div class="finance-title">Terhelések</div>
                  <div class="ledger-row"><span>Málusz</span><strong>{format_huf(malus)}</strong></div>
                  <div class="ledger-row"><span>ATM levonás</span><strong>{format_huf(atm_deduction)}</strong></div>
                  <div class="ledger-row"><span>Egyéb kiadás</span><strong>{format_huf(other_expense)}</strong></div>
                  <div class="ledger-row"><span>Terhelések összesen</span><strong>{format_huf(total_deductions)}</strong></div>
                </div>
              </div>
              <div class="money-hero" style="margin-top:14px"><div class="eyebrow">Végösszeg</div><div class="amount">{format_huf(payable)}</div><div class="delta">{route_count} kör · {order_count} rendelés</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif selected_view == "Útvonalak":
        st.markdown(
            f'<div class="profile-card"><div class="profile-card-head"><div><div class="profile-card-title">Elszámolt körök</div><div class="profile-card-sub">A settlement.jit_row alapján</div></div><span class="route-pill">{len(route_detail)} kör</span></div>',
            unsafe_allow_html=True,
        )
        if route_detail.empty:
            st.info("Ehhez a futárhoz nem található route részlet az aktuális sessionben.")
        else:
            for _, route in route_detail.iterrows():
                route_total = sum(
                    parse_huf_value(route.get(column))
                    for column in ["Alapdíj", "Borravaló", "Késedelmi díj", "Túramegfelelés", "Egyéb bónusz"]
                )
                st.markdown(
                    f"""
                    <div class="route-card">
                      <div><div class="route-id">{html.escape(str(route.get('Route ID') or '–'))}</div><div class="route-sub">{html.escape(str(route.get('Excel dátum') or '–'))} · {html.escape(str(row.get('Raktár') or '–'))}</div></div>
                      <div><span class="route-pill">{html.escape(str(route.get('Naptípus') or '–'))}</span></div>
                      <div><div class="route-id">{int(parse_huf_value(route.get('Rendelések')))} rendelés</div><div class="route-sub">{html.escape(str(route.get('Túratípus') or '–'))}</div></div>
                      <div><div class="route-id">{format_huf(route_total)}</div><div class="route-sub">Elszámolt összeg</div></div>
                      <div class="route-arrow">›</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown('</div>', unsafe_allow_html=True)

    elif selected_view == "Dokumentumok":
        st.info("A dokumentumok bekötése a következő fejlesztési kör része.")

    elif selected_view == "Reklamációk":
        st.info("A reklamációk bekötése a következő fejlesztési kör része.")

    else:
        profile = load_courier_profile(courier_id)
        st.markdown(
            f"""
            <div class="profile-card">
              <div class="profile-card-head"><div><div class="profile-card-title">Futár alapadatai</div><div class="profile-card-sub">courier_master</div></div></div>
              <div class="ledger-row"><span>Teljes név</span><strong>{html.escape(courier_name)}</strong></div>
              <div class="ledger-row"><span>Courier ID</span><strong>{html.escape(courier_id)}</strong></div>
              <div class="ledger-row"><span>Raktár</span><strong>{html.escape(str(row.get('Raktár') or profile.get('warehouse_name') or '–'))}</strong></div>
              <div class="ledger-row"><span>Branch</span><strong>{html.escape(str(row.get('Branch') or 'JIT'))}</strong></div>
              <div class="ledger-row"><span>Biztosítás</span><strong>{html.escape(insurance_label)}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)


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
    import_session_id = (
        st.session_state.get("settlement_import_session_id")
        or load_latest_jit_session_id()
    )
    data = apply_excel_base_rates(load_courier_master(), import_session_id)
    data = apply_imported_balance_components(data, import_session_id)
    balance_period_start, balance_period_end = load_settlement_month(import_session_id)
    data = apply_manual_balance_adjustments(data, balance_period_start, balance_period_end)

    with st.sidebar:
        st.markdown("## Elszámolás")
        st.caption("Szűrés és műveletek")
        selected_month=st.selectbox("Elszámolási hónap",month_options(),key="new_month")
        branch=st.selectbox("Branch",["Összes"]+sorted(data["Branch"].unique().tolist()),key="new_branch")
        calculation_mode=st.selectbox("Számítás módja",["Összes","Excel"],key="new_calculation_mode")
        warehouse=st.selectbox("Raktár",["Összes"]+sorted(data["Raktár"].unique().tolist()),key="new_warehouse")
        status=st.selectbox("Elszámolás állapota",["Összes","Előkészítve","Ellenőrzés alatt","Jóváhagyva"],key="new_status")
        search=st.text_input("Futár keresése",placeholder="Név vagy azonosító",key="new_search")
        st.divider()
        if st.button("Adatok betöltése",type="primary",use_container_width=True):
            st.toast(f"Betöltve: {selected_month}",icon="✅")
        if st.button("Szűrők törlése",use_container_width=True):
            st.session_state["new_branch"]="Összes"
            st.session_state["new_calculation_mode"]="Összes"
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
                st.session_state.pop("settlement_import_result", None)
                st.session_state.pop("settlement_import_preview", None)
                st.session_state.pop("settlement_processing_report", None)
                st.session_state.pop("settlement_base_rate_summary", None)
                load_driver_dashboard.clear()
                load_courier_master.clear()
                load_latest_jit_session_id.clear()
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
        ("Kifizetésre vár", "Jóváhagyás után", "🟢"),
    ]
    card_columns = st.columns(4)
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