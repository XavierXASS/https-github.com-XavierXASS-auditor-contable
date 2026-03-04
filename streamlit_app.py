# ==== IMPORTS (nivel superior, sin sangría) ====
import streamlit as st
import pandas as pd
import numpy as np
import io, re, unicodedata, hashlib
import pdfplumber
from datetime import datetime
from difflib import SequenceMatcher
# ==============================================

# =========================
# Configuración de página
# =========================
st.set_page_config(page_title="Terminal de Emergencia - Pericia", layout="wide")
st.write("")  # estabiliza primer render

# =========================
# Estado por defecto (evita NameError)
# =========================
if "uploaded_pdfs" not in st.session_state:
    st.session_state["uploaded_pdfs"] = []
if "last_excel_name" not in st.session_state:
    st.session_state["last_excel_name"] = None

# =========================
# Encabezado
# =========================
st.title("Terminal de Emergencia - Pericia Xavier")
st.markdown(
    "Cargue su matriz en **Excel (.xlsx)**. La app detectará automáticamente la fila del encabezado, "
    "limpiará columnas *Unnamed*, normalizará fechas y mostrará una vista previa. "
    "Luego cargue **PDFs** y ejecute el **cotejo completo** (incluye SERIE+N° y CONCEPTO)."
)

# =========================
# Utilidades generales
# =========================
def _norm_txt(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _clean_upper(s: str) -> str:
    s = _norm_txt(s).upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _parse_money(s: str):
    if s is None:
        return np.nan
    s = str(s)
    s = re.sub(r"[^\d,\.\-]", "", s)
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    s = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", s)
    try:
        return float(s)
    except Exception:
        return np.nan

def _sim_ratio(a: str, b: str) -> float:
    a = _clean_upper(a)
    b = _clean_upper(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def quarter_from_date(dt: pd.Timestamp) -> int | None:
    if pd.isna(dt):
        return None
    return int((int(dt.month) - 1) // 3 + 1)

# =========================
# Utilidades Excel
# =========================
def detectar_fila_encabezado(df_sin_header: pd.DataFrame, max_busqueda: int = 15) -> int:
    limite = min(max_busqueda, len(df_sin_header))
    scores = df_sin_header.iloc[:limite].apply(lambda r: r.notna().sum(), axis=1)
    return int(scores.idxmax())

def leer_y_normalizar_excel(archivo) -> pd.DataFrame:
    df_raw = pd.read_excel(archivo, engine="openpyxl", header=None)
    header_row = detectar_fila_encabezado(df_raw, max_busqueda=15)
    df = pd.read_excel(archivo, engine="openpyxl", header=header_row)
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if "fecha" in str(c).lower():
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def info_rapida_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    resumen = []
    n = len(df)
    for col in df.columns:
        n_null = int(df[col].isna().sum())
        ejemplo = None
        non_null = df[col].dropna()
        if not non_null.empty:
            ejemplo = str(non_null.iloc[0])[:120]
        resumen.append({
            "columna": col, "tipo": str(df[col].dtype),
            "n_nulos": n_null, "%_nulos": round(100.0 * n_null / max(n, 1), 2),
            "ejemplo": ejemplo
        })
    return pd.DataFrame(resumen)

# --- Normalización SERIE+N° ---
def _digits(s) -> str:
    return re.sub(r"\D", "", "" if s is None else str(s))

def norm_serie_num_series(serie_col: pd.Series | None, num_col: pd.Series | None) -> pd.DataFrame:
    """
    Devuelve DataFrame con:
    - SERIE_FMT: 001-002
    - NUM_PAD:   9 dígitos (000123456)
    - FACT_KEY:  SERIE_FMT-NUM_PAD (sin doble guión)
    """
    idx = serie_col.index if serie_col is not None else num_col.index
    serie_digits = pd.Series("", index=idx) if serie_col is None else serie_col.astype(str).apply(_digits)
    num_digits   = pd.Series("", index=idx) if num_col   is None else num_col.astype(str).apply(_digits)

    serie_digits = serie_digits.str[:6].str.zfill(6)
    serie_fmt = serie_digits.str.replace(r"(\d{3})(\d{3})", r"\1-\2", regex=True)

    num_pad = num_digits.str[-9:].str.zfill(9)
    fact_key = (serie_fmt + "-" + num_pad).str.replace(r"-+$", "", regex=True).str.strip("-")

    return pd.DataFrame({"SERIE_FMT": serie_fmt, "NUM_PAD": num_pad, "FACT_KEY": fact_key})

# =========================
# Utilidades PDF (clasificación, extracción y apoyo a serie/número/concepto)
# =========================
def classify_document(text_norm: str) -> str:
    t = text_norm
    if re.search(r"\bSPI\b|SISTEMA DE PAGOS INTERBANCARIOS|BANCO CENTRAL|BCE", t):
        return "SPI"
    if re.search(r"COMPROBANTE\s+DE\s+PAGO|ORDEN\s+DE\s+PAGO|PAGO\s+N[ouº°]", t):
        return "PAGO"
    if re.search(r"COMPROBANTE\s+DE\s+RETENCION|RETENCION|RETENCI[ÓO]N", t):
        return "RETENCION"
    if re.search(r"COMPROBANTE\s+CONTABLE|ASIENTO\s+CONTABLE|DIARIO\s+GENERAL", t):
        return "CONTABLE"
    if re.search(r"FACTURA|FACT\.|COMPROBANTE\s+DE\s+VENTA|NOTA\s+DE\s+VENTA", t):
        return "FACTURA"
    return "OTRO"

def _find_first(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(0) if m else None

def _find_near_amount(keys, text):
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

def _find_num_close(keys, text):
    """Busca un número de 6-9 dígitos cercano a claves tipo FACTURA / N°"""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        for k in keys:
            if re.search(k, ln, flags=re.IGNORECASE):
                cand = " ".join(lines[max(0, i-1):min(len(lines), i+2)])
                m = re.search(r"(?<!\d)\d{6,9}(?!\d)", cand)
                if m:
                    return m.group(0)
    return None

def _extract_concept(text_norm: str) -> str | None:
    for kw in [r"CONCEPTO[: ]", r"DESCRIPCI[ÓO]N[: ]", r"OBJETO[: ]", r"DETALLE[: ]"]:
        m = re.search(kw + r"(.{5,160})", text_norm, flags=re.IGNORECASE)
        if m:
            return _clean_upper(m.group(1))
    m = re.search(r"\bPOR\s+(.{5,160})", text_norm, flags=re.IGNORECASE)
    return _clean_upper(m.group(1)) if m else None

@st.cache_data(show_spinner=False)
def extract_pdf_fields_cached(file_name: str, file_bytes: bytes) -> dict:
    """
    Extrae campos de un PDF (texto digital) y los clasifica.
    Cacheado por (nombre + hash) para estabilidad y rendimiento.
    """
    digest = hashlib.sha1(file_bytes).hexdigest()[:16]
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = []
            for pg in pdf.pages:
                t = pg.extract_text() or ""
                pages_text.append(t)
        full_text = "\n".join(pages_text)
    except Exception as e:
        return {
            "file": file_name, "digest": digest, "ok": False, "error": f"Lectura PDF falló: {e}",
            "tipo": None, "ruc": None, "factura": None, "fecha_doc": None, "beneficiario": None,
            "serie_pdf": None, "num_pdf": None, "concepto": None,
            "subtotal": np.nan, "iva": np.nan, "total": np.nan,
            "ret_iva": np.nan, "ret_renta": np.nan, "ret_total": np.nan,
            "valor_pago": np.nan, "valor_spi": np.nan, "valor_contable": np.nan,
            "texto_len": 0
        }

    text_norm = _norm_txt(full_text)
    if not text_norm or len(text_norm.strip()) < 40:
        return {
            "file": file_name, "digest": digest, "ok": False, "error": "PDF sin texto (probable escaneo). Requiere OCR.",
            "tipo": None, "ruc": None, "factura": None, "fecha_doc": None, "beneficiario": None,
            "serie_pdf": None, "num_pdf": None, "concepto": None,
            "subtotal": np.nan, "iva": np.nan, "total": np.nan,
            "ret_iva": np.nan, "ret_renta": np.nan, "ret_total": np.nan,
            "valor_pago": np.nan, "valor_spi": np.nan, "valor_contable": np.nan,
            "texto_len": 0
        }

    tipo = classify_document(text_norm)
    ruc = _find_first(r"\b\d{13}\b", text_norm)  # RUC (EC)
    factura = _find_first(r"\b\d{3}[- ]\d{3}[- ]\d{6,9}\b", text_norm)
    fecha = _find_first(r"\b(?:\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})\b", text_norm)

    # Serie/Número por separado (si el PDF no trae factura completa)
    serie_pdf = _find_first(r"\b\d{3}[- ]\d{3}\b", text_norm)
    num_pdf = _find_num_close([r"FACTURA", r"N[º°o]\b", r"\bNO\b", r"N°"], text_norm)

    concepto = _extract_concept(text_norm)

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
        "file": file_name, "digest": digest, "ok": True, "error": None,
        "tipo": tipo, "ruc": ruc, "factura": factura, "fecha_doc": fecha,
        "beneficiario": _clean_upper(concepto if tipo in ["PAGO","CONTABLE"] and concepto else (None)) or None,  # en pagos/contable a veces Benef=parte del concepto
        "serie_pdf": serie_pdf, "num_pdf": num_pdf, "concepto": concepto,
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
        key="xlsx_uploader",
    )

    st.header("2. PDFs")
    side_uploaded_pdfs = st.file_uploader(
        "Drag and drop files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Límite recomendado 200MB por archivo - PDF",
        key="pdfs_uploader",
    )

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
            st.session_state["last_excel_name"] = uploaded_xlsx.name
            st.success(f"Archivo recibido: {uploaded_xlsx.name} | Filas: {len(df):,} | Columnas: {len(df.columns)}")
            st.subheader("Vista previa (primeras 20 filas)")
            st.dataframe(df.head(20), use_container_width=True)

            st.subheader("Columnas detectadas (ya limpias)")
            st.write(list(df.columns))

            st.subheader("Perfil rápido de columnas")
            st.dataframe(info_rapida_dataframe(df), use_container_width=True, hide_index=True)

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

    # ====== Extraer PDFs con cache y progreso ======
    with st.status("Extrayendo información de PDFs…", expanded=False) as status:
        rows = []
        for pf in pdf_files:
            try:
                data = pf.getvalue()
                fields = extract_pdf_fields_cached(pf.name, data)
            except Exception as ex:
                fields = {
                    "file": pf.name, "ok": False, "error": f"Fallo inesperado: {ex}",
                    "tipo": None, "ruc": None, "factura": None, "fecha_doc": None, "beneficiario": None,
                    "serie_pdf": None, "num_pdf": None, "concepto": None,
                    "subtotal": np.nan, "iva": np.nan, "total": np.nan,
                    "ret_iva": np.nan, "ret_renta": np.nan, "ret_total": np.nan,
                    "valor_pago": np.nan, "valor_spi": np.nan, "valor_contable": np.nan,
                    "texto_len": 0
                }
            rows.append(fields)
        status.update(label="Extracción completada", state="complete", expanded=False)

    pdf_df = pd.DataFrame(rows)

    # ---------- Asegurar columnas y parar si todos son ilegibles ----------
    required_cols = [
        "tipo","ruc","factura","fecha_doc","beneficiario",
        "serie_pdf","num_pdf","concepto",
        "subtotal","iva","total","ret_iva","ret_renta","ret_total",
        "valor_pago","valor_spi","valor_contable"
    ]
    for c in required_cols:
        if c not in pdf_df.columns:
            pdf_df[c] = np.nan

    ok_count = int(pdf_df.get("ok", pd.Series([False]*len(pdf_df))).sum())
    st.markdown("**Resumen de PDFs**")
    st.dataframe(pdf_df.fillna(""), use_container_width=True)

    if ok_count == 0:
        st.error("Ningún PDF contiene texto legible (probables escaneos). Suba versiones exportadas del sistema o PDFs con OCR.")
        st.stop()

    # ---------- Normalizaciones seguras ----------
    # Matriz de claves: SERIE+N°
    st.markdown("---")
    st.subheader("Enlace de PDFs con filas de la matriz")

    # Sugerencias comunes
    sug_serie = next((c for c in df.columns if re.search(r"\bSERIE\b", str(c), flags=re.IGNORECASE)), None)
    sug_num   = next((c for c in df.columns if re.search(r"\bN.?[UÚ]M|\bN°\b|\bNO\b", str(c), flags=re.IGNORECASE)), None)
    sug_ruc   = next((c for c in df.columns if re.search(r"\bRUC\b", str(c), flags=re.IGNORECASE)), None)
    sug_benef = next((c for c in df.columns if re.search(r"NOMBRE|BENEFICIARIO|PROVEEDOR", str(c), flags=re.IGNORECASE)), None)
    sug_fecha = next((c for c in df.columns if re.search(r"FECHA", str(c), flags=re.IGNORECASE)), None)
    sug_total = next((c for c in df.columns if re.search(r"TOTAL|MONTO|VALOR", str(c), flags=re.IGNORECASE)), None)
    sug_concp = next((c for c in df.columns if re.search(r"CONCEPTO|DETALLE|DESCRIP", str(c), flags=re.IGNORECASE)), None)

    c1, c2, c3 = st.columns(3)
    with c1:
        col_serie = st.selectbox("Columna **SERIE** (factura)", [None] + list(df.columns),
                                 index=(list(df.columns).index(sug_serie)+1 if sug_serie in df.columns else 0))
    with c2:
        col_num = st.selectbox("Columna **NÚMERO/N°** (factura)", [None] + list(df.columns),
                               index=(list(df.columns).index(sug_num)+1 if sug_num in df.columns else 0))
    with c3:
        col_ruc_m = st.selectbox("Columna **RUC** (matriz)", [None] + list(df.columns),
                                 index=(list(df.columns).index(sug_ruc)+1 if sug_ruc in df.columns else 0))

    c4, c5, c6 = st.columns(3)
    with c4:
        col_benef_m = st.selectbox("Columna **BENEFICIARIO** (matriz)", [None] + list(df.columns),
                                   index=(list(df.columns).index(sug_benef)+1 if sug_benef in df.columns else 0))
    with c5:
        col_fecha_m = st.selectbox("Columna **FECHA** (matriz)", [None] + list(df.columns),
                                   index=(list(df.columns).index(sug_fecha)+1 if sug_fecha in df.columns else 0))
    with c6:
        col_total_m = st.selectbox("Columna **TOTAL/VALOR** (matriz)", [None] + list(df.columns),
                                   index=(list(df.columns).index(sug_total)+1 if sug_total in df.columns else 0))

    col_concepto = st.selectbox("Columna **CONCEPTO** (matriz) (opcional)", [None] + list(df.columns),
                                index=(list(df.columns).index(sug_concp)+1 if sug_concp in df.columns else 0))

    c7, c8 = st.columns(2)
    with c7:
        modo_nomina = st.checkbox("Activar **modo Nómina** (sin factura; fecha rectora = comprobante de pago)", value=False)
    with c8:
        tolerancia_dias = st.slider("Tolerancia de pertenencia (± días)", 0, 15, 5, 1)

    st.caption("Clave primaria **Factura** = SERIE (001-002) + NÚMERO (relleno a 9 dígitos) → `001-002-000123456`. Si el PDF no trae la factura completa, se intenta reconstruir con `serie_pdf` y `num_pdf`.")

    ejecutar_link = st.button("Cotejar PDFs vs Matriz")

    if ejecutar_link:
        work = df.copy()

        # --- Normalizar claves desde la MATRIZ ---
        serie_col = work[col_serie] if col_serie else pd.Series("", index=work.index)
        num_col   = work[col_num]   if col_num   else pd.Series("", index=work.index)
        keys_df = norm_serie_num_series(serie_col, num_col)

        ruc_matrix   = work[col_ruc_m].astype(str).str.strip() if col_ruc_m else pd.Series("", index=work.index)
        benef_matrix = work[col_benef_m].astype(str) if col_benef_m else pd.Series("", index=work.index)
        fecha_matrix = pd.to_datetime(work[col_fecha_m], errors="coerce") if col_fecha_m else pd.Series(pd.NaT, index=work.index)
        total_matrix = pd.to_numeric(work[col_total_m], errors="coerce") if col_total_m else pd.Series(np.nan, index=work.index)
        conc_matrix  = work[col_concepto].astype(str) if col_concepto else pd.Series("", index=work.index)

        work = pd.concat([work, keys_df], axis=1)
        work["_RUC_MATRIZ"] = ruc_matrix
        work["_BENEF_MATRIZ"] = benef_matrix.apply(_clean_upper)
        work["_FECHA_MATRIZ"] = fecha_matrix
        work["_TOTAL_MATRIZ"] = total_matrix
        work["_CONCEPTO_MATRIZ"] = conc_matrix.apply(_clean_upper)

        # --- Normalizaciones desde PDF ---
        pdf_df = pdf_df.copy()
        # factura ya puede venir completa
        pdf_df["factura_norm"] = pdf_df["factura"].fillna("").astype(str).str.replace(" ", "", regex=False)

        # si no hay factura, intentar construir desde serie_pdf + num_pdf
        serie_digits = pdf_df["serie_pdf"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str[:6].str.zfill(6)
        pdf_df["serie_pdf_fmt"] = serie_digits.str.replace(r"(\d{3})(\d{3})", r"\1-\2", regex=True)
        num_digits = pdf_df["num_pdf"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str[-9:].str.zfill(9)
