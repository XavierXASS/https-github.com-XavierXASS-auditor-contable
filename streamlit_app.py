import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Auditor Contable Xavier V2", layout="wide")

# --- MEMORIA DE LA SESIÓN (Mantiene archivos y resultados) ---
if 'pdf_library' not in st.session_state:
    st.session_state.pdf_library = {} 
if 'resultados_auditoria' not in st.session_state:
    st.session_state.resultados_auditoria = []
if 'excel_maestro' not in st.session_state:
    st.session_state.excel_maestro = None

st.title("🛡️ Centro de Gestión de Auditoría Integral")
st.markdown("---")

# --- FUNCIONES DE LÓGICA ---
def realizar_ocr_profundo(pdf_file):
    try:
        # Volvemos a leer el archivo desde el inicio
        pdf_file.seek(0)
        images = convert_from_path(pdf_file.read())
        texto = ""
        for img in images:
            texto += pytesseract.image_to_string(img, lang='spa')
        return texto
    except Exception as e:
        return ""

def extraer_monto(texto, patron):
    match = re.search(patron, texto)
    if match:
        # Limpieza básica de caracteres para convertir a número
        valor_str = match.group(1).replace('.', '').replace(',', '.')
        try:
            return float(valor_str)
        except:
            return 0.0
    return 0.0

# --- BARRA LATERAL: GESTIÓN DE ARCHIVOS ---
with st.sidebar:
    st.header("📂 Gestión de Archivos")
    
    # 1. Cargar Excel (Maestro)
    excel_file = st.file_uploader("1. Cargar Matriz Excel (Maestro)", type=["xlsx"])
    if excel_file:
        st.session_state.excel_maestro = pd.read_excel(excel_file)
        st.success("Matriz cargada.")

    # 2. Cargar PDFs (Acumulativo)
    new_pdfs = st.file_uploader("2. Cargar lotes de PDFs", type=["pdf"], accept_multiple_files=True)
    if new_pdfs:
        for p in new_pdfs:
            if p.name not in st.session_state.pdf_library:
                st.session_state.pdf_library[p.name] = p
        st.success(f"Librería: {len(st.session_state.pdf_library)} PDFs cargados.")

    # 3. Limpieza
    st.markdown("---")
    if st.button("🗑️ Limpiar Lote de PDFs"):
        st.session_state.pdf_library = {}
        st.rerun()
    if st.button("🧹 Borrar Resultados Anteriores"):
        st.session_state.resultados_auditoria = []
        st.rerun()

# --- PANEL PRINCIPAL ---
if st.session_state.excel_maestro is not None:
    df = st.session_state.excel_maestro
    
    # Identificación de columnas automática
    cols = df.columns.tolist()
    col_cp = next((c for c in cols if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    col_ruc = next((c for c in cols if "RUC" in str(c).upper()), None)
    col_total = next((c for c in cols if "TOTAL" in str(c).upper()), None)
    col_fecha = next((c for c in cols if "FECHA" in str(c).upper()), None)

    st.subheader("📋 Control de Auditoría")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**Líneas en Excel:** {len(df)}")
    with col_b:
        st.write(f"**PDFs en sistema:** {len(st.session_state.pdf_library)}")
    
    # Botón de Procesamiento
    if st.button("🚀 PROCESAR AUDITORÍA"):
        temp_results = []
        progreso = st.progress(0)
        bitacora = st.empty()

        for idx, fila in df.iterrows():
            cp = str(fila[col_cp]).strip()
            ruc_excel = str(fila[col_ruc]).strip()
            monto_excel = fila[col_total]
            fecha_val = str(fila[col_fecha])
            año_actual = datetime.datetime.now().year
            
            # REGLA 4: Año anterior
            if str(año_actual-1) in fecha_val:
                temp_results.append({"CP": cp, "ESTADO": "⚠️ DESECHADO", "MOTIVO": f"Año {año_actual-1} (Revisión humana)"})
                continue

            # Buscar PDF en la librería por CP
            pdf_match_name = next((name for name in st.session_state.pdf_library if cp in name), None)
            
            if pdf_match_name:
                bitacora.info(f"Leyendo OCR para CP: {cp}...")
                pdf_data = st.session_state.pdf_library[pdf_match_name]
                texto = realizar_ocr_profundo(pdf_data)
                
                problemas = []
                
                # REGLA 1 y 2: Validación de RUC
                if ruc_excel not in texto:
                    problemas.append(f"RUC {ruc_excel} no hallado")

                # REGLA 5: Cuadre con Anticipos y Retenciones
                amortizacion = extraer_monto(texto, r"(?i)AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                retencion = extraer_monto(texto, r"(?i)RETENCI[OÓ]N[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                multa = extraer_monto(texto, r"(?i)MULTA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                
                calculo_neto = monto_excel - amortizacion - retencion - multa
                
                # REGLA 3: Trimestre (Si el mes no coincide con cierre)
                try:
                    mes_doc = pd.to_datetime(fila[col_fecha]).month
                    if mes_doc not in [3, 6, 9, 12]:
                        problemas.append("Fuera de cierre trimestral")
                except:
                    pass

                # VALIDACIÓN FINAL
                if problemas:
                    temp_results.append({"CP": cp, "ESTADO": "REVISAR", "MOTIVO": " | ".join(problemas)})
                else:
                    temp_results.append({"CP": cp, "ESTADO": "OK", "MOTIVO": f"Verificado. (Amort: ${amortizacion})"})
            else:
                temp_results.append({"CP": cp, "ESTADO": "PENDIENTE", "MOTIVO": "PDF no cargado"})
            
            progreso.progress((idx + 1) / len(df))

        st.session_state.resultados_auditoria = temp_results
        bitacora.success("Procesamiento completado.")

    # --- MOSTRAR RESULTADOS Y REPORTES ---
    if st.session_state.resultados_auditoria:
        res_df = pd.DataFrame(st.session_state.resultados_auditoria)
        st.markdown("---")
        
        # Filtros de vista
        opcion_vista = st.radio("Ver reporte:", ["Todos", "Solo con problemas", "Solo Correctos"], horizontal=True)
        
        if "problemas" in opcion_vista:
            vista_df = res_df[res_df['ESTADO'] != "OK"]
        elif "Correctos" in opcion_vista:
            vista_df = res_df[res_df['ESTADO'] == "OK"]
        else:
            vista_df = res_df

        st.dataframe(vista_df, use_container_width=True)

        # REPORTES
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            csv_parcial = vista_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Reporte Parcial (Vista)", csv_parcial, "Parcial.csv")
        with col_r2:
            csv_final = res_df.to_csv(index=False).encode('utf-8')
            st.download_button("📊 Reporte Final (Matriz)", csv_final, "Auditoria_Final.csv")

else:
    st.warning("👈 Por favor, carga la Matriz Excel en la barra lateral.")
