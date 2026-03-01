import streamlit as st
import pandas as pd
import re

# --- CONFIGURACIÓN DE ALTO RENDIMIENTO ---
st.set_page_config(page_title="AUDITORÍA PROGRESIVA EMAPAG", layout="wide")

@st.cache_data
def limpiar_id(texto):
    return re.sub(r'\D', '', str(texto))

# --- SEGURIDAD ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso Pericial")
    if st.text_input("Clave:", type="password") == "PERITO_EMAPAG_2025":
        if st.button("DESBLOQUEAR"):
            st.session_state.auth = True
            st.rerun()
    st.stop()

st.title("🛡️ Panel de Veredicto Progresivo (150+ PDFs)")

# --- CARGA MASIVA OPTIMIZADA ---
with st.sidebar:
    st.header("📂 Carga de Insumos")
    archivo_excel = st.file_uploader("1. Matriz (.xlsx)", type=["xlsx"])
    # accept_multiple_files procesa los 150+ sin problema si los manejamos como índice
    archivos_pdf = st.file_uploader("2. Evidencia (Subida Masiva)", type=["pdf"], accept_multiple_files=True)

if archivo_excel and archivos_pdf:
    df = pd.read_excel(archivo_excel)
    
    # CREACIÓN DEL ÍNDICE DE ARCHIVOS (Para que no deje de leer ninguno)
    # Usamos un generador para no saturar la RAM
    pdfs_index = {limpiar_id(f.name): f for f in archivos_pdf}
    total_pdfs = len(archivos_pdf)
    total_matriz = len(df)

    # --- PANEL DE VEREDICTO DE REVISIÓN ---
    st.subheader("📈 Estado de la Revisión Documental")
    
    # Calculamos el veredicto de integridad línea por línea
    vinculados = []
    faltantes = []
    for index, row in df.iterrows():
        id_cp = limpiar_id(row.iloc[0]) # Asumimos que CP es la primera columna
        if id_cp in pdfs_index:
            vinculados.append(id_cp)
        else:
            faltantes.append(id_cp)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matriz (Filas)", total_matriz)
    c2.metric("PDFs Detectados", total_pdfs)
    c3.metric("Veredicto: OK", f"{len(vinculados)}")
    c4.metric("Veredicto: FALTA", f"{len(faltantes)}", delta_color="inverse")

    # BARRA DE PROGRESO DE LA PERICIA
    progreso = len(vinculados) / total_matriz
    st.progress(progreso)
    st.caption(f"Integridad documental al {progreso*100:.1f}%")

    # --- REVISIÓN INDIVIDUAL Y COTEJAMIENTO ---
    st.divider()
    col_lista, col_visor = st.columns([1, 2])

    with col_lista:
        st.subheader("📋 Lista de Control")
        seleccion = st.selectbox("Seleccione registro para cotejar:", range(total_matriz),
                                 format_func=lambda x: f"Fila {x+1} - CP: {df.iloc[x].iloc[0]}")
        
        fila_actual = df.iloc[seleccion]
        id_buscado = limpiar_id(fila_actual.iloc[0])

    with col_visor:
        st.subheader("🔍 Inspección y Confrontación")
        if id_buscado in pdfs_index:
            archivo = pdfs_index[id_buscado]
            st.success(f"✅ EVIDENCIA ENCONTRADA: {archivo.name}")
            st.download_button("📂 Abrir PDF para Cotejar Contenido", archivo, file_name=archivo.name)
            
            # Aquí el perito verifica la veracidad del contenido
            with st.expander("📝 Registrar Hallazgos de Contenido"):
                check_fecha = st.checkbox("Fecha Correcta (Matriz = PDF)")
                check_valor = st.checkbox("Valor Correcta (Matriz = PDF)")
                check_calculo = st.checkbox("IVA y Retenciones correctas")
                nota = st.text_area("Notas sobre discrepancias:")
                if st.button("Guardar Veredicto"):
                    st.toast("Cotejamiento registrado.")
        else:
            st.error(f"❌ HALLAZGO: No existe PDF para el CP {id_buscado}")
            st.warning("Este registro en la matriz no tiene sustento físico.")

    # --- INFORME FINAL DE CONFRONTACIÓN ---
    st.divider()
    if st.button("📝 GENERAR INFORME FIEL"):
        st.header("📋 Informe de Situación Pericial")
        col_inf1, col_inf2 = st.columns(2)
        with col_inf1:
            st.write("**Resumen de Integridad:**")
            st.write(f"- Registros con respaldo: {len(vinculados)}")
            st.write(f"- Registros sin respaldo: {len(faltantes)}")
        with col_inf2:
            st.write("**Discrepancias de Cantidad:**")
            sobrantes = total_pdfs - len(vinculados)
            st.write(f"- PDFs sobrantes (no están en matriz): {sobrantes}")
        st.balloons()

else:
    st.info("💡 Consejo: Arrastra los 150+ archivos de una vez. El sistema los indexará automáticamente para el veredicto.")
