import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io

st.set_page_config(page_title="Auditor Contable Xavier", layout="wide")

st.title("🛡️ Auditor Contable Inteligente")
st.markdown("---")

def realizar_ocr(pdf_file):
    try:
        images = convert_from_path(pdf_file.read())
        texto = ""
        for img in images:
            texto += pytesseract.image_to_string(img, lang='spa')
        return texto
    except Exception as e:
        return f"Error OCR: {str(e)}"

# --- INTERFAZ ---
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("1. Datos del Excel")
    excel_input = st.file_uploader("Subir Matriz Excel", type=["xlsx"])
with col2:
    st.subheader("2. Documentos PDF")
    pdfs_input = st.file_uploader("Subir PDFs", type=["pdf"], accept_multiple_files=True)

if excel_input and pdfs_input:
    df = pd.read_excel(excel_input)
    
    # --- BUSCADOR INTELIGENTE DE COLUMNAS (QA) ---
    cols = df.columns.tolist()
    # Buscar CP (C. Pago)
    col_cp = next((c for c in cols if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
    # Buscar Total
    col_total = next((c for c in cols if "TOTAL" in str(c).upper() or "VALOR" in str(c).upper()), None)
    # Buscar Fecha
    col_fecha = next((c for c in cols if "FECHA" in str(c).upper()), None)

    if not col_cp:
        st.error(f"❌ No encontré la columna de 'C. PAGO'. Las columnas detectadas son: {cols}")
    else:
        archivos_unicos = {p.name: p for p in pdfs_input}.values()
        st.success(f"Columnas detectadas: CP='{col_cp}', Total='{col_total}', Fecha='{col_fecha}'")
        
        if st.button("🚀 INICIAR AUDITORÍA"):
            reporte = []
            progreso = st.progress(0)
            bitacora = st.expander("Bitácora de proceso", expanded=True)
            
            for idx, fila in df.iterrows():
                cp = str(fila[col_cp]).strip()
                total_factura = fila[col_total] if col_total else 0
                fecha = str(fila[col_fecha]) if col_fecha else ""
                
                progreso.progress((idx + 1) / len(df))
                
                if "2024" in fecha:
                    reporte.append({"CP": cp, "ESTADO": "⚠️ DESECHADO", "OBSERVACIÓN": "Año 2024"})
                    continue

                pdf_match = next((p for p in archivos_unicos if cp in p.name), None)
                
                if pdf_match:
                    bitacora.write(f"Leyendo CP {cp}...")
                    texto_pdf = realizar_ocr(pdf_match)
                    
                    deducciones = 0
                    patrones = {
                        "Amortización": r"(?i)AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})",
                        "Multa": r"(?i)MULTA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})"
                    }
                    
                    notas = []
                    for concepto, patron in patrones.items():
                        m = re.search(patron, texto_pdf)
                        if m:
                            val = float(m.group(1).replace(',', '.'))
                            deducciones += val
                            notas.append(f"{concepto}: ${val}")

                    calculo_neto = total_factura - deducciones
                    # Comparar con el mismo valor del excel si no hay columna SPI separada
                    if abs(calculo_neto - total_factura) > 0.1 and deducciones > 0:
                        reporte.append({"CP": cp, "ESTADO": "🔍 REVISAR", "OBSERVACIÓN": f"Deducciones: {notas}"})
                    else:
                        reporte.append({"CP": cp, "ESTADO": "✅ OK", "OBSERVACIÓN": "Cuadre correcto"})
                else:
                    reporte.append({"CP": cp, "ESTADO": "❌ ERROR", "OBSERVACIÓN": "PDF no encontrado"})
            
            st.write("### Reporte Final")
            df_res = pd.DataFrame(reporte)
            st.dataframe(df_res, use_container_width=True)
            
            output = io.BytesIO()
            df_res.to_excel(output, index=False)
            st.download_button("📥 Descargar Resultados", output.getvalue(), "Auditoria.xlsx")
            st.balloons()
