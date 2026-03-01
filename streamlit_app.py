import streamlit as st
import pandas as pd
import re
import io

# Configuración de nivel industrial
st.set_page_config(page_title="PERICIA FORENSE EMAPAG", layout="wide", initial_sidebar_state="collapsed")

# Estilo para panel de veredicto
st.markdown("""
    <style>
    .report-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .stProgress > div > div > div > div { background-color: #00cc66; }
    </style>
""", unsafe_allow_html=True)

# --- SISTEMA DE SEGURIDAD ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Terminal Pericial de Alta Seguridad")
    clave = st.text_input("Ingrese Credencial Maestra:", type="password")
    if st.button("DESBLOQUEAR SISTEMA"):
        if clave == "PERITO_EMAPAG_2025":
            st.session_state.autenticado = True
            st.rerun()
    st.stop()

# --- MOTOR DE PROCESAMIENTO ---
def extraer_id(texto):
    """Extrae solo el núcleo numérico para evitar errores de nombres de archivo."""
    return re.sub(r'\D', '', str(texto))

def auditoria_core():
    st.title("🕵️ Sistema de Confrontación Forense")
    
    col_a, col_b = st.columns([1, 2])
    
    with col_a:
        st.subheader("📁 Carga de Evidencia")
        excel_file = st.file_uploader("Matriz Excel", type=["xlsx"], key="main_excel")
        pdf_files = st.file_uploader("Universo de PDFs (Subida Masiva)", type=["pdf"], accept_multiple_files=True, key="main_pdfs")

    if excel_file and pdf_files:
        # Carga rápida de matriz
        df = pd.read_excel(excel_file)
        
        # Indexación de PDFs en memoria de alta velocidad
        # Esto evita el límite de los 21 archivos
        indice_pdfs = {extraer_id(f.name): f for f in pdf_files}
        
        # Mapeo de columnas (Autodetect)
        cols = {c.upper().strip(): c for c in df.columns}
        c_cp = cols.get('C. PAGO') or cols.get('CP') or df.columns[0]
        c_val = cols.get('SPI') or cols.get('VALOR') or cols.get('TOTAL')
        c_fecha = cols.get('FECHA') or cols.get('EMISION')

        # --- PANEL DE VEREDICTO EN TIEMPO REAL ---
        st.subheader("📊 Veredicto Progresivo de la Pericia")
        
        # Análisis de Integridad
        df['ID_LIMPIO'] = df[c_cp].apply(extraer_id)
        registros_ok = df[df['ID_LIMPIO'].isin(indice_pdfs.keys())]
        registros_faltantes = df[~df['ID_LIMPIO'].isin(indice_pdfs.keys())]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Universo Matriz", len(df))
        m2.metric("PDFs Identificados", len(pdf_files))
        m3.metric("Cruce Exitoso", len(registros_ok))
        m4.metric("Faltantes (Hallazgo)", len(registros_faltantes), delta_color="inverse")

        # Barra de fidelidad documental
        porcentaje = len(registros_ok) / len(df)
        st.progress(porcentaje)
        st.caption(f"Fidelidad del Cuatrimestre: {porcentaje*100:.1f}%")

        # --- REVISIÓN LÍNEA POR ARCHIVO ---
        st.divider()
        st.subheader("🔎 Inspección de Campo: Línea vs Realidad")
        
        seleccion = st.selectbox("Seleccione Línea de Auditoría:", range(len(df)),
                                 format_func=lambda x: f"CP: {df.iloc[x][c_cp]} | {df.iloc[x].get(c_val, '')}")
        
        fila = df.iloc[seleccion]
        id_actual = extraer_id(fila[c_cp])
        
        c_left, c_right = st.columns(2)
        
        with c_left:
            st.markdown("### 📜 Datos Matriz")
            st.json(fila.dropna().to_dict())
            
            # Alerta de Fecha 2024/2026
            if c_fecha and "2025" not in str(fila[c_fecha]):
                st.error(f"🚨 ALERTA: Fecha detectada ({fila[c_fecha]}) fuera del periodo 2025.")

        with c_right:
            st.markdown("### 📄 Evidencia Física")
            if id_actual in indice_pdfs:
                archivo = indice_pdfs[id_actual]
                st.success(f"CONFRONTADO: {archivo.name}")
                st.download_button("📂 Abrir PDF Original", archivo, file_name=archivo.name)
                
                # Checkbox de veracidad (Criterios de Pericia)
                v1 = st.checkbox("Beneficiario coincide con Factura")
                v2 = st.checkbox("Valor SPI coincide con Comprobante")
                v3 = st.checkbox("IVA y Retenciones calculados correctamente")
                
                if v1 and v2 and v3:
                    st.success("VEREDICTO: CONFORME")
            else:
                st.error("🚨 HALLAZGO: No existe respaldo físico para este registro.")

        # --- GENERADOR DE REPORTE FIEL ---
        st.divider()
        if st.button("📝 GENERAR INFORME PERICIAL FINAL"):
            st.header("📋 Informe Ejecutivo: Auditoría EMAPAG 3T")
            
            # Análisis de inconsistencias
            st.write("### 1. Inconsistencias de Inventario")
            if len(registros_faltantes) > 0:
                st.warning(f"Se encontraron {len(registros_faltantes)} líneas en la matriz sin sustento documental.")
                st.dataframe(registros_faltantes[[c_cp, c_val]])
            
            sobrantes = [n for n in indice_pdfs.keys() if n not in df['ID_LIMPIO'].values]
            if sobrantes:
                st.info(f"Se detectaron {len(sobrantes)} PDFs que NO están registrados en la matriz.")
            
            st.write("### 2. Errores de Contenido (Automatizados)")
            errores_f = df[df[c_fecha].astype(str).str.contains("2024|2026", na=False)]
            if not errores_f.empty:
                st.error(f"Hallazgo Crítico: {len(errores_f)} registros pertenecen a un año distinto al auditado.")
                st.dataframe(errores_f[[c_cp, c_fecha]])
            
            st.balloons()
            st.success("Informe de confrontación finalizado.")

    else:
        st.info("👋 Xavier, cargue los insumos para iniciar el procesamiento virtual.")

if __name__ == "__main__":
    auditoria_core()
