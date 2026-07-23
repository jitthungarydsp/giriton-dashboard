import html
from datetime import date

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Új Elszámolási oldal",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_design() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg:#f5f7fb; --surface:#ffffff; --text:#172033; --muted:#667085;
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
            padding:15px 16px; border-bottom:1px solid #edf1f6; color:#253047; font-size:14px;
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
        .led {
            display:inline-block; width:14px; height:14px; border-radius:50%;
            box-shadow:inset 0 1px 1px rgba(255,255,255,.7), 0 0 0 3px rgba(0,0,0,.03), 0 2px 6px rgba(0,0,0,.18);
        }
        .led-red { background:radial-gradient(circle at 35% 30%,#ffb3bd 0 18%,#f05a6b 35%,#c92f43 75%); }
        .led-yellow { background:radial-gradient(circle at 35% 30%,#fff0a6 0 18%,#f4c542 35%,#d69900 75%); }
        .led-green { background:radial-gradient(circle at 35% 30%,#a8f0d6 0 18%,#29b784 35%,#15775a 75%); }
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
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def get_demo_data() -> pd.DataFrame:
    return pd.DataFrame([
        {"Futár":"Kiss Péter","Raktár":"Budapest","Bruttó bevétel":482500,"Bónusz":38000,"Levonás":52000,"Kifizetendő":468500,"Státusz":"Előkészítve"},
        {"Futár":"Nagy Ádám","Raktár":"Budapest","Bruttó bevétel":421900,"Bónusz":29500,"Levonás":43200,"Kifizetendő":408200,"Státusz":"Ellenőrzés alatt"},
        {"Futár":"Tóth Bence","Raktár":"Győr","Bruttó bevétel":389600,"Bónusz":25000,"Levonás":31000,"Kifizetendő":383600,"Státusz":"Jóváhagyva"},
        {"Futár":"Szabó Márk","Raktár":"Debrecen","Bruttó bevétel":511300,"Bónusz":42500,"Levonás":64000,"Kifizetendő":489800,"Státusz":"Előkészítve"},
    ])


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
    }
    return mapping.get(status,("status-yellow","led-yellow"))


def render_table(df: pd.DataFrame) -> None:
    rows=[]
    for _,r in df.iterrows():
        badge,led=status_meta(str(r["Státusz"]))
        rows.append(
            f"""<tr>
            <td><div class="courier-name">{html.escape(str(r['Futár']))}</div><div class="courier-sub">{html.escape(str(r['Raktár']))}</div></td>
            <td class="money">{format_huf(r['Bruttó bevétel'])}</td>
            <td class="money">{format_huf(r['Bónusz'])}</td>
            <td class="money">{format_huf(r['Levonás'])}</td>
            <td class="money payable">{format_huf(r['Kifizetendő'])}</td>
            <td><span class="status-badge {badge}">{html.escape(str(r['Státusz']))}</span></td>
            <td style="text-align:center"><span class="led {led}" title="{html.escape(str(r['Státusz']))}"></span></td>
            </tr>"""
        )
    empty='<tr><td colspan="7" style="text-align:center;color:#667085;padding:30px">Nincs találat a megadott szűrőkkel.</td></tr>'
    body=''.join(rows) if rows else empty
    st.markdown(
        f"""
        <div class="table-card">
          <div class="table-card-head"><div><h3>Futárok elszámolásai</h3><span>Részletes havi összesítés</span></div><span>{len(df)} találat</span></div>
          <table class="premium-table">
            <thead><tr><th>Futár</th><th>Bruttó bevétel</th><th>Bónusz</th><th>Levonás</th><th>Kifizetendő</th><th>Státusz</th><th style="text-align:center">Állapot</th></tr></thead>
            <tbody>{body}</tbody>
          </table>
          <div class="table-footer"><span>Megjelenítve: {len(df)} sor</span><div class="pager"><span>‹</span><span class="active">1</span><span>›</span></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_new_settlement_page() -> None:
    apply_design()
    data=get_demo_data()

    with st.sidebar:
        st.markdown("## Elszámolás")
        st.caption("Szűrés és műveletek")
        selected_month=st.selectbox("Elszámolási hónap",month_options(),key="new_month")
        warehouse=st.selectbox("Raktár",["Összes"]+sorted(data["Raktár"].unique().tolist()),key="new_warehouse")
        status=st.selectbox("Elszámolás állapota",["Összes","Előkészítve","Ellenőrzés alatt","Jóváhagyva"],key="new_status")
        search=st.text_input("Futár keresése",placeholder="Név vagy azonosító",key="new_search")
        st.divider()
        if st.button("Adatok betöltése",type="primary",use_container_width=True):
            st.toast(f"Betöltve: {selected_month}",icon="✅")
        if st.button("Szűrők törlése",use_container_width=True):
            st.session_state["new_warehouse"]="Összes"
            st.session_state["new_status"]="Összes"
            st.session_state["new_search"]=""
            st.rerun()
        st.markdown('<p class="side-note">Könnyű, külső UI-csomag nélküli felület. A régi elszámolási oldalt nem módosítja.</p>',unsafe_allow_html=True)

    filtered=data.copy()
    if warehouse!="Összes":
        filtered=filtered[filtered["Raktár"]==warehouse]
    if status!="Összes":
        filtered=filtered[filtered["Státusz"]==status]
    if search.strip():
        filtered=filtered[filtered["Futár"].str.contains(search.strip(),case=False,na=False)]

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
    st.markdown(
        f"""
        <div class="kpi-grid">
          <div class="kpi" style="--accent:#2f6fed"><div class="k-label">Futárok száma</div><div class="k-value">{len(filtered)}</div><div class="k-note">Aktív elszámolások</div></div>
          <div class="kpi" style="--accent:#5b8def"><div class="k-label">Bruttó bevétel</div><div class="k-value">{format_huf(total_gross)}</div><div class="k-note">Havi összesítés</div></div>
          <div class="kpi" style="--accent:#f0b429"><div class="k-label">Levonások</div><div class="k-value">{format_huf(total_deduction)}</div><div class="k-note">Összes levonás</div></div>
          <div class="kpi" style="--accent:#1f9d74"><div class="k-label">Kifizetendő</div><div class="k-value">{format_huf(total_payable)}</div><div class="k-note">Végleges összeg</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_table(filtered)

    st.markdown('<div class="section-title" style="margin-top:18px">Gyors műveletek</div>',unsafe_allow_html=True)
    a,b,c,d=st.columns(4)
    a.button("Részletek megnyitása",use_container_width=True)
    b.button("PDF előnézet",use_container_width=True)
    c.button("PDF generálása",type="primary",use_container_width=True)
    d.button("Export Excelbe",use_container_width=True)


if __name__ == "__main__":
    show_new_settlement_page()