import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría IA Pro Xavier", layout="wide")
st.title("🛡️ Centro de Auditoría Inteligente Xavier - V30")

# --- MEMORIA DE SESIÓN ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'pdf_key' not in st.session_state: st.session_state.pdf_key = 0

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🔑 Acceso y Parámetros")
    user_key = st.text_input("API Key de Google:", type="password")
    
    entidad = st.selectbox("Entidad a Auditar:", ["EMAPAG", "ÉPICO"])
    anio_rev = st.selectbox("Año de Revisión:", [2025, 2024, 2026])
    periodo = st.selectbox("Periodo:", ["1er Trimestre", "2do Trimestre", "3er Trimestre", "4to Trimestre", "Mensual"])
    
    st.markdown("---")
    if st.button("🗑️ Limpiar PDFs"):
        st.session_state.pdf_key += 1
        st.rerun()
    if st.button("🚨 Reiniciar Sistema (Borrar Excel)"):
        st.session_state.maestro = None
        st.rerun()

# --- MOTOR DE INTELIGENCIA DE AUDITORÍA (PARÁMETROS CORREGIDOS) ---
def auditar_con_ia_profesional(pdf_bytes, cp, ruc, total_excel, anio, entidad_name):
    try:
        genai.configure(api_key=user_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Convertimos las primeras 6 páginas (Dossier completo)
        images = convert_from_bytes(pdf_bytes, dpi=100)
        img_payload = []
        for img in images[:6]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            img_payload.append(Image.open(buf))
        
        # EL PROMPT MAESTRO CON TODOS TUS PARÁMETROS
        prompt = f"""
        Eres un Auditor Forense experto para la empresa {entidad_name} en Ecuador.
        MATRIZ EXCEL: CP {cp}, RUC/Cédula {ruc}, Valor a Pagar {total_excel}.
        AÑO DE REVISIÓN: {anio}.

        INSTRUCCIONES DE REVISIÓN (PARÁMETROS):
        1. CLASIFICACIÓN: Determina si el trámite es: Pago a Proveedor (Factura), Nómina de Personal, Planilla IESS/SRI, Liquidación o Comisión Bancaria.
        2. INTEGRIDAD DEL EXPEDIENTE: Verifica si aparecen los 5 documentos:
           - Comprobante de Pago
           - Comprobante Contable
           - Documento Sustento (Factura o Nómina)
           - Comprobante de Retención (si aplica)
           - SPI (Documento del BCE con el logo del Sol Valdivia/Estado de Transferencia).
        3. IDENTIDAD: ¿El RUC {ruc} y el CP {cp} coinciden con lo escrito en los documentos?
        4. FECHAS CRÍTICAS: Detecta si dice "2026" (Error común de digitación) o si el documento es de un año anterior ({anio-1}).
        5. CUADRE MATEMÁTICO: Extrae el Valor del SPI. Verifica que sea igual al: (Total Factura/Nómina - Retenciones - Amortizaciones).
        
        RESPONDE EXACTAMENTE EN ESTE FORMATO:
        TIPO: [Clasificación detectada]
        ESTADO: [OK o REVISAR]
        OBSERVACION: [Detalle de hallazgos, si falta una pieza como el Sol Valdivia, o si el valor no cuadra]
        """
        
        response = model.generate_content([prompt] + img_payload)
        txt = response.text.upper()
        
        # Extracción de la respuesta
        estado = "✅ OK" if "ESTADO: OK" in txt else "🔍 REVISAR"
        tipo = txt.split("TIPO:")[1].split("\n")[0].strip() if "TIPO:" in txt else "DESCONOCIDO"
        obs = txt.split("OBSERVACION:")[1].strip() if "OBSERVACION:" in txt else txt
        
        return tipo, estado, obs
    except Exception as e:
        return "ERROR", "❌ ERROR IA", str(e)[:100]

# --- FLUJO DE TRABAJO ---
c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("1. Cargar Matriz Maestro", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['REVISADO', 'TIPO_TRAMITE', 'ESTADO_IA', 'INFORME_AUDITORIA']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"
        st.rerun()

with c2:
    pdfs = st.file_uploader("2. Cargar PDFs", type=["pdf"], accept_multiple_files=True, key=f"up_{st.session_state.pdf_key}")

if st.session_state.maestro is not None and pdfs and user_key:
    if st.button("🚀 EJECUTAR AUDITORÍA PERICIAL"):
        df = st.session_state.maestro
        # Identificar columnas
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper() or "IDENTIF" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "SPI" in str(c).upper() or "VALOR" in str(c).upper()), None)

        status_msg = st.empty()
        for pdf in pdfs:
            # Extraer CP del nombre del archivo
            num_match = re.search(r'\d+', pdf.name)
            if num_match:
                cp_id = num_match.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                
                if not idx_list.empty:
                    idx = idx_list[0]
                    status_msg.info(f"Auditor Virtual revisando CP {cp_id}...")
                    
                    t, s, o = auditar_con_ia_profesional(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev, entidad)
                    
                    df.at[idx, 'TIPO_TRAMITE'] = t
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'INFORME_AUDITORIA'] = o
                    df.at[idx, 'REVISADO'] = "SÍ"
                    time.sleep(1)
        
        st.session_state.maestro = df
        status_msg.success("Lote procesado. Descarga el avance abajo.")

# --- MOSTRAR RESULTADOS ---
if st.session_state.maestro is not None:
    st.write(f"### Matriz de Auditoría: {entidad} - {periodo}")
    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR MATRIZ ACTUALIZADA", output.getvalue(), f"Auditoria_{entidad}.xlsx")
