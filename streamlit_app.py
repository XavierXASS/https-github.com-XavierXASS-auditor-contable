import streamlit as st
import pandas as pd
import re
import time
import base64
from io import BytesIO

# --- CONFIGURACIÓN V46: PROTOCOLO DE CARGA ESCALONADA ---
st.set_page_config(page_title="AUDITORÍA BATCH V46", layout="wide")

# Inicialización de estados persistentes
if 'db' not in st.session_state: st.session_state.db = {} # Hallazgos acumulados
if 'lote_actual' not in st.session_state: st.session_state.lote_actual = 0
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ---
if not st.session_state.auth:
    st.title("🔐 Terminal Forense - Acceso Restringido")
    pw = st.text_input("Clave Maestra:", type="password")
    if st.button("ACCEDER"):
        if pw == "PERITO_EMAPAG_2025":
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- UTILIDADES TÉCNICAS ---
def clean_id(t): return re.sub(r'\D', '', str(t))

def display_pdf(file):
    file.seek(0)
    base64_pdf = base64.b64encode(file.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)
    file.seek(0)

# --- INTERFAZ ---
st.title("🛡️ Auditoría Forense 3T-2025: Procesamiento por Lotes")

with st.sidebar:
    st.header("📂 Carga Masiva (175+ PDFs)")
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    pdf_files = st.file_uploader("2. Universo de PDFs", type=["pdf"], accept_multiple_files=True)
    
    tamaño_lote = st.slider("Tamaño del Lote de Trabajo", 5, 20, 10)
    
    if st.button("🗑️ REINICIAR TODA LA PERICIA"):
        st.session_state.clear()
        st.rerun()

if ex_file and pdf_files:
    # 1. Indexación Silenciosa (Antigravity)
    pdf_repo = {clean_id(f.name): f for f in pdf_files}
    df = pd.read_excel(ex_file)
    
    # Identificar columna CP
    c_cp = next((c for c in df.columns if 'CP' in str(c).upper() or 'PAGO' in str(c).upper()), df.columns[0])
    
    total_registros = len(df)
    total_lotes = (total_registros // tamaño_lote) + (1 if total_registros % tamaño_lote != 0 else 0)

    # --- BARRA DE PROGRESO Y CONTADORES ---
    st.subheader(f"📊 Progreso Global: {len(st.session_state.db)} de {total_registros} procesados")
    progreso = len(st.session_state.db) / total_registros
    st.progress(progreso)
    
    # --- VISOR DE LOTES ---
    col_nav, col_status = st.columns([2, 1])
    with col_nav:
        lote_sel = st.number_input(f"Trabajando en Lote (1 a {total_lotes})", 1, total_lotes, st.session_state.lote_actual + 1)
        st.session_state.lote_actual = lote_sel - 1
    
    inicio = st.session_state.lote_actual * tamaño_lote
    fin = min(inicio + tamaño_lote, total_registros)
    df_lote = df.iloc[inicio:fin]

    with col_status:
        st.info(f"Mostrando registros {inicio + 1} al {fin}")

    # --- ZONA DE TRABAJO ---
    st.divider()
    idx_lote = st.selectbox("🔍 Seleccionar CP del Lote Actual:", range(len(df_lote)), 
                            format_func=lambda x: f"CP: {df_lote.iloc[x][c_cp]}")
    
    fila = df_lote.iloc[idx_lote]
    id_actual = clean_id(fila[c_cp])
    
    col_pdf, col_form = st.columns([1.5, 1])

    with col_pdf:
        st.subheader("🖼️ Visor de Evidencia")
        if id_actual in pdf_repo:
            display_pdf(pdf_repo[id_actual])
        else:
            st.error(f"❌ HALLAZGO: CP {id_actual} SIN RESPALDO PDF")

    with col_form:
        st.subheader("🖋️ Veredicto de Auditoría")
        st.write(fila.dropna())
        
        # Estado actual si ya fue revisado
        estado_previo = st.session_state.db.get(id_actual, {"status": "PENDIENTE", "obs": ""})
        
        with st.form(f"form_{id_actual}"):
            res = st.radio("Resultado:", ["OK", "ERROR EN RUC", "ERROR EN MONTO", "ERROR EN FECHA", "SIN PDF", "OTRO"], 
                           index=0 if estado_previo['status'] == "PENDIENTE" else ["OK", "ERROR EN RUC", "ERROR EN MONTO", "ERROR EN FECHA", "SIN PDF", "OTRO"].index(estado_previo['status']) if estado_previo['status'] in ["OK", "ERROR EN RUC", "ERROR EN MONTO", "ERROR EN FECHA", "SIN PDF", "OTRO"] else 5)
            nota = st.text_area("Detalle del Hallazgo:", value=estado_previo['obs'])
            
            if st.form_submit_button("💾 GUARDAR Y CONTINUAR"):
                st.session_state.db[id_actual] = {"status": res, "obs": nota}
                st.success(f"CP {id_actual} guardado con éxito.")
                time.sleep(0.5)
                st.rerun()

    # --- BITÁCORA ACUMULATIVA (HISTORIAL) ---
    st.divider()
    with st.expander("📜 Bitácora de Hallazgos Acumulados", expanded=False):
        if st.session_state.db:
            bitacora_df = pd.DataFrame.from_dict(st.session_state.db, orient='index').reset_index()
            bitacora_df.columns = ['ID_CP', 'ESTADO', 'OBSERVACIÓN']
            st.table(bitacora_df.tail(10)) # Muestra los últimos 10 para no saturar
        else:
            st.write("No hay revisiones aún.")

    # --- REPORTE FINAL ---
    if st.button("📄 GENERAR INFORME FINAL (EXCEL)"):
        df_final = df.copy()
        df_final['ESTADO_PERICIAL'] = df_final[c_cp].apply(lambda x: st.session_state.db.get(clean_id(x), {}).get('status', 'NO REVISADO'))
        df_final['HALLAZGOS'] = df_final[c_cp].apply(lambda x: st.session_state.db.get(clean_id(x), {}).get('obs', ''))
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False)
        
        st.download_button("📥 Descargar Informe Completo", output.getvalue(), "Informe_Forense_Final.xlsx")
        st.balloons()

else:
    st.info("👋 Xavier, cargue la matriz y los 175 PDFs para iniciar el proceso por lotes.")
