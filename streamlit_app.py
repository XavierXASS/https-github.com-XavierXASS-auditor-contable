import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Auditoría IA Xavier", layout="wide")
st.title("🛡️ Centro de Auditoría Integral con IA")

# --- CONEXIÓN BLINDADA CON GOOGLE AI ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
genai.configure(api_key=API_KEY)
# Forzamos la versión estable del modelo para evitar el error 404
model = genai.GenerativeModel('gemini-1.5-flash')

# --- MEMORIA DE SESIÓN ---
if 'maestro' not in st.session_state: st.session_state.maestro = None

def auditar_pericial(pdf_bytes, cp, ruc, total, anio_f):
    try:
        images = convert_from_bytes(pdf_bytes, dpi=100)
        payload = []
        for img in images[:6]: # Analizamos las primeras 6 páginas
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            payload.append(Image.open(buf))
        
        prompt = f"""
        Actúa como auditor experto. DATOS EXCEL: CP={cp}, RUC={ruc}, TOTAL={total}.
        INSTRUCCIONES:
        1. Identifica: Pago, Contable, Factura, Retención y SPI (Sol Valdivia).
        2. Verifica si el CP {cp} y RUC {ruc} coinciden en los papeles.
        3. Realiza el cuadre: Factura - Retenciones == Pago SPI.
        4. Reporta si hay fechas de 2026 o de años distintos a {anio_f}.
        
        RESPONDE EXACTAMENTE ASÍ:
        TIPO: [Tipo de pago]
        ESTADO: [OK o REVISAR]
        DETALLE: [Explica hallazgos o piezas faltantes]
        """
        response = model.generate_content([prompt] + payload)
        res = response.text.upper()
        
        estado = "✅ OK" if "ESTADO: OK" in res else "🔍 REVISAR"
        tipo = res.split("TIPO:")[1].split("\n")[0].strip() if "TIPO:" in res else "DESCONOCIDO"
        detalle = res.split("DETALLE:")[1].strip() if "DETALLE:" in res else res
        return tipo, estado, detalle
    except Exception as e:
        return "ERROR", "❌ FALLO IA", f"Reintente: {str(e)}"

# --- INTERFAZ DE USUARIO ---
with st.sidebar:
    st.header("⚙️ Configuración")
    entidad = st.selectbox("Empresa:", ["EMAPAG", "ÉPICO"])
    anio_rev = st.selectbox("Año:", [2025, 2026, 2024])
    periodo = st.selectbox("Periodo:", ["1er Trimestre", "2do Trimestre", "3er Trimestre", "4to Trimestre", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
    
    st.markdown("---")
    if st.button("🗑️ Limpiar PDFs (Mantener Excel)"):
        st.cache_resource.clear()
        st.rerun()
    if st.button("🚨 REINICIAR TODO"):
        st.session_state.maestro = None
        st.rerun()

# --- FLUJO DE TRABAJO ---
c1, c2 = st.columns(2)
with c1:
    st.subheader("1. Matriz Maestro")
    file_ex = st.file_uploader("Subir Excel", type=["xlsx"])
    if file_ex and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(file_ex)
        for c in ['REVISADO', 'TIPO_TRAMITE', 'ESTADO_IA', 'HALLAZGOS']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"
        st.rerun()

with c2:
    st.subheader("2. Archivos PDF")
    pdfs = st.file_uploader("Subir PDFs (Lotes de 10)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None:
    df = st.session_state.maestro
    c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
    c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "SPI" in str(c).upper()), None)

    if pdfs and st.button("🚀 INICIAR AUDITORÍA PERICIAL"):
        status = st.empty()
        progreso = st.progress(0)
        for i, pdf in enumerate(pdfs):
            # Buscar número de CP en el nombre del archivo
            match = re.search(r'\d+', pdf.name)
            if match:
                cp_id = match.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    status.info(f"Analizando CP {cp_id} con Inteligencia Artificial...")
                    t, e, d = auditar_pericial(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev)
                    df.at[idx, 'REVISADO'] = "SÍ"
                    df.at[idx, 'TIPO_TRAMITE'] = t
                    df.at[idx, 'ESTADO_IA'] = e
                    df.at[idx, 'HALLAZGOS'] = d
                    time.sleep(1)
            progreso.progress((i + 1) / len(pdfs))
        st.session_state.maestro = df
        status.success("Lote terminado.")

    st.write(f"### Reporte: {entidad} - {periodo}")
    st.dataframe(df, use_container_width=True)
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR MATRIZ ACTUALIZADA", out.getvalue(), "Auditoria_Final.xlsx")
