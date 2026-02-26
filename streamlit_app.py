import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_bytes
import re
import io
import zipfile
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Integral Xavier", layout="wide")

# --- MEMORIA DE SESIÓN (Crucial para no re-instalar nada) ---
if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'procesados' not in st.session_state: st.session_state.procesados = set()

st.title("🛡️ Sistema de Auditoría Xavier - Versión Oficina (ZIP-Stable)")
st.markdown("---")

def realizar_ocr(pdf_bytes):
    try:
        # DPI 120 para velocidad y estabilidad en red de oficina
        images = convert_from_bytes(pdf_bytes, dpi=120)
        texto = ""
        for img in images:
            texto += pytesseract.image_to_string(ImageOps.grayscale(img), lang='spa').upper()
        return texto
    except: return ""

def auditar_contenido(texto, cp, ruc, anio_ref):
    hallazgos = []
    docs = []
    
    # Identificación de Cabeceras (Tu requerimiento)
    if "PAGO" in texto or "COMPROBANTE DE PAGO" in texto: docs.append("PAGO")
    if "CONTABLE" in texto: docs.append("CONTABLE")
    if "FACTURA" in texto: docs.append("FACTURA")
    if "RETENCI" in texto: docs.append("RETENCION")
    if "TRANSFERENCIA" in texto or "BCE" in texto or "ESTADO DE" in texto: docs.append("SPI (Sol Valdivia)")

    # Limpieza para búsqueda
    t_clean = re.sub(r'\D', '', texto)
    cp_clean = re.sub(r'\D', '', str(cp))
    ruc_clean = re.sub(r'\D', '', str(ruc))

    # Reglas de QA
    if cp_clean not in t_clean: return "🔍 REVISAR", "CP no hallado en el documento"
    if ruc_clean not in t_clean: hallazgos.append("RUC no coincide")
    if "2026" in texto: hallazgos.append("Error año: Dice 2026")
    if "2024" in texto and str(anio_ref) == "2025": hallazgos.append("Documento año anterior")
    
    obligatorios = ["PAGO", "CONTABLE", "FACTURA", "RETENCION", "SPI (Sol Valdivia)"]
    faltantes = [d for d in obligatorios if d not in docs]

    # Amortización (Regla 5)
    amort = 0.0
    m = re.search(r"AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})", texto)
    if m: amort = float(m.group(1).replace('.', '').replace(',', '.'))

    status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
    obs = f"Docs: {', '.join(docs)}. "
    if faltantes: obs += f"Faltan: {', '.join(faltantes)}. "
    if hallazgos: obs += " | Alertas: " + " ; ".join(hallazgos)
    if amort > 0: obs += f" | Anticipo: ${amort}"
    
    return status, obs

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("1. Configuración")
    entidad = st.selectbox("Entidad", ["EMAPAG", "ÉPICO"])
    anio_f = st.number_input("Año Fiscal", value=2025)
    
    st.markdown("---")
    # Botón 1: Borrar PDFs procesados
    if st.button("🗑️ Limpiar Lote de PDFs"):
        st.session_state.procesados = set()
        st.success("Lote limpio. El Excel se mantiene.")
    
    # Botón 2: Borrar TODO
    if st.button("🚨 Reiniciar TODO (Borrar Excel)"):
        st.session_state.maestro = None
        st.rerun()

# --- CARGA DE ARCHIVOS ---
col1, col2 = st.columns(2)
with col1:
    ex_file = st.file_uploader("Subir Matriz Maestro", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        for c in ['ESTADO', 'OBSERVACION', 'REVISADO']:
            if c not in st.session_state.maestro.columns: st.session_state.maestro[c] = "PENDIENTE"

with col2:
    zip_file = st.file_uploader("Subir PDFs en archivo ZIP (Recomendado)", type=["zip", "pdf"], accept_multiple_files=True)

# --- PROCESAMIENTO ---
if st.session_state.maestro is not None and zip_file:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        
        # Procesar si es ZIP o lista de PDFs
        lista_archivos = []
        if isinstance(zip_file, list):
            lista_archivos = zip_file
        else:
            # Si es un solo ZIP, extraemos en memoria
            with zipfile.ZipFile(zip_file) as z:
                for name in z.namelist():
                    if name.endswith(".pdf"):
                        lista_archivos.append((name, z.read(name)))

        progreso = st.progress(0)
        status_msg = st.empty()

        for i, item in enumerate(lista_archivos):
            name = item.name if hasattr(item, 'name') else item[0]
            content = item.read() if hasattr(item, 'read') else item[1]
            
            num_cp = re.search(r'\d+', name)
            if num_cp:
                cp_id = num_cp.group()
                idx_f = df[df[c_cp].astype(str).str.contains(cp_id)].index
                if not idx_f.empty:
                    idx = idx_f[0]
                    status_msg.info(f"Procesando: {name}...")
                    res_st, res_ob = auditar_contenido(realizar_ocr(content), cp_id, df.at[idx, c_ruc], anio_f)
                    df.at[idx, 'ESTADO'] = res_st
                    df.at[idx, 'OBSERVACION'] = res_ob
                    df.at[idx, 'REVISADO'] = "SÍ"
            progreso.progress((i + 1) / len(lista_archivos))
        
        st.session_state.maestro = df
        status_msg.success("Lote terminado.")

    st.dataframe(st.session_state.df_maestro if 'df_maestro' in st.session_state else st.session_state.maestro, use_container_width=True)
    
    # Exportar
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        st.session_state.maestro.to_excel(w, index=False)
    st.download_button("📥 Descargar Avance Auditoría", out.getvalue(), "Maestro_Auditado.xlsx")
