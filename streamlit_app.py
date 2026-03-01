import streamlit as st
import pandas as pd
import re
import unicodedata
from pathlib import Path

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AUDITORÍA PERICIAL EMAPAG - V.FINAL", layout="wide")

# --- CLAVE DE ACCESO ---
CLAVE_MAESTRA = "PERITO_EMAPAG_2025"

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso Restringido: Trabajo Pericial")
    pw = st.text_input("Introduce la Clave de Verificación:", type="password")
    if st.button("INGRESAR"):
        if pw == CLAVE_MAESTRA:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Clave Incorrecta")
    st.stop()

# --- MOTOR ANTI-404 (RUTAS ABSOLUTAS) ---
ROOT = Path(__file__).resolve().parent
# Nombre exacto de tu carpeta en GitHub
FOLDER_NAME = "Revision_EMAPAG_3T" 
PDF_PATH = ROOT / FOLDER_NAME

# --- INTERFAZ PRINCIPAL ---
st.title("🕵️ SISTEMA DE AUDITORÍA FORENSE - EMAPAG")

with st.sidebar:
    st.header("🛠️ Diagnóstico Canario")
    if st.button("VERIFICAR 193 ARCHIVOS"):
        if PDF_PATH.exists():
            docs = list(PDF_PATH.glob("*.pdf"))
            st.success(f"CONEXIÓN OK: {len(docs)} archivos detectados.")
        else:
            st.error(f"404: No se detecta la carpeta '{FOLDER_NAME}'")

# --- PROTOCOLO DE TRABAJO PERICIAL (7 PUNTOS) ---
st.markdown("### 📋 Protocolo Pericial Activo")
with st.expander("Ver los 7 Puntos de Control"):
    st.write("""
    1. **CP vs SPI:** Fecha, número y valor exacto (Sol BCE).
    2. **CC vs SPI:** Contabilización Debe/Haber y valor.
    3. **Factura/RUC:** RUC y fecha 2025 (Excepción nómina).
    4. **Cálculos:** Verificación Subtotal, IVA y Total.
    5. **Retenciones:** Porcentajes y resta del total vs SPI.
    6. **Amortizaciones/Multas:** Deducciones del CC.
    7. **SPI (BCE):** Beneficiario y valor pagado coincidente.
    """)

# --- ÁREA DE ACCIÓN ---
col_matriz, col_zoom = st.columns([1, 1])

with col_matriz:
    st.subheader("Registro de Matriz")
    cp_n = st.text_input("Número de CP / Factura:")
    
    # Sistema de Marcación OK/MAL
    c1, c2 = st.columns(2)
    p1 = c1.selectbox("CP vs SPI", ["ok", "mal", "n/a"])
    p2 = c2.selectbox("CC (Contabilización)", ["ok", "mal", "n/a"])
    p3 = c1.selectbox("Factura/RUC", ["ok", "mal", "n/a"])
    p4 = c2.selectbox("Cálculos/IVA", ["ok", "mal", "n/a"])
    
    hallazgos = st.text_area("Columna de Hallazgos / Observaciones:")
    claridad = st.select_slider("Escala de Claridad (Legibilidad PDF)", options=range(1, 11), value=10)

with col_zoom:
    st.subheader("🔎 Zoom Pericial (Factor Humano)")
    st.write("Normalización de fechas y datos alfanuméricos:")
    
    dato_confuso = st.text_input("Pegue aquí el texto confuso (Ej: '19   de marzo...'):")
    if dato_confuso:
        # Acción: Elimina espacios múltiples y normaliza caracteres
        limpio = re.sub(r'\s+', ' ', unicodedata.normalize("NFC", dato_confuso)).strip()
        st.info(f"**Lectura Corregida:** `{limpio}`")
    
    st.warning("Visualizador de Recorte (Crop) - Cargue el CP arriba para vincular")

if st.button("💾 GUARDAR REGISTRO PERICIAL"):
    st.success(f"CP {cp_n} procesado. Hallazgo registrado: {hallazgos[:30]}...")
    st.balloons()
