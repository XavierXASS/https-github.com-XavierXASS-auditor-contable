import streamlit as st
import pandas as pd
import requests
import base64
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría IA Xavier", layout="wide")
st.title("🛡️ Sistema de Auditoría Xavier - V22 Estable")

# --- CONFIGURACIÓN DE CONEXIÓN ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
URL_API = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

if 'maestro' not in st.session_state:
    st.session_state.maestro = None

def auditar_con_ia_directa(pdf_bytes, cp, ruc, total):
    try:
        # Convertir PDF a imagen (primera página para máxima estabilidad)
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        img_64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        prompt = f"""
        Analiza este documento contable.
        DATOS BUSCADOS: CP {cp}, RUC {ruc}, VALOR {total}.
        
        TAREAS:
        1. Confirma si el CP y el RUC coinciden con el documento.
        2. Identifica si es Pago, Factura, Contable, Retención o SPI (Sol Valdivia).
        3. ¿El valor {total} cuadra con el neto del documento?
        
        Responde corto:
        ESTADO: [OK o REVISAR]
        DETALLE: [Breve hallazgo]
        """

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_64}}
                ]
            }]
        }
        
        response = requests.post(URL_API, json=payload, timeout=30)
        res_json = response.json()
        
        if response.status_code == 200:
            texto_ia = res_json['candidates'][0]['content']['parts'][0]['text'].upper()
            estado = "✅ OK" if "ESTADO: OK" in texto_ia else "🔍 REVISAR"
            detalle = texto_ia.split("DETALLE:")[1].strip() if "DETALLE:" in texto_ia else texto_ia
            return "DETECTADO", estado, detalle
        else:
            return "ERROR", "❌ FALLO", f"Error API: {response.status_code}"
            
    except Exception as e:
        return "ERROR", "❌ FALLO", f"Error técnico: {str(e)}"

# --- INTERFAZ ---
with st.sidebar:
    st.header("Control")
    if st.button("🚨 Reiniciar"):
        st.session_state.maestro = None
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO_IA', 'HALLAZGOS', 'REVISADO']:
            st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("2. PDFs", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)

        status_msg = st.empty()
        for pdf in pdfs:
            num = re.search(r'\d+', pdf.name)
            if num:
                cp_id = num.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    status_msg.info(f"Analizando CP {cp_id}...")
                    t, s, d = auditar_con_ia_directa(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total])
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'HALLAZGOS'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
        
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada.")

if st.session_state.maestro is not None:
    st.dataframe(st.session_state.maestro, use_container_width=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.maestro.to_excel(writer, index=False)
    st.download_button(
        label="📥 DESCARGAR RESULTADOS",
        data=output.getvalue(),
        file_name="Auditoria_Resultados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
