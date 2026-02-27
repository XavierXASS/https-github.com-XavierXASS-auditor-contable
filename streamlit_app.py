import streamlit as st
import pandas as pd
import requests
import base64
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image

# Configuración inicial
st.set_page_config(page_title="Auditoría Xavier", layout="wide")

st.title("🛡️ Sistema de Auditoría Xavier - FINAL")
st.markdown("---")

# --- CONEXIÓN DIRECTA ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
URL_API = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

if 'maestro' not in st.session_state:
    st.session_state.maestro = None

def procesar_ia(pdf_bytes, cp, ruc, total):
    try:
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        img_64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        prompt = f"Eres un auditor. Revisa si el documento tiene: CP {cp}, RUC {ruc} y VALOR {total}. Responde exacto: ESTADO: [OK o REVISAR], DETALLE: [explicacion]"

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_64}}
                ]
            }]
        }
        
        r = requests.post(URL_API, json=payload, timeout=30)
        if r.status_code == 200:
            res_json = r.json()
            texto = res_json['candidates'][0]['content']['parts'][0]['text'].upper()
            est = "✅ OK" if "ESTADO: OK" in texto else "🔍 REVISAR"
            det = texto.split("DETALLE:")[1].strip() if "DETALLE:" in texto else texto
            return est, det
        return "❌ FALLO", f"Error API {r.status_code}"
    except Exception as e:
        return "❌ FALLO", str(e)

# --- INTERFAZ ---
with st.sidebar:
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
    pdfs = st.file_uploader("2. PDFs (Prueba con 1)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        cols = df.columns.tolist()
        c_cp = next((c for c in cols if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in cols if "RUC" in str(c).upper()), None)
        c_total = next((c for c in cols if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)

        for pdf in pdfs:
            num = re.search(r'\d+', pdf.name)
            if num:
                cp_id = num.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    with st.spinner(f"Analizando CP {cp_id}..."):
                        s, d = procesar_ia(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total])
                        df.at[idx, 'ESTADO_IA'] = s
                        df.at[idx, 'HALLAZGOS'] = d
                        df.at[idx, 'REVISADO'] = "SÍ"
        st.session_state.maestro = df
        st.success("Listo.")

if st.session_state.maestro is not None:
    st.dataframe(st.session_state.maestro, use_container_width=True)
