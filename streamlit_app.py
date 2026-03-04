# ==== IMPORTS (nivel superior, sin sangría) ====
import streamlit as st
import pandas as pd
import numpy as np
import io, re, unicodedata, hashlib
import pdfplumber
from datetime import datetime
# ==============================================

# =========================
# Configuración de página
# =========================
st.set_page_config(page_title="Terminal de Emergencia - Pericia", layout="wide")

# Mostrar menos ruido si hay errores
st.write("")  # mantiene primer render estable

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
    "Luego cargue **PDFs** y ejecute el **cotejo completo**."
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

def _clean_benef(s: str) -> str:
    s = _norm_txt(s).upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s[:200]

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
            "columna": col,
            "tipo": str(df[col].dtype),
            "n_nulos": n_null,
            "%_nulos": round(100.0 * n_null / max(n, 1), 2),
            "ejemplo": ejemplo
        })
    return pd.DataFrame(resumen)

# =========================
# Utilidades PDF (clasificación y extracción)
# =========================
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
        return {"file": file_name, "digest": digest, "ok": False, "error": f"Lectura PDF falló: {e}"}

    text_norm = _norm_txt(full_text)
    if not text_norm or len(text_norm.strip()) < 40:
        return {"file": file_name, "digest": digest, "ok": False, "error": "PDF sin texto (probable escaneo). Requiere OCR."}

    tipo = classify_document(text_norm)
    ruc = _find_first(r"\b\d{13}\b", text_norm)
    factura = _find_first(r"\b\d{3}[- ]\d{3}[- ]\d{6,9}\b", text_norm)
    fecha = _find_first(r"\b(?:\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})\b", text_norm)

    benef = None
    for k in [r"RAZ[OÓ]N\s+SOCIAL[: ]", r"BENEFICIARIO[: ]", r"PROVEEDOR[: ]", r"NOMBRE[: ]"]:
        m = re.search(k + r"(.{3,80})", text_norm, flags=re.IGNORECASE)
        if m:
            benef = _clean_benef(m.group(1))
            break

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
                fields = {"file": pf.name, "ok": False, "error": f"Fallo inesperado: {ex}"}
            rows.append(fields)
        status.update(label="Extracción completada", state="complete", expanded=False)

    pdf_df = pd.DataFrame(rows)
    st.markdown("**Resumen de PDFs**")
    st.dataframe(pdf_df.fillna(""), use_container_width=True)

    if "ok" in pdf_df and (pdf_df["ok"] == False).any():
        st.warning("Algunos PDFs no se pudieron leer o no contienen texto. Revisa la columna 'error'. (Para escaneados, se requiere OCR).")

    # ====== Mapeo con la matriz para enlazar fila ↔ documentos ======
    st.markdown("---")
    st.subheader("Enlace de PDFs con filas de la matriz")

    # Sugerencias de columnas habituales
    sug_serie = next((c for c in df.columns if re.search(r"\bSERIE\b", str(c), flags=re.IGNORECASE)), None)
    sug_num   = next((c for c in df.columns if re.search(r"\bN.?[UÚ]M", str(c), flags=re.IGNORECASE)), None)
    sug_ruc   = next((c for c in df.columns if re.search(r"\bRUC\b", str(c), flags=re.IGNORECASE)), None)
    sug_benef = next((c for c in df.columns if re.search(r"NOMBRE|BENEFICIARIO|PROVEEDOR", str(c), flags=re.IGNORECASE)), None)
    sug_fecha = next((c for c in df.columns if re.search(r"FECHA", str(c), flags=re.IGNORECASE)), None)
    sug_total = next((c for c in df.columns if re.search(r"TOTAL|MONTO|VALOR", str(c), flags=re.IGNORECASE)), None)

    c1, c2, c3 = st.columns(3)
    with c1:
        col_serie = st.selectbox("Columna SERIE (factura)", [None] + list(df.columns), index=(list(df.columns).index(sug_serie)+1 if sug_serie in df.columns else 0))
    with c2:
        col_num = st.selectbox("Columna NÚMERO (factura)", [None] + list(df.columns), index=(list(df.columns).index(sug_num)+1 if sug_num in df.columns else 0))
    with c3:
        col_ruc_m = st.selectbox("Columna RUC (matriz)", [None] + list(df.columns), index=(list(df.columns).index(sug_ruc)+1 if sug_ruc in df.columns else 0))

    c4, c5, c6 = st.columns(3)
    with c4:
        col_benef_m = st.selectbox("Columna BENEFICIARIO (matriz)", [None] + list(df.columns), index=(list(df.columns).index(sug_benef)+1 if sug_benef in df.columns else 0))
    with c5:
        col_fecha_m = st.selectbox("Columna FECHA (matriz)", [None] + list(df.columns), index=(list(df.columns).index(sug_fecha)+1 if sug_fecha in df.columns else 0))
    with c6:
        col_total_m = st.selectbox("Columna TOTAL/VALOR (matriz)", [None] + list(df.columns), index=(list(df.columns).index(sug_total)+1 if sug_total in df.columns else 0))

    c7, c8 = st.columns(2)
    with c7:
        modo_nomina = st.checkbox("Activar **modo Nómina** (sin factura; fecha rectora = comprobante de pago)", value=False)
    with c8:
        tolerancia_dias = st.slider("Tolerancia de pertenencia (± días)", 0, 15, 5, 1)

    st.caption("La **clave** de enlace será: RUC + SERIE-NÚMERO (si existen). Si el PDF trae `factura` en formato `001-002-…`, se comparará con SERIE-NÚM.")

    ejecutar_link = st.button("Cotejar PDFs vs Matriz")
    if ejecutar_link:
        work = df.copy()

        # Normalizar campos de matriz para generar clave "SERIE-NUM"
        def _to_str(s):
            return s.astype(str).str.strip()

        serie = _to_str(work[col_serie]) if col_serie else pd.Series("", index=work.index)
        num = _to_str(work[col_num]) if col_num else pd.Series("", index=work.index)
        fact_from_matrix = (serie + "-" + num).str.replace(r"\s+", "", regex=True).str.replace("--", "-", regex=False).str.strip("-")

        ruc_matrix = _to_str(work[col_ruc_m]) if col_ruc_m else pd.Series("", index=work.index)
        benef_matrix = _to_str(work[col_benef_m]) if col_benef_m else pd.Series("", index=work.index)
        fecha_matrix = pd.to_datetime(work[col_fecha_m], errors="coerce") if col_fecha_m else pd.Series(pd.NaT, index=work.index)
        total_matrix = pd.to_numeric(work[col_total_m], errors="coerce") if col_total_m else pd.Series(np.nan, index=work.index)

        work["_FACT_MATRIZ"] = fact_from_matrix
        work["_RUC_MATRIZ"] = ruc_matrix
        work["_BENEF_MATRIZ"] = benef_matrix.apply(_clean_benef)
        work["_FECHA_MATRIZ"] = fecha_matrix
        work["_TOTAL_MATRIZ"] = total_matrix

        # Normalizar datos desde PDF
        pdf_df = pdf_df.copy()
        pdf_df["factura_norm"] = pdf_df["factura"].fillna("").str.replace(" ", "", regex=False)
        pdf_df["ruc_norm"] = pdf_df["ruc"].fillna("").str.strip()
        pdf_df["benef_norm"] = pdf_df["beneficiario"].fillna("").apply(_clean_benef)
        pdf_df["_fecha_doc_dt"] = pd.to_datetime(pdf_df["fecha_doc"], errors="coerce", dayfirst=True)

        # ===== Enlaces múltiples (para luego verificar "faltantes por tipo") =====
        # 1) RUC + FACTURA
        j1 = work.merge(
            pdf_df, left_on=["_RUC_MATRIZ", "_FACT_MATRIZ"],
            right_on=["ruc_norm", "factura_norm"], how="left", suffixes=("", "_pdf")
        )
        j1["_mecanismo"] = np.where(j1["file"].notna(), "RUC+FACT", None)

        # 2) FACTURA sola
        mask_unmatched = j1["file"].isna()
        joins = [j1]
        if mask_unmatched.any() and work["_FACT_MATRIZ"].str.len().gt(0).any():
            j2 = work[mask_unmatched].merge(
                pdf_df, left_on="_FACT_MATRIZ", right_on="factura_norm", how="left", suffixes=("", "_pdf")
            )
            j2["_mecanismo"] = np.where(j2["file"].notna(), "FACT", None)
            joins.append(j2)

        # 3) Beneficiario + Fecha (± tolerancia)
        matched_idx = pd.Index([])
        for jx in joins:
            matched_idx = matched_idx.union(jx.index[jx["file"].notna()])
        left_rem = work.loc[work.index.difference(matched_idx)]

        if not left_rem.empty and col_benef_m and col_fecha_m:
            tmp = left_rem.copy()
            cand = tmp.merge(
                pdf_df,
                left_on=tmp["_BENEF_MATRIZ"].str.upper(),
                right_on=pdf_df["benef_norm"].str.upper(),
                how="left", suffixes=("", "_pdf"),
            )
            delta_ok = (cand["_fecha_doc_dt"].notna()) & (cand["_FECHA_MATRIZ"].notna()) & (cand["_FECHA_MATRIZ"].sub(cand["_fecha_doc_dt"]).abs().dt.days <= int(tolerancia_dias))
            cand = cand[delta_ok]
            if not cand.empty:
                cand["_mecanismo"] = np.where(cand["file"].notna(), "BEN+FECHA±d", None)
                joins.append(cand)

        # Unir *todas* las coincidencias para poder evaluar faltantes por tipo
        all_matches = pd.concat(joins, axis=0, ignore_index=False)

        # Elegir “mejor coincidencia” por fila (para cálculo y comparaciones principales)
        prio = {"FACTURA": 1, "RETENCION": 2, "SPI": 3, "PAGO": 4, "CONTABLE": 5, "OTRO": 6, None: 99}
        all_matches["_prio"] = all_matches["tipo"].map(prio).fillna(99)
        best = all_matches.sort_values(by=["_prio"]).groupby(level=0, as_index=True).head(1)

        st.markdown("**Enlaces generados (mejor coincidencia por fila)**")
        cols_show = ["file","tipo","ruc","factura","fecha_doc","beneficiario","subtotal","iva","total","ret_iva","ret_renta","ret_total","valor_pago","valor_spi","valor_contable","_mecanismo"]
        preview = best[["_RUC_MATRIZ","_FACT_MATRIZ","_BENEF_MATRIZ","_FECHA_MATRIZ","_TOTAL_MATRIZ"] + [c for c in cols_show if c in best.columns]]
        st.dataframe(preview.fillna(""), use_container_width=True)

        # ===== Reglas periciales y cálculos =====
        st.markdown("---")
        st.subheader("Reglas periciales, cálculos y **notas**")

        # Cálculo de valor a pagar (Total - Retenciones)
        best["_ret_total_est"] = best["ret_total"]
        best.loc[best["_ret_total_est"].isna(), "_ret_total_est"] = np.nansum([best["ret_iva"].fillna(0.0), best["ret_renta"].fillna(0.0)], axis=0)
        best["_apagar_docs"] = np.round(best["total"].fillna(0.0) - best["_ret_total_est"].fillna(0.0), 2)

        def _eq2(a, b):
            if pd.isna(a) or pd.isna(b):
                return False
            return round(float(a), 2) == round(float(b), 2)

        # Beneficiario (mandatorio)
        best["_benef_ok"] = best.apply(lambda r: (_clean_benef(r.get("beneficiario")) == _clean_benef(r.get("_BENEF_MATRIZ"))), axis=1)

        # Fechas: rectora la de factura; para otros docs permitir ±tolerancia
        best["_fecha_doc_dt"] = pd.to_datetime(best["fecha_doc"], errors="coerce", dayfirst=True)
        best["_fecha_ok"] = best.apply(
            lambda r: (
                (pd.notna(r.get("_fecha_doc_dt")) and r.get("_fecha_doc_dt") == r.get("_FECHA_MATRIZ"))
                or (pd.notna(r.get("_fecha_doc_dt")) and pd.notna(r.get("_FECHA_MATRIZ")) and abs((r.get("_fecha_doc_dt") - r.get("_FECHA_MATRIZ")).days) <= int(tolerancia_dias))
            ),
            axis=1
        )

        # Comparaciones monetarias
        best["_total_vs_matriz"] = best.apply(lambda r: _eq2(r.get("total"), r.get("_TOTAL_MATRIZ")), axis=1) if col_total_m else False
        best["_apagar_vs_spi"]  = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_spi")), axis=1)
        best["_apagar_vs_pago"] = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_pago")), axis=1)
        best["_apagar_vs_cont"] = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_contable")), axis=1)

        findings = []

        # ======= (1) Filas de la matriz sin documentos =======
        filas_con_doc = set(all_matches.index[all_matches["file"].notna()])
        todas_filas = set(work.index)
        sin_docs = sorted(list(todas_filas - filas_con_doc))
        for i in sin_docs:
            findings.append({"fila": int(i), "categoria": "SIN_DOCUMENTOS", "tipo": "NOTE", "mensaje": "La fila de la matriz no tiene PDFs enlazados."})

        # ======= (2) PDFs sueltos que no empatan con ninguna fila (sugerencias para completar) =======
        matched_file_names = set(all_matches.loc[all_matches["file"].notna(), "file"].astype(str).unique())
        all_pdf_names = set(pdf_df["file"].astype(str))
        pdf_sueltos = sorted(list(all_pdf_names - matched_file_names))
        # Generar tabla de sugerencias
        sugerencias = pdf_df[pdf_df["file"].isin(pdf_sueltos)][["file","tipo","ruc","factura","fecha_doc","beneficiario","total","ret_total","valor_spi","valor_pago","valor_contable"]].copy()
        if not sugerencias.empty:
            st.info("Hay PDFs sin fila en la matriz. Se muestran **sugerencias** para completar:")
            st.dataframe(sugerencias.fillna(""), use_container_width=True)
            st.download_button(
                "⬇️ Descargar sugerencias para completar matriz (CSV)",
                data=sugerencias.to_csv(index=False).encode("utf-8"),
                file_name="sugerencias_completar_matriz_desde_pdfs.csv",
                mime="text/csv"
            )

        # ======= (3) Datos errados + (4) Documentos incompletos + (5) Otros años + (6) Otros trimestres =======
        required_docs = {"FACTURA", "RETENCION", "PAGO", "SPI", "CONTABLE"} if not modo_nomina else {"PAGO", "SPI", "CONTABLE"}  # nómina: sin factura
        # set de tipos presentes por fila (en todas las coincidencias)
        tipos_por_fila = (all_matches[all_matches["file"].notna()]
                          .groupby(level=0)["tipo"]
                          .agg(lambda s: set([t for t in s if pd.notna(t)])))

        for i, r in best.iterrows():
            if pd.isna(r.get("file")):
                continue  # ya notado arriba como SIN_DOCUMENTOS

            # (3) Datos errados: beneficiario, total vs matriz, valor a pagar vs docs
            if not r["_benef_ok"]:
                findings.append({"fila": int(i), "categoria": "DATOS_ERRADOS", "tipo": "ERROR", "mensaje": "Beneficiario difiere entre PDF y matriz.", "sugerencia": r.get("beneficiario")})
            if col_total_m and not r["_total_vs_matriz"] and not pd.isna(r.get("total")) and not pd.isna(r.get("_TOTAL_MATRIZ")):
                findings.append({"fila": int(i), "categoria": "DATOS_ERRADOS", "tipo": "ERROR", "mensaje": "Total de factura difiere del valor en matriz.", "sugerencia": r.get("total")})
            if r.get("valor_spi") and not r["_apagar_vs_spi"]:
                findings.append({"fila": int(i), "categoria": "DATOS_ERRADOS", "tipo": "ERROR", "mensaje": "Valor del SPI no coincide con Total - Retenciones.", "sugerencia": r.get("_apagar_docs")})
            if r.get("valor_pago") and not r["_apagar_vs_pago"]:
                findings.append({"fila": int(i), "categoria": "DATOS_ERRADOS", "tipo": "ERROR", "mensaje": "Valor del Comprobante de Pago no coincide con Total - Retenciones.", "sugerencia": r.get("_apagar_docs")})
            if r.get("valor_contable") and not r["_apagar_vs_cont"]:
                findings.append({"fila": int(i), "categoria": "DATOS_ERRADOS", "tipo": "ERROR", "mensaje": "Haber/Total contable no coincide con Total - Retenciones.", "sugerencia": r.get("_apagar_docs")})

            # (4) Documentos incompletos: qué falta por fila
            tipos_presentes = tipos_por_fila.get(i, set())
            faltantes = sorted(list(required_docs - tipos_presentes))
            if faltantes:
                findings.append({"fila": int(i), "categoria": "DOCS_INCOMPLETOS", "tipo": "NOTE", "mensaje": f"Faltan documentos: {', '.join(faltantes)}"})

            # (5) Documentos de otros años (Infracción)
            fecha_m = r.get("_FECHA_MATRIZ")
            fecha_d = r.get("_fecha_doc_dt")
            if pd.notna(fecha_m) and pd.notna(fecha_d) and fecha_m.year != fecha_d.year:
                findings.append({"fila": int(i), "categoria": "OTRO_AÑO", "tipo": "ERROR", "mensaje": f"Documento del año {fecha_d.year} y la matriz es {fecha_m.year} (Infracción)."})

            # (6) Documentos de otros trimestres (nota)
            qm, qd = quarter_from_date(fecha_m), quarter_from_date(fecha_d)
            if (qm is not None) and (qd is not None) and (fecha_m.year == fecha_d.year) and (qm != qd):
                findings.append({"fila": int(i), "categoria": "OTRO_TRIMESTRE", "tipo": "NOTE", "mensaje": f"Documento trimestre Q{qd} distinto al de la matriz Q{qm}. Verificar en otras matrices."})

            # Modo Nómina: si está activo, advertir si se detectó 'FACTURA'
            if modo_nomina and "FACTURA" in tipos_presentes:
                findings.append({"fila": int(i), "categoria": "NOMINA", "tipo": "NOTE", "mensaje": "Modo Nómina activo; se ignorará la factura si aparece."})

        findings_df = pd.DataFrame(findings, columns=["fila","categoria","tipo","mensaje","sugerencia"]).fillna("")
        if findings_df.empty:
            st.success("✅ Cotejo completado: **sin hallazgos** en las filas enlazadas.")
        else:
            errores = int((findings_df["tipo"] == "ERROR").sum())
            warns   = int((findings_df["tipo"] == "NOTE").sum())
            st.warning(f"Cotejo completado con **{errores} errores** y **{warns} notas**.")
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Resumen por categoría**")
                st.dataframe(findings_df.groupby(["categoria","tipo"]).size().reset_index(name="conteo"), use_container_width=True, hide_index=True)
            with colB:
                st.markdown("**Top 100 hallazgos (detalle)**")
                st.dataframe(findings_df.sort_values(["tipo","categoria","fila"]).head(100), use_container_width=True)

            st.download_button(
                "⬇️ Descargar hallazgos (CSV)",
                data=findings_df.to_csv(index=False).encode("utf-8"),
                file_name="hallazgos_periciales.csv",
                mime="text/csv"
            )

        with st.expander("Detalle de cálculo por fila (para auditoría)", expanded=False):
            det_cols = [
                "_RUC_MATRIZ","_FACT_MATRIZ","_BENEF_MATRIZ","_FECHA_MATRIZ","_TOTAL_MATRIZ",
                "file","tipo","ruc","factura","fecha_doc","beneficiario","subtotal","iva","total",
                "ret_iva","ret_renta","ret_total","_ret_total_est","_apagar_docs",
                "valor_spi","valor_pago","valor_contable","_mecanismo"
            ]
            det_cols = [c for c in det_cols if c in best.columns]
            st.dataframe(best[det_cols].copy(), use_container_width=True)
