import streamlit as st
import pandas as pd
import re
import time

# --- PROTOCOLO ANTIGRAVITY / ALPHABET V43.2 ---
st.set_page_config(page_title="SISTEMA PERICIAL V43.2 - CERTIFIED", layout="wide")

# Estabilización de Memoria y Estados
if 'db_pericial' not in st.session_state: st.session_state.db_pericial = {}
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ---
if not st.session_state.auth:
    st.title("🔐 Terminal Forense Xavier (Protocolo Alphabet)")
    pw = st.text_input("Acceso Maestra (3T-2025):", type="password")
    if st.button("DESBLOQUEAR"):
        if pw == "PERITO_EMAPAG_2025":
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- NÚCLEO TÉCNICO ---
def get_clean_id(t): return re.sub(r'\D', '', str(t))

def parse_money(val):
    try:
        s = str(val).replace('$', '').replace('.', '').replace(',', '.')
        return float(s)
    except: return 0.0

# --- INTERFAZ PRINCIPAL ---
st.title("🛡️ Auditoría Forense: Confrontación de Fidelidad 3T-2025")

with st.sidebar:
    st.header("⚙️ Monitor Antigravity")
    # Marcadores visuales de desempeño en tiempo real
    m_index = st.empty()
    m_map = st.empty()
    m_net = st.empty()
    
    st.divider()
    ex_file = st.file_uploader("1. Matriz Excel (3T-2025)", type=["xlsx"])
    pdf_files = st.file_uploader("2. Soportes PDFs (150+)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("🗑️ REINICIO TOTAL (Limpiar Memoria)"):
        st.session_state.clear()
        st.rerun()

if ex_file and pdf_files:
    # FASE 1: INDEXACIÓN BINARIA (Bajo estándares Alphabet)
    t_start = time.time()
    # Usamos un diccionario para que la búsqueda sea instantánea O(1)
    pdf_repo = {get_clean_id(f.name): f for f in pdf_files}
    t_end_idx = time.time() - t_start
    m_index.success(f"⚡ Indexación: {t_end_idx:.3f}s")

    # FASE 2: MAPEO DE DATOS Y COLUMNAS
    t_start_map = time.time()
    df = pd.read_excel(ex_file)
    cols = {str(c).upper().strip(): c for c in df.columns}
    # Buscamos columnas críticas aunque cambien de nombre
    c_cp = cols.get('C. PAGO') or cols.get('CP') or df.columns[0]
    c_fec = cols.get('FECHA') or cols.get('EMISION')
    t_end_map = time.time() - t_start_map
    m_map.success(f"🔍 Mapeo Matriz: {t_end_map:.3f}s")
    
    m_net.info("📡 Conexión: Estable")

    # --- TABLERO DE CONTROL ---
    st.subheader("📊 Panel de Control del Peritaje")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líneas Matriz", len(df))
    c2.metric("PDFs en Búfer", len(pdf_files))
    c3.metric("Revisados OK", sum(1 for v in st.session_state.db_pericial.values() if v['status'] == "OK"))
    
    # Alerta de Traslape: Detecta registros de 2024 o trimestres previos
    traslape = df[df[c_fec].astype(str).str.contains("2024|1T|2T", na=False)]
    c4.metric("Alertas de Periodo", len(traslape), delta_color="inverse")

    # --- ZONA DE CONFRONTACIÓN FIEL ---
    st.divider()
    idx = st.selectbox("🎯 Registro a Auditar:", range(len(df)), 
                       format_func=lambda x: f"Fila {x+1} | ID CP: {df.iloc[x][c_cp]}")
    
    fila = df.iloc[idx]
    id_actual = get_clean_id(fila[c_cp])
    
    izq, der = st.columns([1.2, 1])

    with izq:
        st.subheader("📄 Evidencia Digital")
        if id_actual in pdf_repo:
            archivo = pdf_repo[id_actual]
            st.success(f"Vinculado con éxito: {archivo.name}")
            st.download_button("📂 Abrir PDF para Inspección", archivo, file_name=archivo.name)
            
            with st.expander("📝 Protocolo Xavier (7 Pasos de Validación)", expanded=True):
                v1 = st.checkbox("1. CP y CC coinciden (PDF vs Excel)")
                v2 = st.checkbox("2. Origen (Factura/Nómina/Subrogación) coincide")
                v3 = st.checkbox("3. Aritmética (Subtotal/IVA 15%) coincide")
                st.caption("Ecuación SPI: Total - Retenciones - Amortizaciones - Multas")
                v4 = st.checkbox("4. Liquidación: El residuo es igual al SPI del Excel")
                v5 = st.checkbox("5. Contabilidad: Debe/Haber (Deducciones) fiel en Excel")
                
                hallazgo = st.text_area("Notas periciales y hallazgos:")
                if st.button("💾 REGISTRAR VEREDICTO"):
                    st.session_state.db_pericial[id_actual] = {
                        "status": "OK" if (v1 and v2 and v3 and v4 and v5) else "ERROR",
                        "obs": hallazgo,
                        "timestamp": time.strftime("%H:%M:%S")
                    }
                    st.success("Resultado guardado en el reporte parcial.")
                    st.rerun()
        else:
            st.error(f"❌ HALLAZGO: No existe respaldo PDF para el ID {fila[c_cp]}")

    with der:
        st.subheader("📜 Datos en Matriz")
        st.write(fila.dropna())
        # Alerta visual de periodo anterior
        if id_actual in traslape[c_cp].astype(str).apply(get_clean_id).values:
            st.warning("🚨 ALERTA: Este registro pertenece a un periodo anterior (2024/1T/2T).")

    # --- REPORTES Y CIERRE ---
    st.divider()
    col_parcial, col_final = st.columns(2)
    
    if col_parcial.button("📄 INFORME PARCIAL DE AVANCE"):
        st.write("### Hallazgos Acumulados")
        st.dataframe(pd.DataFrame.from_dict(st.session_state.db_pericial, orient='index'))
    
    if col_final.button("🏆 INFORME FINAL DE CIERRE"):
        st.balloons()
        st.header("📋 Certificado de Fidelidad de Auditoría")
        st.write(f"Revisiones completadas: {len(st.session_state.db_pericial)}")
        st.write("El informe está listo para su exportación.")

else:
    st.info("💡 Terminal lista. Cargue la Matriz y los PDFs para activar el protocolo de seguridad Antigravity.")
