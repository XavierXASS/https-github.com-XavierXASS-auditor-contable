import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_bytes
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Xavier PRO", layout="wide")

# --- MEMORIA DE SESIÓN ---
if 'df_maestro' not in st.session_state: 
    st.session_state.df_maestro = None
if 'pdf_uploader_key' not in st.session_state:
    st.session_state.pdf_uploader_key = 0

st.title("🛡️ Sistema de Auditoría Xavier - V10 Estable")
st.markdown("---")

def procesar_un_pdf(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        # Volvemos al inicio del archivo para leerlo
        pdf_file.seek(0)
        archivo_bytes = pdf_file.read()
        
        # CORRECCIÓN TÉCNICA: Usamos convert_from_bytes para Streamlit Cloud
        images = convert_from_bytes(archivo_bytes, dpi=130) 
        
        texto_acumulado = ""
        for img in images:
            texto_acumulado += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        # Identificación de documentos presentes
        docs_encontrados = []
        if "PAGO" in texto_acumulado or "COMPROBANTE DE PAGO" in texto_acumulado: docs_encontrados.append("PAGO")
        if "CONTABLE" in texto_acumulado or "COMPROBANTE CONTABLE" in texto_acumulado: docs_encontrados.append("CONTABLE")
        if "FACTURA" in texto_acumulado: docs_encontrados.append("FACTURA")
        if "RETENCI" in texto_acumulado: docs_encontrados.append("RETENCION")
        if "ESTADO DE TRANSFERENCIA" in texto_acumulado or "BCE" in texto_acumulado: docs_encontrados.append("SPI")
        
        # Limpieza de datos para comparación
        texto_solo_numeros = re.sub(r'\D', '', texto_acumulado)
        cp_clean = re.sub(r'\D', '', str(cp_buscado))
        ruc_clean = re.sub(r'\D', '', str(ruc_buscado))

        # Validación 1: ¿Este PDF pertenece al CP buscado?
        # Buscamos el CP con fronteras para que sea exacto (evita que 340 encuentre 34)
        if cp_clean not in texto_solo_numeros:
            return "🔍 REVISAR", f"CP {cp_clean} no hallado en el texto del PDF"
        
        # Validación 2: Errores reales
        alertas = []
        if ruc_clean not in texto_solo_numeros: alertas.append("RUC no coincide")
        if "2026" in texto_acumulado: alertas.append("Fecha dice 2026")
        if "2024" in texto_acumulado and str(anio_ref) == "2025": alertas.append("Documento de 2024")
        
        # Validación 3: Piezas faltantes
        obligatorios = ["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI"]
        faltantes = [d for d in obligatorios if d not in docs_encontrados]
        
        status = "✅ OK" if not alertas and not faltantes else "🔍 REVISAR"
        obs = f"Docs: {', '.join(docs_encontrados)}. "
        if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
        if alertas: obs += " | Alertas: " + " ; ".join(alertas)
        
        return status, obs
    except Exception as e:
        return "ERROR", f"Fallo al procesar: {str(e)[:50]}"

# --- AREA DE CARGA ---
col_ex, col_pdf = st.columns(2)

with col_ex:
    st.subheader("1. Matriz Excel")
    file_excel = st.file_uploader("Subir Maestro", type=["xlsx"])
    if file_excel and st.session_state.df_maestro is None:
        st.session_state.df_maestro = pd.read_excel(file_excel)
        for col in ['AUDITADO', 'ESTADO_REVISION', 'OBSERVACION']:
            if col not in st.session_state.df_maestro.columns:
                st.session_state.df_maestro[col] = "PENDIENTE"
        st.rerun()

with col_pdf:
    st.subheader("2. Comprobantes PDF")
    archivos_lote = st.file_uploader(
        "Cargar lotes de PDFs", 
        type=["pdf"], 
        accept_multiple_files=True,
        key=f"upl_{st.session_state.pdf_uploader_key}"
    )

st.markdown("---")

if st.session_state.df_maestro is not None:
    df = st.session_state.df_maestro
    
    # Identificar columnas
    c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("🚀 INICIAR AUDITORÍA"):
            if not archivos_lote:
                st.error("Carga PDFs primero.")
            else:
                progreso = st.progress(0)
                status_msg = st.empty()
                for i, pdf in enumerate(archivos_lote):
                    # Buscar CP en el nombre del archivo
                    match_num = re.search(r'\d+', pdf.name)
                    if match_num:
                        cp_archivo = match_num.group()
                        # Buscar coincidencia exacta en el Excel
                        # Convertimos a string y quitamos .0 para asegurar match
                        idx_list = df[df[c_cp].astype(str).str.split('.').str[0] == cp_archivo].index
                        
                        if not idx_list.empty:
                            idx = idx_list[0]
                            ruc_obj = df.at[idx, c_ruc]
                            status_msg.info(f"Analizando CP {cp_archivo}...")
                            res_status, res_obs = procesar_un_pdf(pdf, cp_archivo, ruc_obj, 2025)
                            
                            df.at[idx, 'ESTADO_REVISION'] = res_status
                            df.at[idx, 'OBSERVACION'] = res_obs
                            df.at[idx, 'AUDITADO'] = "SÍ"
                    progreso.progress((i + 1) / len(archivos_lote))
                st.session_state.df_maestro = df
                status_msg.success("Lote terminado.")
    
    with c2:
        if st.button("🗑️ LIMPIAR PDFs (Mantener Excel)"):
            st.session_state.pdf_uploader_key += 1
            st.rerun()
            
    with c3:
        if st.button("🚨 BORRAR TODO"):
            st.session_state.df_maestro = None
            st.session_state.pdf_uploader_key += 1
            st.rerun()

    st.dataframe(st.session_state.df_maestro, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.df_maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR EXCEL", output.getvalue(), "Auditoria_Final.xlsx")
