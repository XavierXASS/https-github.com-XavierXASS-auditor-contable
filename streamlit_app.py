import streamlit as st
import pandas as pd
import re
import time

# --- CONFIGURACIÓN INDUSTRIAL ---
st.set_page_config(page_title="SISTEMA PERICIAL XAVIER V.FINAL", layout="wide")

# Estilo para alertas de traslape y errores
st.markdown("""
    <style>
    .alerta-trimestre { background-color: #fff3cd; padding: 10px; border-left: 5px solid #ffc107; border-radius: 5px; }
    .ok-pericial { color: #28a745; font-weight: bold; }
    .error-pericial { color: #dc3545; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- PERSISTENCIA DE DATOS ---
if 'cronometro' not in st.session_state: st.session_state.cronometro = time.time()
if 'veredictos' not in st.session_state: st.session_state.veredictos = {}
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ---
if not st.session_state.auth:
    st.title("🔐 Acceso a Terminal Pericial")
    if st.text_input("Credencial:", type="password") == "PERITO_EMAPAG_2025":
        if st.button("DESBLOQUEAR"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- FUNCIONES DE SOPORTE ---
def normalizar_id(t): return re.sub(r'\D', '', str(t))

# --- PANEL LATERAL (CARGA Y CONTROL) ---
with st.sidebar:
    st.header("📂 Insumos del Peritaje")
    excel_file = st.file_uploader("1. Matriz 3T-2025 (.xlsx)", type=["xlsx"])
    pdf_files = st.file_uploader("2. Soportes PDFs (Carga Masiva)", type=["pdf"], accept_multiple_files=True)
    
    st.divider()
    if st.button("🗑️ LIMPIAR Y NUEVA PERICIA"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# --- LÓGICA PRINCIPAL ---
if excel_file and pdf_files:
    df = pd.read_excel(excel_file)
    # Indexación por ID (CP) para evitar picos de memoria
    dict_pdfs = {normalizar_id(f.name): f for f in pdf_files}
    
    # Mapeo de columnas (Autodetect)
    c = {str(col).upper().strip(): col for col in df.columns}
    col_cp = c.get('C. PAGO') or c.get('CP') or df.columns[0]
    col_val = c.get('SPI') or c.get('VALOR') or c.get('TOTAL')
    col_fec = c.get('FECHA') or c.get('EMISION')

    # --- TABLERO DE CONTROL ---
    st.title("🛡️ Panel de Confrontación Fiel")
    t_uso = time.strftime("%H:%M:%S", time.gmtime(time.time() - st.session_state.cronometro))
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Registros Matriz", len(df))
    m2.metric("PDFs Indexados", len(pdf_files))
    m3.metric("Revisados", len(st.session_state.veredictos))
    m4.metric("Tiempo en Operación", t_uso)

    # --- SELECCIÓN DE LÍNEA ---
    st.divider()
    idx = st.selectbox("🔍 Seleccione Línea para Auditoría:", range(len(df)), 
                       format_func=lambda x: f"Fila {x+1} | ID: {df.iloc[x][col_cp]}")
    
    fila = df.iloc[idx]
    id_actual = normalizar_id(fila[col_cp])
    
    col_pdf, col_mat = st.columns([1.2, 1])

    with col_pdf:
        st.subheader("📄 Evidencia Digital")
        if id_actual in dict_pdfs:
            f = dict_pdfs[id_actual]
            st.success(f"✅ Documento Detectado: {f.name}")
            st.download_button("📂 Abrir PDF para Cotejar", f, file_name=f.name)
            
            # --- PROTOCOLO DE CONFRONTACIÓN ---
            with st.expander("📝 Ejecutar Reglas de Verificación", expanded=True):
                st.write("**Paso 1: Identidad Documental**")
                c1 = st.checkbox("CP y CC en PDF coinciden con Excel")
                
                st.write("**Paso 2: Origen (Factura / Nómina)**")
                c2 = st.checkbox("Datos (RUC/Nombre/Número) coinciden con Excel")
                
                # ALARMA DE TRASLAPE
                fecha_doc = str(fila.get(col_fec, ""))
                if any(x in fecha_doc for x in ["2024", "1T", "2T"]):
                    st.markdown(f'<div class="alerta-trimestre">⚠️ ALARMA: Documento de periodo anterior ({fecha_doc}). Verificar duplicidad.</div>', unsafe_allow_html=True)
                
                st.write("**Paso 3 & 4: Aritmética y Retenciones**")
                c3 = st.checkbox("Subtotal/IVA/Retenciones coinciden con Excel")
                
                st.write("**Paso 5: La Ecuación del SPI**")
                st.caption("Fórmula: Total - Retenciones - Amortización - Multas = SPI")
                c4 = st.checkbox("Cálculo del SPI coincide y el Beneficiario es correcto")
                
                st.write("**Paso 6 & 7: Contabilización y Cierre**")
                c5 = st.checkbox("Debe/Haber (Amortización/Multas) reflejados fielmente en Excel")
                
                obs = st.text_area("Hallazgos específicos:")
                if st.button("💾 GUARDAR VEREDICTO"):
                    st.session_state.veredictos[id_actual] = {
                        "status": "OK" if (c1 and c2 and c3 and c4 and c5) else "ERROR",
                        "nota": obs
                    }
                    st.rerun()
        else:
            st.error(f"❌ HALLAZGO: No existe soporte físico para el CP {fila[col_cp]}")

    with col_mat:
        st.subheader("📜 Datos en Matriz")
        st.write(fila.dropna())

    # --- BOTONES DE REPORTE ---
    st.divider()
    r1, r2 = st.columns(2)
    if r1.button("📄 GENERAR INFORME PARCIAL"):
        st.write("### Situación de la Revisión:")
        st.table(pd.DataFrame.from_dict(st.session_state.veredictos, orient='index'))

    if r2.button("🏆 GENERAR INFORME FINAL"):
        st.header("📋 Informe de Fidelidad Pericial")
        st.write(f"- **Integridad:** {len(st.session_state.veredictos)} de {len(df)} líneas procesadas.")
        sobrantes = [n for n in dict_pdfs.keys() if n not in df[col_cp].astype(str).apply(normalizar_id).values]
        if sobrantes:
            st.warning(f"Se detectaron {len(sobrantes)} PDFs que no figuran en la matriz.")
        st.balloons()
else:
    st.info("👋 Xavier, cargue los insumos para iniciar la auditoría forense.")
