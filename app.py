import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px

# --- Oldal alapbeállításai ---
# --- Oldal alapbeállításai ---
st.set_page_config(
    page_title="Futár Központ", 
    page_icon="🥐", # Lecseréltük a biciklit kiflire
    layout="wide", 
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
    # A képet egy try-except blokkba tesszük, hogy ne dobjon hibát, ha a fájl nem található
    try:
        st.image("letöltés.jfif", width=150)
    except:
        st.write("Logó nem található")
    
    st.write("### Szia, Futár!")
    
    # A hiba elkerülése végett egyszerűsítettem a stílus megadást
    selected_page = option_menu(
        menu_title=None,
        options=["Műszak áttekintés", "Aktuális címek", "Napi statisztika", "PeopleForce", "Műszakjaim"],
        icons=["house", "geo-alt", "bar-chart-line"],
        default_index=0,
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
    st.markdown("---")
    
    # 1. Sor: Két grafikon egymás mellett
    col1, col2 = st.columns(2)
    
    with col1:
        # Címek állapota diagram
        df_status = pd.DataFrame({
            "Állapot": ["Kiszállítva", "Hátralévő", "Sikertelen"],
            "Darab": [12, 6, 2]
        })
        fig1 = px.pie(df_status, values="Darab", names="Állapot", title="📦 Címek állapota",
                      color_discrete_sequence=["#4CAF50", "#FFC107", "#F44336"], hole=0.3)
        st.plotly_chart(fig1, use_container_width=True)
        
    with col2:
        # Fizetési módok diagram
        df_payment = pd.DataFrame({
            "Mód": ["Előre fizetve", "Készpénz", "Bankkártya (Terminál)"],
            "Darab": [10, 5, 5]
        })
        fig2 = px.pie(df_payment, values="Darab", names="Mód", title="💳 Fizetési módok a helyszínen",
                      color_discrete_sequence=["#2196F3", "#9C27B0", "#FF9800"], hole=0.3)
        st.plotly_chart(fig2, use_container_width=True)

    # 2. Sor: Újabb két grafikon
    st.markdown("---")
    col3, col4 = st.columns(2)
    
    with col3:
        # Pontosság diagram
        df_timing = pd.DataFrame({
            "Kategória": ["Időben érkezett", "0-10 perc késés", "10+ perc késés"],
            "Darab": [15, 3, 2]
        })
        fig3 = px.pie(df_timing, values="Darab", names="Kategória", title="⏱️ Kiszállítási pontosság",
                      color_discrete_sequence=["#00BCD4", "#8BC34A", "#E91E63"])
        fig3.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig3, use_container_width=True)
        
    with col4:
        # Csomagtípusok diagram
        df_packages = pd.DataFrame({
            "Típus": ["Normál (Száraz)", "Hűtős", "Fagyasztott"],
            "Darab": [25, 10, 5]
        })
        fig4 = px.pie(df_packages, values="Darab", names="Típus", title="❄️ Csomagok típusai",
                      color_discrete_sequence=["#8D6E63", "#03A9F4", "#3F51B5"])
        st.plotly_chart(fig4, use_container_width=True)
elif selected_page == "PeopleForce":
    st.title("PeopleForce Admin 👥")
    
    # Fülek a szervezéshez
    tab1, tab2, tab3 = st.tabs(["Számlák", "TIG feltöltés", "Jogosultságok"])
    
    with tab1:
        st.subheader("Számla kezelés")
        uploaded_file = st.file_uploader("Számla feltöltése (.pdf)", type="pdf")
        if uploaded_file:
            st.success("Fájl sikeresen feltöltve!")
            # Visszajelző lámpa (logikai állapot alapján)
            st.write("Státusz: 🟢 Ellenőrizve") 
    
    with tab2:
        st.subheader("TIG dokumentumok futároknak")
        st.file_uploader("TIG dokumentum feltöltése", key="tig_upload")
        
    with tab3:
        st.subheader("Jogosultságok")
        user_role = st.selectbox("Felhasználói szint:", ["Futár", "Diszpécser", "Admin"])
        
elif selected_page == "Műszakjaim":
    st.title("Aktuális Címek 📍")
    st.info("Műszakok")
        