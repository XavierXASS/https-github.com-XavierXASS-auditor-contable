# ==== IMPORTS (deben estar al nivel superior, no dentro de if/try/funciones) ====
import streamlit as st
import pandas as pd
import numpy as np
import io, re, unicodedata
import pdfplumber
from datetime import datetime
# =========================
# Sección: Procesamiento de PDFs y cotejo con la matriz
# =========================

st.markdown("---")
st.subheader("Procesamiento de PDFs y cotejo con la matriz")

# -------- Utilidades de normalización y extracción (nivel superior, sin sangría) --------
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
                # revisar misma línea y vecinas
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
    # factura típica: 001-002-000123456
    factura = _find_first(r"\b\d{3}[- ]\d{3}[- ]\d{6,9}\b", text_norm)
    # fecha dd/mm/yyyy o yyyy-mm-dd
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

# -------- UI y lógica (con sangría simple, solo dentro de if/else) --------
if not uploaded_pdfs:
    st.info("Sube los PDFs (Factura, Retención, Comprobante de Pago, SPI, Comprobante Contable) en la barra lateral para habilitar el cotejo.")
else:
    st.caption(f"Se recibieron {len(uploaded_pdfs)} PDF(s).")

    # Procesar todos los PDFs cargados
    pdf_rows = [extract_pdf_fields(pf) for pf in uploaded_pdfs]
    pdf_df = pd.DataFrame(pdf_rows)

    st.markdown("**Resumen de PDFs**")
    st.dataframe(pdf_df.fillna(""), use_container_width=True)

    if (pdf_df["ok"] == False).any():
        st.warning("Algunos PDFs no se pudieron leer o no contienen texto. Revisa la columna 'error'. (Para escaneados, se requiere OCR).")

    # -------- Mapeo con la matriz para enlazar fila ↔ documentos --------
    st.markdown("---")
    st.subheader("Enlace de PDFs con filas de la matriz")

    # Sugerencias según nombres de columnas
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

    st.caption("La **clave** de enlace será: RUC + SERIE-NÚMERO (si existen). Si el PDF trae `factura` en formato `001-002-…`, se comparará con SERIE-NÚM.")

    ejecutar_link = st.button("Cotejar PDFs vs Matriz")

    if ejecutar_link:
        work = df.copy()

        # Normalizar campos de matriz para generar clave factura "SERIE-NUM"
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

        # Normalizar factura desde PDF: quitar espacios
        pdf_df["factura_norm"] = pdf_df["factura"].fillna("").str.replace(" ", "", regex=False)
        pdf_df["ruc_norm"] = pdf_df["ruc"].fillna("").str.strip()
        pdf_df["benef_norm"] = pdf_df["beneficiario"].fillna("").apply(_clean_benef)

        # 1) Join por RUC + FACTURA
        j1 = work.merge(
            pdf_df, left_on=["_RUC_MATRIZ", "_FACT_MATRIZ"], right_on=["ruc_norm", "factura_norm"], how="left", suffixes=("", "_pdf")
        )
        j1["_mecanismo"] = np.where(j1["file"].notna(), "RUC+FACT", None)

        # 2) FACTURA sola para los que no coincidieron
        mask_unmatched = j1["file"].isna()
        joins = [j1]
        if mask_unmatched.any() and work["_FACT_MATRIZ"].str.len().gt(0).any():
            j2 = work[mask_unmatched].merge(
                pdf_df, left_on="_FACT_MATRIZ", right_on="factura_norm", how="left", suffixes=("", "_pdf")
            )
            j2["_mecanismo"] = np.where(j2["file"].notna(), "FACT", None)
            joins.append(j2)

        # 3) Beneficiario + Fecha (±5 días)
        pdf_df["_fecha_doc_dt"] = pd.to_datetime(pdf_df["fecha_doc"], errors="coerce", dayfirst=True)
        # filas restantes (no emparejadas en j1/j2)
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
                how="left",
                suffixes=("", "_pdf"),
            )
            delta_ok = (cand["_fecha_doc_dt"].notna()) & (cand["_FECHA_MATRIZ"].notna()) & (cand["_FECHA_MATRIZ"].sub(cand["_fecha_doc_dt"]).abs().dt.days <= 5)
            cand = cand[delta_ok]
            if not cand.empty:
                cand["_mecanismo"] = np.where(cand["file"].notna(), "BEN+FECHA±5d", None)
                joins.append(cand)

        # Unir resultados y priorizar por tipo
        all_matches = pd.concat(joins, axis=0, ignore_index=False)
        prio = {"FACTURA": 1, "RETENCION": 2, "SPI": 3, "PAGO": 4, "CONTABLE": 5, "OTRO": 6, None: 99}
        all_matches["_prio"] = all_matches["tipo"].map(prio).fillna(99)
        best = all_matches.sort_values(by=["_prio"]).groupby(level=0, as_index=True).head(1)

        st.markdown("**Enlaces generados (mejor coincidencia por fila)**")
        cols_show = ["file", "tipo", "ruc", "factura", "fecha_doc", "beneficiario", "subtotal", "iva", "total", "ret_iva", "ret_renta", "ret_total", "valor_pago", "valor_spi", "valor_contable", "_mecanismo"]
        preview = best[["_RUC_MATRIZ", "_FACT_MATRIZ", "_BENEF_MATRIZ", "_FECHA_MATRIZ", "_TOTAL_MATRIZ"] + [c for c in cols_show if c in best.columns]]
        st.dataframe(preview.fillna(""), use_container_width=True)

        # -------- Reglas periciales y cálculo de valor a pagar --------
        st.markdown("---")
        st.subheader("Reglas periciales y cálculos")

        best["_ret_total_est"] = best["ret_total"]
        best.loc[best["_ret_total_est"].isna(), "_ret_total_est"] = np.nansum([best["ret_iva"].fillna(0.0), best["ret_renta"].fillna(0.0)], axis=0)
        best["_apagar_docs"] = np.round(best["total"].fillna(0.0) - best["_ret_total_est"].fillna(0.0), 2)

        def _eq2(a, b):
            if pd.isna(a) or pd.isna(b):
                return False
            return round(float(a), 2) == round(float(b), 2)

        best["_benef_ok"] = best.apply(lambda r: (_clean_benef(r.get("beneficiario")) == _clean_benef(r.get("_BENEF_MATRIZ"))), axis=1)

        best["_fecha_ok"] = best.apply(
            lambda r: (
                (pd.to_datetime(r.get("fecha_doc"), errors="coerce") == r.get("_FECHA_MATRIZ"))
                or (pd.notna(pd.to_datetime(r.get("fecha_doc"), errors="coerce")) and pd.notna(r.get("_FECHA_MATRIZ")) and abs((pd.to_datetime(r.get("fecha_doc"), errors="coerce") - r.get("_FECHA_MATRIZ")).days) <= 5)
            ),
            axis=1
        )

        best["_total_vs_matriz"] = best.apply(lambda r: _eq2(r.get("total"), r.get("_TOTAL_MATRIZ")), axis=1) if col_total_m else False
        best["_apagar_vs_spi"] = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_spi")), axis=1)
        best["_apagar_vs_pago"] = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_pago")), axis=1)
        best["_apagar_vs_cont"] = best.apply(lambda r: _eq2(r.get("_apagar_docs"), r.get("valor_contable")), axis=1)

        findings = []
        for i, r in best.iterrows():
            if pd.isna(r.get("file")):
                findings.append({"fila": int(i), "campo": "DOCUMENTO", "tipo": "ERROR", "mensaje": "No se encontró PDF enlazado para la fila."})
                continue

            if not r["_benef_ok"]:
                findings.append({"fila": int(i), "campo": "BENEFICIARIO", "tipo": "ERROR", "mensaje": "Beneficiario difiere entre PDF y matriz."})

            if not r["_fecha_ok"]:
                findings.append({"fila": int(i), "campo": "FECHA", "tipo": "WARN", "mensaje": "Fecha documento no coincide; verificar pertenencia al proceso."})

            if col_total_m and not r["_total_vs_matriz"] and not pd.isna(r.get("total")) and not pd.isna(r.get("_TOTAL_MATRIZ")):
                findings.append({"fila": int(i), "campo": "TOTAL", "tipo": "ERROR", "mensaje": "Total de factura difiere del valor en matriz."})

            if r.get("tipo") in ["RETENCION", "FACTURA"] and pd.notna(r.get("total")) and pd.notna(r.get("_ret_total_est")):
                if r["_ret_total_est"] < 0 or r["_ret_total_est"] > r["total"]:
                    findings.append({"fila": int(i), "campo": "RETENCION", "tipo": "ERROR", "mensaje": "Retenciones inconsistentes con total de factura."})

            if r.get("valor_spi") and not r["_apagar_vs_spi"]:
                findings.append({"fila": int(i), "campo": "SPI", "tipo": "ERROR", "mensaje": "Valor del SPI no coincide con Total - Retenciones."})
            if r.get("valor_pago") and not r["_apagar_vs_pago"]:
                findings.append({"fila": int(i), "campo": "PAGO", "tipo": "ERROR", "mensaje": "Valor del Comprobante de Pago no coincide con Total - Retenciones."})
            if r.get("valor_contable") and not r["_apagar_vs_cont"]:
                findings.append({"fila": int(i), "campo": "CONTABLE", "tipo": "ERROR", "mensaje": "Haber/Total contable no coincide con Total - Retenciones."})

        findings_df = pd.DataFrame(findings, columns=["fila", "campo", "tipo", "mensaje"])
        if findings_df.empty:
            st.success("✅ Cotejo completado: sin hallazgos críticos en las filas enlazadas.")
        else:
            st.warning(f"Cotejo completado con {int((findings_df['tipo']=='ERROR').sum())} errores y {int((findings_df['tipo']=='WARN').sum())} advertencias.")
            st.dataframe(findings_df.sort_values(["tipo","fila","campo"]), use_container_width=True)

            st.download_button(
                "⬇️ Descargar hallazgos (CSV)",
                data=findings_df.to_csv(index=False).encode("utf-8"),
                file_name="hallazgos_cotejo.pdfs_vs_matriz.csv",
                mime="text/csv"
            )

        with st.expander("Detalle de cálculo por fila (para auditoría)", expanded=False):
            det_cols = ["_RUC_MATRIZ","_FACT_MATRIZ","_BENEF_MATRIZ","_FECHA_MATRIZ","_TOTAL_MATRIZ","file","tipo","ruc","factura","fecha_doc","beneficiario","subtotal","iva","total","_ret_total_est","_apagar_docs","valor_spi","valor_pago","valor_contable","_mecanismo"]
            st.dataframe(best[det_cols].copy(), use_container_width=True)
