import streamlit as st
import pandas as pd
import re
import base64
import os
import time
from io import BytesIO

# --- V50: PROTOCOLO DE PERSISTENCIA PERICIAL ---
st.set_page_config(page_title="PERICIA EMAPAG V50", layout="wide")

DB_FILE = "progreso_pericial_3T_2025.csv"

def cargar_datos_previos():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE, dtype={'CP': str}).set_index('CP').to_dict('index')
    return {}

if 'db' not in st.session_state: st.session_state.db = cargar_datos_previos()
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ---
if not st.session_state.auth:
    st.title("🔐 Terminal de Auditoría Forense")
    if st.text_input("Credencial Maestra:", type="password") == "PERITO_EMAPAG_2025":
        if st.button("DESBLOQUEAR"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

def clean_id(t): return re.sub(r'\D', '', str(t))

# --- PANEL DE CONTROL ---
with st.sidebar:
    st.header("📂 Carga de Evidencia")
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    pdf_files = st.file_uploader("2. PDFs (Universo 175+)", type=["pdf"], accept_multiple_files=True)
    
    st.divider()
    lote_size = st.number_input("Registros por Lote", min_value=1, value=10)
    st.info(f"📑 Revisiones en Memoria: {len(st.session_state.db)}")
    
    if st.button("⚠️ BORRAR PROGRESO Y REINICIAR"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.session_state.clear()
        st.rerun()

if ex_file and pdf_files:
    # Indexación ligera (solo nombres)
    pdf_repo = {clean_id(f.name): f for f in pdf_files}
    df = pd.read_excel(ex_file)
    c_cp = next((c for c in df.columns if 'CP' in str(c).upper() or 'PAGO' in str(c).upper()), df.columns[0])
    
    # Navegación
    total = len(df)
    num_lotes = (total // lote_size) + (1 if total % lote_size != 0 else 0)
    lote_sel = st.number_input("Lote de Trabajo:", 1, num_lotes, value=1)
    
    inicio = (lote_sel - 1) * lote_size
    fin = min(inicio + lote_size, total)
    df_lote = df.iloc[inicio:fin]

    # --- ÁREA DE TRABAJO ---
    st.divider()
    idx_lote = st.selectbox("🎯 Seleccionar Registro para Confrontación:", range(len(df_lote)), 
                            format_func=lambda x: f"Fila {inicio+x+1} | CP: {df_lote.iloc[x][c_cp]}")
    
    fila = df_lote.iloc[idx_lote]
    id_actual = clean_id(fila[c_cp])
    
    col_pdf, col_form = st.columns([1.6, 1])

    with col_pdf:
        st.write(f"### 🖼️ Soporte Documental (ID: {id_actual})")
        if id_actual in pdf_repo:
            f = pdf_repo[id_actual]
            f.seek(0)
            b64 = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="750"></iframe>', unsafe_allow_html=True)
            f.seek(0)
        else:
            st.error(f"🚨 HALLAZGO: EL CP {id_actual} NO TIENE RESPALDO PDF EN CARGA.")

    with col_form:
        st.write("### 📜 Datos Matriz")
        st.dataframe(fila.dropna(), use_container_width=True)
        
        # Recuperar persistencia
        prev = st.session_state.db.get(id_actual, {"status": "OK", "obs": "", "lote": lote_sel})
        
        with st.form(f"form_auditoria_{id_actual}"):
            res = st.selectbox("Veredicto Pericial:", ["OK", "RUC ERRÓNEO", "MONTO DIFERENTE", "FECHA TRASLAPADA", "SIN SOPORTE PDF", "ERROR CONTABLE"], 
                               index=0 if prev['status'] == "OK" else ["OK", "RUC ERRÓNEO", "MONTO DIFERENTE", "FECHA TRASLAPADA", "SIN SOPORTE PDF", "ERROR CONTABLE"].index(prev['status']) if prev['status'] in ["OK", "RUC ERRÓNEO", "MONTO DIFERENTE", "FECHA TRASLAPADA", "SIN SOPORTE PDF", "ERROR CONTABLE"] else 0)
            obs = st.text_area("Notas Técnicas del Hallazgo:", value=prev['obs'])
            
            if st.form_submit_button("💾 REGISTRAR Y ASEGURAR"):
                # Guardar en RAM
                st.session_state.db[id_actual] = {"status": res, "obs": obs, "lote": lote_sel}
                # Guardar en DISCO (Archivo físico)
                pd.DataFrame.from_dict(st.session_state.db, orient='index').to_csv(DB_FILE)
                st.success(f"Registro {id_actual} asegurado en disco.")
                time.sleep(0.5)
                st.rerun()

    # --- BITÁCORA DEL LOTE (PEDIDO XAVIER) ---
    st.divider()
    st.subheader(f"📜 Bitácora de Hallazgos - Lote {lote_sel}")
    lote_data = [{"CP": k, "Estado": v['status'], "Hallazgo": v['obs']} 
                 for k, v in st.session_state.db.items() if v.get('lote') == lote_sel]
    
    if lote_data:
        st.table(pd.DataFrame(lote_data))
    else:
        st.info("No hay registros validados en este lote.")

    # --- REPORTE MAESTRO ---
    st.divider()
    if st.button("📦 CONSOLIDAR INFORME PERICIAL FINAL"):
        reporte = df.copy()
        reporte['ESTADO_PERICIAL'] = reporte[c_cp].apply(lambda x: st.session_state.db.get(clean_id(x), {}).get('status', 'NO REVISADO'))
        reporte['NOTAS_HALLAZGOS'] = reporte[c_cp].apply(lambda x: st.session_state.db.get(clean_id(x), {}).get('obs', ''))
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            reporte.to_excel(writer, index=False)
        st.download_button("📥 Descargar Matriz Auditada (Excel)", out.getvalue(), "Informe_Forense_Emapag_3T.xlsx")

else:
    st.info("Esperando carga masiva de archivos para iniciar confrontación...")
