# -*- coding: utf-8 -*-
# ==============================================
#  Auditoría Forense - Confirmación + Progreso
#  Archivo: streamlit_app.py
#  Versión: confirm + progress + errores visibles
# ==============================================

import base64
import re
import time
from datetime import datetime
import unicodedata
import traceback

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -------------------------
# CONFIGURACIÓN UI
# -------------------------
st.set_page_config(page_title="SISTEMA PERICIAL - VISOR INTEGRADO", layout="wide")

# -------------------------
# ESTADO INICIAL ROBUSTO
# -------------------------
def init_state():
    defaults = {
        "db_pericial": {},
        "ex_file": None,
        "pdf_files": [],
        "confirm_answer": "No",     # "Sí" / "No"
        "confirmed": False,
        "processing": False,
        "process_done": False,
        "index_rows": [],
        "cross_rows": [],
        "leftovers": [],
        "pdf_index": {},
        "df_cache": None,
        "c_cp": None,
        "c_fec": None,
        "last_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# -------------------------
# UTILIDADES
# -------------------------
def get_clean_id(x) -> str:
    s = re.sub(r"\D", "", str(x))
    return s.lstrip("0") or s

def _norm(s: str) -> str:
    s = str(s).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"[\W_]+", "", s)
    return s

def find_col(df: pd.DataFrame, candidates: list[str], required: bool = True):
    norm_map = {_norm(c): c for c in df.columns}
    for cand in candidates:
        if cand in norm_map:
            return norm_map[cand]
    for k, v in norm_map.items():
        if any(c in k for c in candidates):
            return v
    if required:
        raise KeyError(f"No se encontró ninguna columna similar a: {candidates}")
    return None

@st.cache_data(show_spinner=False)
def to_base64_pdf(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")

def display_pdf(uploaded_file):
    """Muestra el PDF mediante iframe correcto (no texto escapado)."""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    fb = uploaded_file.read()
    if not fb:
        st.error("El PDF está vacío o no se pudo leer.")
        return
    b64 = to_base64_pdf(fb)
    iframe_html = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="880"></iframe>'
    components.html(iframe_html, height=900, scrolling=True)

# -------------------------
# SIDEBAR: CARGA + CONFIRMACIÓN
# -------------------------
with st.sidebar:
    st.header("⚙️ Panel de Control")

    ex_new = st.file_uploader("Matriz Excel (.xlsx)", type=["xlsx"], key="excel_up",
                              disabled=st.session_state.confirmed or st.session_state.processing)
    pdfs_new = st.file_uploader("Soportes PDFs (múltiples)", type=["pdf"], accept_multiple_files=True, key="pdfs_up",
                                disabled=st.session_state.confirmed or st.session_state.processing)

    if ex_new is not None:
        st.session_state.ex_file = ex_new
    if pdfs_new is not None and len(pdfs_new) > 0:
        st.session_state.pdf_files = pdfs_new

    # Confirmación explícita
    st.subheader("❓ ¿Son todos los archivos?")
    st.session_state.confirm_answer = st.radio(
        "Confirma para iniciar el procesamiento",
        options=["No", "Sí"], horizontal=True, label_visibility="collapsed",
        index=(1 if st.session_state.confirm_answer == "Sí" else 0),
        disabled=st.session_state.processing or st.session_state.process_done
    )

    # Parámetros de periodo
    st.divider()
    anio_actual = datetime.now().year
    st.session_state.anio_obj = st.number_input(
        "Año objetivo", min_value=2000, max_value=2100, value=anio_actual, step=1,
        disabled=st.session_state.processing
    )
    tri_opt = st.selectbox("Trimestre objetivo", ["Cualquiera","1","2","3","4"], index=0,
                           disabled=st.session_state.processing)
    st.session_state.tri_obj = None if tri_opt == "Cualquiera" else int(tri_opt)

    # Botones
    can_start = (
        st.session_state.ex_file is not None and
        len(st.session_state.pdf_files) > 0 and
        st.session_state.confirm_answer == "Sí" and
        (not st.session_state.processing) and
        (not st.session_state.process_done)
    )
    if st.button("✅ Procesar ahora", type="primary", use_container_width=True, disabled=not can_start):
        st.session_state.confirmed = True
        st.session_state.processing = True
        st.session_state.process_done = False
        st.session_state.last_error = None

    if st.button("🗑️ Reinicio total", use_container_width=True, disabled=st.session_state.processing):
        st.session_state.clear()
        st.rerun()

# -------------------------
# CABECERA + ESTADO EN VIVO
# -------------------------
st.title("🛡️ Auditoría Forense: Confrontación en Pantalla")
st.divider()
c1, c2, c3 = st.columns([1,1,2])
with c1: st.metric("PDFs detectados", len(st.session_state.pdf_files))
with c2: st.metric("¿Excel detectado?", "Sí" if st.session_state.ex_file is not None else "No")
with c3:
    if st.session_state.last_error:
        st.error("La ejecución anterior terminó con error. Revise el detalle más abajo.")
    elif st.session_state.ex_file is None and len(st.session_state.pdf_files) == 0:
        st.info("Sube la **Matriz .xlsx** y **los PDFs**. Luego marca **Sí** y pulsa **“✅ Procesar ahora”**.")
    elif st.session_state.ex_file is None:
        st.warning("Falta la **Matriz .xlsx**.")
    elif len(st.session_state.pdf_files) == 0:
        st.warning("Faltan **PDFs**.")
    elif not st.session_state.confirmed:
        st.success("Todo listo. Marca **Sí** y pulsa **“✅ Procesar ahora”**.")
    elif st.session_state.processing:
        st.info("Procesando… no cierres esta página.")
    elif st.session_state.process_done:
        st.success("Preparación completada.")

# -------------------------
# PREPARACIÓN (con progreso y captura de errores)
# -------------------------
def run_preparation():
    t0 = time.time()
    status = st.status("Iniciando…", expanded=True)
    bar = st.progress(0)
    log = st.empty()

    # 1) Indexar PDFs por CP
    status.update(label="Indexando PDFs por CP…", state="running")
    CP_PAT = re.compile(r"CP[_\-\s]?(\d+)", re.IGNORECASE)

    def extract_cp(name: str):
        m = CP_PAT.search(name)
        if m:
            return m.group(1).lstrip("0") or "0"
        d = re.sub(r"\D", "", name)
        return d.lstrip("0") or None

    pdf_files = st.session_state.pdf_files
    total = len(pdf_files)
    pdf_index = {}
    idx_rows = []

    for i, f in enumerate(pdf_files, start=1):
        try:
            cp_id = extract_cp(f.name)
            size_mb = None
            try:
                size_mb = round(getattr(f, "size", 0) / (1024*1024), 3)
            except Exception:
                pass
            if not cp_id:
                idx_rows.append({"archivo": f.name, "cp_extraido": None, "estado": "SIN_CP_EN_NOMBRE", "tam_MB": size_mb})
            else:
                pdf_index.setdefault(cp_id, []).append(f)
                idx_rows.append({"archivo": f.name, "cp_extraido": cp_id, "estado": "OK", "tam_MB": size_mb})
        except Exception as e:
            idx_rows.append({"archivo": f.name, "cp_extraido": None, "estado": f"ERROR: {e}", "tam_MB": None})
        if i % 10 == 0 or i == total:
            log.write(f"Indexados {i}/{total} PDFs…")
        bar.progress(int(i * 100 / max(1, total)))

    # 2) Leer Excel
    status.update(label="Leyendo matriz (.xlsx)…", state="running")
    try:
        df = pd.read_excel(st.session_state.ex_file)
    except Exception as e:
        status.update(label="Error leyendo matriz", state="error")
        st.session_state.last_error = f"Lectura Excel: {e}"
        st.exception(e)
        st.session_state.processing = False
        return

    # 3) Detectar columnas
    try:
        c_cp = find_col(df, ["CP","CPAGO","COMPAGO","COMPROBANTE"])
    except KeyError:
        c_cp = df.columns[0]
        st.toast("No se halló columna CP; se usará la primera columna.", icon="⚠️")
    try:
        c_fec = find_col(df, ["FECHA","EMISION","FECEMISION","FECDOC"], required=False)
    except KeyError:
        c_fec = None

    # 4) Tablero rápido
    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric("Filas matriz", len(df))
    cc2.metric("PDFs en buffer", len(pdf_files))
    cc3.metric("Revisados OK", sum(1 for v in st.session_state.db_pericial.values() if v.get("Resultado_Final")=="OK"))
    if c_fec:
        fec = pd.to_datetime(df[c_fec], errors="coerce")
        df["_ANIO"] = fec.dt.year
        df["_TRIM"] = fec.dt.quarter
        anio_obj = st.session_state.anio_obj
        tri_obj = st.session_state.tri_obj
        if tri_obj is None:
            traslape = df[df["_ANIO"] != anio_obj]
        else:
            traslape = df[(df["_ANIO"] != anio_obj) | (df["_TRIM"] != tri_obj)]
        cc4.metric("Alertas de periodo", len(traslape), delta_color="inverse")
    else:
        traslape = pd.DataFrame()
        cc4.metric("Alertas de periodo", 0)

    # 5) Cruce matriz ↔ PDFs
    status.update(label="Cruzando Matriz ↔ PDFs…", state="running")
    cr_rows = []
    for i in range(len(df)):
        fila_cp = str(df.iloc[i][c_cp])
        id_cp = get_clean_id(fila_cp)
        encontrados = len(pdf_index.get(id_cp, []))
        cr_rows.append({
            "fila": i+1, "cp_matriz": fila_cp, "cp_id": id_cp,
            "pdfs_encontrados": encontrados,
            "estado": "OK" if encontrados > 0 else "SIN_PDF"
        })
        if (i+1) % 20 == 0 or (i+1) == len(df):
            log.write(f"Cruce {i+1}/{len(df)} (CP {id_cp})…")
        bar.progress(int((i+1) * 100 / max(1, len(df))))

    # 6) PDFs sobrantes
    set_mat = {get_clean_id(df.iloc[i][c_cp]) for i in range(len(df))}
    leftovers = []
    for cp_id, files in pdf_index.items():
        if cp_id not in set_mat:
            for f in files:
                leftovers.append({"archivo": f.name, "cp_id": cp_id, "estado": "PDF_SIN_FILA"})

    # 7) Guardar resultados
    st.session_state.index_rows = idx_rows
    st.session_state.cross_rows = cr_rows
    st.session_state.leftovers = leftovers
    st.session_state.pdf_index = pdf_index
    st.session_state.df_cache = df
    st.session_state.c_cp = c_cp
    st.session_state.c_fec = c_fec
    st.session_state.last_error = None

    status.update(
        label=f"Preparación lista en {time.time()-t0:.1f}s — Faltantes: {(pd.DataFrame(cr_rows)['estado']=='SIN_PDF').sum()} | Sobrantes: {len(leftovers)}",
        state="complete"
    )
    st.toast("Preparación completada.", icon="✅")

    st.session_state.processing = False
    st.session_state.process_done = True

# Disparo del proceso (cuando confirmas “Sí” y pulsas el botón)
try:
    if st.session_state.processing and not st.session_state.process_done and st.session_state.confirmed:
        run_preparation()
except Exception as e:
    st.session_state.last_error = f"Excepción en preparación: {e}"
    st.error("Ocurrió un error durante el procesamiento. Detalle abajo.")
    st.exception(e)
    st.code("".join(traceback.format_exc()), language="python")
    st.session_state.processing = False
    st.session_state.process_done = False

# -------------------------
# RESÚMENES + VISOR + FORM (cuando termina)
# -------------------------
if st.session_state.process_done and st.session_state.df_cache is not None:
    df = st.session_state.df_cache
    c_cp = st.session_state.c_cp
    pdf_index = st.session_state.pdf_index

    st.divider()
    st.markdown("### 📋 Indexación de PDFs")
    df_idx = pd.DataFrame(st.session_state.index_rows)
    st.dataframe(df_idx, use_container_width=True, hide_index=True)

    st.markdown("### 🔎 Cruce Matriz ↔ PDFs")
    df_cru = pd.DataFrame(st.session_state.cross_rows)
    st.dataframe(df_cru, use_container_width=True, hide_index=True)

    if st.session_state.leftovers:
        st.markdown("### 🗂️ PDFs sin fila asociada (Sobrantes)")
        st.dataframe(pd.DataFrame(st.session_state.leftovers), use_container_width=True, hide_index=True)

    colx, coly, colz = st.columns(3)
    with colx:
        st.download_button("⬇️ Indexación (CSV)",
                           data=df_idx.to_csv(index=False).encode("utf-8"),
                           file_name="indexacion_pdfs.csv", mime="text/csv",
                           use_container_width=True)
    with coly:
        st.download_button("⬇️ Cruce (CSV)",
                           data=df_cru.to_csv(index=False).encode("utf-8"),
                           file_name="cruce_matriz_pdfs.csv", mime="text/csv",
                           use_container_width=True)
    with colz:
        if st.session_state.leftovers:
            st.download_button("⬇️ Sobrantes (CSV)",
                               data=pd.DataFrame(st.session_state.leftovers).to_csv(index=False).encode("utf-8"),
                               file_name="pdfs_sobrantes.csv", mime="text/csv",
                               use_container_width=True)

    # Visor + selección + formulario
    st.divider()
    idx = st.selectbox(
        "🎯 Registro a Auditar:",
        range(len(df)),
        format_func=lambda x: f"Fila {x+1} | CP: {df.iloc[x][c_cp]}"
    )
    fila = df.iloc[idx]
    id_actual = get_clean_id(fila[c_cp])

    col_pdf, col_form = st.columns([1.5, 1])
    with col_pdf:
        st.subheader("🖼️ Visor de Evidencia")
        cand = pdf_index.get(id_actual, [])
        if len(cand) == 0:
            st.error(f"❌ Sin PDF para CP: {fila[c_cp]}")
        elif len(cand) == 1:
            display_pdf(cand[0])
        else:
            nombre = st.selectbox("Múltiples PDFs para este CP", [f.name for f in cand])
            sel = next(x for x in cand if x.name == nombre)
            display_pdf(sel)

    with col_form:
        st.subheader("🖋️ Veredicto y Datos")
        st.dataframe(fila.to_frame("Valor").head(10), use_container_width=True)

        with st.form(key="form_auditoria", clear_on_submit=False):
            st.markdown("### Validaciones por documento")
            # CP
            st.subheader("CP")
            cp_num_pdf = st.text_input("Número de CP (PDF)", value="")
            cp_fecha_pdf = st.text_input("Fecha CP (PDF)", value="")
            cp_valor_pdf = st.number_input("Valor CP (PDF)", min_value=0.0, step=0.01, format="%.2f")
            cp_ok = st.selectbox("Validación CP", ["OK","MAL","NO-LEÍBLE"], index=0)
            # CC
            st.subheader("CC")
            cc_num_pdf = st.text_input("Número de CC (PDF)", value="")
            cc_fecha_pdf = st.text_input("Fecha CC (PDF)", value="")
            cc_valor_debe = st.number_input("Valor Debe (pago)", min_value=0.0, step=0.01, format="%.2f")
            cc_amort_anticipo = st.number_input("Amortización anticipo", min_value=0.0, step=0.01, format="%.2f")
            cc_multas = st.number_input("Multas", min_value=0.0, step=0.01, format="%.2f")
            cc_ok = st.selectbox("Validación CC", ["OK","MAL","NO-LEÍBLE"], index=0)
            # Factura
            st.subheader("Factura")
            fac_ruc = st.text_input("RUC", value="")
            fac_num = st.text_input("Número de Factura", value="")
            fac_fecha = st.text_input("Fecha de Factura", value="")
            fac_subtotal = st.number_input("Subtotal", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_pct = st.number_input("IVA %", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_val = st.number_input("IVA Valor", min_value=0.0, step=0.01, format="%.2f")
            fac_total = st.number_input("Total", min_value=0.0, step=0.01, format="%.2f")
            fac_ok = st.selectbox("Validación Factura", ["OK","MAL","NO-LEÍBLE"], index=0)
            # Retención
            st.subheader("Retención")
            ret_num = st.text_input("Número Retención", value="")
            ret_renta_pct = st.number_input("% Renta", min_value=0.0, step=0.01, format="%.2f")
            ret_renta_val = st.number_input("Valor Renta", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_pct = st.number_input("% IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_val = st.number_input("Valor IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_ok = st.selectbox("Validación Retención", ["OK","MAL","NO-LEÍBLE"], index=0)
            # SPI
            st.subheader("SPI")
            spi_benef = st.text_input("Beneficiario (SPI)", value="")
            spi_valor = st.number_input("Valor Pagado (SPI)", min_value=0.0, step=0.01, format="%.2f")
            spi_ok = st.selectbox("Validación SPI", ["OK","MAL","NO-LEÍBLE"], index=0)
            # Cruces y Hallazgos
            st.subheader("Cruces y Hallazgos")
            coincide_valores = st.selectbox("¿CP = CC = SPI (valor)?", ["Sí","No","No determinable"], index=0)
            fuera_anio = st.checkbox("Factura fuera del año en curso")
            fuera_trimestre = st.checkbox("Factura fuera del trimestre analizado")
            falta_pdf = st.checkbox("Falta PDF para esta línea")
            sobra_pdf = st.checkbox("Existe PDF sin línea asociada")
            hallazgos = st.text_area("Hallazgos")
            claridad = st.slider("Claridad (1–10)", 1, 10, 7)
            resultado_final = st.selectbox("Resultado final", ["OK","MAL","NO-LEÍBLE","INCOMPLETO"], index=0)

            submit = st.form_submit_button("💾 GUARDAR RESULTADO")
            if submit:
                clave = f"{get_clean_id(fila[c_cp])}::fila{idx+1}"
                st.session_state.db_pericial[clave] = {
                    "CP_Num_Matriz": str(fila[c_cp]),
                    "CP_Num_PDF": cp_num_pdf, "CP_Fecha": cp_fecha_pdf, "CP_Valor": cp_valor_pdf, "CP_OK": cp_ok,
                    "CC_Num": cc_num_pdf, "CC_Fecha": cc_fecha_pdf, "CC_Valor_Debe": cc_valor_debe,
                    "CC_Amort_Anticipo": cc_amort_anticipo, "CC_Multas": cc_multas, "CC_OK": cc_ok,
                    "Factura_RUC": fac_ruc, "Factura_Num": fac_num, "Factura_Fecha": fac_fecha,
                    "Factura_Subtotal": fac_subtotal, "Factura_IVA_%": fac_iva_pct,
                    "Factura_IVA_Valor": fac_iva_val, "Factura_Total": fac_total, "Factura_OK": fac_ok,
                    "Ret_Num": ret_num, "Ret_Renta_%": ret_renta_pct, "Ret_Renta_Val": ret_renta_val,
                    "Ret_IVA_%": ret_iva_pct, "Ret_IVA_Val": ret_iva_val, "Ret_OK": ret_ok,
                    "SPI_Beneficiario": spi_benef, "SPI_Valor": spi_valor, "SPI_OK": spi_ok,
                    "Coincide_CP_CC_SPI": coincide_valores,
                    "Alerta_Fuera_Año": fuera_anio, "Alerta_Fuera_Trimestre": fuera_trimestre,
                    "Falta_PDF": falta_pdf, "Sobra_PDF": sobra_pdf,
                    "Hallazgos": hallazgos, "Claridad_1_10": claridad,
                    "Resultado_Final": resultado_final
                }
                st.success("Guardado.")
                st.rerun()

    st.divider()
    if st.button("📊 REPORTE DE FIDELIDAD"):
        rep = pd.DataFrame.from_dict(st.session_state.db_pericial, orient="index")
        st.dataframe(rep, use_container_width=True)
        if not rep.empty:
            st.download_button("⬇️ Descargar (CSV)",
                               data=rep.to_csv().encode("utf-8"),
                               file_name="reporte_fidelidad.csv", mime="text/csv")

# -------------------------
# Si hubo error en preparación, muéstralo abajo
# -------------------------
if st.session_state.last_error:
    st.divider()
    st.error("Último error capturado:")
    st.write(st.session_state.last_error)
