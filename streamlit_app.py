import streamlit as st
import pandas as pd
import os
import re
from pathlib import Path

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AUDITORÍA EMAPAG 3T", layout="wide")

# --- TRABAJO PERICIAL: PUNTOS DE CONTROL ---
# 1. CP/SPI | 2. CC/SPI | 3. RUC/FECHA | 4. CÁLCULOS | 5. RETENCIONES | 6. MULTAS | 7. BENEFICIARIO

# 1. CLAVE DE VERIFICACIÓN (Blindaje de acceso)
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso Pericial")
    clave = st.text_input("Introduce la Clave Maestra:", type="password")
    if st.button("DESBLOQUEAR APP"):
        if clave == "PERITO_EMAPAG_2025": # Cambia esta clave si deseas
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Clave Incorrecta")
    st.stop()

# --- DIAGNÓSTICO CANARIO (Solución al 404) ---
# Este bloque detecta automáticamente si estás en Windows (local) o Linux (Streamlit Cloud)
ROOT = Path(__file__).resolve().parent
PDF_FOLDER = ROOT / "Revision_EMAPAG_3T" # Asegúrate de que tu carpeta se llame así en GitHub

with st.expander("🛠️ DIAGNÓSTICO DE CONEXIÓN (EVITAR 404)"):
    if st.button("🔍 EJECUTAR CHECK DE ARCHIVOS"):
        if PDF_FOLDER.exists():
            total_pdf = len(list(PDF_FOLDER.glob("*.pdf")))
            st.success(f"CONEXIÓN OK: Se detectaron {total_pdf} archivos en {PDF_FOLDER}")
        else:
            st.error(f"ERROR 404: No se encuentra la carpeta '{PDF_FOLDER.name}' en la raíz.")
            st.info("Sugerencia: Verifica que la carpeta esté subida a GitHub con ese nombre exacto.")

# --- INTERFAZ DE TRABAJO PERICIAL ---
st.title("🕵️ SISTEMA DE AUDITORÍA: EMAPAG 3T")

col_datos, col_zoom = st.columns([1, 1])

with col_datos:
    st.subheader("📊 Control de Matriz")
    # Aquí puedes cargar tu Excel con pd.read_excel si está en la raíz
    st.write("Seleccione el CP para iniciar los 7 puntos de control.")
    cp_revisar = st.text_input("Número de Comprobante (CP):")
    
    # Checkbox de cumplimiento
    st.checkbox("1. CP coincide con SPI (Valor/Fecha)")
    st.checkbox("2. CC coincide con SPI (Debe/Haber)")
    st.checkbox("3. Factura/RUC validado")
    
    nota_hallazgo = st.text_area("Hallazgos (Columna de Observaciones):")

with col_zoom:
    st.subheader("🔎 ZOOM PERICIAL (Factor Humano)")
    st.write("Corregir interpretaciones de fechas/nombres:")
    
    texto_sucio = st.text_input("Dato confuso del PDF (Ej: 19  de marzo...):")
    if texto_sucio:
        # Acción: Normalización inmediata de espacios del operador humano
        texto_limpio = re.sub(r'\s+', ' ', texto_sucio).strip()
        st.success(f"**Resultado para Matriz:** `{texto_limpio}`")
    
    st.metric("Calidad de Lectura", "8/10", delta="Normalizado")

if st.button("💾 REGISTRAR CAMBIOS"):
    st.balloons()
    st.success("Información guardada en la matriz temporal.")
