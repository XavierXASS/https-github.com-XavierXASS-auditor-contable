import streamlit as st

st.set_page_config(page_title="Prueba mínima", layout="wide")

st.title("Prueba mínima")

with st.form(key="form_auditoria", clear_on_submit=False):
    x = st.text_input("Campo X")
    ok = st.form_submit_button("Guardar")

if ok:
    st.success(f"Guardado: {x}")
