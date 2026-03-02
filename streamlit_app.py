import streamlit as st
import pandas as pd
import base64
import os

# CONFIGURACIÓN BÁSICA - SIN PROCESOS PESADOS
st.set_page_config(layout="wide")
DB_FILE = "pericia_final.csv"

if 'db' not in st.session_state:
    if os.path.exists(DB_FILE):
        st.session_state.db = pd.read_csv(DB_FILE).set_index('CP').to_dict('index')
    else:
        st.session_state.db = {}

st.title("🛡️ Terminal de Emergencia - Pericia Xavier")

ex_file = st.sidebar.file_uploader("1. Excel", type=["xlsx"])
pdf_files = st.sidebar.file_uploader("2. PDFs", type=["pdf"], accept_multiple_files=True)

if ex_file and pdf_files:
    df = pd.read_excel(ex_file)
    pdf_repo = {re.sub(r'\D', '', f.name): f for f in pdf_files}
    
    # Navegación simple por fila
    idx = st.number_input("Fila de la Matriz:", 0, len(df)-1, value=0)
    fila = df.iloc[idx]
    id_actual = re.sub(r'\D', '', str(fila.iloc[0])) # Toma el CP de la primera columna

    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        if id_actual in pdf_repo:
            f = pdf_repo[id_actual]
            b64 = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="800"></iframe>', unsafe_allow_html=True)
            f.seek(0)
        else:
            st.error(f"CP {id_actual} SIN PDF")

    with col2:
        st.write(fila.dropna())
        res = st.selectbox("Estado:", ["OK", "HALLAZGO", "SIN PDF"], key=f"sel_{idx}")
        obs = st.text_area("Notas:", key=f"obs_{idx}")
        if st.button("💾 GUARDAR LÍNEA"):
            st.session_state.db[id_actual] = {"Estado": res, "Notas": obs}
            pd.DataFrame.from_dict(st.session_state.db, orient='index').to_csv(DB_FILE)
            st.success("Guardado.")

    if st.button("📦 DESCARGAR EXCEL FINAL"):
        reporte = df.copy()
        reporte['ESTADO'] = reporte.iloc[:,0].apply(lambda x: st.session_state.db.get(re.sub(r'\D','',str(x)), {}).get('Estado', 'PENDIENTE'))
        st.download_button("Descargar", reporte.to_csv().encode('utf-8'), "Auditoria_Xavier.csv")
