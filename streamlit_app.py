import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Xavier PRO", layout="wide")

# Solo guardamos el progreso del Excel, NO los PDFs (para no saturar la memoria)
if 'df_maestro' not in st.session_state: st.session_state.df_maestro = None

st.title("🛡️ Auditoría Inteligente (Versión Estable)")
st.markdown("---")

def procesar_un_pdf(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        # Leemos con resolución moderada para evitar "Network Error"
        images = convert_from_path(pdf_file, dpi=130) 
        texto_acumulado = ""
        for img in images:
            texto_acumulado += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        hallazgos = []
        # Identificar documentos
        if "FACTURA" in texto_acumulado: hallazgos.append("FACTURA")
        if "RETENCI" in texto_acumulado: hallazgos.append("RETENCION")
        if "TRANSFERENCIA" in texto_acumulado: hallazgos.append("SPI")
        
        # Limpieza para validación
        texto_limpio = re.sub(r'\D', '', texto_acumulado)
        ruc_clean = re.sub(r'\D', '', str(ruc_buscado))
        cp_clean = re.sub(r'\D', '', str(cp_buscado))

        if cp_clean not in texto_limpio:
            return "🔍 REVISAR", "CP no hallado en el contenido del PDF"
        
        alertas = []
        if ruc_clean not in texto_limpio: alertas.append("RUC no coincide")
        if "2026" in texto_acumulado: alertas.append("Fecha dice 2026")
        
        status = "✅ OK" if not alertas else "🔍 REVISAR"
        obs = f"Detectado: {', '.join(hallazgos)}. " + " | ".join(alertas)
        return status, obs
    except Exception as e:
        return "ERROR", f"Fallo de lectura: {str(e)}"

# --- INTERFAZ ---
with st.sidebar:
    st.header("1. Configuración")
    entidad = st.selectbox("Empresa", ["EMAPAG", "ÉPICO"])
    anio_fiscal = st.number_input("Año", value=2025)
    
    st.header("2. Cargar Maestro")
    file_excel = st.file_uploader("Subir Excel", type=["xlsx"])
    if file_excel:
        if st.session_state.df_maestro is None:
            st.session_state.df_maestro = pd.read_excel(file_excel)
            for col in ['AUDITADO', 'ESTADO', 'OBSERVACION']:
                if col not in st.session_state.df_maestro.columns:
                    st.session_state.df_maestro[col] = "NO"

    if st.button("🗑️ Reiniciar Todo"):
        st.session_state.df_maestro = None
        st.rerun()

# --- CUERPO ---
if st.session_state.df_maestro is not None:
    df = st.session_state.df_maestro
    
    st.subheader(f"Auditoría {entidad} {anio_fiscal}")
    st.info("Para evitar errores de red, sube los PDFs en grupos de máximo 15 archivos.")
    
    # El cargador de PDF ahora está en el cuerpo principal
    archivos_subidos = st.file_uploader("Cargar PDFs a procesar", type=["pdf"], accept_multiple_files=True)

    if archivos_subidos and st.button("🚀 PROCESAR ESTE LOTE"):
        # Mapear PDFs por número encontrado en el nombre (opcional) o por contenido
        progreso = st.progress(0)
        
        for i, pdf in enumerate(archivos_subidos):
            # Intentar extraer el CP del nombre del archivo para saber qué fila auditar
            # Buscamos el primer número largo en el nombre del archivo
            cp_en_nombre = re.search(r'\d+', pdf.name)
            if cp_en_nombre:
                cp_detectado = cp_en_nombre.group()
                
                # Buscar esta fila en el maestro
                # (Buscamos en la columna que contenga "PAGO" o "CP")
                col_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
                
                idx_fila = df[df[col_cp].astype(str).str.contains(cp_detectado)].index
                
                if not idx_fila.empty:
                    idx = idx_fila[0]
                    ruc_obj = df.at[idx, next(c for c in df.columns if "RUC" in str(c).upper())]
                    
                    # Analizar
                    st.write(f"Procesando: {pdf.name}...")
                    status, obs = procesar_un_pdf(pdf, cp_detectado, ruc_obj, anio_fiscal)
                    
                    df.at[idx, 'ESTADO'] = status
                    df.at[idx, 'OBSERVACION'] = obs
                    df.at[idx, 'AUDITADO'] = "SÍ"
            
            progreso.progress((i + 1) / len(archivos_subidos))
        
        st.session_state.df_maestro = df
        st.success("Lote procesado. Puedes descargar el avance o subir más archivos.")

    st.dataframe(df, use_container_width=True)

    # Descarga
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    st.download_button("📥 Descargar Maestro Auditado", output.getvalue(), f"Auditoria_{entidad}.xlsx")

else:
    st.warning("Carga el archivo Excel en la izquierda para comenzar.")
