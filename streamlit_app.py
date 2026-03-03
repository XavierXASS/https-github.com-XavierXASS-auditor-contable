import streamlit as st
import pandas as pd

st.set_page_config(page_title="Terminal de Emergencia - Pericia", layout="wide")

st.title("Terminal de Emergencia - Pericia Xavier")

# --- Uploader de Excel ---
uploaded_xlsx = st.file_uploader(
    "Sube tu matriz en Excel (.xlsx)",
    type=["xlsx"],
    key="uploader_excel",
    accept_multiple_files=False,
    help="Límite recomendado 200 MB por archivo"
)

if uploaded_xlsx is not None:
    with st.spinner("Leyendo archivo…"):
        try:
            # Lee la primera hoja por defecto
            df = pd.read_excel(uploaded_xlsx, engine="openpyxl")
            st.success(f"Archivo recibido: {uploaded_xlsx.name} | Filas: {len(df):,} | Columnas: {len(df.columns)}")
            # Vista previa (primeras 20 filas)
            st.subheader("Vista previa")
            st.dataframe(df.head(20), use_container_width=True)

            # Info rápida de columnas (útil para validar nombres escritos)
            st.subheader("Columnas detectadas")
            st.write(list(df.columns))

        except Exception as e:
            st.error(f"Ocurrió un error leyendo el Excel: {e}")
else:
    st.info("Carga tu matriz en la sección de la izquierda para ver la vista previa.")
``
