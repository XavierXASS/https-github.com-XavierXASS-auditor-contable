import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io

st.set_page_config(page_title="Auditoría Contable Xavier", layout="wide")

st.title("🛡️ Auditor Contable Inteligente")
st.markdown("---")

def analizar_documento(pdf_file, cp_buscado):
    try:
        images = convert_from_path(pdf_file.read())
        texto = ""
        for img in images:
            texto += pytesseract.image_to_string(img, lang='spa')
        deducciones = 0
        hallazgos = []
        patrones = {
            "Amortización": r"(?i)AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})",
            "Multa": r"(?i)MULTA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})",
            "Retención": r"(?i)RETENCI[OÓ]N[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})"
        }
        for concepto, patron in patrones.items():
            matches = re.findall(patron, texto)
            for m in matches:
                valor = float(m.replace(',', '.'))
                deducciones += valor
                hallazgos.append(f"{concepto}: ${valor:.2f}")
        return True, deducciones, hallazgos, texto
    except Exception as e:
        return False, 0, [f"Error OCR: {str(e)}"], ""

with st.sidebar:
    st.header("Carga de Datos")
    excel_input = st.file_uploader("Subir Matriz Excel", type=["xlsx"])
    pdfs_input = st.file_uploader("Subir PDFs (Muestra)", type=["pdf"], accept_multiple_files=True)

if excel_input and pdfs_input:
    df = pd.read_excel(excel_input)
    if st.button("🚀 INICIAR AUDITORÍA"):
        reporte = []
        for idx, fila in df.iterrows():
            cp = str(fila['C. PAGO']).strip()
            total_factura = fila['TOTAL']
            fecha = str(fila['FECHA'])
            obs_qa = []
            status = "✅ OK"
            if "2024" in fecha:
                reporte.append({"CP": cp, "ESTADO": "⚠️ DESECHADO", "OBSERVACIÓN": "Año 2024"})
                continue
            pdf_match = next((p for p in pdfs_input if cp in p.name), None)
            if pdf_match:
                exito, deduc, notas, txt = analizar_documento(pdf_match, cp)
                calculo_neto = total_factura - deduc
                if abs(calculo_neto - fila['TOTAL']) > 0.1:
                     status = "🔍 REVISAR"
                     obs_qa.append(f"Diferencia en cuadre")
                obs_qa.extend(notas)
                reporte.append({"CP": cp, "ESTADO": status, "OBSERVACIÓN": " | ".join(obs_qa)})
            else:
                reporte.append({"CP": cp, "ESTADO": "❌ ERROR", "OBSERVACIÓN": "PDF no encontrado"})
        st.write("### Informe de Verificación")
        df_final = pd.DataFrame(reporte)
        st.dataframe(df_final, use_container_width=True)
        output = io.BytesIO()
        df_final.to_excel(output, index=False)
        st.download_button("📥 Descargar Reporte", output.getvalue(), "Auditoria.xlsx")
