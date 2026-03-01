import streamlit as st
import pandas as pd
import re
import time
import base64
from io import BytesIO

# --- CONFIGURACIÓN V45 ---
st.set_page_config(page_title="AUDITORÍA XAVIER V45", layout="wide")

if 'db' not in st.session_state: st.session_state.db = {}
if 'auth' not in st.session_state: st.session_state.auth = False

# --- SEGURIDAD ---
if not st.session_state.auth:
    st.title("🔐 Terminal Forense")
    pw = st.text_input("Clave:", type="password")
    if st.button("ACCEDER"):
        if pw == "PERITO_EMAPAG_2025":
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- UTILIDADES ---
def clean_id(t): return re.sub(r'\D', '', str(t))

def to_excel(df, veredictos):
    # Fusiona la matriz con los hallazgos para el informe final
    df_final = df.copy()
    # Creamos columnas de resultados
    df_final['ESTADO_PERICIAL'] = df_final.iloc[:, 0].apply(lambda x: veredictos.get(clean_id(x), {}).get('status', 'PENDIENTE'))
    df_final['HALLAZGOS_DETALLES'] = df_final.iloc[:, 0].apply(lambda x: veredictos.get(clean_id(x), {}).get('obs', ''))
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Informe_Forense')
    return output.getvalue()

# --- INTERFAZ ---
st.title("🛡️ Auditoría Forense: Confrontación y Reporte")

with st.sidebar:
    st.header("⚙️ Carga de Datos")
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    # Aumentamos estabilidad de carga masiva
    pdf_files = st.file_uploader("2. Soportes PDFs", type=["pdf"], accept_multiple_files=True)
    
    if st.button("🗑️ LIMPIAR TODO"):
        st.session_state.clear()
        st.rerun()

if ex_file and pdf_files:
    # Indexación ultrarrápida
    pdf_repo = {clean_id(f.name): f for f in pdf_files}
    df = pd.read_excel(ex_file)
    
    # Identificar columna CP
    c_cp = df.columns[0] # Por defecto la primera
    for col in df.columns:
        if 'CP' in str(col).upper() or 'PAGO' in str(col).upper():
            c_cp = col
            break

    # --- TABLERO ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Matriz", len(df))
    c2.metric("PDFs", len(pdf_files))
    c3.metric("Auditados", len(st.session_state.db))

    # --- SELECTOR ---
    idx = st.selectbox("🎯 Seleccionar Registro:", range(len(df)), 
                       format_func=lambda x: f"Fila {x+1} | ID CP: {df.iloc[x][c_cp]}")
    
    fila = df.iloc[idx]
    id_actual = clean_id(fila[c_cp])
    
    col_pdf, col_data = st.columns([1.5, 1])

    with col_pdf:
        st.subheader("🖼️ Visor de Evidencia")
        if id_actual in pdf_repo:
            f = pdf_repo[id_actual]
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
            # Reset del puntero para que no se pierda el archivo en la siguiente lectura
            f.seek(0)
        else:
            st.error(f"⚠️ HALLAZGO CONFIRMADO: El ID {id_actual} no tiene respaldo físico en la carga.")

    with col_data:
        st.subheader("🖋️ Verificación")
        st.write(fila.dropna())
        
        with st.form("pericia"):
            v_ok = st.radio("Veredicto:", ["PENDIENTE", "CONFORME", "CON HALLAZGO"])
            obs = st.text_area("Notas del Perito:")
            if st.form_submit_button("💾 GUARDAR"):
                st.session_state.db[id_actual] = {"status": v_ok, "obs": obs}
                st.rerun()

    # --- INFORMES (LA PARTE QUE FALTABA) ---
    st.divider()
    st.subheader("📊 Generación de Entregables")
    
    if st.session_state.db:
        col_inf1, col_inf2 = st.columns(2)
        
        with col_inf1:
            st.write("1. Vista previa de auditados:")
            st.dataframe(pd.DataFrame.from_dict(st.session_state.db, orient='index'))
            
        with col_inf2:
            st.write("2. Descargar Matriz Auditada (Final):")
            excel_data = to_excel(df, st.session_state.db)
            st.download_button(
                label="📥 DESCARGAR EXCEL DE HALLAZGOS",
                data=excel_data,
                file_name=f"Informe_Pericial_3T_2025.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.info("Guarde al menos un veredicto para generar el informe.")

else:
    st.info("Esperando carga de archivos...")
