import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_bytes
import re
import io
import zipfile
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Pro Xavier V13", layout="wide")

# --- PERSISTENCIA ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'pdf_key' not in st.session_state: st.session_state.pdf_key = 0

st.title("🛡️ Sistema de Auditoría Xavier - Versión Definitiva")
st.markdown("---")

def realizar_ocr_ligero(pdf_bytes):
    try:
        # Usamos DPI 100 para que sea ultra rápido y no sature la red de tu oficina
        images = convert_from_bytes(pdf_bytes, dpi=100)
        texto = ""
        for img in images:
            # Convertimos a Blanco y Negro puro para que Tesseract no se confunda
            img = ImageOps.grayscale(img)
            texto += pytesseract.image_to_string(img, lang='spa').upper()
        return texto
    except Exception as e:
        return f"ERROR LECTURA: {str(e)}"

def auditar_campos(texto, cp_ex, ruc_ex, anio_ref):
    hallazgos = []
    docs_detectados = []
    
    # Identificar documentos por palabras clave
    if "PAGO" in texto: docs_detectados.append("PAGO")
    if "CONTABLE" in texto: docs_detectados.append("CONTABLE")
    if "FACTURA" in texto: docs_detectados.append("FACTURA")
    if "RETENCI" in texto: docs_detectados.append("RETENCION")
    if "TRANSFERENCIA" in texto or "BCE" in texto: docs_detectados.append("SPI (SOL VALDIVIA)")

    # Limpieza estricta para comparar números
    t_clean = re.sub(r'\D', '', texto)
    cp_clean = re.sub(r'\D', '', str(cp_ex))
    ruc_clean = re.sub(r'\D', '', str(ruc_ex))

    # REGLA 1: El CP debe estar en el texto
    if cp_clean not in t_clean:
        return "🔍 REVISAR", f"El número {cp_clean} no aparece en el contenido del PDF."

    # REGLA 2: RUC
    if ruc_clean not in t_clean: hallazgos.append("RUC no coincide")
    
    # REGLA 3: Fechas
    if "2026" in texto: hallazgos.append("Fecha dice 2026")
    if "2024" in texto and str(anio_ref) == "2025": hallazgos.append("Año 2024 (Revisar)")

    # Amortización de Anticipos (Tu requerimiento clave)
    amort = 0.0
    m = re.search(r"AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})", texto)
    if m:
        try: amort = float(m.group(1).replace('.', '').replace(',', '.'))
        except: pass

    faltantes = set(["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI (SOL VALDIVIA)"]) - set(docs_detectados)
    
    status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
    obs = f"Visto: {', '.join(docs_detectados)}. "
    if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
    if hallazgos: obs += " | Alertas: " + " ; ".join(hallazgos)
    if amort > 0: obs += f" | Anticipo: ${amort}"
    
    return status, obs

# --- INTERFAZ ---
with st.sidebar:
    st.header("1. Configuración")
    entidad = st.selectbox("Entidad", ["EMAPAG", "ÉPICO"])
    anio_f = st.number_input("Año Revisión", value=2025)
    
    st.markdown("---")
    if st.button("🗑️ Limpiar Lote PDF"):
        st.session_state.pdf_key += 1
        st.rerun()
    if st.button("🚨 Reiniciar TODO"):
        st.session_state.maestro = None
        st.rerun()

# --- CARGA ---
c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("Subir Excel Maestro", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO', 'OBSERVACION', 'AUDITADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with c2:
    zip_pdf = st.file_uploader("Subir PDFs (ZIP o sueltos)", type=["zip", "pdf"], accept_multiple_files=True, key=f"upl_{st.session_state.pdf_key}")

# --- PROCESO ---
if st.session_state.maestro is not None and zip_pdf:
    if st.button("🚀 INICIAR VERIFICACIÓN"):
        df = st.session_state.maestro
        
        # Identificar columnas
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)

        # Preparar lista de archivos
        files_to_process = []
        for item in zip_pdf:
            if item.name.endswith(".zip"):
                with zipfile.ZipFile(item) as z:
                    for n in z.namelist():
                        if n.upper().endswith(".PDF"): files_to_process.append((n, z.read(n)))
            else:
                files_to_process.append((item.name, item.read()))

        progreso = st.progress(0)
        log_status = st.empty()

        for i, (fname, fcontent) in enumerate(files_to_process):
            # Buscar número en el nombre del archivo
            num_match = re.search(r'\d+', fname)
            if num_match:
                cp_id = num_match.group()
                # Match exacto con el Excel
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_list.empty:
                    idx = idx_list[0]
                    log_status.info(f"Auditando CP {cp_id} (Archivo: {fname})")
                    
                    texto_leido = realizar_ocr_ligero(fcontent)
                    st_res, ob_res = auditar_campos(texto_leido, cp_id, df.at[idx, c_ruc], anio_f)
                    
                    df.at[idx, 'ESTADO'] = st_res
                    df.at[idx, 'OBSERVACION'] = ob_res
                    df.at[idx, 'AUDITADO'] = "SÍ"
                else:
                    st.warning(f"El archivo {fname} tiene el número {cp_id}, pero ese CP no está en tu Excel.")
            
            progreso.progress((i + 1) / len(files_to_process))

        st.session_state.maestro = df
        log_status.success(f"Auditado lote de {len(files_to_process)} archivos.")

    # Mostrar Matriz
    st.write("### Avance de la Auditoría")
    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    # Exportar
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 DESCARGAR EXCEL ACTUALIZADO", out.getvalue(), "Resultado_Auditoria.xlsx")
