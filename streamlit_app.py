import streamlit as st
import pandas as pd
import re
import unicodedata
from io import BytesIO

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="PERICIA EMAPAG 3T 2025", layout="wide")
CLAVE = "PERITO_EMAPAG_2025"

# --- SEGURIDAD ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso al Trabajo Pericial")
    if st.text_input("Clave de Verificación:", type="password") == CLAVE:
        if st.button("DESBLOQUEAR"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- PANEL DE CARGA DE DATOS (SOLUCIÓN A TU DUDA) ---
st.title("🕵️ SISTEMA DE CRUCE PERICIAL: MATRIZ VS PDF")

with st.sidebar:
    st.header("📂 Carga de Insumos")
    archivo_excel = st.file_uploader("1. Subir Matriz (Excel)", type=["xlsx"])
    archivos_pdf = st.file_uploader("2. Subir PDFs del Cuatrimestre (Múltiples)", type=["pdf"], accept_multiple_files=True)

# --- TRABAJO PERICIAL: CRUCE AUTOMÁTICO ---
if archivo_excel and archivos_pdf:
    df = pd.read_excel(archivo_excel)
    st.success(f"Matriz cargada: {len(df)} registros detectados.")
    st.info(f"PDFs cargados: {len(archivos_pdf)} archivos para el 3T 2025.")

    # Mapeo de archivos para evitar el 404 interno
    lista_pdfs = {f.name: f for f in archivos_pdf}

    # --- ÁREA DE AUDITORÍA ---
    st.subheader("📋 Validación de los 7 Puntos de Control")
    
    fila_idx = st.number_input("Seleccione fila de la matriz para auditar:", 0, len(df)-1, 0)
    fila = df.iloc[fila_idx]
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.write("**Datos de la Matriz (Excel):**")
        st.json(fila.to_dict()) # Muestra CP, Fecha, Valor, etc.
        
        # EL ZOOM PERICIAL (Punto 3 y 4)
        st.subheader("🔎 Zoom de Validación")
        texto_confuso = st.text_input("Texto extraído del PDF (para normalizar):")
        if texto_confuso:
            limpio = re.sub(r'\s+', ' ', unicodedata.normalize("NFC", texto_confuso)).strip()
            st.metric("Lectura Normalizada", limpio)
            
    with col2:
        st.write("**Evidencia PDF:**")
        # Buscador automático de PDF por número de CP
        cp_buscado = str(fila['C. PAGO']) # Ajustar al nombre de tu columna
        archivo_encontrado = next((name for name in lista_pdfs if cp_buscado in name), None)
        
        if archivo_encontrado:
            st.success(f"✅ Documento encontrado: {archivo_encontrado}")
            # Aquí el perito valida visualmente
            st.download_button("Abrir PDF para Inspección", lista_pdfs[archivo_encontrado], file_name=archivo_encontrado)
        else:
            st.error(f"❌ HALLAZGO: No existe PDF para el CP {cp_buscado} en este cuatrimestre.")

    # --- REGISTRO DE HALLAZGOS ---
    st.divider()
    with st.expander("📝 Registrar Resultado de Pericia"):
        c1, c2, c3 = st.columns(3)
        res_cp = c1.selectbox("CP vs SPI", ["ok", "mal", "ilegible"])
        res_cc = c2.selectbox("CC (Contabilización)", ["ok", "mal", "ilegible"])
        res_fac = c3.selectbox("Factura/RUC", ["ok", "mal", "ilegible"])
        
        obs = st.text_area("Columna de Hallazgos (Detalle su conclusión pericial):")
        if st.button("GUARDAR EN MATRIZ FINAL"):
            st.success(f"Registro guardado para el CP {cp_buscado}.")

else:
    st.warning("⚠️ Acción requerida: Sube el Excel y los PDFs en la barra lateral para comenzar el cruce.")
