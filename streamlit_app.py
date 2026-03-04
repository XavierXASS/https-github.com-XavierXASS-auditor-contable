# ==== IMPORTS (nivel superior, sin sangría) ====
import streamlit as st
import pandas as pd
import numpy as np
import io, re, unicodedata
import pdfplumber
from datetime import datetime
# ==============================================


# =========================
# Configuración de página
# =========================
st.set_page_config(
    page_title="Terminal de Emergencia - Pericia",
    layout="wide",
)


# =========================
# Estado por defecto (evita NameError)
# =========================
if "uploaded_pdfs" not in st.session_state:
    st.session_state["uploaded_pdfs"] = []


# =========================
# Encabezado
# =========================
st.title("Terminal de Emergencia - Pericia Xavier")
st.markdown(
    "Cargue su matriz en **Excel (.xlsx)**. "
    "La app detectará automáticamente la fila del encabezado, limpiará columnas *Unnamed*, "
    "normalizará fechas y mostrará una vista previa. Luego puede **cargar PDFs** y **cotejarlos** con cada fila."
)


# =========================
# Utilidades Excel
# =========================
def detectar_fila_encabezado(df_sin_header: pd.DataFrame, max_busqueda: int = 15) -> int:
    """
    Detecta la fila más probable para ser el encabezado.
    Estrategia: dentro de las primeras `max_busqueda` filas, elegir
    la que tenga más celdas no vacías. Retorna índice 0-based.
    """
    limite = min(max_busqueda, len(df_sin_header))
    scores = df_sin_header.iloc[:limite].apply(lambda r: r.notna().sum(), axis=1)
    header_guess = int(scores.idxmax())
    return header_guess


def leer_y_normalizar_excel(archivo) -> pd.DataFrame:
    """
    Lee el Excel subido, detecta encabezado, elimina columnas 'Unnamed',
    quita filas vacías, recorta espacios en nombres de columnas y convierte
    columnas con 'fecha' en datetime cuando sea posible.
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
    Resumen de columnas:
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
# Utilidades de PDFs
# =========================
def _norm_txt(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _clean_benef(s: str) -> str:
    s = _norm_txt(s).upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s[:200]

def _parse_money(s: str):
    if s is None:
        return np.nan
    s = str(s)
    # Mantener dígitos, coma, punto y signo
    s = re.sub(r"[^\d,\.\-]", "", s)
    # Si hay coma y no hay punto, tratar coma como decimal
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    # Eliminar separadores de miles ambiguos (puntos entre miles)
    s = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", s)
    try:
        return float(s)
    except Exception:
        return np.nan

def _find_first(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(0) if m else None

def _find_near_amount(keys, text):
    """
    Busca cantidades cercanas a palabras clave (línea +/- 1).
    Devuelve la primera que parezca válida.
    """
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        for k in keys:
            if re.search(k, ln, flags=re.IGNORECASE):
                cand = " ".join(lines[max(0, i-1):min(len(lines), i+2)])
                m = re.search(r"[-+]?\d[\d\.\,]*\d", cand)
                if m:
                    val = _parse_money(m.group(0))
                    if not np.isnan(val):
                        return val
    return np.nan

def classify_document(text_norm: str) -> str:
    t = text_norm
    if re.search(r"\bSPI\b|SISTEMA DE PAGOS INTERBANCARIOS|BANCO CENTRAL|BCE", t):
        return "SPI"
    if re.search(r"COMPROBANTE\s+DE\s+PAGO|ORDEN\s+DE\s+PAGO|PAGO\s+N[ou]", t):
        return "PAGO"
    if re.search(r"COMPROBANTE\s+DE\s+RETENCION|RETENCION|RETENCI[ÓO]N", t):
        return "RETENCION"
    if re.search(r"COMPROBANTE\s+CONTABLE|ASIENTO\s+CONTABLE|DIARIO\s+GENERAL", t):
        return "CONTABLE"
    if re.search(r"FACTURA|FACT\.|NOTA\s+DE\s+VENTA|COMPROBANTE\s+DE\s+VENTA", t):
        return "FACTURA"
    return "OTRO"

def extract_pdf_fields(file) -> dict:
    # Extraer texto de todas las páginas (sin OCR)
    try:
        with pdfplumber.open(file) as pdf:
            pages_text = []
            for pg in pdf.pages:
                t = pg.extract_text() or ""
                pages_text.append(t)
        full_text = "\n".join(pages_text)
    except Exception as e:
        return {"file": file.name, "ok": False, "error": f"Lectura PDF falló: {e}"}

    text_norm = _norm_txt(full_text)
    if not text_norm or len(text_norm.strip()) < 40:
        # Muy poco texto -> probablemente escaneado
        return {"file": file.name, "ok": False, "error": "PDF sin texto (probable escaneo). Requiere OCR."}

    tipo = classify_document(text_norm)

    # Campos comunes
    ruc = _find_first(r"\b\d{13}\b", text_norm)  # RUC de 13 dígitos (EC)
    # Factura típica: 001-002-000123456
    factura = _find_first(r"\b\d{3}[- ]\d{3}[- ]\d{6,9}\b", text_norm)
    # Fecha dd/mm/yyyy o yyyy-mm-dd
    fecha = _find_first(r"\b(?:\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})\b", text_norm)

    benef = None
    for k in [r"RAZ[OÓ]N\s+SOCIAL[: ]", r"BENEFICIARIO[: ]", r"PROVEEDOR[: ]", r"NOMBRE[: ]"]:
        m = re.search(k + r"(.{3,80})", text_norm, flags=re.IGNORECASE)
        if m:
            benef = _clean_benef(m.group(1))
            break

    # Montos por tipo de documento
    subtotal = iva = total = np.nan
    ret_iva = ret_renta = ret_total = np.nan
    valor_pago = valor_spi = valor_contable = np.nan

    if tipo == "FACTURA":
        subtotal = _find_near_amount([r"\bSUBTOTAL\b"], text_norm)
        iva = _find_near_amount([r"\bIVA\b"], text_norm)
        total = _find_near_amount([r"\bTOTAL\b", r"\bVALOR\s*A\s*PAGAR\b"], text_norm)
    elif tipo == "RETENCION":
        ret_iva = _find_near_amount([r"RETENCION\s+IVA", r"\bIVA\s+\d+%"], text_norm)
        ret_renta = _find_near_amount([r"RETENCION\s+RENTA", r"\bRENTA\s+\d+%"], text_norm)
        rt = _find_near_amount([r"TOTAL\s+RETENCI[OÓ]N", r"TOTAL\s+RETENCIONES"], text_norm)
        ret_total = rt if not np.isnan(rt) else (0 if (np.isnan(ret_iva) and np.isnan(ret_renta)) else np.nansum([ret_iva, ret_renta]))
    elif tipo == "PAGO":
        valor_pago = _find_near_amount([r"\bVALOR\b", r"\bMONTO\b", r"\bTOTAL\b"], text_norm)
    elif tipo == "SPI":
        valor_spi = _find_near_amount([r"\bVALOR\b", r"\bMONTO\b", r"\bTOTAL\b"], text_norm)
    elif tipo == "CONTABLE":
        valor_contable = _find_near_amount([r"\bHABER\b", r"\bTOTAL\b"], text_norm)

    return {
        "file": file.name, "ok": True, "error": None,
        "tipo": tipo, "ruc": ruc, "factura": factura, "fecha_doc": fecha,
        "beneficiario": benef,
        "subtotal": subtotal, "iva": iva, "total": total,
        "ret_iva": ret_iva, "ret_renta": ret_renta, "ret_total": ret_total,
        "valor_pago": valor_pago, "valor_spi": valor_spi, "valor_contable": valor_contable,
        "texto_len": len(text_norm)
    }


# =========================
# UI: Carga en barra lateral
# =========================
with st.sidebar:
    st.header("1. Excel")
    uploaded_xlsx = st.file_uploader(
        "Drag and drop file here",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Límite recomendado 200MB por archivo - .XLSX",
        key="xlsx_uploader"
    )

    st.header("2. PDFs")
    side_uploaded_pdfs = st.file_uploader(
        "Drag and drop files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Límite recomendado 200MB por archivo - PDF",
        key="pdfs_uploader"
    )

# Sincronizar PDFs a session_state (fuente única de verdad)
st.session_state["uploaded_pdfs"] = side_uploaded_pdfs or []


# =========================
# Lógica principal: Excel
# =========================
if uploaded_xlsx is None:
    st.info("Cargue su matriz en la barra lateral para iniciar la vista previa.")
    df = None
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

            with st.expander("Siguientes pasos sugeridos", expanded=False):
                st.markdown(
                    "- Definir columnas obligatorias del caso (Fecha, Serie, Número, RUC, Beneficiario, Total).\n"
                    "- Cargar PDFs para enlazar (Factura, Retención, Comprobante de Pago, SPI, Contable).\n"
                    "- Ejecutar cotejo y exportar hallazgos."
                )

        except Exception as e:
            st.error(f"Ocurrió un error leyendo/normalizando el Excel: {e}")
            df = None


# =========================
# Procesamiento de PDFs y cotejo con la matriz
# =========================
st.markdown("---")
st.subheader("Procesamiento de PDFs y cotejo con la matriz")

pdf_files = st.session_state.get("uploaded_pdfs", [])

if not pdf_files:
    st.info("Sube los PDFs (Factura, Retención, Comprobante de Pago, SPI, Contable) en la barra lateral para habilitar el cotejo.")
elif df is None:
    st.info("Primero carga y visualiza la matriz en Excel para poder enlazar PDFs.")
else:
    st.caption(f"Se recibieron {len(pdf_files)} PDF(s).")

    # Procesar todos los PDFs cargados
    pdf_rows = [extract_pdf_fields(pf) for pf in pdf_files]
    pdf_df = pd.DataFrame(pdf_rows)

    st.markdown("**Resumen de PDFs**")
    st.dataframe(pdf_df.fillna(""), use_container_width=True)

    if (pdf_df["ok"] == False).any():
        st.warning("Algunos PDFs no se pudieron leer o no contienen texto. Revisa la columna 'error'. (Para escaneados, se requiere OCR).")

    # -------- Mapeo con la matriz para enlazar fila ↔ documentos --------
    st.markdown("---")
    st.subheader("Enlace de PDFs con filas de la matriz")

    # Sugerencias según nombres de columnas comunes
    sug_serie = next((c for c in df.columns if re.search(r"\bSERIE\b", str(c), flags=re.IGNORECASE)), None)
    sug_num   = next((c for c in df.columns if re.search(r"\bN.?[UÚ]M", str(c), flags=re.IGNORECASE)), None)
    sug_ruc   = next((c for c in df.columns if re.search(r"\bRUC\b", str(c), flags=re.IGNORECASE)), None)
    sug_benef = next((c for c in df.columns if re.search(r"NOMBRE|BENEFICIARIO|PROVEEDOR", str(c), flags=re.IGNORECASE)), None)
    sug_fecha = next((c for c in df.columns if re.search(r"FECHA", str(c), flags=re.IGNORECASE)), None)
