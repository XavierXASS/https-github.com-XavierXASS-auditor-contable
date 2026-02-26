import streamlit as st
import pandas as pd
import google.generativeai as genai
import re
import io
import time
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="Auditoría IA Profesional", layout="wide")

# --- VISIÓN HOLÍSTICA: CONFIGURACIÓN INTEGRAL ---
API_KEY = "AIzaSyCNYo_YWsGsArXjAzOk0_CY1ISiw83t1yI"
genai.configure(api_key=API_KEY)

# Inicialización del modelo con la ruta estable (v1)
model = genai.GenerativeModel("gemini-1.5-flash")

if 'maestro' not in st.session_state: st.session_state.maestro = None

def auditar_pericial(pdf_bytes, cp_ex, ruc_ex, total_ex, anio_ref):
    try:
        # Convertir PDF a imágenes (máximo detalle para auditoría)
        images = convert_from_bytes(pdf_bytes, dpi=120)
        payload = []
        # Enviamos las 6 páginas clave para cubrir todo el expediente
        for img in images[:6]:
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            payload.append(Image.open(buf))
        
        prompt = f"""
        Eres un Auditor Contable Experto. Analiza este expediente de pago para {anio_ref}.
        DATOS DE LA MATRIZ: CP: {cp_ex}, RUC: {ruc_ex}, TOTAL SPI ESPERADO: {total_ex}.

        TAREAS DE QA:
        1. Identificación: Localiza el 'Comprobante de Pago', 'Comprobante Contable', 'Factura', 'Retención' y 'SPI' (Sol Valdivia).
        2. Validación de Identidad: ¿El CP {cp_ex} y el RUC {ruc_ex} aparecen correctamente?
        3. Cuadre Matemático: Extrae el Valor de la Factura, resta las Retenciones (IVA/Renta) y Amortizaciones. ¿El resultado coincide con el valor del SPI?
        4. Alertas: Reporta si hay fechas de 2026 o documentos de 2024.

        RESPONDE EXACTAMENTE ASÍ:
        TIPO: [Tipo de pago: Proveedor, Nómina, IESS, etc.]
        ESTADO: [OK o REVISAR]
        INFORME: [Detalle del cuadre de valores y documentos hallados/faltantes]
        """
        
        response = model.generate_content([prompt] + payload)
        res = response.text.upper()
        
        # Procesamiento de la respuesta de la IA
        status = "✅ OK" if "ESTADO: OK" in res else "🔍 REVISAR"
        tipo = res.split("TIPO:")[1].split("\n")[0].strip() if "TIPO:" in res else "DESCONOCIDO"
        detalle = res.split("INFORME:")[1].strip() if "INFORME:" in res else res
        
        return tipo, status, detalle
    except Exception as e:
        return "ERROR", "❌ FALLO TÉCNICO", f"Error de conexión con Google: {str(e)}"

# --- INTERFAZ DE USUARIO ---
st.title("🛡️ Sistema de Auditoría Xavier - V20")

with st.sidebar:
    st.header("⚙️ Control")
    anio_rev = st.selectbox("Año de Revisión", [2025, 2026, 2024])
    if st.button("🚨 Limpiar Sistema"):
        st.session_state.maestro = None
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    ex_file = st.file_uploader("1. Cargar Matriz Maestro", type=["xlsx"])
    if ex_file and st.session_state.maestro is None:
        st.session_state.maestro = pd.read_excel(ex_file)
        # Aseguramos columnas de auditoría sobre el mismo archivo
        for c in ['ESTADO_IA', 'INFORME_DETALLADO', 'REVISADO']:
            if c not in st.session_state.maestro.columns:
                st.session_state.maestro[c] = "PENDIENTE"

with c2:
    pdfs = st.file_uploader("2. Cargar PDFs (Lote de 5-10)", type=["pdf"], accept_multiple_files=True)

if st.session_state.maestro is not None and pdfs:
    if st.button("🚀 INICIAR REVISIÓN PERICIAL"):
        df = st.session_state.maestro
        c_cp = next((c for c in df.columns if "PAGO" in str(c).upper() or "CP" in str(c).upper()), None)
        c_ruc = next((c for c in df.columns if "RUC" in str(c).upper()), None)
        c_total = next((c for c in df.columns if "TOTAL" in str(c).upper() or "SPI" in str(c).upper()), None)

        status_msg = st.empty()
        bar = st.progress(0)

        for i, pdf in enumerate(pdfs):
            # Buscar el CP en el nombre del archivo para vincular con la fila del Excel
            num_search = re.search(r'\d+', pdf.name)
            if num_search:
                cp_id = num_search.group()
                idx_list = df[df[c_cp].astype(str).str.contains(cp_id)].index
                
                if not idx_list.empty:
                    idx = idx_list[0]
                    status_msg.info(f"IA analizando visualmente CP {cp_id}...")
                    
                    # Llamada a la IA
                    t, s, d = auditar_pericial(pdf.read(), cp_id, df.at[idx, c_ruc], df.at[idx, c_total], anio_rev)
                    
                    df.at[idx, 'ESTADO_IA'] = s
                    df.at[idx, 'INFORME_DETALLADO'] = d
                    df.at[idx, 'REVISADO'] = "SÍ"
            
            bar.progress((i + 1) / len(pdfs))
        
        st.session_state.maestro = df
        status_msg.success("Auditoría terminada para este lote.")

    # Mostrar Matriz Actualizada
    st.dataframe(st.session_state.maestro, use_container_width=True)
    
    # Exportar el mismo archivo
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        st.session_state.maestro.to_excel(writer, index=False)
    st.download_button("📥 DESCARGAR MATRIZ AUDITADA", out.getvalue(), "Auditoria_Final_IA.xlsx")

else:
    st.info("Carga el Excel Maestro arriba para comenzar.")
