import streamlit as st
from streamlit_option_menu import option_menu

# --- Oldal alapbeállításai ---
st.set_page_config(
    page_title="Futár Központ", 
    page_icon="🚴‍♂️", 
    layout="wide", # Szélesvásznú nézet, hogy kiférjenek a kártyák
    initial_sidebar_state="expanded"
)

# --- Segédfüggvények (a te logikád alapján) ---
def render_kiflis_status_card(title, subtitle, icon, status, message, type="info"):
    """Egy szép vizuális kártyát generál a státusznak megfelelően."""
    if type == "warning":
        st.warning(f"**{title}**\n\n{message}")
    elif type == "info":
        st.info(f"**{title}**\n\n{message}")
    elif type == "success":
        st.success(f"**{title}**\n\n{message}")

def check_shift_status(minutes_to_start):
    """Eldönti, milyen üzenetet mutasson a műszak közeledtével."""
    minutes_to_start = max(int(minutes_to_start or 0), 0)
    
    if minutes_to_start > 40:
        render_kiflis_status_card(
            title="Lassan kezdődik a műszakod ⏳",
            subtitle=f"Még {minutes_to_start} perc van a kezdésig.",
            icon="40+",
            status="Készülődés",
            message="Még van idő összerakni magad, de a műszak már integet a távolból.",
            type="info"
        )
    else:
        render_kiflis_status_card(
            title="Ideje Giritonba bejelentkezni! ❗",
            subtitle=f"Még {minutes_to_start} perc van a kezdésig.",
            icon="!",
            status="Depó felé",
            message="Jelentkezz be Giritonba. Ha valami nem áll össze, kérj segítséget a diszpécsertől.",
            type="warning"
        )

# --- Oldalsáv / Navigáció ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2972/2972185.png", width=100) # Ide jöhet egy egyedi logó
    st.write("### Szia, Futár!")
    
    selected_page = option_menu(
        menu_title=None,
        options=["Műszak áttekintés", "Aktuális címek", "Napi statisztika"],
        icons=["house", "geo-alt", "bar-chart-line"],
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "orange", "font-size": "18px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px"},
            "nav-link-selected": {"background-color": "#4CAF50"}, # Zöld kiemelés
        }
    )

# --- Főképernyő tartalom ---

if selected_page == "Műszak áttekintés":
    st.title("Mai Műszak 📦")
    st.markdown("---")
    
    # Felső mutatók (KPI kártyák)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Kiszállított", value="12 / 20", delta="8 hátra", delta_color="normal")
    with col2:
        st.metric(label="Borravaló", value="4 500 Ft", delta="Jó átlag", delta_color="normal")
    with col3:
        st.metric(label="Műszak vége", value="16:00", delta="-2.5 óra", delta_color="inverse")
    with col4:
        st.metric(label="Késés", value="0 perc", delta="Időben vagy!", delta_color="off")
    
    st.markdown("### Aktuális teendők")
    # Itt használjuk a te logikádat, egy csúszkával tesztelheted:
    test_minutes = st.slider("Mennyi idő van a kezdésig? (Teszt)", 0, 60, 45)
    check_shift_status(test_minutes)
    
    # Alsó rész: Gyorsgombok
    st.markdown("### Gyorsműveletek")
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        st.button("🗺️ Útvonaltervező indítása", use_container_width=True)
    with btn_col2:
        st.button("📞 Diszpécser hívása", use_container_width=True)
    with btn_col3:
        st.button("☕ Szünet kérése", use_container_width=True)

elif selected_page == "Aktuális címek":
    st.title("Aktuális Címek 📍")
    st.info("Itt fognak megjelenni a soron következő szállítási címek és a vásárlói megjegyzések.")
    
elif selected_page == "Napi statisztika":
    st.title("Napi Statisztika 📊")
    st.info("Itt láthatod a teljesítményedet, megtett kilométereket és a borravaló eloszlását.")