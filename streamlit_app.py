import streamlit as st
import pandas as pd
import requests
import base64
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría Xavier V24", layout="wide")
st.title("🛡️ Sistema de Auditoría Xavier - V24")

# --- CONEXIÓN DIRECTA ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
# Esta es la URL que funciona en el 100% de los casos de red restringida
URL_API = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

if 'maestro' not in st.session_state:
    st.session_state.maestro = None

def probar_conexion():
    """Función para probar que la IA responde antes de procesar nada"""
    payload = {"contents": [{"parts": [{"text": "Responde solo la palabra: LISTO"}]}]}
    try:
        r = requests.post(URL_API, json=payload, timeout=10)
        if r.status_code == 200:
            return True, "✅ Conexión con Google AI: EXITOSA"
        else:
            return False, f"❌ Error {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, f"❌ Error de red: {str(e)}"

def auditar_con_ia(pdf_bytes, cp, ruc, total):
    try:
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        img_64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        prompt = f"Eres un auditor. Revisa este documento. CP: {cp}, RUC: {ruc}, VALOR: {total}. Verifica si coinciden. Responde: ESTADO: [OK o REVISAR], DETALLE: [explicacion]"

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_64}}
                ]
            }]
        }
        
        response = requests.post(URL_API, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            texto = res_json['candidates'][0]['content']['parts'][0]['text'].upper()
            est = "✅ OK" if "ESTADO: OK" in texto else "🔍 REVISAR"
            det = texto.split("DETALLE:")[1].strip() if "DETALLE:" in texto else texto
            return est, det
        return "❌ FALLO", f"Error API {response.status_code}"
    except Exception as e:
        return "❌ FALLO", str(e)

# --- INTERFAZ ---
with st.sidebar:
    st.header("1. Diagnóstico")
    if st.button("🔌 PROBAR CONEXIÓN CON GOOGLE"):
        exito, msg = probar_conexion()
        if exito: st.success(msg)
        else: st.error(msg)
    
    st.markdown("---")
    if st.button("🚨 Reiniciar Todo"):
        st.session_state.maestro = None
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("2. Subir Matriz Excel", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO_IA', 'HALLAZGOS', 'REVISADO']:
            st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("3. Subir 1 PDF (Para probar)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        # Buscador de columnas
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper()), None)

        for pdf in pdfs:
            num = re.search(r'\d+', pdf.name)
            if num:
                cp_id = num.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    with st.spinner(f"Auditando CP {cp_id}..."):
                        s, d = auditar_con_ia(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total])
                        df.at[idx, 'ESTADO_IA'] = s
                        df.at[idx, 'HALLAZGOS'] = d
                        df.at[idx, 'REVISADO'] = "SÍ"
        st.session_state.maestro = df
        st.success("Proceso terminado.")

if st.session_state.maestro is not None:
    st.dataframe(st.session_state.maestro, use_container_width=True)
