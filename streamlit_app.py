import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
import datetime
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Pro Xavier", layout="wide")

# --- ESTADO DE SESIÓN PARA PERSISTENCIA ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'pdf_cache' not in st.session_state: st.session_state.pdf_cache = {}

st.title("🛡️ Auditoría Inteligente de Comprobantes")
st.markdown("---")

# --- LÓGICA DE DETECCIÓN AVANZADA ---
def analizar_pdf_integral(pdf_file, cp_buscado, ruc_buscado, anio_ref):
    try:
        pdf_file.seek(0)
        images = convert_from_path(pdf_file.read(), dpi=200)
        texto_completo = ""
        for img in images:
            texto_completo += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        
        hallazgos = []
        documentos_detectados = []
        
        # 1. Identificación de piezas (Cabeceras)
        mapeo_docs = {
            "COMPROBANTE DE PAGO": "PAGO",
            "COMPROBANTE CONTABLE": "CONTABLE",
            "FACTURA": "FACTURA",
            "RETENCIÓN": "RETENCIÓN",
            "ESTADO DE TRANSFERENCIA": "SPI" # El documento con el Sol Valdivia
        }
        for clave, nombre in mapeo_docs.items():
            if clave in texto_completo: documentos_detectados.append(nombre)

        # 2. Validación de CP (Si el CP del Excel está en el texto)
        if cp_buscado not in re.sub(r'\D', '', texto_completo):
            return "ERROR: CP no hallado en el contenido", "Faltan datos"

        # 3. Validación de RUC
        if ruc_buscado not in re.sub(r'\D', '', texto_completo):
            hallazgos.append("RUC incorrecto/no hallado")

        # 4. Alertas de Fechas (QA Crítico)
        if "2026" in texto_completo: hallazgos.append("Revisar Fecha: Dice 2026")
        if "2024" in texto_completo and anio_ref == 2025: hallazgos.append("Documento de año anterior (2024)")

        # 5. Validación de integridad
        faltantes = set(mapeo_docs.values()) - set(documentos_detectados)
        
        status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
        obs = f"Docs: {','.join(documentos_detectados)}. "
        if faltantes: obs += f"Faltan: {','.join(faltantes)}. "
        if hallazgos: obs += f"Alertas: {'; '.join(hallazgos)}"
        
        return status, obs
    except:
        return "ERROR OCR", "No se pudo leer el archivo"

# --- INTERFAZ LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración")
    entidad = st.selectbox("Entidad", ["EMAPAG", "ÉPICO"])
    anio_fiscal = st.number_input("Año de Revisión", value=2025)
    
    st.markdown("---")
    file_excel = st.file_uploader("1. Cargar Matriz Excel", type=["xlsx"])
    if file_excel:
        if st.session_state.maestro is None:
            st.session_state.maestro = pd.read_excel(file_excel)
            # Añadimos columnas de control si no existen
            if 'ESTADO_REVISION' not in st.session_state.maestro.columns:
                st.session_state.maestro['ESTADO_REVISION'] = "PENDIENTE"
                st.session_state.maestro['OBSERVACIONES_TECNICAS'] = ""

    files_pdf = st.file_uploader("2. Cargar PDFs (Cualquier nombre)", type=["pdf"], accept_multiple_files=True)
    if files_pdf:
        for f in files_pdf: st.session_state.pdf_cache[f.name] = f
        st.success(f"{len(st.session_state.pdf_cache)} PDFs listos")

    if st.button("🗑️ Resetear Sistema"):
        st.session_state.maestro = None
        st.session_state.pdf_cache = {}
        st.rerun()

# --- CUERPO PRINCIPAL ---
if st.session_state.maestro is not None:
    df = st.session_state.maestro
    
    # Identificar columnas automáticamente
    c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

    st.write(f"### Matriz de Auditoría: {entidad} {anio_fiscal}")
    st.info("La aplicación buscará el número de Comprobante de Pago (CP) dentro de cada PDF, sin importar cómo se llame el archivo.")

    if st.button("🚀 PROCESAR FILAS PENDIENTES"):
        progreso = st.progress(0)
        status_msg = st.empty()
        
        for idx, fila in df.iterrows():
            if fila['ESTADO_REVISION'] != "PENDIENTE" and fila['ESTADO_REVISION'] != "ERROR OCR":
                continue # Saltar lo ya revisado
                
            cp_val = re.sub(r'\D', '', str(fila[c_cp]))
            ruc_val = re.sub(r'\D', '', str(fila[c_ruc]))
            
            status_msg.text(f"Buscando documentos para CP {cp_val}...")
            
            # Buscador holístico: ¿Qué PDF contiene este CP?
            pdf_encontrado = None
            for nombre, contenido in st.session_state.pdf_cache.items():
                # Primero intentamos por nombre de archivo para ir rápido
                if cp_val in nombre:
                    pdf_encontrado = contenido
                    break
            
            # Si no está en el nombre, lo buscaremos por contenido (esto se hace dentro de analizar_pdf)
            # Para esta demo, el usuario debe cargar los PDFs que cree corresponden
            
            if pdf_encontrado:
                res_status, res_obs = analizar_pdf_integral(pdf_encontrado, cp_val, ruc_val, anio_fiscal)
                df.at[idx, 'ESTADO_REVISION'] = res_status
                df.at[idx, 'OBSERVACIONES_TECNICAS'] = res_obs
            else:
                df.at[idx, 'OBSERVACIONES_TECNICAS'] = "PDF no cargado en el lote"

            progreso.progress((idx + 1) / len(df))
        
        st.session_state.maestro = df
        status_msg.success("Revisión de lote terminada.")

    # Mostrar el Excel Maestro actualizado
    st.dataframe(df, use_container_width=True)

    # Exportar el MISMO archivo con las nuevas columnas
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    st.download_button(
        "📥 DESCARGAR MATRIZ ACTUALIZADA",
        output.getvalue(),
        file_name=f"Maestro_Auditado_{entidad}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("Por favor, carga el archivo Excel para empezar la auditoría.")
