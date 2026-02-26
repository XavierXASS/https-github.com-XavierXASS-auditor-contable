import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Xavier PRO", layout="wide")

# --- MEMORIA DE SESIÓN ---
if 'df_maestro' not in st.session_state: 
    st.session_state.df_maestro = None
if 'pdf_uploader_key' not in st.session_state:
    st.session_state.pdf_uploader_key = 0

st.title("🛡️ Sistema de Auditoría Xavier - Control Total")
st.markdown("---")

def procesar_un_pdf(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        pdf_file.seek(0)
        # DPI 130: Eficiencia máxima para no tumbar la conexión
        images = convert_from_path(pdf_file.read(), dpi=130) 
        texto_acumulado = ""
        for img in images:
            texto_acumulado += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        # Identificación de piezas
        docs_h = []
        if "COMPROBANTE DE PAGO" in texto_acumulado: docs_h.append("PAGO")
        if "COMPROBANTE CONTABLE" in texto_acumulado: docs_h.append("CONTABLE")
        if "FACTURA" in texto_acumulado: docs_h.append("FACTURA")
        if "RETENCI" in texto_acumulado: docs_h.append("RETENCION")
        if "ESTADO DE TRANSFERENCIA" in texto_acumulado: docs_h.append("SPI")
        
        texto_limpio = re.sub(r'\D', '', texto_acumulado)
        ruc_clean = re.sub(r'\D', '', str(ruc_buscado))
        cp_clean = re.sub(r'\D', '', str(cp_buscado))

        if cp_clean not in texto_limpio:
            return "🔍 REVISAR", f"CP {cp_clean} no hallado en el PDF"
        
        alertas = []
        if ruc_clean not in texto_limpio: alertas.append("RUC no coincide")
        if "2026" in texto_acumulado: alertas.append("Fecha dice 2026")
        if "2024" in texto_acumulado and anio_ref == 2025: alertas.append("Año anterior (2024)")
        
        faltantes = set(["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI"]) - set(docs_h)
        
        status = "✅ OK" if not alertas and not faltantes else "🔍 REVISAR"
        obs = f"Detectados: {', '.join(docs_h)}. "
        if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
        if alertas: obs += " | Alertas: " + " ; ".join(alertas)
        return status, obs
    except Exception as e:
        return "ERROR", f"Fallo técnico: {str(e)}"

# --- AREA DE CARGA (SIEMPRE VISIBLE) ---
col_ex, col_pdf = st.columns(2)

with col_ex:
    st.subheader("1. Matriz Excel")
    file_excel = st.file_uploader("Subir Maestro", type=["xlsx"])
    if file_excel and st.session_state.df_maestro is None:
        st.session_state.df_maestro = pd.read_excel(file_excel)
        for col in ['AUDITADO', 'ESTADO_REVISION', 'OBSERVACION']:
            if col not in st.session_state.df_maestro.columns:
                st.session_state.df_maestro[col] = "PENDIENTE"
        st.success("Excel cargado correctamente.")

with col_pdf:
    st.subheader("2. Comprobantes PDF")
    archivos_lote = st.file_uploader(
        "Cargar lotes de PDFs", 
        type=["pdf"], 
        accept_multiple_files=True,
        key=f"upl_{st.session_state.pdf_uploader_key}"
    )
    if archivos_lote:
        st.info(f"{len(archivos_lote)} archivos listos para procesar.")

st.markdown("---")

# --- ACCIONES Y RESULTADOS ---
if st.session_state.df_maestro is not None:
    # Botones de limpieza en el centro para fácil acceso
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("🚀 INICIAR AUDITORÍA DEL LOTE"):
            if not archivos_lote:
                st.error("Sube primero los PDFs a la derecha.")
            else:
                df = st.session_state.df_maestro
                progreso = st.progress(0)
                status_msg = st.empty()
                
                # Identificar columnas
                c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
                c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

                for i, pdf in enumerate(archivos_lote):
                    num_en_nombre = re.search(r'\d+', pdf.name)
                    if num_en_nombre:
                        cp_detectado = num_en_nombre.group()
                        mask = df[c_cp].astype(str).str.contains(cp_detectado)
                        idx_fila = df[mask].index
                        
                        if not idx_fila.empty:
                            idx = idx_fila[0]
                            ruc_obj = df.at[idx, c_ruc]
                            status_msg.write(f"⏳ Analizando CP {cp_detectado}...")
                            res_status, res_obs = procesar_un_pdf(pdf, cp_detectado, ruc_obj, 2025) # 2025 por defecto
                            
                            df.at[idx, 'ESTADO_REVISION'] = res_status
                            df.at[idx, 'OBSERVACION'] = res_obs
                            df.at[idx, 'AUDITADO'] = "SÍ"
                    
                    progreso.progress((i + 1) / len(archivos_lote))
                
                st.session_state.df_maestro = df
                status_msg.success(f"Lote de {len(archivos_lote)} terminado.")
    
    with c2:
        if st.button("🗑️ LIMPIAR PDFs (Mantener Excel)"):
            st.session_state.pdf_uploader_key += 1
            st.rerun()
            
    with c3:
        if st.button("🚨 BORRAR TODO"):
            st.session_state.df_maestro = None
            st.session_state.pdf_uploader_key += 1
            st.rerun()

    # Mostrar Tabla
    st.write("### Avance de la Auditoría")
    st.dataframe(st.session_state.df_maestro, use_container_width=True)

    # Descarga
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.df_maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR EXCEL ACTUALIZADO", output.getvalue(), "Auditoria_Xavier.xlsx")

else:
    st.warning("Paso 1: Sube el archivo Excel arriba a la izquierda para habilitar la revisión.")
