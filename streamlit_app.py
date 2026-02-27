import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría Pro Xavier", layout="wide")
st.title("🛡️ Centro de Auditoría Xavier - V27 (Alta Disponibilidad)")

# --- CONFIGURACIÓN DE SEGURIDAD ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
genai.configure(api_key=API_KEY)

if 'maestro' not in st.session_state:
    st.session_state.maestro = None

def obtener_modelo_activo():
    """Busca dinámicamente un modelo disponible para evitar el error 404"""
    try:
        modelos = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priorizamos el flash por velocidad, si no, cualquiera que funcione
        for m in modelos:
            if "gemini-1.5-flash" in m: return m
        return modelos[0] if modelos else None
    except Exception as e:
        st.error(f"Error al listar modelos: {e}")
        return None

def auditar_con_ia(pdf_bytes, cp, ruc, total):
    try:
        nombre_modelo = obtener_modelo_activo()
        if not nombre_modelo:
            return "ERROR", "❌ ERROR", "No se encontró recurso de IA (404 Global)"
        
        model = genai.GenerativeModel(nombre_modelo)
        
        # Convertir primera página
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img_buf = io.BytesIO()
        images[0].save(img_buf, format='JPEG')
        
        prompt = f"""
        Actúa como auditor. Datos: CP {cp}, RUC {ruc}, VALOR {total}.
        Verifica si el CP y RUC están en el documento y si el valor cuadra.
        Responde: ESTADO: [OK o REVISAR], DETALLE: [explicación breve].
        """

        response = model.generate_content([prompt, Image.open(img_buf)])
        res_text = response.text.upper()
        
        estado = "✅ OK" if "ESTADO: OK" in res_text else "🔍 REVISAR"
        detalle = res_text.split("DETALLE:")[1].strip() if "DETALLE:" in res_text else res_text
        return estado, detalle
    except Exception as e:
        return "❌ FALLO", f"Error técnico: {str(e)[:50]}"

# --- INTERFAZ ---
with st.sidebar:
    st.header("⚙️ Herramientas")
    if st.button("🔌 TEST DE RECURSOS (QA)"):
        modelo = obtener_modelo_activo()
        if modelo: st.success(f"Recurso hallado: {modelo}")
        else: st.error("404: No se hallaron recursos disponibles.")
    
    if st.button("🚨 Reiniciar Maestro"):
        st.session_state.maestro = None
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    ex_f = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    if ex_f and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_f)
        for c in ['ESTADO_IA', 'HALLAZGOS', 'REVISADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("2. PDFs (Sube 1 para probar)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)

        status_log = st.empty()
        for pdf in pdfs:
            num = re.search(r'\d+', pdf.name)
            if num:
                cp_id = num.group()
                idx_l = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_l.empty:
                    idx = idx_l[0]
                    status_log.info(f"Auditando CP {cp_id}...")
                    s, d = auditar_con_ia(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total])
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'HALLAZGOS'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
                    time.sleep(1) # Seguridad
        st.session_state.maestro = df
        status_log.success("Auditoría terminada.")

if st.session_state.maestro is not None:
    st.dataframe(st.session_state.maestro, use_container_width=True)
