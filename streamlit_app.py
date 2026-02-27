import streamlit as st
import pandas as pd
import requests
import base64
import io
import re
import time
from pdf2image import convert_from_bytes
from PIL import Image

# 1. QA DE CONFIGURACIÓN
st.set_page_config(page_title="Auditoría Xavier FINAL", layout="wide")
st.title("🛡️ Centro de Auditoría Xavier - V33 (Vía Directa)")

if 'maestro' not in st.session_state: st.session_state.maestro = None

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🔐 Acceso")
    # Tu llave actual: AIzaSyDk0LEdj70JhtPZ68NxrxogUaP-zjSqpnU
    api_key = st.text_input("API Key de Google:", type="password")
    
    st.header("⚙️ Parámetros")
    entidad = st.selectbox("Entidad:", ["EMAPAG", "ÉPICO"])
    anio_rev = st.selectbox("Año de Revisión:", [2025, 2024, 2026])
    
    st.markdown("---")
    if st.button("🗑️ Limpiar PDFs (Mantener Excel)"):
        st.cache_data.clear()
        st.success("Lote de PDFs limpiado.")
    
    if st.button("🚨 Reiniciar TODO"):
        st.session_state.maestro = None
        st.rerun()

# --- MOTOR DE IA (VÍA DIRECTA - SIN LIBRERÍAS) ---
def auditar_con_ia_directa(pdf_bytes, cp, ruc, total, anio, entidad_name):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    try:
        # Convertir primera página del PDF a imagen para la IA
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img_buf = io.BytesIO()
        images[0].save(img_buf, format='JPEG')
        img_b64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')

        prompt = f"Eres auditor para {entidad_name}. Revisa: CP {cp}, RUC {ruc}, VALOR {total}. Confirma si el CP y RUC están en el papel, si están los 5 documentos y si el cuadre factura-retencion es igual al SPI. Responde: ESTADO: [OK o REVISAR] | DETALLE: [explicacion]"

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            texto_ia = res_json['candidates'][0]['content']['parts'][0]['text'].upper()
            estado = "✅ OK" if "ESTADO: OK" in texto_ia else "🔍 REVISAR"
            detalle = texto_ia.split("DETALLE:")[1].strip() if "DETALLE:" in texto_ia else texto_ia
            return estado, detalle
        else:
            return "❌ ERROR", f"Fallo API: {response.status_code}"
    except Exception as e:
        return "❌ ERROR", str(e)

# --- FLUJO PRINCIPAL ---
c1, c2 = st.columns(2)
with c1:
    st.subheader("1. Matriz Excel")
    ex_file = st.file_uploader("Subir Maestro", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO_IA', 'HALLAZGOS', 'REVISADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with c2:
    st.subheader("2. Comprobantes PDF")
    pdfs = st.file_uploader("Cargar PDFs", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs and api_key:
    if st.button("🚀 INICIAR AUDITORÍA PERICIAL"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)

        status_msg = st.empty()
        for pdf in pdfs:
            # Extraer número del nombre del archivo
            num_match = re.search(r'\d+', pdf.name)
            if num_match:
                cp_id = num_match.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    status_msg.info(f"IA analizando CP {cp_id}...")
                    s, d = auditar_con_ia_directa(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev, entidad)
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'HALLAZGOS'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
                    time.sleep(1)
        st.session_state.maestro = df
        status_msg.success("Lote procesado.")

if st.session_state.maestro is not None:
    st.dataframe(st.session_state.maestro, use_container_width=True)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR RESULTADOS", out.getvalue(), "Auditoria_Xavier.xlsx")
