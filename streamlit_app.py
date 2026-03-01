import streamlit as st
import pandas as pd
import re
from pathlib import Path

# --- CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="PERICIA FORENSE EMAPAG 3T", layout="wide")
CLAVE = "PERITO_EMAPAG_2025"

# --- BLOQUE DE SEGURIDAD ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso Sistema Pericial")
    if st.text_input("Clave Maestra:", type="password") == CLAVE:
        if st.button("DESBLOQUEAR"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- INTERFAZ DE CARGA ---
st.title("🕵️ PANEL DE CONTROL PERICIAL - EMAPAG 3T")

with st.sidebar:
    st.header("📂 Insumos del Cuatrimestre")
    archivo_excel = st.file_uploader("1. Matriz (.xlsx)", type=["xlsx"])
    archivos_pdf = st.file_uploader("2. Comprobantes (PDFs)", type=["pdf"], accept_multiple_files=True)

# --- CEREBRO PERICIAL ---
if archivo_excel and archivos_pdf:
    df = pd.read_excel(archivo_excel)
    pdfs_dict = {f.name: f for f in archivos_pdf}
    
    # --- PANEL DE RESULTADOS RÁPIDOS (REVISIÓN PARCIAL) ---
    st.subheader("⚡ Estado de la Pericia en Tiempo Real")
    c1, c2, c3, c4 = st.columns(4)
    
    # Lógica de Triangulación (Regla 1)
    # Asumimos columnas: 'CP', 'CC', 'SPI', 'AMORTIZACION' (Ajustar nombres si varían)
    df['DIFERENCIA'] = df.apply(lambda r: abs((r.get('CP', 0) - r.get('AMORTIZACION', 0)) - r.get('SPI', 0)), axis=1)
    cuadra = df[df['DIFERENCIA'] < 0.01]
    hallazgos_v = df[df['DIFERENCIA'] >= 0.01]
    
    # Lógica de Integridad (Regla 2)
    vinculados = [cp for cp in df['C. PAGO'].astype(str) if any(cp in n for n in pdfs_dict.keys())]
    
    c1.metric("Registros Matriz", len(df))
    c2.metric("PDFs Cargados", len(archivos_pdf))
    c3.metric("Triangulación OK", f"{len(cuadra)}")
    c4.metric("Archivos Vinculados", f"{len(vinculados)}")

    # --- LISTA DE HALLAZGOS CRÍTICOS (REGLA 1 ESPECIAL) ---
    if len(hallazgos_v) > 0:
        with st.expander("🚨 ALERTAS DE TRIANGULACIÓN (CP vs CC vs SPI)"):
            st.write("Registros donde el valor pagado no coincide (descontando amortizaciones):")
            st.dataframe(hallazgos_v[['C. PAGO', 'BENEFICIARIO', 'DIFERENCIA']])

    # --- ZOOM PERICIAL Y REVISIÓN LÍNEA A LÍNEA ---
    st.divider()
    idx = st.selectbox("🔍 Seleccione Registro para Inspección Documental:", range(len(df)))
    fila = df.iloc[idx]
    cp_num = str(fila.get('C. PAGO', ''))
    
    col_pdf, col_form = st.columns([1, 1])
    
    with col_pdf:
        match = next((n for n in pdfs_dict.keys() if cp_num in n), None)
        if match:
            st.success(f"Archivo: {match}")
            st.download_button("📂 Abrir Evidencia", pdfs_dict[match], file_name=match)
        else:
            st.error(f"❌ DOCUMENTO NO ENCONTRADO para CP {cp_num}")

    with col_form:
        st.info(f"**Validación de Datos - CP {cp_num}**")
        st.write(f"Beneficiario: {fila.get('BENEFICIARIO', 'N/A')}")
        
        # Zoom de normalización
        zoom_txt = st.text_input("Normalizar texto confuso (Ej. Fecha/RUC):")
        if zoom_txt:
            limpio = re.sub(r'\s+', ' ', zoom_txt).strip()
            st.code(f"Dato Normalizado: {limpio}")

    # --- GENERADOR DE INFORME FINAL ---
    st.divider()
    if st.button("📝 GENERAR INFORME PERICIAL FINAL"):
        st.markdown("### INFORME DE HALLAZGOS - EMAPAG 3T 2025")
        st.write(f"- **Integridad:** Se detectaron {len(df) - len(vinculados)} registros sin respaldo PDF.")
        st.write(f"- **Financiero:** {len(hallazgos_v)} inconsistencias en la triangulación de pagos.")
        st.write(f"- **Periodo:** {len(df[df.astype(str).apply(lambda x: x.str.contains('2026')).any(axis=1)])} registros con error de año (2026).")
        st.balloons()

else:
    st.warning("📥 Esperando subida de Matriz y PDFs para iniciar peritaje...")
