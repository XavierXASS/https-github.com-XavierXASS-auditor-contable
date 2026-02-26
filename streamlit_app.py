import streamlit as st
import pandas as pd

st.set_page_config(page_title="Auditor Xavier", layout="wide")
st.title("🛡️ Auditor Contable Inteligente")
st.write("---")

st.info("Sistema listo. Por favor, carga tus archivos en el panel de la izquierda.")

# Panel lateral
with st.sidebar:
    st.header("Carga de Datos")
    excel = st.file_uploader("Subir Matriz Excel", type=["xlsx"])
    pdfs = st.file_uploader("Subir PDFs", type=["pdf"], accept_multiple_files=True)

if excel and pdfs:
    st.success(f"Archivos cargados: Excel y {len(pdfs)} PDFs. Listo para procesar.")
    if st.button("🚀 INICIAR AUDITORÍA"):
        st.write("Procesando... (Esta es una versión de prueba)")
