import streamlit as st

from page.admin import show_admin_page

menu = [
    "Admin"
]

page = st.sidebar.radio(
    "Menü",
    menu
)

if page == "Admin":

    show_admin_page()