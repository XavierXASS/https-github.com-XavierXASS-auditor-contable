import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io
import datetime
from PIL import Image, ImageOps

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Auditor Contable Xavier V5", layout="wide")

if 'pdf_library' not in st.session_state:
    st.session_state.pdf_library = {} 
if 'resultados_auditoria' not in st.session_state:
    st.session_state.resultados_auditoria = []

st.title("🛡️ Sistema de Auditoría Integral Xavier")
st.markdown("---")

def realizar_ocr_profundo(pdf_file):
    try:
        pdf_file.seek(0)
        # Aumentamos la resolución a 300 DPI para ver mejor los números pequeños
        images = convert_from_path(pdf_file.read(), dpi=300)
        texto_acumulado = ""
        for img in images:
            # Convertimos a escala de grises y aumentamos contraste para el OCR
            img = ImageOps.grayscale(img)
            texto_acumulado += pytesseract.image_to_string(img, lang='spa')
        return texto_acumulado
    except:
        return ""

def limpiar_numeros(texto):
    """Extrae solo los dígitos de una cadena de texto"""
    return re.sub(r'\D', '', str(texto))

def extraer_monto(texto, patron):
    match = re.search(patron, texto)
    if match:
        valor_str = match.group(1).replace('.', '').replace(',', '.')
        try: return float(valor_str)
        except: return 0.0
    return 0.0

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📂 Carga de Archivos")
    excel_file = st.file_uploader("1. Matriz Maestro (Excel)", type=["xlsx"])
    new_pdfs = st.file_uploader("2. Lotes de PDFs", type=["pdf"], accept_multiple_files=True)
    
    if new_pdfs:
        for p in new_pdfs:
            st.session_state.pdf_library[p.name] = p
        st.success(f"Librería: {len(st.session_state.pdf_library)} PDFs")

    if st.button("🗑️ Limpiar todo"):
        st.session_state.pdf_library = {}
        st.session_state.resultados_auditoria = []
        st.rerun()

# --- PROCESO ---
if excel_file is not None:
    df_maestro = pd.read_excel(excel_file)
    cols = df_maestro.columns.tolist()
    
    c_cp = next((c for c in cols if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    c_ruc = next((c for c in cols if "RUC" in str(c).upper()), None)
    c_total = next((c for c in cols if "TOTAL" in str(c).upper()), None)
    c_fecha = next((c for c in cols if "FECHA" in str(c).upper()), None)

    if st.button("🚀 EJECUTAR AUDITORÍA COMPLETA"):
        temp_results = []
        bar = st.progress(0)
        status_text = st.empty()

        for idx, fila in df_maestro.iterrows():
            # Identificadores limpios
            cp = limpiar_numeros(fila[c_cp])
            ruc_objetivo = limpiar_numeros(fila[c_ruc])
            
            monto_ex = fila[c_total]
            fecha_ex = str(fila[c_fecha])
            
            status_text.info(f"Analizando CP {cp}...")
            
            if "2024" in fecha_ex:
                temp_results.append({"CP": cp, "ESTADO": "⚠️ DESECHADO", "MOTIVO": "Año anterior (2024)"})
                continue

            # Buscar PDF
            pdf_name = next((n for n in st.session_state.pdf_library if cp in n), None)
            
            if pdf_name:
                texto_pdf = realizar_ocr_profundo(st.session_state.pdf_library[pdf_name])
                texto_solo_numeros = limpiar_numeros(texto_pdf)
                
                fallos = []
                
                # VALIDACIÓN DE RUC (Buscamos la secuencia de números sin importar el formato)
                if ruc_objetivo not in texto_solo_numeros:
                    fallos.append(f"RUC {ruc_objetivo} no detectado")

                # REGLA 5: Deducciones
                amort = extraer_monto(texto_pdf, r"(?i)AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                ret = extraer_monto(texto_pdf, r"(?i)RETENCI[OÓ]N[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                multa = extraer_monto(texto_pdf, r"(?i)MULTA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})")
                
                # REGLA 3: Trimestre
                try:
                    mes = pd.to_datetime(fila[c_fecha]).month
                    if mes not in [3, 6, 9, 12]:
                        fallos.append("Mes fuera de cierre trimestral")
                except: pass

                if fallos:
                    temp_results.append({"CP": cp, "ESTADO": "🔍 REVISAR", "MOTIVO": " | ".join(fallos)})
                else:
                    temp_results.append({"CP": cp, "ESTADO": "✅ OK", "MOTIVO": f"RUC validado. Amort: ${amort}"})
            else:
                temp_results.append({"CP": cp, "ESTADO": "❌ PENDIENTE", "MOTIVO": "Falta archivo PDF"})
            
            bar.progress((idx + 1) / len(df_maestro))

        st.session_state.resultados_auditoria = temp_results
        status_text.success("Auditoría finalizada.")

    if st.session_state.resultados_auditoria:
        res_df = pd.DataFrame(st.session_state.resultados_auditoria)
        st.subheader("📊 Resultados de la Auditoría")
        st.dataframe(res_df, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            res_df.to_excel(writer, index=False, sheet_name='Reporte')
        st.download_button(label="📥 DESCARGAR REPORTE EXCEL", data=output.getvalue(), file_name=f"Auditoria_{datetime.date.today()}.xlsx")
else:
    st.info("👈 Por favor, carga la Matriz Maestro para comenzar.")
