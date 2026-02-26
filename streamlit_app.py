import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Xavier PRO", layout="wide")

# --- PERSISTENCIA DE LA MATRIZ (Memoria de la sesión) ---
if 'df_maestro' not in st.session_state: 
    st.session_state.df_maestro = None
# Clave para reiniciar el cargador de PDFs
if 'pdf_uploader_key' not in st.session_state:
    st.session_state.pdf_uploader_key = 0

st.title("🛡️ Sistema de Auditoría por Lotes")
st.markdown("---")

def procesar_un_pdf(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        pdf_file.seek(0)
        # DPI 130 para equilibrio entre legibilidad y ahorro de memoria RAM
        images = convert_from_path(pdf_file.read(), dpi=130) 
        texto_acumulado = ""
        for img in images:
            texto_acumulado += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        # Identificación de cabeceras obligatorias
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
            return "🔍 REVISAR", f"CP {cp_clean} no hallado en el contenido del PDF"
        
        alertas = []
        if ruc_clean not in texto_limpio: alertas.append("RUC no coincide")
        if "2026" in texto_acumulado: alertas.append("Fecha errónea: 2026")
        if "2024" in texto_acumulado and anio_ref == 2025: alertas.append("Año anterior (2024)")
        
        faltantes = set(["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI"]) - set(docs_h)
        
        status = "✅ OK" if not alertas and not faltantes else "🔍 REVISAR"
        obs = f"Detectados: {', '.join(docs_h)}. "
        if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
        obs += " | ".join(alertas)
        return status, obs
    except Exception as e:
        return "ERROR", f"Fallo técnico: {str(e)}"

# --- BARRA LATERAL: GESTIÓN ESPECÍFICA ---
with st.sidebar:
    st.header("⚙️ Configuración")
    entidad = st.selectbox("Entidad", ["EMAPAG", "ÉPICO"])
    anio_f = st.number_input("Año Fiscal de Revisión", value=2025)
    
    st.markdown("---")
    st.header("📂 1. Cargar Maestro")
    file_excel = st.file_uploader("Subir Matriz Excel", type=["xlsx"])
    
    if file_excel:
        if st.session_state.df_maestro is None:
            st.session_state.df_maestro = pd.read_excel(file_excel)
            for col in ['AUDITADO', 'ESTADO_REVISION', 'OBSERVACION_TECNICA']:
                if col not in st.session_state.df_maestro.columns:
                    st.session_state.df_maestro[col] = "PENDIENTE"

    st.markdown("---")
    st.header("🧹 Limpieza de Trabajo")
    
    # BOTÓN 1: Solo borra PDFs
    if st.button("🗑️ Limpiar Lote de PDFs"):
        st.session_state.pdf_uploader_key += 1
        st.success("Cargador de PDFs reiniciado. Puedes subir el nuevo lote.")
        st.rerun()

    # BOTÓN 2: Borra TODO
    if st.button("🚨 Reiniciar Sistema Completo"):
        st.session_state.df_maestro = None
        st.session_state.pdf_uploader_key += 1
        st.warning("Todo el sistema ha sido borrado.")
        st.rerun()

# --- PANEL PRINCIPAL ---
if st.session_state.df_maestro is not None:
    df = st.session_state.df_maestro
    st.subheader(f"Auditoría: {entidad} {anio_f}")
    st.info("💡 Procesa en lotes de 10 a 15 PDFs para evitar errores de red.")
    
    # Cargador de PDFs con llave dinámica para reinicio manual
    archivos_lote = st.file_uploader(
        "Cargar lote de PDFs a procesar ahora", 
        type=["pdf"], 
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.pdf_uploader_key}"
    )

    if archivos_lote and st.button("🚀 PROCESAR ESTE LOTE"):
        progreso = st.progress(0)
        status_msg = st.empty()
        
        # Identificar columnas
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

        for i, pdf in enumerate(archivos_lote):
            # Extraer número del nombre del archivo
            num_en_nombre = re.search(r'\d+', pdf.name)
            if num_en_nombre:
                cp_detectado = num_en_nombre.group()
                
                # Buscar en el maestro
                # Limpiamos el CP del maestro para comparar
                mask = df[c_cp].astype(str).str.contains(cp_detectado)
                idx_fila = df[mask].index
                
                if not idx_fila.empty:
                    idx = idx_fila[0]
                    ruc_obj = df.at[idx, c_ruc]
                    
                    status_msg.write(f"⏳ Analizando: {pdf.name}...")
                    res_status, res_obs = procesar_un_pdf(pdf, cp_detectado, ruc_obj, anio_f)
                    
                    df.at[idx, 'ESTADO_REVISION'] = res_status
                    df.at[idx, 'OBSERVACION_TECNICA'] = res_obs
                    df.at[idx, 'AUDITADO'] = "SÍ"
            
            progreso.progress((i + 1) / len(archivos_lote))
        
        st.session_state.df_maestro = df
        status_msg.success(f"✅ Lote de {len(archivos_lote)} archivos procesado con éxito.")

    # Vista previa del avance
    st.write("### Avance de la Matriz Maestra")
    st.dataframe(df, use_container_width=True)

    # Botón de descarga
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    st.download_button(
        "📥 Descargar Avance de Auditoría (Excel)", 
        output.getvalue(), 
        file_name=f"Auditoria_{entidad}_Avance.xlsx"
    )

else:
    st.info("👈 Por favor, carga la Matriz Maestro en el panel lateral para comenzar.")
