import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Pro Xavier", layout="wide")

if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'pdf_cache' not in st.session_state: st.session_state.pdf_cache = {}

st.title("🛡️ Auditoría Inteligente de Comprobantes")
st.markdown("---")

def analizar_pdf_integral(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        pdf_file.seek(0)
        # Bajamos a 150 DPI para que sea más rápido y no sature la memoria
        images = convert_from_path(pdf_file.read(), dpi=150)
        texto_completo = ""
        for img in images:
            texto_completo += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        hallazgos = []
        documentos_detectados = []
        
        mapeo_docs = {
            "COMPROBANTE DE PAGO": "PAGO",
            "COMPROBANTE CONTABLE": "CONTABLE",
            "FACTURA": "FACTURA",
            "RETENCIÓN": "RETENCIÓN",
            "ESTADO DE TRANSFERENCIA": "SPI"
        }
        for clave, nombre in mapeo_docs.items():
            if clave in texto_completo: documentos_detectados.append(nombre)

        # Limpieza de CP y RUC para búsqueda
        cp_clean = re.sub(r'\D', '', str(cp_buscado))
        ruc_clean = re.sub(r'\D', '', str(ruc_buscado))
        texto_clean = re.sub(r'\D', '', texto_completo)

        if cp_clean not in texto_clean:
            return "🔍 REVISAR", f"CP {cp_clean} no hallado en el texto del PDF"

        if ruc_clean not in texto_clean:
            hallazgos.append("RUC no hallado")

        if "2026" in texto_completo: hallazgos.append("Alerta Fecha: 2026")
        if "2024" in texto_completo and anio_ref == 2025: hallazgos.append("Año anterior (2024)")

        faltantes = set(mapeo_docs.values()) - set(documentos_detectados)
        status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
        
        obs = f"Docs: {','.join(documentos_detectados)}. "
        if faltantes: obs += f"Faltan: {','.join(faltantes)}. "
        if hallazgos: obs += f"Alertas: {'; '.join(hallazgos)}"
        
        return status, obs
    except Exception as e:
        return "ERROR OCR", f"Error técnico: {str(e)}"

with st.sidebar:
    st.header("⚙️ Configuración")
    entidad = st.selectbox("Entidad", ["EMAPAG", "ÉPICO"])
    anio_fiscal = st.number_input("Año de Revisión", value=2025)
    
    file_excel = st.file_uploader("1. Cargar Matriz Excel", type=["xlsx"])
    if file_excel:
        if st.session_state.maestro is None:
            st.session_state.maestro = pd.read_excel(file_excel)
            if 'ESTADO_REVISION' not in st.session_state.maestro.columns:
                st.session_state.maestro['ESTADO_REVISION'] = "PENDIENTE"
                st.session_state.maestro['OBSERVACIONES_TECNICAS'] = ""

    files_pdf = st.file_uploader("2. Cargar PDFs (En lotes de 20 para evitar errores)", type=["pdf"], accept_multiple_files=True)
    if files_pdf:
        for f in files_pdf: 
            st.session_state.pdf_cache[f.name.upper()] = f
    
    st.write(f"Total PDFs en memoria: {len(st.session_state.pdf_cache)}")

    if st.button("🗑️ Resetear Todo"):
        st.session_state.maestro = None
        st.session_state.pdf_cache = {}
        st.rerun()

if st.session_state.maestro is not None:
    df = st.session_state.maestro
    c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

    if st.button("🚀 PROCESAR FILAS PENDIENTES"):
        progreso = st.progress(0)
        status_msg = st.empty()
        
        for idx, fila in df.iterrows():
            if fila['ESTADO_REVISION'] in ["✅ OK", "🔍 REVISAR", "❌ DESECHADO"]:
                continue
                
            cp_val = str(fila[c_cp]).strip().split('.')[0]
            ruc_val = str(fila[c_ruc]).strip().split('.')[0]
            
            status_msg.text(f"Buscando PDF para CP {cp_val}...")
            
            pdf_encontrado = None
            for nombre, contenido in st.session_state.pdf_cache.items():
                if cp_val in nombre:
                    pdf_encontrado = contenido
                    break
            
            if pdf_encontrado:
                res_status, res_obs = analizar_pdf_integral(pdf_encontrado, cp_val, ruc_val, anio_fiscal)
                df.at[idx, 'ESTADO_REVISION'] = res_status
                df.at[idx, 'OBSERVACIONES_TECNICAS'] = res_obs
            else:
                df.at[idx, 'OBSERVACIONES_TECNICAS'] = "PDF no cargado"

            progreso.progress((idx + 1) / len(df))
        
        st.session_state.maestro = df
        status_msg.success("Procesamiento terminado.")

    st.dataframe(df, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    st.download_button("📥 DESCARGAR MAESTRO ACTUALIZADO", output.getvalue(), file_name=f"Auditoria_{entidad}.xlsx")
