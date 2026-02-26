import streamlit as st
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
import re
import io

# Configuración profesional de la página
st.set_page_config(page_title="Auditor Contable Xavier", layout="wide")

st.title("🛡️ Auditor Contable Inteligente")
st.markdown("---")

# Función de OCR con manejo de errores para evitar bloqueos
def realizar_ocr(pdf_file):
    try:
        images = convert_from_path(pdf_file.read())
        texto = ""
        for img in images:
            texto += pytesseract.image_to_string(img, lang='spa')
        return texto
    except Exception as e:
        return f"Error al leer PDF: {str(e)}"

# --- PANEL CENTRAL DE CARGA ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Datos del Excel")
    excel_input = st.file_uploader("Subir Matriz Excel", type=["xlsx"])

with col2:
    st.subheader("2. Documentos PDF")
    pdfs_input = st.file_uploader("Subir todos los PDFs (Muestra o Lote completo)", type=["pdf"], accept_multiple_files=True)

if excel_input and pdfs_input:
    # Cargar Excel
    df = pd.read_excel(excel_input)
    
    # QA: Eliminar duplicados de los PDFs subidos por nombre
    archivos_unicos = {p.name: p for p in pdfs_input}.values()
    total_archivos = len(archivos_unicos)
    
    st.success(f"Configuración lista: {len(df)} líneas en Excel y {total_archivos} PDFs únicos detectados.")
    
    if st.button("🚀 INICIAR AUDITORÍA AHORA"):
        reporte = []
        
        # Elementos de retroalimentación visual
        progreso_texto = st.empty()
        barra_progreso = st.progress(0)
        bitacora = st.expander("Ver bitácora de procesamiento en tiempo real", expanded=True)
        
        for idx, fila in df.iterrows():
            cp = str(fila['C. PAGO']).strip()
            total_factura = fila.get('TOTAL', 0)
            fecha = str(fila.get('FECHA', ""))
            
            # Actualizar progreso
            progreso_texto.markdown(f"**Analizando CP {cp}** ({idx+1} de {len(df)})")
            barra_progreso.progress((idx + 1) / len(df))
            
            # QA Regla Año Anterior
            if "2024" in fecha:
                reporte.append({"CP": cp, "ESTADO": "⚠️ DESECHADO", "OBSERVACIÓN": "Año 2024 - Revisión manual"})
                bitacora.write(f"🔸 CP {cp}: Omitido por año anterior.")
                continue

            # Buscar el PDF correspondiente
            pdf_match = next((p for p in archivos_unicos if cp in p.name), None)
            
            if pdf_match:
                bitacora.write(f"🌀 CP {cp}: Leyendo PDF escaneado...")
                texto_pdf = realizar_ocr(pdf_match)
                
                # Lógica de búsqueda de deducciones (Multas/Amortizaciones)
                deducciones = 0
                notas = []
                patrones = {
                    "Amortización": r"(?i)AMORTIZA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})",
                    "Multa": r"(?i)MULTA[A-Z\s]*[\-\s]*(\d+[\.,]\d{2})"
                }
                
                for concepto, patron in patrones.items():
                    m = re.search(patron, texto_pdf)
                    if m:
                        val = float(m.group(1).replace(',', '.'))
                        deducciones += val
                        notas.append(f"{concepto}: ${val}")

                # Conciliación
                calculo_neto = total_factura - deducciones
                if abs(calculo_neto - fila.get('TOTAL', 0)) > 0.1:
                    reporte.append({"CP": cp, "ESTADO": "🔍 REVISAR", "OBSERVACIÓN": f"Diferencia detectada. Deducciones: {notas}"})
                else:
                    reporte.append({"CP": cp, "ESTADO": "✅ OK", "OBSERVACIÓN": "Conciliado con éxito"})
            else:
                reporte.append({"CP": cp, "ESTADO": "❌ ERROR", "OBSERVACIÓN": "PDF no encontrado"})
        
        # --- RESULTADOS FINALES ---
        st.markdown("---")
        st.subheader("📝 Reporte de Auditoría Finalizada")
        df_res = pd.DataFrame(reporte)
        st.dataframe(df_res, use_container_width=True)
        
        # Botón de descarga
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_res.to_excel(writer, index=False)
        st.download_button("📥 DESCARGAR EXCEL DE RESULTADOS", output.getvalue(), "Auditoria_Final.xlsx")
        st.balloons()

else:
    st.info("Esperando archivos... Sube tu Excel y tus PDFs para habilitar el botón de inicio.")
