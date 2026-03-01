import streamlit as st
import pandas as pd
import re
import base64
import os
import time
from io import BytesIO

# --- PROTOCOLO ANTIGRAVITY V52: MÁXIMA SEGURIDAD PERICIAL ---
st.set_page_config(page_title="TERMINAL PERICIAL XAVIER V52", layout="wide")

DB_FILE = "pericia_segura_3T.csv"

def save_disk(data):
    pd.DataFrame.from_dict(data, orient='index').to_csv(DB_FILE)

def load_disk():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE, dtype={'CP': str}).set_index('CP').to_dict('index')
    return {}

if 'db' not in st.session_state: st.session_state.db = load_disk()
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ALPHABET ---
if not st.session_state.auth:
    st.title("🔐 Terminal Forense Xavier - Certificación Alphabet")
    if st.text_input("Credencial Maestra:", type="password") == "PERITO_EMAPAG_2025":
        if st.button("DESBLOQUEAR SISTEMA"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

def clean_id(t): return re.sub(r'\D', '', str(t))

# --- SIDEBAR Y CONTROL DE CARGA ---
with st.sidebar:
    st.header("📂 Insumos del Peritaje")
    ex_file = st.file_uploader("1. Matriz Excel (3T-2025)", type=["xlsx"])
    pdf_files = st.file_uploader("2. Universo de PDFs (175+)", type=["pdf"], accept_multiple_files=True)
    
    st.divider()
    lote_size = st.number_input("Registros por Lote", 5, 20, 10)
    
    if st.button("🗑️ BORRAR TODO Y REINICIAR"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.session_state.clear()
        st.rerun()

if ex_file and pdf_files:
    # Indexación Antigravity (Cero latencia)
    t_idx_start = time.time()
    pdf_repo = {clean_id(f.name): f for f in pdf_files}
    df = pd.read_excel(ex_file)
    c_cp = next((c for c in df.columns if 'CP' in str(c).upper() or 'PAGO' in str(c).upper()), df.columns[0])
    t_idx_end = time.time() - t_idx_start

    # --- MONITOR DE DESEMPEÑO ---
    st.subheader("🚀 Monitor de Proceso Antigravity")
    m1, m2, m3 = st.columns(3)
    m1.metric("Status", "SISTEMA ESTABLE")
    m2.metric("Latencia Indexación", f"{t_idx_end:.4f}s")
    m3.metric("Auditados", f"{len(st.session_state.db)} / {len(df)}")

    # --- NAVEGACIÓN DE LOTES ---
    num_lotes = (len(df) // lote_size) + (1 if len(df) % lote_size != 0 else 0)
    lote_sel = st.number_input(f"Lote Actual (1 a {num_lotes})", 1, num_lotes, value=1)
    
    inicio = (lote_sel - 1) * lote_size
    fin = min(inicio + lote_size, len(df))
    df_lote = df.iloc[inicio:fin]

    # --- TABS: LA "OTRA PANTALLA" QUE PEDISTE ---
    tab_auditoria, tab_parcial = st.tabs(["🎯 ESTACIÓN DE TRABAJO", "📋 REPORTE PARCIAL (OTRA PANTALLA)"])

    with tab_auditoria:
        idx_l = st.selectbox("Seleccione CP a auditar:", range(len(df_lote)), 
                             format_func=lambda x: f"CP: {df_lote.iloc[x][c_cp]} (Fila {inicio+x+1})")
        
        fila = df_lote.iloc[idx_l]
        id_actual = clean_id(fila[c_cp])
        
        c_pdf, c_form = st.columns([1.6, 1])

        with c_pdf:
            st.write(f"### 🖼️ Visor de Soporte (CP: {id_actual})")
            if id_actual in pdf_repo:
                f = pdf_repo[id_actual]
                f.seek(0)
                b64 = base64.b64encode
