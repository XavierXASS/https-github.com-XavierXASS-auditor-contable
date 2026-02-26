import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_bytes
import re
import io
from PIL import Image, ImageOps

# CONFIGURACIÓN DE ALTO RENDIMIENTO
st.set_page_config(page_title="Auditoría Xavier FINAL", layout="wide")

# Mantenemos los resultados aunque se borren los PDFs cargados
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'log_exito' not in st.session_state: st.session_state.log_exito = []

st.title("🛡️ Auditoría Xavier - Versión Ultra-Estable")
st.markdown("---")

def ocr_super_ligero(pdf_bytes):
    try:
        # DPI 90: Suficiente para leer RUC y CP, pero usa 70% menos memoria
        images = convert_from_bytes(pdf_bytes, dpi=90)
        texto = ""
        for img in images:
            # Procesamiento de imagen para máximo contraste (Blanco y Negro)
            img = ImageOps.grayscale(img)
            img = ImageOps.autocontrast(img)
            texto += pytesseract.image_to_string(img, lang='spa').upper()
        return texto
    except: return ""

def auditar(texto, cp, ruc, anio_ref):
    docs = []
    # Identificación de Cabeceras (Tu requerimiento)
    if "PAGO" in texto: docs.append("PAGO")
    if "CONTABLE" in texto: docs.append("CONTABLE")
    if "FACTURA" in texto: docs.append("FACTURA")
    if "RETENCI" in texto: docs.append("RETENCION")
    if "TRANSFERENCIA" in texto or "BCE" in texto: docs.append("SPI")

    t_num = re.sub(r'\D', '', texto)
    cp_num = re.sub(r'\D', '', str(cp))
    ruc_num = re.sub(r'\D', '', str(ruc))

    hallazgos = []
    if cp_num not in t_num: return "🔍 REVISAR", "El CP no se encuentra escrito en el PDF."
    if ruc_num not in t_num: hallazgos.append("RUC no coincide")
    if "2026" in texto: hallazgos.append("Alerta: Fecha 2026")
    if "2024" in texto and str(anio_ref) == "2025": hallazgos.append("Año anterior")
    
    # Amortizaciones (Regla 5)
    amort = 0.0
    m = re.search(r"AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})", texto)
    if m: amort = float(m.group(1).replace('.', '').replace(',', '.'))

    faltantes = set(["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI"]) - set(docs)
    status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
    
    obs = f"Docs: {', '.join(docs)}. "
    if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
    if hallazgos: obs += " | " + " ; ".join(hallazgos)
    if amort > 0: obs += f" | Anticipo: ${amort}"
    
    return status, obs

# --- INTERFAZ ---
with st.sidebar:
    st.header("Configuración")
    anio_f = st.number_input("Año de Revisión", value=2025)
    st.markdown("---")
    if st.button("🗑️ Borrar Excel y Resultados"):
        st.session_state.maestro = None
        st.session_state.log_exito = []
        st.rerun()

# CARGA DE EXCEL (Solo una vez)
if st.session_state.maestro is None:
    ex_file = st.file_uploader("1. Sube tu Matriz Excel", type=["xlsx"])
    if ex_file:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO_AUDITORIA', 'OBSERVACION_TECNICA']:
            if c not in st.session_state.maestro.columns:
                st.session_state.maestro[c] = "PENDIENTE"
        st.rerun()

# PROCESAMIENTO DE PDFs
if st.session_state.maestro is not None:
    st.subheader("2. Cargar Comprobantes")
    st.info("💡 Sube los PDFs de 1 en 1 (o en grupos de 3). El sistema los procesará al instante.")
    
    # El secreto: Cada carga se procesa y el uploader se limpia solo después
    pdf_input = st.file_uploader("Arrastra aquí tus PDFs", type=["pdf"], accept_multiple_files=True)
    
    if pdf_input:
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

        for pdf in pdf_input:
            if pdf.name not in st.session_state.log_exito:
                # Extraer CP del nombre
                num_en_nombre = re.search(r'\d+', pdf.name)
                if num_en_nombre:
                    cp_detectado = num_en_nombre.group()
                    idx_fila = df[df[c_cp].astype(str).str.contains(cp_detectado)].index
                    
                    if not idx_fila.empty:
                        idx = idx_fila[0]
                        with st.spinner(f"Auditando {pdf.name}..."):
                            txt = ocr_super_ligero(pdf.read())
                            st_res, ob_res = auditar(txt, cp_detectado, df.at[idx, c_ruc], anio_f)
                            df.at[idx, 'ESTADO_AUDITORIA'] = st_res
                            df.at[idx, 'OBSERVACION_TECNICA'] = ob_res
                            st.session_state.log_exito.append(pdf.name)
                else:
                    st.warning(f"No se detectó número de CP en el nombre: {pdf.name}")
        
        st.session_state.maestro = df
        st.success("Lote procesado. Los resultados se guardaron abajo.")

    # MOSTRAR RESULTADOS
    st.markdown("---")
    st.write("### Vista Previa de la Auditoría")
    st.dataframe(st.session_state.maestro, use_container_width=True)

    # DESCARGA
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR RESULTADOS FINALES", output.getvalue(), "Auditoria_Final.xlsx")

else:
    st.warning("Paso 1: Sube el archivo Excel Maestro.")
