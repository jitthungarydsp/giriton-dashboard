import html
import traceback
from datetime import date
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
        


/* --- Kattintható workflow kártyák --- */
.workflow-card-row {
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:16px;
    margin:8px 0 14px 0;
}
div[class*="st-key-status_card_"] button {
    min-height:148px !important;
    border-radius:20px !important;
    padding:20px 20px !important;
    text-align:left !important;
    justify-content:flex-start !important;
    white-space:pre-line !important;
    font-size:15px !important;
    font-weight:750 !important;
    line-height:1.55 !important;
    box-shadow:0 9px 24px rgba(20,40,80,.08) !important;
    transition:transform .15s ease, box-shadow .15s ease !important;
}
div[class*="st-key-status_card_"] button:hover {
    transform:translateY(-2px) !important;
    box-shadow:0 13px 30px rgba(20,40,80,.12) !important;
}
div.st-key-status_card_settlement button {
    background:linear-gradient(135deg,#f4f8ff 0%,#eef4ff 100%) !important;
    border:1px solid #d8e5ff !important;
    border-left:6px solid #2474e5 !important;
    color:#1454ad !important;
}
div.st-key-status_card_tig button {
    background:linear-gradient(135deg,#fbf7ff 0%,#f4ecff 100%) !important;
    border:1px solid #eadcff !important;
    border-left:6px solid #7b2bd4 !important;
    color:#6320b4 !important;
}
div.st-key-status_card_reports button {
    background:linear-gradient(135deg,#fffaf4 0%,#fff3e7 100%) !important;
    border:1px solid #ffe2c4 !important;
    border-left:6px solid #f2760a !important;
    color:#c75b00 !important;
}
div.st-key-status_card_payment button {
    background:linear-gradient(135deg,#f4fff9 0%,#ebfbf2 100%) !important;
    border:1px solid #d5f3e1 !important;
    border-left:6px solid #16a765 !important;
    color:#087a45 !important;
}
div[class*="st-key-status_card_"] button[kind="primary"] {
    outline:3px solid rgba(31,166,74,.18) !important;
    box-shadow:0 0 0 2px #1FA64A inset, 0 13px 30px rgba(23,133,59,.15) !important;
}
.status-filter-note {
    background:#f7fffa;
    border:1px solid #d9f1e2;
    border-radius:14px;
    padding:11px 14px;
    color:#355d43;
    font-size:13px;
    margin:2px 0 14px 0;
}
@media (max-width:1000px) {
    .workflow-card-row { grid-template-columns:repeat(2,minmax(0,1fr)); }
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


/* --- Képminta szerinti kattintható workflow-kártyák --- */
.workflow-card-grid { margin-top: 4px; }
[class*="st-key-status_card_"] div.stButton > button {
    width: 100% !important;
    min-height: 166px !important;
    border-radius: 22px !important;
    border: 1px solid rgba(20, 50, 80, .08) !important;
    box-shadow: 0 9px 24px rgba(31, 55, 90, .09) !important;
    padding: 22px 20px 20px 98px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    white-space: pre-line !important;
    font-size: 15px !important;
    line-height: 1.72 !important;
    font-weight: 700 !important;
    position: relative !important;
    overflow: hidden !important;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease !important;
}
[class*="st-key-status_card_"] div.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 14px 30px rgba(31, 55, 90, .13) !important;
}
[class*="st-key-status_card_"] div.stButton > button p {
    white-space: pre-line !important;
    text-align: left !important;
    width: 100% !important;
}
[class*="st-key-status_card_"] div.stButton > button::before {
    position: absolute;
    left: 24px;
    top: 31px;
    width: 54px;
    height: 54px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 28px;
    font-weight: 800;
}
[class*="st-key-status_card_"] div.stButton > button::after {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 5px;
}
.st-key-status_card_settlement div.stButton > button { background: linear-gradient(135deg,#F8FBFF 0%,#EDF4FF 100%) !important; color:#1557B0 !important; }
.st-key-status_card_settlement div.stButton > button::before { content:"▣"; background:#DCEAFF; color:#1464CF; }
.st-key-status_card_settlement div.stButton > button::after { background:#1670E8; }
.st-key-status_card_tig div.stButton > button { background: linear-gradient(135deg,#FCFAFF 0%,#F4ECFF 100%) !important; color:#6321C5 !important; }
.st-key-status_card_tig div.stButton > button::before { content:"◇"; background:#EDE0FF; color:#7026D5; }
.st-key-status_card_tig div.stButton > button::after { background:#7427D8; }
.st-key-status_card_reports div.stButton > button { background: linear-gradient(135deg,#FFFDF9 0%,#FFF3E6 100%) !important; color:#C95B00 !important; }
.st-key-status_card_reports div.stButton > button::before { content:"◉"; background:#FFE9CE; color:#E66A00; }
.st-key-status_card_reports div.stButton > button::after { background:#F27600; }
.st-key-status_card_payment div.stButton > button { background: linear-gradient(135deg,#F9FFFC 0%,#EAF9F0 100%) !important; color:#087B44 !important; }
.st-key-status_card_payment div.stButton > button::before { content:"▰"; background:#D9F5E4; color:#079552; }
.st-key-status_card_payment div.stButton > button::after { background:#10A85B; }

/* Az aktív gomb Streamlit primary típusa: zöld keret és pipa. */
[class*="st-key-status_card_"] div.stButton > button[kind="primary"] {
    border: 2px solid #18A957 !important;
    box-shadow: 0 0 0 3px rgba(24,169,87,.10), 0 12px 28px rgba(31,55,90,.12) !important;
}
[class*="st-key-status_card_"] div.stButton > button[kind="primary"] span::after {
    content:"✓";
    position:absolute;
    right:20px;
    top:54px;
    width:34px;
    height:34px;
    border-radius:50%;
    display:grid;
    place-items:center;
    background:#18A957;
    color:white;
    font-size:21px;
    font-weight:900;
    box-shadow:0 4px 10px rgba(24,169,87,.24);
}
.status-filter-bar {
    margin: 18px 0 16px;
    padding: 14px 18px;
    border: 1px solid #DCEFE3;
    border-radius: 16px;
    background: linear-gradient(135deg,#FBFFFC 0%,#F2FBF6 100%);
    box-shadow: 0 5px 16px rgba(23,133,59,.06);
    color:#42624B;
    font-size:14px;
}
.status-filter-chip {
    display:inline-flex;
    align-items:center;
    gap:7px;
    margin-left:10px;
    padding:7px 12px;
    border-radius:999px;
    background:#E4F7EB;
    color:#087B44;
    font-weight:800;
}
@media (max-width: 900px) {
    [class*="st-key-status_card_"] div.stButton > button { min-height:145px !important; padding-left:82px !important; }
    [class*="st-key-status_card_"] div.stButton > button::before { left:18px; width:48px; height:48px; }
}

</style>
        """,
        unsafe_allow_html=True,
    )


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


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
        "Raktár", "Státusz", "Bruttó bevétel", "Bónusz",
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
        "Bruttó bevétel", "Bónusz", "Borravaló", "Levonás",
        "Kifizetendő", "Előző havi összeg", "KPI",
    ]:
        df[column] = 0.0

    return df[columns]


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
            "Bruttó bevétel", "Bónusz", "Borravaló", "Levonás",
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
    df["Bruttó bevétel"] = (
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


def format_huf(value: float | int) -> str:
    return f"{value:,.0f} Ft".replace(",", " ")


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


def render_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nincs találat a megadott szűrőkkel.")
        return

    st.markdown(
        """
        <div class="courier-list-header">
          <div>Futár</div><div>Branch</div><div>Számítás</div>
          <div>Bruttó</div><div>Levonás</div><div>Kifizetendő</div><div>Státusz</div>
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
            cols[3].caption(format_huf(row["Bruttó bevétel"]))
            cols[4].caption(format_huf(row["Levonás"]))
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
    data = load_courier_master()
    match = data[data["Courier ID"].astype(str) == courier_id]

    if match.empty:
        st.warning("A futár nem található.")
        return

    row = match.iloc[0]

    st.markdown(
        f"""
        <div class="detail-card" style="padding:20px 22px;margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;">
            <div>
              <div style="font-size:24px;font-weight:850;color:#17351F;">{html.escape(str(row['Futár']))}</div>
              <div style="color:#5E7464;margin-top:4px;">
                Courier ID: {html.escape(courier_id)} · {html.escape(str(row['Branch']))} · {html.escape(str(row['Raktár']))}
              </div>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              <span class="status-badge status-green">KPI {row['KPI']:.1f}%</span>
              <span class="status-badge status-yellow">{html.escape(str(row['Számítás módja']))}</span>
              <span class="status-badge {status_meta(str(row['Státusz']))[0]}">{html.escape(str(row['Státusz']))}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("KPI", f"{row['KPI']:.1f}%")
    k2.metric("Aktuális havi összeg", format_huf(row["Kifizetendő"]))
    k3.metric("Előző havi összeg", format_huf(row["Előző havi összeg"]))
    k4.metric(
        "Havi változás",
        format_huf(int(row["Kifizetendő"]) - int(row["Előző havi összeg"])),
    )

    (
        tab_current,
        tab_bonus,
        tab_malus,
        tab_reserve,
        tab_documents,
        tab_complaints,
        tab_profile,
    ) = st.tabs(
        [
            "Aktuális hónap",
            "Bónusz",
            "Málusz",
            "Céltartalék",
            "Dokumentumok",
            "Reklamációk",
            "Profil",
        ]
    )

    with tab_current:
        st.markdown("#### Aktuális havi összesítés")
        current_left, current_right = st.columns([1.1, 0.9])

        with current_left:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Bruttó bevétel": format_huf(row["Bruttó bevétel"]),
                            "Bónusz": format_huf(row["Bónusz"]),
                            "Levonás": format_huf(row["Levonás"]),
                            "Kifizetendő": format_huf(row["Kifizetendő"]),
                            "Státusz": row["Státusz"],
                        }
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        with current_right:
            st.markdown(
                f"""
                <div class="detail-card">
                  <h4>Havi áttekintés</h4>
                  <div class="detail-line"><span class="detail-label">Számítás módja</span><span class="detail-value">{html.escape(str(row['Számítás módja']))}</span></div>
                  <div class="detail-line"><span class="detail-label">Branch</span><span class="detail-value">{html.escape(str(row['Branch']))}</span></div>
                  <div class="detail-line"><span class="detail-label">Raktár</span><span class="detail-value">{html.escape(str(row['Raktár']))}</span></div>
                  <div class="detail-line"><span class="detail-label">Státusz</span><span class="detail-value">{html.escape(str(row['Státusz']))}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("#### Dokumentumműveletek")
        action1, action2 = st.columns(2)
        action1.button(
            "Elszámolás generálása",
            type="primary",
            use_container_width=True,
            key=f"ui_settlement_generate_{courier_id}",
            help="Dizájn gomb, még nincs mögötte üzleti logika.",
        )
        action2.button(
            "TIG generálása",
            type="primary",
            use_container_width=True,
            key=f"ui_tig_generate_{courier_id}",
            help="Dizájn gomb, még nincs mögötte üzleti logika.",
        )

        upload1, upload2 = st.columns(2)
        upload1.file_uploader(
            "Elszámolás feltöltése",
            type=["pdf"],
            key=f"ui_settlement_upload_{courier_id}",
        )
        upload2.file_uploader(
            "TIG feltöltése",
            type=["pdf"],
            key=f"ui_tig_upload_{courier_id}",
        )

    with tab_bonus:
        st.markdown("#### Bónuszok")
        bonus_list, bonus_editor = st.columns([1.35, 0.65])

        with bonus_list:
            bonus_demo = pd.DataFrame(
                [
                    {"Dátum": "2026-07-03", "Megnevezés": "Havi teljesítménybónusz", "Összeg": "38 000 Ft", "Státusz": "Elszámolva"},
                    {"Dátum": "2026-07-08", "Megnevezés": "Minőségi bónusz", "Összeg": "12 000 Ft", "Státusz": "Tervezet"},
                ]
            )
            st.dataframe(bonus_demo, use_container_width=True, hide_index=True)

        with bonus_editor:
            st.markdown("##### Új bónusz")
            st.text_input("Megnevezés", key=f"ui_bonus_name_{courier_id}")
            st.number_input("Összeg (Ft)", min_value=0, step=500, key=f"ui_bonus_amount_{courier_id}")
            st.text_area("Megjegyzés", key=f"ui_bonus_note_{courier_id}")
            st.button(
                "Bónusz mentése",
                use_container_width=True,
                key=f"ui_bonus_save_{courier_id}",
                help="Csak dizájn, még nem ment adatot.",
            )

    with tab_malus:
        st.markdown("#### Máluszok és levonások")
        malus_list, malus_editor = st.columns([1.35, 0.65])

        with malus_list:
            malus_demo = pd.DataFrame(
                [
                    {"Dátum": "2026-07-04", "Megnevezés": "Késés", "Összeg": "8 000 Ft", "Státusz": "Elszámolva"},
                    {"Dátum": "2026-07-09", "Megnevezés": "Felszerelés hiány", "Összeg": "15 000 Ft", "Státusz": "Tervezet"},
                ]
            )
            st.dataframe(malus_demo, use_container_width=True, hide_index=True)

        with malus_editor:
            st.markdown("##### Új málusz")
            st.selectbox(
                "Típus",
                ["Késés", "Károkozás", "Felszerelés", "Adminisztráció", "Egyéb"],
                key=f"ui_malus_type_{courier_id}",
            )
            st.number_input("Összeg (Ft)", min_value=0, step=500, key=f"ui_malus_amount_{courier_id}")
            st.text_area("Megjegyzés", key=f"ui_malus_note_{courier_id}")
            st.button(
                "Málusz mentése",
                use_container_width=True,
                key=f"ui_malus_save_{courier_id}",
                help="Csak dizájn, még nem ment adatot.",
            )

    with tab_reserve:
        st.markdown("#### Céltartalék és biztosítás")

        reserve1, reserve2 = st.columns(2)
        with reserve1:
            st.markdown(
                """
                <div class="detail-card">
                  <h4>Biztosítási státusz</h4>
                  <div class="detail-line"><span class="detail-label">Állapot</span><span class="detail-value">Van biztosítása</span></div>
                  <div class="detail-line"><span class="detail-label">Érvényesség</span><span class="detail-value">2026. december 31.</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.radio(
                "Van biztosításom",
                ["Igen", "Nem"],
                horizontal=True,
                key=f"ui_insurance_{courier_id}",
            )

        with reserve2:
            st.markdown(
                """
                <div class="detail-card">
                  <h4>Aktuális céltartalék</h4>
                  <div style="font-size:28px;font-weight:850;color:#17351F;">65 000 Ft</div>
                  <div style="color:#5E7464;margin-top:6px;">Dizájnadat</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.number_input(
                "Céltartalék összege (Ft)",
                min_value=0,
                value=65000,
                step=1000,
                key=f"ui_reserve_amount_{courier_id}",
            )

        st.text_area(
            "Megjegyzés",
            placeholder="Például biztosítási kötvény, jóváhagyás vagy adminisztratív megjegyzés.",
            key=f"ui_reserve_note_{courier_id}",
        )
        st.button(
            "Céltartalék mentése",
            use_container_width=True,
            key=f"ui_reserve_save_{courier_id}",
            help="Csak dizájn, még nem ment adatot.",
        )

    with tab_documents:
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

    with tab_complaints:
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

    with tab_profile:
        st.markdown("#### Profil")
        profile1, profile2 = st.columns(2)

        with profile1:
            st.text_input("Név", value=str(row["Futár"]), key=f"ui_profile_name_{courier_id}")
            st.text_input("Courier ID", value=courier_id, disabled=True, key=f"ui_profile_id_{courier_id}")
            st.text_input("Telefonszám", value="+36 30 123 4567", key=f"ui_profile_phone_{courier_id}")
            st.text_input("E-mail", value="futar@example.com", key=f"ui_profile_email_{courier_id}")
            st.selectbox(
                "Branch",
                ["Kifli", "Egyéb"],
                index=0,
                key=f"ui_profile_branch_{courier_id}",
            )
            st.text_input("Raktár", value=str(row["Raktár"]), key=f"ui_profile_warehouse_{courier_id}")

        with profile2:
            st.selectbox(
                "Számítás módja",
                ["Excel", "API", "Egyéni"],
                index=["Excel", "API", "Egyéni"].index(str(row["Számítás módja"])),
                key=f"ui_profile_calc_{courier_id}",
            )
            st.text_input("Vállalkozás neve", value="Minta Futár Kft.", key=f"ui_profile_company_{courier_id}")
            st.text_input("Adószám", value="12345678-2-42", key=f"ui_profile_tax_{courier_id}")
            st.text_input("Bankszámlaszám", value="11700000-00000000-00000000", key=f"ui_profile_bank_{courier_id}")
            st.selectbox("Biztosítás", ["Van", "Nincs"], key=f"ui_profile_insurance_{courier_id}")
            st.selectbox("Profil státusz", ["Aktív", "Inaktív"], key=f"ui_profile_status_{courier_id}")

        st.button(
            "Profil mentése",
            type="primary",
            use_container_width=True,
            key=f"ui_profile_save_{courier_id}",
            help="Csak dizájn, még nem ment adatot.",
        )


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
    st.subheader("Paraméterértékek katalógusa")
    st.caption(
        "Vállalkozói díjak, futárdíjak és időszakos bónuszok "
        "érvényességi idővel. Ez továbbra is designer nézet."
    )

    catalog = pd.DataFrame(
        [
            {
                "Kategória": "Vállalkozói díj",
                "Level": "",
                "Megnevezés": "Alap vállalkozói díj",
                "Érték": "1 250 Ft / óra",
                "Érvényes ettől": "2026-01-01",
                "Érvényes eddig": "2026-06-30",
                "Státusz": "Lejárt",
            },
            {
                "Kategória": "Vállalkozói díj",
                "Level": "",
                "Megnevezés": "Alap vállalkozói díj",
                "Érték": "1 350 Ft / óra",
                "Érvényes ettől": "2026-07-01",
                "Érvényes eddig": "2026-12-31",
                "Státusz": "Aktív",
            },
            {
                "Kategória": "Futárdíj",
                "Level": "",
                "Megnevezés": "Alap futárdíj",
                "Érték": "950 Ft / cím",
                "Érvényes ettől": "2026-07-01",
                "Érvényes eddig": "2026-12-31",
                "Státusz": "Aktív",
            },
            {
                "Kategória": "Időszakos bónusz",
                "Level": "",
                "Megnevezés": "Nyári teljesítménybónusz",
                "Érték": "15 000 Ft",
                "Érvényes ettől": "2026-07-01",
                "Érvényes eddig": "2026-08-31",
                "Státusz": "Aktív",
            },
        ]
    )

    filter1, filter2 = st.columns([1, 1])
    category_filter = filter1.selectbox(
        "Kategória",
        ["Összes", "Vállalkozói díj", "Futárdíj", "Időszakos bónusz"],
        key="ui_parameter_category_filter",
    )
    status_filter = filter2.selectbox(
        "Státusz",
        ["Összes", "Aktív", "Jövőbeni", "Lejárt"],
        key="ui_parameter_status_filter",
    )

    shown = catalog.copy()
    if category_filter != "Összes":
        shown = shown[shown["Kategória"] == category_filter]
    if status_filter != "Összes":
        shown = shown[shown["Státusz"] == status_filter]

    shown = shown[["Kategória","Level","Megnevezés","Érték","Érvényes ettől","Érvényes eddig","Státusz"]]
    st.dataframe(shown, use_container_width=True, hide_index=True)

    row_action1, row_action2 = st.columns(2)
    if row_action1.button(
        "Kiválasztott szerkesztése",
        use_container_width=True,
        key="ui_parameter_edit",
        help="Designer gomb, még nem módosít adatot.",
    ):
        st.info("A kiválasztott katalóguselem szerkesztőnézete nyílna meg.")

    if row_action2.button(
        "Kiválasztott törlése",
        use_container_width=True,
        key="ui_parameter_delete",
        help="Designer gomb, még nem töröl adatot.",
    ):
        st.warning("A kiválasztott katalóguselem törlésre kerülne.")

    st.divider()
    st.markdown("#### Új paraméter felvétele")

    form_left, form_right = st.columns(2)

    with form_left:
        parameter_type = st.selectbox(
            "Paraméter típusa",
            ["Vállalkozói díj", "Futárdíj", "Időszakos bónusz"],
            key="ui_parameter_type",
        )
        st.text_input("Level", key="ui_parameter_level")
        st.text_input(
            "Megnevezés",
            placeholder="Például: Alap futárdíj",
            key="ui_parameter_name",
        )
        value_col1, value_col2 = st.columns([1.35, 0.65])
        value_col1.number_input(
            "Érték",
            min_value=0,
            step=100,
            key="ui_parameter_value",
        )
        value_col2.selectbox(
            "Egység",
            ["Ft", "Ft / óra", "Ft / cím", "%"],
            key="ui_parameter_unit",
        )

    with form_right:
        st.date_input(
            "Érvényes ettől",
            key="ui_parameter_start_date",
        )
        st.date_input(
            "Érvényes eddig",
            key="ui_parameter_end_date",
        )
        st.text_area(
            "Megjegyzés",
            placeholder="Belső megjegyzés vagy feltétel.",
            key="ui_parameter_note",
        )

    if parameter_type == "Időszakos bónusz":
        st.markdown("##### Bónusz beállítások")
        bonus1, bonus2 = st.columns(2)
        bonus1.selectbox(
            "Bónusz alkalmazása",
            ["Minden futárra", "Csak vállalkozókra", "Csak alkalmazott futárokra"],
            key="ui_bonus_scope",
        )
        bonus2.selectbox(
            "Bónusz gyakorisága",
            ["Egyszeri", "Napi", "Heti", "Havi"],
            key="ui_bonus_frequency",
        )

    save1, save2 = st.columns([1, 1])
    if save1.button(
        "Paraméter mentése",
        type="primary",
        use_container_width=True,
        key="ui_parameter_save",
        help="Csak designer gomb, még nincs mögötte mentési logika.",
    ):
        st.success("Az új paraméter bekerülne a katalógusba.")

    if save2.button(
        "Űrlap törlése",
        use_container_width=True,
        key="ui_parameter_form_clear",
        help="Csak designer gomb.",
    ):
        st.info("Az űrlap mezői törlődnének.")

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
    data=load_courier_master()

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
            help="Az Excel összes munkalapját nyersen menti a settlement sémába.",
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
                load_driver_dashboard.clear()
                load_courier_master.clear()

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

    total_gross=int(filtered["Bruttó bevétel"].sum()) if not filtered.empty else 0
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

    st.markdown('<div class="section-title">Áttekintés</div>',unsafe_allow_html=True)

    workflow_cards = [
        ("Elszámolásra vár", "Még nem készült elszámolás", "status_card_settlement"),
        ("TIG-re vár", "Még nem készült TIG", "status_card_tig"),
        ("Bejelentések", "Nyitott ügyek", "status_card_reports"),
        ("Kifizetésre vár", "Jóváhagyás után", "status_card_payment"),
    ]
    active_workflow_filter = st.session_state.get("dashboard_status_filter")
    card_columns = st.columns(4, gap="medium")

    for card_column, (card_status, card_note, card_key) in zip(card_columns, workflow_cards):
        card_count = int((base_filtered["Státusz"] == card_status).sum())
        button_label = f"{card_status}\n{card_count} db\n{card_note}"
        is_active = active_workflow_filter == card_status

        if card_column.button(
            button_label,
            key=card_key,
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if is_active:
                st.session_state.pop("dashboard_status_filter", None)
            else:
                st.session_state["dashboard_status_filter"] = card_status
            st.rerun()

    if active_workflow_filter:
        st.markdown(
            f'<div class="status-filter-bar">⌁ <strong>Aktív szűrő:</strong>'
            f'<span class="status-filter-chip">{html.escape(active_workflow_filter)} &nbsp;×</span>'
            '<span style="margin-left:10px;color:#6D7F71;">A kijelölt kártyára kattintva kikapcsolható.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        selected_warehouse_label = warehouse if warehouse != "Összes" else "összes raktár"
        st.markdown(
            f'<div class="status-filter-bar">⌁ Nincs aktív státuszszűrés — az '
            f'<strong>{html.escape(selected_warehouse_label)}</strong> összes futárja látható.</div>',
            unsafe_allow_html=True,
        )

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