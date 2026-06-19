import streamlit as st
import pandas as pd

st.title("Driver Search")

search_type = st.radio(
    "Keresés típusa",
    ["Driver ID", "Driver Name"]
)

search_value = st.text_input("Keresett érték")

col1, col2 = st.columns(2)

with col1:
    start_date = st.date_input("Kezdő dátum")

with col2:
    end_date = st.date_input("Záró dátum")

available_columns = [
    "Driver ID",
    "Driver Name",
    "Orders",
    "Earnings",
    "Tip",
    "Hours"
]

selected_columns = st.multiselect(
    "Megjelenítendő oszlopok",
    available_columns,
    default=["Driver ID", "Driver Name"]
)

if st.button("Keresés"):

    df = pd.read_csv("drivers.csv")

    if search_type == "Driver ID":
        result = df[
            df["Driver ID"]
            .astype(str)
            .str.contains(search_value, case=False)
        ]
    else:
        result = df[
            df["Driver Name"]
            .str.contains(search_value, case=False)
        ]

    result = result[
        (pd.to_datetime(result["Date"]).dt.date >= start_date)
        &
        (pd.to_datetime(result["Date"]).dt.date <= end_date)
    ]

    st.dataframe(result[selected_columns])