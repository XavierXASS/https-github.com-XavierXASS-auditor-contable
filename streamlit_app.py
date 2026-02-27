import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

# --- CONFIGURACIÓN HOLÍSTICA ---
st.set_page_config(page_title="Auditoría Pro Xavier", layout="wide")
st.title("🛡️ Centro de Auditoría con Inteligencia Artificial")

# --- MEMORIA DE SESIÓN ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'pdf_uploader_key' not in st.session_state: st.session_state.pdf_uploader_key = 0

# --- BARRA LATERAL: SEGURIDAD Y CONFIGURACIÓN ---
with st.sidebar:
    st.header("🔑 Acceso Seguro")
    user_key = st.text_input("Pega tu NUEVA API Key aquí:", type="password")
    
    st.header("⚙️ Parámetros")
    entidad = st.selectbox("Empresa:", ["EMAPAG", "ÉPICO"])
    anio_rev = st.selectbox("Año Fiscal:", [2025, 2026, 2024])
    
    st.markdown("---")
    if st.button("🗑️ Limpiar Lote de PDFs"):
        st.session_state.pdf_uploader_key += 1
        st.rerun()
    if st.button("🚨 Reiniciar Todo (Borrar Excel)"):
        st.session_state.maestro = None
        st.session_state.pdf_uploader_key += 1
        st.rerun()

# --- LÓGICA DE AUDITORÍA CON IA ---
def auditar_con_ia(pdf_bytes, cp, ruc, total, anio):
    try:
        genai.configure(api_key=user_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Convertimos las primeras 5 páginas (Expediente completo)
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img_payload = []
        for img in images[:5]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            img_payload.append(Image.open(buf))
        
        prompt = f"""
        Actúa como auditor experto para la empresa {entidad}.
        DATOS BUSCADOS: CP {cp}, RUC {ruc}, VALOR SPI {total}.
        
        TAREAS:
        1. Identifica presencia de: Comprobante de Pago, Contable, Factura, Retención y SPI (Sol Valdivia).
        2. ¿El CP {cp} y el RUC {ruc} coinciden en los documentos?
        3. Cuadre: Valor Factura - Retenciones == Pago SPI.
        4. Alertas: ¿Fecha dice 2026? ¿Es del año anterior a {anio}?
        
        Responde EXACTAMENTE así:
        ESTADO: [OK o REVISAR]
        INFORME: [Breve explicación de hallazgos]
        """
        
        response = model.generate_content([prompt] + img_payload)
        txt = response.text.upper()
        
        est = "✅ OK" if "ESTADO: OK" in txt else "🔍 REVISAR"
        inf = txt.split("INFORME:")[1].strip() if "INFORME:" in txt else txt
        return est, inf
    except Exception as e:
        return "❌ ERROR", str(e)[:100]

# --- FLUJO DE TRABAJO ---
c1, c2 = st.columns(2)
with c1:
    ex_f = st.file_uploader("1. Matriz Excel Maestro", type=["xlsx"])
    if ex_f and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_f)
        for c in ['REVISADO', 'ESTADO_IA', 'HALLAZGOS']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("2. Lote de PDFs", type=["pdf"], accept_multiple_files=True, key=f"up_{st.session_state.pdf_uploader_key}")

if st.session_state.maestro is not None and pdfs and user_key:
    if st.button("🚀 INICIAR AUDITORÍA PERICIAL"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)

        status_msg = st.empty()
        for pdf in pdfs:
            num = re.search(r'\d+', pdf.name)
            if num:
                cp_id = num.group()
                idx_l = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_l.empty:
                    idx = idx_l[0]
                    status_msg.info(f"IA analizando visualmente CP {cp_id}...")
                    s, d = auditar_con_ia(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev)
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'HALLAZGOS'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
                    time.sleep(1)
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada.")

if st.session_state.maestro is not None:
    st.write("### Avance de la Matriz")
    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR MATRIZ ACTUALIZADA", out.getvalue(), "Auditoria_Final.xlsx")
