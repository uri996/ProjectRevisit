import streamlit as st

from backend.services import application as application_module


@st.cache_resource
def application():
    return application_module.create_application()
