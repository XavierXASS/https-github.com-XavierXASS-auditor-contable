import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

# 1. QA DE CONFIGURACIÓN INICIAL
st.set_page_config(page_title="Auditoría Pro Xavier - QA Pass", layout="wide")
st.title("🛡️ Sistema de Auditoría Xavier - V32 (QA de Conexión)")

# --- PERSISTENCIA DE DATOS ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'conexion_ok' not in st.session_state: st.session_state.conexion_ok = False

# --- BARRA LATERAL CON DIAGNÓSTICO ---
with st.sidebar:
    st.header("🔐 Seguridad de Acceso")
    user_key = st.text_input("API Key de Google:", type="password", help="Genera una nueva en Google AI Studio si la anterior falló.")
    
    # BOTÓN DE QA DE CONEXIÓN (TU PEDIDO)
    if st.button("🔌 PROBAR CONEXIÓN (QA TEST)"):
        if not user_key:
            st.error("Por favor, pega una llave primero.")
        else:
            with st.spinner("Realizando Handshake con Google..."):
                try:
                    genai.configure(api_key=user_key)
                    test_model = genai.GenerativeModel('gemini-1.5-flash')
                    # Prueba de respuesta mínima
                    response = test_model.generate_content("Hola, confirma conexión para auditoría.")
                    if response:
                        st.session_state.conexion_ok = True
                        st.success("✅ CONEXIÓN EXITOSA: La IA está lista.")
                    else:
                        st.session_state.conexion_ok = False
                        st.error("❌ Google no respondió. Revisa la validez de la llave.")
                except Exception as e:
                    st.session_state.conexion_ok = False
                    st.error(f"❌ FALLO DE QA: {str(e)}")

    st.header("⚙️ Parámetros")
    entidad = st.selectbox("Entidad:", ["EMAPAG", "ÉPICO"])
    anio_rev = st.selectbox("Año de Revisión:", [2025, 2024, 2026])
    
    if st.button("🚨 Reiniciar Sistema"):
        st.session_state.maestro = None
        st.session_state.conexion_ok = False
        st.rerun()

# --- LÓGICA DE AUDITORÍA (SOLO SI PASA EL QA) ---
def auditar_pericial(pdf_bytes, cp, ruc, total, anio, entidad_name):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img_payload = []
        for img in images[:6]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            img_payload.append(Image.open(buf))
        
        prompt = f"""
        Eres un Auditor experto para {entidad_name}. 
        DATOS BUSCADOS: CP {cp}, RUC {ruc}, VALOR SPI {total}.
        AÑO REVISIÓN: {anio}.
        TAREAS:
        1. Identifica: Pago, Contable, Factura, Retención y SPI (Sol Valdivia).
        2. Verifica que RUC y CP coincidan en los papeles.
        3. Realiza el cuadre: Factura - Retenciones == SPI.
        4. Alertas: Fecha 2026 o año anterior ({anio-1}).
        RESPONDE: TIPO: [tipo] | ESTADO: [OK o REVISAR] | DETALLE: [hallazgos]
        """
        response = model.generate_content([prompt] + img_payload)
        return response.text.upper()
    except Exception as e:
        return f"ERROR EN PROCESO: {str(e)}"

# --- FLUJO PRINCIPAL ---
if not st.session_state.conexion_ok:
    st.warning("⚠️ El sistema está bloqueado. Por seguridad, primero realiza el 'TEST DE CONEXIÓN' en la barra lateral.")
else:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("1. Excel Maestro")
        ex_file = st.file_uploader("Subir Matriz", type=["xlsx"])
        if ex_file and st.session_state.maestro is None:
            st.session_state.maestro = pd.read_excel(ex_file)
            for c in ['ESTADO_IA', 'INFORME', 'REVISADO']:
                if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"
            st.rerun()

    with c2:
        st.subheader("2. PDFs")
        pdfs = st.file_uploader("Cargar PDFs", type=["pdf"], accept_multiple_files=True)

    if st.session_state.maestro is not None and pdfs:
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
                    idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                    if not idx_list.empty:
                        idx = idx_list[0]
                        status_msg.info(f"IA analizando CP {cp_id}...")
                        res_raw = auditar_pericial(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev, entidad)
                        df.at[idx, 'ESTADO_IA'] = "✅ OK" if "OK" in res_raw else "🔍 REVISAR"
                        df.at[idx, 'INFORME'] = res_raw
                        df.at[idx, 'REVISADO'] = "SÍ"
            st.session_state.maestro = df
            status_msg.success("Proceso terminado.")

    if st.session_state.maestro is not None:
        st.dataframe(st.session_state.maestro, use_container_width=True)
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as w:
            st.session_state.maestro.to_excel(w, index=False)
        st.download_button("📥 DESCARGAR MATRIZ AUDITADA", out.getvalue(), "Auditoria_Final.xlsx")
