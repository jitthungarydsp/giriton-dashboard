import pandas as pd
import streamlit as st

from resources.route_statistics_sheet import read_route_statistics
from resources.users import load_users


def to_number(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def prepare_dataframe(records):
    df = pd.DataFrame(records)

    if df.empty:
        return df

    for column in ["driver_id", "route_id", "driver_name", "status", "license_plate"]:
        if column not in df.columns:
            df[column] = ""

    if "work_date" not in df.columns:
        df["work_date"] = df.get("updated_at", "").astype(str).str[:10]

    df["work_date"] = pd.to_datetime(df["work_date"], errors="coerce")
    df = df.dropna(subset=["work_date"])

    for column in [
        "total_distance_km",
        "distance_covered_km",
        "parcels_delivered",
        "parcels_total",
    ]:
        if column not in df.columns:
            df[column] = 0

        df[column] = to_number(df[column])

    df["driver_id"] = df["driver_id"].astype(str)
    df["route_id"] = df["route_id"].astype(str)

    return df


def filter_dataframe_by_user(df, user):
    if df.empty or user["role"] == "admin":
        return df

    if user["role"] == "trainer":
        users_data = load_users()
        trainer_courier_ids = {
            str(portal_user.get("courierId"))
            for portal_user in users_data["users"]
            if portal_user.get("trainer") == user["username"]
        }

        return df[df["driver_id"].isin(trainer_courier_ids)]

    return df[df["driver_id"] == str(user.get("courierId"))]


def add_common_metrics(df, title):
    if df.empty:
        st.warning("Nincs megjeleníthető statisztika.")
        return

    route_count = len(df[["work_date", "driver_id", "route_id"]].drop_duplicates())
    courier_count = df["driver_id"].nunique()
    parcels_delivered = int(df["parcels_delivered"].sum())
    parcels_total = int(df["parcels_total"].sum())
    total_distance = df["total_distance_km"].sum()
    covered_distance = df["distance_covered_km"].sum()
    completion_rate = parcels_delivered / parcels_total * 100 if parcels_total else 0
    average_parcels = parcels_delivered / route_count if route_count else 0
    average_distance = covered_distance / route_count if route_count else 0

    st.subheader(title)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Futárok", courier_count)
    c2.metric("Körök", route_count)
    c3.metric("Kivitt címek", parcels_delivered)
    c4.metric("Teljesítés", f"{completion_rate:.1f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Össz. cím", parcels_total)
    c6.metric("Megtett km", f"{covered_distance:.1f}")
    c7.metric("Átlag cím/kör", f"{average_parcels:.1f}")
    c8.metric("Átlag km/kör", f"{average_distance:.1f}")

    st.caption(f"Tervezett össz. km: {total_distance:.1f}")


def aggregate_by_period(df, period):
    if df.empty:
        return df

    working_df = df.copy()

    if period == "day":
        working_df["Időszak"] = working_df["work_date"].dt.strftime("%Y-%m-%d")
    elif period == "week":
        iso = working_df["work_date"].dt.isocalendar()
        working_df["Időszak"] = (
            iso["year"].astype(str)
            + "-W"
            + iso["week"].astype(str).str.zfill(2)
        )
    else:
        working_df["Időszak"] = working_df["work_date"].dt.strftime("%Y-%m")

    grouped = working_df.groupby(
        ["Időszak", "driver_id", "driver_name"],
        dropna=False,
    ).agg(
        Körök=("route_id", "nunique"),
        Kivitt_címek=("parcels_delivered", "sum"),
        Össz_cím=("parcels_total", "sum"),
        Megtett_km=("distance_covered_km", "sum"),
        Tervezett_km=("total_distance_km", "sum"),
    ).reset_index()

    grouped["Teljesítés %"] = grouped.apply(
        lambda row: row["Kivitt_címek"] / row["Össz_cím"] * 100 if row["Össz_cím"] else 0,
        axis=1,
    )
    grouped["Cím/kör"] = grouped.apply(
        lambda row: row["Kivitt_címek"] / row["Körök"] if row["Körök"] else 0,
        axis=1,
    )
    grouped["Km/kör"] = grouped.apply(
        lambda row: row["Megtett_km"] / row["Körök"] if row["Körök"] else 0,
        axis=1,
    )

    grouped = grouped.rename(
        columns={
            "driver_id": "Courier ID",
            "driver_name": "Futár",
            "Kivitt_címek": "Kivitt címek",
            "Össz_cím": "Össz. cím",
            "Megtett_km": "Megtett km",
            "Tervezett_km": "Tervezett km",
        }
    )

    return grouped.sort_values(["Időszak", "Futár"], ascending=[False, True])


def show_period_table(df, period, title):
    st.subheader(title)

    period_df = aggregate_by_period(df, period)

    if period_df.empty:
        st.warning("Nincs adat ehhez a bontáshoz.")
        return

    st.dataframe(period_df, use_container_width=True, hide_index=True)


def show_statistics_page():
    st.title("Statisztika")

    user = st.session_state["user"]

    try:
        records = read_route_statistics()
    except Exception as exc:
        st.error(f"Nem sikerült beolvasni a Google Sheet statisztikát: {exc}")
        return

    df = prepare_dataframe(records)
    df = filter_dataframe_by_user(df, user)

    if df.empty:
        st.warning(
            "Még nincs statisztikai adat. Nyisd meg a Mai futárok oldalt, hogy a rendszer elkezdje tölteni a Route_Statistics fület."
        )
        return

    if user["role"] == "admin":
        metric_title = "Céges KPI"
    elif user["role"] == "trainer":
        metric_title = "Csapat KPI"
    else:
        metric_title = "Saját KPI"

    add_common_metrics(df, metric_title)

    st.divider()

    tab_day, tab_week, tab_month, tab_raw = st.tabs(
        ["Napi", "Heti", "Havi", "Nyers adatok"]
    )

    with tab_day:
        show_period_table(df, "day", "Napi bontás")

    with tab_week:
        show_period_table(df, "week", "Heti bontás")

    with tab_month:
        show_period_table(df, "month", "Havi bontás")

    with tab_raw:
        st.dataframe(
            df.sort_values(["work_date", "driver_name"], ascending=[False, True]),
            use_container_width=True,
            hide_index=True,
        )
