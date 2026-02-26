import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

# --- CONFIGURACIÓN DE IA ---
st.set_page_config(page_title="Auditoría IA Pro - Xavier", layout="wide")

st.title("🛡️ Centro de Auditoría con Inteligencia Artificial")
st.markdown("---")

# Barra lateral para la llave y configuración
with st.sidebar:
    st.header("🔑 Acceso")
    # Usamos la llave que proporcionaste
    api_key_input = st.text_input("Google API Key:", value="AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI", type="password")
    
    st.header("⚙️ Contexto")
    entidad = st.selectbox("Entidad:", ["EMAPAG", "ÉPICO"])
    anio_ref = st.number_input("Año de revisión:", value=2025)
    
    if st.button("🚨 Reiniciar Todo"):
        st.session_state.maestro = None
        st.rerun()

# Configurar la IA
if api_key_input:
    genai.configure(api_key=api_key_input)
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- MEMORIA DE SESIÓN ---
if 'maestro' not in st.session_state: st.session_state.maestro = None

# --- LÓGICA DE AUDITORÍA PERICIAL CON IA ---
def auditar_pericial(pdf_bytes, cp, ruc, total_ex, anio_ref, entidad_nombre):
    try:
        # Convertimos todas las páginas del PDF para que la IA vea todo el expediente
        images = convert_from_bytes(pdf_bytes, dpi=100)
        
        # Preparamos las imágenes para Gemini
        img_payload = []
        for img in images[:5]: # Enviamos las primeras 5 páginas (suficiente para los 5 docs)
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            img_payload.append(Image.open(buf))
        
        prompt = f"""
        Eres un auditor forense contable en Ecuador trabajando para {entidad_nombre}. 
        Analiza este expediente (varias páginas) referente al CP {cp} y RUC/Cédula {ruc}.

        OBJETIVO:
        1. Identifica el trámite: ¿Es Pago a Proveedor, Nómina, Planilla IESS/SRI, Liquidación o Comisión Bancaria?
        2. Verifica presencia de piezas: Comprobante de Pago, Contable, Factura/Nómina, Retención y SPI (Sol Valdivia/BCE).
        3. Errores Críticos: Busca fechas del 2026 o del año anterior (buscamos {anio_ref}).
        4. Validación Numérica: Extrae el valor pagado en el SPI y compáralo con el total del trámite menos retenciones/amortizaciones. El valor en Excel es {total_ex}.

        RESPONDE EXACTAMENTE ASÍ:
        TIPO: [Tipo de trámite detectado]
        ESTADO: [OK o REVISAR]
        DETALLE: [Lista breve de hallazgos, piezas faltantes o errores de fecha/RUC]
        """
        
        response = model.generate_content([prompt] + img_payload)
        res_text = response.text.upper()
        
        # Parseo de respuesta
        estado = "✅ OK" if "ESTADO: OK" in res_text else "🔍 REVISAR"
        tipo = res_text.split("TIPO:")[1].split("\n")[0].strip() if "TIPO:" in res_text else "DESCONOCIDO"
        detalle = res_text.split("DETALLE:")[1].strip() if "DETALLE:" in res_text else res_text
        
        return tipo, estado, detalle
    except Exception as e:
        return "ERROR", "ERROR IA", str(e)

# --- FLUJO DE CARGA ---
col_ex, col_pdf = st.columns(2)

with col_ex:
    st.subheader("1. Matriz Excel")
    file_ex = st.file_uploader("Subir Maestro", type=["xlsx"])
    if file_ex and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(file_ex)
        for c in ['TIPO_TRAMITE', 'ESTADO_IA', 'INFORME_DETALLADO', 'REVISADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"
        st.rerun()

with col_pdf:
    st.subheader("2. Expedientes PDF")
    pdfs = st.file_uploader("Sube los archivos (Lotes de 5 a 10)", type=["pdf"], accept_multiple_files=True)

# --- EJECUCIÓN ---
if st.session_state.maestro is not None and api_key_input:
    df = st.session_state.maestro
    
    # Identificar columnas
    c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
    c_total = next((c for c in df.columns if "TOTAL" in str(c).upper()), None)

    if pdfs and st.button("🚀 INICIAR AUDITORÍA PERICIAL"):
        status_msg = st.empty()
        progreso = st.progress(0)
        
        for i, pdf in enumerate(pdfs):
            # Extraer número del nombre del archivo para mapear
            num_match = re.search(r'\d+', pdf.name)
            if num_match:
                cp_id = num_match.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                
                if not idx_list.empty:
                    idx = idx_list[0]
                    status_msg.info(f"IA analizando visualmente el CP {cp_id}...")
                    
                    tipo, est, det = auditar_pericial(
                        pdf.read(), 
                        cp_id, 
                        df.at[idx, c_ruc], 
                        df.at[idx, c_total], 
                        anio_ref, 
                        entidad
                    )
                    
                    df.at[idx, 'TIPO_TRAMITE'] = tipo
                    df.at[idx, 'ESTADO_IA'] = est
                    df.at[idx, 'INFORME_DETALLADO'] = det
                    df.at[idx, 'REVISADO'] = "SÍ"
                    time.sleep(1) # Respetar límites de API gratuita
            
            progreso.progress((i + 1) / len(pdfs))
        
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada.")

    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    # Descarga
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR AUDITORÍA COMPLETA", out.getvalue(), f"Auditoria_IA_{entidad}.xlsx")

else:
    st.info("👈 Por favor, carga el Excel y verifica tu API Key para empezar.")
