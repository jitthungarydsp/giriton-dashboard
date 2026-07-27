# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Új Elszámolási oldal",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------
# DESIGN
# ---------------------------------------------------------
def apply_design() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #f5f7fb;
            --surface: #ffffff;
            --surface-soft: #eef4ff;
            --text: #172033;
            --muted: #667085;
            --border: #e4e9f2;
            --primary: #2f6fed;
            --primary-dark: #2459bf;
            --success: #16856b;
            --warning: #c47a12;
            --danger: #c43d4b;
            --shadow: 0 8px 24px rgba(20, 40, 80, 0.06);
        }

        .stApp {
            background: var(--bg);
        }

        .block-container {
            max-width: 1540px;
            padding-top: 1.25rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid var(--border);
        }

        .hero {
            background: linear-gradient(135deg, #ffffff 0%, #edf4ff 100%);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px 28px;
            margin-bottom: 18px;
            box-shadow: var(--shadow);
        }

        .hero-badge {
            display: inline-block;
            background: #dfeaff;
            color: var(--primary-dark);
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.03em;
            margin-bottom: 10px;
        }

        .hero h1 {
            color: var(--text);
            margin: 0;
            font-size: 32px;
            line-height: 1.15;
        }

        .hero p {
            color: var(--muted);
            margin: 8px 0 0 0;
            font-size: 15px;
        }

        .section-title {
            color: var(--text);
            font-size: 18px;
            font-weight: 750;
            margin: 10px 0 12px 0;
        }

        .info-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 16px;
            min-height: 112px;
            box-shadow: 0 4px 16px rgba(20, 40, 80, 0.04);
        }

        .info-label {
            color: var(--muted);
            font-size: 13px;
            margin-bottom: 8px;
        }

        .info-value {
            color: var(--text);
            font-size: 25px;
            font-weight: 800;
            line-height: 1.1;
        }

        .info-note {
            color: var(--muted);
            font-size: 12px;
            margin-top: 8px;
        }

        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
            background: var(--success);
        }

        div[data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 4px 16px rgba(20, 40, 80, 0.04);
        }

        div[data-testid="stMetricLabel"] {
            color: var(--muted);
        }

        div[data-testid="stMetricValue"] {
            color: var(--text);
            font-weight: 800;
        }

        .stButton > button,
        .stDownloadButton > button {
            min-height: 42px;
            border-radius: 11px;
            font-weight: 700;
        }

        .stButton > button[kind="primary"] {
            background: var(--primary);
            border-color: var(--primary);
        }

        .stButton > button[kind="primary"]:hover {
            background: var(--primary-dark);
            border-color: var(--primary-dark);
        }

        div[data-baseweb="select"] > div,
        div[data-testid="stDateInput"] > div,
        div[data-testid="stTextInputRootElement"] {
            border-radius: 11px;
        }

        div[data-testid="stDataFrame"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
        }

        .small-muted {
            color: var(--muted);
            font-size: 12px;
        }

        .footer-note {
            text-align: center;
            color: var(--muted);
            font-size: 12px;
            padding-top: 26px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# MOCK DATA - később adatbázisra cserélhető
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def get_demo_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Futár": "Kiss Péter",
                "Raktár": "Budapest",
                "Bruttó bevétel": 482_500,
                "Bónusz": 38_000,
                "Levonás": 52_000,
                "Kifizetendő": 468_500,
                "Státusz": "Előkészítve",
            },
            {
                "Futár": "Nagy Ádám",
                "Raktár": "Budapest",
                "Bruttó bevétel": 421_900,
                "Bónusz": 29_500,
                "Levonás": 43_200,
                "Kifizetendő": 408_200,
                "Státusz": "Ellenőrzés alatt",
            },
            {
                "Futár": "Tóth Bence",
                "Raktár": "Győr",
                "Bruttó bevétel": 389_600,
                "Bónusz": 25_000,
                "Levonás": 31_000,
                "Kifizetendő": 383_600,
                "Státusz": "Jóváhagyva",
            },
            {
                "Futár": "Szabó Márk",
                "Raktár": "Debrecen",
                "Bruttó bevétel": 511_300,
                "Bónusz": 42_500,
                "Levonás": 64_000,
                "Kifizetendő": 489_800,
                "Státusz": "Előkészítve",
            },
        ]
    )


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def format_huf(value: float | int) -> str:
    return f"{value:,.0f} Ft".replace(",", " ")


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge">ÚJ MODUL</div>
            <h1>Új Elszámolási oldal</h1>
            <p>Gyors, átlátható és biztonságos futárelszámolási felület.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# PAGE
# ---------------------------------------------------------
def show_new_settlement_page() -> None:
    apply_design()
    render_header()

    data = get_demo_data()

    with st.sidebar:
        st.markdown("## Elszámolás")
        st.caption("Szűrés és műveletek")

        today = date.today()
        start_date = st.date_input(
            "Kezdő dátum",
            value=today - timedelta(days=7),
            key="new_settlement_start_date",
        )
        end_date = st.date_input(
            "Záró dátum",
            value=today,
            key="new_settlement_end_date",
        )

        warehouse_options = ["Összes"] + sorted(data["Raktár"].unique().tolist())
        warehouse = st.selectbox(
            "Raktár",
            warehouse_options,
            key="new_settlement_warehouse",
        )

        status_options = ["Összes"] + sorted(data["Státusz"].unique().tolist())
        status = st.selectbox(
            "Státusz",
            status_options,
            key="new_settlement_status",
        )

        search = st.text_input(
            "Futár keresése",
            placeholder="Név vagy azonosító",
            key="new_settlement_search",
        )

        st.divider()
        load_clicked = st.button(
            "Adatok frissítése",
            type="primary",
            use_container_width=True,
            key="new_settlement_load",
        )
        st.button(
            "Szűrők törlése",
            use_container_width=True,
            key="new_settlement_clear",
        )

        st.markdown(
            '<p class="small-muted">A design külső UI-csomag nélkül készült, ezért gyors és stabil marad.</p>',
            unsafe_allow_html=True,
        )

    filtered = data.copy()
    if warehouse != "Összes":
        filtered = filtered[filtered["Raktár"] == warehouse]
    if status != "Összes":
        filtered = filtered[filtered["Státusz"] == status]
    if search.strip():
        filtered = filtered[
            filtered["Futár"].str.contains(search.strip(), case=False, na=False)
        ]

    if load_clicked:
        st.toast("Az adatok frissítve.", icon="✅")

    total_gross = int(filtered["Bruttó bevétel"].sum()) if not filtered.empty else 0
    total_bonus = int(filtered["Bónusz"].sum()) if not filtered.empty else 0
    total_deduction = int(filtered["Levonás"].sum()) if not filtered.empty else 0
    total_payable = int(filtered["Kifizetendő"].sum()) if not filtered.empty else 0

    st.markdown('<div class="section-title">Áttekintés</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Futárok száma", len(filtered))
    c2.metric("Bruttó bevétel", format_huf(total_gross))
    c3.metric("Levonások", format_huf(total_deduction))
    c4.metric("Kifizetendő", format_huf(total_payable))

    st.markdown('<div class="section-title">Elszámolások</div>', unsafe_allow_html=True)

    table_col, action_col = st.columns([3.2, 1.1], gap="large")

    with table_col:
        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Bruttó bevétel": st.column_config.NumberColumn(format="%d Ft"),
                "Bónusz": st.column_config.NumberColumn(format="%d Ft"),
                "Levonás": st.column_config.NumberColumn(format="%d Ft"),
                "Kifizetendő": st.column_config.NumberColumn(format="%d Ft"),
                "Státusz": st.column_config.TextColumn(width="medium"),
            },
        )

    with action_col:
        st.markdown("### Gyors műveletek")
        selected_courier = st.selectbox(
            "Futár kiválasztása",
            filtered["Futár"].tolist() if not filtered.empty else ["Nincs találat"],
            key="new_settlement_selected_courier",
        )

        st.button(
            "Részletek megnyitása",
            use_container_width=True,
            key="new_settlement_open_details",
        )
        st.button(
            "PDF előnézet",
            use_container_width=True,
            key="new_settlement_pdf_preview",
        )
        st.button(
            "PDF generálása",
            type="primary",
            use_container_width=True,
            key="new_settlement_pdf_generate",
        )

        st.markdown(
            """
            <div class="info-card" style="margin-top: 12px;">
                <div class="info-label">Rendszerállapot</div>
                <div class="info-note">
                    <span class="status-dot"></span>Az oldal készen áll
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3 = st.tabs(
        ["Bevételi tételek", "Levonások", "Dokumentumok"]
    )

    with tab1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Alap bevétel", format_huf(total_gross - total_bonus))
        c2.metric("Bónuszok", format_huf(total_bonus))
        c3.metric("Összes bevétel", format_huf(total_gross + total_bonus))
        with st.expander("Részletes bevételi bontás"):
            st.info("Ide kerülnek később az útvonal-, ügyfélértékelési és havi bónusz adatok.")

    with tab2:
        c1, c2, c3 = st.columns(3)
        c1.metric("Biztosítás", format_huf(10_000 * len(filtered)))
        c2.metric("Egyéb levonások", format_huf(max(total_deduction - 10_000 * len(filtered), 0)))
        c3.metric("Összes levonás", format_huf(total_deduction))
        with st.expander("Részletes levonási bontás"):
            st.info("Ide kerül később a céltartalék, ATM, biztosítás és manuális levonás.")

    with tab3:
        st.markdown("#### Dokumentumkezelés")
        c1, c2, c3 = st.columns(3)
        c1.button("Elszámolási PDF", use_container_width=True, key="doc_settlement")
        c2.button("TIG dokumentum", use_container_width=True, key="doc_tig")
        c3.button("Export Excelbe", use_container_width=True, key="doc_excel")

    st.markdown(
        '<div class="footer-note">Új Elszámolási oldal • különálló, könnyű Streamlit design</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    show_new_settlement_page()