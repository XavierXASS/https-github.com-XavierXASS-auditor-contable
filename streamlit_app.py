import streamlit as st
import pandas as pd
import requests
import base64
import io
import re
import time
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría IA Definitiva", layout="wide")
st.title("🛡️ Sistema de Auditoría Xavier - V21 (Vía Directa)")

# --- CONFIGURACIÓN DE CONEXIÓN DIRECTA ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
URL_API = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

if 'maestro' not in st.session_state: st.session_state.maestro = None

def auditar_con_ia_directa(pdf_bytes, cp, ruc, total, anio_ref):
    try:
        # 1. Convertir PDF a imagen (primera página para velocidad y estabilidad)
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img = images[0]
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        img_64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        # 2. Preparar la consulta técnica (Prompt)
        prompt = f"Analiza este expediente contable. CP: {cp}, RUC: {ruc}, TOTAL: {total}. Verifica si el CP y RUC coinciden, si están los documentos (Pago, Contable, Factura, Retencion, SPI) y si el cuadre Factura-Retencion es igual al SPI. Responde exactamente: TIPO: [tipo], ESTADO: [OK o REVISAR], DETALLE: [breve explicacion]"

        # 3. Llamada Directa (Sin usar la librería genai que da error 404)
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_64}}
                ]
            }]
        }
        
        response = requests.post(URL_API, json=payload)
        res_json = response.json()
        
        if response.status_code == 200:
            texto_ia = res_json['candidates'][0]['content']['parts'][0]['text'].upper()
            estado = "✅ OK" if "ESTADO: OK" in texto_ia else "🔍 REVISAR"
            # Extraer partes
            tipo = "CONTABLE"
            if "TIPO:" in texto_ia: tipo = texto_ia.split("TIPO:")[1].split(",")[0].strip()
            detalle = texto_ia.split("DETALLE:")[1].strip() if "DETALLE:" in texto_ia else texto_ia
            return tipo, estado, detalle
        else:
            return "ERROR", "❌ FALLO", f"Error API: {response.status_code}"
            
    except Exception as e:
        return "ERROR", "❌ FALLO", str(e)

# --- INTERFAZ ---
with st.sidebar:
    st.header("⚙️ Control")
    if st.button("🚨 Reiniciar Sistema"):
        st.session_state.maestro = None
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO_IA', 'INFORME', 'REVISADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("2. PDFs (Prueba con 1 o 2)", type=["pdf"], accept_multiple_files=True)

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
                    status_msg.info(f"IA analizando CP {cp_id}...")
                    t, s, d = auditar_con_ia_directa(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], 2025)
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'INFORME'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
        
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada.")

    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR RESULTADOS", out.getvalue(), "Auditoria_Final.xlsx"
