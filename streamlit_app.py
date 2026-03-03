import streamlit as st
import pandas as pd


# =========================
# Configuración de página
# =========================
st.set_page_config(
    page_title="Terminal de Emergencia - Pericia",
    layout="wide",
)

st.title("Terminal de Emergencia - Pericia Xavier")
st.markdown(
    "Cargue su matriz en **Excel (.xlsx)**. "
    "La app detectará automáticamente la fila del encabezado, "
    "limpiará columnas *Unnamed*, normalizará fechas y mostrará una vista previa."
)

# =========================
# Utilidades
# =========================
def detectar_fila_encabezado(df_sin_header: pd.DataFrame, max_busqueda: int = 15) -> int:
    """
    Detecta la fila más probable para ser el encabezado.
    Estrategia: dentro de las primeras `max_busqueda` filas, elegir
    la que tenga más celdas no vacías.
    Retorna índice 0-based.
    """
    limite = min(max_busqueda, len(df_sin_header))
    # puntuación: cantidad de valores no nulos por fila
    scores = df_sin_header.iloc[:limite].apply(lambda r: r.notna().sum(), axis=1)
    # idxmax devuelve el índice (0-based) de la fila con mayor puntuación
    header_guess = int(scores.idxmax())
    return header_guess


def leer_y_normalizar_excel(archivo) -> pd.DataFrame:
    """
    Lee el Excel subido, detecta encabezado, elimina columnas 'Unnamed',
    quita filas completamente vacías, recorta espacios en nombres de columnas
    y convierte columnas con 'fecha' en datetime cuando sea posible.
    """
    # 1) Leer sin encabezado para detectar fila de header
    df_raw = pd.read_excel(archivo, engine="openpyxl", header=None)

    # 2) Detectar encabezado
    header_row = detectar_fila_encabezado(df_raw, max_busqueda=15)

    # 3) Releer usando esa fila como encabezado real
    df = pd.read_excel(archivo, engine="openpyxl", header=header_row)

    # 4) Limpieza básica
    # 4.1 Eliminar columnas 'Unnamed'
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]

    # 4.2 Eliminar filas completamente vacías
    df = df.dropna(how="all").reset_index(drop=True)

    # 4.3 Normalizar nombres de columnas (quitar espacios al inicio/fin)
    df.columns = [str(c).strip() for c in df.columns]

    # 4.4 Convertir a datetime las columnas que parecen fechas (por nombre)
    for c in df.columns:
        if "fecha" in str(c).lower():
            df[c] = pd.to_datetime(df[c], errors="coerce")

    return df


def info_rapida_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve un pequeño resumen de columnas:
    - nombre
    - tipo pandas
    - # nulos
    - % nulos
    - ejemplo de valores
    """
    resumen = []
    n = len(df)
    for col in df.columns:
        n_null = int(df[col].isna().sum())
        ejemplo = None
        # busca primer valor no nulo como ejemplo
        non_null = df[col].dropna()
        if not non_null.empty:
            ejemplo = str(non_null.iloc[0])[:120]
        resumen.append({
            "columna": col,
            "tipo": str(df[col].dtype),
            "n_nulos": n_null,
            "%_nulos": round(100.0 * n_null / max(n, 1), 2),
            "ejemplo": ejemplo
        })
    return pd.DataFrame(resumen)


# =========================
# UI: Carga de archivos
# =========================
with st.sidebar:
    st.header("1. Excel")
    uploaded_xlsx = st.file_uploader(
        "Drag and drop file here",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Límite recomendado 200MB por archivo - .XLSX",
    )

    st.header("2. PDFs")
    uploaded_pdfs = st.file_uploader(
        "Drag and drop files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Límite recomendado 200MB por archivo - PDF",
    )

# =========================
# Lógica principal
# =========================
if uploaded_xlsx is None:
    st.info("Cargue su matriz en la barra lateral para iniciar la vista previa.")
else:
    with st.spinner("Leyendo y normalizando el Excel…"):
        try:
            df = leer_y_normalizar_excel(uploaded_xlsx)
            st.success(
                f"Archivo recibido: {uploaded_xlsx.name} | "
                f"Filas: {len(df):,} | Columnas: {len(df.columns)}"
            )

            st.subheader("Vista previa (primeras 20 filas)")
            st.dataframe(df.head(20), use_container_width=True)

            st.subheader("Columnas detectadas (ya limpias)")
            st.write(list(df.columns))

            st.subheader("Perfil rápido de columnas")
            st.dataframe(
                info_rapida_dataframe(df),
                use_container_width=True,
                hide_index=True
            )

            # Hint para siguientes pasos (validaciones específicas)
            with st.expander("Siguientes pasos sugeridos", expanded=False):
                st.markdown(
                    "- Definir columnas obligatorias del caso (IdCaso, Fecha, Monto, Estado, Perito, Observaciones).\n"
                    "- Validar tipos y reglas (fechas válidas, montos >= 0, estados permitidos, unicidad por IdCaso, etc.).\n"
                    "- Exportar hallazgos como CSV/Excel."
                )

        except Exception as e:
            st.error(f"Ocurrió un error leyendo/normalizando el Excel: {e}")
            st.stop()

# Nota: El bloque de PDFs está reservado para futuras funciones (p. ej., lectura o adjuntos).
