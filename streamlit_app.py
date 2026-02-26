import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_bytes
import re
import io
from PIL import Image, ImageOps

st.set_page_config(page_title="Auditoría Integral Xavier PRO", layout="wide")

if 'maestro' not in st.session_state: st.session_state.maestro = None
if 'procesados_nombres' not in st.session_state: st.session_state.procesados_nombres = set()

st.title("🛡️ Sistema de Auditoría Xavier - EMAPAG & ÉPICO")
st.markdown("---")

def ocr_alta_resolucion(pdf_bytes):
    try:
        # Mantenemos DPI alto para no perder detalle en RUC y montos
        images = convert_from_bytes(pdf_bytes, dpi=200)
        texto_completo = ""
        for img in images:
            # Pre-procesamiento para escaneos: Grayscale + Autocontraste
            img = ImageOps.grayscale(img)
            img = ImageOps.autocontrast(img)
            texto_completo += pytesseract.image_to_string(img, lang='spa')
        return texto_completo.upper()
    except Exception as e:
        return f"ERROR_LECTURA: {str(e)}"

def realizar_auditoria(texto, ruc_excel, cp_excel, anio_ref):
    hallazgos = []
    # 1. Identificación de Documentos por Cabeceras (EMAPAG/ÉPICO)
    docs = {
        "PAGO": ["COMPROBANTE DE PAGO", "ORDEN DE PAGO", "EGRESO"],
        "CONTABLE": ["COMPROBANTE CONTABLE", "REGISTRO CONTABLE", "DIARIO"],
        "FACTURA": ["FACTURA", "FACT.", "R.U.C."],
        "RETENCION": ["RETENCION", "COMPROBANTE DE RETENCI"],
        "SPI": ["ESTADO DE TRANSFERENCIA", "BANCO CENTRAL", "SOL VALDIVIA", "BCE"]
    }
    
    encontrados = []
    for doc_tipo, palabras in docs.items():
        if any(p in texto for p in palabras):
            encontrados.append(doc_tipo)

    # 2. Limpieza de datos para cruce
    texto_nums = re.sub(r'\D', '', texto)
    ruc_clean = re.sub(r'\D', '', str(ruc_excel))
    cp_clean = re.sub(r'\D', '', str(cp_excel))

    # 3. Validaciones de QA
    if cp_clean not in texto_nums:
        return "🔍 REVISAR", f"El CP {cp_clean} no aparece en el texto del PDF."
    
    if ruc_clean not in texto_nums:
        hallazgos.append("RUC no coincide")
    
    if "2026" in texto: hallazgos.append("Alerta: Año 2026")
    if "2024" in texto and str(anio_ref) == "2025": hallazgos.append("Año anterior (2024)")

    # 4. Verificación de piezas faltantes
    faltantes = set(docs.keys()) - set(encontrados)
    
    # 5. Amortización (Regla 5)
    amort = 0.0
    m = re.search(r"AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})", texto)
    if m:
        try: amort = float(m.group(1).replace('.', '').replace(',', '.'))
        except: pass

    status = "✅ OK" if not hallazgos and not faltantes else "🔍 REVISAR"
    resumen = f"Docs: {', '.join(encontrados)}. "
    if faltantes: resumen += f"Faltan: {', '.join(faltantes)}. "
    if hallazgos: resumen += " | ALERTAS: " + " ; ".join(hallazgos)
    if amort > 0: resumen += f" | Anticipo: ${amort}"
    
    return status, resumen

# --- INTERFAZ ---
with st.sidebar:
    st.header("⚙️ Configuración")
    entidad = st.selectbox("Entidad a Auditar", ["EMAPAG", "ÉPICO"])
    anio_f = st.number_input("Año de Revisión", value=2025)
    st.markdown("---")
    if st.button("🗑️ Limpiar Lote de PDFs"):
        st.session_state.procesados_nombres = set()
        st.rerun()
    if st.button("🚨 Reiniciar Todo"):
        st.session_state.maestro = None
        st.session_state.procesados_nombres = set()
        st.rerun()

# --- FLUJO DE CARGA ---
col_ex, col_pdf = st.columns(2)

with col_ex:
    st.subheader("1. Matriz Excel")
    file_ex = st.file_uploader("Subir Maestro", type=["xlsx"])
    if file_ex and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(file_ex)
        for c in ['REVISADO', 'ESTADO_AUDITORIA', 'OBSERVACION_TECNICA']:
            if c not in st.session_state.maestro.columns:
                st.session_state.maestro[c] = "PENDIENTE"
        st.rerun()

with col_pdf:
    st.subheader("2. Documentos PDF")
    archivos_pdfs = st.file_uploader("Cargar PDFs (Máx 10 por vez)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and archivos_pdfs:
    if st.button("🚀 INICIAR AUDITORÍA"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        
        status_msg = st.empty()
        progreso = st.progress(0)

        for i, pdf in enumerate(archivos_pdfs):
            if pdf.name not in st.session_state.procesados_nombres:
                status_msg.info(f"Analizando: {pdf.name}...")
                
                # Leemos el PDF
                texto_pdf = ocr_alta_resolucion(pdf.read())
                
                # BUSCADOR INTELIGENTE: ¿A qué fila del Excel pertenece este PDF?
                # Buscamos todos los CP del Excel dentro del texto del PDF
                fila_encontrada = None
                for idx, fila in df.iterrows():
                    cp_buscado = str(fila[c_cp]).strip().split('.')[0]
                    if cp_buscado in re.sub(r'\D', '', texto_pdf):
                        fila_encontrada = idx
                        break
                
                if fila_encontrada is not None:
                    ruc_val = df.at[fila_encontrada, c_ruc]
                    cp_val = df.at[fila_encontrada, c_cp]
                    
                    st_res, ob_res = realizar_auditoria(texto_pdf, ruc_val, cp_val, anio_f)
                    
                    df.at[fila_encontrada, 'ESTADO_AUDITORIA'] = st_res
                    df.at[fila_encontrada, 'OBSERVACION_TECNICA'] = ob_res
                    df.at[fila_encontrada, 'REVISADO'] = "SÍ"
                    st.session_state.procesados_nombres.add(pdf.name)
                else:
                    st.warning(f"El archivo {pdf.name} no contiene ningún CP válido del Excel.")
                
                progreso.progress((i + 1) / len(archivos_pdfs))
        
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada para este lote.")

    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    # Exportar
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        st.session_state.maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR MAESTRO ACTUALIZADO", out.getvalue(), "Auditoria_Final.xlsx")
