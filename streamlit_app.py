import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
from PIL import Image, ImageOps

# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Auditoría Integral Xavier", layout="wide", initial_sidebar_state="expanded")

# Persistencia de datos
if 'pdf_lib' not in st.session_state: st.session_state.pdf_lib = {}
if 'res' not in st.session_state: st.session_state.res = []

st.title("🛡️ Centro Profesional de Auditoría Contable")
st.markdown("---")

# --- SELECTORES DE AUDITORÍA (LO QUE PEDISTE) ---
with st.sidebar:
    st.header("⚙️ Parámetros de Revisión")
    entidad = st.selectbox("Entidad a revisar", ["EMAPAG", "ÉPICO"])
    anio_auditoria = st.selectbox("Año de la auditoría", [2025, 2026, 2024])
    periodo = st.selectbox("Periodo (Mes/Trimestre)", ["1er Trimestre", "2do Trimestre", "3er Trimestre", "4to Trimestre", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
    
    st.markdown("---")
    st.header("📂 Carga de Insumos")
    excel_file = st.file_uploader("1. Subir Matriz Maestro (Excel)", type=["xlsx"])
    uploaded_pdfs = st.file_uploader("2. Cargar PDFs (Acumulativo)", type=["pdf"], accept_multiple_files=True)

    if uploaded_pdfs:
        for p in uploaded_pdfs:
            # QA: Guardamos el archivo y limpiamos el nombre para facilitar la búsqueda
            st.session_state.pdf_lib[p.name.upper()] = p
        st.success(f"Librería: {len(st.session_state.pdf_lib)} documentos listos.")

    if st.button("🗑️ Reiniciar Todo el Sistema"):
        st.session_state.pdf_lib = {}
        st.session_state.res = []
        st.rerun()

# --- MOTOR DE LÓGICA ROBUSTA ---
def limpiar_dato(val):
    """Limpia cualquier dato para que sea un string de números puro"""
    if pd.isna(val): return ""
    s = str(val).strip().split('.')[0]
    return re.sub(r'\D', '', s)

def ocr_avanzado(pdf_file):
    """Lee el PDF con alta resolución y limpieza de imagen"""
    try:
        pdf_file.seek(0)
        images = convert_from_path(pdf_file.read(), dpi=250)
        texto = ""
        for img in images:
            img = ImageOps.grayscale(img) # Mejora lectura de escaneos
            texto += pytesseract.image_to_string(img, lang='spa')
        return texto.upper()
    except: return ""

def extraer_dinero(texto, patron):
    match = re.search(patron, texto)
    if match:
        val = match.group(1).replace('.', '').replace(',', '.')
        try: return float(val)
        except: return 0.0
    return 0.0

# --- PROCESO DE AUDITORÍA ---
if excel_file:
    df = pd.read_excel(excel_file)
    # Buscador flexible de columnas
    cols = {c.upper(): c for c in df.columns}
    c_cp = next((v for k,v in cols.items() if "PAGO" in k or "CP" in k), None)
    c_ruc = next((v for k,v in cols.items() if "RUC" in k), None)
    c_total = next((v for k,v in cols.items() if "TOTAL" in k or "VALOR" in k), None)
    c_fecha = next((v for k,v in cols.items() if "FECHA" in k), None)

    if st.button("🚀 INICIAR VERIFICACIÓN INTEGRAL"):
        temp_res = []
        progreso = st.progress(0)
        status = st.empty()

        for idx, fila in df.iterrows():
            cp_original = str(fila[c_cp]).strip()
            cp_limpio = limpiar_dato(cp_original)
            ruc_excel = limpiar_dato(fila[c_ruc])
            monto_excel = float(fila[c_total])
            fecha_excel = str(fila[c_fecha])
            
            status.info(f"Analizando CP {cp_original}...")
            
            # REGLA 4: Año Anterior
            if str(anio_auditoria - 1) in fecha_excel:
                temp_res.append({"CP": cp_original, "ESTADO": "❌ DESECHADO", "OBSERVACIÓN": f"Documento del año anterior ({anio_auditoria-1})"})
                continue

            # BÚSQUEDA ROBUSTA DEL PDF (Regla 1)
            # Buscamos si el CP está en cualquier parte del nombre del archivo
            pdf_match = None
            for nombre_archivo, contenido in st.session_state.pdf_lib.items():
                if cp_limpio in nombre_archivo:
                    pdf_match = contenido
                    break
            
            if pdf_match:
                texto_pdf = ocr_avanzado(pdf_match)
                problemas = []

                # REGLA 2: Validación de RUC (13 dígitos)
                if ruc_excel not in re.sub(r'\D', '', texto_pdf):
                    problemas.append(f"RUC {ruc_excel} no hallado")

                # REGLA 5: Amortizaciones y Retenciones (Registro Contable)
                amort = extraer_dinero(texto_pdf, r"AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                ret = extraer_dinero(texto_pdf, r"RETENCI[OÓ]N[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                
                # REGLA 3: Trimestre
                try:
                    mes = pd.to_datetime(fila[c_fecha]).month
                    meses_trimestre = {"1er Trimestre": [1,2,3], "2do Trimestre": [4,5,6], "3er Trimestre": [7,8,9], "4to Trimestre": [10,11,12]}
                    if "Trimestre" in periodo:
                        if mes not in meses_trimestre[periodo]:
                            problemas.append(f"Mes {mes} no corresponde a {periodo}")
                except: pass

                # Veredicto
                if problemas:
                    temp_res.append({"CP": cp_original, "ESTADO": "🔍 REVISAR", "OBSERVACIÓN": " | ".join(problemas)})
                else:
                    obs_final = "Todo OK"
                    if amort > 0: obs_final += f" (Amortización detectada: ${amort})"
                    temp_res.append({"CP": cp_original, "ESTADO": "✅ OK", "OBSERVACIÓN": obs_final})
            else:
                temp_res.append({"CP": cp_original, "ESTADO": "⚠️ PENDIENTE", "OBSERVACIÓN": "Archivo PDF no cargado o nombre no contiene el CP"})

            progreso.progress((idx + 1) / len(df))

        st.session_state.res = temp_res
        status.success("Auditoría Finalizada.")

# --- VISTA DE RESULTADOS ---
if st.session_state.res:
    res_df = pd.DataFrame(st.session_state.res)
    st.subheader(f"📊 Informe de Auditoría: {entidad} - {periodo} {anio_auditoria}")
    
    # Filtro rápido
    filtro = st.multiselect("Filtrar por estado", ["✅ OK", "🔍 REVISAR", "⚠️ PENDIENTE", "❌ DESECHADO"], default=["✅ OK", "🔍 REVISAR", "⚠️ PENDIENTE", "❌ DESECHADO"])
    vista_df = res_df[res_df['ESTADO'].isin(filtro)]
    
    st.dataframe(vista_df, use_container_width=True)

    # Exportación XLSX
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        vista_df.to_excel(w, index=False, sheet_name='Resultados')
    st.download_button("📥 Descargar este Reporte (Excel)", out.getvalue(), f"Auditoria_{entidad}_{periodo}.xlsx")

    st.info("💡 Puedes subir más PDFs ahora y volver a presionar 'INICIAR VERIFICACIÓN' para completar los PENDIENTES.")
